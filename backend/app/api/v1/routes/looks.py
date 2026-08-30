"""The four `/looks` routes: make one, list them, change one, wear one.

`POST /suggest` is the route that puts Stage 2 together — wardrobe → forecast →
rule → serialise → stylist → validate → persist → hydrate, in `STAGE-2` 2.7's
order. `GET ""` and `PATCH /{look_id}` are 3.2's and are the first things in
this project to read a `looks` row back after the request that wrote it: every
suggestion made since 2.7 becomes visible here.

`POST /{look_id}/wear` is 3.4's and is the only route here that writes a row
it did not read into Python first: the guard against double-counting is a
conditional `UPDATE`, so two rapid taps race in the database rather than in
this module.

The three reads share `_hydrate`, which is the whole of what makes a persisted
look into a wire one. `Look` carries no `relationship()` — following `Item`,
which names `user_id` and stops — so the items come from an explicit join in
`look_items.position` order, and that is the second reader `position` was
written for at 2.7. Everything it calls was built to be called
from here: `services/stylist.py` holds no `Session` and no clock, `build_rule`
and `summarize_forecast` are pure, and `validate_look_response` judges without
raising. What is left for this module is the three things only a request can
decide — **which** wardrobe the model sees, whether to spend the one retry, and
what a failure is worth on the wire.
"""

import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import date as date_type
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from openai import OpenAIError
from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import ApiError
from app.enums import ItemStatus
from app.models.item import Item
from app.models.look import FEEDBACK_DOWN, FEEDBACK_UP, Look, LookItem
from app.models.user import User
from app.schemas.item import ItemResponse
from app.schemas.look import (
    LookListResponse,
    LookResponse,
    LookSuggestRequest,
    LookSuggestResponse,
    LookUpdate,
    LookWearRequest,
    MissingPieceResponse,
)
from app.services.stylist import Look as StylistLook
from app.services.stylist import (
    LookValidation,
    StylistContext,
    StylistResponse,
    suggest_looks,
    validate_look_response,
)
from app.services.weather import (
    FORECAST_HORIZON_DAYS,
    ForecastOutOfRangeError,
    ForecastProviderError,
    build_rule,
    get_forecast,
    summarize_forecast,
)

router = APIRouter(prefix="/looks", tags=["looks"])

logger = logging.getLogger(__name__)

# `04-API-SPEC.md`'s threshold, counted over the wardrobe that is actually sent
# rather than over every `ready` row: six garments the stylist never sees cannot
# make an outfit, so counting them would answer `502` where `400` is the truth.
# `DECISIONS.md` 172.
MIN_WARDROBE_ITEMS = 6
MIN_RATED_LOOKS = 3
PREFERENCE_LIMIT = 3
RECENT_WEAR_DAYS = 3

# Every member of `Category`, which is nine since 2.6a appended the last two.
# The block prints these to the model rather than the raw enum values, so a
# category missing here is a `KeyError` and a 500 rather than an ugly line —
# and `Item.fit IS NOT NULL` below selects precisely the six categories that
# carry a fit, two of which are the ones 2.6a added. `test_looks_suggest.py`
# pins this dictionary against the vocabulary, because nothing else compares
# them. The three mass nouns keep their singular form.
_CATEGORY_NAMES = {
    "top": "tops",
    "bottom": "bottoms",
    "dress": "dresses",
    "outerwear": "outerwear",
    "shoes": "shoes",
    "bag": "bags",
    "accessory": "accessories",
    "swimwear": "swimwear",
    "sleepwear": "sleepwear",
}


def _stylist_failed() -> ApiError:
    return ApiError(
        status.HTTP_502_BAD_GATEWAY,
        "stylist_failed",
        "I couldn't put a look together just now — try again.",
    )


def _wardrobe(db: Session, user: User) -> list[ItemResponse]:
    """Every item the stylist is allowed to see, in a stable order.

    Three filters, and `AUDITS.md` O-21 is the whole of the third: `ready`
    because a row still being tagged has no attributes to style with, not
    archived because `DELETE /items/{id}` is an archive, and not swimwear or
    sleepwear because `01-ARCHITECTURE.md` promises exactly that exclusion and
    2.6a gave it two vocabulary members to match on. The list comes from
    `settings`, so emptying it sends the whole wardrobe.

    A row whose `category` is `NULL` is dropped by `NOT IN` rather than kept —
    SQL's three-valued logic, left alone deliberately. `category` is in
    `REQUIRED_TAG_FIELDS`, so a `ready` row has one, and an item with no
    category is one the model could not place anyway.

    Ordered oldest first so two identical requests build the same prompt, which
    is what `STAGE-2`'s "two identical requests produce a valid look both times"
    measures.
    """
    rows = db.scalars(
        select(Item)
        .where(
            Item.user_id == user.id,
            Item.status == ItemStatus.READY,
            Item.is_archived.is_(False),
            Item.category.not_in(tuple(settings.stylist_excluded_categories)),
        )
        .order_by(Item.created_at, Item.short_id)
    ).all()
    return [ItemResponse.model_validate(row) for row in rows]


def _anchor(request: LookSuggestRequest, wardrobe: Sequence[ItemResponse]) -> ItemResponse | None:
    """The anchored row, matched against the wardrobe that is about to be sent.

    `04-API-SPEC.md` asks for a `422` when the anchor "does not belong to this
    user", and this is that check widened by one step on purpose. A row she owns
    but the stylist never sees — still `processing`, archived, or in an excluded
    category — cannot appear in a look either: rule 1 would refuse the id as a
    hallucination, so letting it through buys two model calls and a `502` for a
    question one lookup answers here, before anything leaves the process.

    Its own code rather than `validation_error`, because this is the one `422`
    on this endpoint a correct client can provoke — the user tapped "Style
    around this" on a real garment — and the client has something to say about
    it that "check the occasion and the date" does not cover.
    """
    if request.anchor_item_id is None:
        return None

    anchor = next((item for item in wardrobe if item.id == request.anchor_item_id), None)
    if anchor is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "anchor_unavailable",
            "anchor_item_id: that item is not one this wardrobe can be styled around.",
        )
    return anchor


def _locked(
    request: LookSuggestRequest, wardrobe: Sequence[ItemResponse]
) -> tuple[ItemResponse, ...]:
    """The locked rows, matched against the wardrobe that is about to be sent.

    `_anchor`'s lookup, three fields along and refused for the same two
    reasons: a row belonging to another account is `04-API-SPEC.md`'s own
    `422`, and one this account owns but the stylist never sees cannot appear
    in a look either — rule 1 would call the id a hallucination, so letting it
    through buys two model calls and a `502`.

    Its own code rather than `validation_error`, and it is the second `422` on
    this endpoint a correct client can provoke: the ↻ badge locks the garments
    that were on screen a moment ago, and one of them can have been archived
    from another tab since. `CONVENTIONS.md`, `DECISIONS.md` 177.
    """
    by_id = {item.id: item for item in wardrobe}
    locked: list[ItemResponse] = []
    for item_id in request.locked_item_ids:
        item = by_id.get(item_id)
        if item is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "locked_unavailable",
                "locked_item_ids: one of those items is no longer part of this wardrobe.",
            )
        locked.append(item)
    return tuple(locked)


def _excluded(request: LookSuggestRequest, wardrobe: Sequence[ItemResponse]) -> tuple[str, ...]:
    """The rejected rows' `short_id`s, and an unknown id is dropped rather than refused.

    The asymmetry with `_locked` is `04-API-SPEC.md`'s: it asks for a `422` on
    the anchor and on the locks and for nothing here, and the reason survives
    reading. A lock and an anchor are promises about what the look *will*
    contain, so an id that names no wardrobe row makes them unkeepable; an
    exclusion is a promise about what it will not, and an item the stylist is
    never shown is already excluded from every look it can build.
    """
    by_id = {item.id: item for item in wardrobe}
    return tuple(
        by_id[item_id].short_id for item_id in request.exclude_item_ids if item_id in by_id
    )


def _preference_attributes(db: Session, user: User, feedback: int) -> list[str]:
    frequency = func.count(func.distinct(Look.id))
    rows = db.execute(
        select(Item.category, Item.fit)
        .select_from(Look)
        .join(LookItem, LookItem.look_id == Look.id)
        .join(Item, Item.id == LookItem.item_id)
        .where(
            Look.user_id == user.id,
            Look.feedback == feedback,
            Item.fit.is_not(None),
            # An archived garment cannot be recommended, so a preference
            # learned from it can only describe outfits the stylist is unable
            # to build. `DELETE /items/{id}` is an archive, which makes this
            # the same filter `_wardrobe` applies, one table along.
            Item.is_archived.is_(False),
        )
        .group_by(Item.category, Item.fit)
        .having(frequency >= 2)
        .order_by(frequency.desc(), Item.category, Item.fit)
        .limit(PREFERENCE_LIMIT)
    ).all()
    return [f"{fit} {_CATEGORY_NAMES[category]}" for category, fit in rows]


def _preferences(
    db: Session, user: User, wardrobe: Sequence[ItemResponse], for_date: date_type
) -> str | None:
    """The learned-preferences block, or `None` while the signal is still noise.

    **Both thumbs count toward the threshold.** `STAGE-3` 3.5 said "3 liked
    looks" and the guard is three *rated* ones: a thumbs-down is as much a
    statement about this wardrobe as a thumbs-up, it is half of what the block
    prints, and `NULL` is the only value that means nothing was said.
    `DECISIONS.md` 185.

    `for_date` rather than the server's today, which is what the recency window
    is measured back from — see the query below.
    """
    rated_looks = (
        db.scalar(
            select(func.count())
            .select_from(Look)
            .where(Look.user_id == user.id, Look.feedback.is_not(None))
        )
        or 0
    )
    if rated_looks < MIN_RATED_LOOKS:
        return None

    lines = ["USER PREFERENCES (learned from rated looks):"]
    liked = _preference_attributes(db, user, FEEDBACK_UP)
    if liked:
        lines.append(f"- Liked: {', '.join(liked)}")
    disliked = _preference_attributes(db, user, FEEDBACK_DOWN)
    if disliked:
        lines.append(f"- Disliked: {', '.join(disliked)}")

    # Measured back from the day being dressed for, not from the server's
    # today. Two reasons, and the second is the one that bites: asking on
    # Wednesday for Saturday's outfit is asking what will be stale *on
    # Saturday*, and `date.today()` here is the server's calendar day, which
    # `DECISIONS.md` 184 established is not reliably the user's. The window is
    # closed at both ends — `worn_at` accepts a future date (184 again), so
    # without an upper bound a garment worn next week would be reported as
    # recently worn for a look built today. `DECISIONS.md` 185.
    wardrobe_ids = {item.id for item in wardrobe}
    recent_since = for_date - timedelta(days=RECENT_WEAR_DAYS - 1)
    recently_worn = db.scalars(
        select(Item.short_id)
        .where(
            Item.id.in_(wardrobe_ids),
            Item.last_worn_at >= recent_since,
            Item.last_worn_at <= for_date,
        )
        .order_by(Item.last_worn_at.desc(), Item.short_id)
    ).all()
    if recently_worn:
        lines.append(f"- Recently worn (avoid repeating): {', '.join(recently_worn)}")

    return "\n".join(lines)


async def _context(
    db: Session,
    request: LookSuggestRequest,
    user: User,
    wardrobe: Sequence[ItemResponse],
    anchor: ItemResponse | None,
    locked: Sequence[ItemResponse],
    excluded_ids: tuple[str, ...],
) -> StylistContext:
    """The request, the profile and the sky, in the shape `suggest_looks` takes.

    The forecast is for the user's **home** location: `04-API-SPEC.md`'s body
    carries no coordinates, and `DECISIONS.md` 151 made the three home columns
    one field, so either both numbers are there or neither is.
    """
    if user.home_lat is None or user.home_lon is None:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "home_location_missing",
            "Set your home city before asking for a look — the weather decides half of it.",
        )

    try:
        forecast = await get_forecast(user.home_lat, user.home_lon, request.date)
    except ForecastOutOfRangeError as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "forecast_unavailable",
            f"A forecast is only available up to {FORECAST_HORIZON_DAYS} days ahead.",
        ) from exc
    except ForecastProviderError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "forecast_unavailable",
            "The forecast service is unavailable. Try again shortly.",
        ) from exc

    return StylistContext(
        date=request.date,
        occasion=request.occasion,
        forecast_summary=summarize_forecast(forecast),
        weather_rule=build_rule(forecast.temp_max_c, forecast.precip_mm, forecast.wind_kph),
        notes=request.notes,
        include_outerwear=request.include_outerwear,
        # The `short_id`, which is the only spelling the prompt and rule 7 use.
        anchor_id=anchor.short_id if anchor is not None else None,
        locked_ids=tuple(item.short_id for item in locked),
        excluded_ids=excluded_ids,
        replace_role=request.replace_role,
        height_cm=user.height_cm,
        style_notes=user.style_notes,
        preferences=_preferences(db, user, wardrobe, request.date),
    )


async def _attempt(
    wardrobe: Sequence[ItemResponse],
    context: StylistContext,
    attempt: int,
    correction: str | None = None,
) -> LookValidation:
    """One model call, judged, with everything a failure would need reported.

    Both attempts log at `INFO` rather than only the failing one, because the
    question this endpoint could not answer before was never "did it fail" — the
    `502` already said that — but "how often, how slowly, and against how big a
    wardrobe". A line only on failure cannot answer any of the three, since it
    has nothing to be compared against.

    `item_ids` is logged flat because rule 1 is the rule that fires most and the
    id it rejected is the whole diagnosis: an invented id and a real id the model
    shifted the case of are the same message and different bugs.
    """
    started = time.monotonic()
    validation = validate_look_response(
        await suggest_looks(wardrobe, context, correction=correction), wardrobe, context
    )
    logger.info(
        "Stylist attempt finished",
        extra={
            "attempt": attempt,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            # The model actually used, not the pin: `.env` can and does override
            # `OPENAI_STYLIST_MODEL`, and a rejection rate is meaningless beside
            # the name of a model that was not called.
            "model": settings.OPENAI_STYLIST_MODEL,
            "wardrobe_items": len(wardrobe),
            "violation": validation.violation,
            "item_ids": [
                item_id for look in validation.response.looks for item_id in look.item_ids
            ],
        },
    )
    return validation


async def _judged(wardrobe: Sequence[ItemResponse], context: StylistContext) -> LookValidation:
    """One call, and a second one only when the first broke a named rule.

    The retry exists to carry a violation back to the model, so a failure with
    no violation to name does not spend it: a `ValueError` means no usable
    answer arrived and an `OpenAIError` means none arrived at all, and both are
    `502` at the caller without a second trip through the whole wardrobe.
    `03-AI-CONTRACTS.md` says the same thing about a timeout — "the request is
    not retried automatically". `DECISIONS.md` 171.
    """
    validation = await _attempt(wardrobe, context, attempt=1)
    if validation.ok:
        return validation

    return await _attempt(wardrobe, context, attempt=2, correction=validation.violation)


def _persist(
    db: Session,
    user: User,
    context: StylistContext,
    looks: Sequence[StylistLook],
    known: Mapping[str, ItemResponse],
) -> list[LookResponse]:
    """The rows, and the same looks hydrated for the wire.

    One pass, because the wire object carries the `id` the insert generated and
    reading it twice would mean holding the answer in two shapes. `flush`
    rather than `commit` inside the loop: `look_items.look_id` needs the id, and
    a look and its items are one row or none.

    `occasion` is stored from the **request**, not from the model's echo of it.
    The column now holds a closed vocabulary (`DECISIONS.md` 168) and nothing
    validates what the model answered there, so the one value that is certainly
    legal is the one the user sent.

    `position` is the model's own ordering, which is otherwise destroyed — the
    composite primary key imposes none. `role` is left `NULL`: it has no
    vocabulary, `04`'s six values do not cover `dress`, and 2.11 is the task
    that first reads one. `AUDITS.md` O-25, `DECISIONS.md` 170.
    """
    suggested: list[LookResponse] = []

    for answer in looks:
        row = Look(
            user_id=user.id,
            title=answer.title,
            occasion=context.occasion,
            reasoning=answer.reasoning,
            weather_note=answer.weather_note,
            for_date=context.date,
        )
        db.add(row)
        db.flush()

        db.add_all(
            [
                LookItem(look_id=row.id, item_id=known[item_id].id, position=position)
                for position, item_id in enumerate(answer.item_ids)
            ]
        )

        suggested.append(
            LookResponse(
                id=row.id,
                occasion=context.occasion,
                title=answer.title,
                items=[known[item_id] for item_id in answer.item_ids],
                reasoning=answer.reasoning,
                weather_note=answer.weather_note,
                # Read off the row rather than written as False. The INSERT
                # brings the server default back (test_server_defaults.py), so
                # this is what the database actually holds; a literal here
                # would be a second copy of `0002`'s DEFAULT with nothing
                # comparing them.
                is_saved=row.is_saved,
                # Always None here — no INSERT writes it and the column has no
                # default — and read off the row anyway, for `is_saved`'s
                # reason. 3.5 counts unrated looks, so this is a value rather
                # than an absence.
                feedback=row.feedback,
                # Also always None here, and read off the row for the same
                # reason: a look is suggested before it can have been worn.
                worn_at=row.worn_at,
            )
        )

    db.commit()
    return suggested


def _response(looks: list[LookResponse], answer: StylistResponse) -> LookSuggestResponse:
    return LookSuggestResponse(
        looks=looks,
        missing_pieces=[
            MissingPieceResponse(
                category=piece.category, description=piece.description, reason=piece.reason
            )
            for piece in answer.missing_pieces
        ],
        message=answer.message,
    )


@router.post("/suggest")
async def suggest_look(
    request: LookSuggestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LookSuggestResponse:
    """`async def`, unlike the routes that only touch the database.

    Two of the three calls it makes leave the process — Open-Meteo and OpenAI,
    the second of them for four to eight seconds — and both are awaited HTTP.
    `CONVENTIONS.md` puts a blocking third-party call in a synchronous `def`
    for the opposite reason; there is nothing blocking here but the two short
    queries, which is the trade `GET /weather` already makes through
    `get_current_user`.
    """
    wardrobe = _wardrobe(db, current_user)
    # Before the forecast as well as before the model: `06-TESTING-STRATEGY.md`
    # asks for a test proving no AI call is attempted, and a small wardrobe is
    # knowable without spending anything at all.
    if len(wardrobe) < MIN_WARDROBE_ITEMS:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "wardrobe_too_small",
            f"Add at least {MIN_WARDROBE_ITEMS} items so I have something to work with.",
        )

    # Beside the small-wardrobe check and for its reason: all four are
    # answerable from rows already in hand, so a request that cannot be served
    # costs neither the forecast nor the model.
    context = await _context(
        db,
        request,
        current_user,
        wardrobe,
        _anchor(request, wardrobe),
        _locked(request, wardrobe),
        _excluded(request, wardrobe),
    )

    try:
        validation = await _judged(wardrobe, context)
    except ValueError as exc:
        # The four measured leniencies of `DECISIONS.md` 161 arrive here: the
        # model answered, and what it answered is not usable.
        logger.warning("The stylist gave no usable answer", extra={"error": str(exc)})
        raise _stylist_failed() from exc
    except OpenAIError as exc:
        logger.warning("The stylist provider did not answer", extra={"error": str(exc)})
        raise _stylist_failed() from exc

    if not validation.ok:
        logger.warning(
            "The stylist failed validation twice", extra={"violation": validation.violation}
        )
        raise _stylist_failed()

    # From `validation.response` and never from the raw answer: the ids were
    # upper-cased there, and `DECISIONS.md` 164 put normalisation in one place
    # so a row and a lookup cannot disagree about the case of an id.
    answer = validation.response
    known = {item.short_id: item for item in wardrobe}
    return _response(_persist(db, current_user, context, answer.looks, known), answer)


def _hydrate(db: Session, rows: Sequence[Look]) -> list[LookResponse]:
    """Persisted looks, with their items, in the model's own order.

    One query for every look rather than one per look: the list endpoint
    returns up to two hundred, and the per-look shape of this is the N+1 that
    `idx_look_items_item_id` was built at 3.1 to make survivable rather than
    invisible.

    Ordered by `look_items.position`, which is the second reader that column
    was written for — 2.7 recorded it as destroyed-at-persistence-if-unwritten
    and 2.11 read it on the card. Without the `order_by` the join returns rows
    in whatever order the planner likes, and a saved look would relayout
    between two reloads.
    """
    if not rows:
        return []

    look_ids = [row.id for row in rows]
    pairs = db.execute(
        select(LookItem.look_id, Item)
        .join(Item, Item.id == LookItem.item_id)
        .where(LookItem.look_id.in_(look_ids))
        .order_by(LookItem.look_id, LookItem.position)
    ).all()

    items: dict[uuid.UUID, list[ItemResponse]] = {look_id: [] for look_id in look_ids}
    for look_id, item in pairs:
        items[look_id].append(ItemResponse.model_validate(item))

    return [
        LookResponse(
            id=row.id,
            occasion=row.occasion,
            title=row.title,
            items=items[row.id],
            reasoning=row.reasoning,
            weather_note=row.weather_note,
            is_saved=row.is_saved,
            feedback=row.feedback,
            worn_at=row.worn_at,
        )
        for row in rows
    ]


def _owned(db: Session, look_id: uuid.UUID, user_id: uuid.UUID) -> Look:
    look = db.scalar(select(Look).where(Look.id == look_id, Look.user_id == user_id))
    if look is None:
        # Another account's look and one that never existed are the same
        # answer, which is `06-TESTING-STRATEGY.md`'s isolation requirement and
        # `items.py`'s `_owned` unchanged: a 403 would confirm the row exists.
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", "Look not found.")
    return look


@router.get("")
def list_looks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    is_saved: bool | None = None,
    from_date: date_type | None = None,
    to_date: date_type | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LookListResponse:
    # `04-API-SPEC.md` names a fourth filter, `trip_id`, and it is not here:
    # the column arrives with migration `0005`, and a parameter that filters on
    # a column the database lacks is a 500 rather than an empty list.
    filters: list[ColumnElement[bool]] = [Look.user_id == current_user.id]
    if is_saved is not None:
        filters.append(Look.is_saved.is_(is_saved))
    if from_date is not None:
        filters.append(Look.for_date >= from_date)
    if to_date is not None:
        filters.append(Look.for_date <= to_date)

    total = db.scalar(select(func.count()).select_from(Look).where(*filters)) or 0
    rows = db.scalars(
        # `GET /items`'s ordering with its tiebreaker dropped: `short_id` broke
        # the tie there because a whole upload shares one `created_at`, and
        # looks are written one per request. `id` is the tiebreaker instead —
        # arbitrary but stable, which is what keeps `offset` from repeating a
        # row between two pages.
        select(Look)
        .where(*filters)
        .order_by(Look.created_at.desc(), Look.id)
        .limit(limit)
        .offset(offset)
    ).all()

    return LookListResponse(looks=_hydrate(db, rows), total=total)


@router.patch("/{look_id}")
def update_look(
    look_id: uuid.UUID,
    changes: LookUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LookResponse:
    supplied = changes.model_dump(exclude_unset=True)
    if not supplied:
        # `update_item`'s guard, and here it defends less: no column records
        # that this endpoint ran, so an empty body would be a harmless 200.
        # It is refused anyway because a client that sent one meant something
        # by it, and a 200 says the row now reads the way it asked.
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "request: at least one field must be supplied.",
        )

    look = _owned(db, look_id, current_user.id)
    for field, value in supplied.items():
        setattr(look, field, value)
    db.commit()

    return _hydrate(db, [look])[0]


@router.post("/{look_id}/wear")
def wear_look(
    look_id: uuid.UUID,
    worn: LookWearRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LookResponse:
    """Record a look as worn, and age every garment in it by one wearing.

    **The guard is the `UPDATE`'s own `WHERE`, not a read in Python.** A
    `look.worn_at != worn.date` here would be two statements with a gap between
    them, and the gap is exactly wide enough for the second of two rapid taps:
    both read `NULL`, both increment, and the item counts are wrong with no
    error anywhere. `IS DISTINCT FROM` rather than `!=` because the column is
    `NULL` on every look that has never been worn, and `NULL != date` is `NULL`
    — which is not `TRUE`, so the first wearing would never be recorded.

    **What idempotency does and does not promise.** A repeat is a request whose
    date matches the date the row currently holds, and that is the whole of it:
    `looks.worn_at` is one column, so wearing a look on a second day overwrites
    the first and a *third* request naming the first day counts again. The look
    genuinely was worn twice, so incrementing is right; what is lost is the
    ability to notice that the first day has already been counted. A
    `look_wears` table would remember, and 3.4 deliberately does not build one.
    `DECISIONS.md` 184.

    `is_saved` is not consulted. The button lives on the saved-looks screen and
    that is a decision about the screen — encoding it here would make the API
    refuse a request no client sends, which is 3.3's reasoning about the thumbs
    living on the card only.
    """
    look = _owned(db, look_id, current_user.id)

    # `RETURNING` rather than `rowcount`, which SQLAlchemy types as belonging to
    # `CursorResult` while `Session.execute` is annotated `Result[Any]` — so the
    # obvious spelling needs a cast to type-check. This asks the same question
    # in one statement and answers it with a row or nothing.
    changed = (
        db.execute(
            update(Look)
            .where(Look.id == look.id, Look.worn_at.is_distinct_from(worn.date))
            .values(worn_at=worn.date)
            .returning(Look.id)
        ).scalar_one_or_none()
        is not None
    )

    if changed:
        db.execute(
            update(Item)
            .where(Item.id.in_(select(LookItem.item_id).where(LookItem.look_id == look.id)))
            .values(
                wear_count=Item.wear_count + 1,
                # GREATEST rather than assignment, so a correction entered for
                # last Tuesday cannot drag a garment worn yesterday backwards.
                # 3.5 reads this column to avoid recommending something worn in
                # the last three days, and a backwards move silently un-hides
                # it. COALESCE because GREATEST(NULL, date) is NULL in
                # PostgreSQL only when every argument is NULL — but the column
                # is NULL on a garment never worn, and being explicit here is
                # cheaper than depending on which of the two behaviours this
                # version implements.
                last_worn_at=func.greatest(func.coalesce(Item.last_worn_at, worn.date), worn.date),
            )
        )

    db.commit()
    # Refreshed rather than returned from the object in hand: the UPDATE went
    # round the identity map, so `look.worn_at` is still whatever was loaded.
    db.refresh(look)

    return _hydrate(db, [look])[0]

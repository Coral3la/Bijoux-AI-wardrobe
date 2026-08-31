"""The five `/trips` routes: pack one, list them, read one, throw one away, and
pack it again.

`POST /pack` is the route Stage 4 exists for, and it is thin on purpose:
`services/packing.py` does the geocoding, the forecast, the per-day rules, the
reuse arithmetic and the one model call, and hands back a `Trip` that has never
been added to a session. **What is left here is the eighth step 4.3 refused to
take** — the transaction — plus the two things only a request can decide: which
refusals are answerable before anything costs money, and what each of the
service's exceptions is worth on the wire.

**The write is one transaction and it runs only after the model has answered.**
Trip, then a `looks` row per day, then that look's `look_items`, then one
`commit`. `POST /looks/suggest`'s `_persist` is the same shape with one row and
no parent; `DECISIONS.md` 197 left this variant here rather than sharing it,
because a trip's write also has to reconcile the looks that were already under
the trip — which is the whole of `AUDITS.md` **O-32**.

**Repack detaches what a user marked and deletes the rest.** A trip look is an
ordinary look with a foreign key, so it can have been saved, rated or worn, and
three separate features read those columns. O-32's option 2: `trip_id = NULL`
for anything marked, `DELETE` for the rest, and the ordering matters more than
either — `pack_trip` runs **first**, and nothing is destroyed until it has
returned an answer. A `502` from the stylist must not empty a trip. `DELETE
/trips/{id}` takes O-32's option 1 instead and lets `0005`'s cascade run, which
is what the user asked for when they deleted the trip.

**`GET /trips` ships with no caller** and is built because `04-API-SPEC.md` is
authoritative and has carried the heading since Stage 0 — `GET
/me/locations/search`'s shape, recorded rather than quietly dropped.

Nothing here is rate-limited. `DECISIONS.md` 191 moved the counter to
`STAGE-5-qa-deploy.md` § 5.2 with all three of the table's limits, rather than
closing one row of it from inside this task; `POST /trips/pack` is the most
expensive call in the project and the exposure has a date and an owner.
"""

import datetime
import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from openai import OpenAIError
from sqlalchemy import ColumnElement, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.v1.routes._stylist_shared import (
    learned_preferences,
    styleable_wardrobe,
    stylist_failed,
)
from app.core.deps import get_current_user, get_db
from app.core.errors import ApiError
from app.models.item import Item
from app.models.look import Look, LookItem
from app.models.trip import Trip
from app.models.user import User
from app.schemas.item import ItemResponse
from app.schemas.look import LookResponse, MissingPieceResponse
from app.schemas.trip import (
    PackingList,
    TripDay,
    TripDetailResponse,
    TripListResponse,
    TripPackRequest,
    TripPackResponse,
    TripResponse,
)
from app.services.geocoding import GeocodingError
from app.services.packing import (
    DestinationNotFoundError,
    PackingResult,
    StylistRejectedError,
    TripRequest,
    pack_trip,
)
from app.services.weather import (
    FORECAST_HORIZON_DAYS,
    ForecastOutOfRangeError,
    ForecastProviderError,
)

router = APIRouter(prefix="/trips", tags=["trips"])

logger = logging.getLogger(__name__)

# `04-API-SPEC.md`'s threshold: `POST /looks/suggest`'s six plus two, counted
# over the wardrobe that is actually sent rather than over every `ready` row.
# The same `wardrobe_too_small` code with a different number, and the message
# names the number.
MIN_WARDROBE_ITEMS = 8

# `DECISIONS.md` 190. Fourteen rather than `weather.py`'s measured
# `FORECAST_HORIZON_DAYS = 15` is one day of margin against a horizon that rolls
# forward daily.
MAX_TRIP_DAYS = 14

# The three columns `AUDITS.md` O-32 is about, and the whole of what a repack
# refuses to destroy. `is_saved` puts a look on `/saved` (3.2), `feedback` is
# what the preference block counts (3.5), and `worn_at` has already incremented
# `items.wear_count` in a transaction this one cannot reverse.
_MARKED: ColumnElement[bool] = or_(
    Look.is_saved.is_(True), Look.feedback.is_not(None), Look.worn_at.is_not(None)
)


def _within_the_bound(start: datetime.date, end: datetime.date) -> None:
    """`trip_too_long`, which is **two** bounds under one message.

    `DECISIONS.md` 190 fixed the bound on the trip's last day — `end_date <=
    today + 14` — because the `start_date` reading it replaced admitted a
    fourteen-day trip ending on day 27. That bound alone stopped being enough
    the moment `start_date` was left unbounded below (`DECISIONS.md` 201): a
    trip beginning last March and ending next week satisfies it and is three
    hundred days long, which is three hundred days of forecast asked of a
    provider that answers sixteen. So the length is checked as well, and it is
    the check `STAGE-4`'s *a 15-day trip is rejected at the API layer* actually
    names.

    One message for both, because `CONVENTIONS.md` pins it and it happens to be
    true of each: *at most 14 days*, counted *from today*.
    """
    horizon = datetime.date.today() + datetime.timedelta(days=MAX_TRIP_DAYS)
    if (end - start).days + 1 > MAX_TRIP_DAYS or end > horizon:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "trip_too_long",
            f"Trips can span at most {MAX_TRIP_DAYS} days from today.",
        )


def _owned(db: Session, trip_id: uuid.UUID, user_id: uuid.UUID) -> Trip:
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id))
    if trip is None:
        # Another account's trip and one that never existed are the same
        # answer, which is `06-TESTING-STRATEGY.md`'s isolation requirement and
        # the third copy of `items.py`'s `_owned`: a 403 would confirm the row
        # exists.
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", "Trip not found.")
    return trip


async def _packed(db: Session, user: User, request: TripRequest) -> PackingResult:
    """The wardrobe guard, the one model call, and six exceptions made into codes.

    The guard is before the geocoder for `06-TESTING-STRATEGY.md`'s reason: a
    request that cannot be served should cost nothing, and a small wardrobe is
    knowable without spending a provider call or a token.

    **`pack_trip` raises its own exceptions and never an `ApiError`**
    (`DECISIONS.md` 044), and the two it lets travel through untouched are
    mapped here to exactly what `GET /weather` and `/me/locations/search`
    already answer — `forecast_unavailable` split across `400` and `502` by
    whether the range or the provider was at fault, and `geocoding_unavailable`
    for a geocoder that did not answer.

    **`ValueError` is `stylist_failed` here, and the two `pack_trip` raises
    itself cannot reach it.** `suggest_looks` raises `ValueError` when the model
    answered something unusable, which is what `POST /looks/suggest` already
    maps to a `502`; `pack_trip`'s own two are caller bugs — occasions that do
    not match the dates, which `TripPackRequest` refuses first, and a forecast
    shorter than the range, which `get_daily_forecast` refuses first. Neither is
    reachable from this route, so the broad clause costs nothing it should have
    kept.
    """
    wardrobe = styleable_wardrobe(db, user)
    if len(wardrobe) < MIN_WARDROBE_ITEMS:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "wardrobe_too_small",
            f"Add at least {MIN_WARDROBE_ITEMS} items before packing for a trip.",
        )

    try:
        return await pack_trip(
            user,
            wardrobe,
            request,
            # Measured back from the first day of the trip rather than from the
            # server's today: the recency window asks what will be stale when
            # the suitcase is packed, and `DECISIONS.md` 185 already established
            # that the day being dressed for is the right origin.
            preferences=learned_preferences(db, user, wardrobe, request.start_date),
        )
    except DestinationNotFoundError as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "destination_not_found",
            f"We couldn't find {request.destination}. Pick a destination from the suggestions.",
        ) from exc
    except GeocodingError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "geocoding_unavailable",
            "Location search is unavailable. Try again shortly.",
        ) from exc
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
    except StylistRejectedError as exc:
        logger.warning("The stylist failed trip validation twice", extra={"error": str(exc)})
        raise stylist_failed() from exc
    except (ValueError, OpenAIError) as exc:
        logger.warning("The stylist gave no usable trip plan", extra={"error": str(exc)})
        raise stylist_failed() from exc


def _write(
    db: Session, user: User, result: PackingResult, existing: Trip | None = None
) -> tuple[Trip, list[LookResponse], dict[int, uuid.UUID]]:
    """The eighth step: a trip, its looks and their items, in one commit.

    **Nothing here runs until `pack_trip` has returned.** That is the ordering
    `AUDITS.md` O-32 turns on: a repack that detached and deleted first would
    answer `502 stylist_failed` having already emptied a trip the user still
    has, and the looks it destroyed are the ones somebody bothered to save.

    **`existing` is what makes this both endpoints.** A pack adds the row
    `pack_trip` built; a repack keeps the row the user already has — its `id`,
    its `created_at` and the dates and occasions it was asked for — and takes
    only the four columns a fresh run can move. The coordinates are among them:
    a repack re-geocodes the stored destination string, so the same place can
    resolve to a slightly different point between two packs (`DECISIONS.md`
    202).

    `flush` rather than `commit` inside the loop, exactly as `_persist` does:
    `look_items.look_id` needs the id the insert generated, and a look and its
    items are one row or none.

    The three read-back columns — `is_saved`, `feedback`, `worn_at` — are read
    off the row rather than written as literals, which is `_persist`'s reasoning
    unchanged: the INSERT brings the server default back, and a literal here
    would be a second copy of `0002`'s `DEFAULT` with nothing comparing them.
    """
    if existing is None:
        trip = result.trip
        db.add(trip)
    else:
        trip = existing
        trip.dest_lat = result.trip.dest_lat
        trip.dest_lon = result.trip.dest_lon
        trip.forecast = result.trip.forecast
        trip.packing_list = result.trip.packing_list

        # O-32's option 2, and the order is the whole of it: the UPDATE claims
        # every marked look out of the trip, so the DELETE that follows can be
        # unqualified and still take only the unmarked ones. `look_items` goes
        # with them through `0002`'s own cascade, which is a second hop no line
        # of `0005` mentions.
        db.execute(update(Look).where(Look.trip_id == trip.id, _MARKED).values(trip_id=None))
        db.execute(delete(Look).where(Look.trip_id == trip.id))

    db.flush()

    looks: list[LookResponse] = []
    look_ids: dict[int, uuid.UUID] = {}

    for packed in result.looks:
        row = Look(
            user_id=user.id,
            trip_id=trip.id,
            title=packed.title,
            # From the request, never the model's echo of it — `occasion` was
            # struck from both AI schemas at 4.3 and the value that is certainly
            # legal is the one the user sent. `DECISIONS.md` 193.
            occasion=packed.occasion,
            reasoning=packed.reasoning,
            weather_note=packed.weather_note,
            # The day this look is *for*, which is the column `looks` has. The
            # trip's ordinal lives in the AI contract and the day strip; the two
            # are one fact counted from different origins.
            for_date=packed.for_date,
        )
        db.add(row)
        db.flush()

        db.add_all(
            [
                LookItem(look_id=row.id, item_id=item.id, position=position)
                for position, item in enumerate(packed.items)
            ]
        )

        look_ids[packed.day] = row.id
        looks.append(
            LookResponse(
                id=row.id,
                occasion=packed.occasion,
                title=packed.title,
                # Already hydrated by `pack_trip`, which resolved every
                # `short_id` once so that the row insert and the wire object
                # could not disagree about what the model chose.
                items=list(packed.items),
                reasoning=packed.reasoning,
                weather_note=packed.weather_note,
                is_saved=row.is_saved,
                feedback=row.feedback,
                worn_at=row.worn_at,
            )
        )

    db.commit()
    return trip, looks, look_ids


def _by_day(
    start: datetime.date, rows: Iterable[tuple[uuid.UUID, datetime.date | None]]
) -> dict[int, uuid.UUID]:
    """The join `04-API-SPEC.md`'s `days[].look_id` needs, keyed by the ordinal.

    `looks` carries `for_date` and no day number — `LookResponse` is one shape
    for every look since `DECISIONS.md` 182, and a trip is not a reason to widen
    what `GET /looks` answers — so the ordinal is computed back from the trip's
    `start_date`. A look with no `for_date` is dropped rather than guessed at:
    the column is nullable, nothing this route writes leaves it empty, and a
    look that names no day cannot be placed on one.
    """
    return {
        (for_date - start).days + 1: look_id for look_id, for_date in rows if for_date is not None
    }


def _trip(trip: Trip, look_ids: Mapping[int, uuid.UUID]) -> TripResponse:
    """The trip object: one row, two of its JSON columns, and the looks' ids.

    **`days` is three sources merged.** `trips.forecast` holds the parsed day —
    the four numbers, the condition and the rule the model actually obeyed;
    `trips.occasions` holds the occasion as the request sent it; and `look_ids`
    holds what was built for that day. Neither column is on the wire in its own
    right (`DECISIONS.md` 195), because each would be the same data in a second
    shape.

    `occasions` is indexed rather than `.get`, so a trip whose two JSON columns
    disagree about which days exist is a `500` rather than a day rendered with
    somebody else's occasion — `_CATEGORY_NAMES`'s reasoning, one column along.
    Nothing in the database enforces the agreement; `POST /trips/pack` writes
    both from one list.
    """
    occasions = {entry["day"]: entry["occasion"] for entry in trip.occasions}
    return TripResponse(
        id=trip.id,
        destination=trip.destination,
        dest_lat=trip.dest_lat,
        dest_lon=trip.dest_lon,
        start_date=trip.start_date,
        end_date=trip.end_date,
        notes=trip.notes,
        days=[
            TripDay.model_validate(
                {**day, "occasion": occasions[day["day"]], "look_id": look_ids.get(day["day"])}
            )
            for day in trip.forecast or []
        ],
        packing_list=PackingList.model_validate(trip.packing_list),
        created_at=trip.created_at,
    )


def _pieces(result: PackingResult) -> list[MissingPieceResponse]:
    return [
        MissingPieceResponse(
            category=piece.category, description=piece.description, reason=piece.reason
        )
        for piece in result.missing_pieces
    ]


def _looks(db: Session, trip: Trip) -> Sequence[Look]:
    return db.scalars(
        select(Look).where(Look.trip_id == trip.id).order_by(Look.for_date, Look.id)
    ).all()


def _hydrate(db: Session, rows: Sequence[Look]) -> list[LookResponse]:
    """Persisted looks with their items, in the model's own order.

    `looks.py`'s `_hydrate` for the same reason it exists there — one query for
    every look rather than one per look, ordered by `look_items.position`
    because without it the planner returns whatever it likes and a reopened trip
    relayouts between two loads. It is not shared with that module: this one is
    reached through a trip and that one through `GET /looks`, and 197 drew the
    line at what two *routes* both need, which is the wardrobe and the failure,
    not a private read helper each already has.
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


@router.post("/pack")
async def pack(
    request: TripPackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TripPackResponse:
    """`async def`, for `POST /looks/suggest`'s reason and more of it.

    Three of this route's calls leave the process — the geocoder, the forecast
    and the model — and the model call carries the whole wardrobe and every day
    of the trip at once.

    `trip_too_long` is checked before the wardrobe query, because it is the one
    refusal here that needs no database at all.
    """
    _within_the_bound(request.start_date, request.end_date)

    result = await _packed(
        db,
        current_user,
        TripRequest(
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            # Positional from here down — index 0 is day 1, which is what
            # `pack_trip` reads. `TripPackRequest` has already refused any list
            # that is not `1..n` in order, so the flattening cannot lose a day.
            occasions=tuple(entry.occasion for entry in request.occasions),
            notes=request.notes,
        ),
    )

    trip, looks, look_ids = _write(db, current_user, result)
    return TripPackResponse(trip=_trip(trip, look_ids), looks=looks, missing_pieces=_pieces(result))


@router.get("")
def list_trips(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TripListResponse:
    """Every trip this account owns, newest first, without their looks.

    `GET /looks`'s ordering exactly — `created_at DESC` with `id` as the
    tiebreaker, arbitrary but stable, which is what keeps `offset` from
    repeating a row between two pages.

    **The looks are still queried, and only their ids are.** A trip object
    carries `days[].look_id` whatever endpoint answers it, so the join cannot be
    skipped; what can be skipped is loading whole `looks` rows and their items
    for every trip on the page. One query over the page's trip ids, three
    columns wide.
    """
    total = (
        db.scalar(select(func.count()).select_from(Trip).where(Trip.user_id == current_user.id))
        or 0
    )
    rows = db.scalars(
        select(Trip)
        .where(Trip.user_id == current_user.id)
        .order_by(Trip.created_at.desc(), Trip.id)
        .limit(limit)
        .offset(offset)
    ).all()

    by_trip: dict[uuid.UUID, list[tuple[uuid.UUID, datetime.date | None]]] = {
        row.id: [] for row in rows
    }
    if rows:
        for trip_id, look_id, for_date in db.execute(
            select(Look.trip_id, Look.id, Look.for_date).where(Look.trip_id.in_(by_trip))
        ).all():
            by_trip[trip_id].append((look_id, for_date))

    return TripListResponse(
        trips=[_trip(row, _by_day(row.start_date, by_trip[row.id])) for row in rows],
        total=total,
    )


@router.get("/{trip_id}")
def read_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TripDetailResponse:
    """`POST /trips/pack`'s response minus `missing_pieces`, which was never stored.

    It described that run rather than this trip, so a reopened trip cannot carry
    it — `04-API-SPEC.md` and `DECISIONS.md` 195.
    """
    trip = _owned(db, trip_id, current_user.id)
    rows = _looks(db, trip)
    return TripDetailResponse(
        trip=_trip(trip, _by_day(trip.start_date, [(row.id, row.for_date) for row in rows])),
        looks=_hydrate(db, rows),
    )


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """A hard delete, and `AUDITS.md` O-32's option 1 taken deliberately.

    `DELETE /items/{id}` archives because a garment is referenced by every look
    that ever wore it; a trip is referenced by nothing but its own looks and
    `trips` has no `is_archived` to set. The cascade on `looks.trip_id` reaches
    `look_items` in a second hop through `0002`'s own.

    **What that destroys is a look that may have been saved, rated or worn**,
    and unlike a repack that is what the user asked for: they deleted the trip.
    The `items.wear_count` those looks incremented is not reversed and should
    not be — a garment worn in Berlin was worn — which leaves a wear count that
    no longer matches the number of looks a screen can show. That is a
    consequence stated rather than a defect fixed. `DECISIONS.md` 200.
    """
    db.delete(_owned(db, trip_id, current_user.id))
    db.commit()


@router.post("/{trip_id}/repack")
async def repack_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TripPackResponse:
    """The same plan against a fresher sky, and the same failure codes.

    **It takes no body.** The destination, the dates, the occasions and the
    notes are the trip's own — a repack that accepted new ones would be an edit
    endpoint `04-API-SPEC.md` does not describe.

    **It re-geocodes.** `pack_trip` takes a destination string and owns the
    lookup, so the stored `dest_lat`/`dest_lon` are re-derived rather than
    reused. Two consequences, both accepted: a repack can answer
    `destination_not_found` for a trip that packed cleanly last week, and a
    trip's coordinates can move between two packs. The alternative was widening
    the service to accept a pre-resolved `Location` for one caller.
    `DECISIONS.md` 202.

    **The bounds are rechecked, and this is where they bite.** `start_date` is
    never bounded below (`DECISIONS.md` 201), so a trip sits in the database
    until its dates are in the past — and the day after `end_date` falls outside
    `today + 14`, repacking it answers `trip_too_long`. Trips age out of being
    repackable, which is the honest reading of a forecast horizon that moves
    every day.
    """
    trip = _owned(db, trip_id, current_user.id)
    _within_the_bound(trip.start_date, trip.end_date)

    result = await _packed(
        db,
        current_user,
        TripRequest(
            destination=trip.destination,
            start_date=trip.start_date,
            end_date=trip.end_date,
            # Sorted rather than trusted in stored order. `pack_trip` reads this
            # positionally and `POST /trips/pack` wrote the column from one
            # ordered list, so this changes nothing today; it is what stops a
            # row edited by hand from dressing Tuesday for Thursday's occasion.
            occasions=tuple(
                entry["occasion"] for entry in sorted(trip.occasions, key=lambda e: e["day"])
            ),
            notes=trip.notes,
        ),
    )

    trip, looks, look_ids = _write(db, current_user, result, existing=trip)
    return TripPackResponse(trip=_trip(trip, look_ids), looks=looks, missing_pieces=_pieces(result))

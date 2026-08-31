"""The decisions only a request can make, shared by the routes that call the
stylist.

`POST /looks/suggest` has owned all three since 2.7; `POST /trips/pack` needs
them at 4.4, so they moved out of `looks.py` rather than being written a second
time. **Which** wardrobe the model sees is a query, **what this account has
learned** is another, and what a failure is worth on the wire is an `ApiError` —
all three are the route layer's, which is why they are here and not in
`services/stylist_runner.py` beside the retry loop. `DECISIONS.md` 044 keeps
`ApiError` out of `services/`, and a service that imported this module would
invert `01-ARCHITECTURE.md`'s direction. `DECISIONS.md` 197.

**`learned_preferences` is the third, and it arrived one task after the other
two.** 197 moved four helpers and left this one behind because it had a single
caller; `DECISIONS.md` 196 then decided that a trip carries the learned block
too — *a user whose stylist has learned they dislike bodycon dresses does not
stop disliking them in Berlin* — which gave it a second. It belongs on this side
of 197's line by that document's own test: it holds a `Session`, so a service
may not have it.

The leading underscore says this is not a router. `app/api/v1/router.py` imports
the modules in this package by name and mounts a `router` from each; this one has
none, and the underscore is what stops a reader expecting one.
"""

from collections.abc import Sequence
from datetime import date as date_type
from datetime import timedelta

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.enums import ItemStatus
from app.models.item import Item
from app.models.look import FEEDBACK_DOWN, FEEDBACK_UP, Look, LookItem
from app.models.user import User
from app.schemas.item import ItemResponse

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


def stylist_failed() -> ApiError:
    return ApiError(
        status.HTTP_502_BAD_GATEWAY,
        "stylist_failed",
        "I couldn't put a look together just now — try again.",
    )


def styleable_wardrobe(db: Session, user: User) -> list[ItemResponse]:
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

    Named `styleable_wardrobe` rather than `wardrobe`, which is what it was
    called as a private helper: every caller assigns the result to a local
    `wardrobe`, and the bare name would shadow the function at its own call
    site. `03-AI-CONTRACTS.md` already calls this list the styleable wardrobe.
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
            # the same filter `styleable_wardrobe` applies, one table along.
            Item.is_archived.is_(False),
        )
        .group_by(Item.category, Item.fit)
        .having(frequency >= 2)
        .order_by(frequency.desc(), Item.category, Item.fit)
        .limit(PREFERENCE_LIMIT)
    ).all()
    return [f"{fit} {_CATEGORY_NAMES[category]}" for category, fit in rows]


def learned_preferences(
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

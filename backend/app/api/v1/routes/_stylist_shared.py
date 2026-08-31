"""The two decisions only a request can make, shared by the routes that call
the stylist.

`POST /looks/suggest` has owned both since 2.7; `POST /trips/pack` needs the
same two at 4.4, so they moved out of `looks.py` rather than being written a
second time. **Which** wardrobe the model sees is a query, and what a failure is
worth on the wire is an `ApiError` — both are the route layer's, which is why
they are here and not in `services/stylist_runner.py` beside the retry loop.
`DECISIONS.md` 044 keeps `ApiError` out of `services/`, and a service that
imported this module would invert `01-ARCHITECTURE.md`'s direction. `DECISIONS.md`
197.

The leading underscore says this is not a router. `app/api/v1/router.py` imports
the modules in this package by name and mounts a `router` from each; this one has
none, and the underscore is what stops a reader expecting one.
"""

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.enums import ItemStatus
from app.models.item import Item
from app.models.user import User
from app.schemas.item import ItemResponse


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

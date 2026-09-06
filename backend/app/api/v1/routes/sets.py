"""The five `/sets` routes: declare one, read one, throw one away, and add or
remove a member.

A **set** is two or more garments the user declared as bought or worn together.
The garments are unchanged `items` rows and the set is a relation over them,
carried by `items.set_id` — so every route here writes a column on `items` or a
row in `item_sets`, and none of them creates, archives or edits a garment.

**Ownership is checked on every one of the five, and always as a `404`.** A set
belonging to another account and a set that never existed are the same answer,
which is `items.py`'s `_owned` for the fourth time: a `403` would confirm the
row exists.

**The line between the two status codes is the path, not the garment.** An item
id named in a *body* is an argument, and one that names nothing this account can
style is a `422` whether the row belongs to somebody else or to nobody — the
alternative would make the pair of codes report whether a UUID exists in another
account's wardrobe. An item id named in the *path* is part of the resource being
addressed, which is why `DELETE /sets/{set_id}/items/{item_id}` answers `404`
for an id that is not a member of the set.

**Two `422` codes rather than one**, both named in `CONVENTIONS.md`.
`set_item_unavailable` is `anchor_unavailable`'s check a third time — an id
naming nothing this account owns that the stylist could be shown — and
`set_member_taken` is a garment already spoken for by another set. They are
separate because the frontend branches on the code to choose a sentence, and
only one of the two has an obvious next action: *open that set*. Neither costs a
model call, which is what makes them cheap enough to check over a whole list
before anything is written.

**There is no `GET /sets` and no `PATCH /sets/{set_id}`**, both out of scope in
`STAGE-4A` and named in `04-API-SPEC.md` so their absence reads as a decision. A
set is reached through a member, and a rename is a delete and a redeclaration.

Nothing here is rate-limited, and nothing here calls a provider.
"""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import ApiError
from app.enums import ItemStatus
from app.models.item import Item
from app.models.item_set import ItemSet
from app.models.user import User
from app.schemas.item import ItemResponse
from app.schemas.item_set import ItemSetCreateRequest, ItemSetMemberRequest, ItemSetResponse

router = APIRouter(prefix="/sets", tags=["sets"])

# The count below which a set stops existing. `02-DATA-MODEL.md` states the rule
# and explains why the database cannot hold it — a CHECK cannot count rows in
# another table — so this constant and the two places that read it are the whole
# of the enforcement.
MIN_MEMBERS = 2


def _owned(db: Session, set_id: uuid.UUID, user_id: uuid.UUID) -> ItemSet:
    item_set = db.scalar(select(ItemSet).where(ItemSet.id == set_id, ItemSet.user_id == user_id))
    if item_set is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", "Set not found.")
    return item_set


def _response(db: Session, item_set: ItemSet) -> ItemSetResponse:
    """The set object, with its members read back from `items`.

    Ordered `created_at DESC, short_id` — `GET /items`' own order, tiebreaker
    included, because every row of one upload shares a `created_at` to the
    microsecond and a set is very often exactly that. Read after the write
    rather than assembled from what the route already holds, so the response
    describes the rows as they now stand.

    No filter: an **archived** member is in the list. Archiving a garment does
    not unmake the fact that it was bought with another, so the set keeps it —
    and a client that draws the set has to say so, because the alternative is a
    member the user can see here and nowhere else.
    """
    members = db.scalars(
        select(Item)
        .where(Item.set_id == item_set.id)
        .order_by(Item.created_at.desc(), Item.short_id)
    ).all()
    return ItemSetResponse(
        id=item_set.id,
        name=item_set.name,
        items=[ItemResponse.model_validate(row) for row in members],
        created_at=item_set.created_at,
    )


def _styleable(db: Session, user_id: uuid.UUID, item_ids: Sequence[uuid.UUID]) -> list[Item]:
    """The rows behind these ids that the stylist would actually be shown.

    `_stylist_shared.styleable_wardrobe`'s three filters, restated over a list
    of ids rather than over a whole account. It is not that function: that one
    answers `ItemResponse`s for the prompt, ordered oldest first, over every
    row; this one answers ORM rows for a membership decision over the handful an
    id list names, and sharing them would mean loading a 150-item wardrobe to
    ask about two of it.

    The reason for asking at all is `CONVENTIONS.md`'s: a set exists so the
    stylist prefers two garments together, so a garment the stylist is never
    shown cannot be a useful member of one. Writing the relation anyway would be
    a `201` that quietly does nothing.
    """
    return list(
        db.scalars(
            select(Item).where(
                Item.id.in_(item_ids),
                Item.user_id == user_id,
                Item.status == ItemStatus.READY,
                Item.is_archived.is_(False),
                Item.category.not_in(tuple(settings.stylist_excluded_categories)),
            )
        ).all()
    )


def _unavailable() -> ApiError:
    return ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "set_item_unavailable",
        "One of those garments is not one this wardrobe can style.",
    )


def _taken() -> ApiError:
    return ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "set_member_taken",
        "One of those garments already belongs to another set.",
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_set(
    request: ItemSetCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemSetResponse:
    """Declare a set over two or more garments.

    **Both refusals are decided over the whole list before anything is
    written**, which is `04-API-SPEC.md`'s wording and the reason they are two
    passes rather than a loop: a request rejected on its fourth id must create
    no set at all, and deciding as we wrote would leave one behind.

    Availability is asked first and membership second. The order is arbitrary in
    the same sense `POST /items/upload`'s type-before-size is (`DECISIONS.md`
    045) — a garment can fail both tests — and fixed for the same reason, so
    that one body always answers with one code. Availability leads because it is
    the wider question: `set_member_taken` is a statement about a garment this
    account owns and can style, which is exactly what the first pass has
    established.

    An id naming no row anywhere is `set_item_unavailable` here rather than
    `404`, and that is deliberate on this endpoint alone: there is no set in the
    URL yet, so every id in the body is an argument, and *nothing in this
    account's wardrobe that could be styled* is true of a row that does not
    exist. `POST /sets/{set_id}/items` reads the other way — see there.
    """
    found = _styleable(db, current_user.id, request.item_ids)
    if len(found) != len(request.item_ids):
        raise _unavailable()

    if any(item.set_id is not None for item in found):
        raise _taken()

    item_set = ItemSet(user_id=current_user.id, name=request.name)
    db.add(item_set)
    # Flushed rather than committed: the id has to exist before the members can
    # point at it, and the whole declaration is one transaction — a set with no
    # members is not a state any reader of this table should be able to observe.
    db.flush()
    for item in found:
        item.set_id = item_set.id
    db.commit()

    return _response(db, item_set)


@router.get("/{set_id}")
def get_set(
    set_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemSetResponse:
    return _response(db, _owned(db, set_id, current_user.id))


@router.delete("/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set(
    set_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """A hard delete that deletes no garment.

    The `item_sets` row goes and `0007`'s `ON DELETE SET NULL` clears `set_id`
    on every member; the items keep their tags, their wear counts, their archive
    state and their place in every look that ever wore them. That is the whole
    reason the foreign key is not a `CASCADE`.

    **Not idempotent in the way `DELETE /items/{id}` is.** A second call is
    `404`, because the row is genuinely gone — where an already-archived item
    answers `200` again, since it stays readable by id.
    """
    db.delete(_owned(db, set_id, current_user.id))
    db.commit()


@router.post("/{set_id}/items")
def add_set_item(
    set_id: uuid.UUID,
    request: ItemSetMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemSetResponse:
    """Add one garment to an existing set.

    **The no-op is tested before either refusal, and that ordering is the
    contract.** A garment already in *this* set answers `200` with the set
    unchanged — the request asked for a state the set is in, and a double-tap is
    not a failure. It has to be asked first because a member can have been
    archived since it joined: `02-DATA-MODEL.md` keeps an archived garment in
    its set, so re-adding one must not be refused by the availability test that
    would refuse it as a *new* member. That asymmetry is `02-DATA-MODEL.md`'s
    own — a fact already recorded stays recorded, while a new membership the
    stylist can never act on is not worth writing.

    **The `404` on this endpoint is the set in the path and nothing else.** An
    item id that resolves to no row at all is `set_item_unavailable`, the same
    answer `POST /sets` gives it — the id is a value in the body rather than the
    resource being addressed. Splitting the two, `422` for another account's
    garment and `404` for one that exists nowhere, would make the pair report
    whether an id exists in somebody else's wardrobe. It is
    `anchor_unavailable`'s collapse one endpoint along, on the argument
    `CONVENTIONS.md` already makes there: an id naming nothing this account can
    style is one answer, whatever the reason it names nothing.
    """
    item_set = _owned(db, set_id, current_user.id)

    already = db.scalar(select(Item).where(Item.id == request.item_id, Item.set_id == item_set.id))
    if already is not None:
        return _response(db, item_set)

    found = _styleable(db, current_user.id, [request.item_id])
    if not found:
        raise _unavailable()

    item = found[0]
    if item.set_id is not None:
        raise _taken()

    item.set_id = item_set.id
    db.commit()

    return _response(db, item_set)


@router.delete("/{set_id}/items/{item_id}", response_model=ItemSetResponse | None)
def remove_set_item(
    set_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemSetResponse | Response:
    """Remove one garment, and end the set if that leaves one behind.

    **Two status codes on one path, and the pair is the contract.** A set of
    three loses one and answers `200` with the two that remain. A set of two
    loses one and there is no set left to answer with: the `item_sets` row is
    deleted, `0007`'s foreign key clears the remaining member's `set_id`, and
    the answer is `204`. `02-DATA-MODEL.md` is where the rule lives — fewer than
    two members is not a set — and this is the only endpoint that can reach it.

    The alternative was `200` on both, carrying a one-member set or a flag
    saying the set had dissolved. It describes something the database no longer
    holds, and the client has to branch anyway: the item detail screen shows a
    set row or an empty one, and the status code is the branch.

    `404` for an `item_id` that is not a member of this set. That is a statement
    about the URL rather than about the garment, which is why it is not
    `set_item_unavailable` — a `422` about what a client asked to *add*.

    The comparison is `<=` rather than `==`: a set holding one row is a state
    this API cannot produce, and if one ever exists the removal that empties it
    should end it rather than leave a set of nothing behind.
    """
    item_set = _owned(db, set_id, current_user.id)

    member = db.scalar(select(Item).where(Item.id == item_id, Item.set_id == item_set.id))
    if member is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", "That item is not in this set.")

    members = (
        db.scalar(select(func.count()).select_from(Item).where(Item.set_id == item_set.id)) or 0
    )
    if members <= MIN_MEMBERS:
        # The row goes and the foreign key clears both members, including the
        # one that was not named in the URL. Clearing this item first would be
        # the same end state reached in two statements instead of one.
        db.delete(item_set)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    member.set_id = None
    db.commit()

    return _response(db, item_set)

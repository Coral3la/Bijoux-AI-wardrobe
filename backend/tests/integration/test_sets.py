"""The five `/sets` routes.

**No AI, no geocoder and no forecast** — a set makes no model call of its own,
which is what `CONVENTIONS.md` says separates `set_item_unavailable` from
`anchor_unavailable`: the argument for refusing an unstyleable garment here is
about a silent no-op rather than about a wasted call. So every test below is the
route, the ORM and PostgreSQL, with no fake anywhere.

What is worth naming is the shape of the refusals. Three of the five endpoints
can answer `404` for the set in the path and `422` for a garment in the body,
and the two are different questions: the set is the resource and a `403` on it
would confirm a row exists, where the garment is an argument and its `422`
carries a code the client branches on to choose a sentence. **A body id that
names no row anywhere is the `422` as well**, so the two codes cannot be read
together as an answer to *does this UUID exist*.

`DELETE /sets/{set_id}/items/{item_id}` answers **two** status codes on one
path, and both are asserted here because neither is derivable from the other:
`200` with the survivors, and `204` when the removal left one member behind and
the set is gone.
"""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.item import Item
from app.models.item_set import ItemSet
from app.models.user import User

pytestmark = pytest.mark.usefixtures("cloudinary_configured")

SETS_URL = "/api/v1/sets"

READY: dict[str, Any] = {
    "status": "ready",
    "category": "top",
    "subcategory": "shirt",
    "color_primary": "white",
    "layer": "base",
    "formality": 3,
    "warmth": 2,
}

# Every way `CONVENTIONS.md` says a garment can fail to be styleable, as the
# columns that make it so. The foreign case is the odd one out — it is about who
# owns the row rather than about the row — so it is spelled by the test rather
# than by this table.
UNSTYLEABLE: dict[str, dict[str, Any]] = {
    "archived": {"is_archived": True},
    "processing": {"status": "processing"},
    "failed": {"status": "failed", "error_message": "no usable answer"},
    "excluded_category": {"category": "swimwear"},
}


def _sets(db: Session, user: User) -> int:
    return (
        db.scalar(select(func.count()).select_from(ItemSet).where(ItemSet.user_id == user.id)) or 0
    )


def _declare(db: Session, user: User, items: list[Item], name: str | None = None) -> ItemSet:
    """A set planted directly, for the endpoints that read one rather than write it."""
    item_set = ItemSet(user_id=user.id, name=name)
    db.add(item_set)
    db.flush()
    for item in items:
        item.set_id = item_set.id
    db.commit()
    return item_set


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user()


@pytest.fixture
def garments(user: User, make_item: Callable[..., Item]) -> list[Item]:
    return [make_item(user_id=user.id, **READY) for _ in range(3)]


# --- POST /sets -------------------------------------------------------------


def test_two_garments_are_declared_as_one_set(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    response = client.post(
        SETS_URL,
        json={"name": "the linen suit", "item_ids": [str(garments[0].id), str(garments[1].id)]},
        headers=authorization(user),
    )

    assert response.status_code == 201
    body = response.json()
    # The key set, pinned literally and transcribed from `04-API-SPEC.md`. It is
    # `test_looks_list.py`'s assertion one resource along, and for its reason:
    # a field added to this object later must fail a test rather than ship
    # unnoticed.
    assert set(body) == {"id", "name", "items", "created_at"}
    assert body["name"] == "the linen suit"
    # Both members answer with the same `set_id`, and it is this set's id —
    # `STAGE-4A`'s first acceptance criterion, which is about `ItemResponse`
    # carrying the column as much as about the route writing it.
    assert {item["set_id"] for item in body["items"]} == {body["id"]}
    assert {item["id"] for item in body["items"]} == {str(garments[0].id), str(garments[1].id)}


def test_a_set_may_be_declared_with_no_name(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # `name` is nullable and there is no rename, so a set with no name is
    # described by its members for the rest of its life.
    response = client.post(
        SETS_URL,
        json={"item_ids": [str(garments[0].id), str(garments[1].id)]},
        headers=authorization(user),
    )

    assert response.status_code == 201
    assert response.json()["name"] is None


def test_fewer_than_two_ids_is_a_validation_error(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # A request-shape rule, the way `POST /items/upload`'s file count is: no
    # correct client can build this body, so it needs no code of its own.
    response = client.post(
        SETS_URL, json={"item_ids": [str(garments[0].id)]}, headers=authorization(user)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "item_ids" in response.json()["detail"]


def test_a_repeated_id_is_a_validation_error_and_not_a_one_member_set(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # `04-API-SPEC.md`: the list is deduplicated *before* the count is checked,
    # so `["a", "a"]` is refused rather than collapsed into a set of one.
    response = client.post(
        SETS_URL,
        json={"item_ids": [str(garments[0].id), str(garments[0].id)]},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert _sets(db, user) == 0


@pytest.mark.parametrize("reason", sorted(UNSTYLEABLE))
def test_a_garment_this_wardrobe_cannot_style_is_refused(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_item: Callable[..., Item],
    garments: list[Item],
    reason: str,
) -> None:
    unstyleable = make_item(user_id=user.id, **(READY | UNSTYLEABLE[reason]))

    response = client.post(
        SETS_URL,
        json={"item_ids": [str(garments[0].id), str(unstyleable.id)]},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "set_item_unavailable"
    # Checked over the whole list before anything is written, so a rejected
    # request creates no set at all — and leaves the good id in the body
    # unattached.
    assert _sets(db, user) == 0
    db.refresh(garments[0])
    assert garments[0].set_id is None


def test_another_accounts_garment_is_refused(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_user: Callable[..., User],
    make_item: Callable[..., Item],
    garments: list[Item],
) -> None:
    # The same `422` as the four above rather than a `404`, which is the whole
    # of what `set_item_unavailable` widens: on this endpoint there is no set in
    # the URL, so every id in the body is an argument and one naming nothing
    # this account can style is answered the same way whoever owns it.
    stranger = make_item(user_id=make_user().id, **READY)

    response = client.post(
        SETS_URL,
        json={"item_ids": [str(garments[0].id), str(stranger.id)]},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "set_item_unavailable"
    assert _sets(db, user) == 0


def test_a_garment_already_in_another_set_is_taken(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_item: Callable[..., Item],
) -> None:
    # A second code rather than a reuse of `set_item_unavailable`, on
    # `locked_unavailable`'s reasoning: the client branches on it, and *already
    # in another set* is the only one of the two with an obvious next action.
    spare = make_item(user_id=user.id, **READY)
    _declare(db, user, [garments[0], garments[1]])

    response = client.post(
        SETS_URL,
        json={"item_ids": [str(garments[0].id), str(spare.id)]},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "set_member_taken"
    assert _sets(db, user) == 1


# --- GET /sets/{set_id} -----------------------------------------------------


def test_a_set_reads_back_with_its_members_in_wardrobe_order(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # `created_at DESC, short_id`, which is `GET /items`' own order. Both halves
    # are measured: the three rows are written inside one transaction, so
    # `now()` gives them an identical `created_at` and `short_id` is what
    # separates them — the tiebreaker `GET /items` calls load-bearing rather
    # than cosmetic — and one is then moved back a day so the DESC half has
    # something to order.
    item_set = _declare(db, user, garments, name="the co-ord")
    assert len({item.created_at for item in garments}) == 1
    garments[0].created_at -= timedelta(days=1)
    db.commit()
    expected = [str(item.id) for item in sorted(garments[1:], key=lambda row: row.short_id)]
    expected.append(str(garments[0].id))

    body = client.get(f"{SETS_URL}/{item_set.id}", headers=authorization(user)).json()

    assert body["id"] == str(item_set.id)
    assert body["name"] == "the co-ord"
    assert [item["id"] for item in body["items"]] == expected


def test_an_archived_member_is_still_in_the_set(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # `02-DATA-MODEL.md`: `DELETE /items/{id}` sets `is_archived` and touches no
    # `set_id`, so the set keeps its count — and the client has to say so,
    # because the alternative is a member the user can see here and nowhere
    # else.
    item_set = _declare(db, user, [garments[0], garments[1]])
    garments[0].is_archived = True
    db.commit()

    body = client.get(f"{SETS_URL}/{item_set.id}", headers=authorization(user)).json()

    assert len(body["items"]) == 2
    assert [item["is_archived"] for item in body["items"] if item["id"] == str(garments[0].id)] == [
        True
    ]


# --- ownership --------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "", None),
        ("DELETE", "", None),
        ("POST", "/items", {"item_id": str(uuid.uuid4())}),
        ("DELETE", f"/items/{uuid.uuid4()}", None),
    ],
    ids=["read", "delete", "add", "remove"],
)
def test_another_accounts_set_is_not_found_on_every_endpoint(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_user: Callable[..., User],
    make_item: Callable[..., Item],
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Beyond `STAGE-4A` 4A.1's test list, and the one addition: the task states
    *another account's set is `404`, never a `422`* as a requirement of all four
    set-addressed endpoints, and nothing else here would fail if one of them
    leaked a `422` instead.

    The set is checked before the body on every one, and the `POST` case is what
    proves it: its `item_id` names no row, which this endpoint answers `422` for
    on a set the caller owns, so a `404` here can only have come from the set.
    """
    stranger = make_user()
    theirs = _declare(db, stranger, [make_item(user_id=stranger.id, **READY) for _ in range(2)])

    response = client.request(
        method, f"{SETS_URL}/{theirs.id}{path}", json=body, headers=authorization(user)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# --- DELETE /sets/{set_id} --------------------------------------------------


def test_deleting_a_set_leaves_every_garment_in_place(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # `ON DELETE SET NULL`, from the wire: the statement is withdrawn and the
    # garments keep their tags, their wear counts and their archive state.
    item_set = _declare(db, user, [garments[0], garments[1]])

    response = client.delete(f"{SETS_URL}/{item_set.id}", headers=authorization(user))

    assert response.status_code == 204
    assert response.content == b""
    assert _sets(db, user) == 0
    for item in garments[:2]:
        db.refresh(item)
        assert item.set_id is None
        assert item.is_archived is False


# --- POST /sets/{set_id}/items ----------------------------------------------


def test_adding_a_third_garment_answers_a_set_of_three(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    item_set = _declare(db, user, [garments[0], garments[1]])

    response = client.post(
        f"{SETS_URL}/{item_set.id}/items",
        json={"item_id": str(garments[2].id)},
        headers=authorization(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["items"]} == {str(item.id) for item in garments}
    assert {item["set_id"] for item in body["items"]} == {str(item_set.id)}


@pytest.mark.parametrize("archived", [False, True], ids=["a double tap", "an archived member"])
def test_re_adding_a_member_is_a_200_that_changes_nothing(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    archived: bool,
) -> None:
    """The request asked for a state the set is in, and a double-tap is not a failure.

    The archived case is what fixes the order of the three checks in the route:
    an archived garment is not styleable, so asking `set_item_unavailable`
    before *is it already here* would refuse a member the set is documented to
    keep. `02-DATA-MODEL.md`, under `item_sets`.
    """
    item_set = _declare(db, user, [garments[0], garments[1]])
    if archived:
        garments[0].is_archived = True
        db.commit()

    response = client.post(
        f"{SETS_URL}/{item_set.id}/items",
        json={"item_id": str(garments[0].id)},
        headers=authorization(user),
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_adding_a_garment_that_belongs_to_another_set_is_taken(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_item: Callable[..., Item],
) -> None:
    spare = make_item(user_id=user.id, **READY)
    mine = _declare(db, user, [garments[0], garments[1]])
    _declare(db, user, [garments[2], spare])

    response = client.post(
        f"{SETS_URL}/{mine.id}/items",
        json={"item_id": str(garments[2].id)},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "set_member_taken"


def test_an_item_id_that_names_no_row_is_refused_rather_than_not_found(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    """The `404` on this endpoint is the set and nothing else.

    Repointed at the second pass of 4A.1, from an archived garment to an id that
    names no row anywhere. The two reach the route through one branch —
    `_styleable` finds nothing either way — so the archived case pinned the
    branch and this one pins the branch *and* the absence of the `404` the first
    draft raised above it. `POST /sets` still covers archived, `processing`,
    `failed`, an excluded category and another account's row, four of them
    parametrised.

    The leak that closed is small and real: `422` for another account's garment
    beside `404` for one that exists nowhere makes the pair of codes an oracle
    for whether a UUID is in use.
    """
    item_set = _declare(db, user, [garments[0], garments[1]])

    response = client.post(
        f"{SETS_URL}/{item_set.id}/items",
        json={"item_id": str(uuid.uuid4())},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "set_item_unavailable"
    assert (
        len(client.get(f"{SETS_URL}/{item_set.id}", headers=authorization(user)).json()["items"])
        == 2
    )


# --- DELETE /sets/{set_id}/items/{item_id} ----------------------------------


def test_removing_from_a_set_of_three_answers_the_two_that_remain(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    item_set = _declare(db, user, garments)

    response = client.delete(
        f"{SETS_URL}/{item_set.id}/items/{garments[0].id}", headers=authorization(user)
    )

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {
        str(garments[1].id),
        str(garments[2].id),
    }
    db.refresh(garments[0])
    assert garments[0].set_id is None


def test_removing_the_second_to_last_member_dissolves_the_set(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # There is no set left to answer with, so the status code is the branch. The
    # survivor's `set_id` is cleared by `0007`'s foreign key rather than by the
    # route, which is why it is asserted here and not only in the rows file.
    item_set = _declare(db, user, [garments[0], garments[1]])

    response = client.delete(
        f"{SETS_URL}/{item_set.id}/items/{garments[0].id}", headers=authorization(user)
    )

    assert response.status_code == 204
    assert response.content == b""
    assert _sets(db, user) == 0
    for item in garments[:2]:
        db.refresh(item)
        assert item.set_id is None


def test_removing_an_item_that_is_not_a_member_is_not_found(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
) -> None:
    # A statement about the URL rather than about the garment, which is why it
    # is a `404` and not the `422` this endpoint's sibling answers about what a
    # client asked to add.
    item_set = _declare(db, user, [garments[0], garments[1]])

    response = client.delete(
        f"{SETS_URL}/{item_set.id}/items/{garments[2].id}", headers=authorization(user)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert (
        len(client.get(f"{SETS_URL}/{item_set.id}", headers=authorization(user)).json()["items"])
        == 2
    )

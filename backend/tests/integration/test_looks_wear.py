"""`/looks/{id}/wear`, both directions — one date on the look, one wearing on
every garment, and 3.4a taking both back.

The stage file asks for one test by name: *calling it twice for the same date
must not double-count*, and it asks for it explicitly rather than by
implication. It is `test_a_repeat_of_the_same_date_changes_nothing` below, and
the two beside it are the pair that give it meaning — a different date **does**
count again, and the third request naming the first date counts a third time,
because `looks.worn_at` is one column and cannot remember a day it has
overwritten. That last test asserts a limitation rather than a feature; it is
here so the limitation is a decision with a name on it (`DECISIONS.md` 184)
instead of a surprise for whoever writes the history table.

`last_worn_at` is `GREATEST`, so the file's other awkward test is the one that
back-dates a wearing and asserts the item did **not** move backwards — which is
the whole reason for the `GREATEST`: 3.5 reads that column to avoid
recommending a garment worn in the last three days.

The `DELETE` half is 3.4a's and its awkward test is
`test_an_item_in_two_worn_looks_keeps_its_date_until_the_last_undo`. That one
pins the reason write 2 is a single statement: SQL reads a column in `SET` as it
stood *before* the statement, so the `CASE` tests the count on the way in and a
garment still worn elsewhere keeps its date. Written as a test rather than left
to the comment beside it, because the day someone splits that `UPDATE` in two is
the day the comment stops being true and nothing says so. Two other tests here
assert what an undo does **not** restore — the item's date and the look's
previous date — for the same reason the three-count test above exists.
"""

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.item import Item
from app.models.look import Look
from app.models.user import User

pytestmark = pytest.mark.usefixtures("cloudinary_configured")

LOOKS_URL = "/api/v1/looks"

READY: dict[str, Any] = {
    "status": "ready",
    "category": "top",
    "subcategory": "t-shirt",
    "color_primary": "white",
    "layer": "base",
    "formality": 2,
    "warmth": 2,
}

TEXT: dict[str, Any] = {
    "title": "Morning meetings",
    "occasion": "work",
    "reasoning": "The jean balances the shirt.",
    "weather_note": "18°C — no jacket needed.",
}

MONDAY = date(2026, 3, 9)
TUESDAY = date(2026, 3, 10)


def _wear(client: TestClient, look: Look, day: date, headers: dict[str, str]) -> Any:
    return client.post(
        f"{LOOKS_URL}/{look.id}/wear", json={"date": day.isoformat()}, headers=headers
    )


def _unwear(client: TestClient, look: Look, headers: dict[str, str]) -> Any:
    return client.delete(f"{LOOKS_URL}/{look.id}/wear", headers=headers)


def test_wearing_a_look_records_the_date_on_it(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, items=[make_item(user_id=user.id, **READY)], **TEXT)

    response = _wear(client, look, MONDAY, authorization(user))

    assert response.status_code == 200
    assert response.json()["worn_at"] == MONDAY.isoformat()
    db.refresh(look)
    assert look.worn_at == MONDAY


def test_wearing_a_look_counts_every_item_in_it(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    items = [make_item(user_id=user.id, **READY) for _ in range(3)]
    look = make_look(user_id=user.id, items=items, **TEXT)

    _wear(client, look, MONDAY, authorization(user))

    for item in items:
        db.refresh(item)
        assert item.wear_count == 1
        assert item.last_worn_at == MONDAY


def test_an_item_outside_the_look_is_left_alone(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The UPDATE names its rows through a subquery over `look_items`, and a
    # subquery with a wrong join reads as working right up until a second
    # garment exists to be swept up by it.
    user = make_user()
    bystander = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[make_item(user_id=user.id, **READY)], **TEXT)

    _wear(client, look, MONDAY, authorization(user))

    db.refresh(bystander)
    assert bystander.wear_count == 0
    assert bystander.last_worn_at is None


def test_a_repeat_of_the_same_date_changes_nothing(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `STAGE-3` 3.4, the test it asks for by name.
    user = make_user()
    item = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)
    headers = authorization(user)

    _wear(client, look, MONDAY, headers)
    second = _wear(client, look, MONDAY, headers)

    assert second.status_code == 200
    assert second.json()["worn_at"] == MONDAY.isoformat()
    db.refresh(item)
    assert item.wear_count == 1


def test_a_second_day_is_a_second_wearing(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)
    headers = authorization(user)

    _wear(client, look, MONDAY, headers)
    _wear(client, look, TUESDAY, headers)

    db.refresh(item)
    assert item.wear_count == 2
    # The look holds the newer date and not the first: one column, one day.
    db.refresh(look)
    assert look.worn_at == TUESDAY


def test_idempotency_reaches_back_exactly_one_date(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # A limitation, asserted on purpose. Monday, Tuesday, Monday counts three
    # wearings, because by the third request the column no longer holds Monday
    # and nothing else in the schema remembers it. `DECISIONS.md` 184 takes
    # this deliberately rather than building `look_wears` at 3.4.
    user = make_user()
    item = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)
    headers = authorization(user)

    _wear(client, look, MONDAY, headers)
    _wear(client, look, TUESDAY, headers)
    _wear(client, look, MONDAY, headers)

    db.refresh(item)
    assert item.wear_count == 3


def test_a_back_dated_wearing_does_not_age_an_item_backwards(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # GREATEST, and the reason for it: 3.5 asks which garments were worn in the
    # last three days, and a correction entered for last week must not answer
    # that question with a garment worn yesterday.
    user = make_user()
    item = make_item(user_id=user.id, last_worn_at=TUESDAY, wear_count=1, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)

    _wear(client, look, MONDAY, authorization(user))

    db.refresh(item)
    assert item.last_worn_at == TUESDAY
    # The wearing still happened, so it is still counted.
    assert item.wear_count == 2


def test_the_look_and_its_items_may_disagree_about_the_last_day(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Two looks sharing one garment. The first look's `worn_at` says Monday and
    # the shared item says Tuesday, and both are true: a look records when *it*
    # was worn, an item when it was last worn in anything.
    user = make_user()
    shared = make_item(user_id=user.id, **READY)
    monday_look = make_look(user_id=user.id, items=[shared], **TEXT)
    tuesday_look = make_look(user_id=user.id, items=[shared], **TEXT)
    headers = authorization(user)

    _wear(client, monday_look, MONDAY, headers)
    _wear(client, tuesday_look, TUESDAY, headers)

    db.refresh(monday_look)
    db.refresh(shared)
    assert monday_look.worn_at == MONDAY
    assert shared.last_worn_at == TUESDAY
    assert shared.wear_count == 2


def test_an_unsaved_look_can_be_worn(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The button is on the saved-looks screen; that is the screen's policy and
    # not the endpoint's. A look is unsaved by default.
    user = make_user()
    look = make_look(user_id=user.id, items=[make_item(user_id=user.id, **READY)], **TEXT)

    response = _wear(client, look, MONDAY, authorization(user))

    assert response.status_code == 200
    assert response.json()["is_saved"] is False


def test_a_future_date_is_accepted(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Deliberately not refused. The client sends the date its own timezone is
    # standing in, and a browser east of UTC routinely names a day the server
    # would still call tomorrow — so a strict check is a 422 a correct client
    # provokes by being east of Greenwich. `DECISIONS.md` 184.
    user = make_user()
    look = make_look(user_id=user.id, items=[make_item(user_id=user.id, **READY)], **TEXT)
    tomorrow = date.today() + timedelta(days=1)

    response = _wear(client, look, tomorrow, authorization(user))

    assert response.status_code == 200
    assert response.json()["worn_at"] == tomorrow.isoformat()


def test_the_response_carries_the_hydrated_items(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The response is a whole look, so the screen that tapped the button can
    # render the new counts without a second request — which is the only reason
    # the two item fields went on the wire in this task rather than at 3.6.
    user = make_user()
    item = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)

    body = _wear(client, look, MONDAY, authorization(user)).json()

    assert [row["id"] for row in body["items"]] == [str(item.id)]
    assert body["items"][0]["wear_count"] == 1
    assert body["items"][0]["last_worn_at"] == MONDAY.isoformat()


def test_a_body_with_no_date_is_refused(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.post(f"{LOOKS_URL}/{look.id}/wear", json={}, headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_an_unknown_field_is_refused(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.post(
        f"{LOOKS_URL}/{look.id}/wear",
        json={"date": MONDAY.isoformat(), "worn_at": MONDAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_wearing_another_users_look_is_404_not_403(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    owner = make_user()
    stranger = make_user()
    item = make_item(user_id=owner.id, **READY)
    look = make_look(user_id=owner.id, items=[item], **TEXT)

    response = _wear(client, look, MONDAY, authorization(stranger))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    # Nothing was written on the way to the refusal.
    db.refresh(item)
    assert item.wear_count == 0


def test_a_look_that_never_existed_is_the_same_404(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.post(
        f"{LOOKS_URL}/{uuid.uuid4()}/wear",
        json={"date": MONDAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_wearing_requires_a_token(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
) -> None:
    look = make_look(user_id=make_user().id, **TEXT)

    response = client.post(f"{LOOKS_URL}/{look.id}/wear", json={"date": MONDAY.isoformat()})

    assert response.status_code == 401


def test_undoing_a_wearing_clears_the_date_on_the_look(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    headers = authorization(user)
    look = make_look(user_id=user.id, items=[make_item(user_id=user.id, **READY)], **TEXT)
    _wear(client, look, MONDAY, headers)

    response = _unwear(client, look, headers)

    assert response.status_code == 200
    assert response.json()["worn_at"] is None
    db.refresh(look)
    assert look.worn_at is None


def test_undoing_gives_every_item_in_the_look_its_count_back(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    headers = authorization(user)
    items = [make_item(user_id=user.id, **READY) for _ in range(3)]
    look = make_look(user_id=user.id, items=items, **TEXT)
    _wear(client, look, MONDAY, headers)

    _unwear(client, look, headers)

    for item in items:
        db.refresh(item)
        assert item.wear_count == 0
        # The count reached zero, so there is provably no wearing left to date
        # — the one case where the true previous value is known.
        assert item.last_worn_at is None


def test_an_item_in_two_worn_looks_keeps_its_date_until_the_last_undo(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The pre-update read, which is what lets write 2 be one statement. SQL
    # evaluates `wear_count` in a SET clause against the row as it stood before
    # the statement, so the CASE sees 2 on the first undo and 1 on the second.
    # Split that UPDATE in two and this test is what fails.
    user = make_user()
    headers = authorization(user)
    shirt = make_item(user_id=user.id, **READY)
    monday_look = make_look(user_id=user.id, items=[shirt], **TEXT)
    tuesday_look = make_look(user_id=user.id, items=[shirt], **TEXT)
    _wear(client, monday_look, MONDAY, headers)
    _wear(client, tuesday_look, TUESDAY, headers)
    db.refresh(shirt)
    assert (shirt.wear_count, shirt.last_worn_at) == (2, TUESDAY)

    _unwear(client, tuesday_look, headers)

    db.refresh(shirt)
    assert shirt.wear_count == 1
    # Still worn in the Monday look, so the date stands rather than clearing.
    assert shirt.last_worn_at == TUESDAY

    _unwear(client, monday_look, headers)

    db.refresh(shirt)
    assert shirt.wear_count == 0
    assert shirt.last_worn_at is None


def test_an_undo_does_not_restore_the_date_the_item_had_before(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The documented non-identity, asserted so it is a decision rather than a
    # discovery: the count comes back exactly and the date does not. Monday was
    # never recorded anywhere — `items.last_worn_at` is one column and there is
    # no history table. `DECISIONS.md` 226.
    user = make_user()
    headers = authorization(user)
    shirt = make_item(user_id=user.id, **READY)
    monday_look = make_look(user_id=user.id, items=[shirt], **TEXT)
    tuesday_look = make_look(user_id=user.id, items=[shirt], **TEXT)
    _wear(client, monday_look, MONDAY, headers)
    _wear(client, tuesday_look, TUESDAY, headers)

    _unwear(client, tuesday_look, headers)

    db.refresh(shirt)
    assert shirt.wear_count == 1
    assert shirt.last_worn_at == TUESDAY
    assert shirt.last_worn_at != MONDAY


def test_an_undo_does_not_restore_the_looks_previous_date(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `looks.worn_at` undoes to NULL, not to Monday, and that is the same
    # one-date-deep reach the wearing half has going in. `DECISIONS.md` 184.
    user = make_user()
    headers = authorization(user)
    look = make_look(user_id=user.id, items=[make_item(user_id=user.id, **READY)], **TEXT)
    _wear(client, look, MONDAY, headers)
    _wear(client, look, TUESDAY, headers)

    _unwear(client, look, headers)

    db.refresh(look)
    assert look.worn_at is None


def test_a_count_already_at_zero_is_floored_rather_than_made_negative(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The drift `DELETE /trips/{id}` leaves behind: it cascades its looks away
    # without reversing the counts those looks raised, so a worn look whose
    # garment reads zero is reachable rather than hypothetical. GREATEST floors
    # it and the CASE still clears the date, which is why the statement has no
    # `WHERE wear_count > 0` narrowing it.
    user = make_user()
    headers = authorization(user)
    item = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)
    _wear(client, look, MONDAY, headers)
    db.refresh(item)
    item.wear_count = 0
    db.commit()

    _unwear(client, look, headers)

    db.refresh(item)
    assert item.wear_count == 0
    assert item.last_worn_at is None


def test_a_second_undo_changes_nothing(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # What makes the double-tap on the undo button safe: the guard is the
    # UPDATE's own WHERE, so the second request matches no row, decrements
    # nothing, and still answers 200 with the look.
    user = make_user()
    headers = authorization(user)
    shirt = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[shirt], **TEXT)
    other_look = make_look(user_id=user.id, items=[shirt], **TEXT)
    _wear(client, look, MONDAY, headers)
    _wear(client, other_look, TUESDAY, headers)
    _unwear(client, look, headers)

    response = _unwear(client, look, headers)

    assert response.status_code == 200
    db.refresh(shirt)
    assert shirt.wear_count == 1


def test_undoing_a_look_that_was_never_worn_is_a_no_op(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)

    response = _unwear(client, look, authorization(user))

    assert response.status_code == 200
    assert response.json()["worn_at"] is None
    db.refresh(item)
    assert item.wear_count == 0


def test_an_item_outside_the_look_is_not_decremented(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    headers = authorization(user)
    inside = make_item(user_id=user.id, **READY)
    outside = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[inside], **TEXT)
    outside_look = make_look(user_id=user.id, items=[outside], **TEXT)
    _wear(client, look, MONDAY, headers)
    _wear(client, outside_look, MONDAY, headers)

    _unwear(client, look, headers)

    db.refresh(outside)
    assert outside.wear_count == 1
    assert outside.last_worn_at == MONDAY


def test_an_unsaved_look_can_be_unworn(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `is_saved` is not consulted here either. The button lives on the
    # saved-looks screen and that is the screen's policy, not the endpoint's.
    user = make_user()
    headers = authorization(user)
    look = make_look(
        user_id=user.id, items=[make_item(user_id=user.id, **READY)], is_saved=False, **TEXT
    )
    _wear(client, look, MONDAY, headers)

    assert _unwear(client, look, headers).status_code == 200


def test_the_undo_response_carries_the_hydrated_items(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The reason this is a 200 with a body rather than a 204: the counts changed
    # on every garment and the client cannot derive them, which is `DECISIONS.md`
    # 184's argument for the wear being non-optimistic, one direction along.
    user = make_user()
    headers = authorization(user)
    item = make_item(user_id=user.id, **READY)
    look = make_look(user_id=user.id, items=[item], **TEXT)
    _wear(client, look, MONDAY, headers)

    body = _unwear(client, look, headers).json()

    assert [row["id"] for row in body["items"]] == [str(item.id)]
    assert body["items"][0]["wear_count"] == 0
    assert body["items"][0]["last_worn_at"] is None


def test_undoing_another_users_wearing_is_404_not_403(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    owner = make_user()
    stranger = make_user()
    item = make_item(user_id=owner.id, **READY)
    look = make_look(user_id=owner.id, items=[item], **TEXT)
    _wear(client, look, MONDAY, authorization(owner))

    response = _unwear(client, look, authorization(stranger))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    # Nothing was written on the way to the refusal.
    db.refresh(item)
    assert item.wear_count == 1
    db.refresh(look)
    assert look.worn_at == MONDAY


def test_undoing_a_look_that_never_existed_is_the_same_404(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.delete(f"{LOOKS_URL}/{uuid.uuid4()}/wear", headers=authorization(user))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_undoing_requires_a_token(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
) -> None:
    look = make_look(user_id=make_user().id, **TEXT)

    response = client.delete(f"{LOOKS_URL}/{look.id}/wear")

    assert response.status_code == 401

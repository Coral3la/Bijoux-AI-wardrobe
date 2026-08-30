"""`POST /looks/{id}/wear` — one date on the look, one wearing on every garment.

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

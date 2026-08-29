"""`PATCH /looks/{id}` — the heart button, and the two keys it is allowed.

`04-API-SPEC.md`'s example body prints `is_saved`, `feedback` and `title`
together. Only two of the three are 3.2's, and `extra="forbid"` is what makes
the third a `422` rather than a silently dropped instruction — which is the
case worth testing hardest, because it is the one a reader of that document
would expect to work.

The rest is `update_item`'s shape one resource along: `exclude_unset` separates
a field left alone from a field changed, an empty body is refused, and another
account's row is a `404` rather than a `403`.
"""

import uuid
from collections.abc import Callable
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


def test_saving_a_look_persists_it(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"is_saved": True}, headers=authorization(user)
    )

    assert response.status_code == 200
    assert response.json()["is_saved"] is True
    # Re-read rather than trusting the body: the response is built from the
    # object in the session, so a missing `db.commit()` would answer 200 with
    # the change and leave the row untouched.
    db.expire(look)
    assert look.is_saved is True


def test_unsaving_a_saved_look_persists_that_too(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The heart is a toggle and the saved-looks screen renders it too, so the
    # false direction is a real request rather than symmetry for its own sake.
    user = make_user()
    look = make_look(user_id=user.id, is_saved=True, **TEXT)

    client.patch(f"{LOOKS_URL}/{look.id}", json={"is_saved": False}, headers=authorization(user))

    db.expire(look)
    assert look.is_saved is False


def test_the_title_can_be_changed(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"title": "Client meeting"}, headers=authorization(user)
    )

    assert response.json()["title"] == "Client meeting"
    db.expire(look)
    assert look.title == "Client meeting"


def test_a_title_is_stripped(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"title": "  Client meeting  "}, headers=authorization(user)
    )

    assert response.json()["title"] == "Client meeting"


def test_a_field_that_was_not_sent_is_left_alone(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `exclude_unset`'s whole job. Without it the first PATCH writes every
    # field the client did not send, and saving a look would erase its title.
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    client.patch(f"{LOOKS_URL}/{look.id}", json={"is_saved": True}, headers=authorization(user))

    db.expire(look)
    assert look.title == "Morning meetings"


def test_both_fields_can_be_sent_together(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    client.patch(
        f"{LOOKS_URL}/{look.id}",
        json={"is_saved": True, "title": "Client meeting"},
        headers=authorization(user),
    )

    db.expire(look)
    assert (look.is_saved, look.title) == (True, "Client meeting")


def test_the_response_carries_the_hydrated_items(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The heart replaces the card it was tapped on with this response, so a
    # PATCH that answered without items would blank the look on screen.
    user = make_user()
    items = [make_item(user_id=user.id, **READY) for _ in range(2)]
    look = make_look(user_id=user.id, items=[items[1], items[0]], **TEXT)

    body = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"is_saved": True}, headers=authorization(user)
    ).json()

    assert [item["id"] for item in body["items"]] == [str(items[1].id), str(items[0].id)]


def test_an_empty_body_is_refused(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(f"{LOOKS_URL}/{look.id}", json={}, headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_feedback_is_refused_until_task_3_3(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `04-API-SPEC.md` prints this key in the example body for this endpoint.
    # `extra="forbid"` is what stops it being accepted and dropped, which would
    # be a 200 saying a look was rated when the column is still NULL.
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"feedback": 1}, headers=authorization(user)
    )

    assert response.status_code == 422


@pytest.mark.parametrize("body", [{"is_saved": None}, {"title": None}])
def test_neither_field_can_be_cleared(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    body: dict[str, Any],
) -> None:
    # `is_saved` is NOT NULL, so an accepted null is an IntegrityError and a
    # 500 with no `code`; a cleared title is a card with an empty heading.
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(f"{LOOKS_URL}/{look.id}", json=body, headers=authorization(user))

    assert response.status_code == 422


@pytest.mark.parametrize("title", ["", "   "])
def test_a_blank_title_is_refused(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    title: str,
) -> None:
    # The whitespace case is the one that needs StringConstraints: the strip
    # runs before the length check, so "   " is measured as "".
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"title": title}, headers=authorization(user)
    )

    assert response.status_code == 422


def test_an_unknown_field_is_refused(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    look = make_look(user_id=user.id, **TEXT)

    response = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"is_savd": True}, headers=authorization(user)
    )

    assert response.status_code == 422


def test_patching_another_users_look_is_404_not_403(
    client: TestClient,
    db: Session,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    stranger = make_user()
    look = make_look(user_id=stranger.id, **TEXT)

    response = client.patch(
        f"{LOOKS_URL}/{look.id}", json={"is_saved": True}, headers=authorization(make_user())
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    db.expire(look)
    assert look.is_saved is False


def test_a_look_that_never_existed_is_the_same_404(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    response = client.patch(
        f"{LOOKS_URL}/{uuid.uuid4()}", json={"is_saved": True}, headers=authorization(make_user())
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_patching_requires_a_token(
    client: TestClient, make_look: Callable[..., Look], make_user: Callable[..., User]
) -> None:
    look = make_look(user_id=make_user().id, **TEXT)

    assert client.patch(f"{LOOKS_URL}/{look.id}", json={"is_saved": True}).status_code == 401

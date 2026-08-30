"""`GET /looks` — the first read of a `looks` row after the request that wrote it.

Every look this project has persisted since 2.7 was written and never looked
at again. What these cover is the four things `04-API-SPEC.md` gives one line
to and the route had to decide: the filter, the ordering, the hydration, and
who is allowed to see a row.

The hydration is the one worth naming. `Look` carries no `relationship()`, so
the items come from an explicit join in `look_items.position` order — and
`position` has had no reader on the server since 2.7 wrote it. These tests are
that reader.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

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


def test_the_list_returns_only_the_callers_looks(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    make_look(user_id=user.id, **TEXT)
    make_look(user_id=make_user().id, **TEXT)

    body = client.get(LOOKS_URL, headers=authorization(user)).json()

    assert body["total"] == 1
    assert len(body["looks"]) == 1


def test_is_saved_true_returns_only_saved_looks(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    saved = make_look(user_id=user.id, is_saved=True, **TEXT)
    make_look(user_id=user.id, is_saved=False, **TEXT)

    body = client.get(f"{LOOKS_URL}?is_saved=true", headers=authorization(user)).json()

    assert [look["id"] for look in body["looks"]] == [str(saved.id)]
    assert body["total"] == 1


def test_is_saved_false_returns_only_unsaved_looks(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The other half of the filter, and not a duplicate of the test above: a
    # route that ignored the parameter entirely passes that one whenever the
    # saved look happens to sort first.
    user = make_user()
    make_look(user_id=user.id, is_saved=True, **TEXT)
    unsaved = make_look(user_id=user.id, is_saved=False, **TEXT)

    body = client.get(f"{LOOKS_URL}?is_saved=false", headers=authorization(user)).json()

    assert [look["id"] for look in body["looks"]] == [str(unsaved.id)]


def test_omitting_the_filter_returns_both(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    make_look(user_id=user.id, is_saved=True, **TEXT)
    make_look(user_id=user.id, is_saved=False, **TEXT)

    body = client.get(LOOKS_URL, headers=authorization(user)).json()

    assert body["total"] == 2


def test_the_list_is_ordered_newest_first(
    client: TestClient,
    db: Any,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `now()` is the transaction timestamp, so three looks planted in one test
    # share a `created_at` and the tiebreaker alone would decide the order.
    # The timestamps are set explicitly for that reason.
    user = make_user()
    looks = [make_look(user_id=user.id, **TEXT) for _ in range(3)]
    for offset, look in enumerate(looks):
        look.created_at = datetime(2026, 3, 14, 9, offset, tzinfo=UTC)
    db.commit()

    body = client.get(LOOKS_URL, headers=authorization(user)).json()

    assert [look["id"] for look in body["looks"]] == [str(look.id) for look in reversed(looks)]


def test_the_items_come_back_in_the_models_own_order(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `look_items.position`'s first server-side reader. Written at 2.7 because
    # the ordering is destroyed at persistence if nothing records it, and read
    # by nothing until this endpoint.
    user = make_user()
    items = [make_item(user_id=user.id, **READY) for _ in range(3)]
    make_look(user_id=user.id, items=[items[2], items[0], items[1]], **TEXT)

    body = client.get(LOOKS_URL, headers=authorization(user)).json()

    returned = [item["id"] for item in body["looks"][0]["items"]]
    assert returned == [str(items[2].id), str(items[0].id), str(items[1].id)]


def test_a_look_carries_the_documented_fields(
    client: TestClient,
    make_look: Callable[..., Look],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The key set, pinned literally. Adding `is_saved` to this shape at 3.2
    # broke no test at all, because nothing anywhere asserted what a look on
    # the wire contains — so 3.3's `feedback` and 3.4's `worn_at` would land
    # the same way. `CONVENTIONS.md`'s rule about a derived expectation, one
    # artefact along: this list is transcribed from `04-API-SPEC.md`.
    user = make_user()
    make_look(user_id=user.id, items=[make_item(user_id=user.id, **READY)], **TEXT)

    body = client.get(LOOKS_URL, headers=authorization(user)).json()

    assert set(body["looks"][0]) == {
        "id",
        "occasion",
        "title",
        "items",
        "reasoning",
        "weather_note",
        "is_saved",
        "feedback",
    }


def test_the_date_range_filters_on_the_day_the_look_was_for(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    make_look(user_id=user.id, for_date=date(2026, 3, 10), **TEXT)
    wanted = make_look(user_id=user.id, for_date=date(2026, 3, 14), **TEXT)
    make_look(user_id=user.id, for_date=date(2026, 3, 20), **TEXT)

    body = client.get(
        f"{LOOKS_URL}?from_date=2026-03-12&to_date=2026-03-16", headers=authorization(user)
    ).json()

    assert [look["id"] for look in body["looks"]] == [str(wanted.id)]


def test_the_total_counts_the_filtered_set_and_not_the_page(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    for _ in range(3):
        make_look(user_id=user.id, is_saved=True, **TEXT)
    make_look(user_id=user.id, is_saved=False, **TEXT)

    body = client.get(f"{LOOKS_URL}?is_saved=true&limit=1", headers=authorization(user)).json()

    assert len(body["looks"]) == 1
    assert body["total"] == 3


def test_the_limit_cap_is_two_hundred_and_over_it_is_rejected(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    headers = authorization(make_user())

    assert client.get(f"{LOOKS_URL}?limit=200", headers=headers).status_code == 200
    assert client.get(f"{LOOKS_URL}?limit=201", headers=headers).status_code == 422


def test_the_list_requires_a_token(client: TestClient) -> None:
    assert client.get(LOOKS_URL).status_code == 401


def test_a_look_with_no_items_comes_back_with_an_empty_list(
    client: TestClient,
    make_look: Callable[..., Look],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Not reachable through `POST /looks/suggest`, which never writes a look
    # without items — but `_hydrate` groups by look id and a look missing from
    # the join would be a KeyError rather than an empty card.
    user = make_user()
    make_look(user_id=user.id, **TEXT)

    body = client.get(LOOKS_URL, headers=authorization(user)).json()

    assert body["looks"][0]["items"] == []


def test_the_trip_id_filter_does_not_exist_yet_and_is_ignored(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `04-API-SPEC.md` lists `trip_id` as a filter on this endpoint and the
    # column arrives with migration `0005`. FastAPI ignores an undeclared query
    # parameter, so this documents the gap rather than asserting a rejection:
    # sending it today filters nothing and answers 200 with every look.
    user = make_user()
    response = client.get(f"{LOOKS_URL}?trip_id={uuid.uuid4()}", headers=authorization(user))

    assert response.status_code == 200

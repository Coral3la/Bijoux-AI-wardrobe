"""`GET /items/stats`.

One of these tests is not about arithmetic. `/items/stats` is a literal path
under a router that already declares `/{item_id}`, and FastAPI matches in
declaration order — so the route registered second is unreachable, and the
symptom is a `422` complaining that "stats" is not a UUID.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models.item import Item
from app.models.user import User

pytestmark = pytest.mark.usefixtures("cloudinary_configured")

STATS_URL = "/api/v1/items/stats"

READY: dict[str, Any] = {"status": "ready", "layer": "base"}


def test_stats_is_not_parsed_as_an_item_id(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.get(STATS_URL, headers=authorization(user))

    assert response.status_code == 200


def test_stats_counts_by_category_and_colour(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    make_item(user_id=user.id, category="top", color_primary="black", **READY)
    make_item(user_id=user.id, category="top", color_primary="white", **READY)
    make_item(user_id=user.id, category="shoes", color_primary="black", **READY)

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["by_category"] == {"top": 2, "shoes": 1}
    assert body["by_color"] == {"black": 2, "white": 1}


def test_stats_counts_processing_and_failed_separately(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=user.id)
    make_item(user_id=user.id, status="failed")

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["total"] == 3
    assert body["processing"] == 1
    assert body["failed"] == 1
    # An untagged row has no category, so it counts in `total` and in nothing
    # else. Zero-filling the missing categories is the client's business.
    assert body["by_category"] == {"top": 1}


def test_stats_excludes_archived_rows(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=user.id, category="top", is_archived=True, **READY)

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["total"] == 1
    assert body["by_category"] == {"top": 1}


def test_stats_counts_only_the_callers_items(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    stranger = make_user()
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=stranger.id, category="top", **READY)

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["total"] == 1


def test_the_wear_numbers_are_zero_until_stage_3(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `wear_count` and `last_worn_at` arrive with migration 0003. Reporting
    # `never_worn = total` would be true today and would silently change
    # meaning when the columns land.
    user = make_user()
    make_item(user_id=user.id, category="top", **READY)

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["never_worn"] == 0
    assert body["most_worn"] == []

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


def test_never_worn_counts_ready_items_that_have_never_been_worn(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The `processing` row is the point of the `ready` filter: it has never
    # been worn and never could have been, and counting it would put a tile
    # with no name on it into "items you have never worn".
    user = make_user()
    make_item(user_id=user.id, category="top", wear_count=3, **READY)
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=user.id, category="top")

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["never_worn"] == 2


def test_worn_counts_ready_items_that_have_been_worn(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The same wardrobe as the test above, deliberately: 1 and 2 against three
    # `ready` rows is the partition, and the `processing` row is in neither.
    user = make_user()
    make_item(user_id=user.id, category="top", wear_count=3, **READY)
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=user.id, category="top")

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["worn"] == 1


def test_most_worn_is_the_single_item_with_the_highest_wear_count(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The whole object is asserted rather than its id, because the three keys
    # are the contract: `04-API-SPEC.md` printed a full item here until 3.6
    # and nothing pinned the narrowing.
    user = make_user()
    make_item(user_id=user.id, category="top", display_name="worn twice", wear_count=2, **READY)
    favourite = make_item(
        user_id=user.id, category="top", display_name="worn five times", wear_count=5, **READY
    )
    make_item(user_id=user.id, category="top", display_name="never worn", **READY)

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["most_worn"] == {
        "id": str(favourite.id),
        "display_name": "worn five times",
        "wear_count": 5,
    }


def test_the_wear_numbers_exclude_archived_rows(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The only worn garment in this wardrobe is archived, so `most_worn` is
    # null for a reason the fixture states rather than because nothing was
    # ever planted.
    user = make_user()
    make_item(user_id=user.id, category="top", **READY)
    make_item(user_id=user.id, category="top", wear_count=9, is_archived=True, **READY)
    make_item(user_id=user.id, category="top", is_archived=True, **READY)

    body = client.get(STATS_URL, headers=authorization(user)).json()

    assert body["worn"] == 0
    assert body["never_worn"] == 1
    assert body["most_worn"] is None

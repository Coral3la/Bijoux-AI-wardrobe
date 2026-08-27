"""The half of task 0.7's coverage that needs a database.

0.7 shipped the rejection paths with `get_db` stubbed to raise on use, which is
what proves nothing reaches the database before a batch is decided. What is
left is everything that writes: one row per file, short_id uniqueness and its
retry, and cross-user isolation on the two reads. `06-TESTING-STRATEGY.md`
lists collision retry under unit tests and cannot: the thing that *detects* a
collision is the uq_items_short_id constraint (`DECISIONS.md` 052).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes import items as items_route
from app.core.short_id import generate_short_id
from app.enums import SUBCATEGORIES, Category
from app.models.item import Item
from app.models.user import User

# Every response here carries an ItemResponse, whose image_url is computed at
# serialisation time and raises on an empty cloud name (`DECISIONS.md` 050).
pytestmark = pytest.mark.usefixtures("cloudinary_configured")

UPLOAD_URL = "/api/v1/items/upload"
LIST_URL = "/api/v1/items"

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64


def _part(name: str) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, JPEG, "image/jpeg"))


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Cloudinary stands in for itself. These tests are about the rows; 0.7
    already covers the storage failure path, and a real upload here would put
    an asset under a user id that is rolled back seconds later (047)."""
    public_ids: list[str] = []

    def fake_upload(file_bytes: bytes, user_id: uuid.UUID) -> str:
        public_id = f"bijoux/{user_id}/{uuid.uuid4().hex[:20]}"
        public_ids.append(public_id)
        return public_id

    monkeypatch.setattr(items_route, "upload_image", fake_upload)
    return public_ids


# --- GET /items behaviours 0.7 shipped and 0.10 left undefended -------------
#
# Reassigned into Stage 1 by STAGE-1's "Coverage inherited from Stage 0", to
# the task that first depends on each. They all plant their rows directly
# rather than going through DELETE or upload, so a broken archive and a broken
# filter cannot alibi each other.


def test_archived_items_are_excluded_unless_asked_for(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    make_item(user_id=user.id)
    make_item(user_id=user.id, is_archived=True)

    default = client.get(LIST_URL, headers=authorization(user))
    asked = client.get(f"{LIST_URL}?include_archived=true", headers=authorization(user))

    assert default.json()["total"] == 1
    assert asked.json()["total"] == 2


def test_the_status_filter_narrows_the_result_set(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # 1.7's polling loop empties only if this really filters. The one test
    # that existed proves a bad value is a 422 and says nothing about
    # filtering, so a query that stopped narrowing would present as slow
    # tagging rather than as a broken filter.
    user = make_user()
    make_item(user_id=user.id)
    make_item(user_id=user.id, status="ready", category="top", layer="base")

    processing = client.get(f"{LIST_URL}?status=processing", headers=authorization(user))

    assert processing.json()["total"] == 1
    assert [row["status"] for row in processing.json()["items"]] == ["processing"]


def test_the_list_defaults_to_a_hundred_items(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # 1.5's to defend. The wardrobe screen filters client-side over whatever it
    # loaded, so a store that took this default would filter over the first
    # hundred items and report wrong counts with no error anywhere.
    # Planted in bulk rather than through make_item: 101 separate commits is
    # the slowest test in the suite for no gain. short_id still comes from the
    # generator, because a literal outlives a run that fails to roll back.
    user = make_user()
    db.add_all(
        Item(
            user_id=user.id,
            short_id=generate_short_id(),
            image_public_id=f"bijoux/test/{uuid.uuid4().hex[:20]}",
        )
        for _ in range(101)
    )
    db.commit()

    response = client.get(LIST_URL, headers=authorization(user))

    assert len(response.json()["items"]) == 100
    # total counts the filter, not the page, so it disagrees with the page
    # length here on purpose.
    assert response.json()["total"] == 101


def test_the_limit_cap_is_two_hundred_and_over_it_is_rejected(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Both ends, because "201 is a 422" alone would also pass on a cap of 10.
    # Rejected rather than clamped: a silently clamped page is a client that
    # believes it holds the whole wardrobe and does not.
    user = make_user()

    at_cap = client.get(f"{LIST_URL}?limit=200", headers=authorization(user))
    over_cap = client.get(f"{LIST_URL}?limit=201", headers=authorization(user))

    assert at_cap.status_code == 200
    assert over_cap.status_code == 422
    assert over_cap.json()["code"] == "validation_error"


def test_the_list_is_ordered_newest_first(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # created_at is planted rather than taken from the default, and it has to
    # be: conftest joins every session to one connection-level transaction
    # (`DECISIONS.md` 074), so now() — the *transaction* timestamp — is one
    # value for the whole test no matter how many commits run inside it. The
    # default cannot produce two different times here, which is the same
    # property the tiebreak test below depends on from the other side.
    user = make_user()
    older = make_item(user_id=user.id, created_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC))
    newer = make_item(user_id=user.id, created_at=datetime(2026, 8, 22, 9, 0, tzinfo=UTC))

    response = client.get(LIST_URL, headers=authorization(user))

    assert [row["id"] for row in response.json()["items"]] == [str(newer.id), str(older.id)]


def test_rows_sharing_a_created_at_are_ordered_by_short_id(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # 1.7's to write. Every row of one upload shares a created_at to the
    # microsecond, so short_id is the only thing making the order total; with
    # the tiebreak gone the sort is on one repeated value and a page can
    # repeat or drop rows between two polls. The symptom is tiles changing
    # places, which reads as a grid bug and sends you to the wrong file.
    #
    # The shared timestamp is asserted rather than assumed. Without that line
    # this test would still pass if now() ever became the statement timestamp
    # — it would just have stopped testing the tiebreak, silently.
    user = make_user()
    planted = [
        Item(
            user_id=user.id,
            short_id=generate_short_id(),
            image_public_id=f"bijoux/test/{uuid.uuid4().hex[:20]}",
        )
        for _ in range(4)
    ]
    db.add_all(planted)
    db.commit()

    assert len({row.created_at for row in planted}) == 1

    response = client.get(LIST_URL, headers=authorization(user))

    returned = [row["short_id"] for row in response.json()["items"]]
    assert returned == sorted(row.short_id for row in planted)


# --- what upload writes -----------------------------------------------------


def test_upload_queues_one_tagging_task_per_row(
    client: TestClient,
    db: Session,
    stored: list[str],
    queued: list[uuid.UUID],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    client.post(
        UPLOAD_URL,
        files=[_part("a.jpg"), _part("b.jpg"), _part("c.jpg")],
        headers=authorization(user),
    )

    rows = db.scalars(select(Item).where(Item.user_id == user.id)).all()
    assert sorted(queued) == sorted(row.id for row in rows)


def test_upload_inserts_one_row_per_file(
    client: TestClient,
    db: Session,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.post(
        UPLOAD_URL,
        files=[_part("a.jpg"), _part("b.jpg"), _part("c.jpg")],
        headers=authorization(user),
    )

    assert response.status_code == 202
    rows = db.scalars(select(Item).where(Item.user_id == user.id)).all()
    assert len(rows) == 3


def test_uploaded_rows_start_as_processing(
    client: TestClient,
    db: Session,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The core UX promise: the response is on screen before tagging exists.
    user = make_user()

    client.post(UPLOAD_URL, files=[_part("a.jpg")], headers=authorization(user))

    rows = db.scalars(select(Item).where(Item.user_id == user.id)).all()
    assert [row.status for row in rows] == ["processing"]


def test_uploaded_rows_carry_no_tags_yet(
    client: TestClient,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.post(UPLOAD_URL, files=[_part("a.jpg")], headers=authorization(user))

    item = response.json()["items"][0]
    assert item["category"] is None
    assert item["display_name"] is None


def test_upload_stores_the_public_id_the_storage_layer_returned(
    client: TestClient,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.post(
        UPLOAD_URL, files=[_part("a.jpg"), _part("b.jpg")], headers=authorization(user)
    )

    returned = [item["image_public_id"] for item in response.json()["items"]]
    assert returned == stored


def test_upload_gives_every_row_in_a_batch_a_distinct_short_id(
    client: TestClient,
    db: Session,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    client.post(
        UPLOAD_URL,
        files=[_part(f"{n}.jpg") for n in range(5)],
        headers=authorization(user),
    )

    short_ids = db.scalars(select(Item.short_id).where(Item.user_id == user.id)).all()
    assert len(set(short_ids)) == 5


def test_upload_retries_the_batch_when_a_short_id_collides(
    client: TestClient,
    db: Session,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A collision is only detectable against a row that already holds the id,
    # so one is planted and the generator is forced onto it exactly once. The
    # route's own db.rollback() runs inside the fixture's transaction as a
    # savepoint release, which is why this can be asserted at all.
    user = make_user()
    planted = generate_short_id()
    db.add(Item(user_id=user.id, short_id=planted, image_public_id="bijoux/planted"))
    db.commit()

    draws = iter([planted])
    monkeypatch.setattr(
        items_route,
        "generate_short_id",
        lambda: next(draws, None) or generate_short_id(),
    )

    response = client.post(UPLOAD_URL, files=[_part("a.jpg")], headers=authorization(user))

    assert response.status_code == 202
    assert response.json()["items"][0]["short_id"] != planted


def test_a_short_id_collision_does_not_leave_a_partial_batch(
    client: TestClient,
    db: Session,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user()
    planted = generate_short_id()
    db.add(Item(user_id=user.id, short_id=planted, image_public_id="bijoux/planted"))
    db.commit()

    draws = iter([planted, generate_short_id()])
    monkeypatch.setattr(
        items_route,
        "generate_short_id",
        lambda: next(draws, None) or generate_short_id(),
    )

    client.post(UPLOAD_URL, files=[_part("a.jpg"), _part("b.jpg")], headers=authorization(user))

    uploaded = db.scalars(
        select(Item).where(Item.user_id == user.id, Item.short_id != planted)
    ).all()
    assert len(uploaded) == 2


def test_upload_gives_up_after_three_collisions(
    client: TestClient,
    db: Session,
    stored: list[str],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Three attempts is a bound with a number behind it (052). A generator that
    # only ever collides must surface, not loop.
    user = make_user()
    planted = generate_short_id()
    db.add(Item(user_id=user.id, short_id=planted, image_public_id="bijoux/planted"))
    db.commit()
    monkeypatch.setattr(items_route, "generate_short_id", lambda: planted)

    with pytest.raises(Exception, match="uq_items_short_id"):
        client.post(UPLOAD_URL, files=[_part("a.jpg")], headers=authorization(user))


# --- cross-user isolation ---------------------------------------------------


def test_list_items_returns_only_the_callers_items(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    mine = make_user()
    theirs = make_user()
    ours = Item(user_id=mine.id, short_id=generate_short_id(), image_public_id="bijoux/mine")
    db.add(ours)
    db.add(Item(user_id=theirs.id, short_id=generate_short_id(), image_public_id="bijoux/theirs"))
    db.commit()

    response = client.get(LIST_URL, headers=authorization(mine))

    body = response.json()
    assert [item["short_id"] for item in body["items"]] == [ours.short_id]


def test_the_total_counts_only_the_callers_items(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # total is a second query with the same filters. A filter dropped from one
    # and not the other is invisible in the list and wrong in the count.
    mine = make_user()
    theirs = make_user()
    db.add(Item(user_id=mine.id, short_id=generate_short_id(), image_public_id="bijoux/mine"))
    db.add(Item(user_id=theirs.id, short_id=generate_short_id(), image_public_id="bijoux/theirs"))
    db.commit()

    response = client.get(LIST_URL, headers=authorization(mine))

    assert response.json()["total"] == 1


def test_reading_another_users_item_is_404_not_403(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # 043: one code for every resource, because an API that distinguishes
    # "not yours" from "does not exist" is an existence oracle.
    mine = make_user()
    theirs = make_user()
    item = Item(user_id=theirs.id, short_id=generate_short_id(), image_public_id="bijoux/theirs")
    db.add(item)
    db.commit()
    db.refresh(item)

    response = client.get(f"{LIST_URL}/{item.id}", headers=authorization(mine))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_an_item_that_never_existed_is_the_same_404(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    mine = make_user()

    response = client.get(f"{LIST_URL}/{uuid.uuid4()}", headers=authorization(mine))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_reading_your_own_item_succeeds(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Without this the 404 above would pass just as well against a route that
    # refuses everyone.
    mine = make_user()
    item = Item(user_id=mine.id, short_id=generate_short_id(), image_public_id="bijoux/mine")
    db.add(item)
    db.commit()
    db.refresh(item)

    response = client.get(f"{LIST_URL}/{item.id}", headers=authorization(mine))

    assert response.status_code == 200
    assert response.json()["short_id"] == item.short_id


# --- the vocabulary the database has to know too, task 2.6a ------------------


@pytest.mark.parametrize("category", [Category.SWIMWEAR, Category.SLEEPWEAR])
def test_the_category_type_accepts_the_two_values_0003_added(
    db: Session,
    make_item: Callable[..., Item],
    category: Category,
) -> None:
    # The only test in the suite that can tell migration `0003` was written.
    # `items.category` is the `item_category` ENUM type, not text, so every
    # unit test over `app/enums.py` passes on a database that has never heard
    # of either value and the first real write is a DataError. Round-tripped
    # rather than only inserted: the read is what proves the label came back as
    # the member rather than as whatever the driver made of it.
    item = make_item(category=category, subcategory=SUBCATEGORIES[category][0])

    stored = db.execute(select(Item).where(Item.id == item.id)).scalar_one()

    assert stored.category is category

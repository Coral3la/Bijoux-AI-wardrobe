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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes import items as items_route
from app.core.short_id import generate_short_id
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


# --- what upload writes -----------------------------------------------------


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

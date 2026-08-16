"""The server defaults arrive with the INSERT, which is what makes both
`db.refresh` calls removable — and this is the only thing that says so.

`DECISIONS.md` 040 claimed that `created_at` "is a server default that
SQLAlchemy is not guaranteed to have fetched", and made `register` call
`db.refresh(user)` on that basis. 075 measured the same claim false for `Item`
and left the loop in place because 0.10 was a test task. Both were measured
before task 1.1 and both are false:

    users  RETURNING users.id, users.created_at
    items  RETURNING items.id, items.status, items.water_resistant,
           items.attributes, items.user_edited, items.is_archived,
           items.created_at, items.updated_at

A green suite is not evidence here and never was — 075 records that dropping
the item loop left all 192 tests passing, because every assertion reads values
that are present either way. What separates "the INSERT returned it" from "an
attribute access quietly went back to the database for it" is the statement
log, so that is what these assert. Without them the two removals would be
defended by nothing, and the failure they guard against is silent: a future
SQLAlchemy that stops emitting RETURNING turns one deliberate round trip into
one lazy load per response, with every test still green and every response
slower.

`expire_on_commit=False` on both `SessionLocal` and the test session is what
makes the attributes readable after commit at all; it is not what populates
them.
"""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, event

from app.db.session import SessionLocal
from app.models.user import User

REGISTER_URL = "/api/v1/auth/register"
UPLOAD_URL = "/api/v1/items/upload"

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64

pytestmark = pytest.mark.usefixtures("cloudinary_configured")


@pytest.fixture
def statements(connection: Connection) -> Iterator[list[str]]:
    """Every statement the request emits, in order, whitespace collapsed."""
    recorded: list[str] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        recorded.append(" ".join(statement.split()))

    event.listen(connection, "before_cursor_execute", record)
    yield recorded
    event.remove(connection, "before_cursor_execute", record)


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.v1.routes import items as items_route

    def fake_upload(file_bytes: bytes, user_id: uuid.UUID) -> str:
        return f"bijoux/{user_id}/{uuid.uuid4().hex[:20]}"

    monkeypatch.setattr(items_route, "upload_image", fake_upload)


def _selects_after_the_insert(statements: list[str], table: str) -> list[str]:
    inserted = next(
        index
        for index, statement in enumerate(statements)
        if statement.upper().startswith(f"INSERT INTO {table.upper()}")
    )
    return [s for s in statements[inserted + 1 :] if s.upper().startswith("SELECT")]


def test_registering_returns_the_users_server_defaults_from_the_insert(
    client: TestClient, statements: list[str]
) -> None:
    response = client.post(
        REGISTER_URL,
        json={
            "email": f"{uuid.uuid4().hex}@example.com",
            "password": "correct horse battery",
            "display_name": "Coral",
        },
    )

    assert response.status_code == 201
    inserts = [s for s in statements if s.upper().startswith("INSERT INTO USERS")]
    assert inserts == [inserts[0]]
    assert "RETURNING users.id, users.created_at" in inserts[0]


def test_registering_reads_no_row_back_after_the_insert(
    client: TestClient, statements: list[str]
) -> None:
    # The assertion that would fail if `db.refresh(user)` came back, and the one
    # that would fail if RETURNING ever stopped covering `created_at` and the
    # serialiser started lazy-loading it instead.
    client.post(
        REGISTER_URL,
        json={
            "email": f"{uuid.uuid4().hex}@example.com",
            "password": "correct horse battery",
            "display_name": "Coral",
        },
    )

    assert _selects_after_the_insert(statements, "users") == []


def test_uploading_returns_the_items_server_defaults_from_the_insert(
    client: TestClient,
    statements: list[str],
    stored: None,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.post(
        UPLOAD_URL, files=[("files", ("a.jpg", JPEG, "image/jpeg"))], headers=authorization(user)
    )

    assert response.status_code == 202
    inserts = [s for s in statements if s.upper().startswith("INSERT INTO ITEMS")]
    assert "RETURNING items.id" in inserts[0]
    assert "items.created_at" in inserts[0]
    assert "items.status" in inserts[0]


def test_uploading_a_batch_reads_no_row_back_after_the_insert(
    client: TestClient,
    statements: list[str],
    stored: None,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Three files rather than one: the loop 075 measured was one refresh *per
    # row*, so a batch is where its absence is worth the most and where a
    # reintroduced lazy load would be most visible.
    user = make_user()

    client.post(
        UPLOAD_URL,
        files=[("files", (f"{n}.jpg", JPEG, "image/jpeg")) for n in range(3)],
        headers=authorization(user),
    )

    assert _selects_after_the_insert(statements, "items") == []


def test_the_application_session_does_not_expire_rows_on_commit() -> None:
    # Asserting configuration rather than behaviour, deliberately and as a last
    # resort. Every test above replaces `get_db` with the fixture's session,
    # which sets `expire_on_commit=False` itself — so `SessionLocal` is never
    # exercised by this suite, and flipping it leaves all of them green.
    #
    # It matters more now than it did before the two refreshes came out: with
    # them gone, `expire_on_commit=True` would expire every attribute at commit
    # and each response would read its server defaults back with a second query
    # — the exact round trip those removals deleted, restored in production
    # only, where nothing looks.
    assert SessionLocal.kw["expire_on_commit"] is False

"""The test database, and the guard that keeps it from being the real one.

Read the order of the first three statements before changing anything here.
`TEST_DATABASE_URL` is copied into `DATABASE_URL` **before** anything from
`app` is imported, because `app.core.config` builds its `settings` singleton at
import time and `app.db.session` builds an engine from it at import time. Move
an `app` import above the copy and every test in the suite silently runs
against whatever `backend/.env` points at — which on this project is the
developer's live Neon database. `DECISIONS.md` 073.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class _ConfiguredUrls(BaseSettings):
    """Deliberately not `app.core.config.Settings` — importing that is the one
    thing this module must not do first. Same `env_file`, so the same value
    resolves here as would resolve there, with environment beating dotenv."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = ""
    TEST_DATABASE_URL: str = ""


_urls = _ConfiguredUrls()

if not _urls.TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is not set. The suite creates and drops rows, so it "
        "refuses to guess at a database. See backend/.env.example."
    )

if _urls.TEST_DATABASE_URL == _urls.DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is the same database as DATABASE_URL. Every test "
        "rolls its transaction back, but the schema is migrated and the "
        "developer's rows are one bad fixture away from being dropped."
    )

os.environ["DATABASE_URL"] = _urls.TEST_DATABASE_URL

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Connection, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.api.v1.routes import items as items_route  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.deps import get_db  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.core.short_id import generate_short_id  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.item import Item  # noqa: E402
from app.models.look import Look, LookItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import stylist, vision  # noqa: E402

# The copy above is only load-bearing if environment really does beat dotenv.
# Asserting it here turns that assumption into an import-time failure instead of
# a suite that quietly points somewhere else.
assert settings.DATABASE_URL == _urls.TEST_DATABASE_URL, (
    "settings did not resolve to TEST_DATABASE_URL; the import order in this file has been broken"
)

# Login and register hash for real. Everything else only needs a row that
# exists, and bcrypt at the default cost is ~250 ms a call — enough to be felt
# across a suite. verify_password returns False on an unreadable hash by
# design (security.py catches the ValueError), so this is not a way in.
UNUSABLE_PASSWORD_HASH = "not-a-bcrypt-hash"


def _row_counts() -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table: conn.scalar(text(f"SELECT count(*) FROM {table}")) or 0
            for table in ("users", "items", "looks", "look_items")
        }


@pytest.fixture(autouse=True)
def _no_live_openai(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """`CONVENTIONS.md` allows no test to call OpenAI unless it is marked
    `eval`, and until task 1.3 nothing enforced that — every fake was a
    per-test monkeypatch and a test that missed one simply spent money.

    One did. A tagging test faked `tag_item` at the name `tagging.py` imported
    and left `vision`'s own binding alone, so `validate_tags` retried against
    the live API on the developer's real key. It answered `400` and cost
    nothing, which is luck rather than a mechanism.

    `_client` rather than `tag_item`, because it is the single door: every call
    in this project goes through it, and a fake installed here cannot be routed
    around by importing the function from somewhere else.

    **Both doors, since task 2.4.** `stylist.py` has its own `_client` — the two
    contracts are pinned to their own models (`DECISIONS.md` 160) — so "the
    single door" became two the moment it landed, and a guard naming one of them
    is the same gap this fixture was written to close, one module along. The
    stylist call is also the expensive one: it carries the whole wardrobe."""
    if request.node.get_closest_marker("eval"):
        return

    def _refuse() -> Any:
        raise AssertionError(
            "this test reached for the OpenAI client. Fake the call, or mark "
            "the test @pytest.mark.eval if it is meant to spend money."
        )

    monkeypatch.setattr(vision, "_client", _refuse)
    monkeypatch.setattr(stylist, "_client", _refuse)


@pytest.fixture(autouse=True)
def queued(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """The tagging task, recorded instead of run. Task 1.3 put one behind every
    successful upload, and `TestClient` awaits background tasks before
    `client.post` returns — so without this, every test that uploads runs the
    real task, which opens a second connection outside the transaction these
    fixtures roll back.

    Autouse and in `conftest.py` rather than in one test file, because two of
    them drive the upload route: `test_items_rows.py` and
    `test_server_defaults.py`. Ask for it by name to assert on what was queued.

    **`test_uploaded_rows_start_as_processing` passed by accident in the window
    between 1.3 landing and this fixture existing, and that is worth writing
    down rather than quietly fixing.** The real task ran to completion and would
    have written `ready` — except that its own session cannot see a row the test
    has not committed, so it found nothing and returned, and the assertion held
    for a reason that has nothing to do with what it claims to measure. A test
    that passes for the wrong reason is a finding, not a near miss."""
    item_ids: list[uuid.UUID] = []

    async def record(item_id: uuid.UUID) -> None:
        item_ids.append(item_id)

    monkeypatch.setattr(items_route, "tag_and_store", record)
    return item_ids


@pytest.fixture(scope="session")
def _schema() -> Iterator[None]:
    # Not autouse: a run of tests/unit alone must not need a database at all,
    # which is the property DECISIONS.md 028, 038 and 052 bought for enums.py,
    # security.py and short_id.py. Only `connection` pulls this in.
    #
    # alembic resolves script_location against the working directory, not
    # against the ini file, so both are made absolute.
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # Without this, alembic's fileConfig runs with disable_existing_loggers=True
    # and switches off every application logger for the rest of the session, so
    # no test after this fixture can assert on a log line. `DECISIONS.md` 076.
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")

    # The per-test rollback is the most deletable line in this file: turn it
    # into a commit and every test still passes, while the database fills up
    # and later runs start seeing each other's rows. Comparing counts across
    # the session is what makes that a failure instead of a slow surprise.
    # Counts rather than "is empty", so a database left dirty by an earlier
    # crashed run does not report this run as the leak.
    before = _row_counts()
    yield
    after = _row_counts()
    assert after == before, (
        f"tests leaked rows into the test database: {before} -> {after}. "
        "Something committed outside the per-test transaction."
    )


@pytest.fixture
def connection(_schema: None) -> Iterator[Connection]:
    # One transaction per test, never committed. The session below joins it as
    # a SAVEPOINT, so a route calling db.commit() or db.rollback() — which
    # items.py does on a short_id collision — moves the savepoint and leaves
    # this transaction intact. Rolling it back is what empties the database.
    conn = engine.connect()
    transaction = conn.begin()
    try:
        yield conn
    finally:
        transaction.rollback()
        conn.close()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    # Every request in a test shares the fixture's session, so a row a test
    # wrote is visible to the route and a row a route wrote is visible to the
    # test — both inside the transaction that gets rolled back.
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    def _make(email: str | None = None, password: str | None = None, **columns: Any) -> User:
        user = User(
            email=email or f"{uuid.uuid4().hex}@example.com",
            password_hash=hash_password(password) if password else UNUSABLE_PASSWORD_HASH,
            **columns,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def make_item(db: Session, make_user: Callable[..., User]) -> Callable[..., Item]:
    """A planted row. `short_id` comes from the generator rather than a
    literal, because a literal survives any run that fails to roll back and
    leaves the suite red until someone truncates the table (`CONVENTIONS.md`)."""

    def _make(**columns: Any) -> Item:
        item = Item(
            user_id=columns.pop("user_id", None) or make_user().id,
            short_id=generate_short_id(),
            image_public_id=f"bijoux/test/{uuid.uuid4().hex[:20]}",
            **columns,
        )
        db.add(item)
        db.commit()
        return item

    return _make


@pytest.fixture
def make_look(db: Session, make_user: Callable[..., User]) -> Callable[..., Look]:
    """A persisted look, with `look_items` rows in the order given.

    Here rather than copied into two files because `GET /looks` and
    `PATCH /looks/{id}` both need one and neither is four lines — which is the
    line `test_looks_rows.py`'s `statements` fixture is on the other side of.

    `items` is a list of rows, and `position` is the index, so a test that cares
    about ordering states it by writing the list in the order it expects back.
    """

    def _make(items: list[Item] | None = None, **columns: Any) -> Look:
        user_id = columns.pop("user_id", None) or make_user().id
        look = Look(user_id=user_id, **columns)
        db.add(look)
        db.flush()
        db.add_all(
            [
                LookItem(look_id=look.id, item_id=item.id, position=position)
                for position, item in enumerate(items if items is not None else [])
            ]
        )
        db.commit()
        return look

    return _make


@pytest.fixture
def cloudinary_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any response carrying an ItemResponse needs a cloud name.

    `build_url` raises StorageError on an empty CLOUDINARY_CLOUD_NAME, and on a
    GET that happens during serialisation, after the handler has returned — a
    bare 500 with no `code` (`DECISIONS.md` 050). CI configures no Cloudinary
    credentials, so without this the item tests fail there and pass locally,
    which is the worst of both. `build_url` re-reads settings on every call,
    which is what makes monkeypatching it work at all (046).
    """
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")


@pytest.fixture
def authorization() -> Callable[[User], dict[str, str]]:
    # A real signed token through the real dependency, rather than overriding
    # get_current_user: cross-user isolation is only proven if the identity
    # under test arrived the way a client's would.
    def _header(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    return _header

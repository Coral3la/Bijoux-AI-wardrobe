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
from app.core.config import settings  # noqa: E402
from app.core.deps import get_db  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

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
            for table in ("users", "items")
        }


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

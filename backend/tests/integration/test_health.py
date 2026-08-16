"""GET /health, both branches, with no database anywhere.

`DECISIONS.md` 027 fixes three things about this route and none of them had a
test: it always returns 200, `status` reports the process while `db` reports
the dependency, and a failing dependency is reported in the body rather than by
letting Render recycle the only component still able to answer the question.

The `STAGE-0` acceptance criterion was ticked on one manual observation against
Neon. That proves the database was reachable; it proves nothing about the
`db: "error"` branch, which had never executed outside that check.

No database is needed here. The route takes its session through
`Depends(get_db)`, so both branches are reachable by overriding it — one stub
answers, one raises. The exception the failing stub raises is the one measured
to escape a genuinely unreachable database: a refused port, an unresolvable
host, a wrong password and a missing database all surface as
`sqlalchemy.exc.OperationalError`, so `main.py` catching `SQLAlchemyError` is
wide enough. That was checked rather than assumed, because 044 records a third
party where the documented base class was not wide enough.
"""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import APP_VERSION
from app.core.deps import get_db
from app.main import app

HEALTH_URL = "/health"

# What a psycopg failure looks like once SQLAlchemy has wrapped it. The message
# is the one a refused port produces; only the type is load-bearing.
UNREACHABLE = OperationalError(
    "SELECT 1", None, Exception("connection to server at 127.0.0.1 failed")
)


class _AnsweringSession:
    """Records that it was asked. Without this the route could drop the query
    entirely, return `db: "ok"` unconditionally, and every assertion below
    about the healthy path would still hold."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))


class _UnreachableSession:
    def execute(self, statement: Any) -> None:
        raise UNREACHABLE


@pytest.fixture
def answering() -> Iterator[_AnsweringSession]:
    session = _AnsweringSession()
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.clear()


@pytest.fixture
def healthy(answering: _AnsweringSession) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def unreachable() -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: _UnreachableSession()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_reports_ok_when_the_database_answers(healthy: TestClient) -> None:
    response = healthy.get(HEALTH_URL)

    assert response.status_code == 200
    assert response.json()["db"] == "ok"


def test_health_really_queries_the_database(
    healthy: TestClient, answering: _AnsweringSession
) -> None:
    # `db: "ok"` has to mean something happened. A route that never touches the
    # session would satisfy the test above and report a healthy dependency it
    # never contacted.
    healthy.get(HEALTH_URL)

    assert answering.statements == ["SELECT 1"]


def test_health_reports_error_when_the_database_is_unreachable(unreachable: TestClient) -> None:
    assert unreachable.get(HEALTH_URL).json()["db"] == "error"


def test_health_returns_200_when_the_database_is_unreachable(unreachable: TestClient) -> None:
    # The whole of 027. A 503 here recycles the instance on Render's free tier,
    # stacking a 30-50 second cold start on top of whatever the original fault
    # was — while Neon's free tier autosuspends, so a transient failure is an
    # ordinary event rather than an emergency.
    assert unreachable.get(HEALTH_URL).status_code == 200


def test_health_status_reports_the_process_not_the_dependency(unreachable: TestClient) -> None:
    # The two fields answer two different questions. If `status` mirrored `db`,
    # one of them would be redundant and the response would carry no more
    # information than its status code.
    assert unreachable.get(HEALTH_URL).json()["status"] == "ok"


def test_health_logs_a_warning_when_the_database_is_unreachable(
    unreachable: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    # Since the status code is 200 by design, the log line is the *only* signal
    # that the dependency is down. Asserting the event rather than the state
    # afterwards, per `06-TESTING-STRATEGY.md`.
    with caplog.at_level(logging.WARNING, logger="app.main"):
        unreachable.get(HEALTH_URL)

    assert [record.levelname for record in caplog.records] == ["WARNING"]


def test_health_reports_the_application_version(healthy: TestClient) -> None:
    # `04-API-SPEC.md` prints `0.4.0` as illustrative and warns that the value
    # does not track the task number, so the assertion is against the constant.
    assert healthy.get(HEALTH_URL).json()["version"] == APP_VERSION


def test_health_carries_no_keys_beyond_the_documented_three(healthy: TestClient) -> None:
    assert set(healthy.get(HEALTH_URL).json()) == {"status", "db", "version"}


def test_health_is_mounted_outside_the_api_version_prefix(healthy: TestClient) -> None:
    # 04-API-SPEC.md: /health is the one route outside /api/v1, because
    # 07-DEPLOYMENT.md pins Render's health check to /health and a liveness
    # probe should not be versioned alongside the application's own contract.
    assert healthy.get("/api/v1/health").status_code == 404

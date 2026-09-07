"""GET /weather — both failure codes, the rule string, the auth boundary, and
the `forecasts` table behind the cache.

The route's own job is small: pick the temperature, map two service exceptions
onto two status codes, and shape the body. All four are asserted here because
none of them is visible from `tests/unit/test_weather.py`, which never builds a
request.

Visual Crossing is stubbed at the transport, so nothing here leaves the process.

**The store commits outside the per-test transaction.** `weather.py` opens its
own `SessionLocal()` on a second pooled connection, so a row it writes is not
rolled back with the `db` fixture's, and a row seeded through `db` would be
invisible to it until commit. Both halves follow from that: every test in this
module starts and ends with the table empty, and a test that needs a row seeds
it through `_write_stored`, which is the one path that commits. `conftest.py`'s
leak guard counts six named tables and this is not one of them, so the fixture
below is the only thing that empties it.
"""

import datetime
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.enums import Condition
from app.models.forecast import StoredForecast
from app.models.user import User
from app.services import weather
from app.services.weather import Forecast

WEATHER_URL = "/api/v1/weather"

TODAY = datetime.date.today()
TEL_AVIV = (32.08, 34.78)


def _body(
    temp_max: float = 19.0,
    temp_min: float = 12.0,
    precip: float = 0.0,
    wind: float = 14.0,
    icon: str = "partly-cloudy-day",
    day: datetime.date | None = None,
) -> dict[str, Any]:
    return {
        "days": [
            {
                "datetime": (day or TODAY).isoformat(),
                "tempmax": temp_max,
                "tempmin": temp_min,
                "precip": precip,
                "windspeed": wind,
                "icon": icon,
                "source": "fcst",
            }
        ]
    }


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "VISUAL_CROSSING_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def clear_cache() -> Iterator[None]:
    weather.clear_cache()
    yield
    weather.clear_cache()


@pytest.fixture(autouse=True)
def empty_store(_schema: None) -> Iterator[None]:
    # Before as well as after: a crashed earlier run leaves rows behind, and a
    # row left for today would make the stored-hit test pass on its own.
    _empty_store()
    yield
    _empty_store()


def _empty_store() -> None:
    session = SessionLocal()
    try:
        session.execute(delete(StoredForecast))
        session.commit()
    finally:
        session.close()


def _seed(day: datetime.date, temp_max: float, fetched_at: datetime.datetime) -> None:
    lat, lon = TEL_AVIV
    forecast = Forecast(
        date=day,
        temp_min_c=12.0,
        temp_max_c=temp_max,
        precip_mm=0.0,
        wind_kph=14.0,
        condition=Condition.PARTLY_CLOUDY,
    )
    weather._write_stored(lat, lon, [forecast], fetched_at)


def _rows_for_today() -> list[StoredForecast]:
    lat, lon = TEL_AVIV
    session = SessionLocal()
    try:
        return list(
            session.scalars(
                select(StoredForecast).where(
                    StoredForecast.lat == lat,
                    StoredForecast.lon == lon,
                    StoredForecast.date == TODAY,
                )
            ).all()
        )
    finally:
        session.close()


def _refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(weather, "_transport", lambda: httpx.MockTransport(refused))


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def _stub(**kwargs: Any) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_body(**kwargs))

        monkeypatch.setattr(weather, "_transport", lambda: httpx.MockTransport(handler))

    return _stub


def test_returns_the_forecast_and_the_rule(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Callable[..., None],
) -> None:
    stub()
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": 32.08, "lon": 34.78, "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 200
    assert response.json() == {
        "date": TODAY.isoformat(),
        "temp_min_c": 12.0,
        "temp_max_c": 19.0,
        "precip_mm": 0.0,
        "wind_kph": 14.0,
        "condition": Condition.PARTLY_CLOUDY,
        "rule": (
            "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional."
        ),
    }


def test_the_rule_is_built_from_the_maximum_not_the_minimum(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Callable[..., None],
) -> None:
    # 04-API-SPEC.md's worked example is this exact pair, and it prints the
    # 16-21 rule. Under temp_min_c it would print "Outerwear is REQUIRED", so
    # this single assertion is the whole of DECISIONS.md 142.
    stub(temp_min=12.0, temp_max=19.0)
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": 32.08, "lon": 34.78, "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert "REQUIRED" not in response.json()["rule"]
    assert response.json()["rule"].startswith("Use warmth 2-3 for the base.")


def test_rain_reaches_the_rule_string(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Callable[..., None],
) -> None:
    stub(temp_max=12.0, precip=4.0)
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": 32.08, "lon": 34.78, "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert "water_resistant" in response.json()["rule"]


def test_a_date_past_the_horizon_is_400_forecast_unavailable(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    # One past the pre-check, not the horizon: the day between the two is
    # slack that leaves the process and is refused by `source`, not here.
    beyond = TODAY + datetime.timedelta(days=weather._PRECHECK_HORIZON_DAYS + 1)

    response = client.get(
        WEATHER_URL,
        params={"lat": 32.08, "lon": 34.78, "date": beyond.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "forecast_unavailable"
    assert str(weather.FORECAST_HORIZON_DAYS) in response.json()["detail"]


def test_an_unreachable_provider_is_502_forecast_unavailable(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(weather, "_transport", lambda: httpx.MockTransport(refused))
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": 32.08, "lon": 34.78, "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 502
    assert response.json()["code"] == "forecast_unavailable"


def test_both_failures_share_one_code_at_two_statuses(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # forecast_unavailable is the first code in the project used at two
    # statuses. Pinned so that splitting it later is a deliberate change to a
    # named test rather than a quiet one. DECISIONS.md 147.
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(weather, "_transport", lambda: httpx.MockTransport(refused))
    user = make_user()
    header = authorization(user)
    # One past the pre-check, not the horizon: the day between the two is
    # slack that leaves the process and is refused by `source`, not here.
    beyond = TODAY + datetime.timedelta(days=weather._PRECHECK_HORIZON_DAYS + 1)

    out_of_range = client.get(
        WEATHER_URL,
        params={"lat": 32.08, "lon": 34.78, "date": beyond.isoformat()},
        headers=header,
    )
    unreachable = client.get(
        WEATHER_URL,
        params={"lat": 32.08, "lon": 34.78, "date": TODAY.isoformat()},
        headers=header,
    )

    assert (out_of_range.status_code, unreachable.status_code) == (400, 502)
    assert out_of_range.json()["code"] == unreachable.json()["code"] == "forecast_unavailable"


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 91, "lon": 34.78},
        {"lat": 32.08, "lon": 181},
        {"lat": 32.08},
        {"lon": 34.78},
    ],
)
def test_bad_coordinates_are_422_before_any_request(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    params: dict[str, Any],
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("validation must reject before the provider is called")

    monkeypatch.setattr(weather, "_transport", lambda: httpx.MockTransport(explode))
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={**params, "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


# --- the forecasts table -----------------------------------------------------


def test_a_fresh_stored_row_reaches_no_provider(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a fresh stored row must be served without a request")

    monkeypatch.setattr(weather, "_transport", lambda: httpx.MockTransport(explode))
    _seed(TODAY, temp_max=25.0, fetched_at=datetime.datetime.now(datetime.UTC))
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": TEL_AVIV[0], "lon": TEL_AVIV[1], "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 200
    assert response.json()["temp_max_c"] == 25.0
    assert response.json()["rule"].startswith("Use items with warmth 1-2. Outerwear optional")


def test_a_provider_failure_is_answered_from_a_stale_row(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Three days old: far past STORE_TTL_SECONDS, so on its own this row would
    # be refetched. The provider failing is what makes it an answer.
    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)
    assert stale < datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        seconds=weather.STORE_TTL_SECONDS
    )
    _seed(TODAY, temp_max=25.0, fetched_at=stale)
    _refused(monkeypatch)
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": TEL_AVIV[0], "lon": TEL_AVIV[1], "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 200
    assert response.json()["temp_max_c"] == 25.0
    assert response.json()["date"] == TODAY.isoformat()


def test_a_provider_failure_with_no_row_for_the_day_is_still_502(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A row for a *different* day, so what is proved is that the fallback is
    # per requested day and not "any row for this place".
    tomorrow = TODAY + datetime.timedelta(days=1)
    _seed(tomorrow, temp_max=25.0, fetched_at=datetime.datetime.now(datetime.UTC))
    _refused(monkeypatch)
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": TEL_AVIV[0], "lon": TEL_AVIV[1], "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 502
    assert response.json()["code"] == "forecast_unavailable"


def test_a_second_answer_for_the_same_day_updates_the_row(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Callable[..., None],
) -> None:
    # A stale row is what sends the request on to the provider; the provider's
    # answer then has to land on that row rather than beside it.
    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)
    _seed(TODAY, temp_max=10.0, fetched_at=stale)
    stub(temp_max=19.0)
    user = make_user()

    response = client.get(
        WEATHER_URL,
        params={"lat": TEL_AVIV[0], "lon": TEL_AVIV[1], "date": TODAY.isoformat()},
        headers=authorization(user),
    )

    assert response.status_code == 200
    assert response.json()["temp_max_c"] == 19.0
    rows = _rows_for_today()
    assert len(rows) == 1
    assert rows[0].temp_max_c == 19.0
    assert rows[0].fetched_at > stale


def test_the_endpoint_requires_a_token(client: TestClient, stub: Callable[..., None]) -> None:
    # 04-API-SPEC.md line 4: bearer auth on everything except /auth/* and
    # /health. Without this the endpoint is an open proxy to a third-party API.
    stub()

    response = client.get(
        WEATHER_URL, params={"lat": 32.08, "lon": 34.78, "date": TODAY.isoformat()}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert response.headers["WWW-Authenticate"] == "Bearer"

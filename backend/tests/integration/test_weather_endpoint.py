"""GET /weather — both failure codes, the rule string, and the auth boundary.

The route's own job is small: pick the temperature, map two service exceptions
onto two status codes, and shape the body. All four are asserted here because
none of them is visible from `tests/unit/test_weather.py`, which never builds a
request.

Open-Meteo is stubbed at the transport, so nothing here leaves the process.
"""

import datetime
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.enums import Condition
from app.models.user import User
from app.services import weather

WEATHER_URL = "/api/v1/weather"

TODAY = datetime.date.today()


def _body(
    temp_max: float = 19.0,
    temp_min: float = 12.0,
    precip: float = 0.0,
    wind: float = 14.0,
    code: int = 2,
    day: datetime.date | None = None,
) -> dict[str, Any]:
    return {
        "daily": {
            "time": [(day or TODAY).isoformat()],
            "temperature_2m_max": [temp_max],
            "temperature_2m_min": [temp_min],
            "precipitation_sum": [precip],
            "wind_speed_10m_max": [wind],
            "weather_code": [code],
        }
    }


@pytest.fixture(autouse=True)
def clear_cache() -> Iterator[None]:
    weather.clear_cache()
    yield
    weather.clear_cache()


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
    beyond = TODAY + datetime.timedelta(days=weather.FORECAST_HORIZON_DAYS + 1)

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
    beyond = TODAY + datetime.timedelta(days=weather.FORECAST_HORIZON_DAYS + 1)

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

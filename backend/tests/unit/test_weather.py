"""The weather rule, the WMO map and the forecast cache. No network anywhere.

`build_rule` is the reason `03-AI-CONTRACTS.md` computes weather in Python
rather than letting the model reason about a temperature: it is a pure function
from three numbers to a string, so every band boundary is assertable without an
AI call. The twelve assertions the stage file asks for are
`test_rule_at_every_temperature_boundary` (ten) plus the two modifier tests.

`get_forecast` is exercised against a stubbed transport rather than the live
API. What that proves is our parsing of our own fixture, so the fixture is a
**verbatim copy of a real response body** — captured 2026-08-26 from
`api.open-meteo.com` for Tel Aviv — and `DECISIONS.md` 143 records the field
names and units it was checked against. A hand-written fixture would have
agreed with whatever this module happened to read.
"""

from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from app.enums import Condition
from app.services import weather
from app.services.weather import (
    FORECAST_HORIZON_DAYS,
    ForecastOutOfRangeError,
    ForecastProviderError,
    build_rule,
    condition_for,
    get_forecast,
)

# Captured verbatim on 2026-08-26 from
# api.open-meteo.com/v1/forecast?latitude=32.08&longitude=34.78&daily=... .
# The snapped coordinates are the provider's own grid, not a transcription
# error: 32.08 was sent and 32.0625 came back. See DECISIONS.md 145.
LIVE_BODY: dict[str, Any] = {
    "latitude": 32.0625,
    "longitude": 34.8125,
    "generationtime_ms": 0.11086463928222656,
    "utc_offset_seconds": 10800,
    "timezone": "Asia/Jerusalem",
    "timezone_abbreviation": "GMT+3",
    "elevation": 16.0,
    "daily_units": {
        "time": "iso8601",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "precipitation_sum": "mm",
        "wind_speed_10m_max": "km/h",
        "weather_code": "wmo code",
    },
    "daily": {
        "time": ["2026-08-26"],
        "temperature_2m_max": [31.7],
        "temperature_2m_min": [23.7],
        "precipitation_sum": [0.0],
        "wind_speed_10m_max": [11.8],
        "weather_code": [2],
    },
}

# The provider's own error envelope, captured from the same session by asking
# for a date past the horizon. Its shape is the reason a 400 from Open-Meteo is
# mapped to `ForecastOutOfRangeError` and not to the provider error.
LIVE_ERROR_BODY: dict[str, Any] = {
    "error": True,
    "reason": "Parameter 'start_date' is out of allowed range from 2026-05-25 to 2026-09-10",
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    weather.clear_cache()


def _transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.fixture
def stub_ok(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Records every request that reached the transport, so a test can assert
    the cache prevented a second one."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=LIVE_BODY)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(handler))
    return seen


# --- build_rule: the twelve assertions ------------------------------------


@pytest.mark.parametrize(
    "temp,expected_fragment",
    [
        (35, "warmth 1-2 only"),
        (28, "warmth 1-2 only"),  # boundary
        (27, "Outerwear optional"),
        (22, "Outerwear optional"),  # boundary
        (21, "optional"),
        (16, "optional"),  # boundary
        (15, "REQUIRED, warmth 3-4"),
        (10, "REQUIRED, warmth 3-4"),  # boundary
        (9, "REQUIRED, warmth 4-5"),
        (-5, "REQUIRED, warmth 4-5"),
    ],
)
def test_rule_at_every_temperature_boundary(temp: int, expected_fragment: str) -> None:
    assert expected_fragment in build_rule(temp, precip_mm=0, wind_kph=0)


def test_rain_modifier_appended() -> None:
    rule = build_rule(14, precip_mm=5, wind_kph=0)
    assert "water_resistant" in rule


def test_wind_modifier_appended() -> None:
    rule = build_rule(14, precip_mm=0, wind_kph=45)
    assert "Avoid flowy or a_line items" in rule


# --- build_rule: what the table does not pin down -------------------------


def test_every_band_emits_the_string_03_specifies() -> None:
    # Transcribed from 03-AI-CONTRACTS.md's table rather than derived from the
    # module, so a reworded rule fails here instead of silently moving the
    # expectation with it. This is 06's self-referential-expectation lesson.
    assert build_rule(30, 0, 0) == "Use items with warmth 1-2 only. Do NOT include any outerwear."
    assert build_rule(25, 0, 0) == (
        "Use items with warmth 1-2. Outerwear optional and only if warmth <= 2."
    )
    assert build_rule(18, 0, 0) == (
        "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional."
    )
    assert build_rule(12, 0, 0) == "Outerwear is REQUIRED, warmth 3-4."
    assert build_rule(5, 0, 0) == "Outerwear is REQUIRED, warmth 4-5, plus a mid layer."


@pytest.mark.parametrize(
    "temp,expected_fragment",
    [
        (27.9, "Outerwear optional"),
        (21.9, "warmth 2-3 for the base"),
        (15.9, "REQUIRED, warmth 3-4"),
        (9.9, "REQUIRED, warmth 4-5"),
    ],
)
def test_a_decimal_temperature_stays_in_the_lower_band(temp: float, expected_fragment: str) -> None:
    # The provider returns one decimal place (31.7 in the captured body) and
    # 03's table is written in whole degrees, so every band edge has a gap the
    # table does not name. Thresholds are lower bounds: 27.9 is not 28.
    assert expected_fragment in build_rule(temp, precip_mm=0, wind_kph=0)


def test_modifiers_are_off_at_their_own_boundary() -> None:
    # 03 says `precip_mm > 1` and `wind_kph > 30`, so 1.0 and 30.0 are dry and
    # calm. Asserted because a `>=` here would put the demo wardrobe into a
    # rain rule it has no water_resistant item to satisfy.
    rule = build_rule(14, precip_mm=1.0, wind_kph=30.0)
    assert "Rain expected" not in rule
    assert "Windy" not in rule


def test_both_modifiers_append_in_document_order() -> None:
    rule = build_rule(8, precip_mm=4, wind_kph=50)
    assert rule.index("Rain expected") < rule.index("Windy")
    assert rule.startswith("Outerwear is REQUIRED, warmth 4-5, plus a mid layer.")


# --- the WMO map ----------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        (0, Condition.CLEAR),
        (1, Condition.PARTLY_CLOUDY),
        (2, Condition.PARTLY_CLOUDY),
        (3, Condition.CLOUDY),
        (45, Condition.FOG),
        (48, Condition.FOG),
        (51, Condition.DRIZZLE),
        (57, Condition.DRIZZLE),
        (61, Condition.RAIN),
        (82, Condition.RAIN),
        (71, Condition.SNOW),
        (86, Condition.SNOW),
        (95, Condition.THUNDERSTORM),
        (99, Condition.THUNDERSTORM),
    ],
)
def test_wmo_code_maps_to_the_closed_vocabulary(code: int, expected: Condition) -> None:
    assert condition_for(code) == expected


def test_every_mapped_condition_is_in_the_vocabulary() -> None:
    assert {c.value for c in weather.WMO_CONDITIONS.values()} <= set(Condition.values())


def test_an_unknown_code_falls_back_and_says_so(caplog: pytest.LogCaptureFixture) -> None:
    # A code outside WMO 4677 must not fail the request: `condition` is a label
    # and an icon, while the rule that actually dresses the user is computed
    # from temperature, rain and wind and is unaffected. DECISIONS.md 146.
    #
    # Asserted on the record attribute rather than on `caplog.text`, and the
    # difference is not cosmetic: `extra=` sets an attribute, and only
    # `JsonFormatter` reads it back out. `caplog.text` renders with the plain
    # development formatter, which drops every extra silently — so a test
    # written against it would pass with the code omitted from the log.
    with caplog.at_level("WARNING"):
        assert condition_for(4677) == Condition.CLOUDY

    assert [record.weather_code for record in caplog.records] == [4677]


# --- get_forecast: parsing the real response shape ------------------------


@pytest.mark.asyncio
async def test_parses_the_captured_live_body(stub_ok: list[httpx.Request]) -> None:
    forecast = await get_forecast(32.08, 34.78, date(2026, 8, 26))

    assert forecast.date == date(2026, 8, 26)
    assert forecast.temp_max_c == 31.7
    assert forecast.temp_min_c == 23.7
    assert forecast.precip_mm == 0.0
    assert forecast.wind_kph == 11.8
    assert forecast.condition == Condition.PARTLY_CLOUDY


@pytest.mark.asyncio
async def test_requests_the_field_names_the_provider_documents(
    stub_ok: list[httpx.Request],
) -> None:
    # These five names were verified against a live call on 2026-08-26. The one
    # that matters is `wind_speed_10m_max`: the legacy spelling
    # `windspeed_10m_max` is what most examples use, and asking for a name the
    # provider no longer returns yields a 200 with the key absent.
    await get_forecast(32.08, 34.78, date(2026, 8, 26))

    daily = stub_ok[0].url.params["daily"].split(",")
    assert daily == [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "wind_speed_10m_max",
        "weather_code",
    ]
    assert stub_ok[0].url.params["timezone"] == "auto"


@pytest.mark.asyncio
async def test_coordinates_are_rounded_before_they_leave(stub_ok: list[httpx.Request]) -> None:
    await get_forecast(32.0812345, 34.7787654, date(2026, 8, 26))

    assert stub_ok[0].url.params["latitude"] == "32.08"
    assert stub_ok[0].url.params["longitude"] == "34.78"


# --- the cache ------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_request_for_the_same_key_does_not_leave(
    stub_ok: list[httpx.Request],
) -> None:
    await get_forecast(32.08, 34.78, date(2026, 8, 26))
    await get_forecast(32.08, 34.78, date(2026, 8, 26))

    assert len(stub_ok) == 1


@pytest.mark.asyncio
async def test_coordinates_that_round_together_share_one_entry(
    stub_ok: list[httpx.Request],
) -> None:
    # 32.081 and 32.0842 are 350 m apart and Open-Meteo snaps both to the same
    # grid cell, so a cache keyed on full precision would never hit.
    await get_forecast(32.081, 34.78, date(2026, 8, 26))
    await get_forecast(32.0842, 34.7811, date(2026, 8, 26))

    assert len(stub_ok) == 1


@pytest.mark.asyncio
async def test_a_different_date_is_a_different_entry(stub_ok: list[httpx.Request]) -> None:
    await get_forecast(32.08, 34.78, date(2026, 8, 26))
    await get_forecast(32.08, 34.78, date(2026, 8, 27))

    assert len(stub_ok) == 2


@pytest.mark.asyncio
async def test_an_expired_entry_is_fetched_again(
    stub_ok: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_000.0
    monkeypatch.setattr(weather.time, "monotonic", lambda: now)
    await get_forecast(32.08, 34.78, date(2026, 8, 26))

    now += weather.CACHE_TTL_SECONDS + 1
    await get_forecast(32.08, 34.78, date(2026, 8, 26))

    assert len(stub_ok) == 2


@pytest.mark.asyncio
async def test_an_entry_inside_the_ttl_is_not_fetched_again(
    stub_ok: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_000.0
    monkeypatch.setattr(weather.time, "monotonic", lambda: now)
    await get_forecast(32.08, 34.78, date(2026, 8, 26))

    now += weather.CACHE_TTL_SECONDS - 1
    await get_forecast(32.08, 34.78, date(2026, 8, 26))

    assert len(stub_ok) == 1


# --- failure paths --------------------------------------------------------


@pytest.mark.asyncio
async def test_a_date_past_the_horizon_never_reaches_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the horizon guard must run before any network call")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(explode))

    with pytest.raises(ForecastOutOfRangeError):
        await get_forecast(32.08, 34.78, date.today() + timedelta(days=FORECAST_HORIZON_DAYS + 1))


@pytest.mark.asyncio
async def test_the_last_servable_date_is_allowed(stub_ok: list[httpx.Request]) -> None:
    # Measured 2026-08-26: the provider served 2026-09-10 and refused
    # 2026-09-11, so the horizon is today + 15, not today + 16.
    await get_forecast(32.08, 34.78, date.today() + timedelta(days=FORECAST_HORIZON_DAYS))

    assert len(stub_ok) == 1


@pytest.mark.asyncio
async def test_a_provider_400_is_out_of_range_rather_than_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 400 from Open-Meteo means our request was refused, not that the service
    # is down — a date older than its archive window arrives this way, past the
    # local guard. Mapping it to the provider error would answer 502 for a
    # request that was simply unanswerable.
    def bad_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=LIVE_ERROR_BODY)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(bad_request))

    with pytest.raises(ForecastOutOfRangeError):
        await get_forecast(32.08, 34.78, date(2026, 8, 26))


@pytest.mark.asyncio
async def test_an_unreachable_provider_raises_the_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(refused))

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, date(2026, 8, 26))


@pytest.mark.asyncio
async def test_a_500_raises_the_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream unavailable")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(broken))

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, date(2026, 8, 26))


@pytest.mark.asyncio
async def test_a_body_missing_the_day_raises_the_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 200 whose `daily` arrays are empty is the shape a wrong field name
    # produces, and it must not surface as an IndexError from inside a service.
    def empty(request: httpx.Request) -> httpx.Response:
        body = {**LIVE_BODY, "daily": {k: [] for k in LIVE_BODY["daily"]}}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(empty))

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, date(2026, 8, 26))


@pytest.mark.asyncio
async def test_a_failure_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json=LIVE_BODY)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(flaky))

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, date(2026, 8, 26))
    forecast = await get_forecast(32.08, 34.78, date(2026, 8, 26))

    assert forecast.temp_max_c == 31.7
    assert calls == 2

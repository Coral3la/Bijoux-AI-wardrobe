"""The weather rule, the icon map and the forecast cache. No network anywhere.

`build_rule` is the reason `03-AI-CONTRACTS.md` computes weather in Python
rather than letting the model reason about a temperature: it is a pure function
from three numbers to a string, so every band boundary is assertable without an
AI call. The twelve assertions the stage file asks for are
`test_rule_at_every_temperature_boundary` (ten) plus the two modifier tests.

`get_forecast` is exercised against a stubbed transport rather than the live
API. What that proves is our parsing of our own fixture, so the fixture is a
**verbatim copy of a real response body** — captured 2026-09-07 from
`weather.visualcrossing.com` for Tel Aviv — and `DECISIONS.md` 234 records the
field names and units it was checked against. A hand-written fixture would have
agreed with whatever this module happened to read.
"""

from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.enums import Condition
from app.services import weather
from app.services.weather import (
    FORECAST_HORIZON_DAYS,
    Forecast,
    ForecastOutOfRangeError,
    ForecastProviderError,
    build_rule,
    condition_for,
    get_daily_forecast,
    get_forecast,
    requires_outerwear,
    summarize_forecast,
)

# Captured verbatim on 2026-09-07 from
# weather.visualcrossing.com/.../timeline/32.08,34.78/2026-09-07/2026-09-07
# with the production query string. The coordinates come back as sent — no
# provider grid, unlike Open-Meteo's 32.0625 — and today's `source` is `comb`,
# observations so far combined with forecast, which is why the guard refuses
# `stats` by name rather than allow-listing `fcst`. `stub_ok` re-dates the day
# to the one each request asks for and serves the rest as captured: since B2 of
# the 2026-09-05 review, `get_forecast` refuses an answer for a day it did not
# ask for, and two tests below ask for days other than this one.
LIVE_BODY: dict[str, Any] = {
    "queryCost": 1,
    "latitude": 32.08,
    "longitude": 34.78,
    "resolvedAddress": "32.08,34.78",
    "address": "32.08,34.78",
    "timezone": "Asia/Jerusalem",
    "tzoffset": 3.0,
    "days": [
        {
            "datetime": "2026-09-07",
            "tempmax": 31.0,
            "tempmin": 25.0,
            "precip": 0.0,
            "windspeed": 20.1,
            "icon": "partly-cloudy-day",
            "source": "comb",
        }
    ],
}

CAPTURED = date(2026, 9, 7)


def _day(
    day: str, tempmax: float, tempmin: float, precip: float, windspeed: float, icon: str
) -> dict[str, Any]:
    return {
        "datetime": day,
        "tempmax": tempmax,
        "tempmin": tempmin,
        "precip": precip,
        "windspeed": windspeed,
        "icon": icon,
        "source": "fcst",
    }


# Four days in the shape `LIVE_BODY` has, and **the shape is the part that was
# captured** — the field names, the units and the one-object-per-day layout are
# 2026-09-07's, the numbers are not. A four-day live body could not be committed
# and stay meaningful: its dates are relative to the day it was fetched, and a
# fixture naming absolute dates in the past describes a range the horizon check
# now refuses. What this fixture is for is the one thing `LIVE_BODY` cannot
# show, having a single day: that the parser reads *all* of them, in order.
RANGE_BODY: dict[str, Any] = {
    "queryCost": 1,
    "latitude": 52.52,
    "longitude": 13.41,
    "resolvedAddress": "52.52,13.41",
    "address": "52.52,13.41",
    "timezone": "Europe/Berlin",
    "tzoffset": 1.0,
    "days": [
        _day("2026-03-14", 12.4, 4.2, 4.0, 18.5, "rain"),
        _day("2026-03-15", 14.1, 6.0, 0.0, 12.0, "cloudy"),
        _day("2026-03-16", 17.3, 8.8, 0.0, 9.4, "clear-day"),
        _day("2026-03-17", 15.0, 7.1, 0.2, 33.6, "partly-cloudy-day"),
    ],
}

BERLIN = (52.52, 13.41)
TRIP_START = date(2026, 3, 14)
TRIP_END = date(2026, 3, 17)

# The provider's own `400`, captured from the same session by sending an
# impossible date: plain text, one line, and it does not echo the request. A
# date past the horizon does *not* arrive this way — the provider answers it
# from statistics with a `200`, which is what `source` is requested for.
LIVE_ERROR_TEXT = (
    "Bad API Request:Start date time value 2026-99-99 cannot be parsed. "
    "Format must be yyyy-M-d['T'H:m:s][.SSS][X]"
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    weather.clear_cache()


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "VISUAL_CROSSING_API_KEY", "test-key")


def _transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _requested(request: httpx.Request) -> tuple[str, str, str]:
    """The location and the two dates, which travel in the path rather than
    the query string: `.../timeline/{lat},{lon}/{start}/{end}`."""
    *_, location, start, end = request.url.path.split("/")
    return location, start, end


@pytest.fixture
def stub_range(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """`stub_ok` for the four-day body. Its own fixture rather than a
    parameter on that one, because every range test asserts against
    `RANGE_BODY`'s numbers and a shared fixture would have to be told which
    body it was serving in each of them.

    Answers only the days the request asked for, as the provider does: a
    one-day `get_forecast` warming the cache is refused a four-day answer
    since B2, and the four-day tests ask for the whole window anyway."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        _, start, end = _requested(request)
        days = [day["datetime"] for day in RANGE_BODY["days"]]
        for day in (start, end):
            assert day in days, f"{day} is outside RANGE_BODY, {days[0]} to {days[-1]}"
        first = days.index(start)
        last = days.index(end) + 1
        return httpx.Response(200, json={**RANGE_BODY, "days": RANGE_BODY["days"][first:last]})

    monkeypatch.setattr(weather, "_transport", lambda: _transport(handler))
    return seen


@pytest.fixture
def stub_ok(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Records every request that reached the transport, so a test can assert
    the cache prevented a second one.

    Answers `LIVE_BODY` dated as the request asked. `get_forecast` refuses a
    day it did not ask for since B2, and two tests here ask for a day other
    than the captured one; every other request asks for 2026-09-07 and gets
    the capture untouched."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        _, start, _ = _requested(request)
        day = {**LIVE_BODY["days"][0], "datetime": start}
        return httpx.Response(200, json={**LIVE_BODY, "days": [day]})

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


# --- requires_outerwear ---------------------------------------------------


@pytest.mark.parametrize("temp", [15, 10, 9, -5])
def test_the_two_demanding_bands_require_outerwear(temp: int) -> None:
    # Rule 6 of `03`'s validation table asks this question of a sentence, never
    # of a temperature — `validate_look_response` is given the rule and not the
    # forecast. Both bands are asserted with their modifiers appended, because
    # rain is exactly when the cold bands fire.
    assert requires_outerwear(build_rule(temp, precip_mm=5, wind_kph=45))


@pytest.mark.parametrize("temp", [35, 28, 27, 22, 21, 16])
def test_the_milder_bands_do_not_require_outerwear(temp: int) -> None:
    assert not requires_outerwear(build_rule(temp, precip_mm=5, wind_kph=45))


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


# --- the sentence the prompt carries --------------------------------------


def forecast_at(temp_max_c: float, precip_mm: float) -> Forecast:
    return Forecast(
        date=date(2026, 3, 14),
        temp_min_c=temp_max_c - 6,
        temp_max_c=temp_max_c,
        precip_mm=precip_mm,
        wind_kph=14.0,
        condition=Condition.RAIN if precip_mm > 1 else Condition.PARTLY_CLOUDY,
    )


def test_the_summary_is_the_sentence_03_prints() -> None:
    # 03-AI-CONTRACTS.md's single-day user message, transcribed: `18°C, no rain.`
    assert summarize_forecast(forecast_at(18.0, 0.0)) == "18°C, no rain."


def test_rain_is_reported_in_millimetres_without_a_trailing_zero() -> None:
    assert summarize_forecast(forecast_at(12.0, 4.0)) == "12°C, rain 4mm."


def test_the_summary_and_the_rule_agree_about_what_rain_is() -> None:
    # The one boundary worth pinning: 1.0 mm is dry to `build_rule`, so a
    # summary that called it rain would put "rain 1mm" above a rule that says
    # nothing about rain — and the model is told to obey the rule exactly.
    forecast = forecast_at(14.0, 1.0)
    assert "no rain" in summarize_forecast(forecast)
    assert "Rain expected" not in build_rule(
        forecast.temp_max_c, forecast.precip_mm, forecast.wind_kph
    )


def test_the_maximum_is_the_temperature_that_is_printed() -> None:
    # DECISIONS.md 142: two temperatures arrive and the document's worked
    # example is only self-consistent under the maximum.
    assert summarize_forecast(forecast_at(19.0, 0.0)).startswith("19°C")


def test_a_decimal_temperature_is_rounded_to_a_whole_degree() -> None:
    assert summarize_forecast(forecast_at(18.4, 0.0)) == "18°C, no rain."


# --- the icon map ---------------------------------------------------------


@pytest.mark.parametrize(
    "icon,expected",
    [
        ("clear-day", Condition.CLEAR),
        ("clear-night", Condition.CLEAR),
        ("partly-cloudy-day", Condition.PARTLY_CLOUDY),
        ("partly-cloudy-night", Condition.PARTLY_CLOUDY),
        ("cloudy", Condition.CLOUDY),
        ("wind", Condition.CLOUDY),
        ("fog", Condition.FOG),
        ("rain", Condition.RAIN),
        ("showers-night", Condition.RAIN),
        ("snow", Condition.SNOW),
        ("snow-showers-day", Condition.SNOW),
        ("thunder-rain", Condition.THUNDERSTORM),
        ("thunder-showers-night", Condition.THUNDERSTORM),
    ],
)
def test_an_icon_maps_to_the_closed_vocabulary(icon: str, expected: Condition) -> None:
    assert condition_for(icon) == expected


def test_every_mapped_condition_is_in_the_vocabulary() -> None:
    assert {c.value for c in weather.ICON_CONDITIONS.values()} <= set(Condition.values())


def test_an_unknown_icon_falls_back_and_says_so(caplog: pytest.LogCaptureFixture) -> None:
    # An icon outside the `icons2` set must not fail the request: `condition`
    # is a label and an icon, while the rule that actually dresses the user is
    # computed from temperature, rain and wind and is unaffected. DECISIONS.md 146.
    #
    # Asserted on the record attribute rather than on `caplog.text`, and the
    # difference is not cosmetic: `extra=` sets an attribute, and only
    # `JsonFormatter` reads it back out. `caplog.text` renders with the plain
    # development formatter, which drops every extra silently — so a test
    # written against it would pass with the code omitted from the log.
    with caplog.at_level("WARNING"):
        assert condition_for("hail") == Condition.CLOUDY

    assert [record.icon for record in caplog.records] == ["hail"]


# --- get_forecast: parsing the real response shape ------------------------


@pytest.mark.asyncio
async def test_parses_the_captured_live_body(stub_ok: list[httpx.Request]) -> None:
    forecast = await get_forecast(32.08, 34.78, CAPTURED)

    assert forecast.date == CAPTURED
    assert forecast.temp_max_c == 31.0
    assert forecast.temp_min_c == 25.0
    assert forecast.precip_mm == 0.0
    assert forecast.wind_kph == 20.1
    assert forecast.condition == Condition.PARTLY_CLOUDY


@pytest.mark.asyncio
async def test_a_null_precip_is_a_dry_day(monkeypatch: pytest.MonkeyPatch) -> None:
    # Null is the provider saying none was measured. An *absent* key is not the
    # same thing and is asserted below to stay a failure.
    day = {**LIVE_BODY["days"][0], "precip": None}
    monkeypatch.setattr(
        weather,
        "_transport",
        lambda: _transport(lambda r: httpx.Response(200, json={"days": [day]})),
    )

    forecast = await get_forecast(32.08, 34.78, CAPTURED)

    assert forecast.precip_mm == 0.0


@pytest.mark.asyncio
async def test_a_null_temperature_is_a_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    day = {**LIVE_BODY["days"][0], "tempmax": None}
    monkeypatch.setattr(
        weather,
        "_transport",
        lambda: _transport(lambda r: httpx.Response(200, json={"days": [day]})),
    )

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, CAPTURED)


@pytest.mark.asyncio
async def test_requests_the_elements_the_provider_documents(
    stub_ok: list[httpx.Request],
) -> None:
    # These seven names were verified against a live call on 2026-09-07. The
    # order is asserted on purpose: a renamed element is a 200 with the key
    # absent, and this is where that shows up as a diff. `unitGroup` is what
    # makes the units °C, mm and km/h, and `iconSet` is what makes `icon` the
    # vocabulary `ICON_CONDITIONS` maps.
    await get_forecast(32.08, 34.78, CAPTURED)

    params = stub_ok[0].url.params
    assert params["elements"].split(",") == [
        "datetime",
        "tempmax",
        "tempmin",
        "precip",
        "windspeed",
        "icon",
        "source",
    ]
    assert params["unitGroup"] == "metric"
    assert params["iconSet"] == "icons2"
    assert params["include"] == "days"


@pytest.mark.asyncio
async def test_coordinates_are_rounded_before_they_leave(stub_ok: list[httpx.Request]) -> None:
    await get_forecast(32.0812345, 34.7787654, CAPTURED)

    assert _requested(stub_ok[0]) == ("32.08,34.78", "2026-09-07", "2026-09-07")


# --- the cache ------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_request_for_the_same_key_does_not_leave(
    stub_ok: list[httpx.Request],
) -> None:
    await get_forecast(32.08, 34.78, CAPTURED)
    await get_forecast(32.08, 34.78, CAPTURED)

    assert len(stub_ok) == 1


@pytest.mark.asyncio
async def test_coordinates_that_round_together_share_one_entry(
    stub_ok: list[httpx.Request],
) -> None:
    # 32.081 and 32.0842 are 350 m apart, closer than any forecast resolves,
    # so a cache keyed on full precision would never hit.
    await get_forecast(32.081, 34.78, CAPTURED)
    await get_forecast(32.0842, 34.7811, CAPTURED)

    assert len(stub_ok) == 1


@pytest.mark.asyncio
async def test_a_different_date_is_a_different_entry(stub_ok: list[httpx.Request]) -> None:
    await get_forecast(32.08, 34.78, CAPTURED)
    await get_forecast(32.08, 34.78, CAPTURED + timedelta(days=1))

    assert len(stub_ok) == 2


@pytest.mark.asyncio
async def test_an_expired_entry_is_fetched_again(
    stub_ok: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_000.0
    monkeypatch.setattr(weather.time, "monotonic", lambda: now)
    await get_forecast(32.08, 34.78, CAPTURED)

    now += weather.CACHE_TTL_SECONDS + 1
    await get_forecast(32.08, 34.78, CAPTURED)

    assert len(stub_ok) == 2


@pytest.mark.asyncio
async def test_an_entry_inside_the_ttl_is_not_fetched_again(
    stub_ok: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_000.0
    monkeypatch.setattr(weather.time, "monotonic", lambda: now)
    await get_forecast(32.08, 34.78, CAPTURED)

    now += weather.CACHE_TTL_SECONDS - 1
    await get_forecast(32.08, 34.78, CAPTURED)

    assert len(stub_ok) == 1


# --- failure paths --------------------------------------------------------


@pytest.mark.asyncio
async def test_a_date_past_the_horizon_never_reaches_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the horizon guard must run before any network call")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(explode))
    past_the_slack = date.today() + timedelta(days=weather._PRECHECK_HORIZON_DAYS + 1)

    with pytest.raises(ForecastOutOfRangeError):
        await get_forecast(32.08, 34.78, past_the_slack)


@pytest.mark.asyncio
async def test_the_last_servable_date_is_allowed(stub_ok: list[httpx.Request]) -> None:
    # Measured 2026-09-07: today + 14 answered `fcst` and today + 15 answered
    # `stats`, so the horizon is 14, not Open-Meteo's 15.
    await get_forecast(32.08, 34.78, date.today() + timedelta(days=FORECAST_HORIZON_DAYS))

    assert len(stub_ok) == 1


@pytest.mark.asyncio
async def test_the_day_of_slack_is_refused_when_the_provider_answers_statistics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The pre-check lets today + 15 leave the process, because a browser a few
    # hours ahead of a UTC server means that day when it says 14. When the
    # provider then answers the day from climate averages — a body shaped
    # exactly like a forecast, marked only by `source` — it is refused as out
    # of range, not served and not a provider failure.
    slack = date.today() + timedelta(days=weather._PRECHECK_HORIZON_DAYS)
    day = {**LIVE_BODY["days"][0], "datetime": slack.isoformat(), "source": "stats"}
    monkeypatch.setattr(
        weather,
        "_transport",
        lambda: _transport(lambda r: httpx.Response(200, json={"days": [day]})),
    )

    with pytest.raises(ForecastOutOfRangeError):
        await get_forecast(32.08, 34.78, slack)


@pytest.mark.asyncio
async def test_an_empty_key_is_a_provider_failure_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a request without a key must not leave the process")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(explode))
    monkeypatch.setattr(settings, "VISUAL_CROSSING_API_KEY", "")

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, CAPTURED)


@pytest.mark.asyncio
async def test_a_provider_400_is_out_of_range_rather_than_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 400 from the provider means our request was refused, not that the
    # service is down — and a user can cause one: `GET /weather` accepts any
    # date, and 1960 was measured to answer `400 From date cannot be before
    # 1970-01-01`. Mapping it to the provider error would tell that user the
    # service is down. `AUDITS.md` O-41 holds the missing lower bound.
    def bad_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=LIVE_ERROR_TEXT)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(bad_request))

    with pytest.raises(ForecastOutOfRangeError):
        await get_forecast(32.08, 34.78, CAPTURED)


@pytest.mark.asyncio
async def test_an_unreachable_provider_raises_the_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(refused))

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, CAPTURED)


@pytest.mark.asyncio
async def test_a_500_raises_the_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream unavailable")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(broken))

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, CAPTURED)


@pytest.mark.asyncio
async def test_a_body_missing_the_day_raises_the_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 200 whose `days` list is empty must not surface as an IndexError from
    # inside a service.
    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**LIVE_BODY, "days": []})

    monkeypatch.setattr(weather, "_transport", lambda: _transport(empty))

    with pytest.raises(ForecastProviderError):
        await get_forecast(32.08, 34.78, CAPTURED)


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
        await get_forecast(32.08, 34.78, CAPTURED)
    forecast = await get_forecast(32.08, 34.78, CAPTURED)

    assert forecast.temp_max_c == 31.0
    assert calls == 2


# --- get_daily_forecast: the range ----------------------------------------


@pytest.mark.asyncio
async def test_a_range_parses_every_day_in_order(stub_range: list[httpx.Request]) -> None:
    # The assertion `LIVE_BODY` cannot make: four day objects read to the end,
    # in order. Day 4's wind is checked because it is the only value in the
    # fixture that trips a modifier at the far end of the list — a parser that
    # read the first day four times would pass every other assertion here.
    forecasts = await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    assert [f.date for f in forecasts] == [
        date(2026, 3, 14),
        date(2026, 3, 15),
        date(2026, 3, 16),
        date(2026, 3, 17),
    ]
    assert [f.temp_max_c for f in forecasts] == [12.4, 14.1, 17.3, 15.0]
    assert [f.temp_min_c for f in forecasts] == [4.2, 6.0, 8.8, 7.1]
    assert [f.precip_mm for f in forecasts] == [4.0, 0.0, 0.0, 0.2]
    assert [f.wind_kph for f in forecasts] == [18.5, 12.0, 9.4, 33.6]
    assert [f.condition for f in forecasts] == [
        Condition.RAIN,
        Condition.CLOUDY,
        Condition.CLEAR,
        Condition.PARTLY_CLOUDY,
    ]


@pytest.mark.asyncio
async def test_a_four_day_range_is_one_request(stub_range: list[httpx.Request]) -> None:
    # The whole of `STAGE-4` 4.2's "one request". A per-day loop returns the
    # same four forecasts and passes the test above.
    await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    assert len(stub_range) == 1
    assert _requested(stub_range[0]) == ("52.52,13.41", "2026-03-14", "2026-03-17")


@pytest.mark.asyncio
async def test_a_range_sends_the_same_elements_and_units_as_one_day(
    stub_range: list[httpx.Request],
) -> None:
    await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    assert stub_range[0].url.params["elements"].split(",") == list(weather.ELEMENTS)
    assert stub_range[0].url.params["unitGroup"] == "metric"


@pytest.mark.asyncio
async def test_range_coordinates_are_rounded_before_they_leave(
    stub_range: list[httpx.Request],
) -> None:
    await get_daily_forecast(52.5200123, 13.4100456, TRIP_START, TRIP_END)

    assert _requested(stub_range[0])[0] == "52.52,13.41"


@pytest.mark.asyncio
async def test_a_one_day_range_is_legal(monkeypatch: pytest.MonkeyPatch) -> None:
    # `start == end`. The shortest trip a `trips` row admits — `ck_trips_date_order`
    # is `>=` — so this is the boundary that migration and this function share.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=LIVE_BODY)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(handler))

    forecasts = await get_daily_forecast(32.08, 34.78, CAPTURED, CAPTURED)

    assert [f.date for f in forecasts] == [CAPTURED]


@pytest.mark.asyncio
async def test_an_inverted_range_never_reaches_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A ValueError rather than a ForecastOutOfRangeError: left to the provider
    # this comes back as a 400 and would be reported to the user as "no
    # forecast for those days", which is not what went wrong.
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("an inverted range must not leave the process")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(explode))

    with pytest.raises(ValueError) as exc_info:
        await get_daily_forecast(*BERLIN, TRIP_END, TRIP_START)

    assert not isinstance(
        exc_info.value, (weather.ForecastOutOfRangeError, weather.ForecastProviderError)
    )


# --- get_daily_forecast: the cache, shared with get_forecast --------------


@pytest.mark.asyncio
async def test_a_range_fills_the_cache_the_single_day_endpoint_reads(
    stub_range: list[httpx.Request],
) -> None:
    # The point of reusing `_cache` rather than holding a second one: the trip
    # screen and `GET /weather` warm each other.
    await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)
    forecast = await get_forecast(*BERLIN, date(2026, 3, 16))

    assert len(stub_range) == 1
    assert forecast.temp_max_c == 17.3


@pytest.mark.asyncio
async def test_a_fully_cached_range_does_not_leave(stub_range: list[httpx.Request]) -> None:
    first = await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)
    second = await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    assert len(stub_range) == 1
    # The cached answer is the whole range in order, not whichever days
    # happened to still be held — a comprehension that dropped a miss would
    # return three days here and satisfy a bare `len(stub_range) == 1`.
    assert second == first
    assert len(second) == 4


@pytest.mark.asyncio
async def test_a_partly_cached_range_fetches_the_whole_range_again(
    stub_range: list[httpx.Request],
) -> None:
    # Three of the four days are held and the request still goes out whole.
    # Stitching a sub-range onto the cached days would be the alternative, and
    # it costs the same one request.
    await get_forecast(*BERLIN, date(2026, 3, 14))
    await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    assert len(stub_range) == 2
    assert _requested(stub_range[1])[1] == "2026-03-14"


@pytest.mark.asyncio
async def test_an_expired_day_makes_the_range_leave_again(
    stub_range: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    # `test_an_expired_entry_is_fetched_again`'s idiom, one function along: the
    # lambda closes over `now`, so rebinding it moves the clock.
    now = 1_000.0
    monkeypatch.setattr(weather.time, "monotonic", lambda: now)
    await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    now += weather.CACHE_TTL_SECONDS + 1
    await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    assert len(stub_range) == 2


# --- get_daily_forecast: the horizon and the failures ---------------------


@pytest.mark.asyncio
async def test_a_range_ending_past_the_horizon_never_reaches_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a range past the horizon must not leave the process")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(explode))
    start = date.today()
    end = start + timedelta(days=weather._PRECHECK_HORIZON_DAYS + 1)

    with pytest.raises(ForecastOutOfRangeError):
        await get_daily_forecast(*BERLIN, start, end)


@pytest.mark.asyncio
async def test_a_range_ending_on_the_last_servable_day_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The horizon here is the provider's, measured at 14 on 2026-09-07 and no
    # longer a day past the trip's 14. `DECISIONS.md` 190 puts
    # `end_date <= today + 14` on `POST /trips/pack` and the picker, because it
    # is a product rule; 234 records that the margin between the two is gone.
    start = date.today()
    end = start + timedelta(days=FORECAST_HORIZON_DAYS)
    days = [(start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)]
    body = {"days": [_day(day, 15.0, 7.0, 0.0, 10.0, "clear-day") for day in days]}
    monkeypatch.setattr(
        weather, "_transport", lambda: _transport(lambda r: httpx.Response(200, json=body))
    )

    forecasts = await get_daily_forecast(*BERLIN, start, end)

    assert len(forecasts) == FORECAST_HORIZON_DAYS + 1


@pytest.mark.asyncio
async def test_a_range_provider_400_is_out_of_range_rather_than_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The route bounds a trip's dates, so the measured 400s — a pre-1970 date,
    # a coordinate the provider cannot resolve — reach a range only through
    # `GET /weather`'s single day. The mapping is the same here regardless.
    def bad_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=LIVE_ERROR_TEXT)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(bad_request))

    with pytest.raises(ForecastOutOfRangeError):
        await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)


@pytest.mark.asyncio
async def test_an_unreachable_provider_raises_the_provider_error_for_a_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(weather, "_transport", lambda: _transport(refused))

    with pytest.raises(ForecastProviderError):
        await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)


@pytest.mark.asyncio
async def test_a_day_missing_an_element_is_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Four day objects and one of them without its wind. This is the shape a
    # misspelled name in `ELEMENTS` produces — a 200 with the key absent — and
    # it is a `KeyError` inside the parser, never a day with a wind of zero.
    # The ragged-array case this replaced has no equivalent: one object per
    # day cannot be a day short in one field and whole in the others.
    days = [dict(day) for day in RANGE_BODY["days"]]
    del days[2]["windspeed"]
    monkeypatch.setattr(
        weather,
        "_transport",
        lambda: _transport(lambda r: httpx.Response(200, json={"days": days})),
    )

    with pytest.raises(ForecastProviderError):
        await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)


@pytest.mark.asyncio
async def test_a_range_missing_a_requested_day_is_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Three well-formed days, and still not the range that was asked for. The
    # Thursday is simply absent. Since the swap this is the only alignment
    # guard: there are no parallel arrays for `zip(strict=True)` to compare.
    short = {"days": [RANGE_BODY["days"][n] for n in (0, 1, 3)]}
    monkeypatch.setattr(
        weather, "_transport", lambda: _transport(lambda r: httpx.Response(200, json=short))
    )

    with pytest.raises(ForecastProviderError):
        await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)


@pytest.mark.asyncio
async def test_a_failed_range_caches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500)

    monkeypatch.setattr(weather, "_transport", lambda: _transport(flaky))

    for _ in range(2):
        with pytest.raises(ForecastProviderError):
            await get_daily_forecast(*BERLIN, TRIP_START, TRIP_END)

    assert len(calls) == 2

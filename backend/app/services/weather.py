"""Open-Meteo forecast and the weather rule. No API key, no AI, no database.

`build_rule` is the reliability mechanism `03-AI-CONTRACTS.md` builds the whole
feature on: a temperature is never sent to the model to reason about, it is
converted here into an explicit instruction the stylist is told to obey. That
makes the weather behaviour a pure function of three numbers, testable to the
character without spending anything.

**The field names and units below were verified against a live call on
2026-08-26** rather than taken from documentation — `wind_speed_10m_max` is
km/h, `precipitation_sum` is mm, `temperature_2m_max` is °C, `weather_code` is
a WMO 4677 integer, and `timezone=auto` resolves the calendar day from the
coordinates so a server in UTC does not fetch yesterday for a user in Asia.
The legacy spelling `windspeed_10m_max` is what most examples online use and it
returns a 200 with the key simply absent. `DECISIONS.md` 143.

Two failures, deliberately not merged, because the route answers them with two
different status codes. `ForecastOutOfRangeError` means the date cannot be
served — ours to reject, and the provider's own `400` arrives here too.
`ForecastProviderError` means Open-Meteo did not answer usably. `DECISIONS.md`
147.
"""

import datetime
import logging
import time
from dataclasses import dataclass
from typing import Any, Final

import httpx

from app.enums import Condition

logger = logging.getLogger(__name__)

FORECAST_URL: Final = "https://api.open-meteo.com/v1/forecast"

# Requested in this order and unpacked positionally nowhere — each is read by
# name — but the order is asserted in the tests so a silent rename shows up as
# a diff rather than as a null.
DAILY_FIELDS: Final = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
    "weather_code",
)

# Measured 2026-08-26: the provider served 2026-09-10 and refused 2026-09-11,
# so the last servable day is **today + 15**, which is sixteen days counting
# today. `AUDITS.md` O-7 reads "16 days ahead" and is off by one against this;
# it is corrected there rather than here, because Stage 4 is what depends on it.
FORECAST_HORIZON_DAYS: Final = 15

CACHE_TTL_SECONDS: Final = 30 * 60

# Two decimals is about 1.1 km. Open-Meteo snaps to a coarser grid than that on
# its own — 32.08 was sent and 32.0625 came back — so rounding here discards
# precision the provider was going to discard anyway, and it is what makes the
# cache able to hit at all: `users.home_lat` is a REAL column and a value that
# survived a float round-trip would otherwise never match a typed-in one.
COORD_PRECISION: Final = 2

_TIMEOUT_SECONDS: Final = 10.0

# WMO 4677, grouped into the eight values `app/enums.py` admits. Codes absent
# here are handled by `condition_for` rather than by being added speculatively.
WMO_CONDITIONS: Final[dict[int, Condition]] = {
    0: Condition.CLEAR,
    1: Condition.PARTLY_CLOUDY,
    2: Condition.PARTLY_CLOUDY,
    3: Condition.CLOUDY,
    45: Condition.FOG,
    48: Condition.FOG,
    51: Condition.DRIZZLE,
    53: Condition.DRIZZLE,
    55: Condition.DRIZZLE,
    56: Condition.DRIZZLE,
    57: Condition.DRIZZLE,
    61: Condition.RAIN,
    63: Condition.RAIN,
    65: Condition.RAIN,
    66: Condition.RAIN,
    67: Condition.RAIN,
    80: Condition.RAIN,
    81: Condition.RAIN,
    82: Condition.RAIN,
    71: Condition.SNOW,
    73: Condition.SNOW,
    75: Condition.SNOW,
    77: Condition.SNOW,
    85: Condition.SNOW,
    86: Condition.SNOW,
    95: Condition.THUNDERSTORM,
    96: Condition.THUNDERSTORM,
    99: Condition.THUNDERSTORM,
}

# Lower bounds, not the whole-degree ranges `03-AI-CONTRACTS.md` prints. The
# table reads "22–27" and "≥ 28" and the provider answers 31.7, so every edge
# has a gap the table does not name: 27.9 belongs to the band below 28.
# `DECISIONS.md` 148.
_BANDS: Final[tuple[tuple[float, str], ...]] = (
    (28, "Use items with warmth 1-2 only. Do NOT include any outerwear."),
    (22, "Use items with warmth 1-2. Outerwear optional and only if warmth <= 2."),
    (
        16,
        "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional.",
    ),
    (10, "Outerwear is REQUIRED, warmth 3-4."),
)
_COLDEST: Final = "Outerwear is REQUIRED, warmth 4-5, plus a mid layer."

_RAIN = "Rain expected. Strongly prefer water_resistant outerwear and closed water_resistant shoes."
_WIND = "Windy. Avoid flowy or a_line items."


class WeatherError(Exception):
    """A forecast was asked for and not produced."""


class ForecastOutOfRangeError(WeatherError):
    """The date is outside what the provider will answer for."""


class ForecastProviderError(WeatherError):
    """Open-Meteo did not answer, or answered something unreadable."""


@dataclass(frozen=True, slots=True)
class Forecast:
    date: datetime.date
    temp_min_c: float
    temp_max_c: float
    precip_mm: float
    wind_kph: float
    condition: Condition


def build_rule(temp_c: float, precip_mm: float, wind_kph: float) -> str:
    """Three numbers in, one instruction out. `03-AI-CONTRACTS.md`'s table.

    Pure, and the only thing in the weather path that the stylist's behaviour
    is allowed to depend on.
    """
    rule = _COLDEST
    for threshold, band in _BANDS:
        if temp_c >= threshold:
            rule = band
            break

    # Strictly greater, per the document: 1 mm is a dry day and 30 kph is calm.
    if precip_mm > 1:
        rule = f"{rule} {_RAIN}"
    if wind_kph > 30:
        rule = f"{rule} {_WIND}"
    return rule


def condition_for(code: int) -> Condition:
    """A WMO 4677 code as the closed vocabulary names it.

    An unmapped code falls back rather than raising. `condition` is a label and
    an icon; what actually dresses the user is `build_rule`, computed from
    temperature, rain and wind, and unaffected by this. Failing a whole
    suggestion over an unknown icon would be the worse answer — but a silent
    fallback would hide a widened vocabulary, so it is logged. `DECISIONS.md` 146.
    """
    condition = WMO_CONDITIONS.get(code)
    if condition is None:
        logger.warning("Unmapped WMO weather code", extra={"weather_code": code})
        return Condition.CLOUDY
    return condition


_cache: dict[tuple[float, float, datetime.date], tuple[float, Forecast]] = {}


def clear_cache() -> None:
    _cache.clear()


def _transport() -> httpx.AsyncBaseTransport | None:
    """Overridden in tests to keep the suite off the network. `None` is httpx's
    own default, so production behaviour is the unpatched one."""
    return None


def _read(body: Any) -> tuple[datetime.date, float, float, float, float, int]:
    daily = body["daily"]
    return (
        datetime.date.fromisoformat(daily["time"][0]),
        float(daily["temperature_2m_max"][0]),
        float(daily["temperature_2m_min"][0]),
        float(daily["precipitation_sum"][0]),
        float(daily["wind_speed_10m_max"][0]),
        int(daily["weather_code"][0]),
    )


async def get_forecast(lat: float, lon: float, date: datetime.date) -> Forecast:
    """One day's forecast for one place, cached for thirty minutes.

    Raises `ForecastOutOfRangeError` for a date the provider will not answer
    for — checked locally first, so the common case costs no request — and
    `ForecastProviderError` for anything else.
    """
    if date > datetime.date.today() + datetime.timedelta(days=FORECAST_HORIZON_DAYS):
        raise ForecastOutOfRangeError(
            f"Open-Meteo forecasts {FORECAST_HORIZON_DAYS} days ahead; {date} is beyond that."
        )

    lat = round(lat, COORD_PRECISION)
    lon = round(lon, COORD_PRECISION)
    key = (lat, lon, date)

    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]

    # Annotated because the mixed value types otherwise infer as `object`, which
    # httpx's `params` will not accept.
    params: dict[str, str | float] = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(DAILY_FIELDS),
        # Without this the provider answers in UTC and `date` means a different
        # 24 hours than the user's calendar day.
        "timezone": "auto",
        "start_date": date.isoformat(),
        "end_date": date.isoformat(),
    }

    # A client per call rather than one held at module level: httpx binds a
    # connection pool to the event loop that created it, and a 30-minute cache
    # already removes the repeat calls pooling would pay for.
    try:
        async with httpx.AsyncClient(transport=_transport(), timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(FORECAST_URL, params=params)
        # A 400 here is the provider refusing the request, not being down — a
        # date older than its archive window arrives this way, past the guard
        # above. Answering 502 for it would blame the wrong side.
        if response.status_code == httpx.codes.BAD_REQUEST:
            raise ForecastOutOfRangeError(_reason(response))
        response.raise_for_status()
        parsed = _read(response.json())
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning(
            "Forecast request failed",
            extra={"latitude": lat, "longitude": lon, "date": date.isoformat()},
        )
        raise ForecastProviderError("The forecast provider did not answer.") from exc

    day, temp_max, temp_min, precip, wind, code = parsed
    forecast = Forecast(
        date=day,
        temp_min_c=temp_min,
        temp_max_c=temp_max,
        precip_mm=precip,
        wind_kph=wind,
        condition=condition_for(code),
    )

    _cache[key] = (now + CACHE_TTL_SECONDS, forecast)
    _evict(now)
    return forecast


def _reason(response: httpx.Response) -> str:
    try:
        return str(response.json()["reason"])
    except ValueError, KeyError, TypeError:
        return "The forecast provider refused the request."


def _evict(now: float) -> None:
    """Keeps the cache bounded by what was asked for in the last half hour
    rather than by everything ever asked for."""
    for key in [key for key, (expires, _) in _cache.items() if expires <= now]:
        del _cache[key]

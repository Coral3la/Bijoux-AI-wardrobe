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

Two entry points since task 4.2: `get_forecast` for one day and
`get_daily_forecast` for a range, sharing one parser, one cache and one horizon.
The range is a single request — the provider's `start_date`/`end_date` pair
answers one — and the fourteen-day bound a *trip* is held to is not here but at
`POST /trips/pack`, because it is a product rule and this module only knows what
Open-Meteo will serve. `DECISIONS.md` 190.

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
_COLD: Final = "Outerwear is REQUIRED, warmth 3-4."
_COLDEST: Final = "Outerwear is REQUIRED, warmth 4-5, plus a mid layer."

_BANDS: Final[tuple[tuple[float, str], ...]] = (
    (28, "Use items with warmth 1-2 only. Do NOT include any outerwear."),
    (22, "Use items with warmth 1-2. Outerwear optional and only if warmth <= 2."),
    (
        16,
        "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional.",
    ),
    (10, _COLD),
)

# The two bands that make outerwear compulsory, named rather than matched. A
# `"REQUIRED" in rule` test would read the table's prose, and a re-typed pair of
# sentences in `stylist.py` would be a third copy of what `03-AI-CONTRACTS.md`
# already says once; this way the set is the same objects the table is built
# from, and a reworded band changes both at once.
_OUTERWEAR_REQUIRED: Final = frozenset({_COLD, _COLDEST})

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


def requires_outerwear(rule: str) -> bool:
    """Whether a rule from `build_rule` makes outerwear compulsory.

    Read by `validate_look_response`'s rule 6 (2.5), which cannot ask the
    temperature: the stylist is given a sentence, never a number, and the band
    table is the only thing that knows which sentences are the demanding two.
    `startswith` rather than equality because the rain and wind modifiers are
    appended to the band, and rain is exactly when the coldest bands fire.
    """
    return any(rule.startswith(band) for band in _OUTERWEAR_REQUIRED)


def summarize_forecast(forecast: Forecast) -> str:
    """The `Weather:` line of `03-AI-CONTRACTS.md`'s user message.

    Transcribes the document's two examples — `18°C, no rain.` and
    `12°C, rain 4mm` — and adds nothing to them. No condition word: the
    single-day example has none, and `partly_cloudy` next to a rule the model is
    told to obey exactly is decoration the prompt pays tokens for.

    `temp_max_c` for `DECISIONS.md` 142's reason, which is `build_rule`'s own:
    two temperatures reach this function and the document's worked example is
    only self-consistent under the maximum. **The rain threshold is
    `build_rule`'s `> 1` rather than `> 0`**, so this sentence cannot say "no
    rain" above a rule that says rain is expected — 0.5 mm is a dry day in both
    or in neither.

    Built here rather than in the route because the units are this module's, the
    way `requires_outerwear` is: 2.7 assembles a `StylistContext` and does not
    decide what a millimetre reads like.
    """
    rain = f"rain {forecast.precip_mm:g}mm" if forecast.precip_mm > 1 else "no rain"
    return f"{round(forecast.temp_max_c)}°C, {rain}."


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


def _forecasts(body: Any) -> list[Forecast]:
    """Every day the provider answered with, in the order it returned them.

    One parser for both entry points: `get_forecast` takes the first element of
    a one-day range and `get_daily_forecast` takes all of them. A second reader
    of `daily` would be six field names written twice, with nothing keeping the
    two in step — `DAILY_FIELDS` already exists because a rename here is a
    `200` with a key silently absent.

    **`strict=True` is defence in depth and not the guard that catches a ragged
    body — measured, at 4.2, by removing it.** The provider answers six parallel
    arrays and nothing in its protocol promises they are the same length, so
    without it `zip` stops at the shortest and returns a short list. What turns
    that into a failure is `get_daily_forecast`'s day-by-day comparison against
    the range it asked for, which fires on the same body and fires on shifted
    days too; deleting `strict=True` alone leaves the whole suite green. It
    stays because the two catch different things — a body ragged *past* the
    requested range trips this and not that — and because a parser that guesses
    at misaligned arrays is worse than one that refuses. `ValueError` is what
    `zip` raises, and both callers already map it to `ForecastProviderError`.
    """
    daily = body["daily"]
    return [
        Forecast(
            date=datetime.date.fromisoformat(day),
            temp_min_c=float(temp_min),
            temp_max_c=float(temp_max),
            precip_mm=float(precip),
            wind_kph=float(wind),
            condition=condition_for(int(code)),
        )
        for day, temp_max, temp_min, precip, wind, code in zip(
            daily["time"],
            daily["temperature_2m_max"],
            daily["temperature_2m_min"],
            daily["precipitation_sum"],
            daily["wind_speed_10m_max"],
            daily["weather_code"],
            strict=True,
        )
    ]


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
        # `[0]` inside the `try`, because an empty `daily.time` is an
        # `IndexError` and the clause below is what turns it into the
        # provider error — the same reach `_read` had when it indexed here.
        forecast = _forecasts(response.json())[0]
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning(
            "Forecast request failed",
            extra={"latitude": lat, "longitude": lon, "date": date.isoformat()},
        )
        raise ForecastProviderError("The forecast provider did not answer.") from exc

    _cache[key] = (now + CACHE_TTL_SECONDS, forecast)
    _evict(now)
    return forecast


async def get_daily_forecast(
    lat: float, lon: float, start: datetime.date, end: datetime.date
) -> list[Forecast]:
    """One place, every day from `start` to `end` inclusive, in one request.

    **One request for the whole range, not one per day.** Open-Meteo's
    `start_date`/`end_date` pair already answers a range — `get_forecast` sends
    the same day twice into it — so a per-day loop would be N round trips for a
    body the provider builds anyway, and 4.3 needs fourteen of them at once.

    **The horizon is the provider's, not the trip's.** This raises against
    `FORECAST_HORIZON_DAYS`, which was measured at 15 on 2026-08-26; the
    fourteen-day product bound `DECISIONS.md` 190 fixed is `end_date <= today +
    14` and belongs to `POST /trips/pack` and the date picker, which are the two
    places 190 names. A service that refused day 15 would also have to refuse it
    to `GET /weather`, which serves it today.

    Raises `ForecastOutOfRangeError` when the **last** day is past the horizon —
    the first day cannot be past it without the last one being — and
    `ForecastProviderError` when Open-Meteo does not answer, answers something
    unreadable, or answers days other than the ones asked for. `ValueError` for
    an inverted range, which is a caller's bug rather than a forecast condition:
    left to the provider it would come back as a `400` and be reported as
    "beyond the horizon", which is not what went wrong.
    """
    if end < start:
        raise ValueError(f"The range ends before it starts: {start} to {end}.")

    if end > datetime.date.today() + datetime.timedelta(days=FORECAST_HORIZON_DAYS):
        raise ForecastOutOfRangeError(
            f"Open-Meteo forecasts {FORECAST_HORIZON_DAYS} days ahead; {end} is beyond that."
        )

    lat = round(lat, COORD_PRECISION)
    lon = round(lon, COORD_PRECISION)
    wanted = [start + datetime.timedelta(days=n) for n in range((end - start).days + 1)]

    now = time.monotonic()
    # The same per-day entries `get_forecast` reads and writes, so a trip warms
    # the cache for the single-day endpoint and vice versa. All or nothing: a
    # partial hit costs one request for the whole range, which is what a miss
    # costs anyway, and re-fetching a day already held is cheaper than the
    # bookkeeping for stitching two sub-ranges together.
    held = [
        entry[1]
        for day in wanted
        if (entry := _cache.get((lat, lon, day))) is not None and entry[0] > now
    ]
    if len(held) == len(wanted):
        return held

    params: dict[str, str | float] = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(DAILY_FIELDS),
        "timezone": "auto",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }

    try:
        async with httpx.AsyncClient(transport=_transport(), timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(FORECAST_URL, params=params)
        if response.status_code == httpx.codes.BAD_REQUEST:
            raise ForecastOutOfRangeError(_reason(response))
        response.raise_for_status()
        forecasts = _forecasts(response.json())
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning(
            "Daily forecast request failed",
            extra={
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        )
        raise ForecastProviderError("The forecast provider did not answer.") from exc

    # Every day asked for, in order, and no others. A short or shifted answer is
    # a provider failure rather than a result: 4.3 builds one look per day and
    # validates `len(looks) == days`, so a range quietly missing its Thursday
    # becomes a `502` two model calls later instead of an error here.
    if [forecast.date for forecast in forecasts] != wanted:
        logger.warning(
            "Daily forecast answered a different range",
            extra={
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "returned_days": len(forecasts),
            },
        )
        raise ForecastProviderError("The forecast provider answered a different range.")

    for forecast in forecasts:
        _cache[(lat, lon, forecast.date)] = (now + CACHE_TTL_SECONDS, forecast)
    _evict(now)
    return forecasts


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

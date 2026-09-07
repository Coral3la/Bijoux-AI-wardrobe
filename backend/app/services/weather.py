"""Visual Crossing forecast and the weather rule. One API key, no AI, no database.

`build_rule` is the reliability mechanism `03-AI-CONTRACTS.md` builds the whole
feature on: a temperature is never sent to the model to reason about, it is
converted here into an explicit instruction the stylist is told to obey. That
makes the weather behaviour a pure function of three numbers, testable to the
character without spending anything.

Visual Crossing replaced Open-Meteo on 2026-09-07, in place and with no provider
abstraction: Open-Meteo's free tier is rate-limited per IP, and Render's free
web service leaves through a shared outbound IP whose daily quota other tenants
had already spent, so every forecast call answered `429` and every route
answered `502`. `DECISIONS.md` 234.

**The field names and units below were verified against a live call on
2026-09-07** rather than taken from documentation — under `unitGroup=metric`,
`tempmax`/`tempmin` are °C, `precip` is mm, `windspeed` is km/h (proved by ratio
against the same day under `unitGroup=us`, 12.5 mph to 20.1) and is the day's
**maximum** hourly value, which is the meaning `wind_speed_10m_max` carried and
the one `build_rule`'s 30 km/h threshold was calibrated on. The calendar day is
resolved in the location's own timezone with no parameter — `Asia/Jerusalem`
came back for Tel Aviv's coordinates — so a server in UTC does not fetch
yesterday for a user in Asia. The key travels in the query string, which is the
only place the provider accepts it; `core/logging.py` silences httpx's own
per-request INFO line for that reason.

Two entry points since task 4.2: `get_forecast` for one day and
`get_daily_forecast` for a range, sharing one parser, one cache and one horizon.
The range is a single request — the path's `{start}/{end}` pair answers one —
and the fourteen-day bound a *trip* is held to is not here but at
`POST /trips/pack`, because it is a product rule and this module only knows what
the provider will serve. `DECISIONS.md` 190, corrected by 234.

Two failures, deliberately not merged, because the route answers them with two
different status codes. `ForecastOutOfRangeError` means the date cannot be
served — ours to reject, the provider's own `400` arrives here too, and so does
a day the provider answered from climate statistics rather than a forecast.
`ForecastProviderError` means the provider did not answer usably. `DECISIONS.md`
147.
"""

import datetime
import logging
import time
from dataclasses import dataclass
from typing import Any, Final

import httpx

from app.core.config import settings
from app.enums import Condition

logger = logging.getLogger(__name__)

FORECAST_URL: Final = (
    "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
)

# Requested in this order and unpacked positionally nowhere — each is read by
# name — but the order is asserted in the tests so a silent rename shows up as
# a diff rather than as a null.
ELEMENTS: Final = ("datetime", "tempmax", "tempmin", "precip", "windspeed", "icon", "source")

# Measured 2026-09-07: today answered `source: "comb"`, today + 1 through
# today + 14 answered `"fcst"`, and today + 15 answered `"stats"` — a climate
# average shaped exactly like a forecast. So the last forecast day is
# **today + 14**, one short of Open-Meteo's measured 15. This is the number the
# route prints and the one `DECISIONS.md` 190's trip bound is compared against.
FORECAST_HORIZON_DAYS: Final = 14

# One day looser than the horizon for the local pre-check only: the client's
# calendar day can be ahead of a UTC server's, and the provider resolves the day
# in the location's own timezone, so the day the browser meant is still `fcst`.
# The `source` check is what refuses a day that really is past the horizon.
_PRECHECK_HORIZON_DAYS: Final = FORECAST_HORIZON_DAYS + 1

# The one `source` value that is not a forecast or an observation. Refused by
# name rather than allow-listed: an allow-list of `fcst` refuses today, which
# answers `comb`, and breaks again the first time a past date answers `obs`.
_STATISTICAL_SOURCE: Final = "stats"

CACHE_TTL_SECONDS: Final = 30 * 60

# Two decimals is about 1.1 km, and it is what makes the cache able to hit at
# all: `users.home_lat` is a REAL column and a value that survived a float
# round-trip would otherwise never match a typed-in one. Visual Crossing echoes
# the coordinates it was sent — 32.08 came back as 32.08 — so unlike Open-Meteo
# there is no provider grid behind this, only the cache key.
COORD_PRECISION: Final = 2

_TIMEOUT_SECONDS: Final = 10.0

# The `icons2` set, grouped into the eight values `app/enums.py` admits. Icons
# absent here are handled by `condition_for` rather than by being added
# speculatively. `DRIZZLE` has no icon in this set and is unreachable from this
# provider; it stays in the vocabulary, which is `02-DATA-MODEL.md`'s and not
# the provider's. `wind` names a condition the vocabulary does not have, and
# `CLOUDY` is arbitrary for it — a windy day can be clear. It is mapped to the
# value the fallback would give it anyway so that the fallback's warning is
# kept for icons that are genuinely unknown, not because a windy day is cloudy.
ICON_CONDITIONS: Final[dict[str, Condition]] = {
    "clear-day": Condition.CLEAR,
    "clear-night": Condition.CLEAR,
    "partly-cloudy-day": Condition.PARTLY_CLOUDY,
    "partly-cloudy-night": Condition.PARTLY_CLOUDY,
    "cloudy": Condition.CLOUDY,
    "wind": Condition.CLOUDY,
    "fog": Condition.FOG,
    "rain": Condition.RAIN,
    "showers-day": Condition.RAIN,
    "showers-night": Condition.RAIN,
    "snow": Condition.SNOW,
    "snow-showers-day": Condition.SNOW,
    "snow-showers-night": Condition.SNOW,
    "thunder-rain": Condition.THUNDERSTORM,
    "thunder-showers-day": Condition.THUNDERSTORM,
    "thunder-showers-night": Condition.THUNDERSTORM,
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


class ForecastOutOfRangeError(Exception):
    """The date is outside what the provider will answer for."""


class ForecastProviderError(Exception):
    """Visual Crossing did not answer, or answered something unreadable."""


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


def condition_for(icon: str) -> Condition:
    """An `icons2` icon as the closed vocabulary names it.

    An unmapped icon falls back rather than raising. `condition` is a label and
    an icon; what actually dresses the user is `build_rule`, computed from
    temperature, rain and wind, and unaffected by this. Failing a whole
    suggestion over an unknown icon would be the worse answer — but a silent
    fallback would hide a widened vocabulary, so it is logged. `DECISIONS.md` 146.
    """
    condition = ICON_CONDITIONS.get(icon)
    if condition is None:
        logger.warning("Unmapped weather icon", extra={"icon": icon})
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
    a one-day range and `get_daily_forecast` takes all of them.

    **The only alignment guard is `get_daily_forecast`'s day-by-day comparison
    against the range it asked for.** The provider answers one object per day,
    so there are no parallel arrays for a `zip(strict=True)` to keep in step,
    and a day that is short a field is a `KeyError` on that day rather than a
    ragged body. What a short or shifted answer still needs is the comparison
    downstream, which fires on a missing Thursday exactly as it did before.

    A day the provider filled from climate statistics is refused here, before
    any `Forecast` is built from it: the body is shaped exactly like a forecast
    and only `source` tells them apart. `ForecastOutOfRangeError` because the
    date cannot be served, and it passes through the caller's `except` clauses
    untouched.
    """
    return [_forecast(day) for day in body["days"]]


def _forecast(day: Any) -> Forecast:
    if day["source"] == _STATISTICAL_SOURCE:
        raise ForecastOutOfRangeError(
            f"{day['datetime']} is past the provider's forecast and was answered from statistics."
        )
    # A null `precip` is the provider saying none was measured, so it is a dry
    # day; an *absent* key is the shape a misspelled element name produces and
    # stays a `KeyError`, so a typo in `ELEMENTS` cannot read as a permanently
    # dry world. A null temperature or wind has no honest substitute and the
    # `TypeError` from `float(None)` is a provider failure like any other.
    precip = day["precip"]
    return Forecast(
        date=datetime.date.fromisoformat(day["datetime"]),
        temp_min_c=float(day["tempmin"]),
        temp_max_c=float(day["tempmax"]),
        precip_mm=0.0 if precip is None else float(precip),
        wind_kph=float(day["windspeed"]),
        condition=condition_for(str(day["icon"])),
    )


async def get_forecast(lat: float, lon: float, date: datetime.date) -> Forecast:
    """One day's forecast for one place, cached for thirty minutes.

    Raises `ForecastOutOfRangeError` for a date the provider will not answer
    for — checked locally first, so the common case costs no request — and
    `ForecastProviderError` for anything else.
    """
    # `[0]` needs no `try`: `get_daily_forecast` has already refused any answer
    # whose dates are not exactly `[date]`, so the list has one element.
    return (await get_daily_forecast(lat, lon, date, date))[0]


async def get_daily_forecast(
    lat: float, lon: float, start: datetime.date, end: datetime.date
) -> list[Forecast]:
    """One place, every day from `start` to `end` inclusive, in one request.

    **One request for the whole range, not one per day.** The path's
    `{start}/{end}` pair already answers a range — `get_forecast` sends the same
    day twice into it — so a per-day loop would be N round trips for a body the
    provider builds anyway, and 4.3 needs fourteen of them at once. The provider
    bills by `queryCost`, and seventeen days cost 3, so a range is a few records
    against the free daily thousand rather than one per day.

    **The horizon is the provider's, not the trip's.** The local pre-check
    raises against `_PRECHECK_HORIZON_DAYS`, one day past the measured
    `FORECAST_HORIZON_DAYS`, and the day of slack is refused by the `source`
    check in `_forecasts` when it really is past the horizon. The fourteen-day
    product bound `DECISIONS.md` 190 fixed is `end_date <= today + 14` and
    belongs to `POST /trips/pack` and the date picker, which are the two places
    190 names.

    Raises `ForecastOutOfRangeError` when the **last** day is past the pre-check
    — the first day cannot be past it without the last one being — or when the
    provider answered any day from statistics, and `ForecastProviderError` when
    no key is configured, the provider does not answer, answers something
    unreadable, or answers days other than the ones asked for. `ValueError` for
    an inverted range, which is a caller's bug rather than a forecast condition:
    left to the provider it would come back as a `400` and be reported as
    "beyond the horizon", which is not what went wrong.
    """
    if end < start:
        raise ValueError(f"The range ends before it starts: {start} to {end}.")

    if end > datetime.date.today() + datetime.timedelta(days=_PRECHECK_HORIZON_DAYS):
        raise ForecastOutOfRangeError(
            f"The provider forecasts {FORECAST_HORIZON_DAYS} days ahead; {end} is beyond that."
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

    # After the cache and before the request: a held answer needs no key, and
    # a missing one is a deployment fault worth one log line rather than a
    # `401` round trip.
    if not settings.VISUAL_CROSSING_API_KEY:
        logger.warning("VISUAL_CROSSING_API_KEY is not set")
        raise ForecastProviderError("The forecast provider is not configured.")

    url = f"{FORECAST_URL}/{lat},{lon}/{start.isoformat()}/{end.isoformat()}"
    params = {
        "key": settings.VISUAL_CROSSING_API_KEY,
        "unitGroup": "metric",
        "include": "days",
        "elements": ",".join(ELEMENTS),
        "iconSet": "icons2",
        "contentType": "json",
    }

    # A client per call rather than one held at module level: httpx binds a
    # connection pool to the event loop that created it, and a 30-minute cache
    # already removes the repeat calls pooling would pay for.
    try:
        async with httpx.AsyncClient(transport=_transport(), timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params)
        if response.status_code == httpx.codes.BAD_REQUEST:
            raise ForecastOutOfRangeError(_reason(response))
        response.raise_for_status()
        forecasts = _forecasts(response.json())
    # Before the broad clause, not after: `HTTPStatusError` is an `HTTPError`,
    # so ordered the other way this branch never runs and the status code the
    # provider answered with is lost — which is the whole point of the split.
    # No `exc_info` here: the exception's own message carries the request URL,
    # and the URL carries the key.
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Daily forecast request failed",
            extra={
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "status_code": exc.response.status_code,
                "body": exc.response.text[:200],
            },
        )
        raise ForecastProviderError("The forecast provider did not answer.") from exc
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning(
            "Daily forecast request failed",
            extra={
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            exc_info=exc,
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
    """The provider's `400` is a one-line plain-text body — measured as
    `Bad API Request:Start date time value … cannot be parsed` — and it does not
    echo the request, so it is safe to carry."""
    return response.text.strip()[:200] or "The forecast provider refused the request."


def _evict(now: float) -> None:
    """Keeps the cache bounded by what was asked for in the last half hour
    rather than by everything ever asked for."""
    for key in [key for key, (expires, _) in _cache.items() if expires <= now]:
        del _cache[key]

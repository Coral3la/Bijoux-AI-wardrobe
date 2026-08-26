"""Open-Meteo geocoding. No API key, no AI, no database.

A separate module from `weather.py` rather than a function inside it: the two
share a vendor and nothing else — a different host, a different response shape,
and no cache. `01-ARCHITECTURE.md`'s tree names both.

The proxy exists so the browser never calls a third party directly
(`04-API-SPEC.md`), which is the same reason the OpenAI and Cloudinary keys
live here — except that this provider needs no key at all, so what the proxy
buys is one origin for the frontend and one place to change if the provider
does.

**The no-match shape was verified against a live call on 2026-08-26** rather
than read from documentation, on `DECISIONS.md` 143's terms. A query that
matches nothing answers `200` with **no `results` key at all** — not with an
empty array — so a parser written the obvious way raises `KeyError` on the most
ordinary thing a search box does.
"""

import logging
from dataclasses import dataclass
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL: Final = "https://geocoding-api.open-meteo.com/v1/search"

# The provider's own behaviour, not a house rule: one character returns nothing
# at all and two match only exactly, with fuzzy matching from three. Two is
# therefore the shortest query that can succeed, and the route rejects anything
# below it before a request leaves the process.
MIN_QUERY_LENGTH: Final = 2

RESULT_LIMIT: Final = 5

_TIMEOUT_SECONDS: Final = 10.0


class GeocodingError(Exception):
    """Open-Meteo did not answer, or answered something unreadable."""


@dataclass(frozen=True, slots=True)
class Location:
    name: str
    country: str | None
    lat: float
    lon: float


def _transport() -> httpx.AsyncBaseTransport | None:
    """Overridden in tests to keep the suite off the network. `None` is httpx's
    own default, so production behaviour is the unpatched one."""
    return None


def _location(result: Any) -> Location:
    # `country` is read with `.get` and the other three are not: a result
    # without coordinates is not a location and there is nothing to return for
    # it, where a country is a label the caller can render without.
    country = result.get("country")
    return Location(
        name=str(result["name"]),
        country=None if country is None else str(country),
        lat=float(result["latitude"]),
        lon=float(result["longitude"]),
    )


def _read(body: Any) -> list[Location]:
    # `.get`, not `body["results"]` — see the module docstring. A query that
    # matches nothing omits the key entirely.
    return [_location(result) for result in body.get("results", ())]


async def search_locations(query: str) -> list[Location]:
    """Up to `RESULT_LIMIT` places matching `query`, nearest match first.

    Deliberately uncached, unlike `get_forecast`: a type-ahead sends a
    different prefix on every keystroke, so a cache would hold entries that are
    each asked for once. Raises `GeocodingError` if the provider does not
    answer usably; no match is an empty list, which is an answer rather than a
    failure.
    """
    params: dict[str, str | int] = {
        "name": query,
        "count": RESULT_LIMIT,
        # The provider localises `country` and some place names to this
        # language. Pinned to the one locale the application has;
        # `05-FRONTEND-SPEC.md`'s i18n rule is about our strings, and these are
        # the provider's data.
        "language": "en",
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(transport=_transport(), timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(SEARCH_URL, params=params)
        response.raise_for_status()
        return _read(response.json())
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("Location search failed", extra={"query": query})
        raise GeocodingError("The location search provider did not answer.") from exc

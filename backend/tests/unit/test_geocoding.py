"""The geocoding client: what it sends, what it reads back, and how it fails.

No network. The transport is stubbed the way `test_weather.py` stubs the
forecast one, so what these tests prove is our parsing of a captured body — and
the two bodies below are **verbatim copies of real responses**, taken on
2026-08-26, for the reason `DECISIONS.md` 143 gives: a hand-written fixture
agrees with whatever the parser happens to read.

The second one is the point of this module. A query that matches nothing comes
back with **no `results` key**, which is not what an empty search result
usually looks like and is not what the obvious parser survives.
"""

from typing import Any

import httpx
import pytest

from app.services import geocoding
from app.services.geocoding import (
    MIN_QUERY_LENGTH,
    RESULT_LIMIT,
    SEARCH_URL,
    GeocodingError,
    search_locations,
)

# Captured 2026-08-26 from
# geocoding-api.open-meteo.com/v1/search?name=berlin&count=5&language=en&format=json.
# Two entries are kept out of the five: one country apiece is enough to show
# that `name` alone does not identify a place, which is what LocationResult's
# comment about `admin1` is about.
LIVE_BODY: dict[str, Any] = {
    "results": [
        {
            "id": 2950159,
            "name": "Berlin",
            "latitude": 52.52437,
            "longitude": 13.41053,
            "elevation": 74.0,
            "feature_code": "PPLC",
            "country_code": "DE",
            "timezone": "Europe/Berlin",
            "population": 3426354,
            "country": "Germany",
            "admin1": "State of Berlin",
        },
        {
            "id": 4348599,
            "name": "Berlin",
            "latitude": 39.79123,
            "longitude": -74.92905,
            "elevation": 30.0,
            "feature_code": "PPL",
            "country_code": "US",
            "timezone": "America/New_York",
            "population": 7622,
            "country": "United States",
            "admin1": "New Jersey",
        },
    ],
    "generationtime_ms": 0.44,
}

# Captured in the same session by searching for `zzzzzzzz`. The absence of
# `results` is the whole fixture.
LIVE_NO_MATCH_BODY: dict[str, Any] = {"generationtime_ms": 0.67}


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Installs a transport and hands back the requests it saw."""

    def _stub(body: Any = LIVE_BODY, status_code: int = 200) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(status_code, json=body)

        monkeypatch.setattr(geocoding, "_transport", lambda: httpx.MockTransport(handler))
        return seen

    return _stub


@pytest.mark.asyncio
async def test_parses_the_captured_live_body(stub: Any) -> None:
    stub()

    locations = await search_locations("berlin")

    assert len(locations) == 2
    first = locations[0]
    assert first.name == "Berlin"
    assert first.country == "Germany"
    assert first.lat == 52.52437
    assert first.lon == 13.41053


@pytest.mark.asyncio
async def test_a_query_that_matches_nothing_is_an_empty_list(stub: Any) -> None:
    # The key is absent, not empty. Reading body["results"] here is a KeyError,
    # which the caller would answer with a 502 for a search that worked.
    stub(body=LIVE_NO_MATCH_BODY)

    assert await search_locations("zzzzzzzz") == []


@pytest.mark.asyncio
async def test_sends_the_parameters_the_provider_documents(stub: Any) -> None:
    seen = stub()

    await search_locations("berlin")

    assert len(seen) == 1
    request = seen[0]
    assert str(request.url).startswith(SEARCH_URL)
    # "5" as a literal, not str(RESULT_LIMIT): an expectation read out of the
    # module under test moves with the mutation and measures nothing, which is
    # what DECISIONS.md 101 caught at 1.6 and what a mutation caught again
    # here. The number is transcribed from 04-API-SPEC.md's "up to 5".
    assert dict(request.url.params) == {
        "name": "berlin",
        "count": "5",
        "language": "en",
        "format": "json",
    }


@pytest.mark.asyncio
async def test_a_result_without_a_country_still_parses(stub: Any) -> None:
    # `country` is the one of the four the provider may omit, and a place with
    # no country label is still somewhere the forecast can be fetched for.
    stub(body={"results": [{"name": "Nowhere", "latitude": 1.0, "longitude": 2.0}]})

    locations = await search_locations("nowhere")

    assert locations[0].country is None
    assert locations[0].lat == 1.0


@pytest.mark.asyncio
async def test_a_result_without_coordinates_is_a_provider_error(stub: Any) -> None:
    stub(body={"results": [{"name": "Berlin", "country": "Germany"}]})

    with pytest.raises(GeocodingError):
        await search_locations("berlin")


@pytest.mark.asyncio
async def test_a_provider_error_status_raises(stub: Any) -> None:
    stub(body={"error": True}, status_code=500)

    with pytest.raises(GeocodingError):
        await search_locations("berlin")


@pytest.mark.asyncio
async def test_an_unreachable_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(geocoding, "_transport", lambda: httpx.MockTransport(handler))

    with pytest.raises(GeocodingError):
        await search_locations("berlin")


@pytest.mark.asyncio
async def test_a_body_that_is_not_an_object_raises(stub: Any) -> None:
    # `.get` on a list is an AttributeError rather than the TypeError the
    # forecast parser meets, which is why the caught tuple names both.
    stub(body=["Berlin"])

    with pytest.raises(GeocodingError):
        await search_locations("berlin")


@pytest.mark.asyncio
async def test_the_failure_is_logged_with_the_query(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    # On the record attribute, not on caplog.text: `extra=` is only rendered by
    # JsonFormatter, and the development formatter drops it — an assertion on
    # the message would pass with the query missing. DECISIONS.md 146.
    stub(body={"error": True}, status_code=500)

    with caplog.at_level("WARNING"), pytest.raises(GeocodingError):
        await search_locations("berlin")

    assert caplog.records[-1].query == "berlin"


def test_the_result_limit_is_the_count_the_document_names() -> None:
    # 04-API-SPEC.md: "Returns up to 5". Pinned here so the constant cannot
    # drift away from the document while every other test agrees with it.
    assert RESULT_LIMIT == 5


def test_the_minimum_query_length_is_the_providers_own() -> None:
    # Transcribed from the provider's documented behaviour rather than read out
    # of the module: one character matches nothing and two match exactly, so
    # two is the shortest query that can return a place.
    assert MIN_QUERY_LENGTH == 2

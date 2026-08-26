"""GET /me/locations/search — the contract `04-API-SPEC.md` did not carry.

The four keys and the count were specified; the envelope, the empty case, the
minimum query length and the failure code were not, and they are settled here
and written into that document in the same commit.

Open-Meteo is stubbed at the transport, so nothing here leaves the process.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models.user import User
from app.services import geocoding

SEARCH_URL = "/api/v1/me/locations/search"

# The first of the five results the live call returned, trimmed to the keys
# this endpoint reads plus two it deliberately drops.
BERLIN: dict[str, Any] = {
    "id": 2950159,
    "name": "Berlin",
    "latitude": 52.52437,
    "longitude": 13.41053,
    "country": "Germany",
    "country_code": "DE",
    "admin1": "State of Berlin",
    "timezone": "Europe/Berlin",
}


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Any:
    def _stub(body: Any, status_code: int = 200) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(status_code, json=body)

        monkeypatch.setattr(geocoding, "_transport", lambda: httpx.MockTransport(handler))
        return seen

    return _stub


def test_returns_the_four_documented_keys_and_nothing_else(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Any,
) -> None:
    stub({"results": [BERLIN]})
    user = make_user()

    response = client.get(SEARCH_URL, params={"q": "berlin"}, headers=authorization(user))

    assert response.status_code == 200
    assert response.json() == {
        "results": [{"name": "Berlin", "country": "Germany", "lat": 52.52437, "lon": 13.41053}]
    }


def test_no_match_is_an_empty_list_rather_than_a_404(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Any,
) -> None:
    # The provider omits `results` entirely here. A 404 would fire on every
    # keystroke that has not finished spelling a city.
    stub({"generationtime_ms": 0.67})
    user = make_user()

    response = client.get(SEARCH_URL, params={"q": "zzzzzzzz"}, headers=authorization(user))

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_a_one_character_query_never_reaches_the_provider(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Any,
) -> None:
    seen = stub({"results": [BERLIN]})
    user = make_user()

    response = client.get(SEARCH_URL, params={"q": "b"}, headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert seen == []


def test_a_whitespace_query_is_refused_after_stripping(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Any,
) -> None:
    # Two characters long and empty once trimmed. Measured before it is
    # measured is the whole of the ordering lesson in 072.
    seen = stub({"results": [BERLIN]})
    user = make_user()

    response = client.get(SEARCH_URL, params={"q": "  "}, headers=authorization(user))

    assert response.status_code == 422
    assert seen == []


def test_the_query_is_stripped_before_it_is_sent(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Any,
) -> None:
    seen = stub({"results": [BERLIN]})
    user = make_user()

    client.get(SEARCH_URL, params={"q": "  berlin  "}, headers=authorization(user))

    assert len(seen) == 1
    assert dict(seen[0].url.params)["name"] == "berlin"


def test_a_missing_query_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.get(SEARCH_URL, headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_a_silent_provider_is_502_geocoding_unavailable(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Any,
) -> None:
    stub({"error": True}, status_code=500)
    user = make_user()

    response = client.get(SEARCH_URL, params={"q": "berlin"}, headers=authorization(user))

    assert response.status_code == 502
    assert response.json()["code"] == "geocoding_unavailable"


def test_the_failure_message_names_no_provider(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    stub: Any,
) -> None:
    # CONVENTIONS.md: the frontend never renders a raw error, and every failure
    # path has a written message. "Open-Meteo" means nothing to a user.
    stub({"error": True}, status_code=500)
    user = make_user()

    detail = client.get(SEARCH_URL, params={"q": "berlin"}, headers=authorization(user)).json()[
        "detail"
    ]

    assert "Open-Meteo" not in detail
    assert detail == "Location search is unavailable. Try again shortly."


def test_without_a_token_it_is_401(client: TestClient) -> None:
    response = client.get(SEARCH_URL, params={"q": "berlin"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"

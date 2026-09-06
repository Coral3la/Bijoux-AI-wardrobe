"""The SPA catch-all, against a temporary static dir and a fresh application.

`app.main` registers the route only when `backend/static` exists — inside the
Docker image and nowhere else — so the `app` every other integration test
imports has no catch-all to hit, and nothing covered it when B1 of the
2026-09-05 review closed a path traversal there. `register_spa` is the function
`main.py` calls at import; here it is called on an application of its own,
after `tmp_path` has been given an `index.html`, which is the order the
import-time `is_dir()` check makes impossible on the real one.

No database anywhere: nothing here reaches a route that takes a session.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import register_spa

INDEX_HTML = "<!doctype html><title>bijoux</title>"
LOGO_SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
OUTSIDE = "one directory above static/, where the image keeps its source"


@pytest.fixture
def spa(tmp_path: Path) -> TestClient:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(INDEX_HTML)
    (static / "assets" / "logo.svg").write_bytes(LOGO_SVG)
    (tmp_path / "secret.txt").write_text(OUTSIDE)

    application = FastAPI()
    register_spa(application, static)
    return TestClient(application)


def test_a_traversal_does_not_leave_the_static_dir(spa: TestClient) -> None:
    # Percent-encoded, because httpx collapses a literal `/../` before the
    # request leaves — `/../secret.txt` arrives as `/secret.txt` and proves
    # nothing. The server decodes `%2e%2e`, the route sees `../secret.txt`,
    # and that resolves to a file which exists.
    response = spa.get("/%2e%2e/secret.txt")

    assert response.text == INDEX_HTML


def test_an_asset_inside_the_static_dir_is_served_as_itself(spa: TestClient) -> None:
    # The one test that fails when containment fails *closed*. The route
    # compares a resolved candidate against `static_dir` as given, so a
    # `static_dir` that is not itself resolved — a symlink, an unresolved
    # `tmp_path` — makes every request fall back to index.html, and the
    # other four tests all stay green over a dead route. The fixture relies on
    # pytest resolving `tmp_path`, measured on 2026-09-06 and deliberately not
    # repeated with `.resolve()` there: this is what shouts if it stops.
    response = spa.get("/assets/logo.svg")

    assert response.content == LOGO_SVG


def test_health_with_a_trailing_slash_is_404_json(spa: TestClient) -> None:
    response = spa.get("/health/")

    assert (response.status_code, response.json()) == (404, {"detail": "Not Found"})


def test_a_missed_api_path_is_404_json(spa: TestClient) -> None:
    response = spa.get("/api/v1/nope")

    assert (response.status_code, response.json()) == (404, {"detail": "Not Found"})


def test_a_deep_link_is_answered_with_index_html(spa: TestClient) -> None:
    response = spa.get("/wardrobe")

    assert (response.status_code, response.text) == (200, INDEX_HTML)

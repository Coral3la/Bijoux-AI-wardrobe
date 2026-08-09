"""The rejection paths of POST /items/upload, proven not to reach Cloudinary or
the database. Both dependencies are replaced with stubs that raise if they are
touched, so "every file is decided before any file is uploaded" is enforced
rather than assumed. The paths that really write rows need the test database
task 0.10 owns, and their tests belong there."""

import uuid
from collections.abc import Iterator
from typing import Any

import cloudinary.uploader
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.main import app
from app.models.user import User
from app.services.storage import StorageError

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
TEXT = b"this is not an image at all\n"

UPLOAD_URL = "/api/v1/items/upload"


def _part(name: str, data: bytes) -> tuple[str, tuple[str, bytes, str]]:
    # Every part declares image/jpeg: the decision is made from the bytes, so a
    # lying Content-Type must not change any of these outcomes (045).
    return ("files", (name, data, "image/jpeg"))


class _ForbiddenSession:
    """FastAPI resolves every dependency before the handler runs, so a stub
    that raises on call would fail even a request the route rejects first. This
    one raises on *use*, which is the property these tests are asserting."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the database was used: Session.{name}")


def _no_database() -> Any:
    return _ForbiddenSession()


@pytest.fixture
def user() -> User:
    return User(id=uuid.uuid4(), email="upload@example.com", password_hash="x")


@pytest.fixture
def no_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Cloudinary was called")

    monkeypatch.setattr(cloudinary.uploader, "upload", explode)


@pytest.fixture
def client(user: User) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _no_database
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client() -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _no_database
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_rejects_a_text_file_with_415_and_never_calls_cloudinary(
    client: TestClient, no_upload: None
) -> None:
    response = client.post(UPLOAD_URL, files=[_part("notes.txt", TEXT)])

    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file_type"


def test_rejects_an_svg_with_415(client: TestClient, no_upload: None) -> None:
    response = client.post(UPLOAD_URL, files=[_part("logo.svg", SVG)])

    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file_type"


def test_rejects_an_empty_file_with_415_rather_than_413(
    client: TestClient, no_upload: None
) -> None:
    response = client.post(UPLOAD_URL, files=[_part("empty.jpg", b"")])

    assert response.status_code == 415


def test_rejects_an_over_large_image_with_413(client: TestClient, no_upload: None) -> None:
    too_big = JPEG + b"\x00" * (settings.max_upload_bytes - len(JPEG) + 1)

    response = client.post(UPLOAD_URL, files=[_part("huge.jpg", too_big)])

    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


def test_reports_an_over_large_non_image_as_the_wrong_type(
    client: TestClient, no_upload: None
) -> None:
    # 045 puts type before size, and the route runs its two passes in that
    # order so a batch cannot invert the rule a single file obeys.
    too_big = TEXT + b"\x00" * settings.max_upload_bytes

    response = client.post(UPLOAD_URL, files=[_part("huge.txt", too_big)])

    assert response.status_code == 415


def test_one_bad_file_rejects_the_batch_before_the_good_ones_are_uploaded(
    client: TestClient, no_upload: None
) -> None:
    response = client.post(
        UPLOAD_URL,
        files=[_part("good.jpg", JPEG), _part("also-good.png", PNG), _part("bad.txt", TEXT)],
    )

    assert response.status_code == 415


def test_names_the_offending_file_in_the_detail(client: TestClient, no_upload: None) -> None:
    response = client.post(UPLOAD_URL, files=[_part("good.jpg", JPEG), _part("bad.txt", TEXT)])

    assert "bad.txt" in response.json()["detail"]


def test_rejects_more_files_than_the_request_limit(client: TestClient, no_upload: None) -> None:
    files = [_part(f"{n}.jpg", JPEG) for n in range(settings.MAX_FILES_PER_REQUEST + 1)]

    response = client.post(UPLOAD_URL, files=files)

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["detail"].startswith("files: ")


def test_rejects_a_request_with_no_files(client: TestClient, no_upload: None) -> None:
    response = client.post(UPLOAD_URL, files=[])

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["detail"].startswith("files: ")


def test_maps_a_storage_failure_to_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise StorageError("The image could not be stored.")

    monkeypatch.setattr("app.api.v1.routes.items.upload_image", fail)

    response = client.post(UPLOAD_URL, files=[_part("good.jpg", JPEG)])

    assert response.status_code == 502
    assert response.json()["code"] == "upload_failed"


def test_requires_a_token(anonymous_client: TestClient, no_upload: None) -> None:
    response = anonymous_client.post(UPLOAD_URL, files=[_part("good.jpg", JPEG)])

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_reading_an_item_requires_a_token(anonymous_client: TestClient) -> None:
    response = anonymous_client.get(f"/api/v1/items/{uuid.uuid4()}")

    assert response.status_code == 401


def test_listing_items_requires_a_token(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/api/v1/items")

    assert response.status_code == 401


def test_rejects_an_item_id_that_is_not_a_uuid(client: TestClient) -> None:
    response = client.get("/api/v1/items/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_rejects_a_status_filter_outside_the_closed_vocabulary(client: TestClient) -> None:
    response = client.get("/api/v1/items", params={"status": "almost_ready"})

    assert response.status_code == 422
    assert response.json()["detail"].startswith("status: ")

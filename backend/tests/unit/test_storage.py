"""Cloudinary upload and delivery URLs. No network: the type and size rules are
pure functions of bytes, and the one call that would leave the process is
monkeypatched. Nothing here needs a database or a fixture."""

import uuid
from typing import Any

import cloudinary.uploader
import pytest
from cloudinary.exceptions import Error as CloudinaryError

from app.core.config import settings
from app.services.storage import (
    SIGNATURE_BYTES,
    FileTooLargeError,
    StorageError,
    Transform,
    UnsupportedFileTypeError,
    build_url,
    upload_image,
    validate_image,
    validate_image_type,
)

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"
HEIF = b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00"

GIF = b"GIF89a\x01\x00\x01\x00\x00\x00\x00"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
BMP = b"BM\x36\x00\x00\x00\x00\x00\x00\x00\x36\x00"
TEXT = b"this is not an image at all\n"


@pytest.fixture
def cloud_name(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")
    return "test-cloud"


@pytest.fixture
def no_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Cloudinary was called")

    monkeypatch.setattr(cloudinary.uploader, "upload", explode)


@pytest.mark.parametrize(
    "data", [JPEG, PNG, WEBP, HEIC, HEIF], ids=["jpeg", "png", "webp", "heic", "heif"]
)
def test_accepts_every_format_the_api_spec_allows(data: bytes) -> None:
    validate_image(data)


@pytest.mark.parametrize(
    "data", [GIF, SVG, BMP, TEXT, b""], ids=["gif", "svg", "bmp", "text", "empty"]
)
def test_rejects_anything_outside_the_allow_list(data: bytes) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_image(data)


def test_rejects_a_file_shorter_than_its_signature_rather_than_raising_indexerror() -> None:
    # WebP is checked at offsets 0 and 8, HEIF at 4 and 8, so every prefix
    # below 12 bytes is short of the bytes an indexing implementation reads.
    for data in (WEBP, HEIC):
        for length in range(12):
            with pytest.raises(UnsupportedFileTypeError):
                validate_image(data[:length])


def test_rejects_bytes_that_carry_a_signature_somewhere_other_than_its_offset() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_image(b"\x00\x00\x00\x00" + JPEG)


def test_the_size_limit_is_mebibytes() -> None:
    assert settings.max_upload_bytes == settings.MAX_UPLOAD_MB * 1024 * 1024


def test_accepts_an_image_of_exactly_the_size_limit() -> None:
    validate_image(JPEG + b"\x00" * (settings.max_upload_bytes - len(JPEG)))


def test_rejects_an_image_one_byte_over_the_size_limit() -> None:
    with pytest.raises(FileTooLargeError):
        validate_image(JPEG + b"\x00" * (settings.max_upload_bytes - len(JPEG) + 1))


def test_reports_an_unsupported_type_before_a_size_problem() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_image(b"x" * (settings.max_upload_bytes + 1))


def test_the_signature_width_is_the_widest_offset_any_signature_reads() -> None:
    # WebP compares data[8:12] and HEIF data[8:12]; nothing reads further, and
    # the upload route reads exactly this many bytes per file in its first pass.
    assert SIGNATURE_BYTES == 12


@pytest.mark.parametrize(
    "data", [JPEG, PNG, WEBP, HEIC, HEIF], ids=["jpeg", "png", "webp", "heic", "heif"]
)
def test_accepts_every_format_from_the_signature_width_alone(data: bytes) -> None:
    validate_image_type(data[:SIGNATURE_BYTES])


@pytest.mark.parametrize("data", [GIF, SVG, BMP, TEXT], ids=["gif", "svg", "bmp", "text"])
def test_rejects_a_head_that_carries_no_accepted_signature(data: bytes) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_image_type(data[:SIGNATURE_BYTES])


@pytest.mark.parametrize(
    "data,signature_length",
    [(JPEG, 3), (PNG, 8), (WEBP, 12), (HEIC, 12), (HEIF, 12)],
    ids=["jpeg", "png", "webp", "heic", "heif"],
)
def test_rejects_a_head_truncated_below_its_own_signature(
    data: bytes, signature_length: int
) -> None:
    # The truncated upload a dropped connection produces must be a 415, not an
    # IndexError from indexing past the end and not a 413 from the size pass.
    for length in range(signature_length):
        with pytest.raises(UnsupportedFileTypeError):
            validate_image_type(data[:length])


def test_rejects_an_empty_head() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_image_type(b"")


def test_has_one_member_per_documented_transform() -> None:
    # `07-DEPLOYMENT.md` names four. A fifth member added without a
    # `_TRANSFORMS` entry surfaces as a KeyError inside build_url at whatever
    # call site reaches it first; this is the cheaper place to notice.
    assert len(Transform) == 4


@pytest.mark.parametrize(
    "transform,expected",
    [
        (Transform.THUMBNAIL, "w_300,h_300,c_pad,b_white,f_auto,q_auto"),
        (Transform.DETAIL, "w_800,c_limit,f_auto,q_auto"),
        (Transform.VISION, "w_800,c_limit,f_auto,q_auto"),
        (Transform.LOOKCARD, "w_400,h_500,c_pad,b_transparent,f_auto,q_auto"),
    ],
    ids=["thumbnail", "detail", "vision", "lookcard"],
)
def test_builds_each_transform_exactly_as_deployment_documents_it(
    cloud_name: str, transform: Transform, expected: str
) -> None:
    url = build_url("bijoux/a-user/asset", transform)

    assert (
        url == f"https://res.cloudinary.com/test-cloud/image/upload/{expected}/bijoux/a-user/asset"
    )


def test_keeps_the_folder_separators_in_a_public_id(cloud_name: str) -> None:
    assert build_url("bijoux/a-user/asset", Transform.DETAIL).endswith("/bijoux/a-user/asset")


def test_escapes_a_public_id_that_would_otherwise_change_the_path(cloud_name: str) -> None:
    assert build_url("a b?c#d", Transform.DETAIL).endswith("/a%20b%3Fc%23d")


def test_raises_when_no_cloud_name_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "")

    with pytest.raises(StorageError):
        build_url("bijoux/a-user/asset", Transform.DETAIL)


def test_uploads_into_a_folder_named_for_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_upload(file: Any, **options: Any) -> dict[str, Any]:
        seen["file"] = file
        seen["options"] = options
        return {"public_id": "bijoux/a-user/xyz789"}

    monkeypatch.setattr(cloudinary.uploader, "upload", fake_upload)
    user_id = uuid.uuid4()

    assert upload_image(JPEG, user_id) == "bijoux/a-user/xyz789"
    assert seen["file"] == JPEG
    assert seen["options"]["folder"] == f"{settings.CLOUDINARY_UPLOAD_FOLDER}/{user_id}"


def test_does_not_reach_cloudinary_when_the_bytes_are_not_an_image(no_upload: None) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        upload_image(TEXT, uuid.uuid4())


def test_does_not_reach_cloudinary_when_the_file_is_too_large(no_upload: None) -> None:
    with pytest.raises(FileTooLargeError):
        upload_image(JPEG + b"\x00" * settings.max_upload_bytes, uuid.uuid4())


def test_wraps_a_cloudinary_failure_in_a_storage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise CloudinaryError("Socket error")

    monkeypatch.setattr(cloudinary.uploader, "upload", fail)

    with pytest.raises(StorageError):
        upload_image(JPEG, uuid.uuid4())


def test_wraps_an_unexpected_sdk_failure_in_a_storage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Measured, not assumed: cloudinary.utils.sign_request raises a plain
    # ValueError for a missing key or secret, before any request is made.
    def fail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("Must supply api_key")

    monkeypatch.setattr(cloudinary.uploader, "upload", fail)

    with pytest.raises(StorageError):
        upload_image(JPEG, uuid.uuid4())


def test_raises_when_the_response_carries_no_public_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cloudinary.uploader, "upload", lambda *a, **k: {"url": "https://x/y"})

    with pytest.raises(StorageError):
        upload_image(JPEG, uuid.uuid4())

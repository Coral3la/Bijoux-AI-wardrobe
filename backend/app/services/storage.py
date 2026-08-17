"""Cloudinary upload and delivery URLs.

The only module in the project that talks to Cloudinary. It raises its own
exceptions rather than `ApiError` so that `scripts/seed_demo.py` can call it
with no HTTP request in sight; the upload route maps them onto statuses.
"""

import logging
import uuid
from enum import StrEnum
from urllib.parse import quote

import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError

from app.core.config import settings

logger = logging.getLogger(__name__)

DELIVERY_HOST = "https://res.cloudinary.com"

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


class UnsupportedFileTypeError(Exception):
    """The bytes are not one of the image formats this project accepts."""


class FileTooLargeError(Exception):
    """The bytes are larger than `settings.max_upload_bytes`."""


class StorageError(Exception):
    """Cloudinary could not be reached, or refused what it was sent."""


class Transform(StrEnum):
    THUMBNAIL = "thumbnail"
    DETAIL = "detail"
    VISION = "vision"
    LOOKCARD = "lookcard"


# The table in `07-DEPLOYMENT.md`. `detail` and `vision` were the same string
# until task 1.1, and this is exactly the move the split existed to allow:
# `vision` is fetched by OpenAI rather than by a browser, so f_auto would pick
# a format from an Accept header we cannot observe. Pinned to JPEG instead.
# `DECISIONS.md` 083.
_TRANSFORMS: dict[Transform, str] = {
    Transform.THUMBNAIL: "w_300,h_300,c_pad,b_white,f_auto,q_auto",
    Transform.DETAIL: "w_800,c_limit,f_auto,q_auto",
    Transform.VISION: "w_800,c_limit,f_jpg,q_auto",
    Transform.LOOKCARD: "w_400,h_500,c_pad,b_transparent,f_auto,q_auto",
}

# ISO base media brands that mean "this is a HEIF still image". An iPhone set
# to keep originals uploads one of these rather than a JPEG.
_HEIF_BRANDS = frozenset(
    {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}
)

# The widest offset any signature reads. Twelve bytes decide the type for every
# accepted format, which is what lets the upload route check twenty files
# before pulling a single one of them into memory.
SIGNATURE_BYTES = 12


def _is_accepted_image(data: bytes) -> bool:
    # Slices rather than indexes throughout: a file shorter than a signature
    # produces a short slice that matches nothing, where data[7] would raise.
    return (
        data.startswith(b"\xff\xd8\xff")  # JPEG
        or data.startswith(b"\x89PNG\r\n\x1a\n")  # PNG
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")  # WebP
        or (data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS)  # HEIC / HEIF
    )


def validate_image_type(head: bytes) -> None:
    if not _is_accepted_image(head):
        raise UnsupportedFileTypeError("Only JPEG, PNG, WebP and HEIC images can be uploaded.")


def validate_image(file_bytes: bytes) -> None:
    validate_image_type(file_bytes)
    if len(file_bytes) > settings.max_upload_bytes:
        raise FileTooLargeError(f"Images must be {settings.MAX_UPLOAD_MB} MB or smaller.")


def upload_image(file_bytes: bytes, user_id: uuid.UUID) -> str:
    validate_image(file_bytes)

    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            folder=f"{settings.CLOUDINARY_UPLOAD_FOLDER}/{user_id}",
            resource_type="image",
        )
    except CloudinaryError as exc:
        logger.error(
            "Cloudinary rejected an upload", extra={"user_id": str(user_id), "error": str(exc)}
        )
        raise StorageError("The image could not be stored.") from exc
    except Exception as exc:
        # The SDK validates credentials with a plain ValueError before it sends
        # anything, so CloudinaryError alone would let a misconfigured key reach
        # the client as a bare 500. The type is logged because this is the
        # branch for failures we did not predict.
        logger.error(
            "Cloudinary upload failed unexpectedly",
            extra={"user_id": str(user_id), "error_type": type(exc).__name__, "error": str(exc)},
        )
        raise StorageError("The image could not be stored.") from exc

    public_id = result.get("public_id")
    if not isinstance(public_id, str):
        logger.error("Cloudinary returned no public_id", extra={"user_id": str(user_id)})
        raise StorageError("The image could not be stored.")
    return public_id


def build_url(public_id: str, transform: Transform) -> str:
    if not settings.CLOUDINARY_CLOUD_NAME:
        raise StorageError("CLOUDINARY_CLOUD_NAME is not set.")

    # quote() leaves "/" alone, so the folder separators in a public_id survive
    # and anything else that would change the meaning of the path is escaped.
    return (
        f"{DELIVERY_HOST}/{settings.CLOUDINARY_CLOUD_NAME}"
        f"/image/upload/{_TRANSFORMS[transform]}/{quote(public_id)}"
    )

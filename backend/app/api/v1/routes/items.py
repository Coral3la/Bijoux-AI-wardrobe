import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import ApiError
from app.core.short_id import generate_short_id
from app.enums import Category, ColorPrimary, ItemStatus
from app.models.item import Item
from app.models.user import User
from app.schemas.item import ItemListResponse, ItemResponse, ItemUploadResponse
from app.services.storage import (
    SIGNATURE_BYTES,
    FileTooLargeError,
    StorageError,
    UnsupportedFileTypeError,
    upload_image,
    validate_image_type,
)
from app.services.tagging import tag_and_store

router = APIRouter(prefix="/items", tags=["items"])

logger = logging.getLogger(__name__)

MAX_SHORT_ID_ATTEMPTS = 3

_REJECTIONS: dict[type[Exception], tuple[int, str]] = {
    UnsupportedFileTypeError: (status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_file_type"),
    FileTooLargeError: (status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large"),
    StorageError: (status.HTTP_502_BAD_GATEWAY, "upload_failed"),
}


def _rejected(exc: Exception, filename: str | None) -> ApiError:
    http_status, code = _REJECTIONS[type(exc)]
    return ApiError(http_status, code, f"{filename or 'file'}: {exc}")


def _reject_unacceptable(files: list[UploadFile]) -> None:
    # Both passes cover every file before any upload runs: 04-API-SPEC.md
    # rejects the whole request for one bad file, so deciding as we uploaded
    # would leave the assets of a failed batch orphaned in Cloudinary.
    # Type before size, so an over-large non-image reports the type (045).
    for file in files:
        head = file.file.read(SIGNATURE_BYTES)
        file.file.seek(0)
        try:
            validate_image_type(head)
        except UnsupportedFileTypeError as exc:
            raise _rejected(exc, file.filename) from exc

    for file in files:
        # The multipart parser fills in `size` before this handler runs, so
        # this is the only size check that happens before the bytes are read.
        # validate_image repeats it inside upload_image for the seed script.
        if file.size is not None and file.size > settings.max_upload_bytes:
            raise _rejected(
                FileTooLargeError(f"Images must be {settings.MAX_UPLOAD_MB} MB or smaller."),
                file.filename,
            )


def _log_orphans(public_ids: list[str], user_id: uuid.UUID) -> None:
    if not public_ids:
        return
    # Foldering by user (047) makes orphans auditable only if the ids of a
    # failed batch are written down at the moment they are stranded.
    logger.error(
        "Upload batch failed after assets were stored",
        extra={"user_id": str(user_id), "orphaned_public_ids": public_ids},
    )


def _insert(db: Session, user_id: uuid.UUID, public_ids: list[str]) -> list[Item]:
    attempts_left = MAX_SHORT_ID_ATTEMPTS
    while True:
        attempts_left -= 1
        items = [
            Item(user_id=user_id, short_id=generate_short_id(), image_public_id=public_id)
            for public_id in public_ids
        ]
        db.add_all(items)
        try:
            db.commit()
        except IntegrityError as exc:
            # A failed flush leaves the session unusable, so a retry is a
            # rollback and a fresh set of rows, never a second commit of these.
            db.rollback()
            if not attempts_left or "uq_items_short_id" not in str(exc.orig):
                raise
            logger.warning(
                "short_id collision, regenerating the batch",
                extra={"user_id": str(user_id), "attempts_left": attempts_left},
            )
        else:
            # No refresh: the ORM's INSERT already returns every server default
            # this response reads, and tests/integration/test_server_defaults.py
            # asserts that no SELECT follows it. DECISIONS.md 075.
            return items


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
def upload_items(
    files: Annotated[
        list[UploadFile], File(min_length=1, max_length=settings.MAX_FILES_PER_REQUEST)
    ],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemUploadResponse:
    _reject_unacceptable(files)

    public_ids: list[str] = []
    for file in files:
        try:
            public_ids.append(upload_image(file.file.read(), current_user.id))
        except (UnsupportedFileTypeError, FileTooLargeError, StorageError) as exc:
            _log_orphans(public_ids, current_user.id)
            raise _rejected(exc, file.filename) from exc

    try:
        items = _insert(db, current_user.id, public_ids)
    except SQLAlchemyError:
        _log_orphans(public_ids, current_user.id)
        raise

    for item in items:
        # Queued after the commit, so the task's own session can find the
        # row. Starlette awaits these in order once the response is sent,
        # which makes a batch tag serially — see 1.7 in STAGE-1.
        background_tasks.add_task(tag_and_store, item.id)

    return ItemUploadResponse(items=[ItemResponse.model_validate(item) for item in items])


@router.get("")
def list_items(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    item_status: Annotated[ItemStatus | None, Query(alias="status")] = None,
    category: Category | None = None,
    color_primary: ColorPrimary | None = None,
    formality_min: Annotated[int | None, Query(ge=1, le=5)] = None,
    formality_max: Annotated[int | None, Query(ge=1, le=5)] = None,
    warmth_min: Annotated[int | None, Query(ge=1, le=5)] = None,
    warmth_max: Annotated[int | None, Query(ge=1, le=5)] = None,
    search: str | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemListResponse:
    filters: list[ColumnElement[bool]] = [Item.user_id == current_user.id]
    if not include_archived:
        filters.append(Item.is_archived.is_(False))
    if item_status is not None:
        filters.append(Item.status == item_status)
    if category is not None:
        filters.append(Item.category == category)
    if color_primary is not None:
        filters.append(Item.color_primary == color_primary)
    if formality_min is not None:
        filters.append(Item.formality >= formality_min)
    if formality_max is not None:
        filters.append(Item.formality <= formality_max)
    if warmth_min is not None:
        filters.append(Item.warmth >= warmth_min)
    if warmth_max is not None:
        filters.append(Item.warmth <= warmth_max)
    if search:
        filters.append(Item.display_name.ilike(f"%{search}%"))

    total = db.scalar(select(func.count()).select_from(Item).where(*filters)) or 0
    rows = db.scalars(
        # short_id breaks the tie because every row in one upload shares a
        # created_at: now() is the transaction timestamp, not the statement's.
        select(Item)
        .where(*filters)
        .order_by(Item.created_at.desc(), Item.short_id)
        .limit(limit)
        .offset(offset)
    ).all()

    return ItemListResponse(items=[ItemResponse.model_validate(row) for row in rows], total=total)


@router.get("/{item_id}")
def get_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemResponse:
    # The ownership test is in the WHERE clause rather than a branch after the
    # load, so "not yours" and "does not exist" are the same answer at source.
    item = db.scalar(select(Item).where(Item.id == item_id, Item.user_id == current_user.id))
    if item is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", "Item not found.")
    return ItemResponse.model_validate(item)

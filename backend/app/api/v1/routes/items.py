import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import ApiError
from app.core.short_id import generate_short_id
from app.enums import (
    CATEGORY_DEPENDENT_FIELDS,
    Category,
    ColorPrimary,
    ItemStatus,
    TagIssue,
    validate_tag_dict,
)
from app.models.item import Item
from app.models.user import User
from app.schemas.item import (
    ItemListResponse,
    ItemResponse,
    ItemStatsResponse,
    ItemUpdate,
    ItemUploadResponse,
)
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


# Derived from the request schema rather than restated, so a field
# cannot be patchable and un-mergeable at the same time.
_TAG_FIELDS: tuple[str, ...] = tuple(ItemUpdate.model_fields)

# The vocabulary's coercion reasons end ", set to null" because
# they describe what the vision path does with a value it cannot
# keep. PATCH does not coerce, it refuses, so that clause is false
# here and is cut. One report, two policies, and the message has
# to be re-framed by whichever is reading it (089). Error reasons
# carry no such clause and pass through unchanged.
_COERCION_SUFFIX = ", set to "


def _owned(db: Session, item_id: uuid.UUID, user_id: uuid.UUID) -> Item:
    item = db.scalar(select(Item).where(Item.id == item_id, Item.user_id == user_id))
    if item is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", "Item not found.")
    return item


def _rejection(issue: TagIssue) -> str:
    return issue.reason.split(_COERCION_SUFFIX)[0]


def _merged(item: Item, changes: dict[str, Any]) -> dict[str, Any]:
    """
    The stored row with the request laid over it.

    The whole row rather than the request alone, because a
    category change invalidates values the client never sent:
    `PATCH {"category": "top"}` on a pair of jeans leaves a stored
    `subcategory` of `jeans` behind, and request-only validation
    calls that request clean (`04-API-SPEC.md`).

    The five category-dependent fields are cleared **before**
    validation, not after. That is what keeps "any coercion is a
    422" a rule with no exceptions: a coercion the category change
    would have caused never fires, so every coercion that does
    fire concerns a value this request actually sent. Sorting them
    out afterwards would need a `kind` on `TagIssue`, which is the
    field 086 refused to add. `DECISIONS.md` 030.
    """
    merged = {field: getattr(item, field) for field in _TAG_FIELDS}
    merged |= changes

    if "category" in changes and changes["category"] != item.category:
        for field in CATEGORY_DEPENDENT_FIELDS:
            if field not in changes:
                merged[field] = None
    return merged


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


# Declared above /{item_id}: FastAPI matches in declaration order,
# so `stats` below it is parsed as a UUID and answers 422.
@router.get("/stats")
def item_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemStatsResponse:
    # Archived rows are excluded, matching GET /items. A dashboard
    # that kept counting deleted garments would make DELETE look
    # like it did nothing.
    filters: list[ColumnElement[bool]] = [
        Item.user_id == current_user.id,
        Item.is_archived.is_(False),
    ]

    def _counts(column: InstrumentedAttribute[Any]) -> dict[str, int]:
        rows = db.execute(
            select(column, func.count()).where(*filters, column.is_not(None)).group_by(column)
        ).all()
        return {str(value): count for value, count in rows}

    # Grouping by status answers three of these numbers at once,
    # and `total` comes from the sum rather than a fourth query.
    by_status = _counts(Item.status)

    return ItemStatsResponse(
        total=sum(by_status.values()),
        by_category=_counts(Item.category),
        by_color=_counts(Item.color_primary),
        processing=by_status.get(ItemStatus.PROCESSING, 0),
        failed=by_status.get(ItemStatus.FAILED, 0),
        never_worn=0,
        most_worn=[],
    )


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


@router.patch("/{item_id}")
def update_item(
    item_id: uuid.UUID,
    changes: ItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemResponse:
    # exclude_unset is what separates "clear this field" from
    # "leave it alone": without it the first PATCH nulls every
    # field the client did not send. It also defines "supplied"
    # for the clearing rule above — a field present as null counts
    # as supplied and is not cleared a second time.
    supplied = changes.model_dump(exclude_unset=True)
    if not supplied:
        # Otherwise an empty body is a 200 that sets user_edited
        # on a request which edited nothing, and the column stops
        # meaning what 02 says it means.
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "request: at least one field must be supplied.",
        )

    item = _owned(db, item_id, current_user.id)
    merged = _merged(item, supplied)
    report = validate_tag_dict(merged)

    # Errors *and* coercions are refused. A coercion is the
    # vocabulary saying it cannot keep this value; the vision path
    # accepts that because there is nobody to ask, and here there
    # is somebody, with a form open. Accepting one returns 200
    # with the field changed from what was typed (028).
    if report.errors or report.coerced:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "; ".join(_rejection(issue) for issue in report.errors + report.coerced),
        )

    for field in _TAG_FIELDS:
        setattr(item, field, report.tags[field])
    item.user_edited = True
    db.commit()

    return ItemResponse.model_validate(item)


@router.delete("/{item_id}")
def archive_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemResponse:
    # Idempotent: archiving an archived row is a 200 carrying the
    # same object. The row is still readable by id, so a 404 on
    # the second call would contradict the GET that still answers.
    item = _owned(db, item_id, current_user.id)
    item.is_archived = True
    db.commit()

    return ItemResponse.model_validate(item)


@router.post("/{item_id}/retag", status_code=status.HTTP_202_ACCEPTED)
def retag_item(
    item_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    force: bool = False,
) -> ItemResponse:
    item = _owned(db, item_id, current_user.id)
    if item.user_edited and not force:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "item_edited",
            "This item has been edited by hand. Pass force=true to retag it anyway.",
        )

    # The tag columns are deliberately left alone. If this retag
    # fails, _store writes `failed` without touching them, so a
    # previously-good item keeps the tags it had; nulling them
    # here would destroy good data to make a failure look tidier.
    # error_message is cleared because the row is about to be
    # `processing`, and a processing row carrying a past failure
    # is incoherent on the wire.
    item.status = ItemStatus.PROCESSING
    item.error_message = None
    # Committed before the task is queued: tag_and_store opens its
    # own session and cannot see an uncommitted row. The same
    # UPDATE moves updated_at through onupdate, so the sweep's ten
    # minutes runs from this retag rather than from the insert
    # (088).
    db.commit()
    # A retag against a row that is already `processing` is
    # allowed, and two tasks can then write the same row with the
    # last write winning. Refusing would cost a row that cannot be
    # retagged for up to ten minutes when the process that owned
    # it died, which is the worse failure and the one a user meets
    # (089).
    background_tasks.add_task(tag_and_store, item.id)

    return ItemResponse.model_validate(item)

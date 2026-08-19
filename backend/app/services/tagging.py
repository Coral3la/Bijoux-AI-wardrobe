"""Tagging after the response has gone, and the sweep that
closes out what it drops.

`POST /items/upload` commits its rows and answers `202` before
any tag exists, so this module is what fills them in — one task
per item, run by Starlette once the response is on the wire.

Two calls and three ways to fail. `tag_item` raises `ValueError`
on an unusable response and lets the provider's own exceptions
escape; `validate_tags` raises `TaggingError` when the model
answered and the answer could not be accepted (086). Those are
different facts about one item — no answer arrived, against the
answer was not acceptable — and both end `failed`, so they write
different `error_message` text and the column can tell them
apart. The third is this module's own: a row swept at boot was
never answered for at all.

**Nothing may escape into the background task.** An uncaught
exception there leaves the row `processing` until the next
startup sweep, and the sweep is a ten-minute-latency backstop
rather than a handler.

The session is this module's own, opened per item, never the
request's. Not because FastAPI has closed the request's by then
— it has not, and that was checked rather than assumed: in
fastapi 0.141 yield dependencies exit after the response is
sent, so `get_db`'s session is still open while this runs. The
reasons that survive are that sharing it holds one Neon
connection for a whole twenty-file batch rather than for one
item, and that it would couple a service function to a request
lifetime for nothing. `DECISIONS.md` 088.

SQLAlchemy is synchronous and these functions are `async`, so
every query here blocks the event loop for one round trip. That
is the shape `STAGE-1` chose deliberately: the OpenAI call is
the long pole, and it belongs on the loop rather than occupying
a threadpool slot.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

from openai import OpenAIError
from sqlalchemy import CursorResult, func, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.enums import ItemStatus
from app.models.item import Item
from app.services.storage import StorageError, Transform, build_url
from app.services.vision import (
    PROMPT_VERSION,
    ItemTags,
    TaggingError,
    tag_item,
    validate_tags,
)

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)

# Three texts, because there are three ways a row stops being
# `processing`, and `error_message` is the only place they are
# told apart. The column is read by a developer: `03` gives the
# user a fixed "Couldn't read this one" and never renders this.
_UNACCEPTABLE = "The tags could not be accepted: {reason}"
_NO_ANSWER = "No usable answer arrived: {reason}"
_ABANDONED = "Tagging never finished; the process that started it is gone."


def _described(exc: Exception) -> str:
    # The type is carried because a provider exception's message
    # is frequently empty, and once the log has rotated this
    # column is the only record a failed row keeps.
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


async def _tagged(image_public_id: str) -> tuple[ItemTags | None, str | None]:
    """The two calls and every way they fail. Never raises.

    Exactly one half of the pair is `None`: the tags on success,
    the `error_message` to write on failure.
    """
    try:
        image_url = build_url(image_public_id, Transform.VISION)
        raw = await tag_item(image_url)
        return await validate_tags(raw, image_url), None
    except TaggingError as exc:
        # Its message is already the violation, naming the field
        # and the value, so a type name in front of it would
        # only get in the way.
        logger.warning(
            "Tagging rejected the model's answer",
            extra={"image_public_id": image_public_id, "violation": str(exc)},
        )
        return None, _UNACCEPTABLE.format(reason=exc)
    except (ValueError, StorageError, OpenAIError) as exc:
        # The three predicted ways no answer arrives: a response
        # that is not a dict, no URL to send, and the provider
        # itself. Every documented openai exception subclasses
        # OpenAIError, checked against the installed 2.52 rather
        # than taken from the docs — and the branch below is
        # still there for whatever that misses.
        logger.warning(
            "No usable answer from the vision model",
            extra={"image_public_id": image_public_id, "error": _described(exc)},
        )
        return None, _NO_ANSWER.format(reason=_described(exc))
    except Exception as exc:
        # The one broad catch in the project, and `CONVENTIONS`
        # has the carve-out: an exception escaping a
        # BackgroundTask leaves the row spinning until the
        # sweep, so an unpredicted failure still has to stop the
        # tile. Traceback rather than a warning, because
        # reaching here means the list above is incomplete.
        # CancelledError is a BaseException, so a shutdown
        # mid-call is not swallowed by this.
        logger.exception(
            "Tagging failed in a way this task does not predict",
            extra={"image_public_id": image_public_id},
        )
        return None, _NO_ANSWER.format(reason=_described(exc))


def _tagging_record(tags: ItemTags | None) -> dict[str, Any]:
    """What this task leaves under `attributes["tagging"]`.

    `prompt_version` is written on both paths. Which prompt
    could not read a photograph is the same question as which
    prompt read one, and a baseline that records only successes
    measures a biased sample (1.11). `coerced` is absent on the
    failure path because there is no accepted answer to have
    discarded anything, and written as `[]` on the success path
    because once 1.4's retag rewrites this column, an absent key
    and "nothing was discarded" stop being the same claim.
    """
    record: dict[str, Any] = {"prompt_version": PROMPT_VERSION}
    if tags is not None:
        record["coerced"] = [
            {"field": issue.field, "value": issue.value, "reason": issue.reason}
            for issue in tags.coerced
        ]
    return record


def _store(item: Item, tags: ItemTags | None, error_message: str | None) -> None:
    # A new dict rather than a mutation: JSONB is not
    # mutation-tracked, so `item.attributes["tagging"] = …`
    # would flush nothing at all. The spread is what keeps a
    # future `brand` alive across a retag — `attributes` is the
    # user-level column and this task is a guest in one key of
    # it (`02-DATA-MODEL.md`).
    item.attributes = {**item.attributes, "tagging": _tagging_record(tags)}

    if tags is None:
        item.status = ItemStatus.FAILED
        item.error_message = error_message
        return

    item.status = ItemStatus.READY
    item.error_message = None
    item.category = tags.category
    item.subcategory = tags.subcategory
    item.fit = tags.fit
    item.length = tags.length
    item.rise = tags.rise
    item.color_primary = tags.color_primary
    item.color_secondary = tags.color_secondary
    item.pattern = tags.pattern
    item.material = tags.material
    item.formality = tags.formality
    item.warmth = tags.warmth
    item.layer = tags.layer
    item.water_resistant = tags.water_resistant
    item.display_name = tags.display_name
    # The one field that changes name on the way to the
    # database. The dict keeps the model's own `confidence` all
    # the way here (028).
    item.ai_confidence = tags.confidence


async def tag_and_store(
    item_id: uuid.UUID,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """One item tagged and written. The background task's body.

    `session_factory` is a parameter so that a test can bind
    this to the transaction `conftest.py` rolls back; the route
    calls it with one argument, and 1.4's retag will too.
    """
    db = session_factory()
    try:
        item = db.get(Item, item_id)
        if item is None:
            # Not an error. A task is queued against a committed
            # row, but 1.4's soft delete and a test's rollback
            # can both take it away before the task is reached.
            logger.warning("Tagging found no row to write to", extra={"item_id": str(item_id)})
            return

        tags, error_message = await _tagged(item.image_public_id)
        _store(item, tags, error_message)
        db.commit()
        logger.info("Item tagged", extra={"item_id": str(item_id), "status": item.status})
    except SQLAlchemyError:
        # The row keeps its `processing` and the startup sweep
        # closes it out. There is nothing else to do from here:
        # the database is the only place an answer could have
        # been written.
        db.rollback()
        logger.exception("Tagging could not be persisted", extra={"item_id": str(item_id)})
    finally:
        db.close()


def sweep_stale_processing(db: Session) -> int:
    """Fail every `processing` row no live process can still own.

    Keyed on `updated_at` rather than `created_at`, which is
    only correct because `Item.updated_at` now carries
    `onupdate`: 1.4's retag puts a week-old row back to
    `processing`, and `created_at` would call it abandoned on
    the next boot before its task had run. The two halves are
    one decision and neither survives the other's removal (088).

    Ten minutes rather than "everything still `processing` at
    boot", which one instance and no `--workers` (`07`) would
    otherwise justify: a local `uvicorn` and the deployed
    instance read the same `DATABASE_URL`, so starting one must
    not fail work in flight in the other. Two OpenAI calls at a
    thirty-second timeout is the worst a live task can take.

    The comparison is made in SQL so the age is measured on the
    database's clock rather than on whichever machine booted.
    """
    # Session.execute is typed as returning Result, which has no
    # rowcount; every DML statement really returns a
    # CursorResult.
    result = cast(
        "CursorResult[Any]",
        db.execute(
            update(Item)
            .where(
                Item.status == ItemStatus.PROCESSING,
                Item.updated_at < func.now() - STALE_AFTER,
            )
            .values(status=ItemStatus.FAILED, error_message=_ABANDONED)
        ),
    )
    db.commit()
    return result.rowcount


def run_startup_sweep(session_factory: Callable[[], Session] = SessionLocal) -> None:
    """`sweep_stale_processing` with a session, and a promise
    not to take the process down with it.

    A sweep that raised at boot would turn task 0.7's
    database-free rejection tests red — they enter the app
    through `with TestClient(app)` and so run this — and on
    Render it would turn a database blip during a cold start
    into an API that never comes up.
    """
    db = session_factory()
    try:
        swept = sweep_stale_processing(db)
        if swept:
            logger.warning("Startup swept abandoned tagging", extra={"items": swept})
    except SQLAlchemyError:
        logger.exception("Startup sweep could not run")
    finally:
        db.close()

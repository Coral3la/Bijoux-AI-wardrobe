"""The background task, and the startup sweep that closes out what it drops.

Both halves of task 1.3, and a third thing riding along in two of the tests:
`Item.updated_at` gained `onupdate` here, so this is the first task in the
project that can prove the column moves when a row is written to.

The model is faked at `tagging.tag_item` — the name this module imported, not
`vision.tag_item`, because patching the definition would not reach a name that
was already bound. `validate_tags` is deliberately left real: the coercion and
the `top`/`layer` give-up are the two documented paths from a model answer to a
column value, and mocking the validator would test neither.
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from openai import OpenAIError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.item import Item
from app.services import tagging, vision
from app.services.storage import Transform, build_url
from app.services.tagging import (
    STALE_AFTER,
    run_startup_sweep,
    sweep_stale_processing,
    tag_and_store,
)
from app.services.vision import PROMPT_VERSION

# A clean answer, written out rather than imported from `vision._FAKE_TAGS`:
# a test that reads its expectation from the thing under test measures nothing
# on its own. `bottom` because it is the category whose `fit` rules bite.
CLEAN: dict[str, Any] = {
    "category": "bottom",
    "subcategory": "jeans",
    "fit": "straight",
    "length": "full",
    "rise": "high",
    "color_primary": "light_blue",
    "color_secondary": None,
    "pattern": "denim_wash",
    "material": "denim",
    "formality": 2,
    "warmth": 2,
    "layer": "base",
    "water_resistant": False,
    "display_name": "light blue straight jeans",
    "confidence": 0.9,
}


@pytest.fixture
def session_factory(db: Session) -> Callable[[], Session]:
    # The whole reason `tag_and_store` takes a factory. Without it the task
    # opens a second connection outside this transaction, cannot see a row the
    # test has not committed, and writes anything it does write for real.
    return lambda: db


def _fake_everywhere(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    # Two bindings, and the second is not optional. `validate_tags` resolves
    # `tag_item` from `vision`'s own module globals when it retries, so faking
    # only the name this module imported leaves the *second* call live. It
    # reached the real API once, from a test, before this line existed — which
    # is the failure `CONVENTIONS.md`'s eval rule forbids and the guard in
    # `conftest.py` now refuses.
    monkeypatch.setattr(tagging, "tag_item", fake)
    monkeypatch.setattr(vision, "tag_item", fake)


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, Any]], None]:
    def _answer(raw: dict[str, Any]) -> None:
        async def fake_tag_item(image_url: str, correction: str | None = None) -> dict[str, Any]:
            return dict(raw)

        _fake_everywhere(monkeypatch, fake_tag_item)

    return _answer


@pytest.fixture
def raises(monkeypatch: pytest.MonkeyPatch) -> Callable[[Exception], None]:
    def _raise(exc: Exception) -> None:
        async def fake_tag_item(image_url: str, correction: str | None = None) -> dict[str, Any]:
            raise exc

        _fake_everywhere(monkeypatch, fake_tag_item)

    return _raise


@pytest.fixture
def cloud_name(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")
    yield


# --- the happy path ---------------------------------------------------------


@pytest.mark.asyncio
async def test_tagging_writes_every_tag_and_marks_the_row_ready(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    item = make_item()
    answers(CLEAN)

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "ready"
    assert row.error_message is None
    assert row.category == "bottom"
    assert row.subcategory == "jeans"
    assert row.display_name == "light blue straight jeans"
    # The one field that changes name between the model and the column.
    assert row.ai_confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_the_image_sent_to_the_model_is_the_vision_transform(
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
    cloud_name: None,
) -> None:
    # f_jpg rather than f_auto, because OpenAI's fetcher sends an Accept header
    # we cannot observe (`DECISIONS.md` 083). Nothing else in the task names it.
    item = make_item()
    seen: list[str] = []

    async def fake_tag_item(image_url: str, correction: str | None = None) -> dict[str, Any]:
        seen.append(image_url)
        return dict(CLEAN)

    _fake_everywhere(monkeypatch, fake_tag_item)

    await tag_and_store(item.id, session_factory)

    assert seen == [build_url(item.image_public_id, Transform.VISION)]


@pytest.mark.asyncio
async def test_tagging_records_the_prompt_version(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    item = make_item()
    answers(CLEAN)

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.attributes["tagging"]["prompt_version"] == PROMPT_VERSION


@pytest.mark.asyncio
async def test_an_answer_with_nothing_discarded_writes_an_empty_list(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    # Explicitly `[]` rather than absent: once 1.4's retag rewrites this column,
    # a missing key and "nothing was discarded" stop being the same statement.
    item = make_item()
    answers(CLEAN)

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.attributes["tagging"]["coerced"] == []


@pytest.mark.asyncio
async def test_a_discarded_value_survives_in_attributes(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    # `fit: "flared"` came back on real jeans at task 1.1, was correctly nulled,
    # and was remembered by nothing. That is the gap 084 opened and this closes.
    item = make_item()
    answers(CLEAN | {"fit": "flared"})

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "ready"
    assert row.fit is None
    coerced = row.attributes["tagging"]["coerced"]
    assert [(issue["field"], issue["value"]) for issue in coerced] == [("fit", "flared")]
    assert coerced[0]["reason"]


@pytest.mark.asyncio
async def test_tagging_leaves_other_attributes_keys_alone(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    # `attributes` is the user-level column (`02-DATA-MODEL.md`) and this task is
    # a guest in one key of it. Replacing the column would eat a future `brand`.
    item = make_item(attributes={"brand": "acme"})
    answers(CLEAN)

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.attributes["brand"] == "acme"


@pytest.mark.asyncio
async def test_tagging_moves_updated_at(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    # The `onupdate` half of this task. Delete it from the model and the column
    # keeps its insert-time value here, and 1.4 inherits the staleness.
    item = make_item(updated_at=datetime.now(UTC) - timedelta(minutes=5))
    inserted = item.updated_at
    answers(CLEAN)

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    db.refresh(row)
    assert row.updated_at > inserted


# --- the two failures, which must not read the same in the column -----------


@pytest.mark.asyncio
async def test_an_answer_that_cannot_be_accepted_fails_the_row_with_the_violation(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    # `standalone` on a top is a legal member of the enum and the one category
    # the vocabulary refuses to guess for, so it survives the retry as an error.
    item = make_item()
    answers(
        CLEAN
        | {"category": "top", "subcategory": "shirt", "rise": None, "fit": "relaxed"}
        | {"layer": "standalone"}
    )

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "failed"
    assert row.error_message is not None
    assert "could not be accepted" in row.error_message
    assert "layer" in row.error_message


@pytest.mark.asyncio
async def test_no_answer_at_all_fails_the_row_with_different_text(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    raises: Callable[[Exception], None],
    cloud_name: None,
) -> None:
    # 086 keeps these apart on purpose: the model answered unacceptably, against
    # no usable answer arrived. Both end `failed` and the column has to say which.
    item = make_item()
    raises(ValueError("The vision model returned no content."))

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "failed"
    assert row.error_message is not None
    assert "No usable answer" in row.error_message
    assert "could not be accepted" not in row.error_message


@pytest.mark.asyncio
async def test_a_provider_failure_does_not_escape_the_task(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    raises: Callable[[Exception], None],
    cloud_name: None,
) -> None:
    item = make_item()
    raises(OpenAIError("connection error"))

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "failed"
    assert row.error_message is not None
    assert "OpenAIError" in row.error_message


@pytest.mark.asyncio
async def test_an_unpredicted_failure_still_stops_the_row_spinning(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    raises: Callable[[Exception], None],
    cloud_name: None,
) -> None:
    # The `except Exception` carve-out `CONVENTIONS.md` records. Narrow the catch
    # and this row stays `processing` until a boot ten minutes away.
    item = make_item()
    raises(RuntimeError("something nobody predicted"))

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "failed"


@pytest.mark.asyncio
async def test_a_missing_cloud_name_fails_one_row_rather_than_the_batch(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The URL is built inside the task for this reason. Built in the route, a
    # StorageError would 502 a whole upload after the rows were already written.
    item = make_item()
    answers(CLEAN)
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "")

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "failed"
    assert row.error_message is not None
    assert "StorageError" in row.error_message


@pytest.mark.asyncio
async def test_a_failed_row_still_records_which_prompt_could_not_read_it(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    raises: Callable[[Exception], None],
    cloud_name: None,
) -> None:
    # A baseline that records only successes measures a biased sample (1.11).
    # No `coerced` key, because there is no accepted answer to have discarded.
    item = make_item()
    raises(ValueError("no content"))

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.attributes["tagging"]["prompt_version"] == PROMPT_VERSION
    assert "coerced" not in row.attributes["tagging"]


@pytest.mark.asyncio
async def test_tagging_a_row_that_is_gone_is_not_an_error(
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    answers(CLEAN)

    await tag_and_store(uuid.uuid4(), session_factory)


# --- the startup sweep ------------------------------------------------------


def test_the_stale_threshold_is_ten_minutes() -> None:
    # Pinned literally as well as behaviourally: the tests below plant literal
    # minutes, so a test that computed its age from this constant would adapt
    # to a mutation of it and measure nothing.
    assert STALE_AFTER.total_seconds() == 600


def test_the_sweep_fails_a_processing_row_past_the_threshold(
    db: Session, make_item: Callable[..., Item]
) -> None:
    item = make_item(updated_at=datetime.now(UTC) - timedelta(minutes=11))

    assert sweep_stale_processing(db) == 1

    row = db.get(Item, item.id)
    assert row is not None
    db.refresh(row)
    assert row.status == "failed"
    assert row.error_message is not None
    assert "never finished" in row.error_message


def test_the_sweep_leaves_a_recent_processing_row_alone(
    db: Session, make_item: Callable[..., Item]
) -> None:
    item = make_item(updated_at=datetime.now(UTC) - timedelta(minutes=9))

    assert sweep_stale_processing(db) == 0

    row = db.get(Item, item.id)
    assert row is not None
    db.refresh(row)
    assert row.status == "processing"


def test_the_sweep_leaves_a_ready_row_alone(db: Session, make_item: Callable[..., Item]) -> None:
    # Drop the status predicate and the sweep fails the whole wardrobe.
    item = make_item(status="ready", updated_at=datetime.now(UTC) - timedelta(days=3))

    assert sweep_stale_processing(db) == 0

    row = db.get(Item, item.id)
    assert row is not None
    db.refresh(row)
    assert row.status == "ready"


def test_the_sweep_moves_updated_at(db: Session, make_item: Callable[..., Item]) -> None:
    # The sweep is the first `update()` this project runs, so it is also where
    # `onupdate` is proved to apply to a Core statement and not only to a flush.
    item = make_item(updated_at=datetime.now(UTC) - timedelta(minutes=11))
    planted = item.updated_at

    sweep_stale_processing(db)

    row = db.get(Item, item.id)
    assert row is not None
    db.refresh(row)
    assert row.updated_at > planted


def test_the_startup_sweep_does_not_raise_when_the_database_is_unreachable() -> None:
    # Task 0.7's rejection tests need no database and now enter the app through
    # `with TestClient(app)`, which runs this. A raising sweep turns eight
    # passing tests red for a reason that has nothing to do with them.
    closed: list[bool] = []

    class _DeadSession:
        def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise OperationalError("SELECT 1", {}, Exception("no route to host"))

        def close(self) -> None:
            closed.append(True)

    run_startup_sweep(lambda: _DeadSession())  # type: ignore[arg-type,return-value]

    assert closed == [True]


@pytest.mark.asyncio
async def test_a_successful_retag_clears_the_previous_failure_message(
    db: Session,
    make_item: Callable[..., Item],
    session_factory: Callable[[], Session],
    answers: Callable[[dict[str, Any]], None],
    cloud_name: None,
) -> None:
    # The line 1.3 left for 1.4. Unreachable until retag existed, because a
    # row only ever reached this task as `processing` with no message; now a
    # row that failed once can succeed on its second attempt, and a `ready`
    # row carrying last time's error is a lie `ItemResponse` shows a client.
    item = make_item(status="failed", error_message="No usable answer arrived: ValueError")
    answers(CLEAN)

    await tag_and_store(item.id, session_factory)

    row = db.get(Item, item.id)
    assert row is not None
    assert row.status == "ready"
    assert row.error_message is None

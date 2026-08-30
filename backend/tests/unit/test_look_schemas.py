"""The two numbers `feedback` admits, compared against their definition.

`app/models/look.py` holds `FEEDBACK_UP` and `FEEDBACK_DOWN`, migration `0004`
builds `ck_looks_feedback_values` from them, and `LookUpdate.feedback` is
spelled `Literal[-1, 1]` — a **transcription**, because
`Literal[FEEDBACK_UP, FEEDBACK_DOWN]` does not type-check. PEP 586 admits
literal values only and `Final` does not exempt a name; Pydantic accepts the
spelling at runtime, so nothing but `mypy` reports it.

`DECISIONS.md` 181 promised the constants and the schema would be held together
by the compiler. They are held together by this file instead, which is the
weaker of the two and is why it is a file rather than a sentence: a transcribed
literal with nothing comparing it is exactly the drift `CONVENTIONS.md`'s
"limits and units" section collects instances of.
"""

from typing import Literal, get_args, get_origin

import pytest
from pydantic import ValidationError

from app.models.look import FEEDBACK_DOWN, FEEDBACK_UP
from app.schemas.look import LookResponse, LookUpdate


def _feedback_literals(model: type, field: str) -> set[int]:
    """The values the `Literal[...]` arm of `Literal[…] | None` admits."""
    annotation = model.model_fields[field].annotation
    for arm in get_args(annotation):
        if get_origin(arm) is Literal:
            return set(get_args(arm))
    raise AssertionError(f"{model.__name__}.{field} has no Literal arm")


@pytest.mark.parametrize("model", [LookUpdate, LookResponse])
def test_the_literal_admits_exactly_the_two_named_constants(model: type) -> None:
    assert _feedback_literals(model, "feedback") == {FEEDBACK_UP, FEEDBACK_DOWN}


@pytest.mark.parametrize("value", [FEEDBACK_UP, FEEDBACK_DOWN, None])
def test_the_schema_accepts_both_thumbs_and_the_clear(value: int | None) -> None:
    assert LookUpdate(feedback=value).feedback == value


@pytest.mark.parametrize("value", [0, 2, -2])
def test_the_schema_refuses_a_value_the_column_would_refuse(value: int) -> None:
    # The same three the CHECK constraint rejects in `test_looks_rows.py`. Both
    # ends refuse them, which is the point: the schema answers 422 with a
    # message, and the column is what makes that a guarantee rather than a
    # convention.
    with pytest.raises(ValidationError):
        LookUpdate(feedback=value)

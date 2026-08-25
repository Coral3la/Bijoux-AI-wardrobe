"""The committed seed table, checked without a database.

`scripts/seed_demo.py` refuses to insert a row the vocabulary would not accept,
which is only worth anything if the refusal is exercised. Two halves here and
they defend different things: the first walks the real table, so an `enums.py`
tightening that invalidates a committed row turns this suite red rather than
turning up at a defence; the second feeds `_problems` rows it must reject, so
that narrowing it to `report.ok` — which would let every coercion through — is
caught. `DECISIONS.md` 130.
"""

from typing import Any

import pytest

from app.core.security import MAX_PASSWORD_BYTES, hash_password
from app.enums import ItemStatus
from app.schemas.auth import MIN_PASSWORD_LENGTH
from scripts.seed_demo import (
    DEMO_PASSWORD,
    FAILURE_ITEMS,
    SEED_ITEMS,
    SeedItem,
    _problems,
)

# A row every field of which is deliberately unremarkable, so that a test below
# is about the one value it changes and nothing else.
VALID_TAGS: dict[str, Any] = {
    "category": "top",
    "subcategory": "shirt",
    "fit": "relaxed",
    "length": "long_sleeve",
    "rise": None,
    "color_primary": "white",
    "color_secondary": None,
    "pattern": "solid",
    "material": "cotton",
    "formality": 3,
    "warmth": 2,
    "layer": "base",
    "water_resistant": False,
    "display_name": "white cotton shirt",
}


def _row(**overrides: Any) -> SeedItem:
    tags = {**VALID_TAGS, **overrides}
    return SeedItem(source="test.jpg", public_id="bijoux/test/x", tags=tags)


@pytest.mark.parametrize("item", SEED_ITEMS + FAILURE_ITEMS, ids=lambda i: i.source)
def test_every_committed_seed_row_is_insertable(item: SeedItem) -> None:
    assert _problems(item) == []


def test_the_valid_row_this_module_mutates_is_itself_valid() -> None:
    # Without this, every rejection test below could be passing because the base
    # row is broken rather than because the mutation was caught.
    assert _problems(_row()) == []


def test_a_value_outside_its_vocabulary_is_rejected() -> None:
    assert _problems(_row(color_primary="turquoise"))


def test_a_coercion_is_rejected_even_though_the_vision_path_accepts_one() -> None:
    # `fit: "flared"` is the real observation from task 1.1 that opened this.
    # `validate_tag_dict` reports it as a coercion and not an error, so a check
    # written as `report.ok` would insert this row with `fit` silently null.
    assert _problems(_row(fit="flared"))


def test_a_legal_value_beside_a_category_that_cannot_take_it_is_rejected() -> None:
    # 1.2a's rule, from the other end: `skinny` is a real `Fit` and means
    # nothing on a top, and this is the seed table's only defence against
    # writing the exact row `DECISIONS.md` 084 found in live output.
    assert _problems(_row(fit="skinny"))


def test_a_layer_a_top_cannot_have_is_rejected() -> None:
    assert _problems(_row(layer="outer"))


@pytest.mark.parametrize("missing", ["category", "material", "display_name", "water_resistant"])
def test_a_ready_row_missing_a_required_field_is_rejected(missing: str) -> None:
    assert _problems(_row(**{missing: None}))


def test_a_ready_row_may_not_carry_an_error_message() -> None:
    item = SeedItem(
        source="test.jpg",
        public_id="bijoux/test/x",
        tags=dict(VALID_TAGS),
        error_message="something",
    )
    assert _problems(item)


def test_a_failed_row_needs_an_error_message() -> None:
    item = SeedItem(source="test.jpg", public_id="bijoux/test/x", tags={}, status=ItemStatus.FAILED)
    assert _problems(item)


def test_a_failed_row_with_no_tags_at_all_is_otherwise_acceptable() -> None:
    # `validate_tag_dict` reads every field with `.get`, so `{}` is a clean
    # report — the property `DECISIONS.md` 086 found, relied on here rather
    # than worked around.
    item = SeedItem(
        source="test.jpg",
        public_id="bijoux/test/x",
        tags={},
        status=ItemStatus.FAILED,
        error_message="No usable answer arrived: timeout",
    )
    assert _problems(item) == []


def test_a_processing_row_is_never_seeded() -> None:
    # The startup sweep rewrites any `processing` row older than ten minutes,
    # so a seeded one changes status on its own between the seed and the demo.
    item = SeedItem(
        source="test.jpg",
        public_id="bijoux/test/x",
        tags=dict(VALID_TAGS),
        status=ItemStatus.PROCESSING,
    )
    assert _problems(item)


def test_the_demo_password_is_one_the_api_would_have_accepted() -> None:
    # It is published rather than secret, and it is never registered through
    # `POST /auth/register` — the script calls `hash_password` directly. This
    # keeps it inside the rules a user's own password has to satisfy, so the
    # documented credential cannot be one the register form would reject.
    assert len(DEMO_PASSWORD) >= MIN_PASSWORD_LENGTH
    assert len(DEMO_PASSWORD.encode("utf-8")) <= MAX_PASSWORD_BYTES
    assert hash_password(DEMO_PASSWORD)

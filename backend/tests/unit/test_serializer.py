"""The wardrobe serialiser, checked without a database and without AI.

Three dimensions, named by `06-TESTING-STRATEGY.md`: null handling, field order,
and the token budget. The first two are the reason the third is safe to state —
a format whose columns can shift is one whose token count means nothing.

Expected lines are **transcribed from `03-AI-CONTRACTS.md`**, never built from
`serializer.py`'s own constants. A derived expectation moves with the mutation
it is supposed to catch; `DECISIONS.md` 101 and the `RESULT_LIMIT` survivor at
2.2 are the two times this project learned that.
"""

import datetime
import itertools
import uuid
from typing import Any

import tiktoken

from app.core.config import settings
from app.core.short_id import generate_short_id
from app.schemas.item import ItemResponse
from app.services.serializer import serialize_wardrobe
from scripts.seed_demo import FAILURE_ITEMS, SEED_ITEMS

# Transcribed from `STAGE-2` 2.3: "150 items must serialise to under 6,000
# tokens". Both literals live here rather than in `serializer.py`, which has no
# opinion about how large a wardrobe is.
WARDROBE_SIZE = 150
BUDGET_TOKENS = 6_000

# Legal under `app/core/short_id.py`'s alphabet, and both are `03`'s own. Two of
# that document's other ids contained a `0` and a `1` when this file was written
# and could not have been generated, which is why only these two were borrowed;
# task 2.4 replaced them (`AUDITS.md` O-22) and all five are legal now.
TOP_ID = "A3F9K2"
JEANS_ID = "7BX1QM"

_EPOCH = datetime.datetime(2026, 8, 26, tzinfo=datetime.UTC)


def _item(**tags: Any) -> ItemResponse:
    """One `ItemResponse` with every column the serialiser never reads set to a
    fixed value, so a test says only what it is about."""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "short_id": generate_short_id(),
        "status": "ready",
        "image_public_id": "bijoux/demo/photograph",
        "category": None,
        "subcategory": None,
        "fit": None,
        "length": None,
        "rise": None,
        "color_primary": None,
        "color_secondary": None,
        "pattern": None,
        "material": None,
        "formality": None,
        "warmth": None,
        "layer": None,
        "water_resistant": False,
        "display_name": None,
        "attributes": {},
        "ai_confidence": None,
        "user_edited": False,
        "error_message": None,
        # Added at 3.4 with the two columns' first appearance on the wire. Both
        # are required rather than defaulted, so this fixture failed to build
        # until they were written here — the collection error that named all
        # three copies of this dict at once.
        "wear_count": 0,
        "last_worn_at": None,
        "is_archived": False,
        "created_at": _EPOCH,
        "updated_at": _EPOCH,
    }
    fields.update(tags)
    return ItemResponse(**fields)


def _shirt(**overrides: Any) -> ItemResponse:
    tags: dict[str, Any] = {
        "short_id": TOP_ID,
        "category": "top",
        "subcategory": "shirt",
        "fit": "oversized",
        "length": "long_sleeve",
        "color_primary": "white",
        "pattern": "solid",
        "material": "cotton",
        "formality": 3,
        "warmth": 2,
        "layer": "base",
    }
    tags.update(overrides)
    return _item(**tags)


def _slots(line: str) -> list[str]:
    return line.split(" | ")


# --- the documented format ------------------------------------------------


def test_a_fully_tagged_item_serialises_to_the_documented_line():
    assert serialize_wardrobe([_shirt()]) == (
        "A3F9K2 | top/shirt | oversized | long_sleeve | white | — | solid | cotton | F3 W2 | base"
    )


def test_a_bottom_carries_its_rise_as_a_trailing_extra():
    jeans = _item(
        short_id=JEANS_ID,
        category="bottom",
        subcategory="jeans",
        fit="straight",
        length="full",
        rise="high",
        color_primary="light_blue",
        pattern="denim_wash",
        material="denim",
        formality=2,
        warmth=2,
        layer="base",
    )
    assert serialize_wardrobe([jeans]) == (
        "7BX1QM | bottom/jeans | straight | full | light_blue | — | denim_wash | denim "
        "| F2 W2 | base | rise:high"
    )


def test_the_slots_are_in_the_documented_order():
    line = serialize_wardrobe([_shirt(color_secondary="grey")])
    assert _slots(line) == [
        "A3F9K2",
        "top/shirt",
        "oversized",
        "long_sleeve",
        "white",
        "grey",
        "solid",
        "cotton",
        "F3 W2",
        "base",
    ]


# --- nulls keep their column ----------------------------------------------


def test_a_null_core_field_becomes_a_placeholder_rather_than_disappearing():
    shoes = _item(
        category="shoes",
        subcategory="boots",
        length="ankle",
        color_primary="black",
        pattern="solid",
        material="leather",
        formality=3,
        warmth=4,
        layer="standalone",
    )
    slots = _slots(serialize_wardrobe([shoes]))
    assert slots[2] == "—"
    assert slots[3] == "ankle"


def test_every_core_slot_holds_its_column_across_a_mixed_wardrobe():
    wardrobe = [
        _shirt(),
        _item(category="shoes", subcategory="sandals", color_primary="brown"),
        _item(category="bag", subcategory="tote", color_primary="black"),
    ]
    for line in serialize_wardrobe(wardrobe).splitlines():
        assert len(_slots(line)) >= 10
        assert _slots(line)[8].startswith("F")


def test_an_item_with_no_tags_at_all_serialises_rather_than_raising():
    slots = _slots(serialize_wardrobe([_item()]))
    assert slots[1] == "—/—"
    assert slots[8] == "F— W—"


# --- the secondary colour, added at 2.3 ------------------------------------


def test_a_secondary_colour_occupies_its_own_slot_after_the_primary():
    line = serialize_wardrobe([_shirt(color_primary="beige", color_secondary="brown")])
    assert " | beige | brown | " in line


def test_a_missing_secondary_colour_is_a_placeholder_not_an_omission():
    assert " | white | — | solid | " in serialize_wardrobe([_shirt()])


# --- trailing extras -------------------------------------------------------


def test_water_resistant_is_appended_only_when_true():
    assert serialize_wardrobe([_shirt()]).endswith("base")
    assert serialize_wardrobe([_shirt(water_resistant=True)]).endswith("base | water_resistant")


def test_both_extras_appear_with_rise_first():
    line = serialize_wardrobe([_shirt(rise="high", water_resistant=True)])
    assert line.endswith("base | rise:high | water_resistant")


# --- the shape of the whole document ---------------------------------------


def test_one_line_per_item():
    wardrobe = [_shirt() for _ in range(7)]
    assert len(serialize_wardrobe(wardrobe).splitlines()) == 7


def test_an_empty_wardrobe_is_an_empty_string():
    assert serialize_wardrobe([]) == ""


def test_the_serialiser_applies_no_filter_of_its_own():
    """`ready`-only and `is_archived` belong to the caller at 2.7. A serialiser
    that dropped rows would make the count in `WARDROBE ({n} items)` a lie."""
    wardrobe = [
        _shirt(status="processing"),
        _shirt(is_archived=True),
        _shirt(status="failed", error_message="no usable answer"),
    ]
    assert len(serialize_wardrobe(wardrobe).splitlines()) == 3


# --- the token budget ------------------------------------------------------


def _seed_wardrobe(size: int) -> list[ItemResponse]:
    """The real committed wardrobe, cycled up to `size`, with a fresh id on each
    row. Measuring synthetic items would measure the fixture; measuring repeated
    ids would understate the cost, because a random six-character id is the most
    expensive thing on the line."""
    rows = itertools.islice(itertools.cycle(SEED_ITEMS), size)
    return [_item(**seed.tags, short_id=generate_short_id()) for seed in rows]


def test_a_150_item_wardrobe_stays_under_the_token_budget():
    encoding = tiktoken.encoding_for_model(settings.OPENAI_STYLIST_MODEL)
    text = serialize_wardrobe(_seed_wardrobe(WARDROBE_SIZE))
    assert len(encoding.encode(text)) < BUDGET_TOKENS


def test_the_failed_seed_rows_serialise_too():
    assert len(serialize_wardrobe([_item(**f.tags) for f in FAILURE_ITEMS]).splitlines()) == 2

"""`validate_look_response` — `03-AI-CONTRACTS.md`'s validation table.

No AI call and no database: the function takes an answer, a wardrobe and a
context, and returns a verdict. That is the whole point of the split — the
retry, the give-up and `502 stylist_failed` are 2.7's, so every rule here is
testable against a hand-built `StylistResponse`.

Five rules run, not `03`'s eight. Rule 5 reads `packing_list.item_ids` and
`STYLIST_SCHEMA` carries no `packing_list` until Stage 4 (`DECISIONS.md` 157);
rules 7 and 8 arrive with the anchor at 2.10 and the swap at 2.11.

Violation text is asserted by the fragment a reader would recognise rather than
by whole sentence, because the sentence is prompt text sent to the model and
`_CORRECTION` wraps it — what a test should pin is which rule fired.
"""

import datetime
import uuid
from typing import Any

import pytest

from app.schemas.item import ItemResponse
from app.services import stylist

# `03-AI-CONTRACTS.md`'s worked ids, all legal under `app/core/short_id.py`.
TOP_ID = "A3F9K2"
JEANS_ID = "7BX1QM"
BOOTS_ID = "SEFA38"
BLAZER_ID = "EH8VVQ"
DRESS_ID = "ZR44QW"
COAT_ID = "MW23PD"
CARDIGAN_ID = "K9HTB4"

# Transcribed from `03-AI-CONTRACTS.md`'s rule table, both bands.
MILD_RULE = "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional."
COLD_RULE = "Outerwear is REQUIRED, warmth 3-4."

_EPOCH = datetime.datetime(2026, 8, 26, tzinfo=datetime.UTC)


def _item(short_id: str, **tags: Any) -> ItemResponse:
    """One `ItemResponse` with every column the validator never reads fixed, so
    a test says only what it is about."""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "short_id": short_id,
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
        "is_archived": False,
        "created_at": _EPOCH,
        "updated_at": _EPOCH,
    }
    return ItemResponse(**(fields | tags))


TOP = _item(TOP_ID, category="top", subcategory="shirt", layer="base")
JEANS = _item(JEANS_ID, category="bottom", subcategory="jeans", layer="base")
BOOTS = _item(BOOTS_ID, category="shoes", subcategory="boots", layer="standalone")
BLAZER = _item(BLAZER_ID, category="outerwear", subcategory="blazer", layer="outer")
DRESS = _item(DRESS_ID, category="dress", subcategory="dress", layer="standalone")
COAT = _item(COAT_ID, category="outerwear", subcategory="coat", layer="outer")
CARDIGAN = _item(CARDIGAN_ID, category="outerwear", subcategory="cardigan", layer="mid")

WARDROBE = [TOP, JEANS, BOOTS, BLAZER, DRESS, COAT, CARDIGAN]


def _context(**overrides: Any) -> stylist.StylistContext:
    fields: dict[str, Any] = {
        "date": datetime.date(2026, 3, 14),
        "occasion": "work",
        "forecast_summary": "18°C, no rain.",
        "weather_rule": MILD_RULE,
    }
    return stylist.StylistContext(**(fields | overrides))


def _look(*item_ids: str) -> stylist.Look:
    return stylist.Look(
        occasion="work",
        title="Morning meetings",
        item_ids=item_ids,
        reasoning="The straight jean balances the oversized shirt.",
        weather_note="18°C in the morning — the blazer is enough without a coat.",
    )


def _response(*looks: stylist.Look) -> stylist.StylistResponse:
    return stylist.StylistResponse(looks=looks, missing_pieces=(), message="One look.")


def _validate(response: stylist.StylistResponse, **context: Any) -> stylist.LookValidation:
    return stylist.validate_look_response(response, WARDROBE, _context(**context))


# --- a look that is fine ----------------------------------------------------


def test_a_complete_look_passes() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID)))

    assert result.ok
    assert result.violation is None


# --- rule 1, the hallucination guard ----------------------------------------


def test_an_id_that_is_in_no_wardrobe_row_is_rejected() -> None:
    # Not a case difference and not a near miss: `Q7WXYZ` is a legal short_id
    # that no row holds, which is what a hallucination looks like.
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID, "Q7WXYZ")))

    assert not result.ok
    assert "unknown item id Q7WXYZ" in str(result.violation)


def test_lower_case_ids_are_accepted_and_come_back_upper_case() -> None:
    # `DECISIONS.md` 156: the alphabet is upper-case only, so case is the one
    # difference between what a model sends and what a row holds that is not a
    # hallucination. 2.7 persists and hydrates from `result.response`.
    result = _validate(_response(_look(TOP_ID.lower(), JEANS_ID.lower(), BOOTS_ID.lower())))

    assert result.ok
    assert result.response.looks[0].item_ids == (TOP_ID, JEANS_ID, BOOTS_ID)


# --- rule 2, shoes and a covered body ---------------------------------------


def test_a_look_without_shoes_is_rejected() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID)))

    assert "no shoes" in str(result.violation)


def test_a_look_with_neither_a_pair_nor_a_dress_is_rejected() -> None:
    result = _validate(_response(_look(TOP_ID, BOOTS_ID)))

    assert "neither a top and a bottom nor a dress" in str(result.violation)


def test_a_dress_satisfies_the_pair() -> None:
    result = _validate(_response(_look(DRESS_ID, BOOTS_ID)))

    assert result.ok


# --- rule 3, one outer layer ------------------------------------------------


def test_two_outer_layer_items_are_rejected() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID, BLAZER_ID, COAT_ID)))

    assert "two outer layer items" in str(result.violation)


def test_a_mid_layer_under_an_outer_is_allowed() -> None:
    # The rule is by `layer`, not by category — the prompt says "Never place two
    # `outer` layer items", and `LAYERS_BY_CATEGORY` lets outerwear be `mid`.
    # A cardigan under a coat is two outerwear rows and one outer layer.
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID, CARDIGAN_ID, COAT_ID)))

    assert result.ok


# --- rule 4, one look for one day -------------------------------------------


def test_more_looks_than_days_are_rejected() -> None:
    complete = _look(TOP_ID, JEANS_ID, BOOTS_ID)
    result = _validate(_response(complete, complete))

    assert "you returned 2 looks and exactly 1 was requested" in str(result.violation)


# --- rule 6, the weather rule's outerwear -----------------------------------


def test_a_required_coat_that_is_absent_is_rejected() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID)), weather_rule=COLD_RULE)

    assert "requires outerwear and the look contains none" in str(result.violation)


def test_a_required_coat_that_is_present_passes() -> None:
    result = _validate(
        _response(_look(TOP_ID, JEANS_ID, BOOTS_ID, COAT_ID)), weather_rule=COLD_RULE
    )

    assert result.ok


def test_rule_six_does_not_run_when_the_user_asked_for_no_outerwear() -> None:
    # `DECISIONS.md` 158 gives an explicit `include_outerwear` precedence over
    # the weather rule, and the prompt says so in words. Enforcing rule 6 over
    # that look would spend the retry and then answer 502 to the one answer
    # that did what it was told.
    result = _validate(
        _response(_look(TOP_ID, JEANS_ID, BOOTS_ID)),
        weather_rule=COLD_RULE,
        include_outerwear=False,
    )

    assert result.ok


# --- the order the table prints ---------------------------------------------


def test_the_first_rule_in_order_is_the_one_reported() -> None:
    # This look breaks rule 1 and rule 2 at once — an unknown id, and no shoes.
    # Rule 1 is what makes every later rule able to look an id up at all, so it
    # is both the one reported and the reason the others cannot raise.
    result = _validate(_response(_look(TOP_ID, "Q7WXYZ")))

    assert "unknown item id" in str(result.violation)


def test_a_rejected_look_is_logged_with_the_first_violation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Asserted on the record attribute rather than on `caplog.text`, for
    # `test_weather.py`'s reason: `extra=` sets an attribute and only
    # `JsonFormatter` reads it back out, so a test written against the rendered
    # text would pass with the violation dropped from the log. The sentence is
    # transcribed rather than read off `result.violation`, which would be an
    # expectation that moves with the mutation it is meant to catch.
    with caplog.at_level("WARNING"):
        _validate(_response(_look(TOP_ID, JEANS_ID)))

    assert [record.violation for record in caplog.records] == ["the look has no shoes"]

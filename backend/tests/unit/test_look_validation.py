"""`validate_look_response` — `03-AI-CONTRACTS.md`'s validation table.

No AI call and no database: the function takes an answer, a wardrobe and a
context, and returns a verdict. That is the whole point of the split — the
retry, the give-up and `502 stylist_failed` are 2.7's, so every rule here is
testable against a hand-built `StylistResponse`.

Eight rules run, not `03`'s nine. Rule 5 reads `packing_list.item_ids` and
`STYLIST_SCHEMA` carries no `packing_list` until Stage 4 (`DECISIONS.md` 157);
rule 8 arrived with the swap at 2.11 and rule 9 at 2.11a.

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
# Rule 9's two, and they are a pair on purpose: a second top is legal as the
# `mid` layering piece and illegal as a second `base`.
TANK_ID = "TANK55"
OVERSHIRT_ID = "SHRT26"
# The pair rule 9 was widened for: a shoe-swap came back with long jeans and
# shorts in one look.
SHORTS_ID = "SHTS47"

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
TANK = _item(TANK_ID, category="top", subcategory="tank", layer="base")
OVERSHIRT = _item(OVERSHIRT_ID, category="top", subcategory="shirt", layer="mid")
SHORTS = _item(SHORTS_ID, category="bottom", subcategory="shorts", layer="base")

WARDROBE = [TOP, JEANS, BOOTS, BLAZER, DRESS, COAT, CARDIGAN, TANK, OVERSHIRT, SHORTS]


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


# --- rule 3, one outer layer — absorbed into rule 9's table at 2.11b --------


def test_two_outer_layer_items_are_rejected() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID, BLAZER_ID, COAT_ID)))

    assert "2 outer layer items and may contain at most 1" in str(result.violation)


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


# --- rule 7, the anchored item ----------------------------------------------


def test_an_anchor_that_is_absent_from_the_look_is_rejected() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID)), anchor_id=BLAZER_ID)

    assert not result.ok
    assert f"does not contain the anchored item {BLAZER_ID}" in str(result.violation)


def test_an_anchor_that_is_present_passes() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID, BLAZER_ID)), anchor_id=BLAZER_ID)

    assert result.ok


def test_the_anchor_is_matched_after_the_ids_are_upper_cased() -> None:
    # The anchor is a `short_id` off a row and is upper-case by construction;
    # the model's spelling is not. Rule 7 runs on the normalised look, so a
    # lower-case answer naming the anchored item is a pass and not a violation
    # about an item that is in fact there. `DECISIONS.md` 156.
    result = _validate(
        _response(_look(TOP_ID.lower(), JEANS_ID.lower(), BOOTS_ID.lower())), anchor_id=BOOTS_ID
    )

    assert result.ok


def test_no_anchor_means_rule_seven_does_not_run() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID)))

    assert result.ok


# --- rule 8, the locked items and the rejected one ---------------------------


def test_a_locked_item_that_is_absent_from_the_look_is_rejected() -> None:
    result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID)), locked_ids=(TOP_ID, BLAZER_ID))

    assert not result.ok
    assert f"does not contain the locked item {BLAZER_ID}" in str(result.violation)


def test_the_rejected_item_coming_back_is_rejected() -> None:
    result = _validate(
        _response(_look(TOP_ID, JEANS_ID, BOOTS_ID)),
        locked_ids=(TOP_ID, JEANS_ID),
        excluded_ids=(BOOTS_ID,),
    )

    assert not result.ok
    assert f"contains the rejected item {BOOTS_ID}" in str(result.violation)


def test_a_swap_that_kept_the_locks_and_dropped_the_rejected_item_passes() -> None:
    # The swap this endpoint exists for: the rejected blazer is gone, the three
    # locked garments are untouched, and the coat that replaced it is a row the
    # wardrobe holds. Rule 3 still runs over the answer — one outer, not two.
    result = _validate(
        _response(_look(TOP_ID, JEANS_ID, BOOTS_ID, COAT_ID)),
        locked_ids=(TOP_ID, JEANS_ID, BOOTS_ID),
        excluded_ids=(BLAZER_ID,),
        replace_role="outer",
    )

    assert result.ok


def test_the_locks_are_matched_after_the_ids_are_upper_cased() -> None:
    # Rule 7's reasoning on rule 8's field: locked ids are `short_id`s off rows
    # and upper-case by construction, the model's spelling is not, and rule 8
    # runs on the normalised look. `DECISIONS.md` 156.
    result = _validate(
        _response(_look(TOP_ID.lower(), JEANS_ID.lower(), BOOTS_ID.lower())),
        locked_ids=(TOP_ID, JEANS_ID),
        excluded_ids=(BLAZER_ID,),
    )

    assert result.ok


def test_an_exclusion_with_no_locks_does_not_run(caplog: pytest.LogCaptureFixture) -> None:
    # `03-AI-CONTRACTS.md` gates the whole of rule 8 on `locked_item_ids`: with
    # nothing locked the request asked for a reroll rather than a swap, and the
    # exclusion is a preference printed to the model rather than a promise
    # worth a retry and then a 502.
    with caplog.at_level("WARNING"):
        result = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID)), excluded_ids=(BOOTS_ID,))

    assert result.ok
    assert caplog.records == []


# --- rule 9, one item per slot ----------------------------------------------


def test_a_second_base_top_is_rejected_and_a_mid_layer_one_is_not() -> None:
    # Both columns, because neither says it alone: `top` would refuse the
    # overshirt the system prompt allows, and `base` would refuse the jeans in
    # every look here. One test rather than three, because the three readings
    # are one rule and the middle case is the whole of what it permits.
    two_base = _validate(_response(_look(TOP_ID, TANK_ID, JEANS_ID, BOOTS_ID)))

    assert not two_base.ok
    assert f"2 base-layer tops and may contain at most 1: {TOP_ID}, {TANK_ID}" in str(
        two_base.violation
    )

    layered = _validate(_response(_look(TOP_ID, OVERSHIRT_ID, JEANS_ID, BOOTS_ID)))
    assert layered.ok

    alone = _validate(_response(_look(TOP_ID, JEANS_ID, BOOTS_ID)))
    assert alone.ok


def test_two_bottoms_are_rejected() -> None:
    # The look that widened this rule at 2.11b: a shoe-swap answered with long
    # jeans and shorts, and every rule in the table passed it — rule 2 asks
    # whether a bottom is present, never how many.
    result = _validate(_response(_look(TOP_ID, JEANS_ID, SHORTS_ID, BOOTS_ID)))

    assert not result.ok
    assert f"2 bottoms and may contain at most 1: {JEANS_ID}, {SHORTS_ID}" in str(result.violation)


def test_a_dress_beside_a_separate_is_rejected() -> None:
    # Rule 2 passes this look twice over — it has a dress, and it has a top and
    # a bottom. What it cannot say is that the dress replaces them.
    result = _validate(_response(_look(DRESS_ID, JEANS_ID, BOOTS_ID)))

    assert not result.ok
    assert f"a dress and the separate item {JEANS_ID}" in str(result.violation)


def test_a_dress_under_an_outer_layer_is_still_allowed() -> None:
    # The exclusion is `top` and `bottom` alone. A coat over a dress is a
    # different slot and one of the commonest looks there is.
    result = _validate(_response(_look(DRESS_ID, BOOTS_ID, COAT_ID)))

    assert result.ok


def test_one_item_per_slot_passes() -> None:
    # Every slot this wardrobe can fill, filled once, plus the `mid` top the
    # base-top slot deliberately does not count — the widest legal look here.
    result = _validate(_response(_look(TOP_ID, OVERSHIRT_ID, JEANS_ID, BOOTS_ID, COAT_ID)))

    assert result.ok
    assert result.violation is None


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

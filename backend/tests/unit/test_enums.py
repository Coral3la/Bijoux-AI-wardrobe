"""The closed vocabulary. No database, no AI, no fixtures — this module imports
nothing but `app.enums`, which is the property that keeps it that way."""

from typing import Any

import pytest

from app.enums import (
    SUBCATEGORIES,
    Category,
    ColorPrimary,
    is_valid_subcategory,
    validate_tag_dict,
)


def tags(**overrides: Any) -> dict[str, Any]:
    """A valid white cotton shirt, overridden field by field."""
    base: dict[str, Any] = {
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
        "confidence": 0.92,
    }
    return base | overrides


def fields_in(issues: tuple[Any, ...]) -> set[str]:
    return {issue.field for issue in issues}


# --- the vocabularies themselves -------------------------------------------


def test_color_primary_values_are_the_documented_seventeen_in_order() -> None:
    assert ColorPrimary.values() == [
        "black",
        "white",
        "grey",
        "beige",
        "brown",
        "navy",
        "blue",
        "light_blue",
        "red",
        "pink",
        "orange",
        "yellow",
        "green",
        "olive",
        "purple",
        "gold",
        "silver",
    ]


def test_category_values_are_the_documented_seven_in_order() -> None:
    assert Category.values() == [
        "top",
        "bottom",
        "dress",
        "outerwear",
        "shoes",
        "bag",
        "accessory",
    ]


def test_values_returns_plain_strings_not_enum_members() -> None:
    assert all(type(value) is str for value in ColorPrimary.values())


def test_subcategories_resolves_the_same_entry_by_member_and_by_raw_string() -> None:
    assert SUBCATEGORIES[Category.TOP] is SUBCATEGORIES["top"]


def test_every_subcategories_key_is_a_category() -> None:
    assert all(category in Category.values() for category in SUBCATEGORIES)


# --- is_valid_subcategory ---------------------------------------------------


@pytest.mark.parametrize("category,subs", list(SUBCATEGORIES.items()))
def test_documented_subcategories_are_valid_for_their_category(
    category: Category, subs: tuple[str, ...]
) -> None:
    assert all(is_valid_subcategory(category, sub) for sub in subs)


@pytest.mark.parametrize("category,subs", list(SUBCATEGORIES.items()))
def test_subcategories_are_rejected_by_every_other_category(
    category: Category, subs: tuple[str, ...]
) -> None:
    others = [other for other in SUBCATEGORIES if other != category]
    assert not any(is_valid_subcategory(other, sub) for other in others for sub in subs)


def test_unknown_category_is_rejected_rather_than_raising() -> None:
    assert is_valid_subcategory("kaftan", "shirt") is False


# --- coercions --------------------------------------------------------------


def test_invalid_fit_is_coerced_to_null() -> None:
    result = validate_tag_dict(tags(fit="baggy"))
    assert result.ok
    assert result.tags["fit"] is None
    assert fields_in(result.coerced) == {"fit"}


def test_invalid_length_is_coerced_to_null() -> None:
    result = validate_tag_dict(tags(length="three_quarter"))
    assert result.ok
    assert result.tags["length"] is None
    assert fields_in(result.coerced) == {"length"}


def test_invalid_color_secondary_is_coerced_to_null() -> None:
    result = validate_tag_dict(tags(color_secondary="burgundy"))
    assert result.ok
    assert result.tags["color_secondary"] is None
    assert fields_in(result.coerced) == {"color_secondary"}


def test_rise_on_a_non_bottom_is_coerced_to_null() -> None:
    result = validate_tag_dict(tags(rise="high"))
    assert result.ok
    assert result.tags["rise"] is None
    assert fields_in(result.coerced) == {"rise"}


def test_invalid_rise_on_a_bottom_is_coerced_to_null() -> None:
    result = validate_tag_dict(tags(category="bottom", subcategory="jeans", rise="ultra_high"))
    assert result.ok
    assert result.tags["rise"] is None
    assert fields_in(result.coerced) == {"rise"}


def test_valid_rise_on_a_bottom_is_kept() -> None:
    result = validate_tag_dict(tags(category="bottom", subcategory="jeans", rise="high"))
    assert result.ok
    assert result.tags["rise"] == "high"
    assert result.coerced == ()


@pytest.mark.parametrize(
    "category,subcategory",
    [("dress", "dress"), ("shoes", "boots"), ("bag", "tote"), ("accessory", "belt")],
)
def test_standalone_categories_coerce_the_layer(category: str, subcategory: str) -> None:
    result = validate_tag_dict(tags(category=category, subcategory=subcategory, layer="base"))
    assert result.ok
    assert result.tags["layer"] == "standalone"
    assert fields_in(result.coerced) == {"layer"}


def test_outerwear_with_a_base_layer_is_coerced_to_outer() -> None:
    result = validate_tag_dict(tags(category="outerwear", subcategory="blazer", layer="base"))
    assert result.ok
    assert result.tags["layer"] == "outer"
    assert fields_in(result.coerced) == {"layer"}


@pytest.mark.parametrize("layer", ["mid", "outer"])
def test_outerwear_keeps_a_layer_the_rule_already_permits(layer: str) -> None:
    result = validate_tag_dict(tags(category="outerwear", subcategory="cardigan", layer=layer))
    assert result.ok
    assert result.tags["layer"] == layer
    assert result.coerced == ()


def test_an_invalid_layer_is_an_error_and_is_not_also_coerced() -> None:
    result = validate_tag_dict(tags(category="shoes", subcategory="boots", layer="underlayer"))
    assert fields_in(result.errors) == {"layer"}
    assert result.coerced == ()


# --- errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("category", "kaftan"),
        ("color_primary", "burgundy"),
        ("pattern", "paisley"),
        ("material", "bamboo"),
        ("layer", "underlayer"),
    ],
)
def test_a_value_outside_a_strict_vocabulary_is_an_error(field: str, value: str) -> None:
    result = validate_tag_dict(tags(**{field: value}))
    assert not result.ok
    assert field in fields_in(result.errors)


def test_subcategory_from_the_wrong_category_is_an_error() -> None:
    result = validate_tag_dict(tags(category="top", subcategory="blazer"))
    assert fields_in(result.errors) == {"subcategory"}


def test_subcategory_without_a_category_is_an_error() -> None:
    result = validate_tag_dict({"subcategory": "shirt"})
    assert fields_in(result.errors) == {"subcategory"}


def test_rise_without_a_category_is_an_error() -> None:
    result = validate_tag_dict({"rise": "high"})
    assert fields_in(result.errors) == {"rise"}


@pytest.mark.parametrize("field", ["formality", "warmth"])
@pytest.mark.parametrize("value", [0, 6, 2.5, "3"])
def test_formality_and_warmth_reject_anything_outside_one_to_five(field: str, value: Any) -> None:
    result = validate_tag_dict(tags(**{field: value}))
    assert fields_in(result.errors) == {field}


@pytest.mark.parametrize("field", ["formality", "warmth"])
def test_true_is_not_an_integer_for_formality_or_warmth(field: str) -> None:
    result = validate_tag_dict(tags(**{field: True}))
    assert fields_in(result.errors) == {field}


@pytest.mark.parametrize("value", [1, 5])
def test_formality_and_warmth_accept_both_bounds(value: int) -> None:
    result = validate_tag_dict(tags(formality=value, warmth=value))
    assert result.ok


def test_water_resistant_must_be_a_boolean() -> None:
    result = validate_tag_dict(tags(water_resistant="yes"))
    assert fields_in(result.errors) == {"water_resistant"}


def test_display_name_must_be_a_string() -> None:
    result = validate_tag_dict(tags(display_name=42))
    assert fields_in(result.errors) == {"display_name"}


@pytest.mark.parametrize("value", [-0.1, 1.1, "high", True])
def test_confidence_outside_zero_to_one_is_an_error(value: Any) -> None:
    result = validate_tag_dict(tags(confidence=value))
    assert fields_in(result.errors) == {"confidence"}


@pytest.mark.parametrize("value", [0.0, 1.0, 0.34])
def test_confidence_inside_the_range_is_accepted_at_any_value(value: float) -> None:
    result = validate_tag_dict(tags(confidence=value))
    assert result.ok


# --- the report -------------------------------------------------------------


def test_reason_names_every_error_for_the_retry_prompt() -> None:
    result = validate_tag_dict(tags(color_primary="burgundy", material="bamboo"))
    assert not result.ok
    assert len(result.errors) == 2
    assert "burgundy" in result.reason
    assert "bamboo" in result.reason


def test_a_valid_tag_dict_passes_through_untouched() -> None:
    original = tags()
    result = validate_tag_dict(original)
    assert result.ok
    assert result.coerced == ()
    assert result.tags == original


def test_an_absent_key_is_never_invented() -> None:
    result = validate_tag_dict({"category": "shoes"})
    assert result.ok
    assert result.tags == {"category": "shoes"}


def test_the_caller_s_mapping_is_not_mutated() -> None:
    original = tags(fit="baggy")
    validate_tag_dict(original)
    assert original["fit"] == "baggy"

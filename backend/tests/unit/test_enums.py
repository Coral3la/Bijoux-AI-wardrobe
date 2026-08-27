"""The closed vocabulary. No database, no AI, no fixtures — this module imports
nothing but `app.enums`, which is the property that keeps it that way."""

from typing import Any

import pytest

from app.enums import (
    CATEGORY_DEPENDENT_FIELDS,
    FIELD_APPLIES_TO,
    LAYERS_BY_CATEGORY,
    SUBCATEGORIES,
    VALUE_APPLIES_TO,
    Category,
    ColorPrimary,
    Fit,
    Layer,
    LayerRule,
    Length,
    Occasion,
    Vocabulary,
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


def reasons_in(issues: tuple[Any, ...]) -> list[str]:
    return [issue.reason for issue in issues]


def bare(category: str, **overrides: Any) -> dict[str, Any]:
    """A category, its first legal subcategory, and nothing else but the overrides.

    Deliberately minimal, where `tags()` above is deliberately complete. An absent
    key is never invented, so a rule under test cannot be disturbed by an
    attribute the category cannot have — which is exactly what went wrong with
    `tags()` when the category-dependent rules landed: it built a shirt, and the
    multi-category tests were asserting against a tote bag with long sleeves.
    """
    return {"category": category, "subcategory": SUBCATEGORIES[Category(category)][0], **overrides}


_GARMENTS = (
    Category.TOP,
    Category.BOTTOM,
    Category.DRESS,
    Category.OUTERWEAR,
    Category.SWIMWEAR,
    Category.SLEEPWEAR,
)
_CARRIED = (Category.SHOES, Category.BAG, Category.ACCESSORY)


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


def test_category_values_are_the_documented_nine_in_order() -> None:
    # Order is not cosmetic: `0003` appended swimwear and sleepwear to the
    # `item_category` type, and this list is what keeps the two in step.
    assert Category.values() == [
        "top",
        "bottom",
        "dress",
        "outerwear",
        "shoes",
        "bag",
        "accessory",
        "swimwear",
        "sleepwear",
    ]


def test_occasion_values_are_the_documented_six_in_order() -> None:
    # Transcribed from 02-DATA-MODEL.md, which took them from 04-API-SPEC.md at
    # task 2.7. Nothing in the database enforces this list — `looks.occasion` is
    # TEXT — so this test and `LookSuggestRequest` are the whole of it.
    assert Occasion.values() == ["casual", "work", "evening", "sport", "formal", "travel"]


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
    # length is overridden because the base helper is a shirt: `long_sleeve` on a
    # pair of jeans is now a coercion of its own and not this test's subject.
    result = validate_tag_dict(
        tags(category="bottom", subcategory="jeans", rise="ultra_high", length="full")
    )
    assert result.ok
    assert result.tags["rise"] is None
    assert fields_in(result.coerced) == {"rise"}


def test_valid_rise_on_a_bottom_is_kept() -> None:
    result = validate_tag_dict(
        tags(category="bottom", subcategory="jeans", rise="high", length="full")
    )
    assert result.ok
    assert result.tags["rise"] == "high"
    assert result.coerced == ()


@pytest.mark.parametrize(
    "category,subcategory",
    [("dress", "dress"), ("shoes", "boots"), ("bag", "tote"), ("accessory", "belt")],
)
def test_standalone_categories_coerce_the_layer(category: str, subcategory: str) -> None:
    # fit and length are nulled because a bag has neither, and carrying the base
    # helper's shirt attributes into one is what made this test fail when the
    # category-dependent rules landed. The subject here is `layer` alone.
    result = validate_tag_dict(
        tags(category=category, subcategory=subcategory, layer="base", fit=None, length=None)
    )
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
    result = validate_tag_dict(
        tags(category="shoes", subcategory="boots", layer="underlayer", fit=None, length=None)
    )
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


# --- the tables, pinned literally -------------------------------------------
#
# Every behavioural test below derives what it expects from these tables, which
# means a mutation *to a table* would leave all of them green: the expectation
# moves with the rule. These are the tests that fail instead. `02-DATA-MODEL.md`
# is authoritative for all four and is what they are transcribed from.


def test_fit_applies_to_the_six_garment_categories() -> None:
    assert FIELD_APPLIES_TO["fit"] == frozenset(
        {
            Category.TOP,
            Category.BOTTOM,
            Category.DRESS,
            Category.OUTERWEAR,
            Category.SWIMWEAR,
            Category.SLEEPWEAR,
        }
    )


def test_length_applies_to_everything_except_bags_and_accessories() -> None:
    assert FIELD_APPLIES_TO["length"] == frozenset(Category) - {Category.BAG, Category.ACCESSORY}


def test_rise_applies_to_bottoms_only() -> None:
    assert FIELD_APPLIES_TO["rise"] == frozenset({Category.BOTTOM})


def test_the_narrowed_fit_words_are_the_three_agreed_at_1_2a() -> None:
    assert VALUE_APPLIES_TO["fit"] == {
        Fit.SKINNY: frozenset({Category.BOTTOM}),
        Fit.WIDE: frozenset({Category.BOTTOM, Category.DRESS}),
        Fit.BODYCON: frozenset({Category.TOP, Category.BOTTOM, Category.DRESS}),
    }


def test_the_narrowed_lengths_are_the_sleeve_words_and_the_hem_words() -> None:
    sleeved = frozenset(
        {Category.TOP, Category.DRESS, Category.OUTERWEAR, Category.SWIMWEAR, Category.SLEEPWEAR}
    )
    hemmed = frozenset(
        {Category.BOTTOM, Category.DRESS, Category.OUTERWEAR, Category.SWIMWEAR, Category.SLEEPWEAR}
    )
    assert VALUE_APPLIES_TO["length"] == {
        Length.SLEEVELESS: sleeved,
        Length.SHORT_SLEEVE: sleeved,
        Length.LONG_SLEEVE: sleeved,
        Length.MINI: hemmed,
        Length.MIDI: hemmed,
        Length.MAXI: hemmed,
    }


def test_the_middle_of_the_length_list_is_left_unenforced() -> None:
    # The five words that describe more than one axis: cropped trousers and a
    # cropped top, ankle boots and ankle trousers. A rule over them would coerce
    # correct answers away, which is where 029's cost argument still holds.
    assert set(VALUE_APPLIES_TO["length"]).isdisjoint(
        {Length.CROP, Length.REGULAR, Length.LONGLINE, Length.ANKLE, Length.FULL}
    )


def test_the_layer_table_is_the_one_in_the_data_model() -> None:
    standalone = LayerRule(admits=frozenset({Layer.STANDALONE}), answer=Layer.STANDALONE)
    expected = {
        Category.TOP: LayerRule(admits=frozenset({Layer.BASE, Layer.MID}), answer=None),
        Category.BOTTOM: LayerRule(admits=frozenset({Layer.BASE}), answer=Layer.BASE),
        Category.DRESS: standalone,
        Category.OUTERWEAR: LayerRule(
            admits=frozenset({Layer.MID, Layer.OUTER}), answer=Layer.OUTER
        ),
        Category.SHOES: standalone,
        Category.BAG: standalone,
        Category.ACCESSORY: standalone,
        Category.SWIMWEAR: standalone,
        Category.SLEEPWEAR: standalone,
    }

    # dict() rather than the bare name so that the table stays on the left: ruff's
    # SIM300 reads an upper-case name as a constant and would have this flipped,
    # and pytest labels the left side as the actual in the diff this test exists
    # to produce under mutation.
    assert dict(LAYERS_BY_CATEGORY) == expected


def test_category_dependent_fields_is_every_field_with_a_category_rule() -> None:
    # `PATCH /items/{id}` clears exactly this list when the category changes (030),
    # so a field that gains a rule here and not there is silent data loss.
    assert set(CATEGORY_DEPENDENT_FIELDS) == {"subcategory", "layer"} | set(FIELD_APPLIES_TO)


# --- the tables' own invariants ----------------------------------------------


def test_the_layer_table_covers_every_category() -> None:
    # validate_tag_dict indexes this with every category it accepts, so a missing
    # row is a KeyError on real model output rather than a rule that is merely lax.
    assert set(LAYERS_BY_CATEGORY) == set(Category)


def test_every_layer_answer_is_admitted_by_its_own_rule() -> None:
    # An answer its own rule refuses would coerce a value into one the same rule
    # rejects, and nothing runs twice to notice.
    for category, rule in LAYERS_BY_CATEGORY.items():
        assert rule.answer is None or rule.answer in rule.admits, category


def test_top_is_the_only_category_with_no_layer_answer() -> None:
    # 082's question, pinned as an answer: base and mid are both legitimate for a
    # top, so the vocabulary refuses rather than guessing. Every other category
    # names one, which is why every other category coerces instead of erroring.
    assert {c for c, rule in LAYERS_BY_CATEGORY.items() if rule.answer is None} == {Category.TOP}


@pytest.mark.parametrize("field,vocabulary", [("fit", Fit), ("length", Length)])
def test_narrowed_values_are_members_of_their_own_vocabulary(
    field: str, vocabulary: type[Vocabulary]
) -> None:
    # A typo would be silent in both directions: an unreachable key narrows
    # nothing, and the value it was meant to narrow stays unconstrained.
    assert set(VALUE_APPLIES_TO[field]) <= set(vocabulary.values())


def test_a_narrowed_value_never_applies_where_its_field_does_not() -> None:
    for field, values in VALUE_APPLIES_TO.items():
        for value, categories in values.items():
            assert categories <= FIELD_APPLIES_TO[field], (field, value)


# --- fit, both directions, per category -------------------------------------


@pytest.mark.parametrize("category", _CARRIED)
def test_fit_is_nulled_on_a_category_with_no_silhouette(category: Category) -> None:
    result = validate_tag_dict(bare(category, fit="oversized"))

    assert result.ok
    assert result.tags["fit"] is None
    assert fields_in(result.coerced) == {"fit"}


@pytest.mark.parametrize("category", _GARMENTS)
def test_an_unnarrowed_fit_survives_on_every_garment_category(category: Category) -> None:
    result = validate_tag_dict(bare(category, fit="relaxed"))

    assert result.ok
    assert result.tags["fit"] == "relaxed"
    assert result.coerced == ()


@pytest.mark.parametrize("value", sorted(VALUE_APPLIES_TO["fit"]))
@pytest.mark.parametrize("category", _GARMENTS)
def test_a_narrowed_fit_survives_exactly_where_the_table_says(
    category: Category, value: str
) -> None:
    kept = category in VALUE_APPLIES_TO["fit"][value]
    result = validate_tag_dict(bare(category, fit=value))

    assert result.ok
    assert (result.tags["fit"] == value) is kept
    assert (result.coerced == ()) is kept


# --- length, both directions, per category ----------------------------------


@pytest.mark.parametrize("category", (Category.BAG, Category.ACCESSORY))
def test_length_is_nulled_on_a_category_that_has_no_length(category: Category) -> None:
    result = validate_tag_dict(bare(category, length="regular"))

    assert result.ok
    assert result.tags["length"] is None
    assert fields_in(result.coerced) == {"length"}


@pytest.mark.parametrize("value", ["crop", "regular", "longline", "ankle", "full"])
@pytest.mark.parametrize("category", sorted(FIELD_APPLIES_TO["length"]))
def test_an_unnarrowed_length_survives_wherever_the_field_applies(
    category: Category, value: str
) -> None:
    result = validate_tag_dict(bare(category, length=value))

    assert result.ok
    assert result.tags["length"] == value
    assert result.coerced == ()


@pytest.mark.parametrize("value", sorted(VALUE_APPLIES_TO["length"]))
@pytest.mark.parametrize("category", sorted(FIELD_APPLIES_TO["length"]))
def test_a_narrowed_length_survives_exactly_where_the_table_says(
    category: Category, value: str
) -> None:
    kept = category in VALUE_APPLIES_TO["length"][value]
    result = validate_tag_dict(bare(category, length=value))

    assert result.ok
    assert (result.tags["length"] == value) is kept
    assert (result.coerced == ()) is kept


def test_maxi_on_a_t_shirt_no_longer_validates() -> None:
    # 029's own example, which that entry accepted on the premise that the axes do
    # not collide in practice. `skinny` on a tank falsified the premise at 1.1.
    result = validate_tag_dict({"category": "top", "subcategory": "t_shirt", "length": "maxi"})

    assert result.ok
    assert result.tags["length"] is None
    assert fields_in(result.coerced) == {"length"}


def test_maxi_on_a_coat_still_validates() -> None:
    # Which is why outerwear is in the hem set: a maxi coat is a real garment, and
    # nulling it would be the false coercion the narrow tables exist to avoid.
    result = validate_tag_dict({"category": "outerwear", "subcategory": "coat", "length": "maxi"})

    assert result.ok
    assert result.tags["length"] == "maxi"
    assert result.coerced == ()


# --- layer, both directions, per category -----------------------------------

_ADMITTED_LAYERS = [
    (category, layer)
    for category, rule in LAYERS_BY_CATEGORY.items()
    for layer in sorted(rule.admits)
]
_REFUSED_LAYERS = [
    (category, layer)
    for category, rule in LAYERS_BY_CATEGORY.items()
    for layer in sorted(set(Layer) - rule.admits)
]


@pytest.mark.parametrize("category,layer", _ADMITTED_LAYERS)
def test_a_category_keeps_a_layer_it_admits(category: Category, layer: Layer) -> None:
    result = validate_tag_dict(bare(category, layer=layer))

    assert result.ok
    assert result.tags["layer"] == layer
    assert result.coerced == ()


@pytest.mark.parametrize(
    "category,layer",
    [pair for pair in _REFUSED_LAYERS if LAYERS_BY_CATEGORY[pair[0]].answer is not None],
)
def test_a_category_with_an_answer_coerces_a_layer_it_refuses(
    category: Category, layer: Layer
) -> None:
    result = validate_tag_dict(bare(category, layer=layer))

    assert result.ok
    assert result.tags["layer"] == LAYERS_BY_CATEGORY[category].answer
    assert fields_in(result.coerced) == {"layer"}


@pytest.mark.parametrize("layer", [Layer.OUTER, Layer.STANDALONE])
def test_a_top_refusing_a_layer_is_an_error_and_the_value_is_left_alone(layer: Layer) -> None:
    # The two layers stated rather than derived from the table. Deriving them
    # indexes LAYERS_BY_CATEGORY at import, so dropping the `top` row turned this
    # module into a collection error under mutation — the suite refusing to run
    # instead of a named test failing, which is a weaker thing to have measured.
    # The whole content of 082's fix: no answer exists, so none is substituted.
    # 1.2b retries on this; `PATCH /items/{id}` returns 422 naming the field.
    result = validate_tag_dict(bare("top", layer=layer))

    assert fields_in(result.errors) == {"layer"}
    assert result.coerced == ()
    assert result.tags["layer"] == layer


def test_the_layer_error_names_what_the_category_takes() -> None:
    # 1.2b puts `reason` into the retry prompt, so naming the admitted values is
    # the difference between a retry that can succeed and one that guesses again.
    result = validate_tag_dict(bare("top", layer="standalone"))

    assert result.reason == (
        "layer 'standalone' is not valid for category 'top', which takes base or mid"
    )


def test_the_layer_coercion_names_the_answer_it_used() -> None:
    result = validate_tag_dict(bare("outerwear", layer="base"))

    assert reasons_in(result.coerced) == [
        "category 'outerwear' takes layer mid or outer, set to outer"
    ]


# --- which sentence each rise case produces ---------------------------------
#
# Membership now runs before applicability, so an unknown value beside a
# non-bottom is reported as unknown rather than as inapplicable. Both null the
# field, so no earlier test could tell them apart — and 1.2b turns both into
# retry text, which makes the wording contract rather than cosmetics.


def test_an_invalid_rise_beside_a_non_bottom_reports_membership() -> None:
    result = validate_tag_dict(bare("top", rise="ultra_high"))

    assert reasons_in(result.coerced) == [
        "rise 'ultra_high' is not in the closed vocabulary, set to null"
    ]


def test_a_valid_rise_beside_a_non_bottom_reports_applicability() -> None:
    result = validate_tag_dict(bare("top", rise="high"))

    assert reasons_in(result.coerced) == ["rise does not apply to category 'top', set to null"]


# --- no category, and a category outside the vocabulary ---------------------


@pytest.mark.parametrize("field,value", [("fit", "slim"), ("length", "regular"), ("layer", "base")])
def test_a_category_dependent_field_without_a_category_is_an_error(field: str, value: str) -> None:
    result = validate_tag_dict({field: value})

    assert fields_in(result.errors) == {field}
    assert result.coerced == ()


def test_no_category_dependent_rule_fires_on_an_unrecognised_category() -> None:
    # The category is the one fault. Every rule below it is keyed by the category,
    # so there is nothing to look up — and reporting four consequences of one
    # fault would bury it in the retry text 1.2b builds from `reason`.
    raw = {
        "category": "kaftan",
        "fit": "skinny",
        "length": "maxi",
        "rise": "high",
        "layer": "standalone",
    }
    result = validate_tag_dict(raw)

    assert fields_in(result.errors) == {"category"}
    assert result.coerced == ()
    assert result.tags == raw


# --- the eight responses task 1.1 actually observed -------------------------
#
# Each row carries only the fields `STAGE-1` 1.11 recorded — category,
# subcategory, fit — because an absent key is never invented, so nothing here is
# filled in to make a point. Two of the eight were wrong and both are now caught,
# by two different mechanisms; the other six must stay untouched.

_OBSERVED_WRONG = [
    # A value in no vocabulary at all: caught by membership, which already worked.
    ({"category": "bottom", "subcategory": "jeans", "fit": "flared"}, "fit"),
    # A legal member beside a category it cannot describe: 084's gap, closed here.
    ({"category": "top", "subcategory": "tank", "fit": "skinny"}, "fit"),
]

_OBSERVED_RIGHT = [
    {"category": "top", "subcategory": "tank", "fit": None},
    {"category": "top", "subcategory": "bodysuit", "fit": "bodycon"},
    {"category": "bottom", "subcategory": "jeans", "fit": "wide"},
    {"category": "shoes", "subcategory": "heels", "fit": None},
    {"category": "outerwear", "subcategory": "jacket", "fit": None, "length": "regular"},
]


@pytest.mark.parametrize("raw,field", _OBSERVED_WRONG)
def test_a_wrong_answer_observed_at_task_1_1_is_now_caught(raw: dict[str, Any], field: str) -> None:
    result = validate_tag_dict(raw)

    assert result.tags[field] is None
    assert fields_in(result.coerced) == {field}


@pytest.mark.parametrize("raw", _OBSERVED_RIGHT)
def test_a_right_answer_observed_at_task_1_1_is_left_untouched(raw: dict[str, Any]) -> None:
    # `bodycon` on a bodysuit and `wide` on jeans are the two that matter: the
    # narrow tables must not reach them, or they cost more than they catch.
    result = validate_tag_dict(raw)

    assert result.ok
    assert result.coerced == ()
    assert result.tags == raw

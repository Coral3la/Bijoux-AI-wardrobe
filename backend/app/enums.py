"""The closed vocabulary.

Mirrors `docs/02-DATA-MODEL.md`, which is authoritative. Add a value there
first. The frontend copy is `frontend/src/app/shared/models/enums.ts`, and it
mirrors the *values* only — the category-dependent rules below live here alone.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Vocabulary(StrEnum):
    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class ItemStatus(Vocabulary):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Category(Vocabulary):
    TOP = "top"
    BOTTOM = "bottom"
    DRESS = "dress"
    OUTERWEAR = "outerwear"
    SHOES = "shoes"
    BAG = "bag"
    ACCESSORY = "accessory"
    # Appended rather than grouped with the garments, so this list and the
    # `item_category` type's sort order stay identical: migration `0003` adds
    # them with `ALTER TYPE … ADD VALUE`, which appends. Declaration order is
    # also what `_categories()` renders the vision prompt from.
    SWIMWEAR = "swimwear"
    SLEEPWEAR = "sleepwear"


class Layer(Vocabulary):
    BASE = "base"
    MID = "mid"
    OUTER = "outer"
    STANDALONE = "standalone"


class Fit(Vocabulary):
    SKINNY = "skinny"
    SLIM = "slim"
    STRAIGHT = "straight"
    RELAXED = "relaxed"
    OVERSIZED = "oversized"
    WIDE = "wide"
    BODYCON = "bodycon"
    A_LINE = "a_line"
    FLOWY = "flowy"


class Length(Vocabulary):
    SLEEVELESS = "sleeveless"
    SHORT_SLEEVE = "short_sleeve"
    LONG_SLEEVE = "long_sleeve"
    CROP = "crop"
    REGULAR = "regular"
    LONGLINE = "longline"
    MINI = "mini"
    MIDI = "midi"
    MAXI = "maxi"
    ANKLE = "ankle"
    FULL = "full"


class Rise(Vocabulary):
    LOW = "low"
    MID = "mid"
    HIGH = "high"


class ColorPrimary(Vocabulary):
    BLACK = "black"
    WHITE = "white"
    GREY = "grey"
    BEIGE = "beige"
    BROWN = "brown"
    NAVY = "navy"
    BLUE = "blue"
    LIGHT_BLUE = "light_blue"
    RED = "red"
    PINK = "pink"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    OLIVE = "olive"
    PURPLE = "purple"
    GOLD = "gold"
    SILVER = "silver"


class Pattern(Vocabulary):
    SOLID = "solid"
    STRIPES = "stripes"
    CHECKS = "checks"
    FLORAL = "floral"
    ANIMAL = "animal"
    GRAPHIC = "graphic"
    DENIM_WASH = "denim_wash"
    OTHER = "other"


class Material(Vocabulary):
    COTTON = "cotton"
    DENIM = "denim"
    KNIT = "knit"
    WOOL = "wool"
    LEATHER = "leather"
    LINEN = "linen"
    SILK = "silk"
    SYNTHETIC = "synthetic"
    OTHER = "other"


# The one vocabulary here that is not an `items` column. It names the sky rather
# than a garment, and it lives beside the others because the reason they are
# closed applies to it unchanged: `partly_cloudy` and `Partly Cloudy` and
# `partlycloudy` are the same weather and would be three i18n keys. Open-Meteo
# answers in WMO 4677 integers and `app/services/weather.py` maps them; the
# eight values below are what `GET /weather` and the frontend agree on.
# `DECISIONS.md` 144.
class Condition(Vocabulary):
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    FOG = "fog"
    DRIZZLE = "drizzle"
    RAIN = "rain"
    SNOW = "snow"
    THUNDERSTORM = "thunderstorm"


SUBCATEGORIES: dict[Category, tuple[str, ...]] = {
    Category.TOP: (
        "t_shirt",
        "tank",
        "shirt",
        "blouse",
        "sweater",
        "sweatshirt",
        "hoodie",
        "bodysuit",
    ),
    Category.BOTTOM: ("jeans", "trousers", "shorts", "skirt", "leggings", "cargo"),
    Category.DRESS: ("dress", "jumpsuit"),
    Category.OUTERWEAR: ("jacket", "coat", "blazer", "cardigan", "vest", "puffer"),
    Category.SHOES: ("sneakers", "boots", "heels", "flats", "sandals", "loafers"),
    Category.BAG: ("tote", "crossbody", "shoulder", "clutch", "backpack"),
    Category.ACCESSORY: ("belt", "scarf", "hat", "sunglasses", "jewelry"),
    Category.SWIMWEAR: ("swimsuit", "bikini", "swim_shorts", "cover_up", "rash_guard"),
    Category.SLEEPWEAR: ("pajamas", "nightdress", "robe"),
}

# Which categories a field describes at all. Outside them the attribute does not
# exist, so the value is nulled rather than corrected: `02-DATA-MODEL.md` makes
# all three always-nullable, and any other answer would be a substituted value.
FIELD_APPLIES_TO: dict[str, frozenset[Category]] = {
    "fit": frozenset(
        {
            Category.TOP,
            Category.BOTTOM,
            Category.DRESS,
            Category.OUTERWEAR,
            Category.SWIMWEAR,
            Category.SLEEPWEAR,
        }
    ),
    "length": frozenset(
        {
            Category.TOP,
            Category.BOTTOM,
            Category.DRESS,
            Category.OUTERWEAR,
            Category.SHOES,
            Category.SWIMWEAR,
            Category.SLEEPWEAR,
        }
    ),
    "rise": frozenset({Category.BOTTOM}),
}

_SLEEVED = frozenset(
    {Category.TOP, Category.DRESS, Category.OUTERWEAR, Category.SWIMWEAR, Category.SLEEPWEAR}
)
_HEMMED = frozenset(
    {Category.BOTTOM, Category.DRESS, Category.OUTERWEAR, Category.SWIMWEAR, Category.SLEEPWEAR}
)

# Words narrower than the field they belong to; a word absent from here applies
# wherever its field does. `a_line` and `flowy` are absent deliberately — an
# A-line top is a real cut, and nulling it would be the wrong answer this table
# exists to prevent. Nested by field rather than keyed by value alone because
# `mid` is a member of both Rise and Layer, so a flat map would be ambiguous the
# moment a rule touched either.
VALUE_APPLIES_TO: dict[str, dict[str, frozenset[Category]]] = {
    "fit": {
        Fit.SKINNY: frozenset({Category.BOTTOM}),
        Fit.WIDE: frozenset({Category.BOTTOM, Category.DRESS}),
        Fit.BODYCON: frozenset({Category.TOP, Category.BOTTOM, Category.DRESS}),
    },
    "length": {
        Length.SLEEVELESS: _SLEEVED,
        Length.SHORT_SLEEVE: _SLEEVED,
        Length.LONG_SLEEVE: _SLEEVED,
        Length.MINI: _HEMMED,
        Length.MIDI: _HEMMED,
        Length.MAXI: _HEMMED,
    },
}


@dataclass(frozen=True, slots=True)
class LayerRule:
    admits: frozenset[Layer]
    answer: Layer | None


# `answer` is what `02-DATA-MODEL.md` names for the category, not what the size of
# `admits` implies: outerwear admits two values and still answers `outer`, because
# the document says a coat is outer. Deriving the answer from the set would make
# outerwear an error path and break
# test_outerwear_with_a_base_layer_is_coerced_to_outer. `top` is the one category
# the document names no answer for, so `answer=None` is a statement rather than a
# gap — a top is legitimately base or mid and the vocabulary will not pick.
LAYERS_BY_CATEGORY: dict[Category, LayerRule] = {
    Category.TOP: LayerRule(admits=frozenset({Layer.BASE, Layer.MID}), answer=None),
    Category.BOTTOM: LayerRule(admits=frozenset({Layer.BASE}), answer=Layer.BASE),
    Category.DRESS: LayerRule(admits=frozenset({Layer.STANDALONE}), answer=Layer.STANDALONE),
    Category.OUTERWEAR: LayerRule(admits=frozenset({Layer.MID, Layer.OUTER}), answer=Layer.OUTER),
    Category.SHOES: LayerRule(admits=frozenset({Layer.STANDALONE}), answer=Layer.STANDALONE),
    Category.BAG: LayerRule(admits=frozenset({Layer.STANDALONE}), answer=Layer.STANDALONE),
    Category.ACCESSORY: LayerRule(admits=frozenset({Layer.STANDALONE}), answer=Layer.STANDALONE),
    Category.SWIMWEAR: LayerRule(admits=frozenset({Layer.STANDALONE}), answer=Layer.STANDALONE),
    Category.SLEEPWEAR: LayerRule(admits=frozenset({Layer.STANDALONE}), answer=Layer.STANDALONE),
}

# `PATCH /items/{id}` clears these when the category changes, because there it is
# the stored row that became impossible rather than the request that was wrong
# (`DECISIONS.md` 030). Exported so the route reads the list rather than
# restating it in a second language's worth of rules.
CATEGORY_DEPENDENT_FIELDS: tuple[str, ...] = ("subcategory", "rise", "fit", "length", "layer")

# What it takes for a row to describe a garment: the ten columns that carry no
# meaning when null. `fit`, `length`, `rise` and `color_secondary` are absent
# because a null in any of them is an answer (`02-DATA-MODEL.md` makes all four
# always-nullable), not a gap.
#
# Two callers, one definition. `vision.py` asks whether the model answered
# everything and adds `confidence` to this list for itself; `PATCH /items/{id}`
# asks whether a garment is described well enough to leave `failed`, and cannot
# ask about `confidence` at all — `ItemUpdate` has no such field and
# `ai_confidence` is null on every row that never tagged. Requiring it here
# would make that rule unfireable on exactly the row it exists to rescue
# (`DECISIONS.md` 116). The name difference is real and is `tagging.py`'s:
# the model answers `confidence` and the column is `ai_confidence` (028).
REQUIRED_TAG_FIELDS: tuple[str, ...] = (
    "category",
    "subcategory",
    "color_primary",
    "pattern",
    "material",
    "formality",
    "warmth",
    "layer",
    "water_resistant",
    "display_name",
)


@dataclass(frozen=True, slots=True)
class TagIssue:
    field: str
    value: Any
    reason: str


@dataclass(frozen=True, slots=True)
class TagValidation:
    tags: dict[str, Any]
    errors: tuple[TagIssue, ...]
    coerced: tuple[TagIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def reason(self) -> str:
        return "; ".join(issue.reason for issue in self.errors)


_STRICT_ENUM_FIELDS: tuple[tuple[str, type[Vocabulary]], ...] = (
    ("category", Category),
    ("color_primary", ColorPrimary),
    ("pattern", Pattern),
    ("material", Material),
    ("layer", Layer),
)

_NULLABLE_ENUM_FIELDS: tuple[tuple[str, type[Vocabulary]], ...] = (
    ("fit", Fit),
    ("length", Length),
    ("rise", Rise),
    ("color_secondary", ColorPrimary),
)


def _is_int(value: Any) -> bool:
    # bool subclasses int, so True would otherwise validate as formality 1
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def is_valid_subcategory(category: str, sub: str) -> bool:
    if category not in Category.values():
        return False
    return sub in SUBCATEGORIES[Category(category)]


def validate_tag_dict(d: Mapping[str, Any]) -> TagValidation:
    tags: dict[str, Any] = dict(d)
    errors: list[TagIssue] = []
    coerced: list[TagIssue] = []

    for field, vocabulary in _STRICT_ENUM_FIELDS:
        value = tags.get(field)
        if value is not None and value not in vocabulary.values():
            errors.append(
                TagIssue(field, value, f"{field} {value!r} is not in the closed vocabulary")
            )

    for field, vocabulary in _NULLABLE_ENUM_FIELDS:
        value = tags.get(field)
        if value is not None and value not in vocabulary.values():
            tags[field] = None
            coerced.append(
                TagIssue(
                    field, value, f"{field} {value!r} is not in the closed vocabulary, set to null"
                )
            )

    category = tags.get("category")
    # A category outside the vocabulary is already one error, and every rule below
    # is keyed by it, so there is nothing left to look up rather than something to
    # report a second time. `subcategory` predates this and still reports both.
    known_category = category is not None and category in Category.values()

    subcategory = tags.get("subcategory")
    if subcategory is not None:
        if category is None:
            errors.append(
                TagIssue(
                    "subcategory", subcategory, "subcategory cannot be validated without category"
                )
            )
        elif not is_valid_subcategory(category, subcategory):
            errors.append(
                TagIssue(
                    "subcategory",
                    subcategory,
                    f"subcategory {subcategory!r} is not valid for category {category!r}",
                )
            )

    for field, categories in FIELD_APPLIES_TO.items():
        value = tags.get(field)
        if value is None:
            continue
        if category is None:
            errors.append(TagIssue(field, value, f"{field} cannot be validated without category"))
            continue
        if not known_category:
            continue
        if category not in categories:
            tags[field] = None
            coerced.append(
                TagIssue(
                    field, value, f"{field} does not apply to category {category!r}, set to null"
                )
            )
            continue
        narrowed = VALUE_APPLIES_TO.get(field, {}).get(value)
        if narrowed is not None and category not in narrowed:
            tags[field] = None
            coerced.append(
                TagIssue(
                    field,
                    value,
                    f"{field} {value!r} does not describe category {category!r}, set to null",
                )
            )

    layer = tags.get("layer")
    if layer is not None and layer in Layer.values():
        if category is None:
            errors.append(TagIssue("layer", layer, "layer cannot be validated without category"))
        elif known_category:
            rule = LAYERS_BY_CATEGORY[Category(category)]
            if layer not in rule.admits:
                takes = " or ".join(sorted(rule.admits))
                if rule.answer is None:
                    errors.append(
                        TagIssue(
                            "layer",
                            layer,
                            f"layer {layer!r} is not valid for category {category!r}, "
                            f"which takes {takes}",
                        )
                    )
                else:
                    tags["layer"] = rule.answer
                    coerced.append(
                        TagIssue(
                            "layer",
                            layer,
                            f"category {category!r} takes layer {takes}, set to {rule.answer}",
                        )
                    )

    for field in ("formality", "warmth"):
        value = tags.get(field)
        if value is not None and (not _is_int(value) or not 1 <= value <= 5):
            errors.append(TagIssue(field, value, f"{field} must be an integer from 1 to 5"))

    water_resistant = tags.get("water_resistant")
    if water_resistant is not None and not isinstance(water_resistant, bool):
        errors.append(
            TagIssue("water_resistant", water_resistant, "water_resistant must be a boolean")
        )

    display_name = tags.get("display_name")
    if display_name is not None and not isinstance(display_name, str):
        errors.append(TagIssue("display_name", display_name, "display_name must be a string"))

    confidence = tags.get("confidence")
    if confidence is not None and (not _is_number(confidence) or not 0.0 <= confidence <= 1.0):
        errors.append(TagIssue("confidence", confidence, "confidence must be a number from 0 to 1"))

    return TagValidation(tags=tags, errors=tuple(errors), coerced=tuple(coerced))

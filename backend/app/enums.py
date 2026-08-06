"""The closed vocabulary.

Mirrors `docs/02-DATA-MODEL.md`, which is authoritative. Add a value there
first. The frontend copy is `frontend/src/app/shared/models/enums.ts`.
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
}


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
    ("color_secondary", ColorPrimary),
)

_STANDALONE_CATEGORIES = (Category.DRESS, Category.SHOES, Category.BAG, Category.ACCESSORY)


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

    rise = tags.get("rise")
    if rise is not None:
        if category is None:
            errors.append(TagIssue("rise", rise, "rise cannot be validated without category"))
        elif category != Category.BOTTOM:
            tags["rise"] = None
            coerced.append(
                TagIssue("rise", rise, f"rise does not apply to category {category!r}, set to null")
            )
        elif rise not in Rise.values():
            tags["rise"] = None
            coerced.append(
                TagIssue(
                    "rise", rise, f"rise {rise!r} is not in the closed vocabulary, set to null"
                )
            )

    layer = tags.get("layer")
    if layer is not None and layer in Layer.values():
        if category in _STANDALONE_CATEGORIES and layer != Layer.STANDALONE:
            tags["layer"] = Layer.STANDALONE
            coerced.append(
                TagIssue("layer", layer, f"category {category!r} requires layer standalone")
            )
        elif category == Category.OUTERWEAR and layer not in (Layer.MID, Layer.OUTER):
            tags["layer"] = Layer.OUTER
            coerced.append(
                TagIssue(
                    "layer", layer, "category outerwear requires layer mid or outer, set to outer"
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

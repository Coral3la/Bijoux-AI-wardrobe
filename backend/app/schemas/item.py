import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints, computed_field

from app.enums import Category, ColorPrimary, ItemStatus, Layer, Material, Pattern
from app.services.storage import Transform, build_url


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    short_id: str
    status: ItemStatus
    image_public_id: str

    category: Category | None
    subcategory: str | None
    fit: str | None
    length: str | None
    rise: str | None
    color_primary: ColorPrimary | None
    color_secondary: ColorPrimary | None
    pattern: Pattern | None
    material: Material | None
    formality: int | None
    warmth: int | None
    layer: Layer | None
    water_resistant: bool

    display_name: str | None
    attributes: dict[str, Any]
    ai_confidence: float | None
    user_edited: bool
    error_message: str | None
    is_archived: bool

    created_at: datetime
    updated_at: datetime

    # Derived rather than stored, so it cannot disagree with image_public_id.
    # The thumbnail is the transform the wardrobe grid renders; anything else
    # the client wants, it builds from image_public_id with its own pipe.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def image_url(self) -> str:
        return build_url(self.image_public_id, Transform.THUMBNAIL)


class ItemUploadResponse(BaseModel):
    items: list[ItemResponse]


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int


class ItemUpdate(BaseModel):
    """
    A partial edit. Shape only — every value judgement is the
    vocabulary's.

    Fields are typed permissively rather than as `Category`,
    `Layer` and the rest, so one function decides what a value
    means: `validate_tag_dict` runs over the merged row and
    reports membership and the category-dependent rules together,
    in one message shape. Typing the enums here would answer half
    of that in Pydantic's words and half in the vocabulary's, for
    the same field.

    What Pydantic does own is shape: an unknown key, a value of
    the wrong kind, and a blank `display_name`. `extra="forbid"`
    is load-bearing — the default would make `PATCH
    {"colour_primary": "navy"}` a `200` that changed nothing, and
    `validate_tag_dict` cannot catch it because it only inspects
    keys it knows (`DECISIONS.md` 030).
    """

    model_config = ConfigDict(extra="forbid")

    category: str | None = None
    subcategory: str | None = None
    fit: str | None = None
    length: str | None = None
    rise: str | None = None
    color_primary: str | None = None
    color_secondary: str | None = None
    pattern: str | None = None
    material: str | None = None
    formality: int | None = None
    warmth: int | None = None
    layer: str | None = None
    water_resistant: bool | None = None
    # Stripped and non-empty, because `validate_tag_dict` checks
    # only that it is a string, and a blank one is a tile with
    # nothing written on it — the one field in the set whose
    # failure a user sees rather than a developer (086). Spelled
    # with StringConstraints because
    # `Field(strip_whitespace=True)` silently does nothing (072).
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = (
        None
    )


class ItemStatsResponse(BaseModel):
    total: int
    by_category: dict[str, int]
    by_color: dict[str, int]
    processing: int
    failed: int
    # Both wait for migration 0003, which adds `wear_count` and
    # `last_worn_at` at Stage 3. Zero rather than `total`, which
    # is what "nothing has been worn yet" would honestly report:
    # that number would change meaning when the columns arrive,
    # and nothing would catch it. `04-API-SPEC.md` prints the
    # zeros.
    never_worn: int
    most_worn: list[ItemResponse]

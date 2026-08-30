import uuid
from datetime import date, datetime
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

    # On the wire from task 3.4, which is `02-DATA-MODEL.md`'s own deadline for
    # them: the columns landed at `0004` and this is the first shape that reads
    # them. `wear_count` is `NOT NULL DEFAULT 0`, so a garment uploaded before
    # the column existed answers `0` rather than `null` — the property 3.6's
    # `never_worn` counts on. `last_worn_at` stays nullable because never-worn
    # is a real state and not a zero.
    wear_count: int
    last_worn_at: date | None

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


class MostWornItem(BaseModel):
    """The most-worn garment, cut to what an insights panel draws.

    Deliberately not an `ItemResponse`. The panel renders one
    line and a link, and the twenty-odd tag columns behind that
    line would be wire weight with no reader — `04-API-SPEC.md`
    printed the full item here from Stage 0 and no client was
    ever written against it. `id` is what `/wardrobe/:id` routes
    on, which is why it is the id and not the `short_id`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Nullable to match `ItemResponse`, though a `ready` row
    # always has one: `display_name` is in `REQUIRED_TAG_FIELDS`.
    # Typing it `str` buys nothing and turns a row edited by hand
    # into a 500.
    display_name: str | None
    wear_count: int


class ItemStatsResponse(BaseModel):
    total: int
    by_category: dict[str, int]
    by_color: dict[str, int]
    processing: int
    failed: int
    # A partition, not two independent numbers: they are counted
    # in one statement over one population and sum to it. What
    # they do not sum to is `total`, which counts every status.
    worn: int
    never_worn: int
    # `None`, not an empty list, and the difference is the whole
    # reason this field is not `list[ItemResponse]` any more:
    # there is exactly one most-worn garment or there is nothing
    # worn at all, and a list of one made the caller ask which.
    most_worn: MostWornItem | None

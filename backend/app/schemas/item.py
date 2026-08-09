import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field

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

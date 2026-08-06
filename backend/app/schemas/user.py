import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    height_cm: int | None
    size_top: str | None
    size_bottom: str | None
    size_shoe: str | None
    style_notes: str | None
    home_city: str | None
    home_lat: float | None
    home_lon: float | None
    created_at: datetime

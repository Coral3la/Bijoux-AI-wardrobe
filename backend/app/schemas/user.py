import uuid
from datetime import datetime
from typing import Annotated, Final, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.models.user import MAX_HEIGHT_CM, MIN_HEIGHT_CM

# Moved here from `schemas/auth.py` at task 2.2, where 0.10 first wrote it.
# `PATCH /me` needs the same rule and `auth.py` already imports this module, so
# the alias belongs to the module that owns the user shape and the register body
# imports it rather than the other way round. `DECISIONS.md` 072 predicted the
# reuse and not the move. StringConstraints rather than
# Field(strip_whitespace=True), which silently does nothing in Pydantic v2:
# strip runs before min_length, which is what makes "   " a 422 instead of a
# blank column.
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

_HOME_FIELDS: Final = ("home_city", "home_lat", "home_lon")


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


class UserUpdate(BaseModel):
    """A partial edit of the profile.

    The whole body `04-API-SPEC.md` prints, not the three home fields
    `STAGE-2` 2.2 named: `03-AI-CONTRACTS.md`'s stylist prompt reads
    `height_cm` and `style_notes`, and with a narrow schema that block is
    structurally empty in every request the project will ever make
    (`AUDITS.md` O-6).

    Semantics are `PATCH /items/{id}`'s exactly — `extra="forbid"` so a
    misspelled key is a 422 rather than a 200 that changed nothing, and the
    route reads `exclude_unset` so an omitted field is left alone where an
    explicit null clears it.
    """

    model_config = ConfigDict(extra="forbid")

    # Nullable here, and that is a change rather than an oversight: before this
    # task nothing in the API could blank a display name, and `04-API-SPEC.md`
    # said so. `userLabel` in the frontend has fallen back to the email address
    # since 0.9 (071) because four accounts predate the register rule, so the
    # column being blank is a state the client already renders.
    display_name: DisplayName | None = None
    height_cm: Annotated[int, Field(ge=MIN_HEIGHT_CM, le=MAX_HEIGHT_CM)] | None = None
    size_top: str | None = None
    size_bottom: str | None = None
    size_shoe: str | None = None
    style_notes: str | None = None
    home_city: str | None = None
    home_lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    home_lon: Annotated[float, Field(ge=-180, le=180)] | None = None

    @model_validator(mode="after")
    def _home_is_one_field(self) -> Self:
        """A city with no coordinates cannot be fetched a forecast for and
        coordinates with no city name have nothing to print above the weather
        strip, so the three are supplied together or cleared together."""
        supplied = [field for field in _HOME_FIELDS if field in self.model_fields_set]
        if not supplied:
            return self

        listed = ", ".join(_HOME_FIELDS)
        if len(supplied) != len(_HOME_FIELDS):
            raise ValueError(f"{listed} are set together; send all three or none")

        values = [getattr(self, field) for field in _HOME_FIELDS]
        if any(value is None for value in values) and not all(value is None for value in values):
            raise ValueError(f"{listed} are cleared together; send all three as null or none")
        return self

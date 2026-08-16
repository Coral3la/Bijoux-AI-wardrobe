from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.core.security import MAX_PASSWORD_BYTES
from app.schemas.user import UserResponse

MIN_PASSWORD_LENGTH = 8

# StringConstraints rather than Field(strip_whitespace=True): Field has no such
# parameter in Pydantic v2, so that spelling is an ignored extra key and leaves
# "   " a valid display name. Strip runs before min_length, which is what makes
# a whitespace-only name a 422 rather than a blank column. DECISIONS.md 072.
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    display_name: DisplayName

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"must be at most {MAX_PASSWORD_BYTES} bytes once UTF-8 encoded; "
                "accented and non-Latin characters take more than one byte each"
            )
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse

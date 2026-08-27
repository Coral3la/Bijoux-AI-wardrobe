from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.enums import Category

APP_VERSION = "0.1.0"

# The vision pin. Dated rather than the moving `gpt-4o-mini` alias:
# `06-TESTING-STRATEGY.md` records the model with every eval run, and an
# accuracy curve measured against a pointer that can move underneath it is not
# reproducible. `DECISIONS.md` 078.
OPENAI_MODEL = "gpt-4o-mini-2024-07-18"

# The stylist pin — the same snapshot, and a second constant rather than a
# second reference to the first since task 2.4. Task 1.11 is chartered to
# re-pin `OPENAI_MODEL` against a newer model and to measure the difference on
# a golden set of *photographs*; while the two shared one constant, that re-pin
# also silently changed the model behind every Stage 2 acceptance criterion,
# all of which are about how the stylist behaves. One constant could not carry
# two independent decisions. Verified against a live call at 2.4.
# `DECISIONS.md` 160.
OPENAI_STYLIST_PIN = "gpt-4o-mini-2024-07-18"


def _category_names(value: str) -> list[str]:
    return [name.strip().lower() for name in value.split(",") if name.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str

    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_UPLOAD_FOLDER: str = "bijoux"
    CLOUDINARY_REMOVE_BACKGROUND: bool = False

    OPENAI_API_KEY: str = ""
    OPENAI_VISION_MODEL: str = OPENAI_MODEL
    OPENAI_STYLIST_MODEL: str = OPENAI_STYLIST_PIN
    OPENAI_TIMEOUT_SECONDS: int = 30

    USE_FAKE_AI: bool = False
    # The categories the stylist is never shown. `01-ARCHITECTURE.md` and
    # `STAGE-2` 2.4 both promise this list is configurable and 2.6a gave it two
    # members to name; comma-separated because that is how `CORS_ORIGINS`
    # already spells a list. Emptying it sends the whole wardrobe, which is
    # what `DECISIONS.md` 002 argues for everywhere else.
    STYLIST_EXCLUDED_CATEGORIES: str = "swimwear,sleepwear"
    CORS_ORIGINS: str = "http://localhost:4200"
    MAX_UPLOAD_MB: int = 10
    MAX_FILES_PER_REQUEST: int = 20
    ENV: Literal["development", "production"] = "development"

    @field_validator("STYLIST_EXCLUDED_CATEGORIES")
    @classmethod
    def _known_categories(cls, value: str) -> str:
        # At process start rather than per request: a typo here does not raise,
        # it filters nothing, and a filter that silently stops filtering is the
        # failure O-21 spent two tasks making impossible.
        unknown = [name for name in _category_names(value) if name not in Category.values()]
        if unknown:
            raise ValueError(f"not categories in 02-DATA-MODEL.md: {', '.join(unknown)}")
        return value

    @property
    def stylist_excluded_categories(self) -> frozenset[Category]:
        return frozenset(
            Category(name) for name in _category_names(self.STYLIST_EXCLUDED_CATEGORIES)
        )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


settings = Settings()

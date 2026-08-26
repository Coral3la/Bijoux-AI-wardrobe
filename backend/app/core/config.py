from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    CORS_ORIGINS: str = "http://localhost:4200"
    MAX_UPLOAD_MB: int = 10
    MAX_FILES_PER_REQUEST: int = 20
    ENV: Literal["development", "production"] = "development"

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

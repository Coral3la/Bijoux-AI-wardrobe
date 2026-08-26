import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import REAL, TIMESTAMP, CheckConstraint, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# `02-DATA-MODEL.md`'s CHECK, as numbers rather than as a literal inside the
# constraint string, so `UserUpdate` can reject an out-of-range height from the
# same two values the column is built from. Until task 2.2 the column was the
# only thing enforcing this and nothing sent it a height; a request carrying 400
# would have reached Postgres, where an IntegrityError is a 500 with no `code`.
MIN_HEIGHT_CM: Final = 120
MAX_HEIGHT_CM: Final = 230


class User(Base):
    __tablename__ = "users"

    # The convention in db/base.py expands this to ck_users_height_cm_range,
    # which is the name migration 0001 spells out literally.
    __table_args__ = (
        CheckConstraint(
            f"height_cm BETWEEN {MIN_HEIGHT_CM} AND {MAX_HEIGHT_CM}", name="height_cm_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)

    height_cm: Mapped[int | None] = mapped_column(SmallInteger)
    size_top: Mapped[str | None] = mapped_column(Text)
    size_bottom: Mapped[str | None] = mapped_column(Text)
    size_shoe: Mapped[str | None] = mapped_column(Text)
    style_notes: Mapped[str | None] = mapped_column(Text)

    home_city: Mapped[str | None] = mapped_column(Text)
    home_lat: Mapped[float | None] = mapped_column(REAL)
    home_lon: Mapped[float | None] = mapped_column(REAL)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

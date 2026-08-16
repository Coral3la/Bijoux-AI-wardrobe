import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    REAL,
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import Category, ItemStatus, Layer


class Item(Base):
    __tablename__ = "items"

    # Spelled out here as well as in migration 0001 so the ORM's description of
    # the table names the same constraints the database has, per 02-DATA-MODEL.md.
    # Not so that create_all could build this schema: create_type=False on all
    # three enums (024) means it emits no CREATE TYPE and no CREATE EXTENSION,
    # so it fails on CITEXT before it reaches item_status (074).
    __table_args__ = (
        CheckConstraint("formality BETWEEN 1 AND 5", name="formality_range"),
        CheckConstraint("warmth BETWEEN 1 AND 5", name="warmth_range"),
        Index(
            "idx_items_wardrobe",
            "user_id",
            "status",
            "category",
            postgresql_where=text("is_archived = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    short_id: Mapped[str] = mapped_column(CHAR(6), unique=True)

    image_public_id: Mapped[str] = mapped_column(Text)
    # create_type=False throughout: migration 0001 creates the three types with
    # op.execute, and the values come from enums.py so the two cannot drift.
    status: Mapped[str] = mapped_column(
        ENUM(*ItemStatus.values(), name="item_status", create_type=False),
        server_default=text("'processing'"),
    )

    category: Mapped[str | None] = mapped_column(
        ENUM(*Category.values(), name="item_category", create_type=False)
    )
    subcategory: Mapped[str | None] = mapped_column(Text)
    fit: Mapped[str | None] = mapped_column(Text)
    length: Mapped[str | None] = mapped_column(Text)
    rise: Mapped[str | None] = mapped_column(Text)
    color_primary: Mapped[str | None] = mapped_column(Text)
    color_secondary: Mapped[str | None] = mapped_column(Text)
    pattern: Mapped[str | None] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    formality: Mapped[int | None] = mapped_column(SmallInteger)
    warmth: Mapped[int | None] = mapped_column(SmallInteger)
    layer: Mapped[str | None] = mapped_column(
        ENUM(*Layer.values(), name="item_layer", create_type=False)
    )
    water_resistant: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    display_name: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ai_confidence: Mapped[float | None] = mapped_column(REAL)
    user_edited: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    error_message: Mapped[str | None] = mapped_column(Text)

    is_archived: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

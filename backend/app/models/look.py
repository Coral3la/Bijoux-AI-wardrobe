"""A suggestion, and the items it is made of.

Migration `0002` creates both tables; 2.7 is the first thing that writes a row,
one per call to `POST /looks/suggest` with `is_saved=False`, before the response
returns. Migration `0004` adds `feedback` and `worn_at` and the two indexes
`AUDITS.md` O-25 deferred to the stage that reads them.

**One documented column is still deliberately absent.** `02-DATA-MODEL.md`
prints `trip_id` on `looks` and adds it in migration `0005`, which is also what
creates the `trips` table it references. A model declaring a column the database
lacks breaks every query against it — the rule `items.wear_count` established at
task 0.7 and this migration discharges for the other three.

No `relationship()` anywhere, following `Item`, which names `user_id` and stops.
2.7 hydrates from the wardrobe it already holds in memory, and the aggregation
Stage 3 needs is plain SQL over the two tables.

`Look` is also the name of the frozen dataclass in `app/services/stylist.py`.
They are different things — one is a row, the other is what the model answered —
and each is right in its own module, so 2.7 aliases one at the import rather
than either being renamed.
"""

import uuid
from datetime import date, datetime
from typing import Final

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# `02-DATA-MODEL.md`'s CHECK, as numbers rather than as a literal inside the
# constraint string, so 3.3's `Literal[FEEDBACK_UP, FEEDBACK_DOWN]` rejects a
# thumbs value from the same two the column is built from. Not MIN/MAX, which
# `users.height_cm` is: this is set membership and there is nothing between them.
FEEDBACK_UP: Final = 1
FEEDBACK_DOWN: Final = -1


class Look(Base):
    __tablename__ = "looks"

    # The convention in db/base.py expands this to ck_looks_feedback_values,
    # which is the name migration 0004 spells out literally — as raw DDL there,
    # because op.create_check_constraint would apply the convention a second
    # time and emit ck_looks_ck_looks_feedback_values.
    __table_args__ = (
        CheckConstraint(f"feedback IN ({FEEDBACK_DOWN}, {FEEDBACK_UP})", name="feedback_values"),
        Index("idx_looks_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )

    title: Mapped[str | None] = mapped_column(Text)
    occasion: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    weather_note: Mapped[str | None] = mapped_column(Text)
    for_date: Mapped[date | None] = mapped_column(Date)

    is_saved: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # No server default on either: a look nobody has rated is NULL rather than
    # 0, which is what lets 3.5 count rated looks without excluding a value.
    feedback: Mapped[int | None] = mapped_column(SmallInteger)
    worn_at: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )


class LookItem(Base):
    __tablename__ = "look_items"

    # PostgreSQL indexes the referenced side of a foreign key and not the
    # referencing side, so without this the cascade from `items` and 3.5's
    # per-item aggregation both scan the table. The composite primary key
    # already serves every lookup by `look_id`. `AUDITS.md` O-25.
    __table_args__ = (Index("idx_look_items_item_id", "item_id"),)

    # The composite primary key is the whole of this table's integrity: one
    # garment can appear once in a look and no more, which is what lets 3.4's
    # wear increment count each item exactly once per look.
    look_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("looks.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )

    # Both land unwritten: the stylist returns ids and no roles, and 2.9 orders
    # the look card by `layer` and `category`. `role`'s vocabulary closed at
    # 2.11 without a reader for the column; `position` has its first at 2.11.
    role: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))

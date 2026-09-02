"""A suggestion, and the items it is made of.

Migration `0002` creates both tables; 2.7 is the first thing that writes a row,
one per call to `POST /looks/suggest` with `is_saved=False`, before the response
returns. Migration `0004` adds `feedback` and `worn_at` and the two indexes
`AUDITS.md` O-25 deferred to the stage that reads them.

Migration `0005` adds `trip_id` and the index over it, in the same revision
that creates the `trips` table it references — a `looks.trip_id` pointing at
nothing is not a schema, so the two halves could not be separate migrations.
The column is **nullable and stays nullable**: every look written before Stage 4
belongs to no trip, and `POST /looks/suggest` goes on writing them that way.

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
        # Both nullables in one statement and in both directions: a look off a
        # trip has no slot, and a trip look never lacks one. The short name is
        # deliberate — the convention expands it to
        # ck_looks_slot_belongs_to_a_trip, which is what migration 0006 spells
        # out literally as raw DDL for the reason the CHECK above is raw there.
        CheckConstraint("(trip_id IS NULL) = (slot IS NULL)", name="slot_belongs_to_a_trip"),
        Index("idx_looks_user_id", "user_id"),
        # The referencing side of `0005`'s foreign key, which PostgreSQL does
        # not index for us — so without it the cascade from `trips` and a
        # trip's own read of its looks both scan the table. `AUDITS.md` O-25's
        # argument, taken in the migration that creates the key rather than
        # deferred to the stage that reads it, because they are the same stage.
        Index("idx_looks_trip_id", "trip_id"),
        # A day carries one look or two and never two of the same slot, which is
        # this object and not the request validator. An Index with unique=True
        # rather than a UniqueConstraint because a UNIQUE constraint cannot
        # carry a WHERE.
        #
        # The predicate is scope rather than a fix for a collision: under the
        # default NULLS DISTINCT an unconditional index would refuse nothing
        # extra, since two NULLs are never equal. It says in the DDL that the
        # invariant belongs to trip looks, keeps the index off every
        # POST /looks/suggest row, and survives a future NULLS NOT DISTINCT
        # that would otherwise refuse every second suggestion sharing a
        # for_date. Migration 0006 carries the argument in full.
        Index(
            "uq_looks_trip_day_slot",
            "trip_id",
            "for_date",
            "slot",
            unique=True,
            postgresql_where=text("trip_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    # `ON DELETE CASCADE` for the reason the user key has it: a trip's looks
    # were built for its days and its forecast, and a trip that is gone leaves
    # nothing that could render them. A look with no trip is the normal case
    # and is what `NULL` means here.
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE")
    )
    # `day` or `evening`, and NULL off a trip — the CHECK above holds both
    # halves. Typed `str` and not `Slot` for the reason `occasion` below is: the
    # column is TEXT, the database refuses no value, and the enum is the wire's
    # gate rather than the column's.
    slot: Mapped[str | None] = mapped_column(Text)

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

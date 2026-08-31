"""A trip, and the plan that was packed for it.

Migration `0005` creates this table and, in the same revision, adds
`looks.trip_id` — the foreign key `02-DATA-MODEL.md` has printed on the `looks`
DDL since Stage 0 and that `0002` deliberately did not build, because the table
it references did not exist yet. Nothing writes a row here: `pack_trip` is
4.3's and `POST /trips/pack` is 4.4's, and this task ships the schema alone.

No `relationship()`, following `Item` and `Look`, which name their foreign key
columns and stop. A trip's looks are read with a `WHERE trip_id = :id` in the
route that wants them.

**Three columns are `JSONB` and only one has a shape this task can name.**
`occasions` is `04-API-SPEC.md`'s request body — `[{"day": 1, "occasion":
"work"}, …]` — and it is `NOT NULL DEFAULT '[]'` because a trip carries one
entry per day and an absent list and an empty one would mean the same thing.
`forecast` and `packing_list` are nullable and typed only as the objects
`02-DATA-MODEL.md` prints: both are written at 4.3, and their keys are settled
beside the trip response schema (`DECISIONS.md` 189) rather than guessed here
by the migration that stores them.

`dest_lat` and `dest_lon` are `REAL` and nullable, exactly as `users.home_lat`
and `home_lon` are. Same source — the Open-Meteo geocoder — and `weather.py`
rounds to two decimals before either becomes a cache key, so the precision a
`REAL` discards is precision the provider discards first (`DECISIONS.md` 145).
They are nullable and `destination` is not, because the destination is what the
user typed and the coordinates are what the geocoder made of it.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    REAL,
    TIMESTAMP,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Trip(Base):
    __tablename__ = "trips"

    # The convention in db/base.py expands "date_order" to ck_trips_date_order,
    # and migration 0005 spells the same short name inside create_table so that
    # one string is expanded by one rule in both places. 0001 passed the
    # expanded name into that slot instead and the live schema holds
    # ck_users_ck_users_height_cm_range for it — measured at 4.1, and the
    # reason this constraint is named in four characters rather than in twenty.
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="date_order"),
        Index("idx_trips_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )

    destination: Mapped[str] = mapped_column(Text)
    dest_lat: Mapped[float | None] = mapped_column(REAL)
    dest_lon: Mapped[float | None] = mapped_column(REAL)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)

    occasions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    forecast: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    packing_list: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

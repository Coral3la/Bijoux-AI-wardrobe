"""A suggestion, and the items it is made of.

Migration `0002` creates both tables; 2.7 is the first thing that writes a row,
one per call to `POST /looks/suggest` with `is_saved=False`, before the response
returns.

**Three documented columns are deliberately absent.** `02-DATA-MODEL.md` prints
`feedback` and `worn_at` on `looks` for readability and adds them in migration
`0004`; `trip_id` arrives with `0005`, which is also what creates the `trips`
table it references. A model declaring a column the database lacks breaks every
query against it — the rule `items.wear_count` established at task 0.7.

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

from sqlalchemy import TIMESTAMP, Boolean, Date, ForeignKey, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Look(Base):
    __tablename__ = "looks"

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

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )


class LookItem(Base):
    __tablename__ = "look_items"

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
    # the look card by `layer` and `category`. `role`'s vocabulary is `AUDITS.md`
    # O-25 and is 2.7's to settle; `position` has its first reader at 2.11.
    role: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))

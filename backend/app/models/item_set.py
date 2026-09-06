"""A set: two or more garments the user declared as bought or worn together.

Migration `0007` creates this table and, in the same revision, adds the
`items.set_id` that points at it. **The relation lives on `items`, not here** —
this row carries only what belongs to the set itself, which is who declared it,
what they called it and when. `02-DATA-MODEL.md` rejected the alternative of a
composite item filling two slots the way a `dress` does, because the set's top
has to stay wearable with other trousers and a row occupying both slots cannot
say that.

No `relationship()`, following `Item`, `Look` and `Trip`. A set's members are
read with a `WHERE set_id = :id` in `routes/sets.py`, in `GET /items`' own
order.

**`name` is nullable and is written once.** `STAGE-4A` puts renaming out of
scope, so there is no `PATCH /sets/{set_id}` and a user who wants a different
name deletes the set and declares it again.

**Fewer than two members is not a set, and nothing here can say so.** A `CHECK`
cannot count rows in another table, so the rule is the API's: the removal that
would leave one member behind deletes this row, and `0007`'s `ON DELETE SET
NULL` clears the survivor. A set is therefore one of the few rows in this
project whose central invariant the database does not hold.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItemSet(Base):
    __tablename__ = "item_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

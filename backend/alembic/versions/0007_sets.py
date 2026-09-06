"""sets

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `02-DATA-MODEL.md`'s two objects in one revision, in this order, for the
    # reason `0005` created `trips` beside `looks.trip_id`: an `items.set_id`
    # referencing a table that does not exist is not a schema.
    #
    # **It carries no data.** Every existing row's `set_id` is `NULL` and that
    # is the correct value for it — a set is a statement a user makes, not a
    # property every garment has — so unlike `0006` there is no backfill and
    # nothing between the DDL statements.
    #
    # **No CHECK, and that is the interesting absence.** *Fewer than two members
    # is not a set* is the rule this table exists under, and a `CHECK` cannot
    # count rows in another table, so `routes/sets.py` enforces it and the
    # database does not. Which also means `0004`'s finding — that
    # `op.create_check_constraint` re-expands a name the naming convention has
    # already expanded, and any CHECK therefore has to be raw DDL — has nothing
    # to bite on here.
    op.create_table(
        "item_sets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Nullable, and written once: `STAGE-4A` puts renaming out of scope, so
        # a set with no name is described by its members and there is no `PATCH`
        # that could give it one later.
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_item_sets_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_item_sets"),
    )

    # `ON DELETE SET NULL`, never `CASCADE`. Deleting a set withdraws a
    # statement about garments and must not delete the garments — every member
    # survives with `set_id` `NULL`, which is what makes `DELETE /sets/{id}`
    # safe enough to offer beside a photograph of a coat. It is also the
    # mechanism behind the API's *fewer than two members is not a set*: the
    # route deletes the `item_sets` row and this key clears the last member.
    op.add_column("items", sa.Column("set_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_items_set_id_item_sets", "items", "item_sets", ["set_id"], ["id"], ondelete="SET NULL"
    )

    # Partial, because the column is `NULL` on almost every row. Its reader is
    # the one query the item detail screen makes — the other members of this
    # item's set — and it is the referencing side of the key above, which
    # PostgreSQL does not index on its own. `idx_looks_trip_id` at `0005` is the
    # same argument on the same footing.
    op.create_index(
        "idx_items_set_id", "items", ["set_id"], postgresql_where=sa.text("set_id IS NOT NULL")
    )


def downgrade() -> None:
    # A real reversal, unlike `0003`'s, and it destroys only the relation: the
    # `items` rows keep every tag, every wear count and their archive state, and
    # lose the column that said which of them were bought together.
    #
    # The index is named although `DROP COLUMN` would take it, and the foreign
    # key is not although it would be taken by the same statement — `0005` and
    # `0006` both read this way, and the order is the reverse of `upgrade()`
    # rather than `02-DATA-MODEL.md`'s sentence: a `drop_index` **after** the
    # column it indexes has already gone is an error, not a no-op.
    op.drop_index("idx_items_set_id", table_name="items")
    op.drop_column("items", "set_id")
    op.drop_table("item_sets")

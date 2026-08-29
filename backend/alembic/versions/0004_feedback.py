"""feedback

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("looks", sa.Column("feedback", sa.SmallInteger(), nullable=True))
    op.add_column("looks", sa.Column("worn_at", sa.Date(), nullable=True))
    # Spelled as raw DDL rather than op.create_check_constraint, which is the
    # only place in this project where the naming convention would be applied
    # twice: alembic builds the constraint on a MetaData carrying
    # `target_metadata.naming_convention`, so a literal name goes in and
    # `ck_looks_ck_looks_feedback_values` comes out. Measured, not inferred.
    op.execute(
        "ALTER TABLE looks ADD CONSTRAINT ck_looks_feedback_values CHECK (feedback IN (-1, 1))"
    )

    op.add_column(
        "items",
        sa.Column("wear_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("items", sa.Column("last_worn_at", sa.Date(), nullable=True))

    # AUDITS.md O-25's second half, deferred from 0002 to the stage whose
    # readers arrive: 3.2 lists looks by user, and 3.5 aggregates look_items by
    # item_id, which PostgreSQL does not index for us on the referencing side of
    # a foreign key. Built here because Stage 3 has one migration and a second
    # would renumber 0005_trips again.
    op.create_index("idx_looks_user_id", "looks", ["user_id"])
    op.create_index("idx_look_items_item_id", "look_items", ["item_id"])


def downgrade() -> None:
    op.drop_index("idx_look_items_item_id", table_name="look_items")
    op.drop_index("idx_looks_user_id", table_name="looks")

    op.drop_column("items", "last_worn_at")
    op.drop_column("items", "wear_count")

    # No drop_constraint: PostgreSQL takes a CHECK with the column it reads.
    op.drop_column("looks", "worn_at")
    op.drop_column("looks", "feedback")

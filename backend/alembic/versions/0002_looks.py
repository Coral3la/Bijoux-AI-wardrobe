"""looks

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `02-DATA-MODEL.md`'s DDL minus three columns that belong to later
    # migrations: `feedback` and `worn_at` to `0003`, `trip_id` to `0004` —
    # which is also the migration that creates the table it references. No new
    # enum type and no extension, so `downgrade` is two drops.
    op.create_table(
        "looks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("occasion", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("weather_note", sa.Text(), nullable=True),
        sa.Column("for_date", sa.Date(), nullable=True),
        sa.Column("is_saved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_looks_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_looks"),
    )

    op.create_table(
        "look_items",
        sa.Column("look_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("position", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["look_id"], ["looks.id"], name="fk_look_items_look_id_looks", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name="fk_look_items_item_id_items", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("look_id", "item_id", name="pk_look_items"),
    )


def downgrade() -> None:
    op.drop_table("look_items")
    op.drop_table("looks")

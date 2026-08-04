"""initial

Revision ID: 0001
Revises:
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


item_status = postgresql.ENUM(
    "processing", "ready", "failed", name="item_status", create_type=False
)
item_category = postgresql.ENUM(
    "top",
    "bottom",
    "dress",
    "outerwear",
    "shoes",
    "bag",
    "accessory",
    name="item_category",
    create_type=False,
)
item_layer = postgresql.ENUM(
    "base", "mid", "outer", "standalone", name="item_layer", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("CREATE TYPE item_status AS ENUM ('processing', 'ready', 'failed')")
    op.execute(
        "CREATE TYPE item_category AS ENUM "
        "('top', 'bottom', 'dress', 'outerwear', 'shoes', 'bag', 'accessory')"
    )
    op.execute("CREATE TYPE item_layer AS ENUM ('base', 'mid', 'outer', 'standalone')")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("height_cm", sa.SmallInteger(), nullable=True),
        sa.Column("size_top", sa.Text(), nullable=True),
        sa.Column("size_bottom", sa.Text(), nullable=True),
        sa.Column("size_shoe", sa.Text(), nullable=True),
        sa.Column("style_notes", sa.Text(), nullable=True),
        sa.Column("home_city", sa.Text(), nullable=True),
        sa.Column("home_lat", sa.REAL(), nullable=True),
        sa.Column("home_lon", sa.REAL(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("height_cm BETWEEN 120 AND 230", name="ck_users_height_cm_range"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("short_id", sa.CHAR(length=6), nullable=False),
        sa.Column("image_public_id", sa.Text(), nullable=False),
        sa.Column("status", item_status, server_default=sa.text("'processing'"), nullable=False),
        sa.Column("category", item_category, nullable=True),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("fit", sa.Text(), nullable=True),
        sa.Column("length", sa.Text(), nullable=True),
        sa.Column("rise", sa.Text(), nullable=True),
        sa.Column("color_primary", sa.Text(), nullable=True),
        sa.Column("color_secondary", sa.Text(), nullable=True),
        sa.Column("pattern", sa.Text(), nullable=True),
        sa.Column("material", sa.Text(), nullable=True),
        sa.Column("formality", sa.SmallInteger(), nullable=True),
        sa.Column("warmth", sa.SmallInteger(), nullable=True),
        sa.Column("layer", item_layer, nullable=True),
        sa.Column("water_resistant", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ai_confidence", sa.REAL(), nullable=True),
        sa.Column("user_edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("formality BETWEEN 1 AND 5", name="ck_items_formality_range"),
        sa.CheckConstraint("warmth BETWEEN 1 AND 5", name="ck_items_warmth_range"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_items_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_items"),
        sa.UniqueConstraint("short_id", name="uq_items_short_id"),
    )

    op.create_index(
        "idx_items_wardrobe",
        "items",
        ["user_id", "status", "category"],
        postgresql_where=sa.text("is_archived = false"),
    )


def downgrade() -> None:
    op.drop_table("items")
    op.drop_table("users")

    op.execute("DROP TYPE item_layer")
    op.execute("DROP TYPE item_category")
    op.execute("DROP TYPE item_status")

    # Extensions are database-scoped, not schema-scoped: dropping citext would
    # break any other schema in the same database that uses it. Both CREATEs in
    # upgrade() are IF NOT EXISTS, so leaving them costs nothing on re-upgrade.

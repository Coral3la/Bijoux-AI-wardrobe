"""trips

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `02-DATA-MODEL.md`'s DDL whole, plus the foreign key that migration
    # `0002` printed on `looks` and could not build: `trip_id` references a
    # table that did not exist until this line. The two halves are one
    # revision because a `looks.trip_id` with no `trips` is not a schema.
    #
    # **The CHECK carries the short name, and that is the whole of the
    # difference between this line and the three `0001` got wrong.**
    # `create_table` applies `target_metadata.naming_convention` exactly once,
    # so `ck_%(table_name)s_%(constraint_name)s` wants `date_order` and turns
    # it into `ck_trips_date_order`. `0001` passed the *expanded* name into
    # that slot, and the live schema therefore holds
    # `ck_users_ck_users_height_cm_range`, `ck_items_ck_items_formality_range`
    # and `ck_items_ck_items_warmth_range` — measured against the test database
    # at 4.1, both spellings run, not reasoned from the convention.
    #
    # This is `0004`'s finding through a different door and it needs no raw
    # DDL: `op.create_check_constraint` re-expands a name that is already whole,
    # which is why `0004` had to bypass it, and `create_table` does not.
    op.create_table(
        "trips",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("dest_lat", sa.REAL(), nullable=True),
        sa.Column("dest_lon", sa.REAL(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "occasions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("forecast", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("packing_list", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("end_date >= start_date", name="date_order"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_trips_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trips"),
    )

    # Nullable, and it stays nullable: every look this project has written so
    # far belongs to no trip, and `POST /looks/suggest` goes on writing them
    # that way. The `NOT NULL` a trip's own looks satisfy is the route's, not
    # the column's.
    op.add_column("looks", sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_looks_trip_id_trips", "looks", "trips", ["trip_id"], ["id"], ondelete="CASCADE"
    )

    # `AUDITS.md` O-25's reasoning, one migration on and taken this time rather
    # than deferred: PostgreSQL indexes the referenced side of a foreign key
    # and not the referencing side, so without `idx_looks_trip_id` both the
    # cascade from `trips` and 4.6's read of a trip's looks scan the table.
    # `idx_trips_user_id` is `idx_looks_user_id`'s twin and has the same reader,
    # `GET /trips`. Neither is deferred to the stage that reads them, because
    # that stage is this one.
    op.create_index("idx_trips_user_id", "trips", ["user_id"])
    op.create_index("idx_looks_trip_id", "looks", ["trip_id"])


def downgrade() -> None:
    op.drop_index("idx_looks_trip_id", table_name="looks")
    op.drop_index("idx_trips_user_id", table_name="trips")

    # The foreign key goes with the column, as `0004`'s CHECK went with the one
    # it read. Dropping `trips` first would fail on it.
    op.drop_column("looks", "trip_id")
    op.drop_table("trips")

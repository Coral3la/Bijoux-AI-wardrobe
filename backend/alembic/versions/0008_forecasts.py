"""forecasts

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One table, no foreign key, no index beyond the primary key, and no data:
    # the rows are written by the first provider answer after this runs. The
    # key is the pair `services/weather.py` rounds to `COORD_PRECISION` plus the
    # day, in `DOUBLE PRECISION` so that the Python float that made the
    # in-memory key is the value the column holds — `REAL` would round 32.08 to
    # something the next lookup does not equal.
    op.create_table(
        "forecasts",
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("temp_min_c", sa.Double(), nullable=False),
        sa.Column("temp_max_c", sa.Double(), nullable=False),
        sa.Column("precip_mm", sa.Double(), nullable=False),
        sa.Column("wind_kph", sa.Double(), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("lat", "lon", "date", name="pk_forecasts"),
    )


def downgrade() -> None:
    # Destroys a cache. Every trip keeps its own `trips.forecast`, so nothing a
    # user can see is lost; the next provider answer refills the table.
    op.drop_table("forecasts")

"""vocabulary

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-27

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Measured on the test container rather than assumed from the version
    # number, which is what `STAGE-2` 2.6a asked for: on PostgreSQL 18.6 both
    # statements run inside the transaction `alembic/env.py` opens, so there is
    # no `autocommit_block()` here. What PostgreSQL still refuses is *using* a
    # value in the transaction that added it, and nothing below uses one.
    op.execute("ALTER TYPE item_category ADD VALUE IF NOT EXISTS 'swimwear'")
    op.execute("ALTER TYPE item_category ADD VALUE IF NOT EXISTS 'sleepwear'")


def downgrade() -> None:
    # PostgreSQL has no DROP VALUE. The only true reversal is a type swap —
    # rename, recreate, ALTER COLUMN TYPE, drop — which rebuilds the column
    # `0001` created and fails outright once any row carries either value.
    # Two unused labels on the type are harmless, whereas a downgrade that
    # raised would block `alembic downgrade 0001`, which is the step every
    # mutation run in `06-TESTING-STRATEGY.md` starts from. `IF NOT EXISTS`
    # above is what makes the re-upgrade over them clean.
    pass

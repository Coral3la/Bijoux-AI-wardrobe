"""look slot

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Every entry that has no `slot` gets `day`, and every entry that has one is
# left exactly as it is, which makes the statement idempotent: it can be re-run
# over a half-migrated database without turning an `evening` into a `day`.
#
# It is **not** what protects an evening across a downgrade-and-upgrade cycle,
# and the first draft of this migration claimed it was. `downgrade()` strips the
# key before a re-upgrade ever sees it, so by then there is nothing left to
# preserve — the guard at the top of `downgrade()` is what handles that case,
# and the comment there carries the measurement.
_FILL_OCCASION_SLOTS = """
UPDATE trips
SET occasions = (
    SELECT jsonb_agg(
        CASE WHEN entry ? 'slot' THEN entry ELSE entry || '{"slot": "day"}'::jsonb END
        ORDER BY ord
    )
    FROM jsonb_array_elements(occasions) WITH ORDINALITY AS t(entry, ord)
)
WHERE EXISTS (
    SELECT 1 FROM jsonb_array_elements(occasions) AS e(entry) WHERE NOT (entry ? 'slot')
)
"""

# The reverse, and it is what keeps the down-then-up cycle a test of the fill
# above rather than a no-op over rows that already carry the key.
_STRIP_OCCASION_SLOTS = """
UPDATE trips
SET occasions = (
    SELECT jsonb_agg(entry - 'slot' ORDER BY ord)
    FROM jsonb_array_elements(occasions) WITH ORDINALITY AS t(entry, ord)
)
WHERE EXISTS (
    SELECT 1 FROM jsonb_array_elements(occasions) AS e(entry) WHERE entry ? 'slot'
)
"""


def upgrade() -> None:
    # The order of the four steps below cannot be permuted, and the CHECK is
    # why: it is false for every trip look in the database until the backfill
    # under it has run. Column, then data, then constraints.
    #
    # `TEXT` and no enum type, exactly as `occasion` is: nothing in the database
    # refuses a value outside the vocabulary, and `Slot` on the request schema
    # is the gate. What the two constraints below refuse is a bad *shape*.
    op.add_column("looks", sa.Column("slot", sa.Text(), nullable=True))

    # Every look that belongs to a trip today is a `day` look, because until
    # task 4.15 nothing can ask for anything else. `slot IS NULL` rather than an
    # unqualified UPDATE so that a re-run after a downgrade cannot overwrite a
    # slot written since.
    op.execute("UPDATE looks SET slot = 'day' WHERE trip_id IS NOT NULL AND slot IS NULL")
    op.execute(_FILL_OCCASION_SLOTS)

    # Raw DDL, and `0004` is why: `op.create_check_constraint` builds the
    # constraint on a MetaData carrying `target_metadata.naming_convention`, so
    # `ck_%(table_name)s_%(constraint_name)s` is applied to a name that already
    # holds it and `ck_looks_ck_looks_slot_belongs_to_a_trip` comes out.
    # Measured at 3.1 with `alembic upgrade --sql`, not reasoned from the
    # template. `0005` avoided the same trap through `create_table`, which
    # expands exactly once; there is no `create_table` here.
    op.execute(
        "ALTER TABLE looks ADD CONSTRAINT ck_looks_slot_belongs_to_a_trip "
        "CHECK ((trip_id IS NULL) = (slot IS NULL))"
    )

    # *Never `day` twice on one day*, as a fact of the database rather than of
    # `TripPackRequest`. An `Index` with `unique=True` rather than a
    # `UniqueConstraint` because a `UNIQUE` constraint cannot carry a `WHERE`.
    #
    # **The predicate is scope, and not a fix for a collision.** Under the
    # default `NULLS DISTINCT` two NULLs are never equal, so an unconditional
    # index would refuse nothing extra — the detached looks and every
    # `POST /looks/suggest` row would sit in it harmlessly. What `WHERE trip_id
    # IS NOT NULL` buys is four things. The invariant is about a **trip's**
    # shape, and the DDL says so rather than leaving a reader to derive it from
    # NULL semantics. An index over trip looks alone is the smaller structure
    # and the cheaper write on the path every suggestion takes. A future
    # `NULLS NOT DISTINCT` — shipped since PostgreSQL 15 and flippable for
    # reasons having nothing to do with slots — would otherwise start refusing
    # every second suggestion that shares a `for_date`, silently. And a wider
    # promise in the DDL invites a wider assumption from the next reader.
    #
    # It survives both writers as they are already ordered. `_write` detaches
    # the marked looks and deletes the rest before inserting any; `_replace_look`
    # detaches or deletes the one look it replaces before inserting its
    # successor. Neither holds two rows for one `(trip_id, for_date, slot)` at
    # any point inside its transaction.
    op.create_index(
        "uq_looks_trip_day_slot",
        "looks",
        ["trip_id", "for_date", "slot"],
        unique=True,
        postgresql_where=sa.text("trip_id IS NOT NULL"),
    )


# A downgrade to `0005` says this database has no slots, and `0005` cannot
# represent an evening: with the column gone, the two looks of one date are
# indistinguishable rows. **Measured at 4.12 against a planted two-slot day**
# rather than reasoned about — the cycle fails on the way back up, at the last
# statement of `upgrade()`:
#
#     sqlalchemy.exc.IntegrityError: (psycopg.errors.UniqueViolation)
#     could not create unique index "uq_looks_trip_day_slot"
#     DETAIL: Key (trip_id, for_date, slot)=(…, 2026-03-14, day) is duplicated.
#
# because the backfill has just given both rows `day`. The upgrade rolls back and
# the database is stuck at `0005` with nothing saying why.
#
# So this migration refuses instead. Deleting the evening looks here would make
# the cycle reversible by destroying rows a downgrade never announced it would
# touch; raising leaves that decision with whoever typed the command, which is
# `conftest.py`'s guard on `TEST_DATABASE_URL` one artefact along. On the test
# database the question does not arise — the suite leaks no rows, so a downgrade
# there is always over day-only data.
_EVENING_SURVIVORS = """
SELECT (SELECT count(*) FROM looks WHERE slot = 'evening')
     + (SELECT count(*) FROM trips, jsonb_array_elements(occasions) AS e(entry)
        WHERE entry ->> 'slot' = 'evening')
"""


def downgrade() -> None:
    surviving = op.get_bind().scalar(sa.text(_EVENING_SURVIVORS))
    if surviving:
        raise RuntimeError(
            "a downgrade would flatten every evening slot to 'day', and the "
            "next upgrade could not then build uq_looks_trip_day_slot. "
            f"Rows affected: {surviving}. Delete them deliberately first:\n"
            "  DELETE FROM looks WHERE slot = 'evening';\n"
            "  UPDATE trips SET occasions = ("
            " SELECT jsonb_agg(entry ORDER BY ord)"
            " FROM jsonb_array_elements(occasions) WITH ORDINALITY AS t(entry, ord)"
            " WHERE entry ->> 'slot' IS DISTINCT FROM 'evening');"
        )

    # The index is dropped explicitly although `DROP COLUMN` would take it —
    # and the CHECK — with the column it reads. `0004` and `0005` both read this
    # way, and a downgrade that names what it removes is one a reader can check
    # against the upgrade above.
    op.drop_index("uq_looks_trip_day_slot", table_name="looks")
    op.drop_column("looks", "slot")

    op.execute(_STRIP_OCCASION_SLOTS)

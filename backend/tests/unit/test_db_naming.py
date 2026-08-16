"""The constraint naming convention, which nothing else defends.

`app/db/base.py` pins the names SQLAlchemy generates. Changing it breaks no
other test in this suite, and that is not an oversight in the suite — it has no
runtime effect. The live schema comes from migration `0001`, which spells every
constraint name out as a literal, so the name PostgreSQL reports in an
`IntegrityError` is the migration's and never the convention's.

Which leaves a real seam with nothing across it: rename a constraint in `0001`
and the convention still produces the old name, or change the convention and
`0001` still produces the old name, and in both cases the model and the database
describe one constraint under two names with every test still green. The suite
cannot notice by running, either — `conftest.py` migrates once per session
against a container that usually already holds the revision, so an edited
migration is simply never executed.

So these two compare the artefacts directly rather than through behaviour. The
behaviour half is already covered: `test_register_rejects_a_duplicate_email` and
`test_upload_retries_the_batch_when_a_short_id_collides` both fail if the string
their route matches on stops being the name the database reports.
"""

from pathlib import Path

from app.db.base import Base
from app.models import item, user  # noqa: F401  — registers both tables on Base.metadata

MIGRATION_0001 = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_initial.py"

# Every constraint `0001` creates, under the name the convention expands to.
EXPECTED_NAMES = {
    "pk_users",
    "uq_users_email",
    "ck_users_height_cm_range",
    "pk_items",
    "uq_items_short_id",
    "ck_items_formality_range",
    "ck_items_warmth_range",
    "fk_items_user_id_users",
}

# The two the write paths match on by name, in a narrow `if` so that a violation
# nobody anticipated still becomes a 500 rather than a wrong answer (037).
MATCHED_BY_A_ROUTE = ("uq_users_email", "uq_items_short_id")


def _metadata_constraint_names() -> set[str]:
    return {
        constraint.name
        for table in Base.metadata.sorted_tables
        for constraint in table.constraints
        if constraint.name is not None
    }


def test_the_convention_produces_exactly_the_names_the_migration_spells() -> None:
    assert _metadata_constraint_names() == EXPECTED_NAMES


def test_the_names_the_routes_match_on_appear_literally_in_migration_0001() -> None:
    # Reading the migration as text rather than running it, because running it
    # proves nothing against a database that already holds the revision.
    source = MIGRATION_0001.read_text(encoding="utf-8")

    for name in MATCHED_BY_A_ROUTE:
        assert name in source
        assert name in _metadata_constraint_names()

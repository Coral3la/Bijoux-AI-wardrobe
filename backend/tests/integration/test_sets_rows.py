"""The table migration `0007` creates and the column it adds, against the
database.

`test_trips_rows.py`'s shape one migration on, and for its reasons: what these
cover is the half of the DDL no unit test can see. Here that is two cascades
pointing opposite ways — `ON DELETE CASCADE` from `users`, which takes the sets
with the account, and `ON DELETE SET NULL` from `item_sets`, which takes
nothing at all — plus the revision's own reversibility.

**The `SET NULL` is the one worth having.** It is the whole reason a set can be
deleted from a screen showing a photograph of a coat: `DELETE /sets/{set_id}`
withdraws a statement about garments and must leave the garments standing, and
one word of `0007` is what makes that true. Written as a Core `DELETE` rather
than `db.delete()`, because with no `relationship()` on either model this is
the database's behaviour and not SQLAlchemy's.

**The cycle test is new to this suite.** Nothing before `0007` asserted that a
`downgrade()` runs at all — `0006`'s deliberately refuses under a condition of
its own, and `0003`'s does nothing — so this is the first migration whose
reversal is a claim, and `02-DATA-MODEL.md` makes it in words. It runs alembic
against the same test database `conftest.py` migrated, which is why it puts the
schema back in a `finally`: an assertion that failed with the column dropped
would otherwise leave every later test in the session failing for a reason that
has nothing to do with them.

`tests/unit/test_db_naming.py` covers the other half — that the three
constraint names `0007` spells are the ones the convention generates.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.db.session import engine
from app.models.item import Item
from app.models.item_set import ItemSet
from app.models.user import User

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Everything `0007` builds, in one query, so "clean" is a set comparison rather
# than four assertions that could each be forgotten. The index and the foreign
# key are named here because `DROP COLUMN` would take both without being asked
# — which is exactly what a downgrade that names them must not rely on.
_OBJECTS = text(
    "SELECT 'item_sets' FROM information_schema.tables WHERE table_name = 'item_sets' "
    "UNION ALL "
    "SELECT 'items.set_id' FROM information_schema.columns "
    "WHERE table_name = 'items' AND column_name = 'set_id' "
    "UNION ALL "
    "SELECT indexname FROM pg_indexes WHERE indexname = 'idx_items_set_id' "
    "UNION ALL "
    "SELECT conname FROM pg_constraint WHERE conname = 'fk_items_set_id_item_sets'"
)

BUILT = {"item_sets", "items.set_id", "idx_items_set_id", "fk_items_set_id_item_sets"}


def _objects() -> set[str]:
    # Its own connection rather than the `db` fixture's, because that one holds
    # an open transaction for the whole test and the DDL below runs outside it.
    with engine.connect() as conn:
        return set(conn.scalars(_OBJECTS))


@pytest.fixture
def alembic_config(_schema: None) -> Config:
    """`conftest.py`'s configuration, rebuilt so this test can drive it directly.

    `_schema` rather than `db`, and the difference is the point: this test wants
    the database migrated and wants no transaction open against it.
    """
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["configure_logger"] = False
    return config


def test_the_revision_upgrades_downgrades_and_upgrades_again_cleanly(
    alembic_config: Config,
) -> None:
    """Down to `0006` and back, with nothing left behind in either direction.

    `conftest.py` has already run the upgrade, so the first assertion is the
    state every other test in this file stands on. The re-upgrade is the half
    that a partial `downgrade()` would fail: leave the table behind and
    `create_table` raises, leave the column behind and `add_column` does.

    The pool is disposed around the cycle. `ALTER TABLE items DROP COLUMN`
    changes the shape of a table every pooled connection has already prepared
    statements against, and a connection that survived the drop can meet the
    re-added column with `cached plan must not change result type` — in a later
    test, with nothing pointing back here.
    """
    assert _objects() == BUILT

    engine.dispose()
    command.downgrade(alembic_config, "0006")
    try:
        assert _objects() == set()
    finally:
        command.upgrade(alembic_config, "head")
        engine.dispose()

    assert _objects() == BUILT


def test_deleting_a_set_clears_its_members_and_deletes_no_item(
    db: Session,
    make_user: Callable[..., User],
    make_item: Callable[..., Item],
) -> None:
    # `ON DELETE SET NULL`, which is the one word of `0007` that makes
    # `DELETE /sets/{set_id}` safe to offer. A `CASCADE` here would answer the
    # same 204 and take two garments with it.
    user = make_user()
    item_set = ItemSet(user_id=user.id, name="the linen suit")
    db.add(item_set)
    db.flush()
    items = [make_item(user_id=user.id, set_id=item_set.id) for _ in range(2)]
    db.commit()

    db.execute(delete(ItemSet).where(ItemSet.id == item_set.id))
    db.commit()

    for item in items:
        db.refresh(item)
        assert item.set_id is None
    assert db.scalar(select(func.count()).select_from(Item).where(Item.user_id == user.id)) == 2


def test_deleting_a_user_deletes_their_sets(db: Session, make_user: Callable[..., User]) -> None:
    user = make_user()
    db.add(ItemSet(user_id=user.id))
    db.commit()

    db.execute(delete(User).where(User.id == user.id))
    db.commit()

    assert (
        db.scalar(select(func.count()).select_from(ItemSet).where(ItemSet.user_id == user.id)) == 0
    )

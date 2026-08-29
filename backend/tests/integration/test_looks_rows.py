"""The two tables migration `0002` creates, measured against the database.

Nothing writes a look yet — `POST /looks/suggest` is 2.7's — so these plant
rows through the ORM. What they cover is the half of the DDL that is not a
column list and that no unit test can see: the composite primary key, and the
two `ON DELETE CASCADE` paths that decide what happens to a look when the user
or the look itself goes away.

Migration `0004`'s `feedback` CHECK and its two indexes are here for the same
reason. `FEEDBACK_UP` and `FEEDBACK_DOWN` are readable without a database and
the constraint built from them is not, so what the CHECK tests assert is that
the numbers in the module and the numbers in the column are the same numbers.

The indexes are the harder half: an index changes no result, only the plan, so
deleting both from the migration leaves every other test in this suite green.
Measured — that mutation was run, and the test below is what it bought.

`tests/unit/test_db_naming.py` covers the other half — that the constraint names
`0002` and `0004` spell are the ones the convention generates.
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Connection, delete, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.item import Item
from app.models.look import FEEDBACK_DOWN, FEEDBACK_UP, Look, LookItem
from app.models.user import User


@pytest.fixture
def statements(connection: Connection) -> Iterator[list[str]]:
    """Every statement the session emits, in order, whitespace collapsed.

    `test_server_defaults.py`'s fixture, deliberately copied rather than moved
    to `conftest.py`: it is four lines, and the two files measure different
    claims about different tables.
    """
    recorded: list[str] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        recorded.append(" ".join(statement.split()))

    event.listen(connection, "before_cursor_execute", record)
    yield recorded
    event.remove(connection, "before_cursor_execute", record)


def _look_items(db: Session, look_id: uuid.UUID) -> int:
    return (
        db.scalar(select(func.count()).select_from(LookItem).where(LookItem.look_id == look_id))
        or 0
    )


def test_a_look_returns_its_server_defaults_from_the_insert(
    db: Session, make_user: Callable[..., User], statements: list[str]
) -> None:
    # `is_saved` is the one that matters: 2.7 persists every suggestion with it
    # false and never sets it, so if the INSERT does not bring the default back,
    # the value the route holds came from a second query or from nowhere.
    user = make_user()

    look = Look(user_id=user.id, occasion="work", for_date=date(2026, 3, 14))
    db.add(look)
    db.commit()

    inserts = [s for s in statements if s.upper().startswith("INSERT INTO LOOKS")]
    assert "RETURNING looks.id" in inserts[0]
    assert "looks.is_saved" in inserts[0]
    assert "looks.created_at" in inserts[0]
    assert look.is_saved is False


def test_the_same_item_cannot_be_in_one_look_twice(
    db: Session, make_user: Callable[..., User], make_item: Callable[..., Item]
) -> None:
    user = make_user()
    item = make_item(user_id=user.id)
    look = Look(user_id=user.id)
    db.add(look)
    db.commit()
    db.add(LookItem(look_id=look.id, item_id=item.id))
    db.commit()

    db.add(LookItem(look_id=look.id, item_id=item.id))
    with pytest.raises(IntegrityError) as exc_info:
        db.commit()

    assert "pk_look_items" in str(exc_info.value)
    db.rollback()


def test_deleting_a_look_deletes_its_rows_in_look_items(
    db: Session, make_user: Callable[..., User], make_item: Callable[..., Item]
) -> None:
    user = make_user()
    look = Look(user_id=user.id)
    db.add(look)
    db.commit()
    db.add_all([LookItem(look_id=look.id, item_id=make_item(user_id=user.id).id) for _ in range(3)])
    db.commit()

    # A Core DELETE rather than `db.delete(look)`: with no relationship on the
    # model, this is the database's cascade and not SQLAlchemy's.
    db.execute(delete(Look).where(Look.id == look.id))
    db.commit()

    assert _look_items(db, look.id) == 0


def test_deleting_a_user_deletes_their_looks(
    db: Session, make_user: Callable[..., User], make_item: Callable[..., Item]
) -> None:
    user = make_user()
    look = Look(user_id=user.id)
    db.add(look)
    db.commit()
    db.add(LookItem(look_id=look.id, item_id=make_item(user_id=user.id).id))
    db.commit()

    db.execute(delete(User).where(User.id == user.id))
    db.commit()

    assert db.scalar(select(func.count()).select_from(Look).where(Look.user_id == user.id)) == 0
    assert _look_items(db, look.id) == 0


def test_a_look_starts_unrated_and_unworn(db: Session, make_user: Callable[..., User]) -> None:
    # NULL rather than 0: `feedback` has no server default, so "nobody has
    # rated this" and "somebody rated it neutrally" cannot be the same value.
    look = Look(user_id=make_user().id)
    db.add(look)
    db.commit()

    assert look.feedback is None
    assert look.worn_at is None


@pytest.mark.parametrize("feedback", [FEEDBACK_UP, FEEDBACK_DOWN, None])
def test_the_feedback_check_admits_the_two_named_values_and_null(
    db: Session, make_user: Callable[..., User], feedback: int | None
) -> None:
    look = Look(user_id=make_user().id, feedback=feedback)
    db.add(look)
    db.commit()

    assert look.feedback == feedback


@pytest.mark.parametrize("feedback", [0, 2, -2])
def test_the_feedback_check_refuses_anything_else(
    db: Session, make_user: Callable[..., User], feedback: int
) -> None:
    # 0 is the one that matters: it is what an unrated look would hold if the
    # column had a default, and it is the value a client sends by mistake.
    db.add(Look(user_id=make_user().id, feedback=feedback))

    with pytest.raises(IntegrityError) as exc_info:
        db.commit()

    assert "ck_looks_feedback_values" in str(exc_info.value)
    db.rollback()


def test_the_two_indexes_0004_builds_exist(db: Session) -> None:
    # `tests/unit/test_db_naming.py` compares the convention against the
    # constraint names and explicitly cannot see an index, because
    # `Table.constraints` does not hold one. This is that comparison for the
    # two `AUDITS.md` O-25 deferred, made against the database rather than
    # against the metadata: their only readers are 3.2 and 3.5, and a query
    # plan is not something a test in this project asserts on.
    built = set(
        db.scalars(
            text("SELECT indexname FROM pg_indexes WHERE tablename IN ('looks', 'look_items')")
        )
    )

    assert {"idx_looks_user_id", "idx_look_items_item_id"} <= built

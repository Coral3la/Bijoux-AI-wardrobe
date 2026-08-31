"""The table migration `0005` creates and the column it adds, against the
database.

`test_looks_rows.py`'s shape one migration on, and for its reasons. Nothing
writes a trip yet — `pack_trip` is 4.3's and `POST /trips/pack` is 4.4's — so
these plant rows through the ORM. What they cover is the half of the DDL no
unit test can see: the two `ON DELETE CASCADE` paths, the `end_date >=
start_date` CHECK, and the two indexes.

The cascade from `trips` to `looks` is the one worth having. It reaches
`look_items` in a second hop that no line of DDL in `0005` mentions — `0002`
wrote that half — so a trip deleted with looks under it is the only place the
chain is asserted end to end.

The indexes are the harder half, as they were at 3.1: an index changes no
result, only the plan, so deleting both from the migration leaves every other
test in this suite green.

`tests/unit/test_db_naming.py` covers the other half — that the three
constraint names `0005` spells are the ones the convention generates.
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
from app.models.look import Look, LookItem
from app.models.trip import Trip
from app.models.user import User


@pytest.fixture
def statements(connection: Connection) -> Iterator[list[str]]:
    """Every statement the session emits, in order, whitespace collapsed.

    `test_looks_rows.py`'s fixture, copied for the reason that one was copied
    from `test_server_defaults.py`: it is four lines, and the three files
    measure different claims about different tables.
    """
    recorded: list[str] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        recorded.append(" ".join(statement.split()))

    event.listen(connection, "before_cursor_execute", record)
    yield recorded
    event.remove(connection, "before_cursor_execute", record)


def _trip(user_id: uuid.UUID, **overrides: Any) -> Trip:
    fields: dict[str, Any] = {
        "user_id": user_id,
        "destination": "Berlin",
        "start_date": date(2026, 3, 14),
        "end_date": date(2026, 3, 17),
    }
    return Trip(**(fields | overrides))


def _look_items(db: Session, look_id: uuid.UUID) -> int:
    return (
        db.scalar(select(func.count()).select_from(LookItem).where(LookItem.look_id == look_id))
        or 0
    )


def test_a_trip_returns_its_server_defaults_from_the_insert(
    db: Session, make_user: Callable[..., User], statements: list[str]
) -> None:
    # `occasions` is the one that matters. It is NOT NULL with a default, so a
    # trip inserted without one holds `[]` — and if the INSERT does not bring
    # that back, the value the route holds came from a second query or from
    # nowhere. `created_at` is the same claim `looks` makes one table over.
    trip = _trip(make_user().id)
    db.add(trip)
    db.commit()

    inserts = [s for s in statements if s.upper().startswith("INSERT INTO TRIPS")]
    assert "RETURNING trips.id" in inserts[0]
    assert "trips.occasions" in inserts[0]
    assert "trips.created_at" in inserts[0]
    assert trip.occasions == []


def test_a_trip_starts_with_no_forecast_and_no_packing_list(
    db: Session, make_user: Callable[..., User]
) -> None:
    # NULL rather than an empty object, and the distinction is 4.3's: a trip
    # that has not been packed and a trip whose packing list came back empty
    # cannot be the same value.
    trip = _trip(make_user().id)
    db.add(trip)
    db.commit()

    assert trip.forecast is None
    assert trip.packing_list is None
    assert trip.notes is None


def test_a_look_belongs_to_no_trip_by_default(db: Session, make_user: Callable[..., User]) -> None:
    # Every look this project has written so far is one of these, and
    # `POST /looks/suggest` goes on writing them after Stage 4.
    look = Look(user_id=make_user().id)
    db.add(look)
    db.commit()

    assert look.trip_id is None


def test_deleting_a_user_deletes_their_trips(db: Session, make_user: Callable[..., User]) -> None:
    user = make_user()
    db.add(_trip(user.id))
    db.commit()

    db.execute(delete(User).where(User.id == user.id))
    db.commit()

    assert db.scalar(select(func.count()).select_from(Trip).where(Trip.user_id == user.id)) == 0


def test_deleting_a_trip_deletes_its_looks_and_their_items(
    db: Session,
    make_user: Callable[..., User],
    make_item: Callable[..., Item],
) -> None:
    # The chain `0005` opens and does not itself spell: trips -> looks is this
    # migration's cascade, looks -> look_items is `0002`'s, and nothing else
    # asserts the two together. A Core DELETE rather than `db.delete(trip)`,
    # because with no relationship on the model this is the database's cascade
    # and not SQLAlchemy's.
    user = make_user()
    trip = _trip(user.id)
    db.add(trip)
    db.commit()

    look = Look(user_id=user.id, trip_id=trip.id)
    db.add(look)
    db.commit()
    db.add(LookItem(look_id=look.id, item_id=make_item(user_id=user.id).id))
    db.commit()

    db.execute(delete(Trip).where(Trip.id == trip.id))
    db.commit()

    assert db.scalar(select(func.count()).select_from(Look).where(Look.id == look.id)) == 0
    assert _look_items(db, look.id) == 0


def test_deleting_a_trip_leaves_a_look_that_was_never_on_it(
    db: Session, make_user: Callable[..., User]
) -> None:
    # The cascade is keyed on the column and not on the account. Without this,
    # a `DELETE` that took every look the user owned would pass every other
    # test in this file.
    user = make_user()
    trip = _trip(user.id)
    db.add(trip)
    db.commit()
    loose = Look(user_id=user.id)
    db.add(loose)
    db.commit()

    db.execute(delete(Trip).where(Trip.id == trip.id))
    db.commit()

    assert db.scalar(select(func.count()).select_from(Look).where(Look.id == loose.id)) == 1


def test_the_date_order_check_admits_a_one_day_trip(
    db: Session, make_user: Callable[..., User]
) -> None:
    # `>=`, not `>`. A trip that leaves and returns on one day is the shortest
    # legal trip, and it is the case a `>` would have refused.
    day = date(2026, 3, 14)
    trip = _trip(make_user().id, start_date=day, end_date=day)
    db.add(trip)
    db.commit()

    assert trip.start_date == trip.end_date


def test_the_date_order_check_refuses_an_end_before_its_start(
    db: Session, make_user: Callable[..., User]
) -> None:
    db.add(_trip(make_user().id, start_date=date(2026, 3, 17), end_date=date(2026, 3, 14)))

    with pytest.raises(IntegrityError) as exc_info:
        db.commit()

    # The *whole* name PostgreSQL reports, not a substring of it. Written this
    # way because the substring version passed against a database holding
    # `ck_trips_ck_trips_date_order` — the doubled name migration `0001`
    # produced three times and `0005` was one comment away from producing a
    # fourth. `in` cannot tell those two apart; `pg_constraint` can.
    assert "ck_trips_date_order" in str(exc_info.value)
    assert "ck_trips_ck_trips" not in str(exc_info.value)
    db.rollback()


def test_the_constraints_0005_builds_carry_the_names_the_convention_expands(
    db: Session,
) -> None:
    # `test_db_naming.py` compares `Base.metadata` against a written list, so
    # both halves of it can say `ck_trips_date_order` while the database says
    # something else — which is the state `0001` has been in since Stage 0 and
    # that file's own docstring describes without being able to detect. This
    # asks PostgreSQL.
    built = set(
        db.scalars(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'trips'::regclass OR conname = 'fk_looks_trip_id_trips'"
            )
        )
    )

    assert {
        "pk_trips",
        "fk_trips_user_id_users",
        "ck_trips_date_order",
        "fk_looks_trip_id_trips",
    } <= built


def test_the_two_indexes_0005_builds_exist(db: Session) -> None:
    # 3.1's test one migration on, and for its reason: `test_db_naming.py`
    # compares the convention against constraint names and explicitly cannot
    # see an index, because `Table.constraints` does not hold one.
    built = set(
        db.scalars(text("SELECT indexname FROM pg_indexes WHERE tablename IN ('trips', 'looks')"))
    )

    assert {"idx_trips_user_id", "idx_looks_trip_id"} <= built

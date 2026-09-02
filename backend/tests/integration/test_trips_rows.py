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

**Migration `0006`'s two objects are here for the same reasons, and one of them
is stronger than anything above.** The CHECK ties `trip_id` and `slot` together
in both directions, and `uq_looks_trip_day_slot` refuses a second `day` look on
one date — a unique index changes a *result*, not a plan, so it is asserted by
what it refuses rather than by its presence in `pg_indexes`.

**The predicate is the one thing here no behaviour can defend.** Under the
default `NULLS DISTINCT` two NULLs are never equal, so deleting `WHERE trip_id
IS NOT NULL` refuses nothing new and every test below stays green — O-25's "an
index changes no result" surviving inside an object the rest of which does
change one. So the predicate is asserted against `pg_indexes.indexdef`
directly, which is the only assertion that fails when it goes.
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Connection, delete, event, func, select, text, update
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

    look = Look(user_id=user.id, trip_id=trip.id, slot="day")
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


def test_a_trip_look_must_carry_a_slot(db: Session, make_user: Callable[..., User]) -> None:
    # The half of `0006`'s CHECK that protects every reader: `_by_day` places a
    # look by `(for_date, slot)`, and a trip look with no slot is a look that
    # cannot be placed on either card of its day.
    user = make_user()
    trip = _trip(user.id)
    db.add(trip)
    db.commit()

    db.add(Look(user_id=user.id, trip_id=trip.id))

    with pytest.raises(IntegrityError) as exc_info:
        db.commit()

    # The whole name, and the doubled spelling asserted absent — `0005`'s test,
    # written this way because the substring version passed against a database
    # holding `ck_trips_ck_trips_date_order`.
    assert "ck_looks_slot_belongs_to_a_trip" in str(exc_info.value)
    assert "ck_looks_ck_looks" not in str(exc_info.value)
    db.rollback()


def test_a_look_with_no_trip_may_not_carry_a_slot(
    db: Session, make_user: Callable[..., User]
) -> None:
    # The other direction, and the reason the CHECK is `=` rather than an
    # implication: a slot is meaningless off a trip, so `POST /looks/suggest`'s
    # looks cannot acquire one and a detach cannot leave one behind.
    db.add(Look(user_id=make_user().id, slot="day"))

    with pytest.raises(IntegrityError) as exc_info:
        db.commit()

    assert "ck_looks_slot_belongs_to_a_trip" in str(exc_info.value)
    db.rollback()


def test_one_date_carries_a_day_look_and_an_evening_look(
    db: Session, make_user: Callable[..., User]
) -> None:
    # The row shape the whole feature is for, asserted before the refusal below
    # so that a unique index over the wrong columns fails here rather than
    # passing everything.
    user = make_user()
    trip = _trip(user.id)
    db.add(trip)
    db.commit()

    db.add_all(
        [
            Look(user_id=user.id, trip_id=trip.id, for_date=trip.start_date, slot="day"),
            Look(user_id=user.id, trip_id=trip.id, for_date=trip.start_date, slot="evening"),
        ]
    )
    db.commit()

    assert db.scalar(select(func.count()).select_from(Look).where(Look.trip_id == trip.id)) == 2


def test_a_second_day_look_on_one_date_is_refused(
    db: Session, make_user: Callable[..., User]
) -> None:
    # *Never `day` twice on one day*, as a fact of the database. Without this
    # index the invariant lives only in `TripPackRequest`, and a row written by
    # anything else — a script, a repack whose validator drifted — leaves a day
    # wearing two outfits and an evening undressed.
    user = make_user()
    trip = _trip(user.id)
    db.add(trip)
    db.commit()

    db.add(Look(user_id=user.id, trip_id=trip.id, for_date=trip.start_date, slot="day"))
    db.commit()
    db.add(Look(user_id=user.id, trip_id=trip.id, for_date=trip.start_date, slot="day"))

    with pytest.raises(IntegrityError) as exc_info:
        db.commit()

    assert "uq_looks_trip_day_slot" in str(exc_info.value)
    db.rollback()


def test_a_repack_may_detach_both_of_one_date_s_looks(
    db: Session, make_user: Callable[..., User]
) -> None:
    # `AUDITS.md` O-32's detach on a two-slot day: both looks were saved, both
    # leave the trip, and the two rows they become are legal. This does *not*
    # defend the index's predicate — under `NULLS DISTINCT` two rows of
    # `(NULL, date, NULL)` are distinct with it or without it — and the
    # docstring above names the assertion that does. What it pins is the pair of
    # columns the detach writes: drop `slot=None` from the UPDATE and the CHECK
    # fails here.
    user = make_user()
    trip = _trip(user.id)
    db.add(trip)
    db.commit()

    db.add_all(
        [
            Look(user_id=user.id, trip_id=trip.id, for_date=trip.start_date, slot="day"),
            Look(user_id=user.id, trip_id=trip.id, for_date=trip.start_date, slot="evening"),
        ]
    )
    db.commit()

    db.execute(update(Look).where(Look.trip_id == trip.id).values(trip_id=None, slot=None))
    db.commit()

    detached = db.scalars(
        select(Look).where(Look.user_id == user.id, Look.for_date == trip.start_date)
    ).all()
    assert len(detached) == 2
    assert {look.slot for look in detached} == {None}


def test_the_objects_0006_builds_exist(db: Session) -> None:
    # 3.1's and 4.1's artefact checks for this migration's two, which is the
    # comparison `test_db_naming.py` cannot make: it reads `Table.constraints`,
    # and that holds neither an index nor — because this one is spelled as a
    # partial index — the uniqueness rule beside it.
    constraints = set(
        db.scalars(text("SELECT conname FROM pg_constraint WHERE conrelid = 'looks'::regclass"))
    )
    indexes = set(db.scalars(text("SELECT indexname FROM pg_indexes WHERE tablename = 'looks'")))

    assert "ck_looks_slot_belongs_to_a_trip" in constraints
    assert "uq_looks_trip_day_slot" in indexes


def test_the_unique_index_is_scoped_to_trip_looks(db: Session) -> None:
    # The predicate, asserted against the definition because nothing else can
    # see it: removing `WHERE trip_id IS NOT NULL` changes no result under
    # `NULLS DISTINCT`, so every other test in this file passes without it. What
    # the scope buys is written down in `0006` — the invariant belongs to trip
    # looks, the index stays off every `POST /looks/suggest` row, and a future
    # `NULLS NOT DISTINCT` cannot turn it into a refusal of every second
    # suggestion that shares a `for_date`.
    definition = db.scalar(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_looks_trip_day_slot'")
    )

    assert definition is not None
    assert "UNIQUE INDEX" in definition
    assert "WHERE (trip_id IS NOT NULL)" in definition

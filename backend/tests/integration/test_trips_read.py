"""`GET /trips`, `GET /trips/{id}` and `DELETE /trips/{id}`.

**No AI, no geocoder and no forecast.** All three endpoints read rows that
`POST /trips/pack` wrote, so these plant them directly — `test_trips_rows.py`'s
approach one layer up, and the reason the pack tests live in their own file.
What is measured here is the half of the trip object no fake can reach: the
merge of two JSON columns with the looks, the ordering, the isolation, and the
cascade.

The planted `forecast` and `packing_list` are the shapes `02-DATA-MODEL.md`
prints. Nothing in the database enforces either, so a test that planted
something else would pass while describing a row this API cannot produce.
"""

import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import Category, ItemStatus, Layer
from app.models.item import Item
from app.models.look import Look, LookItem
from app.models.trip import Trip
from app.models.user import User

START = date(2026, 3, 14)

RULE = "Use warmth 2-3 for the base. A mid layer or light outerwear is optional."


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user()


@pytest.fixture
def garments(user: User, make_item: Callable[..., Item], cloudinary_configured: None) -> list[Item]:
    return [
        make_item(
            user_id=user.id,
            status=ItemStatus.READY,
            category=category,
            layer=Layer.BASE if category is not Category.SHOES else Layer.STANDALONE,
        )
        for category in (Category.SHOES, Category.TOP, Category.BOTTOM)
    ]


@pytest.fixture
def make_trip(db: Session) -> Callable[..., Trip]:
    """A trip row with the two JSON columns filled the way `pack_trip` fills them."""

    def _make(
        user_id: uuid.UUID,
        days: int = 3,
        start: date = START,
        item_ids: list[uuid.UUID] | None = None,
        **columns: Any,
    ) -> Trip:
        packed = [str(item_id) for item_id in (item_ids or [])]
        trip = Trip(
            user_id=user_id,
            destination=columns.pop("destination", "Berlin"),
            dest_lat=52.52,
            dest_lon=13.41,
            start_date=start,
            end_date=start + timedelta(days=days - 1),
            occasions=[
                {"day": day, "slot": "day", "occasion": "work"} for day in range(1, days + 1)
            ],
            forecast=[
                {
                    "day": day,
                    "date": (start + timedelta(days=day - 1)).isoformat(),
                    "temp_min_c": 8.0,
                    "temp_max_c": 12.0 + day,
                    "precip_mm": 0.0,
                    "wind_kph": 9.0,
                    "condition": "clear",
                    "rule": RULE,
                }
                for day in range(1, days + 1)
            ],
            packing_list={
                "item_ids": packed,
                "reuse_summary": {
                    "item_count": len(packed),
                    "look_count": days,
                    "most_reused": None,
                },
            },
            **columns,
        )
        db.add(trip)
        db.commit()
        return trip

    return _make


@pytest.fixture
def make_trip_look(db: Session) -> Callable[..., Look]:
    def _make(trip: Trip, day: int, items: list[Item], **columns: Any) -> Look:
        look = Look(
            user_id=trip.user_id,
            trip_id=trip.id,
            title=f"Day {day}",
            occasion="work",
            # `0006`'s CHECK reads `trip_id` and `slot` together, so a trip look
            # planted directly carries one. `day` because until task 4.15 no
            # request can produce anything else — the routes write the same
            # literal.
            slot="day",
            reasoning="The straight jean balances the oversized shirt.",
            weather_note="13°C — a light layer.",
            for_date=trip.start_date + timedelta(days=day - 1),
            **columns,
        )
        db.add(look)
        db.flush()
        db.add_all(
            [
                LookItem(look_id=look.id, item_id=item.id, position=position)
                for position, item in enumerate(items)
            ]
        )
        db.commit()
        return look

    return _make


# --- GET /trips -------------------------------------------------------------


def test_the_list_is_newest_first_with_a_total(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_trip: Callable[..., Trip],
) -> None:
    older = make_trip(user.id, destination="Lisbon")
    newer = make_trip(user.id, destination="Berlin")
    # `created_at` is a server default, so two rows written in one transaction
    # can share it; the ordering is stated by moving one rather than by hoping.
    older.created_at = datetime.fromisoformat("2026-01-01T09:00:00+00:00")
    db.commit()

    payload = client.get("/api/v1/trips", headers=authorization(user)).json()

    assert [trip["destination"] for trip in payload["trips"]] == ["Berlin", "Lisbon"]
    assert payload["total"] == 2
    assert {trip["id"] for trip in payload["trips"]} == {str(newer.id), str(older.id)}


def test_the_list_carries_whole_trip_objects_and_no_looks(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    """One shape for one resource — `DECISIONS.md` 034's rule, and 195's reading of it."""
    trip = make_trip(user.id, item_ids=[item.id for item in garments])
    look = make_trip_look(trip, 1, garments)

    payload = client.get("/api/v1/trips", headers=authorization(user)).json()

    listed = payload["trips"][0]
    assert "looks" not in listed
    assert len(listed["days"]) == 3
    assert listed["packing_list"]["item_ids"] == [str(item.id) for item in garments]
    # The day strip still carries its look ids, which is why the list endpoint
    # cannot skip the join even though it answers no looks.
    assert listed["days"][0]["look_id"] == str(look.id)


def test_the_list_pages_and_counts_the_whole_set(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_trip: Callable[..., Trip],
) -> None:
    for _ in range(3):
        make_trip(user.id)

    payload = client.get("/api/v1/trips?limit=2&offset=1", headers=authorization(user)).json()

    assert len(payload["trips"]) == 2
    assert payload["total"] == 3


def test_the_list_holds_only_this_accounts_trips(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_user: Callable[..., User],
    make_trip: Callable[..., Trip],
) -> None:
    make_trip(user.id, destination="Berlin")
    make_trip(make_user().id, destination="Lisbon")

    payload = client.get("/api/v1/trips", headers=authorization(user)).json()

    assert [trip["destination"] for trip in payload["trips"]] == ["Berlin"]
    assert payload["total"] == 1


def test_an_out_of_range_limit_is_validation_error(
    client: TestClient, user: User, authorization: Callable[[User], dict[str, str]]
) -> None:
    response = client.get("/api/v1/trips?limit=500", headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_listing_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/trips")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


# --- GET /trips/{id} --------------------------------------------------------


def test_a_trip_answers_its_looks_as_a_sibling_key(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    trip = make_trip(user.id, item_ids=[item.id for item in garments])
    looks = [make_trip_look(trip, day, garments) for day in (1, 2, 3)]

    payload = client.get(f"/api/v1/trips/{trip.id}", headers=authorization(user)).json()

    assert payload["trip"]["id"] == str(trip.id)
    assert [look["id"] for look in payload["looks"]] == [str(look.id) for look in looks]
    # `missing_pieces` described the run that made the plan and was never
    # stored, so a reopened trip cannot carry it.
    assert "missing_pieces" not in payload


def test_the_days_carry_the_stored_rule_and_the_requested_occasion(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_trip: Callable[..., Trip],
) -> None:
    trip = make_trip(user.id)

    days = client.get(f"/api/v1/trips/{trip.id}", headers=authorization(user)).json()["trip"][
        "days"
    ]

    assert [day["day"] for day in days] == [1, 2, 3]
    assert [day["date"] for day in days] == [
        (START + timedelta(days=offset)).isoformat() for offset in range(3)
    ]
    assert {day["rule"] for day in days} == {RULE}
    assert {day["occasion"] for day in days} == {"work"}


def test_a_day_with_no_look_answers_a_null_look_id(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    """The state a repack's detach can produce, and the reason `look_id` is nullable.

    `DECISIONS.md` 195 refused pairing `days[i]` with `looks[i]` positionally
    precisely because that pairing fails silently here — it would shift day 3's
    look onto day 2 rather than leaving a gap.
    """
    trip = make_trip(user.id)
    make_trip_look(trip, 1, garments)
    make_trip_look(trip, 3, garments)

    days = client.get(f"/api/v1/trips/{trip.id}", headers=authorization(user)).json()["trip"][
        "days"
    ]

    assert [day["look_id"] is None for day in days] == [False, True, False]


def test_the_looks_come_back_in_date_order_however_they_were_written(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    """The `ORDER BY for_date` in the trip's own read, which nothing else defends.

    Written deliberately out of order — day 3, then day 1, then day 2 — because
    with no `order_by` the planner returns insertion order and every other test
    in this file writes its looks in the order it expects them back. A mutation
    run at 4.4 proved that: deleting the clause left all 1088 tests green.
    """
    trip = make_trip(user.id)
    for day in (3, 1, 2):
        make_trip_look(trip, day, garments)

    payload = client.get(f"/api/v1/trips/{trip.id}", headers=authorization(user)).json()

    assert [look["title"] for look in payload["looks"]] == ["Day 1", "Day 2", "Day 3"]


def test_the_looks_are_hydrated_in_look_items_position_order(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    """Without the `order_by` the planner returns what it likes and a reopened
    trip relayouts between two loads."""
    trip = make_trip(user.id)
    reversed_items = list(reversed(garments))
    make_trip_look(trip, 1, reversed_items)

    payload = client.get(f"/api/v1/trips/{trip.id}", headers=authorization(user)).json()

    assert [item["id"] for item in payload["looks"][0]["items"]] == [
        str(item.id) for item in reversed_items
    ]


def test_a_look_belonging_to_another_trip_is_not_answered(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    trip = make_trip(user.id)
    other = make_trip(user.id, destination="Lisbon")
    make_trip_look(trip, 1, garments)
    make_trip_look(other, 1, garments)

    payload = client.get(f"/api/v1/trips/{trip.id}", headers=authorization(user)).json()

    assert len(payload["looks"]) == 1


def test_another_accounts_trip_is_not_found(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_user: Callable[..., User],
    make_trip: Callable[..., Trip],
) -> None:
    """The same code and status as one that never existed — a 403 would confirm it."""
    trip = make_trip(make_user().id)

    response = client.get(f"/api/v1/trips/{trip.id}", headers=authorization(user))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_a_trip_that_never_existed_is_not_found(
    client: TestClient, user: User, authorization: Callable[[User], dict[str, str]]
) -> None:
    response = client.get(f"/api/v1/trips/{uuid.uuid4()}", headers=authorization(user))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# --- DELETE /trips/{id} -----------------------------------------------------


def test_deleting_a_trip_answers_204_with_no_body(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_trip: Callable[..., Trip],
) -> None:
    trip = make_trip(user.id)

    response = client.delete(f"/api/v1/trips/{trip.id}", headers=authorization(user))

    assert response.status_code == 204
    assert response.content == b""


def test_deleting_a_trip_takes_its_looks_and_their_items(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    """`AUDITS.md` O-32's option 1, taken deliberately for this endpoint.

    The cascade reaches `look_items` in a second hop through `0002`'s own, which
    no line of `0005` mentions — so this is where the chain is asserted end to
    end from the API rather than from the ORM.
    """
    trip = make_trip(user.id)
    look = make_trip_look(trip, 1, garments)
    # Held as plain UUIDs before the delete. Both rows stay in this session's
    # identity map afterwards, and reading `.id` off a deleted instance raises
    # `ObjectDeletedError` rather than answering — which would fail this test
    # for a reason that has nothing to do with the cascade.
    trip_id, look_id = trip.id, look.id

    client.delete(f"/api/v1/trips/{trip_id}", headers=authorization(user))

    # Counted rather than fetched, which is `test_trips_rows.py`'s idiom one
    # layer down: a count never touches the identity map.
    assert db.scalar(select(func.count()).select_from(Trip).where(Trip.id == trip_id)) == 0
    assert db.scalar(select(func.count()).select_from(Look).where(Look.id == look_id)) == 0
    assert (
        db.scalar(select(func.count()).select_from(LookItem).where(LookItem.look_id == look_id))
        == 0
    )
    # The garments themselves are untouched: a trip is deleted, not a wardrobe.
    assert db.scalar(select(func.count()).select_from(Item).where(Item.user_id == user.id)) == 3


def test_deleting_a_trip_leaves_a_saved_look_from_another_trip_alone(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_trip_look: Callable[..., Look],
) -> None:
    trip = make_trip(user.id)
    other = make_trip(user.id, destination="Lisbon")
    kept = make_trip_look(other, 1, garments, is_saved=True)
    make_trip_look(trip, 1, garments)

    client.delete(f"/api/v1/trips/{trip.id}", headers=authorization(user))

    db.expire_all()
    assert db.get(Look, kept.id) is not None


def test_a_look_that_belongs_to_no_trip_survives_a_delete(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    garments: list[Item],
    make_trip: Callable[..., Trip],
    make_look: Callable[..., Look],
) -> None:
    """`looks.trip_id` is nullable and `NULL` is the ordinary case."""
    trip = make_trip(user.id)
    loose = make_look(user_id=user.id, items=garments, title="An ordinary suggestion")

    client.delete(f"/api/v1/trips/{trip.id}", headers=authorization(user))

    db.expire_all()
    assert db.get(Look, loose.id) is not None


def test_deleting_another_accounts_trip_is_not_found(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_user: Callable[..., User],
    make_trip: Callable[..., Trip],
) -> None:
    trip = make_trip(make_user().id)

    response = client.delete(f"/api/v1/trips/{trip.id}", headers=authorization(user))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    db.expire_all()
    assert db.get(Trip, trip.id) is not None


def test_deleting_requires_a_token(
    client: TestClient, user: User, make_trip: Callable[..., Trip]
) -> None:
    trip = make_trip(user.id)

    response = client.delete(f"/api/v1/trips/{trip.id}")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"

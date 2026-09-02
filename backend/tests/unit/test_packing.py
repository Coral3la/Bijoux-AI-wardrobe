"""`pack_trip` — the orchestration `STAGE-4` 4.3 specifies.

No AI call, no network and no database: the geocoder, the forecast and the
stylist are all monkeypatched, and the function under test holds no `Session` by
construction (`DECISIONS.md` 196), so what is asserted here is the arithmetic
and the mapping rather than anybody's I/O.

**The stylist is patched on `packing`, not on `stylist_runner`.** `pack_trip`
imports `judged` by name, so that is the reference the call goes through —
`tests/integration/test_looks_suggest.py` patches one module further in for the
same reason, and both are the seam their own caller actually reads.
"""

import datetime
import uuid
from typing import Any

import pytest

from app.schemas.item import ItemResponse
from app.services import packing
from app.services.geocoding import GeocodingError, Location
from app.services.stylist import Look, LookValidation, MissingPiece, StylistResponse
from app.services.weather import Condition, Forecast

BERLIN = Location(name="Berlin", country="Germany", lat=52.52, lon=13.41)

TOP_ID = "A3F9K2"
JEANS_ID = "7BX1QM"
BOOTS_ID = "SEFA38"
TANK_ID = "TANK55"

START = datetime.date(2026, 3, 14)

MILD_RULE = "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional."


def _item(short_id: str, category: str) -> ItemResponse:
    return ItemResponse(
        id=uuid.uuid4(),
        short_id=short_id,
        status="ready",
        image_public_id="bijoux/demo/photograph",
        category=category,
        subcategory="thing",
        fit=None,
        length=None,
        rise=None,
        color_primary="black",
        color_secondary=None,
        pattern="solid",
        material="cotton",
        formality=2,
        warmth=2,
        layer="base",
        water_resistant=False,
        display_name="a thing",
        ai_confidence=0.9,
        error_message=None,
        is_archived=False,
        user_edited=False,
        attributes={},
        wear_count=0,
        last_worn_at=None,
        created_at=datetime.datetime(2026, 8, 26, tzinfo=datetime.UTC),
        updated_at=datetime.datetime(2026, 8, 26, tzinfo=datetime.UTC),
    )


TOP = _item(TOP_ID, "top")
JEANS = _item(JEANS_ID, "bottom")
BOOTS = _item(BOOTS_ID, "shoes")
TANK = _item(TANK_ID, "top")
WARDROBE = [TOP, JEANS, BOOTS, TANK]


class _User:
    """Only the three attributes `pack_trip` reads, so no database row is needed."""

    id = uuid.uuid4()
    height_cm = 165
    style_notes = "prefer high-rise"


def _slot(day: int, slot: str = "day", occasion: str = "work") -> packing.TripSlot:
    return packing.TripSlot(day=day, slot=slot, occasion=occasion)


def _request(days: int = 2, **overrides: Any) -> packing.TripRequest:
    fields: dict[str, Any] = {
        "destination": "Berlin",
        "start_date": START,
        "end_date": START + datetime.timedelta(days=days - 1),
        # One `day` slot per day unless a test asks for an evening, which is
        # what every trip this API can currently send looks like: the wire
        # carries no slot until 4.15.
        "occasions": tuple(_slot(day) for day in range(1, days + 1)),
        "notes": None,
    }
    return packing.TripRequest(**(fields | overrides))


def _forecast(offset: int) -> Forecast:
    return Forecast(
        date=START + datetime.timedelta(days=offset),
        temp_min_c=14.0,
        temp_max_c=18.0,
        precip_mm=0.0,
        wind_kph=9.0,
        condition=Condition.CLOUDY,
    )


def _answer(*looks: Look, packing_list: tuple[str, ...] | None = None) -> StylistResponse:
    packed = (
        packing_list
        if packing_list is not None
        else tuple(dict.fromkeys(item_id for look in looks for item_id in look.item_ids))
    )
    return StylistResponse(
        looks=looks,
        missing_pieces=(MissingPiece(category="shoes", description="a flat", reason="none"),),
        message="Two days in Berlin.",
        packing_list=packed,
    )


def _look(day: int, *item_ids: str, slot: str = "day") -> Look:
    return Look(
        title=f"Day {day} {slot}",
        item_ids=item_ids,
        reasoning="r",
        weather_note="w",
        day=day,
        slot=slot,
    )


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Geocoder, forecast and stylist, all recorded rather than called."""

    def _install(
        answer: StylistResponse, *, days: int = 2, violation: str | None = None
    ) -> dict[str, Any]:
        seen: dict[str, Any] = {}

        async def _search(query: str) -> list[Location]:
            seen["query"] = query
            return [BERLIN]

        async def _daily(
            lat: float, lon: float, start: datetime.date, end: datetime.date
        ) -> list[Forecast]:
            seen["coords"] = (lat, lon)
            return [_forecast(offset) for offset in range(days)]

        async def _judged(wardrobe: Any, context: Any) -> LookValidation:
            seen["context"] = context
            seen["wardrobe"] = wardrobe
            return LookValidation(response=answer, violation=violation)

        monkeypatch.setattr(packing, "search_locations", _search)
        monkeypatch.setattr(packing, "get_daily_forecast", _daily)
        monkeypatch.setattr(packing, "judged", _judged)
        return seen

    return _install


# --- the reuse target -------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [(1, 4), (2, 8), (3, 11), (4, 12), (5, 13), (7, 15), (14, 22)],
)
def test_the_reuse_target_is_the_smaller_of_the_two_formulas(days: int, expected: int) -> None:
    # `min(days * 4, days + 8)`: the multiplication wins to day 2 and the
    # addition from day 3 on, which is where a packing list starts to be a
    # packing list rather than a pile of outfits.
    assert packing.reuse_target(days) == expected


@pytest.mark.asyncio
async def test_the_reuse_target_is_computed_from_days_and_not_from_looks(wired: Any) -> None:
    # A two-day trip with an evening out asks the model for three looks and
    # still gets day 2's ceiling of eight items. Deliberate pressure toward the
    # reuse this feature exists for, and `DECISIONS.md` 225 takes it knowingly:
    # the target may need tuning against the demo wardrobe before it is honest.
    seen = wired(
        _answer(
            _look(1, TOP_ID, JEANS_ID, BOOTS_ID),
            _look(2, TANK_ID, JEANS_ID, BOOTS_ID),
            _look(2, TOP_ID, JEANS_ID, BOOTS_ID, slot="evening"),
        )
    )

    await packing.pack_trip(
        _User(),
        WARDROBE,
        _request(occasions=(_slot(1), _slot(2), _slot(2, "evening", "evening"))),
    )

    assert [(day.day, day.slot) for day in seen["context"].days] == [
        (1, "day"),
        (2, "day"),
        (2, "evening"),
    ]
    assert seen["context"].reuse_target == packing.reuse_target(2)


# --- what reaches the model -------------------------------------------------


@pytest.mark.asyncio
async def test_the_context_carries_one_day_per_forecast_day(wired: Any) -> None:
    seen = wired(
        _answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID))
    )

    await packing.pack_trip(_User(), WARDROBE, _request())

    days = seen["context"].days
    assert [day.day for day in days] == [1, 2]
    assert [day.date for day in days] == [START, START + datetime.timedelta(days=1)]
    assert all(day.weather_rule == MILD_RULE for day in days)


@pytest.mark.asyncio
async def test_the_destination_sent_to_the_model_is_the_geocoders_name(wired: Any) -> None:
    # What the user typed reaches the geocoder; what the geocoder matched
    # reaches the model and the trip row keeps the typed string.
    seen = wired(
        _answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID))
    )

    result = await packing.pack_trip(_User(), WARDROBE, _request(destination="berlin"))

    assert seen["query"] == "berlin"
    assert seen["context"].destination == "Berlin"
    assert result.trip.destination == "berlin"


@pytest.mark.asyncio
async def test_the_preferences_block_reaches_a_trip(wired: Any) -> None:
    seen = wired(
        _answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID))
    )

    await packing.pack_trip(_User(), WARDROBE, _request(), preferences="- Liked: relaxed tops")

    assert seen["context"].preferences == "- Liked: relaxed tops"
    assert seen["context"].height_cm == 165


# --- the plan that comes back -----------------------------------------------


@pytest.mark.asyncio
async def test_each_look_is_dated_from_its_day_ordinal(wired: Any) -> None:
    # `day` is the trip's ordinal and `for_date` is the column `looks` has; the
    # mapping between them is this line and nothing else.
    wired(_answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID)))

    result = await packing.pack_trip(_User(), WARDROBE, _request())

    assert [look.day for look in result.looks] == [1, 2]
    assert [look.for_date for look in result.looks] == [START, START + datetime.timedelta(days=1)]


@pytest.mark.asyncio
async def test_looks_are_returned_in_day_order_whatever_order_they_arrived_in(wired: Any) -> None:
    # Rule 10 admits a complete-but-shuffled array, so the ordering is this
    # function's job rather than the model's.
    wired(_answer(_look(2, TANK_ID, JEANS_ID, BOOTS_ID), _look(1, TOP_ID, JEANS_ID, BOOTS_ID)))

    result = await packing.pack_trip(_User(), WARDROBE, _request())

    assert [look.day for look in result.looks] == [1, 2]
    assert result.looks[0].items[0].short_id == TOP_ID


@pytest.mark.asyncio
async def test_the_packing_list_is_stored_as_row_uuids(wired: Any) -> None:
    # The whole boundary between the two vocabularies: the model is shown
    # `short_id`s and the client is given UUIDs. `DECISIONS.md` 193.
    wired(_answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID)))

    result = await packing.pack_trip(_User(), WARDROBE, _request())

    assert result.trip.packing_list["item_ids"] == [
        str(TOP.id),
        str(JEANS.id),
        str(BOOTS.id),
        str(TANK.id),
    ]


@pytest.mark.asyncio
async def test_the_reuse_summary_counts_items_looks_and_the_most_reused(wired: Any) -> None:
    wired(_answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID)))

    result = await packing.pack_trip(_User(), WARDROBE, _request())

    assert result.trip.packing_list["reuse_summary"] == {
        "item_count": 4,
        "look_count": 2,
        "most_reused": {"item_id": str(JEANS.id), "days": 2},
    }


@pytest.mark.asyncio
async def test_nothing_worn_twice_summarises_to_no_most_reused(wired: Any) -> None:
    # An ordinary outcome on a short trip rather than an error, and `null` is
    # what the frontend branches on to hide the line.
    wired(_answer(_look(1, TOP_ID, JEANS_ID), _look(2, TANK_ID, BOOTS_ID)))

    result = await packing.pack_trip(_User(), WARDROBE, _request())

    assert result.trip.packing_list["reuse_summary"]["most_reused"] is None


@pytest.mark.asyncio
async def test_a_tie_for_most_reused_is_broken_by_the_packing_list_order(wired: Any) -> None:
    # Two garments worn on two days each, and a packing list whose order is not
    # the order the days wore them: the tie must break on the **list**, or the
    # same plan can summarise differently depending on iteration order.
    #
    # A mutation run at 4.3 is why this test is shaped this way. The first
    # version wore the same two items in the same order in both looks, so wear
    # order and packing order agreed and the assertion held whichever the code
    # read — it passed against a deliberately broken tie-break.
    wired(
        _answer(
            _look(1, TOP_ID, JEANS_ID, BOOTS_ID),
            _look(2, TOP_ID, JEANS_ID, BOOTS_ID),
            packing_list=(JEANS_ID, TOP_ID, BOOTS_ID),
        )
    )

    result = await packing.pack_trip(_User(), WARDROBE, _request())

    assert result.trip.packing_list["reuse_summary"]["most_reused"] == {
        "item_id": str(JEANS.id),
        "days": 2,
    }


@pytest.mark.asyncio
async def test_a_garment_worn_in_both_slots_of_one_day_reports_one_day(wired: Any) -> None:
    # The jeans and the boots are worn twice on the one day this trip has, and
    # `days` counts **dates**: one day, which fails the `> 1` test and leaves
    # `most_reused` null. A real reuse that produces no reuse line, taken
    # deliberately, because the sentence §7 renders is about days.
    wired(
        _answer(
            _look(1, TOP_ID, JEANS_ID, BOOTS_ID),
            _look(1, TANK_ID, JEANS_ID, BOOTS_ID, slot="evening"),
        ),
        days=1,
    )

    result = await packing.pack_trip(
        _User(),
        WARDROBE,
        _request(days=1, occasions=(_slot(1), _slot(1, "evening", "evening"))),
    )

    assert result.trip.packing_list["reuse_summary"] == {
        "item_count": 4,
        "look_count": 2,
        "most_reused": None,
    }


@pytest.mark.asyncio
async def test_look_count_exceeds_the_day_count_when_a_day_has_two_slots(wired: Any) -> None:
    # The other half of this pair is
    # `test_the_reuse_summary_counts_items_looks_and_the_most_reused`, where two
    # days of one slot each count two looks: the two numbers part company
    # exactly when a date carries an evening.
    wired(
        _answer(
            _look(1, TOP_ID, JEANS_ID, BOOTS_ID),
            _look(2, TANK_ID, JEANS_ID, BOOTS_ID),
            _look(2, TOP_ID, JEANS_ID, BOOTS_ID, slot="evening"),
        )
    )

    result = await packing.pack_trip(
        _User(),
        WARDROBE,
        _request(occasions=(_slot(1), _slot(2), _slot(2, "evening", "evening"))),
    )

    assert [(look.day, look.slot) for look in result.looks] == [
        (1, "day"),
        (2, "day"),
        (2, "evening"),
    ]
    assert [look.for_date for look in result.looks] == [
        START,
        START + datetime.timedelta(days=1),
        START + datetime.timedelta(days=1),
    ]
    assert result.trip.packing_list["reuse_summary"]["look_count"] == 3
    # The jeans are worn in all three looks and on both days; the count is of
    # days, so it is 2 and not 3.
    assert result.trip.packing_list["reuse_summary"]["most_reused"]["days"] == 2


@pytest.mark.asyncio
async def test_the_evening_look_takes_its_own_occasion(wired: Any) -> None:
    # Both entries of a date reach the model with the same weather rule and a
    # different occasion, which is the whole of what separates the two looks.
    seen = wired(
        _answer(
            _look(1, TOP_ID, JEANS_ID, BOOTS_ID),
            _look(1, TANK_ID, JEANS_ID, BOOTS_ID, slot="evening"),
        ),
        days=1,
    )

    result = await packing.pack_trip(
        _User(),
        WARDROBE,
        _request(days=1, occasions=(_slot(1), _slot(1, "evening", "evening"))),
    )

    assert [day.occasion for day in seen["context"].days] == ["work", "evening"]
    assert all(day.weather_rule == MILD_RULE for day in seen["context"].days)
    assert [look.occasion for look in result.looks] == ["work", "evening"]


@pytest.mark.asyncio
async def test_the_forecast_column_holds_the_parsed_days_and_each_days_rule(wired: Any) -> None:
    # Not the raw provider body, which this service never holds: what is stored
    # is what `04-API-SPEC.md`'s `days[]` renders, so reopening a trip re-reads
    # the plan rather than re-fetching a forecast that has moved.
    wired(_answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID)))

    result = await packing.pack_trip(_User(), WARDROBE, _request())

    assert result.trip.forecast[0] == {
        "day": 1,
        "date": "2026-03-14",
        "temp_min_c": 14.0,
        "temp_max_c": 18.0,
        "precip_mm": 0.0,
        "wind_kph": 9.0,
        "condition": "cloudy",
        "rule": MILD_RULE,
    }


@pytest.mark.asyncio
async def test_the_forecast_column_has_one_row_per_date_and_not_per_look(wired: Any) -> None:
    # `days` holds one entry per slot from 4.14, and this column holds one per
    # calendar day — the zip that used to pair them would have written day 2
    # twice and given the trip a day it has not got.
    wired(
        _answer(
            _look(1, TOP_ID, JEANS_ID, BOOTS_ID),
            _look(2, TANK_ID, JEANS_ID, BOOTS_ID),
            _look(2, TOP_ID, JEANS_ID, BOOTS_ID, slot="evening"),
        )
    )

    result = await packing.pack_trip(
        _User(),
        WARDROBE,
        _request(occasions=(_slot(1), _slot(2), _slot(2, "evening", "evening"))),
    )

    assert [day["day"] for day in result.trip.forecast] == [1, 2]
    assert [day["date"] for day in result.trip.forecast] == ["2026-03-14", "2026-03-15"]


@pytest.mark.asyncio
async def test_the_trip_row_is_built_and_not_persisted(wired: Any) -> None:
    # No `Session` reaches this service, so the row comes back with its server
    # defaults unresolved and 4.4 is what adds it.
    wired(_answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID)))

    result = await packing.pack_trip(_User(), WARDROBE, _request(notes="one dinner out"))

    assert result.trip.id is None
    # The slot is written down rather than left to be inferred: the repack
    # rebuilds its request out of this column.
    assert result.trip.occasions == [
        {"day": 1, "slot": "day", "occasion": "work"},
        {"day": 2, "slot": "day", "occasion": "work"},
    ]
    assert result.trip.notes == "one dinner out"
    assert result.missing_pieces[0].category == "shoes"


# --- what cannot be packed --------------------------------------------------


@pytest.mark.asyncio
async def test_a_destination_that_matches_nothing_is_its_own_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Distinct from `GeocodingError`: the provider answered, and nothing matched.
    # `DECISIONS.md` 152's argument, one service along.
    async def _none(query: str) -> list[Location]:
        return []

    monkeypatch.setattr(packing, "search_locations", _none)

    with pytest.raises(packing.DestinationNotFoundError):
        await packing.pack_trip(_User(), WARDROBE, _request())


@pytest.mark.asyncio
async def test_a_geocoder_that_does_not_answer_travels_through_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fails(query: str) -> list[Location]:
        raise GeocodingError("no answer")

    monkeypatch.setattr(packing, "search_locations", _fails)

    with pytest.raises(GeocodingError):
        await packing.pack_trip(_User(), WARDROBE, _request())


@pytest.mark.asyncio
async def test_a_plan_that_fails_validation_twice_raises(wired: Any) -> None:
    wired(
        _answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID), _look(2, TANK_ID, JEANS_ID, BOOTS_ID)),
        violation="day 2: the look has no shoes",
    )

    with pytest.raises(packing.StylistRejectedError, match="no shoes"):
        await packing.pack_trip(_User(), WARDROBE, _request())


@pytest.mark.asyncio
async def test_occasions_that_do_not_match_the_dates_are_a_callers_bug(wired: Any) -> None:
    # A `ValueError` rather than a `PackingError`: the route validates this
    # before building the request, so reaching it means the caller is wrong
    # rather than that the trip cannot be packed.
    #
    # The count is no longer the check — a two-day trip legitimately sends three
    # occasions — so what is refused is a day of the range nobody dressed.
    wired(_answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID)))

    with pytest.raises(ValueError, match=r"days \[1, 2, 3\] and the trip is 2"):
        await packing.pack_trip(
            _User(), WARDROBE, _request(occasions=(_slot(1), _slot(2), _slot(3, occasion="casual")))
        )


@pytest.mark.asyncio
async def test_one_slot_asked_for_twice_is_a_callers_bug(wired: Any) -> None:
    # `uq_looks_trip_day_slot` would refuse the second row four layers down, as
    # an `IntegrityError` on a route that has already spent a model call.
    wired(_answer(_look(1, TOP_ID, JEANS_ID, BOOTS_ID)))

    with pytest.raises(ValueError, match="day 2 evening twice"):
        await packing.pack_trip(
            _User(),
            WARDROBE,
            _request(
                occasions=(
                    _slot(1),
                    _slot(2, "evening", "evening"),
                    _slot(2, "evening", "dinner"),
                )
            ),
        )

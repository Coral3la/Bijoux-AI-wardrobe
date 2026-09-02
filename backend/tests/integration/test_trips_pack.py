"""`POST /trips/pack` and `POST /trips/{id}/repack`, measured end to end.

The geocoder and the forecast are faked on `services/packing`, which is the
binding `pack_trip` actually reads; the stylist is faked one module further in,
on `stylist_runner.suggest_looks`, so that **`validate_look_response` runs for
real**. That split is deliberate and it is the same one `test_looks_suggest.py`
makes: the trip path's rules 5, 10 and 11 are new at 4.3 and an answer that
passes them here has passed the rules the endpoint will actually apply.

No fixture file, for `DECISIONS.md` 159's reason: `short_id`s are generated per
row, so every plan below is built from the ids the wardrobe fixture planted.

The two endpoints share a file because they share the whole fake stack and
because the thing most worth measuring about a repack — that a stylist failure
leaves the existing looks alone — needs a pack to have happened first.
"""

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openai import APITimeoutError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import Category, Condition, ItemStatus, Layer
from app.models.item import Item
from app.models.look import FEEDBACK_DOWN, FEEDBACK_UP, Look, LookItem
from app.models.trip import Trip
from app.models.user import User
from app.services import packing, stylist_runner
from app.services.geocoding import GeocodingError, Location
from app.services.stylist import Look as StylistLook
from app.services.stylist import MissingPiece, StylistResponse
from app.services.weather import (
    Forecast,
    ForecastOutOfRangeError,
    ForecastProviderError,
)

BERLIN = Location(name="Berlin", country="Germany", lat=52.52, lon=13.41)

# Warm and dry on purpose, so rule 6 never fires and a plan with no coat is a
# valid plan. What this file is about is the endpoint, not the band table —
# `tests/unit/test_weather.py` measures that.
CONDITIONS = (24.0, 0.0, 10.0)

# Nine garments, which clears the eight-item threshold by one. Two shoes, three
# tops and two bottoms are what let four days be four *different* looks: rule 11
# refuses a repeated outfit, and it is the rule a lazy plan trips over first.
WARDROBE: tuple[tuple[str, Category, Layer], ...] = (
    ("shoes_a", Category.SHOES, Layer.STANDALONE),
    ("shoes_b", Category.SHOES, Layer.STANDALONE),
    ("top_a", Category.TOP, Layer.BASE),
    ("top_b", Category.TOP, Layer.BASE),
    ("top_c", Category.TOP, Layer.BASE),
    ("bottom_a", Category.BOTTOM, Layer.BASE),
    ("bottom_b", Category.BOTTOM, Layer.BASE),
    ("bag", Category.BAG, Layer.STANDALONE),
    ("accessory", Category.ACCESSORY, Layer.STANDALONE),
)

# Day *n* wears `OUTFITS[n - 1]`. Every set is distinct (rule 11) and the reuse
# is deliberate: `shoes_a` and `bottom_a` are each worn twice over three days,
# which is what makes `most_reused` a tie and therefore a test of the documented
# tie-break — most days, then first in the packing list.
OUTFITS: tuple[tuple[str, ...], ...] = (
    ("shoes_a", "top_a", "bottom_a"),
    ("shoes_a", "top_b", "bottom_a"),
    ("shoes_b", "top_c", "bottom_b"),
    ("shoes_b", "top_a", "bottom_b"),
)


class FakeStylist:
    """`test_looks_suggest.py`'s fake unchanged: answers in order, last repeats."""

    def __init__(self, *answers: StylistResponse | Exception) -> None:
        self.answers = list(answers)
        self.contexts: list[Any] = []

    async def __call__(
        self, wardrobe: Any, context: Any, correction: str | None = None
    ) -> StylistResponse:
        self.contexts.append(context)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def calls(self) -> int:
        return len(self.contexts)


def plan(wardrobe: dict[str, Item], days: int) -> StylistResponse:
    """A valid `trip_packing_plan` for `days` days, built from the planted ids."""
    looks = tuple(
        StylistLook(
            day=day,
            # `slot` is required on the trip path from task 4.13 — rule 10 matches
            # the `(day, slot)` pair against what the request asked for, and a
            # look carrying one and not the other is refused before any other
            # trip rule runs. `day` while nothing can request an evening.
            slot="day",
            title=f"Day {day}",
            item_ids=tuple(wardrobe[name].short_id for name in OUTFITS[day - 1]),
            reasoning="The straight jean balances the oversized shirt.",
            weather_note="24°C — no coat needed.",
        )
        for day in range(1, days + 1)
    )
    return StylistResponse(
        looks=looks,
        missing_pieces=(
            MissingPiece(
                category="outerwear",
                description="a light rain shell",
                reason="nothing water-resistant in the wardrobe",
            ),
        ),
        message="Three days in Berlin from seven pieces.",
        # Deduplicated in day order, which is the order `_reuse_summary` breaks
        # ties by. Rule 5 checks it in both directions.
        packing_list=tuple(dict.fromkeys(item_id for look in looks for item_id in look.item_ids)),
    )


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user(height_cm=170, style_notes="prefer high-rise bottoms")


@pytest.fixture
def wardrobe(
    user: User, make_item: Callable[..., Item], cloudinary_configured: None
) -> dict[str, Item]:
    return {
        name: make_item(user_id=user.id, status=ItemStatus.READY, category=category, layer=layer)
        for name, category, layer in WARDROBE
    }


@pytest.fixture
def geocoder(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[str]]:
    """Open-Meteo's geocoder, recorded instead of called."""
    asked: list[str] = []

    def _install(*, result: list[Location] | Exception | None = None) -> list[str]:
        matches = [BERLIN] if result is None else result

        async def _search(query: str) -> list[Location]:
            asked.append(query)
            if isinstance(matches, Exception):
                raise matches
            return matches

        monkeypatch.setattr(packing, "search_locations", _search)
        return asked

    return _install


@pytest.fixture
def forecasts(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[tuple[Any, ...]]]:
    asked: list[tuple[Any, ...]] = []

    def _install(*, error: Exception | None = None, temp_max: float = CONDITIONS[0]) -> list[Any]:
        async def _daily(lat: float, lon: float, start: date, end: date) -> list[Forecast]:
            asked.append((lat, lon, start, end))
            if error is not None:
                raise error
            return [
                Forecast(
                    date=start + timedelta(days=offset),
                    temp_min_c=temp_max - 6.0,
                    temp_max_c=temp_max,
                    precip_mm=CONDITIONS[1],
                    wind_kph=CONDITIONS[2],
                    condition=Condition.CLEAR,
                )
                for offset in range((end - start).days + 1)
            ]

        monkeypatch.setattr(packing, "get_daily_forecast", _daily)
        return asked

    return _install


@pytest.fixture
def stylist(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeStylist]:
    def _install(*answers: StylistResponse | Exception) -> FakeStylist:
        fake = FakeStylist(*answers)
        monkeypatch.setattr(stylist_runner, "suggest_looks", fake)
        return fake

    return _install


def body(days: int = 3, start: date | None = None, **overrides: Any) -> dict[str, Any]:
    first = start or date.today() + timedelta(days=2)
    return {
        "destination": "Berlin",
        "start_date": first.isoformat(),
        "end_date": (first + timedelta(days=days - 1)).isoformat(),
        "occasions": [{"day": day, "occasion": "work"} for day in range(1, days + 1)],
        "notes": "one dinner out",
    } | overrides


def post(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    **overrides: Any,
) -> Any:
    return client.post("/api/v1/trips/pack", json=body(**overrides), headers=authorization(user))


@pytest.fixture
def wired(
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
    wardrobe: dict[str, Item],
) -> Callable[..., FakeStylist]:
    """The whole outside world faked, with the stylist answering a valid plan."""

    def _install(days: int = 3, **overrides: Any) -> FakeStylist:
        geocoder()
        forecasts()
        return stylist(overrides.pop("answer", plan(wardrobe, days)))

    return _install


def _counts(db: Session) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(Trip)) or 0,
        db.scalar(select(func.count()).select_from(Look)) or 0,
        db.scalar(select(func.count()).select_from(LookItem)) or 0,
    )


# --- POST /trips/pack -------------------------------------------------------


def test_a_three_day_trip_answers_one_look_per_day(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    fake = wired(days=3)

    response = post(client, user, authorization)

    assert response.status_code == 200
    assert len(response.json()["looks"]) == 3
    assert len(response.json()["trip"]["days"]) == 3
    # One call for the whole trip, never one per day: it is the reason a trip
    # can reuse anything at all.
    assert fake.calls == 1


def test_the_trip_its_looks_and_their_items_are_written_in_one_commit(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)
    before = _counts(db)

    post(client, user, authorization)

    trips, looks, look_items = _counts(db)
    assert (trips, looks) == (before[0] + 1, before[1] + 3)
    # Three looks of three garments each.
    assert look_items == before[2] + 9


def test_every_written_look_carries_the_trip_id(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)

    trip_id = uuid.UUID(post(client, user, authorization).json()["trip"]["id"])

    assert db.scalar(select(func.count()).select_from(Look).where(Look.trip_id == trip_id)) == 3


def test_each_look_is_dated_by_its_day_ordinal(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """Day 1 is `start_date`; `looks.for_date` is the column that records it."""
    wired(days=3)
    start = date.today() + timedelta(days=2)

    trip_id = uuid.UUID(post(client, user, authorization).json()["trip"]["id"])

    assert sorted(db.scalars(select(Look.for_date).where(Look.trip_id == trip_id)).all()) == [
        start + timedelta(days=offset) for offset in range(3)
    ]


def test_the_day_strip_joins_the_forecast_the_occasion_and_the_look(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)

    payload = post(client, user, authorization).json()

    days = payload["trip"]["days"]
    look_ids = {look["id"] for look in payload["looks"]}
    assert [day["day"] for day in days] == [1, 2, 3]
    assert {day["occasion"] for day in days} == {"work"}
    assert {day["temp_max_c"] for day in days} == {CONDITIONS[0]}
    assert all(day["rule"] for day in days)
    # The join `DECISIONS.md` 195 chose over pairing `days[i]` with `looks[i]`.
    assert {day["look_id"] for day in days} == look_ids


def test_the_packing_list_holds_row_uuids_and_the_reuse_summary(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)

    packing_list = post(client, user, authorization).json()["trip"]["packing_list"]

    # Row UUIDs, never the `short_id`s the model answered with: `04-API-SPEC.md`
    # keeps those for the AI layer alone.
    assert packing_list["item_ids"] == [
        str(wardrobe[name].id)
        for name in ("shoes_a", "top_a", "bottom_a", "top_b", "shoes_b", "top_c", "bottom_b")
    ]
    assert packing_list["reuse_summary"] == {
        "item_count": 7,
        "look_count": 3,
        # `shoes_a` and `bottom_a` are both worn twice; the tie goes to the one
        # earlier in the packing list, which is the documented rule and the only
        # thing keeping two runs from summarising the same plan differently.
        "most_reused": {"item_id": str(wardrobe["shoes_a"].id), "days": 2},
    }


def test_the_packing_list_is_smaller_than_four_garments_a_day(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """`STAGE-4`'s acceptance criterion, asserted on the wire rather than in prose."""
    wired(days=3)

    payload = post(client, user, authorization).json()

    assert len(payload["trip"]["packing_list"]["item_ids"]) < 3 * 4


def test_every_look_item_is_in_the_packing_list_and_the_reverse(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)

    payload = post(client, user, authorization).json()

    packed = set(payload["trip"]["packing_list"]["item_ids"])
    worn = {item["id"] for look in payload["looks"] for item in look["items"]}
    assert packed == worn


def test_the_looks_are_hydrated_in_the_models_own_order(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    wired: Callable[..., FakeStylist],
) -> None:
    """`look_items.position` is written from the answer and read back by it."""
    wired(days=3)

    looks = post(client, user, authorization).json()["looks"]

    first = next(look for look in looks if look["title"] == "Day 1")
    assert [item["id"] for item in first["items"]] == [
        str(wardrobe[name].id) for name in OUTFITS[0]
    ]


def test_the_response_carries_missing_pieces_and_no_message(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """`DECISIONS.md` 195: `trips` has no column for a message and no screen renders one."""
    wired(days=3)

    payload = post(client, user, authorization).json()

    assert [piece["category"] for piece in payload["missing_pieces"]] == ["outerwear"]
    assert "message" not in payload


def test_the_trip_row_stores_the_occasions_and_the_parsed_forecast(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """Neither column is on the wire, so nothing else would notice them missing."""
    wired(days=3)

    trip_id = uuid.UUID(post(client, user, authorization).json()["trip"]["id"])

    trip = db.get(Trip, trip_id)
    assert trip is not None
    assert trip.occasions == [{"day": day, "occasion": "work"} for day in (1, 2, 3)]
    assert trip.forecast is not None
    # The rule is stored beside the numbers rather than recomputed on read, so a
    # trip packed under one band table cannot re-render under another.
    assert all(day["rule"] for day in trip.forecast)


def test_the_learned_preferences_reach_the_trip_context(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    wired: Callable[..., FakeStylist],
) -> None:
    """`DECISIONS.md` 196 — a user does not stop disliking bodycon in Berlin."""
    for feedback in (FEEDBACK_UP, FEEDBACK_UP, FEEDBACK_DOWN):
        look = Look(user_id=user.id, feedback=feedback)
        db.add(look)
        db.flush()
        db.add_all(
            [LookItem(look_id=look.id, item_id=wardrobe[name].id) for name in ("top_a", "bottom_a")]
        )
    db.commit()
    fake = wired(days=3)

    post(client, user, authorization)

    assert fake.contexts[0].preferences is not None
    assert "USER PREFERENCES" in fake.contexts[0].preferences


def test_the_trip_context_carries_the_reuse_target(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    fake = wired(days=3)

    post(client, user, authorization)

    # `min(days * 4, days + 8)` — eleven for three days.
    assert fake.contexts[0].reuse_target == 11


# --- the refusals that cost nothing ----------------------------------------


def test_a_fifteen_day_trip_is_trip_too_long(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """`STAGE-4`'s acceptance criterion: rejected at the API layer."""
    fake = wired()

    response = post(client, user, authorization, days=15, start=date.today())

    assert response.status_code == 400
    assert response.json()["code"] == "trip_too_long"
    assert fake.calls == 0


def test_a_trip_ending_beyond_the_horizon_is_trip_too_long(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """Short enough to pass the length check and still past `today + 14`."""
    fake = wired(days=3)

    response = post(client, user, authorization, days=3, start=date.today() + timedelta(days=13))

    assert response.status_code == 400
    assert response.json()["code"] == "trip_too_long"
    assert fake.calls == 0


def test_a_long_trip_ending_inside_the_horizon_is_still_refused(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """The case `start_date` being unbounded below creates.

    A trip beginning forty days ago and ending next week satisfies `end_date <=
    today + 14` and is forty-seven days long. Without the length half of the
    check this reaches `get_daily_forecast` and asks a provider for forty-seven
    days. `DECISIONS.md` 201.
    """
    fake = wired()

    response = post(client, user, authorization, days=47, start=date.today() - timedelta(days=40))

    assert response.status_code == 400
    assert response.json()["code"] == "trip_too_long"
    assert fake.calls == 0


def test_a_wardrobe_under_eight_ready_items_is_refused_before_the_geocoder(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_item: Callable[..., Item],
    cloudinary_configured: None,
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    for _ in range(7):
        make_item(user_id=user.id, status=ItemStatus.READY, category=Category.TOP, layer=Layer.BASE)
    asked = geocoder()
    forecasts()
    fake = stylist(StylistResponse(looks=(), missing_pieces=(), message=""))

    response = post(client, user, authorization)

    assert response.status_code == 400
    assert response.json()["code"] == "wardrobe_too_small"
    assert "8" in response.json()["detail"]
    # A request that cannot be served costs neither a geocode nor a token.
    assert asked == []
    assert fake.calls == 0


def test_swimwear_and_sleepwear_do_not_count_toward_the_threshold(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_item: Callable[..., Item],
    cloudinary_configured: None,
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    """The threshold counts the wardrobe that is *sent*, not every `ready` row.

    Nine `ready` garments, four of which the stylist is never shown, so five
    arrive and the request is refused. Deliberately not built on the `wardrobe`
    fixture, whose nine styleable items are the thing this is measuring the
    absence of.
    """
    for category in (Category.SWIMWEAR, Category.SLEEPWEAR):
        for _ in range(2):
            make_item(user_id=user.id, status=ItemStatus.READY, category=category, layer=Layer.BASE)
    for _ in range(5):
        make_item(user_id=user.id, status=ItemStatus.READY, category=Category.TOP, layer=Layer.BASE)
    geocoder()
    forecasts()
    fake = stylist(StylistResponse(looks=(), missing_pieces=(), message=""))

    response = post(client, user, authorization)

    assert response.status_code == 400
    assert response.json()["code"] == "wardrobe_too_small"
    assert fake.calls == 0


# --- the failures that come from outside ------------------------------------


def test_a_destination_that_matches_nothing_is_destination_not_found(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    """The geocoder answered; nothing matched. Not `geocoding_unavailable`."""
    geocoder(result=[])
    forecasts()
    fake = stylist(plan(wardrobe, 3))

    response = post(client, user, authorization, destination="Nowhereton")

    assert response.status_code == 400
    assert response.json()["code"] == "destination_not_found"
    assert "Nowhereton" in response.json()["detail"]
    assert fake.calls == 0


def test_a_geocoder_that_does_not_answer_is_geocoding_unavailable(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    geocoder(result=GeocodingError("no answer"))
    forecasts()
    stylist(plan(wardrobe, 3))

    response = post(client, user, authorization)

    assert response.status_code == 502
    assert response.json()["code"] == "geocoding_unavailable"


def test_a_range_past_the_provider_horizon_is_a_400(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    geocoder()
    forecasts(error=ForecastOutOfRangeError("beyond"))
    stylist(plan(wardrobe, 3))

    response = post(client, user, authorization)

    assert response.status_code == 400
    assert response.json()["code"] == "forecast_unavailable"


def test_a_forecast_provider_failure_is_a_502(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    """The same code split across two statuses, exactly as `GET /weather` splits it."""
    geocoder()
    forecasts(error=ForecastProviderError("down"))
    stylist(plan(wardrobe, 3))

    response = post(client, user, authorization)

    assert response.status_code == 502
    assert response.json()["code"] == "forecast_unavailable"


def test_a_plan_that_fails_validation_twice_is_stylist_failed(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    geocoder()
    forecasts()
    # Two days answered for a three-day trip: rule 4, twice.
    fake = stylist(plan(wardrobe, 2))

    response = post(client, user, authorization)

    assert response.status_code == 502
    assert response.json()["code"] == "stylist_failed"
    # One retry carrying the violation, and no more.
    assert fake.calls == 2


def test_a_provider_that_does_not_answer_is_not_retried(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    """`DECISIONS.md` 171: the retry exists to carry a violation, and silence has none."""
    geocoder()
    forecasts()
    fake = stylist(APITimeoutError(request=None))  # type: ignore[arg-type]

    response = post(client, user, authorization)

    assert response.status_code == 502
    assert response.json()["code"] == "stylist_failed"
    assert fake.calls == 1


def test_a_failed_pack_writes_nothing(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    """The transaction is downstream of the model, so a `502` leaves no trip behind."""
    geocoder()
    forecasts()
    stylist(plan(wardrobe, 2))
    before = _counts(db)

    post(client, user, authorization)

    assert _counts(db) == before


# --- the bodies the schema refuses ------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"occasions": [{"day": 1, "occasion": "work"}]}, id="too_few_occasions"),
        pytest.param(
            {"occasions": [{"day": day, "occasion": "work"} for day in (1, 3, 2)]},
            id="days_out_of_order",
        ),
        pytest.param(
            {"occasions": [{"day": day, "occasion": "work"} for day in (0, 1, 2)]},
            id="days_not_one_based",
        ),
        pytest.param(
            {"occasions": [{"day": day, "occasion": "brunch"} for day in (1, 2, 3)]},
            id="occasion_outside_the_six",
        ),
        pytest.param({"destination": "   "}, id="blank_destination"),
        pytest.param({"tempo": "slow"}, id="unknown_key"),
    ],
)
def test_a_malformed_body_is_validation_error(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
    overrides: dict[str, Any],
) -> None:
    fake = wired(days=3)

    response = post(client, user, authorization, **overrides)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert fake.calls == 0


def test_an_end_date_before_the_start_is_validation_error(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """Refused here rather than by the CHECK, which would be a 500 with no code."""
    wired(days=3)
    start = date.today() + timedelta(days=5)

    response = post(
        client,
        user,
        authorization,
        start_date=start.isoformat(),
        end_date=(start - timedelta(days=1)).isoformat(),
        occasions=[{"day": 1, "occasion": "work"}],
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_packing_requires_a_token(client: TestClient) -> None:
    response = client.post("/api/v1/trips/pack", json=body())

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


# --- POST /trips/{id}/repack ------------------------------------------------


def _packed(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    **overrides: Any,
) -> Any:
    response = post(client, user, authorization, **overrides)
    assert response.status_code == 200
    return response.json()


def test_repack_replaces_the_looks_and_keeps_the_trip(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)
    first = _packed(client, user, authorization)
    trip_id = first["trip"]["id"]

    response = client.post(f"/api/v1/trips/{trip_id}/repack", headers=authorization(user))

    assert response.status_code == 200
    payload = response.json()
    assert payload["trip"]["id"] == trip_id
    assert payload["trip"]["created_at"] == first["trip"]["created_at"]
    # New rows, not the old ones.
    assert {look["id"] for look in payload["looks"]}.isdisjoint(
        {look["id"] for look in first["looks"]}
    )
    assert db.scalar(select(func.count()).select_from(Trip)) == 1


def test_repack_refreshes_the_forecast(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    geocoder()
    asked = forecasts()
    stylist(plan(wardrobe, 3))
    trip_id = _packed(client, user, authorization)["trip"]["id"]

    client.post(f"/api/v1/trips/{trip_id}/repack", headers=authorization(user))

    # The provider is asked a second time, for the same range.
    assert len(asked) == 2
    assert asked[0] == asked[1]


def test_repack_re_geocodes_the_stored_destination(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    """`DECISIONS.md` 202 — the coordinates are re-derived, not reused."""
    asked = geocoder()
    forecasts()
    stylist(plan(wardrobe, 3))
    trip_id = _packed(client, user, authorization)["trip"]["id"]

    client.post(f"/api/v1/trips/{trip_id}/repack", headers=authorization(user))

    assert asked == ["Berlin", "Berlin"]


def test_repack_detaches_a_saved_look_instead_of_deleting_it(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """`AUDITS.md` O-32, option 2. A saved look survives with no trip."""
    wired(days=3)
    first = _packed(client, user, authorization)
    trip_id = first["trip"]["id"]
    kept = uuid.UUID(first["looks"][0]["id"])
    look = db.get(Look, kept)
    assert look is not None
    look.is_saved = True
    db.commit()

    client.post(f"/api/v1/trips/{trip_id}/repack", headers=authorization(user))

    db.expire_all()
    survivor = db.get(Look, kept)
    assert survivor is not None
    assert survivor.is_saved is True
    assert survivor.trip_id is None


@pytest.mark.parametrize(
    ("column", "value"),
    [
        pytest.param("feedback", FEEDBACK_UP, id="rated"),
        pytest.param("worn_at", date.today(), id="worn"),
    ],
)
def test_repack_detaches_a_rated_or_worn_look(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
    column: str,
    value: Any,
) -> None:
    """The other two of O-32's three columns; three separate features read them."""
    wired(days=3)
    first = _packed(client, user, authorization)
    kept = uuid.UUID(first["looks"][1]["id"])
    look = db.get(Look, kept)
    assert look is not None
    setattr(look, column, value)
    db.commit()

    client.post(f"/api/v1/trips/{first['trip']['id']}/repack", headers=authorization(user))

    db.expire_all()
    survivor = db.get(Look, kept)
    assert survivor is not None
    assert survivor.trip_id is None
    assert getattr(survivor, column) == value


def test_repack_deletes_the_looks_nobody_marked(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)
    first = _packed(client, user, authorization)
    unmarked = [uuid.UUID(look["id"]) for look in first["looks"]]

    client.post(f"/api/v1/trips/{first['trip']['id']}/repack", headers=authorization(user))

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Look).where(Look.id.in_(unmarked))) == 0
    # And their `look_items` went with them, through `0002`'s own cascade.
    assert (
        db.scalar(select(func.count()).select_from(LookItem).where(LookItem.look_id.in_(unmarked)))
        == 0
    )


def test_a_detached_look_is_not_on_the_trips_day_strip(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """O-32's own follow-up: `days[].look_id` must point at the new looks."""
    wired(days=3)
    first = _packed(client, user, authorization)
    kept = uuid.UUID(first["looks"][0]["id"])
    look = db.get(Look, kept)
    assert look is not None
    look.is_saved = True
    db.commit()

    payload = client.post(
        f"/api/v1/trips/{first['trip']['id']}/repack", headers=authorization(user)
    ).json()

    assert str(kept) not in {day["look_id"] for day in payload["trip"]["days"]}
    assert all(day["look_id"] is not None for day in payload["trip"]["days"])


def test_a_stylist_failure_leaves_the_existing_looks_alone(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> None:
    """The ordering O-32's recommendation did not state and this task added.

    A repack that detached and deleted before calling the model would answer
    `502` having already emptied a trip the user still has.
    """
    geocoder()
    forecasts()
    stylist(plan(wardrobe, 3))
    first = _packed(client, user, authorization)
    stylist(plan(wardrobe, 2))

    response = client.post(
        f"/api/v1/trips/{first['trip']['id']}/repack", headers=authorization(user)
    )

    assert response.status_code == 502
    db.expire_all()
    assert (
        db.scalar(
            select(func.count())
            .select_from(Look)
            .where(Look.trip_id == uuid.UUID(first["trip"]["id"]))
        )
        == 3
    )


def test_repacking_a_trip_that_has_aged_out_is_trip_too_long(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wired: Callable[..., FakeStylist],
) -> None:
    """A trip stays in the database; the horizon moves. `DECISIONS.md` 201."""
    wired(days=3)
    trip_id = _packed(client, user, authorization)["trip"]["id"]
    trip = db.get(Trip, uuid.UUID(trip_id))
    assert trip is not None
    trip.start_date = date.today() + timedelta(days=13)
    trip.end_date = date.today() + timedelta(days=15)
    db.commit()

    response = client.post(f"/api/v1/trips/{trip_id}/repack", headers=authorization(user))

    assert response.status_code == 400
    assert response.json()["code"] == "trip_too_long"


def test_repacking_another_accounts_trip_is_not_found(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    make_user: Callable[..., User],
    wired: Callable[..., FakeStylist],
) -> None:
    wired(days=3)
    trip_id = _packed(client, user, authorization)["trip"]["id"]

    response = client.post(f"/api/v1/trips/{trip_id}/repack", headers=authorization(make_user()))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"

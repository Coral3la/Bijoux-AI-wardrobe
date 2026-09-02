"""`POST /trips/{trip_id}/swap`, measured end to end against a packed trip.

Every test here packs first, because a swap is an edit to a stored plan and
there is nothing to measure about one that has no plan under it. The fake stack
is `test_trips_pack.py`'s shape: the geocoder and the forecast are faked on
`services/packing`, and the stylist one module further in on
`stylist_runner.suggest_looks`, so **`validate_look_response` runs for real** on
the swap as well as on the pack — which is what makes rule 8 an assertion about
the endpoint rather than about a fixture.

**The fixtures are copied rather than imported, and that is this suite's
convention rather than an oversight.** No test module in this project imports
another — twenty files, zero cross-imports — and the alternative that avoids
both, a `tests/integration/conftest.py`, would mean moving fixtures out of a file
this task has no other reason to touch. What is duplicated is the fake stack;
the assertions are this endpoint's alone.

The stylist fake answers in order, so one install serves both calls: the trip
plan for the pack, then a single-day look for the swap. The swap's look carries
no `day` and no `packing_list`, because it comes back on the single-day path —
and that is the shape being measured, not a convenience.

**Two of these tests exist to catch a mutation rather than a bug.** The rule
this endpoint sends is read from `trips.forecast` and never rebuilt, and nothing
about the response would look wrong if it were — so the stored rule is
overwritten with a sentence `build_rule` cannot produce, and the assertion is on
what reached the model. The same shape guards the ordering: a stylist failure
must leave the day's look exactly where it was.
"""

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openai import APITimeoutError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import Category, Condition, ItemStatus, Layer
from app.models.item import Item
from app.models.look import FEEDBACK_DOWN, FEEDBACK_UP, Look
from app.models.trip import Trip
from app.models.user import User
from app.services import packing, stylist_runner
from app.services.geocoding import Location
from app.services.stylist import Look as StylistLook
from app.services.stylist import MissingPiece, StylistResponse
from app.services.weather import Forecast

BERLIN = Location(name="Berlin", country="Germany", lat=52.52, lon=13.41)

# Warm and dry, so rule 6 never fires and a look with no coat is a valid look.
CONDITIONS = (24.0, 0.0, 10.0)

WARDROBE: tuple[tuple[str, Category, Layer], ...] = (
    ("shoes_a", Category.SHOES, Layer.STANDALONE),
    ("shoes_b", Category.SHOES, Layer.STANDALONE),
    # Worn by no day of the packed plan, which is what makes it a *newcomer* to
    # the packing list rather than a garment already in the suitcase. Swapping in
    # something already packed is the commoner case and tests nothing about
    # where a new id lands.
    ("shoes_c", Category.SHOES, Layer.STANDALONE),
    ("top_a", Category.TOP, Layer.BASE),
    ("top_b", Category.TOP, Layer.BASE),
    ("top_c", Category.TOP, Layer.BASE),
    ("bottom_a", Category.BOTTOM, Layer.BASE),
    ("bottom_b", Category.BOTTOM, Layer.BASE),
    ("bag", Category.BAG, Layer.STANDALONE),
    ("accessory", Category.ACCESSORY, Layer.STANDALONE),
)

OUTFITS: tuple[tuple[str, ...], ...] = (
    ("shoes_a", "top_a", "bottom_a"),
    ("shoes_a", "top_b", "bottom_a"),
    ("shoes_b", "top_c", "bottom_b"),
)

# The second look of a date, for the days a test asks to carry one. Keyed by day
# rather than a single tuple so that two evenings could never wear the same
# outfit and trip rule 11; day 2 is `DAY`, the day under test throughout.
#
# **`top_b` is the point of this outfit.** It is worn by day 2's day look and by
# nothing else in `OUTFITS`, so putting it here makes it a garment worn on one
# date in both slots — which is what the packing list's fourth criterion needs to
# measure, and what no single-slot trip can produce.
EVENING_OUTFITS: dict[int, tuple[str, ...]] = {
    2: ("shoes_b", "top_b", "bottom_b"),
}


class FakeStylist:
    """Answers in order, last repeats — `test_looks_suggest.py`'s fake unchanged."""

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


def pairs(days: int, evenings: tuple[int, ...] = ()) -> list[tuple[int, str]]:
    """The `(day, slot)` pairs a trip of `days` days with these evenings asks for.

    One list feeds the request body and the fake's answer, which is what keeps
    rule 10 a real check here rather than a tautology.
    """
    return [
        (day, slot)
        for day in range(1, days + 1)
        for slot in (("day", "evening") if day in evenings else ("day",))
    ]


def plan(wardrobe: dict[str, Item], days: int, evenings: tuple[int, ...] = ()) -> StylistResponse:
    """A valid `trip_packing_plan`, built from the planted ids.

    `evenings` names the dates that carry a second look, from task 4.16. A day
    slot keeps `OUTFITS[day - 1]` whatever else is asked for — every reuse
    assertion in this suite is written against who wears what, so an evening must
    not move an existing day's outfit.
    """
    looks = tuple(
        StylistLook(
            day=day,
            # `slot` is required on the trip path from task 4.13 — rule 10 matches
            # the `(day, slot)` pair against what the request asked for, and a
            # look carrying one and not the other is refused before any other
            # trip rule runs.
            slot=slot,
            title=f"Day {day} {slot}",
            item_ids=tuple(
                wardrobe[name].short_id
                for name in (EVENING_OUTFITS[day] if slot == "evening" else OUTFITS[day - 1])
            ),
            reasoning="The straight jean balances the oversized shirt.",
            weather_note="24°C — no coat needed.",
        )
        for day, slot in pairs(days, evenings)
    )
    return StylistResponse(
        looks=looks,
        missing_pieces=(),
        message="Three days in Berlin.",
        packing_list=tuple(dict.fromkeys(item_id for look in looks for item_id in look.item_ids)),
    )


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user(height_cm=170, style_notes="prefer high-rise bottoms")


@pytest.fixture
def wardrobe(
    user: User, make_item: Callable[..., Item], cloudinary_configured: None
) -> dict[str, Item]:
    """The nine garments, with `shoes_a` deliberately given the **highest** id.

    Every other test here is indifferent to the ids; the tie-break test is not.
    `reuse_summary` breaks a tie on packing-list order, and `shoes_a` is first in
    that order — so a mutation that sorted the list before summarising it would
    still answer `shoes_a` about half the time on random ids, and the test would
    pass for the wrong reason at whatever rate the ids allowed.

    Generated per run rather than written down, which is `CONVENTIONS.md`'s rule
    about literals under a `UNIQUE` constraint: a hard-coded id survives a run
    that fails to roll back and leaves the suite red until someone truncates the
    table.
    """
    ids = sorted(uuid.uuid4() for _ in WARDROBE)
    highest = ids.pop()
    planted = {name: (highest if name == "shoes_a" else ids.pop(0)) for name, _, _ in WARDROBE}

    return {
        name: make_item(
            id=planted[name],
            user_id=user.id,
            status=ItemStatus.READY,
            category=category,
            layer=layer,
        )
        for name, category, layer in WARDROBE
    }


@pytest.fixture
def geocoder(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[str]]:
    asked: list[str] = []

    def _install() -> list[str]:
        async def _search(query: str) -> list[Location]:
            asked.append(query)
            return [BERLIN]

        monkeypatch.setattr(packing, "search_locations", _search)
        return asked

    return _install


@pytest.fixture
def forecasts(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[Any]]:
    asked: list[tuple[Any, ...]] = []

    def _install() -> list[Any]:
        async def _daily(lat: float, lon: float, start: date, end: date) -> list[Forecast]:
            asked.append((lat, lon, start, end))
            return [
                Forecast(
                    date=start + timedelta(days=offset),
                    temp_min_c=CONDITIONS[0] - 6.0,
                    temp_max_c=CONDITIONS[0],
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


def body(days: int, evenings: tuple[int, ...] = ()) -> dict[str, Any]:
    first = date.today() + timedelta(days=2)
    return {
        "destination": "Berlin",
        "start_date": first.isoformat(),
        "end_date": (first + timedelta(days=days - 1)).isoformat(),
        "occasions": [
            {"day": day, "slot": slot, "occasion": "evening" if slot == "evening" else "work"}
            for day, slot in pairs(days, evenings)
        ],
        "notes": "one dinner out",
    }


DAYS = 3

# Day 2 is the day under test throughout: it is neither the first nor the last,
# so an off-by-one in the ordinal arithmetic that `_by_day` inverts cannot pass
# by landing on the day it was already on.
DAY = 2

# `shoes_a` is worn on day 1 and day 2 (see `OUTFITS`), which is what makes the
# reuse half of this suite measurable: swapping it out of day 2 must leave it in
# the packing list, because day 1 still wears it.
REPLACED = "shoes_a"
REPLACEMENT = "shoes_c"

# A sentence `build_rule` cannot produce from any three numbers. If the endpoint
# ever derives the rule again instead of reading the column, this string is what
# stops being sent — and nothing else about the response would change.
STORED_RULE = "Dress for the inside of a submarine."


def swap_look(wardrobe: dict[str, Item], keep: tuple[str, ...], new: str) -> StylistResponse:
    """One look on the single-day path: the locked garments plus the replacement.

    No `day` and no `packing_list`, which is what `outfit_recommendation` answers
    — the trip schema's two extra fields belong to `POST /trips/pack` and their
    absence here is the contract being exercised.
    """
    return StylistResponse(
        looks=(
            StylistLook(
                title="Day two, second attempt",
                item_ids=tuple(wardrobe[name].short_id for name in (*keep, new)),
                reasoning="The white sneaker keeps the trousers from reading formal.",
                weather_note="24°C — no coat needed.",
            ),
        ),
        missing_pieces=(
            MissingPiece(
                category="bag", description="a small crossbody", reason="nothing packable"
            ),
        ),
        message="Swapped the shoes.",
    )


@pytest.fixture
def packed(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    stylist: Callable[..., FakeStylist],
) -> Callable[..., tuple[str, FakeStylist]]:
    """A packed three-day trip, and the fake that will answer the swap next."""

    def _pack(
        answer: StylistResponse | Exception | None = None,
        evenings: tuple[int, ...] = (),
    ) -> tuple[str, FakeStylist]:
        asked_geocoder = geocoder()
        asked_forecast = forecasts()
        fake = stylist(
            plan(wardrobe, DAYS, evenings),
            swap_look(wardrobe, keep=("top_b", "bottom_a"), new=REPLACEMENT)
            if answer is None
            else answer,
        )
        response = client.post(
            "/api/v1/trips/pack",
            json=body(days=DAYS, evenings=evenings),
            headers=authorization(user),
        )
        assert response.status_code == 200
        # Cleared so that "no provider was called" below is a claim about the
        # swap alone. The pack legitimately called both.
        asked_geocoder.clear()
        asked_forecast.clear()
        return response.json()["trip"]["id"], fake

    return _pack


def swap(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    trip_id: str,
    **overrides: Any,
) -> Any:
    payload: dict[str, Any] = {
        "day": DAY,
        # Required from 4.16 and defaulted here rather than at every call site:
        # most of this suite packs single-slot trips, and the ones that do not
        # override it.
        "slot": "day",
        "item_id": overrides.pop("item_id"),
        "replace_role": "shoes",
        "exclude_item_ids": [],
    } | overrides
    return client.post(f"/api/v1/trips/{trip_id}/swap", json=payload, headers=authorization(user))


def day_look(payload: dict[str, Any], day: int, slot: str = "day") -> dict[str, Any] | None:
    """One slot's look, joined through `days[].slots[].look_id` as a client would."""
    slots = next(entry["slots"] for entry in payload["trip"]["days"] if entry["day"] == day)
    look_id = next((entry["look_id"] for entry in slots if entry["slot"] == slot), None)
    return next((look for look in payload["looks"] if look["id"] == look_id), None)


def names(look: dict[str, Any] | None) -> set[str]:
    return {item["id"] for item in (look or {"items": []})["items"]}


# --- what a swap changes ----------------------------------------------------


def test_a_swap_replaces_the_named_garment_on_that_day(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    trip_id, _ = packed()

    response = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert response.status_code == 200
    changed = names(day_look(response.json(), DAY))
    assert str(wardrobe[REPLACEMENT].id) in changed
    assert str(wardrobe[REPLACED].id) not in changed


def test_a_swap_leaves_every_other_day_alone(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`STAGE-4` 4.6a's first criterion, and `DECISIONS.md` 192's first property.

    Day 1 wears `shoes_a` too, so a substitution that propagated would be visible
    here — which is the whole reason the fixture makes the two days share a shoe.
    """
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()

    after = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    for day in (1, 3):
        assert names(day_look(after, day)) == names(day_look(before, day))
    assert str(wardrobe[REPLACED].id) in names(day_look(after, 1))


def test_the_new_look_takes_the_day_rather_than_leaving_a_gap(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Unlike a repack's detach, which `05-FRONTEND-SPEC.md` renders as a gap."""
    trip_id, _ = packed()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    assert all(
        entry["look_id"] is not None for day in payload["trip"]["days"] for entry in day["slots"]
    )
    assert len(payload["looks"]) == DAYS


def test_the_swap_survives_a_reload(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """The half `POST /looks/suggest` could not have delivered.

    That endpoint persists a look with no `trip_id`, so the trip would answer the
    old look on the next read and the swap would exist only in the browser.
    """
    trip_id, _ = packed()
    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    reloaded = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()

    assert str(wardrobe[REPLACEMENT].id) in names(day_look(reloaded, DAY))
    assert str(wardrobe[REPLACED].id) not in names(day_look(reloaded, DAY))


# --- the slot ---------------------------------------------------------------


def test_a_swap_on_an_evening_leaves_the_days_look_alone(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """The hole 4.15 opened: both looks of a date answered to one lookup key."""
    trip_id, _ = packed(
        answer=swap_look(wardrobe, keep=("top_b", "bottom_b"), new=REPLACEMENT),
        evenings=(DAY,),
    )
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    unchanged = names(day_look(before, DAY))

    payload = swap(
        client,
        user,
        authorization,
        trip_id,
        slot="evening",
        item_id=str(wardrobe["shoes_b"].id),
    ).json()

    assert names(day_look(payload, DAY)) == unchanged
    evening = names(day_look(payload, DAY, "evening"))
    assert str(wardrobe[REPLACEMENT].id) in evening
    assert str(wardrobe["shoes_b"].id) not in evening


def test_a_slot_the_day_has_not_got_is_item_not_in_look(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """One code for two facts, taken deliberately: with no look for that slot, no
    item is in it, and the badge only exists beside a look that does. The
    assertion that matters is the second — refused before the model is asked, so
    a broken client costs a query and not a call."""
    trip_id, fake = packed()

    response = swap(
        client,
        user,
        authorization,
        trip_id,
        slot="evening",
        item_id=str(wardrobe[REPLACED].id),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "item_not_in_look"
    assert fake.calls == 1


def test_the_replaced_look_is_the_slots_row_and_no_other(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """O-32's detach, narrowed to one slot: the evening leaves and the day stays."""
    trip_id, _ = packed(
        answer=swap_look(wardrobe, keep=("top_b", "bottom_b"), new=REPLACEMENT),
        evenings=(DAY,),
    )
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    evening_id = uuid.UUID(day_look(before, DAY, "evening")["id"])
    day_id = uuid.UUID(day_look(before, DAY)["id"])
    saved = db.get(Look, evening_id)
    assert saved is not None
    saved.is_saved = True
    db.commit()

    swap(
        client,
        user,
        authorization,
        trip_id,
        slot="evening",
        item_id=str(wardrobe["shoes_b"].id),
    )

    detached = db.get(Look, evening_id)
    assert detached is not None
    # `trip_id` and `slot` clear together — `ck_looks_slot_belongs_to_a_trip`
    # reads the two as one fact, and `0006` refuses the row otherwise.
    assert detached.trip_id is None
    assert detached.slot is None
    assert detached.is_saved is True

    kept = db.get(Look, day_id)
    assert kept is not None
    assert kept.trip_id is not None
    assert kept.slot == "day"


def test_the_packing_list_keeps_a_garment_the_evening_still_wears(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`top_b` is worn by day 2's two slots and by no other date.

    Swapping it out of the day look must leave it in the suitcase, because the
    evening still wears it — the same property `shoes_a` measures across two
    *days*, one level down. It holds because `_swapped_ids` reads every look the
    trip still has rather than the one that changed.
    """
    trip_id, _ = packed(
        answer=swap_look(wardrobe, keep=("shoes_a", "bottom_a"), new="top_c"),
        evenings=(DAY,),
    )

    payload = swap(
        client,
        user,
        authorization,
        trip_id,
        item_id=str(wardrobe["top_b"].id),
        replace_role="top",
    ).json()

    assert str(wardrobe["top_b"].id) not in names(day_look(payload, DAY))
    assert str(wardrobe["top_b"].id) in names(day_look(payload, DAY, "evening"))
    assert str(wardrobe["top_b"].id) in payload["trip"]["packing_list"]["item_ids"]
    # The occasion of the slot that was swapped, not of the date's last entry.
    # `_swap_context`'s lookup was keyed by day alone until 4.16, and over a
    # two-slot date it kept the evening's — so this look would have come back
    # dressed for dinner with nothing on the wire to say so.
    assert day_look(payload, DAY)["occasion"] == "work"
    assert day_look(payload, DAY, "evening")["occasion"] == "evening"


# --- what reaches the model -------------------------------------------------


def test_the_stored_rule_is_sent_and_never_rebuilt(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`DECISIONS.md` 199's stored rule, and the mutation this test exists for.

    A swap that called `build_rule` again would judge one day of a packed plan
    against whatever the band table says today, and the response would look
    identical. The column is overwritten with a sentence no three numbers can
    produce, so the only way this passes is by reading it.
    """
    trip_id, fake = packed()
    trip = db.scalar(select(Trip).where(Trip.id == uuid.UUID(trip_id)))
    assert trip is not None
    trip.forecast = [
        {**entry, "rule": STORED_RULE} if entry["day"] == DAY else entry
        for entry in trip.forecast or []
    ]
    db.commit()

    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert fake.contexts[-1].weather_rule == STORED_RULE


def test_the_swap_asks_no_geocoder_and_no_forecast(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    geocoder: Callable[..., list[str]],
    forecasts: Callable[..., list[Any]],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """One model call and nothing else leaves the process.

    The trip is not moving and its forecast is stored, so re-resolving either
    would spend a provider call to arrive back where the column already is.
    """
    trip_id, fake = packed()
    asked_geocoder = geocoder()
    asked_forecast = forecasts()

    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert asked_geocoder == []
    assert asked_forecast == []
    assert fake.calls == 2


def test_the_rest_of_the_look_is_locked_and_the_rejected_piece_excluded(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Rules 7 and 8's fields, built from the row rather than sent by the client."""
    trip_id, fake = packed()

    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    context = fake.contexts[-1]
    kept = {name for name in OUTFITS[DAY - 1] if name != REPLACED}
    assert set(context.locked_ids) == {wardrobe[name].short_id for name in kept}
    assert wardrobe[REPLACED].short_id in context.excluded_ids
    assert context.replace_role == "shoes"


def test_the_clients_exclusions_are_carried_and_the_rejected_piece_appended(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`STAGE-4` 4.6a's fourth criterion across two taps rather than one.

    The client accumulates what earlier swaps on this day rejected; the server
    cannot derive it, because the looks that carried those rejections are gone.
    """
    trip_id, fake = packed()

    swap(
        client,
        user,
        authorization,
        trip_id,
        item_id=str(wardrobe[REPLACED].id),
        exclude_item_ids=[str(wardrobe["shoes_b"].id)],
    )

    excluded = set(fake.contexts[-1].excluded_ids)
    assert wardrobe["shoes_b"].short_id in excluded
    assert wardrobe[REPLACED].short_id in excluded


def test_the_days_own_occasion_is_sent(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    trip_id, fake = packed()

    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    context = fake.contexts[-1]
    assert context.occasion == "work"
    assert context.date == date.today() + timedelta(days=2) + timedelta(days=DAY - 1)


# --- the packing list -------------------------------------------------------


def test_the_packing_list_gains_the_new_item(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    trip_id, _ = packed()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    assert str(wardrobe[REPLACEMENT].id) in payload["trip"]["packing_list"]["item_ids"]


def test_an_item_still_worn_on_another_day_stays_in_the_packing_list(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`STAGE-4` 4.6a's third criterion, and the whole reason the feature says so.

    Day 1 still wears `shoes_a`, so pulling it off day 2 does not take it out of
    the suitcase — and a swap that removed it would make the reuse summary a lie.
    """
    trip_id, _ = packed()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    assert str(wardrobe[REPLACED].id) in payload["trip"]["packing_list"]["item_ids"]


def test_an_item_no_day_still_wears_leaves_the_packing_list(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """The other half of criterion 2: the suitcase has to be able to shrink.

    `top_b` is worn on day 2 alone, so swapping it out is the case where the
    packing list must lose a row.
    """
    trip_id, _ = packed(
        answer=swap_look(
            {name: item for name, item in wardrobe.items()},
            keep=("shoes_a", "bottom_a"),
            new="top_c",
        )
    )

    payload = swap(
        client,
        user,
        authorization,
        trip_id,
        item_id=str(wardrobe["top_b"].id),
        replace_role="top",
    ).json()

    assert str(wardrobe["top_b"].id) not in payload["trip"]["packing_list"]["item_ids"]


def test_every_look_item_is_still_in_the_packing_list(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Rule 5's second direction, held after an edit the model never saw whole.

    The stylist was asked for one day and answered one look; the invariant is the
    endpoint's to keep, which is why the list is computed over every look rather
    than patched around the one that changed.
    """
    trip_id, _ = packed()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    packing = set(payload["trip"]["packing_list"]["item_ids"])
    worn = {item["id"] for look in payload["looks"] for item in look["items"]}
    assert worn <= packing
    assert packing == worn


def test_the_surviving_items_keep_their_order(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Survivors in place, newcomer last — and `reuse_summary` reads this order.

    A list rebuilt from scratch would answer the same *set* and could resequence
    the tie-break, which is how one plan comes to summarise two ways.
    """
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    existing = before["trip"]["packing_list"]["item_ids"]

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    after = payload["trip"]["packing_list"]["item_ids"]
    assert after[: len(existing)] == existing
    assert after[-1] == str(wardrobe[REPLACEMENT].id)


def test_the_reuse_summary_is_recomputed(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """The counts move with the list, and `most_reused` is re-derived with them.

    `shoes_a` was worn on two of three days before the swap and one after, so a
    summary left alone would still name it.
    """
    trip_id, _ = packed()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    summary = payload["trip"]["packing_list"]["reuse_summary"]
    assert summary["item_count"] == len(payload["trip"]["packing_list"]["item_ids"])
    assert summary["look_count"] == DAYS
    assert summary["most_reused"] != {"item_id": str(wardrobe[REPLACED].id), "days": 2}


# --- what happens to the look that was there --------------------------------


def test_an_unmarked_look_is_deleted(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    old_id = uuid.UUID(day_look(before, DAY)["id"])

    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert db.scalar(select(Look).where(Look.id == old_id)) is None


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("is_saved", True),
        ("feedback", FEEDBACK_UP),
        ("feedback", FEEDBACK_DOWN),
        ("worn_at", date.today()),
    ],
)
def test_a_marked_look_is_detached_rather_than_deleted(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
    column: str,
    value: Any,
) -> None:
    """`AUDITS.md` O-32's option 2, one level down from the repack that set it.

    The three columns are the same three, and the reason is the same: `is_saved`
    puts a look on `/saved`, `feedback` is what the preference block counts, and
    `worn_at` has already moved `items.wear_count` in a transaction this one
    cannot reverse.
    """
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    old_id = uuid.UUID(day_look(before, DAY)["id"])
    old = db.scalar(select(Look).where(Look.id == old_id))
    assert old is not None
    setattr(old, column, value)
    db.commit()

    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    db.expire_all()
    detached = db.scalar(select(Look).where(Look.id == old_id))
    assert detached is not None
    assert detached.trip_id is None
    assert getattr(detached, column) == value


def test_a_detached_look_keeps_all_three_columns(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """The detach writes `trip_id` and nothing else.

    A statement that reset the marks on its way past would keep the row and lose
    the signal, which is the failure option 2 exists to prevent — and it would
    still pass a test that only asked whether the row survived.
    """
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    old_id = uuid.UUID(day_look(before, DAY)["id"])
    old = db.scalar(select(Look).where(Look.id == old_id))
    assert old is not None
    old.is_saved = True
    old.feedback = FEEDBACK_DOWN
    old.worn_at = date.today()
    db.commit()

    swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    db.expire_all()
    detached = db.scalar(select(Look).where(Look.id == old_id))
    assert detached is not None
    assert (detached.is_saved, detached.feedback, detached.worn_at) == (
        True,
        FEEDBACK_DOWN,
        date.today(),
    )


def test_a_detached_look_leaves_the_trip_and_its_items_behind(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """A saved look survives on `/saved` and is no longer part of the trip."""
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    old_id = day_look(before, DAY)["id"]
    old = db.scalar(select(Look).where(Look.id == uuid.UUID(old_id)))
    assert old is not None
    old.is_saved = True
    db.commit()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    assert old_id not in [look["id"] for look in payload["looks"]]
    saved = client.get("/api/v1/looks", params={"is_saved": True}, headers=authorization(user))
    assert old_id in [look["id"] for look in saved.json()["looks"]]


# --- the ordering, and the refusals -----------------------------------------


def test_a_stylist_failure_leaves_the_days_look_alone(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`DECISIONS.md` 200's ordering, and the mutation this test exists for.

    A destructive half above the model call would answer `502` having already
    taken the day's look away — and the user would have pressed ↻ and lost an
    outfit. Nothing is written until there is something to write.
    """
    trip_id, _ = packed(answer=APITimeoutError(request=None))  # type: ignore[arg-type]
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()

    response = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert response.status_code == 502
    assert response.json()["code"] == "stylist_failed"
    after = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    assert day_look(after, DAY)["id"] == day_look(before, DAY)["id"]
    assert names(day_look(after, DAY)) == names(day_look(before, DAY))
    assert after["trip"]["packing_list"] == before["trip"]["packing_list"]


def test_swapping_a_piece_that_is_not_in_the_days_look(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """The stale-badge case, answered before the model rather than after it.

    `top_c` is a real garment this account owns and day 2 does not wear it, which
    is what a badge tapped after a repack in another tab looks like.
    """
    trip_id, fake = packed()

    response = swap(
        client, user, authorization, trip_id, item_id=str(wardrobe["top_c"].id), replace_role="top"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "item_not_in_look"
    # One call, which is the pack's. The swap cost nothing.
    assert fake.calls == 1


def test_a_day_with_no_look_is_item_not_in_look(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """No twentieth code for a state the screen draws no badge on.

    A repack detaches a saved look and leaves its day empty; there is no look, so
    the item is not in it, and that sentence is true rather than a stretch.
    """
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    orphan = db.scalar(select(Look).where(Look.id == uuid.UUID(day_look(before, DAY)["id"])))
    assert orphan is not None
    # Both columns, because `0006`'s CHECK reads them together: a look leaving a
    # trip with its slot still set is a row the database refuses, which is what
    # `_write` and `_replace_look` do in one `UPDATE`. Detaching by hand here
    # rather than through a repack, so the day is empty without a second model
    # call — the same shortcut this test has always taken, now with the second
    # column the detach owns.
    orphan.trip_id = None
    orphan.slot = None
    db.commit()

    response = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert response.status_code == 422
    assert response.json()["code"] == "item_not_in_look"


@pytest.mark.parametrize("day", [0, DAYS + 1, -1])
def test_a_day_this_trip_has_not_got_is_a_validation_error(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
    day: int,
) -> None:
    """One check and one message for both ends, which is `trip_too_long`'s shape.

    A `ge=1` on the schema would have answered `0` and `4` differently, and the
    request schema cannot know how many days a trip has.
    """
    trip_id, _ = packed()

    response = swap(
        client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id), day=day
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_an_archived_piece_elsewhere_in_the_look_is_locked_unavailable(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`DECISIONS.md` 177's `422`, reached from the row rather than from the body.

    Rule 1 would otherwise call the id a hallucination two model calls later, and
    the answer would arrive as a `502` about a request `422` is the truth about.
    """
    trip_id, fake = packed()
    wardrobe["bottom_a"].is_archived = True
    db.commit()

    response = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert response.status_code == 422
    assert response.json()["code"] == "locked_unavailable"
    assert fake.calls == 1


def test_a_wardrobe_below_six_is_refused_before_the_model(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Five usable rows, which is one below the single-day threshold.

    Nothing in day 2's look is archived, so this is the wardrobe guard answering
    and not `locked_unavailable` — the order the handler checks them in.
    """
    trip_id, fake = packed()
    for name in ("top_a", "top_c", "bag", "accessory", "bottom_b"):
        wardrobe[name].is_archived = True
    db.commit()

    response = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert response.status_code == 400
    assert response.json()["code"] == "wardrobe_too_small"
    assert fake.calls == 1


def test_a_wardrobe_below_the_trips_eight_can_still_swap(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Seven usable rows: too few to pack a trip, enough to change one shoe.

    This is the test that pins the threshold at **six** rather than at this
    module's eight. A swap runs the single-day rule order, where rule 11 — no two
    looks alike — does not run at all, so eight would refuse a look the model can
    build. Without this test, `MIN_SWAP_WARDROBE_ITEMS = 8` passes the suite.
    """
    trip_id, _ = packed()
    for name in ("top_a", "top_c", "bag"):
        wardrobe[name].is_archived = True
    db.commit()

    response = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert response.status_code == 200


def test_another_accounts_trip_is_not_found(
    client: TestClient,
    user: User,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    trip_id, _ = packed()

    response = swap(client, make_user(), authorization, trip_id, item_id=str(wardrobe[REPLACED].id))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_an_unknown_field_is_refused(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`extra="forbid"`, as every body in this API has since 2.7.

    A dropped key is an instruction the user gave and the look did not obey,
    reported as a success.
    """
    trip_id, _ = packed()

    response = swap(
        client,
        user,
        authorization,
        trip_id,
        item_id=str(wardrobe[REPLACED].id),
        locked_item_ids=[],
    )

    assert response.status_code == 422


def test_a_role_is_required(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Required here where `POST /looks/suggest` makes it optional.

    That endpoint serves plain suggestions too, so it needs a validator for the
    role-without-locks body; this one does nothing else, so requiring the field
    deletes that body rather than validating it.
    """
    trip_id, _ = packed()
    response = client.post(
        f"/api/v1/trips/{trip_id}/swap",
        json={"day": DAY, "item_id": str(wardrobe[REPLACED].id)},
        headers=authorization(user),
    )

    assert response.status_code == 422


def test_the_new_look_takes_the_trips_occasion_not_the_old_looks(
    client: TestClient,
    db: Session,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`trips.occasions` is the source of truth, not the row being replaced.

    The two agree on every trip this API can write, so the day's look is edited
    by hand to separate them — which is the only way to tell the two readings
    apart, and the reason this test exists rather than being covered by the
    others. `occasion` was struck from both AI schemas at 4.3 precisely so that
    the value stored is the one the user sent (`DECISIONS.md` 193), and reading
    it off the old look would carry a drifted value forward for ever.
    """
    trip_id, _ = packed()
    before = client.get(f"/api/v1/trips/{trip_id}", headers=authorization(user)).json()
    old = db.scalar(select(Look).where(Look.id == uuid.UUID(day_look(before, DAY)["id"])))
    assert old is not None
    old.occasion = "evening"
    db.commit()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    assert day_look(payload, DAY)["occasion"] == "work"


def test_the_tie_break_reads_the_packing_lists_own_order(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """Most days, then **first in the packing list** — the documented tie-break.

    Swapping `top_c` off day 3 for `top_a` leaves three garments worn on two days
    each: `shoes_a`, `top_a` and `bottom_a`. Which one `most_reused` names is
    decided entirely by the order of `packing_list.item_ids`, and `shoes_a` is
    first in it. The fixture gives `shoes_a` the highest id, so an implementation
    that sorted the list before summarising it — or rebuilt it from the looks —
    would answer one of the other two rather than passing by luck.
    """
    trip_id, _ = packed(answer=swap_look(wardrobe, keep=("shoes_b", "bottom_b"), new="top_a"))

    payload = swap(
        client,
        user,
        authorization,
        trip_id,
        item_id=str(wardrobe["top_c"].id),
        day=3,
        replace_role="top",
    ).json()

    summary = payload["trip"]["packing_list"]["reuse_summary"]
    assert summary["most_reused"] == {"item_id": str(wardrobe["shoes_a"].id), "days": 2}
    assert payload["trip"]["packing_list"]["item_ids"][0] == str(wardrobe["shoes_a"].id)


def test_the_response_is_the_whole_trip(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    wardrobe: dict[str, Item],
    packed: Callable[..., tuple[str, FakeStylist]],
) -> None:
    """`TripDetailResponse`, not a fragment — and no `missing_pieces`.

    The packing list moved, so the day strip, the reuse summary and every look
    are answered together; a client that had to reassemble a plan from one look
    would be the second thing that knows how a trip is put together.
    """
    trip_id, _ = packed()

    payload = swap(client, user, authorization, trip_id, item_id=str(wardrobe[REPLACED].id)).json()

    assert set(payload) == {"trip", "looks"}
    assert len(payload["trip"]["days"]) == DAYS
    assert payload["trip"]["packing_list"]["reuse_summary"]["look_count"] == DAYS

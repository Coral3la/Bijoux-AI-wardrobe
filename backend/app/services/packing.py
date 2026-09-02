"""A destination and a date range in, a suitcase out. Stage 4's signature
feature, and the only place in this project that asks the model for more than
one look at a time.

`pack_trip` is **pure with respect to the database**: it holds no `Session`,
reads no rows and writes none. It is handed the wardrobe and the learned
preferences, and it hands back a `Trip` that has never been added to a session
and the looks that belong to it. `POST /trips/pack` persists all of it at 4.4,
in one transaction it owns. That is `services/stylist.py`'s property one layer
up (`DECISIONS.md` 162), and it is what lets the reuse arithmetic below be
tested with no database in reach.

**One model call for the whole trip, never one per day.** Per-day calls cannot
reuse items intelligently, because each one is blind to what the others chose,
and reuse is the entire point of a packing list — `01-ARCHITECTURE.md` flow 3
and `STAGE-4` 4.3 both say so, and the reuse target below is what makes the
instruction numeric.

Raises its own exceptions and never an `ApiError` (`DECISIONS.md` 044), so it
stays callable from a script with no request in flight; 4.4 maps them. The
weather and geocoding services' exceptions travel through untouched, because
`forecast_unavailable` and `geocoding_unavailable` already mean on this endpoint
exactly what they mean on the two that raise them.
"""

import datetime
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.models.trip import Trip
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.geocoding import Location, search_locations
from app.services.stylist import MissingPiece, TripContext, TripDay
from app.services.stylist_runner import judged
from app.services.weather import Forecast, build_rule, get_daily_forecast, summarize_forecast

logger = logging.getLogger(__name__)


class PackingError(Exception):
    """A trip was asked for and no plan could be made."""


class DestinationNotFoundError(PackingError):
    """The geocoder answered, and nothing matched what the user typed."""


class StylistRejectedError(PackingError):
    """The model answered twice and neither answer passed validation."""


@dataclass(frozen=True, slots=True)
class TripSlot:
    """One look the trip asks for: which day, which half of it, and what for.

    Named after `stylist.TripDay`, which it becomes one step later — the same row
    with the forecast added — and not after `enums.Slot`, which is the vocabulary
    `slot` draws its two values from.

    A dataclass rather than a `(day, slot, occasion)` tuple: two of the three
    fields are enum values whose meaning is not positional, `entry.slot` reads
    where `entry[1]` has to be remembered, and mypy checks a field name where it
    cannot check a tuple index.

    Not `schemas/trip.py`'s `TripOccasion`, which is these three values on the
    wire. `DECISIONS.md` 196 keeps wire models out of this service; the route
    maps one into the other, exactly as it maps a look request into
    `StylistContext`.
    """

    day: int
    slot: str
    occasion: str


@dataclass(frozen=True, slots=True)
class TripRequest:
    """What the user asked for, as this service reads it.

    A frozen dataclass here rather than a Pydantic model in `app/schemas/trip.py`
    because that module belongs to task 4.4: a wire model written a task early is
    a contract invented by the task that does not own it. 4.4 maps its request
    body into this, exactly as `POST /looks/suggest` maps its body into
    `StylistContext`. `DECISIONS.md` 196.

    `occasions` is **one entry per look and no longer one per day**, from task
    4.14: a date carries one `TripSlot` or two, and `(day, slot)` is what names a
    look in every layer below this one. It stopped being positional in the same
    move — index 0 was day 1 while the two counts were the same number, and a
    list that can hold two entries for day 2 cannot be read by index at all.

    The route is what checks that the days are `1..n` in order and that a date's
    entries are `day` then `evening`, so the tuple cannot be ragged by the time
    it arrives; `pack_trip` still refuses a set of days that disagrees with the
    date range, and one `(day, slot)` asked for twice, because a caller's bug
    should not reach the model.
    """

    destination: str
    start_date: datetime.date
    end_date: datetime.date
    occasions: tuple[TripSlot, ...]
    notes: str | None = None

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True, slots=True)
class PackedLook:
    """One outfit — one slot of one day — with its items already resolved.

    Carries hydrated `ItemResponse`s rather than `short_id`s because both of
    4.4's jobs need them: `item.id` for the `look_items` rows and the whole item
    for the response body. Resolving once here is one lookup with one answer.

    `for_date` is the day this look is *for*, which is the column `looks` has —
    `day` is the trip's own ordinal and lives only in the AI contract and the
    day strip. The two are the same fact counted from different origins.

    **`for_date` stopped identifying a look at 4.14** and `slot` is what tells
    two looks of one date apart — which is `looks.slot` on the row, and the
    reason `0006` put the unique index on the pair rather than on the date.
    """

    day: int
    slot: str
    for_date: datetime.date
    occasion: str
    title: str
    items: tuple[ItemResponse, ...]
    reasoning: str
    weather_note: str


@dataclass(frozen=True, slots=True)
class PackingResult:
    """An unpersisted trip and its looks.

    `trip` is a `Trip` that has never been added to a session: its `id` and
    `created_at` are server defaults and are `None` until 4.4 flushes it. Every
    JSON column on it is already filled — `occasions`, `forecast` and
    `packing_list` — because their shapes are this task's and the route should
    not have to know them.
    """

    trip: Trip
    looks: tuple[PackedLook, ...]
    missing_pieces: tuple[MissingPiece, ...]


def reuse_target(days: int) -> int:
    """`STAGE-4`'s `min(days * 4, days + 8)`, the number the prompt asks for.

    Prompt-only, and deliberately not a validation rule: a wardrobe that cannot
    dress seven days from twelve garments should answer with the looks it can
    build rather than spend the one retry and then a `502` on arithmetic —
    `DECISIONS.md` 158's reasoning about the weather rule, one instruction along.
    What measures it is `STAGE-4`'s prompt-tuning note, against the demo wardrobe
    at 3, 5 and 7 days, recorded in `docs/eval-results.md`.

    It lives here rather than in the prompt builder so that the tuning that note
    describes moves one number in the packing module. `DECISIONS.md` 193.
    """
    return min(days * 4, days + 8)


async def _destination(query: str) -> Location:
    """The first place the geocoder matches, or `DestinationNotFoundError`.

    The first result rather than a chosen one: `GET /me/locations/search` returns
    up to five and the trip form picks one (4.5), so by the time a destination
    reaches this service the user has already disambiguated it. A free-text
    destination that matches nothing is a different failure from a geocoder that
    did not answer — `search_locations` raises `GeocodingError` for the second
    and returns `[]` for the first, and `DECISIONS.md` 152 is the argument for
    keeping them apart.
    """
    matches = await search_locations(query)
    if not matches:
        raise DestinationNotFoundError(f"No place matches {query!r}.")
    return matches[0]


def _days(request: TripRequest, forecasts: Sequence[Forecast]) -> tuple[TripDay, ...]:
    """One `TripDay` per requested slot: the ordinal, the slot, the occasion and
    the rule.

    One per **entry** rather than one per forecast day, which is the shape change
    4.14 is: a date with an evening out is two lines in the trip message and two
    looks in the answer, and it is `(day, slot)` that pairs them.

    The forecast is therefore looked up by ordinal rather than zipped, because
    the two sequences stopped being the same length. **Both slots of a date get
    the same summary and the same rule**, which is the contract and not a
    shortcut: `trips.forecast` holds one row per calendar day, so an evening
    dressed against its own numbers would need an hourly forecast and a second
    band table. What separates the two looks is the occasion.
    `DECISIONS.md` 225.

    `build_rule` reads `temp_max_c` for `DECISIONS.md` 142's reason, which is the
    single-day path's: two temperatures arrive and the document's worked example
    is only self-consistent under the maximum.
    """
    by_ordinal = {index + 1: forecast for index, forecast in enumerate(forecasts)}

    days = []
    for entry in request.occasions:
        forecast = by_ordinal[entry.day]
        days.append(
            TripDay(
                day=entry.day,
                slot=entry.slot,
                date=forecast.date,
                occasion=entry.occasion,
                forecast_summary=summarize_forecast(forecast),
                weather_rule=build_rule(forecast.temp_max_c, forecast.precip_mm, forecast.wind_kph),
            )
        )
    return tuple(days)


def _forecast_column(
    days: Sequence[TripDay], forecasts: Sequence[Forecast]
) -> list[dict[str, Any]]:
    """What `trips.forecast` stores: the parsed days, with each day's rule.

    **Not the raw provider body**, which `02-DATA-MODEL.md` called it until 4.3
    and which this service never holds — `get_daily_forecast` answers parsed
    `Forecast` objects, so the unparsed JSON is not in reach to store. What is
    stored is exactly what `04-API-SPEC.md`'s `days[]` renders, minus the
    occasion and the look id the route adds: reopening a trip re-reads the plan
    rather than re-fetching a forecast that has since moved.

    The rule is stored beside the numbers rather than rebuilt on read. It is a
    pure function of three of them, so a reader could recompute it — but then a
    trip packed under one version of the band table would render under another,
    and the sentence the model actually obeyed would be lost.

    **One row per calendar day and not per look**, which is where this stopped
    being a `zip` at 4.14: `days` now holds one entry per requested slot, so a
    date with an evening out arrived twice and the column would have grown a day
    the trip has not got. The rules collapse into a `{ordinal: rule}` map, which
    loses nothing because both slots of a date are built from the one forecast
    row.
    """
    rules = {day.day: day.weather_rule for day in days}
    return [
        {
            "day": ordinal,
            "date": forecast.date.isoformat(),
            "temp_min_c": forecast.temp_min_c,
            "temp_max_c": forecast.temp_max_c,
            "precip_mm": forecast.precip_mm,
            "wind_kph": forecast.wind_kph,
            "condition": forecast.condition.value,
            "rule": rules[ordinal],
        }
        for ordinal, forecast in enumerate(forecasts, start=1)
    ]


def reuse_summary(
    item_ids: Sequence[str],
    outfits: Sequence[tuple[datetime.date | None, Sequence[ItemResponse]]],
) -> dict[str, Any]:
    """The numbers `05-FRONTEND-SPEC.md` §7 prints, and not the sentence.

    *"8 items across 5 looks — the jeans appear on 3 days"* is two renderings of
    three numbers, and the sentence is built in the frontend behind an i18n key:
    a server that wrote English into a `JSONB` column would put a user-facing
    string where no translation can reach it (`CONVENTIONS.md`).

    `most_reused` is `null` when nothing is worn twice, which is an ordinary
    outcome on a short trip rather than an error. **The tie-break is written
    down** — most days, then first in the packing list — so that two garments
    worn on three days each cannot make the same plan summarise differently on
    two runs. It is the packing list's order that decides, not the order the
    days happened to wear things in. `02-DATA-MODEL.md` carries this shape;
    `DECISIONS.md` 193.

    **Public, and taking outfits rather than looks, since task 4.6a-1.** It was
    `_reuse_summary(item_ids, looks: Sequence[PackedLook])` while `pack_trip`
    was the only writer of `trips.packing_list`; `POST /trips/{id}/swap` is the
    second, and it holds `LookResponse`s rather than `PackedLook`s. The tie-break
    is the reason it is shared rather than copied — a second implementation of it
    is the one thing that could make one plan summarise two ways — and the
    parameter narrowed to what this function actually reads. `DECISIONS.md` 209.

    **`look_count` and `most_reused.days` stopped being the same number at
    4.14.** One counts the entries in `outfits`, the other counts the distinct
    **dates** a garment is worn on, so a garment worn to the office and again to
    dinner on Monday and on no other date reports **one** day — which fails the
    `> 1` test and leaves `most_reused` null, a real reuse that produces no reuse
    line. That is taken deliberately: `05-FRONTEND-SPEC.md` §7 renders this
    number into *"You'll wear the camel trousers on 3 days"*, and a line about
    days that counted looks would print a false sentence on the one line in the
    product that makes this feature land. `DECISIONS.md` 225.

    **The date arrives beside each outfit** rather than the outfits arriving
    grouped by it. Both callers hold it — `pack_trip` on `PackedLook.for_date`,
    the swap on the `looks` row it hydrated from — where a parallel
    `Sequence[date]` would be the two-sequences-that-must-agree shape 195
    refused, and a mapping would make `look_count` a sum over a grouping done
    twice.

    **The date is nullable because `looks.for_date` is**, and this is where that
    parts company with `_by_day`, which drops an undated look rather than
    guessing at one. Dropping is not available here: `look_count` counts the
    looks it was handed, so a dropped one would make a trip report fewer looks
    than it has. Undated outfits share the one `None` bucket instead, which can
    never count as two dates. Nothing this API writes leaves a trip look
    without a date.
    """
    # A set of dates per garment, so that wearing one thing in both slots of a
    # Monday counts once — which is the same collapse the old `Counter` did
    # within a single look, one level up.
    worn: dict[str, set[datetime.date | None]] = {item_id: set() for item_id in item_ids}
    for for_date, items in outfits:
        for item in items:
            worn.setdefault(str(item.id), set()).add(for_date)

    # `max` returns the **first** element with the maximal key, and `item_ids`
    # is in packing-list order — so iterating it is the whole of the tie-break
    # and an explicit second key term would be dead weight. A mutation run at 4.3
    # proved it: adding `-item_ids.index(...)` changed no test, because it could
    # not change an answer.
    best = max(item_ids, key=lambda item_id: len(worn[item_id]), default=None)

    most_reused = (
        {"item_id": best, "days": len(worn[best])}
        if best is not None and len(worn[best]) > 1
        else None
    )
    return {
        "item_count": len(item_ids),
        "look_count": len(outfits),
        "most_reused": most_reused,
    }


async def pack_trip(
    user: User,
    wardrobe: Sequence[ItemResponse],
    request: TripRequest,
    preferences: str | None = None,
) -> PackingResult:
    """`STAGE-4` 4.3's seven steps, with the eighth left to the route.

    Geocode, forecast, one rule per day, the reuse target, one stylist call
    judged by `stylist_runner.judged`, then the arithmetic that turns the
    answer's `short_id`s into the row UUIDs the wire and the column both use.

    **The signature is wider than `STAGE-4` 4.3 printed** — `pack_trip(user,
    trip_request)` — and it has to be: the wardrobe is a query and so is the
    preferences block, and a service that ran them itself would need a `Session`
    and could not be tested without a database. `DECISIONS.md` 196.

    Raises `DestinationNotFoundError`, `StylistRejectedError`, `GeocodingError`,
    `ForecastOutOfRangeError`, `ForecastProviderError`, and `ValueError` for a
    request whose occasions do not match its dates or ask for one slot twice — a
    caller's bug rather than a trip that cannot be packed.
    """
    # The count stopped being the check at 4.14, because a trip with an evening
    # out has more occasions than days. What has to hold is that every day of the
    # range is dressed and no `(day, slot)` is asked for twice — the second is
    # what `uq_looks_trip_day_slot` would refuse four layers down, as a `500`
    # with no code on it.
    covered = sorted({entry.day for entry in request.occasions})
    if covered != list(range(1, request.days + 1)):
        raise ValueError(
            f"The request has occasions for days {covered} and the trip is {request.days} days."
        )

    asked: set[tuple[int, str]] = set()
    for entry in request.occasions:
        if (entry.day, entry.slot) in asked:
            raise ValueError(f"The request asks for day {entry.day} {entry.slot} twice.")
        asked.add((entry.day, entry.slot))

    location = await _destination(request.destination)
    forecasts = await get_daily_forecast(
        location.lat, location.lon, request.start_date, request.end_date
    )
    if len(forecasts) != request.days:
        raise ValueError(
            f"The forecast covers {len(forecasts)} days and the trip is {request.days}."
        )

    days = _days(request, forecasts)
    context = TripContext(
        destination=location.name,
        days=days,
        reuse_target=reuse_target(request.days),
        notes=request.notes,
        height_cm=user.height_cm,
        style_notes=user.style_notes,
        preferences=preferences,
    )

    validation = await judged(wardrobe, context)
    if not validation.ok:
        logger.warning(
            "The stylist failed trip validation twice",
            extra={"violation": validation.violation, "days": request.days},
        )
        raise StylistRejectedError(validation.violation or "The stylist's plan was not usable.")

    # From `validation.response` and never the raw answer: the ids were
    # upper-cased there, and `DECISIONS.md` 164 put normalisation in one place so
    # that a lookup and a stored row cannot disagree about the case of an id.
    answer = validation.response
    known = {item.short_id: item for item in wardrobe}

    # Driven by the slots that were **asked for** rather than by the array that
    # came back, which is what makes the order total now that a date can hold two
    # looks: sorting the answer by `day` alone left the two looks of a Monday in
    # whichever order the model wrote them, and `PackingResult.looks` is what the
    # response body and the `looks` inserts are both ordered by.
    #
    # Rule 10 has passed by here, so every requested pair is answered exactly
    # once and a complete-but-shuffled array is legal. Reading the answer by its
    # pair also drops the old `if look.day is not None` skip, which silently
    # returned a trip one look short of the days it was asked for.
    answered = {(look.day, look.slot): look for look in answer.looks}

    packed = []
    for day in days:
        look = answered[(day.day, day.slot)]
        packed.append(
            PackedLook(
                day=day.day,
                slot=day.slot,
                for_date=request.start_date + datetime.timedelta(days=day.day - 1),
                # From the request rather than the answer, which has carried no
                # occasion since 4.3 struck it from both schemas.
                occasion=day.occasion,
                title=look.title,
                items=tuple(known[item_id] for item_id in look.item_ids),
                reasoning=look.reasoning,
                weather_note=look.weather_note,
            )
        )
    looks = tuple(packed)

    # `short_id` in, UUID out. The model is shown nothing else and the client is
    # given nothing else, so this line is the whole of the boundary between the
    # two vocabularies. `DECISIONS.md` 193.
    packed_ids = [str(known[item_id].id) for item_id in answer.packing_list or ()]

    trip = Trip(
        user_id=user.id,
        destination=request.destination,
        dest_lat=location.lat,
        dest_lon=location.lon,
        start_date=request.start_date,
        end_date=request.end_date,
        # The slot is written down and not inferred. `POST /trips/{id}/repack`
        # rebuilds its request from this column and `0006` backfilled the key
        # into every row that predates it, so a reader that defaulted it would be
        # the one place left in the project that knows the pre-slot shape.
        occasions=[{"day": day.day, "slot": day.slot, "occasion": day.occasion} for day in days],
        forecast=_forecast_column(days, forecasts),
        packing_list={
            "item_ids": packed_ids,
            "reuse_summary": reuse_summary(
                packed_ids, [(look.for_date, look.items) for look in looks]
            ),
        },
        notes=request.notes,
    )
    return PackingResult(trip=trip, looks=looks, missing_pieces=answer.missing_pieces)

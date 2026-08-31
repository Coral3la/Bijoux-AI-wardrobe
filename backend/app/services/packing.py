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
from collections import Counter
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
class TripRequest:
    """What the user asked for, as this service reads it.

    A frozen dataclass here rather than a Pydantic model in `app/schemas/trip.py`
    because that module belongs to task 4.4: a wire model written a task early is
    a contract invented by the task that does not own it. 4.4 maps its request
    body into this, exactly as `POST /looks/suggest` maps its body into
    `StylistContext`. `DECISIONS.md` 196.

    `occasions` is positional — index 0 is **day 1** — where the wire carries
    `[{"day": 1, "occasion": "work"}, …]`. The route is what checks that those
    days are `1..n` before building this, so the tuple cannot be ragged by the
    time it arrives; `pack_trip` still refuses a length that disagrees with the
    date range, because a caller's bug should not reach the model.
    """

    destination: str
    start_date: datetime.date
    end_date: datetime.date
    occasions: tuple[str, ...]
    notes: str | None = None

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True, slots=True)
class PackedLook:
    """One day's outfit, with its items already resolved.

    Carries hydrated `ItemResponse`s rather than `short_id`s because both of
    4.4's jobs need them: `item.id` for the `look_items` rows and the whole item
    for the response body. Resolving once here is one lookup with one answer.

    `for_date` is the day this look is *for*, which is the column `looks` has —
    `day` is the trip's own ordinal and lives only in the AI contract and the
    day strip. The two are the same fact counted from different origins.
    """

    day: int
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
    """One `TripDay` per forecast day: the ordinal, the occasion and the rule.

    `build_rule` reads `temp_max_c` for `DECISIONS.md` 142's reason, which is the
    single-day path's: two temperatures arrive and the document's worked example
    is only self-consistent under the maximum.
    """
    return tuple(
        TripDay(
            day=index + 1,
            date=forecast.date,
            occasion=request.occasions[index],
            forecast_summary=summarize_forecast(forecast),
            weather_rule=build_rule(forecast.temp_max_c, forecast.precip_mm, forecast.wind_kph),
        )
        for index, forecast in enumerate(forecasts)
    )


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
    """
    return [
        {
            "day": day.day,
            "date": forecast.date.isoformat(),
            "temp_min_c": forecast.temp_min_c,
            "temp_max_c": forecast.temp_max_c,
            "precip_mm": forecast.precip_mm,
            "wind_kph": forecast.wind_kph,
            "condition": forecast.condition.value,
            "rule": day.weather_rule,
        }
        for day, forecast in zip(days, forecasts, strict=True)
    ]


def _reuse_summary(item_ids: Sequence[str], looks: Sequence[PackedLook]) -> dict[str, Any]:
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
    """
    worn = Counter(
        str(item.id) for look in looks for item in {item.id: item for item in look.items}.values()
    )
    # `max` returns the **first** element with the maximal key, and `item_ids`
    # is in packing-list order — so iterating it is the whole of the tie-break
    # and an explicit second key term would be dead weight. A mutation run at 4.3
    # proved it: adding `-item_ids.index(...)` changed no test, because it could
    # not change an answer.
    best = max(item_ids, key=lambda item_id: worn[item_id], default=None)

    most_reused = (
        {"item_id": best, "days": worn[best]} if best is not None and worn[best] > 1 else None
    )
    return {
        "item_count": len(item_ids),
        "look_count": len(looks),
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
    request whose occasions do not match its dates — a caller's bug rather than
    a trip that cannot be packed.
    """
    if len(request.occasions) != request.days:
        raise ValueError(
            f"The request has {len(request.occasions)} occasions for {request.days} days."
        )

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

    # Ordered by the day the model gave, not by the position it answered in.
    # Rule 10 has passed by here, so every day is present exactly once, and a
    # complete-but-shuffled array is legal.
    looks = tuple(
        PackedLook(
            day=look.day,
            for_date=request.start_date + datetime.timedelta(days=look.day - 1),
            occasion=request.occasions[look.day - 1],
            title=look.title,
            items=tuple(known[item_id] for item_id in look.item_ids),
            reasoning=look.reasoning,
            weather_note=look.weather_note,
        )
        for look in sorted(answer.looks, key=lambda look: look.day or 0)
        if look.day is not None
    )

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
        occasions=[{"day": day.day, "occasion": day.occasion} for day in days],
        forecast=_forecast_column(days, forecasts),
        packing_list={
            "item_ids": packed_ids,
            "reuse_summary": _reuse_summary(packed_ids, looks),
        },
        notes=request.notes,
    )
    return PackingResult(trip=trip, looks=looks, missing_pieces=answer.missing_pieces)

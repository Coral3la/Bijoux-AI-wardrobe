"""The wire shapes of the six `/trips` endpoints.

**One trip object, answered by all five endpoints that answer a trip**, with the
looks always a sibling key rather than a field inside it — `DECISIONS.md` 195,
which is 034's rule applied a fourth time. `TripResponse` is therefore the whole
of what `04-API-SPEC.md` prints under *The trip object*, and `TripPackResponse`
and `TripDetailResponse` differ only by `missing_pieces`, which describes a run
rather than a row and so is never stored.

**`days[]` is the join, and the route is what builds it.** Two of the trip's
columns are not on the wire: `trips.occasions` is the request as it arrived and
`trips.forecast` is the parsed provider answer, and a day merges one entry from
each with the `look_id` of the look built for it. That merge needs the looks, so
it lives in `routes/trips.py`; what lives here is the shape it has to produce.

**`TripPackRequest` and `services/packing.TripRequest` are two descriptions of
one body**, which `DECISIONS.md` 196 accepted in advance: the service holds a
frozen dataclass so it stays callable from a script with no request in flight,
and this is the Pydantic model the route maps into it. The mapping is one
function in the route and nothing compares the two shapes.
"""

import datetime
import uuid
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.enums import Condition, Occasion, Role, Slot
from app.schemas.look import LookResponse, MissingPieceResponse


class TripOccasion(BaseModel):
    """One occasion of one slot of one day, in `04-API-SPEC.md`'s shape.

    `day` is the trip's own 1-based ordinal, not a date component — day 1 is
    `start_date`. It is spelled out on the wire rather than left positional
    because `03-AI-CONTRACTS.md` numbers the days the same way, and a body whose
    meaning depends on array order is one a client can get wrong silently.

    **`slot` arrived at 4.15 and is required, with no default.** A default of
    `"day"` would have kept the pre-slot body valid and would have turned the one
    mistake a client can make here into a `502`: an evening entry that lost its
    slot parses as a second `day`, which the schema would accept and rule 10
    would refuse — after the model call, rather than before it. A value that is
    only ever right for one of two possibilities is not a default. What paid for
    the strictness is one line in `trips.page.ts`, which sends the literal until
    4.17 gives it a picker.
    """

    model_config = ConfigDict(extra="forbid")

    day: int
    slot: Slot
    occasion: Occasion


class TripPackRequest(BaseModel):
    """`POST /trips/pack`'s body, and three of the endpoint's four `422`s.

    `extra="forbid"` is `LookSuggestRequest`'s reasoning unchanged: a dropped
    key is an instruction the user gave and the plan did not obey, reported as
    a success.

    **`occasions` is required, one or two entries per day, days `1..n` in
    order.** `04-API-SPEC.md` asks for a `validation_error` on "an `occasions`
    list whose days are not `1..n`", and this reads that strictly: the entries
    must arrive *in* order, not merely be a permutation of the right set. A
    shuffled body would have to be sorted somewhere, and a sort the route can
    forget is worse than a refusal the schema cannot. 4.5's chip row is built in
    day order, so no correct client sends anything else.

    *That read "one entry per day" and gave `pack_trip` reading the tuple
    positionally as the reason, through 4.14. The service stopped reading it that
    way in the same commit that gave a day two slots; the refusal stands on its
    own footing, which is that a client cannot be trusted to have meant an order
    it did not send.*

    **The 14-day cap is deliberately not here.** It is `trip_too_long`, a `400`
    the route raises, and putting a `max_length` on `occasions` would answer a
    fifteen-day trip with `422 validation_error` instead — which is the wrong
    code for `STAGE-4`'s own acceptance criterion, *a 15-day trip is rejected at
    the API layer*.
    """

    model_config = ConfigDict(extra="forbid")

    # Stripped and non-empty, and **not** held to `/me/locations/search`'s
    # two-character minimum. That endpoint is a type-ahead, where refusing early
    # saves a provider request per keystroke; this is one destination sent once,
    # and a string too short to match anything is answered by the geocoder as
    # `destination_not_found` — a sentence about the place, where a `422` would
    # be a sentence about the form.
    destination: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    start_date: datetime.date
    end_date: datetime.date
    occasions: list[TripOccasion]
    # Stripped but not length-checked, exactly as `LookSuggestRequest.notes` is:
    # an empty note is falsy, so the prompt omits the line, and a blank one is
    # not worth a 422 to a user who tabbed through the field.
    notes: Annotated[str, StringConstraints(strip_whitespace=True)] | None = None

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @model_validator(mode="after")
    def _occasions_cover_the_range(self) -> Self:
        """`04-API-SPEC.md`'s two remaining `422`s, in the order they can be asked.

        The date check runs first because `days` is meaningless on an inverted
        range: a trip ending before it starts has a negative length, and the
        occasions message would then name a number no client could satisfy.

        **The invariant widened at 4.15 and is two checks now.** A day carries
        one entry or two, so the days cannot be compared against `1..n`
        directly; they are grouped first, and the grouping is of **consecutive**
        entries, which is the whole of what keeps *in order* enforced — a body
        that revisits day 1 after day 2 groups as `[1, 2, 1]` and fails the first
        check rather than quietly merging into one day.

        A lone `evening` is refused alongside `day` twice, and for the same
        reason: `uq_looks_trip_day_slot` would accept either happily, and neither
        is a day anybody asked for. `02-DATA-MODEL.md` and `DECISIONS.md` 225.
        """
        if self.end_date < self.start_date:
            raise ValueError("end_date: a trip cannot end before it starts")

        grouped: list[tuple[int, list[Slot]]] = []
        for entry in self.occasions:
            if grouped and grouped[-1][0] == entry.day:
                grouped[-1][1].append(entry.slot)
            else:
                grouped.append((entry.day, [entry.slot]))

        if [day for day, _ in grouped] != list(range(1, self.days + 1)):
            raise ValueError(
                f"occasions: one or two entries per day, days 1 to {self.days} in order"
            )

        for day, slots in grouped:
            if slots not in ([Slot.DAY], [Slot.DAY, Slot.EVENING]):
                raise ValueError(
                    f"occasions: day {day} must be one 'day' entry, or 'day' then 'evening'"
                )
        return self


class TripSwapRequest(BaseModel):
    """`POST /trips/{trip_id}/swap`'s body: one day, one garment, one role.

    **`replace_role` is required here where `LookSuggestRequest` makes it
    optional**, and that narrowing is the point rather than an oversight. That
    endpoint serves a plain suggestion as well as a swap, so the field is absent
    on most of its traffic and a validator has to refuse the one body that names
    a role without locks (`DECISIONS.md` 177). This endpoint does nothing else:
    the ↻ badge always sends a role, so requiring it deletes the invalid body
    instead of validating it.

    **The role is the client's and is never derived here.** `ROLE_BY_CATEGORY`
    lives in `frontend/src/app/shared/models/enums.ts` and has no counterpart in
    `app/enums.py` — this API validates the seven values and derives none — so a
    map added on this side to turn `item_id` into a role would be the second
    copy of a table deliberately kept in one place. `AUDITS.md` O-25.

    **`day` carries no `ge=1`**, and the bound is the route's for
    `trip_too_long`'s reason: the schema cannot know how many days this trip has,
    so a `ge` here would answer `0` and `99` with two different shapes of the
    same refusal. One check against the trip's own days, one message.

    **`slot` arrived at 4.16 and is required, with no default** — the same
    refusal `TripOccasion` takes one task back, with a quieter failure behind it.
    A defaulted slot on the pack request produces a `502`: two `day` entries for
    one date, refused by rule 10. A defaulted slot *here* produces a `200`, on
    the wrong look: the badge next to Monday's dinner would rebuild Monday's
    office outfit and answer as though it had done what was asked. **A slot the
    day has not got is `item_not_in_look`** — `_by_day` finds nothing for the
    pair, and `_replaceable` answers the `422` it already answers for a day with
    no look, before the model is called. The two facts share one code
    deliberately: with no look for that slot, no item is in it, and the badge
    only exists beside a look that does. `STAGE-4` 4.16.

    `exclude_item_ids` accumulates in the client across taps on one day, which is
    what stops a second swap of the same role handing back the garment the first
    one rejected. The server cannot derive it: the looks that carried those
    rejections were replaced by this endpoint and are gone.
    """

    model_config = ConfigDict(extra="forbid")

    day: int
    slot: Slot
    item_id: uuid.UUID
    replace_role: Role
    exclude_item_ids: list[uuid.UUID] = Field(default_factory=list)


class ReuseCount(BaseModel):
    """`packing_list.reuse_summary.most_reused`, which is an object or `null`.

    `null` when nothing is worn on more than one day, which is an ordinary
    outcome on a short trip rather than an error — `02-DATA-MODEL.md` says so
    and `packing.py` computes it that way.
    """

    item_id: uuid.UUID
    days: int


class ReuseSummary(BaseModel):
    # The numbers `05-FRONTEND-SPEC.md` §7 prints twice — the header's
    # "8 items · 4 looks" and the reuse line under the packing list — and not
    # the English sentence `02-DATA-MODEL.md` first sketched. A server that
    # answered "the jeans appear on 3 days" would put user-facing text where no
    # i18n key can reach it (`CONVENTIONS.md`).
    item_count: int
    look_count: int
    most_reused: ReuseCount | None


class PackingList(BaseModel):
    # Row UUIDs, never `short_id`s. The ids the model answered with are mapped
    # through the wardrobe by `pack_trip` before anything is stored, because a
    # UUID is the only id that leaves this API — `04-API-SPEC.md` keeps
    # `short_id` for the AI layer alone.
    item_ids: list[uuid.UUID]
    reuse_summary: ReuseSummary


class TripDaySlot(BaseModel):
    """One slot of one day: what it is for, and what was built for it.

    The half of a day that belongs to the **slot** rather than to the date. The
    four numbers, the condition and the rule are properties of the calendar day
    and stay on `TripDay`; the occasion and the look are properties of the slot
    and moved down here at 4.15. The alternative — one `days[]` row per
    `(day, slot)` with the forecast repeated in both — puts one measurement in
    two places with nothing keeping them equal, which is the failure
    `DECISIONS.md` 195 refused when it declined to pair days and looks
    positionally, and 225 refuses again.

    **`look_id` is nullable and that is not padding.** A repack detaches a look
    that was saved, rated or worn instead of deleting it (`AUDITS.md` O-32), and
    between that detach and the new looks landing a slot has none; a `null` here
    renders as a gap where a required field would make the whole trip
    unreadable. **The gap is per slot from 4.15**: a detached Monday evening
    leaves Monday's day look exactly where it was.
    """

    slot: Slot
    occasion: Occasion
    look_id: uuid.UUID | None


class TripDay(BaseModel):
    """One entry of the day strip: the forecast, and what is worn against it.

    Three sources in one object — `trips.forecast` for the numbers, the
    condition and the rule, `trips.occasions` for the occasions, and the trip's
    looks for each slot's `look_id`.

    **The occasion and the look moved into `slots[]` at 4.15**, leaving this
    object holding only what is a property of the date. A day carries one slot
    entry or two, `day` then `evening`.
    """

    day: int
    date: datetime.date
    temp_min_c: float
    temp_max_c: float
    precip_mm: float
    wind_kph: float
    condition: Condition
    # Exactly the sentence the model was given for this day, read back from the
    # column rather than recomputed. `WeatherResponse.rule` exposes the same
    # string for the same reason: it is what makes the weather behaviour
    # inspectable from outside the process.
    rule: str
    slots: list[TripDaySlot]


class TripResponse(BaseModel):
    """The trip object, whole. Every endpoint below answers exactly this.

    **`days` and `packing_list` are typed non-null over two nullable columns.**
    `trips.forecast` and `trips.packing_list` are nullable because migration
    `0005` was written before their shapes were settled (`DECISIONS.md` 189),
    not because a trip may lack them. This is `schemas/look.py`'s five-column
    reliance one table along, and it is named here for the same reason — the
    guarantee is about who writes the columns, so it is only worth as much as
    the census of writers below.

    **The census stopped being one writer at task 4.6a-1**, which is exactly the
    event this paragraph was written to be checked against. `POST /trips/pack`
    was the only writer through 4.4; `POST /trips/{id}/swap` is the second, and
    it writes `packing_list` alone — never `forecast`, which is the stored plan
    a swap obeys rather than re-derives (`DECISIONS.md` 199, 209). So `forecast`
    still has one writer and `packing_list` has two, and both of them fill the
    column on every path they can return `200` from. The typing holds; what
    changed is that it now rests on two functions agreeing rather than one
    existing. `DECISIONS.md` 203's trade-off is amended to match.

    **`dest_lat` and `dest_lon` are typed nullable**, unlike those two. Their
    column nullability has a reason of its own in `app/models/trip.py` — the
    destination is what the user typed and the coordinates are what the geocoder
    made of it — and that is a claim about the two fields rather than about when
    the migration was written.
    """

    id: uuid.UUID
    destination: str
    dest_lat: float | None
    dest_lon: float | None
    start_date: datetime.date
    end_date: datetime.date
    notes: str | None
    days: list[TripDay]
    packing_list: PackingList
    created_at: datetime.datetime


class TripPackResponse(BaseModel):
    """`POST /trips/pack` and `POST /trips/{id}/repack`.

    **No `message` key**, unlike `LookSuggestResponse`. `trips` has no column
    for one and `05-FRONTEND-SPEC.md` §7 has no line that renders it, so a
    sentence that survived only until the next page load would be a field lying
    about what the API stores. `missing_pieces` passes that test differently: it
    describes *this run*, and `POST /looks/suggest` already answers it
    unpersisted. `DECISIONS.md` 195.
    """

    trip: TripResponse
    looks: list[LookResponse]
    missing_pieces: list[MissingPieceResponse]


class TripDetailResponse(BaseModel):
    """`GET /trips/{id}` and `POST /trips/{trip_id}/swap`.

    `POST /trips/pack`'s response minus `missing_pieces`, which was never stored
    — so a reopened trip cannot carry it, and a swap has none to report: it asks
    the model for one day's look, and a gap in a wardrobe described against one
    day is not the trip's `missing_pieces`.

    **Two callers, one of which edits**, since task 4.6a-1. A `TripSwapResponse`
    holding the same two fields was refused on `DECISIONS.md` 182's rule — one
    row described twice, with nothing keeping the descriptions in step — and the
    accepted cost is a class called `…DetailResponse` answered by a `POST` that
    changes the trip. `DECISIONS.md` 209.
    """

    trip: TripResponse
    looks: list[LookResponse]


class TripListResponse(BaseModel):
    # Wrapped with a count, like every other list this API answers: a top-level
    # array has nowhere to grow a key and nowhere to put `total`.
    trips: list[TripResponse]
    total: int

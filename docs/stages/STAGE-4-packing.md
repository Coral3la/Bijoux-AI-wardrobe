# Stage 4 — Trip Packing

**Week 4 second half through week 5. Target: 5 days.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

Enter a destination and dates, get an outfit for every occasion of every day —
one, or two where the evening is different — built from the real wardrobe against
the real forecast, plus a minimal packing list that maximises item reuse.

*This read "one outfit per day" through 4.10. Tasks 4.11 to 4.18 widen a day to
one or two slots, `day` and `evening`, because a person wears one thing to the
office and changes for dinner; `DECISIONS.md` 225.*

**This is the signature feature.** It is the sentence that describes the project — *it packs your suitcase from your closet* — and it is the hardest thing here to fake without a working system underneath. Protect its schedule.

## Prerequisites

Stage 2 acceptance criteria pass. Stage 3 may be skipped entirely.

## Out of scope for this stage

No luggage-size optimisation, no laundry modelling, no per-day accessory swaps beyond what the model returns naturally. No collaborative or shared trips.

---

## Tasks, in order

### 4.1 Migration 0005
`trips` table plus `looks.trip_id`.

### 4.2 Multi-day forecast
Extend `services/weather.py` with `get_daily_forecast(lat, lon, start, end) -> list[DayForecast]`. Open-Meteo provides 16 days; cap requests at 14.

Return `400` with `code: "forecast_unavailable"` when dates fall outside the horizon. Say so plainly rather than guessing from seasonal averages.

### 4.3 Packing orchestration
`services/packing.py` → `pack_trip(user, wardrobe, request, preferences=None) -> PackingResult`:

**The signature is wider than the line above printed**, and it had to be: this
service holds no `Session`, so the wardrobe and the learned-preferences block —
both queries — arrive as arguments rather than being fetched. `TripRequest` is a
frozen dataclass in `packing.py` and not a Pydantic model, because
`schemas/trip.py` belongs to 4.4. `DECISIONS.md` 196.

1. Geocode the destination
2. Fetch the daily forecast for the range
3. Build one weather rule per day
4. Compute the reuse target: `min(days * 4, days + 8)`
5. Assemble the trip user message per `03-AI-CONTRACTS.md`
6. **One** stylist call for the whole trip
7. Validate, including `len(looks) == days`
8. Persist the trip and all looks with `trip_id` set

**Step 8 is not this task's.** `pack_trip` returns an unpersisted `Trip` and its
looks; `POST /trips/pack` writes them at 4.4, in one transaction it owns. That is
what keeps the reuse arithmetic testable with no database in reach.

**One call, not one per day.** Per-day calls cannot reuse items intelligently because each is blind to the others' choices, and reuse is the entire point of a packing list. If output quality suffers on long trips, chunk into blocks of 7 days and pass the first block's chosen items into the second block's prompt as already-packed — do not fall back to per-day calls.

### 4.4 Trip endpoints
`POST /trips/pack`, `GET /trips`, `GET /trips/{id}`, `DELETE /trips/{id}`, `POST /trips/{id}/repack`.

Constraints: maximum 14 days, at least 8 `ready` items, rate limit 10 packs per hour.

**The rate limit is not built here.** `04-API-SPEC.md` records that no task in
any stage file builds the counter its table needs, and asks that whoever writes
it add it to a stage file first — so it is added to `STAGE-5-qa-deploy.md` § 5.2,
beside the integration tests that have named rate limits since Stage 0, with all
three of the table's limits and a commit checkpoint of its own. This endpoint
ships unthrottled, which is an exposure with a date rather than an omission:
`POST /trips/pack` is the most expensive call in the project. Building it here
for one endpoint would leave the table reading as implemented while
`POST /items/upload` and `POST /looks/suggest` stayed exactly as open as they
have been since 0.7 and 2.7. `DECISIONS.md` 191.

**Built, and four things this line did not say.** `AUDITS.md` **O-32** was this
task's to settle and it is: `repack` **detaches** a look that was saved, rated or
worn and deletes the rest, `DELETE` cascades, and — the half none of the audit's
three options mentioned — **`pack_trip` runs first**, so a `502` from the stylist
cannot empty a trip. `trip_too_long` gained its producer here and turned out to
be **two** bounds rather than one: `end_date <= today + 14` stops bounding
anything once `start_date` is left free, so the trip's **length** is checked as
well, and that is the check "a 15-day trip is rejected at the API layer" actually
names. `DestinationNotFoundError` got its wire code — **`destination_not_found`,
`400`**, the nineteenth — which is a statement about the request rather than
about a provider, so it does not reuse `geocoding_unavailable`. And **repack
takes no body and re-geocodes**, which means a trip's coordinates can move
between two packs and a trip ages out of being repackable the day its `end_date`
leaves the horizon. `DECISIONS.md` 200–204.

**Dates are bounded on the last day, not the first.** `end_date <= today + 14`.
The line above and `04-API-SPEC.md`'s "`start_date` no more than 14 days ahead"
together admit a fourteen-day trip ending on day 27, which no forecast covers;
the bound has to bind the end or it does not bind the provider at all. Fourteen
rather than `weather.py`'s measured fifteen is one day of margin against a
horizon that moves daily. No seasonal-average fallback is built in this stage,
as a data source or as a message. `DECISIONS.md` 190.

### 4.5 Trip form
Destination with autocomplete via `/me/locations/search`. Date range picker. Once dates are chosen, render one occasion chip row per day, defaulting to `casual`. An optional notes field.

Keep this to a single screen. A multi-step wizard would add a day of work and no value.

### 4.6 Packing view
Header with destination, dates, item count and look count. A horizontal day strip showing temperature and a weather icon per day. Tapping a day swaps the look card below. The packing list is grouped by category with checkable rows, using local state only.

The reuse summary — *"8 items across 5 looks — the jeans appear on 3 days"* — goes somewhere prominent. It is the line that makes the feature land.

### 4.6a-1 The swap endpoint

`POST /trips/{trip_id}/swap`. **Added at 4.6a's orientation**, after reading the
handler that four previous sessions had assumed would serve this: `POST
/looks/suggest` forecasts the user's *home* coordinates, refuses an account with
none, persists a look with no `trip_id` and never touches `trips.packing_list`.
None of that is fixable by a field on the body, so the swap is a trip endpoint —
and 4.6a, which was framed as frontend, gets the backend it needs first rather
than inventing a contract it does not own.

It reads the day's stored forecast **including the rule sentence the model
obeyed**, so it calls no geocoder and no weather provider: one model call and
nothing else leaves the process. It runs the single-day rule order, detaches or
deletes the replaced look on `AUDITS.md` O-32's predicate, recomputes
`packing_list`, and does all of it downstream of the model answering.

**Acceptance criteria — 4.6a-1's own:**

- [x] A swap changes the named day and no other, and survives a reload
- [x] The stored rule is what reaches the model, and `build_rule` is not called
- [x] No geocoder and no forecast request is made
- [x] A saved, rated or worn look is detached with its three columns untouched
- [x] A stylist failure leaves the day's look and the packing list exactly as they were
- [x] The packing list keeps its survivors' order and appends what is new
- [x] A stale badge answers `item_not_in_look` before the model is called

`DECISIONS.md` 209.

### 4.6a Swap one item on a trip look

The ↻ badge from the look card, on the trip look. Reuses Stage 2's plumbing
unchanged — `locked_item_ids`, `replace_role`, `exclude_item_ids`, and
validation rules 7 and 8 — rather than building a second swap.

Three properties are what make it a task rather than a wiring job:

1. The replacement is **local to that day**. A trip's looks each obey their own
   weather rule, so propagating one day's substitution applies a judgement made
   at 12°C and rain to a day dressed at 19°C and dry.
2. The **packing list is recomputed**: the new item enters it, and the old one
   leaves only if no remaining day still wears it.
3. Where the old item *is* still worn on other days, the UI **names them**.
   Reuse is the whole point of the feature, so removing the jeans from Tuesday
   does not take them out of the suitcase while Thursday still wears them — and
   without that line the user swaps expecting to pack less and packs the same.

Whether the recomputation happens on the server or in the client is this task's
open question. `trips.packing_list` is a stored `JSONB` column either way.
*Answered at 4.6a-1: the server recomputes it, in the transaction that writes the
new look — the tie-break `reuse_summary` documents cannot survive a second
implementation, and a client-side recompute leaves the stored column wrong until
the next repack. `DECISIONS.md` 209.*

**This task is now the frontend half only**, and the wire it calls is 4.6a-1's:
`POST /trips/{trip_id}/swap`, taking `day`, `item_id`, `replace_role` and the
accumulated `exclude_item_ids`, and answering the whole trip. *This section said
the swap "reuses Stage 2's plumbing unchanged"; that is true of the rules, the
context and the retry loop, and it was never true of the endpoint.*

**Acceptance criteria — 4.6a's own**, because this task was inserted after the
list at the foot of this file was written:

- [x] Swapping an item on day 3 changes day 3 and no other day
- [x] After a swap the packing list contains the new item, and every look item
      is still in the packing list
- [x] An item swapped out of one day but still worn on another stays in the
      packing list, and the UI says which days still wear it
- [x] The rejected item is not returned by the swap that rejected it

*The last two are met across the split: the frontend renders the still-worn line
and accumulates `exclude_item_ids` per day, and 4.6a-1's server appends the
replaced garment to that list and enforces it through rule 8 — so the rejection
is a rule rather than a hope even if a client forgets to send it.*

`DECISIONS.md` 192, 209, 210.

### 4.6b Repack and delete a trip

The two controls `/trips/:id` shipped without. `POST /trips/{id}/repack` and
`DELETE /trips/{id}` were built, tested and documented at 4.4 and reachable by
nobody; **this task is the one `AUDITS.md` O-33 asked for**, added after the
list at the foot of this file was written and after 4.6 declined to build them
out of turn.

The repack inherits the whole of `POST /trips/pack`'s surface — the
twenty-second wait, the four status lines and all seven failure codes — on a
screen that has content to lose, which is what makes it a task rather than a
button. The delete has one real question, which is where it navigates: there is
no trips list and `/trips` is the form.

**Acceptance criteria — 4.6b's own**, for the same reason 4.6a has its own:

- [ ] Repacking a trip re-renders it from the response, keeping the selected day
- [ ] A repack that fails leaves the trip on screen with its message above it
- [ ] The delete needs two presses and disarms on blur and on a repack
- [ ] Deleting a trip navigates to `/wardrobe`
- [ ] The pack and the repack share one status cycle and one error table

`DECISIONS.md` 207, `AUDITS.md` O-33.

### 4.7 Export
A share or copy button producing the packing list as plain text. Trivial to build, and it is the thing a user would actually use on the morning of a trip.

### 4.9 Global navigation

The bar every screen in this project has done without. **This task is the one
`AUDITS.md` O-29 asked for**, added after the list at the foot of this file was
written and after five separate tasks each shipped the bespoke link that item
told them not to — the same shape as 4.6b, one item further down the file.

The immediate need is that `/trips` is reachable only by typing the URL, which
makes the signature feature of this project invisible. The real work is larger:
one navigation surface serving every top-level screen, replacing the controls
that stood in for it. **Numbered 4.9 rather than 4.8**, which is left unused,
and placed after 4.7 in the file although 4.7 is not built — this is chrome
rather than a step in the packing feature, and nothing in it blocks the export.

**Delete what it replaces.** The point of the task is the count coming down, so
the back links and account-row anchors go in the same commit as the bar. A
contextual action that happens to navigate is not navigation and stays where it
is; the line between the two has to be drawn explicitly and defended in a spec.

**Read O-29's history before writing anything.** That item kept its count in
prose across eleven weeks and five instances, and the number is wrong.

**Acceptance criteria — 4.9's own**, for the same reason 4.6a and 4.6b have theirs:

- [x] Every top-level screen is reachable from every other one, with no address bar
- [x] The bar renders for a signed-in user and never on `/login` or `/register`
- [x] The active item survives a query-parameter change and a child route
- [x] Every back link and account-row anchor the bar replaces is deleted, with its keys
- [x] `AUDITS.md` O-29 is closed on a count taken from the tree rather than from its own prose

`DECISIONS.md` 208, `AUDITS.md` O-29.

### 4.10 The trips list

Every trip on the account, newest first, each row opening the trip and carrying
a delete. **Added after the list at the foot of this file was written**, which
is 4.6b's shape and 4.9's — the third task in this stage numbered by the session
that found the gap rather than by the plan.

It answers two things at once: an old trip can be thrown away, and a trip whose
URL was lost can be found again. `GET /trips` gets its first caller, which four
documents had recorded it would never have.

**`/trips` becomes the list and the form moves to `/trips/new`.** The
alternative — a new path under `/trips` with a sixth navigation item — does not
survive contact with `routerLinkActive`: a link to `/trips` is a prefix of every
trip URL, so a sixth item would light *beside* the Trips item on the screen it
points at, and re-pointing the Trips item at a child path would put it out on
the form and on the Itinerary instead. Moving the form is one route line and
leaves `nav-bar.ts` untouched. `DECISIONS.md` 224.

Out of scope, each named because a reader will look for it: no filter, sort or
search; no forecast preview and no photograph on a row; no pagination, though
the endpoint offers `limit` and `offset`; and no change to `/trips/:id`, whose
delete still returns to `/wardrobe` — `AUDITS.md` **O-34** is that follow-up.

**Acceptance criteria — 4.10's own**, for the reason 4.6a, 4.6b and 4.9 have theirs:

- [x] The route is reachable from the global navigation, with no address bar
- [x] An account with no trips gets the empty state and a way to the form
- [x] A row carries the destination, the dates and the day count, and opens the trip
- [x] A delete takes two presses and removes the row
- [ ] The deletion survives a reload *(a browser check against a live API; the
      suite proves the request, not the persistence)*
- [x] A refused delete puts the row back where it was, not at the top
- [x] `trips.page.spec.ts` and `trip-detail.page.spec.ts` still pass

`DECISIONS.md` 224, `AUDITS.md` O-34.

### 4.11 The slot in the documents

`02`, `03`, `04`, `05`, this file and `PROGRESS.md`, with `DECISIONS.md` 225. No
code, no migration, no test — **4.3's shape**, which landed its contract in a
commit of its own before `pack_trip` existed, and the reason is the same: the
seven tasks below are a schema change, a model contract, an arithmetic change,
three route changes and two screens, and the cost of finding out at 4.15 that
`days[].slots` should have been something else is six files rather than one
paragraph.

**Acceptance criteria — 4.11's own:**

- [x] Every document that describes a day's occasion describes a slot
- [x] No code, no migration and no test changes in the commit

### 4.12 Migration 0006 and the `Slot` vocabulary

`looks.slot`, `CHECK ((trip_id IS NULL) = (slot IS NULL))` as raw DDL, and the
partial `uq_looks_trip_day_slot`. Two backfills: every look with a `trip_id`
becomes a `day` look, and every entry in every `trips.occasions` gains
`"slot": "day"`. `Slot` joins `app/enums.py` beside `Occasion` and is mirrored in
`enums.ts`.

**The `CHECK` is false for every existing trip look until the first backfill has
run**, so the order inside `upgrade()` is column, data, then constraints — which
is the one thing in this migration that cannot be reordered.

**It touches `routes/trips.py`, which this line did not anticipate.** The CHECK
binds four statements the moment it lands: `_write` and `_replace_look` insert
trip looks and now write `slot="day"` — a literal that is true until 4.15,
because no request can name a slot before then — and both detach statements now
clear `slot` alongside `trip_id`, or the constraint refuses the row on the way
out of the trip. Two integration fixtures that plant a trip look directly carry
the same literal. That is the migration's own blast radius rather than scope
taken from a later task, and the sentence it makes false —
`04-API-SPEC.md`'s *"`trip_id = NULL`, and no other column touched"* — is
amended here rather than deferred.

**The downgrade refuses rather than flattening an evening**, which was measured
at 4.12 and is the one decision here `DECISIONS.md` 225 does not carry. Drop the
column with a two-slot day in the database and its two looks become
indistinguishable rows; the next upgrade gives both `day` and
`uq_looks_trip_day_slot` cannot build, leaving the database stuck at `0005`. So
`downgrade()` counts the surviving evenings first and raises with the two
statements that clear them. It bites from 4.15 and not before, because nothing
can write an evening yet.

**Acceptance criteria — 4.12's own:**

- [x] `alembic upgrade head` then `downgrade` then `upgrade` is clean on a
      database holding a packed trip — run against `TEST_DATABASE_URL` over a
      trip planted at `0005`, and again over the empty schema
- [x] A second `day` look for one date is refused by the database, not by Python
- [x] A look with a `trip_id` and no slot is refused, and so is a slot with no trip
- [x] Every look and every `occasions` entry written before `0006` reads as `day`
- [x] A downgrade refuses while an evening survives, and leaves the revision where
      it was

### 4.13 The stylist half

`trip_packing_plan` gains `slot`; the trip user message becomes one line per
`(day, slot)` with the widened packing constraint; rules 4, 6 and 10 read the
requested pairs; the trip path's violation prefix splits into `look N:` before
rule 10 and `day N slot:` after it.

Pure, unit-tested, no database and no route. **The prefix split moves pinned
strings** — the trip-path assertions in `tests/unit/test_look_validation.py` —
and that is the visible half of this task.

**Acceptance criteria — 4.13's own:**

- [x] Two looks answered for one `(day, slot)` fail rule 10, with the pair named
- [x] A look for a slot that was never requested fails rule 10 — pinned against
      the rule, because rule 4 makes it unreachable through the validator
- [x] Each look is judged against its own day's rule, and both slots of a date
      against the same one
- [x] The single-day path's rules, order and violation strings are untouched

### 4.14 `pack_trip` and the reuse arithmetic

`TripRequest.occasions` becomes the `(day, slot, occasion)` triples;
`PackedLook` carries its slot; `reuse_summary`'s `look_count` counts looks and
`most_reused.days` counts **distinct days**.

**The two numbers stop being the same number here**, which is why this is not
4.13's commit: a contract that is wrong fails loudly on the next model call, and
arithmetic that is wrong prints a plausible sentence under a packed trip.

**The triples are a `TripSlot`, and the count stopped being the check.**
`pack_trip` refused `len(occasions) != days`; it now refuses a day of the range
nobody dressed, and a `(day, slot)` asked for twice. The second is what
`uq_looks_trip_day_slot` would otherwise refuse four layers down, as a `500` with
no code on it, after a model call has already been spent.

**`_forecast_column` is the line this task did not name.** `days` holds one entry
per requested slot from here and that column holds one row per calendar day, so
the `zip(days, forecasts, strict=True)` that paired them would have raised on the
first evening — and loosened, would have written day 2 twice and given the trip a
day it has not got. It reads a `{ordinal: rule}` map instead, which loses nothing
because both slots of a date are built from the one forecast row.

**It touches `routes/trips.py` at three call sites**, on 4.12's precedent rather
than as scope taken from 4.15: pack maps the wire's `{day, occasion}` into
`TripSlot`s with a `slot="day"` literal, repack reads the slot back out of
`trips.occasions`, and the swap hands `reuse_summary` the dates its looks are
worn on — `LookResponse` carries none, so the rows it was hydrated from travel
beside it.

**`trips.occasions` had been writing a shape its own migration had abolished.**
`0006` backfilled `"slot": "day"` into every existing entry at 4.12, and
`pack_trip` — the column's only writer — went on writing `{day, occasion}`, so
for two commits a trip packed *after* the migration held entries older than it.
Nothing read the key, so nothing failed. The writer is this task's; the key is
written down rather than defaulted on read, for the reason `02-DATA-MODEL.md`
gives — a reader that filled it in would be the one place left in the project
that knows the pre-slot shape.

**Acceptance criteria — 4.14's own:**

- [x] A garment worn in both slots of one day and nowhere else reports one day
      and leaves `most_reused` null — `most_reused` is null and `look_count` is 2
- [x] `look_count` exceeds the day count exactly when a day has two slots — three
      looks over two days, against the two-day two-look case that was already
      pinned
- [x] The reuse target is still computed from days — a two-day trip with an
      evening asks for three looks against day 2's ceiling of eight items

### 4.15 The trip routes

`TripPackRequest`'s validator takes the new invariant; `TripDay` grows
`slots[]` and loses `occasion` and `look_id`; `_by_day` is keyed by `(day, slot)`;
`_write` writes `looks.slot`; `_looks` orders by `for_date` then slot. Pack,
repack, list and read.

**`_by_day` returns `dict[int, uuid.UUID]` today and silently keeps one of two
colliding looks**, which is the concrete failure this task exists to prevent.

**`_write`'s `look_ids` is the same key and this line did not name it.** It is
`_by_day`'s answer built from what was just inserted rather than read back, so
pack and repack would have collided where the three read paths did.
`list_trips`'s own `SELECT` gains `Look.slot` for the same reason.

**The slot is required on the wire and takes no default**, which is a strictness
one line in `trips.page.ts` pays for: the form sends `slot: 'day'` as a literal
until 4.17 gives it a picker. A default of `"day"` would have kept the pre-slot
body valid and turned the one mistake a client can make into a `502` — an evening
entry that lost its slot parses as a second `day`, and rule 10 refuses the pair
after the model call rather than the schema refusing it before. Same blast-radius
shape as 4.12 reaching into `routes/trips.py`.

**`_looks` sorts by the vocabulary's rank and not the collation's.** `day` sorts
before `evening` alphabetically by luck, and a third slot would not; the rank is
built from `Slot.values()`, as `stylist.py`'s `_SLOT_ORDER` is. `Look.id` is
dropped as the third sort term in the same edit — `uq_looks_trip_day_slot` makes
`(for_date, slot)` unique within a trip, so a tiebreaker after it is unreachable.

**This task opens the hole 4.16 closes.** A trip with an evening becomes packable
here, and `swap_item` looks up `(day, "day")` — a literal, like 4.12's and
4.14's — so a swap on a two-slot day edits the day look whatever the caller
meant. Nothing in the product can send that request yet: the ↻ badge names no
slot until 4.18.

**Acceptance criteria — 4.15's own:**

- [x] A two-slot day answers two `slots[]` entries with two different `look_id`s —
      and `_by_day` keyed by the ordinal alone fails it, measured
- [x] The looks of one day come back in `day` then `evening` order — asserted as
      two independently produced orderings being equal, `days[].slots[]` against
      `looks`; a reversed slot rank fails it
- [x] A repack rebuilds the same slots from the stored column — it takes no body,
      so `trips.occasions` is the only record of the evening
- [x] `occasions` that are not one or two per day in order are a `422` — four new
      shapes: a lone evening, an evening before its day, a day revisited after
      the next, and an entry with no slot

### 4.16 The swap, per slot

`TripSwapRequest.slot`; `_day`, `_replaceable` and `_replace_look` take the slot;
a slot the day has not got falls to `item_not_in_look`.

**Two of the three functions this line names needed nothing, and one it does not
name needed everything.** `_day` reads `trips.forecast`, which is one row per
*date* — the slot narrows no lookup there, and both slots of a date are judged
against the one rule by contract (`DECISIONS.md` 225). `_replaceable` already
answers `item_not_in_look` for a look that is not there, so once `swap_item`
looks up `(day, request.slot)` the last criterion holds with no new code. What
did need the slot is **`_swap_context`**, which held the last of the two dict
comprehensions `0006` made lossy — `{entry["day"]: entry["occasion"]}`, keeping
whichever entry came last, so a swap on Monday's day look would have rebuilt it
for dinner with nothing on the wire to say so. `_trip`'s copy died at 4.15; this
one dies here.

**A slot the day has not got and a garment that is not in the look share one
code deliberately.** With no look for that slot, no item is in it; the badge is
drawn only beside a look that exists, so the case reaches the server from a
hand-built request or a broken client, and the `4xx` text is not what either
reads. Three lines — a lookup and a raise — would separate them, and a future
reader who wants that can add them then. What the test pins is the half that
matters: the refusal lands **before** the model is called.

**`slot` is required with no default, and the failure behind that is quieter than
4.15's.** A pack request missing its slot produces two `day` entries for one date
and a `502` from rule 10. A swap request missing its slot would answer **`200`**,
having rebuilt the wrong look of a two-slot day. One literal in
`trip-detail.page.ts` sends `'day'` until 4.18 gives the badge a slot to name —
4.12, 4.14 and 4.15's pattern, a fourth time.

**The swap suite needed a two-slot trip before it could measure one.** Its fakes
are copies rather than imports (twenty test modules, zero cross-imports), so
`pairs`, `evenings` and an `EVENING_OUTFITS` entry land here as they landed in
`test_trips_pack.py` at 4.15. A day slot keeps `OUTFITS[day - 1]` whatever else
is asked for, because every reuse assertion in that file is written against who
wears what.

**Acceptance criteria — 4.16's own:**

- [x] A swap on day 2 evening changes that look and not day 2's day look — and
      the lookup reverted to the `day` slot fails it, measured
- [x] A swap naming a slot the day has not got is `item_not_in_look`, before the
      model is called — asserted on the code *and* on the fake's call count
- [x] The replaced look is detached or deleted with its slot's row and no other —
      a saved evening leaves with `trip_id` and `slot` cleared together, and the
      day look keeps both
- [x] The packing list keeps the garment when the day's other slot still wears it
      — `top_b` is worn by day 2's two slots and by no other date, which is the
      one shape a single-slot trip cannot produce

### 4.17 The trip form

One or two occasion rows per day: a control that adds the evening and removes it,
and a resize that keeps evenings with their days.

**Two controls rather than one, and the line above says "a control".** *Add an
evening* sits on the day's fieldset; the `×` that takes it away sits on the
evening row beside its own label. The destination chip one section up already
removes itself that way, and separating the two means the button that destroys is
never the button that adds. The cost is a mis-tap on `×` losing a chosen
occasion, taken deliberately — the occasion goes with the slot rather than being
held for a re-add, because an evening that is not on the trip has nothing to be
for. `05-FRONTEND-SPEC.md`'s bullet is amended to match rather than the code
bent to it.

**The resize criterion cost nothing, and that is what chose the draft's shape.**
`TripDraft.occasions` is one `TripDayDraft` per **day** — `{ day, evening }`,
with the field names taken from the slot vocabulary — rather than the wire's flat
list of slots. An entry carries its own evening, so padding the tail and
truncating from the end cannot separate the two; a flat list would have had to
count slots to find a day's boundary. It also makes `evening: null` the only way
to say *no second slot*, so **a lone evening is structurally unbuildable** rather
than merely unsent — the form cannot express the body `TripPackRequest` refuses.
The flattening happens once, in `trips.page.ts`, which is where the day numbering
already was.

**A new evening opens on occasion `evening`**, not on `casual`. Pressing *Add an
evening* has already said what the slot is for. It renders as `EVENING · EVENING`
on the trip page, which is the vocabulary collision `AUDITS.md` **O-35** already
owns and 4.18's dedupe rule already plans to collapse — this walks into an owned
problem rather than making a new one.

**`MAX_TRIP_DAYS` bounds days, and evenings are not days.** A fourteen-day trip
with fourteen evenings is twenty-eight looks in one model call against a
twenty-two item ceiling, because `reuse_target` is a function of days by 4.14's
own criterion. Nothing refuses it and nothing here adds a bound the API does not
have. It is 225's pressure-toward-reuse taken to its limit, and whether a plan
that size is still sensible is for the prompt-tuning note below to measure; if it
is not, that is its own task rather than a patch inside this one.

**Acceptance criteria — 4.17's own:**

- [x] A day can be given an evening and have it taken away again — and a
      `removeEvening` that does nothing fails it, measured
- [x] Extending the trip keeps an evening already set on an earlier day — a
      `resize` that rebuilds the day without its evening fails it
- [x] The request carries the entries in day order, `day` before `evening` —
      asserted on the request body, and the flattening reversed fails it

### 4.18 The trip page

Day / Evening cards stacked under one day head, the occasion moved into the slot
head, the still-worn line naming slots, and the swap scoped by `(day, slot)`.

**`shared/models/trip.model.ts` moves too, and this line did not name it.**
`TripDay` carried `occasion` and `look_id` at the day level — the shape the
server stopped sending at **4.15** — so the model, `trip-detail.page.spec.ts`,
`trip-list.page.spec.ts` and every fixture in them had been describing a payload
that no longer existed for three tasks. Nothing failed and nothing could have:
the specs mock their own responses. That is the window `PROGRESS.md` records as
invisible to tests, and this is the commit that closes it.

**The still-worn line names the evening and not the day.** `day` is the slot
every date has and `evening` is the marked one, so *Day 2, Day 4 evening* reads
as a person would say it where *Day 2 day* is a stutter — the same judgement the
slot head's own dedupe makes about `EVENING · EVENING`. Two whole keys carry it
rather than one with a slot word appended, because word order is a translator's.
`05-FRONTEND-SPEC.md` said *"each with its slot"* and is amended, on 4.17's
precedent: the document describes what shipped.

**The exclusions test had to press two different garments to mean anything.**
Rejecting the shirt on the day slot and then the shirt again on the evening sends
the same single id whether the list is keyed by day or by pair — the first
version of that test passed against a deliberately day-keyed map. It presses the
shirt and then the **heels**, which is the only shape that can tell the two
apart. Measured, not assumed.

**Acceptance criteria — 4.18's own:**

- [x] A two-slot day draws two cards under one forecast — and the forecast is
      asserted absent from both slot heads, so the head cannot have been drawn
      twice
- [x] A swap spins one tile, on the slot it was asked for — the shirt is worn in
      both halves of one date, and matching the signals by day alone fails it
- [x] A garment removed from a day look and still worn that evening says so,
      naming the evening — *"You'll still wear the white shirt on Day 1
      evening."*, which naming only the day would render as the date the reader
      is looking at
- [x] Exclusions accumulated on one slot do not narrow the other — two presses on
      two garments, and a day-keyed map fails it

---

## Acceptance criteria

- [ ] A 4-day Berlin trip returns exactly 4 looks, one per day *(a trip whose
      days each carry one occasion; from 4.11 the count is one per requested
      `(day, slot)` pair, and a 4-day trip with two evenings out returns 6)*
- [ ] A day given two occasions returns two looks for that date, and they are not
      the same outfit
- [ ] Where the weather rule and the two occasions allow it, a day's two looks
      share at least one garment — measured against the demo wardrobe and
      recorded, not enforced
- [ ] Each look obeys that specific day's weather rule — the rainy day gets water-resistant outerwear where the wardrobe allows
- [ ] The packing list contains strictly fewer items than `days × 4`
- [ ] Every packed item appears in at least one look, and every look item appears in the packing list
- [ ] No two days produce an identical full look
- [ ] Dates beyond the forecast horizon return `400 forecast_unavailable` with a clear message
- [x] A 15-day trip is rejected at the API layer — `test_a_fifteen_day_trip_is_trip_too_long`, and the length half of the bound it measures is `DECISIONS.md` 201's
- [x] `repack` refreshes the forecast and replaces the looks — `test_repack_refreshes_the_forecast` and `test_repack_replaces_the_looks_and_keeps_the_trip`. **What it replaces is O-32's answer rather than this line's**: a saved, rated or worn look is detached, not deleted

## Commit checkpoints

`feat(db): trips schema` · `feat(weather): multi-day forecast` · `feat(ai): trip packing orchestration` · `feat(api): trip endpoints` · `feat(web): trip form` · `feat(web): packing view` · `feat(api): swap an item on a trip look` · `feat(web): swap an item on a trip look` · `feat(web): packing list export` · `feat(web): global navigation` · `feat(web): trips list` · `docs: two occasions a day` · `feat(db): the look slot` · `feat(ai): the slot in the stylist contract` · `feat(ai): pack two looks a day` · `feat(api): trip slots` · `feat(api): swap within a slot` · `feat(web): two occasions on the trip form` · `feat(web): day and evening on the trip page`

## Prompt tuning note

Reuse is the part that needs iteration. Without an explicit numeric target the model reuses almost nothing. Start with `min(days * 4, days + 8)`, run it against the demo wardrobe for 3, 5 and 7 days, and record the actual item counts in `docs/eval-results.md`. Tighten the target until reuse is visible without the looks becoming repetitive.

**Cross-slot reuse is measured here too and is enforced nowhere**, which is the
same trade the target itself takes: *the two looks on a day share at least one
item* would `502` on a hiking day followed by a formal dinner, where no honest
garment is shared. Run the same three lengths with evenings on half the days and
record how often the two looks of a day share a bottom or an outerwear piece.
`03-AI-CONTRACTS.md` carries the argument; rule 11 is the only part of it that is
a refusal.

# Stage 4 — Trip Packing

**Week 4 second half through week 5. Target: 5 days.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

Enter a destination and dates, get one outfit per day built from the real wardrobe against the real forecast, plus a minimal packing list that maximises item reuse.

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

- [ ] Swapping an item on day 3 changes day 3 and no other day
- [ ] After a swap the packing list contains the new item, and every look item
      is still in the packing list
- [ ] An item swapped out of one day but still worn on another stays in the
      packing list, and the UI says which days still wear it
- [ ] The rejected item is not returned by the swap that rejected it

`DECISIONS.md` 192.

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

---

## Acceptance criteria

- [ ] A 4-day Berlin trip returns exactly 4 looks, one per day
- [ ] Each look obeys that specific day's weather rule — the rainy day gets water-resistant outerwear where the wardrobe allows
- [ ] The packing list contains strictly fewer items than `days × 4`
- [ ] Every packed item appears in at least one look, and every look item appears in the packing list
- [ ] No two days produce an identical full look
- [ ] Dates beyond the forecast horizon return `400 forecast_unavailable` with a clear message
- [x] A 15-day trip is rejected at the API layer — `test_a_fifteen_day_trip_is_trip_too_long`, and the length half of the bound it measures is `DECISIONS.md` 201's
- [x] `repack` refreshes the forecast and replaces the looks — `test_repack_refreshes_the_forecast` and `test_repack_replaces_the_looks_and_keeps_the_trip`. **What it replaces is O-32's answer rather than this line's**: a saved, rated or worn look is detached, not deleted

## Commit checkpoints

`feat(db): trips schema` · `feat(weather): multi-day forecast` · `feat(ai): trip packing orchestration` · `feat(api): trip endpoints` · `feat(web): trip form` · `feat(web): packing view` · `feat(api): swap an item on a trip look` · `feat(web): swap an item on a trip look` · `feat(web): packing list export` · `feat(web): global navigation`

## Prompt tuning note

Reuse is the part that needs iteration. Without an explicit numeric target the model reuses almost nothing. Start with `min(days * 4, days + 8)`, run it against the demo wardrobe for 3, 5 and 7 days, and record the actual item counts in `docs/eval-results.md`. Tighten the target until reuse is visible without the looks becoming repetitive.

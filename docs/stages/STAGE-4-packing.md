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
`services/packing.py` → `pack_trip(user, trip_request) -> PackingResult`:

1. Geocode the destination
2. Fetch the daily forecast for the range
3. Build one weather rule per day
4. Compute the reuse target: `min(days * 4, days + 8)`
5. Assemble the trip user message per `03-AI-CONTRACTS.md`
6. **One** stylist call for the whole trip
7. Validate, including `len(looks) == days`
8. Persist the trip and all looks with `trip_id` set

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

**Acceptance criteria — 4.6a's own**, because this task was inserted after the
list at the foot of this file was written:

- [ ] Swapping an item on day 3 changes day 3 and no other day
- [ ] After a swap the packing list contains the new item, and every look item
      is still in the packing list
- [ ] An item swapped out of one day but still worn on another stays in the
      packing list, and the UI says which days still wear it
- [ ] The rejected item is not returned by the swap that rejected it

`DECISIONS.md` 192.

### 4.7 Export
A share or copy button producing the packing list as plain text. Trivial to build, and it is the thing a user would actually use on the morning of a trip.

---

## Acceptance criteria

- [ ] A 4-day Berlin trip returns exactly 4 looks, one per day
- [ ] Each look obeys that specific day's weather rule — the rainy day gets water-resistant outerwear where the wardrobe allows
- [ ] The packing list contains strictly fewer items than `days × 4`
- [ ] Every packed item appears in at least one look, and every look item appears in the packing list
- [ ] No two days produce an identical full look
- [ ] Dates beyond the forecast horizon return `400 forecast_unavailable` with a clear message
- [ ] A 15-day trip is rejected at the API layer
- [ ] `repack` refreshes the forecast and replaces the looks

## Commit checkpoints

`feat(db): trips schema` · `feat(weather): multi-day forecast` · `feat(ai): trip packing orchestration` · `feat(api): trip endpoints` · `feat(web): trip form` · `feat(web): packing view` · `feat(web): swap an item on a trip look` · `feat(web): packing list export`

## Prompt tuning note

Reuse is the part that needs iteration. Without an explicit numeric target the model reuses almost nothing. Start with `min(days * 4, days + 8)`, run it against the demo wardrobe for 3, 5 and 7 days, and record the actual item counts in `docs/eval-results.md`. Tighten the target until reuse is visible without the looks becoming repetitive.

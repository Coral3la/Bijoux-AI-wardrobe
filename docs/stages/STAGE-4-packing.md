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

### 4.1 Migration 0004
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

### 4.5 Trip form
Destination with autocomplete via `/me/locations/search`. Date range picker. Once dates are chosen, render one occasion chip row per day, defaulting to `casual`. An optional notes field.

Keep this to a single screen. A multi-step wizard would add a day of work and no value.

### 4.6 Packing view
Header with destination, dates, item count and look count. A horizontal day strip showing temperature and a weather icon per day. Tapping a day swaps the look card below. The packing list is grouped by category with checkable rows, using local state only.

The reuse summary — *"8 items across 5 looks — the jeans appear on 3 days"* — goes somewhere prominent. It is the line that makes the feature land.

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

`feat(db): trips schema` · `feat(weather): multi-day forecast` · `feat(ai): trip packing orchestration` · `feat(api): trip endpoints` · `feat(web): trip form` · `feat(web): packing view` · `feat(web): packing list export`

## Prompt tuning note

Reuse is the part that needs iteration. Without an explicit numeric target the model reuses almost nothing. Start with `min(days * 4, days + 8)`, run it against the demo wardrobe for 3, 5 and 7 days, and record the actual item counts in `docs/eval-results.md`. Tighten the target until reuse is visible without the looks becoming repetitive.

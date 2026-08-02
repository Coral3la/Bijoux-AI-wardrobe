# Stage 2 — The Stylist

**Week 3. Target: 5–6 days.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

Ask for an outfit, get one back that is built from real items in the wardrobe and is correct for the actual weather outside.

This is the stage where the project stops being a catalogue and becomes a product.

## Prerequisites

Stage 1 acceptance criteria pass. The demo wardrobe exists and is browsable.

## Out of scope for this stage

No saving, no thumbs up/down, no wear tracking — that is Stage 3. No trips. The look card renders and can be regenerated; it is not yet persisted as a user-facing collection.

---

## Tasks, in order

### 2.1 Weather service
`services/weather.py`:
- `get_forecast(lat, lon, date) -> Forecast` via Open-Meteo, no API key
- `build_rule(temp_c, precip_mm, wind_kph) -> str` — the mapping table from `03-AI-CONTRACTS.md`
- 30-minute in-memory cache keyed by `(lat, lon, date)`

**Write the unit tests for `build_rule` before the rest of this stage.** It is a pure function, every boundary is testable, and it is the mechanism that makes weather behaviour reliable. Twelve assertions, no AI.

`GET /weather` exposes both the forecast and the rule string.

### 2.2 Location search
`GET /me/locations/search?q=` proxying Open-Meteo geocoding. `PATCH /me` accepting `home_city`, `home_lat`, `home_lon`.

### 2.3 Wardrobe serialiser
`services/serializer.py` → `serialize_wardrobe(items) -> str` producing the compact one-line-per-item format. Omit nulls. Uppercase `short_id` at the start of each line.

Unit test the token budget: 150 items must serialise to under 6,000 tokens. Use `tiktoken` to assert it.

### 2.4 Stylist service
`services/stylist.py` → `suggest_looks(wardrobe, context) -> StylistResponse`.

Prompt in `app/prompts/stylist_system.md`. User message assembled per `03-AI-CONTRACTS.md`. Structured Outputs with the response schema. `USE_FAKE_AI` branch returning a recorded fixture.

Send the **whole wardrobe**. The only server-side exclusion is swimwear and sleepwear, and it is a configurable list.

### 2.5 Response validation
`validate_look_response()` implementing all six rules in order. The first rule — every returned ID exists in **this user's** wardrobe — is the hallucination guard and must never be relaxed.

One retry naming the violation, then `502` with `code: "stylist_failed"`.

Unit tests: each of the six rules failing independently, against hand-built response objects.

### 2.6 Look persistence
Migration `0002_looks` creating `looks` and `look_items`. Every suggestion is persisted with `is_saved=false` before the response returns — this costs nothing and is what makes the evaluation story possible later.

### 2.7 Suggest endpoint
`POST /looks/suggest` orchestrating: fetch wardrobe → fetch forecast → build rule → serialise → call stylist → validate → persist → hydrate IDs into full item objects → return.

Guard: fewer than 6 `ready` items returns `400` with `code: "wardrobe_too_small"` **before** any AI call.

### 2.8 Stylist screen
Occasion chips, date picker defaulting to today, coat override (Auto / Yes / No), a free-text notes field, and the current weather displayed above the button.

While waiting — 4 to 8 seconds — show a skeleton of the look card and cycle two or three short status lines. Never a bare spinner.

### 2.9 Look card
Items laid out by `layer` and `category`, not in arbitrary order. `reasoning` and `weather_note` rendered as text. `missing_pieces` as a muted note beneath when present. Tapping an item opens its detail page. A "Try again" button re-requests.

### 2.10 Anchor — "Style around this"
Add `anchor_item_id` to `POST /looks/suggest`. Inject the `ANCHOR` block into the prompt. Add validation rule 7: the anchored item appears in the returned look.

Frontend: a primary **Style around this** button on the item detail screen, navigating to the stylist with the anchor pre-set and pinned above the form with an × to clear.

This is the original problem the product exists to solve — *I am holding this garment and do not know what goes with it.* Roughly half a day.

### 2.11 Swap a single item
Add `locked_item_ids`, `replace_role`, and `exclude_item_ids` to the same endpoint. Inject the `LOCKED` block. Add validation rule 8: all locked items present, the excluded item absent.

Frontend: a small ↻ badge on each item in the look card. Tapping it locks the others, names that role for replacement, and adds the rejected item to the exclusion list. Spinner on that tile only — the rest of the card must not move.

Most looks are fine except one piece, usually the shoes. "Try again" rerolls everything and throws away the good parts. Roughly half a day, same endpoint, no new infrastructure.

### 2.12 Weather strip
A persistent strip on the wardrobe screen showing the current temperature and condition for the user's home location, tappable through to the stylist. Small piece of work, disproportionate effect on how alive the app feels.

---

## Acceptance criteria

- [ ] `build_rule` unit tests pass at every boundary, both sides
- [ ] Requesting a look on the demo wardrobe returns a complete outfit in under 10 seconds
- [ ] The look always contains shoes, and either a top and bottom or a dress
- [ ] Every returned item exists in the wardrobe — verified by an integration test using a poisoned fixture that returns an unknown ID, asserting `502`
- [ ] Forcing 12°C produces outerwear; forcing 30°C produces none. Same wardrobe, same occasion.
- [ ] A user with 5 items gets `400 wardrobe_too_small` and no AI call is made
- [ ] `reasoning` explains the combination rather than listing the items
- [ ] Two identical requests produce a valid look both times
- [ ] "Style around this" on a specific item returns a look containing that item, 5 times out of 5
- [ ] Swapping the shoes keeps every other item identical and never returns the rejected shoe
- [ ] A request with no anchor and no locks behaves exactly as before

## Commit checkpoints

`feat(weather): open-meteo client and rules` · `test: weather rule boundaries` · `feat(ai): wardrobe serializer` · `feat(ai): stylist service` · `feat(ai): response validation` · `feat(db): looks schema` · `feat(api): suggest endpoint` · `feat(web): stylist screen` · `feat(web): look card` · `feat(ai): anchor item support` · `feat(web): style around this` · `feat(ai): single item swap` · `feat(web): swap button`

## If you fall behind

Cut the weather strip and the coat override. If pressed further, cut the swap (2.11) — but **keep the anchor (2.10)**. The anchor is the original use case; the swap is refinement on top of it.

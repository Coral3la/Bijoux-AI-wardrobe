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
`GET /me/locations/search?q=` proxying Open-Meteo geocoding. `PATCH /me` accepting **the whole body `04-API-SPEC.md` prints** — `display_name`, `height_cm`, the three sizes, `style_notes` and the three home fields.

This line named the three home fields only until the task ran. It was widened on `AUDITS.md` **O-6**'s recommendation: the stylist prompt at 2.4 reads `height_cm` and `style_notes`, `05-FRONTEND-SPEC.md` §8's profile screen is owned by no task, and a narrow `PATCH` would leave that prompt block structurally empty in every request this project ever makes. Same route, longer schema. `DECISIONS.md` 149.

The demo account is seeded with a home location here too — `AUDITS.md` **O-20** measured that no row on the database had one, which leaves 2.7's forecast lookup and 2.12's strip with no default on the account a visitor signs into.

### 2.3 Wardrobe serialiser
`services/serializer.py` → `serialize_wardrobe(items) -> str` producing the compact one-line-per-item format. Omit nulls. Uppercase `short_id` at the start of each line.

Unit test the token budget: 150 items must serialise to under 6,000 tokens. Use `tiktoken` to assert it.

### 2.4 Stylist service
`services/stylist.py` → `suggest_looks(wardrobe, context, correction=None) -> StylistResponse`.

Prompt in `app/prompts/stylist_system.md`. User message assembled per `03-AI-CONTRACTS.md`. Structured Outputs with the response schema. `USE_FAKE_AI` branch returning a deterministic look.

Send the **whole wardrobe**. The only server-side exclusion is swimwear and sleepwear, and it is a configurable list.

**Two lines above are what the task found rather than what it was given, and both are recorded rather than quietly done.**

The exclusion had nothing to match on when this task ran: neither word was in `Category` or `SUBCATEGORIES` (`AUDITS.md` **O-21**). It was not struck, because the product answer is that a user photographing their wardrobe uploads swimwear and sleepwear and the app should handle them — so both became first-class categories at new task **2.6a**, which has since landed, and 2.7 applies the filter beside `ready`-only and `is_archived`. `suggest_looks` filters nothing; it serialises exactly the wardrobe it is handed, which is what lets it be tested as a format.

And the `USE_FAKE_AI` branch **cannot** return a recorded fixture. `short_id`s are generated per row, so literal ids in a fixture would fail 2.5's hallucination guard on every call and no E2E journey could ever see a look card. The fake picks from the wardrobe it is given — first shoes, then a top and bottom, else a dress — and says out loud in `reasoning` that it is a placeholder. `DECISIONS.md` 159.

`correction` is in the signature because a violation has to reach the model somehow; it is 1.2b's `tag_item(image_url, correction=…)` shape on the second contract. "2.5 owns the retry" is what this line said until 2.5 ran and found the seam is one task further out: 2.5 words the violation, **2.7 spends the retry**, because re-calling the stylist takes the whole wardrobe and context and a validator that held those would be the orchestrator. `DECISIONS.md` 164.

### 2.5 Response validation
`validate_look_response()` implementing the rules of `03-AI-CONTRACTS.md`'s table in order. The first rule — every returned ID exists in **this user's** wardrobe — is the hallucination guard and must never be relaxed.

**Five rules, not six, and the missing one is arithmetic rather than a cut.** Rule 5 reads `packing_list.item_ids` and `STYLIST_SCHEMA` has no `packing_list`: it was deferred to Stage 4 at task 2.4 because its `by_category` map cannot be expressed in strict mode as written (`DECISIONS.md` 157). A rule with no field to read cannot be implemented, and writing it against a field that arrives in two stages would be untested code. Rules 7 and 8 arrive with the anchor at 2.10 and the swap at 2.11. So 2.5 runs 1, 2, 3, 4 and 6.

One retry naming the violation, then `502` with `code: "stylist_failed"` — **both of which are 2.7's.** `validate_look_response` is synchronous, calls nothing and raises nothing; it returns the first violation beside the response with its ids upper-cased, and the endpoint that holds the wardrobe and the context decides whether to spend the retry. `DECISIONS.md` 164.

Unit tests: each of the five rules failing independently, against hand-built response objects.

### 2.6 Look persistence
Migration `0002_looks` creating `looks` and `look_items`. Every suggestion is persisted with `is_saved=false` before the response returns — this costs nothing and is what makes the evaluation story possible later.

### 2.6a Vocabulary — swimwear and sleepwear

Opened by **O-21** and scheduled here because 2.7 is the first task that needs the filter, and because landing it after `0002_looks` leaves that migration at the number `02-DATA-MODEL.md` already prints.

Add `swimwear` and `sleepwear` to `Category` in `02-DATA-MODEL.md` first, then `app/enums.py` (`SUBCATEGORIES`, `FIELD_APPLIES_TO`, `LAYERS_BY_CATEGORY` all take entries), then `frontend/src/app/shared/models/enums.ts` and its spec. Migration `0003` does the `ALTER TYPE item_category ADD VALUE` — `category` is a PostgreSQL `ENUM` type created by `0001`, not a `TEXT` column, so this is a migration and not only a constant. **Measure whether `ALTER TYPE … ADD VALUE` runs inside Alembic's transaction on PostgreSQL 18 before writing it**; do not assume from the version number. `02`'s migration table renumbers with it: Stage 3's feedback becomes `0004`, Stage 4's trips `0005`.

Nothing already committed is re-tagged — no seed row would match either value, so the demo wardrobe is unaffected. One knock-on: the vision prompt renders `SUBCATEGORIES`, so `PROMPT_VERSION` changes the moment this lands. Harmless while 1.11 is unrun, and a reason to land it before 1.11 rather than after.

**Ran 2026-08-27.** `ALTER TYPE … ADD VALUE` was measured rather than assumed: on PostgreSQL 18.6 both statements run inside Alembic's transaction, so `0003` needs no `autocommit_block()`. `downgrade()` is a deliberate no-op — PostgreSQL has no `DROP VALUE` and a raising downgrade would block the `alembic downgrade 0001` every mutation run starts from. The task list above was one file short: **`frontend/public/i18n/en.json` needed ten keys**, because both the filter bar and the tag editor render `vocabulary.category.<value>` over every member of `CATEGORIES` and `t()` falls back to the raw key. `DECISIONS.md` 167.

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

`feat(weather): open-meteo client and rules` · `test: weather rule boundaries` · `feat(api): profile and location search` · `feat(ai): wardrobe serializer` · `feat(ai): stylist service` · `feat(ai): response validation` · `feat(db): looks schema` · `feat(core): swimwear and sleepwear categories` · `feat(api): suggest endpoint` · `feat(web): stylist screen` · `feat(web): look card` · `feat(ai): anchor item support` · `feat(web): style around this` · `feat(ai): single item swap` · `feat(web): swap button`

## If you fall behind

Cut the weather strip and the coat override. If pressed further, cut the swap (2.11) — but **keep the anchor (2.10)**. The anchor is the original use case; the swap is refinement on top of it.

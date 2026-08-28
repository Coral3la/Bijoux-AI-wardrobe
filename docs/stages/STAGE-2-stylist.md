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

This line named the three home fields only until the task ran. It was widened on `AUDITS.md` **O-6**'s recommendation: the stylist prompt at 2.4 reads `height_cm` and `style_notes`, `05-FRONTEND-SPEC.md` §8's profile screen was owned by no task — 2.10a owns it now — and a narrow `PATCH` would leave that prompt block structurally empty in every request this project ever makes. Same route, longer schema. `DECISIONS.md` 149.

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

**Ran 2026-08-27.** The orchestration is the easy half; what this task actually
decided is the three things only a request can decide, and each closes or opens
something. **The wardrobe the model sees** — `ready`, not archived, and not in
`STYLIST_EXCLUDED_CATEGORIES`, a validated `Settings` list defaulting to
swimwear and sleepwear, which closes `AUDITS.md` **O-21** eight tasks after it
was opened. **The retry** — one re-call carrying the violation, and *none* for a
`ValueError` or a provider exception, because a retry with nothing to say is a
coin flip that costs the whole wardrobe twice. **What a failure is worth** —
`502 stylist_failed` for all three, one message to the user, three
distinguishable log lines.

Two guard details are narrower than the line above. The count is over the
**filtered** wardrobe rather than every `ready` row — six garments the stylist
never sees cannot make an outfit — and it runs before the *forecast* as well as
before the model. `04-API-SPEC.md` says "usable" now, so the document and the
code agree.

The task list was three items longer than this section. `occasion` had no home:
`04` carried the six values alone, so `02-DATA-MODEL.md` gains an `occasion`
section, `enums.py` an `Occasion`, and `enums.ts` plus six i18n keys mirror it —
**O-8** closes, and the i18n half is 2.6a's lesson applied rather than
rediscovered. A missing home location needed a code that did not exist:
`home_location_missing` (`400`), because `forecast_unavailable` means *no
weather for that day* and this means *we do not know where you are*. And the
`Weather:` line of the prompt had no builder: `summarize_forecast` lands beside
`build_rule`, using the same `> 1` mm threshold so the sentence cannot
contradict the rule printed under it.

`look_items.role` stays `NULL` — **O-25**'s vocabulary is 2.11's, which is the
task that reads one — while `position` is written from the model's ordering,
because that is destroyed at persistence if nothing records it. A look that
failed twice is not persisted at all. `DECISIONS.md` 168–173, and **O-26** and
**O-27** open: the model's `occasion` echo now has no reader, and `USE_FAKE_AI`
cannot build a valid look on a day cold enough to require a coat.

### 2.8 Stylist screen
Occasion chips, date picker defaulting to today, coat override (Auto / Yes / No), a free-text notes field, and the current weather displayed above the button.

While waiting — 4 to 8 seconds — show a skeleton of the look card and cycle two or three short status lines. Never a bare spinner.

### 2.9 Look card
Items laid out by `layer` and `category`, not in arbitrary order. `reasoning` and `weather_note` rendered as text. `missing_pieces` as a muted note beneath when present. Tapping an item opens its detail page. A "Try again" button re-requests.

### 2.10 Anchor — "Style around this"
Add `anchor_item_id` to `POST /looks/suggest`. Inject the `ANCHOR` block into the prompt. Add validation rule 7: the anchored item appears in the returned look.

Frontend: a primary **Style around this** button on the item detail screen, navigating to the stylist with the anchor pre-set and pinned above the form with an × to clear.

This is the original problem the product exists to solve — *I am holding this garment and do not know what goes with it.* Roughly half a day.

### 2.10a Profile screen — the home city the stylist needs
`/profile`, and the route into it from the wardrobe header. A form over `PATCH /me`: display name, height, the three sizes, style notes, and the home city through the `GET /me/locations/search` type-ahead. `05-FRONTEND-SPEC.md` §8 already specifies the screen.

**Nothing on the backend is in scope, and that was measured rather than assumed.** `PATCH /me` has accepted the whole nine-field body since 2.2 (`DECISIONS.md` 149), the geocoder proxy has shipped with no caller since the same task, and `seed_demo.py` writes the demo account's Tel Aviv. What is missing is the only thing that can reach any of it — which is `AUDITS.md` **O-6**'s second half, recommended after 2.12 and unwritten since.

**It goes ahead of 2.11 because it is not a refinement.** `POST /looks/suggest` answers `400 home_location_missing` on an account with no `home_lat`/`home_lon`, and every route to setting one today is a `curl`. The swap improves a look the user can already get; this decides whether she can get one. It goes ahead of 2.12 because the weather strip is drawn from the home location this screen sets.

The three home columns are one field (`DECISIONS.md` 151): the picker writes `home_city`, `home_lat` and `home_lon` together or clears all three, and `UserUpdate` answers `422` to any other combination. Roughly half a day.

### 2.11 Swap a single item
Add `locked_item_ids`, `replace_role`, and `exclude_item_ids` to the same endpoint. Inject the `LOCKED` block. Add validation rule 8: all locked items present, the excluded item absent.

Frontend: a small ↻ badge on each item in the look card. Tapping it locks the others, names that role for replacement, and adds the rejected item to the exclusion list. Spinner on that tile only — the rest of the card must not move.

Most looks are fine except one piece, usually the shoes. "Try again" rerolls everything and throws away the good parts. Roughly half a day, same endpoint, no new infrastructure.

**The three fields are one feature and landed together.** `replace_role` without `locked_item_ids` is a `422` by `04-API-SPEC.md`'s own rule, so the swap cannot be built one field at a time: locking the rest of the look is what gives the role something to mean.

**`AUDITS.md` O-25's vocabulary half closed here, and a dress has no role.** `top · bottom · outer · shoes · bag · accessory` is now a section in `02-DATA-MODEL.md` with a `Role` in `enums.py` and a `ROLES` in `enums.ts`, enforced by `replace_role` alone — `look_items.role` is **still `NULL`**, because the badge derives a role from the item's own `category` in the browser and nothing reads the column before Stage 3. The two mismatches the audit opened over are answered: `outerwear` the category is `outer` the role, and `dress` is not a role at all, since replacing a dress can legally return a top and a bottom under rule 2. So the badge is drawn on every tile **except a dress**, which is an amendment to `05-FRONTEND-SPEC.md` rather than an implementation detail. `DECISIONS.md` 175, 176.

**One new error code, and one `422` deliberately left generic.** `locked_unavailable` for a locked id the wardrobe would not send — `anchor_unavailable`'s check and its widening, and the second `422` here a correct client can provoke, since a locked garment can be archived between the look and the tap. A role with no locks stays `validation_error`: the badge always sends both, so no correct client can build that body. An unknown `exclude_item_ids` entry is dropped rather than refused. `DECISIONS.md` 177.

**The fake had to learn the locks, for the reason the anchor taught at 2.10.** `_fake_items` keeps every locked item and never picks an excluded one; without it rule 8 would reject the placeholder twice and every `USE_FAKE_AI` swap — E2E journeys included — would be a `502`. Swap requests send **no** `anchor_item_id`: every garment the anchor protected is locked anyway, and on the anchored tile itself rule 7 would demand the item rule 8 forbids.

### 2.11a Rule 9 — two base-layer tops

Add validation rule 9 to `03-AI-CONTRACTS.md`'s table and to
`validate_look_response`: no look contains two items that are `category: top`
and `layer: base`. Rewrite the system prompt's OUTPUT line so it names the tag
the rule reads. One unit test, no new error code, no endpoint change.

**It is a bug rather than a feature, which is why it is lettered and not
numbered.** The prompt has forbidden two base tops since Stage 0 and nothing
enforced it — `AUDITS.md` **O-28**, opened and closed here — while every other
OUTPUT line in that block has a rule behind it. The model does this often
enough to be worth the rule.

**The prompt is edited in the same commit, and that is half the task.** *"Unless
one is explicitly a layering piece"* is a judgement the model can make in prose
while returning two rows both tagged `base`; the new line names the tag, so the
retry becomes the exception rather than the ordinary route to a `502`. The rule
without the rewrite would be correct and expensive. `DECISIONS.md` 178.

Half an hour. Rule 9 reads both columns because `LAYERS_BY_CATEGORY` gives
`top` no answer — a top is legitimately `base` or `mid`, so neither column
identifies a second shirt alone.

### 2.11b Rule 9 widened — one item per slot

Generalise 2.11a's rule from base tops to every slot a person has one of:
one `outer`, one `base` top, one `bottom`, one `dress`, one pair of `shoes`,
one `bag`, accessories at the prompt's own limit of two — and no separate
`top` or `bottom` beside a `dress`. Rule 3 is absorbed into it and keeps its
number. Four unit tests, no new error code, no endpoint change.

**Opened by a look that reached a user**: a shoe-swap answered with long jeans
*and* shorts. 2.11a fixed the instance it was shown and this fixes the class —
**rule 2 asks whether a bottom is present and never how many**, so nothing in
the table could see it. `AUDITS.md` **O-28** widened; the item is the first
this project has closed twice.

**The fake had to be taught the rule, which is the third time.** `_fake_items`
joined a dress with a top and a bottom whenever the dress was anchored or
locked, so under `USE_FAKE_AI` every anchored dress became a `502` the moment
the rule widened — measured by running it. Rules 7, 8 and now 9 have each
needed this, which is `AUDITS.md` **O-27**'s open question rather than
something this task settles. `DECISIONS.md` 179.

Half an hour.

### 2.12 Weather strip — and the only way into the stylist
A persistent strip on the wardrobe screen showing the current temperature and condition for the user's home location, tappable through to the stylist. Small piece of work, disproportionate effect on how alive the app feels.

**It carries the general "style me" entry point, and that is the larger half of the task.** `/stylist` opens on the general request form — occasion, date, coat, notes, no anchor — and nothing in the application links to it: `app.routes.ts` has said so since 2.8, there is no nav shell, and 2.10's "Style around this" is a route in from one garment rather than a way to ask for a look at all. This strip is the only entry point `05-FRONTEND-SPEC.md` draws.

**So the tap target does not depend on the forecast.** An account with no home location has no temperature to print, and a strip that rendered nothing in that case would leave the wardrobe with no route to the stylist. It degrades instead: the strip stays, the temperature is replaced by a prompt to set a home city that links to 2.10a's screen, and the tap into `/stylist` is there either way.

**Built at task 2.12, and the strip is not itself the tap target.** `05-FRONTEND-SPEC.md` draws the whole strip as tappable, and the degraded state makes that impossible: the prompt to set a home city is a link to `/profile`, and an anchor inside an anchor is not a document. So the strip is a row — the weather line, or that prompt — with a labelled **Style me** link into `/stylist` that is present in every state. `05` is annotated where it draws it. `DECISIONS.md` 180.

**Three states, not two.** The forecast, the no-home-location prompt, and an account that *has* a home city whose forecast has not arrived or did not — which renders nothing on the left and keeps the link. Showing the set-a-city prompt there would be the wrong sentence about a request that failed, and an error banner would report something the user did not ask about: the strip fails silently, which is `StylistStore.loadWeather`'s own judgement one screen over.

**The component fetches for itself rather than borrowing the stylist's store.** `WeatherStrip` reads `home_lat`/`home_lon` off `AuthService.currentUser()` and calls `GET /weather` — the same ten lines `StylistStore.loadWeather` runs — because the alternative wires the wardrobe screen to the state container of a screen it merely links to. It prints the day's **high**, which is the number `summarize_forecast` already sends the model, and imports `todayInLocalTime` rather than copying it so the strip and the date picker cannot disagree about which day today is.

**No emoji.** The mock in `05` draws 🌤; there are eight conditions and no icon map, and a sun over a rainy line is worse than no glyph at all. Building one was not this task's.

---

## Acceptance criteria

- [ ] `build_rule` unit tests pass at every boundary, both sides
- [ ] Requesting a look on the demo wardrobe returns a complete outfit in under 10 seconds
- [ ] The look always contains shoes, and either a top and bottom or a dress
- [ ] Every returned item exists in the wardrobe — verified by an integration test using a poisoned fixture that returns an unknown ID, asserting `502`
- [ ] Forcing 12°C produces outerwear; forcing 30°C produces none. Same wardrobe, same occasion.
- [ ] A user with 5 items gets `400 wardrobe_too_small` and no AI call is made
- [ ] The wardrobe screen reaches `/stylist` in one tap, with a home city set and without one
- [ ] `reasoning` explains the combination rather than listing the items
- [ ] Two identical requests produce a valid look both times
- [ ] "Style around this" on a specific item returns a look containing that item, 5 times out of 5
- [ ] Swapping the shoes keeps every other item identical and never returns the rejected shoe
- [ ] A look never contains two tops tagged `base`; a base top under a `mid` overshirt still passes
- [ ] A look never contains two bottoms, two pairs of shoes, or a dress beside a top or a bottom
- [ ] A request with no anchor and no locks behaves exactly as before

## Commit checkpoints

`feat(weather): open-meteo client and rules` · `test: weather rule boundaries` · `feat(api): profile and location search` · `feat(ai): wardrobe serializer` · `feat(ai): stylist service` · `feat(ai): response validation` · `feat(db): looks schema` · `feat(core): swimwear and sleepwear categories` · `feat(api): suggest endpoint` · `feat(web): stylist screen` · `feat(web): look card` · `feat(ai): anchor item support` · `feat(web): style around this` · `feat(web): profile and home city` · `feat(ai): single item swap` · `feat(web): swap button` · `fix(ai): reject two base-layer tops in a look` · `fix(ai): one item per slot in a look` · `feat(web): weather strip`

## If you fall behind

Cut the coat override, and cut the weather strip's *forecast* — but not the strip itself: it carries the only link into `/stylist`, so what is cut is the temperature, not the tap target. If pressed further, cut the swap (2.11) — but **keep the anchor (2.10)**. The anchor is the original use case; the swap is refinement on top of it.

**2.10a is not on this list.** Without a home city the stylist answers `400` on every request and there is nothing to demonstrate at all.

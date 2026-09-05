# Code review — 2026-09-05

Read-only pass over `backend/`, `frontend/` and `e2e/`. Nothing in the tree was
changed by this review. The developer applies findings in approved batches.

## Summary

The repository is in good shape. Every non-test source file under the three
directories was read in full. Read-only tooling was run on a scratchpad mirror,
never on the tree: `ruff check` (clean), `ruff format --check` (one file),
`mypy` (clean, 50 files), `eslint` over `src/**/*.ts` and `*.html` (clean),
`tsc --noEmit --noUnusedLocals --noUnusedParameters` over both tsconfigs
(clean), an i18n key sweep both ways (one unused key, no missing key), and a
Tailwind theme-token usage count (every token has a caller). So there are no
unused imports, no unused locals, no `any`, no `console.log`, no skipped or
focused tests, no `TODO`s, and no commented-out code anywhere in scope.

What the review did find:

- **One real security defect.** The SPA catch-all in `app/main.py` joins a raw
  path parameter onto the static directory with no containment check. Driving
  the mirrored app with `GET /../pyproject.toml` returned the file. This is live
  only in the Docker image, where `static/` exists — which is production.
- **One latent defect and a large duplication in the same place.** `get_forecast`
  never checks that the provider answered the day it asked for, while its
  sibling `get_daily_forecast` does; making the first delegate to the second
  fixes the gap and deletes forty-five duplicated lines.
- **A trip system prompt that contradicts the trip user message** about how
  many looks a day carries.
- **Stale comments** whose stated reason is now false: the `trip_id` filter
  (two places), three route comments about screens with "no entry point", the
  stylist page's "skeleton unmounts the form", and two chip copies justified by
  a description of `appChip` that stopped being true when the directive was
  converted.
- **Dead code with no caller**: `userLabel`, the skeleton's `circle` shape, the
  chip's `accent` variant (self-declared), three of four transforms in the
  frontend pipe and two of four in the backend enum, one i18n key, an
  unreachable `health` branch, a stale Karma launch config, and two base
  exception classes nothing catches.
- **Duplication the code itself records as "the third/fourth instance"**: the
  Atelier pill written out at nine call sites, the type-ahead copied between the
  profile and the trip form, error-code extraction spelled seven times, the
  garment-name fallback six times, and two verbatim copies of `_hydrate` on the
  backend.

Nothing found changes what the application does for a correct client except
the traversal fix and the `get_forecast` range check, and neither of those
changes a legitimate response.

## What this review does not cover

- Test bodies were linted and type-checked but not read line by line: none of
  the 43 frontend specs and none of the 33 backend test modules beyond
  `conftest.py`. Findings about tests are limited to what greps and the dead-
  export scan surfaced.
- No test was run, no build was made, no dev server was started. The traversal
  probe ran against a scratchpad copy with a fake `static/` directory.
- Documents other than `CONVENTIONS.md` and one paragraph of `04-API-SPEC.md`
  were not read; "stale comment" findings are judged against the code, not
  against `DECISIONS.md`.
- Templates were read as inline strings, not rendered. A class that exists and
  does the wrong thing visually would not have been caught. (`border-bs` was
  suspected and checked against the built CSS: it is a real Tailwind 4 logical
  utility and emits a rule.)
- `.github/`, the root `Dockerfile` and `docs/` were outside scope. Noticed in
  passing: `.github/workflows/` holds only a `.gitkeep`, so the CI that
  `CONVENTIONS.md` refers to does not exist yet.

Severity: **bug** (wrong behaviour), **cleanup** (dead, stale or misleading;
no behaviour), **simplification** (a shorter version with identical behaviour).
Each finding says whether the change is safe with no behaviour change.

---

## Bugs

### B1. Path traversal in the SPA catch-all

`backend/app/main.py:86-88`

```python
candidate = _STATIC_DIR / spa_path
if candidate.is_file():
    return FileResponse(candidate)
```

`spa_path` is the raw `{spa_path:path}` parameter. Neither uvicorn nor
Starlette collapses `..`, so `../pyproject.toml` resolves to a file above
`static/` and is served. Verified on the mirror: `GET /../sentinel.txt`
returned the sentinel's contents with status 200, `GET /../pyproject.toml`
returned the project config. In the image every backend source file and
`alembic.ini` are one directory up from `static/`, and `/../../etc/passwd`
reaches the OS. The route is only registered when `static/` exists
(`main.py:76`), so local `uvicorn --reload` is unaffected; production, which is
the Docker image, is exposed.

Fix (two lines; `_STATIC_DIR` is already resolved at `main.py:74`):

```python
candidate = (_STATIC_DIR / spa_path).resolve()
if candidate.is_file() and candidate.is_relative_to(_STATIC_DIR):
    return FileResponse(candidate)
```

Safe: every legitimate asset path resolves inside `static/` and is unchanged.
Worth a test that a `..` path answers `index.html` (or 404) rather than a file.

### B2. `get_forecast` accepts a shifted answer that `get_daily_forecast` refuses

`backend/app/services/weather.py:283-342` and `345-444`

`get_daily_forecast` compares every returned date against the range it asked
for (`428-439`) and raises `ForecastProviderError` on a mismatch. `get_forecast`
takes `_forecasts(...)[0]` (`332`) with no such check, so a provider answer for
a neighbouring day is returned and cached under the requested key for thirty
minutes. Unlikely with `timezone=auto`, but the two entry points disagree about
what counts as an answer, and the docstring at `240-259` says they share one
parser precisely so they cannot.

The two functions are otherwise the same forty-five lines (horizon check,
rounding, params, request, `400` handling, cache write). Fix both at once:

```python
async def get_forecast(lat: float, lon: float, date: datetime.date) -> Forecast:
    return (await get_daily_forecast(lat, lon, date, date))[0]
```

Behaviour for a well-formed answer is identical (same request, same cache
entries, same errors). The only change is the new refusal of a shifted day.
The log line at `334-337` ("Forecast request failed") becomes the daily one;
no test pins either string.

### B3. The trip system prompt contradicts the trip user message (low)

`backend/app/prompts/stylist_system.md:31-33` and `37-39`

The system prompt's PACKING A TRIP section says "build exactly one look per
day and give each look the `day` number" and "No two days may wear an identical
set of items". Since 4.13/4.15 a date carries one or two looks, the schema
requires `slot` (`stylist.py:108-112`), and the user message says "Build one
look per line above — N looks for M days" (`stylist.py:558`). The word `slot`
does not appear in the system prompt at all. The model is told two different
counts; rule 4 and rule 10 catch a per-day answer, but only after a paid call
and at the cost of the one retry.

Fix: reword the two sentences to "one look per line" / "per slot" and mention
`slot`. Not a code change; whether the retry rate has actually moved is a
question for `docs/eval-results.md`.

---

## Cleanup

### C1. Unreachable `health` branch, and `/health/` serves the SPA

`backend/app/main.py:83`

```python
if spa_path.startswith("api/") or spa_path == "health":
```

`/health` matches the route at `main.py:59` first, so the catch-all never sees
`spa_path == "health"`. What it does see is `health/` (trailing slash), which
this clause does not match — verified: `GET /health/` answers `index.html` with
200. Delete the clause (safe, no path reaches it). If the trailing-slash case
matters, that is a separate decision (`startswith("health")`).

### C2. `ruff format` wants a change in `main.py`

`backend/app/main.py:68-69`

`ruff format --check` reports one file: a blank line is missing before the
section comment at `69` and the file's last line. `ruff format app/main.py`.
Safe.

### C3. Stale reason for the missing `trip_id` filter (backend)

`backend/app/api/v1/routes/looks.py:434-436`

> the column arrives with migration `0005`, and a parameter that filters on a
> column the database lacks is a 500 rather than an empty list.

`0005` landed on 2026-08-31 and `Look.trip_id` exists (`models/look.py:106`).
`04-API-SPEC.md` (GET /looks) already carries the current reason: the filter
has no caller in any planned screen. Replace the comment with that sentence, or
delete it. Safe.

### C4. Same stale reason on the frontend

`frontend/src/app/core/api/looks.api.ts:31-34`

> `04-API-SPEC.md` names a `trip_id` the server does not implement until
> migration 0005

Same fix as C3. Safe.

### C5. Three route comments describe an app with no navigation bar

`frontend/src/app/app.routes.ts:31-33`, `39-42`, `48-52`

`/stylist` "No entry point links here yet", `/profile` "with no link into it:
`app.html` is a bare router-outlet", `/saved` "the nav bar AUDITS.md O-29 asks
for. That item is still open." `app.html:6-8` renders `NavBar`, whose
`NAV_ITEMS` (`nav-bar.ts:11-17`) link all three; `weather-strip.ts:96-100` and
`item-detail.page.ts:54-61` also reach `/stylist`. The `/trips` comment at
`58-63` already records O-29 as claimed by 4.9. Delete the three sentences or
reduce each to the ordering reason. Safe.

### C6. "The skeleton unmounts that control on every submit" — it no longer does

`frontend/src/app/features/stylist/stylist.page.ts:197-201`

The anchor is said to live on the page because "the skeleton unmounts that
control on every submit". The form is permanent since DR.20 (`stylist.page.ts:
126-130`; `look-request-form.ts:181-185` records the change and gives the
current reason). Rewrite to the current reason or delete. Safe.

### C7. Two chip copies justified by a description of `appChip` that is no longer true

`frontend/src/app/features/wardrobe/filter-bar.ts:52-65`,
`frontend/src/app/features/stylist/look-request-form.ts:14-26`

Both comments say the local `CHIP`/`CHIP_STATES` exist because `appChip` "paints
the pre-Atelier chip — 14px, a strong line, a white fill" and sets its font
size in a shared base. `shared/ui/chip.ts:12-13` and `19-23` now carry the
Atelier chip: the same base string and the same default states as both copies,
byte for byte apart from `shrink-0` (both) and `gap-x-1.5` (filter bar). The
directive was converted at 222 (`chip.ts:5-11`) and these two comments were not
revisited.

Fix: `appChip [active]="…"` on the buttons plus `class="shrink-0"` /
`class="shrink-0 gap-x-1.5"` (a static class merges with the host binding —
`upload-sheet.ts:64-69` relies on the same rule); delete `CHIP`, `CHIP_STATES`
and `chipClass` in both files and the two `[attr.aria-pressed]` template
bindings, which the directive supplies from the same input (`chip.ts:34-38`).
Rendered classes and the announced state are identical. Also retire the
comment at `filter-bar.ts:78-85`, whose subject is the binding being removed.

### C8. `appChip`'s `accent` variant is dead by its own comment

`frontend/src/app/shared/ui/chip.ts:3`, `15-18`, `24-27`

"`accent` has no caller and is left standing rather than deleted". Only
`chip.spec.ts:67-70` exercises it. Delete the variant from `ChipVariant`, the
`STATES` entry and the spec case. `variant` then has one value and the input
can go too. Safe.

### C9. `userLabel` has no caller

`frontend/src/app/shared/models/user.model.ts:41-46`

No non-spec file calls it; the two mentions (`item-card.ts:158`,
`wardrobe.page.ts:301`) are comments explaining that they deliberately do not.
Delete the function and `user.model.spec.ts`; rewrite the two comments so they
do not point at a function that is gone. Safe.

### C10. The skeleton's `shape` input has no caller

`frontend/src/app/shared/ui/skeleton.ts:3`, `17`, `33`

Every call site sets `radius` and none sets `shape`. Delete `SkeletonShape`,
the input, and the ternary (`const corners = this.radius()`), plus the spec
case. Safe.

### C11. Three of the four frontend transforms have no caller

`frontend/src/app/shared/pipes/cloudinary-url.pipe.ts:14-19`, `21`

Only `detail` is used (`item-detail.page.ts:36`). The comment explains why
`thumbnail` is caller-less; `lookcard` and `vision` are not explained and have
no caller either. Either narrow to `detail` (and `pipe.spec.ts:30`), or extend
the comment to say the full table is kept as a deliberate mirror of
`07-DEPLOYMENT.md`. Deleting is safe.

### C12. Two of the four backend transforms have no caller

`backend/app/services/storage.py:45`, `47`, `57`, `59`

`THUMBNAIL` is read by `schemas/item.py:59` and `VISION` by `tagging.py:90`.
`DETAIL` and `LOOKCARD` are read only by `test_storage.py:148-152`; the frontend
builds `detail` from its own copy. Same choice as C11: delete the two members
(and the two test rows) or say the enum mirrors the deployment table on
purpose. Deleting is safe.

### C13. Unused i18n key

`frontend/public/i18n/en.json:249` — `item.notFound`

Nothing references it. `item-detail.page.ts:189-190` renders `item.error.load`
for every load failure, including a 404, where `trip-detail.page.ts:44-57` has
the branch this key was written for. Delete the key, or add the branch. Safe.

### C14. A comment cites a `DECISIONS.md` entry that does not exist

`backend/scripts/seed_demo.py:83` — "`DECISIONS.md` 432"

The decisions log ends at 229. Fix the number or drop the citation.

### C15. Stale Karma launch configuration

`frontend/.vscode/launch.json:12-18` (and its task at `tasks.json:23-40`)

The "ng test" configuration opens `localhost:9876/debug.html`, Karma's page.
The project tests with vitest (`angular.json:78`, `package.json`
devDependencies). Delete both entries. Safe.

### C16. Scaffold comments that restate nothing

- `frontend/src/styles.scss:1` — "You can add global styles to this file…"
- `frontend/src/app/shared/models/enums.ts:1` — the file's own path
- `frontend/tsconfig.json:1-2`, `tsconfig.app.json:1-2`, `tsconfig.spec.json:1-2`,
  `.vscode/launch.json:2`, `.vscode/tasks.json:2` — links to generic docs

None says why. Delete. Safe.

### C17. A type-narrowing filter that is redundant after its own loop

`backend/app/services/stylist.py:1028-1034`

The loop at `1028-1032` returns on any `None` day or slot, so the
`if look.day and look.slot` at `1034` can only drop a look whose `day` is `0`
— which it then reports as "missing" rather than "not asked for". Use
`is not None` on both, or build the narrowed list inside the loop. Behaviour is
identical except for `day: 0`, which becomes the more accurate message.

### C18. `_in_day_order` returns a position nobody reads

`backend/app/services/stylist.py:1169-1183`; callers `1065`, `1092`, `1149`,
`1284`

The function returns `(position, look)` pairs and its docstring says the
position is "what it is reported as"; all four callers write `for _, look in`.
Return the sorted `list[Look]`, simplify `1284` to
`for look in (_in_day_order(looks) if trip else looks)`, and cut the docstring
sentence. No test imports it. Safe.

### C19. Two exception base classes nothing catches

`backend/app/services/packing.py:43-44` (`PackingError`),
`backend/app/services/weather.py:134-135` (`WeatherError`)

Routes catch the subclasses by name; the only readers are an `isinstance`
assertion at `test_weather.py:633` and a comment at `test_packing.py:543`.
`CLAUDE.md` forbids speculative abstraction. Subclass `Exception` directly and
adjust the one assertion, or keep them and name a reader. Safe. Low priority.

### C20. `e2e/` is three placeholders

`e2e/fixtures/.gitkeep`, `e2e/pages/.gitkeep`, `e2e/tests/.gitkeep`

No Playwright config, no `package.json`, no test. Presumably Stage 5's; listed
so the scope line above is honest. `backend/tests/fixtures/.gitkeep` is the
same shape, awaiting 5.1's recorded fixtures (`vision.py:224-226`). No action.

### C21. `look_items.role` is a column with no writer and no reader

`backend/app/models/look.py:151-155`

Already documented at `154` and `looks.py:235-240`. Not deletable without a
migration; recorded, no action.

---

## Simplification and duplication

### S1. `_hydrate` is copied verbatim between two routes

`backend/app/api/v1/routes/looks.py:369-411`,
`backend/app/api/v1/routes/trips.py:478-517`

Forty-three identical lines. `trips.py:484-487` argues 197's line covers only
"what two routes both need" — this is exactly that. Move to
`_stylist_shared.py` as `hydrate_looks(db, rows)`. Both integration test
modules import the private name (`looks._hydrate`, `trips._hydrate`) and need
their import updated. Safe.

### S2. Forecast and geocoding error mapping written three and two times

Forecast: `routes/weather.py:37-48`, `routes/looks.py:184-195`,
`routes/trips.py:232-243` — the same two `except` branches with the same two
messages. Geocoding: `routes/me.py:65-70`, `routes/trips.py:226-231`.

Add `forecast_unavailable(exc)` and `geocoding_unavailable()` builders to
`_stylist_shared.py` beside `stylist_failed()` (`76-81`), which is the same
shape. Safe.

### S3. The judged-call block is written twice

`backend/app/api/v1/routes/looks.py:344-359`,
`backend/app/api/v1/routes/trips.py:1025-1038`

Same fifteen lines: `await judged(...)`, `ValueError` → 502, `OpenAIError` →
502, `not validation.ok` → 502, differing only in log text. One
`judged_or_502(wardrobe, context, *, what: str)` in `_stylist_shared.py`
(which already owns `ApiError`). Safe.

### S4. `get_item` re-implements `_owned`

`backend/app/api/v1/routes/items.py:355-366` vs `137-141`

Same query, same 404, same message. Body becomes
`return ItemResponse.model_validate(_owned(db, item_id, current_user.id))`.
Identical.

### S5. The `MissingPieceResponse` mapping is written twice

`backend/app/api/v1/routes/looks.py:295-300`,
`backend/app/api/v1/routes/trips.py:450-456`

One `missing_pieces(answer)` in `_stylist_shared.py`. Safe.

### S6. A third `_looks` query in `swap_item`

`backend/app/api/v1/routes/trips.py:1087`

`swapped_rows` (`1062`) already holds the same rows: nothing between `1062` and
`1087` changes which looks exist, and `expire_on_commit=False` keeps them
loaded. Replace with
`_by_day(trip.start_date, [(row.id, row.for_date, row.slot) for row in swapped_rows])`.
One query fewer, identical response. The projection
`[(row.id, row.for_date, row.slot) for row in rows]` appears at `875`, `1008`
and `1090`; a `_pairs(rows)` helper would name it once.

### S7. A whole dictionary built to look up one pair

`backend/app/api/v1/routes/trips.py:1008-1010`

`_by_day(...)` over every row, then `.get((request.day, request.slot))`. A
direct scan for the one row whose `for_date` and `slot` match reads as what it
is. Minor; identical.

### S8. `in_()` handed a dict

`backend/app/api/v1/routes/trips.py:850` — `Look.trip_id.in_(by_trip)`

SQLAlchemy iterates the keys, so it works; a reader has to know that.
`in_(list(by_trip))`. Identical.

### S9. `_owned` three times

`routes/items.py:137`, `routes/looks.py:414`, `routes/trips.py:167`

Same five lines over three models; `trips.py:172` calls itself "the third
copy". A generic `owned(db, model, row_id, user_id, what)` would collapse them.
Low value; listed because the code counts the copies.

### S10. The type-ahead is copied between the profile and the trip form

`frontend/src/app/features/profile/profile.page.ts:30-32`, `344-355`,
`373-391`, `473-497`, `523-529`;
`frontend/src/app/features/trips/trip-form.ts:39-41`, `436-452`, `458-477`,
`564-596`

Debounce timer, `issued` counter, `query`/`results`/`searching`/`searched`/
`searchError` signals, `noMatches`, `onQuery`, `search`, `stopTimer`,
`MIN_QUERY_LENGTH`, `SEARCH_DEBOUNCE_MS` — about seventy lines each, identical
apart from names. Extract a `locationSearch(api)` factory in `core/` on the
`packStatus` pattern (`pack-wait.ts:75-96`): called in an injection context,
returns the signals and the two handlers, registers its own `DestroyRef`
cleanup. Both components keep their templates; both specs keep passing.
Identical behaviour.

### S11. Error-code extraction spelled seven times

`core/state/looks.store.ts:7-9`, `24-32`; `core/state/stylist.store.ts:10-12`,
`41-59`; `core/state/wardrobe.store.ts:23-25`, `178-189`, `195-203`;
`features/trips/pack-wait.ts:40-42`, `49-65`;
`features/trips/trip-detail.page.ts:44-57`, `88-96`;
`features/wardrobe/item-detail.page.ts:324-326`

Each declares `ApiErrorBody` (or an inline `{ code?: string }`) and repeats "if
`HttpErrorResponse`, read `error.error.code`, look it up, else fall back". One
`apiErrorCode(error: unknown): string | undefined` and one
`errorKeyFor(error, table, fallback)` in `core/api/` remove six copies; the two
that also read a status keep a one-line branch. Safe.

### S12. The garment-name fallback six times

`look-card.ts:362-364`, `stylist.page.ts:347-349`, `packing-list.ts:147-149`,
`trip-look.ts:225-227`, `trip-detail.page.ts:771-773`,
`wardrobe-insights.ts:142`, and inline at `item-detail.page.ts:37`, `45`

`item.display_name ?? this.i18n.t('item.untitled')`. One `itemName(item, i18n)`
in `shared/models/item.model.ts`, or a pipe. Safe.

### S13. The stylist page re-implements the status cycle `pack-wait.ts` already solved

`frontend/src/app/features/stylist/stylist.page.ts:28-34`, `226-229`,
`268-278`, `418-441`

`packStatus(active)` (`pack-wait.ts:75-96`) does the same thing with
`effect`+`onCleanup`, and its comment at `70-74` says the guard the stylist page
still carries "is unreachable" in that form. Generalise to
`statusCycle(active, keys, intervalMs)` in `shared/`, and delete the stylist
page's `timer`, `statusIndex`, `startStatusCycle`, `stopStatusCycle`, its
`effect` and its `DestroyRef` line. Keep `STATUS_INTERVAL_MS` exported for the
spec. Safe.

### S14. The Atelier pill is written out at nine call sites

`login.page.ts:39-43`, `register.page.ts:33-34`, `profile.page.ts:43-44`,
`look-request-form.ts:159`, `trip-form.ts:393`, `trip-detail.page.ts:37-38`,
`trip-list.page.ts:22-23`, `saved-looks.page.ts:36-37`, `wardrobe.page.ts:259`;
plus `LABEL`/`FIELD` in `login.page.ts:28`, `36-37`, `register.page.ts:28`,
`30-31`, `profile.page.ts:36`, `40-41`; plus `ICON_BUTTON` in
`look-card.ts:46-47` and `saved-looks.page.ts:30-31`.

`trip-list.page.ts:10-16` records "the fourth instance"; 220 and 221 named the
third as the point to absorb it into `appButton`. Add `pill`, `ghostPill` and
`icon` variants to `shared/ui/button.ts` (or a sibling directive) and delete
the constants. Identical when the strings move verbatim. The largest change in
this list; timing is the developer's call.

### S15. A date utility lives in a stylist component file

`frontend/src/app/features/stylist/look-request-form.ts:45-49`
(`todayInLocalTime`); imported by `saved-looks.page.ts:11`,
`weather-strip.ts:9`, `trip-form.ts:17`

Three features import a helper from a fourth feature's component. Move it (with
`forecastHorizon`/`tripHorizon`) to `shared/`. Safe.

### S16. "Has a home location" four times

`weather-strip.ts:127-130` and `170`, `stylist.store.ts:105`,
`profile.page.ts:518`

`user !== null && user.home_lat !== null && user.home_lon !== null`. One
`hasHome(user)` in `user.model.ts`. Low.

### S17. Two non-null assertions that a different return type removes

`frontend/src/app/features/trips/trip-detail.page.ts:512-513`, `524`, `526`

`matches()` returns a boolean, so the callers need `swapping!` and `failure!`.
Return the matched value (`T | null`) instead and both `!` go. Minor.

### S18. Three spellings of "is this string in the vocabulary"

`look-card.ts:21-23` (`isCategory`), `saved-looks.page.ts:44-46`
(`isOccasion`), `wardrobe.page.ts:32-36` (`member`, already generic)

Export `member` from `enums.ts` as `isMember(value, vocabulary)`. Low.

### S19. Spec helpers copied across files

`function text(` in 20 frontend spec files, `element(` in 15, `item(` in 11,
`user(`/`look(`/`buttonWith(` in 5 each; on the backend `_item(` in 4.

The backend's tests never cross-import by policy. Whether the frontend specs
share that rule is not written down; if not, a `src/testing/` module removes
roughly a hundred near-identical functions. Listed, not recommended.

---

## Observations, no action

- `vision.py:264-279` / `stylist.py:417-432` (`_client`) and `vision.py:261` /
  `stylist.py:201` (`_CORRECTION`) are documented as deliberately independent.
- Twenty-six private backend names are imported by tests (`_hydrate`, `_trip`,
  `_swap_context`, `_client`, `_FAKE_TAGS`, …). Any rename in S1–S5 touches
  them.
- `MIN_WARDROBE_ITEMS` is defined in both `looks.py:83` (6) and `trips.py:116`
  (8) under one name; `trips.py` already has `MIN_SWAP_WARDROBE_ITEMS` at
  `131`, so `MIN_PACK_WARDROBE_ITEMS` would read better. Optional.

## Reviewed

- `backend/app/` — every module: main, core (config, deps, errors, logging,
  request_id, security, short_id), db, models, schemas, enums, all seven route
  modules, all nine services, both prompts.
- `backend/alembic/` — env and migrations 0001–0006.
- `backend/scripts/seed_demo.py`, `backend/tests/conftest.py`,
  `pyproject.toml`, `requirements.txt`, `.env.example`, `alembic.ini`.
- `frontend/src/` — every non-spec `.ts`, `app.html`, `index.html`,
  `styles.scss`, `tailwind.css`, environments; `public/i18n/en.json`;
  `angular.json`, `package.json`, the three tsconfigs, `eslint.config.js`,
  `.postcssrc.json`, `.vscode/`.
- `e2e/` — whole tree.
- Tooling on a mirror: ruff, mypy, eslint, tsc (unused checks), i18n sweep
  both directions, theme-token usage, dead-export scan, traversal probe.

# Conventions

## Git

### Human-only commits

**Claude Code must never execute a git command that writes to the repository.**
Forbidden: `commit`, `push`, `add`, `branch`, `checkout`, `switch`, `merge`, `rebase`, `reset`, `revert`, `tag`, `stash`, `cherry-pick`.

Read-only git commands are allowed and encouraged: `status`, `diff`, `log`, `show`.

At the end of every completed task, print the suggested commit message in a fenced code block and stop. The developer stages and commits by hand. This is not a safety measure — it is how the commit history stays something the author can explain line by line.

### Message format

Conventional commits, scoped:

```
feat(api): add trip packing endpoint
fix(web): stop polling after 3 minutes
refactor(api): drop the redundant db.refresh calls
test(e2e): cover tagging failure path
docs: record stage 2 evaluation results
chore(db): add trips migration
```

`refactor` was added before task 1.1, for the commit that removed the two redundant `db.refresh` calls. It is standard conventional-commits and this list simply did not carry it. `chore` was the closest available fit and would have been wrong: a change that alters what the code does — even by subtraction, and even with no change in observable behaviour — is not housekeeping. Adding a type once is cheaper than mislabelling commits for four stages. `DECISIONS.md` 040.

Scopes: `api` · `web` · `ai` · `db` · `auth` · `core` · `storage` · `weather` · `e2e` · `ci` · `docs`

A scope names the module a reader would grep for, not the deployable unit. `auth`, `core`, `storage` and `weather` were added at task 0.5 because four stage files already used them in their commit checkpoints and the list here did not — widening the list is one line, whereas narrowing it would mean renaming things inaccurately (`feat(db): closed vocabulary enums` is false; `enums.py` touches no database).

**Commits before task 0.5 predate this convention and are not retrofitted.** The first four commits on `main` use plain descriptive subjects with no type or scope. History is not rewritten on this project — see 017, which is the same reasoning applied to the same file. Conventional commits apply from task 0.5 onward, and the discontinuity in `git log` is expected rather than a mistake.

One commit per task in the stage files. Not one commit per stage — a stage-sized commit is unreviewable and unrevertable.

Branches: `stage-N-short-name`, merged to `main` when the stage's acceptance criteria pass and CI is green.

## Pinned majors, and what search results assume

**When a pinned library's installed major differs from the one nearly every example online assumes, say so at orientation, before any code is written.** Name the installed version, the shape the examples will use, and the shape this project uses.

The expected first symptom is always the same: *the method or file the tutorial reaches for does not exist.* It is a bad symptom because it reads as a broken install rather than as a version gap, and the obvious next move — searching the error — returns more material written against the same older major.

Two instances so far, both of which cost time before the rule existed:

- **Tailwind 4** at task 0.8. Almost all Tailwind material is v3-shaped: `tailwind.config.js`, `theme.extend`, `@apply` conventions. v4 is CSS-first and that config file does not exist at all. `DECISIONS.md` 056.
- **openai 2.x** at task 1.1. `client.chat.completions.parse` and `client.responses.parse` are top-level, while structured-outputs examples overwhelmingly use 1.x's `client.beta.chat.completions.parse`. `client.beta` still exists, which makes the older shape look current rather than superseded.

This is a rule about *disclosure*, not about version choice — 015, 018 and 054 already settled that this project runs current majors and accepts the cost. What it forbids is discovering the gap halfway through a task and treating it as an obstacle rather than as a known property of the pin.

## Python

- Python 3.14. `ruff` for lint and format, `mypy` in non-strict mode.
- Type hints on every function signature. Pydantic models for every request and response body.
- Services are plain functions with typed inputs and outputs. No business logic in route handlers — routes validate, call a service, and shape the response.
- No bare `except`. Catch the specific exception; log with context.
- **One carve-out, added at task 1.3: a function whose caller cannot report a failure ends with `except Exception`, after the specific types.** The worked example is `app/services/tagging.py`. An exception escaping a `BackgroundTask` is caught by nobody — the response has already been sent, so there is no handler and no envelope — and it leaves the row `processing` until a startup sweep up to ten minutes away. The rule's usual justification does not apply there: catching broadly normally hides a bug behind a generic message, whereas here narrowing the catch hides it behind a tile that spins forever. The shape is fixed: the predicted exceptions are caught by type and logged as warnings, the broad catch logs a **traceback**, because reaching it means the list above it is incomplete. `CancelledError` is a `BaseException` and is deliberately not swallowed by this. Written here rather than only at the use site because a carve-out that lives in one module gets either re-litigated or copied without its reason. `DECISIONS.md` 088.
- Never `print`. Use the configured logger.
- Secrets only from settings. No literal keys anywhere, including tests.
- Configuration fields on `Settings` are UPPER_SNAKE and match their environment variable names exactly. Values derived from them are lowercase properties.
- SQLAlchemy is synchronous — `Session`, not `AsyncSession`. `async def` is for HTTP clients (OpenAI, Open-Meteo), not for database work. A route that calls a **blocking** third-party library is a synchronous `def` for the same reason: FastAPI runs it in a threadpool, where a `def` handler occupies one slot, whereas the same call awaited inside an `async def` blocks the event loop for every request in the process. `POST /items/upload` is the worked example — `DECISIONS.md` 049.

```
snake_case      functions, variables, modules
PascalCase      classes, Pydantic models
UPPER_SNAKE     constants, enum members, settings fields
```

## TypeScript / Angular

- Standalone components. `OnPush` change detection everywhere.
- Signals for state. Observables only at the HTTP boundary.
- `inject()` rather than constructor injection.
- Named exports. No `default`.
- No `any`. If a type is genuinely unknown, use `unknown` and narrow it.
- No user-facing string hard-coded in a template. Every one goes through an i18n key.
- CSS logical properties only — `ms-4`, `me-2`, `text-start`. Never `left` or `right` for layout.

```
kebab-case      files: item-card.ts, wardrobe.page.ts
PascalCase      classes: ItemCard, WardrobeStore
camelCase       everything else
```

**One exception, added at task 0.8: a type that describes an API payload keeps the server's `snake_case`.** `User.display_name`, `Item.color_primary`, `Item.image_public_id` — the names arrive that way and are not renamed. `04-API-SPEC.md` is authoritative over the wire shape, and the alternative gives every field two names, so a network tab, a stack trace and a source file disagree about what it is called. The boundary is legible: if the name came from the server, it is the server's name; everything the frontend invents is `camelCase`. `DECISIONS.md` 059.

## Comments

Comment **why**, never **what**. Code that needs a comment to explain what it does should be rewritten instead.

```python
# Good — explains a decision that is not visible in the code
# Whole wardrobe goes to the model: filtering by season blocks valid
# cross-season looks, and 150 items is only ~4k tokens.

# Bad — restates the code
# Loop over the items
```

**A sentence that is true and about to stop being true is not a stale sentence.** Both instances turned up at task 1.1, pointing opposite ways, and both looked identical at a glance.

`app/db/base.py`'s comment described a `create_all` test fixture that cannot exist and never could. Genuinely stale; correcting it was right, and it had survived two tasks because 074 flagged the document and not the code.

`03-AI-CONTRACTS.md`'s "this schema has not yet been sent to the API" reads exactly as stale and was not. It was accurate right up to the moment the live call ran, and deleting it while writing the code that would eventually falsify it would have removed the only marker saying the contract was still unverified — replacing a true statement with an implied and false one.

The test is whether the sentence is false **now**, not whether it is about to be. Where a sentence is deliberately temporary, say what replaces it and when, so the next reader tidies it on purpose rather than by instinct. This applies to comments and to the documents alike; in this project the tidy has been the mistake more often than the comment has.

## Delivering code

Every file this agent produces is **written to disk**, and the delivery is a
printed `git --no-pager diff` over what it touched. The developer reviews what
landed rather than what was intended, then stages and commits by hand.
`DECISIONS.md` 117.

That is the whole rule. The review did not go away when the paste did — it moved
to the diff, and the standard is the one this project already applied to the tree
before every commit: **verify the tree, not the intent.** An unread diff is the
same failure an unpasted module was.

Alongside the diff, say what the file is responsible for, what it imports and
what will import it, and the two or three decisions inside it that could have
gone another way. Where a change spans several files, say how many. A file with
nothing worth saying about it is declared as such in one line rather than padded.

`DECISIONS.md` **017 is untouched and still in force**: the agent runs no git
command that writes, and the developer stages and commits by hand. That entry is
about commits and has never been about file delivery — see 117 for the citation
this section used to carry and why it did not hold.

Verification did not move either. Code is still built and run in a scratchpad
mirror first — lint, type-check, test — before it is written into the tree, and
the measured output is quoted rather than the behaviour asserted. What changed is
who types the file, not whether it was known-good before it arrived.

### Why the paste existed, and what it measured — history

Retired at task 1.9 and kept because the findings are real and the reasoning is
why the rule stood for nine tasks. **None of the measurements below is
withdrawn.** Two of the rules they justified are now moot and are marked as such;
they are not deleted, because a reader meeting a narrow comment in
`backend/app/` should be able to find out why it is narrow.

The rule was: prose files written to disk, Python modules under `backend/app/`
printed in a fenced block for the developer to paste, always, with no exception
for verified output. It existed because the developer reads the file on the way
past, and it had a measured cost.

- **The truncation, task 1.2a.** A line exceeding the display width could not be
  transferred by paste with confidence, and comments were where that failed
  silently. Code fails loudly — a truncated statement does not compile, an
  unbalanced paren is caught by lint, a printed line count catches a block that
  never landed. **A truncated comment leaves a working file whose reasoning has a
  hole in it and nothing reports it.** Six comment lines arrived cut at the same
  visual column and one three-line comment vanished entirely, in a file whose
  every statement was byte-correct.
- **The partial block, task 1.4.** On the `onupdate` line added to
  `app/models/item.py`, the code landed byte-correct and the five comment lines
  above it did not arrive at all. Three were 71–72 columns, over the limit,
  because the width pass that fixed `tagging.py` was never re-run over the
  smaller edits in the same delivery. The second half of that lesson was about
  the shape of a delivery rather than its width: a whole file printed once is
  checkable against a line count, and a change split into three blocks has no
  total to check — the block that goes missing is the one that compiles fine
  without it. **This is why a multi-file diff still says how many files it
  covers.**
- **The correction, task 1.2b.** The carve-out for prose was twice read as wider
  than it was. First as a bullet that, read literally, exempted every Python
  module in the project — every one of them contains comment prose. Then as
  licence to write `app/services/vision.py` to disk because it had been linted,
  type-checked and run in the mirror. Both were wrong on the rule's own terms,
  and the second is the one worth carrying forward: **"verified" was never a
  licence.** A module that is green has satisfied nothing that a review pass was
  asking for. That argument survives the retirement intact — it is now an
  argument about reading the diff.
- **Moot: the 66-column width rule.** Comment lines in printed code were kept
  inside the narrowest pane the developer read in; the measured truncation point
  at 1.2a was 66 columns and the comments that failed were written to 80. Nothing
  is retyped now, so nothing can arrive cut. The number was a property of one
  pane on one day in any case. Comments already written narrow stay as they are;
  there is no reason to widen them and no reason to keep the constraint.
- **Moot: "printed code is read back out of the verified mirror, never
  retyped."** Its purpose was to stop a retyped block reintroducing the errors
  the mirror existed to remove — at 1.2a a retyped block lost two closing parens.
  Files are copied from the mirror into the tree now, so the failure has no route
  in. The mirror itself is not moot: see above.

### The argument that generalised

**Task 1.5 moved `frontend/` to write-to-disk and this is the sentence that did
it:** a `git diff` review answers the thing the paste was for — the developer
reading the file on the way past — and is *immune* to the thing the width rule
was for, because **a diff is not retyped, so no line can arrive cut at column
66.** That was written as a justification for one directory. It was always an
argument about the medium rather than about the directory, and at 1.9 it becomes
the argument for the whole project.

What the paste gave up in exchange is real and is not recovered: the enforced
slowness of typing a module out, on a file whose every line is a judgement call.
The diff is faster to skim than a paste is to type, and skimming it is the
failure mode this section now guards against rather than truncation.

## Error handling

Backend returns `{ "detail": str, "code": str }`. Codes are stable strings the frontend can branch on: `wardrobe_too_small`, `trip_too_long`, `stylist_failed`, `forecast_unavailable`, `geocoding_unavailable`, `home_location_missing`, `anchor_unavailable`, `locked_unavailable`, `rate_limited`, `item_edited`, `email_exists`, `invalid_credentials`, `invalid_token`, `validation_error`, `unsupported_file_type`, `file_too_large`, `not_found`, `upload_failed`.

**`trip_too_long` (`400`) was added at task 4.3 and its producer is task 4.4**, `POST /trips/pack`, when `end_date` is later than `today + 14`. The message is *"Trips can span at most 14 days from today."* — it names the bound and the day it is counted from, because `DECISIONS.md` 190 put the bound on the trip's **last** day rather than its first and a message saying only "at most 14 days" would describe a rule this API does not enforce. It sits beside `wardrobe_too_small` because they are the same kind of refusal: both are answerable from the request alone, before the geocoder, the forecast or the model costs anything.

**A code written one task before the endpoint that raises it is a deliberate exception, and the precedent cuts the other way.** `tagging_failed` was struck at 1.4 on the rule that a code with no producer invites a frontend branch that can never be taken — and it had no producer *possible*, since a tagging failure is a column and a tile rather than an envelope. This one has a named owner one task away and a written status, message and trigger, which is the difference between staging and a dead string. Two things follow that a reader should not have to infer. Until 4.4 lands, nothing in the codebase emits it and no frontend branch should exist for it. And after 4.4 it is a `400` that a **correct client cannot provoke**: `DECISIONS.md` 190 caps the date picker at the same bound, so the only thing that exercises this code is its own test — `replace_role`-without-locks' shape (`DECISIONS.md` 177), and the day the picker breaks is the day this code stops being tested by anything a user does.

**`anchor_unavailable` (`422`) was added at task 2.10**, for `POST /looks/suggest` when `anchor_item_id` names nothing in the wardrobe that would actually be sent — another account's item, or one this account owns that is not styleable: still `processing` or `failed`, archived, or in an excluded category. `04-API-SPEC.md` asks for a `422` when the anchor "does not belong to this user", and this is that check widened by one step on `wardrobe_too_small`'s reasoning: a garment the stylist is never shown cannot appear in a look, so letting it through buys two model calls and a `502` for a question one lookup answers before anything leaves the process. It is a separate code from `validation_error` because it is the one `422` on this endpoint a correct client can provoke — the user tapped "Style around this" on a real garment — so it is the one the client has a sentence for beyond *check the occasion and the date*.

**`locked_unavailable` (`422`) was added at task 2.11**, for `POST /looks/suggest` when any id in `locked_item_ids` names nothing in the wardrobe that would actually be sent — `anchor_unavailable`'s check and `anchor_unavailable`'s widening, three fields along. It is the second `422` on this endpoint a correct client can provoke, and that is what earns it a code: the ↻ badge locks the garments that were on screen a moment ago, one of which can have been archived from another tab since, and `validation_error`'s "check the occasion and the date" is about a request the user never made. The neighbouring `422` — `replace_role` sent with nothing locked — is deliberately **not** given a code: no correct client can build that body, so it stays the request schema's own `validation_error`. An `exclude_item_ids` entry that resolves to no row is dropped rather than refused, because an item the stylist is never shown is already absent from every look it can build. `DECISIONS.md` 177.

**`home_location_missing` (`400`) was added at task 2.7**, for `POST /looks/suggest` on an account whose `home_lat`/`home_lon` are `NULL`. The endpoint takes no coordinates — the forecast is for the user's home location — so an account that has never set one cannot be given a look at all. Reusing `forecast_unavailable` was rejected on `geocoding_unavailable`'s reasoning one task earlier: the two conditions say different things to a user, and only one of them is fixed on the profile screen. `AUDITS.md` **O-20** is why this is reachable rather than theoretical — the seeded demo row on the live database still has no home location. `DECISIONS.md` 173.

**`item_edited` replaced `tagging_failed` at task 1.4, and the swap is two separate findings.** `item_edited` (`409`) is `POST /items/{id}/retag` refusing to overwrite a hand-corrected item — `04-API-SPEC.md` had specified that `409` since Stage 0 as the only failure in the whole document with no code beside it. `tagging_failed` was struck because **nothing produced it and nothing could**: a tagging failure is written to `items.error_message` and rendered as a tile, never as an error envelope, which task 1.3 confirmed from the other end when it wrote three distinct `error_message` texts and no envelope anywhere. The alternative was to assign it to a synchronous retag, which would contradict retag answering `202` and which no document asks for. A code with no producer is worse than a missing one: it invites a frontend branch that can never be taken. Found by the 2026-08-18 audit as O-1.

**`geocoding_unavailable` (`502`) was added at task 2.2**, for `GET /me/locations/search` when Open-Meteo's geocoder does not answer. It is a separate code from `forecast_unavailable` rather than a reuse of it because the two endpoints fail independently and say different things to a user: one means *we cannot look up that place*, the other means *we have no weather for that day*. The alternative — widening `forecast_unavailable` to mean "an Open-Meteo call failed" — would name the vendor rather than the condition, which is the opposite of what every other code in this list does. `DECISIONS.md` 152.

The last four were added at task 0.6. `unsupported_file_type` (`415`) and `file_too_large` (`413`) are STAGE-0's upload rejections; `not_found` (`404`) is the cross-user isolation answer `06-TESTING-STRATEGY.md` requires, and is deliberately one code for every resource rather than one per resource; `upload_failed` (`502`) covers any failure to store an image and closes a gap no document had noticed — without it a Cloudinary outage produced an unhandled `500` with no `code` at all. See `DECISIONS.md` 043.

Services do not raise `ApiError`. They raise their own exceptions and the route maps them, so that a service is still callable from a script with no request in flight — `DECISIONS.md` 044, following the same reasoning as 036.

Two keys, on every error the application raises and on FastAPI's own `422` — the machinery is `app/core/errors.py`, built at task 0.5. Routing-level failures raised before our code runs are the documented exception: a `404` on an unknown path and a `405` on the wrong method carry `detail` only. `HTTPException` alone does not produce this shape and `RequestValidationError` produces a `detail` that is a list; both are normalised by handlers. Where an error concerns a specific field, the field is named inside `detail`, never as a third key. See `DECISIONS.md` 033.

The frontend never renders a raw error. Every failure path has a written message and, where recovery is possible, an action.

## Limits and units

A limit expressed in MB means **mebibytes** — 1024², not 1000². `MAX_UPLOAD_MB=10` is 10,485,760 bytes. The backend reads it from `settings.max_upload_bytes`; the frontend mirrors the same arithmetic in the upload sheet at task 1.6. Written down because the two definitions differ by 5% and the failure mode is a file the browser accepts and the API rejects.

**Amended at task 0.8 — "both sides read it from one place" was not true and should not have been written.** `MAX_UPLOAD_MB` and `MAX_FILES_PER_REQUEST` are environment variables read by pydantic-settings at process start; a browser cannot read them, and no endpoint publishes them. What the frontend has is a **hand-written copy that can drift silently**, and the drift is invisible until a user picks a file the sheet accepts and the API answers with `413`. Nothing detects it — there is no test that can compare a Python setting against a TypeScript constant. This is the same shape of overstatement as the original `DECISIONS.md` 008 ("bounded by a 10 MB limit"), corrected on the same terms: the arithmetic is stated in one place *in prose*, and honoured in two places *in code*. If it ever matters enough to fix, the fix is an endpoint that returns the limits, not a build step.

Where a limit is counted in a unit other than the one a user would count in, the error message names the unit — `DECISIONS.md` 036 is the worked example, with a minimum in characters and a maximum in bytes.

**Third instance, at task 1.6, and the first one a test catches.** `upload-sheet.ts` mirrors `MAX_FILES_PER_REQUEST` (20) and `max_upload_bytes` (10 mebibytes) from `app/core/config.py`, with the same accepted cost as the two below — two hand-written copies and nothing comparing them. What is different is one measurement: a mutation run at 1.6 changed the component's arithmetic to 1000² and **all 155 tests stayed green**, because every size expectation in the spec read the component's own constant. The number is now transcribed as a literal (`10_485_760`) from the sentence above, and one test pins the constant to it. That does not detect drift from the *Python* setting — nothing can — but it does detect the mebibyte/megabyte error, which is the specific failure this section exists to name.

**Fourth instance, at task 2.2, and it is the first one that is not a copy at all.** `height_cm` is bounded by `CHECK (height_cm BETWEEN 120 AND 230)` in `02-DATA-MODEL.md` and in the column, and `PATCH /me` has to refuse an out-of-range height before Postgres does — an `IntegrityError` reaching a client is a `500` with no `code`. Rather than transcribe `120` and `230` into the schema, the two numbers moved into `app/models/user.py` as `MIN_HEIGHT_CM` and `MAX_HEIGHT_CM`, the `CheckConstraint` is built from them, and `UserUpdate` imports them. **One definition, honoured in two places, with the compiler between them** — which is what the three instances below could not have, because a Python setting and a TypeScript constant cannot import each other. Where both sides are Python, drift is a choice rather than a fact of life. The literal that still exists is migration `0001`'s, which is frozen by design.

**Second instance, at task 0.9.** `register.page.ts` mirrors both password rules: `MIN_PASSWORD_LENGTH` from `app/schemas/auth.py` and `MAX_PASSWORD_BYTES` from `app/core/security.py`, the second enforced with `TextEncoder` so the count is bytes rather than characters. Same shape as the upload limits above and the same accepted cost — two hand-written copies, nothing comparing them, and the drift invisible until a user is rejected by a rule the form allowed. The message names bytes. `DECISIONS.md` 070.

## Tests

- `tests/unit/`, `tests/integration/`, `tests/fixtures/`
- Names describe behaviour: `test_rejects_subcategory_from_wrong_category`, not `test_validation_2`
- One assertion concept per test
- No test may call OpenAI unless marked `@pytest.mark.eval`
- No `waitForTimeout` in Playwright, ever
- The backend suite runs against `TEST_DATABASE_URL` and refuses to start without it, or if it equals `DATABASE_URL` (`DECISIONS.md` 073)
- **The `alembic` CLI is not covered by that guard, and it targets the developer's database.** `alembic/env.py` reads `settings.DATABASE_URL`, so `alembic upgrade head` typed into a shell migrates whatever `.env` names as `DATABASE_URL` — the dev database, not the test one. `tests/conftest.py` protects only the **in-process** path: it copies `TEST_DATABASE_URL` into `os.environ["DATABASE_URL"]` before `app.core.config` is imported and asserts the result, so the `command.upgrade` pytest runs is safe and the CLI is not. Override it inline per command — `env DATABASE_URL="$TEST_DATABASE_URL" alembic …` — and never with `export`, because a shell where the two are equal is a shell where `conftest.py` refuses to start. The cheapest way to exercise a new migration is to run pytest, which migrates to head itself. Found at task 4.1
- **No test hard-codes a value that a `UNIQUE` constraint covers.** Planted `short_id`s come from `generate_short_id()`. A literal survives any run that fails to roll back and leaves the suite permanently red until someone truncates the table by hand — which is not hypothetical, it happened at 0.10

**Before claiming a test defends a behaviour, delete the behaviour and run the suite.** A named test must fail. This is the practice `06-TESTING-STRATEGY.md` established at task 0.9 and applied to the backend at 0.10, where twelve of thirteen mutations were caught and the thirteenth proved a line of application code was redundant. Mutations are run from a pristine copy with a green baseline verified on both ends — a harness that leaves a mutation behind produces a table that reads as evidence and is not.

## Definition of done

A task is done when the code works, has tests, passes lint and type checks, and the relevant document is updated in the same commit. A stage is done when every acceptance criterion in its file passes and `PROGRESS.md` reflects it.

**An artifact that has to outlive the task that produced it is written to disk in that task's commit. A conversation is not storage.** If a finding is worth revisiting, it is worth a file; if it is not worth a file, say so and drop it rather than parking it. Added at task 1.2a, from an instance that demonstrated its own lesson: a list of documentation candidates produced at 1.1 was kept "for its own session" in a conversation with an agent that starts every session holding nothing but the tree, and it did not survive the session boundary. The rule is cheap to honour — a file, a date, the exact command, and what the artifact is known **not** to cover — and the last of those is the part with a shelf life, because an audit whose known holes are not written beside it reads as a clean bill of health.

Where a task's tests depend on scaffolding that a **later** task owns, that task ships the tests it can run unaided and the stage file names the task that completes the coverage. Task 0.5 is the worked example: `security.py` is pure and is unit-tested on delivery, while the register, login and `/auth/me` route tests wait for the `conftest.py` and test-database fixture that task 0.10 owns. This is a deferral with a named owner, not an exemption — a task may not simply declare itself untestable.

Task 0.7 is the second instance, and it shows how far "unaided" reaches. Its rejection paths need no database at all, so they are tested on delivery by overriding `get_db` with a stub that raises when *used* — which turns the absence of the fixture into the assertion, since a route that never touches the session provably rejected the request before it could. Only the row-writing half waits for 0.10.

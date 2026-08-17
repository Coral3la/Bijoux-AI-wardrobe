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

## Delivering code, and what a paste cannot carry

Code on this project is printed by the agent and pasted by the developer (`DECISIONS.md` 017). That transfer has a measured limit, found at task 1.2a: **a line that exceeds the display width cannot be transferred by paste with confidence, and comments are where that fails silently.**

Code fails loudly. A truncated statement does not compile, an unbalanced paren is caught by the next lint run, and a printed line count catches a block that never landed. **A truncated comment leaves a working file whose reasoning has a hole in it, and nothing anywhere reports that** — the file imports, the suite is green, and the sentence explaining why a line exists simply stops mid-word. At 1.2a six comment lines arrived cut at the same visual column and one three-line comment vanished entirely, in a file whose every statement was byte-correct.

So:

- **A file whose delivery includes comment prose is written to disk by the agent.** Only its statements are printed for review. This costs nothing the printing rule was protecting: the developer reads the structure by pasting the code, and reads the reasoning in the explanation above the block, never by pasting the comments.
- **Where a whole file is printed anyway, comment lines stay inside the narrowest pane the developer reads in.** The measured truncation point at 1.2a was **66 columns**; the comments that failed were written to 80. That number is a property of one pane on one day and will not survive a font change, which is the real argument for the rule above it — re-measure before trusting it, and prefer writing to disk.
- **Printed code is read back out of the verified mirror, never retyped.** The mirror is where it was linted, type-checked and run (`verify before printing`), so retyping it into a message reintroduces exactly the class of error the mirror exists to remove. At 1.2a a retyped block lost two closing parens and would not have compiled.

## Error handling

Backend returns `{ "detail": str, "code": str }`. Codes are stable strings the frontend can branch on: `wardrobe_too_small`, `stylist_failed`, `forecast_unavailable`, `rate_limited`, `tagging_failed`, `email_exists`, `invalid_credentials`, `invalid_token`, `validation_error`, `unsupported_file_type`, `file_too_large`, `not_found`, `upload_failed`.

The last four were added at task 0.6. `unsupported_file_type` (`415`) and `file_too_large` (`413`) are STAGE-0's upload rejections; `not_found` (`404`) is the cross-user isolation answer `06-TESTING-STRATEGY.md` requires, and is deliberately one code for every resource rather than one per resource; `upload_failed` (`502`) covers any failure to store an image and closes a gap no document had noticed — without it a Cloudinary outage produced an unhandled `500` with no `code` at all. See `DECISIONS.md` 043.

Services do not raise `ApiError`. They raise their own exceptions and the route maps them, so that a service is still callable from a script with no request in flight — `DECISIONS.md` 044, following the same reasoning as 036.

Two keys, on every error the application raises and on FastAPI's own `422` — the machinery is `app/core/errors.py`, built at task 0.5. Routing-level failures raised before our code runs are the documented exception: a `404` on an unknown path and a `405` on the wrong method carry `detail` only. `HTTPException` alone does not produce this shape and `RequestValidationError` produces a `detail` that is a list; both are normalised by handlers. Where an error concerns a specific field, the field is named inside `detail`, never as a third key. See `DECISIONS.md` 033.

The frontend never renders a raw error. Every failure path has a written message and, where recovery is possible, an action.

## Limits and units

A limit expressed in MB means **mebibytes** — 1024², not 1000². `MAX_UPLOAD_MB=10` is 10,485,760 bytes. The backend reads it from `settings.max_upload_bytes`; the frontend mirrors the same arithmetic in the upload sheet at task 1.6. Written down because the two definitions differ by 5% and the failure mode is a file the browser accepts and the API rejects.

**Amended at task 0.8 — "both sides read it from one place" was not true and should not have been written.** `MAX_UPLOAD_MB` and `MAX_FILES_PER_REQUEST` are environment variables read by pydantic-settings at process start; a browser cannot read them, and no endpoint publishes them. What the frontend has is a **hand-written copy that can drift silently**, and the drift is invisible until a user picks a file the sheet accepts and the API answers with `413`. Nothing detects it — there is no test that can compare a Python setting against a TypeScript constant. This is the same shape of overstatement as the original `DECISIONS.md` 008 ("bounded by a 10 MB limit"), corrected on the same terms: the arithmetic is stated in one place *in prose*, and honoured in two places *in code*. If it ever matters enough to fix, the fix is an endpoint that returns the limits, not a build step.

Where a limit is counted in a unit other than the one a user would count in, the error message names the unit — `DECISIONS.md` 036 is the worked example, with a minimum in characters and a maximum in bytes.

**Second instance, at task 0.9.** `register.page.ts` mirrors both password rules: `MIN_PASSWORD_LENGTH` from `app/schemas/auth.py` and `MAX_PASSWORD_BYTES` from `app/core/security.py`, the second enforced with `TextEncoder` so the count is bytes rather than characters. Same shape as the upload limits above and the same accepted cost — two hand-written copies, nothing comparing them, and the drift invisible until a user is rejected by a rule the form allowed. The message names bytes. `DECISIONS.md` 070.

## Tests

- `tests/unit/`, `tests/integration/`, `tests/fixtures/`
- Names describe behaviour: `test_rejects_subcategory_from_wrong_category`, not `test_validation_2`
- One assertion concept per test
- No test may call OpenAI unless marked `@pytest.mark.eval`
- No `waitForTimeout` in Playwright, ever
- The backend suite runs against `TEST_DATABASE_URL` and refuses to start without it, or if it equals `DATABASE_URL` (`DECISIONS.md` 073)
- **No test hard-codes a value that a `UNIQUE` constraint covers.** Planted `short_id`s come from `generate_short_id()`. A literal survives any run that fails to roll back and leaves the suite permanently red until someone truncates the table by hand — which is not hypothetical, it happened at 0.10

**Before claiming a test defends a behaviour, delete the behaviour and run the suite.** A named test must fail. This is the practice `06-TESTING-STRATEGY.md` established at task 0.9 and applied to the backend at 0.10, where twelve of thirteen mutations were caught and the thirteenth proved a line of application code was redundant. Mutations are run from a pristine copy with a green baseline verified on both ends — a harness that leaves a mutation behind produces a table that reads as evidence and is not.

## Definition of done

A task is done when the code works, has tests, passes lint and type checks, and the relevant document is updated in the same commit. A stage is done when every acceptance criterion in its file passes and `PROGRESS.md` reflects it.

**An artifact that has to outlive the task that produced it is written to disk in that task's commit. A conversation is not storage.** If a finding is worth revisiting, it is worth a file; if it is not worth a file, say so and drop it rather than parking it. Added at task 1.2a, from an instance that demonstrated its own lesson: a list of documentation candidates produced at 1.1 was kept "for its own session" in a conversation with an agent that starts every session holding nothing but the tree, and it did not survive the session boundary. The rule is cheap to honour — a file, a date, the exact command, and what the artifact is known **not** to cover — and the last of those is the part with a shelf life, because an audit whose known holes are not written beside it reads as a clean bill of health.

Where a task's tests depend on scaffolding that a **later** task owns, that task ships the tests it can run unaided and the stage file names the task that completes the coverage. Task 0.5 is the worked example: `security.py` is pure and is unit-tested on delivery, while the register, login and `/auth/me` route tests wait for the `conftest.py` and test-database fixture that task 0.10 owns. This is a deferral with a named owner, not an exemption — a task may not simply declare itself untestable.

Task 0.7 is the second instance, and it shows how far "unaided" reaches. Its rejection paths need no database at all, so they are tested on delivery by overriding `get_db` with a stub that raises when *used* — which turns the absence of the fixture into the assertion, since a route that never touches the session provably rejected the request before it could. Only the row-writing half waits for 0.10.

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
test(e2e): cover tagging failure path
docs: record stage 2 evaluation results
chore(db): add trips migration
```

Scopes: `api` · `web` · `ai` · `db` · `auth` · `core` · `storage` · `weather` · `e2e` · `ci` · `docs`

A scope names the module a reader would grep for, not the deployable unit. `auth`, `core`, `storage` and `weather` were added at task 0.5 because four stage files already used them in their commit checkpoints and the list here did not — widening the list is one line, whereas narrowing it would mean renaming things inaccurately (`feat(db): closed vocabulary enums` is false; `enums.py` touches no database).

**Commits before task 0.5 predate this convention and are not retrofitted.** The first four commits on `main` use plain descriptive subjects with no type or scope. History is not rewritten on this project — see 017, which is the same reasoning applied to the same file. Conventional commits apply from task 0.5 onward, and the discontinuity in `git log` is expected rather than a mistake.

One commit per task in the stage files. Not one commit per stage — a stage-sized commit is unreviewable and unrevertable.

Branches: `stage-N-short-name`, merged to `main` when the stage's acceptance criteria pass and CI is green.

## Python

- Python 3.14. `ruff` for lint and format, `mypy` in non-strict mode.
- Type hints on every function signature. Pydantic models for every request and response body.
- Services are plain functions with typed inputs and outputs. No business logic in route handlers — routes validate, call a service, and shape the response.
- No bare `except`. Catch the specific exception; log with context.
- Never `print`. Use the configured logger.
- Secrets only from settings. No literal keys anywhere, including tests.
- Configuration fields on `Settings` are UPPER_SNAKE and match their environment variable names exactly. Values derived from them are lowercase properties.
- SQLAlchemy is synchronous — `Session`, not `AsyncSession`. `async def` is for HTTP clients (OpenAI, Open-Meteo), not for database work.

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

## Comments

Comment **why**, never **what**. Code that needs a comment to explain what it does should be rewritten instead.

```python
# Good — explains a decision that is not visible in the code
# Whole wardrobe goes to the model: filtering by season blocks valid
# cross-season looks, and 150 items is only ~4k tokens.

# Bad — restates the code
# Loop over the items
```

## Error handling

Backend returns `{ "detail": str, "code": str }`. Codes are stable strings the frontend can branch on: `wardrobe_too_small`, `stylist_failed`, `forecast_unavailable`, `rate_limited`, `tagging_failed`, `email_exists`, `invalid_credentials`, `invalid_token`, `validation_error`, `unsupported_file_type`, `file_too_large`, `not_found`, `upload_failed`.

The last four were added at task 0.6. `unsupported_file_type` (`415`) and `file_too_large` (`413`) are STAGE-0's upload rejections; `not_found` (`404`) is the cross-user isolation answer `06-TESTING-STRATEGY.md` requires, and is deliberately one code for every resource rather than one per resource; `upload_failed` (`502`) covers any failure to store an image and closes a gap no document had noticed — without it a Cloudinary outage produced an unhandled `500` with no `code` at all. See `DECISIONS.md` 043.

Services do not raise `ApiError`. They raise their own exceptions and the route maps them, so that a service is still callable from a script with no request in flight — `DECISIONS.md` 044, following the same reasoning as 036.

Two keys, on every error the application raises and on FastAPI's own `422` — the machinery is `app/core/errors.py`, built at task 0.5. Routing-level failures raised before our code runs are the documented exception: a `404` on an unknown path and a `405` on the wrong method carry `detail` only. `HTTPException` alone does not produce this shape and `RequestValidationError` produces a `detail` that is a list; both are normalised by handlers. Where an error concerns a specific field, the field is named inside `detail`, never as a third key. See `DECISIONS.md` 033.

The frontend never renders a raw error. Every failure path has a written message and, where recovery is possible, an action.

## Limits and units

A limit expressed in MB means **mebibytes** — 1024², not 1000². `MAX_UPLOAD_MB=10` is 10,485,760 bytes, and both sides read it from one place: the backend from `settings.max_upload_bytes`, the frontend mirroring the same arithmetic in the upload sheet at task 1.6. Written down because the two definitions differ by 5% and the failure mode is a file the browser accepts and the API rejects.

Where a limit is counted in a unit other than the one a user would count in, the error message names the unit — `DECISIONS.md` 036 is the worked example, with a minimum in characters and a maximum in bytes.

## Tests

- `tests/unit/`, `tests/integration/`, `tests/fixtures/`
- Names describe behaviour: `test_rejects_subcategory_from_wrong_category`, not `test_validation_2`
- One assertion concept per test
- No test may call OpenAI unless marked `@pytest.mark.eval`
- No `waitForTimeout` in Playwright, ever

## Definition of done

A task is done when the code works, has tests, passes lint and type checks, and the relevant document is updated in the same commit. A stage is done when every acceptance criterion in its file passes and `PROGRESS.md` reflects it.

Where a task's tests depend on scaffolding that a **later** task owns, that task ships the tests it can run unaided and the stage file names the task that completes the coverage. Task 0.5 is the worked example: `security.py` is pure and is unit-tested on delivery, while the register, login and `/auth/me` route tests wait for the `conftest.py` and test-database fixture that task 0.10 owns. This is a deferral with a named owner, not an exemption — a task may not simply declare itself untestable.

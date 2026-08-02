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

Scopes: `api` · `web` · `ai` · `db` · `e2e` · `ci` · `docs`

One commit per task in the stage files. Not one commit per stage — a stage-sized commit is unreviewable and unrevertable.

Branches: `stage-N-short-name`, merged to `main` when the stage's acceptance criteria pass and CI is green.

## Python

- Python 3.12. `ruff` for lint and format, `mypy` in non-strict mode.
- Type hints on every function signature. Pydantic models for every request and response body.
- Services are plain functions with typed inputs and outputs. No business logic in route handlers — routes validate, call a service, and shape the response.
- No bare `except`. Catch the specific exception; log with context.
- Never `print`. Use the configured logger.
- Secrets only from settings. No literal keys anywhere, including tests.

```
snake_case      functions, variables, modules
PascalCase      classes, Pydantic models
UPPER_SNAKE     constants and enum members
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

Backend returns `{ "detail": str, "code": str }`. Codes are stable strings the frontend can branch on: `wardrobe_too_small`, `stylist_failed`, `forecast_unavailable`, `rate_limited`, `tagging_failed`.

The frontend never renders a raw error. Every failure path has a written message and, where recovery is possible, an action.

## Tests

- `tests/unit/`, `tests/integration/`, `tests/fixtures/`
- Names describe behaviour: `test_rejects_subcategory_from_wrong_category`, not `test_validation_2`
- One assertion concept per test
- No test may call OpenAI unless marked `@pytest.mark.eval`
- No `waitForTimeout` in Playwright, ever

## Definition of done

A task is done when the code works, has tests, passes lint and type checks, and the relevant document is updated in the same commit. A stage is done when every acceptance criterion in its file passes and `PROGRESS.md` reflects it.

# Stage 5 — QA, CI and Deployment

**Week 6. Target: 5 days.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

A deployed, publicly reachable application with a Playwright suite that runs green in CI without spending a cent on OpenAI, and documented evidence that the AI layer performs to a measured standard.

For a submission aimed at QA automation roles, **this stage carries more weight in an interview than any additional feature would.**

## Prerequisites

Stages 0, 1, 2 and 4 complete. Stage 3 complete or explicitly cut.

---

## Tasks, in order

### 5.1 Freeze the AI fixtures
Capture real responses from the live API — vision tags for 10 varied garments, one single-day stylist response, one 4-day trip response, and one deliberately failing tagging response. Commit them under `backend/tests/fixtures/ai/`.

Recorded, not hand-written. Hand-written fixtures drift from what the model actually returns and quietly stop testing reality.

Wire `USE_FAKE_AI=true` to serve them deterministically, keyed by input.

### 5.2 Backend test suite to target
Fill the gaps from `06-TESTING-STRATEGY.md`:
- unit: weather rules, serialiser, enums, `short_id`, both validators
- contract: schema enums match database enums
- integration: upload returns before tagging, background transition, failure path, hallucination guard, cross-user isolation on every endpoint, `user_edited` protection, `wardrobe_too_small`, rate limits

Coverage target ≥ 75% on `app/services` and `app/api`. Report it; do not chase 100%.

**Four `GET /items` behaviours this task would otherwise have covered were reassigned into Stage 1**, to the task that first depends on each: the `include_archived` exclusion to **1.4**; `limit`'s default and cap to **1.5**; the `status` filter and the `created_at DESC, short_id` ordering to **1.7**. The `status` filter's *test* is written at 1.4's start, ahead of the two frontend tasks that lean on it, but the behaviour belongs to 1.7 — this line said 1.4 owned it until task 1.7, where `STAGE-1` said otherwise and won, being the document carrying the argument. All four shipped at 0.7 and were undefended at 0.10. They moved because each one fails in a way that presents as something else — a polling loop that never empties, a grid that reorders itself, a `DELETE` that appears to do nothing, a filter bar counting over the first hundred items — and none of those is worth four stages of exposure. Do not go looking for them here.

### 5.3 Playwright suite
`e2e/` with Page Object Model. All 11 journeys from `06-TESTING-STRATEGY.md`.

Locators: `getByRole` and `getByLabel` first, `data-testid` only where the accessible name is genuinely ambiguous. Rely on Playwright's auto-waiting; no `waitForTimeout` anywhere in the suite.

Include the failure journey — a tagging failure producing a warning tile with a working retry. Error paths are where a QA-oriented submission separates itself.

**Two things owed here from task 0.9, both because no other layer can prove them.** First: **assert that `novalidate` is still on the auth forms**, by submitting an invalid email and checking that *our* message renders rather than the browser's bubble. The unit suite cannot catch its removal — its submissions bypass constraint validation, and adding a native `required` leaves the whole suite green. Second: one journey must type an invalid value into a form and assert the validation message renders with nothing programmatic in the loop. The component specs cannot prove this: they call `fixture.whenStable()`, which forces change detection, where zoneless Angular re-renders only when the view is marked dirty. Playwright is the only layer that cannot cheat, and this is the last live doubt from 0.9 rather than a new requirement — see `06-TESTING-STRATEGY.md` and `DECISIONS.md` 070.

### 5.4 Document known bugs honestly
Any real defect found and not fixed gets a `test.fail()` test with a comment naming expected versus actual behaviour, and a line in `docs/KNOWN-ISSUES.md`.

A suite that records a known bug reads as more mature than one that hides it. This was the right call on the Playwright assignment and it is the right call here.

**Three limitations found in earlier stages are assigned here rather than left to be rediscovered.** Each needs either a fix or a `KNOWN-ISSUES.md` entry, and the decision is this task's:

- **Unknown query parameters are silently ignored.** `?colour_primary=navy` returns `200` unfiltered. `DECISIONS.md` 039 forbids this for request bodies and query strings have no equivalent of `extra="forbid"`, so the guarantee stops at the body. The fix is middleware rejecting query keys a route did not declare (`DECISIONS.md` 051).
- **A failed upload batch strands assets in Cloudinary.** They are logged, never deleted, and reconciling them is a manual directory listing per user (`DECISIONS.md` 053).
- **`GET /items` returns a bare `500` if `CLOUDINARY_CLOUD_NAME` is unset**, because `build_url` raises during serialisation and `/health` does not check Cloudinary (`DECISIONS.md` 050).

### 5.5 CI
`.github/workflows/ci.yml` per `07-DEPLOYMENT.md`. Three jobs: backend, frontend, e2e. Playwright HTML report and traces uploaded as artefacts. `eval`-marked tests excluded. No OpenAI key present anywhere in CI.

Branch protection on `main` requiring CI to pass.

### 5.6 Deploy
Neon migrated, Render service live with a health check, Vercel build pointed at it, CORS configured, demo account seeded on the production database.

Run the full manual path against production once, on a phone, on mobile data. Desktop-only testing hides real problems on the device this app is actually for.

### 5.7 Final evaluation run
Run the `eval` suite against production settings. Record in `docs/eval-results.md`:
- vision accuracy per field, against the golden dataset
- weather rule compliance across 10 runs at each of 4 temperatures
- structural validity rate across 20 stylist calls
- packing reuse ratios at 3, 5 and 7 days

Include the earlier numbers from Stage 1 alongside the final ones. **The improvement curve is the artefact** — it demonstrates measurement and iteration rather than assertion.

### 5.8 Project README
Rewrite the root README for a reader who has never seen the project: what it does, a screenshot or GIF of the packing flow, the stack, architecture diagram, how to run it, testing approach, evaluation results, known issues, and what you would do next.

This is what a recruiter opens first. Give it real time.

---

## Acceptance criteria

- [ ] CI green on `main`, no OpenAI key configured in the repository
- [ ] All 11 Playwright journeys pass locally and in CI
- [ ] Backend coverage ≥ 75% on services and API
- [ ] The app is reachable at a public URL and works on a phone over mobile data
- [ ] The demo account works on production
- [ ] `eval-results.md` contains real numbers with dates and prompt versions
- [ ] `KNOWN-ISSUES.md` exists and is honest
- [ ] The root README would let a stranger run the project

## Commit checkpoints

`test: record ai fixtures` · `test: backend suite to target` · `test(e2e): page objects` · `test(e2e): user journeys` · `docs: known issues` · `ci: github actions pipeline` · `chore: production deployment` · `docs: evaluation results` · `docs: project readme`

## Pre-defence

Work through the checklist at the end of `07-DEPLOYMENT.md`. Two items are easy to skip and expensive to have skipped: **warm the backend before the demo**, and **record a video backup of the full path**.

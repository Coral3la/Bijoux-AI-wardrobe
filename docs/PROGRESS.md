# Progress

**Current stage:** Stage 1 — Wardrobe
**Status:** Stage 1 in progress — 1.1 complete.

Claude Code updates this file at the end of every stage: tick the criteria, set the next stage, and note anything that changed relative to the plan.

---

## Stage 0 — Foundation
`stages/STAGE-0-foundation.md` · target 3–4 days

- [x] Repository skeleton
- [x] Backend bootstrap, `/health`
- [x] Database and migration 0001
- [x] Closed vocabulary `enums.py`
- [x] Auth: register, login, `/auth/me`
- [x] Cloudinary service
- [x] Upload endpoint
- [x] Frontend bootstrap
- [x] Login and register screens
- [x] Test scaffolding

## Stage 1 — Wardrobe
`stages/STAGE-1-wardrobe.md` · target 6–7 days

- [x] Vision service
- [ ] Tag validation and retry
- [ ] Background tagging
- [ ] Item endpoints
- [ ] Wardrobe grid
- [ ] Upload sheet (camera + gallery)
- [ ] Polling
- [ ] Filters
- [ ] Item detail and tag editor
- [ ] Seed script — 40 items
- [ ] Golden dataset and first accuracy run

## Stage 2 — Stylist
`stages/STAGE-2-stylist.md` · target 5–6 days

- [ ] Weather service and rule table
- [ ] Location search
- [ ] Wardrobe serialiser
- [ ] Stylist service
- [ ] Response validation
- [ ] Looks schema
- [ ] Suggest endpoint
- [ ] Stylist screen
- [ ] Look card
- [ ] Anchor — "Style around this"
- [ ] Swap a single item
- [ ] Weather strip

## Stage 3 — Feedback  *(cut line — reduce to "save a look" if behind)*
`stages/STAGE-3-feedback.md` · target 3 days

- [ ] Migration 0003
- [ ] Save a look
- [ ] Thumbs up/down
- [ ] Wear tracking
- [ ] Preferences fed into the prompt
- [ ] Wardrobe insights

## Stage 4 — Trip Packing  *(signature feature — do not cut)*
`stages/STAGE-4-packing.md` · target 5 days

- [ ] Migration 0004
- [ ] Multi-day forecast
- [ ] Packing orchestration
- [ ] Trip endpoints
- [ ] Trip form
- [ ] Packing view
- [ ] Export

## Stage 5 — QA and Deployment  *(do not cut)*
`stages/STAGE-5-qa-deploy.md` · target 5 days

- [ ] AI fixtures recorded
- [ ] Backend suite to target
- [ ] Playwright suite, 11 journeys
- [ ] Known issues documented
- [ ] CI pipeline
- [ ] Deployed to production
- [ ] Final evaluation run
- [ ] Project README

---

## Log

_Append one line per completed stage: date, what shipped, what changed from the plan._

**2026-08-16 — task 0.10, test scaffolding.** 192 backend tests pass (155 before). New: `tests/conftest.py`, `tests/integration/test_auth.py`, `tests/integration/test_items_rows.py`. Both corrections 0.9 recorded are closed — `RegisterRequest.display_name` is required and trimmed, `POST /auth/login`'s `401` carries `WWW-Authenticate: Bearer`.

Changed from the plan, all recorded in `DECISIONS.md` 072–075:

- The `display_name` fix as specified (`Field(strip_whitespace=True)`) does nothing in Pydantic v2 and was respelled with `StringConstraints`.
- The test database is a separate `postgres:18` container named by `TEST_DATABASE_URL`, with an import-time guard against pointing it at `DATABASE_URL`.
- `pyproject.toml` needed `pythonpath = ["."]` as well as the `eval` marker: the bare `pytest` in `07-DEPLOYMENT.md`'s CI step could not import `app` at all.
- Documented Postgres 16 corrected to 18 in four documents; CI's `postgres:16` pin is 5.5's.

**Stage 0 is closed.** The last open criterion — `GET /health` returning `db: "ok"` — was verified manually after the 0.10 commit, against a running server on the Neon database: `{"status":"ok","db":"ok","version":"0.1.0"}`. It is a manual check rather than a test because it needs a live server and a reachable database; nothing in the suite covers it.

**2026-08-16 — before task 1.1, four behaviours reassigned across stages.** The `status` filter, the `created_at DESC, short_id` ordering, the `include_archived` exclusion and `limit`'s default and cap all shipped at 0.7 and were left undefended at 0.10, implicitly falling to task 5.2. They now belong to 1.4 (status filter, archived exclusion — both written at that task's start), 1.5 (limit) and 1.7 (ordering). Recorded here rather than only in the stage files because it is a change to the plan, not a change to the code.

**2026-08-17 — task 1.1, vision service.** 241 backend tests pass (208 before). New: `app/services/vision.py`, `app/prompts/vision_system.md`, `tests/unit/test_vision.py`. `tag_item` returns the model's raw dict; 1.2 owns validation.

Both questions 1.1 was given to settle are settled, and neither went the way the stage file predicted:

- **The schema works.** First live call to `gpt-4o-mini-2024-07-18`, no `400`. The nullable `color_secondary` union and the `minimum`/`maximum` bounds were both accepted, and the response passed `validate_tag_dict` with no errors and no coercions. The null branch of that union is still unexercised — the model returned a value.
- **`f_auto` on a HEIC did not fail.** Three `Accept` headers: `image/jpeg`, `image/jpeg`, `image/webp`. `vision` is pinned to `f_jpg` anyway, because the header OpenAI's fetcher sends is unobservable. 083 is careful that this removed a variable rather than fixed a fault.

Changed from the plan, recorded in `DECISIONS.md` 078–083:

- Model re-pinned to the dated `gpt-4o-mini-2024-07-18`, one constant in `config.py`; 1.11 gains a comparison run against `gpt-5.4-mini-2026-03-17`.
- The OpenAI client is built lazily — `AsyncOpenAI(api_key="")` raises in the constructor, and a module-level client would stop the suite collecting in CI from 1.3.
- `03-AI-CONTRACTS.md`'s `tag_item` signature and its `response_format` shorthand were both wrong and are corrected.
- `06-TESTING-STRATEGY.md`'s contract test is now a tautology and says so; the real seam is `02-DATA-MODEL.md` → `enums.py`.
- Found by mutation and deferred to 1.2: the vocabulary's `layer` rules run in one direction only (082).

**2026-08-17 — after 1.1, eight live images run out of curiosity.** Not an evaluation; 1.11 owns that. Three findings written into 1.2, 1.9 and 1.11 rather than left in a conversation, and recorded in `DECISIONS.md` 084 with amendments to 029 and 082:

- `fit: "flared"` on a real pair of jeans — a value in no vocabulary, on one of the three fields the schema deliberately does not constrain. Coerced to null correctly and **discarded with no record**, which is a second and separate gap from the one below.
- `fit: "skinny"` on a tank top — a legal `Fit` member, meaningless beside that category, passing with no error and no coercion. Same shape as 082's `layer` finding, which makes it one gap with three instances rather than two unrelated ones. 029's premise for leaving `length` alone is falsified by it.
- `confidence: 0.9` on all eight responses **including both wrong ones**. The `confidence < 0.35` review rule has no settings field, no UI surface and no owning task; it would have flagged nothing. Confidence is a fluency signal, not an accuracy signal, and nothing may treat it as evidence of correctness.

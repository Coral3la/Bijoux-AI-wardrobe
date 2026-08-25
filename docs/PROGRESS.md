# Progress

**Current stage:** Stage 1 — Wardrobe
**Status:** Stage 1 in progress — 1.1, 1.2a, 1.2b, 1.3, 1.4, 1.5, 1.6, 1.7 and 1.8 complete.

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
- [x] Category-dependent validation — 1.2a
- [x] Tag validation and retry — 1.2b
- [x] Background tagging
- [x] Item endpoints
- [x] Wardrobe grid
- [x] Upload sheet (camera + gallery)
- [x] Polling
- [x] Filters
- [ ] Item detail and tag editor
- [x] Seed script — the demo wardrobe
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

**2026-08-16 — before task 1.1, four behaviours reassigned across stages.** The `status` filter, the `created_at DESC, short_id` ordering, the `include_archived` exclusion and `limit`'s default and cap all shipped at 0.7 and were left undefended at 0.10, implicitly falling to task 5.2. They now belong to 1.4 (archived exclusion), 1.5 (limit) and 1.7 (status filter and ordering) — the `status` filter's *test* is written at 1.4's start, ahead of the two frontend tasks that lean on it, but the behaviour is owned by 1.7, which is the thing that depends on it. This sentence said 1.4 owned it until task 1.7, where `STAGE-1` 1.4 said the opposite; the stage file wins because it is the one carrying the argument. Recorded here rather than only in the stage files because it is a change to the plan, not a change to the code.

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

**2026-08-17 — task 1.2a, category-dependent validation.** 376 backend tests pass (241 before). Changed: `app/enums.py` (283 → 376 lines), `tests/unit/test_enums.py` (294 → 707). No new files. `enums.py` gains three tables and one judgement — is this value one the category it arrived beside can be described by — and `CATEGORY_DEPENDENT_FIELDS` so `PATCH` reads the list rather than restating it. `_STANDALONE_CATEGORIES` is deleted; it is four rows of `LAYERS_BY_CATEGORY` now.

All three candidate fields opted in, and the three decisions turned out to be one argument, recorded in `DECISIONS.md` 085:

- **`layer`** — every category gets an admitted set and an answer, and **`top` is the only category with no answer**, so a top tagged `outer` or `standalone` is an error rather than a coercion. 082's open question is closed by refusing to guess instead of by picking `base`. The cost is accepted and written down: an item can now finish `failed` with no tags where it previously finished `ready` with a wrong layer.
- **`fit`** — applies to `top`/`bottom`/`dress`/`outerwear` only, with three narrowed words. Deliberately narrower than the "trouser words" aside in `03-AI-CONTRACTS.md`, which explained one jacket rather than stating a rule; that line is corrected.
- **`length`** — applies to everything but `bag` and `accessory`, with the sleeve and hem ends narrowed and the middle five left alone. **029 is closed** by that and by the `fit` rows: `maxi` on a t-shirt no longer validates, which was 029's own example.

Changed from the plan, and one thing that was measured rather than reasoned about:

- The rules stay **server-side**. `enums.ts` mirrors values, not rules; 1.9 inherits the reasoning and the choice of what its `fit` select does about it.
- `030` grows from three cleared fields to five and stops naming `_STANDALONE_CATEGORIES`. 1.4 gains the consequence it will actually meet: a `PATCH` against a still-`processing` row can now be a `422` where it was a `200`, because a category-dependent field cannot be validated without a category.
- 1.2b gains the prompt-rendering item — the tables are public so `_vocabulary_block()` can render them — and 1.11 gains a prompt version alongside the model id, since that render moves the prompt before the first eval run.
- **Predicted five failing parametrisations, measured six.** The two missed were the base fixture's `long_sleeve` riding along on a pair of jeans — the same jeans-with-sleeves case named three paragraphs earlier as the evidence for leaving the middle of the length list unenforced. The evidence and the prediction contradicted each other inside one message; the count was asserted where it could have been run.

Two rules landed in the documents from how this task went rather than from what it built: `06-TESTING-STRATEGY.md` gains "two readings of one input beat one reading of two" and "a test that reads its expectation from the thing under test measures nothing on its own", and `CONVENTIONS.md` gains the paste-width limit and the rule that an artifact meant to outlive its task is written to disk in that task's commit.

**2026-08-17 — task 1.2b, `validate_tags` and the retry.** 419 backend tests pass (376 before); 353 of them are unit tests, run with no database. Changed: `app/services/vision.py` (248 → 503 lines), `tests/unit/test_vision.py` (303 → 845, 32 tests → 75), `app/prompts/vision_system.md` (29 → 28). No new files. `vision.py` gains `ItemTags`, `TaggingError`, `validate_tags`, `PROMPT_VERSION` and a `correction` parameter on `tag_item`; `_vocabulary_block()` gains 1.2a's three tables.

Four decisions, two entries — `DECISIONS.md` 086 and 087:

- **The documented signature could not do what the documents said it did.** `validate_tags(raw)` appears in `03`, `06` and `STAGE-1`, and a retry is a second call to the model, so it is `async validate_tags(raw, image_url)`. No orchestrator was added: `TaggingError` (the model answered unacceptably) and `ValueError`/provider errors (no answer arrived) are different facts and 1.3 wants both, so 1.3 calls the two functions in sequence and catches both. `vision.py`'s claim that "task 1.2 wraps both" was never achievable and is corrected.
- **A new retry trigger nobody had specified.** `validate_tag_dict` reads every field with `.get`, so `{}` is a clean report — correct for `PATCH`, and a `TypeError` escaping a background task when a typed object is built from it. The eleven fields the schema types with no `null` are now checked in `vision.py`, and a blank `display_name` counts as missing.
- **No confidence branch, and no setting.** Both sides of `confidence < 0.35` produce `status='ready'`, so the branch could only set a flag nothing reads. 028 said the comparison was made "against `settings`" and named a field nobody had written; it is struck there and in `03`'s table. The number is still persisted at 1.3 and mined at 1.11.
- **`ItemTags.coerced` carries the accepted answer's discarded values only.** The rejected attempt's describe tags that were never written. Both attempts are logged, with field, value and category — the record 084 found missing.

Changed from the plan, and the two things that were measured rather than argued:

- **1.11 was checked rather than assumed** and already required a prompt version in three places; what did not exist was anything producing one. `PROMPT_VERSION` hashes the **rendered** prompt, so it moves when `enums.py` does. Persisting it beside the tags is added to 1.3.
- **The prompt grew about 40% and nothing measures whether that helped.** More instruction is more to ignore, and the `top`/`layer` error may now fire rarely enough that the give-up path is exercised only by tests. Written into 1.11 as something only the golden set can answer.
- **Seventeen mutations, all caught, baseline green at both ends.** The finding is that deleting the real `{{VOCABULARY}}` placeholder fails at *collection* — the 1.1 guard raises at import and takes the test module with it — so `test_a_prompt_file_without_the_placeholder_raises_at_load` defends the guard's logic and **not** the shipped prompt file. Its comment now says so. `06-TESTING-STRATEGY.md` has the table.
- **`06`'s `USE_FAKE_AI` code sample was still wrong.** It printed `tag_item(...) -> ItemTags`, `_fake_tags_for` and `_call_openai`, none of which have existed; `03` named that document as one of the three that disagreed at 1.1 and only its prose was fixed. Corrected against the file.
- `CONVENTIONS.md` gains one carve-out: prompt and template files under `backend/app/` are written to disk, not printed. A prompt truncated mid-sentence loads, renders, returns plausible tags and is invisible to every test that reads it.

**2026-08-18 — task 1.3, background tagging.** 440 backend tests pass (419 before). New: `app/services/tagging.py` (277 lines), `tests/integration/test_tagging.py` (504 lines, 20 tests). Changed: `app/models/item.py` (one line), `app/api/v1/routes/items.py` (a `BackgroundTasks` parameter and a three-line loop), `app/main.py` (a `lifespan`), `tests/conftest.py` (two autouse fixtures), `tests/integration/test_items_rows.py` (one test). One entry, `DECISIONS.md` 088.

Four decisions:

- **The task opens its own session, and the obvious reason for that is false.** FastAPI is widely said to close a yield dependency before background tasks run — the 0.106 behaviour. Checked against the installed fastapi 0.141: yield dependencies go into `request_stack`, and the response, which is where Starlette runs background tasks, is awaited inside it. **The request's session is still open.** The conclusion did not move, because the reasons that decide it survive: sharing it pins a Neon connection for a whole batch rather than one item, and it couples a service function to a request lifetime. The wrong reason is written into 088 *as wrong*, so nobody inherits it and "fixes" the code back.
- **Three `error_message` texts, not one.** The model answered unacceptably; no usable answer arrived; the process that started the work is gone. 086 kept the first two apart and this is where the distinction becomes readable in a column.
- **`attributes["tagging"]` on both paths.** `prompt_version` is written on a failed row too — a 1.11 baseline that records only successes measures a biased sample. `coerced` is `[]` when nothing was discarded and absent when there was no accepted answer to discard from.
- **The sweep keys on `updated_at`, which only works because of the `onupdate` fix.** `created_at` looks equivalent and breaks at 1.4, where `retag` puts a week-old row back to `processing`. The two halves are one decision; neither survives the other's removal.

Changed from the plan, and the two things that were measured rather than argued:

- **A test called the live OpenAI API, on the real key.** `tagging.py` does `from app.services.vision import tag_item`, so faking that binding intercepts the first call — and `validate_tags` resolves `tag_item` from **`vision`'s** globals when it retries, which went out to the network. It answered `400` and cost nothing, which is luck and not a mechanism. Two fixes: the fake is installed at both bindings, and `tests/conftest.py` gained an autouse guard that replaces `vision._client` with one that raises unless the test is marked `eval`. `CONVENTIONS.md` has forbidden this since Stage 0 and nothing enforced it. `06-TESTING-STRATEGY.md`'s Layer-3 fixture — which is where the wrong pattern was written down — is corrected, and it is the first thing to fall out of the audit's "documents not read" boundary.
- **`test_uploaded_rows_start_as_processing` passed by accident**, in the window between the route queuing a task and the recorder fixture existing. The real task ran, could not see a row the test had not committed, found nothing and returned — so the assertion held for a reason unrelated to what it claims to measure. The recorder now lives in `conftest.py` and is autouse, because a second file (`test_server_defaults.py`) drives the same route and had the same hole. Recorded in the fixture's docstring: a test that passes for the wrong reason is a finding.
- **Thirteen mutations plus a fatal control, all caught, baseline green at both ends.** Every one was caught by the test named for it. Two were more interesting than the rest: removing the missing-row guard failed three tests rather than one, which is what exposed the `test_server_defaults.py` hole above; and dropping `onupdate` failed exactly the two tests that assert the column moved, one through a flush and one through a Core `update()`, which is the pair that proves it applies to both.
- **`asyncio.gather` was not built.** One task per item means a batch tags serially. Five photographs — the acceptance criterion — fit comfortably; twenty do not. Recorded in `STAGE-1` at **1.7**, where the polling that will notice it gets built, rather than in a note nobody re-reads.
- **`error_message` is not cleared on a successful write**, because at 1.3 a row is only ever `processing` when the task runs and the line would be dead code. 1.4's retag must clear it, and that is written into 1.4.

**2026-08-19 — task 1.4, item endpoints.** 477 backend tests pass (440 before). New: `tests/integration/test_items_edit.py` (28 tests), `test_items_stats.py` (6). Changed: `app/schemas/item.py` (`ItemUpdate`, `ItemStatsResponse`), `app/api/v1/routes/items.py` (four endpoints and three helpers), `app/services/tagging.py` (one line), `tests/conftest.py` (`make_item` moved in from `test_tagging.py`), `test_items_rows.py` and `test_tagging.py` (one test each). One entry, `DECISIONS.md` 089. Audit **O-1 closed**.

Four decisions:

- **One validator, two policies, and the difference is whether there is anyone to tell.** `validate_tag_dict` applies no policy; it reports `errors` and `coerced` and the caller decides. The vision path accepts a coercion because the source is a model and rejecting fifteen fields over one word throws away fourteen good tags. `PATCH` refuses it because the source is a person with a form open, and a `200` whose body differs from what was typed is the worst answer an editing UI gives.
- **030's clearing happens before validation, and the ordering is what makes "any coercion is a 422" exception-free.** Clear first and the impossible values never reach the validator, so every coercion that fires is about a value this request sent. Clearing afterwards would need coercions sorted into "caused by the stored row" and "caused by the request" — the `kind` on `TagIssue` that 086 refused.
- **`user_edited` is never cleared**, and the cost is written into `02` beside the column rather than left to be reconstructed: a hand-corrected item needs `force` on every later retag, forever.
- **A retag against a `processing` row is allowed.** Two tasks can write the same row, last write winning, for a fraction of a cent. Refusing would strand a row whose owning process died for up to ten minutes with the one fixing action unavailable — the worse failure, and the one a user meets.

Changed from the plan, and the things that were measured rather than argued:

- **`04` described `PATCH` as validating the request, and a literal reading of that produces the wrong endpoint.** A category change would pass with `subcategory` and `rise` still describing the old garment. Corrected to say the *merged* row before any code was written, and it is the finding the audit did not reach — O-1 named the missing success contracts and not this.
- **A message written for one policy is wrong under the other, and nothing had noticed.** The vocabulary's coercion reasons end `", set to null"` — true for the vision path, false in a `422` where nothing was set to anything. The route cuts the clause; the vocabulary keeps it, because the log and `attributes` still want it. This is a real cost of sharing one report across two callers and it was invisible until both existed.
- **A test passed for the wrong reason and a mutation found it.** `test_an_unknown_key_is_422` sent only the typo, so with `extra="ignore"` the key was dropped, the dump was empty, and the *empty-body* branch answered `422` — the test stayed green with the guard removed. It now sends a valid field alongside, so only Pydantic can produce the answer. Second instance of this class in two tasks, both caught by mutation rather than by reading.
- **Twenty-two mutations plus a fatal control, baseline green at both ends.** Declaring `GET /items/stats` below `/{item_id}` fails six tests rather than one, which is the audit's "noted in passing" turning out to be load-bearing rather than tidy.
- **One property is untested and named rather than assumed**: the `db.commit()` before `add_task`. It cannot be asserted under `conftest.py`'s fixtures, where the route's session is the test's session and the task is recorded rather than run. Written into `STAGE-1` 1.4.

**2026-08-20 — task 1.5, wardrobe grid.** 479 backend tests pass (477 before) and **109 frontend tests** (72 before, 71 after the deletion below — 38 added). New: `core/api/items.api.ts` (25 lines), `core/state/wardrobe.store.ts` (121), `features/wardrobe/item-card.ts` (80), `shared/models/item.model.ts` (47), and four spec files (`items.api.spec.ts` 53, `wardrobe.store.spec.ts` 200, `item-card.spec.ts` 163, `wardrobe.page.spec.ts` 243). Changed: `features/wardrobe/wardrobe.page.ts` (121 lines, from an app-shell placeholder), `public/i18n/en.json` (+22 keys), `backend/tests/integration/test_items_rows.py` (two tests), `core/auth/auth.service.spec.ts` (one test deleted). Seven entries, `DECISIONS.md` 090–096. Audit **O-4 closed**; **O-13 and O-14 opened**.

**This entry was written at task 1.6 rather than at 1.5.** The 1.5 commit moved the status line and one checkbox and added no log entry, so for one commit the only record of the task was `DECISIONS.md` 090–096, `AUDITS.md` O-13/O-14 and `06`'s mutation table. It is reconstructed from `3a8066e`'s diff and those entries, not from memory, and the two test counts were measured — the frontend by counting `it(` at `3a8066e^` and `3a8066e`, the backend by `pytest --collect-only`. Recorded rather than backdated silently: every other task's "changed from the plan" list is in this file, and a gap that is filled without saying so reads as though it was never there.

Seven decisions, and the through-line is that four of them are about what a control *claims*:

- **The empty state's CTA ships inert and the wardrobe ships no FAB.** These look like one case and are two, and the rule that separates them is **ownership, not affordance**: 1.5's acceptance line requires the empty state and its button, so it is in the brief; no task requires a FAB, so building one would be an affordance nobody asked for. `disabled` was refused because it is a claim about state — it says "not now" when the truth is "not built". 090.
- **A `processing` tile keeps its dimmed photograph** rather than the skeleton `05`'s legend drew. The `public_id` is on the wire in the *first* response, so a grey block would replace the picture the user just took with a placeholder. `05`'s legend was corrected in the same commit; the same claim in `STAGE-1`'s acceptance list and `01-ARCHITECTURE.md` was **not**, and 1.6 finishes that. 091.
- **The frontend branches on the error `code`, not the status**, and `item_edited` is the first code anything reads. The status would have worked and that is why it was the weaker choice: `409` has one meaning on that endpoint by coincidence, and the coincidence is written down nowhere. 092.
- **Retag state is per item** — a `Set` of ids and a `Map` of id to message — so a spinner and a failure land on the tile that owns them. 093.
- **One page of 200, no `offset`, and the header renders the server's `total`.** The explicit limit is required rather than chosen; `total` counts the filter, so above 200 items it is the only truthful number on screen. 094.
- **`I18nService` gets no plural rule; the caller picks between `.one` and `.other`.** Real pluralisation is per-locale and a rule written for English now would be replaced rather than extended when Hebrew arrives. 095.
- **The stale `register` service test is deleted rather than repaired**, and "nothing is lost" was checked by mutation rather than asserted. 096.

Changed from the plan, and the two things that were measured rather than argued:

- **The frontend test suite had been unrunnable for four commits and nothing in this project runs it.** `ng test` failed to *build* on a type error in `auth.service.spec.ts` — `register(…, null)` against a parameter narrowed at 0.10 — while this file recorded three of those tasks as complete. The type error is the symptom. The cause is that `.github/workflows/` is empty and the pipeline `06` specifies runs `ng lint` and `ng build`, **neither of which reads a spec file**: `ng lint` does not type-check and `tsconfig.app.json` excludes `**/*.spec.ts` from the build. `ng test` is the only command in the project that type-checks a spec. `AUDITS.md` **O-13**.
- **Two mutations survived — the first genuine survivors on this project — and both were the same false claim.** Binding the spinner to "any retag in flight" and giving every tile the first entry in the error map both passed the entire suite, 108 tests green, with the per-item claim broken in the template. **The state was tested and the binding was not**, and what hid it is smaller and more general: every test that looked like it covered this rendered a *single item*, where a per-item signal and a global one are indistinguishable. Two tests now render two failing tiles and assert the presence *and the absence*. 093.
- **"Both CTAs" was one CTA and one open question.** *Try a demo wardrobe* has no mechanism and cannot have one on an authenticated screen — the link means switching accounts and `04` has no endpoint for it. It moves to `/login` as prefilled `demo@bijoux.app` credentials, which is **O-12** against 1.10. Audit **O-4 closed** and the recommendation taken in full.
- **`05`'s file tree names seven `shared/ui/` components and 1.5 built none of them**, putting its empty state and buttons inline. Not noticed at 1.5; opened at 1.6 as **O-15**.
- **Half the grid has been seen only by its tests, and that is written down rather than assumed.** The empty state, the ready tiles, both column counts and the processing tile were checked at `ng serve`. The `failed` tile, the retry button, the per-tile placement, the `409` branch and the load-error state were not, because reaching a failed row before 1.9 needs a terminal round trip. **O-14**, owner: whoever verifies 1.9.
- **The delivery rule changed and the review moved with it.** From 1.5 everything under `frontend/` is written to disk and reviewed by `git diff` against a summary by file; `backend/app/` is still printed for manual paste, always. `CONVENTIONS.md` carries the boundary and the reason the frontend can take it and the backend cannot.

**2026-08-20 — task 1.6, upload sheet.** **156 frontend tests pass (109 before, 47 added).** Backend untouched — 1.6 was assigned none of the four `GET /items` behaviours inherited from Stage 0. New: `features/wardrobe/upload-sheet.ts`, `features/wardrobe/pending-strip.ts` and their two specs. Changed: `core/api/items.api.ts` (`upload`), `core/state/wardrobe.store.ts` (`pending`, `isUploading`, `uploadError`, `upload`, `dismissUploadError`), `features/wardrobe/wardrobe.page.ts` (the CTA wired, a FAB, the sheet hosted, the strip placed), `shared/models/item.model.ts` (`ItemUploadResponse`), `public/i18n/en.json` (+17 keys), and four documents besides this one. Five entries, `DECISIONS.md` 097–101. Audit **O-15 opened**, **O-14 extended**.

Five decisions:

- **Previews are their own collection and nothing is ever a synthetic `Item`.** A `pending` signal of local key, object URL and filename, rendered in a strip above the grid. Fabricating a row would put an invented `id` and `short_id` on the one model 059 says mirrors the wire field for field, and 1.7's polling and 1.8's filters would both have to learn that some members of `items()` are not rows. 097.
- **The sheet is a plain element, not `<dialog>`, and the test environment is why.** `showModal`, `show` and `close` are all `undefined` in jsdom, so a dialog-based sheet could not be opened by any test in this project. The platform element is the better one and is not being rejected on its merits; focus trapping and `Esc` are the two costs, paid by hand. **A testability constraint that changes a design decision is recorded as a decision.** 098.
- **The camera keeps the sheet open and the gallery closes it.** Both documents specify the camera only. After a batch the user's next move is watching the rows arrive, which a sheet over the grid hides. 098.
- **Upload failures are keyed by `code` and the server's `detail` is not rendered**, so a `415` on one file out of twelve cannot say which. `04-API-SPEC.md` fills `detail` with the filename precisely so a client can show it, and `CONVENTIONS.md` forbids rendering a raw error; no third document resolves it, and the general rule wins because `detail` is untranslatable English. Recorded as a known limitation rather than solved. 099.
- **The `202` carries no `total`, so the client moves its own count**, by the number of returned rows, prepended. Without it 094's header understates by the size of every batch. 100.

Changed from the plan, and the things that were measured rather than argued:

- **A mutation survived, and it was the test rather than the code.** Changing the sheet's arithmetic from 1024² to 1000² left **all 155 tests green**, because every size expectation was written as `MAX_UPLOAD_BYTES ± 1` — imported from the module under test, so the mutation moved the expectations with it. This is the mebibyte/megabyte confusion `CONVENTIONS.md` has a whole section about, invisible to the file that exists to catch it. The literal is now transcribed from that section and one test pins the constant to it. **The other limit in the same file was already checked against literals and was caught correctly**, which is what makes the shape readable: two constants, tested the same way, and only one self-referential. `DECISIONS.md` 101, `06-TESTING-STRATEGY.md` has the table.
- **A prediction was wrong and is recorded as wrong.** M-U — never revoking the object URLs — was declared expected-to-survive *before* the run, on the reasoning that jsdom implements neither half of that API. It was caught by two tests. The reasoning was not falsified but the result is qualified: those tests prove the store called our stub, not that a browser released anything, so it is recorded as a weak catch rather than a clean one.
- **Twelve mutations plus a fatal control, baseline green at both ends.** U1 — the pending strip binding every slot to the first entry — is 1.5's M11/M12 shape, and it was caught, because every test that touches per-file state uses **two files**. That was written into the plan before the code, which is the only reason it did not recur.
- **The gate's limits were measured, not assumed, and two of them changed the code.** jsdom 28.1.0 has no `URL.createObjectURL`, no `DataTransfer`, no `<dialog>` methods, no layout and no `matchMedia`. The missing dialog methods decided 098; the missing `DataTransfer` decided that specs install a plain array through `Object.defineProperty`, which exercises our handler and not `FileList` semantics. The probe is in `06-TESTING-STRATEGY.md` as a property of the environment rather than of this task.
- **The stage file did not own what two other documents assigned to it.** `05` line 111 and 090 both gave 1.6 the empty-state CTA and the FAB while `STAGE-1` 1.6 named neither, so what gets built was governed from the side. One line added. The FAB is load-bearing rather than cosmetic: the CTA renders inside the `isEmpty()` branch and disappears after the first upload, so without it the sheet is reachable once per account.
- **Acceptance criterion 1 was false and is rewritten rather than softened.** It asked for five skeleton tiles; 091 replaced those with the dimmed photograph at 1.5 and amended `05`'s legend only. `01-ARCHITECTURE.md`'s flow 1 carried the same claim and also gave the previews no step at all — both corrected. `06`'s first E2E journey still expected "both CTAs" eight commits after O-4 closed; corrected.
- **The output could not be called `close`.** `@angular-eslint/no-output-native` refuses an output named after a standard DOM event, because a native `close` would fire the same binding. Renamed `dismissed`. Found by `ng lint`, which is the first time on this project that the linter has caught something a test could not.
- **`PendingUpload` did not go where the plan put it.** It was agreed it would live beside `PendingStrip` rather than in `item.model.ts`; it is in `wardrobe.store.ts` instead, because `core/` imports nothing from `features/` anywhere in this project and the type alias would have been the first inversion. The agreed reasoning — keep it out of the file that mirrors the wire — is unchanged.
- **One surface is deliberately unbuilt.** `05`'s file tree names seven `shared/ui/` components and none exist; 1.5 built its empty state inline and 1.6 built its sheet inline. Opened as **O-15** with the recommendation to extract at the *second* caller, which is 1.8's filter sheet.

**2026-08-23 — task 1.7, polling.** **181 frontend tests pass (156 before, 25 added).** Two backend tests added; the count is unmeasured here because `pytest` was not run in this session. No new files — the first task this stage that only edits. Changed: `core/state/wardrobe.store.ts` (the loop, `stoppedWaiting`, `awaitingTags`, `stopPolling`), `core/api/items.api.ts` (`list` takes an optional status), `features/wardrobe/item-card.ts` (the stopped-waiting state), `features/wardrobe/wardrobe.page.ts` (the binding, the destroy stop, the tagging line), `public/i18n/en.json` (two strings rewritten, one added), four spec files, `backend/tests/integration/test_items_rows.py` (two tests), and six documents besides this one. Seven entries, `DECISIONS.md` 102–108. Audit **O-14 extended**.

Seven decisions, and the first one is the reason this was a decision rather than a rewrite:

- **The poll is two requests, and the second is why a tile ever shows a tag.** `GET /items?status=processing` returns only rows that are *still* processing, so it can say an item has left the set and can never say what it became. Three documents described that one request and one acceptance criterion required what it cannot deliver. The loop compares the returned **ids** against the awaited ones and re-issues the full `GET /items?limit=200` when any is missing. 102.
- **The run object is the guard, and there is no polling boolean.** A nullable private field holding the deadline, the timer and the in-flight subscription; a run cannot exist without the things it owns, so the two facts cannot drift. `05`'s sketch has no guard at all and would call `startPolling()` on every response. 103.
- **Re-armed after each response settles, not run from a fixed interval**, so one poll in flight is a property rather than a hope about how fast the server answers — which is also what makes `mock.verify()` mean anything. 104.
- **Giving up is a collection, not a status.** A client-written `failed` in `items()` would be a row no server issued, on the one model whose contract is that everything came off the wire, and 1.8 filters that collection while 1.9 edits from it. 097 stays intact. The tile says **"We stopped waiting. It may still finish."** and takes no danger token, because the server may well still be tagging and 057 reserves that colour for something being wrong. 105.
- **The poll never writes `total`; the reload does.** A filtered response's `total` counts the filter, and the filter is `processing` — writing it would drop the header to the size of the batch. No document ruled either way. 106.
- **A failed poll is ignored, and there is deliberately no visibility handling.** A cold start on Render answering slowly is not news, and the deadline bounds a poll that never succeeds. Pausing on `visibilitychange` was weighed and refused: the browser already throttles background timers, no document asks for it, and the test could only ever prove that our own listener runs when we dispatch the event ourselves. 107.
- **The three minutes restart when a batch arrives mid-run.** 098 keeps the sheet open after a camera capture so the next garment can be shot immediately, which makes back-to-back batches the designed path; two full batches tag serially for longer than one deadline covers, so a per-run deadline would abandon items that were tagging perfectly well. 108.

Changed from the plan, and the things that were measured rather than argued:

- **A mutation survived, and the claim it falsified was mine.** M8 — keying the effect on `processing()` instead of `awaitingTags()` — passed all 180 tests. It was written into the plan as the find of the task, on the reasoning that giving up would restart the loop it had just stopped. **That mechanism does not exist:** an effect reading only `processing()` no longer depends on the signal that giving up writes, so it never re-runs at all. The real fault is quieter and is reachable — the next batch restarts the loop, and when *that* batch finishes the loop keeps polling for an item whose tile already says we stopped waiting for it, for another three minutes, with nothing on screen saying so. One test now closes it and the false mechanism is not written into `DECISIONS.md` 105. **The design was right for weaker reasons than the ones given for it**, and the mutation is how that was found rather than a reader finding it later.
- **A prediction was wrong in the other direction too.** M11 — the deadline comparison `>=` weakened to `>` — was declared expected-to-survive before the run unless a test landed on the exact boundary. The boundary test was written, and M11 was caught by five tests. Second run in a row where a declared survivor died; the declaration is still worth making, because the one that *did* survive was the one nobody had predicted.
- **Seventeen mutations plus a fatal control, baseline green at both ends.** Every other row was caught. The two literals — `2000` and `180_000` — are transcribed by hand from `01-ARCHITECTURE.md` and `05-FRONTEND-SPEC.md` and pinned to the constants in one test each, which is 101's lesson applied before the fact rather than after: mutating either constant now fails nine and six tests respectively.
- **The harness was decided before the first test was written, because the measurement said it had to be.** `vi.useFakeTimers()` in `wardrobe.page.spec.ts`'s `beforeEach` breaks **nineteen** existing tests, all on the 5-second timeout, and takes the suite from 2.1s to 96.4s — Angular's zoneless scheduler needs a task to run and a frozen clock never gives it one. The switch happens after the render instead, as a named helper carrying that number. `vi.useFakeTimers({ shouldAdvanceTime: true })` keeps all 156 green and was refused: it advances the mock clock 1:1 with real time, which is not a fake clock in the way a deadline test needs.
- **Three documents described a loop that cannot show a tag**, and `01-ARCHITECTURE.md` also numbered two consecutive steps `8` and described a loop with no bound. All corrected here rather than left for whoever meets the tiles that never gain tags.
- **The `status` filter's owner was recorded two ways.** `STAGE-1` 1.4 says ownership is 1.7's; this file and `STAGE-5` 5.2 both said 1.4. The stage file wins because it carries the argument, and both other sentences are amended. The test stays where it is, at 1.4's start.
- **`GET /items` had no ordering test anywhere in the project**, four stages after the ordering shipped. Two now: one for `created_at DESC` across two timestamps, one for the `short_id` tiebreak on rows sharing a `created_at`. The second asserts the shared timestamp rather than assuming it — without that line the test would still pass if `now()` ever became the statement timestamp, having silently stopped testing the tiebreak.

**2026-08-23 — task 1.8, filters.** **226 frontend tests pass (181 before, 45 added).** Backend untouched and not run — this task sends no new query parameter, so there was nothing on that side to defend. New: `features/wardrobe/filter-bar.ts` and `filter-bar.spec.ts`. Changed: `core/state/wardrobe.store.ts` (`ItemFilters`, `applyFilters`, `filters`, `visible`, `setFilters`, the scale constants), `features/wardrobe/wardrobe.page.ts` (the branch chain, the bar, the URL, the filtered count), `public/i18n/en.json` (+36 keys), two spec files, and six documents besides this one. Seven entries, `DECISIONS.md` 109–115. Audit **O-15 answered**, **O-16 opened**, **O-14 extended**.

Seven decisions, and the first one is the task:

- **A null tag is an unknown, not a non-match, and the predicate never reads `status`.** Per field rather than per row: a filter on colour tests colour, so a row whose colour is null passes it and is still filtered on its category. The alternative costs an upload that appears and vanishes — the preview renders outside the filter (097) and the row that replaces it carries every tag null. **Per field was decided by a row 1.9 makes reachable**: `PATCH {"color_primary": null}` is a `200` that clears one column, so a `ready` item can carry one null beside four real tags. The stopped-waiting tile staying visible *falls out of* the rule rather than being provided by it. 109.
- **The filters are the store's and the URL is the page's**, read once from the snapshot and written in the same method that sets the state, with `replaceUrl: true`. A root-provided store writing the address bar is 107's failure one collection over. 110.
- **The header is the only count**, and under a filter it reads "12 of 138 items" — both numbers in the one place a count already lives, so 094 and 100 both survive unchanged. The empty result is its own state with its own way out, and never the empty wardrobe's call to action. 111.
- **No chip counts, and `byCategory` was corrected out of `05` rather than built.** It groups `visible()` and this grid is flat. `GET /items/stats` stays unowned. 112.
- **The filter control is an inline disclosure panel, not a sheet**, on 098's own argument: a modal hides the thing being filtered while the control is open. **O-15 is answered rather than acted on** — the second caller was asked to decide and does not want a sheet. 113.
- **Twenty-four label keys by hand rather than pulling O-10's pipe forward**, with the swatch colours held in a `satisfies Record<Color, string>` map — the one hand-mirror on this project with a compiler watching it. 114.
- **The ranges are bound and coerced**, because the gate's range input is not a browser's. 115.

Changed from the plan, and the things that were measured rather than argued:

- **The A/B question was mine to raise and the stage file had already settled it.** "Client-side over the loaded collection" is the brief verbatim, so server-side filtering was mapped and built nowhere. The mapping stands as the record of what was considered, and its one durable finding is **O-16**: 1.8 was the last plausible consumer of seven `GET /items` query parameters and declined them, so they now have no caller, no test and no candidate.
- **Two questions were missing from the orientation and cost one round trip.** Whether the exemption is per field or per row, and whether dimensions combine as AND — the second had been asked for by name and I did not turn it into a question. Both were settled before any code, which is where the cost stopped.
- **The gate was measured again, and four measurements changed the code rather than the tests.** A range with no bound value reads **50** where a browser reads 3; jsdom does not snap to `step`; `scrollIntoView` is `undefined` and **calling it throws**; and `window.location.search` never moves under `MockPlatformLocation` while `history.replaceState` moves it and leaves `router.url` stale. Written into `06-TESTING-STRATEGY.md` as properties of the environment.
- **Twenty-four mutations plus a control, one survivor, and the three declared in advance were all wrong.** The survivor was rounding inside `setFormality`, which no test reached because the only fractional drag was on a **warmth** handle — two near-identical methods, one tested. A second test now drags a formality handle. The control fails 29 tests. `06` carries the run.
- **The `pending().length === 0` clause survived the rewrite and was defended twice**: 1.6's test still guards the empty state, and a new one guards it against the branch 1.8 added underneath it. Dropping the clause fails both.
- **Two controls say "Clear filters" when the no-match state is on screen** — the bar's and the state's. Accepted rather than solved: the state carries its own way out. 111.
- **One acceptance criterion was rewritten rather than softened.** It asked for "correct counts" without naming anything that renders a count, and omitted formality, which the brief gives a control. It now describes what appears, including the per-field null rule.

**2026-08-23 — task 1.9, commit 1 of 2: a completed edit clears a failed status.** **486 backend tests pass (481 before, 5 added).** Frontend untouched and not run — this commit changes the wire the editor will be written against, and nothing on the screen yet reads it. Changed: `app/enums.py` (`REQUIRED_TAG_FIELDS`), `app/services/vision.py` (its tuple derived, four lines), `app/api/v1/routes/items.py` (`_is_complete`, and one branch in `update_item`), `tests/integration/test_items_edit.py` (five tests), and four documents besides this one. One entry, `DECISIONS.md` 116.

- **The wire could not honour a promise `03` has carried since it was written.** `PATCH` wrote tags and touched `status` nowhere, so an item hand-tagged from a failed tile answered `200` and kept `failed` and its `error_message` for good; `item-card.ts` branches on status alone (089), so the tile went on saying "Tagging failed" above a full set of tags the user had just typed. A `failed` row whose merged result carries every required tag now becomes `ready`, and `error_message` clears with it. `processing` is never written — a task in flight overwrites every tag column when it lands. `ready` is never demoted — clearing a tag is answering, not failing, and 109 already depends on that. 116.
- **The required set was found rather than written, and one of its eleven fields could not come along.** `vision.py:381` already named it. Ten are row fields and moved to `enums.py` as `REQUIRED_TAG_FIELDS`, beside `CATEGORY_DEPENDENT_FIELDS` and read the same way; `vision.py` now derives its own as `(*REQUIRED_TAG_FIELDS, "confidence")`. **Keeping all eleven shared would have shipped a branch that could not be reached:** `confidence` is the report's name for `ai_confidence`, which is nullable, is never written on the failure path, and has no field in `ItemUpdate` — so the row O-3 exists to rescue could never have satisfied it.

Changed from the plan, and the things that were measured rather than argued:

- **The declared survivor died, and the reason is the shape's best argument.** Removing `water_resistant` from `REQUIRED_TAG_FIELDS` was declared in advance as an expected survivor — the column is `NOT NULL` with a server default, so it can never block a `PATCH`, and no test on this endpoint can tell its presence from its absence. It was **caught by three tests in `test_vision.py`**, none of them a `PATCH` test. The reasoning about the endpoint held; the prediction about the blast radius did not, because **deriving one tuple from the other shares its defence as well as its contents**. Third run in a row where a declared survivor died, and the first where the survivor's own reasoning survived the death.
- **Nine mutations plus a fatal control, baseline green at both ends, every row caught.** The two worth naming: `is None` weakened to falsiness dies on `water_resistant: false`, which is `vision.py`'s own commented trap one module over; and the rule made bidirectional — incomplete demotes to `failed` — dies on a `ready` row having a tag cleared, which is the test written for exactly that mutation and for nothing else.
- **The five tests build their body from `REQUIRED_TAG_FIELDS` rather than transcribing it**, so a field entering or leaving the vocabulary moves them. What is written by hand is the boundary: one key removed from a complete body is the incomplete case. The helper yields **nine** keys, not ten, and that is visible rather than hidden — a nine-key body clearing a `failed` status is what demonstrates the `water_resistant` free pass.
- **`ruff format --check` has been failing on the committed tree since task 1.7** and is not this commit's to fix: one missing blank line at `tests/integration/test_items_rows.py:204`. `ruff check` passes and always has. `CONVENTIONS.md`'s definition of done says "passes lint", nothing in the project runs the formatter in check mode, and no CI exists to run it — the same shape as **O-13**, where nothing ran the frontend suite for four commits. Reported rather than repaired, because a formatting fix in an unrelated test file does not belong in this commit.

**2026-08-23 — task 1.9, between commits 1 and 2: the delivery rule.** No code changed and the suite was not re-run for its own sake — this commit is a rule, its reasoning, and one blank line. Changed: `docs/CONVENTIONS.md` (the delivery section rewritten), `docs/DECISIONS.md` (117), `backend/tests/integration/test_items_rows.py` (one line). One entry, `DECISIONS.md` 117.

- **Print-and-paste is retired.** Every file is written to disk and delivered as a printed `git --no-pager diff`; the developer reviews what landed rather than what was intended, and still stages and commits by hand. The rule changed mid-task, `CLAUDE.md` was updated in commit 1 as the developer instructed, and **`CONVENTIONS.md` therefore contradicted it for the span of exactly one commit** — reported at the time rather than resolved silently, and closed here. 117.
- **The rule it replaces never had a decision entry, and this was found while writing the one that retires it.** `CONVENTIONS.md` cited `DECISIONS.md` 017 for the paste in two places. **017 is about commits** — no git writes by the agent, manual staging, a review pass over every diff — and says nothing about how a file is delivered. It is untouched and still in force; the diff review *is* its review pass, now carrying the whole weight. A rule that borrows another entry's number is a rule whose reasoning nobody can locate, which is the argument for writing 117 at all.
- **The measurements are kept as history and two rules are marked moot rather than deleted.** 1.2a's truncation (six comment lines cut at 66 columns, one three-line comment gone, in a byte-correct file), 1.4's partial-block loss (five comment lines, from a delivery split into three blocks), and 1.2b's correction all stay under a heading that says they are history — a reader meeting a deliberately narrow comment in `backend/app/` should be able to find out why it is narrow. **Moot: the 66-column width rule and "printed code is read back out of the verified mirror, never retyped"**, both because nothing is retyped now. The mirror is not moot; verification is unchanged.
- **1.5's frontend argument is promoted rather than restated.** *"A diff is not retyped, so no line can arrive cut at column 66"* was written to justify one directory and was always an argument about the medium. It is now the project's.
- **The formatter is fixed and its place in the gate is left open, deliberately.** `ruff format --check` had been failing on the committed tree since 1.7 on one blank line at `test_items_rows.py:204`; `ruff check` always passed and no CI runs either. The line is fixed, so the tree is clean end to end. **Whether the formatter joins the definition of done is not decided here** — that is the same shape as **O-13** and it is not a call to make in the middle of 1.9.

One thing worth recording about how this commit came about, because it is a property of the working agreement rather than of the code: the previous commit's delivery flagged a stray blank line in `enums.py` that **did not exist** — an added blank and a context blank in a diff hunk read as three where there were two. The instruction that came back was to fix it inside that commit. It was not fixed, because it was not broken, and the formatter confirmed it. *Verify the tree, not the intent* had only ever been pointed at the agent; it points both ways.

**2026-08-23 — task 1.9, commit 2 of 2: item detail.** **296 frontend tests pass (226 before, 70 added).** Backend untouched and not run. New: `shared/pipes/cloudinary-url.pipe.ts`, `features/wardrobe/item-detail.page.ts`, `features/wardrobe/tag-editor.ts` and three specs. Changed: `app.routes.ts`, `core/api/items.api.ts`, `core/state/wardrobe.store.ts`, `shared/models/item.model.ts`, `features/wardrobe/item-card.ts`, `features/wardrobe/filter-bar.ts`, `public/i18n/en.json`, four specs, and six documents besides this one. Twelve entries, `DECISIONS.md` 118–129. Audits **O-3 closed**, **O-10 closed**, **O-14 corrected and extended**, **O-15 fourth decline**, **O-17 opened**.

Twelve decisions, and the first two are the shape of the screen:

- **All fourteen fields on every save, and the category cascade is the client's.** The stage brief requires the user to *see* five empty fields before saving, which a request-diff cannot deliver. Sending everything makes the route's clearing branch — guarded by `field not in changes` — never fire, so the five nulls on the wire are the five blanks on screen. It also makes the `422` that 1.4 documents as a trap unreachable. 119.
- **The edit waits, and 097 is the argument rather than taste.** An optimistic row is an `Item` no server issued, and it is worse than the synthetic preview 097 refused, because a preview is visibly not a row where a guessed edit is indistinguishable from a real one. The server also decides two things this client cannot: whether five dependent fields were cleared, and whether the row has stopped being `failed` (116). 120.
- **A delete removes the row and moves the count only if it was counted.** The `200` carries no `total`, which is 100 inverted; a deep-linked row was never in `items()` and never in `total`, so decrementing for it would understate the wardrobe. It is also the first operation that removes a row without a `load()`, which makes it the first real test of **the leak 093 accepted in writing**. 121.
- **One retag control, and the `409` is produced rather than avoided.** Forcing whenever `user_edited` is set would mean the conflict is never produced from the UI and acceptance criterion 6 stays a route test forever. 122.
- **The category select can say "not chosen yet" and cannot say "clear this".** Two requirements that looked like one: O-3 opens this editor on a row with every tag null, so the control must represent *unchosen* — and a select with no empty option renders `Tops`, so a save would invent a category the user never picked, on the one screen built to stop that. 123.
- **Subcategory narrows by category; nothing else does.** `SUBCATEGORIES` is a value mirror that already exists. The rules that narrow `fit`, `length` and `rise` are rules, they stay server-side (085), and copying them is what this task declined. 124.
- **One message for every rejected save, and the form keeps every value.** 099's collision again — the field name is in `detail` and `CONVENTIONS.md` forbids rendering a raw error — resolved the same way and recorded as a limitation. The condition attached to it is the half that matters: the form is seeded once and never re-seeded, so a rejection that also emptied ten fields cannot happen. 128.
- **The tile's image is the link and the retry button is its sibling.** How a user reaches item detail was specified in **no document**; `05`'s legend gives the tile one behaviour and §4 describes a screen with no route into it. 129.

Changed from the plan, and the things that were measured rather than argued:

- **All three declared survivors were caught, and the one that survived was not predicted — again.** The delete not removing the row, the decrement ignoring provenance, and the cascade clearing four of five all died. The survivor was **`M6`: reading the route parameter as `itemId` instead of `id`, which passed all 296 tests** — because the spec's `ActivatedRoute` stub answered *every* key with the same value. The stub now honours the key and the mutation fails 33. **A stub that ignores its argument is a stub that cannot fail**, and the defect was in the test rather than in the code, which is a first for this project's mutation runs. Sixteen mutations plus a control; `06-TESTING-STRATEGY.md` carries the table.
- **The reasoning behind two of the three predictions was right and the predictions were still wrong.** `WardrobePage`'s constructor reloads on every arrival and shows a loading line while it does, so a delete that mutates the store correctly and one that does not are indistinguishable *on screen* — that is true, and it is written into 121. What it missed is that the tests for it are store-level precisely because the page cannot see the difference. The prediction was about the screen; the tests were not.
- **A price quoted before the work was wrong in its own favour, and the decision stood anyway.** The i18n key move was estimated at "thirteen specs today". It cost **four lines in `filter-bar.ts` and zero spec lines**: `filter-bar.spec.ts` loads the real `en.json` and asserts rendered labels — `buttonWith('Tops')` — not key strings, so moving the values with the keys left every one of them green untouched. 118 records the correction beside the decision.
- **Two bugs in the first draft that only the gate found.** `[formControlName]` is a property binding and does **not** reflect as an attribute, so eleven of the fourteen controls were unfindable by `select[formcontrolname=…]`; every control now carries an `id`. And `subcategories` was a `computed` reading `form.controls.category.value` — a plain form control is not a signal, so it never recomputed and the subcategory list never narrowed. The category is now a signal written in the two places it can change. Both were caught by tests written before the component was run, which is the only reason they were caught at all.
- **`window.confirm` decided the delete, the way the missing `<dialog>` decided the sheet at 1.6.** It is a function that returns `undefined` in jsdom 28.1.0, so a confirm-guarded delete would read as tested and never run. 126, and `06` carries the probe. `inert` being unsupported is the same measurement's other half and is why the modal was declined on cost rather than on principle.
- **O-14's verification method was wrong on disk and is corrected rather than left.** It told whoever verifies this task to *"force a tagging failure by editing an item and retagging it"* — editing sets `user_edited` so the retag is a `409`, and a forced retag re-runs tagging against a photograph that already succeeded. The model never sees the tags. Two of its bullets close at 1.9 (the `409` branch, the loop across a real navigation) and four do not.
- **Acceptance criterion 3 is recorded as unowned rather than quietly failed.** *"A deliberately bad image ends as `failed`"* — `USE_FAKE_AI` cannot fail, a bad photograph usually still tags, and editing cannot cause a failure. The only dependable route is a terminal round trip no task owns. **O-17**, with a recommendation to cut it or move it to 5.3 and no invented task.
- **`shared/ui/` is declined a fourth time and `shared/pipes/` is no longer empty.** Stage 1 has one frontend-adjacent task left and it is a seed script, so O-15's other recommendation — delete the line from `05`'s tree — is now the live one.

**2026-08-25 — task 1.10, demo seed data.** **566 backend tests pass (486 before, 80 added)** and **301 frontend tests (296 before, 5 added)**. New: `backend/scripts/seed_demo.py` (1,698 lines, of which 64 are the committed table), `backend/tests/unit/test_seed_data.py` (66 of its cases are the table itself). Changed: `backend/pyproject.toml` (`[tool.mypy] files` widened to `["app", "scripts"]`), `frontend/src/app/features/auth/login.page.ts`, `login.page.spec.ts`, `public/i18n/en.json`, and seven documents besides this one. Twelve entries, `DECISIONS.md` 130–141. Audit **O-12 closed as superseded**, **O-5 and O-14 extended**, **O-18 opened**.

**Seeded against Neon on 2026-08-25: 64 items on `demo@bijoux.app`, all `ready`.** The four pre-existing users and their thirteen items were verified untouched after the run. An earlier run of the same seed used `--with-failures` and was replaced by a `--reset`: its two extra rows reuse existing `public_id`s, so the grid showed two garments twice and read as a duplication bug rather than as a demonstration of the failed state. `DECISIONS.md` 135 amends the decision; `AUDITS.md` **O-18** records what the clean wardrobe cannot demonstrate.

Four decisions worth the summary:

- **The tags are hand-written and validated on `PATCH`'s policy — any error *and any coercion* aborts the run.** Cost did not decide against a live tagging pass; reproducibility did. `USE_FAKE_AI` was refused by name (081): forty identical placeholder shirts is not a wardrobe. 130.
- **The demo user's UUID is pinned.** `--upload` names a Cloudinary folder before any row exists, and `--reset` deletes the user, so a generated id would have orphaned every committed `public_id` on every reset — the problem `STAGE-0` §0.6 named, made permanent. 132.
- **Seeded rows carry `attributes["seed"]`**, a second guest key beside `tagging`, so 1.11 can exclude them with `WHERE NOT (attributes ? 'seed')` before mining `display_name` for words the vocabulary is missing. Verified on the live database: the exclusion returns exactly the 13 non-seed rows. 134.
- **The demo affordance is a button, not O-12's prefilled form.** A value in an input carrying `autocomplete="current-password"` invites a browser to save the demo account over a visitor's own login. 136.

Changed from the plan, and the things that were measured rather than argued:

- **The count moved three times — 40 → 58 → 64 — and the acceptance criterion no longer names one.** The 40 was an estimate made before the photographs existed. The criterion now asks for a browsable wardrobe covering every category, and the script logs what it seeded.
- **Filename-derived tags failed on 13 of 24 rows, and seven of the thirteen were wrong only in a column that inserts silently.** A wrong `subcategory` aborts the run; a wrong `colour`, `warmth` or `material` is a legal value in the right column and is discovered at a defence. `sweater` in a filename carried no warmth information at all — two of three are summer knits. All 64 rows were re-tagged from the image. 141.
- **Two defects found by running rather than reading.** No `relationship()` is declared between `User` and `Item`, so SQLAlchemy's unit of work had no dependency edge and batched the items first, failing on `fk_items_user_id_users`; the fix is an explicit `flush` (133). And every CLI log line passed its values as `extra`, which the **development** formatter drops — the guard that exists to show which database is about to be written to printed the words "Target database" and nothing else. Six call sites now put the values in the message.
- **All 64 `public_id`s were fetched through `build_url` and returned 200.** This is the check `DECISIONS.md` 133 records as untestable — no fixture can tell you a committed reference is live — and it was run by hand instead: 64/64 thumbnails, `image/jpeg`, 4.3–16.5 KB. The Admin API confirms 64 assets under the pinned folder.
- **Four vocabulary gaps found by looking at photographs before 1.11 ran**: `turquoise`, knee-high `length`, the bag subcategories, and `suede`. The fourth is a different kind and 141 says so — suede *is* leather, so that tag is lossy rather than false, and a model answering `leather` there must score as correct.
- **The failure rows are built and not shipped.** `--with-failures` adds two `failed` rows and is off by default; it is not run, because its rows reuse two committed `public_id`s and the grid then shows two garments twice. The wardrobe that ships is 64 rows, all `ready`, with no duplicated photograph — and four shipped behaviours consequently have no demo surface, recorded as **O-18**.
- **Nothing tests the database guard or the insert ordering**, measured by mutation: deleting either leaves the suite green. A test for the guard would have to write into `TEST_DATABASE_URL`, which is the one thing the guard refuses.

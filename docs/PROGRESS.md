# Progress

**Current stage:** Stage 1 — Wardrobe
**Status:** Stage 1 in progress — 1.1, 1.2a, 1.2b, 1.3, 1.4, 1.5 and 1.6 complete.

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

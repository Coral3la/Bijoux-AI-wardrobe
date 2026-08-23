# Stage 1 — The Wardrobe

**Week 1 second half through week 2. Target: 6–7 days.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

Photograph or select clothes, watch them tag themselves, browse and filter them, and correct the AI when it is wrong.

**At the end of this stage the project is already a defensible submission.** Everything after this is upside.

## Prerequisites

Stage 0 acceptance criteria all pass.

## Out of scope for this stage

No stylist. No looks. No weather. No trips. Do not build a "suggest an outfit" button, even disabled.

## Coverage inherited from Stage 0

Four `GET /items` behaviours shipped at task 0.7 and were left undefended at 0.10: the **`status` filter**, the **`created_at DESC, short_id` ordering**, the **`include_archived` exclusion**, and **`limit`'s default and cap**. They were implicitly task 5.2's.

They are reassigned into this stage, to the task that first depends on each — 1.4, 1.5 and 1.7 below. A behaviour defended four stages after the code that relies on it is not defended in any useful sense, and each of these four fails in a way that presents as something else: a polling loop that never empties, a grid that reorders itself between polls, a `DELETE` that appears to do nothing, a filter bar counting over the first hundred items. `STAGE-5` 5.2 records where each one went so nobody goes looking for them there.

**All four are backend integration tests**, in the same file as the rest of `GET /items`'s coverage, regardless of which task owns them — 1.5 and 1.7 are frontend tasks and this is the one thing about them that is not.

---

## Tasks, in order

### 1.1 Vision service
`services/vision.py` → `tag_item(image_url) -> dict`, using OpenAI Structured Outputs with the schema in `03-AI-CONTRACTS.md`, `detail: "low"`.

Prompt lives in `app/prompts/vision_system.md`, which carries a `{{VOCABULARY}}` placeholder rendered from `enums.py` at import — a missing placeholder raises there rather than shipping a prompt with no vocabulary. The schema's enum arrays come from the same source, so prompt, schema and validator cannot diverge. What that does *not* close is `02-DATA-MODEL.md` → `enums.py`, which stays hand-maintained; `06-TESTING-STRATEGY.md` says so where the contract test used to claim otherwise. `DECISIONS.md` 080.

Include the `USE_FAKE_AI` branch from day one, not as an afterthought — Stage 5 depends on it and retrofitting it is annoying.

**The HEIC question is settled.** Measured on one real iPhone HEIC through the `vision` transform, three ways: no `Accept` header and `Accept: */*` both returned `image/jpeg`, a browser-like `Accept` returned `image/webp`. **`f_auto` did not fall back to HEIC** — the failure 046 suspected did not occur, and the live call below ran successfully against the `f_auto` URL. `vision` is pinned to `f_jpg` regardless, because `f_auto`'s answer depends on an `Accept` header OpenAI's fetcher sends and we cannot observe, and negotiation has no upside for a machine consumer. The single-header test this paragraph used to specify would have passed and closed the question with the variable still live; three headers is what surfaced it. `DECISIONS.md` 083.

**The response schema is verified.** One live call, `gpt-4o-mini-2024-07-18`, no `400`: the nullable `color_secondary` union and the `minimum`/`maximum` bounds — the two constructs this paragraph named as the things to suspect — were both accepted, and the response passed `validate_tag_dict` with no errors and no coercions. Two limits on that, recorded in `03-AI-CONTRACTS.md` rather than glossed: the model returned a *value* for `color_secondary`, so the null branch of that union has still never been emitted, and one image says nothing about accuracy. Making the call before wiring up the background task was the right order and stays the advice for 1.2 and 1.3.

### 1.2 Validation and retry — **split into 1.2a and 1.2b**

Task 1.1 handed this task five things, four of which are decisions rather than implementations, and they belong to two different arguments in two different modules. Splitting on the boundary `DECISIONS.md` 028 already drew — `enums.py` decides what is valid, `vision.py` decides what to do about it — gives each half one argument, one commit and one orientation.

**Lettered rather than renumbered, deliberately.** Inserting a task and shifting 1.3–1.11 would rewrite around ninety cross-references, and a good number of them are *statements about the past* — "found at task 0.7 and assigned here", "amended before task 1.2", "deferred to 1.3". Renumbering would make those sentences false rather than stale, which is the worse of the two failures (`CONVENTIONS.md`, on tidying). Every existing reference to "task 1.2" still resolves: 1.2 is the umbrella and both halves are inside it. **They are two tasks for the purposes of the one-commit-per-task rule.**

#### 1.2a — Category-dependent validation, in `enums.py`

One question: **what does the closed vocabulary consider valid, given the category the value arrived beside — and what does an invalid value become?**

**The gap is one rule with three instances — `DECISIONS.md` 084.** `validate_tag_dict` tests membership in a flat vocabulary and never tests appropriateness, so a legal member sitting beside a category it cannot describe passes with no error and no coercion:

- `{"category": "top", "layer": "standalone"}` — found by mutation at 1.1. `layer` is what the stylist's layering rule keys on, so the resulting look is silently wrong rather than visibly invalid. `PATCH /items/{id}` runs the same validator (030), so a hand-built body reaches it too.
- `{"category": "top", "subcategory": "tank", "fit": "skinny"}` — observed on a real image. `skinny` is a trouser word.
- `length` is the third candidate. 029 accepted the risk on the premise that "the vision model does not offer `maxi` for a t-shirt", and that premise is falsified by the second bullet; the entry is amended.

The shape of a fix already exists in the file twice — `SUBCATEGORIES` for `subcategory`, the bottoms-only gate for `rise` — so this is not new machinery. But the mappings are not equally writable. `layer`'s is close to total. `fit`'s is fuzzy, and a fuzzy allow-map manufactures false coercions; a per-category **deny** list is a smaller and more defensible claim there. **Decide the mechanism once and record which of the three fields opt in, including the ones that do not.**

**082's open question is part of this and is a decision, not a deferral.** What a `top` tagged `standalone` *becomes* is the whole content of the fix — `base` is a guess wearing a correction's clothes. **"The asymmetry stays" is an acceptable answer** and has to be chosen and written down as one.

**Two things to check before you start.** `02-DATA-MODEL.md` is authoritative over `enums.py` and the copy is made by hand, so any vocabulary change lands there first. And if the rules become data the UI needs — 1.9's tag editor has to populate a `fit` select for the chosen category — then `enums.ts` becomes a **fourth** hand-maintained copy, with nothing comparing any of them. Decide whether the rules stay server-side before you write them.

Unit tests: every new rule, both directions, per category. No AI, no database — the property 028 bought for this module.

**Settled. All three fields opted in, and the mechanism is one rule rather than three.** A category-dependent check is a pair — which values the category admits, and what the category says the answer is when the value is not admitted — so it coerces where the category determines an answer and errors where it does not. `DECISIONS.md` 085 has the argument; `02-DATA-MODEL.md` carries the rules and is authoritative.

- **`layer`** — every category gets an admitted set and an answer. **`top` is the only category with no answer**, so a top tagged `outer` or `standalone` is an **error**, not a coercion: 082's open question is closed by refusing to guess rather than by picking `base`. An item can now finish `failed` where it previously finished `ready` with a wrong layer, and that trade is accepted in 085.
- **`fit`** — applies to `top`/`bottom`/`dress`/`outerwear` only, and three words are narrower than the field: `skinny` to bottoms, `wide` to bottoms and dresses, `bodycon` to everything but outerwear. Deliberately narrower than `03-AI-CONTRACTS.md`'s "trouser words" aside, which explained one jacket rather than stating a rule.
- **`length`** — applies to everything but `bag` and `accessory`; sleeve words to `top`/`dress`/`outerwear`, hem words to `bottom`/`dress`/`outerwear`. **The middle five stay unenforced** — `crop`, `regular`, `longline`, `ankle`, `full` describe more than one axis each. 029 is closed by this and by the `fit` rows.
- **The rules stay server-side.** `enums.ts` mirrors values, not rules — see 1.9 for what the editor does instead.
- **`CATEGORY_DEPENDENT_FIELDS` is exported from `enums.py`** and is five fields; `030` is amended and 1.4 reads the list rather than restating it.

#### 1.2b — `validate_tags` and retry, in `vision.py`

`validate_tags(raw) -> ItemTags` implementing every check and coercion in `03-AI-CONTRACTS.md`, against the rules 1.2a settled. Exactly one retry on failure, naming the violation. Second failure raises `TaggingError`. This is where `ItemTags` is defined.

Unit tests: every coercion path, every rejection path, the retry, and the give-up. No AI calls in these tests.

**This task also renders 1.2a's rules into the prompt, and it is the only task that opens `vision.py` this stage.** `_vocabulary_block()` currently prints `fit` as nine words with no category guidance, so the model is never told that `skinny` is a trouser word — every instance is a silent coercion nobody learns from, which is half of what `DECISIONS.md` 084 complained about. The tables are public in `enums.py` for exactly this: `FIELD_APPLIES_TO`, `VALUE_APPLIES_TO` and `LAYERS_BY_CATEGORY` render the same way `SUBCATEGORIES` already does, so prompt and validator cannot disagree (080's property, extended to the rules rather than only the values). A prompt is not a guarantee — 082 — so this reinforces the validator rather than replacing it.

**One knock-on to record when it lands:** this changes the live prompt, so 1.11's baseline must record a prompt version alongside the model id.

**`top` is the one new retry trigger.** It is the only category-dependent rule that produces an error rather than a coercion, so it is the only one that reaches `TaggingError`. Test the give-up against it specifically: a model that answers `standalone` for a top twice ends `failed`, which is a path no other rule in the vocabulary can reach.

Three things arrived from 1.1 that belong here rather than in 1.2a, because each is about what the *service* does with the report:

**1. A coerced value leaves no record, and it is a separate problem from 1.2a's.** `fit: "flared"` came back on a real pair of jeans — a value in no vocabulary. The membership check worked and coerced it to null, exactly as designed. What is missing is any trace: `TagValidation.coerced` carries the discarded value at validation time and nothing persists it, so a garment attribute the model observed is dropped, the item screen shows an empty field, and nobody learns the vocabulary was short a word. Logging it is this task's; persisting it — `items.attributes` is a `JSONB` column that exists for exactly this — is 1.3's. **At minimum, log the coercion with the field and the rejected value**, or 1.11 has nothing to mine but nulls.

**2. The null `color_secondary` branch has still never been emitted.** Strict mode accepted `{"type": ["string", "null"], "enum": [...]}` as a schema at 1.1, but every live response so far returned a colour. This task reads that field constantly. Either produce a real null from the API and say so, or state plainly in `03-AI-CONTRACTS.md` that the null branch of the only nullable enum in the schema remains unproven.

**3. The `confidence < 0.35` rule has no owner and no settings field.** `DECISIONS.md` 028 describes the comparison as being made "against `settings`" and no such field exists; `05-FRONTEND-SPEC.md` names no review surface; no stage file mentions confidence. Decide here whether `validate_tags` implements it — and if it does, add the setting. **Know what it is worth first:** eight live responses at 1.1 returned `confidence: 0.9` every time, including both wrong ones, so the threshold would have flagged nothing in eight images. It is a fluency signal, not an accuracy signal.

**Settled. `DECISIONS.md` 086 and 087.**

- **The signature was wrong in three documents.** `validate_tags(raw)` cannot make the second call the retry is, so it is `async validate_tags(raw, image_url)` and `tag_item` gained `correction`. No third function: `TaggingError` means the model answered unacceptably, a `ValueError` or provider error means no answer arrived, and 1.3 wants both — so 1.3 wraps the first call itself.
- **A new row in `03`'s table.** The eleven fields the schema types with no `null`, absent or `null` — or a blank `display_name` — are a retry, then a `TaggingError`. It lives in `vision.py`, not `enums.py`, because `PATCH` must keep sending partial bodies. Without it `{}` is a clean report and `ItemTags` is a `TypeError` escaping a background task.
- **`ItemTags` is a frozen dataclass** typed with the vocabulary classes, and carries the **accepted** answer's `coerced` and no others. Every attempt's coercions are logged with field, value and category; that log is what 1.11 mines.
- **No confidence branch and no setting.** Both sides of the comparison produce `status='ready'`, so the branch could only set a flag nothing reads. 028 is struck where it said otherwise. The value is still persisted and still mined.
- **The prompt renders the rules** — applicability and narrowed words for `fit`/`length`/`rise`, the admitted set for all seven categories on `layer`. Not the answers, and not the five unenforced `length` words. `PROMPT_VERSION` is a hash of the rendered prompt.
- **Seventeen mutations, all caught**, baseline green at both ends. The finding is in `06-TESTING-STRATEGY.md`: the 1.1 placeholder guard does not defend the shipped prompt file, only the guard's logic.

### 1.3 Background tagging
Wire `BackgroundTasks` into `POST /items/upload`. One task per item. On success, update the row to `ready` with tags and `display_name`. On `TaggingError`, set `failed` with `error_message`.

**Three things 1.2b hands over, and the first is a trap if it is skimmed.** The background task calls **two** functions — `raw = await tag_item(url)` then `tags = await validate_tags(raw, url)` — and only the second raises `TaggingError`. The first raises `ValueError` on an unusable response and lets the provider's own exceptions escape, deliberately (`DECISIONS.md` 086): they say *no answer arrived*, where `TaggingError` says *the answer could not be accepted*. Both end `failed`; catch both, and write different `error_message` text so the two are distinguishable in the column. **An uncaught exception in a `BackgroundTask` leaves the row `processing` until the startup sweep**, which is the failure this note exists to prevent.

**`ItemTags.coerced` is the discarded values, and persisting them is this task's.** `items.attributes` is the `JSONB` column that exists for exactly this — a `fit` the model observed, correctly nulled because the vocabulary is short a word, and otherwise remembered by nothing (`DECISIONS.md` 084). They are the accepted answer's only; the rejected attempt's live in the log.

**Persist `vision.PROMPT_VERSION` beside them**, so a row tagged today can be traced to the prompt that tagged it. It is a hash of the rendered prompt and it moves whenever `enums.py` or the prompt file does (`DECISIONS.md` 087). 1.11 records it in `eval-results.md`; without it here, a row's tags cannot be attributed to a prompt after the next change.

Add a startup sweep that resets `processing` rows older than 10 minutes to `failed`.

**`items.updated_at` does not update itself — fix it here.** Migration `0001` gives the column `DEFAULT now()` and nothing more; PostgreSQL has no column-level `ON UPDATE`, and neither the model nor the migration installs a trigger. This task is the first in the project that writes to an existing row, so without a fix every tagged item keeps the `updated_at` it was inserted with, and 1.4's `PATCH`, soft `DELETE` and `retag` all inherit the same staleness. The one-line fix is `onupdate=text("now()")` on `Item.updated_at`: it is a Core-level default, so it applies to ORM flushes and to `update()` statements alike, but **not** to raw `text()` SQL or to anything run in `psql`. If database-level truth is wanted instead, that is a trigger and it needs its own migration. Found at task 0.7, which writes the column correctly on insert and never updates a row, and assigned here rather than pre-built there.

**The upload route is a synchronous `def`** (`DECISIONS.md` 049). `BackgroundTasks` accepts both sync and async callables, so `tag_item` being `async` is fine — but a sync background function would run in the threadpool and an async one on the event loop, which matters because the OpenAI call is the long pole.

### 1.4 Item endpoints
`PATCH /items/{id}` with full closed-vocabulary validation, setting `user_edited=true`. `DELETE` as soft archive. `POST /items/{id}/retag` with the `409` / `?force=true` behaviour. `GET /items/stats`.

**Two things 1.2a changed under this task, both in `DECISIONS.md` 030's amendment.**

- **The category change clears five fields, not three** — `subcategory`, `rise`, `layer`, **`fit`** and **`length`** — and the list is `CATEGORY_DEPENDENT_FIELDS`, exported from `app/enums.py`. Read it; do not restate it. A field that gains a category rule in the vocabulary and not in this route is silent data loss on a `200`.
- **A `PATCH` against a row that is still `processing` can now be a `422` where it used to be a `200`.** A processing row has every tag `NULL`, including `category`, and a category-dependent field cannot be validated without one, so `PATCH {"fit": "slim"}` on a processing item answers `422` naming `fit`. That is correct — whether a silhouette is meaningful is undecidable without the garment's category — but it is new, it is reachable from a failed tile's "Add manually" link, and it is the kind of thing that reads as a bug the first time it is met. `05-FRONTEND-SPEC.md` does not open the editor on a processing item, so the practical exposure is API clients and the retry path.

**One line 1.3 deliberately did not write.** `retag` re-queues `tag_and_store` against a row that may already be `failed`, and `_store` does **not** clear `error_message` on a successful write — at 1.3 a row is only ever `processing` when the task runs, so the line would have been dead code (`DECISIONS.md` 088). Clear it here, or a retagged item comes back `ready` on the wire still carrying the message that explains why it failed last time. `ItemResponse` exposes `error_message`, so this is visible to a client, not only in the table.

**One property of retag is not defended by a test, and it is named rather than left to be assumed.** The `db.commit()` before `background_tasks.add_task` is load-bearing in production — `tag_and_store` opens its own session and cannot see an uncommitted row — and it cannot be asserted under `conftest.py`'s fixtures, where the route's session *is* the test's session and the task is recorded rather than run. A test would pass with the commit removed. The mitigation is that the same line is already required by `POST /items/upload`, where `_insert` commits for the same reason.

**Two `GET /items` tests are written at the *start* of this task, before any of the above.** Both defend behaviour 0.7 shipped, both are cheap, and both are what 1.5 and 1.7 then build on.

- **`include_archived`.** Archived rows are excluded unless the parameter is passed (`DECISIONS.md` 051). This task is the first in the project to create an archived row, so it is the first that can test the exclusion at all. Without it, a `DELETE` that soft-archives correctly and a `GET` that silently stopped filtering are indistinguishable from the client — the symptom is that `DELETE` appears to do nothing.
- **The `status` filter.** `?status=processing` really narrows the result set. The only test today is `test_rejects_a_status_filter_outside_the_closed_vocabulary`, which proves a bad value is a `422` and says nothing whatever about filtering. **Ownership is 1.7's** — the polling loop is what depends on it — and it is written here because 1.7 is a frontend task and because the defence should exist before the two tasks that lean on it.

### 1.5 Wardrobe grid
`WardrobeStore` with the signals from `05-FRONTEND-SPEC.md` that this task has a consumer for — not the whole sketch; `05` §State management records which and why. Responsive grid — 3 columns at 390px, 5 on desktop. Dimmed-photograph tiles for `processing`, warning tiles for `failed` with a working retry button. Empty state with **one** CTA, **Add your first items**, inert until 1.6 wires it to the upload sheet.

**Amended at 1.5: "both CTAs" was one CTA and one open question.** The second — **Try a demo wardrobe** — has no mechanism and cannot have one on this screen, because `/wardrobe` is authenticated and the link means switching accounts, which `04-API-SPEC.md` has no endpoint for. It moves to `/login` as prefilled `demo@bijoux.app` credentials, which is `AUDITS.md` **O-12** against task 1.10. `05` line 103 is corrected in the same commit. The audit found this as O-4, now closed.

**A `failed` tile cannot assume the item has no tags.** Task 1.4's retag puts an already-tagged row back to `processing` without clearing the tag columns, and a retag that fails leaves them in place — so a `failed` item may arrive with a full set of tags from the last time it worked, and it may equally arrive with none, on an item that never succeeded. Render the warning state from `status`, never from "the tags are null". `DECISIONS.md` 089.

**`GET /items`'s `limit` is this task's to defend.** `05-FRONTEND-SPEC.md` requires the store to pass an explicit `limit`, because filters are client-side over the loaded collection while the parameter defaults to 100 and a realistic wardrobe is 80–150. Nothing asserts either end of that today. Test both: the default that applies when no `limit` is passed, and that a value above the documented cap of 200 is a `422` rather than a silently clamped page. The failure this catches is the one `05-FRONTEND-SPEC.md` already names — a filter bar quietly filtering over the first hundred items and reporting wrong counts, with no error anywhere.

### 1.6 Upload sheet
Bottom sheet with both inputs — `capture="environment"` for the camera, `multiple` for the gallery. Local previews via `URL.createObjectURL` before the response returns. The sheet stays open after a camera capture so the next garment can be shot immediately.

The tip line — *"Best results: lay the item flat or hang it against a plain wall"* — is part of the feature, not decoration. Tagging accuracy depends on it.

**This task owns both entry points into the sheet, and the stage file did not say so until now.** The empty state's **Add your first items** ships inert at 1.5 and is wired here; the **+ Add items** FAB in `05-FRONTEND-SPEC.md`'s wardrobe mockup is built here too. `05` line 111 and `DECISIONS.md` 090 both assigned the pair to this task while this file named neither, which left what gets built governed from the side. The FAB is not decoration: the empty state's CTA renders inside the `isEmpty()` branch and disappears after the first upload, so without a second control the sheet is reachable exactly once per account.

**The acceptance list's first line was false before this task and is corrected in its commit.** It asked for skeleton tiles; `DECISIONS.md` 091 replaced those with the dimmed photograph at 1.5 and amended `05`'s legend only. `01-ARCHITECTURE.md`'s flow 1 carried the same stale claim and is corrected with it.

### 1.7 Polling
Poll `GET /items?status=processing` every 2 seconds while any item is processing. Stop when the set empties. Hard stop after 3 minutes, marking the rest failed in the UI.

**This task owns two backend behaviours; one of them was already written at 1.4.**

The **`status` filter** is 1.4's to write and this task's to depend on. A filter that silently stopped filtering would never let the result set empty, so the loop would run to the 3-minute hard stop and the fault would present as slow tagging rather than as a broken query — which is exactly the kind of failure the hard stop is good at disguising.

**A batch tags serially, and this is the task that will notice.** Starlette awaits one response's background tasks in order, so task 1.3's "one task per item" means twenty uploaded files are twenty tagging runs end to end, not twenty at once. Five photographs — the stage's acceptance criterion — comfortably finish inside the poll window; twenty do not, and the symptom is a poll loop that empties slowly and in upload order rather than all at once. That is expected behaviour, not a fault, and the 3-minute hard stop is what bounds it. `asyncio.gather` over the batch is the fix if it ever matters and was deliberately not built at 1.3: it multiplies concurrent OpenAI calls and changes the failure isolation from one item to the batch. `DECISIONS.md` 088.

The **`created_at DESC, short_id` ordering** (`DECISIONS.md` 051) is untested and is this task's to write. `now()` is the transaction timestamp, so every row of one upload shares a `created_at` to the microsecond and the `short_id` tiebreak is the only thing making the order total; without it a page can repeat or drop rows. The symptom is tiles changing places between two polls, which reads as a grid bug and sends you to the wrong file.

### 1.8 Filters
Category chips, colour swatches, formality and warmth ranges. Client-side over the loaded collection. Filter state reflected in the URL so a filtered view can be shared and reloaded.

### 1.9 Item detail and tag editor
Full-size image, tags as chips, wear stats placeholder. The editor uses a select per field bound to the closed vocabulary — **never a free-text input**. Show a "You edited this" badge when `user_edited` is true.

**If 1.2 implemented the `confidence < 0.35` review flag, this screen is where it renders** — `05-FRONTEND-SPEC.md` names no surface for it and `03-AI-CONTRACTS.md`'s table row assumed one existed. If 1.2 decided not to build it, that decision is why there is nothing here, and this line is the reason a reader will not go looking. Either way, do not render `ai_confidence` as a quality score: eight live responses at 1.1 returned `0.9` including two wrong answers, so a number shown beside a tag would tell a user the opposite of the truth.

**Changing the category select clears and re-prompts for `subcategory`, `rise`, `layer`, `fit` and `length` — all five, not `subcategory` alone.** The server nulls whichever of them the request does not supply (`DECISIONS.md` 030, amended at 1.2a), so an editor that only repopulates the subcategory select silently loses the other four on a `200`. The user must see five empty fields before saving. It was three fields until task 1.2a gave `fit` and `length` category rules of their own.

**A `PATCH` against a row that is still `processing` can be overwritten seconds later, and nothing detects it.** The background task holds no lock and checks no status: when it finishes it writes every tag column, so an edit saved while the tile was still spinning is silently replaced by the model's answer — and `user_edited` stays `true` on a row whose values are no longer the user's. It is documented rather than guarded (`DECISIONS.md` 089), and the guard is here: **do not open this editor on a `processing` item.** `05-FRONTEND-SPEC.md` already does not, and the reason it must not is this. The exposure that remains is API clients and the "Add manually" link, which opens on a `failed` tile where no task is in flight.

**The vocabulary's category rules are server-side, and this screen is what pays for that.** `enums.ts` mirrors the *values* only — the decision and its cost are `DECISIONS.md` 085 and they are inherited here rather than reopened. The consequence is concrete: the `fit` select can offer `skinny` while the item is a tank top, and saving it returns `422` naming `fit`. Two acceptable ways to handle that, and **it is this task's choice which**: render the server's message against the field, or filter the select client-side from a hand-written copy of the rules — which would be a second copy in a second language with nothing comparing them, the failure `CONVENTIONS.md` records three times over. The reason there is no third option is that no endpoint publishes the vocabulary; adding one needs `04-API-SPEC.md` changed first, since that document forbids inventing endpoints.

### 1.10 Seed script
`scripts/seed_demo.py` creating `demo@bijoux.app` with 40 pre-tagged items, `status='ready'`, no AI calls. Images uploaded to Cloudinary once and their `public_id`s committed in the script.

Cover every category, a spread of formality 1–5 and warmth 1–5, and enough variety that the stylist has real choices. **This script is what makes the project demonstrable.** Do not leave it for later.

### 1.11 Golden dataset
30 hand-labelled photos in `tests/fixtures/golden/`. Include deliberately hard cases. Write `test_vision_accuracy_on_golden_set` marked `eval`, run it once, and record the result in `docs/eval-results.md`.

This is the first accuracy datapoint. Every prompt change from here gets measured against it.

**`fit` is the field to look at, and there is a prior from task 1.1 — eight images, which is a prior and not a result.** One HEIC plus seven JPEGs run out of curiosity before this dataset existed:

```
black tank top        top/tank       fit=None      conf 0.9
black bodysuit        top/bodysuit   fit=bodycon   conf 0.9
blue flared jeans     bottom/jeans   fit=flared    conf 0.9   <- not in the vocabulary
black wide leg jeans  bottom/jeans   fit=wide      conf 0.9
white tank top        top/tank       fit=skinny    conf 0.9   <- legal, meaningless
brown slingback heels shoes/heels    fit=None      conf 0.9
black slingback heels shoes/heels    fit=None      conf 0.9
```

Three things to carry in, and one to be careful about:

- **The nulls did not cluster cleanly.** Both heels are `None`, consistently — which looks like genuine non-applicability. But `top/tank` appears twice with two different answers, `None` and `skinny`, and a missing vocabulary word would have produced `None` both times. So the shoes/bags reading is supported and the tops reading is undercut by the only repeated pair in the sample.
- **Measure the two failures separately.** A `fit` that is out of vocabulary (`flared`) is a vocabulary gap; a `fit` that is in vocabulary and wrong for its category (`skinny` on a tank) is `DECISIONS.md` 084's gap. Counting them together produces one uninterpretable number.
- **Mine `display_name` as well as `fit`.** `flared` was discarded from the structured field and appears to have survived in the free-text one, so the words the vocabulary is missing may be recoverable from rows already written rather than only from nulls.
- **Be careful with the prior.** Eight images, no hand-labels, and chosen by whatever was to hand. If the golden set contradicts it, the golden set is right.

**Build repeated `(category, subcategory)` pairs into the set deliberately, and decide how many before you start collecting.** This is the one design property of the dataset that cannot be added afterwards. A set of thirty distinct garments can measure **accuracy** — how often the model is right — and can never measure **consistency**, because consistency is only visible when the same question is asked twice. The eight-image prior is the worked example and it is why this line exists: two tank tops came back with two different `fit` values, `None` and `skinny`, and that disagreement is what falsified the "the model returns null when the vocabulary is short a word" reading. A single tank top would have supported it. **Absence has one explanation and reads as a pattern; disagreement has to be explained and cannot be waved away** — which makes consistency the cheaper signal, because one contradiction inside the set is conclusive where a rate needs a baseline to interpret. Report per-pair agreement alongside per-field accuracy.

**Record a prompt version with every run, not only the date and model id.** Task 1.2b renders 1.2a's category rules into the `{{VOCABULARY}}` block, so the prompt this dataset is measured against changes at least once before the first run. A curve measured against a prompt that moved underneath it is not reproducible, which is the same property 078 pinned the model for.

**It exists: `vision.PROMPT_VERSION`, a hash of the rendered prompt, added at 1.2b (`DECISIONS.md` 087).** Read it rather than typing one — it moves whenever `enums.py` or the prompt file does, which a hand-written version does not. **Two things to measure that only this dataset can.** Whether the rendered rules helped at all: 1.2b made the prompt about 40% longer and nothing measures whether more instruction is more to ignore, so the `fit` numbers before and after are the only evidence that will ever exist. And whether the null `color_secondary` branch is real — **eight live responses so far and not one has emitted it**, so thirty photographs including deliberately plain garments settle a question `03-AI-CONTRACTS.md` has been carrying open since 1.1. Record the answer there either way.

If the answer is the vocabulary, note where the fix lands and how exposed it is: **`02-DATA-MODEL.md` first, `enums.py` second, `enums.ts` third, all by hand, with nothing comparing any of them.** That is the seam the generated schema at 1.1 moved rather than closed, and the one place in this project where a change has to be made three times correctly.

The prompt also licenses a null `fit` without ever saying when one is appropriate, unlike `rise` and `color_secondary`, which have explicit rules — the cheapest thing to change first if the answer turns out to be the prompt.

**Run the golden set twice — once on the pin, once on `gpt-5.4-mini-2026-03-17` — and record both.** Task 1.1 kept `gpt-4o-mini-2024-07-18` deliberately and deferred the model question here, because before this dataset exists the comparison is taste and after it exists it is a number (`DECISIONS.md` 078). Report the same per-field metrics for both, note the cost difference, and re-pin if the newer model wins — which is one constant in `app/core/config.py`. Both runs go in `docs/eval-results.md` with their dates, model ids and prompt versions, and the losing run stays in the file: the comparison is the artefact, not just the winner.

---

## Acceptance criteria

- [ ] Uploading 5 photos shows 5 local previews within a second, replaced by 5 dimmed-photograph tiles when the `202` lands
- [ ] All 5 become `ready` with correct-looking tags within ~30 seconds, no page refresh
- [ ] A deliberately bad image ends as `failed` with a working retry button
- [ ] Filtering by category, colour, and warmth all return correct counts
- [ ] Editing a tag persists, sets `user_edited`, and survives a reload
- [ ] `retag` on an edited item returns `409` without `force`
- [ ] `seed_demo.py` produces a browsable 40-item wardrobe from nothing
- [ ] Golden-set category accuracy is recorded and ≥ 85% (target 90%)
- [ ] Integration tests cover cross-user isolation on every item endpoint

## Commit checkpoints

`feat(ai): vision tagging service` · `feat(core): category-dependent validation` · `feat(ai): tag validation and retry` · `feat(api): background tagging` · `feat(api): item crud and retag` · `feat(web): wardrobe grid` · `feat(web): upload sheet` · `feat(web): filters` · `feat(web): tag editor` · `chore: demo seed data` · `test: golden dataset and accuracy eval`

## If you fall behind

Cut, in this order: the stats endpoint and dashboard; the URL-reflected filter state; the list/grid toggle. Never cut the tag editor or the seed script.

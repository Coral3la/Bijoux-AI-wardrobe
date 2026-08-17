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

### 1.2 Validation and retry
`validate_tags(raw) -> ItemTags` implementing every check and coercion in `03-AI-CONTRACTS.md`. Exactly one retry on failure, naming the violation. Second failure raises `TaggingError`.

Unit tests: every coercion path, every rejection path, the retry, and the give-up. No AI calls in these tests.

**The layer rules are one-directional, and this task decides whether that is right.** Found by mutation at 1.1: `validate_tag_dict` forces `layer` to `standalone` for the standalone categories and to `outer` for outerwear, and never rejects a `standalone` where it is nonsense — so `{"category": "top", "layer": "standalone"}` validates with no error and no coercion. `layer` is what the stylist's layering rule keys on (`02-DATA-MODEL.md`), so a top mis-tagged `standalone` would sit silently outside base/mid/outer reasoning from Stage 2 onward. Structured Outputs cannot catch it — `standalone` is a legal enum member — and `PATCH /items/{id}` runs the same validator (030), so a hand-built body reaches it too. Either add the reverse rule here and say what it coerces to, or record that the asymmetry is deliberate. Do not leave it as it is without a sentence. **`DECISIONS.md` 082** holds the finding and is the number Stage 2 will cite either way.

### 1.3 Background tagging
Wire `BackgroundTasks` into `POST /items/upload`. One task per item. On success, update the row to `ready` with tags and `display_name`. On `TaggingError`, set `failed` with `error_message`.

Add a startup sweep that resets `processing` rows older than 10 minutes to `failed`.

**`items.updated_at` does not update itself — fix it here.** Migration `0001` gives the column `DEFAULT now()` and nothing more; PostgreSQL has no column-level `ON UPDATE`, and neither the model nor the migration installs a trigger. This task is the first in the project that writes to an existing row, so without a fix every tagged item keeps the `updated_at` it was inserted with, and 1.4's `PATCH`, soft `DELETE` and `retag` all inherit the same staleness. The one-line fix is `onupdate=text("now()")` on `Item.updated_at`: it is a Core-level default, so it applies to ORM flushes and to `update()` statements alike, but **not** to raw `text()` SQL or to anything run in `psql`. If database-level truth is wanted instead, that is a trigger and it needs its own migration. Found at task 0.7, which writes the column correctly on insert and never updates a row, and assigned here rather than pre-built there.

**The upload route is a synchronous `def`** (`DECISIONS.md` 049). `BackgroundTasks` accepts both sync and async callables, so `tag_item` being `async` is fine — but a sync background function would run in the threadpool and an async one on the event loop, which matters because the OpenAI call is the long pole.

### 1.4 Item endpoints
`PATCH /items/{id}` with full closed-vocabulary validation, setting `user_edited=true`. `DELETE` as soft archive. `POST /items/{id}/retag` with the `409` / `?force=true` behaviour. `GET /items/stats`.

**Two `GET /items` tests are written at the *start* of this task, before any of the above.** Both defend behaviour 0.7 shipped, both are cheap, and both are what 1.5 and 1.7 then build on.

- **`include_archived`.** Archived rows are excluded unless the parameter is passed (`DECISIONS.md` 051). This task is the first in the project to create an archived row, so it is the first that can test the exclusion at all. Without it, a `DELETE` that soft-archives correctly and a `GET` that silently stopped filtering are indistinguishable from the client — the symptom is that `DELETE` appears to do nothing.
- **The `status` filter.** `?status=processing` really narrows the result set. The only test today is `test_rejects_a_status_filter_outside_the_closed_vocabulary`, which proves a bad value is a `422` and says nothing whatever about filtering. **Ownership is 1.7's** — the polling loop is what depends on it — and it is written here because 1.7 is a frontend task and because the defence should exist before the two tasks that lean on it.

### 1.5 Wardrobe grid
`WardrobeStore` with the signals from `05-FRONTEND-SPEC.md`. Responsive grid — 3 columns at 390px, 5 on desktop. Skeleton tiles for `processing`, warning tiles for `failed` with a working retry button. Empty state with both CTAs.

**`GET /items`'s `limit` is this task's to defend.** `05-FRONTEND-SPEC.md` requires the store to pass an explicit `limit`, because filters are client-side over the loaded collection while the parameter defaults to 100 and a realistic wardrobe is 80–150. Nothing asserts either end of that today. Test both: the default that applies when no `limit` is passed, and that a value above the documented cap of 200 is a `422` rather than a silently clamped page. The failure this catches is the one `05-FRONTEND-SPEC.md` already names — a filter bar quietly filtering over the first hundred items and reporting wrong counts, with no error anywhere.

### 1.6 Upload sheet
Bottom sheet with both inputs — `capture="environment"` for the camera, `multiple` for the gallery. Local previews via `URL.createObjectURL` before the response returns. The sheet stays open after a camera capture so the next garment can be shot immediately.

The tip line — *"Best results: lay the item flat or hang it against a plain wall"* — is part of the feature, not decoration. Tagging accuracy depends on it.

### 1.7 Polling
Poll `GET /items?status=processing` every 2 seconds while any item is processing. Stop when the set empties. Hard stop after 3 minutes, marking the rest failed in the UI.

**This task owns two backend behaviours; one of them was already written at 1.4.**

The **`status` filter** is 1.4's to write and this task's to depend on. A filter that silently stopped filtering would never let the result set empty, so the loop would run to the 3-minute hard stop and the fault would present as slow tagging rather than as a broken query — which is exactly the kind of failure the hard stop is good at disguising.

The **`created_at DESC, short_id` ordering** (`DECISIONS.md` 051) is untested and is this task's to write. `now()` is the transaction timestamp, so every row of one upload shares a `created_at` to the microsecond and the `short_id` tiebreak is the only thing making the order total; without it a page can repeat or drop rows. The symptom is tiles changing places between two polls, which reads as a grid bug and sends you to the wrong file.

### 1.8 Filters
Category chips, colour swatches, formality and warmth ranges. Client-side over the loaded collection. Filter state reflected in the URL so a filtered view can be shared and reloaded.

### 1.9 Item detail and tag editor
Full-size image, tags as chips, wear stats placeholder. The editor uses a select per field bound to the closed vocabulary — **never a free-text input**. Show a "You edited this" badge when `user_edited` is true.

**Changing the category select clears and re-prompts for `subcategory`, `rise` and `layer` — all three, not `subcategory` alone.** The server nulls whichever of them the request does not supply (`DECISIONS.md` 030), so an editor that only repopulates the subcategory select silently loses `rise` and `layer` on a `200`. The user must see three empty fields before saving.

### 1.10 Seed script
`scripts/seed_demo.py` creating `demo@bijoux.app` with 40 pre-tagged items, `status='ready'`, no AI calls. Images uploaded to Cloudinary once and their `public_id`s committed in the script.

Cover every category, a spread of formality 1–5 and warmth 1–5, and enough variety that the stylist has real choices. **This script is what makes the project demonstrable.** Do not leave it for later.

### 1.11 Golden dataset
30 hand-labelled photos in `tests/fixtures/golden/`. Include deliberately hard cases. Write `test_vision_accuracy_on_golden_set` marked `eval`, run it once, and record the result in `docs/eval-results.md`.

This is the first accuracy datapoint. Every prompt change from here gets measured against it.

**Look at where `fit` nulls fall.** Task 1.1's single live call returned `fit: null` on a leather jacket, and one image cannot say whether that is the model declining honestly, the model ignoring a vocabulary it was given, or a vocabulary with no good member for outerwear — of the nine values, four are trouser words and three are dress words, leaving `relaxed` and `oversized`. Thirty images can discriminate: **if `fit` nulls cluster on outerwear, bags and accessories, the vocabulary or the prompt is the problem; if they spread evenly across categories, the model is.** The prompt also licenses a null `fit` without saying when one is appropriate, unlike `rise` and `color_secondary`, which have explicit rules — that is the cheapest thing to change first if the answer is the prompt.

**Run the golden set twice — once on the pin, once on `gpt-5.4-mini-2026-03-17` — and record both.** Task 1.1 kept `gpt-4o-mini-2024-07-18` deliberately and deferred the model question here, because before this dataset exists the comparison is taste and after it exists it is a number (`DECISIONS.md` 078). Report the same per-field metrics for both, note the cost difference, and re-pin if the newer model wins — which is one constant in `app/core/config.py`. Both runs go in `docs/eval-results.md` with their dates and model ids, and the losing run stays in the file: the comparison is the artefact, not just the winner.

---

## Acceptance criteria

- [ ] Uploading 5 photos shows 5 skeleton tiles within a second
- [ ] All 5 become `ready` with correct-looking tags within ~30 seconds, no page refresh
- [ ] A deliberately bad image ends as `failed` with a working retry button
- [ ] Filtering by category, colour, and warmth all return correct counts
- [ ] Editing a tag persists, sets `user_edited`, and survives a reload
- [ ] `retag` on an edited item returns `409` without `force`
- [ ] `seed_demo.py` produces a browsable 40-item wardrobe from nothing
- [ ] Golden-set category accuracy is recorded and ≥ 85% (target 90%)
- [ ] Integration tests cover cross-user isolation on every item endpoint

## Commit checkpoints

`feat(ai): vision tagging service` · `feat(ai): tag validation and retry` · `feat(api): background tagging` · `feat(api): item crud and retag` · `feat(web): wardrobe grid` · `feat(web): upload sheet` · `feat(web): filters` · `feat(web): tag editor` · `chore: demo seed data` · `test: golden dataset and accuracy eval`

## If you fall behind

Cut, in this order: the stats endpoint and dashboard; the URL-reflected filter state; the list/grid toggle. Never cut the tag editor or the seed script.

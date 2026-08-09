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

---

## Tasks, in order

### 1.1 Vision service
`services/vision.py` → `tag_item(image_url) -> dict`, using OpenAI Structured Outputs with the schema in `03-AI-CONTRACTS.md`, `detail: "low"`.

Prompt lives in `app/prompts/vision_system.md`. Enum lists are appended programmatically from `enums.py` so the two can never diverge.

Include the `USE_FAKE_AI` branch from day one, not as an afterthought — Stage 5 depends on it and retrofitting it is annoying.

**Settle the HEIC question before the first live call.** The `vision` transform is `f_auto`, and `f_auto` on a HEIC original delivered to a client that sends no `Accept` header is not confirmed to produce a format OpenAI can read — Cloudinary documents the fallback as the format given by the file extension, and these URLs have no extension (`DECISIONS.md` 046). Upload one HEIC through `upload_image`, fetch its `vision` URL with no `Accept` header, and check the `content-type`. If it comes back `image/heic`, change the `vision` transform to `f_jpg` and correct `07-DEPLOYMENT.md`. This costs two minutes here and is very hard to see through a `BackgroundTask`.

**The response schema is unverified until this task runs.** It was written against the documented strict subset but has never been sent to the API, so a `400` on the first live call is a schema problem, not a prompt problem — check the nullable `color_secondary` union and the `minimum`/`maximum` bounds first, and correct `03-AI-CONTRACTS.md` in the same commit. Make one live call with a single image before wiring up the background task; debugging a schema rejection through `BackgroundTasks` is considerably worse.

### 1.2 Validation and retry
`validate_tags(raw) -> ItemTags` implementing every check and coercion in `03-AI-CONTRACTS.md`. Exactly one retry on failure, naming the violation. Second failure raises `TaggingError`.

Unit tests: every coercion path, every rejection path, the retry, and the give-up. No AI calls in these tests.

### 1.3 Background tagging
Wire `BackgroundTasks` into `POST /items/upload`. One task per item. On success, update the row to `ready` with tags and `display_name`. On `TaggingError`, set `failed` with `error_message`.

Add a startup sweep that resets `processing` rows older than 10 minutes to `failed`.

**`items.updated_at` does not update itself — fix it here.** Migration `0001` gives the column `DEFAULT now()` and nothing more; PostgreSQL has no column-level `ON UPDATE`, and neither the model nor the migration installs a trigger. This task is the first in the project that writes to an existing row, so without a fix every tagged item keeps the `updated_at` it was inserted with, and 1.4's `PATCH`, soft `DELETE` and `retag` all inherit the same staleness. The one-line fix is `onupdate=text("now()")` on `Item.updated_at`: it is a Core-level default, so it applies to ORM flushes and to `update()` statements alike, but **not** to raw `text()` SQL or to anything run in `psql`. If database-level truth is wanted instead, that is a trigger and it needs its own migration. Found at task 0.7, which writes the column correctly on insert and never updates a row, and assigned here rather than pre-built there.

**The upload route is a synchronous `def`** (`DECISIONS.md` 049). `BackgroundTasks` accepts both sync and async callables, so `tag_item` being `async` is fine — but a sync background function would run in the threadpool and an async one on the event loop, which matters because the OpenAI call is the long pole.

### 1.4 Item endpoints
`PATCH /items/{id}` with full closed-vocabulary validation, setting `user_edited=true`. `DELETE` as soft archive. `POST /items/{id}/retag` with the `409` / `?force=true` behaviour. `GET /items/stats`.

### 1.5 Wardrobe grid
`WardrobeStore` with the signals from `05-FRONTEND-SPEC.md`. Responsive grid — 3 columns at 390px, 5 on desktop. Skeleton tiles for `processing`, warning tiles for `failed` with a working retry button. Empty state with both CTAs.

### 1.6 Upload sheet
Bottom sheet with both inputs — `capture="environment"` for the camera, `multiple` for the gallery. Local previews via `URL.createObjectURL` before the response returns. The sheet stays open after a camera capture so the next garment can be shot immediately.

The tip line — *"Best results: lay the item flat or hang it against a plain wall"* — is part of the feature, not decoration. Tagging accuracy depends on it.

### 1.7 Polling
Poll `GET /items?status=processing` every 2 seconds while any item is processing. Stop when the set empties. Hard stop after 3 minutes, marking the rest failed in the UI.

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

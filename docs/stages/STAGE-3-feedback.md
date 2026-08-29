# Stage 3 — Saving, Feedback and Wear Tracking

**Week 4, first half. Target: 3 days.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

Turn one-off suggestions into a system that accumulates information about what the user actually likes and actually wears.

## This is the designated cut line

If the schedule has slipped, cut this stage down to task 3.2 alone — saving a look, roughly two hours of work — and move directly to Stage 4. Trip packing is the signature feature and must not be sacrificed for this one.

What is lost by cutting: the personalisation loop and the wardrobe-usage statistics. Both are good; neither is what makes the project memorable.

## Prerequisites

Stage 2 acceptance criteria pass.

## Out of scope for this stage

No trips. No recommendation model trained on feedback — feedback is fed back as **text in the prompt**, nothing more.

---

## Tasks, in order

### 3.1 Migration 0004
`looks.feedback`, `looks.worn_at`, `items.wear_count`, `items.last_worn_at`.

**Built, and it carries two things this line did not name.** `AUDITS.md`
**O-25**'s two deferred indexes — `idx_looks_user_id` and
`idx_look_items_item_id` — are in `0004` because Stage 3 has one migration and a
second would renumber `0005_trips`; `02-DATA-MODEL.md` prints both before the
migration builds them, which was O-25's own condition. And the `feedback` CHECK
is written as raw DDL, because `op.create_check_constraint` applies the naming
convention a second time and emits `ck_looks_ck_looks_feedback_values`.
`FEEDBACK_UP` and `FEEDBACK_DOWN` live in `app/models/look.py`; **3.3 imports
them** rather than spelling `Literal[-1, 1]`. `DECISIONS.md` 181.

### 3.2 Save a look
`PATCH /looks/{id}` accepting `is_saved` and `title`. `GET /looks?is_saved=true`. A heart button on the look card and a saved-looks list screen.

**If cutting this stage, this task alone is what you keep.**

**Built.** `SuggestedLook` became `LookResponse` and is now what all three
`/looks` endpoints answer with — `04-API-SPEC.md`'s `GET /looks` and
`PATCH /looks/{id}` were a heading and a one-line body before this task and are
written out now. `feedback` is refused by the PATCH schema until 3.3, which
**3.3 changes in `LookUpdate` and in `LookResponse` together**. The screen is
`/saved`, backed by a new `LooksStore`, and **nothing links to it** —
`AUDITS.md` O-29. `GET /looks/{id}` and `DELETE /looks/{id}` are still
undocumented and unbuilt: **O-30**. `DECISIONS.md` 182.

### 3.3 Feedback
`PATCH /looks/{id}` accepting `feedback` as `1` or `-1`. Thumbs up and down on the look card. Optimistic UI update.

### 3.4 Wear tracking
`POST /looks/{id}/wear` with a date. In a single transaction: set `looks.worn_at`, increment `wear_count`, and update `last_worn_at` on every item in the look.

Idempotent per date — calling it twice for the same date must not double-count. Integration-test that explicitly.

An "I wore this" button on saved looks. Wear count and last-worn date on the item detail screen.

### 3.5 Feed preferences back into the prompt
Extend the stylist user message with a preferences block assembled from the user's history:

```
USER PREFERENCES (learned from saved and liked looks):
- Frequently chosen together: light_blue jeans + white shirts
- Liked: relaxed and oversized tops
- Disliked: bodycon fits
- Recently worn (avoid repeating): A3F9K2, 7BX1QM
```

Derived with plain SQL aggregation over `looks` joined to `look_items` — attribute frequency across looks with `feedback = 1`, and items worn in the last 3 days. No embeddings, no model training.

Guard: only include this block once there are at least 3 rated looks. Below that the signal is noise.

### 3.6 Wardrobe insights
Extend `GET /items/stats` with `never_worn`, `most_worn`, and cost-per-wear placeholders. A small insights panel on the wardrobe screen: *"34 items you have never worn."*

Cheap to build, and it is the moment the app tells the user something about themselves they did not already know.

---

## Acceptance criteria

- [ ] Saving a look persists it and it appears in the saved list
- [ ] Thumbs up/down persists and survives a reload
- [ ] "I wore this" increments `wear_count` on every item in the look, exactly once per date
- [ ] After 3 liked looks, the preferences block appears in the prompt — assert it in an integration test against the assembled message string
- [ ] Recently worn items are named in the prompt as items to avoid
- [ ] The insights panel shows a correct never-worn count

## Commit checkpoints

`feat(db): feedback and wear columns` · `feat(api): save and rate looks` · `feat(api): wear tracking` · `feat(ai): preference block in prompt` · `feat(web): saved looks screen` · `feat(web): wardrobe insights`

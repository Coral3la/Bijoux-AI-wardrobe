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
`FEEDBACK_UP` and `FEEDBACK_DOWN` live in `app/models/look.py`. This line said
**3.3 imports them** rather than spelling `Literal[-1, 1]`, and 3.3 found that
it cannot: `Literal[FEEDBACK_UP, FEEDBACK_DOWN]` runs under Pydantic and fails
`mypy`, because PEP 586 admits literal values and not names. The schema
transcribes the two numbers and a test compares them. `DECISIONS.md` 181, 183.

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

**Built, with three things this line did not name.** `feedback: null` **clears**
a rating — pressing the thumb already on withdraws it — because `NULL` is the
unrated state 3.5 counts against and a mis-tap would otherwise be permanent.
The optimistic update is **one path for every control**, so the heart became
optimistic too and `DECISIONS.md` 182 is superseded on that point. And the
`Literal[FEEDBACK_UP, FEEDBACK_DOWN]` that 3.1 promised does not type-check;
the schema transcribes `Literal[-1, 1]` and a test compares them. Thumbs are on
the **look card only** — `/saved` is deliberately out of scope. `DECISIONS.md`
183.

### 3.4 Wear tracking
`POST /looks/{id}/wear` with a date. In a single transaction: set `looks.worn_at`, increment `wear_count`, and update `last_worn_at` on every item in the look.

Idempotent per date — calling it twice for the same date must not double-count. Integration-test that explicitly.

An "I wore this" button on saved looks. Wear count and last-worn date on the item detail screen.

**Built, and three things this line did not name.** The idempotency it asks for
is **per the date the row currently holds**, which is as deep as one `DATE`
column can reach: Monday → Tuesday → Monday counts three wearings, and a test
asserts that number rather than leaving it to be discovered. `items.last_worn_at`
moves **forward only** — `GREATEST` — because 3.5 reads it to avoid recommending
something worn in the last three days. And the button is **the one control in
the application that is not optimistic**, a deliberate exception to
`DECISIONS.md` 183: wearing is not a toggle, the client cannot derive the new
`wear_count` for every garment, and there is no previous state to roll back to.
`DECISIONS.md` 184.

### 3.5 Feed preferences back into the prompt
Extend the stylist user message with a preferences block assembled from the user's history:

```
USER PREFERENCES (learned from rated looks):
- Liked: relaxed tops, oversized tops
- Disliked: bodycon dresses
- Recently worn (avoid repeating): A3F9K2, 7BX1QM
```

Derived with plain SQL aggregation over `looks` joined to `look_items` — fit frequency by category across liked and disliked looks, and styleable items worn on the requested day or either of the two calendar days before it. A fit signal appears only after it occurs in at least two qualifying looks; each sentiment is capped at three signals. Archived garments are excluded from both halves. No embeddings, no model training. `DECISIONS.md` 185.

Guard: only include this block once there are at least 3 rated looks. Both thumbs-up and thumbs-down count as ratings; below that the signal is noise.

### 3.6 Wardrobe insights
Extend `GET /items/stats` with `worn`, `never_worn` and `most_worn`. A small insights panel on the wardrobe screen: *"34 items you have never worn."*

Cheap to build, and it is the moment the app tells the user something about themselves they did not already know.

**Cost-per-wear is struck from this line rather than deferred.** It asked for a
third field the project has nowhere to get: there is no price column,
`02-DATA-MODEL.md` lists purchase price as a future `attributes` key that
nothing writes, and a placeholder would put a fabricated number on a dashboard
whose whole purpose is to tell the user something true about themselves.
`04-API-SPEC.md` never carried it, so the contract loses nothing here.

**The backend half is built and the panel is not** — this task ships in two
commits, and the second one is a separate task. `GET /items/stats` reads
`items.wear_count` now; `most_worn` narrowed from the array `04-API-SPEC.md`
had printed since Stage 0 to one object of three fields, or `null` when nothing
has been worn. **`worn` is a third field this line did not ask for**, added
because *"34 items you have never worn"* invites *of how many?* and no number
already in the response answers it: all three are scoped to `ready` rows, one
filter narrower than the counts beside them, so **`total` minus `never_worn` is
not the number of items worn** — `worn` is, and it partitions that population
with `never_worn` in one statement. Swimwear and sleepwear are counted, because
the stylist's exclusion is not the dashboard's. Ties break on `short_id`. The
endpoint is still consumed by no screen — `AUDITS.md` **O-16** holds until the
panel lands. `DECISIONS.md` 186.

**The panel landed, and the paragraph above stops being true with it.** The
second commit is `features/wardrobe/wardrobe-insights.ts`, between the weather
strip and the pending strip, reading `GET /items/stats` through a new
`ItemsApi.stats()` and holding no store — it fetches for itself once on
construction, the way the weather strip does. **`worn` is what the required
line counts against**: the copy is *"34 of your 136 tagged items have never been
worn"*, where 136 is `worn + never_worn` and never `total`, because the wear
numbers are `ready`-scoped and a header saying *138 items* sits three rows
above it. **Three states print no count at all**: with
nothing worn the panel does not render at all, with nothing unworn it says so in
a sentence rather than printing a zero, and a failed request removes it
silently. **`AUDITS.md` O-16's `/items/stats` half is closed** — the endpoint has
a reader — and its seven-query-parameter half is untouched. `DECISIONS.md` 188.

### 3.4a Undo a wearing *(added 2026-09-02)*
An escape hatch for the one control 3.4 built deliberately non-optimistic. A tap on *"I wore this"* is destructive by two measures: it increments `wear_count` on every garment in the look and it moves `last_worn_at` forward, and both feed 3.5's *recently worn* line and 3.6's insights. An accidental tap silently distorts both, with no way back.

**New endpoint** — `DELETE /looks/{id}/wear`, guarded like `POST /looks/{id}/wear` (owner check, `IS DISTINCT FROM` on `worn_at` so a double-tap is a no-op): sets `worn_at` back to `NULL` and decrements `wear_count` by 1 on every item in the look, floored at 0.

**Open decision** — `last_worn_at`. There is no history table (`DECISIONS.md` 184), so on undo the true previous value is unknown. Two options for the task to resolve: (a) if `wear_count` becomes 0 set it to `NULL`, otherwise leave it — the column becomes an *upper bound* rather than a truth, and the recency window over-counts by up to three days per item; (b) recompute it from the max `worn_at` across the user's other looks that share this look's items — one query per item, correct at the cost of a join. The stage file records the choice when the task lands.

**Frontend** — the button on `/saved` prints a toast for ~5 seconds after a successful wear: *"Marked as worn today · Undo"*. The undo calls the new endpoint and, on success, restores the button to its pre-tap state through the same store path 3.4 wrote for the wear.

### 3.5a Soften the *recently worn* hint *(added 2026-09-02)*
Two changes to `learned_preferences` in `_stylist_shared.py`, one file, one paragraph of prompt output. Both routes that call it (`POST /looks/suggest` and `POST /trips/pack`) inherit both.

**Skip singleton categories.** Before naming an item as recently worn, count what else the user owns in that category. If the count is at most `SINGLETON_THRESHOLD` (start at 1; the task may raise it to 2), drop the item from the list — a hint the model cannot honour without leaving a slot empty is worse than no hint. Categories are the nine in `_CATEGORY_NAMES`; the count runs against `styleable_wardrobe`'s output, which is already in hand.

**Reword the line.** The current sentence is *"Recently worn (avoid repeating): ..."*, and 3.5's own paragraph notes that models over-index on it. Replace with something that ranks below style match — a first-cut candidate is *"Recently worn — prefer other items when the style match is comparable: ..."*. The exact phrasing is the task's to settle and to pin in a test against the assembled message string.

### 3.6a Browse the never-worn *(added 2026-09-02)*
A view-only extension of 3.6's insights panel. The panel already prints *"N of your M tagged items have never been worn"* — this task makes that number a link that opens the list behind it, so the user can act on it herself.

**Two shapes considered, the task picks one.** (a) A modal or expanded row on `/wardrobe` filtered to `wear_count = 0`, rendered with the same `item-card` the grid uses. (b) A URL such as `/wardrobe?never_worn=true` that reuses the grid with a filter chip, so the state is bookmarkable and the back button behaves. Either way, no new endpoint: `GET /items` already accepts filters, and `wear_count` becomes one of them.

**Not** a stylist change. The list neither hides nor promotes items to the suggester — it exists purely to answer the question *"which ones are they?"* that the count invites.

---

## Acceptance criteria

- [ ] Saving a look persists it and it appears in the saved list
- [ ] Thumbs up/down persists and survives a reload
- [ ] "I wore this" increments `wear_count` on every item in the look, exactly once per date
- [ ] After 3 rated looks, the preferences block appears in the prompt — assert it in an integration test against the assembled message string
- [ ] Recently worn items are named in the prompt as items to avoid
- [x] The insights panel shows a correct never-worn count
- [ ] `DELETE /looks/{id}/wear` reverses a wearing and the toast on `/saved` calls it — 3.4a
- [ ] A singleton-category item is not named in the *recently worn* line, and the reworded line is asserted against the assembled prompt — 3.5a
- [ ] The never-worn count on the insights panel opens a browsable list of those items — 3.6a

## Commit checkpoints

`feat(db): feedback and wear columns` · `feat(api): save and rate looks` · `feat(api): wear tracking` · `feat(ai): preference block in prompt` · `feat(web): saved looks screen` · `feat(api): wardrobe insights` · `feat(web): wardrobe insights`

Seven checkpoints for six tasks: **3.6 is two commits**, because the endpoint
and the panel are separate pieces of work and this list had one line for both.

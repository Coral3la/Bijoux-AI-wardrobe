# Stage 4A — Sets

**A short stage between Stage 4 and Stage 5. Target: 1 day.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

A **set** is two or more garments that were bought together or are worn
together — a matching top and bottom, a suit, a co-ord. Declare one, and the
stylist prefers to use its members together without ever being required to.

The items stay separate rows. A set is a **relation over them**, not a thing of
its own, and that is the whole design: the set's top must remain wearable with
other trousers, which is the requirement this feature exists to serve.

## Prerequisites

Stage 4's `4.1` to `4.18` are built. Nothing here depends on trips — the
dependency is Stage 1's `items` table and Stage 2's stylist, both of which have
been closed since before Stage 3.

## Out of scope for this stage

**Renaming a set after creation.** `item_sets.name` is written at `POST /sets`
and there is no `PATCH`. A user who wants a different name deletes the set and
declares it again, which costs two taps on a two-member set.

**A sets list screen.** There is no `GET /sets` and no `/sets` route. A set is
reached through a member, on the item detail screen, because that is where a
user is standing when they think about one.

**"Style around this set" as a multi-anchor request.** `POST /looks/suggest`
takes one `anchor_item_id` and it stays one. Anchoring on a whole set is a
second field, a second validation rule and a second failure shape, and the
preference in the prompt is what this stage is testing first.

None of the three is a placeholder here — not a disabled button, not a stub
route, not a `TODO`.

---

## Tasks, in order

### 4A.1 Schema and API

Migration `0007`: the `item_sets` table and the nullable `items.set_id` foreign
key, `ON DELETE SET NULL`. One-to-many — an item belongs to at most one set.
`02-DATA-MODEL.md` has the DDL.

The five endpoints from `04-API-SPEC.md`: `POST /sets`,
`GET /sets/{set_id}`, `DELETE /sets/{set_id}`, `POST /sets/{set_id}/items` and
`DELETE /sets/{set_id}/items/{item_id}`. Two new error codes, both `422` and
both named in `CONVENTIONS.md`: `set_item_unavailable` and `set_member_taken`.

`ItemResponse` gains `set_id`, so every item payload in the application carries
it — `GET /items`, the upload response, and the hydrated items inside every look
and every trip.

`services/serializer.py` writes the `set:<n>` token in the trailing extras, and
`prompts/stylist_system.md` gains **one** line under STYLING PRINCIPLES saying
what the token means. Both are specified in `03-AI-CONTRACTS.md`.

**No new validation rule.** `validate_look_response()` is untouched, and the
reason is in `03-AI-CONTRACTS.md` beside the rule list: a hard *all members or
none* rule refuses the legitimate look that wears the set's top with other
jeans, and a refusal burns the single retry and answers `502` — which is task
2.11's failure shape, met again one field along.

### 4A.2 Sets on the web

**Item detail — `/wardrobe/:id`.** A set row: the other members as thumbnails
that link to their own detail pages, the set's name where it has one, and the
two controls. **Add to this set** picks a garment from the wardrobe; **Remove**
takes the item on screen out of it. A garment in no set gets the same row in its
empty state, offering to declare one.

The removal that leaves one member behind **dissolves the set**, and the control
says so before it is pressed — the same rule `DELETE /sets/{set_id}/items/{item_id}`
enforces on the wire, said once to the user in the place where they can act on
it.

**Wardrobe grid — `/wardrobe`.** A badge on the tile of any item with a
`set_id`. The tile already renders from `ItemResponse` and `set_id` arrives on
it in 4A.1, so this is a marker and not a second request.

`05-FRONTEND-SPEC.md` § 4 is **this task's document** and is updated in this
task's commit, per `CONVENTIONS.md`'s definition of done. It is not touched by
the documents commit that opened this stage, because that commit changed no
screen.

---

## Acceptance criteria

- [ ] Two items declared as a set both answer with the same `set_id`, and the
      set reads back with both of them
- [ ] Adding a third item to the set answers with three members; adding an item
      that already belongs to another set is `422 set_member_taken`
- [ ] An item id that is another account's, archived, `processing`, `failed` or
      in an excluded category is `422 set_item_unavailable`
- [ ] Removing the second-to-last member deletes the set, and the last member's
      `set_id` reads `null`
- [ ] Deleting a set leaves both items in place with `set_id` null — no garment
      is deleted, archived, or otherwise changed
- [ ] Archiving a member changes no membership: the set still holds it, and the
      other members still name it
- [ ] The serialised wardrobe line for a set member ends in `set:<n>`, the same
      `n` for every member of one set and a different `n` for a second set
- [ ] A set with only one member in the wardrobe that was actually sent carries
      no token at all
- [ ] The stylist is never *required* to use a set: a look that wears one
      member and not the other passes validation

## Commit checkpoints

`docs: the sets feature` · `feat(sets): schema and api` · `feat(web): sets`

The first of the three is this stage's opening commit and carries no code.

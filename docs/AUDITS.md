# Audits

A documentation audit reads documents against the code and against each other,
looking for the contradictions no task happens to touch. It is not a task in
any stage.

**Every contradiction this project has found so far was found by accident** — a
task happened to need the line. Three documents printed `validate_tags(raw)`, a
signature that cannot hold a retry, and 1.2b found it only because 1.2b built
that function. What no task touches is not checked, which is what this file is
for.

**How to use it.** Each audit records the commit it read, what it scanned, what
it changed, and what it left open. The next audit **diffs against the last
one**: re-run the mechanical checks under *Checked and clean*, re-read the open
items to see which have been closed by work since, and scan something the last
audit named as out of bounds. Do not start over.

---

## 2026-08-18 — audit 1

**Commit read:** `afa5cef` — *feat(ai): validate_tags, the retry, and the rules in the prompt*
(`afa5cef19a136ef1c10645975894592067f6fabc`, 2026-08-18). Stage 1, tasks 1.1,
1.2a and 1.2b complete.

**Scanned:**

| Document | Read against |
|---|---|
| `03-AI-CONTRACTS.md` | `app/services/vision.py`, `app/enums.py`, `app/prompts/vision_system.md`, `app/core/config.py`, `app/services/storage.py`; `02`, `04`, `STAGE-2` |
| `02-DATA-MODEL.md` | `app/enums.py`, `app/models/item.py`, `alembic/versions/0001_initial.py`, `app/core/short_id.py`, `frontend/src/app/shared/models/enums.ts`; `03`, `04` |
| `04-API-SPEC.md` | `app/api/v1/routes/items.py`, `routes/auth.py`, `app/schemas/item.py`, `schemas/auth.py`, `schemas/user.py`, `app/core/errors.py`, `core/deps.py`, `core/security.py`, `app/main.py`; `02`, `03`, `05`, `07`, `CONVENTIONS`, all stage files for endpoint ownership |
| `stages/STAGE-1-wardrobe.md` §1.3–1.5 | `vision.py`, `enums.py`, `items.py`, `models/item.py`; `02`, `03`, `04`, `05`, `DECISIONS` 030 / 084–087 |

**Six fixes applied in place. Eleven items left open** — every one of them is
either a disagreement where both readings are defensible, or a question whose
answer changes what gets built. Those are the developer's.

---

### Fixed in place

**F-1 · `03` printed the pre-1.2b system prompt.** The block under *System
prompt* was a transcription of `app/prompts/vision_system.md` and had not moved
when 1.2b edited the file. It still carried the `rise` bullet —
*applies only when category is "bottom". Otherwise return null.* — and glossed
`standalone` as *(dresses, shoes, bags, accessories)*, where the file says
*(not layered at all)* and no `rise` bullet at all — because `_vocabulary_block()`
now generates both rules from `enums.py` (`DECISIONS.md` 087). Re-transcribed from the file, including
the `{{VOCABULARY}}` line, which the block had never shown even though it is the
token `_load_system_prompt()` raises on. *No side was picked: 087 recorded the
deletion deliberately and the document was simply not updated with it.*

**F-2 · `04` said the item response carries `user_id`.** "every column of
`items`" — `ItemResponse` has never had `user_id` and should not. Narrowed to
"every column except `user_id`".

**F-3 · `04` printed a thumbnail transform that does not match the one the
server emits.** `w_300,h_300,c_pad,b_white`, against
`w_300,h_300,c_pad,b_white,f_auto,q_auto` in both `storage.py` and
`07-DEPLOYMENT.md`'s table. This one has teeth: `DECISIONS.md` 046 requires the
frontend pipe and the backend builder to agree **byte for byte**, and a pipe
written from `04` would have produced a different URL — a second Cloudinary
cache entry and a silent double-fetch of every tile.

**F-4 · `04` claimed no stage file names any rate limit.** `STAGE-4` 4.4 does:
*"rate limit 10 packs per hour"*. The claim is narrowed to what is actually
true — nothing builds the counter, and the `upload` and `suggest` limits are
named by no task at all. See **O-5**, which is the part that is still open.

**F-5 · `02` said all tag fields are nullable; its own DDL says otherwise.**
`water_resistant` is `NOT NULL DEFAULT FALSE` in the DDL three lines above the
sentence, in migration `0001`, and in `app/models/item.py`. The consequence is
worth having written down rather than the sentence being tidied: on a
`processing` row the column reads as *not water resistant* rather than
*unknown*, and `ItemResponse.water_resistant` is `bool`, not `bool | None`.

**F-6 · `02` warned about Stage 3's inline columns and not Stage 4's.** The
`looks` DDL shows `trip_id UUID REFERENCES trips(id)`, and `trips` does not
exist until migration `0004`. The migrations table already said so; the
paragraph that exists to catch exactly this did not. A Stage 2 implementer
reading the DDL top to bottom would have written a foreign key to a missing
table.

---

### Open — the developer's to decide

Ordered by how soon the answer is needed.

**O-1 to O-11 are audit 1's.** Items numbered from **O-12** onward were opened
by a task rather than by an audit, and say so in their own text — the numbering
is shared so that nothing has two names, and the next audit reads them exactly
as it reads the rest. Two are closed so far: O-1 at task 1.4 and O-4 at 1.5.
**O-14 is the first that records an unverified surface rather than a
contradiction** — a thing no document disagrees about and nobody has looked at.
It was extended at 1.6 rather than duplicated, and **O-15** was opened by the
same task. **O-15 was answered at 1.8 rather than acted on** — the second
caller decided it does not want a sheet — and **O-16** was opened by the same
task. O-14 was extended again at 1.7 and at 1.8.

#### O-1 · ~~`POST /items/{id}/retag` and `DELETE /items/{id}` have no documented success response~~ — **closed at task 1.4**

`04` gives both endpoints a failure contract and no success contract: retag has
no status code and no body, `DELETE` says only "soft-deletes by setting
`is_archived = true`". `06-TESTING-STRATEGY.md` asserts the `409` and nothing
about the `200`. 1.4 will have to invent both.

There is a second, smaller hole in the same place: **the `409` has no error
code**, alone among every failure in the document, and `CONVENTIONS.md`'s
canonical code list carries `tagging_failed`, which no endpoint in `04` emits
and no code raises — tagging failures are written to `items.error_message` and
rendered as a tile, never as an error envelope.

**Recommendation.** Retag answers `202` with the full `ItemResponse`, `status`
back to `processing`; `DELETE` answers `200` with the full `ItemResponse`, not
`204`. Both for the reason 034 and 050 already settled twice: one shape for one
resource, so the client replaces a row rather than merging a special case, and
`202` because retag starts exactly the background work `POST /items/upload`
answers `202` for. A `204` would leave the client guessing at `updated_at` and
`is_archived`. For the `409`, `item_edited` — the codes in this project name the
condition, not the endpoint (`email_exists`, `file_too_large`,
`wardrobe_too_small`). **The name is yours to approve before it is written
anywhere.** `tagging_failed` should either be struck from `CONVENTIONS.md` at
1.4 or deliberately assigned to a synchronous retag; it cannot stay as a code
with no producer.

**Closed at task 1.4, and the recommendation was taken in full.** `PATCH` and
`DELETE` answer `200` with the full `ItemResponse`, retag answers `202` with
`status: "processing"`, and the `409` carries `item_edited`. `tagging_failed`
was struck rather than assigned: assigning it needs a synchronous retag, which
contradicts the `202`. The audit found two endpoints missing a success
contract; there were three — `PATCH` had none either — and all three are now
in `04`. One thing the audit did not reach: `04` also described `PATCH` as
validating *the request*, which passes a category change that leaves
`subcategory` and `rise` describing a different garment. That is corrected in
the same commit and is the finding 1.4 would not have made from the audit
alone.

#### O-2 · `03`'s validation table is missing three checks the validator performs — tasks 1.3 and 1.4

The table says it spans both layers. `validate_tag_dict` also errors on
`water_resistant` not being a boolean, `display_name` not being a string, and
`confidence` not being a number in 0–1. None appear. All three are unreachable
on model output — strict mode types them — and all three are live on
`PATCH /items/{id}`, which is 1.4's, and which reads this table as its
specification.

**Recommendation.** Add the three rows, all *retry once*, and extend the
sentence beginning "The first row, the third, and the new required-fields row
cannot fire on model output" to include them. Not applied here: the audit's
brief is stale claims, and this is a document that is silent rather than wrong —
adding rows to an authoritative spec is specifying, which is yours.

#### O-3 · ~~"Add manually" is promised to the user and owned by no task~~ — **closed at task 1.9**

`03`'s user-facing failure table (line 401) says a failed tile carries a
**Retry** button *and* an **Add manually** link. `STAGE-1` 1.4 reasons about a
`422` that is "reachable from a failed tile's 'Add manually' link". Nothing
builds it: 1.5 says "warning tiles for `failed` with a working retry button",
and `05-FRONTEND-SPEC.md`'s grid shows "⚠ = failed, tap to retry" and no second
affordance.

**Recommendation.** Give it to 1.9 in one line rather than cutting it: the tag
editor already exists there, and the failed tile only needs to open it. The line
must say **category first** — a failed row has every tag `NULL`, so any
category-dependent field submitted before `category` answers `422`, which is
precisely the trap 1.4 already documents. Cutting it instead would strand the
one class of item the product cannot otherwise recover: a photograph the model
cannot read at all.

**Closed at task 1.9, and the recommendation was taken — but it could not have been taken as written.** The link is the tag editor, reached from the failed tile, and the `category` note was right: a failed row has every tag `NULL`, so the editor's category select carries a placeholder that exists only while the stored value is null and refuses to save while it is selected (`DECISIONS.md` 123). What the recommendation did not know is that **the wire could not honour it at all.** `PATCH /items/{id}` wrote tags and never touched `status`, so an item recovered by hand answered `200` and kept its `failed` status and its `error_message` for good — the tile went on saying "Tagging failed" above a full set of tags the user had just typed. That is fixed in the commit before this one (`DECISIONS.md` 116) and it is the reason this item closes rather than shipping a link to a screen that could not finish the job. `05-FRONTEND-SPEC.md`'s grid legend gains the affordance in the same commit.

#### O-4 · ~~"Try a demo wardrobe" has no mechanism~~ — **closed at task 1.5**

`05-FRONTEND-SPEC.md` line 103 puts a **Try a demo wardrobe** link in the
wardrobe empty state "that loads the seeded 40-item account", and `STAGE-1` 1.5
says "Empty state with both CTAs". But `/wardrobe` is only reachable
authenticated, so the link means *switch to somebody else's account* — and `04`
has no endpoint for it and forbids adding endpoints that are not listed.

**Recommendation.** Move it to the login screen as prefilled demo credentials
and drop it from the empty state. No new endpoint, no new mechanism, one string
in `en.json` — and it is honest about what it does, where a link inside your own
empty wardrobe implies your wardrobe is about to fill up. The seeded account is
1.10's and its email is already fixed (`demo@bijoux.app`).

**Closed at task 1.5, and the recommendation was taken in full.** The empty
state ships one CTA and no demo link; `05-FRONTEND-SPEC.md` line 103 and
`STAGE-1` 1.5's "both CTAs" are corrected in the same commit. **Closing this
does not delete the affordance** — the login-screen half is carried forward as
**O-12** below, against 1.10, which is the task that creates the account it
would sign into. One thing the audit did not reach, found only by building the
screen: the *first* CTA has no mechanism either at 1.5, because the upload
sheet is 1.6's. It ships inert rather than absent or `disabled`, and the rule
that decides between those three is ownership rather than affordance —
`DECISIONS.md` 090.

#### O-5 · Two of the three rate limits are still unowned, and they are the two that spend money

Carried forward from task 0.7 and narrowed by **F-4**. `STAGE-4` 4.4 names the
trips limit. `POST /items/upload` (100 files/hour) and `POST /looks/suggest`
(30/hour) are named by no task. `STAGE-5` 5.2 lists rate limits among the
integration tests to write — a test for a mechanism nothing builds.

**Recommendation.** One small task at the top of Stage 2, before
`POST /looks/suggest` ships, building the in-memory counter and applying all
three limits. Stage 2 rather than Stage 5 because `suggest` sends the whole
wardrobe to OpenAI on every call and is the first endpoint where a loop costs
real money, and because a limiter first written in 5.2 has no time left to be
wrong. If that is not affordable, the honest alternative is to delete the table
from `04` and record "no rate limiting" in 5.4 beside the auth-throttling
omission already recorded there — but it should be one or the other, not a
specified table nobody builds.

**Extended at task 1.10, and the upload limit now has a second reason that is
not about loops.** `/login` ships a **View the demo wardrobe** button
(**O-12**, closed above) that signs any visitor into `demo@bijoux.app` with a
published password. `POST /items/upload` accepts twenty files and queues a real
tagging call per file, so on a deployed instance the path from a stranger
opening the site to the project's OpenAI credit being spent is two clicks, with
nothing in between. `04-API-SPEC.md` already names the answer — `429` with
`code: "rate_limited"` — and calls it "the answer to 'how do you stop a demo
account from burning your OpenAI budget?'", which is now literally the question.

**The rate limit is a precondition for deploying, not a Stage 5 nicety.** Today
nothing is deployed and the exposure is nil; the moment Render serves this
frontend it is not. Whoever does task 5.6 owns the ordering: the limiter lands
first, or the demo button is removed from the deployed build and the omission
recorded in 5.4. `DECISIONS.md` 137.

#### O-6 · The user profile the stylist prompt reads can never be filled in — Stage 2

`03`'s stylist user message carries a `USER PROFILE:` block —
*"Height: 165 cm. Preferences: prefer high-rise, avoid crop tops."* `02` gives
`users` the columns and calls `style_notes` "the cheapest possible
personalisation and it works well". `04`'s `PATCH /me` accepts all of them. But
`STAGE-2` 2.2 narrows the task to "`PATCH /me` accepting `home_city`,
`home_lat`, `home_lon`", and `05-FRONTEND-SPEC.md` line 76 already records that
**no task builds the profile screen in §8**. As the documents stand, `height_cm`,
`size_*` and `style_notes` are unreachable for a user, and the `USER PROFILE`
block renders empty in every real request the project will ever make.

**Recommendation.** Widen 2.2 to the whole `PATCH /me` body — it is the same
route and a longer schema — and add the profile screen as a small Stage 2 task
after 2.12. It is a form over one endpoint, `05` §8 already specifies it, and
without it the personalisation the brief sells is a prompt block that is always
blank. If Stage 2 cannot absorb the screen, seed `demo@bijoux.app` with a height
and a `style_notes` line at 1.10 so the mechanism is at least demonstrable, and
record the missing screen in 5.4.

#### O-7 · The trip constraints in `04` cannot all hold at once — Stage 4

`04` line 224: *"maximum 14 days; `start_date` no more than 14 days ahead (the
free forecast horizon)"*. `STAGE-4` 4.2: *"Open-Meteo provides 16 days; cap
requests at 14."* Two problems. The parenthetical is wrong — 14 is this
project's trip cap, not the provider's horizon, which is 16. And the pair is
unsatisfiable at the edges: a 14-day trip starting 14 days out ends on day 28,
twelve days past any forecast, so `POST /trips/pack` would accept a request it
cannot serve and fail somewhere inside the orchestration rather than at the
guard.

**Recommendation.** Constrain `end_date`, not `start_date`: *maximum 14 days;
`end_date` no more than 16 days ahead — Open-Meteo's horizon.* It is the last day
that needs a forecast, the number then comes from the provider rather than from
coincidence, and `400 forecast_unavailable` keeps a single, checkable condition.

#### O-8 · The `occasion` vocabulary lives in the wrong document — Stage 2

`04` line 177 defines six exact values —
`casual · work · evening · sport · formal · travel` — and is the only document
that carries them. `02` opens with "Do not add fields or enum values that are
not listed here" and has no `occasion` section; `looks.occasion` is `TEXT`,
`trips.occasions` is `JSONB`, and neither `enums.py` nor `enums.ts` knows the
word. It is the one closed vocabulary in the project with no validator and no
home.

**Recommendation.** Add an `occasion` section to `02`'s closed vocabulary and an
`Occasion` enum to both mirrors at 2.7, the task that first accepts the value.
`02` is authoritative for vocabularies by its own first line, and the argument
that made every other list closed — `"work"` and `"Work"` and `"office"` are the
same request and break grouping — applies here unchanged. Leaving it in `04`
means the six values are enforced by whichever request schema happens to
remember them.

#### O-9 · The stylist returns a `confidence` nothing can consume — Stage 2

`03`'s look object carries `"confidence": "high"` (line 347). `02`'s `looks`
table has no column for it, `05` renders `reasoning`, `weather_note` and
`missing_pieces` and never it, and no stage task mentions it. This is the same
question `DECISIONS.md` 086 closed for the vision path three commits ago — a
self-reported confidence with no reader is a flag nothing reads — with the same
evidence behind it: eight live responses returned `0.9` including both wrong
ones.

**Recommendation.** Strike it from the response schema before 2.4 builds the
schema from this document. A field in a Structured Outputs schema is a field the
model must produce on every call, so keeping it costs tokens on every request to
carry a number the project has already decided is a fluency signal. If it is
kept instead, it needs a column in `02` and a named reader — the same two things
086 required of the vision `confidence` before it would keep a branch.

#### O-10 · ~~`cloudinary-url.pipe.ts` is referenced by three documents and built by no task~~ — **closed at task 1.9**

Named in `04` line 119, `05`'s file tree, `07`'s transform table ("Build these in
`services/storage.py` and in the frontend `cloudinaryUrl` pipe") and twice in
`DECISIONS.md`. No numbered task creates it; 1.5 renders the server's
`image_url`, and 1.9 is the first screen that needs the `detail` transform.

**Recommendation.** Name it inside 1.9 rather than giving it a task. It is a
pure function of a `public_id` and a transform name, and 1.9 is the first caller.
Note when doing so that its four transform strings become a third hand-written
copy with nothing comparing them — the class `CONVENTIONS.md` already records
for the upload limits and the password rules, and **F-3** above is that class
producing its first real defect.

**Closed at task 1.9, at the caller this item named.** Item detail needs the `detail` transform and `ItemResponse.image_url` is a thumbnail, so it was build-or-render-a-300px-image-at-800px. The four transform strings are indeed a third hand-written copy, as this item warned; the mitigation is 101's, applied deliberately — the pipe's spec transcribes all four **from `07-DEPLOYMENT.md` by hand** and never reads the constant the pipe reads, so mutating any string fails a named test. One thing this item did not reach: `environment.cloudinaryCloudName` has been declared in all three environment files since task 0.8 and was **read by nothing for nine tasks**, which is what the pipe was waiting for. `DECISIONS.md` 118.

**`enum-label.pipe.ts` is a separate component and is still not built** — it appears in `05`'s file tree and in no audit item. `DECISIONS.md` 114 cited *this* item's recommendation when it declined to build it at 1.8, which was a misattribution: O-10 covers the Cloudinary pipe only. 114 is corrected in 1.9's commit. The label question was answered instead by moving 1.8's twenty-four keys out of `wardrobe.filter.*` into `vocabulary.*` and adding eighty-two more there (118).

#### O-11 · `02` documents one extension; migration `0001` creates two — low

`02` says "Requires `CREATE EXTENSION IF NOT EXISTS citext;` in the first
migration". `0001` also creates `pgcrypto`, which `02` never mentions — and on
PostgreSQL 18 `gen_random_uuid()` has been core since 13, so the extension is
not needed for the only thing that would want it.

**Recommendation.** Document it rather than remove it: add `pgcrypto` to that
sentence with the note that it is belt-and-braces on PG 13+. Dropping the
`CREATE EXTENSION` is a migration edit for no functional gain, and `0001` has
already run against Neon.

#### O-12 · ~~The demo-wardrobe affordance is now owned by nobody until it is put on `/login`~~ — **closed at task 1.10, superseded rather than taken**

Carried out of **O-4**, which is closed above. The **Try a demo wardrobe**
entry point is gone from the wardrobe empty state and is not yet anywhere else.
The agreed replacement is prefilled `demo@bijoux.app` credentials on `/login`:
no new endpoint, no new mechanism, one or two strings in `en.json` and a
prefilled `FormGroup`. It belongs to **1.10**, which seeds that account —
before 1.10 there is nothing to sign into, and after 1.10 the account exists
with nothing pointing at it.

**This is a tracking item, not a question.** It is written down because a
closed audit item reads as a finished one, and the affordance was moved rather
than cut. If 1.10 ships without it, the honest alternative is to record the
omission in 5.4 and delete the promise from `05` — but it should be one or the
other.

**Closed at task 1.10. The affordance shipped and the mechanism did not.**
`/login` carries a **View the demo wardrobe** button that calls
`POST /auth/login` with the seeded credentials and lands on `/wardrobe` — every
constraint this item imposed is met (no new endpoint, no new mechanism, the
same call and the same JWT), and the prefilled `FormGroup` it specified is not
what was built. The reason is one this item could not have had, because it is a
property of the screen rather than of the audit: the password input carries
`autocomplete="current-password"` and the email input `autocomplete="username"`,
paired deliberately at `DECISIONS.md` **070** so that password managers offer
save-and-fill — so a prefilled password invites a browser to save the demo
account over a visitor's own stored login. A button never populates the field.
It sits outside the `<form>` because a `<button>` inside one defaults to
`type=submit`. `05-FRONTEND-SPEC.md` line 108, which described the replacement
as prefilled credentials, is corrected in the same commit. `DECISIONS.md` 136.

**One thing this closes onto rather than away from**, recorded here because a
closed item reads as a finished one: the button hands any visitor an
authenticated session on a shared, mutable account, and the rate limit that
would stop them spending the project's OpenAI credit is **O-5**, which is open.

#### O-13 · Nothing in this project runs the frontend test suite, and it had been broken for four commits — whoever writes `ci.yml`

Found at task 1.5, by trying to run it. **`ng test` failed to build**, on a type
error in `auth.service.spec.ts` — `service.register(…, null)` against a
parameter narrowed to `string` at task 0.10 (`21e0f36`). The suite had been
unrunnable since **2026-08-16**, across four commits, while `PROGRESS.md`
recorded three of those tasks as complete.

**What hid it is the finding, not the type error.** `.github/workflows/` is
empty — CI does not exist. And the pipeline `06-TESTING-STRATEGY.md` specifies
would not have caught it either: its frontend job is `npm ci → ng lint → ng
build --configuration production`, and **neither command reads a spec file**.
`ng lint` does not type-check, and `tsconfig.app.json` excludes `**/*.spec.ts`
from the build. `ng test` is the only command in the project that type-checks a
spec, and it is in no pipeline and no document's definition of done. `06`'s own
layer table lists "Frontend unit — Vitest — yes" in the *required* column, so
the document asks for a suite it does not then run.

**Recommendation.** Add `ng test` to the frontend job in `ci.yml` when it is
written, between `lint` and `build`. **Do not write `ci.yml` for this** — it is
a whole task, it belongs to Stage 5, and the point of this item is that it must
not be discovered again by accident. The stale test itself is deleted at 1.5
(`DECISIONS.md` 096) so the suite runs; that is the symptom, and this is the
cause.

**One further observation, recorded because it is a fact and not a conclusion.**
Across roughly twenty runs of the suite at 1.5, `authGuard > lets an
authenticated user through` failed **once** and could not be reproduced in the
seven runs that followed — five clean and two mutated. It is not diagnosed. It
is written here rather than dismissed because an intermittent failure that
nobody records is indistinguishable from one that nobody has seen yet.

#### O-14 · Half of the wardrobe grid has been seen only by its tests — whoever verifies 1.9

**Not a defect.** Task 1.5 was checked by eye at `ng serve` with seven uploaded
items, and the surfaces that check reached are confirmed working: the **empty
state**, the **ready tiles**, the **grid** at both column counts, images loading
from Cloudinary, the **processing tile** keeping its dimmed photograph with
"Tagging…" as `DECISIONS.md` 091 specifies, and the waiting line correctly
reading **"Tagging 1 item"** in the singular, which is 095's whole point.

**Extended at task 1.8.** Two properties of the filter bar cannot be reached by
any test in this project, both measured rather than assumed. **A pasted
filtered URL reopening filtered** is by eye only: Angular's testing setup
installs `MockPlatformLocation`, so `window.location.search` never moves under
a `router.navigate` — the tests can prove what the `Router` was asked for and
can never prove what the address bar did with it, nor that a link pasted into a
fresh tab restores the grid. And **the chip row scrolling horizontally** is
invisible to the gate at all: `getBoundingClientRect()` returns zero for both
height and width, and `scrollWidth` and `clientWidth` are both `0`, so a row
that scrolls and a row that clips are the same DOM. Both belong to whoever
verifies this screen by hand.

**Four surfaces were not looked at, and are defended by tests alone:**

- the **`failed` tile** — the ⚠ state, its message and its appearance over the
  dimmed photograph
- the **retry button** — its label, its "Trying…" in-flight state, and its
  44px tap target
- the **per-tile placement** of the retag spinner and the retag error message
- the **`409 item_edited` branch** — the message a hand-edited item shows when
  its retry is refused
- and, separately, the **load-error state**: *"We couldn't load your
  wardrobe."* with its **Try again** button

**Why it was deferred rather than done.** Reaching the failed state at 1.5 means
a terminal round trip — a hand-written status change through the ORM, or ageing
a row past the startup sweep — which is more friction than one tile is worth,
and it is the *only* way in, because nothing in the UI can make an item fail
until 1.9 ships the editor. At 1.9 it is two clicks: edit an item, and the
`user_edited` path that produces the `409` is reachable from the screen itself.

**What stands behind them in the meantime**, so the size of the gap is stated
rather than implied: ten `ItemCard` tests, four `WardrobePage` tests, two store
tests naming the `item_edited` code, and **two mutations that survived and were
then closed** — the spinner and the error message were both bound globally
while 108 tests passed, which is recorded in `06-TESTING-STRATEGY.md` and is the
reason this item exists at all. Tests are why the risk is low. They are not the
same thing as having looked.

**Owner: whoever verifies task 1.9. The method below was wrong and is corrected
here rather than left to fail in someone's hands.**

~~The check is: force a tagging failure by editing an item and retagging it~~ —
**editing an item cannot cause a tagging failure.** Checked on disk at 1.9:
editing sets `user_edited`, so the retag answers `409` rather than running; and
a *forced* retag re-runs tagging against **the same photograph that tagged
successfully before**. The model never sees the tags, so nothing about an edit
can change what tagging returns. The only reliable routes to a `failed` row
remain the two this item already names: a terminal round trip, or a photograph
the model genuinely cannot read.

**What task 1.9 does close, of the surfaces listed above:**

- the **`409 item_edited` branch** — now reachable from the UI for the first
  time, and it is what a user meets rather than what a store test asserts: edit
  an item, press **Tag this again**, and the second step naming what will be
  discarded is the branch (`DECISIONS.md` 122)
- the **loop across a real navigation** — `/wardrobe` was the only
  authenticated route until 1.9, so back button, bfcache restore and hard reload
  become exercisable now that `/wardrobe/:id` exists

**What stays unreachable, unchanged:** the **`failed` tile** and its ⚠ state, the
**retry button**'s label and in-flight state, the **per-tile placement** of the
spinner and error, the **load-error state**, and the **stopped-waiting tile**.
Four of the five original surfaces and 1.7's tile are untouched by this task.

**The check, corrected:** open an item from the grid and confirm the detail
image is the large one rather than a scaled thumbnail; edit a tag, save, reload,
and confirm it persisted and the badge appeared; press **Tag this again** on
that item and confirm the second step appears rather than the retag running;
delete an item and confirm the grid's count moves; and stop the backend once to
see the load-error state. Producing a `failed` row still needs the terminal.

**Extended again at task 1.9**, with what a detail screen adds that no gate here
can see:

- **Whether a `w_800` image fits a 390px screen**, and whether a fourteen-control
  editor scrolls or clips. `getBoundingClientRect()` is still zero in every
  dimension, so layout is invisible exactly as it was at 1.6 and 1.8.
- **Whether `/wardrobe/:id` pasted into a fresh tab opens the right item.** Same
  blind spot 1.8 recorded for filtered URLs, now on a route parameter:
  `MockPlatformLocation` means the address bar never moves, so the tests prove
  what the `Router` was asked for and never what a browser did with it.
- **The two-press delete against a real pointer.** The arm-and-disarm logic is
  gated thoroughly, but whether a thumb on a phone can hit the same 44px target
  twice without the blur handler firing between presses is a device question.
- **The forced retag end to end.** Every test flushes the `409` by hand; that a
  real backend produces it, and that `?force=true` then re-tags the photograph,
  has never been observed against a live OpenAI account.

**Extended at task 1.6, which added more unverified surface than it closed.**
The upload sheet's mechanism is largely outside what any automated gate in this
project can reach, and the limits were **measured** at 1.6 rather than assumed
— jsdom 28.1.0, the environment `@angular/build:unit-test` uses when
`angular.json` names no `browsers`. `06-TESTING-STRATEGY.md` carries the full
probe; what it means for this item is that the following have been seen only by
tests, or not at all:

- **`URL.createObjectURL` and `revokeObjectURL` are both `undefined`.** Every
  preview test drives a stub. That a preview *appears*, is the right image, is
  replaced rather than duplicated when the rows land, and that its memory is
  released — none of it is gated anywhere.
- **The camera.** `capture="environment"` reflects as a content attribute with
  no property and no behaviour. Whether a phone opens the rear camera is
  unverifiable here **and in Playwright**; it needs a real device.
- **The picker.** `showPicker` is `undefined` and `input.click()` only fires
  our own handlers, so neither the OS dialog opening nor `multiple` genuinely
  multi-selecting is exercised.
- **`DataTransfer` does not exist and `new FileList()` is an illegal
  constructor**, so specs install an array through `Object.defineProperty`.
  Our handler is exercised; `FileList` semantics are not.
- **Sheet geometry.** No layout in jsdom — `getBoundingClientRect().height` is
  `0`, there is no `matchMedia`. Bottom anchoring, the overlay sitting above
  the grid, and the 44px tap targets on its two buttons are all unchecked.
- **The wire.** `HttpTestingController` asserts the `FormData` we built. That
  the browser serialises it with the right boundary, and that no
  `Content-Type` is set by hand, is not observed against a real server.
- **HEIC.** A `File` built in a spec lies about its contents and the backend
  decides type from bytes, so the format most likely to arrive from an iPhone
  is exercised nowhere below a real end-to-end run with a real fixture.

  **Still true at 1.10, and the one candidate to close it has gone.** The seed
  set briefly held a real HEIC — the brown shearling jacket — which would have
  put an iPhone original through `upload_image`, Cloudinary and `build_url` for
  the first time. It was replaced with a JPEG of the same garment before
  `--upload` ran, so **no HEIC exists in the seed set** and this line is not
  closed by 1.10. `tests/unit/test_storage.py` still defends the signature
  branch with synthetic twelve-byte headers; that is detection, not delivery.
  `DECISIONS.md` 141.

**1.6 does not make this item's original five surfaces reachable.** Uploading a
deliberately unreadable image is now possible from the UI, which is cheaper
than the terminal round trip described above — but it is not *reliable*:
`validate_tags` retries, and a blurred or dark photograph usually still returns
acceptable tags. The dependable route to a `failed` row is still the one this
item already names, and the owner is unchanged.

**Extended again at task 1.7.** The polling loop's arithmetic is gated
thoroughly — `06-TESTING-STRATEGY.md` carries the seventeen-mutation run and
the timer probe — and the arithmetic is not the part that fails in a browser.
What has been seen only by tests, or not at all:

- **That a browser's `setInterval` is anywhere near 2 seconds.** Chrome
  throttles timers in background tabs to at least 1 second and can suspend them
  entirely; Safari on iOS suspends them on lock. Every test here drives a mock
  clock, so the *only* claim made is about the loop's own logic. Deliberately
  no visibility handling was built (`DECISIONS.md` 107), which makes this the
  behaviour a real device decides.
- **The 3-minute hard stop has never elapsed in real time.** It is asserted at
  exactly 180 000 mock milliseconds. Whether a real batch of twenty reaches it
  is 1.3's serial tagging against a real OpenAI account, which nothing in this
  project has yet run end to end.
- **The stopped-waiting tile has never been looked at.** It needs a tagging run
  that outlives three minutes, which is harder to stage by hand than the
  `failed` tile this item already names — and its two properties are exactly
  the ones a test states rather than shows: that it does not read as a failure,
  and that its text fits a 110px tile at three columns on a 390px screen.
- **The loop across a real navigation.** `fixture.destroy()` fires `DestroyRef`
  in jsdom, which is what the test asserts. A browser back button, a bfcache
  restore and a hard reload are three different paths and none is exercised;
  `/wardrobe` is still the only authenticated route, so the first of them
  becomes reachable at **1.9**.
- **The reload's timing against a real server.** The poll and the reload are
  serialised by construction, and every test flushes them by hand. Whether a
  slow reload and a fast tagging run interleave the way the loop assumes is not
  observed anywhere below a live run.

**Owner: unchanged — whoever verifies task 1.9**, who will already be forcing a
tagging failure by hand and can leave one batch running past three minutes at
the same time.

#### O-15 · `05`'s file tree names seven `shared/ui/` components and none exist — task 1.8, or whoever needs the second one

`05-FRONTEND-SPEC.md` line 32 lists `shared/ui/ button, chip, sheet, skeleton,
empty-state, spinner, toast`. **None of the seven has ever been built.** Task
1.5 wrote its empty state and its buttons inline in `wardrobe.page.ts`, and
task 1.6 built its bottom sheet inline in `upload-sheet.ts` rather than create
`shared/ui/sheet` for a single caller.

Same class as **O-10** (`cloudinary-url.pipe.ts`: named by three documents,
built by no task) and recorded on the same terms. The difference is that this
one is seven components rather than one, and that two tasks have now
deliberately declined to build any of them.

**Recommendation.** Do not create the directory speculatively. Extract the
first primitive at its **second** caller, not its first — 1.8's filter sheet is
the next thing that wants a sheet, and it is the point at which "inline in the
one component that uses it" stops being true. Whoever does that should note
that a shared `sheet` has to carry the focus and dismissal behaviour that
`upload-sheet.ts` currently owns for itself. If Stage 1 ends with the directory
still empty, the honest fix is to delete the line from `05`'s tree rather than
leave a file map describing a structure the project does not have.

**Answered at task 1.8, and the answer is no.** The recommendation was to
extract at the second caller and to let that caller decide; the second caller
is 1.8's filter control and it is **not a sheet**. It is an inline disclosure
panel, because a modal over the grid hides the thing being filtered while the
control is open — 098's own argument for why the gallery path closes the upload
sheet, applied to the worse case. So `shared/ui/` is still empty and **three**
tasks have now declined to fill it, which strengthens rather than weakens the
other half of this item: if Stage 1 ends this way, delete the line from `05`'s
tree. `DECISIONS.md` 113. This item stays open on that second question only.

**Fourth decline, at task 1.9.** The detail screen and the tag editor were the
next two candidates and neither extracted anything: the editor is form controls
in flow with no sheet, no modal and no toast, and its delete confirmation is a
two-press button rather than a dialog — declined on cost, with `inert`
unsupported in the gate making a fourth hand-rolled focus trap the real price
(`DECISIONS.md` 126). `shared/ui/` is still empty, `shared/pipes/` now is not.
**Stage 1 has one task left that touches the frontend and it is a seed script**,
so this item's other recommendation is now the live one: delete the line from
`05`'s file tree rather than leave a map of a structure the project does not
have. That is a Stage 5 tidy and it needs a decision, not a commit.


#### O-16 · Seven `GET /items` query parameters have no caller, no test, and now no candidate — task 5.2 or 5.4

`DECISIONS.md` 051 implemented all eleven parameters `04-API-SPEC.md` lists
"rather than the subset with a named consumer". Seven of them —
`category`, `color_primary`, `formality_min`, `formality_max`, `warmth_min`,
`warmth_max` and `search` — have never been sent by anything, and
`tests/integration/test_items_rows.py` defends the other four and not these.

**Task 1.8 was the last plausible consumer and declined them**, which is not a
change of plan: `05-FRONTEND-SPEC.md` has specified client-side filtering "over
the loaded collection" since it was written, and `STAGE-1` §1.8 repeats it
verbatim, so the five tag filters were never going to be sent. `search` appears
in no mockup and no stage brief; `offset` is refused by name in 094;
`include_archived` has no screen. On the current plan the client will only ever
send `limit` and `status`.

This is recorded so that whoever meets it meets a decision rather than an
oversight. **It is not a defect** — the endpoint is correct, and an API wider
than its client is a normal thing for an API to be. The two live questions are
whether the seven should be tested before Stage 5 signs the endpoint off
(**5.2**), and whether the unknown-parameter silence `04` line 119 already
assigns to **5.4** should be closed at the same time, since a client that never
sends these cannot notice that `?colour_primary=navy` filters nothing.

Same class as **O-10** and **O-15**: named by a document, built or not built by
nobody, and found only because a task walked past it.

`GET /items/stats` is in the same condition one level up — implemented at 1.4,
tested by six integration tests, and consumed by no screen. 1.8 was its first
possible caller and chose not to be one (`DECISIONS.md` 112), so it stays
unowned until Stage 3 extends it. It is first on `STAGE-1`'s cut list.


#### O-17 · Acceptance criterion 3 has no owner, and nothing in Stage 1 can produce the row it asks for — task 5.3, or a decision to cut it

`STAGE-1`'s third acceptance criterion is *"A deliberately bad image ends as
`failed` with a working retry button."* The **mechanism** is complete: 1.3 writes
`failed` on both failure paths, 1.5 renders the tile, 1.9 adds **Add tags by
hand** beside its retry. What has no owner is **producing the row**.

Three routes were checked on disk at task 1.9 and all three are closed:

- **`USE_FAKE_AI`** returns a hand-written placeholder that passes
  `validate_tag_dict` with no errors and no coercions — asserted by a test — so
  it cannot fail.
- **A bad photograph** is unreliable rather than impossible: `validate_tags`
  retries once, and a blurred or dark image usually still returns acceptable
  tags. O-14 already says this.
- **Editing and retagging** cannot do it, for the reason O-14 is corrected
  above: the model never sees the tags.

So the only dependable route is a hand-written status change through the ORM or
ageing a row past the startup sweep — a terminal round trip that no task owns
and no acceptance criterion should require.

**Recommendation.** Do not invent a task for it. Either **cut the criterion**,
on the grounds that what it is really asking about is the failure path and that
path has integration tests at 1.3 and a `TaggingError` unit test at 1.2b — or
**move it to 5.3**, where a browser-based QA pass can stage the row deliberately
and the terminal round trip is in scope rather than an embarrassment. Recorded
rather than solved because deciding which is a judgement about what Stage 1
claims to have demonstrated, and that is the developer's.

**Not a defect, and not new.** The criterion has been unownable since it was
written; it is recorded now because task 1.9 was the last task that could
plausibly have closed it and did not.

#### O-18 · Four shipped behaviours have no surface in the demo wardrobe — deliberate, recorded at task 1.10

The seeded wardrobe is 64 rows, all `ready`. Nothing in it reaches **1.5's
failed tile**, **1.4's retry button**, or **1.9's `failed`→`ready` promotion**
and its *Add tags by hand* link — all three are entered only through a
`status='failed'` row. **1.8's rule that a null is never hidden by that field's
filter** goes with them, and by construction rather than by omission:
`REQUIRED_TAG_FIELDS` forbids a null in `category`, `color_primary`,
`formality` or `warmth` on any `ready` row, and the wardrobe measures zero
nulls in all four.

**This is a choice, not an oversight.** `--with-failures` exists and adds the
two rows, and it is not run: its rows reuse two committed `public_id`s, so the
grid shows two garments twice — once ready, once failed — which reads as a
duplication bug to anyone who does not know the design (`DECISIONS.md` 135).
Two dedicated photographs would fix it and were declined. The live-retag
alternative is refused for **O-17**'s reason: `validate_tags` retries and a bad
photograph usually still tags, so it is a demonstration that depends on an API
call failing on cue.

**Nothing to do here.** It is written down so the gap is met as a decision
rather than found during a defence, and so that whoever adds two photographs
later knows what they buy. `07-DEPLOYMENT.md`'s checklist no longer implies the
failed states are demonstrable.

#### O-19 · Two documents print a CI that has never been written — task 5.5

Opened by the root-README task, not by an audit. `07-DEPLOYMENT.md` §
*CI — `.github/workflows/ci.yml`* prints a three-job YAML block — backend,
frontend, e2e, with a `postgres:16` service and a `-m "not eval"` step — in the
present tense and under the filename. **`.github/workflows/` contains one file
and it is `.gitkeep`.** The pipeline is task 5.5's to write and does not exist.

**`docs/README.md` makes the same claim in one line**, and it is the second
document rather than a restatement of the first: its *Stack at a glance* table
carries `| CI/CD | GitHub Actions → Render (API) + Vercel (web) |` in the
present tense, in a column where every other row names a service that is
genuinely wired. It is named here rather than left to whoever fixes `07`,
because a fix scoped to the document that happened to prompt the item is how
the second copy survives it. Both lines close together or neither does.

**O-13 already records that CI does not exist**, and found it from the other
end: nothing runs the frontend suite. This item is the document half of the same
fact, and is separate because the fix is different. O-13's recommendation is a
line to add to `ci.yml` when it is written; this one is that until then, the
section reads as documentation of a file rather than as a specification for one,
and two other places rely on it doing so — `07`'s own note that "CI's
`postgres:16` pin is task 5.5's to correct", which describes correcting a file
that has never been created, and the pre-defence checklist's *Latest CI run
green, Playwright HTML report available to show*, which is not a check anybody
can currently perform.

**Why it is worth an item rather than a fix in place.** The block is not wrong —
it is 5.5's specification and `STAGE-5` § 5.5 points at it by name. What is
wrong is that nothing on the page says so, and a specification and a description
of deployed infrastructure are indistinguishable when both are a YAML block
under a filename. The cheapest answer is one sentence marking it as not yet
built; the alternative is to move the block into `STAGE-5` and leave `07` a
pointer. Either is a decision about where a specification lives, which is why it
is here.

**`07` was not read by audit 1** — it is named under *Not covered by this
audit*. This is the first finding out of that document and the boundary is
holding as O-13's was.

---

### Noted in passing, not a documentation defect

`GET /items/stats` (task 1.4) must be **registered before** `GET /items/{item_id}`
in `app/api/v1/routes/items.py`. FastAPI matches in declaration order, and
`/{item_id}` is already declared, so `stats` added below it is parsed as a UUID
and answers `422`.

---

### Checked and clean

Recorded so the next audit re-runs them rather than re-deriving them, and so a
future failure has a date to bisect against.

- **`02`'s vocabulary lists against `app/enums.py`** — all nine enums plus the
  full `SUBCATEGORIES` map, compared token for token by script. Exact match.
  This is the seam `03` and `06` both call unwatched: authoritative by hand,
  compared by nothing.
- **`app/enums.py` against `frontend/src/app/shared/models/enums.ts`** — nine
  lists, exact match. The second half of the same seam.
- **`02`'s layer table against `LAYERS_BY_CATEGORY`** — all seven categories,
  `admits` and `answer` both, including `top`'s deliberate absence of an answer.
- **`03`'s validation table against `validate_tag_dict`** — every row present in
  the code, and the seven rows attributed to 1.2a are the seven `git show
  92f4415` added. Omissions in the other direction are **O-2**.
- **`03`'s response schema against `VISION_SCHEMA`** — fifteen properties, the
  nullable-enum shape on `color_secondary`, the bounds on `formality`, `warmth`
  and `confidence`, `required` derived from the properties.
- **The eleven required fields** listed in `03` against `_REQUIRED_FIELDS`.
- **The retry text** `03` quotes — *layer 'standalone' is not valid for category
  'top', which takes base or mid* — is what `enums.py` produces, character for
  character.
- **Every `DECISIONS.md` reference in the four documents** (028, 029, 030, 027,
  033–037, 039, 040, 043, 045, 048–053, 070, 074, 078, 080, 082–087) resolves to
  an entry that exists, and the three that point at superseded reasoning — 028's
  confidence sentence, 029's flat-enum premise, 030's three fields — each cite
  the entry that supersedes them.
- **Every test named in the four documents exists**, by function name:
  `test_a_nullable_enum_keeps_null_out_of_the_enum_array`,
  `test_only_the_accepted_answers_coercions_are_carried`,
  `test_the_middle_of_the_length_list_gets_no_rule_of_its_own`,
  `test_outerwear_with_a_base_layer_is_coerced_to_outer`,
  `test_maxi_on_a_t_shirt_no_longer_validates`,
  `test_a_prompt_file_without_the_placeholder_raises_at_load`,
  `test_login_401_offers_the_bearer_challenge`,
  `test_rejects_a_status_filter_outside_the_closed_vocabulary`.
- **`04`'s three shipped endpoints against `routes/items.py`** — the 202, the
  eleven query parameters, `limit` 100/200, the `created_at DESC, short_id`
  ordering, the archived exclusion, the unescaped `ILIKE`, the 415/413/502
  mapping and its two passes, the `404 not_found` in the `WHERE` clause.
- **`04`'s auth section against `routes/auth.py`, `schemas/auth.py`,
  `core/security.py`, `core/deps.py`** — 8-character/72-byte passwords, 7-day
  JWT, `409 email_exists`, both `401`s carrying `WWW-Authenticate: Bearer`,
  `extra="forbid"` on both bodies, the `{detail, code}` envelope.
- **`02`'s `items` DDL against `models/item.py` and `0001_initial.py`** — every
  column, both `CHECK`s, the partial index, the `CHAR(6)` unique, the three enum
  types, `wear_count`/`last_worn_at` correctly absent.
- **The `short_id` alphabet** in `02` against `core/short_id.py`, character for
  character.
- **`STAGE-1` 1.3's handover from 1.2b** — the two-function call sequence, the
  two exception types, `PROMPT_VERSION`, `items.attributes`, the `updated_at`
  fix, the synchronous upload route. All match the code as it stands.
- **`STAGE-1` 1.4's `CATEGORY_DEPENDENT_FIELDS`** — five fields, exported,
  matching 030's amendment.
- **`STAGE-1` 1.5 against `05-FRONTEND-SPEC.md`** — 3/5 columns, the explicit
  `limit`, the 200 cap being a `422` rather than a clamp.

### Not covered by this audit

Named because an audit whose holes are not written beside it reads as a clean
bill of health (`CONVENTIONS.md`).

- **Documents not read:** `00`, `01`, `05`, `06`, `07`, `CONVENTIONS.md`.
  `DECISIONS.md` was read only where the four documents cite it. `05` and `07`
  were opened to corroborate specific claims, not audited.
- **Stage files not read:** `STAGE-0`, `2`, `3`, `4`, `5` were searched for
  endpoint and mechanism ownership only. Within `STAGE-1`, tasks 1.1, 1.2,
  1.6–1.11, the acceptance criteria and the commit checkpoints were not audited.
- **Code not read:** the frontend beyond `enums.ts`; the test suite beyond
  confirming named tests exist; `alembic/env.py`; `logging.py`; `db/`.
- **Nothing was run.** No tests, no server, no API call. Claims about live
  behaviour — the eight vision responses, the HEIC `Accept` experiment, the
  `create_all` measurement — are taken as recorded, not re-measured.
- **Vendor claims not verified:** the Structured Outputs strict-subset rules in
  `03` are OpenAI's documentation as transcribed at 1.1.
- **Not looked for:** anything in `06-TESTING-STRATEGY.md`, which is the largest
  unaudited document and the one most likely to describe tests that no longer
  match the suite. That is the obvious scope for audit 2.

# 06 — Testing Strategy

This is the document that turns the project from "an app that works" into "an engineered system". Give it real time.

The central question: **how do you write reliable automated tests against a non-deterministic model?** The answer has three parts — push determinism out of the model, mock the model in E2E, and measure the model separately with a golden dataset.

---

## The layers

| Layer | Tool | Runs in CI | Calls OpenAI |
|---|---|---|---|
| Unit — pure logic | pytest | yes | no |
| Contract — schema validation | pytest | yes | no |
| Integration — API + DB | pytest + httpx | yes | no (mocked) |
| Frontend unit — services, guards, interceptors, models, pages, stores | Vitest | yes | no |
| E2E — user journeys | Playwright + TS | yes | no (mocked) |
| AI evaluation — quality | pytest, `-m eval` | **no**, manual | yes |

Only the last layer costs money, and it is deliberately excluded from CI. Everything else is deterministic and fast.

---

## Layer 1 — Unit tests, no AI

The reason weather rules are computed in Python rather than inferred by the model is testability. This is a pure function:

```python
@pytest.mark.parametrize("temp,expected_fragment", [
    (35, "warmth 1-2 only"),
    (28, "warmth 1-2 only"),      # boundary
    (27, "Outerwear optional"),
    (22, "Outerwear optional"),   # boundary
    (21, "optional"),
    (16, "optional"),             # boundary
    (15, "REQUIRED, warmth 3-4"),
    (10, "REQUIRED, warmth 3-4"), # boundary
    (9,  "REQUIRED, warmth 4-5"),
    (-5, "REQUIRED, warmth 4-5"),
])
def test_weather_rule_boundaries(temp, expected_fragment):
    assert expected_fragment in build_rule(temp, precip_mm=0, wind_kph=0)

def test_rain_modifier_appended():
    rule = build_rule(14, precip_mm=5, wind_kph=0)
    assert "water_resistant" in rule
```

Every boundary in the mapping table gets both sides asserted. Also unit-tested with no AI:

- `serializer.py` — wardrobe to compact lines: null omission, field order, token budget
- `security.py` — hash and verify round-trip, the 72-byte cap raising rather than truncating, token round-trip, expiry, bad signature, tampered payload. Pure by construction: it imports no ORM and no session (`DECISIONS.md` 038), which is what lets these run at task 0.5, before any fixture exists
- `storage.py` — the signature table for every accepted and rejected format, truncated files, the size boundary on both sides, and the four transform URLs against `07-DEPLOYMENT.md`. Pure by the same construction as `security.py`: the accept/reject rule is a function of bytes, and the one call that would leave the process is monkeypatched — including a fake that raises if called at all, which is how "validate before uploading" is enforced rather than assumed
- `enums.py` — `subcategory` validity per `category`, all 9 categories since task 2.6a; and from task 1.2a the rest of the category-dependent rules, both directions per category: `fit` and `length` applicability and their narrowed words, and `layer`'s admitted set and answer for each of the nine — including the one category, `top`, whose answer is an error rather than a value
- `short_id` generation — alphabet excludes `0O1IL`, correct length, no repeat across a large sample. **Collision retry is not here**, and the original wording was wrong to place it: what detects a collision is the `uq_items_short_id` constraint, so the retry cannot run without a database. Task 0.7 shipped the pure half; task 0.10 owns the retry with the rest of the row-writing tests
- `validate_tag_dict()` — every coercion and every rejection path
- `validate_tags()` — the retry and the give-up, with the vision call mocked. From task 1.2b that means: a clean answer accepted without a call at all, every coercion accepted and never retried, the `top`/`layer` error retried once with the violation in the correction, the give-up after exactly one retry, the eleven required fields each missing in turn, and the coercion log. The signature is `async validate_tags(raw, image_url)` — the URL is there because the retry is a second call to the model
- `vision.py`'s rendered prompt — the category rules, **pinned literally**. Every other prompt assertion in that file derives its expectation from `enums.py` and would move with a mutated table; these are transcribed from `02-DATA-MODEL.md`, for the reason two subsections below
- `validate_look_response()` — every rule of `03`'s table that has a field to read, each failing independently, including anchor present and locked items preserved. **Five of the eight at task 2.5**, six with the anchor at 2.10, seven with the swap at 2.11 and **eight of nine with rule 9 at 2.11a**. **Task 4.3 closed the running total and split it in two**: the table now has eleven numbers and ten live rules, and no one call runs them all. A single-day call runs 1, 2, 4, 6, 7, 8, 9; a trip runs 1, 2, 4, 10, 5, 6, 9, 11 — rules 7 and 8 have no fields on `POST /trips/pack`, and rules 5, 10 and 11 got theirs from `trip_packing_plan`. The trip half lives in the same file, against hand-built `TripContext` objects, and asserts the day prefix as well as the rule. Rule 8 is gated on `locked_item_ids` as `03` words it: an exclusion sent with nothing locked is printed to the model and not enforced, and a test pins that. 2.5 also pins the two things the table does not print: an id is matched after `.upper()`, and rule 6 does not run when the user asked for no outerwear

---

## Layer 2 — Contract tests

The AI can only return what the schema permits, but the schema itself must be correct and must stay aligned with the database.

```python
def test_every_subcategory_maps_to_a_valid_category():
    for category, subs in SUBCATEGORIES.items():
        assert category in Category.values()
        assert len(subs) == len(set(subs))
```

**This section used to open with a second example and a claim that is no longer true, and both are corrected at task 1.1 rather than left to mislead.** The example compared `VISION_SCHEMA["schema"]["properties"]["color_primary"]["enum"]` against `ColorPrimary.values()`, and the claim was that it catches the classic failure — someone adds `"burgundy"` to the prompt but not to the enum, and tagging starts failing a week later.

It cannot catch that any more, because **both sides now come from `enums.py`**. `vision.py` builds the schema's enum arrays from the vocabulary classes and renders the prompt's `{{VOCABULARY}}` block from the same ones, so prompt, schema and validator cannot disagree — the drift is closed structurally rather than detected. A comparison between two expressions of one source is a tautology, and a tautology whose docstring claims it is a drift detector is worse than no test: someone reads the green tick and believes a class of error is covered.

**The real remaining seam is `02-DATA-MODEL.md` → `enums.py`.** That document declares itself authoritative, `enums.py` is a hand-written mirror of it, and **nothing compares them.** Add `burgundy` to the document and forget `enums.py` and every test in this project still passes; the vocabulary is simply narrower than the specification says. That is the same shape as the `MAX_UPLOAD_MB` and `MIN_PASSWORD_LENGTH` mirrors `CONVENTIONS.md` records, with the same honest answer: it is stated in prose in one place and honoured in code in another, and no test can bridge it without parsing markdown. `frontend/src/app/shared/models/enums.ts` is a third copy of the same vocabulary and is in exactly the same position.

What task 1.1 does test about the schema is the part that is not a tautology: that `required` covers every property, that `additionalProperties` is `false`, that every property carries a `type`, that `color_secondary` keeps `null` in the **type union and out of the `enum` array** — the vendor-specific shape a tidy-up would "fix" into plain JSON Schema and break — and that the four deliberately unconstrained fields carry no `enum` at all.

---

## Layer 3 — Integration tests

FastAPI `TestClient`, a real PostgreSQL test database, AI services replaced by fakes.

```python
@pytest.fixture
def answers(monkeypatch):
    def _answer(raw: dict) -> None:
        async def fake_tag_item(image_url: str, correction: str | None = None) -> dict:
            return dict(raw)

        monkeypatch.setattr(tagging, "tag_item", fake_tag_item)
        monkeypatch.setattr(vision, "tag_item", fake_tag_item)

    return _answer
```

**Corrected at task 1.3, against the code rather than against intent.** The sample here was a *synchronous* one-argument `_tag` returning `load_fixture("vision/white_shirt.json")`, patched at the string `"app.services.vision.tag_item"`. Four things were wrong with it and every one of them is load-bearing:

- `tag_item` has been `async` with a `correction` parameter since 1.2b, so the fake had the wrong signature and the wrong callable kind.
- `load_fixture` has never existed and `tests/fixtures/` holds only a `.gitkeep`. Recorded fixtures are task **5.1**'s (`DECISIONS.md` 081); until then a fake answer is a dict written in the test.
- Patching the definition in `vision` does not reach a name another module has already imported. `app/services/tagging.py` does `from app.services.vision import tag_item`, so the fake has to be installed at **both** bindings.
- And the reason both matter: `validate_tags` resolves `tag_item` from `vision`'s own module globals when it **retries**. A fake installed at one binding intercepts the first call and lets the second one out to the live API. That is not hypothetical — it happened while 1.3's tests were being written, on the developer's real key. It answered `400` and cost nothing, which is luck.

**So `tests/conftest.py` gained an autouse guard at 1.3.** Unless a test carries `@pytest.mark.eval`, `vision._client` is replaced with one that raises. The rule "no test may call OpenAI unless marked `eval`" has been in `CONVENTIONS.md` since Stage 0 and was enforced by nothing but per-test discipline; `_client` is the single door every call goes through, so a fake installed there cannot be routed around by importing the function from somewhere else.

**This document was named out of scope by the 2026-08-18 audit**, which called it "the largest unaudited document and the one most likely to describe tests that no longer match the suite". This is the first thing to fall out of that boundary, one task later, and it is evidence the boundary was drawn accurately rather than a gap to apologise for. Audit 2's scope is unchanged.

What gets covered:

- **Upload returns 202 before tagging completes.** Assert `status == 'processing'` in the response body — this is the core UX promise and it should be enforced by a test.
- **The upload rejection paths, without a database.** Task 0.7 covers `415` (text, SVG, empty, truncated), `413`, `415`-before-`413` on an over-large non-image, one bad file rejecting a whole batch, the `422` on 0 and on 21 files, the `502` on a storage failure, and `401` on every route — with `get_db` overridden by a stub that raises on *attribute access* and `cloudinary.uploader.upload` monkeypatched to raise if called. That stub is the assertion: it is what proves "every file is decided before any file is uploaded" rather than assuming it. It raises on use rather than on call because FastAPI resolves every dependency before the handler runs, so a call-raising stub would fail requests the route rejects first.
- **Background task transitions the row** to `ready` with populated tags. Task 1.3, `tests/integration/test_tagging.py`.
- **Tagging failure** sets `status='failed'` and `error_message`, and does not raise into the request. Task 1.3 splits this into four: an answer that cannot be accepted, no answer at all, a provider failure, and one nobody predicted — the first two must not read the same in the column, and the last is why `_tagged` ends in `except Exception`.
- **The startup sweep** fails a `processing` row past the threshold, leaves a recent one and a `ready` one alone, and never raises at boot. Tested by planting an explicitly backdated `updated_at` and calling the sweep directly — no clock is manipulated and nothing waits ten minutes.
- **Hallucination guard:** feed a stylist fixture containing an ID that is not in the wardrobe and assert a `502`, not a partially rendered look. This is the single most important integration test in the project.
- **Cross-user isolation:** user A cannot `GET`, `PATCH`, or `DELETE` user B's items. Test every item endpoint.
- **`user_edited` protection:** `POST /items/{id}/retag` returns `409` after a manual edit, and succeeds with `?force=true`.
- **`wardrobe_too_small`:** 5 ready items returns `400` before any AI call is attempted.
- **The trip endpoints.** Task 4.4, split by whether the model has to be faked at all: `tests/integration/test_trips_pack.py` covers `POST /trips/pack` and `POST /trips/{id}/repack` with the geocoder and forecast faked on `services/packing` and the stylist faked on `stylist_runner.suggest_looks` — one module further in, so **`validate_look_response` runs for real** and the trip path's rules 5, 10 and 11 judge every plan the tests assert on. `tests/integration/test_trips_read.py` needs no fake at all and plants rows directly, which is `test_trips_rows.py`'s approach one layer up. Between them: the one-commit write, the day-strip join, the packing list's UUIDs and tie-broken `reuse_summary`, both halves of `trip_too_long`, `wardrobe_too_small` before the geocoder, all five failure codes, `AUDITS.md` O-32's detach and cascade, and cross-user isolation on every endpoint.

- **The swap endpoint.** Task 4.6a-1, `tests/integration/test_trips_swap.py`. Every test packs a trip first, because a swap is an edit to a stored plan; the fake stack is `test_trips_pack.py`'s shape and is **copied rather than imported**, because no test module in this suite imports another and hoisting the fixtures into a `tests/integration/conftest.py` would mean editing a file the task has no other reason to open. What it measures beyond the codes: that the day named changes and no other, that the swap survives a reload — the half `POST /looks/suggest` could not have delivered — that a detached look keeps `is_saved`, `feedback` and `worn_at` byte for byte, that a stylist failure leaves the look and the packing list untouched, and that the packing list keeps its survivors' order. **Two tests exist to catch a mutation rather than a bug.** The stored weather rule is overwritten with a sentence `build_rule` cannot produce, so the only way the assertion passes is by reading the column; and `shoes_a` is planted with the highest `uuid4` of the nine, so the tie-break test cannot pass by luck when a mutation sorts the list before summarising it. A third case is defended by a hand-edited row, because reading `occasion` off the replaced look rather than off `trips.occasions` is an equivalent mutant under every state this API can write.
- **Rate limits** return `429` with `Retry-After`.

### A test that measures a moment cannot assert an event

One idea, found twice at task 0.9 by deleting the behaviour and watching the suite stay green. Both instances read as perfectly ordinary tests.

**Asynchronous behaviour is only observable if something is still pending when you look.** Read a value immediately after triggering an async operation and you see the state *before* it, which is indistinguishable from the operation never having happened. The assertion is true either way, so it proves nothing — and it fails silently, by continuing to pass.

The two instances:

- **`app.config.spec.ts`** replaced `HttpBackend` with a fake that replied **synchronously**, so `restore()` resolved inside the same microtask chain as bootstrap. Every assertion held whether or not the initializer was awaited — which was the entire point of the spec. Fixed with `delay(0)`, so the reply lands on a macrotask. **A test for a blocking behaviour has to be slower than the thing it tests.**
- **`jwt.interceptor.spec.ts`** asserted `router.url === '/'` right after a synchronous flush, to prove no redirect had fired during bootstrap. Navigation is asynchronous, so a **started-but-unfinished** navigation reads exactly like no navigation. Fixed by counting `NavigationStart` events.

Same shape both times: a moment sampled instead of an event observed. The general rule is to **assert on the event, not on the state afterwards** — an event count is deterministic where a state read is a race — and where that is impossible, make the operation slow enough that the wrong answer is visible.

**Mutation is what separates the two, and nothing else does.** Delete the behaviour, run the suite, and confirm a *named* test fails. Seven were run across the specs at task 0.9; **four of them exposed something** — two tests passing for the wrong reason, and two behaviours with no test at all (the `**` wildcard's destination, and the deliberate asymmetry between the two login notices). Both now have tests. Two more remain undefendable at this layer and are 5.3's — see below.

### Two readings of one input beat one reading of two

Where a check can be run twice on the same input, prefer that over running it once on two. The reason is asymmetric and it is what makes this a rule rather than a preference: **absence has one explanation and reads as a pattern, while disagreement has to be explained and cannot be waved away.**

Two instances, one from each side of the project.

- **The log test at task 0.10.** `test_health_logs_a_warning_when_the_database_is_unreachable` passed when its file ran alone and failed in the full suite. Neither run alone said anything; running the *same test* twice in two contexts is what located `fileConfig` disabling every application logger (`DECISIONS.md` 076). One run would have been believed.
- **The eight live images before task 1.2.** Two tank tops came back with two different `fit` values — `None` and `skinny`. That single contradiction falsified the reading that a null `fit` means the vocabulary is short a word, and it did so conclusively, from a sample of two. The six other garments were each photographed once and could support no such conclusion, because a null with nothing to disagree with is just a null.

The consequence for task 1.11 is written into that task: a golden set of thirty distinct garments can measure accuracy and can never measure consistency, so repeated `(category, subcategory)` pairs have to be designed in before the photographs are collected. Consistency is the cheaper signal to act on — one contradiction inside the set is conclusive, where a rate needs a baseline to interpret.

### A test that reads its expectation from the thing under test measures nothing on its own

Task 1.2a's rules live in three tables, and the behavioural tests derive what they expect from those tables — `kept = category in VALUE_APPLIES_TO["fit"][value]`. That makes them precise about whether the *validator honours the table*, and completely blind to whether the table is right: **mutate the table and the expectation moves with it, so every derived test stays green.**

So the rule: **where a test's expectation is read from the thing under test, a second test states it literally, or the pair measures nothing.** `test_enums.py` pins all three tables as literals for exactly this reason, and the measurement is what proves it rather than the argument — mutation 5, dropping the sleeve words' narrowing, is caught by **exactly one test in 376**, and that test is the literal pin. Without it the mutation survives silently and the table can be edited to say anything.

The same shape has a second, sharper form worth knowing: **a `@parametrize` derived from the thing under test moves the failure from a named test to collection.** The first run of task 1.2a's mutation 1 reported `CAUGHT by 0 tests` because a parametrisation indexed `LAYERS_BY_CATEGORY[Category.TOP]` at import, so deleting that row made the module fail to load rather than fail an assertion. A suite that will not collect is a worse signal than a named test failing, and it is easy to misread as a survivor. State parametrisation cases literally where the mutation set will reach them.

### The backend mutation run, task 0.10

Thirteen mutations against the new integration suite. Twelve were caught by a named test; **one survived and is recorded rather than papered over.**

| # | Behaviour deleted | Caught by |
|---|---|---|
| 1 | `display_name` required → optional again | `test_register_requires_a_display_name` + 2 |
| 2 | `strip_whitespace` dropped from the constraint | `test_register_trims_the_display_name` + 1 |
| 3 | respelled as `Field(strip_whitespace=True)` | `test_register_rejects_a_display_name_that_is_only_whitespace` + 1 |
| 4 | `WWW-Authenticate` removed from login's `401` | `test_login_401_offers_the_bearer_challenge` |
| 5 | dummy-hash comparison skipped for an unknown email | `test_login_hashes_even_when_the_email_is_unknown` |
| 6 | ownership dropped from `GET /items/{id}` | `test_reading_another_users_item_is_404_not_403` |
| 7 | ownership dropped from `GET /items` | `test_list_items_returns_only_the_callers_items` + 1 |
| 8 | `short_id` collision no longer retried | `test_upload_retries_the_batch_when_a_short_id_collides` + 1 |
| 9 | `db.rollback()` removed from the retry | `test_upload_retries_the_batch_when_a_short_id_collides` + 1 |
| 10 | rows inserted `ready` instead of `processing` | `test_uploaded_rows_start_as_processing` |
| 11 | **`db.refresh` dropped after insert** | **nothing — survived** |
| 12 | fixture: `join_transaction_mode` dropped | 3 collision tests |
| 13 | fixture: per-test `rollback` → `commit` | the session-scoped row-count check |

Three of these are worth more than a row in a table.

**Number 3 is the reason mutation testing is not only about tests.** The mutation was to write the code *exactly as the stage file and `DECISIONS.md` 070 specified it*, and two named tests failed — which is how it was established that the specification was wrong rather than the implementation. `DECISIONS.md` 072.

**Number 5 is an event assertion standing in for something unassertable.** The dummy bcrypt comparison on an unknown email exists to close a timing channel (037), and timing cannot be asserted reliably. Counting calls to `verify_password` can be: without the dummy hash the route returns before it is ever reached. Same rule as 0.9's `NavigationStart` counting — assert the event, not the state afterwards.

**Number 13 defends the fixture rather than the application, and it is the one that would have gone unnoticed.** Turning the per-test `rollback()` into `commit()` leaves every assertion in the suite passing, because each test asserts against data it created and does not care whether the data survives. Nothing in a green suite distinguishes the two. What breaks is later runs: the database accumulates rows and eventually collides with itself. The defence is a session-scoped teardown comparing `users` and `items` counts across the run.

**And the honest one: number 11 survived.** `db.refresh` after the item insert is redundant — SQLAlchemy already returns the server defaults via `RETURNING` — so there is no behaviour left to defend, and no test was written to pretend otherwise. `DECISIONS.md` 075.

**A note on running mutations, learned the expensive way at this task.** The first attempt used a harness that restored each file in a `finally` block. It was killed by a timeout mid-mutation, the restore never ran, and the *entire next run* executed against a tree with `status='ready'` still baked into `_insert` — producing a table in which every mutation looked caught, by a test that was simply failing throughout. It was noticed only because one test appeared in all thirteen rows, including mutations it could not possibly relate to. **A mutation harness must verify a green baseline before it starts and after it finishes, and restore from a pristine copy rather than from memory.** A mutation table built on a red baseline is worse than no mutation table, because it reads as evidence.

**A second harness failure, found before task 1.1, and it is the opposite shape.** A mutation was applied to migration `0001` — renaming `uq_users_email` — and nothing failed. Read as a row in a table that says *survived*, and it would have supported exactly the wrong conclusion. The migration never ran: `conftest.py` calls `alembic upgrade head` once per session against a container that ordinarily already holds the revision, so the edited file was never executed by anything.

**A mutation that cannot execute is not a mutation that survived, and a table that conflates them reads as evidence for a claim nobody tested.** Before recording a survivor, establish that the mutated line runs at all — the cheapest check is a deliberately fatal mutation in the same file, which must fail loudly. Anything that is genuinely unreachable by the suite gets recorded as **inconclusive**, with the reason, and never as a row implying coverage was measured.

**Task 2.6 paid that second failure off, because it is the first task since 1.1 to add a migration.** A mutation to `0002_looks` executes only if the schema is rebuilt from it: `alembic downgrade 0001` with `DATABASE_URL` set to `TEST_DATABASE_URL` for that one command — never the value in `backend/.env`, which is the developer's own database — and then the next `pytest` re-upgrades from the mutated file. **The trap has a second half, and it was walked into at 2.6 before it was written down here:** the test database stays on the mutated schema after the run, so a control executed without downgrading again is red for the *previous* cycle's reason and reads as a broken deliverable rather than as a dirty database. Downgrade before every cycle, including the final control.

**The trap has a third half, walked into at task 3.1, and it is the one the two
above do not cover.** `0004`'s mutation set includes deleting the two indexes,
which means deleting them from `upgrade()` **and** from `downgrade()` — and a
`downgrade()` that no longer drops an object leaves it standing. The next
cycle's upgrade did not need to create it, the index was there from the control,
and the mutation came back **survived** when it had simply never been tested.
The reverse then bit on the way out: once a mutated `upgrade()` has skipped an
object, the *pristine* `downgrade()` fails on `DROP INDEX` for something that is
not there, alembic leaves the revision where it was, and every run after that is
against a stale schema. That one was invisible because the downgrade's stderr
was being discarded.

So, for a migration mutation specifically: **mutate `upgrade()` only, never
`downgrade()`, and read the downgrade's output rather than silencing it.** The
general rule underneath is 1.1's, one artefact along — a mutation to a migration
is only a measurement if the schema it describes is actually rebuilt from it, and
the half of the file that does the tearing down is part of what has to still
work for that to be true.

### The vision-service mutation run, task 1.2b

Sixteen mutations plus a fatal control, against `validate_tags`, the required-field check and the rendered rules. Run from a pristine copy, baseline green at both ends (353 passed before and after). **All seventeen caught, none survived** — with one caught in a way that is worth more than the row.

| # | Behaviour deleted | Caught by |
|---|---|---|
| 1 | `validate_tags` never retries; the first answer is accepted as-is | 12 tests |
| 2 | the give-up retries a third time instead of raising | 4 tests |
| 3 | the coercion log is dropped | 2 tests |
| 4 | the discarded values are dropped from the result | `test_the_discarded_value_survives_on_the_result` |
| 5 | both attempts' coercions are carried, not the accepted answer's | `test_only_the_accepted_answers_coercions_are_carried` |
| 6 | `_missing_fields` tests falsiness instead of `is None` | 16 tests |
| 7 | the blank `display_name` check is dropped | `test_a_blank_display_name_counts_as_missing` |
| 8 | `layer` dropped from `_REQUIRED_FIELDS` | 3 tests, incl. the literal pin |
| 9 | the narrowed words are not rendered into the prompt | 3 tests |
| 10 | the per-category `layer` table is dropped from the prompt | `test_the_layer_table_reaches_the_prompt_for_every_category` |
| 11 | `_categories` renders set order instead of declaration order | 3 tests |
| 12 | `PROMPT_VERSION` hashes the file instead of the rendered prompt | `test_the_prompt_version_covers_the_generated_vocabulary` |
| 13 | the correction no longer names the violation | 5 tests |
| 14 | `TaggingError` carries the first violation, not the second | `test_the_tagging_error_carries_the_second_violation` |
| 15 | the retry's `ValueError` is relabelled as a `TaggingError` | `test_a_retry_that_returns_nothing_usable_is_not_relabelled` |
| 16 | the prompt file loses its `{{VOCABULARY}}` placeholder | **the suite, at collection — no named test** |
| — | fatal control: `_build` reads the wrong report | 16 tests |

**Number 16 is a real limit on the guard 1.1 built, and it is not a defect.** Deleting the placeholder from the actual prompt file makes `app.services.vision` raise at import, so `test_vision.py` never collects and the run reports one `ERROR` and no failures. That is the guard working exactly as `DECISIONS.md` 080 intended — loud at import rather than silent at call time — but it means **`test_a_prompt_file_without_the_placeholder_raises_at_load` does not defend the real file.** It monkeypatches `PROMPT_PATH` to a stripped copy, so what it proves is that the guard's logic is right, not that the shipped prompt still has a placeholder. Nothing can prove the second by a test, because the import that would fail is the import the test file needs. Recorded because the previous subsection's rule — a suite that will not collect is a worse signal than a named test failing — has an exception here, and this is it: collection failure *is* the intended signal, and the harness must say so rather than print `CAUGHT by 0 tests` and let a reader guess.

**Number 6 is the falsy trap and it is why `is None` is spelled out.** `water_resistant: false` is legitimate on most of a wardrobe, so a truthiness test retries and then fails every garment that is not waterproof — sixteen tests catch it, which makes it look obvious. It was not: the same line reads correctly at a glance, and only `test_a_false_water_resistant_is_not_missing` states the case on purpose.

**Numbers 4, 5 and 14 are each caught by exactly one test, and all three are decisions rather than mechanisms.** Whether the discarded value survives, whose coercions `ItemTags` carries, and which of two violations reaches `error_message` are all choices a later reader could reverse while leaving the module working. One named test each is the whole defence, which is the argument for naming them after the decision rather than after the code.

### The wardrobe-grid mutation run, task 1.5 — the first on the frontend

Thirteen mutations plus a fatal control against the new frontend code, and four
against `GET /items`'s `limit` on the backend. Run from a pristine copy,
baseline green at both ends. **Two survived, both in the same place, and they
are the reason this run was worth doing.**

| # | Behaviour deleted | Caught by |
|---|---|---|
| M0 | fatal control: the store discards the rows it loaded | 9 tests |
| M1 | the store takes `GET /items`' default limit instead of passing one | 3 tests |
| M2 | the failed tile branches on the tags being null, not on `status` | 8 tests |
| M3 | the retag error stops branching on the documented `code` | 2 tests |
| M4 | a retag response is dropped instead of replacing the row | 2 tests |
| M5 | the retrying mark stops being per item in the store | 6 tests |
| M6 | the header counts loaded rows instead of the server `total` | `states the server total rather than the number of tiles` |
| M7 | the plural key is used for every count | `does not say "1 items"` |
| M8 | the empty state is not gated on the first load finishing | `does not show the empty state while the first load is in flight` |
| M9 | an untagged photograph gets an empty `alt` | `falls back to a described alt when the item has no name yet` |
| M10 | the in-flight retag guard is removed | `sends one retag while one is already in flight` |
| M11 | the spinner binds to "any retag in flight", not to this tile | **survived — 108 passed** |
| M12 | every tile shows the first retag error rather than its own | **survived — 108 passed** |
| B0 | fatal control: `GET /items` returns no rows | 3 tests |
| B1 | the default page size is 50 rather than 100 | `test_the_list_defaults_to_a_hundred_items` |
| B2 | the documented cap is raised, so an over-large limit is accepted | `test_the_limit_cap_is_two_hundred_and_over_it_is_rejected` |
| B3 | the cap clamps instead of rejecting | `test_the_limit_cap_is_two_hundred_and_over_it_is_rejected` |

**M11 and M12 are the same hole and it is a shape worth naming: the state was
tested and the binding was not.** `WardrobeStore` keeps retag state per item —
a `Set` of ids retrying, a `Map` of id to error key — and six store tests
assert exactly that. Every one of them passed with the template broken, because
a template can read a correct per-item collection and then bind it globally.
What made it invisible is smaller and more general: **every test that looked
like it covered this rendered a single item**, and with one tile on screen a
per-item signal and a global one are indistinguishable. Two tests now render
two failing tiles and assert the presence *and the absence*. `DECISIONS.md` 093.

**A note on the harness, which behaved differently here from pytest's.** The
equivalent of a collection error is a **build** failure: `ng test` compiles the
whole project before running anything, so a mutation that does not type-check
produces zero test results rather than a failure, and would read as "caught by
0 tests" if the harness only parsed vitest's output. It is detected separately
by matching `Application bundle generation failed` and reported as its own
outcome, on the same reasoning as 1.2a's misreported row.

**One row was thrown away rather than recorded.** The first M5 run listed
`authGuard > lets an authenticated user through` among its failures — a test
with no relationship to the mutated file. It did not reproduce in two further
mutated runs or five clean ones. It is recorded as an unexplained intermittent
in `AUDITS.md` **O-13** and *not* as a row in this table, because a mutation
table that contains one unexplained row is evidence for nothing.

### The upload-sheet mutation run, task 1.6

Twelve mutations plus a fatal control, run from a pristine copy with the
baseline green at both ends. **One survived**, and it was a test defect rather
than a code defect.

| # | Behaviour deleted | Caught by |
|---|---|---|
| U0 | fatal control: the store discards the rows it loaded | 12 tests |
| U1 | the pending strip binds every slot to the first entry | `renders one slot per pending file, each with its own src` · `names each slot after its own file, not after the first` |
| U2 | the per-file size check is dropped | 3 tests |
| U3 | the file-count check is dropped | `refuses more files than the server would take, and sends nothing` |
| U4 | the total is not moved when rows arrive | `moves the total by the number of rows the upload returned` · `puts the uploaded rows into the grid and moves the count` |
| U5 | the returned rows are appended instead of prepended | `puts the returned rows in front of the ones already loaded` |
| U6 | the upload error branches on the status, not the code | 4 tests |
| U7 | the size limit uses 1000² instead of 1024² | **survived — 155 passed.** Now `mirrors ten mebibytes, not ten million bytes` · `accepts a file of exactly the limit and refuses one byte more` |
| U8 | the empty state stops being gated on pending previews | `hides the empty state while previews are pending` |
| U9 | the sheet's open/close rule is inverted between the two inputs | `stays open after a camera capture` · `closes after a gallery pick` |
| U10 | the multipart field name stops being `files` | `posts every file under the field name files` |
| M-U | the object URLs are never revoked | `releases every object url it asked for once the rows arrive` · `drops the previews when the batch is rejected` |

**U7 is the whole finding, and it is this document's own rule catching the
document's own subject.** "A test that reads its expectation from the thing
under test measures nothing on its own" was written at 1.2a about a derived
`@parametrize`. Here every size expectation in `upload-sheet.spec.ts` was
written as `MAX_UPLOAD_BYTES ± 1`, imported from the component — so changing
the component's arithmetic to `1000 * 1000` moved the goalposts with it and the
suite did not move. The mutation is the exact confusion `CONVENTIONS.md` has a
section about, and the file that exists to catch it could not. The fix is to
transcribe the literal (`10_485_760`) from `CONVENTIONS.md`'s own sentence and
pin the constant to it in one test. **The limits that were *already* checked
against literals — 20 files, the "10 MB" in the message text — were caught
correctly**, which is what makes the shape legible: the two constants were
tested the same way and only one of them was self-referential.

**M-U was predicted to survive and did not, and the prediction being wrong is
worth more than the row.** It was declared inconclusive-by-design before the
run, on the reasoning that jsdom implements neither half of the object-URL API
so a revocation test could only ever assert against its own stub. It was caught
by two tests — which does not falsify the reasoning, it qualifies the result:
**those two tests prove the store called our stub, not that any browser
released anything.** Recorded as a weak catch rather than a clean one, on the
same principle as the collection-error row at 1.2a: a table that reported this
identically to U10 would be overstating it.

### What jsdom cannot reach, measured rather than assumed

`@angular/build:unit-test` names no `browsers` in `angular.json`, and the
builder's schema is explicit that this means "tests are run in a Node.js
environment using jsdom". Probed directly against the installed **jsdom
28.1.0** at task 1.6, because the upload sheet is the first feature whose
mechanism lives mostly outside what that environment implements:

```
URL.createObjectURL / revokeObjectURL   undefined
DataTransfer                            undefined
new FileList()                          throws — Illegal constructor
input.files = [File]                    throws — not of type 'FileList'
Object.defineProperty(input,'files')    works
input.showPicker                        undefined
input.capture                           attribute reflects; no property
HTMLDialogElement.showModal/show/close  undefined  (only the `open` attribute)
matchMedia / IntersectionObserver       undefined
ResizeObserver / scrollIntoView         undefined
getBoundingClientRect().height          0
```

Two of these changed the code rather than the tests, which is why they are
here and not only in `AUDITS.md`: the missing `<dialog>` methods decided that
the sheet is a plain element (`DECISIONS.md` 098), and the missing
`DataTransfer` decided that specs install an array through
`Object.defineProperty` and therefore exercise our handler without exercising
`FileList` semantics. **The list is a property of the gate, not of task 1.6**,
and it is written here so the next frontend task costs a re-read rather than a
re-measurement. It is also the reason `AUDITS.md` **O-14** grew rather than
closed. If `browsers` is ever configured, most of this list stops being true —
re-measure before trusting it.

**Extended at task 1.8**, because a filter bar is layout and URL state and the
list above measures neither. Probed against the same jsdom 28.1.0 and the same
builder:

```
getBoundingClientRect().width                           0
element.scrollWidth / clientWidth                       0 / 0
element.scrollLeft (set, then read)                     kept — and meaningless
element.scrollIntoView                                  undefined — CALLING IT THROWS
input[type=range] min=1 max=5, no value: .value         50   (a browser gives 3)
input[type=range] step snapping (set 2.7, step 1)       2.7  — not snapped
input[type=range] clamps above max (set 9, max 5)       5
connected checkbox.click()                              fires input and change
detached checkbox.click()                               checked flips, NO change event
router.navigate([...], { queryParams })                 resolves; router.url reflects it
Location.path(true)                                     reflects it
root ActivatedRoute.snapshot.queryParamMap              reads it
route.queryParamMap                                     one emission per navigation
queryParamsHandling: 'merge' / queryParams: {}          merges / clears
withComponentInputBinding() → input() signal            binds, and follows later navigations
RouterTestingHarness.create() / navigateByUrl           work
window.location.search after router.navigate            "" — MockPlatformLocation, never moves
history.replaceState                                    moves it, and leaves router.url STALE
```

**Four of these changed the code rather than the tests**, which is why they are
here. `scrollIntoView` throwing is why nothing scrolls the chip row for the
user. The range defaulting to 50 is why every handle carries an explicit
`[value]` — a test asserting an initial position would otherwise be asserting a
jsdom artefact. The missing `step` snapping is why the rounding lives in
`WardrobeStore.setFilters` rather than being trusted to the control. And the
last two lines together are why the URL is written only through the `Router`:
`history.replaceState` moves the address bar and desynchronises `router.url`,
and the gate can only see one of the two. `DECISIONS.md` 110, 113, 115.

**What this leaves unverifiable** is in `AUDITS.md` **O-14**: whether a pasted
filtered URL reopens filtered, and whether the chip row scrolls. Neither has a
test that could tell the truth from a lie.

**Extended at task 1.9**, because a tag editor is form controls, focus and a
destructive confirmation, and the lists above measure none of the three. Probed
against the same jsdom 28.1.0 and the same builder:

```
select.options / .value / .selectedIndex                work
select.value = 'no-such-option'                         value "" , selectedIndex -1
change on programmatic .value =                         does NOT fire
change on dispatchEvent(new Event('change'))            fires
select.disabled / option.selected                       supported
element.focus() -> document.activeElement               moves; focus event fires
plain <div>.focus()                                     does not take focus
<div tabindex="-1">.focus()                             takes focus
autofocus attribute on append                           NOT honoured
element.inert                                           NOT supported
window.confirm(...)                                     function; returns undefined ("Not implemented")
window.alert / window.prompt                            same
HTMLDialogElement.showModal / close                     still undefined
form.requestSubmit / reportValidity                     function
input.setCustomValidity                                 function
element.checkVisibility                                 undefined
```

**One of these decided a design and one decided every spec in the task.**
`window.confirm` exists as a function and returns `undefined`, which is falsy —
so a delete written as `if (confirm(...))` would **never proceed under any test
in this project**, and would read as thoroughly tested while its destructive
branch never ran. That is `DECISIONS.md` 098's shape a second time, and it is
why the delete is a two-press button (126). The missing `inert` is the other
half of the same decision: a modal confirmation would need a hand-rolled focus
trap, which is what 126 declined on cost.

And **`change` does not fire on a programmatic `.value =`** — which is not a
jsdom artefact, no browser does either. Every spec in this task dispatches the
event by hand, and nothing may depend on an assignment firing one. The
illegal-value line is the useful other half: assigning a value a `<select>` has
no option for leaves `value` as `""` and `selectedIndex` as `-1`, which is what
"the row carries a tag this category does not offer" looks like in the DOM, and
`tag-editor.spec.ts` asserts it.

Focus, by contrast, is **more** visible than it was at 1.6: `.focus()` moves
`document.activeElement`, the `focus` and `blur` events fire, and
`tabindex="-1"` works — so the delete button's disarm-on-blur is genuinely
gated, where the upload sheet's focus behaviour was not.

### The item detail mutation run, task 1.9

Sixteen mutations plus a control, run from a copy of the mirror with the
baseline green at both ends. **One survived, and the defect was in a test rather
than in the code.**

`M6` changed `route.snapshot.paramMap.get('id')` to `get('itemId')` and **all
296 tests passed.** The cause was `item-detail.page.spec.ts`'s `ActivatedRoute`
stub: `{ get: () => currentId }` answers *every* key with the same value, so it
could not tell the right parameter name from a wrong one. The stub now honours
the key and the same mutation fails 33 tests. **A stub that ignores its argument
is a stub that cannot fail**, which is the general form of this and is worth
more than the row.

**The three survivors declared before the run were all caught**, which is the
first time on this project that a full set of predictions has been wrong in that
direction:

| Declared | Result |
|---|---|
| the delete not removing the row from `items()` | caught, 2 tests |
| the `total` decrement firing for a fallback-fetched row | caught, 1 test |
| the category cascade clearing four of five fields | caught, 2 tests |

The first two were predicted to survive because `WardrobePage`'s constructor
reloads on every arrival, which makes the store mutation invisible on screen —
and that reasoning is still correct. What it missed is that the tests written
for them are **store-level**, deliberately, precisely because the page cannot
see the difference. The prediction was about the screen and the tests are not.

The control — `item` computed to always return `null` — fails 38 tests. An
earlier control renaming the computed did not compile, and per this document's
own rule that is **inconclusive rather than a catch**; it was replaced rather
than recorded.

### The polling mutation run, task 1.7

Seventeen mutations plus a fatal control, run from a pristine copy with the
baseline green at both ends. **One survived**, and it falsified a claim that
had been written into the task's plan as its central finding.

| # | Behaviour deleted | Caught by |
|---|---|---|
| M0 | fatal control: the reload throws away the rows it fetched | 4 tests |
| M1 | the loop re-arms at request time, so polls overlap | 10 tests |
| M2 | the reload decision compares counts instead of ids | `reloads on a change of membership that leaves the count alone` |
| M3 | the reload decision is inverted | 3 tests |
| M4 | the deadline is never checked | 5 tests |
| M5 | the poll writes `total` from its own response | `takes the header total from the reload and never from the poll` |
| M6 | the reload sets `isLoading` like `load()` does | `does not blank the grid while a poll reloads it` |
| M7 | a failed poll sets the load error | `keeps polling through a failed poll and reports nothing` |
| M8 | the effect is keyed on `processing()` rather than `awaitingTags()` | **survived — 180 passed.** Now `does not resume waiting for an abandoned item when a later batch finishes` |
| M9 | `POLL_INTERVAL_MS` 2000 → 3000 | 9 tests |
| M10 | `POLL_DEADLINE_MS` 180 000 → 90 000 | 6 tests |
| M11 | the deadline comparison `>=` → `>` | 5 tests — **declared an expected survivor before the run** |
| M12 | a mid-run batch does not push the deadline out | `gives a batch that arrives mid-run its own three minutes` |
| M13 | the retry never resumes waiting for an abandoned item | `waits for an abandoned item again once its retag succeeds` |
| M14 | `load()` no longer clears what the last visit gave up on | `waits again for everything after a fresh load` |
| M15 | the tile reads the stopped-waiting flag without the status | 2 tests |
| M16 | the page never stops the loop on destroy | `stops polling when the page is destroyed` |

**M8 is the finding, and what makes it worth the space is that the survivor
disproved the reason it was written.** The plan for this task named the
subtracted computed as its central design decision, on this reasoning: an
effect keyed on `processing()` would see a non-empty set and a null run the
instant giving up wrote its signal, and would restart the loop it had just
stopped. **That mechanism does not exist.** An effect that reads only
`processing()` no longer *depends* on the signal giving up writes, so it never
re-runs at all — which is precisely why nothing failed. The design is right and
the argument for it was wrong, and the two are not the same thing.

What is actually reachable is quieter: the loop stays stopped until something
else changes `items()`, and the next upload restarts it with the abandoned
rows back in the run. When *that* batch finishes, the loop keeps polling for an
item whose tile already says we stopped waiting for it — three more minutes of
the screen and the loop disagreeing, with nothing on screen to say so. That is
what the closing test asserts, and it is a smaller claim than the one it
replaced.

**M11 is the second declared survivor in two tasks to be caught**, after M-U at
1.6. It was declared expected-to-survive unless a test landed on the exact
deadline; the boundary test was written for it and five tests failed. The
declarations keep being wrong in the same direction, and they keep being worth
making — because the mutation that actually survived, both times, was one
nobody had predicted.

**M9 and M10 are 101's lesson applied before the fact rather than after.** Every
timing expectation in `wardrobe.store.spec.ts` could have been written as
`POLL_INTERVAL_MS ± 1`, which is exactly the shape that let the mebibyte
mutation survive at 1.6. `2000` and `180_000` are instead transcribed by hand
from `01-ARCHITECTURE.md` and `05-FRONTEND-SPEC.md`, pinned to the constants in
one test each, and the loops that drive the clock use the literals.

### Timers under the frontend gate, measured at task 1.7

The jsdom list above says nothing about time, and polling is entirely about
time. Probed against **vitest 4.1.10** on the same builder:

```
vi.useFakeTimers() replaces setInterval / setTimeout    yes
                   replaces queueMicrotask / Promise    no
Date.now() and performance.now() advance                yes, exactly
requestAnimationFrame                                   defined, and faked
rxjs interval(2000) / timer(180_000)                    driven by advanceTimersByTime
vi.getTimerCount() / vi.clearAllTimers()                work
vi.setSystemTime(+180s) fires pending timers            no — moves the clock only
HttpTestingController expectOne / flush / match         work, synchronously
DestroyRef.onDestroy on fixture.destroy()               fires
document.visibilityState via defineProperty             overridable
visibilitychange / focus / blur / pagehide / online     dispatchable and heard
real waiting inside a test (globalThis.setTimeout)      impossible — it is faked too
```

**And the one that decided how every polling test is written:**

```
await fixture.whenStable() under fake timers     never resolves
```

Angular's zoneless scheduler needs a task to run and a frozen clock never gives
it one. This is not academic: `whenStable` is used **62 times across 7 spec
files**. Adding `vi.useFakeTimers()` to `wardrobe.page.spec.ts`'s `beforeEach`
was measured rather than reasoned about — **19 of that file's tests fail, every
one on the 5-second timeout, and the suite goes from 2.1s to 96.4s.**

Three ways out, all measured:

- **`TestBed.tick()`** exists and renders synchronously under fake timers. This
  is the `whenStable` replacement the polling tests use.
- **`await vi.advanceTimersByTimeAsync(1)`** also flushes the scheduler.
- **`vi.useFakeTimers({ shouldAdvanceTime: true })`** keeps all 156 tests green
  — and does it by advancing the mock clock **1:1 with real time**, measured at
  200ms of drift over 200ms of real waiting. It buys compatibility by not being
  a fake clock in the way a deadline test needs, so it is safe by margin rather
  than by construction. **Refused for that reason.**

What ships instead is a **mid-test switch**: render under real timers exactly as
every existing test does, then `vi.useFakeTimers()`, then `TestBed.tick()` from
that point on. It is the only route that touches no existing test. One
consequence has to be respected and is written into the helper: **a run started
under real timers keeps its real timer**, so nothing may be `processing` at the
moment the clock freezes — the page tests render a `failed` tile and press its
retry to start a run on the far side of the switch.

**What a polling test proves and what it does not.** It proves the arithmetic:
a request every 2 seconds of mock time, the stop when the set empties, the stop
at 3 minutes, the stop on destroy, the query string on the wire, and the DOM
changing when a response lands. It does not prove that a browser's
`setInterval` holds 2 seconds under load or in a background tab — Chrome
throttles background intervals and can suspend them outright — nor that the
loop survives a real navigation or a bfcache restore, nor that five real
photographs finish inside 30 seconds, which is 1.3's serial tagging against a
real account and is visible only by eye or in a Stage 5 end-to-end run.
`AUDITS.md` **O-14** carries those.

### The filter-bar mutation run, task 1.8

Twenty-four mutations plus a control, run from a pristine copy with the
baseline green at both ends. **One survived**, and the three survivors declared
in advance were declared for the right reasons and were all wrong.

The control — `applyFilters` returning nothing — fails 29 tests, which is what
makes the rest of the table readable.

Caught, and the ones worth naming: dropping the null exemption; widening it
from per field to per row (`M6`, killed by the one test written for exactly
that row); `>=` to `>` and `<=` to `<` on both range ends; AND to OR across
dimensions; the grid rendering `items()` instead of `visible()`; the no-match
branch losing its `isEmpty` guard; **the empty branch losing its
`pending().length === 0` clause**, killed by 1.6's own test; the URL never
being written, never being read, or losing `replaceUrl`; a URL value skipping
the vocabulary check; the chip's pressed state going global; a swatch losing
its `aria-label`; and the panel starting open.

**The survivor, and it is a coverage hole rather than a bug.** Rounding the
value inside `setFormality` — the thing 115 says the bar must not do — survived
the entire suite, because the only test that dragged a handle with a fraction
dragged a **warmth** handle, and `setWarmth` is a second, near-identical method
making the same claim. Two methods, one test, and the untested one is
indistinguishable from a correct one. This is 1.5's finding from the other
side: there the state was tested and the binding was not; here one of two
identical paths was tested and the other was not. A second test now drags a
formality handle with `3.4`, and the mutation fails it by name.

**Three survivors were declared before the run and none of them survived** — the third consecutive run in which every declaration was wrong, after M-U at 1.6 and M11 at 1.7. The declarations keep being wrong in the same direction, and they keep being worth making: naming what is expected to survive is what turns a green table into evidence, and on all three runs the real survivor was one nobody had predicted.
The disclosure panel's visual state was expected to survive if the test only
asserted presence in the DOM — the tests assert `aria-expanded` and the range
count instead, and it was caught. `replaceUrl` was expected to survive if the
spy on `Router.navigate` were refused as too white-box — the spy was kept, and
it was caught. The horizontal scroll of the chip row was declared **unmutatable**
rather than a survivor, and it remains so: the gate has no layout.

### The profile and geocoding mutation run, task 2.2

Nineteen mutations plus a control, run from a pristine copy with the baseline
green at both ends (670 passed before and after). **Two survived and both were
fixed rather than recorded**, which makes this the first backend run where a
survivor changed the tests rather than only the table.

The control — dropping `home_city` from `UserResponse` — fails
`test_writes_every_field_in_the_documented_body`, which is what makes the rest
of the table readable.

Caught, and the ones worth naming: reading `body["results"]` instead of
`.get("results", ())`, which is the whole of the no-match finding; dropping
`exclude_unset`; removing the empty-body guard; `extra="forbid"` weakened to
`"ignore"`; the height bounds removed and, separately, weakened from `ge`/`le`
to `gt`/`lt`, which dies only on the test that asserts both endpoints of the
range; the query no longer stripped before it is measured; the minimum query
length dropped to 1; `geocoding_unavailable` swapped for `forecast_unavailable`;
the search route's auth dependency removed; the `count` parameter dropped;
`country` read with `[]` instead of `.get`; `db.commit()` removed, which dies on
the one test that re-reads the row through `db.refresh` rather than trusting the
response body; and the seeded home location removed from the insert, both
entirely and coordinates-only.

**Survivor 1 — the home-location rule needs two checks and only one of them is
usually reachable.** `UserUpdate` refuses a partial home location twice: once on
which keys arrived, once on whether their values agree. Deleting the *keys*
check left all 669 tests green, because every partial request the tests sent —
a city alone, coordinates alone, a half-cleared triple — is already refused by
the values check. The one request that reaches the keys check is
`{"home_city": null}` on its own, which would otherwise be a `200` that clears a
city and leaves its coordinates behind. This is 1.8's shape from a new angle:
there, one claim was made by two near-identical methods and only one was
tested; here, one rule is enforced by two checks and only one is reachable
through the tests that were written. A test named for exactly that request now
kills it.

**Survivor 2 — `RESULT_LIMIT` was tested against itself, which is 1.6 repeated
after the lesson was written down.** `test_sends_the_parameters_the_provider_documents`
asserted `"count": str(RESULT_LIMIT)`, read out of the module under test, so
changing the constant from 5 to 3 moved the expectation with it and the suite
stayed green. `04-API-SPEC.md` says "up to 5". The literal is now transcribed
from that sentence and a second test pins the constant to it, exactly as 1.6 did
for `MAX_UPLOAD_BYTES` and 1.7 for `2000` and `180_000`. **The rule was already
in this document, in `CONVENTIONS.md` and in `DECISIONS.md` 101, and it was
broken anyway** — which is the honest thing to record about it: the failure mode
is not ignorance of the rule, it is that a derived expectation looks more
correct than a literal while it is being written.

One mutation was discarded rather than recorded as a survivor. Giving
`LocationSearchResponse.results` a default of `[]` changes no behaviour, because
the only construction of that model supplies the field on every path — a
mutation that cannot be reached is not a mutation that survived, which this
document has required since 1.1.

### The migration 0004 mutation run, task 3.1

Five mutations plus a control, run in the scratchpad mirror with the baseline
green at both ends and the database downgraded to `0003` at the start of every
cycle. **One survived, and adding the test that kills it is the substantive
change this task made to the suite** — so the baseline moves inside the run:
mutations 1 and 2 were measured against 875, mutation 3 against 875 and then
against 876, and 4 and 5 against 876. The final control is 876.

| # | Mutation | Result |
|---|---|---|
| 1 | the `CHECK` deleted from `0004`'s `upgrade()` | 3 failed |
| 2 | `wear_count` loses `server_default` and `NOT NULL` | 1 failed |
| 3 | both `create_index` calls deleted from `upgrade()` | **survived** → 1 failed after |
| 4 | `ck_looks_feedback_values` dropped from `EXPECTED_NAMES` | 1 failed |
| 5 | `FEEDBACK_UP` changed from `1` to `2` in the model | 1 failed |

**Mutation 3 is the one worth having run.** Both indexes deleted, and all 875
tests stayed green — because **an index changes no result, only the plan**, and
nothing in this suite asserts on a plan. The index half of `AUDITS.md` O-25 was
about to be closed with two objects that no test could tell were missing, which
is the shape this document has objected to since 1.1 in the other direction: a
row that reads as coverage and is not. `test_the_two_indexes_0004_builds_exist`
now reads `pg_indexes` and compares it against the two names, which is
`test_db_naming.py`'s move — compare the artefacts directly, because behaviour
cannot see the difference — one artefact along, and against the database rather
than against the metadata, since `Table.constraints` does not hold an index.

**Mutation 5 is what makes `FEEDBACK_UP` and `FEEDBACK_DOWN` load-bearing rather
than decorative.** Changing the constant to `2` turns
`test_the_feedback_check_admits_the_two_named_values_and_null[2]` red on an
`IntegrityError`: the parametrisation is derived from the module under test, so
ordinarily it would move with the mutation — but here the *database* holds the
literal, written by the migration, and the two cannot move together. This is the
one shape where a derived expectation is safe, and it is worth naming beside the
warning two subsections above: it is safe because the second copy is in
PostgreSQL and is not editable from Python.

Mutation 4 needs no database and is `test_db_naming.py` doing exactly its job.
Mutations 1 and 2 are the DDL that a column list cannot show.

### The trip endpoints mutation run, task 4.4

Ten mutations, run in the scratchpad mirror from a pristine copy with the
baseline green at both ends. **One survived, and adding the test that kills it is
the substantive change this task made to the suite** — so the baseline moves
inside the run, exactly as it did at 3.1: mutations 1 to 9 were measured against
1088, mutation 10 against 1088 and then against 1089.

| # | Mutation | Result |
|---|---|---|
| 1 | `_MARKED` narrowed to `is_saved` alone | 1 failed |
| 2 | the trip-length half of `trip_too_long` deleted | 1 failed |
| 3 | the horizon half of `trip_too_long` deleted | 1 failed |
| 4 | `_by_day`'s ordinal off by one | 1 failed |
| 5 | repack writes a second trip instead of updating its own | 1 failed |
| 6 | `MIN_WARDROBE_ITEMS` back to `POST /looks/suggest`'s six | 1 failed |
| 7 | the detach and delete moved **above** the model call | 1 failed |
| 8 | `db.flush()` dropped before the looks are written | 1 failed |
| 9 | shuffled `occasions` days accepted | 1 failed |
| 10 | `ORDER BY for_date` dropped from the trip's own look read | **survived** → 1 failed after |

**Mutation 7 is the one this task was run to check.** It moves the detach and the
delete above `pack_trip`, which is how a reader writes a repack without thinking
about it and which `AUDITS.md` O-32's three written options all leave open. It is
caught by `test_a_stylist_failure_leaves_the_existing_looks_alone`, and that test
exists because the mutation was anticipated rather than the other way round —
which is the honest order to record, since a test written after a surviving
mutation and a test written to pin a decision look identical in the file.

**Mutation 10 is the survivor — the eighth on this project, and the third instance of the pattern 1.8 named.**
Deleting the `ORDER BY` left all 1088 tests green, because every trip test in the
suite wrote its looks in the order it expected them back — so insertion order and
date order were the same list and no assertion could tell them apart. It is
`AUDITS.md`-shaped rather than a bug: `04-API-SPEC.md` specifies the ordering, the
route implements it, and nothing measured it.
`test_the_looks_come_back_in_date_order_however_they_were_written` plants day 3,
then day 1, then day 2, which is the only arrangement that can fail. The pattern
is 1.5's and 1.8's: **a claim that is only ever exercised in the one arrangement
where it cannot be wrong.**

Mutations 2 and 3 are the two halves of one code, and they are worth having run
separately: a single test asserting `trip_too_long` would have been satisfied by
either half alone, and the two conditions are reached by different requests
(`DECISIONS.md` 201). Mutation 8 is the fatal control — without the flush the
trip has no `id` when its looks are written — and it is caught by name rather
than by a collection error, which is what 1.2a asked of this harness.

### What mutation testing has actually found on this project

Worth stating plainly, because it is not what the technique is usually sold for: **on this project mutation testing has found more false claims than bugs.**

- 0.10, mutation 3: writing the code exactly as `STAGE-0` and `DECISIONS.md` 070 specified it failed two named tests, which is how the *specification* was established to be wrong rather than the implementation. `DECISIONS.md` 072.
- 0.10, mutation 11: `db.refresh` survived, which established that a comment describing a behaviour SQLAlchemy does not have had been believed and copied. `DECISIONS.md` 075, closed at 040.
- Before 1.1: a replacement comment for `db/base.py` claimed the naming convention is what 037, 040 and 052 match on. Mutating the convention broke nothing, which located the real load in migration `0001`'s literals — and caught the false claim *between writing it and committing it*. `DECISIONS.md` 077.

- 1.2a: seven mutations plus a fatal control, all caught, baseline green at both ends — and the finding is not in the table. **The harness misreported one row.** Dropping `LAYERS_BY_CATEGORY`'s `top` entry printed `CAUGHT by 0 tests` beside a mangled filename, because the run had produced a pytest `ERROR` line and the harness only parsed `FAILED`. It was a collection error dressed as a survivor. Both halves were fixed — the parsing, and the derived `@parametrize` that caused the collection to fail at all — and the mutation now fails `test_the_layer_table_covers_every_category` by name. **A mutation table that misreports one row reads as evidence for every row in it.**

- 1.2b: seventeen mutations, all caught — and the finding is again about a claim rather than a bug. Number 16 established that `test_a_prompt_file_without_the_placeholder_raises_at_load` does not defend the shipped prompt file, only the guard's logic, because the real failure happens at import and takes the test module with it. The test's name does not say that and its docstring implied otherwise; both now do.

- 1.5: the first two genuine survivors on the project, and the first run on the frontend. Both were the same false claim — that retag state is per item — held by six passing tests that only ever exercised one item. The technique found a coverage hole rather than a bug, in code that was already green, linted and type-checked.

- 1.7: the fourth survivor, and the first that killed an *argument* rather than a test or a binding. M8 established that the stated reason for the task's central design decision described a mechanism that cannot happen — an effect that stops reading a signal stops re-running on it — while the decision itself remained correct on narrower grounds. The technique found a false explanation in a document, in code that was green, linted and type-checked, and that nobody would have found by reading, because reading is how the explanation got written.

- 1.8: the fifth survivor, and the pattern it belongs to is now worth stating on its own. **Where one claim is made by two near-identical pieces of code, the tests reliably exercise one of them and the suite cannot tell the difference.** At 1.5 it was per-item state: six tests, every one rendering a single item, where a per-item signal and a global one are indistinguishable. At 1.8 it was two range methods making the same "this rounds nothing" claim, with only a warmth handle ever dragged with a fraction, so rounding inside the formality one survived the whole suite. The two look unrelated and are the same shape: **the untested copy is invisible precisely because the tested copy passes**, and reading cannot find it, because the code that was not exercised is the code that looks right. The instances differ; what to do about them does not — when a claim has more than one site, test every site, and prefer one site where the duplication is avoidable.

- 1.6: the third survivor, and the first that was a *test* rather than a binding. `MAX_UPLOAD_BYTES` was mutated from 1024² to 1000² and nothing failed, because every expectation about it was written in terms of it. Same lesson as 1.5 from the opposite direction — there the state was tested and the binding was not, here the behaviour was tested against itself. Both were found in code that was green, linted and type-checked, and neither would have been found by reading.

- 2.2: the sixth and seventh survivors, and the second one is the first **repeat**. A constant was tested against itself — the identical failure 1.6 found in `MAX_UPLOAD_BYTES`, after the rule had been written into this document, into `CONVENTIONS.md` and into `DECISIONS.md` 101, and after 1.7 had applied it correctly to two literals on purpose. The technique caught it a second time in code that was green, linted and type-checked. **A lesson written down is not a lesson enforced**, and nothing in this project can enforce this one except deleting the behaviour and looking.

- 4.4: the eighth survivor, and the third instance of 1.8's shape after 1.5 and 1.8 itself. A specified `ORDER BY` was deleted and 1088 tests stayed green, because every test that could have measured it wrote its rows in the order it expected them back. **The arrangement that would falsify a claim is exactly the arrangement a test author does not reach for**, since the natural way to set a fixture up is the way the answer should come out. Found in code that was green, linted and type-checked, against a line `04-API-SPEC.md` states explicitly.

- 4.5: **the fourth instance of 1.8's shape, and the first that is not a mutation finding at all** — it belongs in this list anyway, because the shape is what the list is for. 4.5's own mutation run was ten mutations, ten killed, no survivors; this was found by the suite, before the run, and it is the first instance where the shape produced a **false pass over a real bug** rather than an untested claim. The chip rows on the trip form are a nested `@for`, and the inner one declares its own `$index`, which shadowed the day's — so tapping *work* on day 3 wrote it to day 2. Two tests touched that code. `sends the occasions the user chose, numbered in day order` clicked **row 1, chip 2** and caught it. `changes one day without touching the others` clicked **row 2, chip 1**, and the shadowed write landed on index 1, which is the index its expectation named — so it **passed with the bug in place and failed once the bug was fixed**. Transposed coordinates are the same trap as 4.4's insertion order one dimension down: the arrangement that would falsify the claim is the one nobody reaches for, and here it is narrower still, because the two indices only have to be *equal* for the confusion between them to be invisible. What to do about it is 1.8's instruction with a number in it: **where a fixture has two coordinates, make them differ**, and say in the test why they differ.

The lesson generalises: the assertion under test is often a sentence in a document, not a branch in the code. Deleting the behaviour is the only way to find out whether the sentence was ever true.

---

## Layer 4 — E2E with Playwright

TypeScript, Page Object Model — the same structure as the Jones assignment.

### The key mechanism: `USE_FAKE_AI`

The backend reads an environment flag. When `USE_FAKE_AI=true`, `vision.py` and `stylist.py` answer without calling OpenAI.

**Neither answers with a recorded fixture, and the stylist cannot.** `vision.py` returns a hand-written placeholder until task 5.1 records real ones — a rule broken on purpose with a name on it, `DECISIONS.md` 081. `stylist.py` returns a look **built from the wardrobe it was handed**: `short_id`s are generated per row by `scripts/seed_demo.py`, so a fixture carrying literal ids would name items that do not exist in the database it is running against, and 2.5's rule 1 — the hallucination guard — would answer `502` to every fake call. Journeys 6 and 7 below exist to see a look card; a fake that can only produce a `502` would make both of them assert the opposite of what they are for. `DECISIONS.md` 159.

```python
# app/services/vision.py
async def tag_item(image_url: str, correction: str | None = None) -> dict[str, Any]:
    if settings.USE_FAKE_AI:
        return dict(_FAKE_TAGS)
    ...
```

**Corrected at task 1.2b against the file.** This block printed `-> ItemTags`, `_fake_tags_for(image_url)` and `_call_openai(image_url)`, none of which have ever existed: `tag_item` returns the model's raw dict and `ItemTags` is `validate_tags`'s return type. `03-AI-CONTRACTS.md` named this document as one of the three that disagreed about the signature and only its own prose was fixed at 1.1, which is how a corrected claim outlived the code sample making it. The fake is one hand-written dict until task 5.1 (`DECISIONS.md` 081), not one per filename.

This makes the entire E2E suite deterministic, free, and fast. It is also exactly what a real QA engineer does with any third-party dependency, and it is a strong thing to be able to explain in an interview.

Fixtures live in `backend/tests/fixtures/ai/` and are **real recorded responses**, captured once from the live API and committed. Hand-written fixtures drift from reality; recorded ones do not.

### Page objects

```
e2e/pages/
  LoginPage.ts
  WardrobePage.ts     uploadFiles(), waitForTagging(), filterByCategory(), itemCount()
  ItemDetailPage.ts   editTag(), save(), retag()
  StylistPage.ts      requestLook(), lookCard(), itemsInLook()
  TripPage.ts         planTrip(), selectDay(), packingListItems()
```

Locators use `getByRole` and `getByLabel` first, `data-testid` only where the accessible name is genuinely ambiguous — for example individual grid tiles, which need `data-testid="item-tile-{shortId}"`.

### The journeys

| # | Test | Asserts |
|---|---|---|
| 1 | Register → land on empty wardrobe | empty state is visible with its one CTA, **Add your first items** |
| 2 | Upload 3 images → tiles appear immediately | 3 tiles in `processing` before any tag arrives |
| 3 | Tagging completes → tags render | polling resolves, tiles show `display_name` |
| 4 | Filter by category | count matches, chip reflects selection |
| 5 | Edit a tag → persists across reload | `user_edited` badge shown |
| 6 | Request a look on the demo wardrobe | look card renders with ≥ 3 items and shoes |
| 7 | Every item in the look exists in the wardrobe | **the hallucination guard, at UI level** |
| 8 | Save a look → appears in saved list | *(Stage 3)* |
| 9 | Plan a 4-day trip | 4 day tabs, packing list < 16 items | *(Stage 4)* |
| 10 | Stylist with < 6 items | button disabled, explanation shown |
| 11 | Tagging failure → retry affordance | failure fixture produces ⚠ tile with a working retry |
| 12 | "Style around this" from item detail | the returned look contains that exact item |
| 13 | Swap the shoes in a look | all other items unchanged, the rejected shoe absent |
| 13a | Swap the shoes on day 3 of a trip | day 3 changes, the other days do not, and the packing list moves with it |

Journeys 12 and 13 are the most reliable assertions in the whole suite — the requested item is either in the DOM or it is not, with no judgement involved. Worth writing early.

Test 11 needs a fixture that deliberately fails. Do not skip it — error paths are where a QA-oriented submission distinguishes itself, and it is exactly the kind of case the Jones assignment rewarded.

**Two things only this layer can prove, both owed from task 0.9.**

**`novalidate` on the auth forms.** Without it the browser's own constraint validation blocks submission and shows an untranslatable bubble before our i18n messages render. **The unit suite cannot defend this and it was wrong to imply otherwise:** the page specs trigger submission with `form.dispatchEvent(new Event('submit'))`, which bypasses constraint validation entirely, and jsdom's `requestSubmit()` fires the handler even with an invalid required field. Adding a native `required` attribute to a field leaves all 72 tests green. Only a real browser rejects it.

**Change detection.** The component specs call `fixture.whenStable()` after every interaction, which forces a change-detection cycle. Zoneless Angular re-renders only when something marks the view dirty, so those specs cannot distinguish "the view was marked dirty" from "the harness ran change detection anyway" — an interaction that updates form state without a template-bound event would leave them green and the browser stale. Playwright is where that closes, because nothing in it can force a render. **Task 5.3 owns it:** one journey must type an invalid value into a form and assert the validation message appears with no programmatic step in the loop. `DECISIONS.md` 070.

### Deliberate bug documentation

If a real defect is found during development that will not be fixed before submission, document it with `test.fail()` and a comment naming the expected versus actual behaviour. A test suite that honestly records a known bug reads as more mature than one that hides it.

---

## Layer 5 — AI evaluation, the golden dataset

This layer answers "is the AI any good?" and it is the part most capstone projects skip entirely.

### Building the dataset

30 garment photos spanning every category, hand-labelled by you with the correct tags. Store as `tests/fixtures/golden/{filename}.json` alongside the images. Include hard cases on purpose: a patterned item, a layered photo, a dark item on a dark background, a shoe photographed at an angle.

### The metrics

```python
@pytest.mark.eval   # excluded from CI, run manually
def test_vision_accuracy_on_golden_set():
    results = [tag_item(img) for img in GOLDEN_IMAGES]

    category_acc = accuracy(results, "category")
    warmth_within_1 = within_tolerance(results, "warmth", tolerance=1)
    color_acc = accuracy(results, "color_primary")

    assert category_acc >= 0.90
    assert warmth_within_1 >= 0.85
    assert color_acc >= 0.80
```

Targets, and why they differ:

| Metric | Target | Reasoning |
|---|---|---|
| `category` accuracy | ≥ 90% | 7 coarse classes; anything lower means the pipeline is broken |
| `warmth` within ±1 | ≥ 85% | An ordinal judgement; ±1 is genuinely ambiguous even between two humans |
| `color_primary` accuracy | ≥ 80% | Lighting makes beige/white and navy/black legitimately hard |
| `fit` accuracy | ≥ 70% | Hardest field; report it, do not gate on it |

Record every run in `docs/eval-results.md` with the date, model, and prompt version. **A chart of accuracy improving as the prompt was refined is one of the strongest artefacts you can put in a capstone defence** — it shows measurement, iteration, and evidence rather than assertion.

### Evaluating the stylist

Harder, because there is no single correct outfit. Do not try to score taste. Score **rule compliance**, which is objective:

```python
@pytest.mark.eval
def test_stylist_obeys_weather_rules():
    for temp, requires_outerwear in [(32, False), (25, False), (12, True), (5, True)]:
        response = suggest_looks(DEMO_WARDROBE, context_at(temp))
        # `.items` is the hydrated shape `POST /looks/suggest` returns at 2.7.
        # `suggest_looks` itself answers `item_ids` — see 03's response schema.
        has_outer = any(i.category == "outerwear" for i in response.looks[0].items)
        assert has_outer == requires_outerwear
```

Run 10 times per temperature and report the compliance rate. Target ≥ 90%. Also assert structural validity: shoes present, no double outer layer, formality spread ≤ 2, every ID real.

---

## CI

`.github/workflows/ci.yml`, on push and pull request:

```
backend:  ruff → mypy → pytest (unit + contract + integration, Postgres service container)
frontend: npm ci → ng lint → ng build --configuration production
e2e:      start backend with USE_FAKE_AI=true → serve frontend build → playwright test
report:   upload Playwright HTML report and traces as artefacts
```

Tests marked `eval` are excluded via `-m "not eval"`. CI never needs an OpenAI key, and CI must be green before merging to `main`.

**The frontend line above is wrong by omission and is not corrected here, because correcting it is writing the pipeline.** Neither `ng lint` nor `ng build` reads a `.spec.ts` — lint does not type-check and `tsconfig.app.json` excludes specs from the build — so the job as written runs none of the frontend suite this document requires two sections above, and would not notice it failing to compile. It did not: the suite was unrunnable from 2026-08-16 to 1.5. `AUDITS.md` **O-13** owns it, against whoever writes `ci.yml`.

---

## Definition of done, per stage

A stage is not complete until:

1. All acceptance criteria in the stage file pass.
2. New logic has unit tests. New endpoints have integration tests.
3. The stage's E2E journeys pass locally and in CI.
4. `PROGRESS.md` is updated and any non-obvious choice is in `DECISIONS.md`.
- 4.6: **the fifth instance, and the first where the false pass came from the browser rather than from the fixture.** The packing list's rows are real `<input type="checkbox">` elements, and a click toggles `checked` natively whether or not the component wrote anything. Two tests asserted on `input.checked` and both passed against a `toggle()` mutated to **add-only, never remove**: the first click set the state and the DOM, the second click flipped the DOM back on its own, and because the signal did not change, Angular re-rendered nothing to correct it. The state was wrong and the assertion could not see it. The fix is to assert on something **bound to the signal** — here the `line-through` class on the row's label — and `input.checked` keeps one test of its own, which is now a claim about the binding rather than about the state. The shape generalises past checkboxes: **an assertion on a control's own interactive property is an assertion about the browser, not about the code**, and any control the user can change directly — checkbox, radio, `<details>`, a text input's `value` — has this hole. 4.6's run was 22 mutations, 19 killed. Of the three that survived, one is equivalent (`get(null ?? '')` and an explicit null guard cannot be told apart), one is deliberate redundancy in the 404 branch (the documented code and a bodyless status, and no response can separate them), and one is **masked by a second guard** — the page filters unhydrated packing ids and the list would drop them anyway, which was confirmed by removing both at once and watching the test fail.

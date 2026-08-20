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
- `enums.py` — `subcategory` validity per `category`, all 7 categories; and from task 1.2a the rest of the category-dependent rules, both directions per category: `fit` and `length` applicability and their narrowed words, and `layer`'s admitted set and answer for each of the seven — including the one category, `top`, whose answer is an error rather than a value
- `short_id` generation — alphabet excludes `0O1IL`, correct length, no repeat across a large sample. **Collision retry is not here**, and the original wording was wrong to place it: what detects a collision is the `uq_items_short_id` constraint, so the retry cannot run without a database. Task 0.7 shipped the pure half; task 0.10 owns the retry with the rest of the row-writing tests
- `validate_tag_dict()` — every coercion and every rejection path
- `validate_tags()` — the retry and the give-up, with the vision call mocked. From task 1.2b that means: a clean answer accepted without a call at all, every coercion accepted and never retried, the `top`/`layer` error retried once with the violation in the correction, the give-up after exactly one retry, the eleven required fields each missing in turn, and the coercion log. The signature is `async validate_tags(raw, image_url)` — the URL is there because the retry is a second call to the model
- `vision.py`'s rendered prompt — the category rules, **pinned literally**. Every other prompt assertion in that file derives its expectation from `enums.py` and would move with a mutated table; these are transcribed from `02-DATA-MODEL.md`, for the reason two subsections below
- `validate_look_response()` — all eight rules, each failing independently, including anchor present and locked items preserved

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

### What mutation testing has actually found on this project

Worth stating plainly, because it is not what the technique is usually sold for: **on this project mutation testing has found more false claims than bugs.**

- 0.10, mutation 3: writing the code exactly as `STAGE-0` and `DECISIONS.md` 070 specified it failed two named tests, which is how the *specification* was established to be wrong rather than the implementation. `DECISIONS.md` 072.
- 0.10, mutation 11: `db.refresh` survived, which established that a comment describing a behaviour SQLAlchemy does not have had been believed and copied. `DECISIONS.md` 075, closed at 040.
- Before 1.1: a replacement comment for `db/base.py` claimed the naming convention is what 037, 040 and 052 match on. Mutating the convention broke nothing, which located the real load in migration `0001`'s literals — and caught the false claim *between writing it and committing it*. `DECISIONS.md` 077.

- 1.2a: seven mutations plus a fatal control, all caught, baseline green at both ends — and the finding is not in the table. **The harness misreported one row.** Dropping `LAYERS_BY_CATEGORY`'s `top` entry printed `CAUGHT by 0 tests` beside a mangled filename, because the run had produced a pytest `ERROR` line and the harness only parsed `FAILED`. It was a collection error dressed as a survivor. Both halves were fixed — the parsing, and the derived `@parametrize` that caused the collection to fail at all — and the mutation now fails `test_the_layer_table_covers_every_category` by name. **A mutation table that misreports one row reads as evidence for every row in it.**

- 1.2b: seventeen mutations, all caught — and the finding is again about a claim rather than a bug. Number 16 established that `test_a_prompt_file_without_the_placeholder_raises_at_load` does not defend the shipped prompt file, only the guard's logic, because the real failure happens at import and takes the test module with it. The test's name does not say that and its docstring implied otherwise; both now do.

- 1.5: the first two genuine survivors on the project, and the first run on the frontend. Both were the same false claim — that retag state is per item — held by six passing tests that only ever exercised one item. The technique found a coverage hole rather than a bug, in code that was already green, linted and type-checked.

The lesson generalises: the assertion under test is often a sentence in a document, not a branch in the code. Deleting the behaviour is the only way to find out whether the sentence was ever true.

---

## Layer 4 — E2E with Playwright

TypeScript, Page Object Model — the same structure as the Jones assignment.

### The key mechanism: `USE_FAKE_AI`

The backend reads an environment flag. When `USE_FAKE_AI=true`, `vision.py` and `stylist.py` return recorded fixtures instead of calling OpenAI.

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
| 1 | Register → land on empty wardrobe | empty state is visible with both CTAs |
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

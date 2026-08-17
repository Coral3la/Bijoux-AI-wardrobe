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
| Frontend unit — services, guards, interceptors, models, pages | Vitest | yes | no |
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
- `enums.py` — `subcategory` validity per `category`, all 7 categories
- `short_id` generation — alphabet excludes `0O1IL`, correct length, no repeat across a large sample. **Collision retry is not here**, and the original wording was wrong to place it: what detects a collision is the `uq_items_short_id` constraint, so the retry cannot run without a database. Task 0.7 shipped the pure half; task 0.10 owns the retry with the rest of the row-writing tests
- `validate_tag_dict()` — every coercion and every rejection path
- `validate_tags()` — the retry and the give-up, with the vision call mocked
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
def fake_vision(monkeypatch):
    def _tag(image_url: str) -> dict:
        return load_fixture("vision/white_shirt.json")
    monkeypatch.setattr("app.services.vision.tag_item", _tag)
```

What gets covered:

- **Upload returns 202 before tagging completes.** Assert `status == 'processing'` in the response body — this is the core UX promise and it should be enforced by a test.
- **The upload rejection paths, without a database.** Task 0.7 covers `415` (text, SVG, empty, truncated), `413`, `415`-before-`413` on an over-large non-image, one bad file rejecting a whole batch, the `422` on 0 and on 21 files, the `502` on a storage failure, and `401` on every route — with `get_db` overridden by a stub that raises on *attribute access* and `cloudinary.uploader.upload` monkeypatched to raise if called. That stub is the assertion: it is what proves "every file is decided before any file is uploaded" rather than assuming it. It raises on use rather than on call because FastAPI resolves every dependency before the handler runs, so a call-raising stub would fail requests the route rejects first.
- **Background task transitions the row** to `ready` with populated tags.
- **Tagging failure** sets `status='failed'` and `error_message`, and does not raise into the request.
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

### What mutation testing has actually found on this project

Worth stating plainly, because it is not what the technique is usually sold for: **on this project mutation testing has found more false claims than bugs.**

- 0.10, mutation 3: writing the code exactly as `STAGE-0` and `DECISIONS.md` 070 specified it failed two named tests, which is how the *specification* was established to be wrong rather than the implementation. `DECISIONS.md` 072.
- 0.10, mutation 11: `db.refresh` survived, which established that a comment describing a behaviour SQLAlchemy does not have had been believed and copied. `DECISIONS.md` 075, closed at 040.
- Before 1.1: a replacement comment for `db/base.py` claimed the naming convention is what 037, 040 and 052 match on. Mutating the convention broke nothing, which located the real load in migration `0001`'s literals — and caught the false claim *between writing it and committing it*. `DECISIONS.md` 077.

The lesson generalises: the assertion under test is often a sentence in a document, not a branch in the code. Deleting the behaviour is the only way to find out whether the sentence was ever true.

---

## Layer 4 — E2E with Playwright

TypeScript, Page Object Model — the same structure as the Jones assignment.

### The key mechanism: `USE_FAKE_AI`

The backend reads an environment flag. When `USE_FAKE_AI=true`, `vision.py` and `stylist.py` return recorded fixtures instead of calling OpenAI.

```python
# app/services/vision.py
async def tag_item(image_url: str) -> ItemTags:
    if settings.USE_FAKE_AI:
        return _fake_tags_for(image_url)   # deterministic, keyed by filename
    return await _call_openai(image_url)
```

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

---

## Definition of done, per stage

A stage is not complete until:

1. All acceptance criteria in the stage file pass.
2. New logic has unit tests. New endpoints have integration tests.
3. The stage's E2E journeys pass locally and in CI.
4. `PROGRESS.md` is updated and any non-obvious choice is in `DECISIONS.md`.

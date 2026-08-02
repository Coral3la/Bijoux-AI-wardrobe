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
| Frontend unit — stores, pipes | Vitest | yes | no |
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
- `enums.py` — `subcategory` validity per `category`, all 7 categories
- `short_id` generation — alphabet excludes `0O1IL`, correct length, collision retry
- `validate_tags()` — every coercion and every rejection path
- `validate_look_response()` — all eight rules, each failing independently, including anchor present and locked items preserved

---

## Layer 2 — Contract tests

The AI can only return what the schema permits, but the schema itself must be correct and must stay aligned with the database.

```python
def test_vision_schema_enums_match_database_enums():
    schema_colors = set(VISION_SCHEMA["schema"]["properties"]["color_primary"]["enum"])
    assert schema_colors == set(ColorPrimary.values())

def test_every_subcategory_maps_to_a_valid_category():
    for category, subs in SUBCATEGORIES.items():
        assert category in Category.values()
        assert len(subs) == len(set(subs))
```

This is the test that catches the classic failure: someone adds `"burgundy"` to the prompt but not to the enum, and tagging starts failing in production a week later.

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
- **Background task transitions the row** to `ready` with populated tags.
- **Tagging failure** sets `status='failed'` and `error_message`, and does not raise into the request.
- **Hallucination guard:** feed a stylist fixture containing an ID that is not in the wardrobe and assert a `502`, not a partially rendered look. This is the single most important integration test in the project.
- **Cross-user isolation:** user A cannot `GET`, `PATCH`, or `DELETE` user B's items. Test every item endpoint.
- **`user_edited` protection:** `POST /items/{id}/retag` returns `409` after a manual edit, and succeeds with `?force=true`.
- **`wardrobe_too_small`:** 5 ready items returns `400` before any AI call is attempted.
- **Rate limits** return `429` with `Retry-After`.

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

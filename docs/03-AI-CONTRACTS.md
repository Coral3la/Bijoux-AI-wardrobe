# 03 — AI Contracts

Provider: **OpenAI**, model `gpt-4o-mini-2024-07-18` for both vision tagging and stylist reasoning.

The model is **two constants** in `app/core/config.py` — `OPENAI_MODEL` defaulting `OPENAI_VISION_MODEL`, and `OPENAI_STYLIST_PIN` defaulting `OPENAI_STYLIST_MODEL`. They hold the same snapshot today and are separate on purpose: task 1.11 is chartered to re-pin the vision model against `gpt-5.4-mini-2026-03-17` and measure the difference on photographs, and while one constant served both, that re-pin also moved the model behind every Stage 2 acceptance criterion. Split at task 2.4; `DECISIONS.md` 078 and 160. Both are a **dated snapshot rather than the moving `gpt-4o-mini` alias**, because every eval run records its model and a curve measured against a pointer that can move is not reproducible.

Both calls use **Structured Outputs**. The wire shape is `response_format: {"type": "json_schema", "json_schema": {…}}`, and `strict` lives **inside** `json_schema` beside `name` and `schema` — this line said `{"type": "json_schema", "strict": true}` through task 0.10, which is not a shape the SDK accepts and would not have worked if copied. The block printed under *Response schema* below is the `json_schema` **value**, not the whole `response_format`. Corrected at 1.1 against the installed SDK's own type definitions.

With `strict: true` the API guarantees the response conforms to the schema, including enum membership. This eliminates most parsing and retry logic — but it does **not** guarantee semantic correctness, so validation still runs on top.

All prompts live in `backend/app/prompts/*.md` and are loaded at import time.

---

## Contract 1 — Vision tagging

**Service:** `app/services/vision.py` → `async tag_item(image_url: str, correction: str | None = None) -> dict[str, Any]`

**`correction` was added at task 1.2b and is the whole of the retry.** Same image, same schema, one more instruction — see *Retry policy* below for the wording and for why the rejected answer is not replayed as a conversation.

**Corrected at task 1.1 — this said `-> ItemTags`, and three documents gave three signatures.** `STAGE-1` 1.1 said `-> dict`, `06-TESTING-STRATEGY.md` said `async … -> ItemTags`, and `ItemTags` existed in no file. Only one reading is consistent with 1.2's `validate_tags(raw) -> ItemTags` and with `DECISIONS.md` 028's split: **`tag_item` returns the model's raw dict, unvalidated, and `ItemTags` is defined at task 1.2** as the validated result. That is also what keeps the key named `confidence` all the way to persistence, as 028 requires. `async` because it is an HTTP client, per `CONVENTIONS.md`.
**Input:** a Cloudinary transform URL at 800px wide, `f_jpg,q_auto` — the format is pinned rather than negotiated because OpenAI's fetcher sends an `Accept` header we cannot observe (`DECISIONS.md` 083)
**Model:** `settings.OPENAI_VISION_MODEL`, `detail: "low"` — sufficient for garment classification and roughly four times cheaper than `high`

### System prompt (`prompts/vision_system.md`)

```
You are a garment cataloguing system. You receive one photograph of a single
clothing item and return structured attributes describing it.

Rules:
- Describe ONLY the main garment in the image. If a person is wearing several
  items, describe the item that is most prominent and centred.
- Use ONLY values from the provided enumerations. Never invent a value.
- `color_secondary` is null unless a second colour covers at least 20% of
  the garment.
- `display_name` is 2-4 lowercase words a person would use to refer to this
  item, e.g. "light blue mom jeans", "black leather ankle boots".
- `confidence` is your honest self-assessment from 0.0 to 1.0. Return below
  0.35 when the image is blurry, cropped, or contains several items.

warmth — how insulating the garment is to wear. Higher is warmer.
  1  tank top, linen shirt, summer dress, sandals
  2  cotton t-shirt, jeans, button-down shirt, sneakers
  3  sweatshirt, thin cardigan, denim jacket, blazer
  4  wool sweater, lined leather jacket, boots
  5  puffer coat, long wool coat, shearling

formality — 1 loungewear, 2 casual, 3 smart casual, 4 business/dressy,
             5 formal evening

layer — base (worn against skin), mid (worn over a base),
        outer (worn over everything), standalone (not layered at all)

{{VOCABULARY}}
```

**Transcribed from `app/prompts/vision_system.md` at the 2026-08-18 audit, which is when the drift was found.** The block above still carried the pre-1.2b file: a `rise` bullet and a `layer` gloss naming the standalone categories, both deleted from the file when `_vocabulary_block()` began generating the same rules from `enums.py` (`DECISIONS.md` 087). The `{{VOCABULARY}}` line is part of the file and is shown for that reason — it is the token `_load_system_prompt()` raises on when it is absent.

The enum lists are rendered from `app/enums.py` into that `{{VOCABULARY}}` placeholder at the end of the prompt file, so prompt, schema and validator cannot drift apart — "appended" was the earlier wording and understated it, since a missing placeholder now raises at import rather than shipping a prompt with no vocabulary. `DECISIONS.md` 080.

### Response schema

```json
{
  "name": "garment_tags",
  "strict": true,
  "schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["category","subcategory","fit","length","rise","color_primary",
                 "color_secondary","pattern","material","formality","warmth",
                 "layer","water_resistant","display_name","confidence"],
    "properties": {
      "category":        { "type": "string", "enum": ["top","bottom","dress","outerwear","shoes","bag","accessory"] },
      "subcategory":     { "type": "string" },
      "fit":             { "type": ["string","null"] },
      "length":          { "type": ["string","null"] },
      "rise":            { "type": ["string","null"] },
      "color_primary":   { "type": "string", "enum": ["black","white","grey","beige","brown","navy","blue","light_blue","red","pink","orange","yellow","green","olive","purple","gold","silver"] },
      "color_secondary": { "type": ["string","null"], "enum": ["black","white","grey","beige","brown","navy","blue","light_blue","red","pink","orange","yellow","green","olive","purple","gold","silver"] },
      "pattern":         { "type": "string", "enum": ["solid","stripes","checks","floral","animal","graphic","denim_wash","other"] },
      "material":        { "type": "string", "enum": ["cotton","denim","knit","wool","leather","linen","silk","synthetic","other"] },
      "formality":       { "type": "integer", "minimum": 1, "maximum": 5 },
      "warmth":          { "type": "integer", "minimum": 1, "maximum": 5 },
      "layer":           { "type": "string", "enum": ["base","mid","outer","standalone"] },
      "water_resistant": { "type": "boolean" },
      "display_name":    { "type": "string" },
      "confidence":      { "type": "number", "minimum": 0, "maximum": 1 }
    }
  }
}
```

`subcategory` is typed as a plain string because its valid values depend on `category`, which JSON Schema cannot express cleanly. `fit` and `length` are plain strings for a different reason: an out-of-vocabulary value there is coerced to null rather than retried, so constraining them in the schema would buy nothing. All three are validated in Python instead.

**Task 1.2a strengthened that reason rather than weakening it.** `fit` and `length` now carry per-category rules of their own, and JSON Schema cannot express those either — so the schema is not merely no worse than Python here, it is structurally incapable of the check. The same limit is what makes `layer` interesting in the other direction: `layer` **is** a constrained enum in the schema, and strict mode still cannot stop the model returning `standalone` for a top, because `standalone` is a legal member of the enum. See the table below.

Notes on the strict subset, because the block above is easy to get subtly wrong:

- **Every property carries a `type`.** A bare `{ "enum": [...] }` does not appear anywhere in the supported subset; the documented form is always `type` plus `enum`.
- **A nullable enum keeps `enum` and adds `null` to the `type` union only** — `null` does *not* go inside the `enum` array. This is the documented pattern, from the section headed **"All fields must be `required`"**: "it is possible to emulate an optional parameter by using a union type with `null`", illustrated with `{ "type": ["string", "null"], "enum": ["F", "C"] }`. It contradicts plain JSON Schema semantics, under which a `null` value would fail the `enum` constraint — follow the vendor's example, not the spec. Only `color_secondary` is in this shape.
- **`minimum` / `maximum` are supported** on `integer` and `number` for the base models, which is what `formality`, `warmth` and `confidence` rely on. They are **not** supported for fine-tuned models — if this project ever fine-tunes, those three bounds move into Python.
- Every property must appear in `required`, and `additionalProperties: false` is mandatory. Optionality is expressed only through a `null` union, never by omission from `required`.

**The schema has been sent to the API and it was accepted.** Task 1.1, 2026-08-17, `gpt-4o-mini-2024-07-18`, one HEIC photographed on an iPhone and delivered through the `vision` transform. No `400`. The two constructs this document flagged as the things to suspect both survived: the `color_secondary` nullable union — `{"type": ["string", "null"], "enum": [...]}` with `null` outside the array — and the `minimum`/`maximum` bounds on `formality`, `warmth` and `confidence`. The response carried all fifteen fields, and `validate_tag_dict` reported no errors and no coercions.

```json
{ "category": "outerwear", "subcategory": "jacket", "fit": null, "length": "regular",
  "rise": null, "color_primary": "brown", "color_secondary": "beige", "pattern": "solid",
  "material": "leather", "formality": 3, "warmth": 4, "layer": "outer",
  "water_resistant": false, "display_name": "brown shearling jacket", "confidence": 0.9 }
```

**Two things this call did not establish, stated so nobody reads more into it than it holds.** The nullable union was accepted *as a schema*, but the model returned `"beige"`, so a `null` `color_secondary` has never actually been emitted under strict mode — that branch is still untested. And one image is one image: nothing here says anything about accuracy, which is task 1.11's to measure against thirty.

**Still true after task 1.2b, and stated plainly rather than left as a to-do.** There are still exactly eight live responses — 1.2b called no API — and **not one of them carried a `null` `color_secondary`. The null branch of the only nullable enum in this schema remains unproven against the live API.** 1.2b declined to buy the answer with a hand-picked photograph: a single-colour garment is not a guarantee the model declines a second colour, so a negative result would prove nothing and a positive one would prove it for one image. **Task 1.11 settles it as a by-product** — thirty photographs including deliberately plain garments will emit a `null` or they will not, and either outcome is a finding worth recording there. What is tested in the meantime is the *shape*: `test_a_nullable_enum_keeps_null_out_of_the_enum_array` pins the construct, and the fake carries `color_secondary: null` so the parsing path is exercised on every run.

**The vocabulary block demonstrably reached the model.** `subcategory` and `length` carry no `enum` in the schema, so the rendered prompt is their only source, and both came back as exact in-vocabulary tokens — `"jacket"` from `SUBCATEGORIES[outerwear]`, a category-dependent list whose shape the model could not have guessed, and `"regular"` from `Length`. `rise: null` follows the prompt's bottoms-only rule.

**`fit` came back `null`, and one image cannot say why.** Three readings are open: the model declined honestly, the model had the list and did not use it, or the vocabulary has no good member for outerwear at all — of the nine values, `skinny`, `slim`, `straight` and `wide` are trouser words and `bodycon`, `a_line` and `flowy` are dress words, leaving `relaxed` and `oversized`.

**That sentence was written to explain why one jacket came back with no `fit`, and it is not a vocabulary rule — read as one it is wrong.** Task 1.2a narrowed only three of the nine, deliberately: `skinny` to bottoms, `wide` to bottoms and dresses, `bodycon` to everything but outerwear. `slim` and `straight` stayed unconstrained because a slim-fit shirt and a straight-cut coat are ordinary garments, and `a_line` and `flowy` stayed unconstrained because an A-line top is a real cut. A deny list is a claim that a word is *wrong* for a category, which is a much stronger claim than that it is *unlikely* — and the wider version above would coerce correct answers away on garments this wardrobe will actually contain. `02-DATA-MODEL.md` carries the three that survived. Note also that the prompt licenses a null `fit` without ever saying when one is appropriate, unlike `rise` and `color_secondary`, which have explicit rules. Task 1.11 can discriminate where this cannot: if `fit` nulls cluster on outerwear, bags and accessories the vocabulary or the prompt is the problem, and if they spread evenly across categories the model is.

**The block above is now a description of generated output, not the source.** `app/services/vision.py` builds the same structure with its enum arrays taken from `app/enums.py` and `required` derived from the properties, so prompt, schema and validator cannot disagree with each other. What they can still disagree with is `02-DATA-MODEL.md`, which is authoritative over `enums.py` by hand and is compared to it by nothing — see the note in `06-TESTING-STRATEGY.md`. `DECISIONS.md` 080.

Two consequences of generating rather than transcribing, both deliberate. `06-TESTING-STRATEGY.md`'s contract test comparing the schema's colours to `ColorPrimary.values()` is now a tautology and is recorded there as one. And this document must be updated by hand if `enums.py` changes, exactly as before — the generation removed a copy from the code, not from the documentation.

### Validation and retry — `validate_tag_dict()` and `validate_tags()`

Two layers, and the table below spans both. Every row except the last two is `app/enums.py` → `validate_tag_dict(d) -> TagValidation`, a pure function that returns a report of `errors` and `coerced` and calls nothing. The *retry* in the right-hand column belongs to `app/services/vision.py` → `async validate_tags(raw: dict[str, Any], image_url: str) -> ItemTags`, which reads that report. See `DECISIONS.md` 028.

**Corrected at task 1.2b — this document, `STAGE-1` and `06-TESTING-STRATEGY.md` all printed `validate_tags(raw)`, and no one-argument function can do what all three then describe.** A retry is a second call to the model and a tag dict cannot say which photograph it came from, so the signature takes the URL and is `async`. The alternative was a third function owning the call-validate-retry loop, which 1.2b declined: it needs a name no document has, and the two-call shape gives 1.3 a distinction it wants — `TaggingError` means the model answered and the answer could not be accepted, while a `ValueError` or a provider exception means no usable answer arrived. `validate_tags` does not flatten the second into the first, including when the *retry* is what fails; both end as `failed`, and they say different things in `error_message`.

| Check | On failure |
|---|---|
| `category` / `color_primary` / `pattern` / `material` / `layer` in its vocabulary | retry once |
| `subcategory` belongs to `category` | retry once |
| `formality` / `warmth` an integer 1–5 | retry once |
| `fit` / `length` in the global enum, or null | coerce to null |
| `color_secondary` in the global colour enum, or null | coerce to null |
| `rise` present only when `category == "bottom"`, and in the enum | coerce to null |
| `fit` present only for `top` / `bottom` / `dress` / `outerwear` | coerce to null |
| `fit` describes its category — `skinny` bottoms only, `wide` bottoms and dresses, `bodycon` not outerwear | coerce to null |
| `length` present for every category except `bag` and `accessory` | coerce to null |
| `length` describes its category — sleeve words for `top`/`dress`/`outerwear`, hem words for `bottom`/`dress`/`outerwear` | coerce to null |
| `layer == "standalone"` for shoes/bag/accessory/dress | coerce |
| `layer` is `mid` or `outer` when `category == "outerwear"` | coerce to `outer` |
| `layer` is `base` when `category == "bottom"` | coerce to `base` |
| `layer` is `base` or `mid` when `category == "top"` | **retry once** |
| any category-dependent field present with no `category` at all | retry once |
| one of the eleven fields the schema types with no `null` is absent or `null` — or, for `display_name`, blank | retry once, naming the field |
| `confidence < 0.35` | nothing — `status='ready'`, exactly as for any other value |

**Seven of those rows are task 1.2a's and they are one rule, not seven.** A category-dependent check is a pair — which values the category admits, and what the category says the answer is when the value is not admitted. Where the category determines a single answer the rule coerces to it; where it does not, the vocabulary reports an error and this layer retries once, naming the violation. `top` is the only category in the whole vocabulary for which no answer exists, which is why exactly one of the seven says *retry* — a top is legitimately `base` or `mid`, and substituting either would be a guess wearing a correction's clothes. `02-DATA-MODEL.md` is authoritative for all seven and `DECISIONS.md` 085 has the reasoning; 029 and 082 are both closed by them.

**One consequence for this layer specifically.** The `top`/`layer` row is the first check in this table that can fire on **model output** and end in `TaggingError`. An item can now finish `failed` with no tags where it previously finished `ready` with a wrong `layer`, and that is the accepted trade: a failed tile is visible and carries a retry button, where a wrong `layer` surfaces two stages later as a bad look with nothing pointing back here.

**The second new row is the one that makes `ItemTags` constructible, and it lives in `vision.py` rather than in the vocabulary.** `validate_tag_dict` reads every field with `.get`, so an absent key and a `null` one are the same thing to it and both pass — which is *correct* for `PATCH`'s partial bodies and wrong as input to a typed object. Without this row, `{}` is a clean report and building `ItemTags` from it is a `TypeError` escaping a background task, where the row stays `processing` until 1.3's sweep rather than finishing `failed`. The eleven are `category`, `subcategory`, `color_primary`, `pattern`, `material`, `formality`, `warmth`, `layer`, `water_resistant`, `display_name`, `confidence` — the properties with no `null` in their schema type, which is asserted against the schema rather than restated. A blank `display_name` counts as missing because the alternative is a tile with nothing written on it.

**The last row was `accept, but set status='ready' and flag for review in UI`, and task 1.2b decided against building it.** Three things were traced before 1.2 and none of them existed: no settings field for the threshold, although `DECISIONS.md` 028 describes the comparison as being made "against `settings`"; no review surface in `05-FRONTEND-SPEC.md`; no mention of confidence in any stage file. What settled it is that **both branches of the comparison produce `status='ready'`** — so the branch could only set a flag nothing reads, which `CONVENTIONS.md` calls dead code. The value is not lost: it is persisted as `items.ai_confidence` at 1.3 and mined at 1.11, so a threshold applied later reads the whole table instead of freezing a judgement at tag time. `DECISIONS.md` 086, which supersedes that part of 028.

**And `confidence` is not evidence of correctness.** Eight live responses at task 1.1 — one HEIC plus seven JPEGs — returned `confidence: 0.9` every time, **including the two that were wrong**: `fit: "flared"`, a value in no vocabulary, and `fit: "skinny"` on a tank top. The 0.35 threshold would have flagged neither, and would have flagged nothing at all in eight images. Whatever the model reports is a fluency signal, not an accuracy signal. **Nothing in this project may treat a high `confidence` as a reason to trust a tag.** The prompt still asks for it, and still names 0.35 as the blurred-or-crowded line, because that is what the number is worth: it describes the photograph, not the answer.

The first row, the third, and the new required-fields row cannot fire on model output — Structured Outputs with `strict: true` makes them impossible — but they are not dead checks. `PATCH /items/{id}` runs the same validator on a hand-built request body, where the first two are the difference between a `422` and a `CHECK` violation surfacing as a `500`; the required-fields row is `vision.py`'s alone, and is what stands between a short answer and an unhandled exception if the guarantee is ever not there.

**What `ItemTags.coerced` carries, stated so 1.3 does not have to guess: the accepted answer's coercions, and no others.** When a first answer is rejected and the retry is accepted, the first answer's coerced values describe tags that were never written — carrying them would let 1.3 record "`fit` was discarded" in `items.attributes` beside a row whose `fit` came back fine on the retry. They are not lost either: **every coercion from every attempt is logged** with its field, its rejected value and the category it arrived beside, which is the record 084 found missing and 1.11 mines for the words the vocabulary is short. `test_only_the_accepted_answers_coercions_are_carried` is what fails if that is widened.

**Task 1.3 wrote them down, which is the half 084 was actually complaining about.** They land in `items.attributes` under a `tagging` key, as `{"field", "value", "reason"}` objects — `[]` when the accepted answer discarded nothing, and no key at all on a `failed` row, where no answer was accepted. `02-DATA-MODEL.md` carries the shape.

**The category-dependent rows are the opposite case and it is worth being exact about why.** Strict mode guarantees membership and nothing else, so every value in those rows is a legal member of its own enum arriving beside a category it cannot describe. `layer: "standalone"` on a top passes the schema perfectly. That is the whole reason these checks exist in Python rather than in the schema, and it is why the vocabulary block in the prompt is worth extending too — the model should be told rather than merely corrected, or every one of them is a silent coercion nobody learns from.

**Done at task 1.2b.** `_vocabulary_block()` renders `FIELD_APPLIES_TO`, `VALUE_APPLIES_TO` and `LAYERS_BY_CATEGORY` the same way it already rendered `SUBCATEGORIES`, so prompt and validator cannot disagree — 080's property extended from the values to the rules. Each of `fit`, `length` and `rise` now prints which categories it applies to and which of its words are narrower than the field; `layer` prints the admitted set for all seven categories. What is *not* printed is each category's **answer**: the answer is what this layer does with a wrong value, not something the model needs, and the five words `02-DATA-MODEL.md` leaves unenforced — `crop`, `regular`, `longline`, `ankle`, `full` — get no rule line, because teaching a narrowing the validator does not apply is the one way this block can make things worse. The rules stay server-side otherwise (085): `enums.ts` still mirrors values only.

Retry policy: **one** retry, appending `Your previous response was invalid: {reason}. Correct it.` A second failure sets `status='failed'` and stores `error_message`. Never retry more than once — a model that fails twice on a strict schema is failing on the image, and a third call only spends money.

**"Appending" is a second content part in a fresh request, not a replayed conversation.** The image is re-sent either way; adding the rejected answer as an assistant turn would probably correct better and costs tokens on every failure, and no measurement supports it yet — 1.11 can change it deliberately. `{reason}` is the violation text `validate_tag_dict` produced, so it names the field and the value: *layer 'standalone' is not valid for category 'top', which takes base or mid*.

**The rendered prompt has a version, and it is a hash.** `vision.PROMPT_VERSION` is the first twelve hex characters of the SHA-256 of `SYSTEM_PROMPT` **after** the vocabulary is rendered into it. Half this prompt is generated from `enums.py`, so a hand-bumped version is wrong the moment a table moves without the constant, and the error surfaces at 1.11 as a baseline nobody can reconstruct. Task 1.11 records it beside the model id. **Task 1.3 persists it, on both paths** — `attributes["tagging"]["prompt_version"]` is written on a `ready` row and on a `failed` one, because which prompt could not read a photograph is the same question as which prompt read one, and a baseline that records only successes measures a biased sample (`DECISIONS.md` 088).

### Cost

Roughly $0.0002 per item at `detail: "low"`. Tagging 150 items costs about three cents. This is not a constraint on the project.

---

## Contract 2 — The stylist

**Service:** `app/services/stylist.py` → `suggest_looks(wardrobe, context) -> StylistResponse`

One function serves both single-day recommendations and trip packing. A single day is a trip of length one with no packing list.

### Wardrobe serialisation (`services/serializer.py`)

Each item becomes one compact line.

**The line is positional and the model is given no key**, so the core slots are
always written — an em dash (`—`, U+2014) where the item has no value — and only
the *trailing extras* are omitted. Dropping a core field instead would shift
every later value one column left, and a material would be read as a pattern.
`STAGE-2` 2.3's one-line "omit nulls" is the narrower half of this rule: the
extras are what it describes. Written down at task 2.3, which is when the two
readings were found to disagree; the example below has shown the em dash for a
shoe with no `fit` since Stage 0.

```
A3F9K2 | top/shirt | oversized | long_sleeve | white | — | solid | cotton | F3 W2 | base
7BX1QM | bottom/jeans | straight | full | light_blue | — | denim_wash | denim | F2 W2 | base | rise:high
SEFA38 | shoes/boots | — | ankle | black | gold | solid | leather | F3 W4 | standalone | water_resistant
EH8VVQ | outerwear/blazer | relaxed | regular | beige | — | solid | wool | F4 W3 | outer
```

Format: `SHORT_ID | category/subcategory | fit | length | color | color_secondary | pattern | material | F{formality} W{warmth} | layer | extras`

**Extras are ordered `rise` then `water_resistant`.** Both are reachable on one
item — a waterproof bottom has each — and the order is arbitrary but fixed, so
that a line is a function of the item and not of the order the code happened to
test two flags in.

`color_secondary` was added to the format at task 2.3. Colour coordination is
what this contract exists to get right and about one item in seven is two-tone,
so a line carrying one colour describes those items wrongly. Measured cost: 303
tokens across 150 items, about 2 per item. `DECISIONS.md` 156.

**`display_name` is deliberately not in the line**, and the cost is real rather
than theoretical: it is free text beside a closed vocabulary, the model refers
to items by `short_id`, and it can name them from `subcategory` plus the two
colours. What that gives up is that a garment its owner calls *the interview
blazer* cannot be asked for, or referred to back, by that name anywhere in this
feature. `DECISIONS.md` 156.

**Measured at task 2.3 with `tiktoken` against `o200k_base`, not estimated:
30.7 tokens per item — a 150-item wardrobe is about 4,600 tokens**, comfortably
within a single request. This is the canonical figure; `01-ARCHITECTURE.md` and
`DECISIONS.md` 002 quote it rather than carrying estimates of their own. The
unit test's ceiling is 6,000, which is roughly 30% above real output.

### Weather rules — computed in Python, never inferred by the model

This is the core reliability mechanism of the feature. Do not send a raw temperature and hope the model reasons correctly about it; the results are inconsistent between calls. Convert the temperature into an explicit, testable instruction.

`services/weather.py` → `build_rule(temp_c, precip_mm, wind_kph) -> str`

| Temperature | Rule emitted |
|---|---|
| ≥ 28°C | `Use items with warmth 1-2 only. Do NOT include any outerwear.` |
| 22–27°C | `Use items with warmth 1-2. Outerwear optional and only if warmth <= 2.` |
| 16–21°C | `Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional.` |
| 10–15°C | `Outerwear is REQUIRED, warmth 3-4.` |
| < 10°C | `Outerwear is REQUIRED, warmth 4-5, plus a mid layer.` |

Modifiers, appended when triggered:

- `precip_mm > 1` → `Rain expected. Strongly prefer water_resistant outerwear and closed water_resistant shoes.`
- `wind_kph > 30` → `Windy. Avoid flowy or a_line items.`

The mapping table is a pure function of numbers to strings, which makes it **unit-testable without any AI call** — 12 assertions covering every boundary. That is a meaningful chunk of the testing story.

### System prompt (`prompts/stylist_system.md`)

```
You are a personal stylist. You build outfits exclusively from the wardrobe
you are given. You never invent, assume, or suggest an item that is not in
the list.

OUTPUT
- Return only the item IDs from the wardrobe list. IDs are exact, 6 characters.
- If an ANCHOR is given, that item must appear in the look.
- If LOCKED items are given, all of them must appear unchanged, and only the
  named role may be replaced.
- Every look must include at least: one top and one bottom, OR one dress.
- Every look must include shoes.
- Add a bag and up to two accessories when they improve the look.
- Never place two "outer" layer items in the same look.
- Never place two "base" tops in the same look unless one is explicitly a
  layering piece.

STYLING PRINCIPLES
- Proportion: pair oversized or wide items with fitted or tucked items.
  Avoid oversized on both top and bottom unless deliberately styled with a
  defined waist or a belt.
- High-rise bottoms pair well with tucked or cropped tops; they lengthen the leg.
- Skinny and slim bottoms balance volume above.
- Colour: build around a neutral base (black, white, grey, beige, navy, brown)
  and let one item carry the colour or pattern. Two loud patterns clash.
- Keep formality within one point across a look. Do not pair a formality-5
  dress with formality-2 sneakers unless the occasion explicitly calls for
  contrast.
- Layering runs base -> mid -> outer, thinnest to thickest.

CONSTRAINTS
- Obey the weather rule for each day exactly. It is not a suggestion.
- Where the wardrobe holds nothing that satisfies the weather rule, dress the
  day from the closest items it does hold — the nearest available warmth, and
  water resistance only if something has it. Never refuse to build a look, and
  never return an empty one, because an ideal item is absent.
- An explicit outerwear instruction from the user overrides the weather rule.
  Where none is given, the weather rule decides.
- Obey the user's stated preferences. They override styling principles.
- If the wardrobe cannot satisfy the request, still return your best look and
  report the shortfall in `missing_pieces`. Never silently return a bad outfit,
  and never invent an item to fill the gap. `missing_pieces` is a note beside a
  complete look and never a replacement for one.

REASONING
- `reasoning` is one or two sentences explaining WHY these pieces work
  together, in terms of proportion, colour, or occasion. Never restate the
  item list.
- `weather_note` is one sentence connecting the outfit to the actual forecast.

Respond in English.
```

### User message structure

```
WARDROBE ({n} items):
{serialised lines}

USER PROFILE:
Height: 165 cm. Preferences: prefer high-rise, avoid crop tops.

REQUEST:
{one of the two blocks below}
```

Single day:
```
Date: 2026-03-14
Occasion: work
Notes: meeting with a client
Weather: 18°C, no rain.
Weather rule: Use warmth 2-3 for the base. A mid layer or light
outerwear (warmth 2-3) is optional.
Outerwear: the user has asked for outerwear. Include one.
Build 1 look.
```

**`Notes` and `Outerwear` were added at task 2.4, and they close a gap rather
than extend the contract.** `04-API-SPEC.md` has specified `notes` and
`include_outerwear` on `POST /looks/suggest` since Stage 0, and this block —
the only message that reaches the model — had a line for neither, so two fields
on the wire had nowhere to go. Both lines are **omitted entirely** when the
field is null: `include_outerwear` is three-state, and a null means *the weather
rule decides* rather than *no outerwear*. `Outerwear` is printed after the
weather rule because it overrides it, and the CONSTRAINTS block says which wins
in words. `DECISIONS.md` 158.

Anchored — the user picked an item to build around:
```
ANCHOR: 7BX1QM
This item MUST appear in the look. Build the rest of the outfit around it.
If it cannot work for this occasion or weather, still include it and
explain the tension in `reasoning`.
```

Swap — the user rejected one item in an existing look:
```
LOCKED: A3F9K2, EH8VVQ, SEFA38
These items MUST appear unchanged.
Replace only the shoes with a different option from the wardrobe.
Do not return the previously rejected item ZR44QW.
```

Trip:
```
Destination: Berlin
Dates: 2026-03-14 to 2026-03-17 (4 days)

Day 1 | work    | 12°C, rain 4mm | Outerwear REQUIRED, warmth 3-4.
       Rain expected. Strongly prefer water_resistant outerwear and shoes.
Day 2 | work    | 14°C, dry      | Outerwear REQUIRED, warmth 3-4.
Day 3 | casual  | 17°C, dry      | Use warmth 2-3 for the base…
Day 4 | evening | 15°C, dry      | Outerwear REQUIRED, warmth 3-4.

Build one look per day.
PACKING CONSTRAINT: minimise the number of distinct items packed. Reuse
bottoms and outerwear across days. Never repeat an identical full look.
Aim for at most 12 distinct items across 4 days.
Then return the deduplicated packing list.
```

The reuse target is computed as `min(days * 4, days + 8)` and injected. Without an explicit numeric target the model reuses almost nothing.

### Response schema

```json
{
  "looks": [
    {
      "occasion": "work",
      "title": "Morning meetings",
      "item_ids": ["A3F9K2", "7BX1QM", "SEFA38", "EH8VVQ"],
      "reasoning": "The high-rise straight jean balances the oversized shirt and the tucked front keeps the waist defined.",
      "weather_note": "18°C in the morning — the blazer is enough without a coat."
    }
  ],
  "missing_pieces": [
    {
      "category": "shoes",
      "description": "a neutral closed shoe",
      "reason": "no water-resistant option suitable for the rainy day"
    }
  ],
  "message": "A work outfit for a mild day."
}
```

`missing_pieces` is `[]` when nothing is missing.

**Built at task 2.4 as `STYLIST_SCHEMA` in `app/services/stylist.py`, verified
against one live call, and narrower than this document was before that task in
three ways.** `DECISIONS.md` 157.

- **`packing_list` is not in the schema yet, and this is staging rather than
  disagreement.** It arrives at Stage 4 together with the trip user message and
  the reuse arithmetic, because its `by_category` map cannot be expressed in
  strict mode as written — strict mode requires `additionalProperties: false`
  and every key named, so a free-form category map has to become a fixed list of
  keys, and that list is a decision for the task that has a reader for it.
  Shipping it now would mean the model emitting `packing_list: null` on every
  call this project makes for two stages.
- **`look_id`, `confidence` and `day` are struck.** None has a column in
  `02-DATA-MODEL.md`, a renderer in `05-FRONTEND-SPEC.md` or a task, and in
  strict mode every property is one the model must produce on every call —
  `AUDITS.md` O-9 asked for exactly this decision before a schema was built from
  this block. `day` survived that test at 2.4 and lost it at 2.5 on a
  measurement: the one live call answered `"day": 14` for a request dated
  2026-03-14 while `USE_FAKE_AI` answered `1`, so an unexplained integer beside
  a date was being filled from the date and the two disagreed about what the
  field meant. A look is keyed to its day by `looks.for_date`, which is the
  column `02-DATA-MODEL.md` actually has; Stage 4 reintroduces a day number
  beside the trip schema that needs one. `AUDITS.md` O-24, `DECISIONS.md` 163.
- **No `minItems`.** It is not verified against this pin, and "one look per
  expected day" is rule 4 of the validation table below, which is `validate_look_response`'s.

The schema's `name` is `outfit_recommendation`, beside `garment_tags` for
Contract 1.

The model returns **JSON only** — no prose outside the structure. Everything the
user reads is a field in this object, rendered by the UI.

### Validation — `validate_look_response()`

Run in this order. Any failure triggers **one** retry with the violation named explicitly, then a `502`.

**Five of the eight run at Stage 2**, and the split is by what has a field to
read rather than by preference. `validate_look_response` is a synchronous
function in `app/services/stylist.py` that calls nothing and raises nothing: it
returns the first violation and the response with its ids normalised, and the
retry, the give-up and `502 stylist_failed` belong to `POST /looks/suggest` at
2.7 — the only place holding the wardrobe and the context a second call needs.
`DECISIONS.md` 164.

1. **Every `item_id` exists in this user's wardrobe.** This is the hallucination guard and it is non-negotiable. An unknown ID is never rendered.
2. Every look contains shoes, and either (a top and a bottom) or a dress.
3. No look contains two `outer` items.
4. `len(looks) == expected_days`.
5. Every item in `packing_list.item_ids` appears in at least one look. **Stage 4, with the field it reads.** `STYLIST_SCHEMA` carries no `packing_list` until the trip message is designed beside it (`DECISIONS.md` 157), so this rule has nothing to look at before then and 2.5 does not implement it.
6. When the weather rule required outerwear, each look for that day contains an `outerwear` item — **unless the user asked for no outerwear.** `DECISIONS.md` 158 gave an explicit `include_outerwear: false` precedence over the weather rule and the system prompt says so in words, so a look that obeyed the user at 12°C is correct; enforcing this rule over it would spend the retry and then answer `502` to the one answer that did as it was told. Narrowed at 2.5. Rule 6 reads the rule *sentence* through `weather.requires_outerwear`, never a temperature — the stylist is never sent a number.
7. When `anchor_item_id` was supplied, it appears in the returned look.
8. When `locked_item_ids` were supplied, every one of them appears, and the rejected item does not.

Rules 7 and 8 are fully deterministic and make excellent E2E assertions — the requested item is either there or it is not. They arrive with the anchor at 2.10 and the swap at 2.11, which are the tasks that put the fields on the wire.

Rule 3 is read by `layer`, not by category: the system prompt says *"Never place two `outer` layer items"*, and `LAYERS_BY_CATEGORY` admits `mid` for outerwear, so a cardigan under a coat is a legal look and two coats are not. Rule 1 is checked against **the wardrobe that was sent**, which after 2.6a is narrower than everything the user owns — an id the model was never shown is a hallucination whether or not the garment is in the drawer.

Rule 6 is the one that catches real drift. Assert it against hand-built `StylistResponse` objects, which is what `tests/unit/test_look_validation.py` does. **There is no recorded response fixture and there cannot be one:** `short_id`s are generated per row, so a fixture naming literal ids describes items no database holds and fails rule 1 — the hallucination guard — on every call (`DECISIONS.md` 159).

---

## If a wardrobe ever exceeds 400 items

Not implemented. Documented so the question has an answer in the defence.

The fallback is two-pass selection: a first cheap call picks 40 candidate IDs given the request, a second call builds looks from only those. This preserves the "whole wardrobe" quality at large scale at the cost of one extra round trip. It is unnecessary below 400 items, and building it early would be optimising a problem the project does not have.

---

## Failure handling, user-facing

| Failure | User sees |
|---|---|
| Tagging fails after retry | Tile marked "Couldn't read this one" with a **Retry** button and an **Add manually** link |

**"Add manually" is the tag editor, and the wire could not honour it until task
1.9.** `PATCH /items/{id}` wrote tags and never touched `status`, so an item
recovered by hand kept its `failed` status and its `error_message` for good —
the row stayed marked "Couldn't read this one" underneath a full set of tags the
user had just typed. The link therefore promised a recovery that did not exist.
Fixed on the wire in this commit: a `PATCH` that leaves the row carrying every
required tag clears `failed` to `ready` and clears `error_message` with it. The
rule runs in one direction only and never writes `processing`, because a
background task in flight would overwrite it seconds later. `DECISIONS.md` 116,
`04-API-SPEC.md`'s `PATCH` section, and `AUDITS.md` **O-3**, which this half
unblocks and task 1.9's editor closes.
| Stylist returns invalid output twice | "I couldn't put a look together just now — try again" |
| Wardrobe too small (< 6 ready items) | Blocked before the API call: "Add at least 6 items so I have something to work with" |
| OpenAI timeout (> 30s) | Same message as invalid output; the request is not retried automatically |

Never surface a raw model error or a stack trace to the user.

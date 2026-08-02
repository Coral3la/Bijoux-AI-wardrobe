# 03 — AI Contracts

Provider: **OpenAI**, model `gpt-4o-mini` for both vision tagging and stylist reasoning.

Both calls use **Structured Outputs** (`response_format: {"type": "json_schema", "strict": true}`). With `strict: true` the API guarantees the response conforms to the schema, including enum membership. This eliminates most parsing and retry logic — but it does **not** guarantee semantic correctness, so validation still runs on top.

All prompts live in `backend/app/prompts/*.md` and are loaded at import time.

---

## Contract 1 — Vision tagging

**Service:** `app/services/vision.py` → `tag_item(image_url: str) -> ItemTags`
**Input:** a Cloudinary transform URL at 800px wide, `f_auto,q_auto`
**Model:** `gpt-4o-mini`, `detail: "low"` — sufficient for garment classification and roughly four times cheaper than `high`

### System prompt (`prompts/vision_system.md`)

```
You are a garment cataloguing system. You receive one photograph of a single
clothing item and return structured attributes describing it.

Rules:
- Describe ONLY the main garment in the image. If a person is wearing several
  items, describe the item that is most prominent and centred.
- Use ONLY values from the provided enumerations. Never invent a value.
- `rise` applies only when category is "bottom". Otherwise return null.
- `color_secondary` is null unless a second colour covers at least 20% of
  the garment.
- `display_name` is 2-4 lowercase words a person would use to refer to this
  item, e.g. "light blue mom jeans", "black leather ankle boots".
- `confidence` is your honest self-assessment from 0.0 to 1.0. Return below
  0.5 when the image is blurry, cropped, or contains several items.

warmth — how insulating the garment is to wear. Higher is warmer.
  1  tank top, linen shirt, summer dress, sandals
  2  cotton t-shirt, jeans, button-down shirt, sneakers
  3  sweatshirt, thin cardigan, denim jacket, blazer
  4  wool sweater, lined leather jacket, boots
  5  puffer coat, long wool coat, shearling

formality — 1 loungewear, 2 casual, 3 smart casual, 4 business/dressy,
             5 formal evening

layer — base (worn against skin), mid (worn over a base),
        outer (worn over everything), standalone (dresses, shoes,
        bags, accessories)
```

The enum lists from `02-DATA-MODEL.md` are appended programmatically so the prompt and the schema can never drift apart.

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
      "category":        { "enum": ["top","bottom","dress","outerwear","shoes","bag","accessory"] },
      "subcategory":     { "type": "string" },
      "fit":             { "type": ["string","null"] },
      "length":          { "type": ["string","null"] },
      "rise":            { "type": ["string","null"] },
      "color_primary":   { "enum": ["black","white","grey","beige","brown","navy","blue","light_blue","red","pink","orange","yellow","green","olive","purple","gold","silver"] },
      "color_secondary": { "type": ["string","null"] },
      "pattern":         { "enum": ["solid","stripes","checks","floral","animal","graphic","denim_wash","other"] },
      "material":        { "enum": ["cotton","denim","knit","wool","leather","linen","silk","synthetic","other"] },
      "formality":       { "type": "integer", "minimum": 1, "maximum": 5 },
      "warmth":          { "type": "integer", "minimum": 1, "maximum": 5 },
      "layer":           { "enum": ["base","mid","outer","standalone"] },
      "water_resistant": { "type": "boolean" },
      "display_name":    { "type": "string" },
      "confidence":      { "type": "number", "minimum": 0, "maximum": 1 }
    }
  }
}
```

`subcategory`, `fit`, and `length` are typed as plain strings because their valid values depend on `category`, which JSON Schema cannot express cleanly. They are validated in Python instead.

### Validation and retry — `validate_tags()`

| Check | On failure |
|---|---|
| `subcategory` belongs to `category` | retry once |
| `fit` / `length` in the global enum, or null | coerce to null |
| `rise` present only when `category == "bottom"` | coerce to null |
| `layer == "standalone"` for shoes/bag/accessory/dress | coerce |
| `confidence < 0.35` | accept, but set `status='ready'` and flag for review in UI |

Retry policy: **one** retry, appending `Your previous response was invalid: {reason}. Correct it.` A second failure sets `status='failed'` and stores `error_message`. Never retry more than once — a model that fails twice on a strict schema is failing on the image, and a third call only spends money.

### Cost

Roughly $0.0002 per item at `detail: "low"`. Tagging 150 items costs about three cents. This is not a constraint on the project.

---

## Contract 2 — The stylist

**Service:** `app/services/stylist.py` → `suggest_looks(wardrobe, context) -> StylistResponse`

One function serves both single-day recommendations and trip packing. A single day is a trip of length one with no packing list.

### Wardrobe serialisation (`services/serializer.py`)

Each item becomes one compact line. Nulls are omitted.

```
A3F9K2 | top/shirt | oversized | long_sleeve | white | solid | cotton | F3 W2 | base
7BX1QM | bottom/jeans | straight | full | light_blue | denim_wash | denim | F2 W2 | base | rise:high
P04FFE | shoes/boots | — | ankle | black | solid | leather | F3 W4 | standalone | waterproof
ZZ81KA | outerwear/blazer | relaxed | regular | beige | solid | wool | F4 W3 | outer
```

Format: `SHORT_ID | category/subcategory | fit | length | color | pattern | material | F{formality} W{warmth} | layer | extras`

About 28 tokens per item. A 150-item wardrobe is roughly 4,200 tokens — comfortably within a single request.

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
- Obey the user's stated preferences. They override styling principles.
- If the wardrobe cannot satisfy the request, still return your best look and
  report the shortfall in `missing_pieces`. Never silently return a bad outfit,
  and never invent an item to fill the gap.

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
Weather: 18°C, no rain.
Weather rule: Use warmth 2-3 for the base. A mid layer or light
outerwear (warmth 2-3) is optional.
Build 1 look.
```

Anchored — the user picked an item to build around:
```
ANCHOR: 7BX1QM
This item MUST appear in the look. Build the rest of the outfit around it.
If it cannot work for this occasion or weather, still include it and
explain the tension in `reasoning`.
```

Swap — the user rejected one item in an existing look:
```
LOCKED: A3F9K2, ZZ81KA, P04FFE
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
      "look_id": "d1_morning",
      "day": 1,
      "occasion": "work",
      "title": "Morning meetings",
      "item_ids": ["A3F9K2", "7BX1QM", "P04FFE", "ZZ81KA"],
      "reasoning": "The high-rise straight jean balances the oversized shirt and the tucked front keeps the waist defined.",
      "weather_note": "18°C in the morning — the blazer is enough without a coat.",
      "confidence": "high"
    }
  ],
  "packing_list": {
    "item_ids": ["A3F9K2", "7BX1QM", "..."],
    "reuse_summary": "8 items across 5 looks — the jeans appear on 3 days.",
    "by_category": { "top": 3, "bottom": 2, "shoes": 2, "outerwear": 1 }
  },
  "missing_pieces": [
    {
      "category": "shoes",
      "description": "a neutral closed shoe",
      "reason": "no water-resistant option suitable for the rainy day"
    }
  ],
  "message": "Packed for four days in Berlin, including one dressier evening."
}
```

`packing_list` is `null` for single-day requests. `missing_pieces` is `[]` when nothing is missing.

The model returns **JSON only** — no prose outside the structure. Everything the user reads is a field in this object, rendered by the UI.

### Validation — `validate_look_response()`

Run in this order. Any failure triggers **one** retry with the violation named explicitly, then a `502`.

1. **Every `item_id` exists in this user's wardrobe.** This is the hallucination guard and it is non-negotiable. An unknown ID is never rendered.
2. Every look contains shoes, and either (a top and a bottom) or a dress.
3. No look contains two `outer` items.
4. `len(looks) == expected_days`.
5. Every item in `packing_list.item_ids` appears in at least one look.
6. When the weather rule required outerwear, each look for that day contains an `outerwear` item.
7. When `anchor_item_id` was supplied, it appears in the returned look.
8. When `locked_item_ids` were supplied, every one of them appears, and the rejected item does not.

Rules 7 and 8 are fully deterministic and make excellent E2E assertions — the requested item is either there or it is not.

Rule 6 is the one that catches real drift. Assert it in tests against a recorded response fixture.

---

## If a wardrobe ever exceeds 400 items

Not implemented. Documented so the question has an answer in the defence.

The fallback is two-pass selection: a first cheap call picks 40 candidate IDs given the request, a second call builds looks from only those. This preserves the "whole wardrobe" quality at large scale at the cost of one extra round trip. It is unnecessary below 400 items, and building it early would be optimising a problem the project does not have.

---

## Failure handling, user-facing

| Failure | User sees |
|---|---|
| Tagging fails after retry | Tile marked "Couldn't read this one" with a **Retry** button and an **Add manually** link |
| Stylist returns invalid output twice | "I couldn't put a look together just now — try again" |
| Wardrobe too small (< 6 ready items) | Blocked before the API call: "Add at least 6 items so I have something to work with" |
| OpenAI timeout (> 30s) | Same message as invalid output; the request is not retried automatically |

Never surface a raw model error or a stack trace to the user.

# 02 — Data Model

PostgreSQL 18. SQLAlchemy 2.0 ORM, Alembic migrations.

**Corrected at task 0.10, by reading the server rather than the plan.** This document, `07-DEPLOYMENT.md` and `docs/README.md` all said 16; the Neon project reports `18.4` and the local test container is `postgres:18`. Nothing in the schema depends on the difference, and it is corrected because a document that names a version the database does not run is the kind of detail that gets found during a defence. **CI still pins `postgres:16` and is task 5.5's to bring into line** — that job does not exist yet, so nothing is broken today.

**This document is authoritative.** Do not add fields or enum values that are not listed here. If something is genuinely missing, stop and ask before changing the schema.

---

## The closed vocabulary

Every descriptive attribute comes from a fixed list. This is the most important design decision in the project.

Free-text tagging produces `"light blue"`, `"baby blue"`, `"sky blue"`, and `"pale blue"` for the same garment. Filtering breaks, grouping breaks, and the stylist model receives inconsistent input. A closed vocabulary means any value outside the list is a validation error that triggers a retry, and every downstream feature can rely on exact matching.

These live in `backend/app/enums.py` and are mirrored in `frontend/src/app/shared/models/enums.ts`. Both files are generated from this document by hand and must stay in sync.

**The category-dependent rules below are the one exception, and they live in `app/enums.py` alone.** `enums.ts` mirrors the *values*, not the rules. Copying the rules into a second language would add a hand-written copy with nothing comparing it to anything, in the same position as the upload limits and the password rules `CONVENTIONS.md` records — and it would have been written before the screen that wants it existed. What the tag editor does instead is written into task 1.9. `DECISIONS.md` 085.

### `category` — 9 values

```
top · bottom · dress · outerwear · shoes · bag · accessory
swimwear · sleepwear
```

**`swimwear` and `sleepwear` were added at task 2.6a, and they are appended
rather than inserted.** Migration `0003` adds them to the `item_category` type
with `ALTER TYPE … ADD VALUE`, which appends, and `app/enums.py` and
`enums.ts` are kept in the same order so the three lists can be compared by
eye. They are first-class categories rather than subcategories of something
else because a person photographing their wardrobe uploads both, and the answer
to a garment the app cannot name is not to pretend it is not a garment —
`AUDITS.md` **O-21**, `DECISIONS.md` 167. Nothing already committed is
re-tagged: no seed row matches either value. The server-side exclusion
`01-ARCHITECTURE.md` describes is what these two exist to be matched on, and it
landed at task 2.7 beside `ready`-only and `is_archived` — as
`STYLIST_EXCLUDED_CATEGORIES`, a setting validated against this list at process
start, which is what makes these two members configurable rather than compiled
in. `DECISIONS.md` 169.

### `subcategory` — validated against the parent category

```
top:        t_shirt · tank · shirt · blouse · sweater · sweatshirt · hoodie · bodysuit
bottom:     jeans · trousers · shorts · skirt · leggings · cargo
dress:      dress · jumpsuit
outerwear:  jacket · coat · blazer · cardigan · vest · puffer
shoes:      sneakers · boots · heels · flats · sandals · loafers
bag:        tote · crossbody · shoulder · clutch · backpack
accessory:  belt · scarf · hat · sunglasses · jewelry
swimwear:   swimsuit · bikini · swim_shorts · cover_up · rash_guard
sleepwear:  pajamas · nightdress · robe
```

`swim_shorts` rather than `shorts`, because no subcategory may appear under two
categories — both mirrors' specs assert it, and a `shorts` that meant trousers
in one place and swimwear in another would break the one property that makes
`(category, subcategory)` an exact match.

### Category-dependent validity

Five fields cannot be validated on their own, and `subcategory` above is the oldest of them. The rule is one pair applied five times: **which values the category admits, and what the category says the answer is when the value is not admitted.**

Where the category determines a single answer, an inadmissible value is corrected to it. Where it does not, the vocabulary cannot answer and reports an error — which the vision path turns into one retry naming the violation, and `PATCH /items/{id}` turns into a `422`. **Nothing invents a value.**

| Field | Admits | An inadmissible value becomes |
|---|---|---|
| `subcategory` | the parent category's list | an error — `top` does not say which of its eight |
| `rise` | `low · mid · high`, and only beside `bottom` | `NULL` — elsewhere there is no rise to have |
| `fit` | see below | `NULL` |
| `length` | see below | `NULL` |
| `layer` | see below | the category's answer, or an error for `top` alone |

A value that is outside its own vocabulary altogether is dealt with first, on the terms that field already states, so nothing is reported twice.

Two consequences worth having before the field sections that follow. **A value present with no `category` at all is an error for every one of the five**, because whether it is meaningful cannot be decided without one — which includes a `PATCH` against a row that is still `processing`, whose tags are all `NULL`. And **when `PATCH` changes `category`, the route clears all five** for any the same request does not supply, because there it is the stored row that became impossible rather than the request that was wrong (`DECISIONS.md` 030). The list of five is exported from `app/enums.py` as `CATEGORY_DEPENDENT_FIELDS`, so the route reads it rather than restating it.

### `fit` — the silhouette

```
skinny · slim · straight · relaxed · oversized · wide · bodycon · a_line · flowy
```

Always nullable. A value outside this list is coerced to `NULL` rather than rejected — an absent attribute is better than a wrong one, and neither the stylist nor any filter requires it.

**`fit` applies to `top`, `bottom`, `dress`, `outerwear`, `swimwear` and `sleepwear`, and to nothing else.** A bag has no meaningful silhouette, and neither has a shoe or a belt — not one of the nine words above describes one. On `shoes`, `bag` and `accessory` the field is `NULL`.

The two added at 2.6a are in the list because they pass the same test the other four do rather than by association: a cover-up is `flowy`, a rash guard is `slim`, a robe is `oversized`. **The three narrowed rows below were left alone**, so `skinny`, `wide` and `bodycon` null out on both. A bodycon swimsuit is the one real loss, on a field that is nullable by design.

**Three of the nine words are narrower than the field itself.** Every word not named here applies wherever the field does.

| Value | Applies to | Why |
|---|---|---|
| `skinny` | `bottom` | A leg word. Returned on a tank top at task 1.1, which is what opened this |
| `wide` | `bottom` · `dress` | Wide-leg. `dress` is in the list because a wide-leg **jumpsuit** is category `dress` |
| `bodycon` | `top` · `bottom` · `dress` | A bodycon coat is not a garment |

`slim`, `straight`, `relaxed` and `oversized` describe all six categories the field applies to. `a_line` and `flowy` are left unconstrained deliberately: an A-line top is a real cut, and a rule that coerced it away would manufacture exactly the wrong answer these three rows exist to prevent. `DECISIONS.md` 085.

### `length`

```
sleeveless · short_sleeve · long_sleeve · crop · regular · longline
mini · midi · maxi · ankle · full
```

Always nullable, on the same terms as `fit`. One flat list covering three axes — sleeve, top length, hem.

**`length` applies to every category except `bag` and `accessory`.** `shoes` keeps it, because `ankle` is a genuine shoe length.

**The two ends of the list are narrower than the field. The middle is not, and that is deliberate.**

| Values | Apply to | Why |
|---|---|---|
| `sleeveless · short_sleeve · long_sleeve` | `top` · `dress` · `outerwear` · `swimwear` · `sleepwear` | A pair of jeans has no sleeves. A rash guard and a pyjama top both have them, and a swimsuit is `sleeveless` |
| `mini · midi · maxi` | `bottom` · `dress` · `outerwear` · `swimwear` · `sleepwear` | A t-shirt has no hem length. `outerwear` is in the list because a maxi coat is a real garment, and the two added at 2.6a because a nightdress and a sarong cover-up both have a hem |

`crop`, `regular`, `longline`, `ankle` and `full` are unconstrained within the five categories the field applies to. They genuinely span the axes — cropped trousers and a cropped top, ankle boots and ankle trousers — and a rule over them would coerce correct answers away. **This is the point at which the flat list stops being enforced**, and the reason it stops here rather than earlier or later is that these five are the only words in it that describe more than one axis.

`maxi` on a t-shirt no longer validates. `DECISIONS.md` 029 was the entry accepting that it did, on the premise that the three axes do not collide in practice; it is closed by this section and by the three `fit` rows above, and 085 carries the reasoning.

### `rise` — bottoms only, `NULL` elsewhere

```
low · mid · high
```

This single field is what separates mom jeans from low-rise jeans, and it drives proportion rules in the stylist prompt.

It is the second instance of category-dependent validity above and the one whose answer is plainest: outside `bottom` there is no rise to have, so an inadmissible value is `NULL` and never an error. The rule was written here before `fit`, `length` and `layer` had one, and it is the shape the other three now follow.

### `color_primary` / `color_secondary` — 17 values

```
black · white · grey · beige · brown · navy · blue · light_blue
red · pink · orange · yellow · green · olive · purple · gold · silver
```

`color_secondary` is `NULL` for solid items.

### `pattern`

```
solid · stripes · checks · floral · animal · graphic · denim_wash · other
```

### `material`

```
cotton · denim · knit · wool · leather · linen · silk · synthetic · other
```

### `formality` — integer 1–5

| Value | Meaning | Examples |
|---|---|---|
| 1 | Loungewear | sweatpants, slides |
| 2 | Casual | t-shirt, jeans, sneakers |
| 3 | Smart casual | blouse, chinos, loafers |
| 4 | Business / dressy | blazer, tailored trousers, heels |
| 5 | Formal | evening dress, tuxedo |

### `warmth` — integer 1–5

**Higher means warmer to wear.** This is a property of the garment, not of the weather.

| Value | Meaning | Examples |
|---|---|---|
| 1 | Very light | tank top, linen shirt, summer dress, sandals |
| 2 | Light | cotton t-shirt, jeans, button-down shirt, sneakers |
| 3 | Medium | sweatshirt, thin cardigan, denim jacket, blazer |
| 4 | Warm | wool sweater, lined leather jacket, boots |
| 5 | Very warm | puffer coat, long wool coat, shearling |

`warmth` replaces a `season` field entirely. Seasons are location-dependent — a Tel Aviv winter is 14°C and a Tel Aviv October is 30°C — so "winter garment" is not a stable property. Insulation is. Season, where it is ever needed for display, is derived from `warmth`.

### `layer`

```
base · mid · outer · standalone
```

A shirt is `base`, a cardigan is `mid`, a coat is `outer`, a dress is `standalone`. Shoes, bags, and accessories are `standalone`. This field drives layering validity: the stylist may not put two `outer` items in one look.

**What each category admits, and what it answers with.**

| Category | Admits | Answer when the value is not admitted |
|---|---|---|
| `top` | `base · mid` | **none — this is an error** |
| `bottom` | `base` | `base` |
| `dress` | `standalone` | `standalone` |
| `outerwear` | `mid · outer` | `outer` |
| `shoes` | `standalone` | `standalone` |
| `bag` | `standalone` | `standalone` |
| `accessory` | `standalone` | `standalone` |
| `swimwear` | `standalone` | `standalone` |
| `sleepwear` | `standalone` | `standalone` |

The two rows added at 2.6a take the plainest answer in the table for a plain
reason: neither is layered in any look this application builds, because task
2.7 excludes both from the wardrobe the stylist is sent. A determinate answer
also means a wrong `layer` on either is corrected rather than refused, which
leaves `top` the only category in this document that reports an error.

Two rows of that table are claims rather than bookkeeping, and they are stated here in their own right so that a later reader can disagree with them by name instead of re-deriving the table.

**A `bottom` admits `base` and nothing else.** Layering is a property of the torso. A pair of trousers is neither worn over another garment nor worn as an entire outfit, so `mid`, `outer` and `standalone` are all wrong for it and `base` is the only word left. That makes `bottom`'s answer determinate, and an inadmissible layer on a bottom is corrected rather than refused.

**A `top` is the only category with no determinate answer.** `mid` is defined by position — worn over a base — rather than by category, and a sweater, a sweatshirt, a hoodie or an open shirt is a top that is routinely worn over a base. A top is therefore legitimately either `base` or `mid`, and the vocabulary cannot say which one a top tagged `outer` or `standalone` should have been. It does not guess. This is the one case in this document that reports an error.

**The cost of that is real and it is accepted.** An item can now finish `failed` with no tags at all where it previously finished `ready` with a wrong `layer`. That is the right side of the trade: a failed tile is visible and carries a retry button, whereas a wrong `layer` surfaces two stages later as a bad look, with nothing pointing back here. The alternative — correcting a top to `base` — would push a hoodie the model answered `mid` about, correctly, down to the wrong value across a whole class of garments, silently, and far more often than the error will fire. `DECISIONS.md` 082 and 085.

### `item_status`

```
processing · ready · failed
```

### `condition` — 8 values, and the one vocabulary here that is not a column

```
clear · partly_cloudy · cloudy · fog · drizzle · rain · snow · thunderstorm
```

It names the sky rather than a garment, so no table has a `condition` column and
no migration creates a type for it. It is here because this document is
authoritative for closed vocabularies by its own first line, and because the
argument that closed every list above applies to it unchanged — `partly_cloudy`
and `Partly Cloudy` and `partlycloudy` are the same weather and would be three
i18n keys. Added at task 2.1, which is where `GET /weather` first has to return
a value; `AUDITS.md` **O-8** made the same case for `occasion`, which is the
section below and landed at task 2.7. `DECISIONS.md` 144.

Open-Meteo answers in **WMO 4677 integers**, not strings. The map from those
twenty-eight codes onto these eight lives in `app/services/weather.py`, which is
the only place the provider's numbering appears — an unmapped code falls back to
`cloudy` and logs, rather than failing a request over a label. `DECISIONS.md` 146.

### `occasion` — 6 values, and the second here that is not a column type

```
casual · work · evening · sport · formal · travel
```

What the user is dressing for. `looks.occasion` holds one of these six and
`trips.occasions` holds one per day, but both columns are `TEXT` and `JSONB` —
no migration creates an `occasion` type, so **nothing in the database refuses a
value outside this list.** What enforces it is `LookSuggestRequest` typing its
field as the enum, which makes an unknown occasion a `422` before any row or any
prompt exists.

Added at task 2.7, the first task that accepts the value, and moved here from
`04-API-SPEC.md`, which carried the six alone from Stage 0 until then — the one
closed vocabulary in the project with no validator and no home. `AUDITS.md`
**O-8**, which this closes. The argument is every other list's: `work` and
`Work` and `office` are the same request, an occasion that is free text cannot
be grouped or given an i18n key, and Stage 3's preference block aggregates over
saved looks. `DECISIONS.md` 168.

### `role` — 6 values, and the third here that is not a column type

```
top · bottom · outer · shoes · bag · accessory
```

Which slot in a look a garment fills. `look_items.role` is `TEXT` and **stays
`NULL`** — nothing writes it, at 2.11 as at 2.7 — so what these six values
enforce is `replace_role` on `POST /looks/suggest`: the ↻ badge on a look card
names the role of the tile the user tapped, and `LookSuggestRequest` typing the
field as the enum makes anything else a `422` before a prompt is built.

Adopted at task 2.11, the first task that sends one, and moved here from
`04-API-SPEC.md`, which carried the six in prose from Stage 0. `AUDITS.md`
**O-25**, whose vocabulary half this closes; the two deferred indexes are still
Stage 3's.

**It is not `Category`, and the two places they differ are the whole reason
this list waited for a reader.** The category spelled `outerwear` is the role
spelled `outer` — one garment class, two words, and the role's is the one
`04` prints. And **`dress` is not a role at all**: replacing a dress can
legally return a top *and* a bottom under the completeness rule, which is a
different look rather than a single-item swap, so the field has no word for it
and the badge is not drawn on a dress tile. `swimwear` and `sleepwear` are
absent for the plainer reason that the stylist is never shown one.

**Nothing derives a role on the backend, deliberately.** The map from
`category` to role lives in `frontend/src/app/shared/models/enums.ts` beside
the badge that reads it, because the server validates the six and never
computes one: `STYLIST_SCHEMA` returns ids, and the column a derivation would
fill has no reader before Stage 3. `DECISIONS.md` 175, 176.

---

## Tables

### `users`

```sql
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           CITEXT NOT NULL UNIQUE,
  password_hash   TEXT NOT NULL,
  display_name    TEXT,

  -- profile, all optional, all fed into the stylist prompt when present
  height_cm       SMALLINT CHECK (height_cm BETWEEN 120 AND 230),
  size_top        TEXT,
  size_bottom     TEXT,
  size_shoe       TEXT,
  style_notes     TEXT,          -- free text: "prefer high-rise, avoid crop tops"

  home_city       TEXT,
  home_lat        REAL,
  home_lon        REAL,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`style_notes` is deliberately free text — it is passed to the model verbatim, never filtered or matched. It is the cheapest possible personalisation and it works well.

Requires `CREATE EXTENSION IF NOT EXISTS citext;` in the first migration.

---

### `items`

```sql
CREATE TABLE items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  short_id        CHAR(6) NOT NULL UNIQUE,

  image_public_id TEXT NOT NULL,          -- Cloudinary public_id, not a full URL
  status          item_status NOT NULL DEFAULT 'processing',

  -- AI-extracted, NULL until tagging first completes
  category        item_category,
  subcategory     TEXT,
  fit             TEXT,
  length          TEXT,
  rise            TEXT,
  color_primary   TEXT,
  color_secondary TEXT,
  pattern         TEXT,
  material        TEXT,
  formality       SMALLINT CHECK (formality BETWEEN 1 AND 5),
  warmth          SMALLINT CHECK (warmth BETWEEN 1 AND 5),
  layer           item_layer,
  water_resistant BOOLEAN NOT NULL DEFAULT FALSE,

  display_name    TEXT,                   -- "light blue mom jeans", model-generated
  attributes      JSONB NOT NULL DEFAULT '{}',
  ai_confidence   REAL,                   -- 0..1, model self-report
  user_edited     BOOLEAN NOT NULL DEFAULT FALSE,
  error_message   TEXT,                   -- populated when status='failed'

  wear_count      INT NOT NULL DEFAULT 0,
  last_worn_at    DATE,
  is_archived     BOOLEAN NOT NULL DEFAULT FALSE,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_items_wardrobe ON items (user_id, status, category)
  WHERE is_archived = FALSE;
```

Notes worth understanding:

- **A `failed` row can carry tags, and the DDL comment above is about the first tagging rather than every one.** A row is created with every tag `NULL` and stays that way until tagging succeeds — but from task 1.4, `POST /items/{id}/retag` puts an already-tagged row back to `processing` **without clearing the tag columns**, and a retag that then fails writes `status='failed'` without touching them either. So a previously-good item keeps the tags it had through a failed retag, which is the point: nulling them at enqueue would destroy good data to make a failure look tidier. The consumer that must know is the wardrobe grid — `STAGE-1` 1.5's failed tile cannot assume the tags are null. `DECISIONS.md` 089.
- **All tag fields are nullable except `water_resistant`**, which is `NOT NULL DEFAULT FALSE` in the DDL above, in migration `0001` and in `app/models/item.py` — so on a `processing` row it reads as *not water resistant* rather than *unknown*, and `ItemResponse.water_resistant` is typed `bool` rather than `bool | None`. The exception was found at the 2026-08-18 audit; the code has always been this way. The row is created the moment the image lands, with `status='processing'`, so the grid can render a tile immediately. Tags fill in seconds later.
- **`image_public_id`, not a URL.** URLs are constructed at read time with the transform needed for that context — thumbnail, full view, or the 800px version sent to the vision model. Storing a URL would freeze one transform forever.
- **`user_edited`** guards against a retag overwriting a manual correction, and gives the testing story a hook: it measures how often the AI got it wrong. **It is set by `PATCH /items/{id}` and never cleared** — not by `?force=true`, and not by the tagging that follows one. The cost is stated here rather than left to be rediscovered: **a hand-corrected item needs `force` on every later retag, for the rest of its life.** That is accepted because the column's second job is historical — an item this user has corrected at some point — and a reset destroys it; because clearing it on a successful write would fire on the upload path too, where it is a no-op today and a silent eraser the moment anything else writes; and because it would open a race in which a `PATCH` against a still-`processing` row is overwritten by the background task *and* loses the flag saying an edit ever happened. `DECISIONS.md` 089.
- **`attributes JSONB`** absorbs future fields (brand, purchase price, embellishments) without a migration. Task 1.3 is its first writer and is a **guest in one key**: everything tagging leaves behind lives under `attributes["tagging"]`, so a future `brand` is never a sibling of a machine-written record, and the write is a merge rather than a replacement so a retag cannot eat one. The shape:

```json
{"tagging": {"prompt_version": "9c1f2ab40d6e",
             "coerced": [{"field": "fit", "value": "flared",
                          "reason": "fit 'flared' is not in the vocabulary"}]}}
```

  `coerced` is the **accepted** answer's discarded values and no others (`DECISIONS.md` 086) — the record 084 found missing, where a real garment attribute the model observed was correctly nulled and remembered by nothing. It is written as `[]` when nothing was discarded, and is **absent** on a `failed` row, where there is no accepted answer to have discarded from. `prompt_version` is written on both paths, so a row can be traced to the prompt that tagged it or failed to.
- **`short_id`** is 6 characters from an unambiguous alphabet — `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, no `0`/`O`/`1`/`I`/`L`. Generate, check uniqueness, retry on collision. It carries no index of its own: the `UNIQUE` constraint already creates one, and a second would be an exact duplicate maintained on every write. "Check uniqueness" is done by *inserting* and catching the violation on `uq_items_short_id`, not by selecting first — the same race-free pattern 037 chose for `uq_users_email`. The generator lives in `app/core/short_id.py` (`DECISIONS.md` 052).
- **`updated_at` is maintained by the ORM, not by the database.** `DEFAULT now()` fires on insert only; PostgreSQL has no column-level `ON UPDATE` and migration `0001` installs no trigger. Task 1.3 added `onupdate=text("now()")` to `Item.updated_at`, which is a **Core-level** default: it applies to ORM flushes and to `update()` statements, and **not** to raw `text()` SQL or to anything typed into `psql`. Database-level truth is a trigger and needs its own migration; it was not built. The startup sweep reads this column to decide which `processing` rows have been abandoned, so the two are one decision and neither survives the other's removal — `DECISIONS.md` 088.
- **`wear_count` and `last_worn_at` exist from migration `0004`**, added at task 3.1. They were shown above and absent from the database for eleven tasks, and `app/models/item.py` omitted them for exactly that long, because a model declaring a column the database lacks breaks every query against it. `wear_count` is `NOT NULL DEFAULT 0`, so a garment uploaded before the column existed reads as worn zero times rather than as unknown — which is what makes 3.6's count correct over the whole wardrobe rather than over the part Stage 3 has touched.

  **Both are written and both are on the wire from task 3.4**, which is what this entry said it was waiting for. `POST /looks/{id}/wear` is the only writer: it increments `wear_count` and moves `last_worn_at` for every item in the look, in the transaction that sets `looks.worn_at`. `ItemResponse` carries both, so they appear on every item payload in the application — `GET /items`, the upload response, and the hydrated items inside every look. **`GET /items/stats` reads `wear_count` from task 3.6, which closes this deferral entirely.** `worn` and `never_worn` partition the `ready`, unarchived rows on `wear_count > 0`, and `most_worn` is the highest of them or `null`. `last_worn_at` has no reader in that endpoint — 3.5's preferences block is its only one.

  **`last_worn_at` moves forward only** — the update is `GREATEST(last_worn_at, :date)`. A wearing recorded for a past date must not drag a garment worn more recently backwards, because 3.5 reads exactly this column to avoid recommending something worn in the last three days. The consequence is that a look's `worn_at` and its items' `last_worn_at` can disagree, and both are correct: **the look records the day the look was worn, the item records the last day it was worn in anything.** Two looks sharing one shirt, worn Monday and Tuesday, leave the Monday look reading Monday and the shirt reading Tuesday.

---

### `looks`

```sql
CREATE TABLE looks (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  trip_id       UUID REFERENCES trips(id) ON DELETE CASCADE,
  slot          TEXT,                     -- 'day' or 'evening'; NULL off a trip

  title         TEXT,
  occasion      TEXT,
  reasoning     TEXT,                     -- why the stylist chose this
  weather_note  TEXT,
  for_date      DATE,

  is_saved      BOOLEAN NOT NULL DEFAULT FALSE,
  feedback      SMALLINT CHECK (feedback IN (-1, 1)),
  worn_at       DATE,                     -- the most recent wearing; see below

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  CHECK ((trip_id IS NULL) = (slot IS NULL))
);

CREATE TABLE look_items (
  look_id   UUID NOT NULL REFERENCES looks(id) ON DELETE CASCADE,
  item_id   UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  role      TEXT,                         -- the `role` vocabulary above; unwritten, see below
  position  SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (look_id, item_id)
);

CREATE INDEX idx_looks_user_id ON looks (user_id);
CREATE INDEX idx_look_items_item_id ON look_items (item_id);

CREATE UNIQUE INDEX uq_looks_trip_day_slot
  ON looks (trip_id, for_date, slot) WHERE trip_id IS NOT NULL;
```

**Both indexes are migration `0004`'s, not `0002`'s.** They were foreseen when
`looks` was built and deliberately not built then — an index on two empty
tables, chosen against no measured query — and adopted at Stage 3, where the
readers arrive: `GET /looks` filtered by user at 3.2, and 3.5's per-item
aggregation over `look_items`. The second is the one that is not obvious:
**PostgreSQL indexes the referenced side of a foreign key and not the
referencing side**, so without it the `ON DELETE CASCADE` from `items` scans
the table. The composite primary key already covers every lookup by `look_id`,
which is the direction 2.7 and 2.9 read, so no third index is warranted.
`AUDITS.md` **O-25**, closed at task 3.1.

**A third index on `looks` arrived at 4.1 anyway, and it is O-25's argument
rather than an exception to it.** `idx_looks_trip_id` is the referencing side of
migration `0005`'s foreign key, so without it the cascade from `trips` scans
`looks` — exactly what `idx_look_items_item_id` exists to prevent one table
over. The sentence above is about the *lookups 2.7 and 2.9 make*, and it is
still true of those; what it did not anticipate is a second foreign key. Built
in the migration that creates the key rather than deferred to the stage that
reads it, because 4.1 and its reader are the same stage.

**`slot` is migration `0006`'s, and it exists because two rows are otherwise
indistinguishable.** A trip day carries one look or two — `day` and `evening` —
and both are rows in this table with the same `trip_id` and the same `for_date`.
Nothing already on the row separates them. **`occasion` cannot**: both slots take
a value from the same six, and a day of meetings followed by drinks with the same
colleagues is `work` twice. **`created_at` and `id` cannot**: `id` is
`gen_random_uuid()`, and `POST /trips/{trip_id}/swap` deletes a look and inserts
its replacement, so the evening look becomes the newer row the first time
anybody changes its shoes. **Position in the response cannot**, because that
ordering is what needs the answer in the first place. Four readers do: the
`days[].slots` join, the swap's lookup of the look being edited, the order
`packing_list.item_ids` is built in — which `reuse_summary`'s tie-break reads —
and the Day/Evening cards themselves. So the slot is a column and not a
derivation. `DECISIONS.md` 225.

**It is `TEXT` and no `ENUM`, exactly as `occasion` is**, and for the reason
given under that vocabulary two sections up: nothing in the database refuses a
value, the Pydantic schema is the gate, and an unknown slot is a `422` before any
row is written. What the two constraints below refuse is not a bad *value* but a
bad *shape* — the two states that would make a packed trip unreadable.

**`CHECK ((trip_id IS NULL) = (slot IS NULL))` ties the two nullables together
in both directions.** A look with no trip has no slot, which is every look
`POST /looks/suggest` has ever written and the ordinary case rather than a
missing value; a look with a trip always has one, so no reader has to decide what
an unslotted trip look means. It is the only constraint in this table that reads
two columns, and it is raw DDL in the migration for `0004`'s measured reason —
`op.create_check_constraint` applies the naming convention to a name that already
carries it and emits `ck_looks_ck_looks_…`.

**`uq_looks_trip_day_slot` is what makes *never `day` twice on one day* a fact of
the database rather than of the request validator.** `UNIQUE (trip_id, for_date,
slot) WHERE trip_id IS NOT NULL`.

**The predicate is scope and not a collision fix**, which is worth stating
because the obvious reading is wrong: under PostgreSQL's default `NULLS
DISTINCT` two NULLs are never equal, so an unconditional index would refuse
nothing extra — every detached look and every `POST /looks/suggest` row would
sit in it harmlessly. `WHERE trip_id IS NOT NULL` earns its place four other
ways. The invariant is about a **trip's** shape, and the DDL says so rather than
leaving it to be derived from NULL semantics. The index covers trip looks alone,
which is the smaller structure and the cheaper write on the path every
suggestion takes. A future `NULLS NOT DISTINCT` — available since PostgreSQL 15,
and flippable for reasons having nothing to do with slots — would otherwise
begin refusing every second suggestion that shares a `for_date`, silently. And a
wider promise in the DDL invites a wider assumption from the next reader.

It survives both writers as they are already ordered: `_write` detaches the marked looks and deletes the rest
before inserting any, and `_replace_look` detaches or deletes the one look it is
replacing before inserting its successor. **This is not the index `AUDITS.md`
O-25 argues against building early.** That argument is about lookups — an index
chosen against no measured query — and this object is a constraint that happens
to be spelled as an index, because a `UNIQUE` constraint cannot carry a `WHERE`.
It is built with the column it constrains rather than with a reader, for the same
reason the `CHECK` is: an invariant added after the rows exist is an invariant
that has to be proved before it can be declared.

**`feedback` is `-1` or `1` and never `0`.** The column has no default, so an
unrated look is `NULL`: "nobody has rated this" and "somebody rated it
neutrally" cannot be the same value, and 3.5 counts rated looks without having
to exclude one. The two numbers live in `app/models/look.py` as `FEEDBACK_UP`
and `FEEDBACK_DOWN`, and the `CheckConstraint` is built from them. **The schema
transcribes them rather than importing them**: `LookUpdate.feedback` is
`Literal[-1, 1]`, because `Literal[FEEDBACK_UP, FEEDBACK_DOWN]` does not
type-check — PEP 586 admits literal values only and `Final` does not exempt a
name. This paragraph promised the compiler would hold the three together; what
holds the schema to the constants is `tests/unit/test_look_schemas.py`, which
compares `get_args` against them. Corrected at 3.3; `DECISIONS.md` 183.

They are **not** `MIN`/`MAX`: this is set membership, and there is nothing
between `-1` and `1` to admit.

**`look_items.role` is still `NULL` on every row.** The vocabulary above is
adopted and enforced on the wire, but nothing writes the column: 2.7 declined
to fill it without a reader and 2.11 — the task that named the list — reads a
role off the item's own `category` in the browser rather than out of this
table, so writing it would be a column filled for Stage 3 in advance.
`position` is the opposite case and is written, because the model's ordering is
destroyed at persistence if nothing records it. `AUDITS.md` **O-25**,
`DECISIONS.md` 170 and 176.

**`worn_at` holds one date, and that bounds what wear tracking can promise.**
Written at task 3.4. `POST /looks/{id}/wear` is idempotent against *this* value:
a request naming the date the column already holds changes nothing, which is the
guarantee `STAGE-3` 3.4 asks for. A different date is a real second wearing and
overwrites it. It follows that a look worn Monday, then Tuesday, then Monday
again is counted three times — the column cannot remember a day it has
overwritten, and nothing else in the schema does either. **The fix, if it is
ever needed, is a `look_wears` table keyed `(look_id, worn_on)`, and Stage 3
deliberately does not build one:** it would be a fourth table and a second
migration in a stage that is the designated cut line, to correct a miscount that
requires a user to record wearings out of order. `DECISIONS.md` 184.

Every suggested look is persisted immediately, whether or not the user saves it. This costs nothing and buys the entire evaluation story: how many suggestions were made, how many were saved, how many were thumbed up, how many were actually worn.

**This many-to-many relationship is the concrete reason this project uses PostgreSQL rather than a document store.** Looks reference items, items belong to users, and both are queried from either direction.

---

### `trips`

```sql
CREATE TABLE trips (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  destination  TEXT NOT NULL,
  dest_lat     REAL,
  dest_lon     REAL,
  start_date   DATE NOT NULL,
  end_date     DATE NOT NULL,

  occasions    JSONB NOT NULL DEFAULT '[]',   -- [{"day":1,"slot":"day","occasion":"work"}, …]
  forecast     JSONB,                          -- the parsed per-day list; see below
  packing_list JSONB,                          -- {"item_ids":[…],"reuse_summary":{…}} — see below
  notes        TEXT,

  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

  CHECK (end_date >= start_date)
);
```

```sql
CREATE INDEX idx_trips_user_id ON trips (user_id);
CREATE INDEX idx_looks_trip_id ON looks (trip_id);
```

The forecast is cached so that reopening a trip does not re-hit the weather API and does not silently change the plan.

Trip length is capped at **14 days** at the API layer, and the bound is on the
**last** day: `end_date <= today + 14`. `DECISIONS.md` 190 — the `start_date`
reading `04-API-SPEC.md` carried would admit a fourteen-day trip ending
thirteen days past any forecast.

**Built at task 4.1**, with the two indexes above. `idx_trips_user_id` is
`idx_looks_user_id`'s twin and has `GET /trips` for a reader; `idx_looks_trip_id`
is the referencing side of the new foreign key, which PostgreSQL does not index
on its own — see the `looks` section above.

**`looks.trip_id` is nullable and stays nullable.** Every look written before
Stage 4 belongs to no trip and `POST /looks/suggest` goes on writing them that
way, so `NULL` is the ordinary case rather than a missing value.

**`occasions` carries one or two entries per day from task 4.11.** A day is one
entry — `day` — or two, `day` then `evening`, in that order; never zero, and
never `day` twice. The column enforces none of it, exactly as it enforces nothing
else (see `packing_list` below): `TripPackRequest` is the gate on the way in,
`uq_looks_trip_day_slot` is the gate on the rows the plan becomes, and the two
agree because one list writes both. **Migration `0006` backfills `"slot": "day"`
into every existing row** rather than letting a reader default it.
`POST /trips/{id}/repack` rebuilds its request from this column, so a reader that
filled in the missing key would be a second place in the project that knows the
pre-slot shape — kept for ever, against a row set that stops existing after one
`UPDATE`. Every trip packed before `0006` is a trip of `day` slots, which is what
it always was; the backfill writes that down rather than leaving it inferred.

**`forecast` holds the parsed days, not the provider's body, and 4.3 is what
settled it.** This line read *"cached Open-Meteo response"*, which reads as the
raw JSON — and `pack_trip` never holds that: `get_daily_forecast` answers parsed
`Forecast` objects, so the unparsed body is not in reach to store. What is
stored is one object per day — `day`, `date`, the four numbers, the `condition`,
and **that day's weather `rule`** — which is exactly what `04-API-SPEC.md`'s
`days[]` renders, minus the occasion and the look id the route adds. The rule is
stored rather than recomputed on read: it is a pure function of three of the
numbers, so a reader *could* rebuild it, but then a trip packed under one version
of the band table would render under another and the sentence the model actually
obeyed would be lost. The cache is still the point — reopening a trip re-reads
the plan rather than re-fetching a forecast that has moved since.

**What `packing_list` holds, settled at task 4.3** — the column was created at
4.1 typed only as the object this file sketched, because its keys belong beside
the trip response schema rather than to the migration that stores them
(`DECISIONS.md` 189). The shape below is `DECISIONS.md` 193's.

```json
{ "item_ids": ["a3f9…", "7bx1…"],
  "reuse_summary": { "item_count": 8, "look_count": 4,
                     "most_reused": { "item_id": "7bx1…", "days": 3 } } }
```

**`item_ids` are row UUIDs as strings, not `short_id`s.** The model answers in
`short_id`s — they are the only ids it is ever shown — and `pack_trip` maps them
through the wardrobe it sent before anything is stored. Two reasons, and the
second is the one that would hurt later: a UUID is the only id that leaves this
API (`04-API-SPEC.md` keeps `short_id` out of the client's hands), and
`items.short_id` is unique per row but is regenerated by `scripts/seed_demo.py`
on every seed, so a packing list keyed on it would point at different garments
after a reseed while `items.id` points at the same ones or at nothing. Strings
rather than a native type because `JSONB` has none; the same is true of the
dates elsewhere in these three columns.

**`reuse_summary` is an object and not the sentence this line used to print.**
It read `"reuse_summary":"…"`, which would have put *"8 items across 5 looks —
the jeans appear on 3 days"* in a database column: user-facing English, written
by the server, where `CONVENTIONS.md` requires every user-facing string to go
through an i18n key and `05-FRONTEND-SPEC.md` §7 needs the same numbers in two
places — the header's *"8 items · 4 looks"* and the reuse line under the packing
list. Storing the numbers lets the frontend render both from one row and lets a
second language render them at all. `item_count` is `len(item_ids)` and
`look_count` is the number of **looks**, both stored rather than derived so that
the column answers the header without the looks being loaded. *That read "the
number of days" until task 4.11, and the two were the same number until a day
could carry a second look.* They part company from `0006`: a five-day trip with
two evenings out is five days and seven looks, and it is the looks this field
counts. That is also where the reuse story gets stronger rather than weaker —
`item_count` holding still while `look_count` climbs is what reuse looks like as
arithmetic, and it needs no new field to say so. **`most_reused` is
`null` when nothing is worn twice**, which is a real state on a short trip and
not an error; where several items tie, it is the one worn on the most days and
then the first in the packing list, so the value is a function of the plan and
not of dictionary ordering.

**`most_reused.days` counts days and not looks, and 4.11 is where those stopped
being one number.** A garment worn to the office and again to dinner on Monday,
and on no other date, is worn on **one** day: `05-FRONTEND-SPEC.md` §7 renders
this number into *"You'll wear the camel trousers on 3 days"*, so counting looks
here would print a false sentence on the only line in the product that makes the
feature land. The consequence is taken deliberately rather than papered over —
that garment reports one day, fails the `> 1` test, leaves `most_reused` as
`null`, and the reuse line is omitted altogether, which is correct for a line
about days. **No field is added for cross-slot reuse.** A `slot_reuse` count
beside these three would have no renderer, and a field with no reader is struck
in this project rather than shipped: `confidence`, `look_id`, `day` and
`occasion` all went that way at 2.4, 2.5 and 4.3. `DECISIONS.md` 225.

**Written by `pack_trip` at 4.3 and persisted by `POST /trips/pack` at 4.4.**
The service computes it and returns it unpersisted, which is what lets the
arithmetic be unit-tested with no database in reach. `03-AI-CONTRACTS.md` says
the same thing from the model's side: `trip_packing_plan` carries
`packing_list.item_ids` and **no** `reuse_summary`, because a count is not
something to ask a model for and then have to check.

**`POST /trips/pack` stopped being the only writer at task 4.6a-1.** `POST
/trips/{id}/swap` is the second, and it writes `packing_list` alone — never
`forecast`, which is the stored plan a swap obeys rather than re-derives. What
it writes is a **recomputation rather than a model answer**: the stylist is
asked for one day's look and never sees the trip whole, so the list is derived
from every look the trip still has — survivors in their existing positions, ids
no look wears dropped, newcomers appended. The order is load-bearing, because
`reuse_summary`'s tie-break reads it. Both writers fill the column on every path
they can return `200` from, which is the whole of what the response model's
non-null typing rests on. `DECISIONS.md` 209.

**Nothing in the database enforces any of this.** `packing_list` is `JSONB` with
no `CHECK` and no schema, exactly as `occasions` is — the shape is kept by the
Pydantic response model at 4.4 and by `pack_trip`'s own return type, and a row
written by hand can hold anything. That is the same trade `occasions` takes one
column up and is recorded for the same reason: a reader should not infer a
constraint from a printed example.

**The `CHECK` is named `date_order` in the migration and in the model, not
`ck_trips_date_order`.** The convention in `app/db/base.py` is
`ck_%(table_name)s_%(constraint_name)s`, so it expands the short name — and
feeding it the expanded one produces `ck_trips_ck_trips_date_order`. Measured at
4.1 by running both spellings; see the correction under *Migrations* below.

---

## Migrations

One Alembic migration per stage, never a single mega-migration.

| Migration | Stage | Contents |
|---|---|---|
| `0001_initial` | 0 | extensions, enum types, `users`, `items` |
| `0002_looks` | 2 | `looks`, `look_items` |
| `0003_vocabulary` | 2 | `item_category` gains `swimwear` and `sleepwear` |
| `0004_feedback` | 3 | `looks.feedback`, `looks.worn_at`, `items.wear_count`, `items.last_worn_at`, and O-25's two indexes |
| `0005_trips` | 4 | `trips`, `looks.trip_id`, `idx_trips_user_id`, `idx_looks_trip_id` |
| `0006_look_slot` | 4 | `looks.slot`, its `CHECK`, `uq_looks_trip_day_slot`, and two backfills |

**`0003` renumbered the two that follow it**, which is what a migration inserted
mid-project costs; it was scheduled after `0002_looks` precisely so that the
migration this table already named kept its number. It is also the only
migration here that creates nothing: two `ALTER TYPE … ADD VALUE` statements,
and **a `downgrade()` that does nothing on purpose** — PostgreSQL has no `DROP
VALUE`, the only true reversal is a type swap that fails once any row carries
either label, and a downgrade that raised would block the `alembic downgrade
0001` every mutation run starts from. `ADD VALUE IF NOT EXISTS` is what makes
the re-upgrade over two surviving labels clean. That both statements run inside
the transaction `alembic/env.py` opens was **measured on PostgreSQL 18.6 at
2.6a**, not inferred from the version number.

Stage 3's columns were shown inline in the table definitions above for readability before they existed, and **migration `0004` built them at task 3.1**, so the two now agree. The cut this paragraph anticipated did not happen. Had it, `0004` would indeed never have been written: the one task that survives the cut is 3.2, and both columns it needs — `is_saved` and `title` — are `0002`'s. **`looks.trip_id` was the case this paragraph described, one stage further out, and task 4.1 discharged it.** The `looks` DDL above shows it as a foreign key to a table that did not exist until Stage 4: migration `0002` created `looks` **without** it, and `0005` adds it alongside `trips` — one revision, because a `looks.trip_id` pointing at no table is not a schema. Added at the 2026-08-18 audit, when the migrations table already said so and this paragraph did not; closed at 4.1.

**`0006` is the first migration in this project that carries data as well as
schema**, and both `UPDATE`s are the same statement said twice: every look with a
`trip_id` is a `day` look, and every entry in every `trips.occasions` is a `day`
entry. They run between the `ADD COLUMN` and the two constraints, because the
`CHECK` is false for every existing trip look until the first of them has run.
**It is also Stage 4's second revision**, against the "one migration per stage"
line at the head of this section: `0005` is the stage's migration and `0006` is a
widening of the feature it built, taken as a revision of its own because one
already applied to a database cannot be edited.

Migrations are written by hand from the DDL above, never autogenerated — autogenerate does not faithfully reproduce `CITEXT`, partial indexes or `CHECK` constraints. Alembic reads `DATABASE_URL` from `app.core.config.settings`, never from `alembic.ini`, which is committed to the repository.

Constraint names are spelled out in each migration, and the convention pinned in `app/db/base.py` makes the names SQLAlchemy would generate match them — **in the short form the convention expands, which is not what `0001` wrote and is the one claim in this section that was false.**

**Measured at task 4.1, by running both spellings against the test database.**
The convention is `ck_%(table_name)s_%(constraint_name)s`, and it is applied to
a `CHECK` created inside `op.create_table` exactly once. `0001` passed it names
that were *already* expanded, so the live schema does not hold
`ck_users_height_cm_range`, `ck_items_formality_range` or
`ck_items_warmth_range` at all — it holds `ck_users_ck_users_height_cm_range`,
`ck_items_ck_items_formality_range` and `ck_items_ck_items_warmth_range`. The
model and the database describe those three constraints under two names each,
which is precisely the state this paragraph claimed was impossible.

**Nothing detects it and `tests/unit/test_db_naming.py` cannot**, by
construction: it compares `Base.metadata` against a written list, and both
halves say the short name. It is not a runtime defect — no route matches on any
of the three, and `MATCHED_BY_A_ROUTE` covers the two that are matched on, both
`UNIQUE` rather than `CHECK` — so nothing behaves wrongly today. What it costs
is that an `IntegrityError` on a height or a formality reports a name that
appears in no file. `0004` met the same expansion through
`op.create_check_constraint` and bypassed it with raw DDL; `0005` meets it
through `op.create_table` and passes the short name instead, which is why its
`CHECK` is declared as `date_order`. Repairing `0001`'s three is a rename
migration and is **not** task 4.1's — it is recorded here so the next reader
finds it deliberately rather than from a puzzling error message.

**The migration is the one that matters at runtime.** The live schema is built by `0001`, so the name PostgreSQL reports inside an `IntegrityError` is what that migration produced — which is the point the paragraph above turns on, and it is why the three wrong names are the database's truth rather than a cosmetic slip. The names `DECISIONS.md` 037, 040 and 052 each match on in a narrow `if` are `uq_users_email` and `uq_items_short_id`, both `UNIQUE`, both unaffected, and that is what keeps a duplicate email from being reported as a `short_id` collision and a constraint nobody anticipated from being reported as either. The convention has no runtime effect whatever; what it buys is that the model and the database do not describe one constraint under two names — **which it delivers for every constraint except `0001`'s three `CHECK`s, where the short name was never passed and the guarantee therefore never applied.**

**None of this is so that `create_all` can reproduce the schema — it cannot**, and this sentence claimed otherwise through task 0.10. `create_type=False` on all three enum objects (024) means `create_all` emits `CREATE TABLE users`, `CREATE TABLE items` and one `CREATE INDEX`, with **no `CREATE TYPE` and no `CREATE EXTENSION`** — so against a virgin database it fails on `CITEXT` before it ever reaches `item_status`. Re-measured against a mock dialect before task 1.1; `DECISIONS.md` 074. The comments in `app/db/base.py` and `app/models/item.py` repeated the same claim and are corrected alongside this line.

Because the convention has no runtime effect, changing it breaks nothing — verified by mutation, and the suite cannot notice by running in any case, since `conftest.py` migrates once per session against a database that usually already holds the revision. `tests/unit/test_db_naming.py` compares the two artefacts directly for that reason.

ORM models arrive later than the tables they describe — `users` in task 0.5, `items` in 0.7. Each must be imported in `alembic/env.py` when it lands, or `target_metadata` stays empty.

`alembic/script.py.mako` deviates from Alembic's stock template — corrected import order, `str | None` instead of `Union` — so that generated migrations pass `ruff check` unmodified. Do not overwrite it by re-running `alembic init`.

## Seed data

`backend/scripts/seed_demo.py` creates a demo account with **64 pre-tagged items** — real photos, tags already populated, `status='ready'`, no AI calls. The count lives in the committed table, not in the code; `DECISIONS.md` 138 and 141 record where the photographs came from and how they were tagged.

This is not optional. An evaluator will not photograph 40 garments to see the product work, and the E2E suite needs a deterministic wardrobe to assert against. Build it in Stage 1.

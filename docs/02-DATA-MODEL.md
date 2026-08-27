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

**`look_items.role` is deliberately *not* a section here.** `04-API-SPEC.md`
comments six role values on the column and they do not map onto `category`:
`dress` corresponds to none of them and `outerwear` is spelled `outer`. Task 2.7
writes the column `NULL` rather than adopt a vocabulary on behalf of the task
that first reads one — `AUDITS.md` **O-25**, owned by 2.11, and a list this
document has not printed is a list the project has not decided.

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
- **`wear_count` and `last_worn_at` are shown above but do not exist yet.** Migration `0004` adds them, per the table below. The ORM model added at task 0.7 deliberately omits both, because a model declaring a column the database lacks breaks every query against it.

---

### `looks`

```sql
CREATE TABLE looks (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  trip_id       UUID REFERENCES trips(id) ON DELETE CASCADE,

  title         TEXT,
  occasion      TEXT,
  reasoning     TEXT,                     -- why the stylist chose this
  weather_note  TEXT,
  for_date      DATE,

  is_saved      BOOLEAN NOT NULL DEFAULT FALSE,
  feedback      SMALLINT CHECK (feedback IN (-1, 1)),
  worn_at       DATE,

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE look_items (
  look_id   UUID NOT NULL REFERENCES looks(id) ON DELETE CASCADE,
  item_id   UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  role      TEXT,                         -- 'top' | 'bottom' | 'outer' | 'shoes' | 'bag' | 'accessory'
  position  SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (look_id, item_id)
);
```

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

  occasions    JSONB NOT NULL DEFAULT '[]',   -- [{"day":1,"occasion":"work"}, …]
  forecast     JSONB,                          -- cached Open-Meteo response
  packing_list JSONB,                          -- {"item_ids":[…],"reuse_summary":"…"}
  notes        TEXT,

  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

  CHECK (end_date >= start_date)
);
```

The forecast is cached so that reopening a trip does not re-hit the weather API and does not silently change the plan.

Trip length is capped at **14 days** at the API layer.

---

## Migrations

One Alembic migration per stage, never a single mega-migration.

| Migration | Stage | Contents |
|---|---|---|
| `0001_initial` | 0 | extensions, enum types, `users`, `items` |
| `0002_looks` | 2 | `looks`, `look_items` |
| `0003_vocabulary` | 2 | `item_category` gains `swimwear` and `sleepwear` |
| `0004_feedback` | 3 | `looks.feedback`, `looks.worn_at`, `items.wear_count`, `items.last_worn_at` |
| `0005_trips` | 4 | `trips`, `looks.trip_id` |

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

Stage 3's columns are shown inline in the table definitions above for readability, but they are added by migration `0004`. If Stage 3 is cut, migration `0004` is simply never written. **`looks.trip_id` is the same case one stage further out**, and is named here because the `looks` DDL above shows it as a foreign key to a table that does not exist until Stage 4: migration `0002` creates `looks` **without** it, and `0005` adds it alongside `trips`. Added at the 2026-08-18 audit — the migrations table already said so and this paragraph did not.

Migrations are written by hand from the DDL above, never autogenerated — autogenerate does not faithfully reproduce `CITEXT`, partial indexes or `CHECK` constraints. Alembic reads `DATABASE_URL` from `app.core.config.settings`, never from `alembic.ini`, which is committed to the repository.

Constraint names are spelled out literally in each migration, and the convention pinned in `app/db/base.py` makes the names SQLAlchemy would generate match them. **The migration is the one that matters at runtime.** The live schema is built by `0001`, so the name PostgreSQL reports inside an `IntegrityError` is the migration's literal — and that is the string `DECISIONS.md` 037, 040 and 052 each match on in a narrow `if`, which is what keeps a duplicate email from being reported as a `short_id` collision and a constraint nobody anticipated from being reported as either. The convention has no runtime effect whatever; what it buys is that the model and the database do not describe one constraint under two names.

**None of this is so that `create_all` can reproduce the schema — it cannot**, and this sentence claimed otherwise through task 0.10. `create_type=False` on all three enum objects (024) means `create_all` emits `CREATE TABLE users`, `CREATE TABLE items` and one `CREATE INDEX`, with **no `CREATE TYPE` and no `CREATE EXTENSION`** — so against a virgin database it fails on `CITEXT` before it ever reaches `item_status`. Re-measured against a mock dialect before task 1.1; `DECISIONS.md` 074. The comments in `app/db/base.py` and `app/models/item.py` repeated the same claim and are corrected alongside this line.

Because the convention has no runtime effect, changing it breaks nothing — verified by mutation, and the suite cannot notice by running in any case, since `conftest.py` migrates once per session against a database that usually already holds the revision. `tests/unit/test_db_naming.py` compares the two artefacts directly for that reason.

ORM models arrive later than the tables they describe — `users` in task 0.5, `items` in 0.7. Each must be imported in `alembic/env.py` when it lands, or `target_metadata` stays empty.

`alembic/script.py.mako` deviates from Alembic's stock template — corrected import order, `str | None` instead of `Union` — so that generated migrations pass `ruff check` unmodified. Do not overwrite it by re-running `alembic init`.

## Seed data

`backend/scripts/seed_demo.py` creates a demo account with **64 pre-tagged items** — real photos, tags already populated, `status='ready'`, no AI calls. The count lives in the committed table, not in the code; `DECISIONS.md` 138 and 141 record where the photographs came from and how they were tagged.

This is not optional. An evaluator will not photograph 40 garments to see the product work, and the E2E suite needs a deterministic wardrobe to assert against. Build it in Stage 1.

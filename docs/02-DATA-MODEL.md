# 02 — Data Model

PostgreSQL 16. SQLAlchemy 2.0 ORM, Alembic migrations.

**This document is authoritative.** Do not add fields or enum values that are not listed here. If something is genuinely missing, stop and ask before changing the schema.

---

## The closed vocabulary

Every descriptive attribute comes from a fixed list. This is the most important design decision in the project.

Free-text tagging produces `"light blue"`, `"baby blue"`, `"sky blue"`, and `"pale blue"` for the same garment. Filtering breaks, grouping breaks, and the stylist model receives inconsistent input. A closed vocabulary means any value outside the list is a validation error that triggers a retry, and every downstream feature can rely on exact matching.

These live in `backend/app/enums.py` and are mirrored in `frontend/src/app/shared/models/enums.ts`. Both files are generated from this document by hand and must stay in sync.

### `category` — 7 values

```
top · bottom · dress · outerwear · shoes · bag · accessory
```

### `subcategory` — validated against the parent category

```
top:        t_shirt · tank · shirt · blouse · sweater · sweatshirt · hoodie · bodysuit
bottom:     jeans · trousers · shorts · skirt · leggings · cargo
dress:      dress · jumpsuit
outerwear:  jacket · coat · blazer · cardigan · vest · puffer
shoes:      sneakers · boots · heels · flats · sandals · loafers
bag:        tote · crossbody · shoulder · clutch · backpack
accessory:  belt · scarf · hat · sunglasses · jewelry
```

### `fit` — the silhouette

```
skinny · slim · straight · relaxed · oversized · wide · bodycon · a_line · flowy
```

Always nullable. A bag has no meaningful silhouette, and a value outside this list is coerced to `NULL` rather than rejected — an absent attribute is better than a wrong one, and neither the stylist nor any filter requires it.

### `length`

```
sleeveless · short_sleeve · long_sleeve · crop · regular · longline
mini · midi · maxi · ankle · full
```

Always nullable, on the same terms as `fit`. One flat list covering three axes — sleeve, top length, hem — with no per-category restriction, so `maxi` on a t-shirt validates. Recorded as a known limitation in `DECISIONS.md` 029.

### `rise` — bottoms only, `NULL` elsewhere

```
low · mid · high
```

This single field is what separates mom jeans from low-rise jeans, and it drives proportion rules in the stylist prompt.

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

### `item_status`

```
processing · ready · failed
```

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

  -- AI-extracted, all NULL until tagging completes
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

- **All tag fields are nullable.** The row is created the moment the image lands, with `status='processing'`, so the grid can render a tile immediately. Tags fill in seconds later.
- **`image_public_id`, not a URL.** URLs are constructed at read time with the transform needed for that context — thumbnail, full view, or the 800px version sent to the vision model. Storing a URL would freeze one transform forever.
- **`user_edited`** guards against a retag overwriting a manual correction, and gives the testing story a hook: it measures how often the AI got it wrong.
- **`attributes JSONB`** absorbs future fields (brand, purchase price, embellishments) without a migration.
- **`short_id`** is 6 characters from an unambiguous alphabet — `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, no `0`/`O`/`1`/`I`/`L`. Generate, check uniqueness, retry on collision. It carries no index of its own: the `UNIQUE` constraint already creates one, and a second would be an exact duplicate maintained on every write.

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
| `0003_feedback` | 3 | `looks.feedback`, `looks.worn_at`, `items.wear_count`, `items.last_worn_at` |
| `0004_trips` | 4 | `trips`, `looks.trip_id` |

Stage 3's columns are shown inline in the table definitions above for readability, but they are added by migration `0003`. If Stage 3 is cut, migration `0003` is simply never written.

Migrations are written by hand from the DDL above, never autogenerated — autogenerate does not faithfully reproduce `CITEXT`, partial indexes or `CHECK` constraints. Alembic reads `DATABASE_URL` from `app.core.config.settings`, never from `alembic.ini`, which is committed to the repository.

Constraint names follow the convention pinned in `app/db/base.py` and are spelled out literally in each migration, so a schema built by `create_all` and one built by migrations agree.

ORM models arrive later than the tables they describe — `users` in task 0.5, `items` in 0.7. Each must be imported in `alembic/env.py` when it lands, or `target_metadata` stays empty.

`alembic/script.py.mako` deviates from Alembic's stock template — corrected import order, `str | None` instead of `Union` — so that generated migrations pass `ruff check` unmodified. Do not overwrite it by re-running `alembic init`.

## Seed data

`backend/scripts/seed_demo.py` creates a demo account with **40 pre-tagged items** — real photos, tags already populated, `status='ready'`, no AI calls.

This is not optional. An evaluator will not photograph 40 garments to see the product work, and the E2E suite needs a deterministic wardrobe to assert against. Build it in Stage 1.

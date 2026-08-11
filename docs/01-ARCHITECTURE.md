# 01 — Architecture

## System overview

```
┌─────────────────┐
│  Angular 22     │  Browser · mobile-first · camera + gallery input
│  (Vercel)       │
└────────┬────────┘
         │ HTTPS · JWT in Authorization header
         ▼
┌─────────────────────────────────────────────────┐
│  FastAPI  (Render)                              │
│                                                 │
│  api/v1/     auth · items · looks · trips       │
│  services/   cloudinary · vision · stylist ·    │
│              weather · packing                  │
│  BackgroundTasks → async tagging queue          │
└───┬──────────────┬──────────────┬───────────────┘
    │              │              │
    ▼              ▼              ▼
┌─────────┐  ┌────────────┐  ┌──────────────┐
│Postgres │  │ Cloudinary │  │ OpenAI       │
│ (Neon)  │  │  media     │  │ gpt-4o-mini  │
└─────────┘  └────────────┘  └──────────────┘
                                    ▲
                             ┌──────┴──────┐
                             │ Open-Meteo  │
                             │  weather    │
                             └─────────────┘
```

The backend is the only component that holds secrets. The browser never touches the OpenAI key, and never talks to Cloudinary directly (see "Upload path" below).

---

## Flow 1 — Adding a garment

```
1. User selects/photographs image(s)
2. Angular POSTs multipart to  POST /api/v1/items/upload
3. Backend uploads bytes to Cloudinary  →  public_id
4. Backend INSERTs item row  { status: 'processing', tags: NULL }
5. Backend returns 202 with the item rows immediately
6. Angular renders skeleton tiles in the grid at once
7. BackgroundTask per item:
     a. build Cloudinary transform URL (800px, auto format)
     b. call OpenAI vision with the strict JSON schema
     c. validate against enums
     d. on success → UPDATE item SET status='ready', tags…
        on failure → retry once, then status='failed'
8. Angular polls  GET /api/v1/items?status=processing  every 2s
   until the set is empty, then stops
```

**Why the user never waits:** the HTTP response returns after step 5, roughly 1–2 seconds for the Cloudinary upload. Tagging takes another 2–4 seconds per item and happens after the response is already on screen. Twenty items feel instant even though tagging runs for a minute.

**Why polling and not WebSockets:** polling is ~15 lines, works through every proxy, and survives Render's free-tier idle behaviour. WebSockets would be the correct answer at scale; at 20 items per session they are unjustified complexity. Recorded in `DECISIONS.md`.

---

## Flow 2 — Requesting an outfit

```
1. POST /api/v1/looks/suggest  { occasion, date, wants_outerwear? }
2. Backend fetches user's ready items  (single query, no filtering by season)
3. Backend fetches forecast for user's saved lat/lon from Open-Meteo
4. Backend converts temperature → an explicit rule sentence  (03-AI-CONTRACTS)
5. Backend serialises the wardrobe to compact one-line-per-item text
6. Backend calls OpenAI with response_format = strict JSON schema
7. Backend validates: every returned short_id exists in THIS user's wardrobe
     - invalid → one retry with the violation named in the message
     - still invalid → 502 with a clean error
8. Backend hydrates short_ids into full item objects (image URLs, names)
9. Angular renders the look card
```

### The whole wardrobe goes into the prompt

A 150-item wardrobe serialises to roughly 7,000 tokens in the compact format. That fits comfortably in a single request and costs a fraction of a cent with `gpt-4o-mini`. There is therefore **no retrieval layer, no embeddings, and no vector database** in this project.

Aggressive pre-filtering is also actively harmful to quality: filtering out "summer" items in winter prevents the model from suggesting a summer dress with boots and a leather jacket, which is exactly the kind of combination that makes the product feel smart. The only server-side exclusions are unambiguous ones — swimwear and sleepwear — and they are configurable.

If a wardrobe ever exceeds 400 items, the fallback is documented in `03-AI-CONTRACTS.md`. It is not implemented.

---

## Flow 3 — Packing a trip

Same pipeline as Flow 2, run once with a richer context:

```
1. POST /api/v1/trips/pack  { destination, start_date, end_date, occasions[] }
2. Backend geocodes destination (Open-Meteo geocoding, free)
3. Backend fetches the daily forecast for the date range
4. Backend builds ONE weather rule line PER DAY
5. Single OpenAI call: wardrobe + per-day weather + per-day occasions
     + explicit reuse instruction
6. Model returns N looks plus a deduplicated packing list
7. Same validation as Flow 2, then hydrate and render
```

One call, not one per day. Per-day calls cannot reuse items intelligently because each call is blind to the others' choices. Reuse is the entire point of a packing list.

---

## Repository layout

Monorepo, three deployable units.

```
bijoux/
├── docs/                        ← this documentation set
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, CORS, router registration
│   │   ├── core/
│   │   │   ├── config.py        pydantic-settings, reads .env
│   │   │   ├── security.py      JWT encode/decode, password hashing
│   │   │   ├── errors.py        ApiError and the {detail, code} envelope
│   │   │   ├── logging.py       JSON in production, human-readable in dev
│   │   │   ├── short_id.py      the 6-char id the AI layer uses
│   │   │   └── deps.py          get_db, get_current_user
│   │   ├── db/
│   │   │   ├── session.py       engine, SessionLocal
│   │   │   └── base.py          declarative Base
│   │   ├── models/              SQLAlchemy ORM: user, item, look, trip
│   │   ├── schemas/             Pydantic request/response models
│   │   ├── enums.py             THE closed vocabulary — single source of truth
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   └── routes/          auth.py, items.py, looks.py, trips.py, me.py
│   │   ├── services/
│   │   │   ├── storage.py       Cloudinary upload + transform URLs
│   │   │   ├── vision.py        image → tags
│   │   │   ├── stylist.py       wardrobe + context → looks
│   │   │   ├── packing.py       trip orchestration
│   │   │   ├── weather.py       Open-Meteo client + rule generation
│   │   │   └── serializer.py    wardrobe → compact prompt text
│   │   └── prompts/             *.md prompt templates, version-controlled
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/            golden dataset, recorded AI responses
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/app/
│       ├── core/                auth guard, http interceptor, api services
│       ├── features/
│       │   ├── auth/
│       │   ├── wardrobe/        grid, upload, item detail/edit
│       │   ├── stylist/         request form, look card
│       │   ├── trips/           trip form, packing view
│       │   └── profile/         measurements, location, preferences
│       └── shared/              ui components, pipes, models
│   ├── src/environments/        environment.ts + .development.ts
│   └── public/i18n/en.json      corrected at 0.8 — `public/` is Angular's
│                                asset root since v18, and a file under
│                                src/app/ is never served
├── e2e/                         Playwright, TypeScript
│   ├── pages/                   Page Object Model
│   ├── tests/
│   └── fixtures/
└── .github/workflows/ci.yml
```

---

## Cross-cutting decisions

### Upload goes through the backend

The browser sends bytes to FastAPI, which forwards them to Cloudinary. Direct browser-to-Cloudinary uploads (signed) would save one hop, but then the backend cannot guarantee that every stored image has a matching database row, and orphaned media is a real operational annoyance. One hop is worth the consistency.

**Constraint:** enforce a 10 MiB per-file limit and accept only JPEG, PNG, WebP and HEIC/HEIF, both decided before touching Cloudinary. The format is identified from the file's own bytes, not from the `Content-Type` the client declares, and the list is narrower than `image/*` on purpose — see `DECISIONS.md` 045.

**Both decisions are made for the whole batch before any file is uploaded**, because one bad file rejects the whole request and validating as you go would strand the assets already sent. Type comes from a twelve-byte read per part and size from `UploadFile.size`, so a twenty-file batch is fully decided for 240 bytes of reading and only one file's bytes are ever resident (`DECISIONS.md` 048). What that bounds is process memory, not the request: Starlette spools the entire body before the handler runs, rolling parts above 1 MiB to disk, so twenty 10 MiB files cost ~200 MB of ephemeral disk whatever our code does. See the amendment to `DECISIONS.md` 008 and the risk entry in `07-DEPLOYMENT.md`.

### Background jobs use `BackgroundTasks`, not Celery

Celery plus Redis plus a worker process is three more moving parts, two more environment variables, and another thing that can break on the demo day. FastAPI's `BackgroundTasks` runs the tagging coroutine in the same process after the response is sent, which is exactly the required behaviour at this scale.

Accepted trade-off: if the process restarts mid-tagging, in-flight items stay `processing`. Mitigation is a `POST /items/{id}/retag` endpoint plus a startup sweep that resets stale `processing` rows older than 10 minutes to `failed`.

### `short_id` alongside `id`

Items carry a UUID primary key **and** a 6-character `short_id`. Only `short_id` is ever sent to or received from the model. Full UUIDs would consume roughly 1,200 tokens per request on identifiers alone, and long random strings are more prone to transcription errors by the model.

### Every AI call is a service function, never inline in a route

`vision.py` and `stylist.py` expose plain functions with typed inputs and outputs. Routes call them. This makes them trivially mockable in tests, which is what allows the entire E2E suite to run without an API key. See `06-TESTING-STRATEGY.md`.

### Prompts live in `app/prompts/*.md`, not in Python strings

Prompts are the highest-churn artefact in this project. Keeping them as files means diffs are readable, and changing a prompt does not require touching code.

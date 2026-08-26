# Bijoux

**It packs your suitcase from your own closet.**

Bijoux is a web application for the clothes you already own. You photograph a
garment; the photograph goes to a vision model, which reads back a structured
description of it — category, subcategory, colour, pattern, warmth, formality
and the rest of a closed vocabulary — so the wardrobe builds itself instead of
being typed in. Once the wardrobe exists, Bijoux works as a stylist over it:
outfits assembled from *your* items, adjusted to the real weather outside. The
feature it is built around is the trip. Give it a destination and dates and it
takes the forecast for those days, works out what the days actually demand, and
returns a packing list in which every garment is one you already own.

**Status:** in active development, one stage at a time.
[`docs/PROGRESS.md`](docs/PROGRESS.md) is the live tracker and says what exists
today; not everything described above is built yet.

## Stack

Angular 22 (standalone, signals, zoneless) and Tailwind on the front, FastAPI
and SQLAlchemy 2.0 on Python 3.14 behind it, PostgreSQL 18 for storage,
Cloudinary for the images and OpenAI for both the vision tagging and the
stylist reasoning. Weather comes from Open-Meteo, which needs no key.
[`docs/README.md`](docs/README.md#stack-at-a-glance) has the version-by-version
table; [`docs/01-ARCHITECTURE.md`](docs/01-ARCHITECTURE.md) has the reasoning.

## Running it locally

**Prerequisites:** Python 3.14 (`backend/.python-version`), Node 24 (`.nvmrc`),
and a PostgreSQL database. The one this project documents is Neon's free tier,
which serves **Postgres 18** — the version the test database pins to match.
There is no separate development database: the `DATABASE_URL` you set locally is
the same one a deployment reads, so a clean clone needs its own Neon project
rather than a copy of anyone else's. A Cloudinary account and an OpenAI key are
needed for uploading and tagging; the API starts without them.

**Environment.** `backend/.env` is the only `.env` the backend reads, and it is
read relative to the working directory — so every backend command below is run
from `backend/`. A `.env` at the repository root is invisible to the
application. Copy the template and fill it in:

```bash
cd backend
cp .env.example .env
```

The variables, by name: `DATABASE_URL` and `JWT_SECRET` are the two the
application requires. `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`,
`CLOUDINARY_API_SECRET`, `CLOUDINARY_UPLOAD_FOLDER` and
`CLOUDINARY_REMOVE_BACKGROUND` carry the media account — the cloud name is not
optional in any environment that serves items, for reasons
[`docs/07-DEPLOYMENT.md`](docs/07-DEPLOYMENT.md#environment-variables) sets out.
`OPENAI_API_KEY` and `OPENAI_TIMEOUT_SECONDS` carry the AI account, and
`USE_FAKE_AI` replaces it with recorded fixtures. `JWT_ALGORITHM`,
`JWT_EXPIRE_DAYS`, `CORS_ORIGINS`, `MAX_UPLOAD_MB`, `MAX_FILES_PER_REQUEST` and
`ENV` all have working defaults. `TEST_DATABASE_URL` is for the test suite and
is described under [Tests](#tests) below. That document is the reference for
every one of them, including which are required and what each defaults to.

The frontend needs no environment file. `frontend/src/environments/` is
committed and already points development builds at `http://localhost:8000/api/v1`.

**Install and migrate**, from `backend/`:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

**Then the two commands**, one per terminal:

```bash
cd backend && uvicorn app.main:app --reload   # API on http://localhost:8000
cd frontend && npm install && npm start       # web on http://localhost:4200
```

`npm start` is the script defined in `frontend/package.json`; use it rather
than calling the Angular CLI directly.

## The demo wardrobe

`backend/scripts/seed_demo.py` creates a demo account and a fixed wardrobe from
a committed table of Cloudinary ids and hand-written tags. It makes no AI call,
so the wardrobe is the same wardrobe every run. Run it from `backend/` **as a
module** — `python scripts/seed_demo.py` cannot work:

```bash
python -m scripts.seed_demo --yes                           # seed; refuses if the account exists
python -m scripts.seed_demo --yes --reset                   # delete the demo account and reseed
python -m scripts.seed_demo --yes --reset --with-failures   # include the two failed rows
python -m scripts.seed_demo --upload DIR                    # re-photograph: uploads a folder, logs the table, writes no rows
```

`--upload` is for regenerating that committed table and needs a folder of
images, which is not in the repository.

Sign in as **`demo@bijoux.app`** / **`bijoux-demo-wardrobe`**, or press **View
the demo wardrobe** on the login screen. This is a published credential, not a
leaked one: it is deliberately in the source, and
[`docs/07-DEPLOYMENT.md`](docs/07-DEPLOYMENT.md#the-demo-password-is-published-not-secret)
explains why, along with what else to know about a shared and mutable account.

## Tests

**Backend** — pytest, from `backend/`. The suite needs `TEST_DATABASE_URL` and
refuses to run if it is unset or equal to `DATABASE_URL`, because it creates
and drops rows.
[`docs/07-DEPLOYMENT.md`](docs/07-DEPLOYMENT.md#test_database_url-added-at-task-010)
has a Docker one-liner for it. Migrations are applied to that database by the
suite itself.

```bash
cd backend && pytest -m "not eval"
```

`-m "not eval"` leaves out the AI evaluation tests, which call a real provider
and cost money.

**Frontend** — Vitest through the Angular CLI, from `frontend/`:

```bash
cd frontend && npm test
```

[`docs/06-TESTING-STRATEGY.md`](docs/06-TESTING-STRATEGY.md) is the source of
truth for what each layer covers and how a non-deterministic AI gets tested at
all.

## Documentation

The documentation is the source of truth for this project; where it and the
code disagree, one of them is a bug. [`docs/README.md`](docs/README.md) maps
the full set and is the place to start. Four to know about:

| | |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | The decision log, and the authoritative one. Numbered entries; the rest of the documentation cites them by number for the *why* behind a choice. |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Live build tracker — the current stage and what is ticked off. |
| [`docs/stages/`](docs/stages/) | `STAGE-0` … `STAGE-5`, the build order, one numbered task at a time. |
| [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) | Coding standards, commit format, and the definition of done. |

# 07 — Deployment

Everything below runs on free tiers. Total cost is the OpenAI usage — a few dollars across the whole project.

| Component | Service | Notes |
|---|---|---|
| Database | Neon | Postgres 18, free tier, branching for a separate test DB |
| Backend | Render | Web Service, free tier — sleeps after 15 min idle |
| Frontend | Vercel | Static Angular build |
| Media | Cloudinary | Free tier: 25 monthly credits, far beyond this project's needs |
| AI | OpenAI | `gpt-4o-mini-2024-07-18`, pay as you go. Pinned once in `app/core/config.py` (078) |
| Weather | Open-Meteo | No key, no account, free for non-commercial use |

**Render free-tier cold starts take 30–50 seconds.** Do not discover this during the defence. Either hit `/health` a few minutes beforehand, or upgrade to the paid tier for that week.

---

## Environment variables

### Backend — `backend/.env.example`

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host/db?sslmode=require

JWT_SECRET=              # openssl rand -hex 32
JWT_ALGORITHM=HS256
JWT_EXPIRE_DAYS=7

CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
CLOUDINARY_UPLOAD_FOLDER=bijoux
CLOUDINARY_REMOVE_BACKGROUND=false

OPENAI_API_KEY=
# Both default to OPENAI_MODEL in app/core/config.py, the single pin.
# Uncomment only to override; set-but-empty would override it with "".
#OPENAI_VISION_MODEL=
#OPENAI_STYLIST_MODEL=
OPENAI_TIMEOUT_SECONDS=30

USE_FAKE_AI=false        # true in CI and E2E — returns recorded fixtures
CORS_ORIGINS=http://localhost:4200,https://bijoux.vercel.app
MAX_UPLOAD_MB=10
MAX_FILES_PER_REQUEST=20
ENV=development
```

Only `DATABASE_URL` and `JWT_SECRET` are required. Everything else has a default, and the API keys default to empty strings so that CI can run without an OpenAI account.

**`backend/.env` is the only `.env` the backend reads.** `Settings.model_config` sets `env_file=".env"`, which pydantic-settings resolves against the **current working directory**, and every backend command — `uvicorn`, `alembic`, `pytest`, any `python -` one-liner — is run from `backend/`. A `.env` at the repository root is therefore invisible to the application no matter what is in it. This is worth stating because the failure is silent in the worst way: a missing key does not raise at import, it produces a working process that fails on the first call that needs it. If a credential appears not to be picked up, check which file it is in before checking anything else. `backend/.env.example` is the template, it is the only `.env.example` in the repository, and it lists all five Cloudinary variables.

Empty Cloudinary credentials fail at call time rather than at import, and the SDK reports them as a plain `ValueError`, not as a Cloudinary error — see `DECISIONS.md` 044 for why `storage.py` catches wider than the SDK documents.

**An unset `CLOUDINARY_CLOUD_NAME` breaks reads as well as writes, and less legibly.** `build_url` raises `StorageError` rather than emit a URL with an empty host (046), and from task 0.7 it runs during response serialisation, so `GET /items` fails with a bare `500` carrying no `code` — the one shape `CONVENTIONS.md` promises the frontend never sees. `/health` does not check Cloudinary, so nothing surfaces it earlier. Recorded as a known limitation with task 5.4 as its owner (`DECISIONS.md` 050); the practical answer is that this variable is not optional in any environment that serves items.

## Upload sizing on the free tier

`POST /items/upload` accepts up to 20 files of up to 10 MiB. The route reads one file into memory at a time (`DECISIONS.md` 048), so peak RSS is bounded at roughly 10 MiB — but **Starlette parses and spools the whole multipart body before the handler runs**, rolling every part above 1 MiB to a temporary file. A maximal request therefore writes ~200 MB to the instance's ephemeral disk before any of our code sees it, and a client ignoring the documented limits can do so repeatedly.

Nothing in the application can prevent this: FastAPI resolves the form before the handler body executes, so the only bound is a `Content-Length` check in middleware or a request-size limit at the proxy. **Neither is built.** It belongs with the Render configuration rather than with the API — task 5.6 — and it is written down here rather than left as a surprise under load. The amendment to `DECISIONS.md` 008 has the measurements.

`APP_VERSION` is deliberately **not** an environment variable — it is a constant in `app/core/config.py`, so a deployed build cannot misreport its own version.

`DATABASE_URL` carries SQLAlchemy's `postgresql+psycopg://` prefix. `psql` does not understand it; strip `+psycopg` before pasting a connection string into a terminal.

### `TEST_DATABASE_URL`, added at task 0.10

The backend test suite refuses to run without it, and refuses to run if it is equal to `DATABASE_URL`. It is **not** a field on `Settings` — no application code reads it, and it must never be set on Render (`DECISIONS.md` 073). Locally:

```bash
docker run --name bijoux-test-db -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=bijoux_test -p 5433:5432 -d postgres:18

TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/bijoux_test
```

The same variable is what the Neon `test` branch below and CI's service container are for; only its value changes. The suite runs `alembic upgrade head` against it once per session, so the target needs no preparation beyond existing. **Postgres 18 rather than 16**, to match what Neon actually serves — CI's `postgres:16` pin is task 5.5's to correct.

## The demo account, and the seed script that creates it

`backend/scripts/seed_demo.py` creates `demo@bijoux.app` and its wardrobe from a
committed table of Cloudinary `public_id`s and hand-written tags. It makes no AI
call, so the wardrobe is the same wardrobe every run. Run it **from `backend/`,
as a module** — `python scripts/seed_demo.py` cannot work, because that form puts
`backend/scripts` on `sys.path` instead of `backend/` and `import app` fails.

```bash
python -m scripts.seed_demo --upload ~/bijoux-seed-images   # uploads, logs the table, writes no rows
python -m scripts.seed_demo --yes                           # seeds; refuses if the account exists
python -m scripts.seed_demo --yes --reset                   # deletes demo@bijoux.app and reseeds
python -m scripts.seed_demo --yes --reset --with-failures   # adds the two failed rows
```

It logs the host, the database name and the current user and item counts before
it writes anything, and refuses without `--yes`. It refuses outright if
`DATABASE_URL` resolves to `TEST_DATABASE_URL` — `conftest.py`'s guard from the
other side. Every write and delete is scoped to the demo user's id; there is no
unscoped `DELETE` and no `TRUNCATE` in the file. `DECISIONS.md` 130–135.

### The demo password is published, not secret

**`demo@bijoux.app` / `bijoux-demo-wardrobe`.**

This is a **published credential**, not a leaked one. It is in
`backend/scripts/seed_demo.py`, in `frontend/src/app/features/auth/login.page.ts`
— which needs it for the **View the demo wardrobe** button — and here. It was
chosen fresh for this account and is reused from nothing. Written down in this
document because a password found in committed source with no explanation reads
as a mistake, and because the pre-defence checklist needs somewhere to point.

**The same two strings live in two languages and nothing compares them.** Drift
gives a demo button that answers `401` against a correctly seeded database, and
the only thing that catches it is signing in with the button — which is why that
is a checklist line below and not an assumption. `DECISIONS.md` 136 and 137.

**The demo account is shared and mutable.** Every visitor who presses the button
is the same user; anything they edit or delete stays that way until
`--reset` is run again.

**Before this frontend is deployed, read `AUDITS.md` O-5.** The button hands any
visitor an authenticated session, and `POST /items/upload` queues a real tagging
call per file. The rate limit that answers this is specified in `04-API-SPEC.md`
and is not built.

---

### Frontend — `frontend/src/environments/`

Three files, created by `ng generate environments` at task 0.8 and typed against a shared interface so a key cannot be present in one and missing from the other:

```ts
// environment.model.ts — the shape both files satisfy
export interface Environment {
  readonly production: boolean;
  readonly apiUrl: string;
  readonly cloudinaryCloudName: string;
}

// environment.ts — the BASE file, used by `ng build`
export const environment: Environment = {
  production: true,
  apiUrl: 'https://REPLACE-WITH-RENDER-HOST/api/v1',
  cloudinaryCloudName: 'REPLACE-WITH-CLOUD-NAME',
};

// environment.development.ts — swapped in by fileReplacements for `ng serve`
export const environment: Environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api/v1',
  cloudinaryCloudName: 'REPLACE-WITH-CLOUD-NAME',
};
```

**The base file is the production one**, and the development file is the replacement — that is the direction `ng generate environments` wires `fileReplacements`, and it is the opposite of what this section showed through task 0.7, which printed a single file with `production: false`.

Only the Cloudinary **cloud name** reaches the browser — it is public by design, used to build transform URLs. The API key and secret never leave the backend. Note that unlike `backend/.env`, these files **are committed**: the cloud name belongs in them, a credential never does.

---

## A note on Cloudinary background removal

Cut-out garments on white are what make the look card look like a catalogue rather than a scrapbook. But background removal on Cloudinary is a **paid add-on** with a limited free allowance, and burning it during development is a real risk.

Plan:
1. Build and demo with `CLOUDINARY_REMOVE_BACKGROUND=false`. Photos taken against a plain wall look perfectly acceptable.
2. If the free add-on allowance is available, enable it in Stage 4 for the demo wardrobe only.
3. Free fallback if needed: `rembg` (Python, runs locally) as a one-off script over the seed images. Do not put it in the request path — it is slow and memory-hungry, and Render's free tier will not tolerate it.

Verify the current allowance before relying on this. Treat it as polish, never as a dependency.

**`CLOUDINARY_REMOVE_BACKGROUND` has no consumer.** It is read by nothing as of task 0.6, deliberately: nothing in 0.6's scope mentions it and Stage 0 does not build for later stages. When it is wired, it must be a **delivery-time** transform (`e_background_removal`), not an upload parameter. Applied at upload it would affect only assets uploaded after the flag was set, which contradicts the plan above — enabling it in Stage 4 for a demo wardrobe uploaded in Stage 1 would do nothing at all.

---

## Cloudinary transform URLs

Build these in `services/storage.py` and in the frontend `cloudinaryUrl` pipe. Never store a full URL in the database.

```
thumbnail  w_300,h_300,c_pad,b_white,f_auto,q_auto
detail     w_800,c_limit,f_auto,q_auto
vision     w_800,c_limit,f_jpg,q_auto         # what the AI sees
lookcard   w_400,h_500,c_pad,b_transparent,f_auto,q_auto
```

`c_pad` with a white background keeps the grid visually even regardless of the original aspect ratio. This matters more than it sounds — a grid of mixed aspect ratios looks broken.

Three things to know about this table, all established at task 0.6:

- **`detail` and `vision` held the same string until task 1.1, and now differ.** That is precisely what the split existed to allow: `vision` moved to `f_jpg` without changing what a person sees on the item screen. `DECISIONS.md` 046 and 083.
- **`lookcard`'s `b_transparent` does nothing useful yet.** Padding to transparent around a photograph that still has its own background produces a transparent border and an unchanged photo. It becomes correct only if background removal is ever switched on.
- **`f_auto` on a HEIC original was settled at task 1.1 and the fix was applied.** One real iPhone HEIC, fetched three ways: no `Accept` header and `Accept: */*` both returned `image/jpeg`, a browser-like `Accept` returned `image/webp`. Nothing broken — but `f_auto`'s answer depends on a header OpenAI's fetcher sends and we cannot observe, so `vision` is pinned to `f_jpg`. `DECISIONS.md` 083 records what was and was not caught.

The backend builds these URLs with an f-string rather than with `cloudinary.utils.cloudinary_url`, which returns a tuple and emits `http://` unless `secure=True` is configured. The frontend pipe hand-formats the identical string. Both must agree byte for byte, which is the reason neither uses a library.

---

## Deployment steps

### Neon
1. Create project, copy the connection string.
2. Create a `test` branch for the CI database.
3. Run `alembic upgrade head` against `main`.

### Render
1. New Web Service from the GitHub repo, root directory `backend`.
2. Build: `pip install -r requirements.txt`
3. Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add all environment variables. Health check path `/health`.

Running migrations in the start command is acceptable at this scale — one instance, no concurrent boots. It is not a pattern to carry into a multi-instance production system, and saying so out loud in the defence is a point in your favour.

### Vercel
1. Import the repo, root directory `frontend`.
2. Build: `npm run build`, output `dist/bijoux/browser`. **Node 24** — set it explicitly in Vercel's Node.js Version setting. Angular 22 declares `node: ^22.22.3 || ^24.15.0 || >=26.0.0`; Node 20 is excluded and an earlier draft of this line was wrong to allow it (`DECISIONS.md` 054).
3. Add the Vercel domain to `CORS_ORIGINS` on Render.

**There is no environment variable for the API URL.** An earlier draft of this section said to set `NG_APP_API_URL` in Vercel; that prefix belongs to `@ngx-env/builder`, which this project does not use, so the variable would have been set, silently ignored, and discovered only when the deployed build called `localhost`. The API URL is edited in `frontend/src/environments/environment.ts` and pushed — see `DECISIONS.md` 061. Do not go looking for the dashboard setting.

The Angular project is named `bijoux` while its directory is `frontend`, which is why the root directory and the output path disagree. That is deliberate (`DECISIONS.md` 055).

---

## CI — `.github/workflows/ci.yml`

```yaml
jobs:
  backend:
    services: { postgres: { image: postgres:16 } }
    steps: ruff → mypy → pytest -m "not eval"
  frontend:
    steps: npm ci → ng lint → ng build --configuration production
  e2e:
    needs: [backend, frontend]
    env: { USE_FAKE_AI: "true" }
    steps: start API → serve build → npx playwright test → upload report
```

No OpenAI key is present in CI. If a test needs one, that test belongs in the `eval` group and does not run here.

---

## Pre-defence checklist

- [ ] Demo account seeded — `python -m scripts.seed_demo --yes` from `backend/`, credentials in the section above
- [ ] **View the demo wardrobe** pressed once against the seeded database, because nothing but a real sign-in compares the two copies of the password
- [ ] `--with-failures` decided: on if the failed tile, its retry and the hand-recovery path are being shown; off for a clean wardrobe
- [ ] Backend warmed up — free-tier cold start already paid
- [ ] A rehearsed 3-minute path: upload → tag → daily look → 4-day trip
- [ ] Screen-recorded backup of that path, in case the wifi fails
- [ ] `docs/eval-results.md` populated with real accuracy numbers
- [ ] Latest CI run green, Playwright HTML report available to show
- [ ] OpenAI account has credit
- [ ] One deliberate failure ready to demonstrate — retag a blurry photo and show the graceful error state

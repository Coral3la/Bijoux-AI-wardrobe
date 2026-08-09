# 07 — Deployment

Everything below runs on free tiers. Total cost is the OpenAI usage — a few dollars across the whole project.

| Component | Service | Notes |
|---|---|---|
| Database | Neon | Postgres 16, free tier, branching for a separate test DB |
| Backend | Render | Web Service, free tier — sleeps after 15 min idle |
| Frontend | Vercel | Static Angular build |
| Media | Cloudinary | Free tier: 25 monthly credits, far beyond this project's needs |
| AI | OpenAI | `gpt-4o-mini`, pay as you go |
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
OPENAI_VISION_MODEL=gpt-4o-mini
OPENAI_STYLIST_MODEL=gpt-4o-mini
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

`APP_VERSION` is deliberately **not** an environment variable — it is a constant in `app/core/config.py`, so a deployed build cannot misreport its own version.

`DATABASE_URL` carries SQLAlchemy's `postgresql+psycopg://` prefix. `psql` does not understand it; strip `+psycopg` before pasting a connection string into a terminal.

### Frontend — `frontend/src/environments/`

```ts
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api/v1',
  cloudinaryCloudName: 'your-cloud-name',
};
```

Only the Cloudinary **cloud name** reaches the browser — it is public by design, used to build transform URLs. The API key and secret never leave the backend.

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
vision     w_800,c_limit,f_auto,q_auto        # what the AI sees
lookcard   w_400,h_500,c_pad,b_transparent,f_auto,q_auto
```

`c_pad` with a white background keeps the grid visually even regardless of the original aspect ratio. This matters more than it sounds — a grid of mixed aspect ratios looks broken.

Three things to know about this table, all established at task 0.6:

- **`detail` and `vision` hold the same string and are still two entries.** The vision transform is free to move when task 1.11's golden-set run says the model wants something different, without changing what a person sees on the item screen. `DECISIONS.md` 046.
- **`lookcard`'s `b_transparent` does nothing useful yet.** Padding to transparent around a photograph that still has its own background produces a transparent border and an unchanged photo. It becomes correct only if background removal is ever switched on.
- **`f_auto` on a HEIC original is unverified.** Cloudinary documents the fallback as "the format specified by the file extension", and these URLs carry no extension. It matters for the `vision` transform in particular, because that URL is fetched by OpenAI rather than by a browser and OpenAI may send no `Accept` header. Task 1.1 owns settling it before the first live vision call; if it fails, the fix is `f_jpg` on `vision` alone.

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
2. Build: `npm run build`, output `dist/bijoux/browser`. Node 20 or newer — Angular 22 requires it.
3. Add `NG_APP_API_URL` pointing at the Render URL.
4. Add the Vercel domain to `CORS_ORIGINS` on Render.

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

- [ ] Demo account seeded with 40 tagged items, password written down somewhere you can read it under pressure
- [ ] Backend warmed up — free-tier cold start already paid
- [ ] A rehearsed 3-minute path: upload → tag → daily look → 4-day trip
- [ ] Screen-recorded backup of that path, in case the wifi fails
- [ ] `docs/eval-results.md` populated with real accuracy numbers
- [ ] Latest CI run green, Playwright HTML report available to show
- [ ] OpenAI account has credit
- [ ] One deliberate failure ready to demonstrate — retag a blurry photo and show the graceful error state

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

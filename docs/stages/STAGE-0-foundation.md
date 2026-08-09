# Stage 0 — Foundation

**Week 1, first half. Target: 3–4 days.**

> **Git:** do not run `commit`, `push`, `add`, `branch`, `merge`, `rebase` or `reset`. After each task, print a suggested commit message and stop. See `CONVENTIONS.md`.

## Goal

A running backend and frontend, a user who can register and log in, and a working image upload to Cloudinary. No AI yet.

## Prerequisites

Accounts created for Neon, Cloudinary, OpenAI, Render, Vercel. Connection strings and keys in hand.

## Out of scope for this stage

No AI calls. No tagging. No wardrobe grid. No stylist. Uploading returns a row with `status='processing'` that stays that way — that is correct for now.

---

## Tasks, in order

### 0.1 Repository skeleton
Create the monorepo structure from `01-ARCHITECTURE.md`. Add `.gitignore` covering `.env`, `.venv`, `node_modules`, `dist`, `.pytest_cache`. Add `README.md` at the root pointing at `docs/`.

### 0.2 Backend bootstrap
FastAPI app with `/health` returning `{status, db, version}`. `pydantic-settings` config reading `.env`. CORS from `CORS_ORIGINS`. Structured logging — JSON in production, human-readable in development.

`requirements.txt`: fastapi, uvicorn[standard], sqlalchemy>=2.0, alembic, psycopg[binary], pydantic>=2, pydantic-settings, email-validator, PyJWT, bcrypt, python-multipart, cloudinary, httpx, openai, pytest, pytest-asyncio, ruff, mypy.

Three corrections to that list against the original plan, all made once the code met them: `passlib[bcrypt]` → `bcrypt` (`DECISIONS.md` 019, at task 0.2), `python-jose[cryptography]` → `PyJWT` (031, at 0.5), and `email-validator` added (032, at 0.5) because `EmailStr` will not import without it.

### 0.3 Database and migration 0001
SQLAlchemy `Base`, session factory, `get_db` dependency. Alembic initialised. Migration `0001_initial` creates the `citext` and `pgcrypto` extensions, the three enum types (`item_status`, `item_category`, `item_layer`), `users`, and `items` exactly as specified in `02-DATA-MODEL.md`.

Verify: `alembic upgrade head` then `alembic downgrade base` then `upgrade head` again. A migration that cannot roll back is a broken migration.

### 0.4 The closed vocabulary
`app/enums.py` with every enum from `02-DATA-MODEL.md`, the `SUBCATEGORIES` mapping, and helpers `is_valid_subcategory(category, sub)` and `validate_tag_dict(d)`.

**Do this before anything that consumes it.** Every later stage depends on this file being right.

### 0.5 Auth
`security.py` — bcrypt hashing, JWT encode/decode. `models/user.py`, the first ORM model, imported in `alembic/env.py` as `02-DATA-MODEL.md` requires. Routes `POST /auth/register`, `POST /auth/login`, `GET /auth/me`. `get_current_user` dependency raising `401` on a missing or invalid token.

This task also stands up two pieces of plumbing that no task owned and that it is the first to need: `api/v1/router.py`, the aggregate router named in `01-ARCHITECTURE.md` that every later route module registers into, and `core/errors.py`, the `{detail, code}` envelope that `CONVENTIONS.md` promises and FastAPI does not provide (`DECISIONS.md` 033). The `/api/v1` prefix lives on `api_router` rather than on `main.py`'s `include_router`, so `main.py` never names a version and adding a route module is one line in one file.

**Tests here are `security.py`'s only.** The register, login, duplicate-email, bad-password and `/auth/me` route tests belong to task 0.10, which owns the `conftest.py` and the test-database fixture they need. Do not build that fixture early.

### 0.6 Cloudinary service
`services/storage.py`:
- `validate_image(file_bytes) -> None`, raising `UnsupportedFileTypeError` or `FileTooLargeError`
- `upload_image(file_bytes, user_id) -> public_id`, which calls the validator itself
- `build_url(public_id, transform) -> str` for the four named transforms in `07-DEPLOYMENT.md`

Validate type and size **before** uploading. The original wording here said "validate MIME type", and this task could not do that as written: `upload_image(file_bytes, user_id)` carries no MIME type, and the one the browser declares is client-controlled in any case. The format is identified from the file's own bytes, and the accepted list is narrower than `image/*` — `DECISIONS.md` 045.

The validator is public and separate so that 0.7 can check all twenty files before uploading any; `upload_image` calls it again regardless, because `scripts/seed_demo.py` at 1.10 is a second entrance that never touches a route. The service raises its own exceptions rather than `ApiError`; 0.7 maps them onto `415` / `413` / `502` (`DECISIONS.md` 043, 044).

Also adds `settings.max_upload_bytes`, since a limit derived from a setting belongs on `Settings` per `CONVENTIONS.md` and 0.7 needs the same number without importing the storage module.

**Delete the asset the exercise commands create.** Verifying this task end to end means really uploading a real image under a throwaway `user_id` that will never exist in the database, so remove it from the Cloudinary Media Library afterwards. It is the first instance of the orphaned-asset problem that per-user foldering exists to make auditable (`DECISIONS.md` 047), and leaving it in place while writing down that the problem is auditable would be a poor start.

### 0.7 Upload endpoint
`POST /items/upload` — accepts 1–20 files, uploads each to Cloudinary, inserts an `items` row with a generated `short_id` and `status='processing'`, returns `202` with the rows. No background task yet.

`GET /items` and `GET /items/{id}` with basic filtering.

**Check `UploadFile.size` before `await file.read()`.** `01-ARCHITECTURE.md` claims backend memory during upload is "bounded by a 10 MB limit", and nothing enforces that claim: `validate_image` receives bytes that are already resident, so at twenty files it is a backstop on 200 MB, not a bound on it. Render's free tier will not survive a client that ignores the documented limit. The size check that actually bounds memory is the one on the `UploadFile` before it is read, against `settings.max_upload_bytes`; `validate_image` stays as the second line of defence and as the rule the seed script gets for free.

Validate every file — type and size — before uploading any of them. `04-API-SPEC.md` makes one bad file reject the whole request, so validating as you go would leave the already-uploaded assets of a failed batch orphaned in Cloudinary.

Map `storage.py`'s exceptions here: `UnsupportedFileTypeError` → `415` `unsupported_file_type`, `FileTooLargeError` → `413` `file_too_large`, `StorageError` → `502` `upload_failed`. An item belonging to another user is `404` `not_found`, never `403`.

### 0.8 Frontend bootstrap
`npx @angular/cli@22 new bijoux --routing --style=scss` — Angular 22, the current stable release. Do not use Angular 19; it reached end of life in May 2026. Standalone components and zoneless change detection are both defaults in v22, so no flags are needed for either. Tailwind installed and configured with the palette from `05-FRONTEND-SPEC.md`. Routes: `/login`, `/register`, `/wardrobe`. `authGuard`, `jwtInterceptor`. `AuthService` with signals. `assets/i18n/en.json` with the strings used so far.

Also `shared/models/enums.ts` — the hand-mirrored copy of `app/enums.py`, per `02-DATA-MODEL.md`. It lands here rather than in Stage 1 so that the filters (1.8) and the tag editor (1.9) find it already present.

### 0.9 Login and register screens
Reactive forms, validation messages, error handling, token stored in `localStorage`, redirect to `/wardrobe` on success.

### 0.10 Test scaffolding
`pytest.ini` with the `eval` marker registered. `conftest.py` with a test database fixture and a `TestClient`. Tests for register, login, duplicate email, bad password, and `/auth/me` with and without a token.

---

## Acceptance criteria

- [ ] `GET /health` returns 200 with `db: "ok"`
- [ ] Register → login → `/auth/me` works end to end from the browser
- [ ] `alembic upgrade head` and `downgrade base` both run clean
- [ ] Uploading 3 images returns `202` with 3 rows, all `status='processing'`, and 3 assets appear in Cloudinary
- [ ] Uploading a `.txt` file returns `415`; a 15 MB image returns `413`; an SVG returns `415`
- [ ] A logged-out user hitting `/wardrobe` is redirected to `/login`
- [ ] `ng version` reports Angular 22.x
- [ ] Auth tests pass

## Commit checkpoints

`chore: repo skeleton` · `feat(api): health and config` · `feat(db): initial migration` · `feat(core): closed vocabulary enums` · `feat(auth): register and login` · `feat(storage): cloudinary upload` · `feat(api): item upload endpoint` · `feat(web): app shell and auth screens`

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

**Check `UploadFile.size` before the bytes are read.** `DECISIONS.md` 008 claims backend memory during upload is "bounded by a 10 MB limit", and nothing enforces that claim: `validate_image` receives bytes that are already resident, so at twenty files it is a backstop on 200 MB, not a bound on it. Render's free tier will not survive a client that ignores the documented limit. The size check that actually bounds memory is the one on the `UploadFile` before it is read, against `settings.max_upload_bytes`; `validate_image` stays as the second line of defence and as the rule the seed script gets for free.

Two corrections to that paragraph, both made once the code met it. The sentence quoted is **008's**, not `01-ARCHITECTURE.md`'s — that document says "enforce a 10 MiB per-file limit", which task 0.6 had already corrected, and the misattribution stood here through 0.6. And the instruction originally read "before `await file.read()`", which presumes an `async` handler; this route is a synchronous `def` so that the blocking Cloudinary SDK cannot stall the event loop, and it reads through `file.file`. The substance — check the size before the bytes are in memory — is unchanged. `DECISIONS.md` 049.

Validate every file — type and size — before uploading any of them. `04-API-SPEC.md` makes one bad file reject the whole request, so validating as you go would leave the already-uploaded assets of a failed batch orphaned in Cloudinary.

Reading twenty files in full to type-check them would undo the paragraph above, so the two rules are reconciled with a twelve-byte read: `storage.SIGNATURE_BYTES` is the widest offset any accepted signature inspects, the batch is type-checked from heads and size-checked from `UploadFile.size`, and only then is any file read in full. Type before size, so 045's ordering survives the batch. `DECISIONS.md` 048.

Map `storage.py`'s exceptions here: `UnsupportedFileTypeError` → `415` `unsupported_file_type`, `FileTooLargeError` → `413` `file_too_large`, `StorageError` → `502` `upload_failed`. An item belonging to another user is `404` `not_found`, never `403`.

More than `MAX_FILES_PER_REQUEST` files is a `422` `validation_error`, not a `413` — no document specified it and no new code was invented for it (`DECISIONS.md` 048). `GET /items` implements all eleven documented query parameters rather than a subset, because an undeclared parameter is silently ignored and that is 039's failure arriving through the one door 039 does not cover (`DECISIONS.md` 051).

**Rate limiting is not built here and is not built anywhere.** `04-API-SPEC.md` specifies 100 files per hour on this endpoint and `STAGE-5` asserts on it, but no task in any stage file creates it. Out of scope for 0.7 and recorded in `04-API-SPEC.md` as an unowned gap rather than silently skipped.

**Delete the assets the exercise commands create**, for the same reason 0.6 did: verifying this task means really uploading under a throwaway account, and the successful batch leaves three assets under `bijoux/<that user's uuid>/`.

### 0.8 Frontend bootstrap
`npx @angular/cli@22 new bijoux --directory frontend --style=scss --ssr=false --zoneless --skip-git` — Angular 22, the current stable release. Do not use Angular 19; it reached end of life in May 2026. Standalone components, routing and zoneless change detection are all schematic defaults in v22 — `routing`, `standalone` and `zoneless` each default to `true` in `application/schema.json`. **`--routing` is therefore dropped from the command rather than carried forward**, because a flag that restates a default reads as though it were doing something. `--zoneless` is kept for the opposite reason: it is the one default a reader is most likely to doubt, since it was opt-in until recently. `--ssr=false` is passed because `ssr` is the only relevant option carrying an `x-prompt`, so omitting it stops the command to ask.

Three corrections to the command as it stood through task 0.7. **`--directory frontend`** is what reconciles `01-ARCHITECTURE.md`'s `frontend/` with `07-DEPLOYMENT.md`'s `dist/bijoux/browser` — the project is `bijoux`, the directory is `frontend` (`DECISIONS.md` 055). **`--skip-git`**, because this repository already exists. And **Node 24**: `@angular/cli@22.1.3` declares `node: ^22.22.3 || ^24.15.0 || >=26.0.0`, so the "Node 20+" written elsewhere in these documents was never a version this command would run on (`DECISIONS.md` 054).

Tailwind 4, installed by hand and wired the way Angular's own internal `tailwind` schematic wires it — a separate plain-CSS file listed before `styles.scss`, because Sass resolves `@import` before PostCSS ever runs (`DECISIONS.md` 056). The palette is `05-FRONTEND-SPEC.md`'s, with the accent and display face settled at this task (057).

Routes: `/login`, `/register`, `/wardrobe`, plus `''` and `**` both redirecting to `/wardrobe`. `authGuard`, `jwtInterceptor`. `AuthService` with signals, owning `localStorage` outright so that 0.9 owns only its two screens. `core/i18n/i18n.service.ts` and **`public/i18n/en.json`** — not `assets/`, which is not an asset root in a v22 scaffold and would never have been served (058).

`ng new` scaffolds the test runner: Vitest and jsdom land in `devDependencies` and `angular.json` gets a `@angular/build:unit-test` target, so `ng test` works with no extra configuration and picks up `**/*.spec.ts` automatically.

**Verifying Tailwind takes two greps, not a successful build.** A build that merely succeeds is not evidence — the first attempt at this task produced a green build, a rendering page, and no palette at all (`DECISIONS.md` 064). Both halves have to be asserted positively, because each can pass while the other fails:

```bash
rm -rf dist .angular && npx ng build
grep -c "tab-size" dist/bijoux/browser/styles-*.css          # preflight ran → 1
grep -o -- "--color-accent:[^;]*" dist/bijoux/browser/styles-*.css   # theme survived
```

The first proves `@import 'tailwindcss'` resolved and Tailwind emitted its base layer. The second proves our `@theme` block reached the output rather than being tree-shaken out of it. Grepping for the string `tailwindcss` proves nothing in either direction — that literal never survives import resolution, so it reads `0` in a perfectly working build. Match the hex in lower case; prettier rewrites `#2F4858` on save.

Also `shared/models/enums.ts` — the hand-mirrored copy of `app/enums.py`, per `02-DATA-MODEL.md`. It lands here rather than in Stage 1 so that the filters (1.8) and the tag editor (1.9) find it already present.

### 0.9 Login and register screens
Reactive forms, validation messages, error handling, redirect to `/wardrobe` on success. The token is already stored in `localStorage` — `AuthService` owns that from 0.8, and this task owns only the two screens that call it.

**This task also owns three things 0.8 deferred to it by name**, each with a decision entry rather than an omission:

- **Self-hosting Fraunces** — woff2 files, `@font-face`, a preload hint and a `font-display` choice. Until it lands every heading falls through to Georgia. `DECISIONS.md` 057.
- **Global `401` handling.** `jwtInterceptor` attaches the bearer token and does nothing else at 0.8. This task decides what a `401` on an authenticated request does — clear the token and navigate to `/login` is the expected answer — and records it. `DECISIONS.md` 060.
- **Restoring `currentUser` on reload.** After 0.8 a stored token survives a reload but `currentUser()` is `null`, so `isAuthenticated()` can be `true` with no user object. The fix is a `GET /auth/me` at bootstrap, and it belongs here because it is the same question as the `401` branch above: what to do when a stored token turns out to be bad. `DECISIONS.md` 062.

Note for whoever builds it: the interceptor skips `/auth/login` and `/auth/register` by name, **not** the `/auth/` prefix, because `GET /auth/me` is bearer-authenticated. Do not "simplify" that list into a prefix check (060).

### 0.10 Test scaffolding
`pytest.ini` with the `eval` marker registered. `conftest.py` with a test database fixture and a `TestClient`. Tests for register, login, duplicate email, bad password, and `/auth/me` with and without a token.

This task also owns the row-writing half of 0.7's coverage, which needs the database fixture it builds: that `POST /items/upload` inserts one row per file with `status='processing'`, that `short_id` is unique across a batch and retried on collision, and cross-user isolation on `GET /items` and `GET /items/{id}`. Task 0.7 shipped the half that runs unaided — the rejection paths, with `get_db` stubbed to raise on use so that "nothing reached the database" is asserted rather than assumed. `06-TESTING-STRATEGY.md` lists collision retry under unit tests; it cannot be one, because the constraint is what detects a collision.

Note on the config file: pytest 9 already reports `backend/pyproject.toml` as its `configfile`, and `DECISIONS.md` 020 put every other tool's configuration there. Register the marker under `[tool.pytest.ini_options]` in `pyproject.toml` rather than creating a separate `pytest.ini`, and correct the wording above when you do.

---

## Acceptance criteria

- [ ] `GET /health` returns 200 with `db: "ok"`
- [ ] Register → login → `/auth/me` works end to end from the browser
- [ ] `alembic upgrade head` and `downgrade base` both run clean
- [x] Uploading 3 images returns `202` with 3 rows, all `status='processing'`, and 3 assets appear in Cloudinary
- [x] Uploading a `.txt` file returns `415`; a 15 MB image returns `413`; an SVG returns `415`
- [x] A logged-out user hitting `/wardrobe` is redirected to `/login`
- [x] `ng version` reports Angular 22.x
- [ ] Auth tests pass

## Commit checkpoints

`chore: repo skeleton` · `feat(api): health and config` · `feat(db): initial migration` · `feat(core): closed vocabulary enums` · `feat(auth): register and login` · `feat(storage): cloudinary upload` · `feat(api): item upload endpoint` · `feat(web): app shell and auth screens`

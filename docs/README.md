# Bijoux — AI wardrobe

**Tag your closet, get outfit recommendations, and generate a weather-aware packing list for any trip.**

Bijoux is a web application that lets a person photograph the clothes they already own, automatically tags every garment with AI vision, and then acts as a personal stylist — recommending outfits from **their own wardrobe**, adjusted to the real weather outside, and packing a suitcase for a trip.

---

## The one-line pitch

**It packs your suitcase from your own closet.**

---

## Documentation map

Read these in order. Every document is the single source of truth for its area — if code and docs disagree, fix one of them in the same commit.

| File | Purpose |
|---|---|
| `00-PROJECT-BRIEF.md` | What we build, for whom, and explicitly what we do **not** build |
| `01-ARCHITECTURE.md` | System design, data flow, repository layout |
| `02-DATA-MODEL.md` | Database schema, enums, migrations |
| `03-AI-CONTRACTS.md` | Vision prompt, stylist prompt, JSON schemas, validation and retry |
| `04-API-SPEC.md` | Every REST endpoint |
| `05-FRONTEND-SPEC.md` | Screens, components, state management |
| `06-TESTING-STRATEGY.md` | Unit, integration, E2E, and how to test non-deterministic AI |
| `07-DEPLOYMENT.md` | Environment variables, hosting, CI |
| `AUDITS.md` | Documentation audits — what was read against what, what was fixed, what is open |
| `CONVENTIONS.md` | Coding standards and definition of done |
| `DECISIONS.md` | Architecture decision log — why things are the way they are |
| `PROGRESS.md` | Live build tracker. Update it as work completes. |
| `stages/STAGE-*.md` | The actual build order. One stage at a time. |

---

## Instructions for Claude Code

1. **Work one stage at a time.** Open the current stage file listed in `PROGRESS.md`. Do not start the next stage until the current one's acceptance criteria all pass.
2. **Respect the "Out of scope for this stage" section** in every stage file. It exists to prevent half-built features from later stages leaking into earlier ones.
3. **Never invent schema fields, enum values, or endpoints.** They are defined in `02-DATA-MODEL.md` and `04-API-SPEC.md`. If something is genuinely missing, stop and ask.
4. **After each stage**, update `PROGRESS.md` and append any non-obvious choice to `DECISIONS.md`.
5. **Commit per task, not per stage.** See `CONVENTIONS.md`.
6. If a task is ambiguous, **ask rather than guess**. A wrong assumption baked into the data model is expensive.

---

## Stack at a glance

| Layer | Technology |
|---|---|
| Frontend | Angular 22 (standalone, signals, zoneless), Tailwind CSS |
| Backend | Python 3.14, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic |
| Database | PostgreSQL 18 (Neon free tier) |
| Media | Cloudinary (upload, transforms, optional background removal) |
| AI | OpenAI `gpt-4o-mini-2024-07-18` — vision tagging **and** stylist reasoning, via Structured Outputs. Dated snapshot, pinned once in `app/core/config.py`; `DECISIONS.md` 078 |
| Weather | Open-Meteo (no API key required) |
| Testing | pytest + httpx (backend), Vitest (Angular unit), Playwright + TypeScript (E2E) |
| CI/CD | GitHub Actions → Render (API) + Vercel (web) |

---

## Quickstart

Prerequisites, environment variables, migrations, the two commands, the demo
wardrobe and both test suites are in the [root README](../README.md).

---

## Timeline

Six stages across roughly six weeks. `stages/STAGE-*.md` carry the detail.
Stage 3 is the designated cut line if time runs short — see `00-PROJECT-BRIEF.md`.

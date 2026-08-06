# Decision Log

Append-only. Every entry: what was decided, what the alternative was, and why. This file is where the "why did you build it that way?" questions get answered.

Format: `## NNN — Title` / **Decision** / **Alternative** / **Reasoning** / **Trade-off accepted**

---

## 001 — PostgreSQL, not MongoDB

**Decision:** PostgreSQL 16 with a `JSONB` column for flexible attributes.
**Alternative:** MongoDB Atlas, on the grounds that garments are polymorphic.
**Reasoning:** The garment schema is regular, not polymorphic — 13 attributes that apply to nearly everything. What is genuinely complex is the *relationships*: users to items, looks to items many-to-many, wear history. That is precisely where a relational database is strong. `JSONB` covers the flexible tail, and `pgvector` remains available for free if semantic search is ever wanted.
**Trade-off accepted:** Schema changes require migrations. This is a feature at this scale, not a cost.

## 002 — No retrieval layer, no vector database

**Decision:** The entire wardrobe is serialised into every stylist prompt.
**Alternative:** Embeddings plus a vector store, retrieving the top-k relevant items.
**Reasoning:** A realistic wardrobe is 80–150 items, roughly 4,000 tokens in compact form. It fits in one request and costs a fraction of a cent. Retrieval would add infrastructure and a failure mode to solve a problem that does not exist below ~400 items. Aggressive filtering also actively *hurts* quality — excluding "summer" items in winter blocks the summer-dress-with-boots-and-jacket combinations that make the product feel intelligent.
**Trade-off accepted:** Does not scale past ~400 items. The two-pass fallback is documented in `03-AI-CONTRACTS.md` and intentionally not built.

## 003 — `warmth` 1–5, not `season`

**Decision:** Insulation as an ordinal 1–5 property of the garment.
**Alternative:** A `season` enum.
**Reasoning:** Season is location-dependent. A Tel Aviv winter is 14°C; a Tel Aviv October is 30°C. "Winter garment" is not a stable property of a garment, but insulation is. It also maps directly onto a real temperature, which is what the weather rules compare against.
**Trade-off accepted:** Slightly less intuitive as a label. Mitigated with concrete anchors in the prompt and the UI.

## 004 — Weather rules computed in Python, not inferred by the model

**Decision:** Temperature is converted to an explicit instruction string by a pure function before the prompt is assembled.
**Alternative:** Send the raw temperature and let the model reason.
**Reasoning:** Model reasoning over raw numbers is inconsistent between calls, which is unacceptable for the feature users will judge the app on. A lookup table is deterministic, and it is unit-testable with zero AI calls — 12 assertions covering every boundary.
**Trade-off accepted:** Less nuance than a model might apply. Reliability is worth more here.

## 005 — Closed vocabulary for every attribute

**Decision:** Every descriptive field is an enum. Anything outside it fails validation.
**Alternative:** Free-text tags from the vision model.
**Reasoning:** Free text produces `light blue`, `baby blue`, `sky blue` and `pale blue` for one garment. Filtering, grouping, and stylist reasoning all degrade. A closed vocabulary makes exact matching reliable and makes invalid output detectable.
**Trade-off accepted:** Some expressiveness lost. `attributes JSONB` and `display_name` absorb the nuance that matters.

## 006 — `BackgroundTasks`, not Celery

**Decision:** FastAPI `BackgroundTasks` for asynchronous tagging.
**Alternative:** Celery with Redis.
**Reasoning:** Celery adds a broker, a worker process, more configuration, and more failure modes to handle at most 20 jobs per session. `BackgroundTasks` runs the coroutine after the response is sent, which is the entire requirement.
**Trade-off accepted:** Jobs are lost on process restart. Mitigated with a startup sweep and a manual retag endpoint.

## 007 — Polling, not WebSockets

**Decision:** The frontend polls every 2 seconds while items are processing.
**Alternative:** WebSocket push.
**Reasoning:** Polling is ~15 lines, works through every proxy, and survives Render free-tier idling. WebSockets would be correct at scale; at 20 items per session they are unjustified complexity.
**Trade-off accepted:** Up to 2 seconds of latency and some wasted requests. Both are invisible to the user.

## 008 — Uploads route through the backend

**Decision:** Browser → FastAPI → Cloudinary.
**Alternative:** Signed direct browser-to-Cloudinary upload.
**Reasoning:** Routing through the backend guarantees that every stored asset has a matching database row. Direct upload produces orphaned media whenever a client drops mid-flow.
**Trade-off accepted:** One extra network hop and backend memory during upload. Bounded by a 10 MB limit.

## 009 — Curated styling knowledge, not a web-search agent

**Decision:** Styling principles are written into the system prompt.
**Alternative:** An agent with a web-search tool fetching current trends.
**Reasoning:** Fashion queries return SEO spam and commerce pages. The agent would add seconds of latency and non-determinism in exchange for generic advice. A curated prompt is free, fast, deterministic, testable, and under our control.
**Trade-off accepted:** Not aware of this week's trends. For a wardrobe-combination tool this is close to irrelevant.

## 010 — One stylist call per trip, not one per day

**Decision:** The whole trip is a single call.
**Alternative:** One call per day.
**Reasoning:** Per-day calls are blind to each other's choices and therefore cannot reuse items. Reuse is the entire point of a packing list.
**Trade-off accepted:** A larger prompt and a longer single response. Chunk at 7-day blocks if quality degrades, carrying already-packed items forward.

## 011 — No refresh token

**Decision:** A single 7-day JWT.
**Alternative:** Short access token plus refresh token rotation.
**Reasoning:** Refresh rotation is meaningful for a production application with real session-security requirements. Here it is a day of work and a class of bugs, for a capstone with a demo account.
**Trade-off accepted:** A leaked token is valid for up to 7 days. Noted explicitly as a known limitation rather than hidden.

## 012 — English only, i18n-ready

**Decision:** English UI, all strings keyed in `en.json`, CSS logical properties throughout.
**Alternative:** Ship bilingual English/Hebrew immediately.
**Reasoning:** RTL support done properly costs several days across every component. Structuring for it from day one costs nothing and turns "add Hebrew" into a new JSON file plus `dir="rtl"`.
**Trade-off accepted:** Not usable in Hebrew at submission. Explicitly a next step rather than an omission.

## 013 — A structured form, not a chat interface

**Decision:** Outfit requests go through a form — occasion chips, date, coat override, and a free-text notes field — extended by two structured interactions: anchoring on an item, and swapping a single item in a returned look.
**Alternative:** A conversational chat with the stylist, as some competing apps offer.
**Reasoning:** Three problems with chat. It demands typing at the exact moment the user has least patience — a weekday morning; three taps take four seconds, composing a sentence takes twenty. It is untestable: every turn is free-form input, which leaves no stable assertion and would undermine the entire QA story. And it requires carrying conversation history into every call, inflating the prompt and complicating validation. The two things a user actually wants that a plain form cannot express are *build around this specific garment* and *this one piece is wrong* — and both are better served by a structured field than by a sentence.
**Trade-off accepted:** Cannot handle open-ended requests like "something that makes me look taller". The free-text `notes` field absorbs most of that at no cost, since it is passed to the model verbatim.

## 014 — Per-item swap instead of full regeneration

**Decision:** Each item in a look card carries a ↻ that replaces only that item, keeping the rest locked.
**Alternative:** A single "Try again" that regenerates the whole look.
**Reasoning:** In practice a suggested look is usually acceptable with exactly one piece wrong — most often the shoes. Full regeneration discards the parts that worked and is the most commonly reported frustration with outfit apps. Per-item swap costs one extra request field and one validation rule, reuses the same endpoint entirely, and produces an unusually clean E2E assertion: every other item must be byte-identical.
**Trade-off accepted:** One API call per swap. At the observed usage rate this is negligible, and the rate limit already caps it.

## 015 — Angular 22, with Reactive Forms rather than Signal Forms

**Decision:** Angular 22 (stable since June 2026), standalone components, signals for state, zoneless change detection, and **Reactive Forms** for all form handling.
**Alternative considered (version):** Angular 19, which was the assumed version in an earlier draft of this plan. It reached end of life on 19 May 2026 — no security patches, no browser-compatibility updates. Starting a new project on an unsupported major is indefensible, so v22 it is.
**Alternative considered (forms):** Signal Forms, which reached stable status in v22 and are positioned as the future recommended API.
**Reasoning:** Reactive Forms are mature, thoroughly documented, and already familiar. Signal Forms are stable but new, which means fewer worked examples and a real chance of losing a day to an unfamiliar API — inside a six-week schedule that is a bad trade. Nothing in this project needs what Signal Forms add.
**Trade-off accepted:** The forms layer is not on the newest API. Reactive Forms remain fully supported and are not deprecated. Worth stating plainly in the defence: the newest option is not automatically the right one on a fixed deadline.
**Knock-on effects:** Zoneless is the v22 default and requires no changes here, since state was already signal-based. Angular's default unit-test runner is now Vitest rather than Karma; `ng test` is wired into CI. Node 20+ is required.

## 016 — Project name: Bijoux

**Decision:** The project is named **Bijoux**, tagline "AI wardrobe". Repository: `bijoux-wardrobe`.
**Alternative:** `Styla`, the working title used through planning.
**Reasoning:** Styla is already in use twice in adjacent territory — a fashion app of the same name serving curated shoppable outfits and saved closets, and a German e-commerce frontend vendor trading under styla.com since 2012. For a portfolio project the risk is not legal, it is that the name returns someone else's product when searched. The wardrobe-app category is also crowded with short invented English names (Whering, Indyx, Fits, Acloset, Pureple), so a French register reads as deliberately different rather than as one more entry in the list.
**Trade-off accepted:** *Bijoux* means jewellery, not clothing, so the name does not describe the product literally, and non-French speakers may misspell it. Both are mitigated by the tagline, which carries the descriptive load and always appears with the name in the README, the repository description, and the defence slides.

## 017 — Commits are written by hand, never by the agent

**Decision:** Claude Code is prohibited from running any git command that writes to the repository. It prints a suggested commit message at the end of each task; the developer stages and commits manually. Read-only git commands remain available to the agent.
**Alternative:** Let the agent commit at the end of each task, which is faster and keeps the working tree clean automatically.
**Reasoning:** A capstone is defended, not just submitted, and "who wrote this?" is a fair question. A commit history assembled by hand is a history whose author can walk through it line by line. Manual staging also forces a review pass over every diff before it is recorded, which catches agent drift far earlier than a stage-end review does.
**Trade-off accepted:** Slower, and the working tree needs manual attention. Read-only access is explicitly preserved so the agent can still run `git diff` to inspect its own changes — without it, the rule would degrade the agent's usefulness for no gain.

## 018 — Python 3.14, not 3.12

**Decision:** The backend targets Python 3.14. `ruff` runs with `target-version = "py314"` and `mypy` with `python_version = "3.14"`.
**Alternative:** Python 3.12, as named in the original stack table.
**Reasoning:** 3.14 is the current stable release. Starting a new project on an older minor buys nothing and shortens the support window before the code is even submitted. The cost of being current surfaced immediately as a broken dependency (see 019) — which is better discovered in week one than in Stage 5.
**Trade-off accepted:** A small number of libraries lag a new minor release. `passlib` was the only casualty here and it was replaceable in fifteen lines. `docs/README.md` and `CONVENTIONS.md` were corrected to match.

## 019 — bcrypt directly, not passlib

**Decision:** `requirements.txt` pins plain `bcrypt`. `core/security.py` calls it directly and caps password length itself.
**Alternative:** `passlib[bcrypt]`, as listed in STAGE-0 task 0.2's dependency list.
**Reasoning:** passlib is broken on Python 3.14 — it imports the stdlib `crypt` module, which was removed in 3.13. Separately, bcrypt 5 raises on inputs longer than 72 bytes where earlier versions silently truncated them. Calling bcrypt directly means the truncation is an explicit, visible decision in our code rather than behaviour inherited from a wrapper that has changed twice.
**Trade-off accepted:** We lose passlib's `CryptContext` — algorithm agility and rehash-on-verify. A single-algorithm project with one password hash needs neither. Task 0.5 owns capping password length at 72 bytes and must say so in the validation error rather than truncating silently.

## 020 — Tooling configuration in backend/pyproject.toml

**Decision:** `ruff` and `mypy` configuration live in `backend/pyproject.toml`.
**Alternative:** Separate `ruff.toml` and `mypy.ini`, or no configuration at all.
**Reasoning:** The definition of done requires lint and type checks to pass, so the configuration must exist and be committed. `pyproject.toml` is the file both tools discover without a flag, which means `ruff check` and `mypy` work with no arguments locally and in CI. No stage file owns this file, which is the only reason it needs an entry here.
**Trade-off accepted:** A committed file that no stage file mentions. Note the deliberate scope limit: `files = ["app"]` means `alembic/` and `tests/` are not type-checked. Migrations are historical scripts, not application code, and type-checking them would gate the build on generated boilerplate.

## 021 — Settings is a module-level singleton with UPPER_SNAKE fields

**Decision:** `settings = Settings()` at module scope in `core/config.py`, imported directly wherever it is needed. Fields are UPPER_SNAKE and match their environment variable names exactly; values derived from them are lowercase properties (`allowed_origins`, `is_production`). Only `DATABASE_URL` and `JWT_SECRET` are required.
**Alternative:** `@lru_cache`-decorated `get_settings()` injected with `Depends`, which is the pattern in FastAPI's own documentation.
**Reasoning:** Services in this project are plain functions, not route handlers (see CONVENTIONS), so they cannot receive a dependency — they import `settings`. Injecting it would mean threading a parameter through every service signature to solve a problem we do not have. UPPER_SNAKE because `06-TESTING-STRATEGY.md` already writes `settings.USE_FAKE_AI`, and because a field named identically to its environment variable removes a translation step when debugging a deployment at 2am.
**Trade-off accepted:** Settings cannot be swapped per-request via `dependency_overrides`. Tests set environment variables or monkeypatch attributes instead — which is what they would have to do for a service function in any case.

## 022 — SQLAlchemy used synchronously

**Decision:** Synchronous engine, `Session`, and `def` route handlers. psycopg 3 in sync mode.
**Alternative:** `asyncpg` with `AsyncSession` and `async def` throughout.
**Reasoning:** The workload is bounded by OpenAI latency, not by database throughput, and FastAPI runs sync handlers in a threadpool. Async would add `asyncpg`, async test fixtures and `greenlet` to the dependency tree, and complicate the integration layer that `06-TESTING-STRATEGY.md` builds on `TestClient` and a real Postgres. The AI service functions remain `async` because they are HTTP clients — that is unrelated to the database and is not evidence for an async ORM.
**Trade-off accepted:** A sync handler occupies a threadpool worker for the duration of its database calls. At demo scale this is invisible; at high concurrency it would not be, and that is the point at which the decision should be revisited.

## 023 — Three PostgreSQL enum types, not thirteen

**Decision:** `item_status`, `item_category` and `item_layer` are native PostgreSQL enum types. `subcategory`, `fit`, `length`, `rise`, `color_primary`, `color_secondary`, `pattern` and `material` are `TEXT`.
**Alternative:** A native enum type per attribute — the literal reading of "all enum types" in STAGE-0 task 0.3, since reworded.
**Reasoning:** The closed vocabulary is enforced in `app/enums.py` and at the AI boundary, where an invalid value becomes a validation failure and a retry (`03-AI-CONTRACTS.md`). A native enum converts that same event into a `DataError` raised in the write path, after the retry opportunity has already passed — the wrong layer for the error. PostgreSQL enum types are also close to immutable: a value can be added but not removed without recreating the type and rewriting every dependent column, and the colours, patterns, materials and subcategories are exactly the lists expected to move during Stages 1 and 2. The three that are native are structural rather than descriptive: `status` is set by the application, and all three are what `idx_items_wardrobe` and the layering rules key on. `subcategory` could not be a native enum in any case, because its validity depends on the parent `category`.
**Trade-off accepted:** Nothing at the database level rejects `color_primary = 'burgundy'`. Every write path must go through `validate_tag_dict`. That is a discipline rather than a guarantee, and it is stated as a known limitation rather than hidden.

## 024 — Enum types created and dropped with op.execute

**Decision:** Migration `0001` issues `CREATE TYPE` and `DROP TYPE` through `op.execute`. The `postgresql.ENUM` objects that type the columns carry `create_type=False`.
**Alternative:** `ENUM.create(op.get_bind())` and `.drop(op.get_bind())`, the pattern in Alembic's own cookbook.
**Reasoning:** `op.get_bind()` returns `None` in offline mode, so `.create()` raises and `alembic upgrade head --sql` cannot render the migration at all. `op.execute` behaves identically online and offline. `create_type=False` is separately load-bearing: without it SQLAlchemy auto-creates the type on `create_table` but never drops it, so `downgrade base` leaves orphaned types behind and the next `upgrade head` fails with `type "item_status" already exists`.
**Trade-off accepted:** The enum values appear twice in the migration — once in the `CREATE TYPE` string, once in the `ENUM` object. This is acceptable because a migration is a historical snapshot: it is never edited once applied, so drift from `app/enums.py` is expected and is resolved by a new migration rather than by keeping this file in sync.

## 025 — Migrations are hand-written, never autogenerated

**Decision:** Every migration is written by hand from the DDL in `02-DATA-MODEL.md`. `alembic revision --autogenerate` is not part of the workflow.
**Alternative:** Define the ORM models first and autogenerate each migration from them.
**Reasoning:** The schema uses `CITEXT`, a partial index and four `CHECK` constraints. Autogenerate reproduces none of them faithfully, so a generated file would need hand-editing into the same result by a longer route. Writing from the DDL also keeps `02-DATA-MODEL.md` as the source of truth rather than quietly promoting the models to that role.
**Trade-off accepted:** Models and migrations are kept in agreement by hand. The mitigation is the constraint naming convention pinned in `app/db/base.py`: migrations spell the resulting names out literally, so a schema built by `create_all` and one built by migrations are directly comparable. One trap to know about — `target_metadata` in `alembic/env.py` stays empty until models are imported there, so anyone running `--autogenerate` before that import exists will be offered a migration that drops both tables.

## 026 — No separate index on items.short_id

**Decision:** `short_id` carries a `UNIQUE` constraint and no additional index. `CREATE INDEX idx_items_short` was removed from `02-DATA-MODEL.md` and never shipped in `0001`.
**Alternative:** Keep it, as originally specified in the data model.
**Reasoning:** A `UNIQUE` constraint in PostgreSQL is implemented as a unique btree index on the same column. A second plain index on that column is an exact duplicate — identical structure, no query it can serve that the first cannot, and both maintained on every insert and update.
**Trade-off accepted:** None. This is redundancy removed. It is recorded only because the index was specified in the data model, and without this entry its absence would read as an omission rather than a decision.

## 027 — /health returns 200 when the database is unreachable

**Decision:** `GET /health` always returns 200. `status` reports the process and is always `"ok"`; `db` reports the dependency and is `"ok"` or `"error"`.
**Alternative:** 503 when the `SELECT 1` fails.
**Reasoning:** Render recycles an instance whose health check fails, and on the free tier a recycle costs a 30–50 second cold start stacked on top of whatever the original fault was. Neon's free tier autosuspends, so a transient database failure is an ordinary event rather than an emergency. Keeping the process alive and reporting the dependency's state in the body is more useful than killing the only component still able to answer the question. The two fields also answer two different questions — if `status` mirrored `db`, one of them would be redundant.
**Trade-off accepted:** An orchestrator that reads only status codes cannot distinguish a degraded instance from a healthy one. Nothing in this deployment does that. The response shape is fixed from Stage 0 so the frontend never sees the field's type move.

## 028 — Tag validation is split across two layers

**Decision:** `app/enums.py` owns `validate_tag_dict(d) -> TagValidation`, a pure function that returns a report — the corrected `tags` dict, a tuple of `errors`, a tuple of `coerced` — and never raises, never imports, never calls anything. `app/services/vision.py` owns `validate_tags()`, which interprets that report: one retry on `errors` using `TagValidation.reason`, `TaggingError` on the second failure, and the `confidence < 0.35` comparison against `settings`. Two boundaries follow from this. The tag dict keeps the model's field name `confidence` through validation; the rename to the `items.ai_confidence` column happens at persistence in task 1.3. And vocabulary membership is tested with `value not in Vocabulary.values()`, never `value not in SomeEnum` and never by catching `ValueError` from the enum constructor. Constructing a member — `Category(category)` — is permitted only *after* a `.values()` guard has established that it cannot raise, which is what `is_valid_subcategory` does; `SUBCATEGORIES` is typed `dict[Category, …]`, so indexing it with a bare `str` is a type error even though `StrEnum` makes it work at runtime.
**Alternative:** One `validate_tags()` owning both halves, which is how the behaviour table in `03-AI-CONTRACTS.md` reads at first glance, and the boolean-returning `validate_tag_dict(d)` named in STAGE-0 task 0.4.
**Reasoning:** That table mixes a judgement ("subcategory does not belong to category") with the response to it ("retry once"). A retry is a second OpenAI call, so one function would force `enums.py` to import the vision service and through it `settings` and the OpenAI client — while `06-TESTING-STRATEGY.md` requires the vocabulary to be unit-tested with no AI and no environment at all. The report shape also serves a second caller the table never mentions: `PATCH /items/{id}` runs the same validator (`04-API-SPEC.md`) but must return `422` exactly where the vision path silently coerces. Neither a boolean nor a raised exception can express two policies over one set of rules. Keeping the key named `confidence` until persistence means the validator's input is exactly the documented model schema, with the rename in one place instead of at every call site. The membership convention is defensive: `Enum.__contains__` changed behaviour in Python 3.12 and its handling of unhashable input is version-sensitive, whereas comparing against a `list` uses `==` and cannot raise on whatever JSON arrives in a hand-crafted PATCH body.
**Trade-off accepted:** Two function names for what the documents describe as one, so a reader grepping for `validate_tags` finds only half the logic. `03-AI-CONTRACTS.md` carries a sentence naming which layer owns which column of the table, and this entry is the other half of the answer.

## 029 — `length` is one flat enum, not a per-category map

**Decision:** `Length` holds all eleven values in one vocabulary — sleeve lengths (`sleeveless`, `short_sleeve`, `long_sleeve`), top lengths (`crop`, `regular`, `longline`) and hem lengths (`mini`, `midi`, `maxi`, `ankle`, `full`). There is no `LENGTHS` mapping parallel to `SUBCATEGORIES`. `length: "maxi"` on a t-shirt validates.
**Alternative:** A per-category map, which is the treatment `subcategory` already gets for exactly the same reason.
**Reasoning:** The three axes do not collide in practice — the vision model does not offer `maxi` for a t-shirt — and `length` is advisory in the stylist prompt rather than load-bearing: nothing keys on it the way the layering rule keys on `layer`. A second category-dependent map would double the validation surface, the seed data's exposure to it, and the test matrix, to catch a class of error that has not been observed. An out-of-vocabulary `length` is coerced to null in any case, so the failure mode is a missing attribute rather than a wrong one.
**Trade-off accepted:** An impossible combination passes validation and reaches the database. Revisit if the Stage 1 golden-dataset run shows `length` errors concentrated on the wrong axis rather than spread across it.

## 030 — `PATCH /items/{id}` clears the category-dependent fields rather than demanding them

**Decision:** The route loads the item, merges the request body over it, and passes the merged dict to `validate_tag_dict`; any `errors` **or** any `coerced` entry is a `422` naming the offending field. When the body changes `category`, the route first clears the three fields whose validity depends on it — `subcategory`, `rise`, `layer` — for any of them the same request does not supply, and validates the result. The request schema sets `model_config = ConfigDict(extra="forbid")`, so an unknown key is a `422` from Pydantic before any of this runs.
**Alternative:** Require the client to send every dependent field a category change invalidates. For `bottom` → `top` that is `subcategory` **and** `rise: null`; for anything → `shoes` it is `subcategory` **and** `layer: "standalone"`.
**Reasoning:** Treating a coercion as a `422` is right when the client asked for something impossible and wrong when the *stored row* is what became impossible — and a category change is the second case. A stored `rise: "high"` and `layer: "base"` were valid until the category moved out from under them, and `validate_tag_dict` coerces both, so under the alternative even a well-formed request carrying a correct new subcategory returns `422`. The alternative also pushes the vocabulary's dependency rules into every client: the frontend would have to reimplement `_STANDALONE_CATEGORIES` in TypeScript purely to construct a legal request. Clearing does that work once, on the server, from rules that already exist. It closes a gap in the other direction too — `outerwear` → `top` with a stored `layer: "outer"` triggers no coercion at all, so the alternative would leave a stale layer in place with no error at all. On extra keys: Pydantic's default is `extra="ignore"`, which would make `PATCH {"colour_primary": "navy"}` return `200` having changed nothing — a typo that reads as success. `validate_tag_dict` cannot catch it, since it only inspects keys it knows, so the schema is the only place it can be caught.
**Trade-off accepted:** `PATCH {"category": "top"}` on a pair of jeans returns `200` having silently nulled `subcategory`, `rise` **and** `layer`. That is real data loss on a success response, and it is the sharpest edge in this decision. It is accepted because the discarded values were already wrong the moment the category moved — a `subcategory` of `jeans` under category `top`, a `rise` on a garment that has none — and because the alternative returns `422` on a request that is otherwise correct. The mitigation is entirely in the UI: the tag editor in task 1.9 clears and re-prompts for all three selects — `subcategory`, `rise` and `layer`, not `subcategory` alone — the moment the category select changes, so the user sees three empty fields before saving rather than discovering them nulled afterwards. An API client that does not do this gets no warning, which is the honest limit of this decision.

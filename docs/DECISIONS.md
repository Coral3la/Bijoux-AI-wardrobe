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

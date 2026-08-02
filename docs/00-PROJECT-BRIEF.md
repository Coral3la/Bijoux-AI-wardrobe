# 00 — Project Brief

## The problem

People stand in front of a full closet and cannot decide what to wear. The clothes are not the constraint — recall and combination are. A typical wardrobe holds 80–150 garments, and no one holds all of them in working memory at once, let alone every valid combination between them.

Existing wardrobe apps fail for one reason: **onboarding**. They ask the user to photograph and manually tag 100 items before delivering any value at all. Users quit around item eight.

## The solution

Bijoux removes manual data entry entirely. The user photographs a garment; AI vision tags it automatically into a fixed, machine-readable vocabulary. Once tagged, an AI stylist can reason over the whole wardrobe as structured data and return complete outfits — top, bottom, shoes, outerwear, accessories — chosen for the actual temperature outside and the actual occasion.

The signature feature is **trip packing**: given a destination and dates, Bijoux builds one outfit per day from the user's real clothes, using the real forecast, and returns a minimal packing list that maximises item reuse.

## Target user

Adults who own more clothes than they actively wear and dress themselves daily without help. Mobile-first: the camera is the primary input device.

## What makes this defensible as a capstone

- Non-trivial AI integration in **two different modes** — vision extraction (image → structured data) and constrained reasoning (structured data → decision).
- A real multi-constraint optimisation problem in trip packing: weather per day, occasion per day, item reuse, and outfit coherence at once.
- Asynchronous background processing with visible job state.
- A genuine testing challenge: how do you write reliable automated tests against a non-deterministic model? Answered in `06-TESTING-STRATEGY.md`.

## Success criteria

The project is successful when all of the following are demonstrably true:

1. A new user can go from empty account to their first recommended outfit in **under five minutes**.
2. Bulk-uploading 20 photos returns a fully tagged wardrobe without the user filling in a single form field.
3. Vision tagging reaches **≥ 90% accuracy on `category`** and **within ±1 on `warmth`**, measured against the golden dataset.
4. Outfit recommendations change appropriately between a 30°C day and a 12°C day, using the same wardrobe.
5. Trip packing produces one outfit per day with measurable item reuse (fewer packed items than `days × 4`).
6. Every recommended item ID exists in that user's wardrobe. **Zero hallucinated items** reach the UI.
7. The Playwright suite runs green in CI without calling the OpenAI API.

## Explicitly out of scope

These are deliberate exclusions, not oversights. If asked in the defence, the reasoning below is the answer.

| Excluded | Why |
|---|---|
| Virtual try-on / body avatar rendering | Generative image work is a project of its own. The look card (composited cut-out images) delivers most of the visual payoff for a fraction of the cost. |
| Scraping retailer catalogues | No public APIs; scrapers break constantly and add legal risk. Users photograph what they own. |
| Social feed, sharing, following | Product surface with no technical depth. |
| Native mobile apps | The web app is responsive and camera-capable. |
| Shopping / affiliate links | `missing_pieces` reports gaps as text only. No commerce. |
| Multi-user or family wardrobes | One wardrobe per account. |
| Real-time trend scraping via web-search agent | Web results for fashion queries are SEO spam. Styling knowledge lives in a curated prompt instead — deterministic, testable, and free. |

## Language

The UI ships in **English only**. All user-facing strings live in `frontend/src/assets/i18n/en.json` from day one and are referenced by key, never hard-coded. All layout uses CSS logical properties (`margin-inline-start`, not `margin-left`). Adding Hebrew later is then a new JSON file plus `dir="rtl"`, with no component rewrites.

AI responses are generated in English. The response language is a single variable in the stylist prompt.

## Timeline and the cut line

Six weeks, six stages. If the schedule slips:

- **Cut first:** Stage 3 (feedback and wear tracking). The app is complete without it.
- **Never cut:** Stage 4 (trip packing). It is the signature feature and the reason the project is memorable.
- **Never cut:** Stage 5 (testing and deployment). An undeployed, untested project reads as unfinished regardless of its features.

If Stage 3 is cut, keep only "save a look" — roughly two hours of work — and drop wear tracking and feedback.

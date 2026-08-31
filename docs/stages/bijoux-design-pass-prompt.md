# Bijoux — visual design pass

## What this is

Item (4) in the agreed post-Stage-4 order: a cross-cutting visual pass across every built screen. Accessibility is explicitly out of scope for this pass. Behaviour is out of scope too — no route changes, no signal changes, no API changes, no test additions beyond updating what breaks.

## Direction

Editorial refinement, kept quiet. Extend the current DNA (warm canvas, slate accent, Fraunces for authored chrome) with the neutral rungs and semantic colors the interface has no word for yet. The whole direction lives as extended tokens in `tailwind.css` (DR.1) and four shared components in `shared/ui/` (DR.2); the screen tasks are pure application of those.

## Rules for this pass, non-negotiable

- **One task at a time.** Orient first, no code. Then write files, run `ng build` and touched specs, print the diff over touched files (`git --no-pager diff`), print the suggested commit message, stop. Wait for "approved" or "next".
- **No git write commands.** Ever.
- **Body face stays the current system stack.** Do not add a new font. `--font-display` (Fraunces) stays reserved for headings and displayed counts.
- **CSS logical properties only** — `ms-`, `me-`, `text-start`, `inset-inline-*`, `border-inline-*`. Never `left`/`right` for layout.
- **Every user-facing string goes through an i18n key** in `frontend/public/i18n/en.json`. Do not hardcode.
- **No new tests unless a real regression is at stake.** Touched specs get updated to match the new markup; that is all.
- **No behaviour changes.** No signal renamings, no state extraction, no route rewrites, no API changes. If a template restructure would change what the screen does, stop and ask.
- **No comments unless the *why* is non-obvious** (per `CONVENTIONS.md`).
- **Coral runs `ng build`, `ng lint`, and touched specs after your diff.** You do not run any of these — per `CLAUDE.md`. Print the diff, print the commit message, stop.

## Docs to read once, at the start of DR.1

- `docs/CONVENTIONS.md` — the code-style rules
- `docs/05-FRONTEND-SPEC.md` sections *Structure*, *Navigation*, *Wardrobe*, *Stylist*, *Trips*, *Profile* — what each screen is for
- `AUDITS.md` **O-15** — the seven-component gap this pass closes four of

Do not read anything else. If you find yourself opening a stage file, stop.

---

## Task list

- **DR.1** — Foundations: extend `tailwind.css` tokens.
- **DR.2** — Shared UI kit: `button`, `chip`, `skeleton`, `empty-state` (four of the seven under O-15; the other three earn their place later).
- **DR.3** — Wardrobe visual refresh.
- **DR.4** — Stylist visual refresh.
- **DR.5** — Trips visual refresh.
- **DR.6** — Auth, Profile, Saved and Nav shell refresh.

Start with **DR.1**. Do not proceed to DR.2 until Coral says "next".

---

## DR.1 — Foundations

**File:** `frontend/src/tailwind.css` only.

Extend the existing `@theme static` block. Keep every existing project token untouched — every screen imports them by name. Add:

```css
/* colors */
--color-surface-elevated: #fdfcf9;
--color-ink-muted: #5a5a56;
--color-ink-soft: #8f8f88;
--color-line: #e8e6e0;
--color-line-strong: #d4d1c9;
--color-accent-hover: #253a48;
--color-accent-soft: #506676;
--color-accent-wash: #eef0f2;

/* radii — these override Tailwind 4's built-in --radius-sm/md/lg/xl/2xl deliberately; the resulting shift across the ~75 existing rounded-* call sites is the intended re-anchoring of the visual language, not a regression */
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 12px;
--radius-xl: 16px;
--radius-2xl: 20px;

/* elevation — same intentional override of Tailwind's built-in --shadow-sm/md/lg; the warmer, softer two-layer shape is what the pass is for */
--shadow-sm: 0 1px 2px rgba(26, 26, 26, 0.04), 0 2px 8px rgba(26, 26, 26, 0.06);
--shadow-md: 0 8px 24px rgba(26, 26, 26, 0.08);
--shadow-lg: 0 16px 40px rgba(26, 26, 26, 0.12);
```

`--color-success` and `--color-warning` are deliberately not in this task. Nothing in DR.1–DR.6 uses them; they earn their place when a caller exists (per CONVENTIONS.md's no-speculative-abstraction rule).

That is the whole task. Do not touch component files. Do not touch `styles.scss`. Do not add specs.

**Commit:** `feat(web): design tokens for the visual pass`

---

## DR.2 — Shared UI kit

**Files (all new):**
- `frontend/src/app/shared/ui/button.ts`
- `frontend/src/app/shared/ui/chip.ts`
- `frontend/src/app/shared/ui/skeleton.ts`
- `frontend/src/app/shared/ui/empty-state.ts`
- one spec per component, only smoke tests (renders, honours its inputs, click emits) — no exhaustive coverage.

Standalone Angular components, `OnPush`, `inject()`, named exports, no `any`. Every user-facing string that appears in a caller comes from the caller as an input, not hardcoded here.

### `Button`

Variants as an input: `primary | secondary | ghost | danger`. Sizes: `md | sm` (44px and 36px min height). Ships with the accessible defaults (type="button" unless overridden, focus-visible ring using accent). Content projected via `<ng-content>`. Emits `click` events natively — do not wrap.

Visual specs:
- **primary**: `bg-accent text-white hover:bg-accent-hover rounded-md`
- **secondary**: `bg-surface text-ink border border-line-strong hover:bg-surface-elevated rounded-md`
- **ghost**: `bg-transparent text-ink underline underline-offset-4 hover:text-ink-muted`
- **danger**: `bg-transparent text-danger border border-danger hover:bg-danger hover:text-white rounded-md`

### `Chip`

Inputs: `active: boolean`, `variant?: 'default' | 'accent'` (default = surface + line-strong border; accent = accent-wash + accent-soft border). 36px pill (`rounded-full h-9 px-4 text-sm font-medium`). Active state is `bg-ink text-white` (default variant) or `bg-accent text-white` (accent variant). Content projected.

### `Skeleton`

A shimmering placeholder. Inputs: `shape?: 'rect' | 'circle'` (default rect), `radius?: string` (default `rounded-lg`). Uses `animate-pulse bg-surface-elevated`. Callers set width/height with classes on the host.

### `EmptyState`

Inputs: `icon?: string` (inline SVG path `d` value only, single-path 24×24 stroke icon), `title: string`, `description?: string`. Content projected below the description (for the CTA). Layout: centered `flex flex-col gap-4 items-center text-center py-12 px-6 bg-surface-elevated border border-dashed border-line-strong rounded-xl`.

**Do not** build sheet, spinner, or toast in this task. They are three of O-15's seven and will earn their place when a second caller exists.

**Do not** apply these components to any existing screen in this task. Application is DR.3–DR.6's job.

**Verify:** `ng build`, `ng lint`, plus the four new specs.

**Commit:** `feat(web): shared UI kit — button, chip, skeleton, empty-state`

---

## DR.3 — Wardrobe visual refresh

**Files:**
- `frontend/src/app/features/wardrobe/wardrobe.page.ts`
- `frontend/src/app/features/wardrobe/weather-strip.ts`
- `frontend/src/app/features/wardrobe/wardrobe-insights.ts`
- `frontend/src/app/features/wardrobe/filter-bar.ts`
- `frontend/src/app/features/wardrobe/item-card.ts`
- `frontend/src/app/features/wardrobe/pending-strip.ts`
- `frontend/src/app/features/wardrobe/upload-sheet.ts`
- `frontend/src/app/features/wardrobe/item-detail.page.ts`
- `frontend/src/app/features/wardrobe/tag-editor.ts`
- touched specs updated for markup only

**Behaviour is unchanged.** Only markup, classes, and DR.2 component adoption.

**Header:** h1 becomes `font-display text-4xl leading-tight tracking-tight` (from `text-3xl`). Count on the right becomes `font-display text-lg text-ink-muted tabular-nums`.

**Weather strip:** wrap in `bg-surface rounded-xl p-4 shadow-sm`. No card border — 05-FRONTEND-SPEC line 650 ("Generous whitespace, no card borders — use shadow and spacing for separation") governs; the shadow carries the separation. Temperature and condition in `font-display text-2xl leading-tight` with the condition in `text-ink-muted font-normal`. City + "today" line becomes uppercase caption: `text-xs font-medium tracking-widest uppercase text-ink-soft`. The "Style me" link uses the new `Button` (primary) with an inline arrow SVG on the trailing side.

**Insights panel:** the two numbers (34 and 136) render in `font-display text-lg font-medium` inline within the sentence.

**Category chips row:** replace inline chip markup with the new `Chip` component. Active chip uses default variant.

**Filter bar:** the `[Filters ▾]` button uses the new `Button` (secondary, size sm) with an inline filter SVG on the leading side.

**Item grid:** tiles get `rounded-xl` (from whatever they had). The name below the tile is `text-xs text-ink-muted`. Processing overlay: keep the dim-photo pattern; add an uppercase "Tagging…" label positioned `inset-block-end` in `text-[10px] font-medium tracking-widest uppercase text-ink-muted`.

**Empty state:** replace the inline empty state with the new `EmptyState` component. Existing wardrobe empty-state copy and its "Add your first items" button move to slots.

**FAB:** becomes `bg-ink text-white rounded-full h-14 px-6 shadow-md`. Icon (inline SVG plus sign) on the leading side.

**Item detail page (`/wardrobe/:id`):** the back link at the top stays (it is hierarchical up-navigation, per the nav-bar comment). Layout becomes: back link, then a hero image occupying the full content width with `rounded-2xl aspect-square max-w-md mx-auto`, then the item name as `font-display text-3xl leading-tight` beneath it, then meta list (category / colours / warmth / formality / etc.) rendered as `text-sm text-ink-muted` pairs stacked with `gap-2`. Primary action row uses the new `Button` component: **Style around this** as primary, **Edit tags** as secondary, **Delete** as danger. Wrap the action row in `flex flex-wrap gap-3`. The "processing" and "failed" states keep their existing behaviour, just re-skinned to use `bg-surface-elevated rounded-xl p-4` (no card border; the surface-elevated colour is the distinction).

**Tag editor:** wrap the form in `bg-surface rounded-2xl p-5 shadow-sm`. Each dimension (category, layer, colours, formality, warmth, condition, etc.) becomes a labelled section separated by `border-block-start border-line pt-5` (first section has no border). Section label is `text-xs font-medium tracking-widest uppercase text-ink-soft`. All single-select and multi-select controls use the new `Chip` component — accent variant for multi-select dimensions (colours), default variant for single-select. Save is primary `Button`, Cancel is ghost `Button`.

**Commit:** `refactor(web): wardrobe visual refresh`

---

## DR.4 — Stylist visual refresh

**Files:**
- `frontend/src/app/features/stylist/stylist.page.ts`
- `frontend/src/app/features/stylist/look-request-form.ts`
- `frontend/src/app/features/stylist/look-card.ts`
- touched specs updated for markup only

**Behaviour is unchanged.**

**Header:** add an uppercase caption above the h1 — `text-xs font-medium tracking-widest uppercase text-ink-soft` — reading "Today · <weekday> <day> <month>" bound to today's date. h1 stays Fraunces but goes to `text-4xl leading-tight tracking-tight`. New i18n key `stylist.today` with an ICU-style date binding.

**In-flight state:** the five-tile skeleton uses the new `Skeleton` component. The status line stays as a `role="status" aria-live="polite"` line.

**Reasoning card:** wrap `reasoning` in `bg-surface-elevated rounded-xl p-4` with an uppercase label above it: `text-xs font-medium tracking-widest uppercase text-ink-soft` reading "Why this" (new i18n key `stylist.look.whyThis`). No card border — the surface-elevated colour is the distinction (05 line 650).

**Look card:** the outer element becomes `bg-surface rounded-2xl p-5 shadow-md`. The two "primary" tiles (top + bottom) are a 2-column grid with `gap-3` and each carries an uppercase caption above the item name reading the item's role (`stylist.look.role.<role>` — the key exists). The three "secondary" tiles (shoes/outerwear/accessory) are a 3-column grid with `gap-2` and each just carries the item name below in `text-xs text-ink-soft`.

**Feedback row:** the Save / thumbs-up / thumbs-down / try-again controls become uses of the new `Button` (Save is primary or secondary depending on the current spec; keep whichever variant matches the existing colour). Icons stay inline SVGs.

**Try again:** ghost button, centered.

**Commit:** `refactor(web): stylist visual refresh`

---

## DR.5 — Trips visual refresh

**Files:**
- `frontend/src/app/features/trips/trips.page.ts`
- `frontend/src/app/features/trips/trip-form.ts`
- `frontend/src/app/features/trips/trip-detail.page.ts`
- `frontend/src/app/features/trips/trip-look.ts`
- `frontend/src/app/features/trips/pack-wait.ts`
- `frontend/src/app/features/trips/packing-list.ts`
- touched specs updated for markup only

**Behaviour is unchanged.**

**Trip form (`/trips`):** header gets an uppercase caption "Plan a trip" above the h1 (`text-xs font-medium tracking-widest uppercase text-ink-soft`, new i18n key). The occasion chips inside the form use the `Chip` component with `variant="accent"` (multi-select feel).

**Pack-wait:** the four status lines render in `text-ink-muted text-sm` and the seven-code error table maps each code to `text-danger text-sm font-medium` with `role="alert"`. If the wait ever spans a real skeleton (it does not today per the code comment — keep the plain sentence).

**Trip detail:** uppercase "Trip · <N> days" caption above an h1 Fraunces destination name, subtitle date range in `font-display text-lg text-ink-muted tabular-nums`.

**Reuse sentence:** wrap in `bg-surface-elevated border-inline-start-4 border-accent rounded-md p-3 pl-4`. `text-sm text-ink leading-relaxed`.

**Day strip:** each day pill is a 68px min-width flex-column card. Inactive: `bg-surface border border-line-strong rounded-lg` with weekday label uppercase `text-[10px] tracking-widest text-ink-soft`, day number `font-display text-lg font-medium`, temperature `text-[10px] text-ink-muted`. Active: `bg-accent text-white` with the same three lines, opacity 0.8 on the labels.

**Selected day header:** `font-display text-xl font-medium` day name, with an uppercase caption below showing occasion and temperature.

**Trip look:** the tile grid inside a day mirrors the stylist look card's 2+3 layout — wrap in `bg-surface rounded-2xl p-4 shadow-sm`. The swap button ↻ becomes a `Button` (secondary, size sm) with an inline refresh SVG.

**Packing list:** wrap in `bg-surface rounded-xl overflow-hidden shadow-sm`. No card border — 05 line 650; the shadow carries it. Each row: 12px vertical padding, 14px horizontal, `border-block-end border-line` (last row has no border-block-end) — the row divider IS a line (that is edge definition inside the card, not a card border). 32px thumbnail (`rounded-md`), item name `text-sm`, reuse count on the right in `text-xs text-ink-soft tabular-nums`.

**Trip actions row:** "Repack" is `Button` (secondary), "Delete" is `Button` (danger).

**Commit:** `refactor(web): trips visual refresh`

---

## DR.6 — Auth, Profile, Saved and Nav shell refresh

**Files:**
- `frontend/src/app/features/auth/login.page.ts`
- `frontend/src/app/features/auth/register.page.ts`
- `frontend/src/app/features/profile/profile.page.ts`
- `frontend/src/app/features/looks/saved-looks.page.ts`
- `frontend/src/app/shared/ui/nav-bar.ts`
- `frontend/src/index.html` — boot state only
- touched specs updated for markup only

**Behaviour is unchanged.**

**Auth pages:** single-column, centered, `max-w-sm mx-auto py-16 px-6`. Form inputs get `bg-surface border border-line-strong rounded-md h-11 px-3 focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`. Submit is the primary `Button`. The bootstrap notice on `/login` stays; wrap it in `bg-surface-elevated rounded-md p-3 text-sm` (no card border; the surface-elevated colour is the distinction). The demo-wardrobe button becomes a `Button` (secondary).

**Profile page:** header pattern matches Stylist — uppercase caption above an h1 Fraunces. Form sections separated by `border-block-start border-line pt-6`. Save is primary `Button`.

**Saved looks page:** header pattern matches other feature pages. Empty state uses the `EmptyState` component with copy pointing at the stylist as the CTA.

**Nav bar:** the active item becomes a pill — `bg-accent-wash text-accent rounded-md font-medium` (from the current `font-medium text-accent`). Inactive items stay `text-ink-muted`. The sign-out button stays underlined ghost.

**index.html boot state:** the `.boot-mark` class stays Fraunces (it must — nothing else has loaded). The `.boot-hint` copy becomes `text-ink-muted` via the inline style (keep the color literal `#5a5a56` since the token may not have loaded yet — this is the same reasoning the existing inline block records).

**Commit:** `refactor(web): auth, profile, saved and nav shell visual refresh`

---

## After DR.6

The visual pass covers every screen the application has. Do not proceed to any Stage 5 task without Coral saying so.

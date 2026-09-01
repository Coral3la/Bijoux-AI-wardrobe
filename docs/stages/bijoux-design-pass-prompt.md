# Bijoux — visual design pass

## What this is

Item (4) in the agreed post-Stage-4 order: a cross-cutting visual pass across every built screen. Accessibility is explicitly out of scope for this pass. Behaviour is out of scope too — no route changes, no signal changes, no API changes, no test additions beyond updating what breaks.

## Direction

Editorial refinement, kept quiet. Extend the current DNA (warm canvas, slate accent, Fraunces for authored chrome) with the neutral rungs and semantic colors the interface has no word for yet. The whole direction lives as extended tokens in `tailwind.css` (DR.1) and four shared components in `shared/ui/` (DR.2); the screen tasks are pure application of those.

## Rules for this pass, non-negotiable

- **One task at a time.** Orient first, no code. Then write files, run `ng build` and touched specs, print the diff over touched files (`git --no-pager diff`), print the suggested commit message, stop. Wait for "approved" or "next".
- **No git write commands.** Ever.
- **Body face stays the current system stack.** Do not add a new font. `--font-display` (Fraunces) stays reserved for headings and displayed counts.
- **CSS logical properties only** — `ms-`, `me-`, `text-start`, `inset-inline-*`, `border-inline-*`. Never `left`/`right` for layout. Note the utility names: Tailwind 4 spells the logical block borders **`border-bs`** and **`border-be`** — `border-block-start` is a CSS property name, not a class, and silently renders nothing.
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
- `frontend/src/app/shared/ui/button.ts` — attribute directive, selector `[appButton]`
- `frontend/src/app/shared/ui/chip.ts` — attribute directive, selector `[appChip]`
- `frontend/src/app/shared/ui/skeleton.ts` — standalone component, selector `app-skeleton`
- `frontend/src/app/shared/ui/empty-state.ts` — standalone component, selector `app-empty-state`
- one spec per file, only smoke tests (renders / honours its inputs / for Button, the caller's click reaches through). No exhaustive coverage.

All `OnPush`, `inject()`, named exports, no `any`. Every user-facing string that appears in a caller comes from the caller as content or an input, not hardcoded here.

**Why directives for Button and Chip and components for Skeleton and EmptyState.** Button and Chip decorate an already-interactive native element — `<button>` or `<a>` — that ships with focus, keyboard, `type`, `disabled` and every aria attribute a caller will need. A wrapper component (`<app-button>` + `<ng-content>`) reinvents that surface as a list of passthrough inputs and gets it wrong quietly. As directives they cost the caller one attribute, leave the native element alone, and let `<a appButton>` and `<button appButton>` share the same visual without a new element. Skeleton and EmptyState are the opposite — nothing exists to decorate, they *are* the element — so they stay components.

### `Button` (directive)

Selector: `[appButton]`. Inputs: `variant: 'primary' | 'secondary' | 'ghost' | 'danger'` (default `'primary'`). No `size` input — every button is `min-h-11` (44px floor per 05-FRONTEND-SPEC line 652). Compact-feeling buttons come from the ghost variant or from caller-added padding, not from a shorter height.

Applies its variant as host classes; leaves `type`, `disabled`, `aria-*` and click semantics to the native element. Shared base host classes: `min-h-11 inline-flex items-center justify-center rounded-md px-5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`.

Variant classes on top of the base:
- **primary**: `bg-accent text-surface hover:bg-accent-hover`
- **secondary**: `bg-surface text-ink border border-line-strong hover:bg-surface-elevated`
- **ghost**: `bg-transparent text-ink underline underline-offset-4 hover:text-ink-muted`
- **danger**: `bg-transparent text-danger border border-danger hover:bg-danger hover:text-surface`

### `Chip` (directive)

Selector: `[appChip]`. Inputs: `active: boolean` (default `false`), `variant: 'default' | 'accent'` (default `'default'`). Applies its variant + active state as host classes AND — this is the honest a11y move — sets `[attr.aria-pressed]` from `active()` as a host binding, so a caller who styles a toggle cannot forget to announce one. Callers pass their content between the tags of their own `<button>`.

Shared base host classes: `min-h-11 inline-flex items-center rounded-full px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`.

Variant × active matrix:
- **default, inactive**: `bg-surface text-ink border border-line-strong`
- **default, active**: `bg-ink text-surface`
- **accent, inactive**: `bg-surface text-ink-muted border border-line`
- **accent, active**: `bg-accent-wash text-accent border border-accent-soft`

### `Skeleton` (component)

Selector: `app-skeleton`. A shimmering placeholder. Inputs: `shape?: 'rect' | 'circle'` (default `'rect'`), `radius?: string` (default `'rounded-lg'`; ignored when `shape === 'circle'`, which wins). Host classes: `block animate-pulse bg-surface-elevated` (the `block` matters — a custom element is inline by default, so caller-added `h-24 w-full` wouldn't bite without it). Host attribute: `aria-hidden="true"` — a pulsing empty box has nothing to announce, and callers that need a wait announcement keep their existing `role="status" aria-live="polite"` line beside the skeleton.

### `EmptyState` (component)

Selector: `app-empty-state`. Inputs: `icon?: string` (inline SVG path `d` value only, single-path 24×24 stroke icon; bound as `<path [attr.d]="icon()">`, an attribute binding — no sanitiser question), `title: string`, `description?: string`. Content projected below the description (for the CTA). Title renders as `<h2 class="font-display text-2xl leading-tight">`. Layout: `flex flex-col gap-4 items-center text-center py-12 px-6 bg-surface-elevated border border-dashed border-line-strong rounded-xl`. (The dashed border stays — it is a placeholder-signal border, not a card border; 05 line 650 governs cards.)

### Spec smoke tests, per file

Each of the four specs has three assertions. For directives: renders, applies its variant classes to the host, and — the one load-bearing spec assertion in DR.2 — **a caller-supplied class on the same element survives beside the directive's own** (a template class binding wins per Angular's styling precedence; every screen in DR.3–DR.6 leans on this, and the alternative to testing it is discovering it silently in a later task). For components: renders, honours its inputs, projected content appears.

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

**Weather strip:** wrap in `bg-surface rounded-xl p-4 shadow-sm`. No card border — 05-FRONTEND-SPEC line 650 ("Generous whitespace, no card borders — use shadow and spacing for separation") governs; the shadow carries the separation.

**This needs the existing `wardrobe.weather.line` split into two keys, and the split is required rather than cosmetic.** That key is `'{{temp}}°C · {{condition}} in {{city}}'` — one interpolated sentence in one text node, so no fragment of it can be styled, and giving the whole sentence `font-display` would put a geocoded city name in Fraunces. `05` line 646 names this strip as one of four surfaces that must use the body face, and `weather-strip.ts` carries that comment citing `DECISIONS.md` 071. Replace it with:

- `wardrobe.weather.reading` → `'{{temp}}°C · {{condition}}'`, rendered `font-display text-2xl leading-tight` as **one text node**. Project-authored words only: a rounded number and a `vocabulary.condition.*` term. The condition is not muted separately — that would need the sentence broken into fragments, which is the thing this split exists to avoid.
- `wardrobe.weather.place` → `'{{city}} · today'`, rendered as an uppercase caption in the **body face**: `text-xs font-medium tracking-widest uppercase text-ink-soft`. User data never reaches Fraunces.

The "Style me" link uses the new `[appButton]` directive with `variant="primary"` and an inline arrow SVG on the trailing side.

**Insights panel:** the **whole count line** renders `font-display text-lg` as one text node. The two numbers are not emphasised individually: `wardrobe.insights.neverWorn.*` is a single key, and picking out the numerals inside it would mean either fragmenting the sentence — which destroys the word order a Hebrew translation needs, the whole reason the i18n layer exists — or pushing markup through `innerHTML`. The count line carries no user data, so Fraunces is legal on all of it (071). The most-worn line beneath it **stays in the body face**: it interpolates `{{name}}`.

**Category chips row:** apply the new `[appChip]` directive to the existing chip `<button>` elements. Active chip uses default variant. **Remove `filter-bar.ts`'s inline `[attr.aria-pressed]` bindings on those chips** — a template binding wins over a directive host binding, so leaving both would let them diverge silently. The Chip directive now owns that announcement. The colour swatches in the same file are **not** chips under this plan — they stay swatches with their existing markup.

**Filter bar:** the `[Filters ▾]` button uses the new `[appButton]` directive with `variant="secondary"` and an inline filter SVG on the leading side.

**Item grid:** tiles get `rounded-xl` (from whatever they had). **No caption below the tile** — `item-card` renders the photograph and its overlays and nothing else. 05's mockup drew a name there; no task ever built one, and adding it now would print `wardrobe.item.untagged` ("Wardrobe item, not tagged yet") under every processing tile. Processing overlay: keep the dim-photo pattern; add an uppercase "Tagging…" label positioned `inset-block-end` in `text-[10px] font-medium tracking-widest uppercase text-ink-muted`.

**Empty state:** replace the inline empty state with the new `app-empty-state`. Existing wardrobe empty-state copy and its "Add your first items" button move to inputs and projected content. Note the visual shift: the wardrobe empty's current `<h2 class="font-display text-2xl">` becomes EmptyState's own `font-display text-2xl leading-tight` (essentially the same). The saved-looks empty state (DR.6) will pick up the same treatment — this is deliberate, empty states get one identity.

**No-match state:** the wardrobe's no-match branch (filter yields zero results) also converts to `app-empty-state`, with its own copy and a "Clear filters" ghost `[appButton]` as its projected CTA. The rule from `DECISIONS.md` 111 holds — a wardrobe with items in it and nothing visible must **not** offer the empty wardrobe's "Add your first items" call to action, so its inputs and slot content are different from the empty-wardrobe case.

**FAB:** becomes `bg-ink text-surface rounded-full h-14 px-6 shadow-md`. Icon (inline SVG plus sign) on the leading side.

**Upload sheet:** apply `[appButton]` to the two picker controls — `variant="primary"` on the camera path, `variant="ghost"` on the gallery path — and **keep their existing `focus-within:outline-*` classes**. Those controls are `<label>` elements wrapping an `sr-only` `<input type="file">`, so focus lands on the input and never on the label: the directive's own `focus-visible` ring cannot fire there, and the caller's `focus-within` ring is what makes them keyboard-visible. This is exactly the composition DR.2's class-merge test guards — the directive contributes its base and variant classes, the label's own classes survive beside them. Cancel becomes a ghost `[appButton]`.

**Item detail page (`/wardrobe/:id`):** the back link at the top stays (it is hierarchical up-navigation, per the nav-bar comment). Layout becomes: back link, then a hero image occupying the full content width with `rounded-2xl aspect-square max-w-md mx-auto`, then the item name beneath it.

**The name takes `text-3xl leading-tight` in the body face — not `font-display`.** `display_name` is user-entered and may be non-Latin; `05` line 646 names item detail as one of the four surfaces that must apply the body-face rule deliberately, and `item-detail.page.ts` carries that comment citing `DECISIONS.md` 071. An earlier draft of this plan specified Fraunces here and was wrong: a stated floor outranks a plan bullet.

**No meta list.** An earlier draft asked for category / colours / warmth / formality as `text-sm text-ink-muted` pairs. Those values are already on screen — the tag editor is always open, which `05` §4 settled ("there is nothing else on the screen to be behind"), so a read-only list above it would print every value twice.

**Action row** is `flex flex-wrap gap-3` holding **Retag** as a secondary `[appButton]` and **Delete** as a danger `[appButton]`. There is no **Edit tags** control to make secondary — same `05` §4 decision — and **Style around this** stays where `05` §4 puts it, directly under the photograph as a primary `[appButton]`, because that section forbids burying it behind the edit and delete actions. Retag's two-step `409` conflict panel and Delete's arm-on-first-press keep their behaviour exactly.

The "processing" and "failed" states keep their existing behaviour, just re-skinned to use `bg-surface-elevated rounded-xl p-4` (no card border; the surface-elevated colour is the distinction).

**Tag editor:** wrap the form in `bg-surface rounded-2xl p-5 shadow-sm`.

**Four group sections, not one per dimension.** An earlier draft asked for a labelled section per dimension; there are ten of them in a two-column grid, and ten bordered sections roughly doubles the form's height on a phone while demoting each control's `<label>` to a section heading. Keep the existing two-column grid and apply the section pattern at group level:

| section | key | fields |
| --- | --- | --- |
| Garment | `tagEditor.section.garment` | category, subcategory, layer |
| Colour & pattern | `tagEditor.section.colourAndPattern` | color_primary, color_secondary, pattern, material |
| Fit & scale | `tagEditor.section.fitAndScale` | fit, length, rise, formality, warmth, water_resistant |
| Name | `tagEditor.section.name` | display_name |

Sections are separated by `border-bs border-line pt-5` (the first has no border). Section label is `text-xs font-medium tracking-widest uppercase text-ink-soft`.

**Keep the ten native `<select>` elements as selects** — a select-to-chip-group conversion is a real UX change (native OS picker, keyboard, screen-reader semantics all shift) and belongs in its own task, not a visual pass. Re-skin the selects, and the `display_name` text input with them: `bg-surface border border-line-strong rounded-md min-h-11 px-3 text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`.

Save is a primary `[appButton]`. **There is no Cancel button** — the editor is always open, so there is nothing to cancel back to, and inventing one would be new behaviour rather than a re-skin.

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

**Look card:** the outer element becomes `bg-surface rounded-2xl p-5 shadow-md`.

**The card keeps the layer grouping it was built with.** An earlier draft of this plan asked for two "primary" tiles (top + bottom) above three "secondary" ones, each captioned with the item's role from `stylist.look.role.<role>`, and it was wrong three times over. `look-card.ts` does not lay tiles out by role: `groups()` sorts by layer then category, cuts the sorted run into one `<section>` per layer, and heads each with the shared vocabulary — an order `look-card.spec.ts` asserts across the whole card, because that order is the point of the sort. Slotting by role instead would delete that computed and the two tests that hold it, which is a restructure and not a re-skin. `stylist.look.role.<role>` does not exist either — `en.json` carries no role key of any kind. And five fixed slots have nowhere to put a **bag**, which `05`'s own mockup draws, nor a **dress**, which `roleOf` gives no role on purpose (`AUDITS.md` O-25); a look is three to six items, not five.

The visual half is all DR.4 takes: the per-layer `<h3>` becomes the uppercase caption (`text-xs font-medium tracking-widest uppercase text-ink-soft`), and the tiles stay in the three-column grid they are already in.

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
- `frontend/src/app/features/trips/packing-list.ts`
- touched specs updated for markup only

**Behaviour is unchanged.**

**Trip form (`/trips`):** header gets an uppercase caption "Plan a trip" above the h1 (`text-xs font-medium tracking-widest uppercase text-ink-soft`, new i18n key). The occasion chips inside the form use the `Chip` directive with the **default** variant. An earlier draft said `variant="accent"` "(multi-select feel)"; nothing here is multi-select — there is one row per day and one occasion chosen on each, which is the stylist's occasion row exactly, and DR.4 gave that the default variant. Two identical controls one screen apart do not get two looks.

**The wait and its errors — in `pack-wait.ts`'s two callers, not in `pack-wait.ts`.** That file has no template: it is `packErrorKey()` and `packStatus()`, a pure module both screens import (`DECISIONS.md` 207), so it has left this task's file list. The four status lines go to `text-ink-muted text-sm` in `trips.page.ts` and `trip-detail.page.ts`; the seven-code error table already renders `text-danger text-sm font-medium` with `role="alert"` on every path, so that half of this bullet was true before the pass began. The wait keeps its plain sentence and gains no skeleton.

**Trip detail:** uppercase "Trip · <N> days" caption above the h1, subtitle date range in `font-display text-lg text-ink-muted tabular-nums`.

**The destination h1 stays in the body face.** An earlier draft of this plan asked for Fraunces and was wrong for item detail's reason one screen over: the destination is a place name off the geocoder, Fraunces is latin-subset, and `DECISIONS.md` 071 names this screen among the four that must apply the body-face rule deliberately. `trip-detail.page.ts` carries that comment and `trip-detail.page.spec.ts` asserts the absent class outright — `expect(element().querySelector('h1')!.className).not.toContain('font-display')`. A stated floor outranks a plan bullet; a stated floor with a test under it is not a discussion.

The caption is pluralised (`trip.view.caption.one` / `.other`): a one-day trip is legal, and one interpolated key would ship "Trip · 1 days".

**The reuse sentence is not touched.** An earlier draft asked to wrap it in a left-bordered callout. It is not an element: `trip.view.reuse` is interpolated *into* `headerLine()` through `trip.view.headerLine` — one string in one `<p>` — and `DECISIONS.md` 206 made it one deliberately, because "a sentence split across two ends of one screen is worse than either placement". Boxing the reuse half means splitting that computed back apart; boxing the whole counts-and-reuse line calls attention to both halves, which is not what a callout is for. (The draft's `border-inline-start-4` was not a class either — Tailwind 4 spells it `border-s-4` — and the `pl-4` beside it was physical, against this pass's own rules. Both die with the bullet.)

**Day strip:** each day pill is a 68px min-width flex-column card. Inactive: `bg-surface border border-line-strong rounded-lg`; active: `bg-accent text-surface`, with the detail lines at opacity 0.8.

**Four lines, and none of them is a weekday.** An earlier draft asked for weekday / day number / temperature. There is no weekday anywhere on this screen and there cannot be one: `DECISIONS.md` 206 refused a date formatter, and `day.date` is the ISO string the server sent. The draft also had no slot for the condition glyph, which is the strip's only weather signal and is `aria-hidden` decoration paired with an `sr-only` condition name. The pill keeps what it has: "Day N" in `font-display text-lg font-medium` (project-authored, so 071 permits the display face), the ISO date in `text-[10px] tabular-nums`, the glyph at `text-lg`, and the temperature in `text-[10px] tabular-nums`.

**There is no selected-day header.** An earlier draft asked for a `font-display text-xl` day name over an occasion-and-temperature caption. Nothing like it exists to re-skin, and every fact in it is already on screen twice — the selected pill carries the day, the date and the temperature, and the look's own h2 sits directly beneath. A heading between them adds a line and no information.

**Trip look:** wrap in `bg-surface rounded-2xl p-4 shadow-sm`.

**The tile grid mirrors nothing and is not restructured.** Two earlier drafts said this grid mirrors the stylist look card — first its "2+3 layout", then, after DR.4, its "layer-grouped layout". Both were wrong, and the second was written without opening the file. `trip-look.ts` arranges `look().items` in `look_items.position` order — the order the model chose — in the four-column grid task 4.6 shipped, and its own header comment says that is not this pass's to change (`DECISIONS.md` 210).

**The ↻ badge stays hand-rolled.** An earlier draft made it `<button appButton variant="secondary">` with `px-3`. The badge is a corner overlay — `absolute end-0 top-0 min-h-11 min-w-11 rounded-full bg-surface/90` — and three of those fight the directive on the same CSS properties: `rounded-full` against its `rounded-md`, `px-3` against its `px-5`, `bg-surface/90` against its `bg-surface`. Same-property conflicts are decided by stylesheet order, not by attribute order, which is not the additive composition DR.2's class-merge test guards. The badge is not a button in a row and does not want a button-in-a-row's shape.

**Packing list:** wrap in `bg-surface rounded-xl overflow-hidden shadow-sm`. No card border — 05 line 650; the shadow carries it. Each row: 12px vertical padding, 14px horizontal, `border-be border-line` (last row has no border-be) — the row divider IS a line (that is edge definition inside the card, not a card border). Rows keep the checkbox and the name they have.

**No thumbnails and no reuse counts.** An earlier draft asked for a 32px thumbnail and a per-row reuse count. The thumbnails would be the third rendering of the same photographs on one screen — `trip-look.ts` puts them on tiles directly above. The reuse count does not exist: `packing-list.ts` receives `[items]` and nothing else, so it is a new input plus arithmetic in `trip-detail.page.ts`, which is a feature and not a re-skin. The group heading takes the pass's section-label treatment (`text-xs font-medium tracking-widest uppercase text-ink-soft`) rather than staying `text-sm font-medium`, so the card reads as one thing.

**Trip actions row:** "Repack" is `Button` (secondary). "Delete" binds its variant — `[variant]="armed() ? 'danger' : 'secondary'"` — rather than taking a fixed `danger`: the delete arms on the first press and fires on the second (`DECISIONS.md` 207, 126), and the colour change *is* the visible half of that gate. A permanently red delete makes the two presses look identical. The variant replaces the `[class.text-danger]` and `[class.font-medium]` bindings it had, so one owner paints the armed state.

The row's `border-t border-current/10` becomes `border-bs border-line`.

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

**Profile page:** header pattern matches Stylist — uppercase caption above an h1 Fraunces. Form sections separated by `border-bs border-line pt-6`. Save is primary `Button`.

**Saved looks page:** header pattern matches other feature pages. Empty state uses the `EmptyState` component with copy pointing at the stylist as the CTA.

**Nav bar:** the active item becomes a pill — `bg-accent-wash text-accent rounded-md font-medium` (from the current `font-medium text-accent`). Inactive items stay `text-ink-muted`. The sign-out button stays underlined ghost.

**index.html boot state:** the `.boot-mark` class stays Fraunces (it must — nothing else has loaded). The `.boot-hint` copy becomes `text-ink-muted` via the inline style (keep the color literal `#5a5a56` since the token may not have loaded yet — this is the same reasoning the existing inline block records).

**Commit:** `refactor(web): auth, profile, saved and nav shell visual refresh`

---

## After DR.6

The visual pass covers every screen the application has. Do not proceed to any Stage 5 task without Coral saying so.

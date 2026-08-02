# 05 — Frontend Specification

Angular 22, standalone components, signals for state, Tailwind CSS.
Mobile-first: design every screen at 390px wide first, then widen.

**Version notes.** Angular 22 is the current stable release; Angular 19 reached end of life in May 2026 and must not be used. Two consequences for this project:

- **Zoneless change detection is the default.** New projects ship without Zone.js. Nothing in this spec depends on Zone.js, so no adjustment is needed — signals were already the state model.
- **Reactive Forms, not Signal Forms.** Signal Forms became stable in v22, but this project uses Reactive Forms throughout. See decision 015.

Angular 22 also introduces selectorless components (importing a component directly into a template without a selector string). Use it or not — it changes nothing structurally, and mixing both styles is fine.

---

## Structure

```
src/app/
├── core/
│   ├── auth/            auth.service.ts (signals), auth.guard.ts, jwt.interceptor.ts
│   ├── api/             items.api.ts, looks.api.ts, trips.api.ts, weather.api.ts, me.api.ts
│   └── state/           wardrobe.store.ts, user.store.ts
├── features/
│   ├── auth/            login.page.ts, register.page.ts
│   ├── wardrobe/        wardrobe.page.ts, upload-sheet.ts, item-card.ts,
│   │                    item-detail.page.ts, tag-editor.ts, filter-bar.ts
│   ├── stylist/         stylist.page.ts, look-request-form.ts, look-card.ts
│   ├── trips/           trips.page.ts, trip-form.ts, packing-view.ts, day-strip.ts
│   └── profile/         profile.page.ts
├── shared/
│   ├── ui/              button, chip, sheet, skeleton, empty-state, spinner, toast
│   ├── models/          item.model.ts, look.model.ts, trip.model.ts, enums.ts
│   └── pipes/           cloudinary-url.pipe.ts, enum-label.pipe.ts
└── assets/i18n/en.json
```

---

## State management

Signals only. No NgRx — the state here is three collections and a user object, and NgRx would be more ceremony than the problem deserves. With zoneless change detection as the v22 default, signals are also the only state model that updates the view reliably without extra wiring.

```ts
// wardrobe.store.ts
export class WardrobeStore {
  readonly items      = signal<Item[]>([]);
  readonly filters    = signal<ItemFilters>({});
  readonly isLoading  = signal(false);

  readonly visible    = computed(() => applyFilters(this.items(), this.filters()));
  readonly processing = computed(() => this.items().filter(i => i.status === 'processing'));
  readonly byCategory = computed(() => groupBy(this.visible(), i => i.category));
  readonly isEmpty    = computed(() => this.items().length === 0);
  readonly canStyle   = computed(() =>
    this.items().filter(i => i.status === 'ready').length >= 6);
}
```

`canStyle` is used to disable the stylist entry point with a clear explanation rather than letting a request fail server-side.

---

## Screens

### 1. Auth — `/login`, `/register`

Single-column, centred. Email, password, display name on register. Nothing else. This screen must not consume design time.

### 2. Wardrobe — `/wardrobe` *(default route once authenticated)*

The home screen and the most-used surface.

```
┌────────────────────────────────┐
│ Wardrobe            138 items  │
│ 🌤 18°C Tel Aviv               │  ← weather strip, tappable → stylist
├────────────────────────────────┤
│ [All][Tops][Bottoms][Shoes]…   │  ← horizontal scroll, category chips
│ [Filters ▾]              [⌗]   │  ← filter sheet + grid/list toggle
├────────────────────────────────┤
│  ┌────┐ ┌────┐ ┌────┐          │
│  │img │ │img │ │▓▓▓▓│          │  ← 3-col mobile, 5-col desktop
│  └────┘ └────┘ └────┘             ▓▓▓▓ = skeleton, status processing
│  ┌────┐ ┌────┐ ┌────┐          │
│  │img │ │ ⚠ │ │img │          │  ← ⚠ = failed, tap to retry
│  └────┘ └────┘ └────┘          │
├────────────────────────────────┤
│         [ + Add items ]        │  ← FAB, bottom-right on mobile
└────────────────────────────────┘
```

**Empty state is important.** A first-time user sees: a one-line explanation, a large **Add your first items** button, and a secondary **Try a demo wardrobe** link that loads the seeded 40-item account. Do not ship a blank grid.

**Filter sheet:** category, colour swatches, formality range, warmth range, "never worn" toggle *(Stage 3)*. Filters are client-side over the loaded collection — the whole wardrobe fits in memory.

### 3. Upload sheet — bottom sheet over the wardrobe

Two buttons, both leading to the same pipeline:

```html
<!-- opens the camera directly on mobile -->
<input type="file" accept="image/*" capture="environment" (change)="onFiles($event)">

<!-- multi-select from the gallery -->
<input type="file" accept="image/*" multiple (change)="onFiles($event)">
```

- **Take a photo** — for adding items one at a time. After each upload the sheet stays open so the user can shoot the next garment without navigating.
- **Choose from gallery** — up to 20 at once. This is the wardrobe-filling path.

A one-line tip sits above the buttons: *"Best results: lay the item flat or hang it against a plain wall."*

On selection: show local previews immediately from `URL.createObjectURL`, POST the files, then replace the previews with the returned rows. The user should never see an empty screen while uploading.

### 4. Item detail — `/wardrobe/:id`

Large image, all tags shown as chips. **Edit tags** opens `tag-editor`, where every field is a select bound to the closed vocabulary — never a free-text input. Also: wear count and last worn *(Stage 3)*, retag, delete.

**Primary action on this screen: "Style around this."** It navigates to the stylist with `anchor_item_id` pre-set and the item shown pinned at the top of the form. This is the shortest path from *I am looking at this garment* to *here is what goes with it*, and it is the original problem the product exists to solve — do not bury it behind the edit and delete actions.

The tag editor is not optional polish. Vision tagging is wrong on roughly 10–20% of items, and this screen is both the fix and the answer to "what happens when the AI is wrong?"

### 5. Stylist — `/stylist`

```
┌────────────────────────────────┐
│  What's the occasion?          │
│  [Casual][Work][Evening][Sport]│
│                                │
│  When?     [Today ▾]           │
│  Coat?     [Auto][Yes][No]     │
│  Notes     [_________________] │
│                                │
│  🌤 18°C · light rain later    │
│                                │
│        [ Style me ]            │
└────────────────────────────────┘
```

When arriving with an anchor, the item appears pinned above the form: *"Building around: light blue mom jeans"*, with an × to clear it.

Submitting swaps the form for a look card. Expect 4–8 seconds — show a skeleton of the look card itself, not a spinner, and cycle two or three short status lines ("Reading the forecast…", "Going through your wardrobe…").

### 6. Look card — the visual payoff

```
┌────────────────────────────────┐
│  Morning meetings              │
│  ┌──────┐  ┌──────┐            │
│  │ top  │  │ outer│            │  cut-out images on a neutral card
│  └──────┘  └──────┘            │
│  ┌──────┐  ┌──────┐  ┌──────┐  │
│  │bottom│  │shoes │  │ bag  │  │
│  └──────┘  └──────┘  └──────┘  │
│                                │
│  "The high-rise jean balances  │  ← reasoning
│   the oversized shirt…"        │
│  🌤 18°C — the blazer is enough│  ← weather_note
│                                │
│  [♡ Save]  [👍]  [👎]  [↻ Again]│  ← feedback is Stage 3
└────────────────────────────────┘
```

Items are laid out by `layer` and `category`, not in an arbitrary order. Tapping an item opens its detail page.

**Each item also carries a small ↻ badge.** Tapping it re-requests the same look with every other item locked and only that role replaced, adding the rejected item to `exclude_item_ids`. Show a spinner on that tile alone; the rest of the card stays put.

This matters more than it looks. Most of the time a suggested look is fine and exactly one piece is wrong — usually the shoes. "Try again" rerolls everything and loses the good parts, which is the single most common frustration with outfit apps. Per-item swap is cheap to build on top of the same endpoint and none of the competing apps offer it.

If `missing_pieces` is non-empty, render a muted note beneath: *"A neutral closed shoe would complete this."*

### 7. Trips — `/trips` *(Stage 4)*

**Form:** destination (autocomplete via `/me/locations/search`), date range, then one occasion chip row per day, defaulting to `casual`.

**Result — packing view:**

```
┌────────────────────────────────┐
│  Berlin · 14–17 March          │
│  8 items · 4 looks             │
├────────────────────────────────┤
│ [Day 1][Day 2][Day 3][Day 4]   │  ← horizontal day strip
│  12°C   14°C   17°C   15°C     │
│   🌧      ☁      ☀      ☁      │
├────────────────────────────────┤
│  (look card for selected day)  │
├────────────────────────────────┤
│  PACKING LIST                  │
│  Tops (3) ────────────────     │
│   ▢ white oversized shirt      │  ← checkable, local state only
│   ▢ black knit sweater         │
│  Bottoms (2) ─────────────     │
│   …                            │
│  "The jeans appear on 3 days"  │
└────────────────────────────────┘
```

The reuse summary is the line that makes the feature land. Show it prominently.

### 8. Profile — `/profile`

Height, sizes, style notes, home city with autocomplete. Style notes needs placeholder text that teaches by example: *"e.g. I prefer high-rise bottoms and avoid crop tops."*

---

## Polling for tagging status

```ts
// in WardrobeStore, started when processing items exist
effect(() => {
  if (this.processing().length === 0) { this.stopPolling(); return; }
  this.startPolling(); // every 2s, GET /items?status=processing
});
```

Hard stop after 3 minutes; mark anything still processing as failed in the UI and offer retry. Never poll forever.

---

## Visual direction

One decision, made once, applied everywhere: **the clothes are the design.** The interface is a neutral gallery wall.

- Background `#FAFAF8`, surfaces white, text `#1A1A1A`, one accent used sparingly.
- Cut-out garment images on white read as a catalogue. Nothing else should compete with them.
- Generous whitespace, no card borders — use shadow and spacing for separation.
- One display typeface for headings, one system stack for body.
- Every interactive element ≥ 44px tall. This is a phone app that happens to run in a browser.

---

## Internationalisation readiness

English only in this project, Hebrew afterwards. Two rules make that a JSON file rather than a rewrite:

1. **No hard-coded user-facing strings.** Everything goes through a key in `assets/i18n/en.json`.
2. **CSS logical properties only** — `margin-inline-start`, `padding-inline-end`, `text-align: start`. Never `left` or `right` for layout.

Tailwind supports the logical variants (`ms-4`, `me-2`, `text-start`). Use them from the first component.

---

## Accessibility floor

Not a full audit, but non-negotiable: every image has meaningful `alt` (use `display_name`), every icon-only button has `aria-label`, focus is visible, and the whole app is keyboard-navigable. Playwright's `getByRole` locators depend on this — good accessibility directly produces stable tests.

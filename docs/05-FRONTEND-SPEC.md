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
│   ├── i18n/            i18n.service.ts
│   └── state/           wardrobe.store.ts, user.store.ts
├── features/
│   ├── auth/            login.page.ts, register.page.ts
│   ├── wardrobe/        wardrobe.page.ts, upload-sheet.ts, item-card.ts,
│   │                    item-detail.page.ts, tag-editor.ts, filter-bar.ts
│   │                    (all built; shared/ui/ below is still empty)
│   ├── stylist/         stylist.page.ts, look-request-form.ts, look-card.ts
│   ├── trips/           trips.page.ts, trip-form.ts, packing-view.ts, day-strip.ts
│   └── profile/         profile.page.ts
├── shared/
│   ├── ui/              button, chip, sheet, skeleton, empty-state, spinner, toast
│   ├── models/          user.model.ts, item.model.ts, look.model.ts,
│   │                    trip.model.ts, enums.ts
│   └── pipes/           cloudinary-url.pipe.ts (built at 1.9), enum-label.pipe.ts

src/environments/        environment.model.ts, environment.ts,
                         environment.development.ts
public/i18n/en.json
```

Two corrections made at task 0.8. `user.model.ts` was missing — `AuthService` needs a `User` and a `TokenResponse` from its first line, and both mirror `04-API-SPEC.md`'s user object (`DECISIONS.md` 059). And the string file is at **`public/i18n/en.json`**, not `src/app/assets/i18n/en.json`: `public/` has been Angular's asset root since v18, `src/assets` does not exist in a v22 scaffold, and a file under `src/app/` is not served at runtime at all. The path this diagram drew through task 0.7 could not have been built.

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

**The sketch above is the finished shape, not the shape at any one task.** Task 1.5 ships `items`, `total`, `isLoading`, `loadError`, `isEmpty`, `processing`, `retrying` and `retagErrors`, plus `load()` and `retag()`. `filters` and `visible` arrive with the filter bar at 1.8 — **`byCategory` does not, and was corrected out of that list at 1.8 rather than built**: it groups `visible()`, the wardrobe grid is flat, and the header carries the only count on the screen, so it would be a computed with no consumer of exactly the kind this sentence refuses on 1.5's behalf (`DECISIONS.md` 112), and `canStyle` with the stylist at Stage 2 — building them at 1.5 would be four computeds with no consumer, and `canStyle` in particular is the stylist gate, which `STAGE-1` puts out of scope for the whole stage. `total` and the two retag collections are not in the sketch at all: `total` counts the filter rather than the page and is the only truthful count above 200 items (`DECISIONS.md` 094), and the retag pair is keyed by item id so a spinner and a failure land on the tile that owns them (`DECISIONS.md` 093).

---

## Screens

### 1. Auth — `/login`, `/register`

Single-column, centred. Email, password, display name on register. Nothing else. This screen must not consume design time.

Built at task 0.9. **Display name is required by the form** although the API accepts `null`, because registration is the only place in the whole application where it can be set — `PATCH /me` accepts `display_name` since task 2.2 and can clear it, and **task 2.10a builds the profile screen in §8** — scheduled there after `AUDITS.md` O-6's second half had recommended it since 2.2 without a task being written. Until it lands, nothing renders that field. This sentence read *"`PATCH /me` at Stage 2 covers only `home_city`/`home_lat`/`home_lon`"* until 2.2 widened the endpoint (`AUDITS.md` O-6, `DECISIONS.md` 149); the conclusion is unchanged and the reason for it moved from the API to the missing screen. Password rules mirror the API's on register (8 characters minimum, 72 **bytes** maximum) and are absent on login, where `LoginRequest` has none. Both forms carry `novalidate` so the browser's own bubble cannot preempt the i18n messages, and submit is disabled only while a request is in flight — never on an invalid form, which must stay submittable so the messages can appear. `DECISIONS.md` 070.

`/login` also renders the bootstrap notice: **"Please sign in again."** when a stored token was rejected, or an unreachable message with a **Try again** button when `GET /auth/me` got no answer. `/register` renders neither — a user who asked for the register form is not looking at an unexplained login screen, and the notice survives on the service if they follow the link across. `DECISIONS.md` 067.

### 2. Wardrobe — `/wardrobe` *(default route once authenticated)*

The home screen and the most-used surface.

```
┌────────────────────────────────┐
│ Wardrobe            138 items  │
│ Signed in as Coral             │
│ Profile  Saved      Sign out   │  ← account row: → /profile, → /saved
│ 🌤 18°C Tel Aviv    [Style me] │  ← weather strip, → stylist (see 2.12)
│ 34 of 136 tagged never worn    │  ← insights panel (3.6), hides itself
├────────────────────────────────┤
│ [All][Tops][Bottoms][Shoes]…   │  ← horizontal scroll, category chips
│ [Filters ▾]              [⌗]   │  ← filter sheet + grid/list toggle
├────────────────────────────────┤
│  ┌────┐ ┌────┐ ┌────┐          │
│  │img │ │img │ │▓▓▓▓│          │  ← 3-col mobile, 5-col desktop
│  └────┘ └────┘ └────┘             ▓▓▓▓ = dimmed photo, status processing
│  ┌────┐ ┌────┐ ┌────┐          │
│  │img │ │ ⚠ │ │img │          │  ← ⚠ = failed: retry, or add tags by hand
│  └────┘ └────┘ └────┘          │
├────────────────────────────────┤
│         [ + Add items ]        │  ← FAB, bottom-right on mobile
└────────────────────────────────┘
```

**Built at task 2.12, and two details of the strip above are not what this legend drew.** **The strip is not itself the tap target**: it carries a labelled **Style me** link instead, because the degraded state — no home location, so the temperature is replaced by a prompt linking to `/profile` — would otherwise put an anchor inside an anchor. The link is present in all three states (a forecast, no home city, a home city whose forecast did not arrive), which is what makes this the entry point `STAGE-2` §2.12 requires rather than a decoration that disappears with the weather. **And there is no glyph**: 🌤 above is one icon for eight conditions, and a sun printed over a line reading *Rain* is worse than no icon, so the line is temperature, condition and city in the body face (`DECISIONS.md` 071, which names this strip). `DECISIONS.md` 180.

**The account row is drawn here for the first time**, and both its links were
built before this section named either. It is one line — who is signed in, and
the three things they can do about it: **Profile** (task 2.10a), **Saved**
(added with the entry-point fix after 3.6) and **Sign out**. Both links are
anchors with `inline-flex min-h-11`, because `min-height` does not apply to an
inline element and the anchors would otherwise miss the 44px target the button
beside them keeps.

**Neither link is what `AUDITS.md` O-29 asks for.** That item wants a
navigation component in this section, and it is open: five bespoke controls
across five tasks, each invented by the task that needed it. The Saved link is
the fifth instance, shipped because Stage 3 is the designated cut line and a
saved-looks screen nobody can reach makes the whole stage invisible — not
because the debt was paid. `DECISIONS.md` 187.

**The insights panel is built at task 3.6, and it is the first screen in the application to read `GET /items/stats`.** One `<section>` between the weather strip and the pending strip: both of those are standing context about the wardrobe, where the pending strip is transient feedback that belongs beside the grid it changes. It prints how many garments have never been worn, and beneath that the most-worn garment as a link to its detail screen. It **fetches for itself**, once, on construction, and holds no store — `WeatherStrip`'s shape and `WeatherStrip`'s reasoning (`DECISIONS.md` 180): `WardrobeStore` is `providedIn: 'root'`, outlives this page and holds the collection the poll mutates, so a `ready`-scoped count kept beside `total` in it would be a second count of one wardrobe with nobody to reconcile the two.

**The number beside the count is `worn + never_worn`, never `total`.** The three wear numbers are scoped to `ready` rows and `total` counts every status, so on a wardrobe with two failed uploads a panel counting against `total` would say *of 138* about a population those two rows are not in — directly beneath a header stating that same 138 about a set of rows they are in. The line names its population instead — *"34 of your 136 tagged items have never been worn"* — and **tagged** is the word the grid already uses: a `processing` tile says *Tagging…*, a `failed` one offers to tag again. `DECISIONS.md` 186, 188.

**Three states render nothing or something softer, and all three are real.** With **nothing worn at all** the panel does not render — the only sentence available is *"you have never worn any of your 40 items"*, which the user knows and which is about the application not having been told rather than about her wardrobe. With **nothing left unworn** the count line is replaced by *"You have worn everything in your wardrobe"* rather than a zero presented as a boast. A **failed request** removes the panel silently: statistics are context on a screen that works without them, and the wardrobe around it is not disturbed. `DECISIONS.md` 188.

**Empty state is important.** A first-time user sees: a one-line explanation and a large **Add your first items** button. Do not ship a blank grid.

**Corrected at task 1.5.** This paragraph also asked for a secondary **Try a demo wardrobe** link "that loads the seeded 40-item account", and there is no mechanism for it and cannot be one here: `/wardrobe` is reachable only when authenticated, so the link means *switch to somebody else's account*, `04-API-SPEC.md` has no endpoint for that and forbids adding endpoints it does not list. The affordance is not cut — it moves to `/login` as prefilled credentials for `demo@bijoux.app`, which needs no endpoint and is honest about what it does, where a link inside your own empty wardrobe implies your wardrobe is about to fill up. That is recorded as an open item in `AUDITS.md` (**O-12**) against the task that seeds the account, 1.10. Found by the 2026-08-18 audit as O-4.

**Corrected again at task 1.10: it is a button, not prefilled credentials.** `/login` carries a **View the demo wardrobe** button that signs the visitor in with the seeded credentials and lands on `/wardrobe` — same endpoint, same JWT, one click. The sentence above described the mechanism O-12 specified, and it stopped being true when the screen was built: a value prefilled into an input carrying `autocomplete="current-password"` invites a browser to save the demo account over a visitor's own stored login, which `DECISIONS.md` 070 had made likely rather than hypothetical. **The account is shared and mutable** — every visitor is the same user — and the button carries a line saying so. `DECISIONS.md` 136; O-12 is closed as superseded.

**Filter sheet:** category, colour swatches, formality range, warmth range, "never worn" toggle *(Stage 3 — deferred, see below)*. Filters are client-side over the loaded collection — the whole wardrobe fits in memory.

**Built at task 1.8, and it is not a sheet.** It is an inline disclosure panel opened from the `[Filters ▾]` button and rendered in flow: a modal over the grid hides the thing being filtered, which is 098's own argument for why the gallery path closes the upload sheet — and a filter is the worse case, because the result changes while the control is open. No `shared/ui/sheet` was extracted; **O-15** asked the second caller to decide and the second caller does not want one. The category chip row above is the same filter as the panel's category dimension, single-valued, with `All` as its reset. Dimensions combine as **AND**; multi-select within a dimension was declined rather than deferred. The `never worn` toggle remains Stage 3's. `DECISIONS.md` 109, 113.

**And Stage 3 closed without it.** The line above assigned the toggle to a stage rather than to a task, and no task in `STAGE-3` ever named it: 3.6 built the insights panel that counts never-worn garments and did not build a filter that selects them. It is **deferred and unowned** — a candidate for Stage 5 polish, where `STAGE-5` already collects the work that belongs to no feature. Recorded here at 3.6 rather than left as a stage reference that has expired, and deliberately not assigned to a task by the agent that noticed it.

**A row whose value for a filtered field is `null` is never hidden by that field's filter**, per field rather than per row, and the predicate never reads `status`. A processing row has null tags, so a filter cannot hide an upload in progress — which is what keeps the tagging line and the grid saying the same thing — and the stopped-waiting tile stays visible for the same reason rather than by an exception. `DECISIONS.md` 109.

**Under an active filter the header states both numbers** — the matched rows against the wardrobe total, "12 of 138 items" — and it is the only count on the screen. A wardrobe with items in it and nothing visible gets its own state, with its own string and a **Clear filters** control, and never the empty wardrobe's call to action. `DECISIONS.md` 111.

**Built at task 1.5**, and three things about the grid are not what this section originally drew. **A `processing` tile keeps its photograph**, dimmed, with a "Tagging…" label — the legend above said skeleton, and the image is on the wire from the first response, so a grey block would replace a picture the user has just taken with a placeholder (`DECISIONS.md` 091). **A `failed` tile renders from `status` and never from "the tags are null"**: a retag leaves the previous attempt's values in place, so a failed item may arrive fully tagged (`DECISIONS.md` 089). **The empty state's button is inert until 1.6** wires it to the upload sheet, and the FAB drawn above is 1.6's rather than 1.5's — 1.5's acceptance line requires the one and no task requires the other (`DECISIONS.md` 090). The weather strip is 2.12's (this line said 2.2's until task 2.1; `STAGE-2` is authoritative and 2.2 is the location search), the chip row and filter panel are 1.8's, and the grid/list toggle is **nobody's** — this line assigned it to 1.8 while `STAGE-1` §1.8 named it nowhere, and 1.8 corrected that rather than building an affordance no brief asks for (090's ownership test); it stays first on the stage's cut list; the mockup above spans three stages.

That only holds if the whole wardrobe was loaded. `GET /items` defaults to `limit=100` and caps at 200, while a realistic wardrobe is 80–150 items, so the store must pass an explicit `limit` rather than take the default — otherwise the filter bar silently filters over the first hundred items and the counts are wrong with no error anywhere.

### 3. Upload sheet — bottom sheet over the wardrobe

Two buttons, both leading to the same pipeline:

```html
<!-- opens the camera directly on mobile -->
<input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
       capture="environment" (change)="onFiles($event)">

<!-- multi-select from the gallery -->
<input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
       multiple (change)="onFiles($event)">
```

`accept` was `image/*` through task 0.6. It is narrowed to match the formats the API actually accepts (`DECISIONS.md` 045) — left as `image/*`, the gallery picker offers GIFs, BMPs and SVGs that the upload endpoint answers with a `415`, which reads to the user as the app breaking rather than as the picker being wrong. `accept` is a hint the user can override, so it replaces no server-side check.

The sheet must also enforce the batch rules before it posts, because the server rejects the **whole** request for one bad file: at most `MAX_FILES_PER_REQUEST` (20) files, each at most `MAX_UPLOAD_MB` mebibytes. Mirror the arithmetic from `CONVENTIONS.md` — 1024², not 1000².

- **Take a photo** — for adding items one at a time. After each upload the sheet stays open so the user can shoot the next garment without navigating.
- **Choose from gallery** — up to 20 at once. This is the wardrobe-filling path.

A one-line tip sits above the buttons: *"Best results: lay the item flat or hang it against a plain wall."*

On selection: show local previews immediately from `URL.createObjectURL`, POST the files, then replace the previews with the returned rows. The user should never see an empty screen while uploading.

**Built at task 1.6**, and four things about it are decisions this section did not take. **The previews are a strip above the grid, not tiles inside it** — they have no `id`, no `status` and no `short_id`, so placing them in grid position would mean inventing those on the one model `DECISIONS.md` 059 says mirrors the wire field for field. The accepted cost is that for a second or two the newest garments sit above the grid rather than in it, and "replace the previews with the returned rows" is a visual swap (`DECISIONS.md` 097). **The sheet is a plain element rather than `<dialog>`**, because jsdom implements neither `showModal` nor `show` nor `close`, so a dialog-based sheet could not be opened by any test in this project — a testability constraint that changed a design decision, recorded as one (098). **The camera keeps the sheet open and the gallery closes it**: this section gives the rule for the camera only, and after a batch the user's next move is watching the rows arrive, which a sheet over the grid would hide (098). **This section specifies no error surface at all**, and the sheet needed one: failures render our own strings keyed by the response `code`, which means the filename `04-API-SPEC.md` puts inside `detail` is not shown — a `415` on one file out of twelve cannot say which (099).

The **+ Add items** FAB in §2's mockup is also 1.6's. It is not decoration: the empty state's CTA renders inside the `isEmpty()` branch and goes away after the first upload, so without it the sheet would be reachable once per account.

### 4. Item detail — `/wardrobe/:id`

**Built at task 1.9, and this section is rewritten rather than annotated** — as originally written it described a screen no task in Stage 1 could build.

The image at the `detail` transform, built from `image_public_id` through `cloudinary-url.pipe.ts`: the server sends `image_url` as a 300px padded thumbnail and nothing else, so this is the first screen in the project that cannot use it (`DECISIONS.md` 118). The name in the **body** face, per §Typography's rule — this is one of the four surfaces that renders text the project did not write.

The editor is always open rather than behind an **Edit tags** control, because there is nothing else on the screen to be behind. Ten selects bound to the closed vocabulary, `formality` and `warmth` as 1.8's range controls, `water_resistant` as a checkbox, and **`display_name` as a text input** — the stage brief's "never a free-text input" is about tags, and a name is not a tag (`DECISIONS.md` 125). Every save sends all fourteen fields; changing the category empties the five dependent fields on screen and sends them as explicit nulls (119). The category select offers a placeholder only while the row has no category, and never a way to clear one it has (123). Subcategory narrows by category because that is a value mirror; nothing else narrows, because the rest are rules and they stay server-side (124).

**The editor does not open on a `processing` row** — a background task is in flight and would overwrite the edit seconds later — and the page enforces that itself, because a deep link can land on one. A row still `failed` after a save says so, on the status the response carried (116).

**Retag is one control.** It sends the unforced request; a `409 item_edited` opens a second step naming what will be discarded, and only that step sends `force=true`. Forcing straight away whenever `user_edited` is set would mean the `409` is never produced from the UI, and Stage 1's sixth acceptance criterion would stay a route test (122). **Delete arms on the first press and deletes on the second** — not `window.confirm`, which returns `undefined` in the test environment, and not a modal (126).

Wear count and last worn are **built at task 3.4**. Until then the section carried a placeholder — the columns existed from migration `0004` and nothing wrote them, so a zero would have changed meaning when they landed. It now reads *"Never worn"* on an unworn garment and *"Wears: 3"* with *"Last worn 2026-03-09"* on a worn one. **Never-worn gets its own sentence rather than a zero and a blank date**, because it is the state most of a wardrobe is in and 3.6 builds a whole insights panel on counting it. The date is printed as the ISO day the server sent: this application has no date-formatting layer, and adding one for a single line would be the speculative abstraction `CONVENTIONS.md` forbids.

**"Style around this" is not built, and this is where it was promised.** The line that said *"Primary action on this screen … do not bury it behind the edit and delete actions"* described a navigation into the stylist with `anchor_item_id` pre-set — a Stage 2 screen, out of scope for the whole of Stage 1, and named in no Stage 1 task. It is not cut: it is the first thing this screen should gain when the stylist exists, and the reasoning for it stands — it is the shortest path from *I am looking at this garment* to *here is what goes with it*. Recorded here so that whoever builds Stage 2 finds it, on 090's test: ownership, not affordance.

**The route into this screen was specified nowhere.** The grid legend below gives a tile one behaviour, "tap to retry". Task 1.9 makes the tile's photograph a link to `/wardrobe/:id`, with the retry button as its sibling rather than inside it — an anchor wrapping a button is nested interactive content (`DECISIONS.md` 129). A `failed` tile also carries **Add tags by hand**, which is `03-AI-CONTRACTS.md`'s long-promised "Add manually" link and `AUDITS.md` **O-3**.

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

*Amended after task 3.3: the screen has a way out.* A **Back to wardrobe** link
sits above the heading — `stylist.back`, the same string and the same treatment
as item detail and profile, so it reads as the application's back link rather
than this screen's invention. It is deliberately **outside** the three-way branch
this section describes: that branch replaces everything below the heading, so a
link inside it would disappear for the four to eight seconds of the wait and
again for as long as the card is up, which is most of the time anybody spends
here. A real anchor, not a history call — `/wardrobe` is a place, and the browser
back button on a screen reached from the weather strip goes somewhere else.
It is the fourth hand-placed navigation control in the application; `AUDITS.md`
**O-29** counts it.

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

*Amended at task 3.2: the heart is built. Amended again at 3.3: so are the
thumbs, and the heart stopped waiting for the server.* All three are **toggle
buttons with fixed accessible names** — "Save this look", "Good look", "Not for
me" — with `aria-pressed` carrying the state, rather than labels that swap
between Save and Unsave: a name that changes with the state announces the change
twice and disagrees with itself about which way the next press goes.

The heart's glyph (♡ / ♥) is `aria-hidden` decoration. **The thumbs use a ring
rather than a second glyph**: emoji have no hollow/filled pair for 👍 the way
♡/♥ are a pair, and the nearest thing — the same thumb with a skin-tone
modifier — would encode "off" as a skin tone.

**Pressing the thumb that is already on withdraws the rating** rather than
rewriting it, sending `feedback: null`. The other thumb replaces it. A rating
that could only be replaced and never withdrawn would make a mis-tap permanent
in what 3.5 tells the stylist.

**All three are optimistic** and roll back on failure, and the error line above
the card reads both stores — until 3.3 it read the stylist's alone, so a failed
heart tap rolled the control back and explained nothing. `DECISIONS.md` 182, 183.

Items are laid out by `layer` and `category`, not in an arbitrary order. Tapping an item opens its detail page.

**Each item also carries a small ↻ badge.** Tapping it re-requests the same look with every other item locked and only that role replaced, adding the rejected item to `exclude_item_ids`. Show a spinner on that tile alone; the rest of the card stays put.

*Amended at task 2.11: **each item that has a role**, which is every garment except a dress.* `replace_role`'s vocabulary has no `dress` — replacing one can legally come back as a top and a bottom, which is a different look rather than a single-item swap — so a dress tile carries no badge and "Try again" is the only reroll for it. `02-DATA-MODEL.md`'s `role` section, `AUDITS.md` **O-25**, `DECISIONS.md` 175.

This matters more than it looks. Most of the time a suggested look is fine and exactly one piece is wrong — usually the shoes. "Try again" rerolls everything and loses the good parts, which is the single most common frustration with outfit apps. Per-item swap is cheap to build on top of the same endpoint and none of the competing apps offer it.

If `missing_pieces` is non-empty, render a muted note beneath: *"A neutral closed shoe would complete this."*

### 6a. Saved looks — `/saved` *(Stage 3)*

**Added at task 3.2.** `STAGE-3` 3.2 asks for a saved-looks list screen and this
document had no screen for it — the heart was drawn on the card above and the
list it feeds was specified nowhere.

```
┌────────────────────────────────┐
│  ← Wardrobe   Saved looks      │
│  ┌──────────────────────────┐  │
│  │ Morning meetings      ♥  │  │
│  │ 18°C — the blazer is …   │  │
│  │ ┌───┐┌───┐┌───┐┌───┐     │  │
│  │ └───┘└───┘└───┘└───┘     │  │
│  │ [ I wore this ]          │  │  ← task 3.4
│  └──────────────────────────┘  │
│  ┌──────────────────────────┐  │
│  │ Dinner out            ♥  │  │
│  …                             │
└────────────────────────────────┘
```

**"I wore this", added at task 3.4.** Below the garments rather than beside the
heart: the heart is about the list and this is about today, and a text label
does not belong in a row built for a glyph. It is the only control in the
application that is **not** optimistic, which is a deliberate exception to
`DECISIONS.md` 183 rather than an omission — wearing is not a toggle, so a
second tap does not undo it; the response changes `wear_count` on every garment
and the client cannot derive those numbers; and there is no previous state to
roll back to, because nothing is written before the answer arrives. It shows a
busy state and renders what the server says. `DECISIONS.md` 184.

**After a successful tap it stays, disabled, reading "Worn today."** The state is
worth showing, and the endpoint is idempotent for that exact date anyway, so a
client that retried would cost nothing. A look worn on an *earlier* day gets the
button back, enabled: that is a second wearing and the server counts it as one.
The date sent is the browser's local today, from the same `todayInLocalTime` the
stylist form and the weather strip use — two spellings of "today" in one
application would disagree for anyone off UTC.

**Not the look card.** That component groups by layer, carries a ↻ badge on
every garment and ends in "Try again", none of which a saved look can do —
there is no request behind it to re-run. A row carries the title, the weather
note, the garments as a flat strip **in the server's order**, and the heart.
Reusing the card would have meant two inputs whose only job is to switch its own
features off.

**Unsaving leaves the row where it is**, with an empty heart, until the next
load. Taking it away under the finger that unsaved it makes the tap
uncorrectable; leaving it makes it one tap back.

Empty state links to `/stylist` — it is the likeliest first visit, since the
heart is one task old and no account has used it.

**Nothing links to this screen.** `AUDITS.md` **O-29**; the entry point is its
own work, as `/stylist`'s was at 2.12.

### 7. Trips — `/trips` *(Stage 4)*

**Form:** destination (autocomplete via `/me/locations/search`), date range, then one occasion chip row per day, defaulting to `casual`.

**Built at task 4.5, and the line above is one field short.** `STAGE-4` 4.5 asks
for *"an optional notes field"* and this section never drew one. The form has it,
and it is **unbounded** — `TripPackRequest.notes` is stripped and not
length-checked, so a counter or a cap here would be a refusal the API does not
make. Five more things the sentence above does not say, each settled at 4.5's
orientation:

- **The destination is *picked*, never typed.** The wire takes one string and
  the endpoint geocodes it again for itself (`DECISIONS.md` 202), so the picker's
  coordinates are dropped and only the provider's own `name` is sent — a string
  the geocoder returned is one it will match. The chip prints `name, country` to
  tell the two Berlins apart, and the country is display text that never leaves
  the browser, which is `DECISIONS.md` 153 biting a third time: both Berlins send
  `"Berlin"`. The submit button is disabled until a place has been chosen.
- **The dates are capped at `today + 14` and floored at nothing.** The cap is
  `DECISIONS.md` 190's, and the missing floor is 201's: a lower bound on the
  server's calendar day is a refusal a browser east of UTC earns by its timezone,
  so the form does not enforce one either. The client refuses an inverted range
  and a trip longer than fourteen days before spending a round trip; the server
  answers `trip_too_long` for both.
- **The chip rows are sized by the dates and keep what was chosen.** Changing
  either date resizes the list — padding with `casual`, truncating from the end —
  so a day already set to *work* survives extending the trip. The rows are built
  in day order because the request schema requires the numbers to arrive as
  `1..n` *in* order rather than as a permutation of them.
- **The wait is four cycling status lines and no skeleton.** The stylist draws
  the outline of the look card because its form *becomes* one; this form becomes
  a sentence, and a skeleton of a sentence is a grey bar pretending to be
  progress. The lines name the four steps the server takes — geocode, forecast,
  wardrobe, assemble — and **none of them names a duration**, because nobody has
  measured this call.
- **Success is a confirmation panel, not a navigation.** `/trips/:id` is 4.6's
  and does not exist, so 4.5 ends at *"Berlin is packed. 8 items · 4 looks"*,
  built from `packing_list.reuse_summary` — which is this section's own header
  line, word for word. Task 4.6 replaces the panel with a `router.navigate` and
  the counts move up to the header they were written for. The destination is
  rendered in the **body face**, per `DECISIONS.md` 071, which names this screen.

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

**Built at task 1.7, and the sketch above is wrong in three ways that are worth keeping visible rather than editing out.**

**It is two requests, not one.** A body filtered to `status=processing` contains only rows that are *still* processing, so it can tell the client that an item has left the set and can never tell it what the item became. The poll alone therefore leaves every tile dimmed and untagged for ever, which is the opposite of the acceptance criterion it exists to satisfy — *"All 5 become `ready` with correct-looking tags … no page refresh"*. The shipped loop polls `GET /items?status=processing&limit=200`, compares the returned **ids** against the ones it was waiting for, and re-issues the full `GET /items?limit=200` whenever one is missing. Ids rather than a count, because a second batch landing while the first finishes leaves the count unchanged with the membership entirely different. `DECISIONS.md` 102.

**The effect needs a guard the sketch does not have.** `processing()` is computed from `items()`, and every poll response changes `items()`, so an effect written exactly as above calls `startPolling()` on every response. The guard is the run object itself — a nullable private field holding the deadline, the timer and the in-flight subscription — rather than a boolean beside it, so "are we polling" and "is anything scheduled" cannot drift apart. `DECISIONS.md` 103.

**The effect reads `awaitingTags()`, not `processing()`.** Those two differ by the items the loop has stopped waiting for, and keying it on `processing()` means the loop goes on polling for rows whose tiles already say we gave up on them — silently, for another three minutes, from the next time anything puts a row into the collection. This survived the entire suite as a mutation before the test that closes it existed; `06-TESTING-STRATEGY.md` carries it.

**And nothing is "marked failed in the UI".** A client-written `status` would be a row no server issued, inside the one collection whose contract is that everything in it came off the wire — and 1.8 filters that collection while 1.9 edits from it. The abandoned ids are a second collection beside `retrying` and `retagErrors`, read by the tile *together with* `status` so a stale entry on a row that has since arrived `ready` draws nothing. The tile says **"We stopped waiting. It may still finish."** and does not take `--color-danger`: the server may well still be tagging, and 057 reserves that token for something being wrong. `DECISIONS.md` 105.

The re-arm is after each response settles rather than on a fixed interval, so one poll is in flight at a time by construction (104); a failed poll is ignored and the deadline bounds it (106); and the loop is stopped by the wardrobe page's `DestroyRef`, because `WardrobeStore` is `providedIn: 'root'` and outlives the screen (107).

---

## Visual direction

One decision, made once, applied everywhere: **the clothes are the design.** The interface is a neutral gallery wall.

- Background `#FAFAF8`, surfaces white, text `#1A1A1A`, one accent used sparingly.
- **The accent is `#2F4858`**, a deep desaturated ink-blue, settled at task 0.8. A warm mid-chroma accent — terracotta was the alternative — reads as a garment itself and competes with brown, beige, red and pink, four of the seventeen wardrobe colours it would sit beside in the grid. `DECISIONS.md` 057.
- **The display typeface is Fraunces**, self-hosted at task 0.9 as a latin-subset variable woff2 in `public/fonts/`, preloaded, `font-display: swap`. Body text uses Tailwind's default `--font-sans`, which is already the system stack this section asks for and is deliberately not overridden. `DECISIONS.md` 065.
- **The display face is for chrome we author.** Anything a user entered or a model generated uses the body face — Fraunces is latin-subset and the family has no Hebrew coverage, so a non-Latin name in a display heading falls back per character and renders in two faces on one line. The wardrobe screen's "Signed in as …" is the first instance and it takes the body face. Four later surfaces must apply the rule deliberately: **item detail (1.9), weather strip (2.2), look card title (2.9), trip header (4.5)** — each renders text this project did not write. `DECISIONS.md` 071.
- **`--color-danger: #7f2f3c`** is the fifth token, added at 0.9 for validation messages and failure notices. It is used only where something is wrong: the "server may be waking up" notice deliberately does not take it, because task 1.3's failed tiles lean on the same signal and it must not also mean "slow". `DECISIONS.md` 057.
- The five colours and the display face are declared once, as `@theme` tokens in `frontend/src/tailwind.css`, and generate their own utilities (`bg-canvas`, `text-ink`, `text-danger`, `font-display`). There is no `tailwind.config.js` — Tailwind 4 is CSS-first. `DECISIONS.md` 056.
- Cut-out garment images on white read as a catalogue. Nothing else should compete with them.
- Generous whitespace, no card borders — use shadow and spacing for separation.
- One display typeface for headings, one system stack for body.
- Every interactive element ≥ 44px tall. This is a phone app that happens to run in a browser.

---

## Internationalisation readiness

English only in this project, Hebrew afterwards. Two rules make that a JSON file rather than a rewrite:

1. **No hard-coded user-facing strings.** Everything goes through a key in `public/i18n/en.json`, read by `core/i18n/i18n.service.ts` — forty lines, signal-based, no dependency, with `{{name}}` interpolation from the first version. Keys are flat and dotted (`login.title`); a missing key renders as itself, and a placeholder with no value supplied is left visible rather than blanked, so both failures are findable on screen. Components inject the service and call `t()`; there is no translate pipe. `DECISIONS.md` 058 has the reasoning and names `@ngx-translate/core` as the escape hatch if a second locale ever arrives.
2. **CSS logical properties only** — `margin-inline-start`, `padding-inline-end`, `text-align: start`. Never `left` or `right` for layout.

Tailwind supports the logical variants (`ms-4`, `me-2`, `text-start`). Use them from the first component.

---

## Accessibility floor

Not a full audit, but non-negotiable: every image has meaningful `alt` (use `display_name`), every icon-only button has `aria-label`, focus is visible, and the whole app is keyboard-navigable. Playwright's `getByRole` locators depend on this — good accessibility directly produces stable tests.

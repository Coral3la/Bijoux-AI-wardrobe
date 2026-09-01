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
│   ├── stylist/         stylist.page.ts, look-request-form.ts, look-card.ts
│   ├── trips/           trips.page.ts, trip-form.ts, packing-view.ts, day-strip.ts
│   └── profile/         profile.page.ts
├── shared/
│   ├── ui/              nav-bar.ts (task 4.9, the only one built)
│   │                    button, chip, sheet, skeleton, empty-state, spinner,
│   │                    toast — the seven are AUDITS.md O-15 and none exists
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

## Navigation

**Built at task 4.9, and it is the first chrome in this project that belongs to
no screen.** `shared/ui/nav-bar.ts`, rendered by `app.html` above the router
outlet, so it is a sibling of every screen rather than part of one.

```
┌────────────────────────────────┐
│ Wardrobe Stylist Trips Saved … │  ← sticky, scrolls horizontally at 390px
├────────────────────────────────┤
│ (the screen)                   │
└────────────────────────────────┘
```

**Five items, one per top-level screen**, in `NAV_ITEMS`: Wardrobe, Stylist,
Trips, Saved, Profile — plus **Sign out**, last and pushed to the end, which is
the one control here that does not navigate. `/wardrobe/:id` and `/trips/:id`
get no item of their own: they are children of items that exist.

**It renders only for a signed-in user**, gated in the shell on
`auth.isAuthenticated()`. That signal is the *user*, not the token, so a
restore still in flight renders no bar and a rejected token never renders one —
and `/login` and `/register` get none without either being named. A screen
added to `app.routes.ts` cannot acquire a bar by existing.

**The active item is `routerLinkActive` at its default, non-exact matching**,
with `ariaCurrentWhenActive="page"`. Non-exact compares path segments as a
prefix and query parameters as a **subset**, and these links carry no query
parameters at all — so the Wardrobe item stays lit under `?category=tops`,
which the grid writes on every filter change, and on `/wardrobe/:id`; the Trips
item stays lit on `/trips/:id`. `{ exact: true }` compares query parameters
exactly and would switch the Wardrobe item off the first time anybody filtered.
`DECISIONS.md` 208.

**It is one bar at every width**, not tabs on a phone and a bar on a desktop:
the wardrobe's **Add items** FAB is `fixed bottom-6 end-6`, so a bottom tab bar
would sit underneath it. At 390px the row scrolls horizontally rather than
wrapping, on the category chip row's precedent — a sticky bar that grows to two
lines costs vertical space on every screen.

**What it replaced.** Six back links and two account-row anchors, deleted at
4.9 with eight i18n keys. Three navigation-shaped controls survive because they
are contextual actions rather than navigation: the weather strip's **Style me**
and **Set your home city** (§2.12, unedited by this task), and `/saved`'s empty
state offering **Ask for a look**. `item.back` on `/wardrobe/:id` survives too,
as a hierarchical *up* from a child screen. `AUDITS.md` O-29 carries the census
of what was there before.

---

## Screens

### 1. Auth — `/login`, `/register`

**Rewritten at the auth pass, and the sentence it replaces is quoted rather than deleted: *"Single-column, centred. Email, password, display name on register. Nothing else. This screen must not consume design time."*** That was right for a scaffold and wrong for the first screen a stranger meets, and `DECISIONS.md` 223 is the argument.

**A full-height cream canvas with no application chrome.** The navigation bar is gated on a confirmed user (`app.html`), so these two screens have none, and the wordmark at the start of the top edge — display serif, 22px, 0.28em, uppercase — is the only furniture. Everything else is centred in what is left: a display-serif title at 48px (*"Welcome back."* on `/login`, *"Begin a wardrobe."* on `/register`), one italic tagline both screens share (*"Your wardrobe, considered."*), then a 400px column of fields.

**A field is a label and one rule.** A mono micro-label at 10px and 0.24em over a transparent input on a single `ink-soft` hairline — no box, no fill, no placeholder. The submit is the Atelier pill with the arrow the stylist's and the trip's forms already carry. Under it, in italic prose, the swap line: *"New here?"* → **Register**, *"Already have an account?"* → **Log in**, the link set as a caps-letter-spaced accent run. Two keys, not one sentence — the question is ours and the word after it is a control's label.

**The two screens are twins and differ in four places**: the title, the swap line, one extra field on register, and login's three extra objects — the two bootstrap notices and the demo button, which the picked mockup was not drawn against and which keep every decision recorded for them.

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

**The account row was drawn here and is gone.** It held **Profile** (task
2.10a), **Saved** (after 3.6), **Sign out** and a *Signed in as …* line, and
**task 4.9 deleted all four**: the two anchors and the sign-out are in the
navigation bar now, and the identity line is nowhere — `/profile` is the screen
about who you are, and no other screen ever announced it. The mockup above is
drawn without the row. The bar is not in that mockup either, because it is not
this screen's: it is the shell's, it sits above every screen, and it is
specified under **Navigation** above rather than here. `AUDITS.md` O-29 is
**closed** and `DECISIONS.md` 208 is the entry.

**This section is where O-29 said the navigation belonged, and that is the one
part of its recommendation not taken.** A bar rendered by `app.html` cannot be
specified inside the wardrobe's section without describing it as something the
wardrobe owns — which is the mistake that produced the account row in the first
place.

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

**Rewritten at the Ritual pass.** The three-state screen this section used to describe — ask, wait, look, each replacing the last — is gone. `DECISIONS.md` 220 is why.

```
┌──────────────────────────────────────────────┐
│ Stylist                 Clear · 22° / 27°    │  ← h1 + forecast, one rule under
├──────────────────────────────────────────────┤
│ ┌── stone panel ───────────────────────────┐ │
│ │ OCCASION            COAT                 │ │  ← two chip rows, side by side ≥md
│ │ [CASUAL][WORK][…]   [AUTO][YES][NO]      │ │
│ │ WHEN     [2026-09-01]                    │ │
│ │ NOTES    [__________________________]    │ │
│ │                        [ STYLE ME → ]    │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│  … one slot: skeleton | look | ready line …  │
└──────────────────────────────────────────────┘
```

**The form is permanent.** It sits under the header in every state and is never swapped out — not for the wait, not for the result. Beneath it is **one slot with three states**: a four-tile skeleton with a cycling status line while a request is in flight, the look, or a muted italic *"Ready when you are."* when there is nothing to show.

**The submit label changes with the state and the flow does not.** `stylist.submit` (*Style me*) when no look is on screen, `stylist.submit.restyle` (*Change & restyle*) when one is. The **page** owns that choice and hands the form a key, because only the page knows whether a look exists.

**Changing a field while a look is on screen does not invalidate the look.** Nothing is re-requested until the button is pressed. The pitch proposed recalculating in place and it was declined: a look that changes while it is being read cannot be compared against the one you would get instead.

**Try again clears the look** and the screen rests on the waiting line. The form never left, so nothing is re-mounted.

**The anchor pin** sits above the form when the screen was reached with `?anchor=`: *"Building around: light blue mom jeans"*, with an × that clears both the pin and the query parameter.

**The forecast is in the header**, beside the `h1`, not inside the form. Two elements: the condition in the authored prose face, the reading in mono — `Clear · 22° / 27°`. It names no day, because the forecast is for whatever date the picker holds. **There is no dateline**; it printed *"Today"* over a line that says it already.

Expect 4–8 seconds. The status lines cycle *"Reading the forecast…"*, *"Going through your wardrobe…"*, *"Putting the look together…"* and rest on the last.

*What this section used to carry, kept because the reasoning outlived the control.* It described a **Back to wardrobe** link and argued it had to sit **outside** the three-way branch, since that branch replaced everything below the heading and a link inside it would vanish for the wait and for as long as the card was up. **Task 4.9 deleted the link** along with the four other peer-level back links; `AUDITS.md` O-29's closing note is the census and `DECISIONS.md` 208 is the entry. The argument still holds and is now answered twice over: the way out is the navigation bar, one level further out than this screen — and there is no branch to fall inside of any more.

### 6. Look card — the visual payoff

```
┌──────────────────────────────────────────────┐
│ CASUAL · TUE 1 SEPT · AUTO COAT              │  ← what the look answers
│ Ease into the day                  4 PIECES  │  ← content face; mono kicker
│ Warm morning, cooler evening.                │
│ ┌────┐ ┌────┐ ┌────┐ ┌────┐                  │
│ │ ↻  │ │ ↻  │ │ ↻  │ │ ↻  │                  │  ← 4 across ≥md, 2 on a phone
│ └────┘ └────┘ └────┘ └────┘                  │
│ Cashmere sweater  Wide-leg …                 │
│ BASE LAYER · TOPS BASE LAYER · BOTTOMS       │
│                                              │
│ The trench is your answer for evenings…      │  ← reasoning, one line
│ Layer up before six.                         │  ← weather_note
│ ────────────────────────────────────────     │
│ (♡) (👍) (👎)                    TRY AGAIN   │
└──────────────────────────────────────────────┘
```

**Rewritten at the Ritual pass.** It is **not a card**: no wrapper, no fill, no shadow, no radius. It sits directly on the canvas, because it is the last thing on the page and there is nothing beside it to be separated from. `/saved` renders looks among peers and keeps its own treatment.

**The card heads with the parameters the look was built for** — occasion, date, coat — in the mono face at 11px above the title. It comes from a **snapshot of the draft taken when the request went out**, not from the live form, so a card cannot relabel itself when a chip is tapped. **The kicker and the form are allowed to disagree, and that is the point**: it is how a reader tells a look built for Tuesday from a form now set to Wednesday, and it is why *Change & restyle* is a press rather than an effect. Notes are excluded — free text, and the line is three short fields. The input is optional and the kicker is silent without it, because a look does not know what was asked for it; only the screen that asked does.

**Layer grouping is gone.** Items are still sorted by `layer` then `category` — the sequence a reader and a screen reader both take — but the `<h3>` headings that cut the sort into sections are deleted and the layer prints in each tile's meta line instead: `Base layer · Tops`, or the category alone when the layer is null, or nothing when neither is known. Four headings over four garments was more chrome than the thing it organised.

**The title, the message, the reasoning, the weather note and every garment name are the model's words**, so all five take the content face at the sizes the direction asks for — `DECISIONS.md` 071, applied here against a mockup that drew them in the display serif. The **piece count**, the **tile meta lines**, the **missing-pieces label** and the **action names** are ours and keep the authored treatment.

*Amended at task 3.2: the heart is built. Amended again at 3.3: so are the
thumbs, and the heart stopped waiting for the server.* All three are **toggle
buttons with fixed accessible names** — "Save this look", "Good look", "Not for
me" — with `aria-pressed` carrying the state, rather than labels that swap
between Save and Unsave: a name that changes with the state announces the change
twice and disagrees with itself about which way the next press goes.

**They are circles on a hairline now**, 44px, in a row above a rule: the heart **fills with the accent** when saved, because ♡ / ♥ are a real pair; the thumbs **take an accent ring**, because emoji have no hollow/filled pair for 👍 and the nearest thing — the same thumb with a skin-tone modifier — would encode "off" as a skin tone. **Try again** is a caps letter-spaced accent link pushed to the end of the row. 44px rather than the mockup's 40, which is the floor winning over the picture for the second time.

**Pressing the thumb that is already on withdraws the rating** rather than
rewriting it, sending `feedback: null`. The other thumb replaces it. A rating
that could only be replaced and never withdrawn would make a mis-tap permanent
in what 3.5 tells the stylist.

**All three are optimistic** and roll back on failure, and the error line — one
for the whole screen, above the result slot — reads both stores.
`DECISIONS.md` 182, 183.

Tapping an item opens its detail page.

**Each item also carries a small ↻ badge**, top-right of its photograph. Tapping it re-requests the same look with every other item locked and only that role replaced, adding the rejected item to `exclude_item_ids`. Show a spinner on that tile's photograph alone; the rest of the strip stays put.

*Amended at task 2.11: **each item that has a role**, which is every garment except a dress.* `replace_role`'s vocabulary has no `dress` — replacing one can legally come back as a top *and* a bottom, which is a different look rather than a single-item swap — so a dress tile carries no badge and "Try again" is the only reroll for it. `02-DATA-MODEL.md`'s `role` section, `AUDITS.md` **O-25**, `DECISIONS.md` 175.

This matters more than it looks. Most of the time a suggested look is fine and exactly one piece is wrong — usually the shoes. "Try again" rerolls everything and loses the good parts, which is the single most common frustration with outfit apps. Per-item swap is cheap to build on top of the same endpoint and none of the competing apps offer it.

If `missing_pieces` is non-empty, render it as a small italic list under a caps label — not a boxed section.

### 6a. Saved looks — `/saved` *(Stage 3)*

**Added at task 3.2** — `STAGE-3` 3.2 asked for a saved-looks list screen and this
document had no screen for it. **Rewritten at the Atelier pass**, from the picked
mockup: the direction is **The Shelf** and `DECISIONS.md` 221 is why.

```
  Saved looks                                        3 saved
  ────────────────────────────────────────────────────────────
  ┌──┐┌──┐┌──┐┌──┐   WORK                    ♡   ( I WORE THIS )
  │  ││  ││  ││  │   Morning meetings
  └──┘└──┘└──┘└──┘   Mild at 18°C — the blazer is enough.
  ────────────────────────────────────────────────────────────
  ┌──┐┌──┐┌──┐┌──┐   EVENING                 ♥   ( ✓ WORN TODAY )
  │  ││  ││  ││  │   Dinner in Neve Tzedek
  └──┘└──┘└──┘└──┘   Cooler after sundown; trousers keep it grown-up.
  ────────────────────────────────────────────────────────────
```

**One look is one row, on the canvas.** A three-column grid — `320px 1fr auto` —
holding a four-plate garment strip, the body, and the controls; a hairline
between rows and none after the last; no card, no fill, no shadow. It stacks to
one column below `md`. The page is 980px wide rather than the `max-w-2xl` it held
before, which is what 320px of photographs costs.

**The strip is `ItemCard` with `caption=false`** — 220's input — so a saved row's
tile is the photograph alone. The plates stay **4:5**, the wardrobe's ratio and
the look card's, where the mockup drew squares. The garments are **in the
server's order**, which is `look_items.position` and therefore the model's own.

**The body is three lines: a mono kicker, the title, the weather note.** The
kicker is the **occasion** the look was built for, uppercase at 10px and
letter-spaced, guarded against a value outside `vocabulary.occasion.*`. The title
is the content face at 22px and the note is the content face italic at 14px —
both are the model's words, so `DECISIONS.md` 071 keeps them out of the serif the
mockup drew them in.

**The mockup's date and its *This week* / *Earlier* grouping are not built, and
the reason is the same for both: `LookResponse` carries no save date.** The rows
are one flat stack. `looks.created_at` is a column and is not on the response
schema; putting it there is a backend commit, and the grouping and the dateline
follow it. `DECISIONS.md` 221.

**The header** is the display serif at 48px with a **mono count** on the far end
— `3 saved` — over a single rule. The count is read off `is_saved` rather than
off the rows, so unsaving the last row shows `0 saved` above it rather than
claiming a save the empty heart denies.

**The controls sit together in the third column**: the heart as a 44px circle,
filled in the accent when saved, and the wear button as a caps-letter-spaced
pill. This **reverses the "below the garments" placement** of 3.4 and keeps its
reasoning — *a text label does not sit in a row built for a glyph* was true of a
card whose only other control was a heart, and is not true of a row whose third
column is the controls.

**"I wore this", added at task 3.4.** It is the only control in the application
that is **not** optimistic, which is a deliberate exception to `DECISIONS.md` 183
rather than an omission — wearing is not a toggle, so a second tap does not undo
it; the response changes `wear_count` on every garment and the client cannot
derive those numbers; and there is no previous state to roll back to, because
nothing is written before the answer arrives. It shows a busy state and renders
what the server says.

**After a successful tap it stays, disabled, reading "✓ Worn today"** — and
un-filled, which is the whole of how the screen says a look was worn today. The
mockup drew a second `✓ Worn` badge beside the title and it is deleted: one fact,
one signal. A look worn on an *earlier* day gets the button back, enabled: that
is a second wearing and the server counts it as one. The date sent is the
browser's local today, from the same `todayInLocalTime` the stylist form and the
weather strip use — two spellings of "today" in one application would disagree
for anyone off UTC.

**Not the look card.** That component heads with the parameters its request
carried, carries a ↻ badge on every garment and ends in "Try again", none of
which a saved look can do — there is no request behind it to re-run. Reusing it
would have meant inputs whose only job is to switch its own features off.

**Unsaving leaves the row where it is**, with an empty heart, until the next
load. Taking it away under the finger that unsaved it makes the tap
uncorrectable; leaving it makes it one tap back.

**The wait draws the row**: two skeleton rows, each a strip of four plates and
two text lines, deferred as a region with the status line inside it (`DECISIONS.md`
217).

Empty state links to `/stylist` with a **ghost** CTA — it is the likeliest first
visit, and an empty saved list is a state a working account passes through rather
than the one action a new account must take.

**The navigation bar is what links here**, since task 4.9; `AUDITS.md` **O-29**
is closed and the sentence that used to stand here — *nothing links to this
screen* — went with it.

### 7. Trips — `/trips` and `/trips/:id` *(Stage 4)*

**Built at tasks 4.5, 4.6, 4.6a and 4.6b. Rewritten at the Atelier pass**, from
the picked mockup: the direction is **The Itinerary** and `DECISIONS.md` 222 is
why. The form is `/trips`; the packed trip is `/trips/:id`.

#### The form — `/trips`

Destination (autocomplete via `/me/locations/search`), date range, one occasion
chip row per day defaulting to `casual`, and an optional notes field. The whole
control sits in **one stone panel** — `bg-surface-elevated`, `rounded-sm`,
`p-6` — which is the treatment the stylist's form took at its own pass and the
only raised object on either trip screen. Every label is a 10px caps eyebrow,
every field is a hairline box on the canvas colour, the chip rows **wrap** where
they used to scroll, and the submit is the caps pill with the arrow that ends
the stylist's form. The header above it is the wardrobe's: a mono caption, the
title in the display serif at 300, a rule under the pair.

Five things the form does, each settled at 4.5's orientation and none of them
changed by the restyle:

- **The destination is *picked*, never typed.** The wire takes one string and
  the endpoint geocodes it again for itself (`DECISIONS.md` 202), so the picker's
  coordinates are dropped and only the provider's own `name` is sent — a string
  the geocoder returned is one it will match. The chip prints `name, country` to
  tell the two Berlins apart, and the country is display text that never leaves
  the browser, which is `DECISIONS.md` 153 biting a third time: both Berlins send
  `"Berlin"`. The submit button is disabled until a place has been chosen. The
  results are rows on a hairline rather than a stack of filled tiles — five
  raised objects inside a panel is three levels of surface in one control.
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
- **The notes field is unbounded.** `TripPackRequest.notes` is stripped and not
  length-checked, so a counter or a cap here would be a refusal the API does not
  make.
- **The wait is four cycling status lines and no skeleton.** The stylist draws
  the outline of the look card because its form *becomes* one; this form becomes
  a sentence, and a skeleton of a sentence is a grey bar pretending to be
  progress. The lines name the four steps the server takes — geocode, forecast,
  wardrobe, assemble — and **none of them names a duration**, because nobody has
  measured this call. They are set in the prose italic, because they are
  sentences this project wrote.

**Success is a navigation, not a panel.** 4.5 ended at a confirmation panel
because `/trips/:id` did not exist yet; 4.6 replaced it with a
`router.navigate` and moved its counts into the header they were written for.

**The chips come from the shared `appChip` directive**, which this pass converted
to Atelier rather than copying a third time — the trip form is the third screen
to want the treatment and the directive's only remaining caller. `DECISIONS.md`
220, 222.

#### The packed trip — `/trips/:id`

```
  TRIP · 5 DAYS
  Milan
  2026-09-10 – 2026-09-14
  Packed 12 pieces across 5 looks. You'll wear the camel trousers on 3 days.
  ──────────────────────────────────────────────────────────────────────────
  DAY 1 · 2026-09-10   Arrival day.            ⛅ 24°C partly cloudy · Casual
  ┌────┐┌────┐┌────┐┌────┐
  │    ││   ↻││    ││    │
  └────┘└────┘└────┘└────┘
  Cashmere sweater   Wide-leg trousers   Leather sneakers   Trench coat
  TOP                TROUSERS            SHOES              OUTERWEAR
  Traveling comfort with room for the evening.
  The trench catches the airplane chill.
  ──────────────────────────────────────────────────────────────────────────
  DAY 2 · 2026-09-11   Meetings and dinner.            ☀ 26°C clear · Work
  …
  ──────────────────────────────────────────────────────────────────────────

  Before you go

  TOPS · 3 ───────────────        TROUSERS · 2 ───────────
   ☑ cream cashmere sweater        ▢ camel wide-leg trousers
   ▢ white silk shirt              ▢ black wool trousers
  ──────────────────────────────────────────────────────────────────────────
  ( RE-PACK WITH TODAY'S FORECAST → )                     ( DELETE TRIP )
```

**There are no day tabs.** Every day is a section, in date order, one flowing
into the next, separated by a hairline and by nothing else — and the last one
closes on a heavier rule before *Before you go*. The page is 820px. This is the
one behaviour change the direction is made of, and what it deletes is a piece of
view state: there is no selected day, so there is no opening selection to defend,
nothing to clear when the reader moves, and nothing for a repack to preserve.

**The day head belongs to the page, not to the look.** A mono kicker naming the
day and its date, the look's title beside it on the same baseline, and the
forecast on the far end as italic prose with a mono reading and a decorative
glyph: `⛅ 24°C partly cloudy · Casual`. The head renders for **every** day,
including one whose look a repack detached — which is why the title is drawn
here rather than inside `TripLook`, and why the condition and the occasion are
one authored key with the dot inside it.

**The dates are printed as they arrive.** `10–14 September` needs a month name
and a range collapser, and this project formats no date on this screen:
`DECISIONS.md` 206 refused a formatter here and the refusal stands, so the header
range and every day kicker carry the ISO string the server sent.

**The look sits flat on the canvas**: a four-column strip of `ItemCard` with
`caption=false` (two columns on a phone), each tile captioned underneath with the
garment's name in the content face and its category as a caps meta line, then the
still-worn line, the reasoning and the weather note. The garments are in
`look_items.position` order — the model's own — and there is no layer grouping.
**It is still not the look card**, for the three grounds 4.6 recorded and 4.6a
re-recorded: that card ends in *Try again*, carries a heart and two thumbs, and
sorts by layer.

**A day can have no look, and it renders as a quiet line rather than an error.**
`days[].look_id` is nullable because a repack detaches a look that was saved,
rated or worn (`AUDITS.md` **O-32**, `DECISIONS.md` 200), so the day keeps its
forecast and loses its outfit. It is italic prose on the canvas, not a raised
card: a gap in an itinerary is a quiet day, not an object.

**The header is four lines**: a mono caption (`Trip · 5 days`), the destination
at 56px in the **content face** — `DECISIONS.md` 071 names this screen, and a
geocoded place name in a latin-subset serif falls back per character — the ISO
date range in mono, and the summary. **The summary is two whole sentences**,
*"Packed 8 pieces across 4 looks."* and *"You'll wear the white oversized shirt
on 3 days."*, set in italic prose with the garment name rendered through
`AuthoredLine` so that it, and only it, takes the content face. The reuse
sentence is the line that makes the feature land, and it is **omitted entirely**
when `most_reused` is null, when the garment has no `display_name`, and when the
item is in none of the response's looks — never rendered as *Untitled item*.
*"The jeans appear on 3 days"* cannot be written from one template, because
`display_name` is model-written text whose grammatical number is unknowable in
the browser; the verb after *you'll* is invariant, which is the whole reason for
the rewording.

**The packing list is headed *Before you go*** and sits flat on the canvas: group
headings are mono caps kickers on a hairline (`TOPS · 3`), rows are a checkbox
inside its own label, ticked rows are struck through in place, and the groups run
two columns above `md`. The heading names the moment rather than the object,
because the itinerary above it is read at the desk and this is read at the
wardrobe on the morning of. The state is **local to the browser** — there is no
column for it, and a tick that survived a reload would be a claim the server
cannot answer for.

**The repack and the delete are the last row**, under a rule, as caps pills.
Five things about the pair, settled at 4.6b's orientation and unchanged by the
restyle:

- **The repack is one press and the delete is two**, and the asymmetry is the
  feature rather than an inconsistency. `DECISIONS.md` 200 has a repack
  *detach* a look that was saved, rated or worn, and `/saved` filters on
  `is_saved` alone — so a saved look **survives a repack and is still on the
  screen that lists it**. There is nothing to warn about, and a confirmation
  step in front of a reversible act is training for clicking through the one in
  front of the irreversible act next to it. The delete cascades, and its armed
  label says so: *"Tap again to delete. Saved looks from this trip go too."*
  That sentence is the only place in the product where the cascade is named, and
  it is why the armed pill is wide.
- **Two presses, not `window.confirm` and not a modal**, which is
  `DECISIONS.md` 126 transposed one screen along — the gate's `confirm()`
  returns `undefined`, so a confirm-guarded delete reads as tested and never
  runs. It disarms on blur, when the repack is pressed, and when a ↻ badge on
  **any** day is pressed. Idle is the danger colour on a hairline; armed is the
  same token filled, because the gate is only a gate if the second press looks
  different from the first.
- **The repack wait is the pack's wait**, four cycling status lines and the same
  interval, because `DECISIONS.md` 202 has the endpoint re-geocode the stored
  destination rather than reuse the columns — so even *"Finding your
  destination…"* is true of it. The lines, the interval, the interval's teardown
  and the seven-code error table live in `pack-wait.ts` and are imported by both
  screens rather than written twice (`DECISIONS.md` 207).
- **A failed repack keeps the trip on screen** and puts its message above the
  actions row. `pack_trip` runs before anything is detached or deleted, so the
  failure costs the user nothing, and a screen blanked by it would say the
  opposite of what the server guarantees. Six of the seven messages are the
  pack's; the general fallback is its own, because *"We couldn't pack this
  trip"* under a packed trip is the wrong sentence.
- **The delete goes to `/wardrobe`.** There is no trips list, and `/trips` is
  the form — which would drop somebody who has just deleted a trip into a fresh
  pack request. This does **not** add to `AUDITS.md` **O-29**'s count: that
  item counts bespoke controls a user can see and press, and this is a
  redirect after an action, the same shape `item-detail.page.ts` has had since
  1.9 and which was never counted either.

**The ↻ badge is task 4.6a's**, and the Itinerary changes what it is scoped to
rather than what it does. It sits on every garment in a day's look that has a
`replace_role` — so not on a dress, because replacing one can legally return a
top *and* a bottom, which is not the single-item swap the field names
(`AUDITS.md` **O-25**). One tap replaces that garment on that day, spends one
model call, and re-renders the whole trip from the response: every look, the
packing list and the reuse line. Six things about it, five from 4.6a's
orientation and one the Itinerary added:

- **The wait is a spinner over the tapped tile and nothing else** — no status
  cycle, no `packStatus`. The pack's four lines exist because that screen has
  nothing to show for twenty seconds; this one has the whole trip, and covering
  it would throw away the only thing that makes a four-to-eight second wait
  legible.
- **The waiting tile is matched to its day before it is drawn, and this is the
  Itinerary's addition.** `swappingItemId` is an item id, and a garment worn on
  Monday and Thursday is the same id on both — so with every day on screen, one
  press would have spun two tiles. `TripLook` is handed a day-scoped id for the
  spinner and a separate **`busy`** flag for the badges, because every badge in
  the trip locks while one request is in flight and the day it is locking for may
  have nothing waiting on it. `DECISIONS.md` 222.
- **There is no preview and no confirmation, and there is no undo.** The swap
  *is* the answer, and a second tap on the tile that came back is the user
  saying *not that one either* — which is what makes the exclusions a
  conversation rather than a form. The cost is recorded rather than mitigated:
  a garment swapped away cannot be swapped back except by taking what the model
  offers next. `DECISIONS.md` 210.
- **The exclusions are per day, client-held, and fresh on every mount.** A shoe
  that is wrong for Tuesday's rain is the right answer for Thursday, so one
  shared list would narrow six days on the strength of one. The server cannot
  rebuild them — the looks that carried those rejections were replaced by the
  swaps that rejected them — and a repack clears them, because it rebuilds every
  day against a forecast the rejections were never judged against.
- **Where the garment that left is still worn, the screen names the days**, under
  the tile grid of **the day it left** and above that day's prose: *"You'll still
  wear the white shirt on Day 2."* This is `STAGE-4` 4.6a's third property and
  the reason the feature is not a wiring job — without it, taking the jeans off
  Tuesday reads as taking them out of the suitcase while Thursday still wears
  them. The days are joined with `trip.swap.daysSeparator` and there is **no
  "and"**: `Intl` would write one and take the browser's locale with it, on a
  screen whose every other word came from `en.json`, which is `DECISIONS.md`
  206's refusal of a date formatter one sentence along.
- **A failed swap says so under the day it was asked for**, not in the page's
  `actionError` above the actions row — that line means *the whole trip's action
  failed*, and a swap that fails costs one day nothing. The day's look stays
  exactly as it was. **Two of the pack's messages could not be reused**:
  `wardrobe_too_small` says *eight* and the swap threshold is **six**, and the
  pack's `stylist_failed` says *"We couldn't pack this trip"* in answer to a tap
  on one shoe. Both got keys of their own, which is `DECISIONS.md` 207's finding
  a second time. `validation_error` is deliberately given no message and falls to
  the general line.

### 8. Profile — `/profile`

Height, sizes, style notes, home city with autocomplete. Style notes needs placeholder text that teaches by example: *"e.g. I prefer high-rise bottoms and avoid crop tops."*

**Rewritten at the auth pass.** One column at 660px under the navigation bar: a caps back link to the wardrobe, then a mono kicker (*Account*) over a display-serif `h1` at 56px with a rule under the pair. Beneath it **six sections 40px apart**, each a mono micro-label, its control on the auth pair's hairline field, and one italic hint saying what the field is for:

1. **Your name** — *"The greeting on the wardrobe uses this."*
2. **Home city** — the chosen city in a stone panel with a **Change** link, or the type-ahead when there is none. The picker is unchanged from the one built at 2.2 and matches the trip form's: two-character floor, 300ms debounce, stale answers dropped, results as rows on hairlines. *Change* clears the three home columns and brings the search box back, which is what the `×` it replaced did.
3. **Height** — an *optional* tag beside the label, a 120px number field, the documented 120–230 bound refused before the request. *"Centimetres. The stylist is told it before it builds a look."*
4. **Sizes** — three free-text fields. Not in the picked mockup and kept: they are columns `PATCH /me` accepts and the stylist's prompt reads.
5. **Style notes** — the textarea, its teaching placeholder unchanged.
6. **Email** — read-only, because `PATCH /me` takes no email. *"Can't be changed here."*

The actions row sits on a hairline: the save pill at the start edge, a **Sign out** at the end. That sign-out duplicates the navigation bar's and is the one control on the screen that is deliberately a second copy — `DECISIONS.md` 223 names which of the two goes if one has to.

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

**Rewritten at the Atelier pass.** Everything below describes the direction from that pass onward; it replaces the neutral-gallery-wall section DR.1–DR.12 built, and `DECISIONS.md` 219 is why. The one sentence that survives the rewrite unchanged is the first one.

One decision, made once, applied everywhere: **the clothes are the design.** Everything else on the screen gets quieter until they are the only thing on it.

**The direction is Atelier** — the vocabulary of an Aesop store or a COS catalogue. A warm paper ground, one thin serif, chrome that nearly disappears, and a great deal of air. It was picked from three whole-screen mockups rather than assembled from properties, and every rule below is read off the picked mockup rather than argued from first principles.

**A screen is converted whole, in one commit, from a picked mockup.** Converted, in order: the **wardrobe** (Atelier, `DECISIONS.md` 219), the **stylist** (the Ritual, 220), **saved looks** (the Shelf, 221), **trips** (the Itinerary, 222) and the **auth pair with the profile** (223, one direction across three pictures rather than three directions across one screen). **Nothing is left to pitch and the pass is closed.** What it did not do is written where it belongs rather than here: `appButton` is still pre-Atelier on three screens (223), and the accessibility pass the palette's contrast needs is still unscheduled (below).

**The palette is global and follows through immediately; everything else is per-screen.** The tokens below are the application's only palette — there is no second, prefixed set — so every screen is on Atelier's colours from the day the wardrobe lands. What each screen's own pitch decides is its **typography, layout, states and copy**. Until the last pitch lands the unconverted screens are therefore half-converted, and that is deliberate: a palette is the substrate a design is drawn on, not the design.

### Palette

One set of tokens in `frontend/src/tailwind.css`, spelled `bg-canvas`, `text-ink`, `border-line` and so on — the names the application has always used, now carrying Atelier's values.

| Token | Value | Used for |
| --- | --- | --- |
| `--color-canvas` | `#F5F1EA` | the page behind everything |
| `--color-surface` | `#FAF7F0` | a card or a form field: warm paper, never white |
| `--color-surface-elevated` | `#EAE4D8` | a tinted panel — inset notices, the skeleton fill |
| `--color-ink` | `#2A2320` | body text, titles, an inverted chip's fill |
| `--color-ink-muted` | `#7A7358` | prose, the piece count, secondary text |
| `--color-ink-soft` | `#B3AC9B` | tile meta, chip counts, field legends |
| `--color-line` | `#E1DBD1` | every hairline: chip borders, the strip's underline |
| `--color-line-strong` | `#D0C9B9` | an input's border, a chip's resting edge |
| `--color-accent` | `#7A7658` | links and only links |
| `--color-accent-hover` | `#625F45` | the primary button under the pointer |
| `--color-accent-soft` | `#A8A48C` | an accent chip's border |
| `--color-accent-wash` | `#EDEBE0` | the navigation bar's active pill |
| `--color-danger` | `#7F2F3C` | unchanged, and still only where something is wrong |

The accent and the muted differ by one digit and that is not a slip — the accent is the warmer of two olive-taupes, and it is what makes a link legible as a link without a colour arriving on the screen. **`--color-surface-elevated` is darker than `--color-surface`**, which its name does not suggest: on warm paper a panel is lifted by tint and never by white.

**Known and accepted: `--color-accent` on `--color-canvas` is 4.1:1**, under AA for normal text, and `--color-accent` on `--color-accent-wash` is 3.8:1. The picked palette has this property; the accessibility pass that fixes it is not scheduled here.

### Type

- **Cormorant Garamond** answers both authored roles: **display** at weight 300 (`font-display`) for page titles, and **prose** in italic (`font-prose`) for the sentences this project writes — the greeting, the weather line, the tagging line, the wait. One family, told apart by style rather than by a second face, and both tokens keep the names and the callers they had.
- **Inter** is the body face and the **content** face (`--font-sans`, so `font-sans` and the default body stack are both it). `AuthoredLine` wraps content spans in `font-sans`, so a name inside an authored sentence is Inter inside italic Cormorant — and so is a garment name under its own photograph.
- **JetBrains Mono** (`font-mono`) draws **every number on the screen**: the piece count in the header, the temperature in the weather line, the counts on the chips, the range readout in the filter panel. One utility face for numerals is the rule, and it is the one that makes a count read as an instrument rather than as prose.
- All three load from Google Fonts with two `preconnect` hints, against `DECISIONS.md` 065's self-hosting. **Fraunces stays self-hosted and preloaded for one consumer** — the pre-bootstrap marker in `index.html`, which cannot wait on a third-party stylesheet.
- **Source Serif 4 is retired**, and so is Fraunces as an application face. `--font-prose` and `--font-display` both name Cormorant Garamond.
- **The three roles from `DECISIONS.md` 071 stand and the rule that decides them is unchanged: who wrote the words.** What changed is which face fills each role. The picked mockup drew the tile caption's garment name in the display face and **the rule won**: a garment name is model-written content and takes the content face, latin-subset Cormorant being the same coverage trap Fraunces was.

### Patterns

- **A chip** is uppercase, letter-spaced, 11px, on a hairline border, full-radius, at least 44px tall. **A category chip carries its count** in the mono face after the label — `TOPS 10` — counted off the loaded wardrobe. **Active inverts**: ink ground, cream text, the count inverted with it. The `Filters` disclosure is the same chip **with no count**, because it names no subset of the grid.
- **The weather strip is a line, not a card.** One italic sentence, the reading in mono after a middle dot, and a caps-letter-spaced **Style me** link pushed to the far end, over a single hairline rule. No panel, no shadow, no rounded ground. All three states of §2.12 still render and the link is in every one of them.
- **The grid** is four columns on desktop and two on a phone, **4:5 plates**, no shadow and no tile background — the photograph sits on the paper. Rows are further apart than columns (40px against 28px), because a caption under every tile would otherwise read as a label for the plate below it. **Each tile carries a caption**: the name in the content face, then `Colour · Category` in 10px uppercase meta — the name is the model's words, the meta is our closed vocabulary, and the two are set accordingly.
- **The floating action is an outlined pill**, not a filled circle: a solid disc of ink over the grid is the one object that would outweigh a photograph, and the word on it removes the need for an icon-only label.
- **An empty state is a centred placard on the canvas**, not a box and not a note: the title in the display serif at 28px with `text-wrap: balance`, the description in italic prose at 40ch, the caller's own CTA below it, and no border, fill or padding of its own. `EmptyState` is shared by `/wardrobe`'s two empty states and `/saved`'s, and the CTA's weight is the caller's — filled for a first upload, ghost for the other two.
- **A list row is a row, not a card.** `/saved` is the pattern: a garment strip, a body, the controls, a hairline between them, on the canvas. Separation is the rule below.
- **A field on a converted screen is a label and one rule** — mono micro-label at 10px and 0.24em over a transparent input on a single `ink-soft` hairline. It is the auth pair's and the profile's; the trip form's and the stylist's boxed fields predate it and were not re-cut.
- **No cards and no shadows on a converted screen.** Separation comes from air and from hairlines. `--shadow-sm/md/lg` remain declared for the screens that have not been converted.
- **Whitespace is still the three named intervals** `--spacing-hero`, `--spacing-region` and `--spacing-group` (`DECISIONS.md` 212, which survives its own supersession): `pt-hero` above a page title, `gap-region` between the parts of a screen, `gap-group` binding a label to what it labels. Tailwind's numeric scale stays available for composition inside a component. A piece of vertical space is owned by one layer of the layout — the container, which can see its neighbours, not the component, which can only see itself.
- Every interactive element ≥ 44px tall. This is a phone app that happens to run in a browser. **The mockup draws a 33px chip and the built one is 44px**, which is the one place the implementation deliberately departs from the picture.

---

## Internationalisation readiness

English only in this project, Hebrew afterwards. Two rules make that a JSON file rather than a rewrite:

1. **No hard-coded user-facing strings.** Everything goes through a key in `public/i18n/en.json`, read by `core/i18n/i18n.service.ts` — forty lines, signal-based, no dependency, with `{{name}}` interpolation from the first version. Keys are flat and dotted (`login.title`); a missing key renders as itself, and a placeholder with no value supplied is left visible rather than blanked, so both failures are findable on screen. Components inject the service and call `t()`; there is no translate pipe. `DECISIONS.md` 058 has the reasoning and names `@ngx-translate/core` as the escape hatch if a second locale ever arrives.
2. **CSS logical properties only** — `margin-inline-start`, `padding-inline-end`, `text-align: start`. Never `left` or `right` for layout.

Tailwind supports the logical variants (`ms-4`, `me-2`, `text-start`). Use them from the first component.

---

## Accessibility floor

Not a full audit, but non-negotiable: every image has meaningful `alt` (use `display_name`), every icon-only button has `aria-label`, focus is visible, and the whole app is keyboard-navigable. Playwright's `getByRole` locators depend on this — good accessibility directly produces stable tests.

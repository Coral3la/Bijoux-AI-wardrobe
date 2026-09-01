import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { TripsApi } from '../../core/api/trips.api';
import { I18nService, Params } from '../../core/i18n/i18n.service';
import { Condition, roleOf } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import { TripDay, TripDetail } from '../../shared/models/trip.model';
import { AuthoredLine } from '../../shared/ui/authored-line';
import { packErrorKey, packStatus } from './pack-wait';
import { PackingList } from './packing-list';
import { StillWorn, TripLook } from './trip-look';

// Local to this screen rather than in `enums.ts`, which mirrors `app/enums.py`
// value for value: a glyph has no counterpart on the server and never will.
// Every one of them is decoration — `aria-hidden` in the template, with the
// condition's own `vocabulary.condition.*` string carrying the meaning — so a
// reader who gets no emoji loses nothing.
const CONDITION_GLYPH: Readonly<Record<Condition, string>> = {
  clear: '☀',
  partly_cloudy: '⛅',
  cloudy: '☁',
  fog: '🌫',
  drizzle: '🌦',
  rain: '🌧',
  snow: '❄',
  thunderstorm: '⛈',
};

// The Atelier pill, the third one written out at a call site rather than taken
// from `appButton` — `look-request-form.ts` has the first and
// `saved-looks.page.ts` the second. 221 recorded why the shared directive is
// still pre-Atelier: converting it reaches every screen in the product, and a
// trips pass is not the commit that gets to do that. DECISIONS.md 221, 222.
const ACTION =
  'inline-flex min-h-11 items-center justify-center gap-x-2 rounded-full border px-6 text-center text-[11px] font-medium tracking-[0.22em] uppercase disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

// Two branches and no table, unlike the pack path's seven. `GET /trips/{id}`
// documents one code of its own — 404 `not_found`, which is the same answer for
// another account's trip as for one that never existed — and `401` is the
// interceptor's, which redirects before this ever runs.
export function tripLoadErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as { code?: string } | null)?.code;
    // The status is read beside the code, and only here: a 404 that never
    // reached the application carries no body to hold one, and it is the same
    // fact about the same URL. A malformed id is FastAPI's 422 rather than a
    // 404 — the path parameter is typed as a UUID — and falls to the general
    // message, which 04-API-SPEC.md's failure list does not mention.
    if (code === 'not_found' || error.status === 404) {
      return 'trip.error.notFound';
    }
  }
  return 'trip.error.load';
}

// Five documented codes and four keys, and the two absences are the table.
//
// `wardrobe_too_small` does **not** reuse `trip.error.wardrobeTooSmall`, which
// says *eight*: the swap threshold is six, because it runs the single-day rule
// order where rule 11 — no two looks alike — never runs, so eight would refuse a
// look the model can build (DECISIONS.md 209). One code, two numbers, two
// sentences. `stylist_failed` does not reuse the pack's either, for
// DECISIONS.md 207's reason exactly one screen along: *"We couldn't pack this
// trip"* under a trip that is visibly packed, said in answer to a tap on one
// shoe, is the wrong sentence.
//
// `validation_error` is deliberately unmapped and falls to the general line. It
// is reachable only by naming a day this trip does not have, which no correct
// client can build — the days come from the trip on screen — and a bare 422 from
// the request schema carries FastAPI's `detail` rather than a `code` anyway.
// `pack-wait.ts` omits `home_location_missing` on the same rule.
const SWAP_ERROR_KEYS: Readonly<Record<string, string>> = {
  item_not_in_look: 'trip.error.itemNotInLook',
  wardrobe_too_small: 'trip.error.swapWardrobeTooSmall',
  locked_unavailable: 'trip.error.lockedUnavailable',
  stylist_failed: 'trip.error.swapStylistFailed',
  not_found: 'trip.error.notFound',
};

// The code alone, never the status — where `tripLoadErrorKey` reads both. That
// one is a `GET`, where a bare 404 with no body really is the trip missing; a
// bare 404 on a `POST` to a route that exists is infrastructure, and telling the
// user their trip was deleted would be a worse guess than saying the swap
// failed.
export function swapErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as { code?: string } | null)?.code;
    if (code !== undefined && code in SWAP_ERROR_KEYS) {
      return SWAP_ERROR_KEYS[code];
    }
  }
  return 'trip.error.swapGeneral';
}

// The three things the itinerary holds *per day* rather than per trip, and they
// are three separate types because they answer at three different moments: the
// swap in flight, the sentence a finished swap left behind, and the message a
// failed one did. Every one of them carries the day it belongs to, because every
// day is on screen at once and a value held without its day would print under
// all of them. DECISIONS.md 222.
interface DaySwap {
  readonly day: number;
  readonly itemId: string;
}

interface DayStillWorn extends StillWorn {
  readonly day: number;
}

interface DaySwapError {
  readonly day: number;
  readonly key: string;
}

// One day of the itinerary, already joined to its look and already matched to
// whichever of the three per-day signals is about it. Computed rather than
// resolved by four method calls in the template: the matching is one rule and it
// is written once here, where the alternative is the same comparison spelled out
// beside four bindings inside a loop.
interface ItineraryDay {
  readonly day: TripDay;
  readonly look: Look | null;
  readonly swappingItemId: string | null;
  readonly stillWorn: StillWorn | null;
  readonly errorKey: string | null;
}

// Which days still wear the garment that just left one, read off the response
// rather than off what was on screen a moment ago: the swap answers the whole
// trip, so this is the same list the packing list below is built from and the
// two cannot disagree. The swapped day cannot appear — rule 8 refuses a look
// containing an excluded id, and the server excludes the replaced garment
// itself — so it is not special-cased here.
function stillWornDays(detail: TripDetail, itemId: string): number[] {
  const looks = new Map(detail.looks.map((look) => [look.id, look]));
  const days: number[] = [];
  for (const day of detail.trip.days) {
    if (day.look_id !== null && looks.get(day.look_id)?.items.some((item) => item.id === itemId)) {
      days.push(day.day);
    }
  }
  return days;
}

@Component({
  selector: 'app-trip-detail-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AuthoredLine, PackingList, TripLook],
  template: `
    <!-- 820px and no gap on the column. The Itinerary is a page read top to
         bottom rather than a stack of regions, so the rhythm is carried by each
         day's own padding and the hairline that closes it — a container gap
         would add a second distance between a rule and the section under it.
         DECISIONS.md 222. -->
    <main class="mx-auto flex w-full max-w-[820px] flex-col px-6 pt-hero pb-region md:px-14">
      @if (detail(); as loaded) {
        <header class="flex flex-col gap-1.5 border-b border-line pb-5">
          <p class="font-mono text-[11px] tracking-[0.18em] text-ink-soft uppercase">
            {{ captionLine() }}
          </p>
          <!-- The content face, not font-display, and the picked mockup drew it
               in the serif. The destination is a place name off the geocoder and
               Cormorant Garamond is latin-subset exactly as Fraunces was, so a
               non-Latin one would fall back per character and render in two
               faces on one line. What content gains in a redesign is size and
               leading, never a face — so it is 56px at the widths that hold it.
               DECISIONS.md 071 names this screen; the spec asserts the absent
               class rather than trusting this comment. -->
          <h1
            class="font-sans text-[40px] leading-[1] font-light tracking-[-0.02em] md:text-[56px]"
          >
            {{ loaded.trip.destination }}
          </h1>
          <p class="font-mono text-[13px] tracking-[0.06em] text-ink-muted tabular-nums">
            {{
              i18n.t('trip.view.dates', {
                start: loaded.trip.start_date,
                end: loaded.trip.end_date,
              })
            }}
          </p>
          <!-- The line the feature lands on, and it is two sentences rather than
               one composed string. The first is ours throughout and is looked up
               whole; the second names a garment the model wrote, so it goes
               through AuthoredLine and only the name leaves the prose face. The
               gap between them is the flex row's, not a text node — sibling
               elements have their whitespace collapsed away. DECISIONS.md 071,
               213, 222. -->
          <p
            class="mt-2 flex max-w-[60ch] flex-wrap items-baseline gap-x-2 font-prose text-base text-ink italic"
          >
            <span>{{ summaryLine() }}</span>
            @if (reuseLine(); as clause) {
              <app-authored-line
                key="trip.view.reuse"
                [params]="clause.params"
                [content]="clause.content"
              />
            }
          </p>
        </header>

        <!-- Every day, in date order, one section each. The tab strip that stood
             here selected one of them and hid the rest, which made a five-day
             trip four things the reader had to go and find; the trip is a
             journey and it now reads as one. DECISIONS.md 222. -->
        @for (entry of itinerary(); track entry.day.day) {
          <article
            class="flex flex-col gap-4 border-b border-line py-10 last-of-type:border-line-strong"
          >
            <div class="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
              <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <!-- The kicker carries the date the tab used to. DECISIONS.md
                     206 refuses a date formatter on this screen, so the day is
                     named by its number and dated by the ISO string the server
                     sent — and both are numerals, which is what puts the whole
                     line in the mono face. -->
                <span class="font-mono text-[11px] tracking-[0.18em] text-ink-soft uppercase">
                  {{ i18n.t('trip.view.day.kicker', { day: entry.day.day, date: entry.day.date }) }}
                </span>
                @if (entry.look; as look) {
                  <!-- The look's own title, written by the model, so the content
                       face at the direction's size. It is the page's to draw
                       rather than the look component's because it shares a
                       baseline with the day number and the weather, and that row
                       has to exist for a day whose look was detached.
                       DECISIONS.md 071, 222. -->
                  <h2 class="font-sans text-[26px] leading-tight">{{ look.title }}</h2>
                }
              </div>
              <!-- The glyph is decoration and says so; the condition and the
                   occasion are both closed vocabulary this project wrote, so
                   they are one authored key with the dot inside it rather than
                   two spans and a separator this template invented. The reading
                   leaves the italic for the mono face, which is the rule every
                   converted screen applies to a number. DECISIONS.md 218, 222. -->
              <p
                class="flex flex-wrap items-baseline gap-x-2 font-prose text-[15px] text-ink-muted italic"
              >
                <span class="text-base not-italic" aria-hidden="true">{{ glyph(entry.day) }}</span>
                <span class="font-mono text-[13px] text-ink tabular-nums not-italic">
                  {{ i18n.t('trip.view.temp', { temp: temperature(entry.day) }) }}
                </span>
                <span>{{ weatherLine(entry.day) }}</span>
              </p>
            </div>

            @if (entry.look; as look) {
              <!-- What is passed down is facts and what comes back is one
                   garment: the page owns the trip, so it owns the arithmetic
                   over every day of it — including which day each of the three
                   per-day signals is about. -->
              <app-trip-look
                [look]="look"
                [swappingItemId]="entry.swappingItemId"
                [busy]="isSwapping()"
                [stillWorn]="entry.stillWorn"
                [errorKey]="entry.errorKey"
                (swap)="swapItem(entry.day.day, $event)"
              />
            } @else {
              <!-- A day with no look, which is a real state rather than an error:
                   a repack detaches a look that was saved, rated or worn instead
                   of deleting it, and the day it belonged to keeps its forecast
                   and loses its outfit. Flat prose on the canvas rather than a
                   raised card — a gap in an itinerary is a quiet day, not an
                   object. AUDITS.md O-32, DECISIONS.md 200, 222. -->
              <p class="font-prose text-base text-ink-muted italic">
                {{ i18n.t('trip.view.day.noLook') }}
              </p>
            }
          </article>
        }

        <app-packing-list class="block pt-hero" [items]="packingItems()" />

        <div class="mt-region flex flex-col gap-group">
          <!-- Above the actions rather than in place of the trip, which is
               DECISIONS.md 200's ordering made visible: pack_trip runs before
               anything is detached or deleted, so a repack that fails costs
               nothing and the trip the user is looking at is still the trip they
               have. A screen blanked by the failure would say the opposite. -->
          @if (actionError(); as key) {
            <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
          }

          @if (repacking()) {
            <p class="font-prose text-base text-ink-muted italic" role="status" aria-live="polite">
              {{ i18n.t(statusKey()) }}
            </p>
          }

          <div class="flex flex-wrap items-center gap-3 border-t border-line pt-5">
            <!-- Unguarded, unlike its neighbour, and the asymmetry is the point:
                 a repack detaches a look that was saved, rated or worn rather
                 than destroying it (DECISIONS.md 200), and /saved filters on
                 is_saved alone — so a saved look survives this button and is
                 still on the screen that lists it. There is nothing to warn
                 about, and a confirmation step for a reversible act teaches the
                 user to click through the one that is not. -->
            <button
              type="button"
              (click)="repack()"
              [disabled]="repacking() || deleting() || isSwapping()"
              [class]="repackClass"
            >
              {{ i18n.t('trip.repack.action') }}
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="h-3 w-3"
                aria-hidden="true"
              >
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>

            <!-- Two deliberate clicks, not window.confirm and not a modal, as
                 item-detail.page.ts does it — DECISIONS.md 126 records why the
                 gate's confirm() makes a confirm-guarded delete read as tested
                 and never run. The armed label carries the cascade, because
                 DELETE /trips/{id} destroys the looks a repack would have kept
                 and this is the only place a user could learn that. -->
            <!-- The paint carries the arming, and it has to: the two-step gate
                 is only visible if the second press looks different from the
                 first. Idle is the danger colour on a hairline and armed is the
                 same colour filled — one token, two weights, and the token
                 itself is untouched by this pass. -->
            <button
              type="button"
              (click)="onDelete()"
              (blur)="disarm()"
              [disabled]="repacking() || deleting() || isSwapping()"
              [class]="deleteClass()"
            >
              {{ deleteLabel() }}
            </button>
          </div>
        </div>
      } @else if (errorKey(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      } @else {
        <!-- Prose, not a skeleton, and that is the decision rather than the
             leftover: this screen's shape depends on the response — how many
             days, whether each has a look — so a skeleton would promise a
             layout the trip may not have. It defers like the other two.
             DECISIONS.md 217. -->
        <p
          class="animate-deferred font-prose text-base text-ink-muted italic"
          role="status"
          aria-live="polite"
        >
          {{ i18n.t('trip.view.loading') }}
        </p>
      }
    </main>
  `,
})
export class TripDetailPage {
  protected readonly i18n = inject(I18nService);
  private readonly api = inject(TripsApi);
  private readonly router = inject(Router);

  // The snapshot, as item detail reads it: nothing changes the id under this
  // component, because every route into it is a fresh navigation — from the
  // form after a pack, or from the address bar.
  private readonly id = inject(ActivatedRoute).snapshot.paramMap.get('id') ?? '';

  protected readonly detail = signal<TripDetail | null>(null);
  protected readonly errorKey = signal<string | null>(null);

  // A second error signal rather than a second message in `errorKey`, which is
  // the load's: that one is a screen with nothing on it, and this one is a line
  // above a trip that is still there. Folding them together would make the
  // template choose between rendering a trip and rendering its failure.
  protected readonly actionError = signal<string | null>(null);
  protected readonly repacking = signal(false);
  protected readonly deleting = signal(false);
  protected readonly armed = signal(false);

  // A third error signal, and the reasoning that split the first two applies
  // again: `errorKey` is a screen with nothing on it, `actionError` is a line
  // above a trip whose repack or delete failed, and this one is a line inside
  // the day whose swap failed. Rendering a failed swap under the actions row
  // would say the trip's action failed when one day's did.
  protected readonly swapError = signal<DaySwapError | null>(null);

  // The day and the garment, not a boolean — the wait is drawn on one tile of
  // one section. It was the id alone until the Itinerary put every day on
  // screen, at which point a garment worn on three days would have spun on all
  // three from one press.
  protected readonly swapping = signal<DaySwap | null>(null);
  protected readonly isSwapping = computed(() => this.swapping() !== null);

  protected readonly stillWorn = signal<DayStillWorn | null>(null);

  // Per day, because a rejection is about a day's weather and its occasion: the
  // shoe that is wrong for Tuesday's rain is the right answer for Thursday. Held
  // here and sent nowhere else — the server cannot rebuild this list, because
  // the looks that carried those rejections were replaced by the swaps that
  // rejected them. Fresh on every mount: the id comes from a route snapshot, so
  // a back button is a new component and a new Map without anything being said.
  private readonly excluded = signal<ReadonlyMap<number, ReadonlySet<string>>>(new Map());

  protected readonly statusKey = packStatus(this.repacking);

  protected readonly repackClass = `${ACTION} border-ink text-ink`;

  private readonly looksById = computed(() => {
    const looks = new Map<string, Look>();
    for (const look of this.detail()?.looks ?? []) {
      looks.set(look.id, look);
    }
    return looks;
  });

  // Every item the response carries, from the looks alone: the trip object
  // holds ids and no rows, and 04-API-SPEC.md's own acceptance criterion is
  // that every packed item appears in at least one look. This map is what makes
  // the packing list and the reuse clause renderable without a second request.
  private readonly itemsById = computed(() => {
    const items = new Map<string, Item>();
    for (const look of this.detail()?.looks ?? []) {
      for (const item of look.items) {
        items.set(item.id, item);
      }
    }
    return items;
  });

  // The whole trip, in the order the server sent the days, with each day joined
  // to its look and to whichever of the three per-day signals names it.
  protected readonly itinerary = computed<readonly ItineraryDay[]>(() => {
    const looks = this.looksById();
    const swapping = this.swapping();
    const worn = this.stillWorn();
    const failure = this.swapError();

    return (this.detail()?.trip.days ?? []).map((day) => ({
      day,
      // Two ways to have no look and one rendering: the day carries null, or it
      // carries an id the response did not hydrate. The second cannot happen
      // from this endpoint and the type permits it, so it is folded into the
      // first rather than given a branch that could never be reached.
      look: day.look_id === null ? null : (looks.get(day.look_id) ?? null),
      swappingItemId: swapping !== null && swapping.day === day.day ? swapping.itemId : null,
      stillWorn: worn !== null && worn.day === day.day ? worn : null,
      errorKey: failure !== null && failure.day === day.day ? failure.key : null,
    }));
  });

  // Ids that hydrate to nothing are dropped rather than rendered as a blank
  // row. It takes a detached look to produce one — the item is still packed and
  // the row describing it left with the look — and a checkbox beside no name is
  // not something a user can act on.
  protected readonly packingItems = computed<readonly Item[]>(() => {
    const items = this.itemsById();
    return (this.detail()?.trip.packing_list.item_ids ?? [])
      .map((id) => items.get(id))
      .filter((item): item is Item => item !== undefined);
  });

  // The counts, as one whole sentence rather than as a template joining two.
  // Pluralised on the looks alone, which is 4.5's reading unchanged: item_count
  // cannot be one, because a wearable look is at least a top, a bottom and
  // shoes, whereas a one-day trip really does pack one look.
  protected readonly summaryLine = computed(() => {
    const summary = this.detail()?.trip.packing_list.reuse_summary;
    if (summary === undefined) {
      return '';
    }
    return summary.look_count === 1
      ? this.i18n.t('trip.view.summary.one', { items: summary.item_count })
      : this.i18n.t('trip.view.summary.other', {
          items: summary.item_count,
          looks: summary.look_count,
        });
  });

  // The two dictionaries AuthoredLine takes, held in a computed rather than
  // built in the template: a fresh object literal on every binding would make
  // the component's own segments computed re-run on every change detection.
  // `weather-strip.ts` hands its line down the same way.
  //
  // Three ways to have no clause and one answer to all of them: nothing is worn
  // twice, the garment was never named, or the look that wore it was detached
  // and its row left with it. The alternative is a sentence reading "You'll
  // wear Untitled item on 3 days", which names nothing and takes the line with
  // it.
  protected readonly reuseLine = computed<{ params: Params; content: Params } | null>(() => {
    const reused = this.detail()?.trip.packing_list.reuse_summary.most_reused;
    if (reused === undefined || reused === null) {
      return null;
    }
    const name = this.itemsById().get(reused.item_id)?.display_name;
    if (name === undefined || name === null) {
      return null;
    }
    // "wear" rather than the specification's "appear", and that is the whole
    // reason for the rewording: display_name is written by the model and its
    // grammatical number is unknowable here, so "the jeans appear" and "the
    // blazer appears" cannot both come out of one template. The verb after
    // "you'll" is invariant.
    return { params: { days: reused.days }, content: { name } };
  });

  // Pluralised because a one-day trip is legal — `tripProblem` refuses an end
  // before a start and nothing refuses the two being equal — and "Trip · 1 days"
  // is the sentence a single interpolated key would have shipped.
  protected readonly captionLine = computed(() => {
    const days = this.detail()?.trip.days.length ?? 0;
    return days === 1
      ? this.i18n.t('trip.view.caption.one')
      : this.i18n.t('trip.view.caption.other', { days });
  });

  protected readonly deleteLabel = computed(() => {
    if (this.deleting()) {
      return this.i18n.t('trip.delete.doing');
    }
    return this.armed() ? this.i18n.t('trip.delete.armed') : this.i18n.t('trip.delete.idle');
  });

  protected readonly deleteClass = computed(() =>
    this.armed()
      ? `${ACTION} border-danger bg-danger text-canvas`
      : `${ACTION} border-line text-danger`,
  );

  constructor() {
    this.api.get(this.id).subscribe({
      next: (detail) => this.detail.set(detail),
      error: (failure: unknown) => this.errorKey.set(tripLoadErrorKey(failure)),
    });
  }

  protected repack(): void {
    // The disabled binding is the visible guard and this one is the real one:
    // a signal write schedules change detection rather than doing it, so two
    // presses landing in the same frame both see an enabled button. Neither
    // clause can be reached from the rendered screen, which is why the mutation
    // pass leaves both of them standing and the tests assert `disabled`.
    if (this.repacking() || this.deleting() || this.isSwapping()) {
      return;
    }
    // The repack disarms the delete, which is the "any other interaction" half
    // of 126's rule: an armed delete surviving the twenty seconds this button
    // costs is a second click landing on a control the user stopped thinking
    // about two screens of status lines ago.
    this.disarm();
    this.repacking.set(true);
    this.actionError.set(null);
    // The exclusions go with the looks they were exclusions from. A repack
    // rebuilds every day against a fresh forecast, so a garment rejected for
    // Tuesday's rain is being judged against different weather the moment this
    // returns, and carrying the list across would silently narrow a plan the
    // user asked to have made again.
    this.clearSwapState();

    this.api.repack(this.id).subscribe({
      // The two keys are copied across rather than the response stored whole.
      // `PackResponse` carries `missing_pieces` and `TripDetail` does not, and
      // structural typing would let the wider object into the narrower signal
      // without a word — leaving a field on this screen's model that nothing
      // renders and `GET /trips/{id}` never answers with.
      next: (response) => {
        this.detail.set({ trip: response.trip, looks: response.looks });
        this.repacking.set(false);
      },
      error: (failure: unknown) => {
        this.actionError.set(packErrorKey(failure, 'trip.error.repackGeneral'));
        this.repacking.set(false);
      },
    });
  }

  protected onDelete(): void {
    if (this.repacking() || this.deleting() || this.isSwapping()) {
      return;
    }

    if (!this.armed()) {
      this.armed.set(true);
      return;
    }
    this.armed.set(false);
    this.deleting.set(true);
    this.actionError.set(null);

    this.api.remove(this.id).subscribe({
      next: () => {
        this.deleting.set(false);
        void this.router.navigate(['/wardrobe']);
      },
      error: () => {
        this.deleting.set(false);
        this.actionError.set('trip.error.delete');
      },
    });
  }

  protected disarm(): void {
    this.armed.set(false);
  }

  // One garment on one day, and the day arrives from the section the badge was
  // pressed in rather than from a selection: there is no selection any more. No
  // preview and no confirmation — the swap *is* the answer, and a second tap on
  // the tile that came back is the user saying "not that one either", which is
  // what makes the exclusions a conversation rather than a form. The cost is
  // that there is no undo, which is recorded rather than mitigated
  // (DECISIONS.md 210).
  protected swapItem(day: number, item: Item): void {
    // The visible guard is the badges' own `disabled`; this is the real one, for
    // repack()'s reason — a signal write schedules change detection rather than
    // doing it, so two presses in one frame both see an enabled button.
    if (this.isSwapping() || this.repacking() || this.deleting()) {
      return;
    }
    // A dress has no role and therefore no badge, so this is unreachable from
    // the rendered screen — and it is a return rather than a `!` because
    // `roleOf` is the only thing standing between a dress and a request the
    // server would answer `422` to.
    const role = roleOf(item.category);
    if (role === undefined) {
      return;
    }
    // 126's "any other interaction", which the badge is: an armed delete
    // surviving a swap is a second press landing on a control the user stopped
    // thinking about. A badge on any day of the trip disarms it.
    this.disarm();

    // The tapped garment joins the day's exclusions before the request goes out,
    // and stays there if it fails. The server appends it for this call anyway;
    // what this list is for is the *next* tap on this day.
    const excluded = new Set(this.excluded().get(day) ?? []).add(item.id);
    this.excluded.update((current) => new Map(current).set(day, excluded));

    this.swapping.set({ day, itemId: item.id });
    // Both belong to the swap that has just been replaced by this one. They are
    // cleared rather than kept per day: only one swap runs at a time, so there
    // is only ever one of each, and a sentence about Monday left standing under
    // Monday while Thursday is being rebuilt answers a press nobody remembers.
    this.swapError.set(null);
    this.stillWorn.set(null);

    this.api
      .swap(this.id, {
        day,
        item_id: item.id,
        replace_role: role,
        exclude_item_ids: [...excluded],
      })
      .subscribe({
        next: (detail) => {
          this.detail.set(detail);
          // Named from the garment that was tapped rather than from the
          // response, which no longer holds it on this day. `Untitled item`
          // stands here where DECISIONS.md 206 dropped the header's reuse
          // clause over it: that sentence has to name a garment the reader has
          // not touched, and this one answers a press on a specific tile — the
          // antecedent is the press, and dropping the line would lose the days,
          // which are what STAGE-4 4.6a asks for.
          const days = stillWornDays(detail, item.id);
          this.stillWorn.set(days.length === 0 ? null : { day, name: this.name(item), days });
          this.swapping.set(null);
        },
        // The day's look is left standing. A failed swap changed nothing on the
        // server, so blanking the look would be the screen disagreeing with the
        // sentence underneath it.
        error: (failure: unknown) => {
          this.swapError.set({ day, key: swapErrorKey(failure) });
          this.swapping.set(null);
        },
      });
  }

  private clearSwapState(): void {
    this.excluded.set(new Map());
    this.swapError.set(null);
    this.stillWorn.set(null);
  }

  private name(item: Item): string {
    return item.display_name ?? this.i18n.t('item.untitled');
  }

  // The day's high, which is what this project already means by "the
  // temperature": the weather strip prints it, summarize_forecast prints it to
  // the model, and DECISIONS.md 142 settled it there. temp_min_c is on the wire
  // and goes unrendered — a range on this line would be two numbers where the
  // sentence beside them needs one.
  protected temperature(day: TripDay): number {
    return Math.round(day.temp_max_c);
  }

  protected glyph(day: TripDay): string {
    return CONDITION_GLYPH[day.condition];
  }

  // Both halves are closed vocabulary this project wrote, so the whole line is
  // authored and the dot between them lives in the string table rather than in
  // this file. Neither value needs the guard `saved-looks.page.ts` puts in front
  // of an occasion: `TripDay` types both as enums, and a value outside either
  // vocabulary is a 500 on the way out of `TripResponse` and cannot arrive here.
  protected weatherLine(day: TripDay): string {
    return this.i18n.t('trip.view.day.weather', {
      condition: this.i18n.t(`vocabulary.condition.${day.condition}`),
      occasion: this.i18n.t(`vocabulary.occasion.${day.occasion}`),
    });
  }
}

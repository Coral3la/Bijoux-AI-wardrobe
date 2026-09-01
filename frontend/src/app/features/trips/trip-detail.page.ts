import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { TripsApi } from '../../core/api/trips.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { Condition, roleOf } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import { TripDay, TripDetail } from '../../shared/models/trip.model';
import { Button } from '../../shared/ui/button';
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
  imports: [Button, PackingList, TripLook],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-region px-6 pt-hero pb-region">
      @if (detail(); as loaded) {
        <header class="flex flex-col gap-1">
          <p class="text-xs font-medium tracking-widest text-ink-soft uppercase">
            {{ captionLine() }}
          </p>
          <!-- Body face, not font-display. The destination is a place name off
               the geocoder, and Fraunces is latin-subset, so a non-Latin one
               would fall back per character and render in two faces on one
               line. DECISIONS.md 071 names this screen, and the spec asserts
               the absent class rather than trusting the comment. -->
          <h1 class="text-3xl leading-tight">{{ loaded.trip.destination }}</h1>
          <p class="font-display text-lg text-ink-muted tabular-nums">
            {{
              i18n.t('trip.view.dates', {
                start: loaded.trip.start_date,
                end: loaded.trip.end_date,
              })
            }}
          </p>
          <!-- The line the feature lands on, and it is here rather than under
               the packing list where 05-FRONTEND-SPEC.md first drew it: the
               counts are the confirmation sentence 4.5 already wrote, word for
               word, and splitting one sentence across two ends of a screen
               costs more than either placement gains. -->
          <p class="text-sm font-medium">{{ headerLine() }}</p>
        </header>

        <!-- Grouped: the strip selects what renders under it, which is the
             label-to-content relationship the group rung is for. At region
             distance the tabs read as a section rather than as a control.
             DECISIONS.md 212. -->
        <div class="flex flex-col gap-group">
          <!-- Buttons with aria-pressed rather than a tablist, matching the
               occasion chips one screen over. A real tablist owes the reader
               arrow-key roving and a tabpanel relationship; this is a filter over
               one region, which is what the chips are too. -->
          <div
            class="flex flex-nowrap gap-2 overflow-x-auto pb-1"
            role="group"
            [attr.aria-label]="i18n.t('trip.view.days')"
          >
            @for (day of loaded.trip.days; track day.day) {
              <button
                type="button"
                (click)="select(day.day)"
                [attr.aria-pressed]="selectedDay() === day.day"
                [class]="tabClass(selectedDay() === day.day)"
              >
                <!-- Four lines, and none of them is a weekday: DECISIONS.md
                     206 refuses a date formatter on this screen, so the day is
                     named by its number and dated by the ISO string the server
                     sent. The display face is legal on "Day 3" — it is a word
                     this project wrote and a numeral (071). -->
                <span [class]="tabDayClass()">
                  {{ i18n.t('trip.day.legend', { day: day.day }) }}
                </span>
                <span [class]="tabDetailClass(selectedDay() === day.day)">{{ day.date }}</span>
                <span class="text-lg" aria-hidden="true">{{ glyph(day) }}</span>
                <span [class]="tabDetailClass(selectedDay() === day.day)">
                  {{ i18n.t('trip.view.temp', { temp: temperature(day) }) }}
                </span>
                <!-- The glyph above is decoration, so the condition is named
                     here or it is named nowhere. -->
                <span class="sr-only">{{ i18n.t('vocabulary.condition.' + day.condition) }}</span>
              </button>
            }
          </div>

          @if (selectedLook(); as look) {
            <!-- The article moved into TripLook at 4.6a, which is where the badge,
                 the per-tile wait and the still-worn line live. What is passed
                 down is facts and what comes back is one garment: the page owns
                 the trip, so it owns the arithmetic over every day of it. -->
            <app-trip-look
              [look]="look"
              [swappingItemId]="swappingItemId()"
              [stillWorn]="stillWorn()"
              [errorKey]="swapError()"
              (swap)="swapItem($event)"
            />
          } @else {
            <!-- A day with no look, which is a real state rather than an error:
                 a repack detaches a look that was saved, rated or worn instead of
                 deleting it, and the day it belonged to keeps its forecast and
                 loses its outfit. AUDITS.md O-32, DECISIONS.md 200. -->
            <p class="rounded-xl bg-surface-elevated p-5 text-sm text-ink-muted">
              {{ i18n.t('trip.view.day.noLook') }}
            </p>
          }
        </div>

        <app-packing-list [items]="packingItems()" />

        <!-- Above the actions rather than in place of the trip, which is
             DECISIONS.md 200's ordering made visible: pack_trip runs before
             anything is detached or deleted, so a repack that fails costs
             nothing and the trip the user is looking at is still the trip they
             have. A screen blanked by the failure would say the opposite. -->
        @if (actionError(); as key) {
          <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
        }

        @if (repacking()) {
          <p class="text-sm text-ink-muted" role="status" aria-live="polite">
            {{ i18n.t(statusKey()) }}
          </p>
        }

        <div class="flex flex-wrap items-center gap-3 border-bs border-line pt-4">
          <!-- Unguarded, unlike its neighbour, and the asymmetry is the point:
               a repack detaches a look that was saved, rated or worn rather
               than destroying it (DECISIONS.md 200), and /saved filters on
               is_saved alone — so a saved look survives this button and is
               still on the screen that lists it. There is nothing to warn
               about, and a confirmation step for a reversible act teaches the
               user to click through the one that is not. -->
          <button
            appButton
            variant="secondary"
            type="button"
            (click)="repack()"
            [disabled]="repacking() || deleting() || swapping()"
            class="disabled:opacity-50"
          >
            {{ i18n.t('trip.repack.action') }}
          </button>

          <!-- Two deliberate clicks, not window.confirm and not a modal, as
               item-detail.page.ts does it — DECISIONS.md 126 records why the
               gate's confirm() makes a confirm-guarded delete read as tested
               and never run. The armed label carries the cascade, because
               DELETE /trips/{id} destroys the looks a repack would have kept
               and this is the only place a user could learn that. -->
          <!-- The variant carries the arming rather than a pair of class
               bindings over a fixed one: the two-step gate is only visible if
               the second press looks different from the first, and one owner
               for that paint cannot fall out of step with the signal. -->
          <button
            appButton
            [variant]="armed() ? 'danger' : 'secondary'"
            type="button"
            (click)="onDelete()"
            (blur)="disarm()"
            [disabled]="repacking() || deleting() || swapping()"
            class="disabled:opacity-50"
          >
            {{ deleteLabel() }}
          </button>
        </div>
      } @else if (errorKey(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      } @else {
        <!-- Prose, not a skeleton, and that is the decision rather than the
             leftover: this screen's shape depends on the response — how many
             days, whether each has a look — so a skeleton would promise a
             layout the trip may not have. It defers like the other two.
             DECISIONS.md 217. -->
        <p class="animate-deferred font-prose text-base" role="status" aria-live="polite">
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
  // the look whose swap failed. Rendering a failed swap under the packing list
  // would say the trip's action failed when one day's did.
  protected readonly swapError = signal<string | null>(null);

  // The id of the tile waiting, not a boolean — the wait is drawn on one tile.
  protected readonly swappingItemId = signal<string | null>(null);
  protected readonly swapping = computed(() => this.swappingItemId() !== null);

  protected readonly stillWorn = signal<StillWorn | null>(null);

  // Per day, because a rejection is about a day's weather and its occasion: the
  // shoe that is wrong for Tuesday's rain is the right answer for Thursday. Held
  // here and sent nowhere else — the server cannot rebuild this list, because
  // the looks that carried those rejections were replaced by the swaps that
  // rejected them. Fresh on every mount: the id comes from a route snapshot, so
  // a back button is a new component and a new Map without anything being said.
  private readonly excluded = signal<ReadonlyMap<number, ReadonlySet<string>>>(new Map());

  protected readonly statusKey = packStatus(this.repacking);

  // The ordinal, not the index, because that is what the day carries and what
  // the join is keyed by. Day 1 on arrival even when day 1 has no look: the
  // strip is the trip's calendar, and an opening selection that depended on
  // which days happened to keep a look would leave the user working out why
  // day 3 is the one lit up.
  protected readonly selectedDay = signal(1);

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

  protected readonly selectedLook = computed(() => {
    const day = this.detail()?.trip.days.find((candidate) => candidate.day === this.selectedDay());
    // Two ways to have no look and one rendering: the day carries null, or it
    // carries an id the response did not hydrate. The second cannot happen from
    // this endpoint and the type permits it, so it is folded into the first
    // rather than given a branch that could never be reached.
    return day?.look_id === undefined || day.look_id === null
      ? null
      : (this.looksById().get(day.look_id) ?? null);
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

  // The counts, then the reuse clause when there is one to make. Composed
  // through a key rather than joined with a separator in code, so the character
  // between the two clauses is a translator's to change.
  protected readonly headerLine = computed(() => {
    const summary = this.detail()?.trip.packing_list.reuse_summary;
    if (summary === undefined) {
      return '';
    }

    // Pluralised on the looks alone, which is 4.5's reading unchanged:
    // item_count cannot be one, because a wearable look is at least a top, a
    // bottom and shoes, whereas a one-day trip really does pack one look.
    const counts =
      summary.look_count === 1
        ? this.i18n.t('trip.packed.counts.one', { items: summary.item_count })
        : this.i18n.t('trip.packed.counts.other', {
            items: summary.item_count,
            looks: summary.look_count,
          });

    const reuse = this.reuseClause();
    return reuse === null ? counts : this.i18n.t('trip.view.headerLine', { counts, reuse });
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

  constructor() {
    this.api.get(this.id).subscribe({
      next: (detail) => this.detail.set(detail),
      error: (failure: unknown) => this.errorKey.set(tripLoadErrorKey(failure)),
    });
  }

  protected select(day: number): void {
    this.selectedDay.set(day);
    // Both belong to the look that was on screen: *"That piece isn't in this
    // day's look"* and *"You'll still wear the shirt on Day 3"* are sentences
    // about a day the reader has just left. The exclusions are not cleared with
    // them — those are per day and keyed by it, so they are still the right
    // answer when the reader comes back.
    this.swapError.set(null);
    this.stillWorn.set(null);
  }

  protected repack(): void {
    // The disabled binding is the visible guard and this one is the real one:
    // a signal write schedules change detection rather than doing it, so two
    // presses landing in the same frame both see an enabled button. Neither
    // clause can be reached from the rendered screen, which is why the mutation
    // pass leaves both of them standing and the tests assert `disabled`.
    if (this.repacking() || this.deleting() || this.swapping()) {
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
    if (this.repacking() || this.deleting() || this.swapping()) {
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

  // One garment on the day on screen. No preview and no confirmation: the swap
  // *is* the answer, and a second tap on the tile that came back is the user
  // saying "not that one either" — which is what makes the exclusions a
  // conversation rather than a form. The cost is that there is no undo, which is
  // recorded rather than mitigated (DECISIONS.md 210).
  protected swapItem(item: Item): void {
    // The visible guard is the badges' own `disabled`; this is the real one, for
    // repack()'s reason — a signal write schedules change detection rather than
    // doing it, so two presses in one frame both see an enabled button.
    if (this.swapping() || this.repacking() || this.deleting()) {
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
    // thinking about.
    this.disarm();

    const day = this.selectedDay();
    // The tapped garment joins the day's exclusions before the request goes out,
    // and stays there if it fails. The server appends it for this call anyway;
    // what this list is for is the *next* tap on this day.
    const excluded = new Set(this.excluded().get(day) ?? []).add(item.id);
    this.excluded.update((current) => new Map(current).set(day, excluded));

    this.swappingItemId.set(item.id);
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
          this.stillWorn.set(days.length === 0 ? null : { name: this.name(item), days });
          this.swappingItemId.set(null);
        },
        // The day's look is left standing. A failed swap changed nothing on the
        // server, so blanking the look would be the screen disagreeing with the
        // sentence underneath it.
        error: (failure: unknown) => {
          this.swapError.set(swapErrorKey(failure));
          this.swappingItemId.set(null);
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
  // and goes unrendered, because a tab wide enough for a range is a tab that
  // fits three days on a phone.
  protected temperature(day: TripDay): number {
    return Math.round(day.temp_max_c);
  }

  protected glyph(day: TripDay): string {
    return CONDITION_GLYPH[day.condition];
  }

  protected tabClass(selected: boolean): string {
    const base =
      'flex min-h-11 min-w-[68px] shrink-0 flex-col items-center gap-0.5 rounded-lg px-3 py-2 text-center focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
    return selected
      ? `${base} bg-accent text-surface`
      : `${base} border border-line-strong bg-surface`;
  }

  protected tabDayClass(): string {
    return 'font-display text-lg font-medium';
  }

  // Faded rather than recoloured on the selected pill: the two detail lines sit
  // on `bg-accent` there, where an ink token would be unreadable and the
  // surface colour at full strength would compete with the day number above it.
  protected tabDetailClass(selected: boolean): string {
    const base = 'text-[10px] tabular-nums';
    return selected ? `${base} opacity-80` : `${base} text-ink-muted`;
  }

  // Three ways to have no clause and one answer to all of them: nothing is worn
  // twice, the garment was never named, or the look that wore it was detached
  // and its row left with it. The alternative is a sentence reading "You'll
  // wear Untitled item on 3 days", which names nothing and takes the header
  // line with it.
  private reuseClause(): string | null {
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
    return this.i18n.t('trip.view.reuse', { name, days: reused.days });
  }
}

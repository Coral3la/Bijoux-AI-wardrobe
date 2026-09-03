import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { MeApi } from '../../core/api/me.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { LocationResult } from '../../shared/models/location.model';
import { OCCASIONS, Occasion, Slot } from '../../shared/models/enums';
import { Chip } from '../../shared/ui/chip';
import { todayInLocalTime } from '../stylist/look-request-form';

// The product bound, not the provider's. `look-request-form.ts` caps a single
// day at `FORECAST_HORIZON_DAYS = 15`, measured against Open-Meteo; a trip is
// capped at 14 because DECISIONS.md 190 keeps one day of margin against a
// horizon that rolls forward daily. The two numbers differ deliberately and are
// bounds on different things — one on a day, one on a trip's last day.
//
// This is the picker copy 190's trade-off predicted: 14 now lives here and in
// `TripPackRequest`'s route with nothing comparing them, which is the fifth
// instance of the drift CONVENTIONS.md's "Limits and units" section records.
export const MAX_TRIP_DAYS = 14;

const DEFAULT_OCCASION: Occasion = 'casual';

// What a newly added evening is for, before anybody picks. 'evening' rather than
// DEFAULT_OCCASION: a user who presses "Add an evening" has said what the slot is
// for, and casual would make every one of them re-pick for nothing. It renders as
// EVENING under EVENING on the trip page, which is the vocabulary collision
// AUDITS.md O-35 already owns and 4.18's dedupe rule collapses.
const EVENING_OCCASION: Occasion = 'evening';

const MIN_QUERY_LENGTH = 2;

export const SEARCH_DEBOUNCE_MS = 300;

const DAY_MS = 86_400_000;

// The caps eyebrow every label on a converted screen is set in. Written once
// here because this form carries six of them — `look-request-form.ts` declares
// the same treatment inline for the three it has, and neither is worth a shared
// export until something outside a form wants one.
const LABEL = 'text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase';

// One day of the trip: what it is for, and what the evening is for if it has
// one. Named after TripDraft, which holds a list of these.
//
// The field names are the two slot values, which is what makes the flattening in
// trips.page.ts a direct mapping rather than a translation. evening: null is the
// no-second-slot state, and it is the point of this shape: a lone evening — which
// TripPackRequest refuses at 4.15 — cannot be built here at all, so the form
// cannot express the body the schema would reject.
export interface TripDayDraft {
  readonly day: Occasion;
  readonly evening: Occasion | null;
}

// What the four controls hold. `destination` is the whole geocoder result
// rather than its name, because the chip has to print "Berlin, Germany" to tell
// the two Berlins apart — only `name` goes on the wire, and the coordinates the
// picker had are thrown away (DECISIONS.md 202: the endpoint geocodes for
// itself). `occasions` is indexed by day, so day N is `occasions[N - 1]`, and
// its length is the length of the trip — one entry per **day** from 4.17, not
// one per look. The wire's flat list is built from it at submit.
export interface TripDraft {
  readonly destination: LocationResult | null;
  readonly start_date: string;
  readonly end_date: string;
  readonly occasions: readonly TripDayDraft[];
  readonly notes: string;
}

// Parsed as UTC rather than local. A bare `YYYY-MM-DD` is UTC midnight in
// JavaScript, and that is what makes the subtraction exact: local midnights
// either side of a daylight-saving change are 23 or 25 hours apart, which
// rounds a fourteen-day trip to thirteen days twice a year.
export function daysInRange(start: string, end: string): number {
  const from = Date.parse(start);
  const to = Date.parse(end);
  if (Number.isNaN(from) || Number.isNaN(to)) {
    return 0;
  }
  return Math.round((to - from) / DAY_MS) + 1;
}

export function tripHorizon(now = new Date()): string {
  const horizon = new Date(now);
  horizon.setDate(horizon.getDate() + MAX_TRIP_DAYS);
  return todayInLocalTime(horizon);
}

function freshDay(): TripDayDraft {
  return { day: DEFAULT_OCCASION, evening: null };
}

function withOccasion(entry: TripDayDraft, slot: Slot, occasion: Occasion): TripDayDraft {
  return slot === 'evening' ? { ...entry, evening: occasion } : { ...entry, day: occasion };
}

// The head is kept, so a user who set day 1 to work and then extends the trip
// still has work on day 1. Padding rather than resetting is the only choice
// that makes the chip rows survive a date change at all.
//
// It keeps evenings with their days for free, and that is the whole reason the
// draft is indexed by day rather than shaped like the wire: an entry carries its
// own evening, so padding the tail and truncating from the end cannot separate
// the two. A flat list of slots would have had to count them.
function resize(occasions: readonly TripDayDraft[], days: number): readonly TripDayDraft[] {
  if (days <= 0) {
    return [];
  }
  if (days === occasions.length) {
    return occasions;
  }
  return Array.from({ length: days }, (_, index) => occasions[index] ?? freshDay());
}

// Casual and today, a one-day trip: the request a user who touches nothing else
// would send, with the chip row already on screen teaching what the form does.
export function newTripDraft(now = new Date()): TripDraft {
  const today = todayInLocalTime(now);
  return {
    destination: null,
    start_date: today,
    end_date: today,
    occasions: [freshDay()],
    notes: '',
  };
}

// The three refusals this form makes before spending a round trip, as an i18n
// key or null. A pure function rather than a method so the page can guard its
// own submit with it — the button is disabled by the same call that draws the
// message, and there is one definition of "this draft is not sendable".
//
// The date checks are in the request schema's own order: an inverted range has
// a negative length, so a length message on it would name a number no client
// could satisfy.
export function tripProblem(draft: TripDraft): string | null {
  if (draft.destination === null) {
    return 'trip.problem.noDestination';
  }
  const days = daysInRange(draft.start_date, draft.end_date);
  if (days < 1) {
    return 'trip.problem.endBeforeStart';
  }
  if (days > MAX_TRIP_DAYS) {
    return 'trip.problem.tooLong';
  }
  return null;
}

@Component({
  selector: 'app-trip-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip],
  template: `
    <!-- The stone panel the stylist's form took at the Ritual pass, for the same
         reason one screen along: this is a standing control rather than a step,
         and a form drawn straight onto the canvas under a page title reads as
         leftover. It is the one raised object on either trip screen — everything
         the detail page draws sits flat. DECISIONS.md 220, 222. -->
    <form class="flex flex-col gap-5 rounded-sm bg-surface-elevated p-6" (submit)="submit($event)">
      <section class="flex flex-col gap-2">
        <h2 [class]="label">{{ i18n.t('trip.destination.label') }}</h2>

        @if (draft().destination; as chosen) {
          <!-- The place, in the content face. It is a name this project did not
               write and Cormorant Garamond is latin-subset — DECISIONS.md 071
               names the trip screen as one of the four surfaces that has to
               apply that rule deliberately. -->
          <div class="flex items-center gap-3 rounded-sm border border-line bg-canvas p-3">
            <p class="font-sans text-sm">
              {{
                i18n.t('trip.destination.result', { name: chosen.name, country: chosen.country })
              }}
            </p>
            <button
              type="button"
              (click)="clearDestination()"
              [attr.aria-label]="i18n.t('trip.destination.clear')"
              class="ms-auto min-h-11 min-w-11 rounded-sm text-ink-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              ×
            </button>
          </div>
        } @else {
          <!-- Enter here searches; it does not pack. A text input inside a form
               submits it on Enter, and a half-typed city name must not spend the
               most expensive call in the project. Profile's line, one screen
               over, for the same reason. -->
          <input
            type="text"
            id="trip_destination"
            [value]="query()"
            (input)="onQuery($event)"
            (keydown.enter)="$event.preventDefault()"
            [placeholder]="i18n.t('trip.destination.placeholder')"
            autocapitalize="words"
            spellcheck="false"
            [class]="fieldClass"
          />

          @if (searching()) {
            <p class="font-prose text-sm text-ink-muted italic" role="status" aria-live="polite">
              {{ i18n.t('trip.destination.searching') }}
            </p>
          }
          @if (searchError()) {
            <p class="text-sm font-medium text-danger">{{ i18n.t('trip.destination.error') }}</p>
          }
          @if (noMatches()) {
            <p class="font-prose text-sm text-ink-muted italic">
              {{ i18n.t('trip.destination.noResults') }}
            </p>
          }

          <!-- Rows on a hairline rather than a stack of filled buttons: the
               results are a list to read down, and five raised tiles inside a
               panel is three levels of surface in one control. -->
          <ul class="flex flex-col">
            @for (result of results(); track result.lat + ':' + result.lon) {
              <li class="border-b border-line last:border-b-0">
                <button
                  type="button"
                  (click)="chooseDestination(result)"
                  class="min-h-11 w-full text-start font-sans text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  {{
                    i18n.t('trip.destination.result', {
                      name: result.name,
                      country: result.country,
                    })
                  }}
                </button>
              </li>
            }
          </ul>
        }
      </section>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div class="flex flex-col gap-2">
          <label for="trip_start" [class]="label">
            {{ i18n.t('trip.startDate.label') }}
          </label>
          <!-- Capped at today + 14 and deliberately not floored. DECISIONS.md
               201 leaves start_date unbounded below on the server, because a
               lower bound on the server's calendar day is a refusal a browser
               east of UTC earns by its timezone — so a floor here would be this
               screen enforcing a rule the API refuses to have. -->
          <input
            type="date"
            id="trip_start"
            [value]="draft().start_date"
            [max]="horizon"
            (change)="chooseStart($event)"
            [class]="fieldClass"
          />
        </div>

        <div class="flex flex-col gap-2">
          <label for="trip_end" [class]="label">
            {{ i18n.t('trip.endDate.label') }}
          </label>
          <input
            type="date"
            id="trip_end"
            [value]="draft().end_date"
            [max]="horizon"
            (change)="chooseEnd($event)"
            [class]="fieldClass"
          />
        </div>
      </div>

      <section class="flex flex-col gap-3">
        <h2 [class]="label">{{ i18n.t('trip.occasions.legend') }}</h2>

        <!-- One row per day, in day order, which is the order the request
             schema requires: it checks that the numbers arrive as 1..n rather
             than merely being a permutation of them, because pack_trip reads
             the tuple positionally.

             Wrapping, where this row scrolled: nothing ever scrolled it for the
             user, and the Atelier chip is small enough that six of them wrap to
             two lines on a phone. Fourteen scrolling rows was the shape that
             made the argument.

             No [attr.aria-pressed] on the chips: the Chip directive announces
             the state from the same input that paints it, and a template
             binding beside it would win silently and be free to disagree. -->
        @for (entry of draft().occasions; track $index; let day = $index) {
          <fieldset class="flex flex-col gap-2">
            <legend class="font-mono text-[10px] tracking-[0.18em] text-ink-soft uppercase">
              {{ i18n.t('trip.day.legend', { day: day + 1 }) }}
            </legend>

            <!-- One block per slot the day has, day first. The chips sit in
                 their own role=group named by the visible sub-label, so a
                 screen reader hears which half of the day it is choosing for;
                 the remove control sits in the header line above them rather
                 than inside the group, beside the label of the thing it
                 removes. -->
            @for (row of slotsOf(entry); track row.slot) {
              <div class="flex items-center gap-2">
                <p
                  [id]="'trip-slot-' + (day + 1) + '-' + row.slot"
                  class="font-mono text-[10px] tracking-[0.18em] text-ink-muted uppercase"
                >
                  {{ i18n.t('trip.slot.' + row.slot) }}
                </p>
                @if (row.slot === 'evening') {
                  <button
                    type="button"
                    (click)="removeEvening(day)"
                    [attr.aria-label]="i18n.t('trip.evening.remove', { day: day + 1 })"
                    class="min-h-11 min-w-11 rounded-sm text-ink-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    ×
                  </button>
                }
              </div>
              <div
                role="group"
                [attr.aria-labelledby]="'trip-slot-' + (day + 1) + '-' + row.slot"
                class="flex flex-wrap items-center gap-1.5"
              >
                @for (candidate of allOccasions; track candidate) {
                  <button
                    appChip
                    type="button"
                    [active]="row.occasion === candidate"
                    (click)="chooseOccasion(day, row.slot, candidate)"
                  >
                    {{ i18n.t('vocabulary.occasion.' + candidate) }}
                  </button>
                }
              </div>
            }

            <!-- Adding and removing are two controls rather than one toggle:
                 the one that destroys sits beside what it destroys, which is
                 the destination chip's × one section up. -->
            @if (entry.evening === null) {
              <button
                type="button"
                (click)="addEvening(day)"
                class="me-auto min-h-11 font-mono text-[10px] tracking-[0.18em] text-ink-muted uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                + {{ i18n.t('trip.evening.add') }}
              </button>
            }
          </fieldset>
        }
      </section>

      <div class="flex flex-col gap-2">
        <label for="trip_notes" [class]="label">
          {{ i18n.t('trip.notes.label') }}
        </label>
        <!-- No length limit, and no counter. TripPackRequest.notes is
             stripped and not length-checked, so a cap here would be a refusal
             the API does not make. -->
        <textarea
          id="trip_notes"
          rows="3"
          [value]="draft().notes"
          [placeholder]="i18n.t('trip.notes.placeholder')"
          (input)="changeNotes($event)"
          class="rounded-sm border border-line bg-canvas px-3 py-2 font-sans text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        ></textarea>
      </div>

      @if (problem(); as key) {
        <p id="trip-problem" class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
      }

      <!-- The Atelier pill, the same one the stylist's form ends in, arrow and
           all. It is written out here rather than taken from appButton for
           221's reason: converting that directive reaches every screen in the
           product. DECISIONS.md 222. -->
      <button
        type="submit"
        [disabled]="problem() !== null"
        [attr.aria-describedby]="problem() === null ? null : 'trip-problem'"
        class="ms-auto inline-flex min-h-11 items-center gap-x-2 rounded-full border border-ink bg-ink px-6 text-[11px] font-medium tracking-[0.22em] text-canvas uppercase disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('trip.submit') }}
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
    </form>
  `,
})
export class TripForm {
  protected readonly i18n = inject(I18nService);
  private readonly api = inject(MeApi);

  // The draft is the page's, not this component's, for the stylist form's
  // reason: this control is unmounted while the request is in flight, and state
  // held here would take the user's occasions and notes down with it every time
  // the endpoint answered 400.
  readonly draft = input.required<TripDraft>();

  readonly draftChanged = output<TripDraft>();
  readonly submitted = output<void>();

  protected readonly allOccasions = OCCASIONS;
  protected readonly horizon = tripHorizon();
  protected readonly label = LABEL;
  protected readonly fieldClass =
    'min-h-11 rounded-sm border border-line bg-canvas px-3 py-2 font-sans text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

  // The type-ahead's own state, and the one thing this component does hold.
  // It is deliberately not in the draft: a half-typed query is not part of the
  // trip, and losing it when the form unmounts costs nothing, because a
  // destination cannot be submitted until it has been chosen — at which point
  // it lives in the draft.
  protected readonly query = signal('');
  protected readonly results = signal<readonly LocationResult[]>([]);
  protected readonly searching = signal(false);
  protected readonly searchError = signal(false);
  private readonly searched = signal(false);

  protected readonly noMatches = computed(
    () => this.searched() && !this.searching() && this.results().length === 0,
  );
  protected readonly problem = computed(() => tripProblem(this.draft()));

  private timer: ReturnType<typeof setTimeout> | null = null;
  // Every search carries the number it was issued with, and an answer whose
  // number is stale is dropped. Debouncing makes two in flight uncommon rather
  // than impossible, and the failure it prevents is a slow "ber" landing on top
  // of a fast "berlin" and offering the wrong five cities.
  private issued = 0;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.stopTimer());
  }

  protected onQuery(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.query.set(value);
    this.searchError.set(false);
    this.stopTimer();

    const trimmed = value.trim();
    // The provider's own floor, transcribed from 04-API-SPEC.md: one character
    // matches nothing and two match only exactly, and shorter than that is a
    // 422, so no request leaves the browser for it.
    if (trimmed.length < MIN_QUERY_LENGTH) {
      this.issued += 1;
      this.searching.set(false);
      this.searched.set(false);
      this.results.set([]);
      return;
    }

    this.timer = setTimeout(() => this.search(trimmed), SEARCH_DEBOUNCE_MS);
  }

  protected chooseDestination(result: LocationResult): void {
    this.query.set('');
    this.results.set([]);
    this.searched.set(false);
    this.draftChanged.emit({ ...this.draft(), destination: result });
  }

  protected clearDestination(): void {
    this.draftChanged.emit({ ...this.draft(), destination: null });
  }

  protected chooseStart(event: Event): void {
    this.withDate(event, (draft, start_date) => ({ ...draft, start_date }));
  }

  protected chooseEnd(event: Event): void {
    this.withDate(event, (draft, end_date) => ({ ...draft, end_date }));
  }

  // The slots this day draws, day first. One entry or two — the order is the
  // order the request schema requires them in, so the template cannot render
  // them the wrong way round and the flattening at submit cannot either.
  protected slotsOf(entry: TripDayDraft): readonly { slot: Slot; occasion: Occasion }[] {
    return entry.evening === null
      ? [{ slot: 'day', occasion: entry.day }]
      : [
          { slot: 'day', occasion: entry.day },
          { slot: 'evening', occasion: entry.evening },
        ];
  }

  // Not single-valued the way a filter chip is: tapping the chosen occasion
  // again leaves it chosen, because a slot has no "no occasion" to fall back to
  // and the request needs one entry per slot.
  protected chooseOccasion(index: number, slot: Slot, occasion: Occasion): void {
    this.replaceDay(index, (entry) => withOccasion(entry, slot, occasion));
  }

  protected addEvening(index: number): void {
    this.replaceDay(index, (entry) => ({ ...entry, evening: EVENING_OCCASION }));
  }

  // The occasion goes with the slot rather than being kept for a re-add: an
  // evening that is not on the trip has nothing to be for, and holding the
  // value would make the × look reversible when the request it builds is not.
  protected removeEvening(index: number): void {
    this.replaceDay(index, (entry) => ({ ...entry, evening: null }));
  }

  protected changeNotes(event: Event): void {
    this.draftChanged.emit({ ...this.draft(), notes: (event.target as HTMLTextAreaElement).value });
  }

  protected submit(event: Event): void {
    event.preventDefault();
    this.submitted.emit();
  }

  private replaceDay(index: number, apply: (entry: TripDayDraft) => TripDayDraft): void {
    const occasions = this.draft().occasions.map((entry, position) =>
      position === index ? apply(entry) : entry,
    );
    this.draftChanged.emit({ ...this.draft(), occasions });
  }

  // One place resizes the chip rows, because both dates change the length and
  // the invariant — one occasion per day — is what the request schema checks.
  // A range that inverts drops to no rows rather than to a negative count; the
  // message under the button is what says so.
  private withDate(event: Event, apply: (draft: TripDraft, value: string) => TripDraft): void {
    const value = (event.target as HTMLInputElement).value;
    // An empty date input is a cleared field, not a date. Dropped rather than
    // emitted, so the picker falls back to the day it was opened on instead of
    // sending an empty string and collecting a 422 for it.
    if (value === '') {
      return;
    }

    const next = apply(this.draft(), value);
    this.draftChanged.emit({
      ...next,
      occasions: resize(next.occasions, daysInRange(next.start_date, next.end_date)),
    });
  }

  private search(q: string): void {
    this.issued += 1;
    const mine = this.issued;
    this.searching.set(true);

    this.api.searchLocations(q).subscribe({
      next: (response) => {
        if (mine !== this.issued) {
          return;
        }
        this.results.set(response.results);
        this.searched.set(true);
        this.searching.set(false);
      },
      error: () => {
        if (mine !== this.issued) {
          return;
        }
        this.results.set([]);
        this.searched.set(false);
        this.searching.set(false);
        this.searchError.set(true);
      },
    });
  }

  private stopTimer(): void {
    if (this.timer === null) {
      return;
    }
    clearTimeout(this.timer);
    this.timer = null;
  }
}

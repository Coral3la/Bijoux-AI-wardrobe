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
import { OCCASIONS, Occasion } from '../../shared/models/enums';
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

const MIN_QUERY_LENGTH = 2;

export const SEARCH_DEBOUNCE_MS = 300;

const DAY_MS = 86_400_000;

// What the four controls hold. `destination` is the whole geocoder result
// rather than its name, because the chip has to print "Berlin, Germany" to tell
// the two Berlins apart — only `name` goes on the wire, and the coordinates the
// picker had are thrown away (DECISIONS.md 202: the endpoint geocodes for
// itself). `occasions` is indexed by day, so day N is `occasions[N - 1]`, and
// its length is the length of the trip.
export interface TripDraft {
  readonly destination: LocationResult | null;
  readonly start_date: string;
  readonly end_date: string;
  readonly occasions: readonly Occasion[];
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

// The head is kept, so a user who set day 1 to work and then extends the trip
// still has work on day 1. Padding rather than resetting is the only choice
// that makes the chip rows survive a date change at all.
function resize(occasions: readonly Occasion[], days: number): readonly Occasion[] {
  if (days <= 0) {
    return [];
  }
  if (days === occasions.length) {
    return occasions;
  }
  return Array.from({ length: days }, (_, index) => occasions[index] ?? DEFAULT_OCCASION);
}

// Casual and today, a one-day trip: the request a user who touches nothing else
// would send, with the chip row already on screen teaching what the form does.
export function newTripDraft(now = new Date()): TripDraft {
  const today = todayInLocalTime(now);
  return {
    destination: null,
    start_date: today,
    end_date: today,
    occasions: [DEFAULT_OCCASION],
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
  template: `
    <form class="flex flex-col gap-6" (submit)="submit($event)">
      <section class="flex flex-col gap-2">
        <h2 class="text-sm font-medium">{{ i18n.t('trip.destination.label') }}</h2>

        @if (draft().destination; as chosen) {
          <!-- The place, in the body face. It is a name this project did not
               write, and Fraunces is latin-subset — DECISIONS.md 071 names the
               trip screen as one of the four surfaces that has to apply that
               rule deliberately. -->
          <div class="flex items-center gap-3 rounded-lg bg-surface p-3">
            <p class="text-sm">
              {{
                i18n.t('trip.destination.result', { name: chosen.name, country: chosen.country })
              }}
            </p>
            <button
              type="button"
              (click)="clearDestination()"
              [attr.aria-label]="i18n.t('trip.destination.clear')"
              class="ms-auto min-h-11 min-w-11 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
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
            <p class="text-sm" role="status" aria-live="polite">
              {{ i18n.t('trip.destination.searching') }}
            </p>
          }
          @if (searchError()) {
            <p class="text-sm font-medium text-danger">{{ i18n.t('trip.destination.error') }}</p>
          }
          @if (noMatches()) {
            <p class="text-sm">{{ i18n.t('trip.destination.noResults') }}</p>
          }

          <ul class="flex flex-col gap-1">
            @for (result of results(); track result.lat + ':' + result.lon) {
              <li>
                <button
                  type="button"
                  (click)="chooseDestination(result)"
                  class="min-h-11 w-full rounded-md bg-surface px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
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
        <div class="flex flex-col gap-1">
          <label for="trip_start" class="text-sm font-medium">
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

        <div class="flex flex-col gap-1">
          <label for="trip_end" class="text-sm font-medium">
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
        <h2 class="text-sm font-medium">{{ i18n.t('trip.occasions.legend') }}</h2>

        <!-- One row per day, in day order, which is the order the request
             schema requires: it checks that the numbers arrive as 1..n rather
             than merely being a permutation of them, because pack_trip reads
             the tuple positionally. -->
        @for (occasion of draft().occasions; track $index; let day = $index) {
          <fieldset class="flex flex-col gap-2">
            <legend class="text-sm">{{ i18n.t('trip.day.legend', { day: day + 1 }) }}</legend>
            <div class="flex flex-nowrap items-center gap-2 overflow-x-auto pb-1">
              @for (candidate of allOccasions; track candidate) {
                <button
                  type="button"
                  [attr.aria-pressed]="occasion === candidate"
                  (click)="chooseOccasion(day, candidate)"
                  [class]="chipClass(occasion === candidate)"
                >
                  {{ i18n.t('vocabulary.occasion.' + candidate) }}
                </button>
              }
            </div>
          </fieldset>
        }
      </section>

      <div class="flex flex-col gap-2">
        <label for="trip_notes" class="text-sm font-medium">
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
          class="rounded-md border border-current/20 bg-surface p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        ></textarea>
      </div>

      @if (problem(); as key) {
        <p id="trip-problem" class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
      }

      <button
        type="submit"
        [disabled]="problem() !== null"
        [attr.aria-describedby]="problem() === null ? null : 'trip-problem'"
        class="min-h-11 rounded-md bg-accent px-4 text-surface disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('trip.submit') }}
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
  protected readonly fieldClass =
    'min-h-11 rounded-md border border-current/20 bg-surface px-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

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

  // Not single-valued the way a filter chip is: tapping the chosen occasion
  // again leaves it chosen, because a day has no "no occasion" to fall back to
  // and the request needs one entry per day.
  protected chooseOccasion(index: number, occasion: Occasion): void {
    const occasions = this.draft().occasions.map((current, position) =>
      position === index ? occasion : current,
    );
    this.draftChanged.emit({ ...this.draft(), occasions });
  }

  protected changeNotes(event: Event): void {
    this.draftChanged.emit({ ...this.draft(), notes: (event.target as HTMLTextAreaElement).value });
  }

  protected chipClass(selected: boolean): string {
    const base =
      'min-h-11 shrink-0 rounded-full px-4 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
    return selected ? `${base} bg-accent text-surface` : `${base} bg-surface`;
  }

  protected submit(event: Event): void {
    event.preventDefault();
    this.submitted.emit();
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

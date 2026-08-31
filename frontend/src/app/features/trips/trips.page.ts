import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { TripsApi } from '../../core/api/trips.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { PackRequest, Trip } from '../../shared/models/trip.model';
import { TripDraft, TripForm, newTripDraft, tripProblem } from './trip-form';

// Four lines for a wait nobody has measured, so the last one is reached at nine
// seconds and rested on. The endpoint geocodes, fetches up to fourteen days of
// forecast, then makes one model call carrying the whole wardrobe — these name
// the four steps in the order the server takes them, and none of them names a
// duration, because no number has been taken.
const STATUS_KEYS = [
  'trip.waiting.geocoding',
  'trip.waiting.forecast',
  'trip.waiting.wardrobe',
  'trip.waiting.assembling',
] as const;

export const STATUS_INTERVAL_MS = 3000;

// Branch on the documented code, never on the status — the rule the stylist
// store follows, and `forecast_unavailable` is why it matters: it is issued at
// two statuses, 400 past the horizon and 502 when Open-Meteo does not answer,
// and both say one thing to the user.
//
// `home_location_missing` is deliberately absent. It is `POST /looks/suggest`'s
// code, for an account with no home coordinates; this endpoint is given a
// destination and never reads them, and 04-API-SPEC.md's failure list for it
// does not carry the code either.
const PACK_ERROR_KEYS: Readonly<Record<string, string>> = {
  trip_too_long: 'trip.error.tripTooLong',
  wardrobe_too_small: 'trip.error.wardrobeTooSmall',
  destination_not_found: 'trip.error.destinationNotFound',
  geocoding_unavailable: 'trip.error.geocodingUnavailable',
  forecast_unavailable: 'trip.error.forecastUnavailable',
  stylist_failed: 'trip.error.stylistFailed',
  validation_error: 'trip.error.validation',
};

interface ApiErrorBody {
  readonly code?: string;
}

function packErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as ApiErrorBody | null)?.code;
    if (code !== undefined && code in PACK_ERROR_KEYS) {
      return PACK_ERROR_KEYS[code];
    }
    // The one status this file reads, and it is read last, after every
    // documented code has failed to match. A body the request schema rejects
    // carries FastAPI's `detail` rather than `code`, so there is nothing else
    // to branch on.
    if (error.status === 422) {
      return PACK_ERROR_KEYS['validation_error'];
    }
  }
  return 'trip.error.general';
}

// `notes` is omitted rather than sent as an empty string: absent is what the
// server defaults it to, and the schema forbids extra keys rather than dropping
// them. The occasions are numbered here rather than in the form, because the
// wire wants `{ day, occasion }` and the draft holds one flat list — day N is
// index N - 1, which is the same positional reading `pack_trip` makes.
//
// The destination is the geocoder's own `name` and nothing else. Its country is
// display text for the chip, and its coordinates are dropped because the
// endpoint geocodes the string again for itself (DECISIONS.md 202).
function toRequest(draft: TripDraft, destination: string): PackRequest {
  const notes = draft.notes.trim();
  return {
    destination,
    start_date: draft.start_date,
    end_date: draft.end_date,
    occasions: draft.occasions.map((occasion, index) => ({ day: index + 1, occasion })),
    ...(notes !== '' && { notes }),
  };
}

@Component({
  selector: 'app-trips-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TripForm],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <!-- Outside the three-way branch below rather than inside it, for the
           stylist's reason: the branch replaces everything under the heading,
           so a link inside it would disappear for the whole of the wait and
           again once the trip is packed — which is most of the time anybody
           spends on this screen. -->
      <a
        routerLink="/wardrobe"
        class="inline-flex min-h-11 items-center self-start text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('trip.back') }}
      </a>

      <header>
        <h1 class="font-display text-3xl">{{ i18n.t('trip.title') }}</h1>
      </header>

      @if (isPacking()) {
        <!-- No skeleton, unlike the stylist. That screen draws the outline of
             the look card because the form becomes one; this form becomes a
             sentence, and a skeleton of a sentence is a grey bar pretending to
             be progress. The status line is the whole of the wait, and it is
             announced rather than silently replaced. -->
        <p class="text-sm" role="status" aria-live="polite">{{ i18n.t(statusKey()) }}</p>
      } @else if (packed(); as trip) {
        <section class="flex flex-col gap-2 rounded-lg bg-surface p-6">
          <!-- The place name in the body face, not font-display. It is text
               this project did not write and Fraunces is latin-subset, so a
               non-Latin destination would fall back per character and render in
               two faces on one line. DECISIONS.md 071 names this screen.

               Task 4.6 replaces this panel with a navigation to the trip view.
               Until it exists, the trip is packed and stored and this is what
               says so. -->
          <h2 class="text-xl">
            {{ i18n.t('trip.packed.title', { destination: trip.destination }) }}
          </h2>
          <p class="text-sm">{{ counts(trip) }}</p>
        </section>
      } @else {
        @if (error(); as key) {
          <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
        }

        <app-trip-form [draft]="draft()" (draftChanged)="draft.set($event)" (submitted)="pack()" />
      }
    </main>
  `,
})
export class TripsPage {
  protected readonly i18n = inject(I18nService);
  private readonly api = inject(TripsApi);

  // Held here rather than in a store, and rather than in the form. Not a store
  // because nothing else reads it: `StylistStore` exists because a look is
  // shared with `LooksStore` and with the swap, whereas this page makes one
  // request and renders its own answer, and 4.6 loads a trip by id rather than
  // being handed one. Not the form, because the form unmounts for the whole of
  // the request and a rejected pack must come back to a filled-in screen.
  protected readonly draft = signal<TripDraft>(newTripDraft());
  protected readonly isPacking = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly packed = signal<Trip | null>(null);

  private readonly statusIndex = signal(0);
  private timer: ReturnType<typeof setInterval> | null = null;

  protected readonly statusKey = computed(() => STATUS_KEYS[this.statusIndex()]);

  constructor() {
    effect(() => {
      if (this.isPacking()) {
        this.startStatusCycle();
      } else {
        this.stopStatusCycle();
      }
    });

    inject(DestroyRef).onDestroy(() => this.stopStatusCycle());
  }

  // Pluralised on the looks alone. `item_count` cannot be one — a wearable look
  // is at least a top, a bottom and shoes — whereas a one-day trip really does
  // pack one look, and it is the only count here that can reach 1.
  protected counts(trip: Trip): string {
    const { item_count, look_count } = trip.packing_list.reuse_summary;
    return look_count === 1
      ? this.i18n.t('trip.packed.counts.one', { items: item_count })
      : this.i18n.t('trip.packed.counts.other', { items: item_count, looks: look_count });
  }

  protected pack(): void {
    const draft = this.draft();
    // The null check is the compiler's: `tripProblem` already refuses a draft
    // with no destination, and TypeScript cannot see that one implies the other.
    // The other two clauses cannot fire from this screen as it stands — the
    // button is disabled while `tripProblem` is set, and the form is unmounted
    // for the whole of the request — which is why the test that a second pack
    // is impossible asserts the missing form rather than a dropped call.
    if (this.isPacking() || tripProblem(draft) !== null || draft.destination === null) {
      return;
    }

    this.isPacking.set(true);
    this.error.set(null);

    this.api.pack(toRequest(draft, draft.destination.name)).subscribe({
      next: (response) => {
        this.packed.set(response.trip);
        this.isPacking.set(false);
      },
      // The draft is left exactly as it was, which is what the form being the
      // page's rather than its own buys: the message goes above a screen the
      // user can correct and send again.
      error: (failure: unknown) => {
        this.error.set(packErrorKey(failure));
        this.isPacking.set(false);
      },
    });
  }

  // Guarded rather than assumed idle: the effect re-runs on every read of
  // `isPacking`, and a second interval started over a live one would be an
  // interval nothing holds a handle to.
  private startStatusCycle(): void {
    if (this.timer !== null) {
      return;
    }
    this.statusIndex.set(0);
    this.timer = setInterval(() => {
      // Clamped, not wrapped. A line that comes back round claims work that is
      // behind us, and this wait has no known length — so the last line is
      // where it rests.
      this.statusIndex.update((index) => Math.min(index + 1, STATUS_KEYS.length - 1));
    }, STATUS_INTERVAL_MS);
  }

  private stopStatusCycle(): void {
    if (this.timer === null) {
      return;
    }
    clearInterval(this.timer);
    this.timer = null;
  }
}

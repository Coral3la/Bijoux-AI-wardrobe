import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { TripsApi } from '../../core/api/trips.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { PackRequest } from '../../shared/models/trip.model';
import { packErrorKey, packStatus } from './pack-wait';
import { TripDraft, TripForm, newTripDraft, tripProblem } from './trip-form';

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
  imports: [TripForm],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
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
  private readonly router = inject(Router);

  // Held here rather than in a store, and rather than in the form. Not a store
  // because nothing else reads it: `StylistStore` exists because a look is
  // shared with `LooksStore` and with the swap, whereas this page makes one
  // request and renders its own answer, and 4.6 loads a trip by id rather than
  // being handed one. Not the form, because the form unmounts for the whole of
  // the request and a rejected pack must come back to a filled-in screen.
  protected readonly draft = signal<TripDraft>(newTripDraft());
  protected readonly isPacking = signal(false);
  protected readonly error = signal<string | null>(null);

  // The cycle is `pack-wait.ts`'s, and following `isPacking` is the whole of the
  // wiring: 4.6b gave the same wait to a second screen, and the interval, its
  // teardown and the guard against a second one started over a live one moved
  // with it rather than being written twice. DECISIONS.md 207.
  protected readonly statusKey = packStatus(this.isPacking);

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
      // isPacking stays true across the navigation. Clearing it first would put
      // the filled-in form back on screen for the frame between the response
      // and the route resolving, and the last thing the user did was submit it.
      //
      // The callback only has anything to do when the navigation did not
      // happen: one that did destroys this component on the way, and the two
      // writes land on signals nobody is reading. Without it a refused
      // navigation leaves the trip packed, stored, and behind a status line
      // that never stops.
      next: (response) => {
        void this.router.navigate(['/trips', response.trip.id]).then((navigated) => {
          if (!navigated) {
            this.isPacking.set(false);
            this.error.set('trip.error.general');
          }
        });
      },
      // The draft is left exactly as it was, which is what the form being the
      // page's rather than its own buys: the message goes above a screen the
      // user can correct and send again.
      error: (failure: unknown) => {
        this.error.set(packErrorKey(failure, 'trip.error.general'));
        this.isPacking.set(false);
      },
    });
  }
}

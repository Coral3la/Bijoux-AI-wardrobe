import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TripsApi } from '../../core/api/trips.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { Trip } from '../../shared/models/trip.model';
import { Button } from '../../shared/ui/button';
import { EmptyState } from '../../shared/ui/empty-state';

// The Atelier pill again, written out at a call site rather than taken from
// `appButton` — the fourth instance, after `look-request-form.ts`,
// `saved-looks.page.ts` and `trip-detail.page.ts`. 221 named the third as the
// point where the shared directive should absorb it, and 222 declined for the
// same reason this file declines: converting `appButton` reaches every screen in
// the product, and a trips list is not the commit that gets to do that. It is
// recorded as growing rather than quietly copied a fourth time.
//
// `px-5` and `shrink-0` are where it differs from the Itinerary's: this one
// lives at the end of a row rather than in a footer, so it may not be squeezed
// by a long destination, and the armed sentence is allowed to wrap onto a line
// of its own instead of widening the row. DECISIONS.md 221, 222.
const ROW_ACTION =
  'inline-flex min-h-11 max-w-full shrink-0 items-center justify-center rounded-full border px-5 text-center text-[11px] font-medium tracking-[0.22em] uppercase disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

@Component({
  selector: 'app-trip-list-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, EmptyState, RouterLink],
  template: `
    <!-- 820px, the Itinerary's measure rather than the form's 672. This screen
         and /trips/:id are the same subject at two magnifications — a row's
         destination becomes that page's h1 — so a reader following a row into a
         trip should find the heading in the same column it was already reading.
         DECISIONS.md 222. -->
    <main
      class="mx-auto flex w-full max-w-[820px] flex-col gap-region px-6 pt-hero pb-region md:px-14"
    >
      <header
        class="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3 border-b border-line pb-5"
      >
        <div class="flex flex-col gap-1">
          <p class="font-mono text-[11px] tracking-[0.18em] text-ink-soft uppercase">
            {{ i18n.t('trip.list.caption') }}
          </p>
          <!-- The display serif, unlike the row headings below it and unlike
               /trips/:id's h1. This title is a sentence this project wrote; a
               destination is a place name off a geocoder, and 071 gives those
               the content face. The two faces on this screen are the two
               authorships. -->
          <h1
            class="font-display text-[40px] leading-none font-light tracking-[-0.02em] md:text-5xl"
          >
            {{ i18n.t('trip.list.title') }}
          </h1>
        </div>

        <!-- Only when there are rows. The empty state below carries its own way
             to the form, and an empty screen with the same link twice is one
             offer stated twice. -->
        @if (hasTrips()) {
          <a appButton variant="ghost" routerLink="/trips/new">{{ i18n.t('trip.list.new') }}</a>
        }
      </header>

      @if (trips(); as rows) {
        <!-- Above the list rather than in place of it, which is the Itinerary's
             rule for the same reason: a failed delete costs the user nothing,
             and the row it failed on is back on screen underneath this line. -->
        @if (actionError(); as key) {
          <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
        }

        @if (rows.length === 0) {
          <app-empty-state
            [title]="i18n.t('trip.list.empty.title')"
            [description]="i18n.t('trip.list.empty.body')"
          >
            <!-- Ghost, like /saved's: an empty trips list is a state a working
                 account passes through — it is what deleting your last trip
                 leaves behind — rather than the one action a new account must
                 take. DECISIONS.md 216. -->
            <a appButton variant="ghost" routerLink="/trips/new">
              {{ i18n.t('trip.list.empty.cta') }}
            </a>
          </app-empty-state>
        } @else {
          <!-- In the order the server sent, which is created_at DESC with id as
               the tiebreaker. No client-side sort: the ordering is the
               endpoint's promise and re-stating it here would be a second
               implementation of it that nothing compares against. -->
          <ul class="flex flex-col">
            @for (trip of rows; track trip.id) {
              <li
                class="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-line py-5 last:border-b-0"
              >
                <!-- The anchor covers the text and not the whole row, because a
                     button inside an anchor is invalid HTML and the delete would
                     be unreachable by keyboard inside one. It is the row's whole
                     free width instead, so the tap target is everything up to
                     the control. -->
                <a
                  [routerLink]="['/trips', trip.id]"
                  class="flex min-w-0 flex-1 flex-col gap-1 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
                >
                  <!-- The content face at the row's scale, for the destination's
                       standing reason: it is a place name off the geocoder and
                       the display serif is latin-subset, so a non-Latin name
                       would fall back per character and render in two faces on
                       one line. DECISIONS.md 071, 222. -->
                  <span class="font-sans text-[26px] leading-tight">{{ trip.destination }}</span>
                  <!-- One key for the whole line rather than three spans and a
                       dash this template invented: the dates, the separator and
                       the day count are one sentence a translation may reorder,
                       which is what trip.view.day.weather already does with its
                       own middot. The ISO dates go out unformatted — 206 refuses
                       a date formatter on these screens. -->
                  <span class="font-mono text-[13px] tracking-[0.06em] text-ink-muted tabular-nums">
                    {{
                      i18n.t('trip.list.meta', {
                        start: trip.start_date,
                        end: trip.end_date,
                        days: dayLabel(trip),
                      })
                    }}
                  </span>
                </a>

                <!-- Two presses, the Itinerary's control at row scale and with
                     its copy unchanged: this button destroys exactly the rows
                     that one does, so it says the same sentence about them. The
                     accessible name names the trip while idle, because a column
                     of buttons all called "Delete" is a column of identical
                     names — and it is dropped when armed, so that the sentence
                     about the cascade is what gets announced rather than being
                     overridden by it. DECISIONS.md 126. -->
                <button
                  type="button"
                  (click)="onDelete(trip)"
                  (blur)="disarm()"
                  [disabled]="deleting()"
                  [attr.aria-label]="isArmed(trip) ? null : deleteName(trip)"
                  [class]="deleteClass(trip)"
                >
                  {{ isArmed(trip) ? i18n.t('trip.delete.armed') : i18n.t('trip.delete.idle') }}
                </button>
              </li>
            }
          </ul>
        }
      } @else if (errorKey(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      } @else {
        <!-- Prose rather than a skeleton, and the whole region defers: a list of
             unknown length has no shape to promise, which is the Itinerary's
             reasoning one screen along. DECISIONS.md 217. -->
        <p
          class="animate-deferred font-prose text-base text-ink-muted italic"
          role="status"
          aria-live="polite"
        >
          {{ i18n.t('trip.list.loading') }}
        </p>
      }
    </main>
  `,
})
export class TripListPage {
  protected readonly i18n = inject(I18nService);
  private readonly api = inject(TripsApi);

  // `null` is loading and `[]` is an account with no trips, which is why this is
  // not initialised to an empty array: the two states render different screens
  // and an empty list on arrival would flash the empty state at every visitor.
  protected readonly trips = signal<readonly Trip[] | null>(null);
  protected readonly errorKey = signal<string | null>(null);
  protected readonly actionError = signal<string | null>(null);

  // One armed id for the whole list rather than a flag per row: arming a second
  // row disarms the first by construction, which is the behaviour anyway — two
  // rows one press away from deletion is two chances to delete the wrong trip.
  protected readonly armedId = signal<string | null>(null);
  protected readonly deleting = signal(false);

  protected readonly hasTrips = computed(() => (this.trips()?.length ?? 0) > 0);

  constructor() {
    this.api.list().subscribe({
      next: (page) => this.trips.set(page.trips),
      error: () => this.errorKey.set('trip.list.error.load'),
    });
  }

  // I18nService has no plural rule (DECISIONS.md 058), so the caller picks the
  // key. Counted off `days`, which GET /trips fills from the stored forecast for
  // every trip it answers — the same array /trips/:id counts its own caption
  // from.
  protected dayLabel(trip: Trip): string {
    return trip.days.length === 1
      ? this.i18n.t('trip.list.days.one')
      : this.i18n.t('trip.list.days.other', { days: trip.days.length });
  }

  protected isArmed(trip: Trip): boolean {
    return this.armedId() === trip.id;
  }

  protected deleteName(trip: Trip): string {
    return this.i18n.t('trip.list.delete.label', { destination: trip.destination });
  }

  protected deleteClass(trip: Trip): string {
    return this.isArmed(trip)
      ? `${ROW_ACTION} border-danger bg-danger text-canvas`
      : `${ROW_ACTION} border-line text-danger`;
  }

  protected onDelete(trip: Trip): void {
    // The disabled binding is the visible guard and this is the real one, for
    // the Itinerary's reason: a signal write schedules change detection rather
    // than doing it, so two presses landing in the same frame both see an
    // enabled button. It also keeps the restore below unambiguous — one delete
    // in flight means one index to put back.
    if (this.deleting()) {
      return;
    }

    if (!this.isArmed(trip)) {
      this.armedId.set(trip.id);
      return;
    }

    const rows = this.trips();
    const index = rows?.findIndex((row) => row.id === trip.id) ?? -1;
    if (rows === null || index === -1) {
      return;
    }

    this.armedId.set(null);
    this.actionError.set(null);
    this.deleting.set(true);
    // Optimistic: the row leaves now and comes back only if the server refuses.
    // Which is also why `trip.delete.doing` is not rendered here — there is no
    // row left to say "Deleting…" on, and a spinner over a gap explains nothing.
    this.trips.set(rows.filter((row) => row.id !== trip.id));

    this.api.remove(trip.id).subscribe({
      next: () => this.deleting.set(false),
      // Back at the index it left from, not at the top. The list is created_at
      // DESC, so a restored row that reappeared first would be the failure
      // telling a second lie on its way out.
      error: () => {
        this.deleting.set(false);
        this.trips.update((current) =>
          current === null ? current : [...current.slice(0, index), trip, ...current.slice(index)],
        );
        this.actionError.set('trip.error.delete');
      },
    });
  }

  protected disarm(): void {
    this.armedId.set(null);
  }
}

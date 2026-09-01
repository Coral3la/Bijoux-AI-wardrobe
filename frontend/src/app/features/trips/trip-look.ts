import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { roleOf } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import { ItemCard } from '../wardrobe/item-card';

// The facts, not the sentence — the shape the server uses one boundary up, for
// the same reason (`ReuseSummary` answers two counts and no English). The page
// owns the arithmetic because it takes the whole trip to do; this component owns
// the words because it is the thing that renders them.
export interface StillWorn {
  readonly name: string;
  readonly days: readonly number[];
}

// Not `LookCard`, for the third time and on the same three grounds: that card
// ends in *Try again*, which has no request behind a trip look; it carries a
// heart and two thumbs, which belong to `/saved` and not to a day of a trip; and
// it sorts by layer then category, where this arranges by `look_items.position`
// — the order the model chose, which is what 4.6 shipped and what this task does
// not get to change. The third ground was written as "it groups by layer"; DR.20
// deleted the grouping and kept the sort, so the sentence moved and the
// conclusion did not. `saved-looks.page.ts` refused the same reuse at 3.2.
//
// Its own component rather than the page's inline `<article>`, which is where
// 4.6 left it, because it now owns three things the page has no business
// holding: which tile carries a badge, which tile is waiting, and the sentence
// that reports what a swap cost. `packing-list.ts` is the neighbour and the
// precedent. Not `shared/ui/` — one caller, and AUDITS.md O-15 stays at zero.
@Component({
  selector: 'app-trip-look',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard],
  template: `
    <article class="flex flex-col gap-4 rounded-2xl bg-surface p-4 shadow-sm">
      <!-- Body face, not font-display: the title is written by the model.
           DECISIONS.md 071, and 4.6's own line unchanged. -->
      <h2 class="text-2xl">{{ look().title }}</h2>

      <!-- In the order the server sent, which is look_items.position and
           therefore the model's own. Four columns, which is 4.6's grid: the
           badge overlays the corner of a photograph rather than information,
           and shrinking the grid to make room for a control would be the
           control winning an argument against the content. -->
      <ul class="grid grid-cols-4 gap-2">
        @for (item of look().items; track item.id) {
          <li class="relative">
            <app-item-card [item]="item" />

            <!-- Beside the tile rather than inside ItemCard, which the wardrobe
                 grid renders too: a badge that only ever appears in a look does
                 not belong to the component both screens share. A sibling of
                 the tile's link and never inside it, for item-card.ts's reason —
                 an anchor containing a button is nested interactive content. -->
            @if (isSwappable(item)) {
              <button
                type="button"
                (click)="swap.emit(item)"
                [disabled]="swappingItemId() !== null"
                [attr.aria-label]="i18n.t('trip.swap.action', { item: name(item) })"
                class="absolute end-0 top-0 min-h-11 min-w-11 rounded-full bg-surface/90 text-lg disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                ↻
              </button>
            }

            <!-- Over this tile and nothing else. Every other garment, the title
                 and the notes stay legible while one piece is being replaced —
                 which is the whole difference between this wait and the pack's,
                 where the screen has nothing to keep. -->
            @if (swappingItemId() === item.id) {
              <div
                class="absolute inset-0 flex items-center justify-center rounded-xl bg-surface/80"
                role="status"
              >
                <span class="sr-only">{{ i18n.t('trip.swap.doing') }}</span>
                <span
                  class="h-6 w-6 animate-spin rounded-full border-2 border-current/30 border-t-current"
                  aria-hidden="true"
                ></span>
              </div>
            }
          </li>
        }
      </ul>

      <!-- The line the feature turns on: taking the jeans off Tuesday must not
           read as taking them out of the suitcase while Thursday still wears
           them. Under the grid the garment left, above the model's own prose,
           and announced because it is the answer to a press. STAGE-4 4.6a's
           third property. -->
      @if (stillWornLine(); as line) {
        <p class="text-sm font-medium" role="status">{{ line }}</p>
      }

      <p class="text-sm">{{ look().reasoning }}</p>
      <p class="text-sm">{{ look().weather_note }}</p>

      <!-- Inside the article, at the foot of the look the swap failed to
           change — not the page's actionError, which sits below the packing
           list and means "the whole trip's action failed". A swap that fails
           costs one day nothing, and the message belongs to that day. -->
      @if (errorKey(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      }
    </article>
  `,
})
export class TripLook {
  protected readonly i18n = inject(I18nService);

  readonly look = input.required<Look>();

  // The id, not a boolean, because the wait is drawn on one tile: a flag would
  // say a swap is running and not which garment is waiting on it. Same shape as
  // StylistStore.swappingItemId, and it disables every badge rather than only
  // its own — one request is in flight at a time, so a second badge that still
  // depressed would be a press with nowhere to go.
  readonly swappingItemId = input<string | null>(null);

  readonly stillWorn = input<StillWorn | null>(null);
  readonly errorKey = input<string | null>(null);

  readonly swap = output<Item>();

  // No "and" before the last day, and the separator is a string a translator
  // owns rather than a comma in this file. `Intl.ListFormat` would write the
  // "and" and take the browser's locale with it, on a screen where every other
  // word came from en.json — which is DECISIONS.md 206's refusal of a date
  // formatter, one sentence along.
  protected readonly stillWornLine = computed(() => {
    const worn = this.stillWorn();
    if (worn === null) {
      return null;
    }
    const days = worn.days
      .map((day) => this.i18n.t('trip.day.legend', { day }))
      .join(this.i18n.t('trip.swap.daysSeparator'));
    return this.i18n.t('trip.swap.stillWorn', { name: worn.name, days });
  });

  // No badge on a dress: replacing one can legally return a top and a bottom,
  // which `replace_role` has no word for and a single-item swap is not. The
  // look card's own predicate, duplicated rather than imported — three tokens
  // against a trips component reaching into a stylist one. AUDITS.md O-25.
  protected isSwappable(item: Item): boolean {
    return roleOf(item.category) !== undefined;
  }

  // The badge's accessible name has to say which garment it replaces: four ↻
  // buttons on one look are otherwise four identical announcements.
  protected name(item: Item): string {
    return item.display_name ?? this.i18n.t('item.untitled');
  }
}

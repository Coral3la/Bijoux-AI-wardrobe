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
//
// **The title left at the Itinerary pass and is the page's now.** It sits on one
// baseline with the day's number and its weather, and that row has to render for
// a day whose look was detached — which is a row this component is not on screen
// for. DECISIONS.md 222.
@Component({
  selector: 'app-trip-look',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard],
  template: `
    <!-- No card, no fill, no shadow. Every day of the trip is on screen at once
         now, so a wrapper here would draw a box around each of five to fourteen
         sections that the hairline between them already separates. The look sits
         on the canvas, the way the wardrobe grid and the stylist's own look do.
         DECISIONS.md 222. -->
    <div class="flex flex-col gap-4">
      <!-- In the order the server sent, which is look_items.position and
           therefore the model's own. Four columns on a desktop and two on a
           phone: the badge overlays the corner of a photograph rather than
           information, and shrinking the grid to make room for a control would
           be the control winning an argument against the content. -->
      <ul class="grid grid-cols-2 gap-x-3 gap-y-5 md:grid-cols-4">
        @for (item of look().items; track item.id) {
          <li class="flex flex-col gap-2">
            <div class="relative">
              <!-- ItemCard captions itself on the wardrobe grid, where the
                   second line is the garment's colour. Here the caption is the
                   category alone, so the look draws its own and turns that one
                   off — the colour is in the photograph directly above it.
                   DECISIONS.md 220's input, third caller. -->
              <app-item-card [item]="item" [caption]="false" />

              <!-- Beside the tile rather than inside ItemCard, which the wardrobe
                   grid renders too: a badge that only ever appears in a look does
                   not belong to the component both screens share. A sibling of
                   the tile's link and never inside it, for item-card.ts's reason —
                   an anchor containing a button is nested interactive content. -->
              @if (isSwappable(item)) {
                <button
                  type="button"
                  (click)="swap.emit(item)"
                  [disabled]="busy()"
                  [attr.aria-label]="i18n.t('trip.swap.action', { item: name(item) })"
                  class="absolute end-1 top-1 inline-flex h-11 w-11 items-center justify-center rounded-full border border-line bg-canvas/90 text-base disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  ↻
                </button>
              }

              <!-- Over this tile and nothing else. Every other garment, every
                   other day, the titles and the notes stay legible while one
                   piece is being replaced — which is the whole difference
                   between this wait and the pack's, where the screen has nothing
                   to keep. The id arrives already scoped to this day, because a
                   garment worn on three of them would otherwise spin on all
                   three. -->
              @if (swappingItemId() === item.id) {
                <div
                  class="absolute inset-0 flex items-center justify-center rounded-[2px] bg-canvas/80"
                  role="status"
                >
                  <span class="sr-only">{{ i18n.t('trip.swap.doing') }}</span>
                  <span
                    class="h-6 w-6 animate-spin rounded-full border-2 border-current/30 border-t-current"
                    aria-hidden="true"
                  ></span>
                </div>
              }
            </div>

            <div class="flex flex-col gap-0.5">
              <!-- The model's name for the garment, so the content face at the
                   direction's size; the category under it is our own closed
                   vocabulary and keeps the authored treatment. Same split the
                   look card and the wardrobe tile draw. DECISIONS.md 071. -->
              <span class="font-sans text-sm text-ink">{{ name(item) }}</span>
              @if (categoryOf(item); as label) {
                <span class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
                  {{ label }}
                </span>
              }
            </div>
          </li>
        }
      </ul>

      <!-- The line the feature turns on: taking the jeans off Tuesday must not
           read as taking them out of the suitcase while Thursday still wears
           them. Under the grid the garment left, above the model's own prose,
           and announced because it is the answer to a press. It names a garment,
           so it is set in the content face. STAGE-4 4.6a's third property. -->
      @if (stillWornLine(); as line) {
        <p class="font-sans text-sm font-medium" role="status">{{ line }}</p>
      }

      <!-- Both are the model's prose, so both take the content face at the sizes
           the direction asks for — 16px for the reasoning against a 55-character
           measure, 14px muted for the note. DECISIONS.md 071, 222. -->
      <div class="flex flex-col gap-1">
        <p class="max-w-[55ch] font-sans text-base leading-relaxed text-ink italic">
          {{ look().reasoning }}
        </p>
        <p class="max-w-[55ch] font-sans text-sm text-ink-muted italic">
          {{ look().weather_note }}
        </p>
      </div>

      <!-- At the foot of the day the swap failed to change — not the page's
           actionError, which sits under the actions row and means "the whole
           trip's action failed". A swap that fails costs one day nothing, and
           the message belongs to that day. The page hands it down already
           matched to this one. -->
      @if (errorKey(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      }
    </div>
  `,
})
export class TripLook {
  protected readonly i18n = inject(I18nService);

  readonly look = input.required<Look>();

  // The id, not a boolean, because the wait is drawn on one tile — and it is
  // this day's id or null, never the trip's: the page matches it to the day
  // before handing it down, so a garment worn on Monday and Thursday does not
  // spin on both while one of them is being replaced.
  readonly swappingItemId = input<string | null>(null);

  // A swap is running *somewhere* in the trip, which is a different fact from
  // the one above now that every day is on screen. One request is in flight at a
  // time, so every badge in the itinerary is disabled while one is — a badge
  // that still depressed would be a press with nowhere to go.
  readonly busy = input(false);

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

  // Silent on a row with no category rather than padded with a placeholder: an
  // untagged garment can reach a look through a detached one, and a caps line
  // reading "Other" under a photograph names nothing.
  protected categoryOf(item: Item): string | null {
    const category = item.category;
    return category === null ? null : this.i18n.t(`vocabulary.category.${category}`);
  }

  // The badge's accessible name has to say which garment it replaces: four ↻
  // buttons on one look are otherwise four identical announcements, and the
  // itinerary now puts every day's four on one page.
  protected name(item: Item): string {
    return item.display_name ?? this.i18n.t('item.untitled');
  }
}

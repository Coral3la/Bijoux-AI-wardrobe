import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { CATEGORIES, Category } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';

interface CategoryGroup {
  readonly headingKey: string;
  readonly items: readonly Item[];
}

// Its own component rather than a section of the page, for one reason that is
// not tidiness: it owns the checkbox state, which is local to the browser and
// belongs to no trip, and task 4.7 exports the grouping this file computes. The
// look card's grouping is by layer and this one is by category — that is
// 05-FRONTEND-SPEC.md's own split, and the two questions are different: a look
// is read top-down as an outfit, a suitcase is packed a drawer at a time.
@Component({
  selector: 'app-packing-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="flex flex-col gap-6">
      <!-- Before you go, not Packing list. The itinerary above it is read at
           the desk while the trip is being planned and this is read at the
           wardrobe on the morning of, so the heading names the moment rather
           than the object — and it is the last thing on a page that reads top
           to bottom as a journey. It is a title this project wrote, so it takes
           the display face at the direction's size. DECISIONS.md 222. -->
      <h2
        class="font-display text-[32px] leading-none font-light tracking-[-0.01em] md:text-[36px]"
      >
        {{ i18n.t('trip.view.beforeYouGo') }}
      </h2>

      <!-- No card. The list sits on the canvas like every other block on this
           screen, and what separates one group from the next is the hairline
           under its own heading. Two columns where there is width for them:
           twelve to fourteen garments in one column is a scroll on a page that
           has already asked for several. DECISIONS.md 222. -->
      <div class="grid gap-x-12 gap-y-8 md:grid-cols-2">
        @for (group of groups(); track group.headingKey) {
          <section class="flex flex-col">
            <h3
              class="border-b border-line pb-1 font-mono text-[10px] font-medium tracking-[0.24em] text-ink-soft uppercase"
            >
              {{
                i18n.t('trip.view.group', {
                  name: i18n.t(group.headingKey),
                  count: group.items.length,
                })
              }}
            </h3>
            <ul class="flex flex-col">
              @for (item of group.items; track item.id) {
                <!-- The label wraps the checkbox rather than pointing at it with
                     for=, so the garment name is the tap target without an id
                     scheme that has to stay unique across a page that also
                     renders the same items inside the looks above. -->
                <li>
                  <label class="flex min-h-11 items-center gap-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      [checked]="packed().has(item.id)"
                      (change)="toggle(item.id)"
                      class="size-4 shrink-0 accent-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    />
                    <!-- Struck through rather than removed or moved to the
                         bottom: the list is read against a suitcase, and a row
                         that leaves the place the eye last saw it costs more
                         than the strike saves.

                         The content face, because a garment name is the model's
                         and not ours. DECISIONS.md 071. -->
                    <span
                      class="font-sans"
                      [class.line-through]="packed().has(item.id)"
                      [class.text-ink-soft]="packed().has(item.id)"
                    >
                      {{ name(item) }}
                    </span>
                  </label>
                </li>
              }
            </ul>
          </section>
        }
      </div>
    </section>
  `,
})
export class PackingList {
  protected readonly i18n = inject(I18nService);

  // Already hydrated and already filtered by the page. An id the page could
  // not resolve to an item never arrives here, so this component has no null
  // row to render and no opinion about one.
  readonly items = input.required<readonly Item[]>();

  // Local state only, per STAGE-4 4.6, and it is deliberately not persisted:
  // there is no column for it, and a tick that survived a reload would be a
  // claim about the trip that the server cannot answer for.
  protected readonly packed = signal<ReadonlySet<string>>(new Set());

  // Grouped in CATEGORIES order rather than by first appearance, so two trips
  // with the same garments list them the same way. A null category cannot
  // reach this list — every packed item comes out of a look, and the stylist
  // is served `ready` rows — but the type admits one, so it sorts to the end
  // beside the look card's own null handling rather than crashing the index.
  protected readonly groups = computed<readonly CategoryGroup[]>(() => {
    const byCategory = new Map<Category | null, Item[]>();
    for (const item of this.items()) {
      const bucket = byCategory.get(item.category);
      if (bucket === undefined) {
        byCategory.set(item.category, [item]);
      } else {
        bucket.push(item);
      }
    }

    const groups: CategoryGroup[] = [];
    for (const category of CATEGORIES) {
      const items = byCategory.get(category);
      if (items !== undefined) {
        groups.push({ headingKey: `vocabulary.category.${category}`, items });
      }
    }
    const untyped = byCategory.get(null);
    if (untyped !== undefined) {
      groups.push({ headingKey: 'trip.view.groupOther', items: untyped });
    }
    return groups;
  });

  protected toggle(id: string): void {
    this.packed.update((current) => {
      const next = new Set(current);
      if (!next.delete(id)) {
        next.add(id);
      }
      return next;
    });
  }

  // The same fallback the look card uses, and for the same reason: display_name
  // is null on a row the wardrobe never finished tagging, and an empty row in a
  // packing list is a garment the user cannot identify.
  protected name(item: Item): string {
    return item.display_name ?? this.i18n.t('item.untitled');
  }
}

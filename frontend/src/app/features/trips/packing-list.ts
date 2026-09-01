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
    <section class="flex flex-col gap-4">
      <h2 class="font-display text-xl">{{ i18n.t('trip.view.packingList') }}</h2>

      <!-- One card, and the dividers inside it are edge definition rather than
           card borders: 05-FRONTEND-SPEC.md line 650 governs the outside, where
           the shadow carries the separation, and overflow-hidden is what stops
           a full-bleed divider running past the corner radius. -->
      <div class="overflow-hidden rounded-xl bg-surface shadow-sm">
        @for (group of groups(); track group.headingKey) {
          <section>
            <h3
              class="border-be border-line px-3.5 pt-3 pb-2 text-xs font-medium tracking-widest text-ink-soft uppercase"
            >
              {{
                i18n.t('trip.view.group', {
                  name: i18n.t(group.headingKey),
                  count: group.items.length,
                })
              }}
            </h3>
            <ul class="flex flex-col">
              @for (item of group.items; track item.id; let last = $last) {
                <!-- The label wraps the checkbox rather than pointing at it with
                     for=, so the garment name is the tap target without an id
                     scheme that has to stay unique across a page that also
                     renders the same items inside the look above. -->
                <li class="border-line" [class.border-be]="!last">
                  <label class="flex min-h-11 items-center gap-3 px-3.5 py-3 text-sm">
                    <input
                      type="checkbox"
                      [checked]="packed().has(item.id)"
                      (change)="toggle(item.id)"
                      class="size-5 shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    />
                    <!-- Struck through rather than removed or moved to the
                         bottom: the list is read against a suitcase, and a row
                         that leaves the place the eye last saw it costs more
                         than the strike saves. -->
                    <span
                      [class.line-through]="packed().has(item.id)"
                      [class.opacity-60]="packed().has(item.id)"
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

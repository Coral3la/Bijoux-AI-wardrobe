import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { CATEGORIES, Category, LAYERS, Layer } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Look, MissingPiece } from '../../shared/models/look.model';
import { ItemCard } from '../wardrobe/item-card';

interface LayerGroup {
  readonly headingKey: string;
  readonly items: Item[];
}

// Both ranks send null to the end rather than to the front. A tagged item
// always carries both — validate_tags requires them — so a null here is a row
// the wardrobe never finished, and the sort must not let one lead the card.
function layerRank(layer: Layer | null): number {
  return layer === null ? LAYERS.length : LAYERS.indexOf(layer);
}

function categoryRank(category: Category | null): number {
  return category === null ? CATEGORIES.length : CATEGORIES.indexOf(category);
}

function isCategory(value: string): value is Category {
  return (CATEGORIES as readonly string[]).includes(value);
}

@Component({
  selector: 'app-look-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard],
  template: `
    <article class="flex flex-col gap-5 rounded-lg bg-surface p-5">
      <header class="flex flex-col gap-1">
        <!-- Body face, not font-display: the title is written by the model, and
             05-FRONTEND-SPEC.md line 290 reserves Fraunces for chrome we
             author — it is latin-subset, so a non-Latin word in a display
             heading renders in two faces on one line. DECISIONS.md 071. -->
        <h2 class="text-2xl">{{ look().title }}</h2>
        @if (message(); as line) {
          <p class="text-sm">{{ line }}</p>
        }
      </header>

      @for (group of groups(); track group.headingKey) {
        <section class="flex flex-col gap-2">
          <h3 class="text-sm font-medium">{{ i18n.t(group.headingKey) }}</h3>
          <ul class="grid grid-cols-3 gap-3">
            @for (item of group.items; track item.id) {
              <li><app-item-card [item]="item" /></li>
            }
          </ul>
        </section>
      }

      <div class="flex flex-col gap-2">
        <p class="text-sm">{{ look().reasoning }}</p>
        <p class="text-sm">{{ look().weather_note }}</p>
      </div>

      @if (missingPieces().length > 0) {
        <section class="flex flex-col gap-1 text-sm text-current/70">
          <h3 class="font-medium">{{ i18n.t('stylist.look.missing') }}</h3>
          <ul class="flex flex-col gap-1">
            @for (piece of missingPieces(); track $index) {
              <li>{{ pieceLine(piece) }}</li>
            }
          </ul>
        </section>
      }

      <button
        type="button"
        (click)="tryAgain.emit()"
        class="min-h-11 self-start rounded-md bg-accent px-4 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('stylist.look.tryAgain') }}
      </button>
    </article>
  `,
})
export class LookCard {
  protected readonly i18n = inject(I18nService);

  readonly look = input.required<Look>();
  readonly missingPieces = input<readonly MissingPiece[]>([]);
  readonly message = input('');

  readonly tryAgain = output<void>();

  // Sorted by layer then category, then cut into runs — which is the whole of
  // the grouping, because a run can only break where the layer changes once
  // the list is in layer order. The headings come from the shared vocabulary
  // so the card names a layer the same way the tag editor does.
  protected readonly groups = computed<readonly LayerGroup[]>(() => {
    const sorted = [...this.look().items].sort(
      (a, b) =>
        layerRank(a.layer) - layerRank(b.layer) ||
        categoryRank(a.category) - categoryRank(b.category),
    );

    const groups: LayerGroup[] = [];
    for (const item of sorted) {
      const headingKey =
        item.layer === null ? 'stylist.look.layerOther' : `vocabulary.layer.${item.layer}`;
      const current = groups.at(-1);
      if (current?.headingKey === headingKey) {
        current.items.push(item);
      } else {
        groups.push({ headingKey, items: [item] });
      }
    }
    return groups;
  });

  // `category` on a missing piece is a plain string — nothing on the wire
  // narrows it (look.model.ts) — and t() falls back to the key, so an
  // unrecognised one would print `vocabulary.category.…` at the reader.
  // The description is the note 05-FRONTEND-SPEC.md asks for; the label in
  // front of it is what makes a list of two read as two.
  protected pieceLine(piece: MissingPiece): string {
    if (!isCategory(piece.category)) {
      return piece.description;
    }
    return `${this.i18n.t(`vocabulary.category.${piece.category}`)} — ${piece.description}`;
  }
}

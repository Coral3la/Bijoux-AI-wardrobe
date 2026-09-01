import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { CATEGORIES, Category, LAYERS, Layer, roleOf } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Feedback, Look, MissingPiece } from '../../shared/models/look.model';
import { Button } from '../../shared/ui/button';
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
  imports: [Button, ItemCard],
  template: `
    <article class="flex flex-col gap-5 rounded-2xl bg-surface p-5 shadow-md">
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
          <h3 class="text-xs font-medium tracking-widest text-ink-soft uppercase">
            {{ i18n.t(group.headingKey) }}
          </h3>
          <ul class="grid grid-cols-3 gap-3">
            @for (item of group.items; track item.id) {
              <li class="relative">
                <app-item-card [item]="item" />

                <!-- Beside the tile rather than inside ItemCard, which the
                     wardrobe grid renders too: a badge that only ever appears
                     in a look does not belong to the component both screens
                     share. It is a sibling of the tile's link and never inside
                     it, for item-card.ts's reason — an anchor containing a
                     button is nested interactive content. -->
                @if (isSwappable(item)) {
                  <button
                    type="button"
                    (click)="swap.emit(item)"
                    [disabled]="swappingItemId() !== null"
                    [attr.aria-label]="i18n.t('stylist.look.swap', { item: name(item) })"
                    class="absolute end-0 top-0 min-h-11 min-w-11 rounded-full bg-surface/90 text-lg disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    ↻
                  </button>
                }

                <!-- Over this tile and nothing else. The card keeps its
                     layout, its headings and every other garment while one
                     piece is being replaced. -->
                @if (swappingItemId() === item.id) {
                  <div
                    class="absolute inset-0 flex items-center justify-center rounded-xl bg-surface/80"
                    role="status"
                  >
                    <span class="sr-only">{{ i18n.t('stylist.look.swapping') }}</span>
                    <span
                      class="h-6 w-6 animate-spin rounded-full border-2 border-current/30 border-t-current"
                      aria-hidden="true"
                    ></span>
                  </div>
                }
              </li>
            }
          </ul>
        </section>
      }

      <!-- The label is a <p> rather than an <h3>: the two headings this card
           does have are the layer groups and the missing-piece list, both of
           which name a set of things, and a third one over the model's prose
           would put a section in the outline that has no section under it. -->
      <div class="flex flex-col gap-2 rounded-xl bg-surface-elevated p-4">
        <p class="text-xs font-medium tracking-widest text-ink-soft uppercase">
          {{ i18n.t('stylist.look.whyThis') }}
        </p>
        <p class="text-sm leading-relaxed">{{ look().reasoning }}</p>
        <p class="text-sm leading-relaxed">{{ look().weather_note }}</p>
      </div>

      @if (missingPieces().length > 0) {
        <section class="flex flex-col gap-1 text-sm text-ink-muted">
          <h3 class="text-xs font-medium tracking-widest text-ink-soft uppercase">
            {{ i18n.t('stylist.look.missing') }}
          </h3>
          <ul class="flex flex-col gap-1">
            @for (piece of missingPieces(); track $index) {
              <li>{{ pieceLine(piece) }}</li>
            }
          </ul>
        </section>
      }

      <!-- 05-FRONTEND-SPEC.md draws [♡ Save] [👍] [👎] [↻ Again] as one row;
           the two thumbs are 3.3's and land between these. -->
      <div class="flex items-center gap-3">
        <!-- A toggle button with a fixed accessible name, rather than a label
             that swaps between "Save" and "Unsave": aria-pressed already
             carries the state, and changing both means a screen reader
             announces the change twice and disagrees with itself about which
             direction the press goes. -->
        <button
          appButton
          variant="secondary"
          type="button"
          (click)="save.emit()"
          [disabled]="busy()"
          [attr.aria-pressed]="look().is_saved"
          [attr.aria-label]="i18n.t('stylist.look.save')"
          class="disabled:opacity-50"
        >
          <span aria-hidden="true">{{ look().is_saved ? '♥' : '♡' }}</span>
        </button>

        <!-- Two toggles rather than one three-state control, because that is
             what 05-FRONTEND-SPEC.md draws and what the wire says: the tap
             that clears a rating is the *same* thumb pressed again, and
             aria-pressed carries which one is on. Fixed accessible names, for
             the heart's reason one control along.

             The pressed state is a ring rather than a second glyph: emoji have
             no hollow/filled pair for thumbs the way ♡/♥ are a pair, and the
             nearest thing — the same thumb with a skin-tone modifier — would
             encode "off" as a skin tone. aria-pressed is what actually carries
             the state; the ring is its visible half. -->
        <button
          appButton
          variant="secondary"
          type="button"
          (click)="rate(1)"
          [disabled]="busy()"
          [attr.aria-pressed]="look().feedback === 1"
          [attr.aria-label]="i18n.t('stylist.look.thumbUp')"
          [class.ring-2]="look().feedback === 1"
          class="ring-accent disabled:opacity-50"
        >
          <span aria-hidden="true">👍</span>
        </button>

        <button
          appButton
          variant="secondary"
          type="button"
          (click)="rate(-1)"
          [disabled]="busy()"
          [attr.aria-pressed]="look().feedback === -1"
          [attr.aria-label]="i18n.t('stylist.look.thumbDown')"
          [class.ring-2]="look().feedback === -1"
          class="ring-accent disabled:opacity-50"
        >
          <span aria-hidden="true">👎</span>
        </button>

        <button appButton variant="ghost" type="button" (click)="tryAgain.emit()" class="ms-auto">
          {{ i18n.t('stylist.look.tryAgain') }}
        </button>
      </div>
    </article>
  `,
})
export class LookCard {
  protected readonly i18n = inject(I18nService);

  readonly look = input.required<Look>();
  readonly missingPieces = input<readonly MissingPiece[]>([]);
  readonly message = input('');
  readonly swappingItemId = input<string | null>(null);
  // One flag for all three controls, because the store takes one write at a
  // time: a save and a rating cannot be in flight together, so two inputs
  // would always carry the same value under two names.
  readonly busy = input(false);

  readonly tryAgain = output<void>();
  readonly swap = output<Item>();
  // No payload: the card renders one look and the page already holds it. The
  // heart says "this one changed", not which one.
  readonly save = output<void>();
  // This one does carry a payload, and it is the value to *write* rather than
  // the button that was pressed: pressing the thumb a look already carries
  // clears it, so the same button emits 1 on one press and null on the next.
  readonly rated = output<Feedback | null>();

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

  // No badge on a dress, and that is the vocabulary rather than the layout:
  // replacing a dress can legally return a top and a bottom, which `04`'s
  // `replace_role` has no word for and a *single*-item swap is not. Every
  // other garment in a look has a role. AUDITS.md O-25, DECISIONS.md 175.
  protected isSwappable(item: Item): boolean {
    return roleOf(item.category) !== undefined;
  }

  // Pressing the thumb that is already on clears the rating rather than
  // rewriting it. The alternative — a rating that can only be replaced, never
  // withdrawn — makes a mis-tap permanent in what 3.5 tells the stylist.
  protected rate(value: Feedback): void {
    this.rated.emit(this.look().feedback === value ? null : value);
  }

  // The badge's accessible name has to say which garment it replaces: six ↻
  // buttons on one card are otherwise six identical announcements.
  protected name(item: Item): string {
    return item.display_name ?? this.i18n.t('item.untitled');
  }

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

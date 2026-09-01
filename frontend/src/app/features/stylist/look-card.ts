import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { CATEGORIES, Category, LAYERS, Layer, roleOf } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Feedback, Look, MissingPiece } from '../../shared/models/look.model';
import { ItemCard } from '../wardrobe/item-card';
import { LookDraft } from './look-request-form';

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

// The locale is pinned rather than read off the browser: there is one string
// table and it is `en`, so a browser locale here would print the weekday in a
// language nothing else on the screen is written in. This is 211's formatter
// coming back after 220 retired it from the header, and it earns its place this
// time: the date it prints is the one the look was built for, which is the one
// fact on this screen that is nowhere else once the picker has moved off it.
// Short forms, because the line is three fields wide and set at 11px — en-GB
// abbreviates September to "Sept", which is the locale's answer and not a typo.
const ANSWERED_FORMAT = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
});

function coatKey(includeOuterwear: boolean | null): string {
  if (includeOuterwear === null) {
    return 'stylist.look.coat.auto';
  }
  return includeOuterwear ? 'stylist.look.coat.yes' : 'stylist.look.coat.no';
}

const ICON_BUTTON =
  'inline-flex h-11 w-11 items-center justify-center rounded-full border text-base disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

@Component({
  selector: 'app-look-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard],
  template: `
    <!-- No wrapper, no fill, no shadow. The look is the last thing on the page
         and there is nothing beside it to be separated from, so a card here was
         a box drawn around the only object in the room. It sits on the canvas
         the same way the wardrobe grid does. DECISIONS.md 220. -->
    <article class="flex flex-col gap-4">
      <header class="flex flex-col gap-1">
        <!-- What the look answers, above the title it answers with. The form
             below stays editable while this is on screen, so the two can
             disagree — and that disagreement is the point: it is how a reader
             tells a look built for Tuesday from a form now set to Wednesday.
             Silent when the card was handed no parameters, which is every
             caller that is not the stylist. DECISIONS.md 220. -->
        @if (answeredLine(); as line) {
          <p class="font-mono text-[11px] tracking-[0.14em] text-ink-soft uppercase">{{ line }}</p>
        }
        <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <!-- The content face at a display size, which is 071 read exactly as
               it is written: the title was composed by the model, so what it
               gains in a redesign is size and leading and never a face. The
               picked mockup draws it in Cormorant; the rule is older than the
               mockup and was reaffirmed on the wardrobe tile caption one commit
               ago on the same class of string. DECISIONS.md 071, 220. -->
          <h2 class="font-sans text-[28px] leading-tight tracking-[-0.01em]">
            {{ look().title }}
          </h2>
          <!-- Chrome, and a number: this project counted the items, so it takes
               the mono face every other number on a converted screen takes. -->
          <span
            class="font-mono text-[11px] tracking-[0.18em] text-ink-soft uppercase tabular-nums"
          >
            {{ piecesLabel() }}
          </span>
        </div>
        @if (message(); as line) {
          <p class="font-sans text-sm text-ink-muted italic">{{ line }}</p>
        }
      </header>

      <!-- One strip, no layer headings. Sorted by layer then category still —
           the order is what 05-FRONTEND-SPEC.md asks for and it survives the
           grouping being dropped — but the layer is printed under each tile
           instead of over a section of them. Four headings above four garments
           was more chrome than the thing it organised. DECISIONS.md 220. -->
      <ul class="grid grid-cols-2 gap-x-3 gap-y-5 md:grid-cols-4">
        @for (item of sorted(); track item.id) {
          <li class="flex flex-col gap-2">
            <div class="relative">
              <!-- ItemCard captions itself on the wardrobe grid, where the
                   second line is the garment's colour. Here it is the layer,
                   so the card draws its own and turns that one off. -->
              <app-item-card [item]="item" [caption]="false" />

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
                  class="absolute end-1 top-1 inline-flex h-11 w-11 items-center justify-center rounded-full border border-line bg-canvas/90 text-base disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  ↻
                </button>
              }

              <!-- Over this tile's photograph and nothing else. The strip keeps
                   its layout, its captions and every other garment while one
                   piece is being replaced. -->
              @if (swappingItemId() === item.id) {
                <div
                  class="absolute inset-0 flex items-center justify-center rounded-[2px] bg-canvas/80"
                  role="status"
                >
                  <span class="sr-only">{{ i18n.t('stylist.look.swapping') }}</span>
                  <span
                    class="h-6 w-6 animate-spin rounded-full border-2 border-current/30 border-t-current"
                    aria-hidden="true"
                  ></span>
                </div>
              }
            </div>

            <div class="flex flex-col gap-0.5">
              <span class="font-sans text-sm text-ink">{{ name(item) }}</span>
              @if (meta(item); as line) {
                <span class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
                  {{ line }}
                </span>
              }
            </div>
          </li>
        }
      </ul>

      <!-- Two lines and no box. The label this used to carry — a caps eyebrow
           reading "Why this" — named a section that is one sentence long, and
           a sentence that has to be introduced is a sentence nobody reads.
           Both are the model's prose, so both take the content face at the size
           the direction asks for. DECISIONS.md 071, 220. -->
      <div class="flex flex-col gap-1">
        <p class="font-sans text-base leading-relaxed text-ink italic">{{ look().reasoning }}</p>
        <p class="font-sans text-sm text-ink-muted italic">{{ look().weather_note }}</p>
      </div>

      @if (missingPieces().length > 0) {
        <section class="flex flex-col gap-1">
          <h3 class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
            {{ i18n.t('stylist.look.missing') }}
          </h3>
          <ul class="flex flex-col gap-1 font-sans text-sm text-ink-muted italic">
            @for (piece of missingPieces(); track $index) {
              <li>{{ pieceLine(piece) }}</li>
            }
          </ul>
        </section>
      }

      <!-- 05-FRONTEND-SPEC.md draws [♡ Save] [👍] [👎] [↻ Again] as one row;
           the two thumbs are 3.3's and land between these. Circles on a
           hairline now rather than filled pills — three labelled buttons in a
           row was the loudest object on a screen whose subject is four
           photographs. They are 44px and not the mockup's 40: the floor is the
           project's and older than the picture. DECISIONS.md 220. -->
      <div class="flex items-center gap-2 border-t border-line pt-4">
        <!-- A toggle button with a fixed accessible name, rather than a label
             that swaps between "Save" and "Unsave": aria-pressed already
             carries the state, and changing both means a screen reader
             announces the change twice and disagrees with itself about which
             direction the press goes. -->
        <button
          type="button"
          (click)="save.emit()"
          [disabled]="busy()"
          [attr.aria-pressed]="look().is_saved"
          [attr.aria-label]="i18n.t('stylist.look.save')"
          [class]="saveClass()"
        >
          <span aria-hidden="true">{{ look().is_saved ? '♥' : '♡' }}</span>
        </button>

        <!-- Two toggles rather than one three-state control, because that is
             what 05-FRONTEND-SPEC.md draws and what the wire says: the tap
             that clears a rating is the *same* thumb pressed again, and
             aria-pressed carries which one is on. Fixed accessible names, for
             the heart's reason one control along.

             The pressed state is a ring rather than a second glyph: emoji have
             no hollow/filled pair for thumbs the way the two hearts are a pair,
             and the nearest thing — the same thumb with a skin-tone modifier —
             would encode "off" as a skin tone. The heart can fill because it
             has a filled twin; the thumbs cannot, which is why the two controls
             do not share a pressed treatment. -->
        <button
          type="button"
          (click)="rate(1)"
          [disabled]="busy()"
          [attr.aria-pressed]="look().feedback === 1"
          [attr.aria-label]="i18n.t('stylist.look.thumbUp')"
          [class]="thumbClass(look().feedback === 1)"
        >
          <span aria-hidden="true">👍</span>
        </button>

        <button
          type="button"
          (click)="rate(-1)"
          [disabled]="busy()"
          [attr.aria-pressed]="look().feedback === -1"
          [attr.aria-label]="i18n.t('stylist.look.thumbDown')"
          [class]="thumbClass(look().feedback === -1)"
        >
          <span aria-hidden="true">👎</span>
        </button>

        <button
          type="button"
          (click)="tryAgain.emit()"
          class="ms-auto inline-flex min-h-11 items-center text-[11px] font-medium tracking-[0.22em] text-accent uppercase underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ i18n.t('stylist.look.tryAgain') }}
        </button>
      </div>
    </article>
  `,
})
export class LookCard {
  protected readonly i18n = inject(I18nService);

  readonly look = input.required<Look>();
  // The request this look came back from, or null. Optional because the card
  // renders a look and a look does not know what was asked for it — only the
  // screen that asked does.
  readonly answered = input<LookDraft | null>(null);
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

  // Sorted by layer then category, and no longer cut into runs. The sort is
  // 05-FRONTEND-SPEC.md's — the sequence a user's eye and a screen reader both
  // take — and it outlives the grouping the headings gave it.
  protected readonly sorted = computed<readonly Item[]>(() =>
    [...this.look().items].sort(
      (a, b) =>
        layerRank(a.layer) - layerRank(b.layer) ||
        categoryRank(a.category) - categoryRank(b.category),
    ),
  );

  // Notes are left out on purpose: they are free text and can run to a
  // paragraph, where this line is three short fields at 11px. What is here is
  // what the request narrowed, and the notes are what widened it.
  //
  // The date is parsed at local midnight, never bare: `new Date('2026-09-01')`
  // is UTC midnight, which is the previous day west of Greenwich — the same
  // trap `todayInLocalTime` was written to avoid one file over.
  protected readonly answeredLine = computed(() => {
    const answered = this.answered();
    if (answered === null) {
      return null;
    }
    return this.i18n.t('stylist.look.answered', {
      occasion: this.i18n.t(`vocabulary.occasion.${answered.occasion}`),
      date: ANSWERED_FORMAT.format(new Date(`${answered.date}T00:00:00`)),
      coat: this.i18n.t(coatKey(answered.include_outerwear)),
    });
  });

  // I18nService has no plural rule (DECISIONS.md 058), so the caller picks the
  // key. A look of one is reachable — a dress with nothing else that passed the
  // rules — so the singular is not hypothetical.
  protected readonly piecesLabel = computed(() => {
    const count = this.look().items.length;
    return count === 1
      ? this.i18n.t('stylist.look.pieces.one')
      : this.i18n.t('stylist.look.pieces.other', { count });
  });

  // Both halves are our own closed vocabulary, so the line is chrome and the
  // separator is language and lives in the string table with it. Either half
  // can be absent on a row the wardrobe never finished tagging, and the key is
  // only used when both are there — `t()` leaves an unsupplied placeholder
  // visible on purpose, so half this line would read "Base layer · {{category}}".
  protected meta(item: Item): string | null {
    const layer = item.layer === null ? null : this.i18n.t(`vocabulary.layer.${item.layer}`);
    const category =
      item.category === null ? null : this.i18n.t(`vocabulary.category.${item.category}`);
    if (layer !== null && category !== null) {
      return this.i18n.t('stylist.look.meta', { layer, category });
    }
    return layer ?? category;
  }

  // The heart fills because it has a filled twin; the ring is what the thumbs
  // get instead. Written out rather than bound class by class because the
  // pressed heart changes three properties at once and a chain of
  // [class.x] bindings for one state is harder to read than one string.
  protected saveClass(): string {
    return this.look().is_saved
      ? `${ICON_BUTTON} border-accent bg-accent text-canvas`
      : `${ICON_BUTTON} border-line text-ink`;
  }

  protected thumbClass(active: boolean): string {
    return active
      ? `${ICON_BUTTON} border-accent text-ink ring-2 ring-accent`
      : `${ICON_BUTTON} border-line text-ink`;
  }

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
  // buttons on one card are otherwise six identical announcements. It is also
  // the caption under the tile now, which is the same string for the same
  // reason — a garment is named by what it is.
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

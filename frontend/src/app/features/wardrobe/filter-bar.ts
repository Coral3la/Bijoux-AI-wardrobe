import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { ItemFilters, SCALE_MAX, SCALE_MIN } from '../../core/state/wardrobe.store';
import { CATEGORIES, COLORS, Category, Color } from '../../shared/models/enums';

// What the wardrobe knows about its own shape, counted where the collection
// lives and passed in rather than fetched here: this bar is given the filters
// it draws and it is given the numbers it draws, so it stays a component with
// two inputs and one output. `all` is separate from the map rather than an
// 'all' key in it, because 'all' is not a Category and typing it as one would
// make `Record<Category, number>` a lie the compiler stops checking.
export interface CategoryCounts {
  readonly all: number;
  readonly byCategory: ReadonlyMap<Category, number>;
}

// Presentation, not vocabulary: these are what a swatch is painted, while the
// words themselves are in en.json, under `vocabulary.*` since 1.9 — a screen's
// namespace was the wrong home for words a second screen now reads (118). `satisfies` is doing real work here — a
// colour added to enums.ts fails this file at compile time, which makes it the
// one mirror on this project that cannot silently drift (CONVENTIONS.md's
// hand-mirrored-constant problem, for once with a compiler watching it).
const SWATCHES = {
  black: '#111111',
  white: '#ffffff',
  grey: '#9ca3af',
  beige: '#e7d8bf',
  brown: '#7a5230',
  navy: '#1e2a5a',
  blue: '#2563eb',
  light_blue: '#93c5fd',
  red: '#dc2626',
  pink: '#f7a8cc',
  orange: '#ea580c',
  yellow: '#facc15',
  green: '#16a34a',
  olive: '#6b7a2f',
  purple: '#7c3aed',
  gold: '#c9a227',
  silver: '#c3c8d0',
} as const satisfies Record<Color, string>;

// Written here rather than taken from the shared `appChip` directive, and that
// is a decision rather than an oversight. The directive paints the pre-Atelier
// chip — 14px, a strong line, a white fill — and it sets its font size in the
// base string every variant shares, so a caller cannot make an 11px chip out of
// it: two utilities setting one property are settled by the order of the
// compiled stylesheet, which is the trap chip.ts itself documents. Five screens
// still want the chip the directive draws. When they are converted the
// directive becomes this and these constants go. DECISIONS.md 219.
const CHIP =
  'inline-flex min-h-11 shrink-0 items-center gap-x-1.5 rounded-full border px-4 text-[11px] font-medium tracking-[0.18em] uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
const CHIP_STATES = {
  inactive: 'border-line text-ink-muted',
  active: 'border-ink bg-ink text-canvas',
} as const;

@Component({
  selector: 'app-filter-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="flex flex-col gap-4">
      <!-- Wrapping, where 1.8 scrolled. The horizontal row was drawn by
           05-FRONTEND-SPEC.md's mockup and nothing ever scrolled it for the
           user — scrollIntoView is undefined in jsdom, so a selected chip off
           the right edge stayed there. The picked mockup wraps, which also
           removes the reason that bug existed. -->
      <div class="flex flex-wrap items-center gap-1.5">
        <!-- aria-pressed is bound here again, where 1.8 had handed it to
             appChip. chip.ts's warning was that a template binding outranks a
             directive host binding and lets the announced state drift from the
             painted one; with no directive there is nothing to drift against,
             and one expression paints and announces. The spec asserts it on a
             selected chip and an unselected one, which is what holds it.
             A backtick in a template comment would end the literal, so this one
             quotes nothing. -->
        <button
          type="button"
          [attr.aria-pressed]="filters().category === undefined"
          [class]="chipClass(filters().category === undefined)"
          (click)="chooseCategory(undefined)"
        >
          <span>{{ i18n.t('wardrobe.filter.category.all') }}</span>
          <span [class]="countClass(filters().category === undefined)">{{ counts().all }}</span>
        </button>
        @for (category of categories; track category) {
          <!-- Every category, including the ones at zero. The chips are the
               closed vocabulary rather than a summary of what is in the
               wardrobe, so a row that grew and shrank as garments were tagged
               would move under the reader's finger — and a zero is a true
               answer to "how many trousers do I own". -->
          <button
            type="button"
            [attr.aria-pressed]="filters().category === category"
            [class]="chipClass(filters().category === category)"
            (click)="chooseCategory(category)"
          >
            <span>{{ i18n.t('vocabulary.category.' + category) }}</span>
            <span [class]="countClass(filters().category === category)">{{
              countOf(category)
            }}</span>
          </button>
        }

        <!-- The one chip with no count, because it counts nothing: it opens the
             three dimensions below rather than naming a subset of the grid. A
             disclosure rather than a sheet — a modal over the grid hides the
             thing being filtered, which is 098's own argument for why the
             gallery path closes the upload sheet. O-15 is answered by this
             rather than acted on. DECISIONS.md 113. -->
        <button
          type="button"
          [attr.aria-expanded]="open()"
          [class]="chipClass(open())"
          (click)="toggle()"
        >
          {{ i18n.t('wardrobe.filter.title') }}
        </button>

        @if (isFiltered()) {
          <button
            type="button"
            (click)="clear()"
            class="inline-flex min-h-11 shrink-0 items-center px-2 text-[11px] font-medium tracking-[0.18em] text-accent uppercase underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('wardrobe.filter.clear') }}
          </button>
        }
      </div>

      @if (open()) {
        <div class="flex flex-col gap-5 rounded-[2px] border border-line p-5">
          <fieldset class="flex flex-col gap-3">
            <legend class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
              {{ i18n.t('wardrobe.filter.color') }}
            </legend>
            <div class="flex flex-wrap gap-2">
              @for (color of colors; track color) {
                <!-- The label is the only thing distinguishing one swatch from
                     another to a screen reader: the control is a colour and
                     carries no text. DECISIONS.md 114. -->
                <button
                  type="button"
                  [attr.aria-label]="i18n.t('vocabulary.color.' + color)"
                  [attr.aria-pressed]="filters().color_primary === color"
                  [style.background-color]="swatch(color)"
                  (click)="chooseColor(color)"
                  [class]="swatchClass(filters().color_primary === color)"
                ></button>
              }
            </div>
          </fieldset>

          <fieldset class="flex flex-col gap-3">
            <legend class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
              {{ i18n.t('wardrobe.filter.formality') }}
            </legend>
            <div class="flex items-center gap-3">
              <!-- Both handles carry an explicit [value]. An unbound range reads
                   50 in the gate and 3 in a browser, so a test asserting an
                   initial position would be asserting jsdom. DECISIONS.md 115. -->
              <input
                type="range"
                step="1"
                [min]="min"
                [max]="max"
                [value]="formalityMin()"
                [attr.aria-label]="rangeLabel('wardrobe.filter.rangeMin', 'formality')"
                (input)="setFormality('min', $event)"
                class="w-full accent-ink"
              />
              <input
                type="range"
                step="1"
                [min]="min"
                [max]="max"
                [value]="formalityMax()"
                [attr.aria-label]="rangeLabel('wardrobe.filter.rangeMax', 'formality')"
                (input)="setFormality('max', $event)"
                class="w-full accent-ink"
              />
              <span class="shrink-0 font-mono text-xs text-ink-muted tabular-nums"
                >{{ formalityMin() }}–{{ formalityMax() }}</span
              >
            </div>
          </fieldset>

          <fieldset class="flex flex-col gap-3">
            <legend class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
              {{ i18n.t('wardrobe.filter.warmth') }}
            </legend>
            <div class="flex items-center gap-3">
              <input
                type="range"
                step="1"
                [min]="min"
                [max]="max"
                [value]="warmthMin()"
                [attr.aria-label]="rangeLabel('wardrobe.filter.rangeMin', 'warmth')"
                (input)="setWarmth('min', $event)"
                class="w-full accent-ink"
              />
              <input
                type="range"
                step="1"
                [min]="min"
                [max]="max"
                [value]="warmthMax()"
                [attr.aria-label]="rangeLabel('wardrobe.filter.rangeMax', 'warmth')"
                (input)="setWarmth('max', $event)"
                class="w-full accent-ink"
              />
              <span class="shrink-0 font-mono text-xs text-ink-muted tabular-nums"
                >{{ warmthMin() }}–{{ warmthMax() }}</span
              >
            </div>
          </fieldset>
        </div>
      }
    </section>
  `,
})
export class FilterBar {
  protected readonly i18n = inject(I18nService);

  readonly filters = input.required<ItemFilters>();
  readonly counts = input.required<CategoryCounts>();
  readonly filtersChanged = output<ItemFilters>();

  protected readonly categories = CATEGORIES;
  protected readonly colors = COLORS;
  protected readonly min = SCALE_MIN;
  protected readonly max = SCALE_MAX;

  protected readonly open = signal(false);

  // The same key count the page reads, for the same reason: a normalised filter
  // object carries only its active keys, so an empty one is an empty object.
  protected readonly isFiltered = computed(() => Object.keys(this.filters()).length > 0);

  // An absent bound is the end of the scale rather than nothing, because a range
  // input has to be somewhere. The filter object keeps the distinction; these
  // two are only ever what the control is drawn at.
  protected readonly formalityMin = computed(() => this.filters().formality_min ?? SCALE_MIN);
  protected readonly formalityMax = computed(() => this.filters().formality_max ?? SCALE_MAX);
  protected readonly warmthMin = computed(() => this.filters().warmth_min ?? SCALE_MIN);
  protected readonly warmthMax = computed(() => this.filters().warmth_max ?? SCALE_MAX);

  protected countOf(category: Category): number {
    return this.counts().byCategory.get(category) ?? 0;
  }

  protected chipClass(active: boolean): string {
    return `${CHIP} ${active ? CHIP_STATES.active : CHIP_STATES.inactive}`;
  }

  // The count leaves the chip's letter-spacing and takes the mono face, so a
  // number on this screen is drawn one way wherever it appears — the piece
  // count in the header, the temperature in the weather line, these. Inverted
  // rather than recoloured on an active chip: the ground has gone dark under
  // it, so a soft grey would be the one unreadable thing in the row.
  protected countClass(active: boolean): string {
    const base = 'font-mono text-[10px] font-normal tracking-normal tabular-nums';
    return active ? `${base} text-canvas/65` : `${base} text-ink-soft`;
  }

  protected toggle(): void {
    this.open.update((open) => !open);
  }

  protected swatch(color: Color): string {
    return SWATCHES[color];
  }

  protected rangeLabel(key: string, dimension: 'formality' | 'warmth'): string {
    return this.i18n.t(key, { name: this.i18n.t(`wardrobe.filter.${dimension}`) });
  }

  protected swatchClass(selected: boolean): string {
    const base =
      'h-11 w-11 rounded-full border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
    return selected ? `${base} border-ink border-4` : `${base} border-line`;
  }

  // Single-valued, so tapping the selected one clears it. Multi-select was
  // declined rather than deferred: nothing in 1.8's brief asks for it, and it
  // costs an OR nested inside the AND plus comma parsing in the URL. 109.
  protected chooseCategory(category: Category | undefined): void {
    this.filtersChanged.emit({ ...this.filters(), category });
  }

  protected chooseColor(color: Color): void {
    const current = this.filters().color_primary;
    this.filtersChanged.emit({
      ...this.filters(),
      color_primary: current === color ? undefined : color,
    });
  }

  // Both bounds go out on every change, so the emitted object always describes
  // a whole interval. Rounding and ordering are the store's — this reads the
  // control and nothing else. DECISIONS.md 115.
  protected setFormality(edge: 'min' | 'max', event: Event): void {
    const value = (event.target as HTMLInputElement).valueAsNumber;
    this.filtersChanged.emit({
      ...this.filters(),
      formality_min: edge === 'min' ? value : this.formalityMin(),
      formality_max: edge === 'max' ? value : this.formalityMax(),
    });
  }

  protected setWarmth(edge: 'min' | 'max', event: Event): void {
    const value = (event.target as HTMLInputElement).valueAsNumber;
    this.filtersChanged.emit({
      ...this.filters(),
      warmth_min: edge === 'min' ? value : this.warmthMin(),
      warmth_max: edge === 'max' ? value : this.warmthMax(),
    });
  }

  protected clear(): void {
    this.filtersChanged.emit({});
  }
}

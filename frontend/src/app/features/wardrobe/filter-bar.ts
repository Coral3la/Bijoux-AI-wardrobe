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

// Presentation, not vocabulary: these are what a swatch is painted, while the
// words themselves are in en.json. `satisfies` is doing real work here — a
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

@Component({
  selector: 'app-filter-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="flex flex-col gap-3">
      <!-- 05-FRONTEND-SPEC.md's mockup draws this row scrolling horizontally
           rather than wrapping. Nothing scrolls it for the user: scrollIntoView
           is undefined in jsdom and calling it throws, so a selected chip off
           the right edge stays there. Measured, not assumed — 06's probe. -->
      <div class="flex flex-nowrap items-center gap-2 overflow-x-auto pb-1">
        <button
          type="button"
          [attr.aria-pressed]="filters().category === undefined"
          (click)="chooseCategory(undefined)"
          [class]="chipClass(filters().category === undefined)"
        >
          {{ i18n.t('wardrobe.filter.category.all') }}
        </button>
        @for (category of categories; track category) {
          <button
            type="button"
            [attr.aria-pressed]="filters().category === category"
            (click)="chooseCategory(category)"
            [class]="chipClass(filters().category === category)"
          >
            {{ i18n.t('wardrobe.filter.category.' + category) }}
          </button>
        }
      </div>

      <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <!-- A disclosure rather than a sheet. A modal over the grid hides the
             thing being filtered, which is 098's own argument for why the
             gallery path closes the upload sheet. O-15 is answered by this
             rather than acted on. DECISIONS.md 113. -->
        <button
          type="button"
          [attr.aria-expanded]="open()"
          (click)="toggle()"
          class="min-h-11 rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ i18n.t('wardrobe.filter.title') }}
        </button>
        @if (isFiltered()) {
          <button
            type="button"
            (click)="clear()"
            class="min-h-11 rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('wardrobe.filter.clear') }}
          </button>
        }
      </div>

      @if (open()) {
        <div class="flex flex-col gap-5 rounded-lg bg-surface p-4 shadow-sm">
          <fieldset class="flex flex-col gap-2">
            <legend class="text-sm font-medium">{{ i18n.t('wardrobe.filter.color') }}</legend>
            <div class="flex flex-wrap gap-2">
              @for (color of colors; track color) {
                <!-- The label is the only thing distinguishing one swatch from
                     another to a screen reader: the control is a colour and
                     carries no text. DECISIONS.md 114. -->
                <button
                  type="button"
                  [attr.aria-label]="i18n.t('wardrobe.filter.color.' + color)"
                  [attr.aria-pressed]="filters().color_primary === color"
                  [style.background-color]="swatch(color)"
                  (click)="chooseColor(color)"
                  [class]="swatchClass(filters().color_primary === color)"
                ></button>
              }
            </div>
          </fieldset>

          <fieldset class="flex flex-col gap-2">
            <legend class="text-sm font-medium">{{ i18n.t('wardrobe.filter.formality') }}</legend>
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
                class="w-full"
              />
              <input
                type="range"
                step="1"
                [min]="min"
                [max]="max"
                [value]="formalityMax()"
                [attr.aria-label]="rangeLabel('wardrobe.filter.rangeMax', 'formality')"
                (input)="setFormality('max', $event)"
                class="w-full"
              />
              <span class="shrink-0 text-sm">{{ formalityMin() }}–{{ formalityMax() }}</span>
            </div>
          </fieldset>

          <fieldset class="flex flex-col gap-2">
            <legend class="text-sm font-medium">{{ i18n.t('wardrobe.filter.warmth') }}</legend>
            <div class="flex items-center gap-3">
              <input
                type="range"
                step="1"
                [min]="min"
                [max]="max"
                [value]="warmthMin()"
                [attr.aria-label]="rangeLabel('wardrobe.filter.rangeMin', 'warmth')"
                (input)="setWarmth('min', $event)"
                class="w-full"
              />
              <input
                type="range"
                step="1"
                [min]="min"
                [max]="max"
                [value]="warmthMax()"
                [attr.aria-label]="rangeLabel('wardrobe.filter.rangeMax', 'warmth')"
                (input)="setWarmth('max', $event)"
                class="w-full"
              />
              <span class="shrink-0 text-sm">{{ warmthMin() }}–{{ warmthMax() }}</span>
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

  protected toggle(): void {
    this.open.update((open) => !open);
  }

  protected swatch(color: Color): string {
    return SWATCHES[color];
  }

  protected rangeLabel(key: string, dimension: 'formality' | 'warmth'): string {
    return this.i18n.t(key, { name: this.i18n.t(`wardrobe.filter.${dimension}`) });
  }

  protected chipClass(selected: boolean): string {
    const base =
      'min-h-11 shrink-0 rounded-full px-4 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
    return selected ? `${base} bg-accent text-surface` : `${base} bg-surface`;
  }

  protected swatchClass(selected: boolean): string {
    const base =
      'h-11 w-11 rounded-full border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
    return selected ? `${base} border-accent border-4` : `${base} border-black/20`;
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

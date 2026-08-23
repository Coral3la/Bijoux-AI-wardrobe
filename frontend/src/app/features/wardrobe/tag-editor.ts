import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';

import { I18nService } from '../../core/i18n/i18n.service';
import { SCALE_MAX, SCALE_MIN } from '../../core/state/wardrobe.store';
import {
  CATEGORIES,
  COLORS,
  FITS,
  LAYERS,
  LENGTHS,
  MATERIALS,
  PATTERNS,
  RISES,
  SUBCATEGORIES,
} from '../../shared/models/enums';
import { Item, ItemUpdate } from '../../shared/models/item.model';

// The five the server nulls when the category changes, mirrored from
// CATEGORY_DEPENDENT_FIELDS in app/enums.py. This is the one place the client
// repeats a backend list, and it is deliberate: the form clears them on screen
// so the user sees five empty fields before saving, which STAGE-1 1.9 requires
// in as many words. Because every save sends all fourteen fields, the server's
// own clearing branch never fires — `field not in changes` is its guard — so
// this list is the *only* thing that clears them, not a duplicate of something
// that would also happen. DECISIONS.md 119.
const DEPENDENT_FIELDS = ['subcategory', 'rise', 'fit', 'length', 'layer'] as const;

// Empty string is the DOM's answer for "no option selected", and null is the
// wire's. One conversion at each edge rather than a nullable form value: a
// <select> cannot hold null, and pretending otherwise puts the coercion in
// every binding instead of in two functions.
const UNSET = '';

function toWire(value: string): string | null {
  return value === UNSET ? null : value;
}

function toForm(value: string | null): string {
  return value ?? UNSET;
}

@Component({
  selector: 'app-tag-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule],
  template: `
    <form [formGroup]="form" (ngSubmit)="submit()" novalidate class="flex flex-col gap-5">
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <!-- Category first, and it is the only select whose empty option is
             conditional. O-3 opens this editor from a failed tile where every
             tag is null, so the control must be able to say "not chosen yet" —
             but offering that same option on an item that has a category would
             be offering to clear it, which Q7 declined. So the placeholder is
             rendered only while the stored value is null and disappears after
             the first save. DECISIONS.md 123. -->
        <label class="flex flex-col gap-1 text-sm">
          {{ i18n.t('item.field.category') }}
          <select
            id="category"
            formControlName="category"
            (change)="onCategoryChange()"
            [class]="selectClass"
          >
            @if (categoryUnset()) {
              <option [value]="UNSET">{{ i18n.t('item.edit.choose') }}</option>
            }
            @for (value of categories; track value) {
              <option [value]="value">{{ i18n.t('vocabulary.category.' + value) }}</option>
            }
          </select>
        </label>

        <!-- Options narrow by category because SUBCATEGORIES is a *value*
             mirror that already exists in enums.ts. The category-dependent
             rules for fit, length and rise are not mirrored and the selects
             below offer every word: those are rules, they live server-side
             (085), and copying them is what B declined. DECISIONS.md 124. -->
        <label class="flex flex-col gap-1 text-sm">
          {{ i18n.t('item.field.subcategory') }}
          <select id="subcategory" formControlName="subcategory" [class]="selectClass">
            <option [value]="UNSET">{{ i18n.t('item.edit.unset') }}</option>
            @for (value of subcategories(); track value) {
              <option [value]="value">{{ i18n.t('vocabulary.subcategory.' + value) }}</option>
            }
          </select>
        </label>

        @for (field of vocabularyFields; track field.name) {
          <label class="flex flex-col gap-1 text-sm">
            {{ i18n.t('item.field.' + field.name) }}
            <select [id]="field.name" [formControlName]="field.name" [class]="selectClass">
              <option [value]="UNSET">{{ i18n.t('item.edit.unset') }}</option>
              @for (value of field.values; track value) {
                <option [value]="value">{{ i18n.t(field.prefix + value) }}</option>
              }
            </select>
          </label>
        }
      </div>

      <!-- Both handles carry an explicit [value] through the form control. An
           unbound range reads 50 in the gate and 3 in a browser, and jsdom does
           not snap to step — so the coercion is ours, at submit, exactly as 115
           put it at the store's one door into filter state. -->
      @for (scale of scales; track scale) {
        <label class="flex flex-col gap-1 text-sm">
          {{ i18n.t('item.field.' + scale) }}
          <input
            type="range"
            [id]="scale"
            [formControlName]="scale"
            [min]="SCALE_MIN"
            [max]="SCALE_MAX"
            step="1"
            class="w-full"
          />
        </label>
      }

      <label class="flex min-h-11 items-center gap-2 text-sm">
        <input type="checkbox" id="water_resistant" formControlName="water_resistant" />
        {{ i18n.t('item.edit.waterResistant') }}
      </label>

      <!-- The one free-text field, and STAGE-1 1.9's "never a free-text input"
           is corrected rather than obeyed: it means a *tag* is never free text.
           display_name is not a tag — it is the alt text and the only
           human-readable thing on a row with no tags, which is the row this
           screen exists for. DECISIONS.md 125. -->
      <label class="flex flex-col gap-1 text-sm">
        {{ i18n.t('item.edit.name') }}
        <input
          type="text"
          id="display_name"
          formControlName="display_name"
          [placeholder]="i18n.t('item.edit.namePlaceholder')"
          class="min-h-11 rounded-md border border-current/20 bg-surface px-3"
        />
      </label>

      @if (blocked()) {
        <p class="text-sm font-medium text-danger">{{ i18n.t('item.edit.chooseCategory') }}</p>
      }
      @if (errorKey(); as key) {
        <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
      }

      <button
        type="submit"
        [disabled]="saving()"
        class="min-h-11 self-start rounded-md bg-accent px-4 text-surface disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ saving() ? i18n.t('item.edit.saving') : i18n.t('item.edit.save') }}
      </button>
    </form>
  `,
})
export class TagEditor {
  protected readonly i18n = inject(I18nService);
  private readonly fb = inject(NonNullableFormBuilder);

  readonly item = input.required<Item>();
  readonly saving = input(false);
  readonly errorKey = input<string | null>(null);

  readonly save = output<ItemUpdate>();

  protected readonly UNSET = UNSET;
  protected readonly SCALE_MIN = SCALE_MIN;
  protected readonly SCALE_MAX = SCALE_MAX;
  protected readonly categories = CATEGORIES;
  protected readonly scales = ['formality', 'warmth'] as const;
  protected readonly selectClass =
    'min-h-11 rounded-md border border-current/20 bg-surface px-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

  protected readonly vocabularyFields = [
    { name: 'fit', values: FITS, prefix: 'vocabulary.fit.' },
    { name: 'length', values: LENGTHS, prefix: 'vocabulary.length.' },
    { name: 'rise', values: RISES, prefix: 'vocabulary.rise.' },
    { name: 'color_primary', values: COLORS, prefix: 'vocabulary.color.' },
    { name: 'color_secondary', values: COLORS, prefix: 'vocabulary.color.' },
    { name: 'pattern', values: PATTERNS, prefix: 'vocabulary.pattern.' },
    { name: 'material', values: MATERIALS, prefix: 'vocabulary.material.' },
    { name: 'layer', values: LAYERS, prefix: 'vocabulary.layer.' },
  ] as const;

  // Built once from the input, never re-synced from it. A save answers with the
  // whole row and the parent replaces the item, and re-seeding the form on that
  // would throw away anything typed since — which is the condition attached to
  // B: a rejection must keep every value the user entered, and the same is true
  // of a success the user has already typed past.
  protected readonly form = this.fb.group({
    category: UNSET,
    subcategory: UNSET,
    fit: UNSET,
    length: UNSET,
    rise: UNSET,
    color_primary: UNSET,
    color_secondary: UNSET,
    pattern: UNSET,
    material: UNSET,
    layer: UNSET,
    formality: SCALE_MIN,
    warmth: SCALE_MIN,
    water_resistant: false,
    display_name: '',
  });

  // Whether the *stored* row had no category, which is what decides the
  // placeholder. Read from the input rather than from the control, so choosing
  // a category makes the option disappear and re-choosing "not chosen" is not
  // offered — while a save that fails leaves it exactly where it was.
  protected readonly categoryUnset = computed(() => this.item().category === null);

  // A signal rather than a read of `form.controls.category.value`: a computed
  // over a plain form control never recomputes, because nothing tells it the
  // value moved. Written in the two places the category can change — the seed
  // and the change handler — which is also the whole list of them.
  private readonly category = signal<string>(UNSET);

  protected readonly subcategories = computed(() => {
    const category = this.category();
    return category === UNSET ? [] : SUBCATEGORIES[category as keyof typeof SUBCATEGORIES];
  });

  // Set only by a submit that could not proceed, so the message appears when
  // the user asks to save and not while they are still filling the form in.
  private readonly blockedSignal = signal(false);
  protected readonly blocked = this.blockedSignal.asReadonly();

  private seeded = false;

  constructor() {
    // Seeded once. A save answers with the whole row and the parent replaces
    // the item, so an effect that re-seeded on every change would discard
    // anything typed since the request went out — including, on a rejection,
    // the values that caused it. B's condition is that the form keeps them.
    effect(() => {
      const item = this.item();
      if (this.seeded) {
        return;
      }
      this.seeded = true;
      this.seed(item);
    });
  }

  // The cascade STAGE-1 1.9 requires in as many words: five empty fields on
  // screen before saving, not four and not one. Because all fourteen fields are
  // sent, those five leave as explicit nulls and the server's own clearing
  // branch never runs.
  protected onCategoryChange(): void {
    this.category.set(this.form.controls.category.value);
    for (const field of DEPENDENT_FIELDS) {
      this.form.controls[field].setValue(UNSET);
    }
  }

  protected submit(): void {
    const value = this.form.getRawValue();
    if (value.category === UNSET) {
      this.blockedSignal.set(true);
      return;
    }
    this.blockedSignal.set(false);
    this.save.emit({
      category: value.category,
      subcategory: toWire(value.subcategory),
      fit: toWire(value.fit),
      length: toWire(value.length),
      rise: toWire(value.rise),
      color_primary: toWire(value.color_primary),
      color_secondary: toWire(value.color_secondary),
      pattern: toWire(value.pattern),
      material: toWire(value.material),
      layer: toWire(value.layer),
      // Rounded and clamped here rather than trusted to the control: jsdom does
      // not snap to `step` and an unbound range reads 50. 115, one screen over.
      formality: scalePoint(value.formality),
      warmth: scalePoint(value.warmth),
      water_resistant: value.water_resistant,
      display_name: value.display_name.trim() === '' ? null : value.display_name.trim(),
    });
  }

  private seed(item: Item): void {
    this.category.set(toForm(item.category));
    this.form.setValue({
      category: toForm(item.category),
      subcategory: toForm(item.subcategory),
      fit: toForm(item.fit),
      length: toForm(item.length),
      rise: toForm(item.rise),
      color_primary: toForm(item.color_primary),
      color_secondary: toForm(item.color_secondary),
      pattern: toForm(item.pattern),
      material: toForm(item.material),
      layer: toForm(item.layer),
      formality: item.formality ?? SCALE_MIN,
      warmth: item.warmth ?? SCALE_MIN,
      water_resistant: item.water_resistant,
      display_name: item.display_name ?? '',
    });
  }
}

function scalePoint(value: number): number {
  return Math.min(SCALE_MAX, Math.max(SCALE_MIN, Math.round(value)));
}

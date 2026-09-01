import { Directive, computed, input } from '@angular/core';

export type ChipVariant = 'default' | 'accent';

// Atelier's chip, and the conversion 220 asked for rather than a third copy of
// it. `filter-bar.ts` and `look-request-form.ts` wrote the same treatment out
// locally because this directive set its font size in the base string every
// variant shares; the trip form is the third screen to need it and is also the
// only caller this directive has left, so converting it here changes exactly one
// screen's paint and retires the copy that would otherwise have been written.
// DECISIONS.md 219, 220, 222.
const BASE =
  'inline-flex min-h-11 items-center rounded-full border px-4 text-[11px] font-medium tracking-[0.18em] uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

// `accent` has no caller and is left standing rather than deleted: it lost its
// last one when the wardrobe's filter bar was converted, which is a tidy that
// belongs to whoever is looking at that screen. It is re-struck off the same
// shape so the two variants cannot drift into different chips.
const STATES: Record<ChipVariant, { readonly inactive: string; readonly active: string }> = {
  default: {
    inactive: 'border-line text-ink-muted',
    active: 'border-ink bg-ink text-canvas',
  },
  accent: {
    inactive: 'border-line bg-surface text-ink-muted',
    active: 'border-accent-soft bg-accent-wash text-accent',
  },
};

@Directive({
  selector: '[appChip]',
  host: {
    '[class]': 'classes()',
    // The state is announced from the same input that paints it, so a caller
    // that styles a toggle cannot ship one that says nothing. A caller keeping
    // its own [attr.aria-pressed] would win this silently: a template binding
    // outranks a directive host binding.
    '[attr.aria-pressed]': 'active()',
  },
})
export class Chip {
  readonly active = input(false);
  readonly variant = input<ChipVariant>('default');

  protected readonly classes = computed(() => {
    const state = STATES[this.variant()];
    return `${BASE} ${this.active() ? state.active : state.inactive}`;
  });
}

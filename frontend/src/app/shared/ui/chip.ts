import { Directive, computed, input } from '@angular/core';

export type ChipVariant = 'default' | 'accent';

const BASE =
  'min-h-11 inline-flex items-center rounded-full px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const STATES: Record<ChipVariant, { readonly inactive: string; readonly active: string }> = {
  default: {
    inactive: 'bg-surface text-ink border border-line-strong',
    active: 'bg-ink text-surface',
  },
  accent: {
    inactive: 'bg-surface text-ink-muted border border-line',
    active: 'bg-accent-wash text-accent border border-accent-soft',
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

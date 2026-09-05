import { Directive, computed, input } from '@angular/core';

// Atelier's chip, and the conversion 220 asked for rather than a third copy of
// it. `filter-bar.ts` and `look-request-form.ts` wrote the same treatment out
// locally because this directive set its font size in the base string every
// variant shares; the trip form is the third screen to need it and is also the
// only caller this directive has left, so converting it here changes exactly one
// screen's paint and retires the copy that would otherwise have been written.
// DECISIONS.md 219, 220, 222.
const BASE =
  'inline-flex min-h-11 items-center rounded-full border px-4 text-[11px] font-medium tracking-[0.18em] uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const STATES = {
  inactive: 'border-line text-ink-muted',
  active: 'border-ink bg-ink text-canvas',
} as const;

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

  protected readonly classes = computed(
    () => `${BASE} ${this.active() ? STATES.active : STATES.inactive}`,
  );
}

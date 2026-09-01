import { Directive, computed, input } from '@angular/core';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

// A directive rather than a component, which is why there is no template here:
// the caller's own <button> or <a> already carries focus, keyboard, type,
// disabled and every aria attribute a screen needs, and a wrapper element would
// have to re-expose each of them as a passthrough input.
//
// There is deliberately no size input. 05-FRONTEND-SPEC.md's "Every interactive
// element ≥ 44px tall" makes 44px a floor rather than a default, so a compact
// button comes from the ghost variant or from the caller's own padding — never
// from a shorter height.
const BASE =
  'min-h-11 inline-flex items-center justify-center rounded-md px-5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-surface hover:bg-accent-hover',
  secondary: 'bg-surface text-ink border border-line-strong hover:bg-surface-elevated',
  ghost: 'bg-transparent text-ink underline underline-offset-4 hover:text-ink-muted',
  danger: 'bg-transparent text-danger border border-danger hover:bg-danger hover:text-surface',
};

@Directive({
  selector: '[appButton]',
  host: {
    '[class]': 'classes()',
  },
})
export class Button {
  readonly variant = input<ButtonVariant>('primary');

  protected readonly classes = computed(() => `${BASE} ${VARIANTS[this.variant()]}`);
}

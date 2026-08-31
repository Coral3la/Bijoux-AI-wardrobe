import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class:
      'flex flex-col items-center gap-4 rounded-xl border border-dashed border-line-strong bg-surface-elevated px-6 py-12 text-center',
  },
  // h2 because both callers are h2 today and the document outline has to
  // survive the refresh. The icon is a path `d` bound as an attribute rather
  // than markup pushed through innerHTML, so no sanitiser is involved.
  template: `
    @if (icon() !== null) {
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="h-10 w-10 text-ink-soft"
        aria-hidden="true"
      >
        <path [attr.d]="icon()" />
      </svg>
    }

    <h2 class="font-display text-2xl leading-tight">{{ title() }}</h2>

    @if (description() !== null) {
      <p class="max-w-prose text-sm text-ink-muted">{{ description() }}</p>
    }

    <ng-content />
  `,
})
export class EmptyState {
  readonly icon = input<string | null>(null);
  readonly title = input.required<string>();
  readonly description = input<string | null>(null);
}

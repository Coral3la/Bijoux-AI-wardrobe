import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  // No border, no fill, and no padding of its own. A dashed box is the most
  // generic shape in web design and it was carrying three of the highest-stakes
  // screens in the product — the second one a new account ever sees among them.
  // Without the box there is nothing to pad: the page's own rhythm already puts
  // a region gap above this, so a component that added more would be fighting
  // DR.7 for the same space. Left-aligned, in the content column, because this
  // is a note rather than a placard. DECISIONS.md 216.
  host: {
    class: 'flex flex-col items-start gap-4 text-start',
  },
  // h2 because both callers were h2 before the rework and the document outline
  // has to survive it.
  template: `
    <h2 class="font-display text-3xl leading-tight">{{ title() }}</h2>

    @if (description() !== null) {
      <p class="max-w-prose font-prose text-lg leading-relaxed text-ink-muted">
        {{ description() }}
      </p>
    }

    <ng-content />
  `,
})
export class EmptyState {
  readonly title = input.required<string>();
  readonly description = input<string | null>(null);
}

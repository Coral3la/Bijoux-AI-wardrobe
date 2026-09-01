import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  // Still no border, no fill and no padding of its own — 216 took the box away
  // and this pass does not put anything back. What changes here is the axis and
  // the faces. **Centred**, which reverses 216 on its own metaphor: that entry
  // left-aligned this "in the content column, because this is a note rather
  // than a placard", and the premise is what did not survive contact with the
  // three call sites. An empty state renders when there is no content column —
  // it is the only object on the screen, and a note pinned to the start edge of
  // a 980px page reads as a fragment of a list that failed to load. A placard
  // is what this actually is. DECISIONS.md 216, 221.
  host: {
    class: 'flex flex-col items-center gap-4 text-center',
  },
  // h2 because both callers were h2 before the rework and the document outline
  // has to survive it.
  //
  // The faces are Atelier's now rather than DR.11a's: the title takes the
  // display serif at 300, and the description goes italic — one family answers
  // both authored roles here, so the italic is the only thing telling prose
  // from display. Both strings are ours, which is why neither takes the content
  // face 071 gives the model's words. DECISIONS.md 219, 221.
  template: `
    <h2 class="font-display text-[28px] leading-tight font-light text-balance">{{ title() }}</h2>

    @if (description() !== null) {
      <p class="max-w-[40ch] font-prose text-base leading-relaxed text-ink-muted italic">
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

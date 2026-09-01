import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { I18nService, Params, Segment } from '../../core/i18n/i18n.service';

// The component 213 specified: one whole i18n key, rendered with its content
// values in the content face and the sentence around them in whatever face the
// caller sets on the host. The key is never split — `segments()` cuts the
// template at placeholder positions, so a translation that words the sentence
// the other way round still wraps the right run.
//
// Two dictionaries rather than one plus a list of content names: with a list,
// forgetting to name a key renders a city in the authored face with no error
// and no test failure. Here a value cannot reach `params` without the author
// putting it there.
//
// Every segment is a <span>, including the authored ones. A bare interpolation
// between template lines is a text node Angular's whitespace handling may
// collapse, and "Good morning," and "Coral" arriving with an extra space
// between them is not the sentence the translator wrote. Elements only means
// every gap is a whitespace-only node, which is removed outright.
@Component({
  selector: 'app-authored-line',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @for (part of parts(); track $index) {
      <span [class.font-sans]="part.content">{{ part.text }}</span>
    }
  `,
})
export class AuthoredLine {
  private readonly i18n = inject(I18nService);

  readonly key = input.required<string>();
  readonly params = input<Params | undefined>(undefined);
  readonly content = input<Params | undefined>(undefined);

  protected readonly parts = computed<readonly Segment[]>(() =>
    this.i18n.segments(this.key(), this.params(), this.content()),
  );
}

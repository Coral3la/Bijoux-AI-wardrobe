import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type SkeletonShape = 'rect' | 'circle';

@Component({
  selector: 'app-skeleton',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    // A pulsing empty box has nothing to announce; the callers that need a wait
    // announced keep their own role="status" line beside the skeleton.
    'aria-hidden': 'true',
    '[class]': 'classes()',
  },
  template: '',
})
export class Skeleton {
  readonly shape = input<SkeletonShape>('rect');
  readonly radius = input('rounded-lg');

  // `block` is load-bearing: a custom element is inline by default, so the
  // width and height the caller sets on the host would not apply without it.
  // A circle has one possible radius, so shape wins over radius when both are
  // set rather than the two fighting.
  protected readonly classes = computed(() => {
    const corners = this.shape() === 'circle' ? 'rounded-full' : this.radius();
    return `block animate-pulse bg-surface-elevated ${corners}`;
  });
}

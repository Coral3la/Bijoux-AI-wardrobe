import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';

import { Skeleton, SkeletonShape } from './skeleton';

let fixture: ComponentFixture<Skeleton>;

async function render(
  inputs: { shape?: SkeletonShape; radius?: string } = {},
): Promise<HTMLElement> {
  fixture = TestBed.createComponent(Skeleton);
  if (inputs.shape !== undefined) {
    fixture.componentRef.setInput('shape', inputs.shape);
  }
  if (inputs.radius !== undefined) {
    fixture.componentRef.setInput('radius', inputs.radius);
  }
  await fixture.whenStable();

  return fixture.nativeElement as HTMLElement;
}

describe('Skeleton', () => {
  afterEach(() => {
    TestBed.resetTestingModule();
  });

  // `block` is asserted rather than assumed: without it the height and width a
  // caller sets on the host do not apply, and the placeholder collapses.
  it('renders as an inert block placeholder', async () => {
    const host = await render();

    expect(host.getAttribute('aria-hidden')).toBe('true');
    expect(host.classList.contains('block')).toBe(true);
    expect(host.classList.contains('animate-pulse')).toBe(true);
    expect(host.classList.contains('rounded-lg')).toBe(true);
  });

  it('takes the radius it is given', async () => {
    const host = await render({ radius: 'rounded-md' });

    expect(host.classList.contains('rounded-md')).toBe(true);
    expect(host.classList.contains('rounded-lg')).toBe(false);
  });

  it('lets a circle win over a radius', async () => {
    const host = await render({ shape: 'circle', radius: 'rounded-md' });

    expect(host.classList.contains('rounded-full')).toBe(true);
    expect(host.classList.contains('rounded-md')).toBe(false);
  });
});

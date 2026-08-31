import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';

import { Chip, ChipVariant } from './chip';

// `class="shrink-0"` is the real one from the wardrobe's chip row, which scrolls
// horizontally: if the host binding replaced it the row would wrap instead.
@Component({
  selector: 'app-chip-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip],
  template: `
    <button appChip [active]="active()" [variant]="variant()" class="shrink-0">Tops</button>
  `,
})
class ChipHost {
  readonly active = input(false);
  readonly variant = input<ChipVariant>('default');
}

let fixture: ComponentFixture<ChipHost>;

async function render(active = false, variant: ChipVariant = 'default'): Promise<HTMLElement> {
  fixture = TestBed.createComponent(ChipHost);
  fixture.componentRef.setInput('active', active);
  fixture.componentRef.setInput('variant', variant);
  await fixture.whenStable();

  const chip = (fixture.nativeElement as HTMLElement).querySelector('button');
  if (chip === null) {
    throw new Error('the host rendered no chip');
  }
  return chip;
}

describe('Chip', () => {
  afterEach(() => {
    TestBed.resetTestingModule();
  });

  it("renders as a pill around the caller's content", async () => {
    const chip = await render();

    expect(chip.textContent?.trim()).toBe('Tops');
    expect(chip.classList.contains('rounded-full')).toBe(true);
    expect(chip.classList.contains('min-h-11')).toBe(true);
  });

  // Painted and announced from one input, so both halves belong in one test:
  // either they follow `active` together or the pair has drifted. Flipped on a
  // live fixture rather than re-rendered, so it asserts the binding reacts.
  it('paints and announces its active state from the same input', async () => {
    const chip = await render(false);

    expect(chip.getAttribute('aria-pressed')).toBe('false');
    expect(chip.classList.contains('border-line-strong')).toBe(true);

    fixture.componentRef.setInput('active', true);
    await fixture.whenStable();

    expect(chip.getAttribute('aria-pressed')).toBe('true');
    expect(chip.classList.contains('bg-ink')).toBe(true);
  });

  it('keeps the classes the caller wrote beside its own', async () => {
    const chip = await render(true, 'accent');

    expect(chip.classList.contains('shrink-0')).toBe(true);
    expect(chip.classList.contains('bg-accent-wash')).toBe(true);
  });
});

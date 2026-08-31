import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';

import { Button, ButtonVariant } from './button';

// A directive has no fixture of its own, so every assertion goes through a host
// that uses it the way a screen will. `class="w-full"` is not filler: it is the
// caller-owned class the third test is about.
@Component({
  selector: 'app-button-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button],
  template: `<button appButton [variant]="variant()" class="w-full">Save</button>`,
})
class ButtonHost {
  readonly variant = input<ButtonVariant>('primary');
}

let fixture: ComponentFixture<ButtonHost>;

async function render(variant?: ButtonVariant): Promise<HTMLButtonElement> {
  fixture = TestBed.createComponent(ButtonHost);
  if (variant !== undefined) {
    fixture.componentRef.setInput('variant', variant);
  }
  await fixture.whenStable();

  const button = (fixture.nativeElement as HTMLElement).querySelector('button');
  if (button === null) {
    throw new Error('the host rendered no button');
  }
  return button;
}

describe('Button', () => {
  afterEach(() => {
    TestBed.resetTestingModule();
  });

  it("dresses the caller's own button and leaves its content alone", async () => {
    const button = await render();

    expect(button.textContent?.trim()).toBe('Save');
    expect(button.classList.contains('min-h-11')).toBe(true);
    expect(button.classList.contains('rounded-md')).toBe(true);
  });

  it('applies the variant it was given and not another', async () => {
    const button = await render('danger');

    expect(button.classList.contains('border-danger')).toBe(true);
    expect(button.classList.contains('bg-accent')).toBe(false);
  });

  // The one assertion in DR.2 that can actually fail. Every screen in DR.3-DR.6
  // adds its own layout class beside the variant, and a host [class] binding
  // that replaced rather than merged would drop all of them silently.
  it('keeps the classes the caller wrote beside its own', async () => {
    const button = await render();

    expect(button.classList.contains('w-full')).toBe(true);
    expect(button.classList.contains('bg-accent')).toBe(true);
  });
});

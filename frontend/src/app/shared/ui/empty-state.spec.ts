import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';

import { EmptyState } from './empty-state';

// The CTA is projected rather than an input, so it needs a host to be projected
// from. This is the shape the wardrobe's empty state takes at DR.3.
@Component({
  selector: 'app-empty-state-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [EmptyState],
  template: `
    <app-empty-state [title]="title">
      <button type="button">Add your first items</button>
    </app-empty-state>
  `,
})
class EmptyStateHost {
  protected readonly title = 'Your wardrobe is empty';
}

let fixture: ComponentFixture<EmptyState>;

async function render(inputs: { icon?: string; description?: string } = {}): Promise<HTMLElement> {
  fixture = TestBed.createComponent(EmptyState);
  fixture.componentRef.setInput('title', 'Your wardrobe is empty');
  if (inputs.icon !== undefined) {
    fixture.componentRef.setInput('icon', inputs.icon);
  }
  if (inputs.description !== undefined) {
    fixture.componentRef.setInput('description', inputs.description);
  }
  await fixture.whenStable();

  return fixture.nativeElement as HTMLElement;
}

describe('EmptyState', () => {
  afterEach(() => {
    TestBed.resetTestingModule();
  });

  // h2 rather than the element: both callers are h2 today and the refresh must
  // not flatten the document outline to reach one visual identity.
  it('renders its title as a second-level heading', async () => {
    const host = await render();

    expect(host.querySelector('h2')?.textContent?.trim()).toBe('Your wardrobe is empty');
  });

  it('renders the optional icon and description only when given them', async () => {
    const host = await render();

    expect(host.querySelector('svg')).toBeNull();
    expect(host.querySelector('p')).toBeNull();

    fixture.componentRef.setInput('icon', 'M4 7h16');
    fixture.componentRef.setInput('description', 'Photograph a few garments.');
    await fixture.whenStable();

    expect(host.querySelector('path')?.getAttribute('d')).toBe('M4 7h16');
    expect(host.querySelector('p')?.textContent?.trim()).toBe('Photograph a few garments.');
  });

  it('projects the caller-supplied call to action', async () => {
    const hostFixture = TestBed.createComponent(EmptyStateHost);
    await hostFixture.whenStable();

    const cta = (hostFixture.nativeElement as HTMLElement).querySelector('button');
    expect(cta?.textContent?.trim()).toBe('Add your first items');
  });
});

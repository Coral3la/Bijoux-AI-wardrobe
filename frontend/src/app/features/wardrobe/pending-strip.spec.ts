import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { PendingUpload } from '../../core/state/wardrobe.store';
import { PendingStrip } from './pending-strip';

let fixture: ComponentFixture<PendingStrip>;
let mock: HttpTestingController;

function entry(name: string, key: string, url: string): PendingUpload {
  return { key, url, name };
}

function images(): HTMLImageElement[] {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('img')];
}

function text(): string {
  return (fixture.nativeElement as HTMLElement).textContent ?? '';
}

async function render(pending: readonly PendingUpload[]): Promise<void> {
  fixture = TestBed.createComponent(PendingStrip);
  fixture.componentRef.setInput('pending', pending);
  await fixture.whenStable();
}

describe('PendingStrip', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // Two entries, never one. With a single preview on screen a per-file
  // binding and a global one are indistinguishable, which is exactly how two
  // mutations survived 108 passing tests at task 1.5. DECISIONS.md 093.
  it('renders one slot per pending file, each with its own src', async () => {
    await render([
      entry('a.jpg', 'pending-0', 'blob:stub/0'),
      entry('b.jpg', 'pending-1', 'blob:stub/1'),
    ]);

    expect(images().map((image) => image.getAttribute('src'))).toEqual([
      'blob:stub/0',
      'blob:stub/1',
    ]);
  });

  it('names each slot after its own file, not after the first', async () => {
    await render([
      entry('a.jpg', 'pending-0', 'blob:stub/0'),
      entry('b.jpg', 'pending-1', 'blob:stub/1'),
    ]);

    expect(images().map((image) => image.getAttribute('alt'))).toEqual([
      'Uploading a.jpg',
      'Uploading b.jpg',
    ]);
  });

  it('does not say "1 photos"', async () => {
    await render([entry('a.jpg', 'pending-0', 'blob:stub/0')]);

    expect(text()).toContain('Uploading 1 photo…');
  });

  it('counts the files when there is more than one', async () => {
    await render([
      entry('a.jpg', 'pending-0', 'blob:stub/0'),
      entry('b.jpg', 'pending-1', 'blob:stub/1'),
    ]);

    expect(text()).toContain('Uploading 2 photos…');
  });

  // Self-guarded rather than gated by its caller, so it cannot be placed on a
  // page and announce "Uploading 0 photos" when nothing is in flight.
  it('renders nothing at all when there is nothing pending', async () => {
    await render([]);

    expect(images()).toHaveLength(0);
    expect(text().trim()).toBe('');
  });
});

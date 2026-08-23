import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { ItemCard } from './item-card';

let fixture: ComponentFixture<ItemCard>;
let mock: HttpTestingController;

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 'item-1',
    short_id: 'AB12CD',
    status: 'ready',
    image_public_id: 'bijoux/users/1/abc',
    image_url: 'https://res.cloudinary.com/demo/image/upload/w_300/abc.jpg',
    category: 'top',
    subcategory: 'shirt',
    fit: 'relaxed',
    length: 'long_sleeve',
    rise: null,
    color_primary: 'white',
    color_secondary: null,
    pattern: 'solid',
    material: 'cotton',
    formality: 3,
    warmth: 2,
    layer: 'base',
    water_resistant: false,
    display_name: 'white oversized shirt',
    attributes: {},
    ai_confidence: 0.9,
    user_edited: false,
    error_message: null,
    is_archived: false,
    created_at: '2026-08-19T09:00:00Z',
    updated_at: '2026-08-19T09:00:00Z',
    ...overrides,
  };
}

function text(): string {
  return (fixture.nativeElement as HTMLElement).textContent ?? '';
}

function image(): HTMLImageElement {
  return (fixture.nativeElement as HTMLElement).querySelector('img')!;
}

function retryButton(): HTMLButtonElement | null {
  return (fixture.nativeElement as HTMLElement).querySelector('button');
}

async function render(
  value: Item,
  retrying = false,
  errorKey: string | null = null,
  stoppedWaiting = false,
): Promise<void> {
  fixture = TestBed.createComponent(ItemCard);
  fixture.componentRef.setInput('item', value);
  fixture.componentRef.setInput('retrying', retrying);
  fixture.componentRef.setInput('errorKey', errorKey);
  fixture.componentRef.setInput('stoppedWaiting', stoppedWaiting);
  await fixture.whenStable();
}

describe('ItemCard', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);

    // The real string file, so a key missing from it fails here rather than
    // rendering as itself on screen.
    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  it('renders the thumbnail the server built', async () => {
    await render(item());

    expect(image().getAttribute('src')).toBe(item().image_url);
  });

  it('uses the display name as alt text', async () => {
    await render(item());

    expect(image().getAttribute('alt')).toBe('white oversized shirt');
  });

  it('falls back to a described alt when the item has no name yet', async () => {
    await render(item({ status: 'processing', display_name: null }));

    expect(image().getAttribute('alt')).toBe('Wardrobe item, not tagged yet');
  });

  it('keeps the photograph and says it is tagging while processing', async () => {
    await render(item({ status: 'processing', display_name: null }));

    expect(image()).not.toBeNull();
    expect(text()).toContain('Tagging…');
    expect(retryButton()).toBeNull();
  });

  it('offers a retry on a failed item', async () => {
    await render(item({ status: 'failed', display_name: null }));

    expect(text()).toContain('Tagging failed');
    expect(retryButton()).not.toBeNull();
  });

  // The one thing about this tile that is easy to get wrong: a retag that
  // fails leaves the previous attempt's tags in place, so the warning state
  // comes from `status` and never from "the tags are null". DECISIONS.md 089.
  it('shows the failed state on an item that still carries a full set of tags', async () => {
    await render(item({ status: 'failed' }));

    expect(text()).toContain('Tagging failed');
    expect(retryButton()).not.toBeNull();
  });

  it('names the garment in the retry button accessible label', async () => {
    await render(item({ status: 'failed' }));

    expect(retryButton()!.getAttribute('aria-label')).toBe(
      'Try tagging white oversized shirt again',
    );
  });

  it('emits once when the retry is pressed', async () => {
    await render(item({ status: 'failed' }));
    let emitted = 0;
    fixture.componentInstance.retry.subscribe(() => (emitted += 1));

    retryButton()!.click();
    await fixture.whenStable();

    expect(emitted).toBe(1);
  });

  it('disables the retry while one is in flight', async () => {
    await render(item({ status: 'failed' }), true);

    expect(retryButton()!.disabled).toBe(true);
    expect(text()).toContain('Trying…');
  });

  it('renders the retag error beside the item it belongs to', async () => {
    await render(item({ status: 'failed' }), false, 'wardrobe.error.retagEdited');

    expect(text()).toContain('would overwrite your changes');
  });
  // --- what the loop giving up looks like, task 1.7 ------------------------

  it('offers a retry on an item the loop stopped waiting for', async () => {
    await render(item({ status: 'processing', display_name: null }), false, null, true);

    expect(text()).toContain('We stopped waiting');
    expect(retryButton()).not.toBeNull();
  });

  // C7. The server still calls this row processing and may yet finish it, so
  // the tile may not borrow the failure's words — and it may not borrow the
  // danger token either, which 057 reserves for something being wrong.
  it('does not call a stopped wait a tagging failure', async () => {
    await render(item({ status: 'processing', display_name: null }), false, null, true);

    expect(text()).not.toContain('Tagging failed');
    expect(text()).not.toContain('Tagging…');
    expect((fixture.nativeElement as HTMLElement).querySelector('.text-danger')).toBeNull();
  });

  // The flag is read with the status and never alone: it outlives its row until
  // the next load(), so on an item that has since come back `ready` it is stale
  // and must draw nothing at all.
  it('ignores a stale stopped-waiting flag on a row that has since finished', async () => {
    await render(item({ status: 'ready' }), false, null, true);

    expect(text()).not.toContain('We stopped waiting');
    expect(retryButton()).toBeNull();
  });

  it('shows the failure rather than the stopped wait when the row really failed', async () => {
    await render(item({ status: 'failed' }), false, null, true);

    expect(text()).toContain('Tagging failed');
    expect(text()).not.toContain('We stopped waiting');
  });
});

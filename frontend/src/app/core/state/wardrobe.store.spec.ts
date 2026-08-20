import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { Item } from '../../shared/models/item.model';
import { WARDROBE_PAGE_SIZE, WardrobeStore } from './wardrobe.store';

let store: WardrobeStore;
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

function listRequest() {
  return mock.expectOne((candidate) => candidate.method === 'GET');
}

function retagRequest(id: string) {
  return mock.expectOne(`${environment.apiUrl}/items/${id}/retag`);
}

describe('WardrobeStore', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(WardrobeStore);
    mock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // 05-FRONTEND-SPEC.md requires an explicit limit because filters are
  // client-side over the loaded collection and the parameter defaults to 100.
  it('asks for a full page rather than taking the default limit', () => {
    store.load();

    const request = listRequest();
    expect(request.request.params.get('limit')).toBe(String(WARDROBE_PAGE_SIZE));
    request.flush({ items: [], total: 0 });
  });

  it('holds the rows and the server total separately', () => {
    store.load();
    listRequest().flush({ items: [item()], total: 138 });

    expect(store.items()).toHaveLength(1);
    expect(store.total()).toBe(138);
  });

  it('is loading until the response arrives', () => {
    store.load();
    expect(store.isLoading()).toBe(true);

    listRequest().flush({ items: [], total: 0 });
    expect(store.isLoading()).toBe(false);
  });

  it('is empty until rows arrive', () => {
    store.load();
    expect(store.isEmpty()).toBe(true);

    listRequest().flush({ items: [item()], total: 1 });
    expect(store.isEmpty()).toBe(false);
  });

  it('turns a failed list into a message key rather than an exception', () => {
    store.load();
    listRequest().flush('', { status: 500, statusText: 'Server Error' });

    expect(store.loadError()).toBe('wardrobe.error.load');
    expect(store.isLoading()).toBe(false);
  });

  it('clears a previous load error when asked to load again', () => {
    store.load();
    listRequest().flush('', { status: 500, statusText: 'Server Error' });

    store.load();
    expect(store.loadError()).toBeNull();
    listRequest().flush({ items: [], total: 0 });
  });

  it('counts only the processing rows', () => {
    store.load();
    listRequest().flush({
      items: [
        item({ id: 'a', status: 'ready' }),
        item({ id: 'b', status: 'processing' }),
        item({ id: 'c', status: 'failed' }),
      ],
      total: 3,
    });

    expect(store.processing().map((row) => row.id)).toEqual(['b']);
  });

  it('replaces the whole row a retag returns', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'a', status: 'failed' })], total: 1 });

    store.retag('a');
    retagRequest('a').flush(item({ id: 'a', status: 'processing' }));

    expect(store.items()[0].status).toBe('processing');
  });

  it('marks only the item being retagged', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'a' }), item({ id: 'b' })], total: 2 });

    store.retag('a');
    expect(store.retrying().has('a')).toBe(true);
    expect(store.retrying().has('b')).toBe(false);

    retagRequest('a').flush(item({ id: 'a' }));
    expect(store.retrying().has('a')).toBe(false);
  });

  it('sends one retag while one is already in flight', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'a' })], total: 1 });

    store.retag('a');
    store.retag('a');

    retagRequest('a').flush(item({ id: 'a' }));
  });

  // item_edited is reachable from a grid tile: edit an item, force a retag,
  // have that retag fail, and the row is `failed` and `user_edited` at once.
  it('names the hand-edited conflict by its documented code', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'a', status: 'failed' })], total: 1 });

    store.retag('a');
    retagRequest('a').flush(
      { detail: 'This item has been edited by hand.', code: 'item_edited' },
      { status: 409, statusText: 'Conflict' },
    );

    expect(store.retagErrors().get('a')).toBe('wardrobe.error.retagEdited');
  });

  it('falls back to the general message when no code arrives', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'a', status: 'failed' })], total: 1 });

    store.retag('a');
    retagRequest('a').flush('', { status: 500, statusText: 'Server Error' });

    expect(store.retagErrors().get('a')).toBe('wardrobe.error.retag');
  });

  it('drops a stale retag error when the same item is retried', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'a', status: 'failed' })], total: 1 });

    store.retag('a');
    retagRequest('a').flush('', { status: 500, statusText: 'Server Error' });

    store.retag('a');
    expect(store.retagErrors().has('a')).toBe(false);
    retagRequest('a').flush(item({ id: 'a', status: 'processing' }));
  });
});

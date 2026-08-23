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

function uploadRequest() {
  return mock.expectOne(`${environment.apiUrl}/items/upload`);
}

function file(name: string): File {
  return new File([new Uint8Array(8)], name, { type: 'image/jpeg' });
}

// jsdom implements neither half of the object-URL API — measured at task 1.6,
// URL.createObjectURL and URL.revokeObjectURL are both `undefined` — so the
// store's preview path cannot run at all without these two. Read the names
// literally: they record that the store *asked for* and *released* a URL.
// Nothing here decodes an image, renders one, or proves a user saw anything.
// AUDITS.md O-14 carries what that leaves unverified.
let granted: string[] = [];
let released: string[] = [];

function stubObjectUrls(): void {
  granted = [];
  released = [];
  let seq = 0;
  URL.createObjectURL = () => {
    const url = `blob:stub/${seq++}`;
    granted.push(url);
    return url;
  };
  URL.revokeObjectURL = (url: string) => {
    released.push(url);
  };
}

describe('WardrobeStore', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(WardrobeStore);
    mock = TestBed.inject(HttpTestingController);
    stubObjectUrls();
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

  // 093's finding, applied before it can recur: every one of these uses two
  // files, because with a single file a per-file collection and a global one
  // are indistinguishable and six passing tests proved nothing at 1.5.
  it('holds one pending entry per selected file, each with its own key and url', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);

    const pending = store.pending();
    expect(pending.map((entry) => entry.name)).toEqual(['a.jpg', 'b.jpg']);
    expect(new Set(pending.map((entry) => entry.key)).size).toBe(2);
    expect(new Set(pending.map((entry) => entry.url)).size).toBe(2);
    uploadRequest().flush({ items: [] });
  });

  it('asks for one object url per selected file', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);

    expect(granted).toHaveLength(2);
    uploadRequest().flush({ items: [] });
  });

  it('releases every object url it asked for once the rows arrive', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush({ items: [] });

    expect(released).toEqual(granted);
  });

  it('marks itself uploading while the request is in flight and clear afterwards', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    expect(store.isUploading()).toBe(true);

    uploadRequest().flush({ items: [] });
    expect(store.isUploading()).toBe(false);
  });

  it('stops being uploading when the request fails', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush(
      { detail: 'no', code: 'upload_failed' },
      { status: 502, statusText: 'Bad Gateway' },
    );

    expect(store.isUploading()).toBe(false);
  });

  it('sends one upload while one is already in flight', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    store.upload([file('c.jpg')]);

    uploadRequest().flush({ items: [] });
    mock.verify();
  });

  // GET /items orders created_at DESC, so a fresh upload belongs at the top.
  it('puts the returned rows in front of the ones already loaded', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'old' })], total: 1 });

    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush({ items: [item({ id: 'new-1' }), item({ id: 'new-2' })] });

    expect(store.items().map((row) => row.id)).toEqual(['new-1', 'new-2', 'old']);
  });

  // The 202 carries no `total`, so nothing moves the header's count but this.
  it('moves the total by the number of rows the upload returned', () => {
    store.load();
    listRequest().flush({ items: [item({ id: 'old' })], total: 1 });

    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush({ items: [item({ id: 'new-1' }), item({ id: 'new-2' })] });

    expect(store.total()).toBe(3);
  });

  it('drops the previews when the batch is rejected', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush(
      { detail: 'a.jpg: nope', code: 'unsupported_file_type' },
      { status: 415, statusText: 'Unsupported Media Type' },
    );

    expect(store.pending()).toEqual([]);
    expect(released).toEqual(granted);
  });

  it.each([
    ['unsupported_file_type', 415, 'wardrobe.upload.error.unsupportedType'],
    ['file_too_large', 413, 'wardrobe.upload.error.fileTooLarge'],
    ['upload_failed', 502, 'wardrobe.upload.error.uploadFailed'],
    ['validation_error', 422, 'wardrobe.upload.error.validation'],
  ])('reads the %s code rather than the status', (code, status, key) => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush({ detail: 'no', code }, { status, statusText: 'Error' });

    expect(store.uploadError()).toBe(key);
  });

  // 092's stated degradation path: a right status with a missing or misspelled
  // code falls to the general message rather than guessing from the status.
  it('falls back to the general message when the body carries no code', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush({ detail: 'no' }, { status: 415, statusText: 'Unsupported Media Type' });

    expect(store.uploadError()).toBe('wardrobe.upload.error.general');
  });

  it('clears an upload error when it is dismissed', () => {
    store.upload([file('a.jpg'), file('b.jpg')]);
    uploadRequest().flush(
      { detail: 'no', code: 'upload_failed' },
      { status: 502, statusText: 'Bad Gateway' },
    );

    store.dismissUploadError();
    expect(store.uploadError()).toBeNull();
  });
});

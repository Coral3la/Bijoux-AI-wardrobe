import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { environment } from '../../../environments/environment';
import { Item } from '../../shared/models/item.model';
import {
  POLL_DEADLINE_MS,
  POLL_INTERVAL_MS,
  WARDROBE_PAGE_SIZE,
  WardrobeStore,
} from './wardrobe.store';

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

// The two requests of DECISIONS.md 102, told apart by the one parameter that
// distinguishes them. listRequest() above matches either, so the polling tests
// use these instead — a test that cannot tell the poll from the reload cannot
// assert that the reload is what puts a tag on a tile.
function pollRequest() {
  return mock.expectOne(
    (candidate) => candidate.method === 'GET' && candidate.params.get('status') === 'processing',
  );
}

function reloadRequest() {
  return mock.expectOne(
    (candidate) => candidate.method === 'GET' && !candidate.params.has('status'),
  );
}

function expectNoRequest(): void {
  mock.expectNone((candidate) => candidate.method === 'GET');
}

// The store spec can turn fake timers on directly, where wardrobe.page.spec.ts
// has to switch mid-test: nothing in this file awaits whenStable(), which is
// the call that never resolves under a frozen clock. See switchToFakeTimers()
// there for the measurement and the nineteen tests it protects.
//
// TestBed.tick() is what runs the effect. Without it the effect never fires,
// no run is created, and every assertion below passes against a store that
// polls nothing — which is why the loading helper ends with one.
function loaded(items: readonly Item[], total = items.length): void {
  store.load();
  listRequest().flush({ items, total });
  TestBed.tick();
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
    // resetTestingModule tears down the injector and with it the effect, but
    // not a setTimeout this store already scheduled. Left alone, a run started
    // by any test that flushed a `processing` row fires two seconds later
    // against a destroyed TestBed.
    store.stopPolling();
    vi.useRealTimers();
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
  // --- polling, task 1.7 ---------------------------------------------------

  it('waits for the processing rows it has not given up on', () => {
    loaded([
      item({ id: 'a', status: 'ready' }),
      item({ id: 'b', status: 'processing' }),
      item({ id: 'c', status: 'failed' }),
    ]);

    expect(store.awaitingTags().map((row) => row.id)).toEqual(['b']);
  });

  it('asks for the processing filter and a full page', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);

    const poll = pollRequest();
    expect(poll.request.params.get('limit')).toBe(String(WARDROBE_PAGE_SIZE));
    poll.flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
  });

  // 2000 is transcribed by hand from 01-ARCHITECTURE.md and 05-FRONTEND-SPEC.md
  // rather than read from POLL_INTERVAL_MS. At 1.6 every expectation about
  // MAX_UPLOAD_BYTES was written in terms of the constant, so changing the
  // constant moved the expectations with it and all 155 tests stayed green
  // (DECISIONS.md 101). A timing constant is the same trap in a new file.
  it('waits the documented two seconds before the first poll', () => {
    expect(POLL_INTERVAL_MS).toBe(2000);

    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(1999);
    expectNoRequest();

    vi.advanceTimersByTime(1);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
  });

  // The loop is re-armed after a response settles rather than run from a fixed
  // interval, so "one poll in flight" is a property and not a hope about how
  // fast the server answers. DECISIONS.md 104.
  it('sends no second poll while the first is still in flight', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    const poll = pollRequest();

    vi.advanceTimersByTime(POLL_INTERVAL_MS * 5);
    expect(mock.match((candidate) => candidate.method === 'GET')).toHaveLength(0);

    poll.flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
  });

  // The whole of DECISIONS.md 102 in one test: a body filtered to
  // status=processing can never carry a finished row, so without the second
  // request a tile stays dimmed and untagged for ever.
  it('reloads the whole wardrobe when an item leaves the processing set', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing', display_name: null })]);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    pollRequest().flush({ items: [], total: 0 });

    reloadRequest().flush({
      items: [item({ id: 'a', status: 'ready', display_name: 'black wool coat' })],
      total: 1,
    });

    expect(store.items()[0].display_name).toBe('black wool coat');
  });

  it('does not reload while the same items are still processing', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });

    expectNoRequest();
  });

  // Compared as ids rather than as a count. A second batch landing while the
  // first is finishing leaves the count unchanged with the membership entirely
  // different, and a count comparison would never fire the reload.
  it('reloads on a change of membership that leaves the count alone', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    pollRequest().flush({ items: [item({ id: 'b', status: 'processing' })], total: 1 });

    reloadRequest().flush({
      items: [item({ id: 'b', status: 'processing' }), item({ id: 'a', status: 'ready' })],
      total: 2,
    });

    expect(store.items().map((row) => row.status)).toEqual(['processing', 'ready']);
  });

  // 094 puts the server's total in the header because it counts the filter
  // rather than the page. A poll's total counts the filter too — and the
  // filter is `processing`, so writing it would drop the header to the size of
  // the batch. DECISIONS.md 106.
  it('takes the header total from the reload and never from the poll', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })], 138);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });

    expect(store.total()).toBe(138);
  });

  // Q5. A cold start on Render answers slowly or not at all, and a red banner
  // over a grid that is otherwise fine is the worse of the two answers. The
  // deadline is what bounds a poll that never succeeds. DECISIONS.md 106.
  it('keeps polling through a failed poll and reports nothing', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    pollRequest().flush('', { status: 503, statusText: 'Service Unavailable' });

    expect(store.loadError()).toBeNull();

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
  });

  it('stops polling once nothing is processing any more', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    pollRequest().flush({ items: [], total: 0 });
    reloadRequest().flush({ items: [item({ id: 'a', status: 'ready' })], total: 1 });
    TestBed.tick();

    vi.advanceTimersByTime(POLL_INTERVAL_MS * 10);
    expectNoRequest();
  });

  it('stops the loop when it is told to, which is what the page does on destroy', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    store.stopPolling();

    vi.advanceTimersByTime(POLL_INTERVAL_MS * 10);
    expectNoRequest();
  });

  // 180_000 and 2000 are both transcribed by hand, for the reason above. The
  // two ends are asserted together because "it gave up eventually" would also
  // pass on a deadline of thirty seconds, and "it had not given up at 178s"
  // would also pass on a loop that never gives up at all.
  it('gives up at the three-minute deadline and not at the poll before it', () => {
    expect(POLL_DEADLINE_MS).toBe(180_000);

    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    for (let elapsed = 2000; elapsed <= 178_000; elapsed += 2000) {
      vi.advanceTimersByTime(2000);
      pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
    }
    expect(store.stoppedWaiting().has('a')).toBe(false);

    vi.advanceTimersByTime(2000);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });

    expect(store.stoppedWaiting().has('a')).toBe(true);
  });

  it('does not start the loop again on the items it gave up on', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    for (let elapsed = 2000; elapsed <= 180_000; elapsed += 2000) {
      vi.advanceTimersByTime(2000);
      pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
    }
    TestBed.tick();

    vi.advanceTimersByTime(180_000);
    expectNoRequest();
    expect(store.awaitingTags()).toHaveLength(0);
    expect(store.processing()).toHaveLength(1);
  });

  // Mutation M8 — keying the effect on processing() rather than awaitingTags()
  // — survived the whole suite until this test existed, and the reason is worth
  // keeping. The claim it was supposed to fail was that giving up would restart
  // the loop it had just stopped; that mechanism does not exist, because an
  // effect reading only processing() no longer depends on the signal that
  // giving up writes, so it never re-runs at all. What does happen is quieter
  // and reachable: the next batch restarts the loop, and when *that* batch
  // finishes the loop keeps polling for the item whose tile already says we
  // stopped waiting for it. The screen and the loop disagree, for three
  // minutes, with nothing on screen to say so.
  it('does not resume waiting for an abandoned item when a later batch finishes', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    for (let elapsed = 2000; elapsed <= 180_000; elapsed += 2000) {
      vi.advanceTimersByTime(2000);
      pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
    }
    expect(store.stoppedWaiting().has('a')).toBe(true);

    store.upload([file('b.jpg')]);
    uploadRequest().flush({ items: [item({ id: 'b', status: 'processing' })] });
    TestBed.tick();

    vi.advanceTimersByTime(2000);
    pollRequest().flush({
      items: [item({ id: 'b', status: 'processing' }), item({ id: 'a', status: 'processing' })],
      total: 2,
    });

    vi.advanceTimersByTime(2000);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
    reloadRequest().flush({
      items: [item({ id: 'b', status: 'ready' }), item({ id: 'a', status: 'processing' })],
      total: 2,
    });
    TestBed.tick();

    vi.advanceTimersByTime(2000 * 10);
    expectNoRequest();
  });

  // 098 keeps the sheet open after a camera capture so the next garment can be
  // shot immediately, which makes back-to-back batches the designed path
  // rather than an unlucky one. Under a per-run deadline the second batch
  // would inherit the remainder of the first one's and be abandoned while it
  // was tagging perfectly well. DECISIONS.md 108.
  it('gives a batch that arrives mid-run its own three minutes', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    vi.advanceTimersByTime(2000);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });

    store.upload([file('b.jpg')]);
    uploadRequest().flush({ items: [item({ id: 'b', status: 'processing' })] });
    TestBed.tick();

    const stillTagging = [
      item({ id: 'b', status: 'processing' }),
      item({ id: 'a', status: 'processing' }),
    ];
    for (let elapsed = 4000; elapsed <= 180_000; elapsed += 2000) {
      vi.advanceTimersByTime(2000);
      pollRequest().flush({ items: stillTagging, total: 2 });
    }

    expect(store.stoppedWaiting().size).toBe(0);
  });

  // Without the clear the retry on an abandoned tile does nothing visible: the
  // 202 puts the row back to `processing` and awaitingTags still excludes it,
  // so no run ever starts.
  it('waits for an abandoned item again once its retag succeeds', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    for (let elapsed = 2000; elapsed <= 180_000; elapsed += 2000) {
      vi.advanceTimersByTime(2000);
      pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
    }
    expect(store.stoppedWaiting().has('a')).toBe(true);

    store.retag('a');
    retagRequest('a').flush(item({ id: 'a', status: 'processing' }));
    TestBed.tick();

    expect(store.stoppedWaiting().has('a')).toBe(false);
    vi.advanceTimersByTime(2000);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
  });

  // load() is an explicit fresh start — the page arriving, or the Try again
  // button on a failed load — so anything the last visit abandoned is waited
  // for again. The poll's own reload deliberately does not do this.
  it('waits again for everything after a fresh load', () => {
    vi.useFakeTimers();
    loaded([item({ id: 'a', status: 'processing' })]);

    for (let elapsed = 2000; elapsed <= 180_000; elapsed += 2000) {
      vi.advanceTimersByTime(2000);
      pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
    }
    expect(store.stoppedWaiting().has('a')).toBe(true);

    loaded([item({ id: 'a', status: 'processing' })]);

    expect(store.stoppedWaiting().size).toBe(0);
    vi.advanceTimersByTime(2000);
    pollRequest().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
  });
});

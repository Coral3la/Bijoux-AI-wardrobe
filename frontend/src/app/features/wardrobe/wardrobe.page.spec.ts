import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { WardrobePage } from './wardrobe.page';

let fixture: ComponentFixture<WardrobePage>;
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

function tiles(): HTMLElement[] {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('app-item-card')];
}

function tileText(index: number): string {
  return tiles()[index].textContent ?? '';
}

function retryButtons(): HTMLButtonElement[] {
  return [
    ...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
  ].filter((candidate) => candidate.getAttribute('aria-label')?.startsWith('Try tagging'));
}

function buttonWith(fragment: string): HTMLButtonElement {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find((candidate) =>
    candidate.textContent?.includes(fragment),
  )!;
}

function listRequest() {
  return mock.expectOne((candidate) => candidate.url === `${environment.apiUrl}/items`);
}

function uploadRequest() {
  return mock.expectOne(`${environment.apiUrl}/items/upload`);
}

function sheet(): HTMLElement | null {
  return (fixture.nativeElement as HTMLElement).querySelector('app-upload-sheet');
}

function strip(): HTMLElement | null {
  return (fixture.nativeElement as HTMLElement).querySelector('app-pending-strip section');
}

function fab(): HTMLButtonElement {
  return buttonWith('Add items');
}

// Fake timers and `await fixture.whenStable()` cannot both be true at once, and
// this file has nineteen tests built on the second one. Measured at task 1.7
// against vitest 4.1.10: with vi.useFakeTimers() in this file's beforeEach a
// bare `await fixture.whenStable()` is still pending after 250ms of real time,
// every one of those nineteen dies on the 5s test timeout, and the suite goes
// from 2.1s to 96.4s. Angular's zoneless scheduler needs a task to run, and a
// frozen clock never gives it one.
//
// So the switch happens *after* the render, never around it: real timers to get
// a component on screen, fake timers to drive the loop, TestBed.tick() instead
// of whenStable() from that point on. The alternative measured was
// vi.useFakeTimers({ shouldAdvanceTime: true }), which keeps all 156 tests
// green — and does it by advancing the mock clock 1:1 with real time, which is
// not a fake clock in the way a deadline test needs. 06-TESTING-STRATEGY.md
// carries the full probe.
//
// A run started under real timers keeps its real timer, so nothing may be
// `processing` at the moment this is called. The tests below render a `failed`
// tile and press its retry, which is how a run gets started on the far side.
function switchToFakeTimers(): void {
  vi.useFakeTimers();
}

// See wardrobe.store.spec.ts: jsdom implements neither half of the object-URL
// API, so the upload path cannot run without these. They record that a URL was
// asked for, nothing more.
function stubObjectUrls(): void {
  let seq = 0;
  URL.createObjectURL = () => `blob:stub/${seq++}`;
  URL.revokeObjectURL = () => undefined;
}

function file(name: string): File {
  return new File([new Uint8Array(8)], name, { type: 'image/jpeg' });
}

// Drives the sheet's gallery input, which is the second of its two file
// inputs. Same defineProperty stand-in for a FileList as upload-sheet.spec.ts.
async function pickFromGallery(files: File[]): Promise<void> {
  const inputs = [
    ...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLInputElement>(
      'input[type=file]',
    ),
  ];
  Object.defineProperty(inputs[1], 'files', { value: files, configurable: true });
  inputs[1].dispatchEvent(new Event('change'));
  await fixture.whenStable();
}

// detectChanges rather than whenStable, and only here: observing the loading
// state means observing it while a request is deliberately unresolved, and
// whenStable() waits on exactly that request through PendingTasks.
function create(): void {
  fixture = TestBed.createComponent(WardrobePage);
  fixture.detectChanges();
}

async function render(items: readonly Item[], total = items.length): Promise<void> {
  create();
  listRequest().flush({ items, total });
  await fixture.whenStable();
}

describe('WardrobePage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'login', children: [] }]),
      ],
    });
    mock = TestBed.inject(HttpTestingController);
    stubObjectUrls();

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  // The reset runs even when verify() throws. This page issues a request on
  // construction, so a test that fails before flushing leaves one open, and
  // without the finally the failed verify() skips the reset and every later
  // test in the file fails on an already-instantiated TestBed instead — six
  // cascading failures hiding one real one.
  afterEach(() => {
    vi.useRealTimers();
    try {
      mock.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });

  it('loads the wardrobe on arrival with an explicit limit', async () => {
    create();

    const request = listRequest();
    expect(request.request.params.get('limit')).toBe('200');
    request.flush({ items: [], total: 0 });
    await fixture.whenStable();
  });

  it('renders one tile per item', async () => {
    await render([item({ id: 'a' }), item({ id: 'b' }), item({ id: 'c' })]);

    expect(tiles()).toHaveLength(3);
  });

  // The count comes from the server's `total`, not from the loaded rows: above
  // 200 items the grid is a page and the header is the wardrobe.
  it('states the server total rather than the number of tiles', async () => {
    await render([item({ id: 'a' }), item({ id: 'b' })], 138);

    expect(text()).toContain('138 items');
  });

  it('does not say "1 items"', async () => {
    await render([item()], 1);

    expect(text()).toContain('1 item');
    expect(text()).not.toContain('1 items');
  });

  it('offers the empty state and its call to action when nothing is stored', async () => {
    await render([], 0);

    expect(text()).toContain('Your wardrobe is empty');
    expect(buttonWith('Add your first items')).toBeDefined();
    expect(tiles()).toHaveLength(0);
  });

  it('does not show the empty state while the first load is in flight', async () => {
    create();

    expect(text()).not.toContain('Your wardrobe is empty');
    expect(text()).toContain('Loading your wardrobe');
    listRequest().flush({ items: [], total: 0 });
    await fixture.whenStable();
  });

  it('explains a failed load and offers a way to repeat it', async () => {
    create();
    listRequest().flush('', { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain("We couldn't load your wardrobe.");

    buttonWith('Try again').click();
    await fixture.whenStable();
    listRequest().flush({ items: [item()], total: 1 });
    await fixture.whenStable();

    expect(tiles()).toHaveLength(1);
  });

  // The screen refreshes itself from task 1.7, so the line stops naming an
  // action the user has to take. The second half is asserted because the
  // apology is the kind of string that survives a feature by being true when
  // it was written and nobody re-reading it afterwards.
  it('says what is tagging without asking the user to reload', async () => {
    await render([
      item({ id: 'a', status: 'processing' }),
      item({ id: 'b', status: 'processing' }),
    ]);

    expect(text()).toContain('Tagging 2 items, one after another');
    expect(text()).not.toContain('Reload');
  });

  it('says nothing about tagging when every item is ready', async () => {
    await render([item()]);

    expect(text()).not.toContain('Tagging');
  });

  it('retags the item whose tile asked for it', async () => {
    await render([item({ id: 'a', status: 'failed' }), item({ id: 'b', status: 'failed' })]);

    retryButtons()[1].click();
    await fixture.whenStable();

    mock
      .expectOne(`${environment.apiUrl}/items/b/retag`)
      .flush(item({ id: 'b', status: 'processing' }));
    await fixture.whenStable();

    expect(text()).toContain('Tagging 1 item');
  });

  // Both of the next two exist because the store-level versions of them do not
  // defend the binding: with the spinner bound to "any retag in flight" and the
  // message bound to "the first error in the map", every other test in this
  // file still passed. Measured, not assumed — mutations M11 and M12.
  it('spins only the tile whose retry was pressed', async () => {
    await render([item({ id: 'a', status: 'failed' }), item({ id: 'b', status: 'failed' })]);

    retryButtons()[1].click();
    await fixture.whenStable();

    expect(tileText(1)).toContain('Trying…');
    expect(tileText(0)).not.toContain('Trying…');

    mock.expectOne(`${environment.apiUrl}/items/b/retag`).flush(item({ id: 'b' }));
    await fixture.whenStable();
  });

  it('shows the hand-edited conflict on the tile that raised it and on no other', async () => {
    await render([item({ id: 'a', status: 'failed' }), item({ id: 'b', status: 'failed' })]);

    retryButtons()[1].click();
    await fixture.whenStable();
    mock
      .expectOne(`${environment.apiUrl}/items/b/retag`)
      .flush({ detail: 'edited', code: 'item_edited' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    expect(tileText(1)).toContain('would overwrite your changes');
    expect(tileText(0)).not.toContain('would overwrite your changes');
  });

  it('opens the sheet from the empty state call to action', async () => {
    await render([]);
    expect(sheet()).toBeNull();

    buttonWith('Add your first items').click();
    await fixture.whenStable();

    expect(sheet()).not.toBeNull();
  });

  // The only entry point once the wardrobe has anything in it: the empty
  // state's CTA is inside a branch that stops rendering after the first
  // upload, so without this the sheet is reachable once per account.
  it('opens the sheet from the floating button on a wardrobe that has items', async () => {
    await render([item()]);

    fab().click();
    await fixture.whenStable();

    expect(sheet()).not.toBeNull();
  });

  it('closes the sheet when the sheet asks to be closed', async () => {
    await render([item()]);
    fab().click();
    await fixture.whenStable();

    buttonWith('Done').click();
    await fixture.whenStable();

    expect(sheet()).toBeNull();
  });

  // The load-bearing placement. The grid lives in the final @else and
  // isEmpty() is still true until the 202 lands, so a strip rendered from
  // inside that branch would be absent for the whole of a first upload —
  // exactly the upload it exists for.
  it('shows the pending strip while the wardrobe is still empty', async () => {
    await render([]);
    fab().click();
    await fixture.whenStable();
    await pickFromGallery([file('a.jpg'), file('b.jpg')]);

    expect(strip()).not.toBeNull();

    uploadRequest().flush({ items: [] });
  });

  // The other half of the same condition: "Your wardrobe is empty" must not
  // sit above two photographs that are on their way into it.
  it('hides the empty state while previews are pending', async () => {
    await render([]);
    fab().click();
    await fixture.whenStable();
    await pickFromGallery([file('a.jpg'), file('b.jpg')]);

    expect(text()).not.toContain('Your wardrobe is empty');

    uploadRequest().flush({ items: [] });
  });

  it('puts the uploaded rows into the grid and moves the count', async () => {
    await render([item({ id: 'old' })], 1);
    fab().click();
    await fixture.whenStable();
    await pickFromGallery([file('a.jpg'), file('b.jpg')]);

    uploadRequest().flush({ items: [item({ id: 'new-1' }), item({ id: 'new-2' })] });
    await fixture.whenStable();

    expect(tiles()).toHaveLength(3);
    expect(text()).toContain('3 items');
    expect(strip()).toBeNull();
  });

  it('hides the floating button while the sheet is open', async () => {
    await render([item()]);
    fab().click();
    await fixture.whenStable();

    expect(buttonWith('Add items')).toBeUndefined();
  });
  // --- polling, task 1.7 ---------------------------------------------------

  // A failed tile with its retry pressed is how these tests get a `processing`
  // row without rendering one: see switchToFakeTimers() above for why a run
  // must not already be armed when the clock freezes.
  function startTagging(): void {
    retryButtons()[0].click();
    mock
      .expectOne(`${environment.apiUrl}/items/a/retag`)
      .flush(item({ id: 'a', status: 'processing', display_name: null }));
    TestBed.tick();
  }

  function poll() {
    return mock.expectOne(
      (candidate) => candidate.method === 'GET' && candidate.params.get('status') === 'processing',
    );
  }

  // The reload is not load(), and this is the test that says why: load() sets
  // isLoading, and this page swaps the whole grid for a loading line when it is
  // true. Reusing it would blank the wardrobe every time one item finished.
  it('does not blank the grid while a poll reloads it', async () => {
    await render([item({ id: 'a', status: 'failed' })]);
    switchToFakeTimers();
    startTagging();

    vi.advanceTimersByTime(2000);
    poll().flush({ items: [], total: 0 });
    TestBed.tick();

    expect(text()).not.toContain('Loading your wardrobe');
    expect(tiles()).toHaveLength(1);

    mock
      .expectOne((candidate) => candidate.method === 'GET' && !candidate.params.has('status'))
      .flush({ items: [item({ id: 'a', display_name: 'black wool coat' })], total: 1 });
    TestBed.tick();

    expect(tileText(0)).not.toContain('Tagging');
  });

  // C7 bridged rather than papered over. The server still calls this row
  // processing and may yet finish it, so the tile may not say it failed and may
  // not take the danger token 057 reserves for something being wrong.
  it('says it stopped waiting rather than that tagging failed', async () => {
    await render([item({ id: 'a', status: 'failed' })]);
    switchToFakeTimers();
    startTagging();

    for (let elapsed = 2000; elapsed <= 180_000; elapsed += 2000) {
      vi.advanceTimersByTime(2000);
      poll().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });
    }
    TestBed.tick();

    expect(tileText(0)).toContain('We stopped waiting');
    expect(tileText(0)).not.toContain('Tagging failed');
    expect(text()).not.toContain('Tagging 1 item');
    expect(retryButtons()).toHaveLength(1);
  });

  // WardrobeStore is providedIn: 'root' and outlives this component, so nothing
  // else would ever stop the loop. Without this the poll keeps running behind
  // every screen the user goes to next.
  it('stops polling when the page is destroyed', async () => {
    await render([item({ id: 'a', status: 'failed' })]);
    switchToFakeTimers();
    startTagging();

    vi.advanceTimersByTime(2000);
    poll().flush({ items: [item({ id: 'a', status: 'processing' })], total: 1 });

    fixture.destroy();

    vi.advanceTimersByTime(60_000);
    mock.expectNone((candidate) => candidate.method === 'GET');
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { Item } from '../../shared/models/item.model';
import { ItemDetailPage } from './item-detail.page';

let fixture: ComponentFixture<ItemDetailPage>;
let mock: HttpTestingController;
let store: WardrobeStore;
let router: Router;

// The route parameter is read from the snapshot once, in the constructor, so
// the stub only has to be right at the moment createComponent runs. A mutable
// id rather than TestBed.overrideProvider: the module is already instantiated
// by the time a test could override, because beforeEach injects from it.
let currentId = 'item-1';

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 'item-1',
    short_id: 'AB12CD',
    status: 'ready',
    image_public_id: 'bijoux/users/1/abc',
    image_url: 'https://res.cloudinary.com/demo/image/upload/w_300/abc.jpg',
    category: 'bottom',
    subcategory: 'jeans',
    fit: 'straight',
    length: 'full',
    rise: 'high',
    color_primary: 'light_blue',
    color_secondary: null,
    pattern: 'denim_wash',
    material: 'denim',
    formality: 2,
    warmth: 2,
    layer: 'base',
    water_resistant: false,
    display_name: 'light blue straight jeans',
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

function host(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return host().textContent ?? '';
}

function styleAroundLink(): HTMLAnchorElement | undefined {
  return [...host().querySelectorAll('a')].find(
    (candidate) => candidate.textContent?.trim() === 'Style around this',
  );
}

function buttonWith(fragment: string): HTMLButtonElement {
  return [...host().querySelectorAll('button')].find((candidate) =>
    candidate.textContent?.includes(fragment),
  )!;
}

function maybeButtonWith(fragment: string): HTMLButtonElement | undefined {
  return [...host().querySelectorAll('button')].find((candidate) =>
    candidate.textContent?.includes(fragment),
  );
}

async function press(fragment: string): Promise<void> {
  buttonWith(fragment).click();
  await fixture.whenStable();
}

async function saveForm(): Promise<void> {
  host().querySelector('form')!.dispatchEvent(new Event('submit'));
  await fixture.whenStable();
}

function itemRequest(id = 'item-1') {
  return mock.expectOne(`${environment.apiUrl}/items/${id}`);
}

// The store is seeded through its own load(), never by reaching into a signal:
// the page's whole question is whether it reads the collection or fetches, and
// a hand-set signal would not tell those apart the way a flushed request does.
async function seedStore(rows: readonly Item[]): Promise<void> {
  store.load();
  mock
    .expectOne((candidate) => candidate.method === 'GET')
    .flush({ items: rows, total: rows.length });
  await Promise.resolve();
}

async function render(id = 'item-1'): Promise<void> {
  currentId = id;
  fixture = TestBed.createComponent(ItemDetailPage);
  await fixture.whenStable();
}

describe('ItemDetailPage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'wardrobe/:id', children: [] },
        ]),
        {
          provide: ActivatedRoute,
          // The key is honoured rather than ignored. A stub that answers every
          // key with the same value cannot tell paramMap.get('id') from
          // paramMap.get('itemId') — found by a mutation that survived the
          // whole suite on exactly that.
          useValue: {
            snapshot: { paramMap: { get: (key: string) => (key === 'id' ? currentId : null) } },
          },
        },
      ],
    });
    currentId = 'item-1';
    mock = TestBed.inject(HttpTestingController);
    store = TestBed.inject(WardrobeStore);
    router = TestBed.inject(Router);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  it('reads the row from the collection without a request', async () => {
    await seedStore([item()]);
    await render();

    expect(text()).toContain('light blue straight jeans');
  });

  // The deep link. Nothing is loaded, so the page fetches by id — and the row
  // it gets never enters items(). 127.
  it('fetches by id when the collection has no such row', async () => {
    await render();
    itemRequest().flush(item());
    await fixture.whenStable();

    expect(text()).toContain('light blue straight jeans');
    expect(store.items()).toEqual([]);
  });

  it('says so when the item cannot be opened', async () => {
    await render();
    itemRequest().flush(
      { detail: 'no', code: 'not_found' },
      { status: 404, statusText: 'Not Found' },
    );
    await fixture.whenStable();

    expect(text()).toContain("We couldn't open that item");
  });

  // O-10's transform, hand-transcribed here as well as in the pipe's own spec:
  // this is the assertion that the *screen* asks for the detail size, where
  // that one asserts the pipe builds it.
  it('renders the detail transform rather than the thumbnail the server sent', async () => {
    await seedStore([item()]);
    await render();

    const src = host().querySelector('img')!.getAttribute('src')!;
    expect(src).toContain('/w_800,c_limit,f_auto,q_auto/');
    expect(src).toContain('bijoux/users/1/abc');
  });

  it('shows the edited badge only when the row carries one', async () => {
    await seedStore([item({ user_edited: true })]);
    await render();

    expect(text()).toContain('You edited this');
  });

  it('does not show the edited badge on an untouched row', async () => {
    await seedStore([item()]);
    await render();

    expect(text()).not.toContain('You edited this');
  });

  // STAGE-1 1.9: do not open this editor on a processing item. A deep link can
  // land on one, so the guard is the page's rather than the caller's.
  it('does not render the editor while the row is processing', async () => {
    await seedStore([item({ status: 'processing' })]);
    await render();

    expect(host().querySelector('form')).toBeNull();
    expect(text()).toContain('Bijoux is tagging this item');
  });

  it('renders the editor on a failed row, which is what O-3 promised', async () => {
    await seedStore([item({ status: 'failed' })]);
    await render();

    expect(host().querySelector('form')).not.toBeNull();
  });

  // D: the message is read off the status the response carried, never off a
  // client-side copy of the required set.
  it('says a failed row still does not count as tagged', async () => {
    await seedStore([item({ status: 'failed' })]);
    await render();

    expect(text()).toContain("still doesn't count as tagged");
  });

  it('stops saying so once the save comes back ready', async () => {
    await seedStore([item({ status: 'failed' })]);
    await render();
    await saveForm();
    itemRequest().flush(item({ status: 'ready' }));
    await fixture.whenStable();

    expect(text()).not.toContain("still doesn't count as tagged");
  });

  it('renders one general message when a save is refused', async () => {
    await seedStore([item()]);
    await render();
    await saveForm();
    itemRequest().flush(
      { detail: 'fit does not describe category', code: 'validation_error' },
      { status: 422, statusText: 'Unprocessable Content' },
    );
    await fixture.whenStable();

    expect(text()).toContain("We couldn't save those tags");
    // 099's rule, one endpoint over: the server's own words are not rendered.
    expect(text()).not.toContain('does not describe category');
  });

  it('shows the wear placeholder rather than a zero', async () => {
    await seedStore([item()]);
    await render();

    expect(text()).toContain('Wear history');
    expect(text()).toContain('once outfits arrive');
  });

  // --- retag, two steps ----------------------------------------------------

  it('sends an unforced retag first', async () => {
    await seedStore([item({ user_edited: true })]);
    await render();
    await press('Tag this again');

    mock
      .expectOne(`${environment.apiUrl}/items/item-1/retag`)
      .flush(item({ status: 'processing' }));
  });

  it('opens a second step naming what is discarded when the 409 lands', async () => {
    await seedStore([item({ user_edited: true })]);
    await render();
    await press('Tag this again');
    mock
      .expectOne(`${environment.apiUrl}/items/item-1/retag`)
      .flush({ detail: 'no', code: 'item_edited' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    expect(text()).toContain('replaces the tags you set by hand');
    expect(maybeButtonWith('Replace my tags')).toBeTruthy();
  });

  it('sends force only from that second step', async () => {
    await seedStore([item({ user_edited: true })]);
    await render();
    await press('Tag this again');
    mock
      .expectOne(`${environment.apiUrl}/items/item-1/retag`)
      .flush({ detail: 'no', code: 'item_edited' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();
    await press('Replace my tags');

    mock
      .expectOne(`${environment.apiUrl}/items/item-1/retag?force=true`)
      .flush(item({ status: 'processing' }));
  });

  it('keeps the tags when the second step is declined', async () => {
    await seedStore([item({ user_edited: true })]);
    await render();
    await press('Tag this again');
    mock
      .expectOne(`${environment.apiUrl}/items/item-1/retag`)
      .flush({ detail: 'no', code: 'item_edited' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();
    await press('Keep my tags');

    expect(maybeButtonWith('Replace my tags')).toBeUndefined();
  });

  it('branches on the code rather than the status', async () => {
    await seedStore([item({ user_edited: true })]);
    await render();
    await press('Tag this again');
    mock
      .expectOne(`${environment.apiUrl}/items/item-1/retag`)
      .flush({ detail: 'no' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    expect(maybeButtonWith('Replace my tags')).toBeUndefined();
    expect(text()).toContain("couldn't start tagging again");
  });

  it('returns to the grid after a retag starts', async () => {
    await seedStore([item()]);
    await render();
    await press('Tag this again');
    mock
      .expectOne(`${environment.apiUrl}/items/item-1/retag`)
      .flush(item({ status: 'processing' }));
    await fixture.whenStable();

    expect(router.url).toBe('/wardrobe');
  });

  // --- delete, two steps ---------------------------------------------------

  it('arms rather than deleting on the first press', async () => {
    await seedStore([item()]);
    await render();
    await press('Delete');

    expect(text()).toContain('Tap again to delete');
    mock.verify();
  });

  it('deletes on the second press', async () => {
    await seedStore([item()]);
    await render();
    await press('Delete');
    await press('Tap again to delete');

    const request = itemRequest();
    expect(request.request.method).toBe('DELETE');
    request.flush(item({ is_archived: true }));
  });

  it('disarms on blur', async () => {
    await seedStore([item()]);
    await render();
    await press('Delete');
    buttonWith('Tap again to delete').dispatchEvent(new Event('blur'));
    await fixture.whenStable();

    expect(text()).not.toContain('Tap again to delete');
  });

  it('disarms when another control is used', async () => {
    await seedStore([item()]);
    await render();
    await press('Delete');
    await saveForm();
    itemRequest().flush(item());
    await fixture.whenStable();

    expect(text()).not.toContain('Tap again to delete');
  });

  it('returns to the grid after a delete', async () => {
    await seedStore([item()]);
    await render();
    await press('Delete');
    await press('Tap again to delete');
    itemRequest().flush(item({ is_archived: true }));
    await fixture.whenStable();

    expect(router.url).toBe('/wardrobe');
    expect(store.items()).toEqual([]);
    expect(store.total()).toBe(0);
  });

  it('stays put and says so when the delete fails', async () => {
    await seedStore([item()]);
    await render();
    await press('Delete');
    await press('Tap again to delete');
    itemRequest().flush({ detail: 'no' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain("We couldn't delete that item");
    expect(store.items()).toHaveLength(1);
  });

  // --- "Style around this", task 2.10 --------------------------------------

  it('offers the stylist the row it is looking at', async () => {
    await seedStore([item()]);
    await render();

    expect(styleAroundLink()?.getAttribute('href')).toBe('/stylist?anchor=item-1');
  });

  it('does not offer it on a row the stylist is never shown', async () => {
    // `processing` and `failed` rows are not `ready`, so `_wardrobe` never
    // sends them and the endpoint would answer `anchor_unavailable`.
    await seedStore([item({ status: 'processing' })]);
    await render();

    expect(styleAroundLink()).toBeUndefined();
  });
});

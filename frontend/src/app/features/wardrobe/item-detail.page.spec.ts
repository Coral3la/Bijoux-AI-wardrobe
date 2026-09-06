import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { ItemSet } from '../../shared/models/item-set.model';
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
    wear_count: 0,
    last_worn_at: null,
    is_archived: false,
    set_id: null,
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
    vi.useRealTimers();
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

  // The placeholder test that stood here until 3.4 is deleted rather than
  // edited, the way `test_feedback_is_refused_until_task_3_3` was on the
  // server: it asserted that nothing was readable yet, and something is.

  it('says a garment has never been worn rather than printing a zero', async () => {
    await seedStore([item({ wear_count: 0, last_worn_at: null })]);
    await render();

    expect(text()).toContain('Wear history');
    expect(text()).toContain('Never worn');
    expect(text()).not.toContain('Wears: 0');
  });

  it('shows the count and the last day once it has been worn', async () => {
    await seedStore([item({ wear_count: 3, last_worn_at: '2026-03-09' })]);
    await render();

    expect(text()).toContain('Wears: 3');
    expect(text()).toContain('Last worn 2026-03-09');
    expect(text()).not.toContain('Never worn');
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
  // --- the set row, task 4A.2 ----------------------------------------------

  function itemSet(members: readonly Item[], overrides: Partial<ItemSet> = {}): ItemSet {
    return {
      id: 'set-1',
      name: null,
      items: members,
      created_at: '2026-09-06T09:00:00Z',
      ...overrides,
    };
  }

  // A garment already in set-1. The store's copy carries the id, because that
  // is what the wire sends on every item payload; the set object carries the
  // rows, because that is what GET /sets/{set_id} answers with.
  function member(id: string, name: string): Item {
    return item({ id, display_name: name, set_id: 'set-1' });
  }

  function setRequest(id = 'set-1') {
    return mock.expectOne(`${environment.apiUrl}/sets/${id}`);
  }

  function pickTile(name: string): HTMLButtonElement {
    return [...host().querySelectorAll<HTMLButtonElement>('app-set-picker li button')].find(
      (candidate) => candidate.textContent?.includes(name),
    )!;
  }

  async function renderInSet(members: readonly Item[], overrides: Partial<ItemSet> = {}) {
    await seedStore(members);
    await render();
    setRequest().flush(itemSet(members, overrides));
    await fixture.whenStable();
  }

  it('asks for no set on a garment that is in none', async () => {
    await seedStore([item()]);
    await render();

    expect(text()).toContain('A set is two or more garments');
    expect(buttonWith('Declare a set')).toBeDefined();
    expect(maybeButtonWith('Remove from this set')).toBeUndefined();
  });

  // The members come from GET /sets/{set_id} and not from items(), for two
  // reasons this file can only show one of: the collection excludes archived
  // rows, and a deep link has no collection at all. The archived half is below.
  it('reads the set by id and draws the other members as links', async () => {
    await renderInSet([
      member('item-1', 'light blue straight jeans'),
      member('item-2', 'navy linen blazer'),
    ]);

    const links = [...host().querySelectorAll('a')].map((node) => node.getAttribute('href'));
    expect(links).toContain('/wardrobe/item-2');
    expect(text()).toContain('navy linen blazer');
  });

  it('does not draw the garment on screen among the members', async () => {
    await renderInSet([
      member('item-1', 'light blue straight jeans'),
      member('item-2', 'navy linen blazer'),
    ]);

    const links = [...host().querySelectorAll('a')].map((node) => node.getAttribute('href'));
    expect(links).not.toContain('/wardrobe/item-1');
  });

  it('prints the set’s name when it has one', async () => {
    await renderInSet([member('item-1', 'jeans'), member('item-2', 'blazer')], {
      name: 'the linen suit',
    });

    expect(text()).toContain('the linen suit');
  });

  // An archived member stays in its set and GET /items excludes it, so this row
  // is the only place in the application it can be seen. 04-API-SPEC.md
  // requires a client that draws a set to say so.
  it('marks a member the wardrobe has archived', async () => {
    await renderInSet([
      member('item-1', 'jeans'),
      { ...member('item-2', 'blazer'), is_archived: true },
    ]);

    expect(text()).toContain('Archived');
  });

  // One short word, so an assertion against en.json's own value cannot tell a
  // lookup from a typed literal. A second table with a different value can.
  it('reads the archived marker from the string table', async () => {
    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush({ ...en, 'item.set.archived': 'Put away' });
    await loading;

    await renderInSet([
      member('item-1', 'jeans'),
      { ...member('item-2', 'blazer'), is_archived: true },
    ]);

    expect(text()).toContain('Put away');
  });

  // The rule DELETE /sets/{id}/items/{id} enforces, said once in the place the
  // user can act on it. Two members exactly: at three the set survives.
  it('warns that removing from a set of two ends the set', async () => {
    await renderInSet([member('item-1', 'jeans'), member('item-2', 'blazer')]);

    expect(text()).toContain('removing this one ends the set');
  });

  it('does not warn on a set of three', async () => {
    await renderInSet([
      member('item-1', 'jeans'),
      member('item-2', 'blazer'),
      member('item-3', 'shirt'),
    ]);

    expect(text()).not.toContain('removing this one ends the set');
  });

  // set_id says this garment is in a set, so the empty state would be a lie —
  // it offers to declare one that already exists.
  it('says so when the set cannot be read, and still does not offer to declare one', async () => {
    await seedStore([member('item-1', 'jeans')]);
    await render();
    setRequest().flush({ detail: 'no' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain("We couldn't open this set");
    expect(maybeButtonWith('Declare a set')).toBeUndefined();
  });

  describe('declaring and adding', () => {
    it('declares a set over this garment and the one picked', async () => {
      await seedStore([item(), item({ id: 'item-2', display_name: 'navy linen blazer' })]);
      await render();
      await press('Declare a set');
      pickTile('navy linen blazer').click();
      await fixture.whenStable();

      const request = mock.expectOne(`${environment.apiUrl}/sets`);
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({ item_ids: ['item-1', 'item-2'] });
      request.flush(itemSet([member('item-1', 'jeans'), member('item-2', 'navy linen blazer')]));
      await fixture.whenStable();

      expect(text()).toContain('navy linen blazer');
    });

    // The silent half. Without it the tile behind this screen goes on saying
    // the garment is in no set until the next load().
    it('moves the store’s copy of both garments', async () => {
      await seedStore([item(), item({ id: 'item-2', display_name: 'navy linen blazer' })]);
      await render();
      await press('Declare a set');
      pickTile('navy linen blazer').click();
      await fixture.whenStable();
      mock
        .expectOne(`${environment.apiUrl}/sets`)
        .flush(itemSet([member('item-1', 'jeans'), member('item-2', 'navy linen blazer')]));
      await fixture.whenStable();

      expect(store.items().map((row) => row.set_id)).toEqual(['set-1', 'set-1']);
    });

    it('adds to the set this garment already has, rather than declaring a second', async () => {
      await renderInSet([member('item-1', 'jeans'), member('item-2', 'blazer')]);
      store.load();
      mock
        .expectOne((candidate) => candidate.method === 'GET')
        .flush({
          items: [
            member('item-1', 'jeans'),
            member('item-2', 'blazer'),
            item({ id: 'item-3', display_name: 'white shirt' }),
          ],
          total: 3,
        });
      await fixture.whenStable();

      await press('Add to this set');
      pickTile('white shirt').click();
      await fixture.whenStable();

      const request = mock.expectOne(`${environment.apiUrl}/sets/set-1/items`);
      expect(request.request.body).toEqual({ item_id: 'item-3' });
      request.flush(
        itemSet([
          member('item-1', 'jeans'),
          member('item-2', 'blazer'),
          member('item-3', 'white shirt'),
        ]),
      );
      await fixture.whenStable();

      expect(text()).toContain('white shirt');
    });

    it('keeps the sheet open and names the refusal when the wire refuses', async () => {
      await seedStore([item(), item({ id: 'item-2', display_name: 'navy linen blazer' })]);
      await render();
      await press('Declare a set');
      pickTile('navy linen blazer').click();
      await fixture.whenStable();
      mock
        .expectOne(`${environment.apiUrl}/sets`)
        .flush(
          { detail: 'no', code: 'set_member_taken' },
          { status: 422, statusText: 'Unprocessable Content' },
        );
      await fixture.whenStable();

      expect(text()).toContain('already belongs to another set');
      expect(pickTile('navy linen blazer')).toBeDefined();
    });

    // Branches on the documented code, never on the status: the two 422s are
    // two different things to say and only one of them names a next step.
    it('tells the two refusals apart', async () => {
      await seedStore([item(), item({ id: 'item-2', display_name: 'navy linen blazer' })]);
      await render();
      await press('Declare a set');
      pickTile('navy linen blazer').click();
      await fixture.whenStable();
      mock
        .expectOne(`${environment.apiUrl}/sets`)
        .flush(
          { detail: 'no', code: 'set_item_unavailable' },
          { status: 422, statusText: 'Unprocessable Content' },
        );
      await fixture.whenStable();

      expect(text()).toContain("can't join a set yet");
    });
  });

  describe('removing', () => {
    // The 200. The set survives with the members that remain, and only this
    // garment is detached — the other two keep the set_id they had.
    it('leaves the other members in the set when the set survives', async () => {
      await renderInSet([
        member('item-1', 'jeans'),
        member('item-2', 'blazer'),
        member('item-3', 'shirt'),
      ]);

      await press('Remove from this set');
      mock
        .expectOne(`${environment.apiUrl}/sets/set-1/items/item-1`)
        .flush(itemSet([member('item-2', 'blazer'), member('item-3', 'shirt')]));
      await fixture.whenStable();

      expect(store.items().map((row) => row.id)).toEqual(['item-1', 'item-2', 'item-3']);
      expect(store.items().map((row) => row.set_id)).toEqual([null, 'set-1', 'set-1']);
    });

    // The 204. The removal dissolved the set, so the member that was never
    // named in the URL loses its set_id too — and nothing on the wire says so.
    it('clears the other member as well when the removal dissolved the set', async () => {
      await renderInSet([member('item-1', 'jeans'), member('item-2', 'blazer')]);

      await press('Remove from this set');
      mock
        .expectOne(`${environment.apiUrl}/sets/set-1/items/item-1`)
        .flush(null, { status: 204, statusText: 'No Content' });
      await fixture.whenStable();

      expect(store.items().map((row) => row.set_id)).toEqual([null, null]);
    });

    it('ends in the same state on both answers', async () => {
      await renderInSet([member('item-1', 'jeans'), member('item-2', 'blazer')]);

      await press('Remove from this set');
      mock
        .expectOne(`${environment.apiUrl}/sets/set-1/items/item-1`)
        .flush(null, { status: 204, statusText: 'No Content' });
      await fixture.whenStable();

      expect(text()).toContain('A set is two or more garments');
      expect(maybeButtonWith('Remove from this set')).toBeUndefined();
    });

    it('stays put and says so when the removal fails', async () => {
      await renderInSet([member('item-1', 'jeans'), member('item-2', 'blazer')]);

      await press('Remove from this set');
      mock
        .expectOne(`${environment.apiUrl}/sets/set-1/items/item-1`)
        .flush({ detail: 'no' }, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(text()).toContain("We couldn't take this garment out of its set");
      expect(store.items()[0].set_id).toBe('set-1');
    });
  });

  describe('the picker on a deep link', () => {
    // The set row survives a hard refresh because the members come off the
    // wire, but the picker's candidates are the wardrobe — and on this route
    // nothing has loaded it. The store's own load, not a second fetch path.
    it('loads the wardrobe when the sheet opens on an empty collection', async () => {
      await render();
      itemRequest().flush(item());
      await fixture.whenStable();

      await press('Declare a set');

      const request = mock.expectOne((candidate) => candidate.method === 'GET');
      expect(request.request.url).toBe(`${environment.apiUrl}/items`);
      request.flush({ items: [item(), item({ id: 'item-2', display_name: 'blazer' })], total: 2 });
      await fixture.whenStable();

      expect(pickTile('blazer')).toBeDefined();
    });

    it('asks for nothing when the collection is already there', async () => {
      await seedStore([item(), item({ id: 'item-2', display_name: 'blazer' })]);
      await render();

      await press('Declare a set');

      mock.expectNone((candidate) => candidate.method === 'GET');
      expect(pickTile('blazer')).toBeDefined();
    });

    // The store is providedIn: 'root' and outlives this page, so a run started
    // by the load above would poll behind whatever screen comes next. This is
    // WardrobePage's guard on the second page that can start one — and it is
    // the failure that would otherwise never be seen, because nothing on screen
    // shows a poll that is still running.
    it('stops polling when the page is destroyed', async () => {
      await render();
      itemRequest().flush(item());
      await fixture.whenStable();

      vi.useFakeTimers();
      buttonWith('Declare a set').click();
      TestBed.tick();
      mock
        .expectOne((candidate) => candidate.method === 'GET')
        .flush({ items: [item({ id: 'item-2', status: 'processing' })], total: 1 });
      TestBed.tick();

      vi.advanceTimersByTime(2000);
      mock
        .expectOne((candidate) => candidate.params.get('status') === 'processing')
        .flush({ items: [item({ id: 'item-2', status: 'processing' })], total: 1 });

      fixture.destroy();

      vi.advanceTimersByTime(60_000);
      mock.expectNone((candidate) => candidate.method === 'GET');
    });
  });
});

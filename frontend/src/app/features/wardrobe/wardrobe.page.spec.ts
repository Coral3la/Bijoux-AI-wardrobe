import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

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

  // Nothing on this screen refreshes itself until task 1.7 polls, so the line
  // has to name the action that does.
  it('tells a waiting user to reload while items are tagging', async () => {
    await render([
      item({ id: 'a', status: 'processing' }),
      item({ id: 'b', status: 'processing' }),
    ]);

    expect(text()).toContain('Tagging 2 items');
    expect(text()).toContain('Reload the page');
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
});

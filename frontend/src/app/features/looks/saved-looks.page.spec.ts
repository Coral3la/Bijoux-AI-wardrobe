import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { LooksStore } from '../../core/state/looks.store';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import { SavedLooksPage } from './saved-looks.page';

let fixture: ComponentFixture<SavedLooksPage>;
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

function look(overrides: Partial<Look> = {}): Look {
  return {
    id: 'look-1',
    occasion: 'work',
    title: 'Morning meetings',
    items: [item()],
    reasoning: 'The high-rise jean balances the oversized shirt.',
    weather_note: 'Mild at 18°C — the blazer is enough.',
    is_saved: true,
    feedback: null,
    ...overrides,
  };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function hearts(): HTMLButtonElement[] {
  return [
    ...element().querySelectorAll<HTMLButtonElement>(
      `button[aria-label="${en['stylist.look.save']}"]`,
    ),
  ];
}

function listRequest() {
  return mock.expectOne(`${environment.apiUrl}/looks?is_saved=true`);
}

async function render(): Promise<void> {
  fixture = TestBed.createComponent(SavedLooksPage);
  fixture.detectChanges();
  await fixture.whenStable();
}

describe('SavedLooksPage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'wardrobe/:id', children: [] },
          { path: 'stylist', children: [] },
        ]),
      ],
    });
    mock = TestBed.inject(HttpTestingController);
    TestBed.inject(LooksStore).reset();

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
  });

  it('asks for the saved looks on arrival', async () => {
    await render();

    listRequest().flush({ looks: [], total: 0 });
  });

  it('says so while the list is loading', async () => {
    await render();

    expect(text()).toContain(en['saved.loading']);

    listRequest().flush({ looks: [], total: 0 });
  });

  it('offers a way to the stylist when nothing is saved', async () => {
    // The empty state is the likeliest first visit: the heart is one task old
    // and no account has used it. A dead end here would be the screen's whole
    // content for most users.
    await render();
    listRequest().flush({ looks: [], total: 0 });
    await fixture.whenStable();

    expect(text()).toContain(en['saved.empty.title']);
    const cta = element().querySelector<HTMLAnchorElement>('a[href="/stylist"]');
    expect(cta?.textContent?.trim()).toBe(en['saved.empty.cta']);
  });

  it('renders one row per saved look, with its garments', async () => {
    await render();
    listRequest().flush({
      looks: [look(), look({ id: 'look-2', title: 'Dinner out' })],
      total: 2,
    });
    await fixture.whenStable();

    expect(element().querySelectorAll('li > h2, li h2')).toHaveLength(2);
    expect(text()).toContain('Morning meetings');
    expect(text()).toContain('Dinner out');
    expect(element().querySelectorAll('app-item-card')).toHaveLength(2);
  });

  it('keeps the server order of the garments', async () => {
    // look_items.position all the way through: the server sorts by it and this
    // screen does not re-sort, unlike the look card which groups by layer.
    await render();
    listRequest().flush({
      looks: [look({ items: [item({ id: 'item-2' }), item({ id: 'item-1' })] })],
      total: 1,
    });
    await fixture.whenStable();

    const images = [...element().querySelectorAll('app-item-card a')].map((node) =>
      node.getAttribute('href'),
    );
    expect(images).toEqual(['/wardrobe/item-2', '/wardrobe/item-1']);
  });

  it('unsaves a look through the heart', async () => {
    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    hearts()[0].click();

    const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ is_saved: false });
    request.flush(look({ is_saved: false }));
  });

  it('leaves the row on screen with an empty heart after unsaving', async () => {
    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    hearts()[0].click();
    mock.expectOne(`${environment.apiUrl}/looks/look-1`).flush(look({ is_saved: false }));
    await fixture.whenStable();

    expect(hearts()).toHaveLength(1);
    expect(hearts()[0].getAttribute('aria-pressed')).toBe('false');
  });

  it('saves it again from the same button', async () => {
    await render();
    listRequest().flush({ looks: [look({ is_saved: false })], total: 1 });
    await fixture.whenStable();

    hearts()[0].click();

    const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
    expect(request.request.body).toEqual({ is_saved: true });
    request.flush(look({ is_saved: true }));
  });

  it('disables every heart while one write is in flight', async () => {
    // The store takes one write at a time, so a second tap would be dropped
    // silently. Disabling says so rather than letting it look broken.
    await render();
    listRequest().flush({ looks: [look(), look({ id: 'look-2' })], total: 2 });
    await fixture.whenStable();

    hearts()[0].click();
    await fixture.whenStable();

    expect(hearts().map((button) => button.disabled)).toEqual([true, true]);

    mock.expectOne(`${environment.apiUrl}/looks/look-1`).flush(look({ is_saved: false }));
  });

  it('reports a failed load', async () => {
    await render();
    listRequest().flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain(en['looks.error.load']);
  });

  it('reports a failed write without emptying the list', async () => {
    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    hearts()[0].click();
    mock
      .expectOne(`${environment.apiUrl}/looks/look-1`)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain(en['looks.error.general']);
    expect(hearts()).toHaveLength(1);
  });
});

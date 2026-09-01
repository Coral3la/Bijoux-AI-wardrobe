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
import { todayInLocalTime } from '../stylist/look-request-form';
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
    wear_count: 0,
    last_worn_at: null,
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
    worn_at: null,
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

// Matched on containment rather than equality: the worn button carries a ✓
// beside its label, so an exact match would find the unworn ones only — which
// is the state half these tests are about.
function wearButtons(): HTMLButtonElement[] {
  return [...element().querySelectorAll<HTMLButtonElement>('button')].filter((candidate) =>
    [en['saved.wear'], en['saved.wear.done']].some((label) =>
      (candidate.textContent ?? '').includes(label),
    ),
  );
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

  // Two rows, and the row's own shape inside each: four plates and the two
  // lines of text beside them. Twelve is that arithmetic — a block per row
  // would satisfy "something is loading" and promise the wrong screen.
  // DECISIONS.md 217, 221.
  it('draws the row shape while the list is loading', async () => {
    await render();

    expect((fixture.nativeElement as HTMLElement).querySelectorAll('app-skeleton')).toHaveLength(
      12,
    );

    listRequest().flush({ looks: [], total: 0 });
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelectorAll('app-skeleton')).toHaveLength(0);
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

  // The row's photographs are the whole of the left column, at a quarter of
  // 320px each. The caption input the stylist added is what turns the wardrobe's
  // colour line off; without it every plate here carries a name nobody can read.
  it('draws the garments without the wardrobe caption', async () => {
    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    expect(element().querySelectorAll('app-item-card')).toHaveLength(1);
    expect(text()).not.toContain('white oversized shirt');
  });

  // What the look was asked for, in the slot the mockup drew a save date in.
  // Nothing on the wire carries a save date, so this is the row's kicker.
  it('heads the row with the occasion the look was built for', async () => {
    await render();
    listRequest().flush({ looks: [look({ occasion: 'evening' })], total: 1 });
    await fixture.whenStable();

    expect(text()).toContain(en['vocabulary.occasion.evening']);
  });

  // `looks.occasion` is TEXT on the server and nothing on the wire narrows it,
  // so a value outside the vocabulary is possible — and t() renders a missing
  // key as itself, which would print `vocabulary.occasion.brunch` at the reader.
  it('prints no kicker for an occasion outside the vocabulary', async () => {
    await render();
    listRequest().flush({ looks: [look({ occasion: 'brunch' })], total: 1 });
    await fixture.whenStable();

    expect(text()).not.toContain('vocabulary.occasion');
  });

  it('counts the saved looks in the header', async () => {
    await render();
    listRequest().flush({ looks: [look(), look({ id: 'look-2' })], total: 2 });
    await fixture.whenStable();

    expect(text()).toContain(en['saved.count.other'].replace('{{count}}', '2'));
  });

  // The two English values coincide at one — "1 saved" either way, because
  // "saved" does not inflect — so nothing on the screen can tell the branch
  // apart and only a second table can. The pair exists for a language that
  // inflects rather than for this one, which is why it is worth pinning at all.
  it('takes the singular key for one saved look', async () => {
    const loading = TestBed.inject(I18nService).load();
    TestBed.inject(HttpTestingController)
      .expectOne('/i18n/en.json')
      .flush({ ...en, 'saved.count.one': 'just the one' });
    await loading;

    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    expect(text()).toContain('just the one');
  });

  // The count is read from the string table rather than assembled in the
  // component, and this is the only assertion that can tell the two apart: a
  // hard-coded `${count} saved` renders identically under en.json's own value
  // and survives every other test in this file.
  it('takes the count line from the string table rather than from the code', async () => {
    const loading = TestBed.inject(I18nService).load();
    TestBed.inject(HttpTestingController)
      .expectOne('/i18n/en.json')
      .flush({ ...en, 'saved.count.other': '{{count}} kept' });
    await loading;

    await render();
    listRequest().flush({ looks: [look(), look({ id: 'look-2' })], total: 2 });
    await fixture.whenStable();

    expect(text()).toContain('2 kept');
  });

  // Counted off is_saved and not off the rows: the list keeps a look that has
  // just been unsaved, so a count of rows would claim a save the empty heart
  // under it denies.
  it('stops counting a look the moment it is unsaved', async () => {
    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    hearts()[0].click();
    mock.expectOne(`${environment.apiUrl}/looks/look-1`).flush(look({ is_saved: false }));
    await fixture.whenStable();

    expect(text()).toContain(en['saved.count.other'].replace('{{count}}', '0'));
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

  it('sends today as the wear date', async () => {
    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    wearButtons()[0].click();

    const request = mock.expectOne(`${environment.apiUrl}/looks/look-1/wear`);
    // The browser's today, which is the whole reason the endpoint refuses no
    // date: a client east of UTC names a day the server would call tomorrow.
    expect(request.request.body).toEqual({ date: todayInLocalTime() });

    request.flush(look({ worn_at: todayInLocalTime() }));
    await fixture.whenStable();
  });

  it('relabels and disables the button once the look was worn today', async () => {
    await render();
    listRequest().flush({ looks: [look({ worn_at: todayInLocalTime() })], total: 1 });
    await fixture.whenStable();

    expect(wearButtons()[0].textContent).toContain(en['saved.wear.done']);
    expect(wearButtons()[0].disabled).toBe(true);
  });

  it('still offers the button when the look was worn on an earlier day', async () => {
    // A look worn last Tuesday can be worn again today, and the endpoint counts
    // that as a second wearing. Only today's date closes the button.
    await render();
    listRequest().flush({ looks: [look({ worn_at: '2020-01-01' })], total: 1 });
    await fixture.whenStable();

    expect(wearButtons()[0].textContent).toContain(en['saved.wear']);
    expect(wearButtons()[0].disabled).toBe(false);
  });

  it('reports a failed wear without emptying the list', async () => {
    await render();
    listRequest().flush({ looks: [look()], total: 1 });
    await fixture.whenStable();

    wearButtons()[0].click();
    mock
      .expectOne(`${environment.apiUrl}/looks/look-1/wear`)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain(en['looks.error.general']);
    expect(wearButtons()[0].textContent).toContain(en['saved.wear']);
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

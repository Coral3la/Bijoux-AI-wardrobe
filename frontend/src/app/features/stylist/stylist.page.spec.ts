import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { Item } from '../../shared/models/item.model';
import { SuggestResponse } from '../../shared/models/look.model';
import { User } from '../../shared/models/user.model';
import { Weather } from '../../shared/models/weather.model';
import { todayInLocalTime } from './look-request-form';
import { STATUS_INTERVAL_MS, StylistPage } from './stylist.page';

let fixture: ComponentFixture<StylistPage>;
let mock: HttpTestingController;
let router: Router;
let currentUser: User | null;
// The `?anchor=` the page is constructed under, and what the wardrobe store
// holds when it looks there first. Both reset in beforeEach.
let anchorParam: string | null;
let collection: Item[];

function user(overrides: Partial<User> = {}): User {
  return {
    id: 'user-1',
    email: 'her@example.com',
    display_name: 'Coral',
    height_cm: null,
    size_top: null,
    size_bottom: null,
    size_shoe: null,
    style_notes: null,
    home_city: 'Tel Aviv',
    home_lat: 32.08,
    home_lon: 34.78,
    created_at: '2026-08-01T09:00:00Z',
    ...overrides,
  };
}

function weather(overrides: Partial<Weather> = {}): Weather {
  return {
    date: todayInLocalTime(),
    temp_min_c: 24,
    temp_max_c: 31,
    precip_mm: 0,
    wind_kph: 12,
    condition: 'clear',
    rule: 'Use warmth 1-2 only.',
    ...overrides,
  };
}

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 'item-1',
    short_id: 'AB12CD',
    status: 'ready',
    image_public_id: 'bijoux/users/1/abc',
    image_url: 'https://res.cloudinary.com/demo/image/upload/w_300/abc.jpg',
    category: 'bottom',
    subcategory: 'jeans',
    fit: 'relaxed',
    length: null,
    rise: 'high',
    color_primary: 'blue',
    color_secondary: null,
    pattern: 'solid',
    material: 'denim',
    formality: 2,
    warmth: 2,
    layer: 'base',
    water_resistant: false,
    display_name: 'light blue mom jeans',
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

function response(overrides: Partial<SuggestResponse> = {}): SuggestResponse {
  return {
    looks: [
      {
        id: 'look-1',
        occasion: 'casual',
        title: 'Morning meetings',
        items: [],
        reasoning: 'The blazer lifts the knit without making it formal.',
        weather_note: 'Warm at 31°C.',
        is_saved: false,
        feedback: null,
        worn_at: null,
      },
    ],
    missing_pieces: [],
    message: 'A casual outfit for a warm day.',
    ...overrides,
  };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function form(): HTMLElement | null {
  return element().querySelector('app-look-request-form');
}

function skeletonTiles(): HTMLElement[] {
  return [...element().querySelectorAll<HTMLElement>('.animate-pulse')];
}

function status(): string {
  return element().querySelector('[role=status]')?.textContent?.trim() ?? '';
}

function buttonWith(label: string): HTMLButtonElement {
  return [...element().querySelectorAll('button')].find(
    (candidate) => candidate.textContent?.trim() === label,
  )!;
}

function backLink(): HTMLAnchorElement | null {
  return element().querySelector<HTMLAnchorElement>('a[href="/wardrobe"]');
}

function weatherRequest() {
  return mock.expectOne((candidate) => candidate.url === `${environment.apiUrl}/weather`);
}

function suggestRequest() {
  return mock.expectOne(`${environment.apiUrl}/looks/suggest`);
}

function anchorPin(): string | null {
  const pinned = [...element().querySelectorAll('p')].find((candidate) =>
    candidate.textContent?.includes('Building around'),
  );
  return pinned?.textContent?.trim() ?? null;
}

function clearAnchorButton(): HTMLButtonElement | null {
  return element().querySelector<HTMLButtonElement>(
    `button[aria-label="${en['stylist.anchor.clear']}"]`,
  );
}

// The page asks for the forecast on construction, so every render answers it.
// `null` leaves the request open for a test that wants to inspect it.
async function render(forecast: Weather | null = weather()): Promise<void> {
  fixture = TestBed.createComponent(StylistPage);
  fixture.detectChanges();
  if (forecast !== null) {
    weatherRequest().flush(forecast);
  }
  await fixture.whenStable();
}

// Every press is awaited, never chained synchronously. The draft lives on the
// page and reaches the form as an input, so two clicks inside one task read
// the same stale draft and the second spreads over the first — the property
// FilterBar has had since 1.8, and the reason its spec awaits too.
async function press(label: string): Promise<void> {
  buttonWith(label).click();
  await fixture.whenStable();
}

async function submit(): Promise<void> {
  await press('Style me');
}

async function type(value: string): Promise<void> {
  const notes = element().querySelector('textarea')!;
  notes.value = value;
  notes.dispatchEvent(new Event('input'));
  await fixture.whenStable();
}

// The three garments a swap is measured on, and enough of a look to lay out:
// shoes are the piece users reject most, which is the example 05 and §2.11
// both use.
const SHOES = item({
  id: 'item-shoes',
  category: 'shoes',
  layer: 'standalone',
  display_name: 'loafers',
});
const SHIRT = item({ id: 'item-top', category: 'top', layer: 'base', display_name: 'shirt' });
const JEANS = item({ id: 'item-jeans', category: 'bottom', layer: 'base', display_name: 'jeans' });

function lookOf(items: readonly Item[]): SuggestResponse {
  const base = response();
  return { ...base, looks: [{ ...base.looks[0], items }] };
}

function swapBadge(name: string): HTMLButtonElement {
  return element().querySelector<HTMLButtonElement>(
    `button[aria-label="Swap ${name} for something else"]`,
  )!;
}

async function tapSwap(name: string): Promise<void> {
  swapBadge(name).click();
  await fixture.whenStable();
}

describe('StylistPage', () => {
  beforeEach(async () => {
    currentUser = user();
    anchorParam = null;
    collection = [];
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'stylist', children: [] }]),
        { provide: AuthService, useValue: { currentUser: () => currentUser } },
        {
          // The key is honoured rather than ignored, for the reason
          // item-detail.page.spec.ts records: a stub answering every key the
          // same way cannot tell `anchor` from anything else, and a mutation
          // that renamed it would survive.
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: { get: (key: string) => (key === 'anchor' ? anchorParam : null) },
            },
          },
        },
        { provide: WardrobeStore, useValue: { items: () => collection } },
      ],
    });
    mock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    vi.useRealTimers();
    try {
      mock.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });

  it('opens on today and asks for that day’s forecast', async () => {
    fixture = TestBed.createComponent(StylistPage);
    fixture.detectChanges();

    const request = weatherRequest();
    expect(request.request.params.get('date')).toBe(todayInLocalTime());
    request.flush(weather());
    await fixture.whenStable();

    expect(element().querySelector<HTMLInputElement>('input[type=date]')!.value).toBe(
      todayInLocalTime(),
    );
  });

  // Absent, not null. The endpoint already defaults both to "not supplied",
  // and a key this form did not fill is a key the schema never has to read.
  it('sends only the occasion and the date when nothing else was touched', async () => {
    await render();
    await submit();

    expect(suggestRequest().request.body).toEqual({
      occasion: 'casual',
      date: todayInLocalTime(),
    });
  });

  it('sends the coat override and the notes once they are set', async () => {
    await render();
    await press('Work');
    await press('Yes');
    await type('  meeting with a client  ');
    await submit();

    expect(suggestRequest().request.body).toEqual({
      occasion: 'work',
      date: todayInLocalTime(),
      include_outerwear: true,
      notes: 'meeting with a client',
    });
  });

  it('leaves whitespace-only notes off the wire', async () => {
    await render();
    await type('   ');
    await submit();

    expect(suggestRequest().request.body).toEqual({
      occasion: 'casual',
      date: todayInLocalTime(),
    });
  });

  // The moved date is derived from the clock, never written down. The page opens
  // on todayInLocalTime() and re-forecasts only when the date actually changes,
  // so a literal here is a test that passes until the calendar reaches it —
  // this one was written five days out and went green to red on 2026-09-01.
  // setDate is calendar arithmetic on purpose: adding 86_400_000 ms lands on the
  // same local day when that day is 25 hours long.
  it('re-reads the forecast when the date moves', async () => {
    await render();

    const moved = new Date();
    moved.setDate(moved.getDate() + 1);
    const movedDate = todayInLocalTime(moved);

    const picker = element().querySelector<HTMLInputElement>('input[type=date]')!;
    picker.value = movedDate;
    picker.dispatchEvent(new Event('change'));
    await fixture.whenStable();

    const request = weatherRequest();
    expect(request.request.params.get('date')).toBe(movedDate);
    request.flush(weather({ date: movedDate, condition: 'rain' }));
    await fixture.whenStable();

    expect(text()).toContain('Rain');
  });

  // §2.8: a skeleton of the look strip, never a bare spinner — four tiles now,
  // because the strip is four columns. The form stays: DR.20 replaced the
  // three-way branch with a form that never leaves, so the wait happens under
  // the controls rather than instead of them. DECISIONS.md 220.
  it('shows the look-strip skeleton under the form while it waits', async () => {
    await render();
    await submit();

    expect(skeletonTiles()).toHaveLength(4);
    expect(form()).not.toBeNull();
    expect(status()).toBe(en['stylist.waiting.forecast']);

    suggestRequest().flush(response());
  });

  // The clock is frozen after the render, never around it: fake timers and
  // `await fixture.whenStable()` cannot both be true at once, measured at task
  // 1.7 and written up in 06-TESTING-STRATEGY.md. TestBed.tick() renders from
  // this point on. The interval starts on the far side of the switch, so it is
  // a fake timer from the moment it exists.
  it('cycles the status lines and rests on the last one', async () => {
    await render();

    vi.useFakeTimers();
    buttonWith('Style me').click();
    TestBed.tick();
    expect(status()).toBe(en['stylist.waiting.forecast']);

    vi.advanceTimersByTime(STATUS_INTERVAL_MS);
    TestBed.tick();
    expect(status()).toBe(en['stylist.waiting.wardrobe']);

    vi.advanceTimersByTime(STATUS_INTERVAL_MS);
    TestBed.tick();
    expect(status()).toBe(en['stylist.waiting.assembling']);

    // Clamped rather than wrapped: at eight seconds the forecast is long read.
    vi.advanceTimersByTime(STATUS_INTERVAL_MS * 4);
    TestBed.tick();
    expect(status()).toBe(en['stylist.waiting.assembling']);

    suggestRequest().flush(response());
    TestBed.tick();
    expect(vi.getTimerCount()).toBe(0);
  });

  // The three states this asserted the back link across are now the navigation
  // bar's, which is outside this component and outside its branch chain by
  // construction — `app.spec.ts` proves it renders and `nav-bar.spec.ts` proves
  // where it goes. What survives here is that the screen builds none of its own.
  it('carries no navigation of its own out of the stylist', async () => {
    await render();
    expect(backLink()).toBeNull();

    await submit();
    expect(backLink()).toBeNull();

    suggestRequest().flush(response());
    await fixture.whenStable();

    expect(backLink()).toBeNull();
  });

  it('renders the look it was given', async () => {
    await render();
    await submit();
    suggestRequest().flush(response());
    await fixture.whenStable();

    expect(text()).toContain('Morning meetings');
    expect(text()).toContain('A casual outfit for a warm day.');
    expect(skeletonTiles()).toHaveLength(0);
    // The form is still there, and its button has changed what it says: the
    // same press asks for another look rather than the first one.
    expect(form()).not.toBeNull();
    expect(text()).toContain(en['stylist.submit.restyle']);
    expect(text()).not.toContain(en['stylist.ready']);
  });

  // The behaviour DR.20 is for, and the one a later tidy of this template could
  // silently undo: a field changed under a look does not invalidate it. Nothing
  // is re-requested until the button is pressed, so the look on screen is the
  // one that was asked for and not a stale render of a newer draft.
  it('keeps the look on screen when the draft changes underneath it', async () => {
    await render();
    await submit();
    suggestRequest().flush(response());
    await fixture.whenStable();

    await press('Evening');
    await type('dinner, walking there');

    mock.expectNone(`${environment.apiUrl}/looks/suggest`);
    expect(text()).toContain('Morning meetings');
  });

  // "Try again" clears the look rather than re-firing the last request: the
  // draft is on screen above it and the reroll a user wants is usually the one
  // with the notes changed. The form never left, so what comes back is the
  // waiting line — nothing is re-mounted. reset() clears the forecast along
  // with the look, so the date is re-asked for; an unanswered request here
  // would fail verify(). DECISIONS.md 220.
  it('clears the look and rests on the waiting line when another is asked for', async () => {
    await render();
    await submit();
    suggestRequest().flush(response());
    await fixture.whenStable();

    await press(en['stylist.look.tryAgain']);
    weatherRequest().flush(weather());
    await fixture.whenStable();

    expect(form()).not.toBeNull();
    expect(text()).not.toContain('Morning meetings');
    expect(text()).toContain(en['stylist.ready']);
    expect(text()).toContain(en['stylist.submit']);
  });

  it('says what went wrong and brings the form back', async () => {
    await render();
    await submit();
    suggestRequest().flush(
      { code: 'wardrobe_too_small' },
      { status: 400, statusText: 'Bad Request' },
    );
    await fixture.whenStable();

    expect(text()).toContain(en['stylist.error.wardrobeTooSmall']);
    expect(form()).not.toBeNull();
  });

  // The draft lives on the page rather than in the form for exactly this: the
  // form is unmounted while the skeleton is up, and state held inside it would
  // take the user's notes down every time the endpoint refused a request.
  it('keeps what was typed when the request is refused', async () => {
    await render();
    await press('Evening');
    await type('dinner, walking there');
    await submit();
    suggestRequest().flush({ code: 'stylist_failed' }, { status: 502, statusText: 'Bad Gateway' });
    await fixture.whenStable();

    expect(element().querySelector<HTMLTextAreaElement>('textarea')!.value).toBe(
      'dinner, walking there',
    );
    expect(buttonWith('Evening').getAttribute('aria-pressed')).toBe('true');
  });

  it('prints no forecast line when the account has no home location', async () => {
    currentUser = user({ home_city: null, home_lat: null, home_lon: null });
    fixture = TestBed.createComponent(StylistPage);
    fixture.detectChanges();
    await fixture.whenStable();

    mock.expectNone((candidate) => candidate.url === `${environment.apiUrl}/weather`);
    expect(text()).not.toContain('°');
    expect(form()).not.toBeNull();
  });

  // --- the anchor, task 2.10 ------------------------------------------------

  it('pins the anchored garment from the collection without a request', async () => {
    anchorParam = 'item-1';
    collection = [item()];
    await render();

    mock.expectNone(`${environment.apiUrl}/items/item-1`);
    expect(anchorPin()).toBe('Building around: light blue mom jeans');
  });

  it('fetches the anchored garment when the collection has none', async () => {
    // The deep-link case: /stylist has no wardrobe screen behind it, so the
    // store is empty on a cold arrival and the row has to be asked for.
    anchorParam = 'item-9';
    await render();
    mock.expectOne(`${environment.apiUrl}/items/item-9`).flush(item({ id: 'item-9' }));
    await fixture.whenStable();

    expect(anchorPin()).toBe('Building around: light blue mom jeans');
  });

  it('names an anchored garment that has no name', async () => {
    anchorParam = 'item-1';
    collection = [item({ display_name: null })];
    await render();

    expect(anchorPin()).toBe('Building around: Untitled item');
  });

  it('sends the anchor as the row’s UUID', async () => {
    anchorParam = 'item-1';
    collection = [item()];
    await render();
    await submit();

    expect(suggestRequest().request.body).toEqual({
      occasion: 'casual',
      date: todayInLocalTime(),
      anchor_item_id: 'item-1',
    });
  });

  it('drops an anchor it cannot fetch rather than sending it', async () => {
    // An id this client cannot name is one it must not send: the pin would have
    // nothing to show and the endpoint would answer `anchor_unavailable`.
    anchorParam = 'gone';
    await render();
    mock
      .expectOne(`${environment.apiUrl}/items/gone`)
      .flush({ code: 'not_found' }, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    await submit();

    expect(anchorPin()).toBeNull();
    expect(suggestRequest().request.body).not.toHaveProperty('anchor_item_id');
  });

  it('clears the anchor and the query parameter on ×', async () => {
    anchorParam = 'item-1';
    collection = [item()];
    await render();

    clearAnchorButton()!.click();
    await fixture.whenStable();
    await submit();

    expect(anchorPin()).toBeNull();
    expect(router.url).toBe('/stylist');
    expect(suggestRequest().request.body).not.toHaveProperty('anchor_item_id');
  });

  it('sends no anchor and asks for no item when there is no parameter', async () => {
    await render();
    await submit();

    mock.expectNone((candidate) => candidate.url.includes('/items/'));
    expect(anchorPin()).toBeNull();
    expect(suggestRequest().request.body).not.toHaveProperty('anchor_item_id');
  });

  it('says so when the endpoint refuses the anchor', async () => {
    anchorParam = 'item-1';
    collection = [item()];
    await render();
    await submit();
    suggestRequest().flush(
      { code: 'anchor_unavailable' },
      { status: 422, statusText: 'Unprocessable Content' },
    );
    await fixture.whenStable();

    expect(text()).toContain(en['stylist.error.anchorUnavailable']);
  });

  // --- the swap, task 2.11 --------------------------------------------------

  it('locks the other items, names the role and rejects the one that was tapped', async () => {
    await render();
    await submit();
    suggestRequest().flush(lookOf([SHOES, SHIRT, JEANS]));
    await fixture.whenStable();

    await tapSwap('loafers');

    expect(suggestRequest().request.body).toEqual({
      occasion: 'casual',
      date: todayInLocalTime(),
      locked_item_ids: ['item-top', 'item-jeans'],
      replace_role: 'shoes',
      exclude_item_ids: ['item-shoes'],
    });
  });

  // The anchor is dropped on purpose: every garment it was protecting is
  // locked here anyway, and on the anchored tile itself rule 7 would require
  // the item that rule 8 forbids — a 502 by construction.
  it('sends no anchor on a swap, even when the look was anchored', async () => {
    anchorParam = 'item-top';
    collection = [SHIRT];
    await render();
    await submit();

    const anchored = suggestRequest();
    expect(anchored.request.body).toHaveProperty('anchor_item_id', 'item-top');
    anchored.flush(lookOf([SHOES, SHIRT, JEANS]));
    await fixture.whenStable();

    await tapSwap('loafers');

    expect(suggestRequest().request.body).not.toHaveProperty('anchor_item_id');
  });

  it('accumulates the rejected items across repeated swaps', async () => {
    await render();
    await submit();
    suggestRequest().flush(lookOf([SHOES, SHIRT, JEANS]));
    await fixture.whenStable();

    await tapSwap('loafers');
    const heels = item({
      id: 'item-heels',
      category: 'shoes',
      layer: 'standalone',
      display_name: 'heels',
    });
    suggestRequest().flush(lookOf([heels, SHIRT, JEANS]));
    await fixture.whenStable();

    await tapSwap('heels');

    // 05-FRONTEND-SPEC.md says the rejected item is *added* to the list, so a
    // second tap cannot be answered with the shoe the first one turned down.
    expect(suggestRequest().request.body).toHaveProperty('exclude_item_ids', [
      'item-shoes',
      'item-heels',
    ]);
  });

  it('keeps the look on screen and says so when a swap fails', async () => {
    await render();
    await submit();
    suggestRequest().flush(lookOf([SHOES, SHIRT, JEANS]));
    await fixture.whenStable();

    await tapSwap('loafers');
    suggestRequest().flush(
      { code: 'locked_unavailable' },
      { status: 422, statusText: 'Unprocessable Content' },
    );
    await fixture.whenStable();

    expect(text()).toContain(en['stylist.error.lockedUnavailable']);
    // The look is still there, badge and all: nothing changed, so nothing on
    // screen should have.
    expect(swapBadge('loafers')).not.toBeNull();
    expect(form()).not.toBeNull();
  });

  it('forgets the exclusions when the user starts over', async () => {
    await render();
    await submit();
    suggestRequest().flush(lookOf([SHOES, SHIRT, JEANS]));
    await fixture.whenStable();

    await tapSwap('loafers');
    suggestRequest().flush(lookOf([SHOES, SHIRT, JEANS]));
    await fixture.whenStable();

    await press(en['stylist.look.tryAgain']);
    weatherRequest().flush(weather());
    await submit();

    expect(suggestRequest().request.body).not.toHaveProperty('exclude_item_ids');
  });

  // The heart on the stylist screen. It is the same button look-card.spec.ts
  // covers; what is measured here is the wiring the card cannot see — which
  // store it reaches, and how the card learns the row changed.
  describe('saving the look on screen', () => {
    function heart(): HTMLButtonElement {
      return element().querySelector<HTMLButtonElement>(
        `button[aria-label="${en['stylist.look.save']}"]`,
      )!;
    }

    async function suggested(): Promise<void> {
      buttonWith(en['stylist.submit']).click();
      suggestRequest().flush(response());
      await fixture.whenStable();
    }

    it('patches the look it was shown', async () => {
      await render();
      await suggested();

      heart().click();

      const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
      expect(request.request.method).toBe('PATCH');
      expect(request.request.body).toEqual({ is_saved: true });
      request.flush({ ...response().looks[0], is_saved: true });
    });

    it('fills the heart in from the response and not from the tap', async () => {
      // StylistStore still holds is_saved: false — the suggest response is
      // never rewritten. The card shows the PATCH answer because the page
      // prefers the newer of the two by id, which is the whole of that
      // computed. Without it the heart would empty again on the next render.
      await render();
      await suggested();

      heart().click();
      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ ...response().looks[0], is_saved: true });
      await fixture.whenStable();

      expect(heart().getAttribute('aria-pressed')).toBe('true');
    });

    it('unsaves on a second tap', async () => {
      await render();
      await suggested();

      heart().click();
      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ ...response().looks[0], is_saved: true });
      await fixture.whenStable();

      heart().click();
      const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
      expect(request.request.body).toEqual({ is_saved: false });
      request.flush({ ...response().looks[0], is_saved: false });
    });

    it("does not carry the previous look's saved state onto the next one", async () => {
      // `updated` is matched by id, so a second suggestion — a different row —
      // must not inherit the first one's filled heart.
      await render();
      await suggested();
      heart().click();
      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ ...response().looks[0], is_saved: true });
      await fixture.whenStable();

      await press(en['stylist.look.tryAgain']);
      weatherRequest().flush(weather());
      await fixture.whenStable();
      buttonWith(en['stylist.submit']).click();
      const second = response();
      suggestRequest().flush({
        ...second,
        looks: [{ ...second.looks[0], id: 'look-2' }],
      });
      await fixture.whenStable();

      expect(heart().getAttribute('aria-pressed')).toBe('false');
    });
  });

  // The thumbs on the stylist screen. look-card.spec.ts covers the buttons;
  // what is measured here is the wiring — that the page reaches LooksStore
  // with the value the card decided, and that the optimistic render lands on
  // a card whose look lives in the *other* store.
  describe('rating the look on screen', () => {
    function thumb(direction: 'Up' | 'Down'): HTMLButtonElement {
      const label = en[`stylist.look.thumb${direction}` as keyof typeof en];
      return element().querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;
    }

    async function suggested(): Promise<void> {
      buttonWith(en['stylist.submit']).click();
      suggestRequest().flush(response());
      await fixture.whenStable();
    }

    it('patches the look with the rating', async () => {
      await render();
      await suggested();

      thumb('Up').click();

      const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
      expect(request.request.method).toBe('PATCH');
      expect(request.request.body).toEqual({ feedback: 1 });
      request.flush({ ...response().looks[0], feedback: 1 });
    });

    it('marks the thumb before the server answers', async () => {
      // The optimistic half, on the screen where it is hardest: the look comes
      // from StylistStore, which is never rewritten, so this only works
      // because the page prefers LooksStore's copy by id.
      await render();
      await suggested();

      thumb('Up').click();
      await fixture.whenStable();

      expect(thumb('Up').getAttribute('aria-pressed')).toBe('true');

      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ ...response().looks[0], feedback: 1 });
    });

    it('withdraws the rating when the same thumb is pressed again', async () => {
      await render();
      await suggested();

      thumb('Up').click();
      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ ...response().looks[0], feedback: 1 });
      await fixture.whenStable();

      thumb('Up').click();
      const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
      expect(request.request.body).toEqual({ feedback: null });
      request.flush({ ...response().looks[0], feedback: null });
    });

    it('puts the thumb back when the write fails', async () => {
      await render();
      await suggested();

      thumb('Down').click();
      await fixture.whenStable();
      expect(thumb('Down').getAttribute('aria-pressed')).toBe('true');

      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(thumb('Down').getAttribute('aria-pressed')).toBe('false');
      expect(text()).toContain(en['looks.error.general']);
    });

    it('says so when a save fails, which it did not until this task', async () => {
      // The heart shipped at 3.2 with its failure invisible on this screen:
      // the error line read StylistStore alone, so a failed tap rolled the
      // control back and explained nothing. Found by the rating rollback test
      // above and fixed for both controls at once.
      await render();
      await suggested();

      element()
        .querySelector<HTMLButtonElement>(`button[aria-label="${en['stylist.look.save']}"]`)!
        .click();
      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(text()).toContain(en['looks.error.general']);
    });

    it('rates and saves the same look independently', async () => {
      // Two fields, two requests, and neither body carries the other's key —
      // `exclude_unset` on the server is what makes that a field left alone
      // rather than a field overwritten.
      await render();
      await suggested();

      thumb('Up').click();
      mock
        .expectOne(`${environment.apiUrl}/looks/look-1`)
        .flush({ ...response().looks[0], feedback: 1 });
      await fixture.whenStable();

      element()
        .querySelector<HTMLButtonElement>(`button[aria-label="${en['stylist.look.save']}"]`)!
        .click();

      const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
      expect(request.request.body).toEqual({ is_saved: true });
      request.flush({ ...response().looks[0], feedback: 1, is_saved: true });
      await fixture.whenStable();

      expect(thumb('Up').getAttribute('aria-pressed')).toBe('true');
    });
  });
});

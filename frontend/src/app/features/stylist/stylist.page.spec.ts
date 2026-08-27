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

  it('re-reads the forecast when the date moves', async () => {
    await render();

    const picker = element().querySelector<HTMLInputElement>('input[type=date]')!;
    picker.value = '2026-09-01';
    picker.dispatchEvent(new Event('change'));
    await fixture.whenStable();

    const request = weatherRequest();
    expect(request.request.params.get('date')).toBe('2026-09-01');
    request.flush(weather({ date: '2026-09-01', condition: 'rain' }));
    await fixture.whenStable();

    expect(text()).toContain('Rain');
  });

  // §2.8: a skeleton of the look card, never a bare spinner. The form goes
  // while it is up — 05-FRONTEND-SPEC.md's "submitting swaps the form".
  it('shows the look-card skeleton instead of the form while it waits', async () => {
    await render();
    await submit();

    expect(skeletonTiles()).toHaveLength(5);
    expect(form()).toBeNull();
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

  it('renders the look it was given', async () => {
    await render();
    await submit();
    suggestRequest().flush(response());
    await fixture.whenStable();

    expect(text()).toContain('Morning meetings');
    expect(text()).toContain('A casual outfit for a warm day.');
    expect(skeletonTiles()).toHaveLength(0);
    expect(form()).toBeNull();
  });

  // The card's "Try again" hands the form back rather than re-firing the last
  // request, so the forecast has to be asked for again — reset() clears it
  // along with the look, and an unanswered request here would fail verify().
  it('brings the form back when another look is asked for', async () => {
    await render();
    await submit();
    suggestRequest().flush(response());
    await fixture.whenStable();

    await press(en['stylist.look.tryAgain']);
    weatherRequest().flush(weather());
    await fixture.whenStable();

    expect(form()).not.toBeNull();
    expect(text()).not.toContain('Morning meetings');
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
    expect(text()).not.toContain('°C');
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
});

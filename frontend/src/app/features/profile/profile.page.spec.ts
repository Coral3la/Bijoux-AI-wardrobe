import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { LocationResult } from '../../shared/models/location.model';
import { User } from '../../shared/models/user.model';
import { MAX_HEIGHT_CM, ProfilePage, SEARCH_DEBOUNCE_MS } from './profile.page';

let fixture: ComponentFixture<ProfilePage>;
let mock: HttpTestingController;
let currentUser: User | null;
let accepted: User[];
let signedOut: boolean;
let router: Router;

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
    home_city: null,
    home_lat: null,
    home_lon: null,
    created_at: '2026-08-01T09:00:00Z',
    ...overrides,
  };
}

function berlin(overrides: Partial<LocationResult> = {}): LocationResult {
  return { name: 'Berlin', country: 'Germany', lat: 52.52437, lon: 13.41053, ...overrides };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function field(id: string): HTMLInputElement {
  return element().querySelector<HTMLInputElement>(`#${id}`)!;
}

function control(label: string): HTMLButtonElement {
  return [...element().querySelectorAll('button')].find(
    (candidate) => candidate.textContent?.trim() === label,
  )!;
}

function results(): string[] {
  return [...element().querySelectorAll('li button')].map(
    (candidate) => candidate.textContent?.trim() ?? '',
  );
}

function searchRequest(q: string) {
  return mock.expectOne(
    (candidate) =>
      candidate.url === `${environment.apiUrl}/me/locations/search` &&
      candidate.params.get('q') === q,
  );
}

function patchRequest() {
  return mock.expectOne(`${environment.apiUrl}/me`);
}

// Real timers to get the component on screen, fake timers from that point on —
// wardrobe.page.spec.ts measured the alternative at task 1.7 and recorded it:
// under a frozen clock Angular's zoneless scheduler never gets a task, so
// `whenStable()` stays pending and every test dies on the 5s timeout. The
// city search is a `setTimeout` rather than an rxjs pipeline (CONVENTIONS.md
// keeps observables at the HTTP boundary), so the debounce has to be advanced,
// and everything after the render is synchronous with `TestBed.tick()`.
async function render(): Promise<void> {
  fixture = TestBed.createComponent(ProfilePage);
  fixture.detectChanges();
  await fixture.whenStable();
  vi.useFakeTimers();
}

function typeInto(id: string, value: string): void {
  const input = field(id);
  input.value = value;
  input.dispatchEvent(new Event('input'));
  TestBed.tick();
}

function searchFor(value: string): void {
  typeInto('home_query', value);
  vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
  TestBed.tick();
}

function press(selector: string): void {
  element().querySelector<HTMLButtonElement>(selector)!.click();
  TestBed.tick();
}

function save(): void {
  press('button[type=submit]');
}

describe('ProfilePage', () => {
  beforeEach(async () => {
    currentUser = user();
    accepted = [];
    signedOut = false;
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'login', children: [] },
        ]),
        {
          provide: AuthService,
          useValue: {
            currentUser: () => currentUser,
            acceptProfile: (value: User) => accepted.push(value),
            logout: () => {
              signedOut = true;
            },
          },
        },
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

  it('seeds from the session rather than asking for the profile', async () => {
    // There is no `GET /me`. The profile the browser holds arrived as
    // `GET /auth/me` at bootstrap, so this screen must not request one.
    currentUser = user({ height_cm: 165, size_top: 'M', style_notes: 'no crop tops' });
    await render();

    mock.expectNone((candidate) => candidate.url === `${environment.apiUrl}/me`);
    expect(field('display_name').value).toBe('Coral');
    expect(field('height_cm').value).toBe('165');
    expect(field('size_top').value).toBe('M');
    expect(element().querySelector<HTMLTextAreaElement>('#style_notes')!.value).toBe(
      'no crop tops',
    );
  });

  // Rendered from the session like every other field, and read-only: there is
  // no email on `PATCH /me`.
  it('shows the address the session is signed in as', async () => {
    currentUser = user({ email: 'her@example.com' });
    await render();

    expect(text()).toContain('her@example.com');
  });

  // Real timers, unlike every other test here: the sign-out navigates, and
  // `whenStable()` never settles under a frozen clock.
  it('ends the session and returns to the login screen', async () => {
    fixture = TestBed.createComponent(ProfilePage);
    fixture.detectChanges();
    await fixture.whenStable();

    control(en['profile.signOut']).click();
    await fixture.whenStable();

    expect(signedOut).toBe(true);
    expect(router.url).toBe('/login');
  });

  it('shows a stored home city instead of the search box', async () => {
    currentUser = user({ home_city: 'Tel Aviv', home_lat: 32.08, home_lon: 34.78 });
    await render();

    expect(text()).toContain('Tel Aviv');
    expect(element().querySelector('#home_query')).toBeNull();
  });

  it('sends every field, with the home trio together', async () => {
    await render();
    typeInto('display_name', 'Coral L');
    typeInto('height_cm', '165');
    typeInto('size_shoe', '38');
    searchFor('berlin');
    searchRequest('berlin').flush({ results: [berlin()] });
    TestBed.tick();

    press('li button');
    save();

    expect(patchRequest().request.body).toEqual({
      display_name: 'Coral L',
      height_cm: 165,
      size_top: null,
      size_bottom: null,
      size_shoe: '38',
      style_notes: null,
      home_city: 'Berlin',
      home_lat: 52.52437,
      home_lon: 13.41053,
    });
  });

  it('clears the home city as three nulls', async () => {
    // The three columns are cleared together or not at all — two of the three
    // is a 422. DECISIONS.md 151.
    currentUser = user({ home_city: 'Tel Aviv', home_lat: 32.08, home_lon: 34.78 });
    await render();

    press(`button[aria-label="${en['profile.home.changeLabel']}"]`);
    save();

    const body = patchRequest().request.body as Record<string, unknown>;
    expect([body['home_city'], body['home_lat'], body['home_lon']]).toEqual([null, null, null]);
  });

  it('refreshes the session so the stylist sees the new coordinates', async () => {
    await render();
    save();
    const saved = user({ home_city: 'Berlin', home_lat: 52.52437, home_lon: 13.41053 });
    patchRequest().flush(saved);
    TestBed.tick();

    expect(accepted).toEqual([saved]);
    expect(text()).toContain(en['profile.saved']);
  });

  it('says so when the save is refused', async () => {
    await render();
    save();
    patchRequest().flush(
      { code: 'validation_error' },
      { status: 422, statusText: 'Unprocessable Content' },
    );
    TestBed.tick();

    expect(text()).toContain(en['profile.error.save']);
    expect(accepted).toEqual([]);
  });

  it('refuses a height outside the documented bounds without spending a request', async () => {
    await render();
    typeInto('height_cm', String(MAX_HEIGHT_CM + 1));

    expect(text()).toContain('Height must be between 120 and 230 cm.');

    save();
    mock.expectNone(`${environment.apiUrl}/me`);
  });

  it('waits for the debounce and asks once', async () => {
    await render();
    typeInto('home_query', 'ber');
    typeInto('home_query', 'berlin');
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    TestBed.tick();

    searchRequest('berlin').flush({ results: [berlin(), berlin({ country: 'United States' })] });
    TestBed.tick();

    expect(results()).toEqual(['Berlin, Germany', 'Berlin, United States']);
  });

  it('asks for nothing under two characters', async () => {
    // The provider's own floor: one character matches nothing, so a request
    // spent finding that out is a 422.
    await render();
    searchFor('b');

    mock.expectNone((candidate) => candidate.url.includes('/locations/search'));
  });

  it('drops an answer the user has already typed past', async () => {
    await render();
    searchFor('ber');
    const stale = searchRequest('ber');

    searchFor('berlin');
    searchRequest('berlin').flush({ results: [berlin()] });
    TestBed.tick();

    stale.flush({ results: [berlin({ name: 'Bergamo', country: 'Italy' })] });
    TestBed.tick();

    expect(results()).toEqual(['Berlin, Germany']);
  });

  it('says so when the geocoder is unavailable', async () => {
    await render();
    searchFor('berlin');
    searchRequest('berlin').flush(
      { code: 'geocoding_unavailable' },
      { status: 502, statusText: 'Bad Gateway' },
    );
    TestBed.tick();

    expect(text()).toContain(en['profile.home.error']);
    expect(results()).toEqual([]);
  });

  it('says so when nothing matches', async () => {
    await render();
    searchFor('zzzz');
    searchRequest('zzzz').flush({ results: [] });
    TestBed.tick();

    expect(text()).toContain(en['profile.home.noResults']);
  });
});

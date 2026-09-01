import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { User } from '../../shared/models/user.model';
import { Weather } from '../../shared/models/weather.model';
import { WeatherStrip } from './weather-strip';

let fixture: ComponentFixture<WeatherStrip>;
let mock: HttpTestingController;
let currentUser: User | null;

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
    date: '2026-08-28',
    temp_min_c: 24,
    temp_max_c: 30.4,
    precip_mm: 0,
    wind_kph: 12,
    condition: 'clear',
    rule: 'Use warmth 1-2 only.',
    ...overrides,
  };
}

function weatherRequest() {
  return mock.expectOne((candidate) => candidate.url === `${environment.apiUrl}/weather`);
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function sentence(): HTMLElement | null {
  return element().querySelector('app-authored-line');
}

function href(label: string): string | null {
  const link = [...element().querySelectorAll('a')].find(
    (candidate) => candidate.textContent?.trim() === label,
  );
  return link?.getAttribute('href') ?? null;
}

async function render(): Promise<void> {
  fixture = TestBed.createComponent(WeatherStrip);
  await fixture.whenStable();
}

describe('WeatherStrip', () => {
  beforeEach(async () => {
    currentUser = user();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'stylist', children: [] },
          { path: 'profile', children: [] },
        ]),
        { provide: AuthService, useValue: { currentUser: () => currentUser } },
      ],
    });
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    try {
      mock.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });

  it('asks for today at the home coordinates and prints the day’s high', async () => {
    await render();

    const request = weatherRequest();
    expect(request.request.params.get('lat')).toBe('32.08');
    expect(request.request.params.get('lon')).toBe('34.78');
    // Today in local time, never UTC — the same rule the stylist's date picker
    // opens on, from the same function.
    const today = new Date();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    expect(request.request.params.get('date')).toBe(`${today.getFullYear()}-${month}-${day}`);

    request.flush(weather());
    await fixture.whenStable();

    // 30.4 rounds to 30: the day's high, which is the number `summarize_forecast`
    // already prints to the model. DECISIONS.md 142. The unit went with the card
    // at the Atelier pass — one city, one reading a day, so "· 30°" is not
    // ambiguous — and this asserts the degree sign rather than the C for that
    // reason. DECISIONS.md 219.
    expect(text()).toContain('· 30°');
    // The whole sentence rather than the three fragments this asserted before
    // DR.12. Fragments survived the rewrite from two keys to one untouched —
    // '30°C', 'Clear' and 'Tel Aviv' are all still on screen either way — so
    // they were pinning the words and not the sentence. DECISIONS.md 218.
    expect(sentence()?.textContent).toBe('Clear in Tel Aviv today');
  });

  // The sentence is ours and the city is not, so the city alone leaves the
  // prose face. This is the assertion that makes the strip a caller of 213
  // rather than a component with a string in it, and it is the one a later
  // "tidy the spans" edit could silently undo. DECISIONS.md 218.
  it('renders the city, and only the city, in the content face', async () => {
    await render();
    weatherRequest().flush(weather());
    await fixture.whenStable();

    const faced = [...(sentence()?.querySelectorAll('span.font-sans') ?? [])];
    expect(faced.map((span) => span.textContent)).toEqual(['Tel Aviv']);
  });

  // §2.12: the strip carries the only entry point into /stylist, so it is the
  // one thing on this component that no state may remove.
  it('links into the stylist with a forecast, without one, and without an account', async () => {
    // Three components in one module rather than three test cases: the state
    // is read at construction, so a second fixture is the whole of the setup,
    // and the assertion is the same sentence three times.
    await render();
    weatherRequest().flush(weather());
    await fixture.whenStable();
    expect(href(en['wardrobe.weather.styleMe'])).toBe('/stylist');

    currentUser = user({ home_city: null, home_lat: null, home_lon: null });
    await render();
    expect(href(en['wardrobe.weather.styleMe'])).toBe('/stylist');

    currentUser = null;
    await render();
    expect(href(en['wardrobe.weather.styleMe'])).toBe('/stylist');
  });

  // The degraded state: no coordinates means no request at all — the three home
  // columns are one field (DECISIONS.md 151) — and the temperature is replaced
  // by the way to set one.
  it('asks for no forecast and points at the profile when there is no home city', async () => {
    currentUser = user({ home_city: null, home_lat: null, home_lon: null });

    await render();

    mock.expectNone((candidate) => candidate.url === `${environment.apiUrl}/weather`);
    expect(href(en['wardrobe.weather.setHome'])).toBe('/profile');
    expect(text()).not.toContain('°');
  });

  // Silent on purpose. The forecast is context on a screen that works without
  // it, and the account already has a home city — the prompt to set one would
  // be the wrong sentence about a request that failed.
  it('says nothing when the forecast fails, and keeps the strip', async () => {
    await render();

    weatherRequest().flush(
      { code: 'forecast_unavailable' },
      { status: 502, statusText: 'Bad Gateway' },
    );
    await fixture.whenStable();

    expect(text()).not.toContain('°');
    expect(text()).not.toContain(en['wardrobe.weather.setHome']);
    expect(href(en['wardrobe.weather.styleMe'])).toBe('/stylist');
  });
});

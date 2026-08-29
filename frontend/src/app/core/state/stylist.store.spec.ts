import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { SuggestResponse } from '../../shared/models/look.model';
import { User } from '../../shared/models/user.model';
import { Weather } from '../../shared/models/weather.model';
import { AuthService } from '../auth/auth.service';
import { StylistStore } from './stylist.store';

let store: StylistStore;
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
    date: '2026-08-27',
    temp_min_c: 24,
    temp_max_c: 31,
    precip_mm: 0,
    wind_kph: 12,
    condition: 'clear',
    rule: 'Use warmth 1-2 only.',
    ...overrides,
  };
}

function response(overrides: Partial<SuggestResponse> = {}): SuggestResponse {
  return {
    looks: [
      {
        id: 'look-1',
        occasion: 'work',
        title: 'Morning meetings',
        items: [],
        reasoning: 'The blazer lifts the knit without making it formal.',
        weather_note: 'Mild at 19°C.',
        is_saved: false,
      },
    ],
    missing_pieces: [],
    message: 'A work outfit for a mild day.',
    ...overrides,
  };
}

function weatherRequest() {
  return mock.expectOne((candidate) => candidate.url === `${environment.apiUrl}/weather`);
}

function suggestRequest() {
  return mock.expectOne(`${environment.apiUrl}/looks/suggest`);
}

function suggest(): void {
  store.suggest({ occasion: 'work', date: '2026-08-27' });
}

// The endpoint's failures as 04-API-SPEC.md documents them, status and code
// together. The status is carried so the pairs stay legible, not because the
// reader uses it — `forecast_unavailable` appears at both of its statuses here
// precisely to pin that it maps to one message either way. DECISIONS.md 147.
const DOCUMENTED_FAILURES: readonly [number, string, string][] = [
  [400, 'wardrobe_too_small', 'stylist.error.wardrobeTooSmall'],
  [400, 'home_location_missing', 'stylist.error.homeLocationMissing'],
  [400, 'forecast_unavailable', 'stylist.error.forecastUnavailable'],
  [502, 'forecast_unavailable', 'stylist.error.forecastUnavailable'],
  [502, 'stylist_failed', 'stylist.error.stylistFailed'],
  [422, 'validation_error', 'stylist.error.validation'],
  [422, 'anchor_unavailable', 'stylist.error.anchorUnavailable'],
  [422, 'locked_unavailable', 'stylist.error.lockedUnavailable'],
];

describe('StylistStore', () => {
  beforeEach(() => {
    currentUser = user();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { currentUser: () => currentUser } },
      ],
    });
    mock = TestBed.inject(HttpTestingController);
    store = TestBed.inject(StylistStore);
  });

  afterEach(() => {
    try {
      mock.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });

  describe('loadWeather', () => {
    it('asks for the home coordinates and the requested date', () => {
      store.loadWeather('2026-08-27');

      const request = weatherRequest();
      expect(request.request.params.get('lat')).toBe('32.08');
      expect(request.request.params.get('lon')).toBe('34.78');
      expect(request.request.params.get('date')).toBe('2026-08-27');

      request.flush(weather());
      expect(store.weather()?.condition).toBe('clear');
    });

    // The three home columns are one field (DECISIONS.md 151), so half of it
    // is the same as none of it: no request leaves at all.
    it('makes no request when the account has no home location', () => {
      currentUser = user({ home_lat: null, home_lon: null });
      store.loadWeather('2026-08-27');

      mock.expectNone((candidate) => candidate.url === `${environment.apiUrl}/weather`);
      expect(store.weather()).toBeNull();
    });

    // The forecast is context, not the answer. A failure here must not put a
    // message on a form that still works — the suggest request is where the
    // user finds out, at the moment they have asked for something.
    it('stays silent when the forecast fails', () => {
      store.loadWeather('2026-08-27');
      weatherRequest().flush(
        { code: 'forecast_unavailable' },
        { status: 502, statusText: 'Bad Gateway' },
      );

      expect(store.weather()).toBeNull();
      expect(store.error()).toBeNull();
    });
  });

  describe('suggest', () => {
    it('holds the look the endpoint answered with', () => {
      suggest();
      expect(store.isSuggesting()).toBe(true);

      suggestRequest().flush(response());

      expect(store.isSuggesting()).toBe(false);
      expect(store.error()).toBeNull();
      expect(store.result()?.looks[0].title).toBe('Morning meetings');
    });

    it.each(DOCUMENTED_FAILURES)('says its own thing about %i %s', (status, code, key) => {
      suggest();
      suggestRequest().flush({ code }, { status, statusText: 'Error' });

      expect(store.error()).toBe(key);
      expect(store.isSuggesting()).toBe(false);
    });

    // A body the request schema rejects is FastAPI's own 422 and carries
    // `detail`, not `code`. Without the status fallback this lands on the
    // general message, which says nothing about a request that was malformed.
    it('reads a schema rejection that carries no code', () => {
      suggest();
      suggestRequest().flush(
        { detail: [{ loc: ['body', 'occasion'], msg: 'unexpected value' }] },
        { status: 422, statusText: 'Unprocessable Entity' },
      );

      expect(store.error()).toBe('stylist.error.validation');
    });

    it('falls back on a code it has never heard of', () => {
      suggest();
      suggestRequest().flush({ code: 'teapot' }, { status: 418, statusText: "I'm a teapot" });

      expect(store.error()).toBe('stylist.error.general');
    });

    it('falls back when the request never reaches the server', () => {
      suggest();
      suggestRequest().error(new ProgressEvent('error'));

      expect(store.error()).toBe('stylist.error.general');
    });

    // The skeleton replaces the look while the second request is in flight, so
    // a failure must not leave the first look underneath a message about it.
    it('clears the previous look before re-requesting', () => {
      suggest();
      suggestRequest().flush(response());
      expect(store.result()).not.toBeNull();

      suggest();
      expect(store.result()).toBeNull();

      suggestRequest().flush(
        { code: 'stylist_failed' },
        { status: 502, statusText: 'Bad Gateway' },
      );
      expect(store.result()).toBeNull();
      expect(store.error()).toBe('stylist.error.stylistFailed');
    });

    it('drops a second request while one is in flight', () => {
      suggest();
      suggest();

      suggestRequest().flush(response());
    });
  });

  describe('swap', () => {
    function swap(itemId = 'item-1'): void {
      store.swap(
        {
          occasion: 'work',
          date: '2026-08-27',
          locked_item_ids: ['item-2', 'item-3'],
          replace_role: 'shoes',
          exclude_item_ids: [itemId],
        },
        itemId,
      );
    }

    // The whole difference from `suggest`, and the reason there are two
    // methods: 05-FRONTEND-SPEC.md wants the spinner on one tile and the rest
    // of the card left standing, and the page renders the skeleton over
    // `isSuggesting` and the card over `result`.
    it('keeps the look on screen and names the tile being replaced', () => {
      suggest();
      suggestRequest().flush(response());

      swap();

      expect(store.result()).not.toBeNull();
      expect(store.isSuggesting()).toBe(false);
      expect(store.swappingItemId()).toBe('item-1');

      suggestRequest().flush(response({ message: 'Different shoes.' }));

      expect(store.swappingItemId()).toBeNull();
      expect(store.result()?.message).toBe('Different shoes.');
    });

    it('sends the locks, the role and the exclusion', () => {
      swap();

      expect(suggestRequest().request.body).toEqual({
        occasion: 'work',
        date: '2026-08-27',
        locked_item_ids: ['item-2', 'item-3'],
        replace_role: 'shoes',
        exclude_item_ids: ['item-1'],
      });
    });

    // A failed swap changed nothing, so the look the user still wants is the
    // one already on screen — the opposite of `suggest`, which clears it.
    it('leaves the previous look standing when the swap fails', () => {
      suggest();
      suggestRequest().flush(response());

      swap();
      suggestRequest().flush(
        { code: 'locked_unavailable' },
        { status: 422, statusText: 'Unprocessable Content' },
      );

      expect(store.result()).not.toBeNull();
      expect(store.swappingItemId()).toBeNull();
      expect(store.error()).toBe('stylist.error.lockedUnavailable');
    });

    it('drops a second swap while one is in flight', () => {
      swap('item-1');
      swap('item-4');

      expect(store.swappingItemId()).toBe('item-1');
      suggestRequest().flush(response());
    });
  });

  // This store is providedIn: 'root' and outlives the screen. Without the
  // reset the second visit opens on the first visit's look.
  it('forgets everything on reset', () => {
    suggest();
    suggestRequest().flush(response());
    store.loadWeather('2026-08-27');
    weatherRequest().flush(weather());

    store.reset();

    expect(store.result()).toBeNull();
    expect(store.weather()).toBeNull();
    expect(store.error()).toBeNull();
    expect(store.isSuggesting()).toBe(false);
    expect(store.swappingItemId()).toBeNull();
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { LocationResult } from '../../shared/models/location.model';
import { PackResponse, Trip } from '../../shared/models/trip.model';
import { STATUS_INTERVAL_MS } from './pack-wait';
import { SEARCH_DEBOUNCE_MS, tripHorizon } from './trip-form';
import { TripsPage } from './trips.page';

// Distinctive on purpose: the assertion that it never reaches the screen has
// to be able to fail.
const RAW_DETAIL = 'the-servers-own-sentence';

let fixture: ComponentFixture<TripsPage>;
let mock: HttpTestingController;
let router: Router;

function berlin(overrides: Partial<LocationResult> = {}): LocationResult {
  return { name: 'Berlin', country: 'Germany', lat: 52.52437, lon: 13.41053, ...overrides };
}

function trip(overrides: Partial<Trip> = {}): Trip {
  return {
    id: 'trip-1',
    destination: 'Berlin',
    dest_lat: 52.52,
    dest_lon: 13.41,
    start_date: '2026-03-14',
    end_date: '2026-03-17',
    notes: null,
    days: [],
    packing_list: {
      item_ids: ['item-1'],
      reuse_summary: { item_count: 8, look_count: 4, most_reused: { item_id: 'item-1', days: 3 } },
    },
    created_at: '2026-03-01T09:00:00Z',
    ...overrides,
  };
}

function packed(overrides: Partial<Trip> = {}): PackResponse {
  return { trip: trip(overrides), looks: [], missing_pieces: [] };
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

async function render(): Promise<void> {
  fixture = TestBed.createComponent(TripsPage);
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

function changeDate(id: string, value: string): void {
  const input = field(id);
  input.value = value;
  input.dispatchEvent(new Event('change'));
  TestBed.tick();
}

function packRequest() {
  return mock.expectOne(`${environment.apiUrl}/trips/pack`);
}

// The screen as a user reaches a sendable state: search, pick, set the range.
// `start` and `end` are relative to today, because the picker caps at the
// horizon and a fixed date would fall outside it as the suite ages.
function fillIn(options: { start?: number; end?: number } = {}): void {
  typeInto('trip_destination', 'berlin');
  vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
  TestBed.tick();
  mock
    .expectOne((candidate) => candidate.url === `${environment.apiUrl}/me/locations/search`)
    .flush({ results: [berlin()] });
  TestBed.tick();
  element().querySelector<HTMLButtonElement>('li button')!.click();
  TestBed.tick();

  changeDate('trip_start', dayFromToday(options.start ?? 1));
  changeDate('trip_end', dayFromToday(options.end ?? 4));
}

function dayFromToday(offset: number): string {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  const month = String(day.getMonth() + 1).padStart(2, '0');
  return `${day.getFullYear()}-${month}-${String(day.getDate()).padStart(2, '0')}`;
}

function submit(): void {
  element().querySelector<HTMLButtonElement>('button[type=submit]')!.click();
  TestBed.tick();
}

function failWith(code: string, status: number): void {
  packRequest().flush({ detail: RAW_DETAIL, code }, { status, statusText: 'Bad Request' });
  TestBed.tick();
}

describe('TripsPage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'trips/:id', children: [] },
        ]),
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

  it('opens on the form with today already chosen', async () => {
    await render();

    expect(field('trip_start').value).toBe(dayFromToday(0));
    expect(field('trip_end').value).toBe(dayFromToday(0));
  });

  it('asks for nothing until the form is submitted', async () => {
    await render();

    mock.expectNone((candidate) => candidate.url === `${environment.apiUrl}/trips/pack`);
  });

  it('sends the destination name, the range and one occasion per day', async () => {
    await render();
    fillIn();
    submit();

    expect(packRequest().request.body).toEqual({
      destination: 'Berlin',
      start_date: dayFromToday(1),
      end_date: dayFromToday(4),
      occasions: [
        { day: 1, slot: 'day', occasion: 'casual' },
        { day: 2, slot: 'day', occasion: 'casual' },
        { day: 3, slot: 'day', occasion: 'casual' },
        { day: 4, slot: 'day', occasion: 'casual' },
      ],
    });
  });

  // The coordinates the picker had are dropped: the endpoint takes a string and
  // geocodes it again for itself (DECISIONS.md 202), and the country is display
  // text for the chip — 153's limitation is that both Berlins send "Berlin".
  it('sends no coordinates and no country', async () => {
    await render();
    fillIn();
    submit();

    const body = packRequest().request.body as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual([
      'destination',
      'end_date',
      'occasions',
      'start_date',
    ]);
  });

  it('sends the occasions the user chose, numbered in day order', async () => {
    await render();
    fillIn({ start: 1, end: 2 });
    const rows = [...element().querySelectorAll('fieldset')];
    rows[1].querySelectorAll('button')[2].click();
    TestBed.tick();
    submit();

    expect((packRequest().request.body as { occasions: unknown }).occasions).toEqual([
      { day: 1, slot: 'day', occasion: 'casual' },
      { day: 2, slot: 'day', occasion: 'evening' },
    ]);
  });

  // Absent is what the server defaults it to, and the schema forbids extra keys
  // rather than dropping them, so a blank note must not be sent as one.
  it('omits blank notes rather than sending an empty string', async () => {
    await render();
    fillIn();
    const notes = element().querySelector<HTMLTextAreaElement>('#trip_notes')!;
    notes.value = '   ';
    notes.dispatchEvent(new Event('input'));
    TestBed.tick();
    submit();

    expect(packRequest().request.body).not.toHaveProperty('notes');
  });

  it('trims the notes it does send', async () => {
    await render();
    fillIn();
    const notes = element().querySelector<HTMLTextAreaElement>('#trip_notes')!;
    notes.value = '  one dinner out  ';
    notes.dispatchEvent(new Event('input'));
    TestBed.tick();
    submit();

    expect((packRequest().request.body as { notes: string }).notes).toBe('one dinner out');
  });

  it('replaces the form with a status line while packing', async () => {
    await render();
    fillIn();
    submit();

    expect(text()).toContain(en['trip.waiting.geocoding']);
    packRequest().flush(packed());
  });

  // This is what actually stops a double pack, rather than the guard inside
  // `pack()`: the control that would ask for a second one is not on screen.
  it('takes the form away while packing, so a second pack cannot be asked for', async () => {
    await render();
    fillIn();
    submit();

    expect(element().querySelector('form')).toBeNull();
    packRequest().flush(packed());
  });

  it('moves through the status lines as the wait goes on', async () => {
    await render();
    fillIn();
    submit();
    vi.advanceTimersByTime(STATUS_INTERVAL_MS);
    TestBed.tick();

    expect(text()).toContain(en['trip.waiting.forecast']);
    packRequest().flush(packed());
  });

  // Clamped, not wrapped: a line that comes back round claims work that is
  // behind us, and this wait has no known length.
  it('rests on the last status line rather than starting over', async () => {
    await render();
    fillIn();
    submit();
    vi.advanceTimersByTime(STATUS_INTERVAL_MS * 12);
    TestBed.tick();

    expect(text()).toContain(en['trip.waiting.assembling']);
    packRequest().flush(packed());
  });

  // 4.5's confirmation panel is gone: the counts it rendered are the packing
  // view's header line, word for word, and the sentence is written once there
  // rather than twice on two screens.
  it('navigates to the packed trip', async () => {
    await render();
    fillIn();
    submit();
    // The status cycle needs a fake clock and the router's navigation does not
    // run under one, so the wait for it is measured on the real one.
    vi.useRealTimers();
    packRequest().flush(packed());
    await fixture.whenStable();

    expect(router.url).toBe('/trips/trip-1');
  });

  // The id comes off the response and not off anything the form holds, which
  // is a distinction a fixture id equal to the destination could not make.
  it('navigates to the id the server answered with', async () => {
    await render();
    fillIn();
    submit();
    vi.useRealTimers();
    packRequest().flush(packed({ id: 'trip-42' }));
    await fixture.whenStable();

    expect(router.url).toBe('/trips/trip-42');
  });

  // Clearing it first would put the filled-in form back on screen for the
  // frame between the response and the route resolving.
  it('keeps the status line up until the navigation lands', async () => {
    await render();
    fillIn();
    submit();
    packRequest().flush(packed());
    TestBed.tick();

    expect(element().querySelector('form')).toBeNull();
    expect(text()).toContain(en['trip.waiting.geocoding']);

    vi.useRealTimers();
    await fixture.whenStable();
  });

  const failures: readonly (readonly [string, number, string])[] = [
    ['trip_too_long', 400, 'trip.error.tripTooLong'],
    ['wardrobe_too_small', 400, 'trip.error.wardrobeTooSmall'],
    ['destination_not_found', 400, 'trip.error.destinationNotFound'],
    ['geocoding_unavailable', 502, 'trip.error.geocodingUnavailable'],
    ['forecast_unavailable', 400, 'trip.error.forecastUnavailable'],
    ['stylist_failed', 502, 'trip.error.stylistFailed'],
    ['validation_error', 422, 'trip.error.validation'],
  ];

  for (const [code, status, key] of failures) {
    it(`says something specific about ${code}`, async () => {
      await render();
      fillIn();
      submit();
      failWith(code, status);

      expect(text()).toContain(en[key as keyof typeof en]);
    });
  }

  // `forecast_unavailable` is the first code this project issues at two
  // statuses — 400 past the horizon, 502 when Open-Meteo does not answer — and
  // both say one thing to the user. A reader keyed on the status would say two.
  it('says the same thing about forecast_unavailable at either status', async () => {
    await render();
    fillIn();
    submit();
    failWith('forecast_unavailable', 502);

    expect(text()).toContain(en['trip.error.forecastUnavailable']);
  });

  // FastAPI's own 422 carries `detail` rather than `code`, so the status is the
  // only thing left to branch on — and falling through to "something went
  // wrong" would be the wrong thing to say about a body this client should
  // never have been able to send.
  it('reads a bare 422 as a validation error', async () => {
    await render();
    fillIn();
    submit();
    packRequest().flush({ detail: [{ msg: 'bad' }] }, { status: 422, statusText: 'Unprocessable' });
    TestBed.tick();

    expect(text()).toContain(en['trip.error.validation']);
  });

  it('falls back to a general message for a code it does not know', async () => {
    await render();
    fillIn();
    submit();
    failWith('teapot', 418);

    expect(text()).toContain(en['trip.error.general']);
  });

  // CONVENTIONS.md: the frontend never renders a raw error. Every failure path
  // has a written message, and `detail` is written for a developer.
  it('never renders the raw error body', async () => {
    await render();
    fillIn();
    submit();
    failWith('stylist_failed', 502);

    expect(text()).not.toContain(RAW_DETAIL);
  });

  // The whole reason the draft is the page's and not the form's: a rejected
  // pack comes back to a screen the user can correct and send again.
  it('brings the filled-in form back after a failure', async () => {
    await render();
    fillIn();
    submit();
    failWith('stylist_failed', 502);

    expect(text()).toContain('Berlin, Germany');
    expect(field('trip_start').value).toBe(dayFromToday(1));
    expect([...element().querySelectorAll('fieldset')]).toHaveLength(4);
  });

  it('can be submitted again after a failure', async () => {
    await render();
    fillIn();
    submit();
    failWith('stylist_failed', 502);
    submit();

    packRequest().flush(packed());
  });

  it('caps the date pickers at the trip horizon', async () => {
    await render();

    expect(field('trip_end').getAttribute('max')).toBe(tripHorizon());
  });
});

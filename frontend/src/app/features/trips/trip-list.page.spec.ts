import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { Trip, TripDay } from '../../shared/models/trip.model';
import { TripListPage } from './trip-list.page';

let fixture: ComponentFixture<TripListPage>;
let mock: HttpTestingController;

// Copied rather than imported from the two neighbouring trip specs, which is the
// convention rather than an oversight: no test module in this project imports
// another. Only what a row renders is filled in with any care — the rest of the
// trip object is here because the wire carries it.
function day(overrides: Partial<TripDay> = {}): TripDay {
  return {
    day: 1,
    date: '2026-03-14',
    temp_min_c: 8,
    temp_max_c: 12.4,
    precip_mm: 4.2,
    wind_kph: 11,
    condition: 'rain',
    rule: 'Outerwear is REQUIRED, warmth 3-4.',
    slots: [{ slot: 'day', occasion: 'work', look_id: 'look-1' }],
    ...overrides,
  };
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
    days: [day(), day({ day: 2 }), day({ day: 3 }), day({ day: 4 })],
    packing_list: {
      item_ids: ['item-1'],
      reuse_summary: { item_count: 8, look_count: 4, most_reused: null },
    },
    created_at: '2026-03-01T09:00:00Z',
    ...overrides,
  };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

// Collapsed, because the template's line breaks land in textContent and every
// string asserted here is one rendered line.
function text(node: Element = element()): string {
  return (node.textContent ?? '').replace(/\s+/g, ' ').trim();
}

function rows(): HTMLLIElement[] {
  return [...element().querySelectorAll('li')];
}

function destinations(): string[] {
  return rows().map((row) => text(row.querySelector('span')!));
}

function listRequest() {
  return mock.expectOne(`${environment.apiUrl}/trips`);
}

async function render(): Promise<void> {
  fixture = TestBed.createComponent(TripListPage);
  fixture.detectChanges();
  await fixture.whenStable();
}

function loadWith(trips: readonly Trip[]): void {
  listRequest().flush({ trips, total: trips.length });
  TestBed.tick();
}

function press(row: number): void {
  rows()[row].querySelector('button')!.click();
  TestBed.tick();
}

describe('TripListPage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'trips/new', children: [] },
          { path: 'trips/:id', children: [] },
        ]),
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

  // The URL is asserted whole, without a query string, because `list()` sends
  // neither limit nor offset and a default appearing on the wire would be the
  // first sign that one had been added for convenience.
  it('asks for every trip on the account and says so while it waits', async () => {
    await render();

    expect(text()).toContain('Opening your trips');
    expect(listRequest().request.method).toBe('GET');
  });

  // The loading line is asserted absent as well as the message present: the two
  // are branches of one @if, and a screen rendering both would mean the failure
  // had been added beside the wait rather than in place of it.
  it('says so when the trips cannot be read', async () => {
    await render();
    listRequest().flush({ detail: 'nope' }, { status: 500, statusText: 'Server Error' });
    TestBed.tick();

    expect(text()).toContain("We couldn't open your trips");
    expect(text()).not.toContain('Opening your trips');
    expect(rows()).toHaveLength(0);
  });

  it('offers the form when the account has no trips', async () => {
    await render();
    loadWith([]);

    expect(text()).toContain('No trips yet');
    expect(rows()).toHaveLength(0);
    expect(element().querySelector('app-empty-state a')!.getAttribute('href')).toBe('/trips/new');
  });

  // Two trips of different lengths, so the singular and the plural are both
  // rendered by one assertion and neither can be read off the other.
  it('renders one row per trip, in the order the server sent them', async () => {
    await render();
    loadWith([
      trip(),
      trip({
        id: 'trip-2',
        destination: 'Lisbon',
        start_date: '2026-02-02',
        end_date: '2026-02-02',
        days: [day({ date: '2026-02-02' })],
      }),
    ]);

    expect(destinations()).toEqual(['Berlin', 'Lisbon']);
    expect(text(rows()[0])).toContain('2026-03-14 – 2026-03-17 · 4 days');
    expect(text(rows()[1])).toContain('2026-02-02 – 2026-02-02 · 1 day');
    expect(rows()[0].querySelector('a')!.getAttribute('href')).toBe('/trips/trip-1');
  });

  it('takes two presses to delete a trip, and the row leaves on the second', async () => {
    await render();
    loadWith([trip(), trip({ id: 'trip-2', destination: 'Lisbon' })]);

    press(0);
    mock.expectNone(`${environment.apiUrl}/trips/trip-1`);
    expect(text(rows()[0])).toContain('Saved looks from this trip go too');

    press(0);
    const request = mock.expectOne(`${environment.apiUrl}/trips/trip-1`);
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
    TestBed.tick();

    expect(destinations()).toEqual(['Lisbon']);
  });

  // The label going back is not the assertion — that could be cosmetic. The
  // press afterwards is: an armed row that lost focus and was pressed once more
  // has to arm again rather than delete, which is the whole point of disarming.
  it('disarms a row that loses focus', async () => {
    await render();
    loadWith([trip()]);

    press(0);
    expect(text(rows()[0])).toContain('Saved looks from this trip go too');

    rows()[0].querySelector('button')!.dispatchEvent(new FocusEvent('blur'));
    TestBed.tick();

    expect(text(rows()[0])).not.toContain('Saved looks from this trip go too');

    press(0);
    mock.expectNone(`${environment.apiUrl}/trips/trip-1`);
  });

  // The middle row, because a restore that appends and a restore that prepends
  // both pass on a list of one and on a row taken from either end.
  it('puts a row the server refused to delete back where it was', async () => {
    await render();
    loadWith([
      trip(),
      trip({ id: 'trip-2', destination: 'Lisbon' }),
      trip({ id: 'trip-3', destination: 'Oslo' }),
    ]);

    press(1);
    press(1);
    mock
      .expectOne(`${environment.apiUrl}/trips/trip-2`)
      .flush({ detail: 'nope' }, { status: 500, statusText: 'Server Error' });
    TestBed.tick();

    expect(destinations()).toEqual(['Berlin', 'Lisbon', 'Oslo']);
    expect(text()).toContain("We couldn't delete this trip");
  });

  // `trip.list.days.one` is "1 day", which is short enough that a hard-coded
  // literal renders identically and survives every assertion above. A second
  // table with a distinctive value is the only thing that can tell the lookup
  // from the typing.
  it('reads the day count out of the string table rather than spelling it here', async () => {
    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush({ ...en, 'trip.list.days.one': 'a single day' });
    await loading;

    await render();
    loadWith([trip({ days: [day()] })]);

    expect(text(rows()[0])).toContain('· a single day');
  });
});

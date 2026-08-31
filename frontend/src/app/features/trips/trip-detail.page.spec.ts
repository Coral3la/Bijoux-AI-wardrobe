import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import { Trip, TripDay, TripDetail } from '../../shared/models/trip.model';
import { TripDetailPage } from './trip-detail.page';

// Distinctive on purpose: the assertion that it never reaches the screen has to
// be able to fail.
const RAW_DETAIL = 'the-servers-own-sentence';

let fixture: ComponentFixture<TripDetailPage>;
let mock: HttpTestingController;
let currentId: string;

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
    is_saved: false,
    feedback: null,
    worn_at: null,
    ...overrides,
  };
}

// Day 1 is rain at 12°C and day 2 is clear at 17°C, so no assertion about one
// of them can pass by reading the other.
function day(overrides: Partial<TripDay> = {}): TripDay {
  return {
    day: 1,
    date: '2026-03-14',
    occasion: 'work',
    temp_min_c: 8,
    temp_max_c: 12.4,
    precip_mm: 4.2,
    wind_kph: 11,
    condition: 'rain',
    rule: 'Outerwear is REQUIRED, warmth 3-4.',
    look_id: 'look-1',
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
    end_date: '2026-03-15',
    notes: null,
    days: [
      day(),
      day({ day: 2, date: '2026-03-15', condition: 'clear', temp_max_c: 17.4, look_id: 'look-2' }),
    ],
    packing_list: {
      item_ids: ['item-1'],
      reuse_summary: { item_count: 8, look_count: 4, most_reused: { item_id: 'item-1', days: 3 } },
    },
    created_at: '2026-03-01T09:00:00Z',
    ...overrides,
  };
}

function detail(overrides: Partial<TripDetail> = {}): TripDetail {
  return {
    trip: trip(),
    looks: [look(), look({ id: 'look-2', title: 'Dinner out', items: [item({ id: 'item-2' })] })],
    ...overrides,
  };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function header(): string {
  return element().querySelector('header')?.textContent ?? '';
}

function tabs(): HTMLButtonElement[] {
  return [...element().querySelectorAll<HTMLButtonElement>('[role="group"] button')];
}

function tripRequest() {
  return mock.expectOne(`${environment.apiUrl}/trips/${currentId}`);
}

async function render(): Promise<void> {
  fixture = TestBed.createComponent(TripDetailPage);
  fixture.detectChanges();
  await fixture.whenStable();
}

async function loaded(overrides: Partial<TripDetail> = {}): Promise<void> {
  await render();
  tripRequest().flush(detail(overrides));
  fixture.detectChanges();
}

describe('TripDetailPage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'wardrobe/:id', children: [] },
        ]),
        {
          provide: ActivatedRoute,
          // The key is honoured rather than ignored, which item-detail's own
          // stub learned from a surviving mutation: a stub answering every key
          // the same way cannot tell paramMap.get('id') from anything else.
          useValue: {
            snapshot: { paramMap: { get: (key: string) => (key === 'id' ? currentId : null) } },
          },
        },
      ],
    });
    currentId = 'trip-1';
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
  });

  it('asks for the trip named in the route', async () => {
    currentId = 'trip-9';
    await render();

    tripRequest().flush(detail());
  });

  it('says so while the trip is loading', async () => {
    await render();

    expect(text()).toContain(en['trip.view.loading']);
    tripRequest().flush(detail());
  });

  it('heads the screen with the destination and the dates', async () => {
    await loaded();

    expect(text()).toContain('Berlin');
    expect(text()).toContain('2026-03-14 – 2026-03-15');
  });

  // The destination is a place name off the geocoder and Fraunces is
  // latin-subset, so a non-Latin one would render in two faces on one line.
  // DECISIONS.md 071 names this screen.
  it('prints the destination in the body face', async () => {
    await loaded();

    expect(element().querySelector('h1')!.className).not.toContain('font-display');
  });

  it('carries the counts and the reuse sentence on one header line', async () => {
    await loaded();

    expect(header()).toContain(
      "8 items · 4 looks · You'll wear the white oversized shirt on 3 days",
    );
  });

  it('says one look rather than 1 looks on a one-day trip', async () => {
    await loaded({
      trip: trip({
        packing_list: {
          item_ids: ['item-1'],
          reuse_summary: { item_count: 4, look_count: 1, most_reused: null },
        },
      }),
    });

    expect(text()).toContain('4 items · 1 look');
    expect(text()).not.toContain('1 looks');
  });

  // Three ways to have no clause, one answer to all of them. Nothing is worn
  // twice on a short trip, which is ordinary rather than an error.
  it('drops the reuse clause when nothing is worn twice', async () => {
    await loaded({
      trip: trip({
        packing_list: {
          item_ids: ['item-1'],
          reuse_summary: { item_count: 8, look_count: 4, most_reused: null },
        },
      }),
    });

    expect(header()).toContain('8 items · 4 looks');
    expect(header()).not.toContain("You'll wear");
  });

  // The second look carries item-2 and not the default item-1: two looks
  // holding the same id would let the tagged copy overwrite the untagged one
  // in the lookup, and the test would pass by hydrating a different row.
  it('drops the reuse clause rather than naming an untagged garment', async () => {
    await loaded({
      looks: [
        look({ items: [item({ display_name: null })] }),
        look({ id: 'look-2', items: [item({ id: 'item-2' })] }),
      ],
    });

    expect(header()).not.toContain("You'll wear");
    expect(header()).not.toContain(en['item.untitled']);
    // The packing list still names the row, and that is the other component's
    // deliberate fallback: a blank line in a suitcase list is worse than a
    // generic one. Only the header sentence refuses to be built from it.
    expect(text()).toContain(en['item.untitled']);
  });

  // The item the summary names was worn by a look a repack detached, so no
  // row for it came back with this response. AUDITS.md O-32.
  it('drops the reuse clause when the named item is in no look', async () => {
    await loaded({
      trip: trip({
        packing_list: {
          item_ids: ['item-1'],
          reuse_summary: {
            item_count: 8,
            look_count: 4,
            most_reused: { item_id: 'item-gone', days: 3 },
          },
        },
      }),
    });

    expect(header()).toContain('8 items · 4 looks');
    expect(header()).not.toContain("You'll wear");
  });

  it('draws one tab per day with its own temperature and condition', async () => {
    await loaded();

    expect(tabs()).toHaveLength(2);
    expect(tabs()[0].textContent).toContain('12°C');
    expect(tabs()[0].textContent).toContain(en['vocabulary.condition.rain']);
    expect(tabs()[1].textContent).toContain('17°C');
    expect(tabs()[1].textContent).toContain(en['vocabulary.condition.clear']);
  });

  // The day's high, rounded, which is what weather-strip.ts prints and what
  // DECISIONS.md 142 settled. 12.4 rather than 12 in the fixture is what makes
  // the rounding visible; temp_min_c is 8 and must not be the number shown.
  it('shows the day high rather than the low', async () => {
    await loaded();

    expect(tabs()[0].textContent).toContain('12°C');
    expect(tabs()[0].textContent).not.toContain('8°C');
  });

  it('opens on day 1', async () => {
    await loaded();

    expect(tabs()[0].getAttribute('aria-pressed')).toBe('true');
    expect(text()).toContain('Morning meetings');
  });

  it('swaps the look when another day is tapped', async () => {
    await loaded();

    tabs()[1].click();
    fixture.detectChanges();

    expect(text()).toContain('Dinner out');
    expect(text()).not.toContain('Morning meetings');
    expect(tabs()[1].getAttribute('aria-pressed')).toBe('true');
  });

  // The join is by look_id and not by position. days[1] carries looks[1] here
  // only because the fixture is in order; this one reverses the looks array so
  // a positional read would put Dinner out on day 1.
  it('joins the day to its look by id rather than by position', async () => {
    await loaded({
      looks: [look({ id: 'look-2', title: 'Dinner out', items: [item({ id: 'item-2' })] }), look()],
    });

    expect(text()).toContain('Morning meetings');
    expect(text()).not.toContain('Dinner out');
  });

  it('renders the look reasoning and the weather note', async () => {
    await loaded();

    expect(text()).toContain('The high-rise jean balances the oversized shirt.');
    expect(text()).toContain('Mild at 18°C — the blazer is enough.');
  });

  // A repack detaches a look that was saved, rated or worn, and the day it
  // belonged to keeps its forecast and loses its outfit. DECISIONS.md 200.
  it('renders a day with no look as a gap rather than crashing', async () => {
    await loaded({
      trip: trip({ days: [day({ look_id: null }), day({ day: 2, look_id: null })] }),
    });

    expect(text()).toContain(en['trip.view.day.noLook']);
    expect(tabs()).toHaveLength(2);
  });

  // The type permits an id the response did not hydrate even though this
  // endpoint cannot produce one, and the two states have to render alike.
  it('renders a day whose look_id matches nothing as the same gap', async () => {
    await loaded({ trip: trip({ days: [day({ look_id: 'look-gone' })] }) });

    expect(text()).toContain(en['trip.view.day.noLook']);
  });

  // Day 1 stays selected even when it is the empty one: an opening selection
  // that depended on which days kept a look would leave the reader working out
  // why day 2 is the one lit up.
  it('opens on day 1 even when day 1 is the gap', async () => {
    await loaded({ trip: trip({ days: [day({ look_id: null }), day({ day: 2 })] }) });

    expect(text()).toContain(en['trip.view.day.noLook']);
    expect(tabs()[0].getAttribute('aria-pressed')).toBe('true');
  });

  it('hydrates the packing list from the items the looks carry', async () => {
    await loaded({
      trip: trip({
        packing_list: {
          item_ids: ['item-2', 'item-1'],
          reuse_summary: { item_count: 2, look_count: 2, most_reused: null },
        },
      }),
      looks: [
        look({ items: [item({ id: 'item-1', display_name: 'white shirt' })] }),
        look({
          id: 'look-2',
          items: [item({ id: 'item-2', category: 'shoes', display_name: 'brown boots' })],
        }),
      ],
    });

    expect(text()).toContain('white shirt');
    expect(text()).toContain('brown boots');
  });

  // A detached look takes its item rows with it, so an id can outlive every
  // row describing it. A checkbox beside no name is not something to act on.
  it('drops a packed id that no look hydrates', async () => {
    await loaded({
      trip: trip({
        packing_list: {
          item_ids: ['item-1', 'item-gone'],
          reuse_summary: { item_count: 2, look_count: 2, most_reused: null },
        },
      }),
    });

    expect(element().querySelectorAll('app-packing-list input[type="checkbox"]')).toHaveLength(1);
  });

  it('shows the not-found message for a trip that is not yours', async () => {
    await render();
    tripRequest().flush(
      { detail: RAW_DETAIL, code: 'not_found' },
      { status: 404, statusText: 'Not Found' },
    );
    fixture.detectChanges();

    expect(text()).toContain(en['trip.error.notFound']);
    expect(text()).not.toContain(RAW_DETAIL);
  });

  // A 404 that never reached the application — a proxy, a wrong base URL —
  // carries no body to hold a code, and it is the same fact about the same URL.
  // This is the half of the branch the documented code cannot cover.
  it('shows the not-found message for a bodyless 404', async () => {
    await render();
    tripRequest().flush(null, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();

    expect(text()).toContain(en['trip.error.notFound']);
  });

  // A malformed id is FastAPI's 422 before read_trip runs — the path parameter
  // is typed as a UUID — which 04-API-SPEC.md's failure list does not mention.
  it('shows the general message for a malformed id', async () => {
    currentId = 'not-a-uuid';
    await render();
    tripRequest().flush(
      { detail: RAW_DETAIL },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();

    expect(text()).toContain(en['trip.error.load']);
    expect(text()).not.toContain(en['trip.error.notFound']);
  });

  it('shows the general message when the server fails', async () => {
    await render();
    tripRequest().flush({ detail: RAW_DETAIL }, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(text()).toContain(en['trip.error.load']);
    expect(text()).not.toContain(RAW_DETAIL);
  });

  // The link is outside every branch, which is what the error states need: a
  // trip that does not load leaves this screen with nothing else on it.
  it('keeps the way back on screen in every state', async () => {
    await render();
    expect(element().querySelector('a[href="/wardrobe"]')).not.toBeNull();

    tripRequest().flush({ code: 'not_found' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();

    expect(element().querySelector('a[href="/wardrobe"]')).not.toBeNull();
  });
});

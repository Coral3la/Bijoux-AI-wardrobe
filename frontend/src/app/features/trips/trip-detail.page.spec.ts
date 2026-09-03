import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import {
  PackResponse,
  Trip,
  TripDay,
  TripDaySlot,
  TripDetail,
} from '../../shared/models/trip.model';
import { STATUS_INTERVAL_MS } from './pack-wait';
import { TripDetailPage } from './trip-detail.page';

// Distinctive on purpose: the assertion that it never reaches the screen has to
// be able to fail.
const RAW_DETAIL = 'the-servers-own-sentence';

let fixture: ComponentFixture<TripDetailPage>;
let mock: HttpTestingController;
let router: Router;
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

// One slot of a day. Defaults to the `day` slot on `work` with `look-1`, which
// is what every single-slot fixture in this file used to spell out on the day
// itself.
function slot(overrides: Partial<TripDaySlot> = {}): TripDaySlot {
  return { slot: 'day', occasion: 'work', look_id: 'look-1', ...overrides };
}

// Day 1 is rain at 12°C and day 2 is clear at 17°C, so no assertion about one
// of them can pass by reading the other.
//
// **`occasion` and `look_id` moved into `slots[]` on the wire at 4.15 and in
// this fixture at 4.18.** Every assertion in this file spent three tasks reading
// a payload the server had stopped sending — the specs mock their own responses,
// so nothing failed and nothing could have. That is the window `PROGRESS.md`
// records, and this is where it closes.
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
    slots: [slot()],
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
      day({
        day: 2,
        date: '2026-03-15',
        condition: 'clear',
        temp_max_c: 17.4,
        slots: [slot({ look_id: 'look-2' })],
      }),
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

// The repack answers PackResponse, which is TripDetail plus a key this screen
// has no model for. The fixture carries it so the assertion that it is dropped
// on the way into the signal has something to drop.
function repacked(overrides: Partial<Trip> = {}): PackResponse {
  return {
    trip: trip({ destination: 'Lisbon', ...overrides }),
    looks: [
      look({ id: 'look-1', title: 'Warmer plan' }),
      look({ id: 'look-2', title: 'Second warmer plan', items: [item({ id: 'item-2' })] }),
    ],
    missing_pieces: [
      { category: 'outerwear', description: 'a warm coat', reason: 'Nothing warm enough.' },
    ],
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

// One per day, in the order they are drawn. The child combinator is
// load-bearing: an ItemCard's own root is an <article> too, so a descendant
// query would count every garment tile in the itinerary as a day.
function daySections(): HTMLElement[] {
  return [...element().querySelectorAll<HTMLElement>('main > article')];
}

function dayText(index: number): string {
  return daySections()[index]?.textContent ?? '';
}

// The day's head alone — its number, its date and its forecast — read apart
// from the look beneath it. The model's weather note says things like "Mild at
// 18°C", so a section-wide assertion about a temperature can be answered by
// prose rather than by the reading the head prints.
function dayHead(index: number): string {
  return daySections()[index]?.firstElementChild?.textContent ?? '';
}

// Every slot card of one day, in the order the wire sent them.
function slotCards(day: number): HTMLElement[] {
  return [...(daySections()[day]?.querySelectorAll(':scope > div') ?? [])].slice(
    1,
  ) as HTMLElement[];
}

function slotHead(day: number, slot = 0): string {
  return slotCards(day)[slot]?.firstElementChild?.textContent ?? '';
}

function tripRequest() {
  return mock.expectOne(`${environment.apiUrl}/trips/${currentId}`);
}

function repackRequest() {
  return mock.expectOne(`${environment.apiUrl}/trips/${currentId}/repack`);
}

function deleteRequest() {
  return mock.expectOne(`${environment.apiUrl}/trips/${currentId}`);
}

function swapRequest() {
  return mock.expectOne(`${environment.apiUrl}/trips/${currentId}/swap`);
}

// The look's garments, in the order it draws them, read off the tiles' alt text
// — which is where a tile's name lives, the photograph being the whole of it.
// The packing list below names every garment in the trip, so a page-wide
// assertion cannot tell "not in this day's look" from "not in the suitcase",
// and the first is what a day-local swap has to be asked.
function lookItems(index: number): string[] {
  return [...daySections()[index].querySelectorAll('app-trip-look img')].map(
    (image) => image.getAttribute('alt') ?? '',
  );
}

// The wait, per day. Every day is on screen at once, so a swap on Monday that
// spins on Thursday is a mutation the old page could not have: `swappingItemId`
// is an item id, and the shirt is worn on both. DECISIONS.md 222.
function spinners(index: number): number {
  return daySections()[index].querySelectorAll('app-trip-look [role="status"]').length;
}

// The wait, per slot. The trousers reused between Monday's office and Monday's
// dinner are one garment id on one date, so a day-scoped spinner spins both of
// them from one press — which is the day-scoped failure above, one level down
// and now a case the reader meets on purpose. STAGE-4 4.18.
function slotSpinners(day: number, slot: number): number {
  return slotCards(day)[slot].querySelectorAll('app-trip-look [role="status"]').length;
}

function slotBadges(day: number, slot: number): HTMLButtonElement[] {
  return [...slotCards(day)[slot].querySelectorAll<HTMLButtonElement>('app-trip-look li button')];
}

// The badges, and only the badges: the packing list's rows are labels around
// checkboxes, so a `button` inside an `li` on this screen is a ↻ and nothing
// else. Scoped to the component anyway, so that stops being a fact this helper
// relies on the day something else grows a list.
function badges(index = 0): HTMLButtonElement[] {
  return [...daySections()[index].querySelectorAll<HTMLButtonElement>('app-trip-look li button')];
}

// Found by the words on it rather than by a class or a position, so the label
// each state renders is asserted by every test that presses the button.
function button(label: string): HTMLButtonElement {
  const found = [...element().querySelectorAll<HTMLButtonElement>('button')].find(
    (candidate) => (candidate.textContent ?? '').trim() === label,
  );
  if (found === undefined) {
    throw new Error(`no button labelled ${label}`);
  }
  return found;
}

function press(label: string): void {
  button(label).click();
  fixture.detectChanges();
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
    router = TestBed.inject(Router);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    vi.useRealTimers();
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

  // Two sentences in one paragraph rather than one composed string, and they
  // are asserted apart because the gap between them is a flex gap: sibling
  // elements have their whitespace-only text node collapsed away, so nothing
  // joins the two in textContent. DECISIONS.md 213, 222.
  it('carries the counts and the reuse sentence in the header', async () => {
    await loaded();

    expect(header()).toContain('Packed 8 pieces across 4 looks.');
    expect(header()).toContain("You'll wear the white oversized shirt on 3 days.");
  });

  // The garment leaves the prose face and nothing else does. AuthoredLine cuts
  // the key at its own placeholder, so a translation that puts the name first
  // still wraps the name and only the name. DECISIONS.md 071, 213.
  it('prints the reused garment in the content face inside the prose line', async () => {
    await loaded();

    const spans = [...element().querySelectorAll('header app-authored-line span')];
    const garment = spans.find((span) => span.textContent === 'white oversized shirt');

    expect(garment?.classList.contains('font-sans')).toBe(true);
    expect(spans.some((span) => span.textContent?.includes("You'll wear"))).toBe(true);
    expect(
      spans
        .find((span) => span.textContent?.includes("You'll wear"))
        ?.classList.contains('font-sans'),
    ).toBe(false);
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

    expect(text()).toContain('Packed 4 pieces across 1 look.');
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

    expect(header()).toContain('Packed 8 pieces across 4 looks.');
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

    expect(header()).toContain('Packed 8 pieces across 4 looks.');
    expect(header()).not.toContain("You'll wear");
  });

  // No tabs. Every day is a section of its own, in date order, and the fixture's
  // two days differ in every field a head prints so no assertion about one can
  // pass by reading the other. DECISIONS.md 222.
  it('draws one section per day with its own date, temperature and condition', async () => {
    await loaded();

    expect(daySections()).toHaveLength(2);
    expect(dayHead(0)).toContain('Day 1 · 2026-03-14');
    expect(dayHead(0)).toContain('12°C');
    expect(dayHead(0)).toContain(en['vocabulary.condition.rain']);
    expect(dayHead(1)).toContain('Day 2 · 2026-03-15');
    expect(dayHead(1)).toContain('17°C');
    expect(dayHead(1)).toContain(en['vocabulary.condition.clear']);
  });

  // 4.18's first criterion. One forecast row covers both halves of a date, so
  // the head is drawn once and the cards under it twice — printing the weather
  // per slot would be one measurement rendered as two facts.
  it('draws two cards under one forecast for a two-slot day', async () => {
    await loaded({
      trip: trip({
        days: [
          day({
            slots: [slot(), slot({ slot: 'evening', occasion: 'formal', look_id: 'look-2' })],
          }),
        ],
      }),
      looks: [look({ id: 'look-1' }), look({ id: 'look-2', title: 'Dinner out' })],
    });

    expect(daySections()).toHaveLength(1);
    expect(slotCards(0)).toHaveLength(2);
    expect(slotHead(0, 0)).toContain(en['trip.slot.day']);
    expect(slotHead(0, 1)).toContain(en['trip.slot.evening']);
    expect(text()).toContain('Dinner out');
    // The temperature and the condition are printed once, on the head.
    expect(dayHead(0)).toContain(en['vocabulary.condition.rain']);
    expect(slotHead(0, 0)).not.toContain(en['vocabulary.condition.rain']);
    expect(slotHead(0, 1)).not.toContain(en['vocabulary.condition.rain']);
  });

  // A repack detaches a look that was saved, rated or worn, and the gap is per
  // slot from 4.18: the evening goes and the day look stays exactly where it is.
  it('leaves a day look standing when its own evening was detached', async () => {
    await loaded({
      trip: trip({
        days: [
          day({
            slots: [slot(), slot({ slot: 'evening', occasion: 'formal', look_id: null })],
          }),
        ],
      }),
      looks: [look({ id: 'look-1' })],
    });

    expect(slotCards(0)).toHaveLength(2);
    expect(lookItems(0)).toHaveLength(1);
    expect(slotHead(0, 1)).toContain(en['vocabulary.occasion.formal']);
    expect(text()).toContain(en['trip.view.day.noLook']);
  });

  // The occasion left the day head for the slot head at 4.18: the forecast
  // belongs to the date and the occasion belongs to the slot, so a day head that
  // still named one would be printing a property of half of itself.
  it('names the occasion on the slot rather than on the day', async () => {
    await loaded({
      trip: trip({
        days: [
          day(),
          day({
            day: 2,
            date: '2026-03-15',
            slots: [slot({ occasion: 'formal', look_id: 'look-2' })],
          }),
        ],
      }),
    });

    expect(dayHead(0)).not.toContain(en['vocabulary.occasion.work']);
    expect(slotHead(0)).toContain(en['vocabulary.occasion.work']);
    expect(slotHead(0)).toContain(en['trip.slot.day']);
    expect(slotHead(1)).toContain(en['vocabulary.occasion.formal']);
  });

  // Where the two labels render as the same word, only one is printed: `Slot`
  // and `Occasion` overlap on `evening` (AUDITS.md O-35), so the commonest
  // evening there is would read EVENING · EVENING. It compares the rendered
  // strings and not the enum values, because what a reader sees doubled is the
  // word — and a second language may collide on a different pair or on none.
  it('prints one word where the slot and the occasion are the same word', async () => {
    await loaded({
      trip: trip({
        days: [day({ slots: [slot({ slot: 'evening', occasion: 'evening' })] })],
      }),
    });

    expect(slotHead(0)).toContain('Evening');
    expect(slotHead(0)).not.toContain('Evening · Evening');
  });

  // The dot between the slot and the occasion is punctuation a developer could
  // have typed into the join, and en.json's own value renders identically either
  // way. A second table with a different separator is the only assertion that
  // can tell a lookup from a literal.
  it('takes the slot head from the string table rather than from the code', async () => {
    const loading = TestBed.inject(I18nService).load();
    mock
      .expectOne('/i18n/en.json')
      .flush({ ...en, 'trip.view.slot.head': '{{slot}} / {{occasion}}' });
    await loading;
    await loaded();

    expect(slotHead(0)).toContain('Day / Work');
  });

  it('takes the weather line from the string table rather than from the code', async () => {
    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush({ ...en, 'trip.view.day.weather': '>> {{condition}}' });
    await loading;
    await loaded();

    expect(dayHead(0)).toContain('>> Rain');
  });

  // The day's high, rounded, which is what weather-strip.ts prints and what
  // DECISIONS.md 142 settled. 12.4 rather than 12 in the fixture is what makes
  // the rounding visible; temp_min_c is 8 and must not be the number shown.
  it('shows the day high rather than the low', async () => {
    await loaded();

    expect(dayHead(0)).toContain('12°C');
    expect(dayHead(0)).not.toContain('8°C');
  });

  // The whole trip at once, which is the direction: nothing is selected and
  // nothing is hidden, so a five-day trip is read rather than clicked through.
  it('draws every day of the trip at once, in date order', async () => {
    await loaded();

    expect(dayText(0)).toContain('Morning meetings');
    expect(dayText(1)).toContain('Dinner out');
  });

  // The join is by look_id and not by position. days[1] carries looks[1] here
  // only because the fixture is in order; this one reverses the looks array so
  // a positional read would put Dinner out on day 1.
  it('joins the day to its look by id rather than by position', async () => {
    await loaded({
      looks: [look({ id: 'look-2', title: 'Dinner out', items: [item({ id: 'item-2' })] }), look()],
    });

    expect(dayText(0)).toContain('Morning meetings');
    expect(dayText(1)).toContain('Dinner out');
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
      trip: trip({
        days: [
          day({ slots: [slot({ look_id: null })] }),
          day({ day: 2, slots: [slot({ look_id: null })] }),
        ],
      }),
    });

    expect(text()).toContain(en['trip.view.day.noLook']);
    expect(daySections()).toHaveLength(2);
  });

  // The type permits an id the response did not hydrate even though this
  // endpoint cannot produce one, and the two states have to render alike.
  it('renders a day whose look_id matches nothing as the same gap', async () => {
    await loaded({ trip: trip({ days: [day({ slots: [slot({ look_id: 'look-gone' })] })] }) });

    expect(text()).toContain(en['trip.view.day.noLook']);
  });

  // A gap keeps its head, and that is what the head being the page's buys: the
  // day still has a forecast and an occasion, and only the outfit is missing.
  it('keeps the head of a day whose look was detached', async () => {
    await loaded({
      trip: trip({ days: [day({ slots: [slot({ look_id: null })] }), day({ day: 2 })] }),
    });

    expect(dayHead(0)).toContain('Day 1 · 2026-03-14');
    expect(dayHead(0)).toContain('12°C');
    expect(dayText(0)).toContain(en['trip.view.day.noLook']);
    expect(dayText(1)).toContain('Morning meetings');
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

  // The way out of a trip that does not load is the navigation bar, which the
  // shell renders above this component in every state including this one. What
  // this screen must not do is build its own — the sixth time that happened is
  // what closed AUDITS.md O-29.
  it('carries no navigation of its own, loaded or not', async () => {
    await render();
    expect(element().querySelector('a[href="/wardrobe"]')).toBeNull();

    tripRequest().flush({ code: 'not_found' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();

    expect(element().querySelector('a[href="/wardrobe"]')).toBeNull();
  });
  // 4.6b. AUDITS.md O-33: both endpoints were built, tested and reachable by
  // nobody until these two controls.
  describe('repack', () => {
    it('asks the repack endpoint for the trip on screen', async () => {
      currentId = 'trip-9';
      await loaded();

      press(en['trip.repack.action']);

      repackRequest().flush(repacked());
    });

    // DECISIONS.md 202: the endpoint re-derives destination, dates, occasions
    // and notes from the stored row, so there is nothing to send. `{}` would be
    // a body on a request that declares no schema for one.
    it('sends no body', async () => {
      await loaded();

      press(en['trip.repack.action']);

      const request = repackRequest();
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toBeNull();
      request.flush(repacked());
    });

    it('renders the trip the repack answered with', async () => {
      await loaded();

      press(en['trip.repack.action']);
      repackRequest().flush(repacked());
      fixture.detectChanges();

      expect(header()).toContain('Lisbon');
      expect(dayText(0)).toContain('Warmer plan');
      expect(text()).not.toContain('Morning meetings');
    });

    // D asked that the selected day survive a repack; there is no selection to
    // survive it now, so what the criterion becomes is that every day comes back
    // — a repack that rendered only the first would be the tab strip's failure
    // with nothing to reveal it. DECISIONS.md 222.
    it('re-renders every day of the trip the repack answered with', async () => {
      await loaded();

      press(en['trip.repack.action']);
      repackRequest().flush(repacked());
      fixture.detectChanges();

      expect(daySections()).toHaveLength(2);
      expect(dayText(1)).toContain('Second warmer plan');
    });

    it('moves through the status lines while the repack runs', async () => {
      await loaded();
      vi.useFakeTimers();

      press(en['trip.repack.action']);
      expect(text()).toContain(en['trip.waiting.geocoding']);

      vi.advanceTimersByTime(STATUS_INTERVAL_MS);
      fixture.detectChanges();

      expect(text()).toContain(en['trip.waiting.forecast']);
      repackRequest().flush(repacked());
    });

    it('takes the status line away once the repack has answered', async () => {
      await loaded();

      press(en['trip.repack.action']);
      repackRequest().flush(repacked());
      fixture.detectChanges();

      expect(text()).not.toContain(en['trip.waiting.geocoding']);
    });

    // C, and DECISIONS.md 200's ordering made visible: pack_trip runs before
    // anything is detached or deleted, so a failed repack costs nothing and the
    // trip is still the trip the user has.
    it('leaves the trip on screen when the repack fails', async () => {
      await loaded();

      press(en['trip.repack.action']);
      repackRequest().flush(
        { detail: RAW_DETAIL, code: 'stylist_failed' },
        { status: 502, statusText: 'Bad Gateway' },
      );
      fixture.detectChanges();

      expect(text()).toContain(en['trip.error.stylistFailed']);
      expect(header()).toContain('Berlin');
      expect(text()).toContain('Morning meetings');
      expect(text()).not.toContain(RAW_DETAIL);
    });

    // The six code-specific messages are the pack's, because the conditions are
    // the same either side of a packed trip. The general one is not.
    it('names the repack rather than the pack when the failure has no code', async () => {
      await loaded();

      press(en['trip.repack.action']);
      repackRequest().flush({ detail: RAW_DETAIL }, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(text()).toContain(en['trip.error.repackGeneral']);
      expect(text()).not.toContain(en['trip.error.general']);
    });

    // DECISIONS.md 202: the repack geocodes the stored string again, so a trip
    // that packed cleanly last week can answer this.
    it('shows the destination message when the geocoder no longer matches', async () => {
      await loaded();

      press(en['trip.repack.action']);
      repackRequest().flush(
        { detail: RAW_DETAIL, code: 'destination_not_found' },
        { status: 400, statusText: 'Bad Request' },
      );
      fixture.detectChanges();

      expect(text()).toContain(en['trip.error.destinationNotFound']);
    });

    it('clears the failure when the next repack succeeds', async () => {
      await loaded();
      press(en['trip.repack.action']);
      repackRequest().flush({ detail: RAW_DETAIL }, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      press(en['trip.repack.action']);
      fixture.detectChanges();

      expect(text()).not.toContain(en['trip.error.repackGeneral']);
      repackRequest().flush(repacked());
    });

    it('cannot be asked for twice while one is running', async () => {
      await loaded();
      press(en['trip.repack.action']);

      expect(button(en['trip.repack.action']).disabled).toBe(true);
      expect(button(en['trip.delete.idle']).disabled).toBe(true);
      repackRequest().flush(repacked());
    });
  });

  // DECISIONS.md 126: two deliberate presses, because the gate's confirm()
  // returns undefined and a confirm-guarded delete would never run.
  describe('delete', () => {
    it('arms on the first press and sends nothing', async () => {
      await loaded();

      press(en['trip.delete.idle']);

      expect(text()).toContain(en['trip.delete.armed']);
      mock.expectNone(`${environment.apiUrl}/trips/${currentId}`);
    });

    it('deletes on the second press', async () => {
      await loaded();

      press(en['trip.delete.idle']);
      press(en['trip.delete.armed']);

      const request = deleteRequest();
      expect(request.request.method).toBe('DELETE');
      request.flush(null, { status: 204, statusText: 'No Content' });
    });

    it('says so while the delete is in flight', async () => {
      await loaded();
      press(en['trip.delete.idle']);
      press(en['trip.delete.armed']);

      expect(text()).toContain(en['trip.delete.doing']);
      expect(button(en['trip.delete.doing']).disabled).toBe(true);
      deleteRequest().flush(null, { status: 204, statusText: 'No Content' });
    });

    it('goes back to the wardrobe once the trip is gone', async () => {
      await loaded();
      press(en['trip.delete.idle']);
      press(en['trip.delete.armed']);
      deleteRequest().flush(null, { status: 204, statusText: 'No Content' });
      await fixture.whenStable();

      expect(router.url).toBe('/wardrobe');
    });

    it('disarms on blur', async () => {
      await loaded();
      press(en['trip.delete.idle']);

      button(en['trip.delete.armed']).dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      expect(text()).toContain(en['trip.delete.idle']);
      expect(text()).not.toContain(en['trip.delete.armed']);
    });

    // The "any other interaction" half of 126's rule: an armed delete surviving
    // a twenty-second repack is a press landing on a control the user stopped
    // thinking about.
    it('disarms when a repack is asked for', async () => {
      await loaded();
      press(en['trip.delete.idle']);

      press(en['trip.repack.action']);
      repackRequest().flush(repacked());
      fixture.detectChanges();

      expect(text()).not.toContain(en['trip.delete.armed']);
    });

    it('keeps the trip on screen when the delete fails', async () => {
      await loaded();
      press(en['trip.delete.idle']);
      press(en['trip.delete.armed']);
      deleteRequest().flush({ detail: RAW_DETAIL }, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(text()).toContain(en['trip.error.delete']);
      expect(header()).toContain('Berlin');
      expect(router.url).not.toBe('/wardrobe');
      expect(text()).not.toContain(RAW_DETAIL);
    });

    // A failed delete disarms, so a second attempt is two presses again rather
    // than one landing on a button the user last saw saying "Delete".
    it('needs arming again after a failure', async () => {
      await loaded();
      press(en['trip.delete.idle']);
      press(en['trip.delete.armed']);
      deleteRequest().flush({ detail: RAW_DETAIL }, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      press(en['trip.delete.idle']);

      expect(text()).toContain(en['trip.delete.armed']);
      mock.expectNone(`${environment.apiUrl}/trips/${currentId}`);
    });
  });

  // Task 4.6a. The component's own spec covers the badge, the spinner and the
  // sentence; this one covers what only the page can be wrong about — what goes
  // on the wire, what comes back, and what is remembered between two presses.
  describe('swap', () => {
    const SHIRT = { id: 'item-1', category: 'top', display_name: 'white shirt' } as const;
    const BOOTS = { id: 'item-2', category: 'shoes', display_name: 'brown boots' } as const;
    const HEELS = { id: 'item-3', category: 'shoes', display_name: 'black heels' } as const;

    // The shirt is worn on both days and the shoes on one each, which is what
    // makes the reuse arithmetic have an answer either way.
    function packed(): TripDetail {
      return {
        trip: trip({
          packing_list: {
            item_ids: ['item-1', 'item-2', 'item-3'],
            reuse_summary: { item_count: 3, look_count: 2, most_reused: null },
          },
        }),
        looks: [
          look({ id: 'look-1', items: [item(SHIRT), item(BOOTS)] }),
          look({ id: 'look-2', title: 'Dinner out', items: [item(SHIRT), item(HEELS)] }),
        ],
      };
    }

    // Day 1's boots replaced by trainers. Day 2 is untouched, which is the
    // acceptance criterion and also what lets a second swap be asked for on it.
    function bootsSwapped(): TripDetail {
      return {
        trip: trip({
          packing_list: {
            item_ids: ['item-1', 'item-3', 'item-4'],
            reuse_summary: { item_count: 3, look_count: 2, most_reused: null },
          },
        }),
        looks: [
          look({
            id: 'look-1',
            items: [
              item(SHIRT),
              item({ id: 'item-4', category: 'shoes', display_name: 'grey trainers' }),
            ],
          }),
          look({ id: 'look-2', title: 'Dinner out', items: [item(SHIRT), item(HEELS)] }),
        ],
      };
    }

    // The shirt gone from day 1 and still worn on day 2, which is the case the
    // still-worn line exists for.
    function shirtSwapped(): TripDetail {
      return {
        trip: trip({
          packing_list: {
            item_ids: ['item-1', 'item-2', 'item-3', 'item-5'],
            reuse_summary: { item_count: 4, look_count: 2, most_reused: null },
          },
        }),
        looks: [
          look({
            id: 'look-1',
            items: [
              item({ id: 'item-5', category: 'top', display_name: 'grey knit' }),
              item(BOOTS),
            ],
          }),
          look({ id: 'look-2', title: 'Dinner out', items: [item(SHIRT), item(HEELS)] }),
        ],
      };
    }

    // One date, two slots, and the shirt worn in both of them — the shape no
    // single-slot trip can produce and the one every criterion below needs.
    function packedTwoSlot(): TripDetail {
      return {
        trip: trip({
          days: [
            day({
              slots: [slot(), slot({ slot: 'evening', occasion: 'formal', look_id: 'look-2' })],
            }),
          ],
          packing_list: {
            item_ids: ['item-1', 'item-2', 'item-3'],
            reuse_summary: { item_count: 3, look_count: 2, most_reused: null },
          },
        }),
        looks: [
          look({ id: 'look-1', items: [item(SHIRT), item(BOOTS)] }),
          look({ id: 'look-2', title: 'Dinner out', items: [item(SHIRT), item(HEELS)] }),
        ],
      };
    }

    // The shirt gone from the day look and still worn that evening, on the one
    // date the trip has.
    function shirtSwappedTwoSlot(): TripDetail {
      const base = packedTwoSlot();
      return {
        trip: base.trip,
        looks: [
          look({
            id: 'look-1',
            items: [
              item({ id: 'item-5', category: 'top', display_name: 'grey knit' }),
              item(BOOTS),
            ],
          }),
          look({ id: 'look-2', title: 'Dinner out', items: [item(SHIRT), item(HEELS)] }),
        ],
      };
    }

    function fail(code: string | null, status: number): void {
      swapRequest().flush(code === null ? { detail: RAW_DETAIL } : { detail: RAW_DETAIL, code }, {
        status,
        statusText: 'Failed',
      });
      fixture.detectChanges();
    }

    it('sends the day, the garment, its role and the exclusions', async () => {
      await loaded(packed());

      badges()[1].click();
      fixture.detectChanges();

      const request = swapRequest();
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({
        day: 1,
        slot: 'day',
        item_id: 'item-2',
        replace_role: 'shoes',
        exclude_item_ids: ['item-2'],
      });
      request.flush(bootsSwapped());
    });

    it('re-renders the trip from the response', async () => {
      await loaded(packed());
      badges()[1].click();
      fixture.detectChanges();
      swapRequest().flush(bootsSwapped());
      fixture.detectChanges();

      expect(lookItems(0)).toEqual(['white shirt', 'grey trainers']);
      expect(text()).toContain('grey trainers');
      expect(text()).not.toContain('brown boots');
      expect(text()).not.toContain(RAW_DETAIL);
    });

    // STAGE-4 4.6a's first criterion. Day 2's look is asserted whole, because a
    // swap that propagated would apply a judgement made at 12°C and rain to a
    // day dressed at 17°C and dry.
    it('changes the named day and no other', async () => {
      await loaded(packed());
      badges()[1].click();
      fixture.detectChanges();
      swapRequest().flush(bootsSwapped());
      fixture.detectChanges();

      expect(lookItems(0)).toEqual(['white shirt', 'grey trainers']);
      expect(lookItems(1)).toEqual(['white shirt', 'black heels']);
    });

    // The day on the wire is the section the badge sits in. There is no
    // selection any more, so the page is handed the day by the loop that drew
    // the badge rather than reading one off a signal. DECISIONS.md 222.
    it('sends the day whose section the badge was pressed in', async () => {
      await loaded(packed());

      badges(1)[1].click();
      fixture.detectChanges();

      expect(swapRequest().request.body).toMatchObject({ day: 2, item_id: 'item-3' });
    });

    // A second tap on one day is "not that one either", so the rejected garment
    // and the one that replaced it are both excluded from the third answer.
    it('accumulates the exclusions across two taps on one day', async () => {
      await loaded(packed());
      badges()[1].click();
      fixture.detectChanges();
      swapRequest().flush(bootsSwapped());
      fixture.detectChanges();

      badges()[1].click();
      fixture.detectChanges();

      expect(swapRequest().request.body).toMatchObject({
        exclude_item_ids: ['item-2', 'item-4'],
      });
    });

    // Per day, not per trip: the shoe that is wrong for Tuesday's rain is the
    // right answer for Thursday. A single shared list would send day 1's
    // rejection with day 2's request, which is what this asserts it does not.
    it("keeps one day's exclusions out of another day's request", async () => {
      await loaded(packed());
      badges()[1].click();
      fixture.detectChanges();
      swapRequest().flush(bootsSwapped());
      fixture.detectChanges();

      badges(1)[0].click();
      fixture.detectChanges();

      expect(swapRequest().request.body).toEqual({
        day: 2,
        slot: 'day',
        item_id: 'item-1',
        replace_role: 'top',
        exclude_item_ids: ['item-1'],
      });
    });

    // The exclusions belong to the looks they were exclusions from, and a
    // repack replaces every one of them against a fresh forecast.
    it('forgets the exclusions when the trip is re-packed', async () => {
      await loaded(packed());
      badges()[1].click();
      fixture.detectChanges();
      swapRequest().flush(bootsSwapped());
      fixture.detectChanges();

      press(en['trip.repack.action']);
      repackRequest().flush(repacked());
      fixture.detectChanges();

      badges()[0].click();
      fixture.detectChanges();

      expect(swapRequest().request.body).toMatchObject({ exclude_item_ids: ['item-1'] });
    });

    // STAGE-4 4.6a's third criterion: removing the jeans from Tuesday must not
    // read as taking them out of the suitcase while Thursday still wears them.
    it('names the days that still wear the garment that left', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      swapRequest().flush(shirtSwapped());
      fixture.detectChanges();

      expect(text()).toContain("You'll still wear the white shirt on Day 2.");
    });

    it('says nothing when the garment that left is worn nowhere else', async () => {
      await loaded(packed());
      badges()[1].click();
      fixture.detectChanges();
      swapRequest().flush(bootsSwapped());
      fixture.detectChanges();

      expect(text()).not.toContain('still wear');
    });

    // Under the day the garment left and under no other. The sentence is held
    // with the day it belongs to, because every day is on screen and a line
    // without one would print under all of them. DECISIONS.md 222.
    it('draws the still-worn line under the day that was swapped alone', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      swapRequest().flush(shirtSwapped());
      fixture.detectChanges();

      expect(dayText(0)).toContain('still wear');
      expect(dayText(1)).not.toContain('still wear');
    });

    it("locks the trip's own actions while a swap is running", async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();

      expect(badges()[0].disabled).toBe(true);
      // The other day's badges too: one request is in flight at a time across
      // the whole itinerary, so a badge that still depressed would be a press
      // with nowhere to go.
      expect(badges(1)[0].disabled).toBe(true);
      expect(button(en['trip.repack.action']).disabled).toBe(true);
      expect(button(en['trip.delete.idle']).disabled).toBe(true);
      swapRequest().flush(shirtSwapped());
    });

    // The shirt is worn on both days, and the spinner belongs to the tile that
    // was pressed. An id held without its day puts a wait on a garment nobody
    // touched, which is the failure the itinerary invented and the tab strip
    // could not have had. DECISIONS.md 222.
    it('draws the wait on the pressed day alone when the garment is worn twice', async () => {
      await loaded(packed());

      badges()[0].click();
      fixture.detectChanges();

      expect(spinners(0)).toBe(1);
      expect(spinners(1)).toBe(0);
      swapRequest().flush(shirtSwapped());
    });

    // 4.18's second criterion, and the day-scoped spinner above one level down.
    it('draws the wait on the pressed slot alone when the garment is worn in both', async () => {
      await loaded(packedTwoSlot());

      slotBadges(0, 0)[0].click();
      fixture.detectChanges();

      expect(slotSpinners(0, 0)).toBe(1);
      expect(slotSpinners(0, 1)).toBe(0);
      const request = swapRequest();
      expect(request.request.body).toMatchObject({ day: 1, slot: 'day' });
      request.flush(shirtSwappedTwoSlot());
    });

    it('sends the slot the badge was pressed in', async () => {
      await loaded(packedTwoSlot());

      slotBadges(0, 1)[0].click();
      fixture.detectChanges();

      const request = swapRequest();
      expect(request.request.body).toMatchObject({ day: 1, slot: 'evening' });
      request.flush(shirtSwappedTwoSlot());
    });

    // 4.18's third criterion. Naming only the day would print the date the
    // reader is looking at and read as a contradiction — the garment was just
    // taken off *this* day.
    it('names the evening when the garment it lost is still worn there', async () => {
      await loaded(packedTwoSlot());
      slotBadges(0, 0)[0].click();
      fixture.detectChanges();
      swapRequest().flush(shirtSwappedTwoSlot());
      fixture.detectChanges();

      expect(text()).toContain("You'll still wear the white shirt on Day 1 evening.");
    });

    // 4.18's fourth criterion. A shoe rejected for Monday's meetings is a
    // candidate again for Monday's dinner, which is the same sentence the
    // per-day exclusions already made about two dates.
    //
    // The two presses are on **different** garments on purpose: rejecting the
    // shirt on the day slot and then the heels on the evening is the only shape
    // that can tell a slot-keyed list from a day-keyed one. Pressing the same
    // garment twice sends the same single id either way, and a day-keyed map
    // survives that assertion untouched — measured, not assumed.
    it("keeps one slot's exclusions out of the other slot's request", async () => {
      await loaded(packedTwoSlot());
      slotBadges(0, 0)[0].click();
      fixture.detectChanges();
      swapRequest().flush(shirtSwappedTwoSlot());
      fixture.detectChanges();

      // The evening's heels, not its shirt.
      slotBadges(0, 1)[1].click();
      fixture.detectChanges();

      expect(swapRequest().request.body).toEqual({
        day: 1,
        slot: 'evening',
        item_id: 'item-3',
        replace_role: 'shoes',
        exclude_item_ids: ['item-3'],
      });
    });

    // 126's "any other interaction", the badge being one of them.
    it('disarms the delete', async () => {
      await loaded(packed());
      press(en['trip.delete.idle']);

      badges()[0].click();
      fixture.detectChanges();

      expect(text()).not.toContain(en['trip.delete.armed']);
      swapRequest().flush(shirtSwapped());
    });

    it("leaves the day's look on screen when the swap fails", async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('stylist_failed', 502);

      expect(text()).toContain('white shirt');
      expect(text()).toContain('Morning meetings');
      expect(header()).toContain('Berlin');
      expect(text()).not.toContain(RAW_DETAIL);
    });

    // DECISIONS.md 207's reasoning one screen along: "We couldn't pack this
    // trip just now" is the wrong sentence in answer to a tap on one shoe.
    it('names the swap rather than the pack when the stylist fails', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('stylist_failed', 502);

      expect(text()).toContain(en['trip.error.swapStylistFailed']);
      expect(text()).not.toContain(en['trip.error.stylistFailed']);
    });

    // Six, not eight: the swap runs the single-day rule order, where rule 11
    // never runs. DECISIONS.md 209.
    it("asks for six tagged items rather than the pack's eight", async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('wardrobe_too_small', 400);

      expect(text()).toContain(en['trip.error.swapWardrobeTooSmall']);
      expect(text()).not.toContain(en['trip.error.wardrobeTooSmall']);
    });

    it('explains a stale badge', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('item_not_in_look', 422);

      expect(text()).toContain(en['trip.error.itemNotInLook']);
    });

    it('explains a garment archived from another tab', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('locked_unavailable', 422);

      expect(text()).toContain(en['trip.error.lockedUnavailable']);
    });

    // Unmapped on purpose, so it lands on the general line rather than on a
    // sentence about a trip that cannot be found or a badge that is stale.
    it('falls back to the general message on validation_error', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('validation_error', 422);

      expect(text()).toContain(en['trip.error.swapGeneral']);
      expect(text()).not.toContain(en['trip.error.notFound']);
      expect(text()).not.toContain(en['trip.error.itemNotInLook']);
      expect(text()).not.toContain(en['trip.error.validation']);
    });

    it('falls back to the general message when the failure carries no code', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail(null, 500);

      expect(text()).toContain(en['trip.error.swapGeneral']);
    });

    // The message is about one day's look, so it is drawn under that day and
    // under no other — which is what the page's actionError above the buttons
    // would have said instead.
    it('shows the failure under the day the swap was asked for', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('stylist_failed', 502);

      expect(dayText(0)).toContain(en['trip.error.swapStylistFailed']);
      expect(dayText(1)).not.toContain(en['trip.error.swapStylistFailed']);
    });

    it('clears the failure when the next swap is asked for', async () => {
      await loaded(packed());
      badges()[0].click();
      fixture.detectChanges();
      fail('stylist_failed', 502);

      badges()[0].click();
      fixture.detectChanges();

      expect(text()).not.toContain(en['trip.error.swapStylistFailed']);
      swapRequest().flush(shirtSwapped());
    });
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { LocationResult } from '../../shared/models/location.model';
import {
  MAX_TRIP_DAYS,
  SEARCH_DEBOUNCE_MS,
  TripDraft,
  TripForm,
  daysInRange,
  newTripDraft,
  tripHorizon,
  tripProblem,
} from './trip-form';

let fixture: ComponentFixture<TripForm>;
let mock: HttpTestingController;
let emitted: TripDraft[] = [];
let submits = 0;

function berlin(overrides: Partial<LocationResult> = {}): LocationResult {
  return { name: 'Berlin', country: 'Germany', lat: 52.52437, lon: 13.41053, ...overrides };
}

function draft(overrides: Partial<TripDraft> = {}): TripDraft {
  return {
    destination: berlin(),
    start_date: '2026-03-14',
    end_date: '2026-03-17',
    occasions: ['casual', 'casual', 'casual', 'casual'],
    notes: '',
    ...overrides,
  };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

async function render(initial: TripDraft = draft()): Promise<void> {
  fixture = TestBed.createComponent(TripForm);
  fixture.componentRef.setInput('draft', initial);
  fixture.componentInstance.draftChanged.subscribe((next) => emitted.push(next));
  fixture.componentInstance.submitted.subscribe(() => submits++);
  fixture.detectChanges();
  await fixture.whenStable();
  vi.useFakeTimers();
}

function field(id: string): HTMLInputElement {
  return element().querySelector<HTMLInputElement>(`#${id}`)!;
}

function legends(): string[] {
  return [...element().querySelectorAll('legend')].map((one) => one.textContent?.trim() ?? '');
}

function chipRows(): HTMLButtonElement[][] {
  return [...element().querySelectorAll('fieldset')].map((row) => [
    ...row.querySelectorAll('button'),
  ]);
}

function pressed(row: number): string[] {
  const chips = chipRows()[row];
  return chips
    .filter((chip) => chip.getAttribute('aria-pressed') === 'true')
    .map((chip) => chip.textContent?.trim() ?? '');
}

function submitButton(): HTMLButtonElement {
  return element().querySelector<HTMLButtonElement>('button[type=submit]')!;
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

function searchFor(value: string): void {
  typeInto('trip_destination', value);
  vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
  TestBed.tick();
}

function searchRequest(q: string) {
  return mock.expectOne(
    (candidate) =>
      candidate.url === `${environment.apiUrl}/me/locations/search` &&
      candidate.params.get('q') === q,
  );
}

function last(): TripDraft {
  return emitted[emitted.length - 1];
}

describe('daysInRange', () => {
  it('counts both ends of the range', () => {
    expect(daysInRange('2026-03-14', '2026-03-17')).toBe(4);
  });

  it('counts a single day as one', () => {
    expect(daysInRange('2026-03-14', '2026-03-14')).toBe(1);
  });

  // The reason the parse is UTC. 29 March 2026 is the European clock change:
  // local midnights either side of it are 23 hours apart, and a local-time
  // subtraction rounds this range down by a day.
  it('is not shortened by a daylight-saving change inside the range', () => {
    expect(daysInRange('2026-03-28', '2026-03-30')).toBe(3);
  });

  it('is not a date when the field is empty', () => {
    expect(daysInRange('', '2026-03-17')).toBe(0);
  });
});

describe('tripProblem', () => {
  it('passes a well-formed draft', () => {
    expect(tripProblem(draft())).toBeNull();
  });

  it('names the destination before anything else', () => {
    expect(tripProblem(draft({ destination: null }))).toBe('trip.problem.noDestination');
  });

  it('refuses a range that ends before it starts', () => {
    expect(tripProblem(draft({ start_date: '2026-03-17', end_date: '2026-03-14' }))).toBe(
      'trip.problem.endBeforeStart',
    );
  });

  // The inverted range is checked first because its length is negative, and a
  // length message on it would name a number no client could satisfy.
  it('calls an inverted range inverted rather than too long', () => {
    expect(tripProblem(draft({ start_date: '2027-03-17', end_date: '2026-03-14' }))).toBe(
      'trip.problem.endBeforeStart',
    );
  });

  it('accepts a trip of exactly the maximum length', () => {
    expect(tripProblem(draft({ start_date: '2026-03-01', end_date: '2026-03-14' }))).toBeNull();
  });

  it('refuses one day more than the maximum', () => {
    expect(tripProblem(draft({ start_date: '2026-03-01', end_date: '2026-03-15' }))).toBe(
      'trip.problem.tooLong',
    );
  });
});

describe('newTripDraft', () => {
  it('opens on a one-day casual trip today, with no destination', () => {
    const fresh = newTripDraft(new Date(2026, 2, 14, 9));

    expect(fresh).toEqual({
      destination: null,
      start_date: '2026-03-14',
      end_date: '2026-03-14',
      occasions: ['casual'],
      notes: '',
    });
  });
});

describe('tripHorizon', () => {
  // The trip bound, not the provider's. `look-request-form.ts` caps a single
  // day at 15 measured against Open-Meteo; this is 14 by DECISIONS.md 190, and
  // the two are deliberately different numbers.
  it('is the maximum trip length ahead of today', () => {
    expect(tripHorizon(new Date(2026, 2, 14, 9))).toBe('2026-03-28');
  });

  it('is local rather than UTC', () => {
    expect(tripHorizon(new Date(2026, 2, 14, 23, 50))).toBe('2026-03-28');
  });
});

describe('TripForm', () => {
  beforeEach(async () => {
    emitted = [];
    submits = 0;
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);

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

  it('draws one occasion row per day, in day order', async () => {
    await render();

    expect(legends()).toEqual(['Day 1', 'Day 2', 'Day 3', 'Day 4']);
  });

  it('shows each day its own occasion', async () => {
    await render(draft({ occasions: ['work', 'casual', 'evening', 'casual'] }));

    expect(pressed(0)).toEqual(['Work']);
    expect(pressed(2)).toEqual(['Evening']);
  });

  // Row 3, chip 2. Written with two different indices on purpose: the chip
  // rows are a nested @for, whose inner $index shadows the day's, and an
  // expectation using the same number for both cannot see that.
  it('changes one day without touching the others', async () => {
    await render();
    chipRows()[2][1].click();
    TestBed.tick();

    expect(last().occasions).toEqual(['casual', 'casual', 'work', 'casual']);
  });

  // A day has no "no occasion" to fall back to, so the chip row cannot clear
  // the way the wardrobe's filter chips can — the request needs one entry per
  // day and an empty row would arm a button that 422s.
  it('leaves the chosen occasion chosen when it is tapped again', async () => {
    await render(draft({ occasions: ['work', 'casual', 'casual', 'casual'] }));
    chipRows()[0][1].click();
    TestBed.tick();

    expect(last().occasions[0]).toBe('work');
  });

  it('grows the occasion rows when the range is extended', async () => {
    await render();
    changeDate('trip_end', '2026-03-19');

    expect(last().occasions).toEqual(['casual', 'casual', 'casual', 'casual', 'casual', 'casual']);
  });

  it('keeps the occasions already chosen when the range grows', async () => {
    await render(draft({ occasions: ['work', 'evening', 'casual', 'casual'] }));
    changeDate('trip_end', '2026-03-18');

    expect(last().occasions).toEqual(['work', 'evening', 'casual', 'casual', 'casual']);
  });

  it('drops the trailing occasions when the range shrinks', async () => {
    await render(draft({ occasions: ['work', 'evening', 'sport', 'formal'] }));
    changeDate('trip_end', '2026-03-15');

    expect(last().occasions).toEqual(['work', 'evening']);
  });

  it('resizes from the start date too', async () => {
    await render();
    changeDate('trip_start', '2026-03-16');

    expect(last().occasions).toHaveLength(2);
  });

  // An empty date input is a cleared field, not a date: emitting it would send
  // `start_date: ""` and collect a 422 for it.
  it('ignores a cleared date rather than emitting an empty one', async () => {
    await render();
    changeDate('trip_start', '');

    expect(emitted).toHaveLength(0);
  });

  it('caps both date inputs at the trip horizon', async () => {
    await render();

    expect(field('trip_start').getAttribute('max')).toBe(tripHorizon());
    expect(field('trip_end').getAttribute('max')).toBe(tripHorizon());
  });

  // DECISIONS.md 201 leaves `start_date` unbounded below on the server, because
  // a floor on the server's calendar day is a refusal a browser east of UTC
  // earns by its timezone. A `min` here would enforce a rule the API refuses.
  it('puts no lower bound on either date', async () => {
    await render();

    expect(field('trip_start').getAttribute('min')).toBeNull();
    expect(field('trip_end').getAttribute('min')).toBeNull();
  });

  it('does not search until the query reaches two characters', async () => {
    await render(draft({ destination: null }));
    searchFor('b');

    mock.expectNone(() => true);
  });

  it('searches once the debounce has passed', async () => {
    await render(draft({ destination: null }));
    searchFor('berlin');
    searchRequest('berlin').flush({ results: [berlin()] });
    TestBed.tick();

    expect(text()).toContain('Berlin, Germany');
  });

  it('does not search on every keystroke', async () => {
    await render(draft({ destination: null }));
    typeInto('trip_destination', 'be');
    typeInto('trip_destination', 'ber');
    searchFor('berl');
    searchRequest('berl').flush({ results: [] });
  });

  // Debouncing makes two searches in flight uncommon rather than impossible,
  // and the failure it prevents is a slow "ber" landing on top of a fast
  // "berlin" and offering the wrong five cities.
  it('drops an answer to a search the user has moved on from', async () => {
    await render(draft({ destination: null }));
    searchFor('ber');
    const stale = searchRequest('ber');
    searchFor('berlin');
    const fresh = searchRequest('berlin');

    fresh.flush({ results: [berlin()] });
    stale.flush({ results: [berlin({ name: 'Bern', country: 'Switzerland' })] });
    TestBed.tick();

    expect(text()).toContain('Berlin, Germany');
    expect(text()).not.toContain('Bern');
  });

  it('says so when nothing matches', async () => {
    await render(draft({ destination: null }));
    searchFor('zzzz');
    searchRequest('zzzz').flush({ results: [] });
    TestBed.tick();

    expect(text()).toContain(en['trip.destination.noResults']);
  });

  it('reports a failed search without blaming the spelling', async () => {
    await render(draft({ destination: null }));
    searchFor('berlin');
    searchRequest('berlin').flush(
      { detail: 'x', code: 'geocoding_unavailable' },
      { status: 502, statusText: 'Bad Gateway' },
    );
    TestBed.tick();

    expect(text()).toContain(en['trip.destination.error']);
    expect(text()).not.toContain(en['trip.destination.noResults']);
  });

  it('emits the whole result when one is chosen', async () => {
    await render(draft({ destination: null }));
    searchFor('berlin');
    searchRequest('berlin').flush({ results: [berlin()] });
    TestBed.tick();
    element().querySelector<HTMLButtonElement>('li button')!.click();
    TestBed.tick();

    expect(last().destination).toEqual(berlin());
  });

  it('replaces the search box with the chosen place', async () => {
    await render();

    expect(element().querySelector('#trip_destination')).toBeNull();
    expect(text()).toContain('Berlin, Germany');
  });

  it('brings the search box back when the place is cleared', async () => {
    await render();
    element().querySelector<HTMLButtonElement>('button[aria-label]')!.click();
    TestBed.tick();

    expect(last().destination).toBeNull();
  });

  it('sends notes as typed', async () => {
    await render();
    const notes = element().querySelector<HTMLTextAreaElement>('#trip_notes')!;
    notes.value = 'one dinner out';
    notes.dispatchEvent(new Event('input'));
    TestBed.tick();

    expect(last().notes).toBe('one dinner out');
  });

  it('submits a well-formed draft', async () => {
    await render();
    submitButton().click();
    TestBed.tick();

    expect(submits).toBe(1);
  });

  it('disables the button and names the problem when there is no destination', async () => {
    await render(draft({ destination: null }));

    expect(submitButton().disabled).toBe(true);
    expect(text()).toContain(en['trip.problem.noDestination']);
  });

  it('disables the button on an inverted range', async () => {
    await render(draft({ start_date: '2026-03-17', end_date: '2026-03-14', occasions: [] }));

    expect(submitButton().disabled).toBe(true);
    expect(text()).toContain(en['trip.problem.endBeforeStart']);
  });

  it('disables the button past the maximum length', async () => {
    await render(
      draft({
        start_date: '2026-03-01',
        end_date: '2026-03-15',
        occasions: Array.from({ length: MAX_TRIP_DAYS + 1 }, () => 'casual' as const),
      }),
    );

    expect(submitButton().disabled).toBe(true);
    expect(text()).toContain(en['trip.problem.tooLong']);
  });

  // Enter in a text input inside a form submits the form. A half-typed city
  // name must not spend the most expensive call in the project.
  it('searches rather than submitting when Enter is pressed in the search box', async () => {
    await render(draft({ destination: null }));
    field('trip_destination').dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
    );
    TestBed.tick();

    expect(submits).toBe(0);
  });
});

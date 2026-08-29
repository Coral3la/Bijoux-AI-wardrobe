import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { Look } from '../../shared/models/look.model';
import { LooksStore } from './looks.store';

let store: LooksStore;
let mock: HttpTestingController;

function look(overrides: Partial<Look> = {}): Look {
  return {
    id: 'look-1',
    occasion: 'work',
    title: 'Morning meetings',
    items: [],
    reasoning: 'The blazer lifts the knit.',
    weather_note: 'Mild at 19°C.',
    is_saved: true,
    ...overrides,
  };
}

beforeEach(() => {
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  store = TestBed.inject(LooksStore);
  mock = TestBed.inject(HttpTestingController);
  store.reset();
});

afterEach(() => {
  mock.verify();
});

describe('LooksStore.loadSaved', () => {
  it('asks for saved looks only', () => {
    store.loadSaved();

    const request = mock.expectOne((candidate) => candidate.url === `${environment.apiUrl}/looks`);
    // Transcribed rather than read off the store: the filter is the whole of
    // what makes this the saved-looks screen and not a list of every
    // suggestion ever made.
    expect(request.request.params.get('is_saved')).toBe('true');
    request.flush({ looks: [], total: 0 });
  });

  it('holds the looks the server returned', () => {
    store.loadSaved();
    mock.expectOne(`${environment.apiUrl}/looks?is_saved=true`).flush({
      looks: [look(), look({ id: 'look-2' })],
      total: 2,
    });

    expect(store.looks().map((entry) => entry.id)).toEqual(['look-1', 'look-2']);
    expect(store.isLoading()).toBe(false);
  });

  it('reports a failure and stops loading', () => {
    store.loadSaved();
    mock
      .expectOne(`${environment.apiUrl}/looks?is_saved=true`)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    expect(store.error()).toBe('looks.error.load');
    expect(store.isLoading()).toBe(false);
  });

  it('raises isLoading while the request is in flight', () => {
    store.loadSaved();
    expect(store.isLoading()).toBe(true);

    mock.expectOne(`${environment.apiUrl}/looks?is_saved=true`).flush({ looks: [], total: 0 });
  });
});

describe('LooksStore.update', () => {
  it('sends only the fields it was given', () => {
    store.update('look-1', { is_saved: false });

    const request = mock.expectOne(`${environment.apiUrl}/looks/look-1`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ is_saved: false });
    request.flush(look({ is_saved: false }));
  });

  it('replaces the look in the list rather than removing it', () => {
    store.loadSaved();
    mock
      .expectOne(`${environment.apiUrl}/looks?is_saved=true`)
      .flush({ looks: [look(), look({ id: 'look-2' })], total: 2 });

    store.update('look-1', { is_saved: false });
    mock.expectOne(`${environment.apiUrl}/looks/look-1`).flush(look({ is_saved: false }));

    // Still two rows. Taking the row away under the finger that unsaved it
    // makes the tap uncorrectable; leaving it with an empty heart makes it one
    // tap back, and the next load is where it actually goes.
    expect(store.looks().map((entry) => entry.id)).toEqual(['look-1', 'look-2']);
    expect(store.looks()[0].is_saved).toBe(false);
  });

  it('exposes the updated look so a screen holding its own copy can prefer it', () => {
    store.update('look-1', { is_saved: true });
    mock.expectOne(`${environment.apiUrl}/looks/look-1`).flush(look({ is_saved: true }));

    expect(store.updated()?.id).toBe('look-1');
    expect(store.updated()?.is_saved).toBe(true);
  });

  it('marks which look is being written and clears it after', () => {
    store.update('look-1', { is_saved: true });
    expect(store.updatingId()).toBe('look-1');

    mock.expectOne(`${environment.apiUrl}/looks/look-1`).flush(look());
    expect(store.updatingId()).toBeNull();
  });

  it('drops a second write while one is in flight', () => {
    store.update('look-1', { is_saved: true });
    store.update('look-2', { is_saved: true });

    mock.expectOne(`${environment.apiUrl}/looks/look-1`).flush(look());
    // The second never left: expectNone would pass on a store that queued it,
    // so the guard is measured by verify() finding nothing outstanding.
    mock.expectNone(`${environment.apiUrl}/looks/look-2`);
  });

  it('reads the documented code rather than the status', () => {
    store.update('look-1', { is_saved: true });
    mock
      .expectOne(`${environment.apiUrl}/looks/look-1`)
      .flush(
        { detail: 'Look not found.', code: 'not_found' },
        { status: 404, statusText: 'Not Found' },
      );

    expect(store.error()).toBe('looks.error.notFound');
    expect(store.updatingId()).toBeNull();
  });

  it('falls back to the general message on a code it does not know', () => {
    store.update('look-1', { is_saved: true });
    mock
      .expectOne(`${environment.apiUrl}/looks/look-1`)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    expect(store.error()).toBe('looks.error.general');
  });

  it('leaves the list untouched when the write fails', () => {
    store.loadSaved();
    mock
      .expectOne(`${environment.apiUrl}/looks?is_saved=true`)
      .flush({ looks: [look()], total: 1 });

    store.update('look-1', { is_saved: false });
    mock
      .expectOne(`${environment.apiUrl}/looks/look-1`)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    expect(store.looks()[0].is_saved).toBe(true);
  });
});

describe('LooksStore.reset', () => {
  it('empties everything the previous visit left behind', () => {
    store.loadSaved();
    mock
      .expectOne(`${environment.apiUrl}/looks?is_saved=true`)
      .flush({ looks: [look()], total: 1 });

    store.reset();

    expect(store.looks()).toEqual([]);
    expect(store.updated()).toBeNull();
    expect(store.error()).toBeNull();
  });
});

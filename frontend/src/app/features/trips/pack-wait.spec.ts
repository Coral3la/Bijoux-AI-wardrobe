import { HttpErrorResponse } from '@angular/common/http';
import { Signal, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { STATUS_INTERVAL_MS, packErrorKey, packStatus } from './pack-wait';

// Distinctive on purpose: a fallback the caller passes has to be able to fail
// the assertion that it was used.
const FALLBACK = 'the-callers-own-fallback';

function failure(code: string | undefined, status = 400): HttpErrorResponse {
  return new HttpErrorResponse({
    error: code === undefined ? { detail: 'no code here' } : { detail: 'x', code },
    status,
    statusText: 'Error',
  });
}

describe('packErrorKey', () => {
  // Every code 04-API-SPEC.md lists for both endpoints, asserted one by one
  // rather than looped over the map: a loop reading the table under test passes
  // for a table with an entry missing.
  it.each([
    ['trip_too_long', 'trip.error.tripTooLong'],
    ['wardrobe_too_small', 'trip.error.wardrobeTooSmall'],
    ['destination_not_found', 'trip.error.destinationNotFound'],
    ['geocoding_unavailable', 'trip.error.geocodingUnavailable'],
    ['forecast_unavailable', 'trip.error.forecastUnavailable'],
    ['stylist_failed', 'trip.error.stylistFailed'],
    ['validation_error', 'trip.error.validation'],
  ])('maps %s to its own message', (code, key) => {
    expect(packErrorKey(failure(code), FALLBACK)).toBe(key);
  });

  // The code is read before the status, which is what lets one code arrive at
  // two statuses and say one thing: forecast_unavailable is a 400 past the
  // horizon and a 502 when Open-Meteo does not answer.
  it('reads the code rather than the status', () => {
    expect(packErrorKey(failure('forecast_unavailable', 502), FALLBACK)).toBe(
      'trip.error.forecastUnavailable',
    );
  });

  // A body the request schema rejects carries FastAPI's detail and no code, so
  // the status is the only thing left to branch on.
  it('reads a 422 with no code as a validation failure', () => {
    expect(packErrorKey(failure(undefined, 422), FALLBACK)).toBe('trip.error.validation');
  });

  it('falls back for a code it does not know', () => {
    expect(packErrorKey(failure('brand_new_code'), FALLBACK)).toBe(FALLBACK);
  });

  it('falls back for a 500 with no code', () => {
    expect(packErrorKey(failure(undefined, 500), FALLBACK)).toBe(FALLBACK);
  });

  // A failure that never reached the network layer — a bug in the callback, a
  // parse error — is not an HttpErrorResponse and must not read `.error` off it.
  it('falls back for something that is not an HTTP failure', () => {
    expect(packErrorKey(new Error('boom'), FALLBACK)).toBe(FALLBACK);
  });

  // The fallback is the caller's, and the two callers pass different ones: the
  // pack says "We couldn't pack this trip" and the repack may not, because it
  // renders under a trip that is visibly packed.
  it('uses the fallback it was given rather than one of its own', () => {
    expect(packErrorKey(new Error('boom'), 'trip.error.repackGeneral')).toBe(
      'trip.error.repackGeneral',
    );
  });
});

describe('packStatus', () => {
  let active: ReturnType<typeof signal<boolean>>;
  let key: Signal<string>;

  function flush(): void {
    TestBed.tick();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({});
    active = signal(false);
    key = TestBed.runInInjectionContext(() => packStatus(active));
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts on the first line', () => {
    flush();

    expect(key()).toBe('trip.waiting.geocoding');
  });

  it('starts no interval while the caller is idle', () => {
    flush();
    vi.advanceTimersByTime(STATUS_INTERVAL_MS * 3);
    flush();

    expect(key()).toBe('trip.waiting.geocoding');
  });

  it('moves through the lines in the order the server takes the steps', () => {
    active.set(true);
    flush();

    for (const expected of [
      'trip.waiting.forecast',
      'trip.waiting.wardrobe',
      'trip.waiting.assembling',
    ]) {
      vi.advanceTimersByTime(STATUS_INTERVAL_MS);
      flush();
      expect(key()).toBe(expected);
    }
  });

  // Clamped, not wrapped: a line that comes back round claims work that is
  // behind us, and this wait has no known length.
  it('rests on the last line rather than starting over', () => {
    active.set(true);
    flush();
    vi.advanceTimersByTime(STATUS_INTERVAL_MS * 12);
    flush();

    expect(key()).toBe('trip.waiting.assembling');
  });

  it('stops the interval when the caller goes idle', () => {
    active.set(true);
    flush();
    vi.advanceTimersByTime(STATUS_INTERVAL_MS);
    flush();
    active.set(false);
    flush();
    vi.advanceTimersByTime(STATUS_INTERVAL_MS * 5);
    flush();

    expect(key()).toBe('trip.waiting.forecast');
  });

  // The half a second caller would otherwise have to remember: a repack that
  // failed and is asked for again starts where the server starts.
  it('starts over from the first line on the next run', () => {
    active.set(true);
    flush();
    vi.advanceTimersByTime(STATUS_INTERVAL_MS * 2);
    flush();
    active.set(false);
    flush();
    active.set(true);
    flush();

    expect(key()).toBe('trip.waiting.geocoding');
  });
});

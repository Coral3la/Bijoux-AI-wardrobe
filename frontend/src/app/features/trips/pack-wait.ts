import { HttpErrorResponse } from '@angular/common/http';
import { Signal, computed, effect, signal } from '@angular/core';

// Four lines for a wait nobody has measured, so the last one is reached at nine
// seconds and rested on. The endpoint geocodes, fetches up to fourteen days of
// forecast, then makes one model call carrying the whole wardrobe — these name
// the four steps in the order the server takes them, and none of them names a
// duration, because no number has been taken.
//
// A repack takes the same four steps: DECISIONS.md 202 has it re-geocode the
// stored destination rather than reuse the columns, so even the first line is
// true of both callers.
const STATUS_KEYS = [
  'trip.waiting.geocoding',
  'trip.waiting.forecast',
  'trip.waiting.wardrobe',
  'trip.waiting.assembling',
] as const;

export const STATUS_INTERVAL_MS = 3000;

// Branch on the documented code, never on the status — the rule the stylist
// store follows, and `forecast_unavailable` is why it matters: it is issued at
// two statuses, 400 past the horizon and 502 when Open-Meteo does not answer,
// and both say one thing to the user.
//
// `home_location_missing` is deliberately absent. It is `POST /looks/suggest`'s
// code, for an account with no home coordinates; neither of these endpoints
// reads them, and 04-API-SPEC.md's failure lists do not carry the code either.
const PACK_ERROR_KEYS: Readonly<Record<string, string>> = {
  trip_too_long: 'trip.error.tripTooLong',
  wardrobe_too_small: 'trip.error.wardrobeTooSmall',
  destination_not_found: 'trip.error.destinationNotFound',
  geocoding_unavailable: 'trip.error.geocodingUnavailable',
  forecast_unavailable: 'trip.error.forecastUnavailable',
  stylist_failed: 'trip.error.stylistFailed',
  validation_error: 'trip.error.validation',
};

interface ApiErrorBody {
  readonly code?: string;
}

// `fallbackKey` is required rather than defaulted to the pack sentence. The six
// code-specific messages describe conditions and read the same either side of a
// packed trip; the general one describes the act, and "We couldn't pack this
// trip" under a trip that is visibly packed is the sentence a default would
// have handed the repack silently.
export function packErrorKey(error: unknown, fallbackKey: string): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as ApiErrorBody | null)?.code;
    if (code !== undefined && code in PACK_ERROR_KEYS) {
      return PACK_ERROR_KEYS[code];
    }
    // The one status this file reads, and it is read last, after every
    // documented code has failed to match. A body the request schema rejects
    // carries FastAPI's `detail` rather than `code`, so there is nothing else
    // to branch on. A repack sends no body at all, so it can only reach this
    // line through a malformed id, which is the same 422 without a `code`.
    if (error.status === 422) {
      return PACK_ERROR_KEYS['validation_error'];
    }
  }
  return fallbackKey;
}

// Called from an injection context, and the returned signal is the whole of the
// caller's involvement: there is no start, no stop and no handle to lose, so a
// second caller cannot forget the half 4.5 had to remember.
//
// The cycle follows `active` rather than being driven beside it. 4.5 guarded
// against a second interval started over a live one; `onCleanup` makes that
// unreachable instead — it clears the previous interval before the effect runs
// again, and on destroy.
export function packStatus(active: Signal<boolean>): Signal<string> {
  const index = signal(0);

  effect((onCleanup) => {
    if (!active()) {
      return;
    }
    // Reset on the way in, not on the way out: a repack that fails and is asked
    // for again starts at "Finding your destination…", which is where the
    // server starts too.
    index.set(0);
    const timer = setInterval(() => {
      // Clamped, not wrapped. A line that comes back round claims work that is
      // behind us, and this wait has no known length — so the last line is
      // where it rests.
      index.update((current) => Math.min(current + 1, STATUS_KEYS.length - 1));
    }, STATUS_INTERVAL_MS);
    onCleanup(() => clearInterval(timer));
  });

  return computed(() => STATUS_KEYS[index()]);
}

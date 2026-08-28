import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';

import { LooksApi } from '../api/looks.api';
import { WeatherApi } from '../api/weather.api';
import { AuthService } from '../auth/auth.service';
import { SuggestRequest, SuggestResponse } from '../../shared/models/look.model';
import { Weather } from '../../shared/models/weather.model';

interface ApiErrorBody {
  readonly code?: string;
}

// The same rule the wardrobe store's two error readers follow: branch on the
// documented code, never on the status. It matters more here than anywhere
// before it — `forecast_unavailable` is the first code in this project issued
// at two statuses, 400 past the forecast horizon and 502 when Open-Meteo does
// not answer, and both say one thing to the user (DECISIONS.md 147). A reader
// keyed on the status would have to say two.
//
// `home_location_missing` is separate from `forecast_unavailable` for the same
// reason 04-API-SPEC.md keeps them apart: one is fixed on a profile screen and
// the other is fixed by nothing. DECISIONS.md 173.
const SUGGEST_ERROR_KEYS: Readonly<Record<string, string>> = {
  wardrobe_too_small: 'stylist.error.wardrobeTooSmall',
  home_location_missing: 'stylist.error.homeLocationMissing',
  forecast_unavailable: 'stylist.error.forecastUnavailable',
  // The one 422 on this endpoint a correct client can provoke: the anchor was
  // a real garment when the button was tapped and is not one the stylist can
  // be shown now. Its own code so it can say that, rather than falling into
  // `validation_error`, which talks about the occasion and the date.
  anchor_unavailable: 'stylist.error.anchorUnavailable',
  // The swap's own 422, and it is the same situation one field along: the
  // locked garments were on screen when the ↻ badge was tapped, and one of
  // them has been archived since. DECISIONS.md 177.
  locked_unavailable: 'stylist.error.lockedUnavailable',
  stylist_failed: 'stylist.error.stylistFailed',
  validation_error: 'stylist.error.validation',
};

function suggestErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as ApiErrorBody | null)?.code;
    if (code !== undefined && code in SUGGEST_ERROR_KEYS) {
      return SUGGEST_ERROR_KEYS[code];
    }
    // The one status this file reads, and it is read last, after every
    // documented code has failed to match. A body the request schema rejects
    // — an occasion outside the six, an extra field, a malformed date — is
    // FastAPI's own 422 and carries `detail` rather than `code`, so there is
    // nothing else to branch on; falling through to "something went wrong"
    // would be the wrong thing to say about a request this client should never
    // have been able to send.
    if (error.status === 422) {
      return SUGGEST_ERROR_KEYS['validation_error'];
    }
  }
  return 'stylist.error.general';
}

@Injectable({ providedIn: 'root' })
export class StylistStore {
  private readonly looks = inject(LooksApi);
  private readonly weatherApi = inject(WeatherApi);
  private readonly auth = inject(AuthService);

  private readonly weatherSignal = signal<Weather | null>(null);
  private readonly suggestingSignal = signal(false);
  private readonly errorSignal = signal<string | null>(null);
  private readonly resultSignal = signal<SuggestResponse | null>(null);
  // The id of the item being swapped, not a boolean, because the card renders
  // the wait on that tile alone — a flag would say a swap is running and not
  // which one. 05-FRONTEND-SPEC.md: the rest of the card stays put.
  private readonly swappingSignal = signal<string | null>(null);

  readonly weather = this.weatherSignal.asReadonly();
  readonly isSuggesting = this.suggestingSignal.asReadonly();
  readonly error = this.errorSignal.asReadonly();
  readonly result = this.resultSignal.asReadonly();
  readonly swappingItemId = this.swappingSignal.asReadonly();

  // Called from the page's constructor. This service is providedIn: 'root' and
  // outlives the screen, so without it the look from one visit is on screen
  // before the form is on the next. Same lifetime problem DECISIONS.md 107
  // solved for the poll, with a stale render in place of a stale request.
  reset(): void {
    this.weatherSignal.set(null);
    this.suggestingSignal.set(false);
    this.errorSignal.set(null);
    this.resultSignal.set(null);
    this.swappingSignal.set(null);
  }

  // Fails silently, on purpose. The forecast is context printed above the
  // button, not the thing the user asked for: the account may carry no home
  // location at all, and a red banner over a form that still works would be
  // louder than what it reports. The suggest request answers
  // `home_location_missing` and `forecast_unavailable` for itself, at the
  // moment the user has actually asked for something — which is the moment
  // they can act on it. Same judgement as DECISIONS.md 106, one screen over.
  loadWeather(date: string): void {
    const user = this.auth.currentUser();
    // Both coordinates or neither: the three home columns are one field
    // (DECISIONS.md 151), so this reads as a single question about the account.
    if (user === null || user.home_lat === null || user.home_lon === null) {
      this.weatherSignal.set(null);
      return;
    }

    this.weatherApi.get(user.home_lat, user.home_lon, date).subscribe({
      next: (weather) => this.weatherSignal.set(weather),
      error: () => this.weatherSignal.set(null),
    });
  }

  // The guard is the upload's rather than the retag's: one screen makes one
  // request at a time, so an in-flight mark is a boolean and a second submit
  // during the four-to-eight seconds is dropped instead of queued.
  suggest(request: SuggestRequest): void {
    if (this.suggestingSignal()) {
      return;
    }
    this.suggestingSignal.set(true);
    this.errorSignal.set(null);
    // Cleared before the request rather than after it answers: the skeleton
    // replaces the look, and a failed re-request that left the previous look
    // underneath would put an error message on top of an outfit it is not
    // about.
    this.resultSignal.set(null);

    this.looks.suggest(request).subscribe({
      next: (response) => {
        this.resultSignal.set(response);
        this.suggestingSignal.set(false);
      },
      error: (error: unknown) => {
        this.errorSignal.set(suggestErrorKey(error));
        this.suggestingSignal.set(false);
      },
    });
  }

  // The same endpoint and deliberately not the same method. `suggest` raises
  // `isSuggesting` and clears the result, which is what puts the skeleton on
  // screen in place of the card; a swap must do neither, because the look the
  // user is looking at is nine tenths of the answer and only one tile is being
  // replaced. What it does share is the one-request-at-a-time guard.
  swap(request: SuggestRequest, itemId: string): void {
    if (this.suggestingSignal() || this.swappingSignal() !== null) {
      return;
    }
    this.swappingSignal.set(itemId);
    this.errorSignal.set(null);

    this.looks.suggest(request).subscribe({
      next: (response) => {
        this.resultSignal.set(response);
        this.swappingSignal.set(null);
      },
      // The previous look is left standing. A failed swap changed nothing, so
      // the card the user still wants is the one already on screen, with the
      // message above it saying the swap did not happen.
      error: (error: unknown) => {
        this.errorSignal.set(suggestErrorKey(error));
        this.swappingSignal.set(null);
      },
    });
  }
}

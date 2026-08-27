// `GET /me/locations/search`. Four keys and deliberately no more: the provider
// also sends `admin1`, `country_code`, `population` and a dozen others, and
// 04-API-SPEC.md keeps them off the wire — so `name` plus `country` does not
// always identify a place, and a search for "berlin" really does come back with
// two of them. Recorded as a known limitation rather than widened.
// DECISIONS.md 153.
export interface LocationResult {
  readonly name: string;
  readonly country: string;
  readonly lat: number;
  readonly lon: number;
}

// Wrapped rather than a bare array, and no match is a 200 with an empty list —
// a 404 would fire on every keystroke that has not finished spelling a city.
export interface LocationSearchResponse {
  readonly results: readonly LocationResult[];
}

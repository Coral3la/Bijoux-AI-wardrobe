import { Condition, Occasion, Role } from './enums';
import { Look, MissingPiece } from './look.model';

// The wire shapes of `/trips`, mirrored from `backend/app/schemas/trip.py`
// field for field and keeping the server's snake_case (DECISIONS.md 059).
//
// The whole trip object is here at 4.5 even though the form renders two of its
// fields. The endpoint answers it whole, and typing half of a response is a
// claim about the endpoint that is not true — `look.model.ts` mirrors fields no
// screen has rendered for the same reason. 4.6 reads `days` and `packing_list`,
// 4.6a moves them and 4.7 exports them.

// `POST /trips/pack`'s `occasions[]`. `day` is the trip's own 1-based ordinal —
// day 1 is `start_date` — and it is on the wire rather than left positional
// because the request schema checks the numbers are `1..n` *in order*, and a
// body whose meaning depends on array order is one a client can get wrong
// silently.
export interface TripOccasion {
  readonly day: number;
  readonly occasion: Occasion;
}

// `POST /trips/pack`'s body. `notes` is genuinely omitted rather than sent as
// null or empty, which is `SuggestRequest`'s rule unchanged: absent is what the
// server already defaults it to, and the schema forbids extra keys rather than
// dropping them, so nothing may be added here for convenience.
//
// There are no coordinates. The endpoint takes the destination as a string and
// geocodes it for itself (DECISIONS.md 202), so the `lat`/`lon` the picker had
// in hand never leave the browser.
export interface PackRequest {
  readonly destination: string;
  readonly start_date: string;
  readonly end_date: string;
  readonly occasions: readonly TripOccasion[];
  readonly notes?: string;
}

// One entry of 4.6's day strip: the forecast, the occasion and the look.
//
// `occasion` and `condition` carry their unions where `Look.occasion` is a
// plain string, and the difference is real rather than an inconsistency.
// `looks.occasion` is TEXT and the database refuses no value (DECISIONS.md
// 168), whereas this object is built by `TripResponse`, which types both as
// enums — so a value outside the vocabulary is a 500 on the way out and cannot
// reach this type.
//
// `look_id` is nullable and that is not padding: a repack detaches a look that
// was saved, rated or worn instead of deleting it (AUDITS.md O-32), and between
// the detach and the new looks landing a day has none.
export interface TripDay {
  readonly day: number;
  readonly date: string;
  readonly occasion: Occasion;
  readonly temp_min_c: number;
  readonly temp_max_c: number;
  readonly precip_mm: number;
  readonly wind_kph: number;
  readonly condition: Condition;
  // The exact sentence the model was given for this day, read back from the
  // column. On the wire to make the weather behaviour inspectable from outside
  // the process, and deliberately not rendered — `Weather.rule` carries the
  // same note for the same reason: it is written for a model, not for a person.
  readonly rule: string;
  readonly look_id: string | null;
}

// `null` when nothing is worn on more than one day, which is an ordinary
// outcome on a short trip rather than an error.
export interface ReuseCount {
  readonly item_id: string;
  readonly days: number;
}

// The numbers, not the sentence. A server that answered "the jeans appear on
// 3 days" would put user-facing text where no i18n key can reach it, so the
// English is the frontend's and these two counts are what 4.5's confirmation
// and 4.6's header are built from.
export interface ReuseSummary {
  readonly item_count: number;
  readonly look_count: number;
  readonly most_reused: ReuseCount | null;
}

// Row UUIDs, never `short_id`s. The ids the model answered with are mapped
// through the wardrobe before anything is stored, because a UUID is the only id
// that leaves this API.
export interface PackingList {
  readonly item_ids: readonly string[];
  readonly reuse_summary: ReuseSummary;
}

// One shape for a trip wherever it comes from — `POST /trips/pack`,
// `GET /trips`, `GET /trips/{id}` and `POST /trips/{id}/repack` all answer with
// this, and a trip's looks are always a sibling key rather than a field inside
// it. DECISIONS.md 195.
//
// `days` and `packing_list` are non-null over two nullable columns, which is
// the server's own typing and rests on who writes them. `forecast` has one
// writer, `POST /trips/pack`; `packing_list` has had two since 4.6a-1, when
// `POST /trips/{id}/swap` began recomputing it. Both fill the column on every
// path they can answer 200 from, so the typing holds — it now rests on two
// functions agreeing rather than on one existing. DECISIONS.md 209. `dest_lat`/`dest_lon` stay nullable, because the destination is what
// the user typed and the coordinates are what the geocoder made of it.
export interface Trip {
  readonly id: string;
  readonly destination: string;
  readonly dest_lat: number | null;
  readonly dest_lon: number | null;
  readonly start_date: string;
  readonly end_date: string;
  readonly notes: string | null;
  readonly days: readonly TripDay[];
  readonly packing_list: PackingList;
  readonly created_at: string;
}

// `POST /trips/pack` and `POST /trips/{id}/repack`.
//
// There is no `message` key, unlike `SuggestResponse`: `trips` has no column
// for one, so a sentence that survived only until the next page load would be a
// field lying about what the API stores. `missing_pieces` passes that test
// differently — it describes this run and is never persisted, which is why
// `GET /trips/{id}` answers everything here except it.
export interface PackResponse {
  readonly trip: Trip;
  readonly looks: readonly Look[];
  readonly missing_pieces: readonly MissingPiece[];
}

// `POST /trips/{trip_id}/swap`'s body: one day, one garment, one role.
//
// `replace_role` is required, where `SuggestRequest` makes it optional. That is
// the endpoint's own narrowing rather than this file's: `POST /looks/suggest`
// serves a plain suggestion as well as a swap, so most of its traffic omits the
// field; this route does one thing and the badge always knows the role of the
// tile it sits on. `Role` comes from `enums.ts`, which is the only place the
// category-to-role map exists — the server validates the six values and derives
// none (AUDITS.md O-25).
//
// `exclude_item_ids` has a server-side default and is still required here,
// because the client that omits it is a client that has lost the accumulation:
// the list is what stops a second tap on one day handing back the garment the
// first tap rejected, and the server cannot rebuild it — the looks carrying
// those rejections were replaced by this endpoint and are gone.
export interface TripSwapRequest {
  readonly day: number;
  readonly item_id: string;
  readonly replace_role: Role;
  readonly exclude_item_ids: readonly string[];
}

// `GET /trips/{id}` and `POST /trips/{trip_id}/swap`, mirroring
// `TripDetailResponse`. It is `PackResponse` minus `missing_pieces`, and it is a
// second interface rather than the same one with the key made optional: the pack
// response always carries the list and this one never does, so an optional key
// would leave every reader of a packed trip checking for something the server
// promised.
//
// The swap answers it too rather than a shape of its own — it edits one day and
// replies with the whole trip, because `packing_list` has moved and a client
// cannot reassemble a plan from a fragment. DECISIONS.md 209.
export interface TripDetail {
  readonly trip: Trip;
  readonly looks: readonly Look[];
}

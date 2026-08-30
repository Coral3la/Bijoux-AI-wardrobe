import { Occasion, Role } from './enums';
import { Item } from './item.model';

// The body of `POST /looks/suggest`, whole since 2.11 put the three swap
// fields on the wire beside 2.10's anchor.
//
// Every optional is genuinely omitted rather than sent as null or empty:
// absent is what the server already defaults them to, and an omitted key
// cannot trip the extra-field rejection the schema applies. 04-API-SPEC.md.
//
// The ids are row UUIDs, which are the only ids this client ever holds. The
// `short_id` the prompt prints never leaves the server.
export interface SuggestRequest {
  readonly occasion: Occasion;
  readonly date: string;
  readonly include_outerwear?: boolean;
  readonly notes?: string;
  readonly anchor_item_id?: string;
  // Sent together by the ↻ badge and by nothing else: `replace_role` names
  // which of the locked items may move, so the endpoint answers 422 to a role
  // with no locks.
  readonly locked_item_ids?: readonly string[];
  readonly replace_role?: Role;
  readonly exclude_item_ids?: readonly string[];
}

// `category` is a plain string for the same reason item.model.ts leaves
// `subcategory` one: nothing on the wire narrows it. The look's `occasion` is
// enforced by the request schema and by nothing else — `looks.occasion` is
// TEXT and the database refuses no value (04-API-SPEC.md, DECISIONS.md 168) —
// so a union here would claim a guarantee the column does not make.
export interface MissingPiece {
  readonly category: string;
  readonly description: string;
  readonly reason: string;
}

// The two the column admits, mirroring `Literal[-1, 1]` on the server and
// `ck_looks_feedback_values` under that. `null` is the third state and the one
// every look starts in: unrated, which 3.5 counts against.
export type Feedback = 1 | -1;

// One shape for a look wherever it comes from: POST /looks/suggest,
// GET /looks and PATCH /looks/{id} all answer with this. The server renamed
// SuggestedLook to LookResponse at 3.2 for the same reason — a second
// near-identical type is one row described twice, with nothing keeping the two
// descriptions in step. DECISIONS.md 182.
export interface Look {
  readonly id: string;
  readonly occasion: string;
  readonly title: string;
  readonly items: readonly Item[];
  readonly reasoning: string;
  readonly weather_note: string;
  readonly is_saved: boolean;
  readonly feedback: Feedback | null;
  // The day this look was *most recently* worn. Not the same claim as any of
  // its items' `last_worn_at`: one column holds one date, so wearing the look
  // again overwrites it, while a garment keeps the latest day it was worn in
  // anything at all. DECISIONS.md 184.
  readonly worn_at: string | null;
}

// PATCH /looks/{id}. Every key is optional to *omit* — `undefined` means
// "leave it alone" — and only `feedback` may be sent as `null`, which clears
// it. A null `is_saved` or `title` is a 422: neither column has an empty state
// a screen can render.
export interface LookUpdate {
  readonly is_saved?: boolean;
  readonly title?: string;
  // Optional to omit *and* nullable to send: unlike the other two, `null` here
  // is a documented write rather than a 422. It un-rates the look.
  readonly feedback?: Feedback | null;
}

// POST /looks/{id}/wear. One required key, and the date is the *client's* local
// today rather than the server's: a browser east of UTC names a day the server
// would still call tomorrow, and the endpoint refuses no date for that reason.
export interface LookWearRequest {
  readonly date: string;
}

export interface LookListResponse {
  readonly looks: readonly Look[];
  readonly total: number;
}

// `looks` is an array carrying exactly one look today. Typed as the wire types
// it rather than flattened to the single element, because flattening is a
// narrowing this client would have to undo the first time the endpoint returns
// two. Task 2.8 reads `looks[0]` at the one place that renders it.
export interface SuggestResponse {
  readonly looks: readonly Look[];
  readonly missing_pieces: readonly MissingPiece[];
  readonly message: string;
}

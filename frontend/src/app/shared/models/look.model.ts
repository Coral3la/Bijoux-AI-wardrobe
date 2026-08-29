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
}

// PATCH /looks/{id}. Both keys are optional to *omit* and neither may be sent
// as null: the endpoint refuses a cleared field rather than nulling a column,
// so `undefined` here means "leave it alone" and there is no way to say
// "erase it". `feedback` is 3.3's and the schema rejects it today, which is
// why it is absent rather than optional.
export interface LookUpdate {
  readonly is_saved?: boolean;
  readonly title?: string;
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

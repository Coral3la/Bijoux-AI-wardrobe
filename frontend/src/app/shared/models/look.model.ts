import { Occasion } from './enums';
import { Item } from './item.model';

// The body of `POST /looks/suggest`. The four anchor and swap fields arrive at
// 2.10 and 2.11, and until then the request schema *refuses* them rather than
// ignoring them — so they are absent from this type rather than optional in
// it. A field this client cannot send is a field it must not offer.
//
// Both optionals are genuinely omitted rather than sent as null: absent is
// what the server already defaults them to, and an omitted key cannot trip the
// extra-field rejection the schema applies. 04-API-SPEC.md.
export interface SuggestRequest {
  readonly occasion: Occasion;
  readonly date: string;
  readonly include_outerwear?: boolean;
  readonly notes?: string;
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

export interface Look {
  readonly id: string;
  readonly occasion: string;
  readonly title: string;
  readonly items: readonly Item[];
  readonly reasoning: string;
  readonly weather_note: string;
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

import { Item } from './item.model';

// Mirrors ItemSetResponse in backend/app/schemas/item_set.py field for field,
// and keeps the server's snake_case (DECISIONS.md 059). A file of its own
// rather than three more exports in item.model.ts: a set is a second resource
// with five endpoints, and item.model.ts holds the shapes of `/items`.
//
// `items` is the full Item rather than ids or a narrower projection — one shape
// for one resource (DECISIONS.md 034, 050) — which is what lets the detail
// screen draw the members as thumbnails without a second request per member.
// The list always holds at least two elements, because a set that would hold
// fewer does not exist, and it can hold an **archived** one: archiving a
// garment does not unmake the fact that it was bought with another. That is why
// the screen drawing this has to mark an archived member — it is visible here
// and nowhere else in the application, GET /items having excluded it.
export interface ItemSet {
  readonly id: string;
  readonly name: string | null;
  readonly items: readonly Item[];
  readonly created_at: string;
}

// POST /sets' body. `item_ids` holds at least two distinct ids; fewer, or the
// same id twice, is a 422 validation_error from the schema rather than an error
// code of its own, because no correct client can build that body. This client
// never can: it sends the garment on screen and the one just picked.
//
// `name` is on the wire and no control writes one — declaring a set is two taps
// and there is no field to type into, since STAGE-4A puts renaming out of scope
// and a name with no way to correct it is worse than none. It is typed here
// because the request body is a mirror rather than a list of this client's
// appetite, and because `set.name` is rendered when a set has one.
export interface ItemSetCreateRequest {
  readonly name?: string | null;
  readonly item_ids: readonly string[];
}

// POST /sets/{set_id}/items' body. One id per request rather than a list: the
// control that calls it picks one garment, and a partial failure over a list
// would need a response shape this API has nowhere else.
export interface ItemSetMemberRequest {
  readonly item_id: string;
}

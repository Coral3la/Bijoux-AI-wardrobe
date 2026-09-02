# 04 — API Specification

Base path: `/api/v1`
Auth: `Authorization: Bearer <jwt>` on everything except `/auth/*` and `/health`.

**This document is authoritative.** Do not add endpoints that are not listed here.

---

## Conventions

- IDs in URLs are UUIDs. `short_id` never appears in a URL — it exists only for the AI layer.
- Errors use a single envelope:
  ```json
  { "detail": "Human-readable message", "code": "wardrobe_too_small" }
  ```
  Two keys, on every error the application raises and on `422`. Routing-level failures are the exception — a `404` on an unknown path and a `405` on the wrong method carry `detail` only, because neither is an application error a client branches on. Where an error concerns a particular field, the field is named inside `detail` — there is no third key. Implemented in `app/core/errors.py` at task 0.5; see `DECISIONS.md` 033 for why FastAPI's native `422` shape is reshaped rather than passed through, and what is lost by doing so.
- Timestamps are ISO 8601 UTC. Dates are `YYYY-MM-DD`.
- Pagination: `?limit=` (default 100, max 200) and `?offset=`.

---

## Auth

### `POST /auth/register`
```json
→ { "email": "a@b.com", "password": "…", "display_name": "Coral" }
← 201 { "access_token": "…", "token_type": "bearer", "user": { … } }
```
Password: minimum 8 characters. Hashed with bcrypt. `409` if the email exists.

### `POST /auth/login`
```json
→ { "email": "a@b.com", "password": "…" }
← 200 { "access_token": "…", "token_type": "bearer", "user": { … } }
```
`401` on bad credentials — the same message for wrong email and wrong password.

JWT lifetime: 7 days. No refresh token in this project; document the omission in `DECISIONS.md`.

### `GET /auth/me`
Returns the current user object.

### The user object

The `user` key above and the body of `GET /auth/me` and `PATCH /me` are all the same shape — every column of `users` except `password_hash`:

```json
{ "id": "uuid", "email": "a@b.com", "display_name": "Coral",
  "height_cm": null, "size_top": null, "size_bottom": null, "size_shoe": null,
  "style_notes": null, "home_city": null, "home_lat": null, "home_lon": null,
  "created_at": "2026-08-06T09:14:22Z" }
```

Every field but `id`, `email`, `display_name` and `created_at` is nullable and is `null` on a fresh account.

**`display_name` is the exception, and it is nullable in the column while never being `null` on a new account.** `POST /auth/register` has required it since task 0.10 — `str`, trimmed, at least one character after trimming — so nothing this API creates can have a blank one. The column stays `TEXT NULL` because four accounts predate the rule, so a client reading `GET /auth/me` must still handle `null`. **`PATCH /me` has set it since task 2.2** — this sentence said it did not, on a document whose own `PATCH` example carried the field — and it can also clear it, which makes a blank name producible by the API for the first time. `userLabel` in the frontend has fallen back to the email address since 0.9 for the legacy rows and covers this unchanged (`DECISIONS.md` 071, 149). Tightening the request did not tighten the response: `UserResponse.display_name` is `str | None`. The spelling of the constraint is not the one `DECISIONS.md` 070 proposed — see 072 for why `Field(strip_whitespace=True)` silently does nothing.

One shape for one resource — see `DECISIONS.md` 034.

Failure codes on this group: `409` `email_exists`, `401` `invalid_credentials`, `401` `invalid_token`, `422` `validation_error`. Every `401` carries `WWW-Authenticate: Bearer` — `get_current_user` has since task 0.5, and `POST /auth/login` since 0.10, where the gap was closed and `test_login_401_offers_the_bearer_challenge` was written to keep it closed. Unknown keys in either request body are a `422` rather than being ignored (`DECISIONS.md` 039).

Authentication is a bearer token in the `Authorization` header. There is no OAuth2 password-flow token endpoint — `/auth/login` takes JSON, not form encoding (`DECISIONS.md` 035).

Passwords are a minimum of 8 **characters** and a maximum of 72 **bytes** in UTF-8. The units genuinely differ; the limit is bcrypt's and the error message names bytes. `DECISIONS.md` 036 has the worked example.

---

## Profile

### `PATCH /me`
```json
→ { "display_name": "…", "height_cm": 165, "size_top": "M",
    "size_bottom": "28", "size_shoe": "38",
    "style_notes": "prefer high-rise, avoid crop tops",
    "home_city": "Tel Aviv", "home_lat": 32.08, "home_lon": 34.78 }
← 200 { user }
```
All fields optional. `home_lat`/`home_lon` power the weather widget and the default location for daily looks.

**Built wide at task 2.2, not narrow.** `STAGE-2` 2.2 asked for `home_city`, `home_lat` and `home_lon` only; the endpoint accepts the whole body above, because `03-AI-CONTRACTS.md`'s stylist prompt reads `height_cm` and `style_notes` and no other route can ever set them — `AUDITS.md` **O-6**, closed there. `display_name` is included and this document said twice that it would not be; both sentences are corrected, and see `DECISIONS.md` 149.

**Semantics are `PATCH /items/{id}`'s exactly.** An omitted field is left alone; a field sent as `null` is cleared; an unknown key is a `422` rather than being ignored; an empty body is a `422`. One partial-update rule for the whole API.

**The home location is one field in three columns.** `home_city`, `home_lat` and `home_lon` are supplied together or cleared together — any other combination is a `422`. A city with no coordinates cannot be given a forecast, and coordinates with no city name have nothing to print above the weather strip. `DECISIONS.md` 151.

`height_cm` is bounded by `02-DATA-MODEL.md`'s own `CHECK (height_cm BETWEEN 120 AND 230)`, refused by the request schema rather than by Postgres — an `IntegrityError` reaching the client is a `500` with no `code`. `home_lat` is `-90…90` and `home_lon` is `-180…180`.

Failure codes on this endpoint: `422` `validation_error`, `401` `invalid_token`.

### `GET /me/locations/search?q=berlin`
```json
← 200 { "results": [ { "name": "Berlin", "country": "Germany",
                       "lat": 52.52437, "lon": 13.41053 } ] }
```
Proxies Open-Meteo geocoding. Returns up to 5 results.
Used by both the profile screen and the trip form, so the frontend never calls a third-party API directly.

**Wrapped in `results`, and no match is a `200` with an empty list** — not a `404`, which would fire on every keystroke that has not finished spelling a city. Note that the provider itself answers a no-match by **omitting the key entirely** rather than by sending an empty array; that is its shape, not ours, and it is what `app/services/geocoding.py` parses around. Verified against a live call on 2026-08-26.

**`q` is trimmed and must be at least 2 characters**, which is the provider's own floor: one character matches nothing and two match only exactly. Shorter than that is a `422` and no request leaves the process.

The four keys are all this returns. The provider also sends `admin1`, `country_code`, `population`, `timezone` and more, and a search for `berlin` really does come back with two places called Berlin in two countries — so `name` plus `country` does not always identify a place uniquely. Recorded as a known limitation rather than widened; `DECISIONS.md` 153.

Failure codes on this endpoint: `422` `validation_error`, `502` `geocoding_unavailable`, `401` `invalid_token`.

---

## Items

### `POST /items/upload`
`multipart/form-data`, field `files` (repeatable, 1–20 files, ≤ 10 MiB each, JPEG · PNG · WebP · HEIC/HEIF only).

```json
← 202 { "items": [ { …full item… } ] }
```

Every element is the same **full item** shape `GET /items` returns, with every tag field `null` — one shape for one resource, on the same reasoning as `DECISIONS.md` 034 for the user object. Through task 0.6 this document printed a narrower five-key object here; that was corrected at 0.7 by widening the response rather than shrinking it, and the abbreviated example is why. See `DECISIONS.md` 050.

Returns as soon as the images are in Cloudinary and the rows are written. Tagging continues in the background.

Failure codes on this endpoint: `415` `unsupported_file_type`, `413` `file_too_large`, `502` `upload_failed`. `413` if **any** file exceeds the limit and `415` if any file is not an accepted format — both reject the whole request, and both are decided for every file before a single one is uploaded, so a rejected batch leaves nothing behind in Cloudinary. Type is decided before size for the whole batch, so an over-large non-image reports `415`, preserving at batch level the rule `DECISIONS.md` 045 set for a single file. Where the failure concerns one file, that file's name appears inside `detail`.

Fewer than 1 or more than 20 parts is a `422` `validation_error` naming `files`, not a `413` — the limit on the *count* is a request-shape rule, where `413` is reserved for the size of an individual file. No separate code (`DECISIONS.md` 048).

**A batch that fails after some files are already stored leaves those assets in Cloudinary.** The rows are rolled back, the client gets its error, and the stranded `public_id`s are written to the log at `ERROR`. Nothing deletes them — `DECISIONS.md` 053.

The accepted formats are narrower than the `image/*` this document specified through task 0.5, and they are identified from the file's own bytes rather than from the `Content-Type` the client declares. SVG in particular is excluded deliberately. `DECISIONS.md` 045 has the reasoning and the trade-off.

### `GET /items`
Query: `status`, `category`, `color_primary`, `formality_min`, `formality_max`, `warmth_min`, `warmth_max`, `search`, `include_archived`, `limit`, `offset`.

```json
← 200 { "items": [ { …full item… } ], "total": 138 }
```

`search` matches `display_name` only — a simple `ILIKE`, no full-text index. It is not escaped, so `%` and `_` in the search string keep their wildcard meaning.

`total` counts the filter, not the page. Results are ordered `created_at DESC, short_id` — the second key is load-bearing rather than cosmetic, because `now()` is the transaction timestamp and every row of one upload therefore shares a `created_at` to the microsecond. Archived items are excluded unless `include_archived` is passed.

**The full item** is every column of `items` **except `user_id`**, with `image_public_id` accompanied by `image_url`, a ready-built **thumbnail** URL (`w_300,h_300,c_pad,b_white,f_auto,q_auto`). Both corrections are the 2026-08-18 audit's, against `app/schemas/item.py` and `07-DEPLOYMENT.md`'s transform table: `ItemResponse` has never carried `user_id`, and a client that builds the thumbnail from the four-parameter string above gets a different URL from the one the server returns. The `public_id` is what `cloudinary-url.pipe.ts` builds every other transform from; the thumbnail is included because it is what the grid renders on arrival. See `DECISIONS.md` 050.

All eleven parameters above are implemented as of task 0.7. **An unknown or misspelled query parameter is still silently ignored and still returns `200` with an unfiltered list** — `?colour_primary=navy` filters nothing and says nothing. Query strings have no `extra="forbid"` equivalent, so `DECISIONS.md` 039's guarantee genuinely stops at request bodies. Rejecting unknown query keys would be one piece of middleware; **task 5.4** owns deciding whether to add it or to publish it as a known issue, and it is named here rather than left implied (`DECISIONS.md` 051).

Pagination defaults to 100, and `05-FRONTEND-SPEC.md` filters client-side "over the loaded collection". A wardrobe above 100 items therefore filters over the first page only unless the client passes `limit`. The wardrobe screen must pass it; `01-ARCHITECTURE.md` sizes a realistic wardrobe at 80–150.

### `GET /items/{id}` · `PATCH /items/{id}` · `DELETE /items/{id}`

`PATCH` accepts any tag field. It sets `user_edited = true` and validates against the closed vocabulary using the same validator the AI output passes through. `422` with the offending field on an invalid value.

**What is validated is the request merged over the stored row, not the request alone** — corrected at task 1.4, where this document said "validates every value" and a literal reading of it produced the wrong endpoint. Under request-only validation `PATCH {"category": "top"}` on a pair of jeans passes, because nothing in the request is invalid, and writes a row whose stored `subcategory` is `jeans` and whose stored `rise` is `high` — both now describing a garment the item is not. The route therefore loads the row, merges the body over it, and validates the result; and because a category change invalidates the *stored* values rather than the request, it first clears the five fields listed in `CATEGORY_DEPENDENT_FIELDS` for any of them the same request does not supply. `DECISIONS.md` 030, amended at 1.2a from three fields to five, has the reasoning and the accepted cost.

```json
← 200 { …full item… }
```

**All three answer with the full item**, added at task 1.4 — this document gave `PATCH` and `DELETE` a failure contract and no success contract at all, which the 2026-08-18 audit recorded as O-1. One shape for one resource (`DECISIONS.md` 034, 050), so a client replaces a row rather than merging a special case; `204` on the `DELETE` was rejected because it leaves the client guessing at `is_archived` and `updated_at`, both of which have just changed.

`DELETE` soft-deletes by setting `is_archived = true`. The Cloudinary asset is retained; deleted items may still be referenced by historical looks. It is **idempotent**: archiving an already-archived row is another `200` carrying the same object, because the row stays readable by id and a `404` on the second call would contradict the `GET` that still answers.

`PATCH` returns `422` `validation_error` on an empty body. A body with no fields would otherwise be a `200` that set `user_edited` on a request which edited nothing.

**A `PATCH` that completes a `failed` row clears the failure**, added at task
1.9. When the merged result carries every field in `REQUIRED_TAG_FIELDS` —
`category`, `subcategory`, `color_primary`, `pattern`, `material`, `formality`,
`warmth`, `layer`, `water_resistant`, `display_name` — a `failed` row answers
`200` with `status: "ready"` and `error_message: null`. `fit`, `length`, `rise`
and `color_secondary` are not in the set: a null in any of them is an answer
rather than a gap.

The rule is narrow in three directions and each one is deliberate. **It never
writes `processing`**: a background task holds the row and writes every tag
column when it lands, so a status set here would be overwritten seconds later by
a task that never knew about it. **It never demotes**: a `ready` row that an edit
leaves incomplete stays `ready`, because a user clearing a tag is answering
rather than failing, and `DECISIONS.md` 109 already depends on a `ready` row
being able to carry a null beside real tags. **And it is the only status this
endpoint writes at all** — everything else about `status` remains the tagging
path's.

Before this, `PATCH` wrote tags and never touched `status`, so an item recovered
by hand from the failed tile kept its `failed` status and its `error_message`
permanently — `03-AI-CONTRACTS.md`'s **Add manually** link promised a recovery
the wire had no mechanism for. `DECISIONS.md` 116.

An item that exists but belongs to another user returns `404` with `code: "not_found"` on every one of these — not `403`. One code for every resource, because telling a caller that a row exists but is not theirs is an existence oracle for other people's wardrobes (`DECISIONS.md` 043).

### `POST /items/{id}/retag`
```json
← 202 { …full item…, "status": "processing" }
```

Re-runs vision tagging. `409` with `code: "item_edited"` if `user_edited` is true, unless `?force=true` is passed — a manual correction must not be silently overwritten. The status code and the body were added at task 1.4 (audit O-1), along with the error code, which this document had left as the only failure in it with no code at all. `202` rather than `200` because retag starts exactly the background work `POST /items/upload` answers `202` for, and the body carries `status: "processing"` so a client can put the tile straight back into its polling set.

**`user_edited` is never cleared** — not by a forced retag, not by the tagging that follows one. `02-DATA-MODEL.md` gives the column a second job, and the accepted cost is that a hand-corrected item needs `?force=true` on every later retag.

**A retag against a row that is already `processing` is allowed**, and answers `202` like any other. Two tasks can then write the same row and the last write wins, at a cost of one wasted pair of model calls. Refusing was the alternative and is worse: a row whose owning process died sits `processing` until the startup sweep clears it, up to ten minutes, and refusing would make the one action that fixes it unavailable for exactly that window. `?force=true` keeps its single meaning. `DECISIONS.md` 089.

### `GET /items/stats`
```json
← 200 {
  "total": 138, "by_category": { "top": 41, … },
  "by_color": { "black": 22, … },
  "processing": 0, "failed": 2,
  "worn": 102, "never_worn": 34,
  "most_worn": { "id": "uuid", "display_name": "light blue mom jeans",
                 "wear_count": 12 }
}
```
Drives the wardrobe dashboard.

**The wear numbers are real from task 3.6.** Until then this block printed two
placeholders — `never_worn` answered `0` and `most_worn` answered `[]` — and
the zero was deliberate rather than lazy: with no wear data at all *every* item
is unworn, so `never_worn = total` would have been correct on the day and would
have changed meaning silently once `0004`'s columns filled.

**`worn` was added beside `never_worn` in the same task**, because a standalone
*"34 items you have never worn"* invites *of how many?* and every number in this
body that a reader would reach for answers it wrongly. The two are counted in
one statement over one population and **partition it**: `worn + never_worn` is
the number of `ready`, unarchived garments.

**`most_worn` is one object or `null`**, narrowed from the array this document
printed from Stage 0 until 3.6. There is exactly one most-worn garment or
nothing has been worn at all, and a list of one made every caller ask which of
those it was reading. It carries three fields rather than a whole item — `id`,
because `/wardrobe/:id` routes on it, plus `display_name` and `wear_count` —
which is what the insights panel draws and no more; nothing had ever been
written against the wide shape. **Ties break on `short_id` ascending**, the
tiebreaker `GET /items` already uses, so two garments worn the same number of
times resolve to the same one on every call.

**All three wear numbers are scoped one filter narrower than the counts above
them** — `ready` as well as unarchived — because a row still being tagged is
unworn trivially and has no name to put on a panel. Their denominator is
therefore **not `total`**, which counts every status: in the body above, 138
total is 136 `ready` rows plus 2 `failed`, and it is the 136 that `worn` and
`never_worn` split. So **`total` minus `never_worn` is not the number of items
the user has worn** — `worn` is. Swimwear and sleepwear *are* counted:
`STYLIST_EXCLUDED_CATEGORIES` is a rule about what the stylist may recommend,
not about what the wardrobe holds, and `total` and `by_category` in this same
body already count them.

**Cost-per-wear is not here and is not coming.** `STAGE-3` §3.6 asked for it
and there is nowhere to get it: no price column exists, `02-DATA-MODEL.md`
lists purchase price as a future `attributes` key that nothing writes, and a
placeholder computed from a price the application never collects would render a
fabricated number as a fact. `DECISIONS.md` 186.

Counts exclude archived rows, matching `GET /items`, so a dashboard cannot keep counting deleted garments. `total` is every non-archived row including `processing` and `failed`; `by_category` and `by_color` omit rows whose tag is still `null`, so their values do not sum to `total` and a category with no items is absent rather than zero.

---

## Weather

### `GET /weather?lat=&lon=&date=`
```json
← 200 {
  "date": "2026-03-14", "temp_min_c": 12, "temp_max_c": 19,
  "precip_mm": 0.2, "wind_kph": 14, "condition": "partly_cloudy",
  "rule": "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional."
}
```
The `rule` string is exactly what goes into the prompt. Exposing it is intentional — it makes the system inspectable and it is easy to assert on in tests.

**The rule is built from `temp_max_c`.** `build_rule` takes one temperature and this response carries two, which no document settled until task 2.1. The example above decides it: min 12 with max 19 prints the 16–21°C rule, and under `temp_min_c` it would print *"Outerwear is REQUIRED, warmth 3-4"* — so the worked example is only self-consistent under the maximum. `DECISIONS.md` 142.

`condition` is the closed vocabulary in `02-DATA-MODEL.md`, eight values, mapped from Open-Meteo's WMO code in `app/services/weather.py`.

Cached in memory for 30 minutes per `(lat, lon, date)`, with the coordinates **rounded to 2 decimal places** before they become a key — the provider snaps to a coarser grid than that on its own, and `users.home_lat` is a `REAL`, so a cache keyed on full precision would never hit. `DECISIONS.md` 145.

Failure codes, both `forecast_unavailable`: `400` when the date is beyond the forecast horizon, `502` when Open-Meteo does not answer. **This is the first code in the project used at two statuses**, and it is deliberate — the frontend branches on the code to decide what to say, and both cases say the same thing ("no forecast for that day"); the status is for the caller who needs to know whose fault it was. `DECISIONS.md` 147.

**The horizon is `today + 15`** — sixteen days counting today. Measured on 2026-08-26: the provider served `2026-09-10` and refused `2026-09-11`. Bad `lat`/`lon` are `422` `validation_error` before any request leaves.

---

## Looks

### `POST /looks/suggest`
```json
→ { "occasion": "work", "date": "2026-03-14",
    "include_outerwear": null, "notes": "meeting with a client",
    "anchor_item_id": null, "locked_item_ids": [], "exclude_item_ids": [],
    "replace_role": null }
← 200 { "looks": [ { "id": "uuid", "occasion": "work", "title": "Morning meetings",
                     "items": [ { …item… } ], "reasoning": "…", "weather_note": "…" } ],
        "missing_pieces": [ { "category": "shoes", "description": "…", "reason": "…" } ],
        "message": "A work outfit for a mild day." }
```

The response is `03-AI-CONTRACTS.md`'s object with `item_ids` **replaced** by
`items`, hydrated to the same shape `GET /items` returns, and with the `id` of
the row this call persisted — the look is a resource from the moment it is
suggested, and `PATCH /looks/{id}` at Stage 3 is the heart button on this very
card. `DECISIONS.md` 172.

*Amended at 3.4, and the sentence that stood here was wrong by then.* It read
*"`is_saved`, `feedback` and `worn_at` are not in the look object: two of them
are columns that do not exist until migration `0004`"* — true when written at
2.7 and false in three steps: 3.2 put `is_saved` on the shape, 3.3 `feedback`,
3.4 `worn_at`. **All three are in the look object on every endpoint that
answers with one**, this one included, because 3.2 made `LookResponse` a single
shape rather than one per endpoint. On a freshly suggested look the three read
`false`, `null` and `null`, off the row rather than written as literals.

`include_outerwear`: `true` forces a coat, `false` forbids one, `null` lets the weather rule decide.
`occasion`: one of `casual · work · evening · sport · formal · travel`. The six
live in `02-DATA-MODEL.md`'s closed vocabulary since task 2.7 and are enforced by
this request schema — `looks.occasion` is `TEXT` and the database refuses
nothing. `422` on any other value. `AUDITS.md` **O-8**, `DECISIONS.md` 168.

**The last four fields arrived with the anchor at 2.10 and the swap at 2.11,
and a field the schema does not know is still *refused* rather than ignored.** A
`anchor_item_id` silently dropped would be a `200` carrying a look that failed
to build around the garment the user is holding, reported as a success.

**`anchor_item_id`** — build the look around this item. It must appear in the result. This powers "Style around this" from the item detail screen, and it is the direct answer to the original problem: *I am holding this garment and do not know what goes with it.*

**`locked_item_ids` + `replace_role` + `exclude_item_ids`** — swap a single item while keeping the rest of the look. `replace_role` is one of `top · bottom · outer · shoes · bag · accessory`. This powers the ↻ button on each item in a look card. The six live in `02-DATA-MODEL.md`'s closed vocabulary since task 2.11 and are enforced by this request schema; `dress` is not among them, so a look built on a dress has no ↻ on that tile (`AUDITS.md` **O-25**, `DECISIONS.md` 175).

All four fields are optional and default to null or empty. A request with none of them behaves exactly as before.

`422` if `anchor_item_id` or any locked ID does not belong to this user, or if `replace_role` is given without `locked_item_ids`.

Since task 2.11 those are two different answers, and the distinction is which
one a correct client can send. An unusable locked id carries
`code: "locked_unavailable"` — checked, like the anchor, against the wardrobe
that would actually be **sent**, so a garment that is still `processing`,
archived or in an excluded category is refused here rather than costing two
model calls and a `502`. `replace_role` with nothing locked is the request
schema's own `code: "validation_error"`: the ↻ badge always sends both, so no
correct client can build that body. Ids in `exclude_item_ids` that name no
wardrobe row are dropped rather than refused. `DECISIONS.md` 177.

`400` with `code: "wardrobe_too_small"` when fewer than 6 items are **usable** —
`ready`, not archived, and not in an excluded category. Counted over the
wardrobe that would actually be sent rather than over every `ready` row, because
six garments the stylist never sees cannot make an outfit: the alternative
answers `502` where `400` is the truth. Checked before the forecast as well as
before the model, so a small wardrobe costs nothing at all. `DECISIONS.md` 172.

`400` with `code: "home_location_missing"` when the account has no
`home_lat`/`home_lon`. The body carries no coordinates — the forecast is for the
user's home location, and `DECISIONS.md` 151 made the three home columns one
field, so either both numbers are there or neither is. It is a separate code
from `forecast_unavailable` because the two say different things to a user:
*we don't know where you are* is fixed on the profile screen, *we have no
weather for that day* is not fixed by anything. `DECISIONS.md` 173.

`422` with `code: "anchor_unavailable"` when `anchor_item_id` names nothing in
the wardrobe that would actually be sent — an item belonging to another account,
or one this account owns that is not styleable: still `processing` or `failed`,
archived, or in an excluded category. Checked against the sent wardrobe rather
than against ownership alone, on `wardrobe_too_small`'s reasoning: a garment the
stylist is never shown cannot appear in a look either, so rule 1 would refuse
the id as a hallucination and the answer would arrive as a `502` two model calls
later, where `422` is the truth. Answered from rows already in hand, so neither
the forecast nor the model is asked for. It is a separate code from
`validation_error` because it is the one `422` on this endpoint a correct client
can provoke — the user tapped "Style around this" on a real garment — and it is
therefore the one the client has something to say about.

`502` with `code: "stylist_failed"` when validation fails twice — and also when
the model answers nothing usable, or the provider does not answer at all. **The
one retry is spent only on a validation violation**, which is the only failure
with something to say back to the model; a timeout is not retried, as
`03-AI-CONTRACTS.md`'s failure table already says. Two calls maximum, the whole
wardrobe each time. `DECISIONS.md` 171.

**The swimwear/sleepwear exclusion is a setting**, `STYLIST_EXCLUDED_CATEGORIES`,
comma-separated and validated against `02-DATA-MODEL.md`'s categories at process
start. Emptying it sends the whole wardrobe. `AUDITS.md` **O-21** closes here;
`01-ARCHITECTURE.md` has promised this list since Stage 0. `DECISIONS.md` 169.

The look is persisted with `is_saved = false` before the response is returned. A
look that failed validation twice is **not** persisted: the table has no column
that could mark a row as never-served, so a rejected row would be
indistinguishable later from a suggestion the user actually saw, and the
save-rate arithmetic `02-DATA-MODEL.md` describes would count answers nobody
ever got. `look_items.position` records the model's own ordering; `role` is left
`NULL` — see `AUDITS.md` **O-25**, which 2.11 owns. `DECISIONS.md` 170.

### `GET /looks` *(Stage 3)*
```json
← 200 { "looks": [ { "id": "uuid", "occasion": "work", "title": "Morning meetings",
                     "items": [ { … } ], "reasoning": "…", "weather_note": "…",
                     "is_saved": true, "feedback": 1, "worn_at": "2026-03-14" } ],
        "total": 12 }
```

Query: `is_saved`, `from_date`, `to_date`, `limit`, `offset`. Ordered
`created_at DESC`, with `id` as the tiebreaker — `GET /items`'s ordering with
its `short_id` tiebreaker swapped, because a whole upload shares one
`created_at` and a look is written one per request. `limit` defaults to `100`
and is capped at `200`, both mirroring `GET /items`; `total` counts the filtered
set rather than the page.

`from_date` and `to_date` are inclusive and filter on **`for_date`** — the day
the look was *for*, not the day it was made.

**`trip_id` is named here and still not implemented, and the reason changed at
task 4.1.** The column exists now — migration `0005` built it — but the query
parameter is undeclared, so FastAPI ignores it: sending one filters nothing and
answers `200` with every look. It is **task 4.4's** if anything, and nothing in
Stage 4 needs it: a trip's looks are read through `GET /trips/{id}`, which
answers them as a sibling key, so this parameter has no caller in any planned
screen.

Items are hydrated in `look_items.position` order, which is the model's own —
this endpoint is that column's first reader on the server.

### `GET /looks/{id}` · `DELETE /looks/{id}`

**Neither is specified and neither is built.** No request, no response, no
status codes — the same shape as `POST /items/{id}/retag` before task 1.4.
`AUDITS.md` **O-30**. Nothing in Stage 3 needs either: the saved-looks screen
lists whole looks and there is no look-detail route.

### `PATCH /looks/{id}` *(Stage 3)*
```json
→ { "is_saved": true, "feedback": 1, "title": "Client meeting" }
← 200 { look }
```

Merges over the stored row: a key left out is a field left alone. Answers the
whole look, hydrated, so the client that tapped a control can render the row it
just changed without a second request.

**All three keys are accepted from task 3.3.** 3.2 shipped `is_saved` and
`title` and refused `feedback` with a `422`; that refusal is gone and so is the
test that pinned it.

`feedback` is `1` or `-1` and nothing else — the two `ck_looks_feedback_values`
admits. `0` is a `422` from the schema before the column ever sees it.

**One of the three can be cleared and two cannot.** `feedback: null` **un-rates
the look** and is a documented write: `NULL` is the state every look starts in
and the one task 3.5 counts against, so a mis-tapped thumb has to be
withdrawable or it permanently changes what the stylist is told about this user.
`null` on `is_saved` or `title` stays a `422`: `is_saved` is `NOT NULL`, so an
accepted `null` reaches Postgres as an `IntegrityError` and a `500` with no
`code`, and a cleared `title` leaves the card with an empty heading. `title` is
stripped and must be non-empty.

`422` with `code: "validation_error"` on an empty body. `404` with
`code: "not_found"` for a look belonging to another account — the same code and
status as one that never existed, per `06-TESTING-STRATEGY.md`.

### `POST /looks/{id}/wear` *(Stage 3)*
```json
→ { "date": "2026-03-14" }
← 200 { look }
```
Sets `looks.worn_at` and, in the same transaction, increments `wear_count` and updates `last_worn_at` on every item in the look. Idempotent per date — calling it twice for the same date does not double-count.

**Written at task 3.4, and the one-line spec above needed five things said.**

`date` is **required** and has no upper bound. The client sends the local today
its own browser is standing in, and a browser east of UTC routinely names a day
this server would still call tomorrow — so a future-date refusal would be a
`422` that a *correct* client provokes by its timezone, which is the one thing
`CONVENTIONS.md` says a validation error must never be. The column is
descriptive rather than a claim about time. An unknown key is
`validation_error`, per `extra="forbid"`.

**Idempotency is per the date the row currently holds, and that is its exact
reach.** A repeat naming the stored date changes nothing and answers `200`. A
*different* date is a genuine second wearing: `worn_at` is overwritten and every
item is incremented again. It follows that Monday → Tuesday → Monday counts
three wearings, because one `DATE` column cannot remember a day it has already
overwritten. That is a limitation of the schema and it is taken deliberately —
a `look_wears` table would remember and is not built. `DECISIONS.md` 184, and
`tests/integration/test_looks_wear.py` asserts the three-count case so it is a
decision rather than a surprise.

**`last_worn_at` moves forward only.** It is `GREATEST(last_worn_at, :date)`,
so recording a wearing for last Tuesday cannot drag a garment worn yesterday
backwards — task 3.5 asks that column which items were worn in the last three
days, and a backwards move would silently un-hide one. A look's `worn_at` and
its items' `last_worn_at` may therefore disagree, and both are true: the look
records when *it* was worn, the garment when it was last worn in anything.

**`is_saved` is not consulted.** Any look the account owns can be marked worn.
The button lives on the saved-looks screen and that is the screen's policy, not
the endpoint's.

`404` with `code: "not_found"` for a look belonging to another account, the same
code and status as one that never existed.

---

## Trips *(Stage 4)*

### The trip object

One shape for one resource, as the user object is (`DECISIONS.md` 034). Every
endpoint below that answers a trip answers **this**, and a trip's looks are
always a **sibling key** rather than a field inside it. Settled at task 4.3;
`DECISIONS.md` 195.

```json
{ "id": "uuid", "destination": "Berlin", "dest_lat": 52.52, "dest_lon": 13.41,
  "start_date": "2026-03-14", "end_date": "2026-03-17",
  "notes": "one dinner out",
  "days": [
    { "day": 1, "date": "2026-03-14",
      "temp_min_c": 8, "temp_max_c": 12, "precip_mm": 4.2, "wind_kph": 11,
      "condition": "rain",
      "rule": "Outerwear is REQUIRED, warmth 3-4. Rain expected. Strongly prefer water_resistant outerwear and closed water_resistant shoes.",
      "slots": [ { "slot": "day",     "occasion": "work",    "look_id": "uuid" },
                 { "slot": "evening", "occasion": "evening", "look_id": "uuid" } ] }
  ],
  "packing_list": {
    "item_ids": [ "uuid", "uuid" ],
    "reuse_summary": { "item_count": 8, "look_count": 4,
                       "most_reused": { "item_id": "uuid", "days": 3 } }
  },
  "created_at": "2026-08-31T09:14:22Z" }
```

**`days` is the day strip, and it is the join.** `05-FRONTEND-SPEC.md` §7 needs a
temperature and an icon per day and the looks under it, and `LookResponse`
carries no day number — one shape for every look since `DECISIONS.md` 182, and a
trip is not a reason to widen it for the other three endpoints. So the day
carries `look_id` and the client indexes the sibling `looks` array by it. The
alternative, pairing `days[i]` with `looks[i]` positionally, is an ordering
contract nothing enforces and a rendering bug that would be invisible until a day
was missing.

**`slots[]` arrived at task 4.11, and it took `occasion` and `look_id` down with
it.** A day carries one slot entry or two — `day`, then `evening` — and the split
is by what each field is a property of: the four numbers, the condition and the
rule belong to the **date**, and the occasion and the look belong to the **slot**.
The alternative was one `days[]` row per `(day, slot)` with the forecast repeated
in both, which puts one measurement in two places with nothing keeping them
equal — the same failure `DECISIONS.md` 195 refused when it declined to pair days
and looks positionally. **This is a breaking change to the trip object**, and the
trip object is answered by all five endpoints that answer a trip, `GET /trips`
included. `DECISIONS.md` 225.

**`look_id` is nullable**, and that is what the join buys over the positional
pairing. A day with no look renders as a gap; paired positionally, day 3's look
would silently slide onto day 2. The route computes the ordinal back from
`looks.for_date` and reads the slot from `looks.slot` — `LookResponse` carries
neither and Stage 4 is not a reason to widen it — so a look with no `for_date` is
placed on no day at all. **The gap is now per slot**: a repack that detaches
Monday's evening look leaves Monday's day look exactly where it is.

**`day` here is `03-AI-CONTRACTS.md`'s ordinal** — 1-based within the trip, day 1
is `start_date` — and `date` is printed beside it so no client does calendar
arithmetic to label a tab. From 4.11 it is half of a key rather than a whole one:
`(day, slot)` is what names a look, on this wire and in the model's answer alike.

**Two of the row's columns are deliberately not on the wire.** `trips.occasions`
is the request as it arrived; `days[].slots[].occasion` is that value merged with
the forecast, so the raw column would be the same data in a second shape — and
after 4.11 the merge is what turns one flat list of `(day, slot, occasion)`
entries into a day carrying its slots.
`trips.forecast` is the cached provider response — `days` is its parsed
projection, and the provider's own field names and units are not this API's
contract (`DECISIONS.md` 143).

**`packing_list.item_ids` are row UUIDs, and `reuse_summary` is an object.** The
`short_id`s the model answered with never leave the server —
`03-AI-CONTRACTS.md`'s schema carries those, and `pack_trip` maps them through
the wardrobe it sent. `reuse_summary` is computed in Python, and it is
`{ item_count, look_count, most_reused }` rather than the English sentence
`02-DATA-MODEL.md` first sketched: the sentence *"the jeans appear on 3 days"* is
user-facing text, and `CONVENTIONS.md` puts every one of those behind an i18n
key in the frontend. `most_reused` is `null` when no item is worn on more than
one day. `02-DATA-MODEL.md` carries the stored shape, which is this one.

### `POST /trips/pack`
```json
→ { "destination": "Berlin", "start_date": "2026-03-14", "end_date": "2026-03-17",
    "occasions": [ { "day": 1, "slot": "day",     "occasion": "work" },
                   { "day": 2, "slot": "day",     "occasion": "work" },
                   { "day": 2, "slot": "evening", "occasion": "evening" },
                   { "day": 3, "slot": "day",     "occasion": "casual" },
                   { "day": 4, "slot": "day",     "occasion": "work" } ],
    "notes": "one dinner out" }
← 200 { "trip": { …trip object… }, "looks": [ …LookResponse… ], "missing_pieces": [ … ] }
```

Server-side: geocode destination → fetch daily forecast → build one rule per day → single stylist call → validate → persist trip and looks.

**`occasions` carries one or two entries per day from task 4.11**, in day order,
`day` before `evening` within a day: never zero entries for a day, and never
`day` twice. The example above is a four-day trip with five looks — one dinner
out on the second night, which is the `notes` field of every trip anybody has
ever taken. The list stays flat rather than nesting slots inside days, because
`pack_trip` reads it positionally and one entry per look is what the model's
message and its answer are both shaped like; what checks it is
`TripPackRequest`'s validator, and what the rows it becomes are held to is
`uq_looks_trip_day_slot` (`02-DATA-MODEL.md`). `DECISIONS.md` 225.

`looks` are full `LookResponse` objects, the same shape `POST /looks/suggest`
answers with, each carrying `trip_id`'s row and hydrated items in the model's own
order. `missing_pieces` is `POST /looks/suggest`'s shape too, and like that
endpoint's it is **not persisted** — it describes this run, so a reopened trip
does not carry it. **There is no `message` key**, unlike the suggest response:
`trips` has no column for it and `05-FRONTEND-SPEC.md` §7 has no line that would
render it, so a sentence that survived only until the next page load would be a
field lying about what the API stores.

**Constraints, corrected against `DECISIONS.md` 190.** Maximum 14 days, and the
bound is on the **last** day: `end_date <= today + 14`. This document said
`start_date` no more than 14 days ahead until task 4.3, which admits a legal
fourteen-day trip beginning on day 14 and ending on day 27 — thirteen days past
anything Open-Meteo answers for. The bound has to bind the end or it does not
bind the provider at all. Fourteen rather than `weather.py`'s measured
`FORECAST_HORIZON_DAYS = 15` is one day of margin against a horizon that rolls
forward daily. At least **8** `ready` items, which is `POST /looks/suggest`'s
threshold plus two — the same `wardrobe_too_small` code with a different number,
and the message names the number.

**No seasonal-average fallback is offered, as data or as a message.** This
document said *"offer seasonal averages as a fallback message"* until 4.3 and
`STAGE-4` 4.2 said the opposite in the same breath — *"say so plainly rather
than guessing from seasonal averages"*. 190 settles it against the fallback: the
whole reliability argument for this feature (`DECISIONS.md` 004) is that the
weather rule is a pure function of numbers a provider measured, and a look built
on a climate average is a look built on a number nobody took.

**Ships unthrottled.** `DECISIONS.md` 191 moved the rate limiter to
`STAGE-5-qa-deploy.md` § 5.2 with all three of the limits below, rather than
closing one row of a three-row table from inside 4.4. This is the most expensive
call in the project and the exposure is recorded with a date and an owner.

Failure codes on this endpoint: `400` `trip_too_long` when `end_date` is beyond
`today + 14` **or the trip is longer than 14 days**; `400` `wardrobe_too_small`
under 8 `ready` items, checked before the geocoder so a request that cannot be
served costs nothing; `400` `destination_not_found` when the geocoder answers and
nothing matches what the user typed; `400` `forecast_unavailable` when the range
is beyond the provider's horizon and `502` `forecast_unavailable` when Open-Meteo
does not answer, exactly as `GET /weather` splits them; `502`
`geocoding_unavailable` when the geocoder does not answer at all; `502`
`stylist_failed` after the model has failed validation twice; `422`
`validation_error` for a malformed body — an `occasions` list that is not one or
two entries per day for days `1..n` in order, a day whose two entries are not
`day` then `evening`, an occasion outside the six, a slot outside the two,
`end_date` before `start_date`; `401` `invalid_token`. **The slot shapes are
`validation_error` and earn no code of their own**, which is the same test 2.4
and 2.5 applied to fields and 4.3 to `occasion`: a code exists to be rendered,
and nothing on `/trips/new` renders a body the form cannot produce.

**`trip_too_long` is two bounds, and task 4.4 is where the second one had to be
written.** `DECISIONS.md` 190 moved the bound onto the trip's last day and this
document carried that alone until 4.4 tried to implement it. **`start_date` is
not bounded below** — deliberately, on `DECISIONS.md` 184's precedent that the
server's calendar day is not the user's, and a client east of UTC routinely names
a day this server would still call yesterday. But `end_date <= today + 14` with
no lower bound admits a trip that began last March and ends next week: legal by
that rule, three hundred days long, and three hundred days of forecast asked of a
provider that answers sixteen. So the **length** is checked as well, and it is
the check `STAGE-4`'s own acceptance criterion — *a 15-day trip is rejected at
the API layer* — actually names. One code and one message for both, because both
are true of *Trips can span at most 14 days from today*. `DECISIONS.md` 201.

**Nothing bounds `start_date` in the past, and a trip therefore ages out rather
than expiring.** A trip packed today stays readable for ever; the day its
`end_date` falls outside `today + 14` it stops being **repackable**, answering
`trip_too_long`. That is the honest consequence of a forecast horizon that rolls
forward daily, and no seasonal-average fallback is offered to paper over it.

### `GET /trips`
```json
← 200 { "trips": [ { …trip object… } ], "total": 3 }
```

Query: `limit`, `offset`. Ordered `created_at DESC` with `id` as the tiebreaker,
`GET /looks`'s ordering exactly; `limit` defaults to `100` and is capped at
`200`; `total` counts the whole set. No looks — a list of trips is a list of
trip objects, and the looks for one of them come from `GET /trips/{id}`.

**Its caller arrived at task 4.10, and what stood here said it never would.**
The paragraph this replaces recorded that no Stage 4 task listed trips — 4.5 is
the form, 4.6 the packing view, 4.6b the repack and delete, 4.6a-1 and 4.6a the
swap, 4.7 the export — and concluded the endpoint was specified and built
because this document is authoritative rather than because anything would ever
read it, the same shape as `GET /me/locations/search` shipping ahead of its
caller (`AUDITS.md` **O-16**'s family). That was true for six tasks. `/trips` is
now the list, it calls this endpoint on arrival, and `05-FRONTEND-SPEC.md` §7
draws the screen.

**The caller sends neither `limit` nor `offset`.** It takes both defaults, so a
browser reads at most 100 trips and the `total` it is handed is rendered
nowhere. Pagination is not built and no task owns it — which is a real ceiling
rather than a theoretical one, because nothing on that screen tells a user with
101 trips that the last one is missing.

Failure codes: `422` `validation_error`, `401` `invalid_token`.

### `GET /trips/{id}`
```json
← 200 { "trip": { …trip object… }, "looks": [ …LookResponse… ] }
```

`POST /trips/pack`'s response minus `missing_pieces`, which was never stored.
`looks` are the trip's looks — `WHERE trip_id = :id`, ordered by `for_date` —
hydrated in `look_items.position` order like every other look this API answers.

`404` with `code: "not_found"` for a trip belonging to another account, the same
code and status as one that never existed, per `06-TESTING-STRATEGY.md`.

**A malformed id is a `422`, not a `404`, and this list said otherwise until
task 4.6 built the client for it.** `trip_id` is declared `uuid.UUID`, so
FastAPI rejects `/trips/abc` before `read_trip` runs and answers `detail`
without a `code` — the same shape every other path-parameter route here
produces, and the same one `POST /trips/pack` already reads a status for. The
line is added rather than the route loosened: a route that accepted any string
would push the parse into the query and answer `404` for a value that was never
an id. `401` `invalid_token` is unchanged.

### `DELETE /trips/{id}`
```
← 204  (no body)
```

**A hard delete, not an archive.** `DELETE /items/{id}` archives because a
garment is referenced by every look that ever wore it and by the wear history
`GET /items/stats` counts; a trip is referenced by nothing but its own looks, and
`trips` has no `is_archived` column to set. The `ON DELETE CASCADE` on
`looks.trip_id` is already declared in migration `0005`, and it reaches
`look_items` in a second hop through `0002`'s own cascade. `DECISIONS.md` 195.

**`AUDITS.md` O-32 is settled here at task 4.4, and this endpoint takes the
cascade deliberately.** A trip look can have been saved, rated or worn, and
`feedback` is what `POST /looks/suggest`'s preference block counts from task 3.5
— so deleting the trip does delete those rows, and that is what the user asked
for: a delete is a deliberate act on the whole trip, where a repack is an edit to
a trip they are keeping. The two endpoints therefore answer O-32 differently, and
the audit recommended exactly that.

**One consequence is stated rather than fixed.** The `items.wear_count` those
looks incremented is not reversed, because a garment worn in Berlin was worn —
which leaves a wear count that no screen can reconcile against the number of
looks it can show. `DECISIONS.md` 200.

`404` with `code: "not_found"` for another account's trip. `401` `invalid_token`.

**Its caller arrived at task 4.6b**, as the second control in `/trips/:id`'s
footer row: two presses, the second one sending the request, and `/wardrobe` on
`204` because there is no trips list to return to. The armed label is where the
cascade above is finally said to a user — *"Tap again to delete. Saved looks
from this trip go too."* — which is the only place in the product that names it.
`AUDITS.md` **O-33**, `DECISIONS.md` 126 and 207.

**A second caller arrived at task 4.10**, one per row on `/trips`, with the same
two presses and the same armed sentence — the copy is reused rather than
rewritten, because a second control destroying the same rows has to say the same
thing about them. That one removes the row optimistically and puts it back at
the index it left from when the request fails. **The line above about `/wardrobe`
is now stale**: it goes there on the reasoning that there is no trips list to
return to, and there is one. `AUDITS.md` **O-34** carries the change, left
deliberately unmade here — 4.10 edited no screen it did not build.

### `POST /trips/{id}/repack`
```json
← 200 { "trip": { …trip object… }, "looks": [ …LookResponse… ], "missing_pieces": [ … ] }
```

Re-runs packing with a refreshed forecast against the trip's stored destination,
dates and occasions, and replaces the existing looks. Same body shape as
`POST /trips/pack`, same failure codes, and the same unthrottled exposure —
`DECISIONS.md` 191 again, one endpoint along.

**"Replaces the existing looks" is `AUDITS.md` O-32's other half, and task 4.4
took the audit's option 2.** A look that was saved, rated or marked worn is
**detached** — `trip_id = NULL` and `slot = NULL`, from task 4.12 — and the rest
are deleted. A tap meant to refresh the weather does not empty three days out of `/saved` or switch the
stylist's learned preferences back off. The cost is a look on `/saved` belonging
to no trip, whose `weather_note` describes a forecast for a city the row no
longer names; that is accepted, because the alternative destroys the signal
outright. Refusing the repack while any look is marked was rejected: it asks the
user to un-save a look in order to repack, which is damaging the record to get
past a guard protecting it.

**`pack_trip` runs first, and nothing is destroyed until it has answered.** This
is not in O-32's recommendation and it is the half that matters most: a repack
that detached and deleted before calling the model would answer `502
stylist_failed` having already emptied a trip the user still has. The detach, the
delete and the new looks are one transaction, downstream of the model call.

**It takes no body, and it re-geocodes.** The destination, the dates, the notes
and the occasions — slots and all, read back from the column `0006` backfilled —
are the trip's own, and a repack that accepted new ones would be an edit endpoint
this document does not describe. The stored `dest_lat`/`dest_lon` are re-derived from the destination string rather than
reused, because `pack_trip` owns the lookup; so a repack can answer
`destination_not_found` for a trip that packed cleanly last week, and a trip's
coordinates can move between two packs. `DECISIONS.md` 200 and 202.

**Its caller arrived at task 4.6b**, and it takes this endpoint's whole surface:
the twenty-second wait, the same four status lines the pack shows, and all seven
failure codes. Six of the seven messages are the pack's word for word, because
the conditions are the same either side of a packed trip; the general fallback
is its own sentence, because *"We couldn't pack this trip"* reads oddly under a
trip that is visibly packed. **A failure leaves the trip on screen** rather than
replacing it, which is the paragraph above rendered: nothing is destroyed until
`pack_trip` has answered, so a repack that fails costs the user nothing and the
interface says so. `AUDITS.md` **O-33**, `DECISIONS.md` 207.

### `POST /trips/{trip_id}/swap`
```json
→ { "day": 3, "slot": "evening", "item_id": "uuid", "replace_role": "shoes",
    "exclude_item_ids": ["uuid"] }
← 200 { "trip": { …trip object… }, "looks": [ …LookResponse… ] }
```

One garment in one slot of one day, replaced against that day's **stored** plan.
The trip object comes back whole because `packing_list` has moved, so the day
strip, the reuse summary and every look are answered together — `GET /trips/{id}`'s shape
exactly, and no `missing_pieces`: a gap described against one day is not the
trip's.

**This is not `POST /looks/suggest`, and four things in that endpoint are why.**
It forecasts the user's **home** coordinates — its body carries none, by
`DECISIONS.md` 151 and 173 — so a swap routed through it would dress a Berlin
day for the weather at home. It answers `home_location_missing` for an account
that can pack a trip perfectly well, since `POST /trips/pack` never reads those
columns. It persists a look with **no `trip_id`**, so the trip would answer the
old look on the next read and the swap would live only in the browser. And it
never touches `trips.packing_list`. What it *does* lend is everything below
HTTP: this endpoint builds a `StylistContext`, runs the **single-day** rule
order — 1, 2, 4, 6, 7, 8, 9 — and reuses the same retry loop.

**It asks no provider but the model.** No geocode, because nothing about a swap
moves the trip; no forecast, because `trips.forecast` already holds this day's
four numbers, its condition and **the rule sentence the model obeyed**. That
stored rule is sent rather than rebuilt: `DECISIONS.md` 199 put it in the column
so a plan cannot re-render under a band table the rest of its days were never
judged against, and a swap is an edit to one day of that plan. Four of the
pack's seven codes are therefore unreachable here — `trip_too_long`,
`destination_not_found`, `geocoding_unavailable` and `forecast_unavailable` —
and **the 14-day bound is deliberately not rechecked**: a trip that has aged out
of being repackable (`DECISIONS.md` 201) can still have its shoes changed,
because the forecast this endpoint reads was taken while it was inside the
horizon.

**`slot` is required, and it arrived with the feature at task 4.11.** `day`
alone stopped naming a look the moment a day could hold two, and the badge that
sends this body sits inside one of them — so the client already knows which, and
a server that guessed would guess wrong half the time on exactly the days this
feature exists for. It is required rather than defaulted to `day` for
`replace_role`'s reason one field along: this endpoint does one thing, the caller
always knows the answer, and a default would accept a body no correct client
sends. `DECISIONS.md` 225.

**The client sends the role; the server derives the locks.** `locked_item_ids`
is the day's look minus `item_id`, read off the row rather than sent — a
client-supplied copy is a second description of a look the server is holding,
and the two can disagree. `replace_role` is **not** derived, and that asymmetry
is deliberate: `ROLE_BY_CATEGORY` lives only in the frontend's `enums.ts`
because this API validates the six values and derives none, so a map on this
side would be the second copy of a table kept in one place on purpose
(`AUDITS.md` **O-25**). `replace_role` is **required** here, unlike on
`POST /looks/suggest`: the ↻ badge always sends one, so requiring it deletes the
role-without-locks body rather than validating it.

**`exclude_item_ids` accumulates in the client**, across taps on one day, and
the garment being replaced is appended to it by the server. Rule 8 then refuses
a look containing an excluded id, which is what makes *the swap that rejected a
shoe cannot answer with it* a rule rather than a hope. The server cannot derive
the accumulated half: the looks that carried those rejections have been replaced
by this endpoint and are gone.

**What happens to the look that was there is `AUDITS.md` O-32 one level down.**
A look that was saved, rated or worn is **detached** — `trip_id = NULL` and
`slot = NULL`, and no other column touched — and an unmarked one is deleted. Same
three columns, same reasoning, and the same predicate the repack uses. Two
differences from the repack are worth stating: this detach leaves **no gap**, because the new look
takes the day in the same transaction, and `items.wear_count` is not reversed,
for the reason it never is. And **the model runs first**: the detach, the
delete, the new look and the `packing_list` write are one transaction downstream
of the answer, so a `502` costs the user nothing.

**The slot is the second column the detach clears, and migration `0006` is why.**
`ck_looks_slot_belongs_to_a_trip` reads `trip_id` and `slot` together in both
directions, so a row that kept its slot on the way out of a trip is one the
database refuses — the detach would fail and take the repack or the swap with it.
Nothing a reader has is lost: a detached look has no trip to be the evening of,
and `/saved` filters on `is_saved` alone. The three columns the paragraph above
promises — `is_saved`, `feedback` and `worn_at` — are still named by neither
statement, and the repack's detach clears the slot for the same reason.
`DECISIONS.md` 225, `02-DATA-MODEL.md` under `looks`.

**`packing_list` is recomputed here**, which makes this the column's second
writer after `POST /trips/pack`. Survivors keep their existing positions, an id
no look still wears is dropped, and anything new is appended in day then
`look_items.position` order. The order is load-bearing rather than cosmetic:
`reuse_summary`'s tie-break is *most days, then first in the packing list*, so a
list rebuilt from scratch would let one plan summarise two ways. It is computed
over every look rather than patched around the one that changed, which makes
*every look item appears in the packing list* true by construction.

`422` with `code: "item_not_in_look"` when `item_id` names no garment in that
slot's look. Its own code rather than `validation_error`, on
`locked_unavailable`'s reasoning: it is the `422` a **correct** client provokes,
by holding a look that a repack in another tab has since replaced. **A slot with
no look answers the same code** — there is no look, so the item is not in it —
rather than earning a twentieth code for a state the screen draws no badge on.
**And a slot this day has not got answers it too**, from 4.11: a body naming
`evening` on a day packed with one look is the same sentence as a body naming a
garment that is not there, and both are what a stale screen sends after a repack.
The bound on `day` keeps its own `validation_error` below, because that one is
about a trip's shape rather than a day's.

`422` with `code: "validation_error"` when `day` is outside `1..n`. The bound is
the route's rather than the request schema's, for `trip_too_long`'s reason: the
schema cannot know how many days a trip has, so a `ge=1` there would answer `0`
and `99` with two different shapes of one refusal.

`422` with `code: "locked_unavailable"` when another garment in that day's look
is no longer styleable — archived from a second tab since the trip was packed.
Reached from the row rather than from the body, and refused here because rule 1
would otherwise call the id a hallucination two model calls later.

`400` with `code: "wardrobe_too_small"` below **6** usable items — `POST
/looks/suggest`'s threshold, not this section's eight. A swap builds one look
for one day and runs the single-day rule order, where rule 11 does not run at
all; eight would refuse a look the model can build.

`502` with `code: "stylist_failed"` when validation fails twice, or the model
answers nothing usable, or the provider does not answer. `404` `not_found`,
`401` `invalid_token`. Unthrottled, like everything else here —
`DECISIONS.md` 191.

`DECISIONS.md` 209.

---

## Health

### `GET /health`
```json
← 200 { "status": "ok", "db": "ok",    "version": "0.4.0" }
← 200 { "status": "ok", "db": "error", "version": "0.4.0" }
```
Used by Render's health check and as the first Playwright smoke test.

Always 200, including when the database is unreachable. `status` reports the process, `db` reports the dependency — see `DECISIONS.md` 027.

`/health` is the one route **outside** the `/api/v1` prefix. It is mounted at the root because `07-DEPLOYMENT.md` pins Render's health check to `/health`, and because a liveness probe should not be versioned alongside the application's own contract.

The `version` value above is illustrative. `APP_VERSION` is a constant in `app/core/config.py` and does **not** track the task or stage number — do not read `0.4.0` as "task 0.4".

---

## Rate limits

Per user, enforced with a simple in-memory counter — Redis is not worth adding here.

| Endpoint | Limit |
|---|---|
| `POST /items/upload` | 100 files per hour |
| `POST /looks/suggest` | 30 per hour |
| `POST /trips/pack` | 10 per hour |

`429` with `code: "rate_limited"` and a `Retry-After` header. This is the answer to "how do you stop a demo account from burning your OpenAI budget?"

**None of the three limits above is enforced today, and the counter now has a task.** The gap was found at `STAGE-0` 0.7, which built `POST /items/upload` without it, and recorded rather than quietly carried: *whoever writes the rate limiter should add it to a stage file first.* That instruction was honoured at task 4.2's commit — `DECISIONS.md` 191 puts the mechanism and all three rows in `STAGE-5-qa-deploy.md` § 5.2, beside the integration tests that have named rate limits since Stage 0, with a commit checkpoint of its own. **`STAGE-4` 4.4 therefore builds none of it**, and its constraints line naming "10 packs per hour" is a statement about this table rather than about that task. Until 5.2, every row here is a specification with no enforcement, and `POST /trips/pack` — the most expensive call in the project — is the one that costs the most to leave open.

**Known limitation:** `/auth/*` is not on this table and is not throttled. Password guessing against `POST /auth/login` and email enumeration through `POST /auth/register` are both unlimited. The table above exists to cap cost, not to resist attack, and the omission is recorded rather than quietly carried — see `DECISIONS.md` 037 for the enumeration side of it.

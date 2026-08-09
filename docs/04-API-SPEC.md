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

Every field but `id`, `email` and `created_at` is nullable and is `null` on a fresh account. One shape for one resource — see `DECISIONS.md` 034.

Failure codes on this group: `409` `email_exists`, `401` `invalid_credentials`, `401` `invalid_token`, `422` `validation_error`. Every `401` carries `WWW-Authenticate: Bearer`. Unknown keys in either request body are a `422` rather than being ignored (`DECISIONS.md` 039).

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

### `GET /me/locations/search?q=berlin`
Proxies Open-Meteo geocoding. Returns up to 5 `{ name, country, lat, lon }`.
Used by both the profile screen and the trip form, so the frontend never calls a third-party API directly.

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

**The full item** is every column of `items` except that `image_public_id` is accompanied by `image_url`, a ready-built **thumbnail** URL (`w_300,h_300,c_pad,b_white`). The `public_id` is what `cloudinary-url.pipe.ts` builds every other transform from; the thumbnail is included because it is what the grid renders on arrival. See `DECISIONS.md` 050.

All eleven parameters above are implemented as of task 0.7. **An unknown or misspelled query parameter is still silently ignored and still returns `200` with an unfiltered list** — `?colour_primary=navy` filters nothing and says nothing. Query strings have no `extra="forbid"` equivalent, so `DECISIONS.md` 039's guarantee genuinely stops at request bodies. Rejecting unknown query keys would be one piece of middleware; **task 5.4** owns deciding whether to add it or to publish it as a known issue, and it is named here rather than left implied (`DECISIONS.md` 051).

Pagination defaults to 100, and `05-FRONTEND-SPEC.md` filters client-side "over the loaded collection". A wardrobe above 100 items therefore filters over the first page only unless the client passes `limit`. The wardrobe screen must pass it; `01-ARCHITECTURE.md` sizes a realistic wardrobe at 80–150.

### `GET /items/{id}` · `PATCH /items/{id}` · `DELETE /items/{id}`

`PATCH` accepts any tag field. It sets `user_edited = true` and validates every value against the closed vocabulary — the same validator the AI output passes through. `422` with the offending field on an invalid value.

`DELETE` soft-deletes by setting `is_archived = true`. The Cloudinary asset is retained; deleted items may still be referenced by historical looks.

An item that exists but belongs to another user returns `404` with `code: "not_found"` on every one of these — not `403`. One code for every resource, because telling a caller that a row exists but is not theirs is an existence oracle for other people's wardrobes (`DECISIONS.md` 043).

### `POST /items/{id}/retag`
Re-runs vision tagging. `409` if `user_edited` is true unless `?force=true` is passed — a manual correction must not be silently overwritten.

### `GET /items/stats`
```json
← 200 {
  "total": 138, "by_category": { "top": 41, … },
  "by_color": { "black": 22, … },
  "processing": 0, "failed": 2,
  "never_worn": 34, "most_worn": [ { item } ]
}
```
Drives the wardrobe dashboard. `never_worn` and `most_worn` return zeros until Stage 3.

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

Cached in memory for 30 minutes per `(lat, lon, date)`.

---

## Looks

### `POST /looks/suggest`
```json
→ { "occasion": "work", "date": "2026-03-14",
    "include_outerwear": null, "notes": "meeting with a client",
    "anchor_item_id": null, "locked_item_ids": [], "exclude_item_ids": [],
    "replace_role": null }
← 200 { …StylistResponse from 03-AI-CONTRACTS, item_ids hydrated to full objects… }
```

`include_outerwear`: `true` forces a coat, `false` forbids one, `null` lets the weather rule decide.
`occasion`: one of `casual · work · evening · sport · formal · travel`.

**`anchor_item_id`** — build the look around this item. It must appear in the result. This powers "Style around this" from the item detail screen, and it is the direct answer to the original problem: *I am holding this garment and do not know what goes with it.*

**`locked_item_ids` + `replace_role` + `exclude_item_ids`** — swap a single item while keeping the rest of the look. `replace_role` is one of `top · bottom · outer · shoes · bag · accessory`. This powers the ↻ button on each item in a look card.

All four fields are optional and default to null or empty. A request with none of them behaves exactly as before.

`422` if `anchor_item_id` or any locked ID does not belong to this user, or if `replace_role` is given without `locked_item_ids`.

`400` with `code: "wardrobe_too_small"` when fewer than 6 items are `ready`.
`502` with `code: "stylist_failed"` when validation fails twice.

The look is persisted with `is_saved = false` before the response is returned.

### `GET /looks`
Query: `is_saved`, `trip_id`, `from_date`, `to_date`. Returns looks with hydrated items.

### `GET /looks/{id}` · `DELETE /looks/{id}`

### `PATCH /looks/{id}` *(Stage 3)*
```json
→ { "is_saved": true, "feedback": 1, "title": "Client meeting" }
```

### `POST /looks/{id}/wear` *(Stage 3)*
```json
→ { "date": "2026-03-14" }
← 200 { look }
```
Sets `looks.worn_at` and, in the same transaction, increments `wear_count` and updates `last_worn_at` on every item in the look. Idempotent per date — calling it twice for the same date does not double-count.

---

## Trips *(Stage 4)*

### `POST /trips/pack`
```json
→ { "destination": "Berlin", "start_date": "2026-03-14", "end_date": "2026-03-17",
    "occasions": [ { "day": 1, "occasion": "work" }, { "day": 2, "occasion": "work" },
                   { "day": 3, "occasion": "casual" }, { "day": 4, "occasion": "evening" } ],
    "notes": "one dinner out" }
← 200 { "trip": { … }, "looks": [ … ], "packing_list": { … }, "missing_pieces": [ … ] }
```

Server-side: geocode destination → fetch daily forecast → build one rule per day → single stylist call → validate → persist trip and looks.

Constraints: maximum 14 days; `start_date` no more than 14 days ahead (the free forecast horizon); at least 8 `ready` items.
`400` with `code: "forecast_unavailable"` when the dates fall outside the horizon — offer seasonal averages as a fallback message, do not guess.

### `GET /trips` · `GET /trips/{id}` · `DELETE /trips/{id}`

### `POST /trips/{id}/repack`
Re-runs packing with a refreshed forecast. Replaces the existing looks.

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

**No task in any stage file builds this table.** It is specified here and `STAGE-5` asserts on it, but `STAGE-0` 0.7 built `POST /items/upload` without it and no task between them owns it. That gap was found at task 0.7 and is recorded rather than quietly carried: whoever writes the rate limiter should add it to a stage file first.

**Known limitation:** `/auth/*` is not on this table and is not throttled. Password guessing against `POST /auth/login` and email enumeration through `POST /auth/register` are both unlimited. The table above exists to cap cost, not to resist attack, and the omission is recorded rather than quietly carried — see `DECISIONS.md` 037 for the enumeration side of it.

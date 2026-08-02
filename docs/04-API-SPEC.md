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
`multipart/form-data`, field `files` (repeatable, 1–20 files, ≤ 10 MB each, `image/*` only).

```json
← 202 {
  "items": [
    { "id": "…", "short_id": "A3F9K2", "status": "processing",
      "image_url": "https://res.cloudinary.com/…", "created_at": "…" }
  ]
}
```

Returns as soon as the images are in Cloudinary and the rows are written. Tagging continues in the background. `413` if any file exceeds the limit; `415` for non-images.

### `GET /items`
Query: `status`, `category`, `color_primary`, `formality_min`, `formality_max`, `warmth_min`, `warmth_max`, `search`, `include_archived`, `limit`, `offset`.

```json
← 200 { "items": [ { …full item… } ], "total": 138 }
```

`search` matches `display_name` only — a simple `ILIKE`, no full-text index.

### `GET /items/{id}` · `PATCH /items/{id}` · `DELETE /items/{id}`

`PATCH` accepts any tag field. It sets `user_edited = true` and validates every value against the closed vocabulary — the same validator the AI output passes through. `422` with the offending field on an invalid value.

`DELETE` soft-deletes by setting `is_archived = true`. The Cloudinary asset is retained; deleted items may still be referenced by historical looks.

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
← 200 { "status": "ok", "db": "ok", "version": "0.4.0" }
```
Used by Render's health check and as the first Playwright smoke test.

---

## Rate limits

Per user, enforced with a simple in-memory counter — Redis is not worth adding here.

| Endpoint | Limit |
|---|---|
| `POST /items/upload` | 100 files per hour |
| `POST /looks/suggest` | 30 per hour |
| `POST /trips/pack` | 10 per hour |

`429` with `code: "rate_limited"` and a `Retry-After` header. This is the answer to "how do you stop a demo account from burning your OpenAI budget?"

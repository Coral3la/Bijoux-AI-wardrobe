from pydantic import BaseModel


class LocationResult(BaseModel):
    # The four keys `04-API-SPEC.md` names, and not the twenty the provider
    # sends. `admin1` would disambiguate the two Berlins the live call returned
    # and is deliberately not here: the document is authoritative over the wire
    # shape, and widening it is a decision rather than a convenience.
    name: str
    country: str | None
    lat: float
    lon: float


class LocationSearchResponse(BaseModel):
    # Wrapped rather than a bare array, like `GET /items` — a top-level array
    # has nowhere to grow a key and nowhere to put a count.
    results: list[LocationResult]

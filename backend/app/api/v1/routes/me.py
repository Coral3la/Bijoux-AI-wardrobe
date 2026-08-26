from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import ApiError
from app.models.user import User
from app.schemas.location import LocationResult, LocationSearchResponse
from app.schemas.user import UserResponse, UserUpdate
from app.services.geocoding import MIN_QUERY_LENGTH, GeocodingError, search_locations

router = APIRouter(prefix="/me", tags=["me"])

# Stripped before it is measured, so two spaces is a 422 rather than a request
# for a place called "  ". Same ordering lesson as `DisplayName`: strip runs
# first, and `Field(strip_whitespace=True)` would silently do nothing (072).
SearchQuery = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=MIN_QUERY_LENGTH), Query()
]


@router.patch("")
def update_me(
    changes: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """The profile, edited a field at a time.

    A synchronous `def`, unlike the search below it: this one talks to the
    database and SQLAlchemy is synchronous throughout this project.
    """
    # exclude_unset is what separates "clear this field" from "leave it alone":
    # without it the first PATCH nulls every column the client did not send.
    # `PATCH /items/{id}` reads the same way for the same reason.
    supplied = changes.model_dump(exclude_unset=True)
    if not supplied:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "request: at least one field must be supplied.",
        )

    for field, value in supplied.items():
        setattr(current_user, field, value)
    db.commit()
    return UserResponse.model_validate(current_user)


@router.get("/locations/search")
async def location_search(
    q: SearchQuery,
    current_user: User = Depends(get_current_user),
) -> LocationSearchResponse:
    """Open-Meteo's geocoder, proxied so the browser holds one origin.

    No match is a `200` with an empty list. The alternative — a `404` — would
    fire on every keystroke that has not finished spelling a city, which is
    what a type-ahead does by design.
    """
    try:
        locations = await search_locations(q)
    except GeocodingError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "geocoding_unavailable",
            "Location search is unavailable. Try again shortly.",
        ) from exc

    return LocationSearchResponse(
        results=[
            LocationResult(
                name=location.name,
                country=location.country,
                lat=location.lat,
                lon=location.lon,
            )
            for location in locations
        ]
    )

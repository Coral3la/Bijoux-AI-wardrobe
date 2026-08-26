import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import get_current_user
from app.core.errors import ApiError
from app.models.user import User
from app.schemas.weather import WeatherResponse
from app.services.weather import (
    FORECAST_HORIZON_DAYS,
    ForecastOutOfRangeError,
    ForecastProviderError,
    build_rule,
    get_forecast,
)

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("")
async def weather(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    date: datetime.date,
    current_user: User = Depends(get_current_user),
) -> WeatherResponse:
    """The forecast and the rule string built from it.

    `async def` rather than `def`: the only call that leaves this process is an
    awaited HTTP request, so it belongs on the event loop. This is the opposite
    of `POST /items/upload`, which is synchronous because Cloudinary's client
    blocks — `DECISIONS.md` 049 draws the line.
    """
    try:
        forecast = await get_forecast(lat, lon, date)
    except ForecastOutOfRangeError as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "forecast_unavailable",
            f"A forecast is only available up to {FORECAST_HORIZON_DAYS} days ahead.",
        ) from exc
    except ForecastProviderError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "forecast_unavailable",
            "The forecast service is unavailable. Try again shortly.",
        ) from exc

    return WeatherResponse(
        date=forecast.date,
        temp_min_c=forecast.temp_min_c,
        temp_max_c=forecast.temp_max_c,
        precip_mm=forecast.precip_mm,
        wind_kph=forecast.wind_kph,
        condition=forecast.condition,
        # temp_max_c, not the minimum and not a mean. 04-API-SPEC.md's own
        # worked example returns min 12 / max 19 and prints the 16-21 rule,
        # which only agrees with itself under the maximum. DECISIONS.md 142.
        rule=build_rule(forecast.temp_max_c, forecast.precip_mm, forecast.wind_kph),
    )

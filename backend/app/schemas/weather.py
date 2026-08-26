import datetime

from pydantic import BaseModel

from app.enums import Condition


class WeatherResponse(BaseModel):
    date: datetime.date
    temp_min_c: float
    temp_max_c: float
    precip_mm: float
    wind_kph: float
    condition: Condition
    # Exactly the string that goes into the stylist prompt. `04-API-SPEC.md`
    # exposes it on purpose: it is what makes the weather behaviour inspectable
    # from outside the process, and it is trivial to assert on in a test.
    rule: str

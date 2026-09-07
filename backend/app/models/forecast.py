"""A day's forecast as the provider last answered it, kept so that an outage or
an exhausted quota still produces one.

Migration `0008` creates this table. It is the durable half of the cache in
`services/weather.py` and nothing else reads it: every row is written by
`_write_stored` after a provider answer and read by `_read_stored` before one.
`DECISIONS.md` 235.

**The key is the rounded coordinate pair the in-memory cache already uses**,
stored as `DOUBLE PRECISION` because that is the type a Python float *is*: the
double `round(lat, COORD_PRECISION)` produces is written and read back
bit-identical, so a lookup on the same rounding matches. `REAL` — which is what
`users.home_lat` is, and the reason 145 rounds at all — cannot hold 32.08 and
would never match it.

The four values are the same doubles for the same reason: the number served on
fallback is the number the provider gave, not a `float4` approximation of it.
`condition` is the enum's value as text, as `trips.forecast` already carries it.

No user, no foreign key: a forecast is a fact about a place and a day and
belongs to nobody. `fetched_at` is what decides whether a row is a normal hit
or a fallback. It is the application's clock rather than a `now()` default
because freshness is judged against the application's clock too, and one clock
on both sides of the comparison cannot disagree with itself.
"""

import datetime

from sqlalchemy import TIMESTAMP, Date, Double, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StoredForecast(Base):
    __tablename__ = "forecasts"

    lat: Mapped[float] = mapped_column(Double, primary_key=True)
    lon: Mapped[float] = mapped_column(Double, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)

    temp_min_c: Mapped[float] = mapped_column(Double)
    temp_max_c: Mapped[float] = mapped_column(Double)
    precip_mm: Mapped[float] = mapped_column(Double)
    wind_kph: Mapped[float] = mapped_column(Double)
    condition: Mapped[str] = mapped_column(Text)

    fetched_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(timezone=True))

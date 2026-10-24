"""Timestamp helpers. All internal comparisons are done in UTC; UK local time
(Europe/London) is used only to decide which delivery day an interval belongs to
and to place the day-ahead cutoff, so DST transitions are handled correctly."""
from datetime import date, time, timedelta

import pandas as pd

UK_TZ = "Europe/London"


def to_utc(series: pd.Series) -> pd.Series:
    """Parse ISO strings / datetimes to tz-aware UTC. Naive values are assumed UTC."""
    return pd.to_datetime(series, utc=True)


def parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def decision_cutoff_utc(delivery_date: date, cutoff_uk: time) -> pd.Timestamp:
    """Cutoff = (delivery_date - 1 day) at `cutoff_uk` UK local time, returned in UTC."""
    d_minus_1 = delivery_date - timedelta(days=1)
    local = pd.Timestamp.combine(d_minus_1, cutoff_uk).tz_localize(UK_TZ)
    return local.tz_convert("UTC")


def uk_delivery_date(start_time_utc: pd.Series) -> pd.Series:
    """UK local calendar date of each delivery interval start."""
    return start_time_utc.dt.tz_convert(UK_TZ).dt.date

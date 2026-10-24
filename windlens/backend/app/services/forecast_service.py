"""Decision-time forecast selection: for each delivery interval, the latest
forecast published at or before the day-ahead cutoff (no look-ahead leakage)."""
import pandas as pd

from app.utils.timestamps import decision_cutoff_utc, parse_hhmm, to_utc, uk_delivery_date

DEFAULT_CUTOFF_UK = "09:20"  # earliest main GB day-ahead gate closure (EPEX hourly)


def prepare_forecasts(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[["startTime", "publishTime", "generation"]].copy()
    df["startTime"] = to_utc(df["startTime"])
    df["publishTime"] = to_utc(df["publishTime"])
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna(subset=["startTime", "publishTime", "generation"])
    return df.drop_duplicates(subset=["startTime", "publishTime", "generation"])


def tag_availability(forecasts: pd.DataFrame, cutoff_uk: str = DEFAULT_CUTOFF_UK) -> pd.DataFrame:
    """Adds delivery_date, cutoff and available_at_cutoff to every forecast version."""
    cutoff_t = parse_hhmm(cutoff_uk)
    df = forecasts.copy()
    df["delivery_date"] = uk_delivery_date(df["startTime"])
    cutoffs = {d: decision_cutoff_utc(d, cutoff_t) for d in df["delivery_date"].unique()}
    df["cutoff"] = df["delivery_date"].map(cutoffs)
    df["available_at_cutoff"] = df["publishTime"] <= df["cutoff"]
    return df


def select_decision_forecasts(forecasts: pd.DataFrame, cutoff_uk: str = DEFAULT_CUTOFF_UK) -> pd.DataFrame:
    """One row per startTime: latest forecast with publishTime <= cutoff.
    Intervals with no eligible forecast are absent (never filled)."""
    tagged = tag_availability(forecasts, cutoff_uk)
    eligible = tagged[tagged["available_at_cutoff"]]
    eligible = eligible.sort_values(["startTime", "publishTime"])
    return eligible.drop_duplicates(subset="startTime", keep="last").reset_index(drop=True)

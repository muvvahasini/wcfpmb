"""Forecast-vs-actual matching and error metrics. error = forecast - actual
(positive bias = over-forecast, negative = under-forecast)."""
import numpy as np
import pandas as pd

from app.utils.timestamps import to_utc


def prepare_actuals(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    if "fuelType" in df.columns:
        df = df[df["fuelType"] == "WIND"]
    df = df[["startTime", "generation"]].copy()
    df["startTime"] = to_utc(df["startTime"])
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna(subset=["startTime", "generation"]).drop_duplicates()
    conflicts = df[df.duplicated("startTime", keep=False)]
    if not conflicts.empty:
        raise ValueError(f"{conflicts['startTime'].nunique()} actual intervals have conflicting values")
    df["hour"] = df["startTime"].dt.floor("h")
    complete_hours = []
    for hour, group in df.groupby("hour"):
        expected = {hour, hour + pd.Timedelta(minutes=30)}
        if len(group) == 2 and set(group["startTime"]) == expected:
            complete_hours.append(hour)

    hourly = df[df["hour"].isin(complete_hours)].groupby("hour", as_index=False)["generation"].mean()
    return hourly.rename(columns={"hour": "startTime"})


def match(selected: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Inner join on delivery interval (1:1 by construction); adds signed/abs error."""
    assert selected["startTime"].is_unique and actuals["startTime"].is_unique
    m = selected.merge(actuals, on="startTime", suffixes=("_forecast", "_actual"), how="inner")
    m["error"] = m["generation_forecast"] - m["generation_actual"]
    m["abs_error"] = m["error"].abs()
    return m


def compute_metrics(matched: pd.DataFrame, n_forecast: int, n_actual: int, mape_floor_mw: float = 100.0) -> dict:
    n = len(matched)
    base = {"matched": n, "forecast_intervals": n_forecast, "actual_intervals": n_actual,
            "coverage_of_actuals": (n / n_actual) if n_actual else 0.0}
    if n == 0:
        return {**base, "mae": None, "rmse": None, "bias": None, "p90_abs_error": None, "mape": None}
    e = matched["error"].to_numpy(dtype=float)
    ok = matched["generation_actual"] > mape_floor_mw  # % error undefined near zero
    mape = float((matched.loc[ok, "abs_error"] / matched.loc[ok, "generation_actual"]).mean() * 100) if ok.any() else None
    return {**base, "mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "bias": float(e.mean()), "p90_abs_error": float(np.percentile(np.abs(e), 90)),
            "mape": mape, "mape_excluded": int((~ok).sum())}

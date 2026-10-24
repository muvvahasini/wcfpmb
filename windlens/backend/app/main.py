import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.services.forecast_service import DEFAULT_CUTOFF_UK, prepare_forecasts, select_decision_forecasts, tag_availability
from app.services.metrics_service import compute_metrics, match, prepare_actuals
from app.utils.timestamps import UK_TZ, to_utc, uk_delivery_date
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("DATA_DIR", ROOT / "data"))
CUTOFF_RE = r"^([01]\d|2[0-3]):[0-5]\d$"
JANUARY_DECISION_START = date(2026, 1, 1)
JANUARY_DECISION_END = date(2026, 1, 31)
DELIVERY_START = JANUARY_DECISION_START + timedelta(days=1)
DELIVERY_END = JANUARY_DECISION_END + timedelta(days=1)

app = FastAPI(title="WindLens API")
app.add_middleware(CORSMiddleware, allow_methods=["GET"], allow_headers=["*"],
                   allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","))


@lru_cache
def load():
    try:
        processed = DATA / "processed"
        a = prepare_actuals(pd.read_csv(processed / "actuals.csv"))
        f = prepare_forecasts(pd.read_csv(processed / "forecasts.csv"))
    except FileNotFoundError:
        raise HTTPException(
            503,
            "Processed data is missing. Run scripts/ingest.py or scripts/process_data.py first.",
        )
    return a, f


@lru_cache(maxsize=32)
def selected(cutoff: str):
    return select_decision_forecasts(load()[1], cutoff)


def records(df: pd.DataFrame):
    return json.loads(df.to_json(orient="records", date_format="iso"))


def clean(d: dict):
    return {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in d.items()}


Cutoff = Query(DEFAULT_CUTOFF_UK, pattern=CUTOFF_RE, description="Day-ahead decision cutoff, HH:MM UK time on D-1")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/metadata")
def metadata(cutoff: str = Cutoff):
    sel = selected(cutoff)
    if sel.empty:
        raise HTTPException(404, "No decision-time forecasts available")
    sel = sel[
        (sel["delivery_date"] >= DELIVERY_START)
        & (sel["delivery_date"] <= DELIVERY_END)
    ]
    actual_dates = set(uk_delivery_date(load()[0]["startTime"]))
    common = sel[sel["delivery_date"].isin(actual_dates)]
    if common.empty:
        raise HTTPException(404, "No complete actual hours overlap January 2026 decision forecasts")
    return {"min_date": str(common["delivery_date"].min()), "max_date": str(common["delivery_date"].max()),
            "default_cutoff": DEFAULT_CUTOFF_UK, "intervals": len(common),
            "decision_start": str(JANUARY_DECISION_START),
            "decision_end": str(JANUARY_DECISION_END)}


@app.get("/api/day")
def day(date_: date = Query(..., alias="date"), cutoff: str = Cutoff):
    if date_ < DELIVERY_START or date_ > DELIVERY_END:
        raise HTTPException(
            422,
            "Delivery date must correspond to a January 2026 purchase decision (2026-01-02 through 2026-02-01).",
        )
    a, _ = load()
    sel = selected(cutoff)
    s = sel[sel["delivery_date"] == date_]
    if s.empty:
        raise HTTPException(404, f"No decision-time forecast for {date_} with cutoff {cutoff}")
    rows = s.merge(a.rename(columns={"generation": "actual"}), on="startTime", how="left").rename(columns={"generation": "forecast"})
    rows["error"] = rows["forecast"] - rows["actual"]
    rows["abs_error"] = rows["error"].abs()
    n_actual = int((uk_delivery_date(a["startTime"]) == date_).sum())
    metrics = compute_metrics(match(s, a), len(s), n_actual)
    return {"date": str(date_), "cutoff_utc": s["cutoff"].iloc[0].isoformat(),
            "mean_forecast": float(s["generation"].mean()), "mean_actual": None if rows["actual"].isna().all() else float(rows["actual"].mean()),
            "metrics": clean(metrics),
            "rows": records(rows[["startTime", "publishTime", "forecast", "actual", "error", "abs_error"]])}


@app.get("/api/forecast-history")
def forecast_history(delivery_time: str, cutoff: str = Cutoff):
    _, f = load()
    ts = to_utc(pd.Series([delivery_time]))[0]
    h = tag_availability(f[f["startTime"] == ts], cutoff).sort_values("publishTime")
    if h.empty:
        raise HTTPException(404, "No forecast versions for that delivery time")
    h["selected"] = False
    avail = h.index[h["available_at_cutoff"]]
    if len(avail):
        h.loc[avail[-1], "selected"] = True
    h = h.rename(columns={"generation": "forecast"})
    return {"delivery_time": ts.isoformat(), "cutoff_utc": h["cutoff"].iloc[0].isoformat(),
            "versions": records(h[["publishTime", "forecast", "available_at_cutoff", "selected"]])}


@app.get("/api/accuracy")
def accuracy(start: date, end: date, cutoff: str = Cutoff):
    if end < start:
        raise HTTPException(422, "end must not be before start")
    if start < DELIVERY_START or end > DELIVERY_END:
        raise HTTPException(
            422,
            "Accuracy range must be within delivery dates for January 2026 purchase decisions (2026-01-02 through 2026-02-01).",
        )
    a, _ = load()
    sel = selected(cutoff)
    s = sel[
        (sel["delivery_date"] >= start)
        & (sel["delivery_date"] <= end)
        & (sel["delivery_date"] >= DELIVERY_START)
        & (sel["delivery_date"] <= DELIVERY_END)
    ]
    if s.empty:
        raise HTTPException(404, "No forecasts in range")
    ad = uk_delivery_date(a["startTime"])
    m = match(s, a)
    overall = compute_metrics(m, len(s), int(((ad >= start) & (ad <= end)).sum()))
    if m.empty:
        return {"overall": clean(overall), "daily": [], "by_hour": [], "histogram": []}

    def agg(g):
        e = g["error"].to_numpy(float)
        return pd.Series({"mae": np.abs(e).mean(), "rmse": np.sqrt((e ** 2).mean()), "bias": e.mean(), "n": len(g)})

    daily = m.groupby("delivery_date").apply(agg, include_groups=False).reset_index()
    daily["delivery_date"] = daily["delivery_date"].astype(str)
    m["hour"] = m["startTime"].dt.tz_convert(UK_TZ).dt.hour
    m["horizon_h"] = (m["startTime"] - m["publishTime"]).dt.total_seconds() / 3600
    by_hour = m.groupby("hour").agg(mae=("abs_error", "mean"), horizon_h=("horizon_h", "mean")).reset_index()
    edges = np.arange(0, float(m["abs_error"].max()) + 500, 250)
    counts, _ = np.histogram(m["abs_error"], bins=edges)
    hist = [{"from": int(lo), "to": int(lo + 250), "count": int(c)} for lo, c in zip(edges[:-1], counts)]
    return {"overall": clean(overall), "daily": records(daily), "by_hour": records(by_hour), "histogram": hist}


if (ROOT / "static").exists():  # built React app, served by the same container
    app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="web")

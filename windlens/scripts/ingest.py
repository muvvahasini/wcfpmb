"""Download Elexon FUELHH and WINDFOR data into data/*.csv.
Usage: python scripts/ingest.py 2025-12-31 2026-02-02"""
import sys, time
import subprocess
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

DATASET_URLS = {
    "FUELHH": "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream",
    "WINDFOR": "https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream",
}
OUT = Path(__file__).resolve().parents[1] / "data"


def get(client, dataset, params):
    for attempt in range(5):
        try:
            r = client.get(DATASET_URLS[dataset], params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{dataset} failed for {params}")


def chunks(start, end, days):
    d = start
    while d < end:
        yield d, min(d + timedelta(days=days), end)
        d += timedelta(days=days)


def main(start: date, end: date):
    OUT.mkdir(exist_ok=True)
    with httpx.Client() as c:
        act = [row for lo, hi in chunks(start, end, 7) for row in get(c, "FUELHH", {
            "settlementDateFrom": lo.isoformat(), "settlementDateTo": hi.isoformat(), "fuelType": "WIND"})]
        fc = [row for lo, hi in chunks(start, end, 2) for row in get(c, "WINDFOR", {
            "publishDateTimeFrom": f"{lo}T00:00:00Z", "publishDateTimeTo": f"{hi}T00:00:00Z"})]
    pd.DataFrame(act)[["startTime", "fuelType", "generation"]].drop_duplicates().to_csv(OUT / "actuals.csv", index=False)
    pd.DataFrame(fc)[["startTime", "publishTime", "generation"]].drop_duplicates().to_csv(OUT / "forecasts.csv", index=False)
    print(f"actuals={len(act)} forecasts={len(fc)} -> {OUT}")
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("process_data.py"))],
        check=True,
    )


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]))

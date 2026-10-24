"""Validate and clean ingested Elexon CSVs without changing the raw files."""
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW_DIR = DATA
PROCESSED_DIR = DATA / "processed"

REQUIRED = {
    "actuals": ("startTime", "fuelType", "generation"),
    "forecasts": ("startTime", "publishTime", "generation"),
}
BUSINESS_KEYS = {
    "actuals": ("startTime",),
    "forecasts": ("startTime", "publishTime"),
}
WINDOW_RADIUS = 3
MAD_THRESHOLD = 6.0
MIN_DEVIATION_MW = 2000.0


def parse_timestamp(value):
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_valid_rows(path, kind, report):
    required = REQUIRED[kind]
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.reader(source)
        try:
            headers = [value.strip() for value in next(reader)]
        except StopIteration:
            report["empty_file"] = True
            return rows
        missing_columns = [column for column in required if column not in headers]
        if missing_columns:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing_columns)}")

        report["input_rows"] = 0
        for values in reader:
            report["input_rows"] += 1
            if not values or all(not value.strip() for value in values):
                report["blank_rows"] += 1
                continue
            if len(values) > len(headers):
                report["malformed_rows"] += 1
                continue

            row = {header: values[index].strip() if index < len(values) else ""
                   for index, header in enumerate(headers)}
            if any(not row[column] for column in required):
                report["rows_with_empty_required_fields"] += 1
                continue
            if kind == "actuals" and row["fuelType"].upper() != "WIND":
                report["non_wind_rows"] += 1
                continue

            try:
                row["startTime"] = parse_timestamp(row["startTime"])
                if kind == "forecasts":
                    row["publishTime"] = parse_timestamp(row["publishTime"])
            except ValueError:
                report["invalid_timestamp_rows"] += 1
                continue
            try:
                generation = float(row["generation"])
                if not math.isfinite(generation):
                    raise ValueError
            except ValueError:
                report["invalid_generation_rows"] += 1
                continue
            if generation < 0:
                report["negative_generation_rows"] += 1
                continue
            row["generation"] = str(generation)
            row["_generation"] = generation
            rows.append(row)
    return rows


def remove_duplicates(rows, kind, report):
    required = REQUIRED[kind]
    business_key = BUSINESS_KEYS[kind]
    unique = []
    seen = set()
    for row in rows:
        exact_key = tuple(row[column] for column in required if column != "generation")
        exact_key += (row["_generation"],)
        if exact_key in seen:
            report["exact_duplicate_rows_removed"] += 1
            continue
        seen.add(exact_key)
        unique.append(row)

    grouped = defaultdict(list)
    for row in unique:
        grouped[tuple(row[column] for column in business_key)].append(row)
    conflicts = {key for key, group in grouped.items() if len(group) > 1}
    if conflicts:
        report["conflicting_duplicate_rows_removed"] = sum(
            len(grouped[key]) for key in conflicts
        )
    return [row for row in unique
            if tuple(row[column] for column in business_key) not in conflicts]


def find_noisy_rows(rows, kind):
    groups = defaultdict(list)
    for row in rows:
        group_key = ("actuals",) if kind == "actuals" else (row["publishTime"],)
        groups[group_key].append(row)

    noisy = set()
    for group in groups.values():
        group.sort(key=lambda row: row["startTime"])
        values = [row["_generation"] for row in group]
        for index, row in enumerate(group):
            neighbors = values[max(0, index - WINDOW_RADIUS):index]
            neighbors += values[index + 1:index + WINDOW_RADIUS + 1]
            if len(neighbors) < 4:
                continue
            center = statistics.median(neighbors)
            mad = statistics.median(abs(value - center) for value in neighbors)
            limit = max(MAD_THRESHOLD * 1.4826 * mad, MIN_DEVIATION_MW)
            if abs(row["_generation"] - center) > limit:
                noisy.add(id(row))
    return [row for row in rows if id(row) in noisy]


def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: row[column] for column in columns} for row in rows)


def process_file(kind, raw_dir, output_dir):
    report = {
        "input_rows": 0,
        "blank_rows": 0,
        "malformed_rows": 0,
        "rows_with_empty_required_fields": 0,
        "non_wind_rows": 0,
        "invalid_timestamp_rows": 0,
        "invalid_generation_rows": 0,
        "negative_generation_rows": 0,
        "exact_duplicate_rows_removed": 0,
        "conflicting_duplicate_rows_removed": 0,
        "noisy_rows_removed": 0,
        "output_rows": 0,
    }
    columns = REQUIRED[kind]
    rows = read_valid_rows(raw_dir / f"{kind}.csv", kind, report)
    rows = remove_duplicates(rows, kind, report)
    noisy = find_noisy_rows(rows, kind)
    noisy_ids = {id(row) for row in noisy}
    clean = [row for row in rows if id(row) not in noisy_ids]

    write_csv(output_dir / f"{kind}.csv", clean, columns)
    write_csv(output_dir / f"flagged_{kind}_outliers.csv", noisy, columns)
    report["noisy_rows_removed"] = len(noisy)
    report["output_rows"] = len(clean)
    return report


def process_files(raw_dir=RAW_DIR, output_dir=PROCESSED_DIR):
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "outlier_rule": (
            "For the actual series and each forecast publication, flag a value when "
            "its deviation from the median of up to 3 neighboring intervals on "
            "each side exceeds max(6 * 1.4826 * MAD, 2000 MW)."
        ),
        "raw_files_preserved": True,
        "datasets": {},
    }
    for kind in REQUIRED:
        report["datasets"][kind] = process_file(kind, raw_dir, output_dir)
    report_path = output_dir / "processing_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Processed data written to {output_dir}; report: {report_path}")
    for kind, counts in report["datasets"].items():
        print(f"{kind}: {counts['input_rows']} input, {counts['output_rows']} kept, "
              f"{counts['noisy_rows_removed']} noisy, "
              f"{counts['exact_duplicate_rows_removed']} exact duplicates removed, "
              f"{counts['conflicting_duplicate_rows_removed']} conflicting duplicates removed")
    return report


if __name__ == "__main__":
    process_files()

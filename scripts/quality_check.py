"""
SpacePoint - Data Quality and Calibration Tool
Author: Kommal

Looks at a raw (not yet cleaned) mission CSV and reports data quality
issues without changing the data. Read-only diagnostic - pairs with
clean_mission_data.py, which fixes what this flags.

Column names are detected automatically (see column_detection.py) -
works on any CSV with a timestamp, latitude/longitude, and any number
of numeric sensor columns.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from column_detection import detect_schema, rename_to_standard

# Physically-impossible bounds for columns we recognize by exact name;
# unrecognized columns just skip this specific check
KNOWN_HARD_RANGES = {
    "latitude": (-90.0, 90.0),
    "longitude": (-180.0, 180.0),
    "altitude": (-5.0, 500.0),
    "temperature": (-10.0, 65.0),
    "humidity": (0.0, 100.0),
    "pressure": (850.0, 1100.0),
    "light": (0.0, 150000.0),
    "air_quality": (0.0, 500.0),
    "battery_voltage": (2.5, 4.35),
}

# Self-calibrating thresholds - a multiple of each column's OWN
# standard deviation, instead of a fixed number in fixed units, so
# these checks work on any sensor regardless of what it measures
JUMP_STD_MULTIPLIER = 5.0
DRIFT_STD_MULTIPLIER = 2.0
DRIFT_WINDOW = 20  # samples averaged at the start/end of the mission


def load_and_detect(input_source) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(input_source, dtype=str)

    schema = detect_schema(df)
    df = rename_to_standard(df, schema)
    sensor_columns = schema["sensor_cols"]

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in sensor_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df, sensor_columns


def check_missing_values(df: pd.DataFrame, sensor_columns: list[str]) -> dict:
    columns = sensor_columns + [c for c in ["latitude", "longitude"] if c in df.columns]
    return {col: int(df[col].isna().sum()) for col in columns}


def check_out_of_range(df: pd.DataFrame, sensor_columns: list[str]) -> dict:
    results = {}
    checkable = sensor_columns + [c for c in ["latitude", "longitude"] if c in df.columns]
    for col in checkable:
        bounds = KNOWN_HARD_RANGES.get(col)
        if not bounds:
            continue
        lo, hi = bounds
        out_of_range = ~df[col].between(lo, hi) & df[col].notna()
        results[col] = int(out_of_range.sum())
    return results


def check_gps_loss(df: pd.DataFrame) -> int:
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return len(df)  # no GPS columns at all - every row counts as lost
    return int((df["latitude"].isna() | df["longitude"].isna()).sum())


def check_duplicate_timestamps(df: pd.DataFrame) -> int:
    if "timestamp" not in df.columns:
        return 0
    return int(df["timestamp"].duplicated().sum())


def check_sudden_jumps(df: pd.DataFrame, sensor_columns: list[str]) -> dict:
    """Flags a jump between consecutive readings bigger than a multiple
    of that column's own standard deviation - self-calibrating, so it
    works on any sensor regardless of its units."""
    results = {}
    for col in sensor_columns:
        std = df[col].std()
        if not std or pd.isna(std):
            results[col] = 0
            continue
        change = df[col].diff().abs()
        results[col] = int((change > std * JUMP_STD_MULTIPLIER).sum())
    return results


def check_drift(df: pd.DataFrame, sensor_columns: list[str]) -> dict:
    """Compares early-mission and late-mission averages - flagged if
    they differ by more than a multiple of the column's own std dev."""
    results = {}
    for col in sensor_columns:
        if len(df) < DRIFT_WINDOW * 2:
            results[col] = "not enough samples to check"
            continue
        std = df[col].std()
        if not std or pd.isna(std):
            results[col] = "not enough variation to check"
            continue
        early_avg = df[col].iloc[:DRIFT_WINDOW].mean()
        late_avg = df[col].iloc[-DRIFT_WINDOW:].mean()
        drift_amount = round(float(late_avg - early_avg), 2)
        results[col] = {
            "drift_amount": drift_amount,
            "flagged": abs(drift_amount) > std * DRIFT_STD_MULTIPLIER,
        }
    return results


def run_quality_check(input_source) -> dict:
    """input_source: a file path or file-like object (e.g. a Streamlit upload)."""
    df, sensor_columns = load_and_detect(input_source)

    return {
        "mission_file": getattr(input_source, "name", str(input_source)),
        "total_rows": len(df),
        "detected_sensor_columns": sensor_columns,
        "missing_values": check_missing_values(df, sensor_columns),
        "out_of_range_values": check_out_of_range(df, sensor_columns),
        "gps_loss_rows": check_gps_loss(df),
        "duplicate_timestamps": check_duplicate_timestamps(df),
        "sudden_jumps": check_sudden_jumps(df, sensor_columns),
        "sensor_drift": check_drift(df, sensor_columns),
    }


def main():
    parser = argparse.ArgumentParser(description="Data quality and calibration check")
    parser.add_argument("--input", type=Path, required=True, help="Path to the raw mission CSV")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the quality report JSON")
    args = parser.parse_args()

    report = run_quality_check(args.input)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))

    print(f"Quality report written to {args.output}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
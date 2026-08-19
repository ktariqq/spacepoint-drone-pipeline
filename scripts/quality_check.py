"""
SpacePoint - Data Quality and Calibration Tool
Author: Kommal

Looks at a raw (not yet cleaned) mission CSV and reports data quality
issues without changing the data. Read-only diagnostic - pairs with
clean_mission_data.py, which fixes what this flags.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

SENSOR_COLUMNS = ["altitude", "temperature", "humidity", "pressure", "light", "air_quality", "battery_voltage"]

HARD_RANGES = {
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

# Change between consecutive readings beyond this isn't physically
# realistic for these sensors, and points to a glitch, not real weather
MAX_JUMP = {
    "temperature": 5.0,
    "humidity": 15.0,
    "pressure": 5.0,
    "light": 30000.0,
    "air_quality": 100.0,
}

# If early-mission and late-mission averages differ by more than this,
# the sensor itself is likely drifting, not the environment changing
DRIFT_THRESHOLD = {
    "temperature": 8.0,
    "humidity": 20.0,
    "pressure": 10.0,
    "air_quality": 50.0,
}

DRIFT_WINDOW = 20  # samples averaged at the start/end of the mission


def check_missing_values(df: pd.DataFrame) -> dict:
    return {col: int(df[col].isna().sum()) for col in SENSOR_COLUMNS + ["latitude", "longitude"]}


def check_out_of_range(df: pd.DataFrame) -> dict:
    results = {}
    for col, (lo, hi) in HARD_RANGES.items():
        out_of_range = ~df[col].between(lo, hi) & df[col].notna()
        results[col] = int(out_of_range.sum())
    return results


def check_gps_loss(df: pd.DataFrame) -> int:
    return int((df["latitude"].isna() | df["longitude"].isna()).sum())


def check_duplicate_timestamps(df: pd.DataFrame) -> int:
    return int(df["timestamp"].duplicated().sum())


def check_sudden_jumps(df: pd.DataFrame) -> dict:
    results = {}
    for col, max_change in MAX_JUMP.items():
        change = df[col].diff().abs()
        results[col] = int((change > max_change).sum())
    return results


def check_drift(df: pd.DataFrame) -> dict:
    results = {}
    for col, threshold in DRIFT_THRESHOLD.items():
        if len(df) < DRIFT_WINDOW * 2:
            results[col] = "not enough samples to check"
            continue
        early_avg = df[col].iloc[:DRIFT_WINDOW].mean()
        late_avg = df[col].iloc[-DRIFT_WINDOW:].mean()
        drift_amount = round(float(late_avg - early_avg), 2)
        results[col] = {
            "drift_amount": drift_amount,
            "flagged": abs(drift_amount) > threshold,
        }
    return results


def run_quality_check(input_source) -> dict:
    """input_source: a file path or file-like object (e.g. a Streamlit upload)."""
    df = pd.read_csv(input_source, parse_dates=["timestamp"])

    return {
        "mission_file": getattr(input_source, "name", str(input_source)),
        "total_rows": len(df),
        "missing_values": check_missing_values(df),
        "out_of_range_values": check_out_of_range(df),
        "gps_loss_rows": check_gps_loss(df),
        "duplicate_timestamps": check_duplicate_timestamps(df),
        "sudden_jumps": check_sudden_jumps(df),
        "sensor_drift": check_drift(df),
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
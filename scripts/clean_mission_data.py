"""
SpacePoint - Remote Sensing Data Cleaning Script
Author: Kommal

Reads a raw mission CSV, removes empty readings, handles missing
values, flags abnormal readings, computes summary averages, and writes:
  - a cleaned CSV (all rows retained, flag columns added)
  - a summary JSON (feeds the dashboard)
  - a plot-data JSON (feeds dashboard charts without re-running Python)
  - static PNG plots (for the written report / offline viewing)

Column names are detected automatically (see column_detection.py) -
this works on any CSV with a timestamp, latitude/longitude, and any
number of numeric sensor columns, not just the original fixed schema.

Usage:
    python clean_mission_data.py --input data/raw/sample_mission.csv \
        --output-dir data/cleaned --mission-name sample_mission
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from column_detection import detect_schema, rename_to_standard

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Physically-impossible bounds for columns we recognize by exact name -
# applied only when a detected sensor happens to match one of these.
# Anything we don't recognize skips this specific check but still gets
# the generic statistical checks below, which need no knowledge of
# what the column actually measures
KNOWN_HARD_RANGES: dict[str, tuple[float, float]] = {
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

MAX_INTERPOLATION_GAP = 5   # consecutive-NaN samples we'll interpolate across
ZSCORE_THRESHOLD = 3.0      # statistical anomaly threshold
FLATLINE_RUN_LENGTH = 10    # repeated-value run length flagged as a stuck sensor


@dataclass
class CleaningReport:
    """Bookkeeping returned alongside the cleaned dataframe."""
    total_rows_in: int = 0
    fully_empty_rows_dropped: int = 0
    duplicate_timestamps_removed: int = 0
    detected_sensor_columns: list = None
    hard_range_violations: dict[str, int] = None
    interpolated_gaps: dict[str, int] = None
    long_gaps_remaining: dict[str, int] = None
    anomaly_flags: dict[str, int] = None
    flatline_flags: dict[str, int] = None
    gps_loss_rows: int = 0

    def __post_init__(self):
        self.detected_sensor_columns = self.detected_sensor_columns or []
        self.hard_range_violations = self.hard_range_violations or {}
        self.interpolated_gaps = self.interpolated_gaps or {}
        self.long_gaps_remaining = self.long_gaps_remaining or {}
        self.anomaly_flags = self.anomaly_flags or {}
        self.flatline_flags = self.flatline_flags or {}


def load_csv(path) -> tuple[pd.DataFrame, list[str]]:
    """path: a file path or file-like object (e.g. a Streamlit upload).
    Returns the dataframe with columns renamed to the standard
    timestamp/latitude/longitude names, plus the detected sensor
    columns (kept under their original names)."""
    log.info(f"Loading {getattr(path, 'name', path)}")
    df = pd.read_csv(path, dtype=str)  # read as str first, coerce deliberately

    schema = detect_schema(df)
    if not schema["lat_col"] or not schema["lon_col"]:
        log.warning("No latitude/longitude columns detected - this mission won't be geotagged")
    if not schema["timestamp_col"]:
        log.warning("No timestamp column detected - generating one from row order")

    df = rename_to_standard(df, schema)
    sensor_columns = schema["sensor_cols"]

    if "timestamp" not in df.columns:
        # No real timestamp in the source data - a synthetic one, one
        # second apart per row, keeps every downstream step (sorting,
        # interpolation, plots, duration) working unchanged
        df["timestamp"] = pd.date_range("2000-01-01", periods=len(df), freq="s")
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        n_bad_timestamps = df["timestamp"].isna().sum()
        if n_bad_timestamps:
            log.warning(f"{n_bad_timestamps} rows have unparsable timestamps — dropping them")
            df = df.dropna(subset=["timestamp"])

    for col in sensor_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "latitude" in df.columns:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    if "longitude" in df.columns:
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df, sensor_columns


def drop_fully_empty_rows(df: pd.DataFrame, sensor_columns: list[str], report: CleaningReport) -> pd.DataFrame:
    """A row with every sensor column NaN is a full logger read failure,
    not a value worth trying to fill."""
    if not sensor_columns:
        return df
    before = len(df)
    mask_all_empty = df[sensor_columns].isna().all(axis=1)
    report.fully_empty_rows_dropped = int(mask_all_empty.sum())
    df = df.loc[~mask_all_empty].reset_index(drop=True)
    log.info(f"Dropped {before - len(df)} fully-empty rows")
    return df


def remove_duplicate_timestamps(df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates(subset="timestamp", keep="first").reset_index(drop=True)
    report.duplicate_timestamps_removed = before - len(df)
    if report.duplicate_timestamps_removed:
        log.info(f"Removed {report.duplicate_timestamps_removed} duplicate timestamp rows")
    return df


def apply_hard_ranges(df: pd.DataFrame, sensor_columns: list[str], report: CleaningReport) -> pd.DataFrame:
    """Physically-impossible values are sensor errors, not real data -
    null them so they're handled by the same missing-value logic
    below. Only applied to columns whose exact name we recognize."""
    checkable_columns = sensor_columns + [c for c in ["latitude", "longitude"] if c in df.columns]
    for col in checkable_columns:
        bounds = KNOWN_HARD_RANGES.get(col)
        if not bounds:
            continue
        lo, hi = bounds
        out_of_range = ~df[col].between(lo, hi) & df[col].notna()
        n = int(out_of_range.sum())
        if n:
            report.hard_range_violations[col] = n
            log.warning(f"{col}: {n} values outside physical range [{lo}, {hi}] — nulled")
            df.loc[out_of_range, col] = np.nan
    return df


def handle_missing_values(df: pd.DataFrame, sensor_columns: list[str], report: CleaningReport) -> pd.DataFrame:
    """Short gaps get time-based interpolation. Long gaps are left as
    NaN and flagged - guessing across a long dropout would misrepresent
    the mission."""
    df = df.set_index("timestamp")

    columns_to_check = sensor_columns + [c for c in ["latitude", "longitude"] if c in df.columns]
    for col in columns_to_check:
        is_na = df[col].isna()
        if not is_na.any():
            continue

        run_id = (~is_na).cumsum()
        run_lengths = is_na.groupby(run_id).transform("sum")

        short_gap_mask = is_na & (run_lengths <= MAX_INTERPOLATION_GAP)
        long_gap_mask = is_na & (run_lengths > MAX_INTERPOLATION_GAP)

        report.interpolated_gaps[col] = int(short_gap_mask.sum())
        report.long_gaps_remaining[col] = int(long_gap_mask.sum())

        if short_gap_mask.any():
            interpolated = df[col].interpolate(method="time", limit=MAX_INTERPOLATION_GAP)
            df.loc[short_gap_mask, col] = interpolated.loc[short_gap_mask]

    df = df.reset_index()

    if "latitude" in df.columns and "longitude" in df.columns:
        gps_loss = df["latitude"].isna() | df["longitude"].isna()
    else:
        gps_loss = pd.Series(True, index=df.index)  # never geotagged at all
    df["flag_gps_loss"] = gps_loss
    report.gps_loss_rows = int(gps_loss.sum())

    return df


def flag_statistical_anomalies(df: pd.DataFrame, sensor_columns: list[str], report: CleaningReport) -> pd.DataFrame:
    """Values that are physically possible but far from the mission's
    own distribution. Kept (not nulled), just flagged. Works on any
    numeric column - doesn't need to know what it measures."""
    for col in sensor_columns:
        mean = df[col].mean()
        std = df[col].std()
        flag_col = f"flag_anomaly_{col}"
        if std == 0 or pd.isna(std):
            df[flag_col] = False
            continue
        z = (df[col] - mean) / std
        df[flag_col] = z.abs() > ZSCORE_THRESHOLD
        n = int(df[flag_col].sum())
        report.anomaly_flags[col] = n
        if n:
            log.info(f"{col}: {n} statistical anomalies flagged (|z| > {ZSCORE_THRESHOLD})")
    return df


def flag_flatline_sensors(df: pd.DataFrame, sensor_columns: list[str], report: CleaningReport) -> pd.DataFrame:
    """A sensor returning the same value for many samples in a row
    usually means it's stuck rather than the environment being stable."""
    for col in sensor_columns:
        same_as_prev = df[col] == df[col].shift(1)
        run_id = (~same_as_prev).cumsum()
        run_lengths = same_as_prev.groupby(run_id).transform("size")
        flag_col = f"flag_flatline_{col}"
        df[flag_col] = same_as_prev & (run_lengths >= FLATLINE_RUN_LENGTH)
        n = int(df[flag_col].sum())
        report.flatline_flags[col] = n
        if n:
            log.info(f"{col}: {n} samples flagged as possible flatlined sensor")
    return df


def consolidate_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Rolls all per-column flags into one readable summary column."""
    flag_cols = [c for c in df.columns if c.startswith("flag_")]

    def summarize(row) -> str:
        active = [c.replace("flag_", "") for c in flag_cols if row[c]]
        return "; ".join(active) if active else ""

    df["flags_summary"] = df.apply(summarize, axis=1)
    df["has_flag"] = df["flags_summary"] != ""
    return df


def compute_summary(df: pd.DataFrame, sensor_columns: list[str], mission_name: str) -> dict:
    stats = {}
    for col in sensor_columns:
        series = df[col].dropna()
        stats[col] = {
            "mean": round(float(series.mean()), 3) if len(series) else None,
            "min": round(float(series.min()), 3) if len(series) else None,
            "max": round(float(series.max()), 3) if len(series) else None,
            "std": round(float(series.std()), 3) if len(series) else None,
            "count": int(series.count()),
        }

    bounding_box = None
    if "latitude" in df.columns and "longitude" in df.columns:
        valid_gps = df.dropna(subset=["latitude", "longitude"])
        if len(valid_gps):
            bounding_box = {
                "min_lat": float(valid_gps["latitude"].min()),
                "max_lat": float(valid_gps["latitude"].max()),
                "min_lon": float(valid_gps["longitude"].min()),
                "max_lon": float(valid_gps["longitude"].max()),
            }

    duration_seconds = None
    if len(df) > 1:
        duration_seconds = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).total_seconds()

    return {
        "mission_name": mission_name,
        "start_time": df["timestamp"].iloc[0].isoformat() if len(df) else None,
        "end_time": df["timestamp"].iloc[-1].isoformat() if len(df) else None,
        "duration_seconds": duration_seconds,
        "sample_count": len(df),
        "flagged_row_count": int(df["has_flag"].sum()) if "has_flag" in df else 0,
        "gps_loss_row_count": int(df["flag_gps_loss"].sum()) if "flag_gps_loss" in df else 0,
        "bounding_box": bounding_box,
        "sensor_columns": sensor_columns,
        "sensor_stats": stats,
    }


def generate_plots(df: pd.DataFrame, sensor_columns: list[str], output_dir: Path, mission_name: str) -> dict:
    """Writes one PNG per detected sensor column and returns the same
    series as plain lists so the dashboard can redraw them without
    needing Python."""
    plots_dir = output_dir / f"{mission_name}_plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    plot_data = {"timestamps": df["timestamp"].astype(str).tolist()}

    for col in sensor_columns:
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(df["timestamp"], df[col], linewidth=1, color="#5622AD")

        flag_col = f"flag_anomaly_{col}"
        if flag_col in df.columns and df[flag_col].any():
            flagged = df[df[flag_col]]
            ax.scatter(flagged["timestamp"], flagged[col], color="#D85A30",
                       s=18, zorder=3, label="flagged anomaly")
            ax.legend(loc="upper right", fontsize=8)

        ax.set_title(f"{mission_name} — {col}")
        ax.set_xlabel("Time")
        ax.set_ylabel(col)
        fig.autofmt_xdate()
        fig.tight_layout()

        # Sanitize the column name for use as a filename - arbitrary
        # dataset columns can contain characters a filesystem won't like
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in col)
        out_path = plots_dir / f"{safe_name}.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        log.info(f"Saved plot: {out_path}")

        plot_data[col] = df[col].where(df[col].notna(), None).tolist()

    return plot_data


def clean_mission_data(input_source, output_dir: Path, mission_name: str) -> CleaningReport:
    """input_source: a file path or file-like object (e.g. a Streamlit upload)."""
    report = CleaningReport()

    df, sensor_columns = load_csv(input_source)
    report.total_rows_in = len(df)
    report.detected_sensor_columns = sensor_columns
    log.info(f"Detected sensor columns: {sensor_columns}")

    df = drop_fully_empty_rows(df, sensor_columns, report)
    df = remove_duplicate_timestamps(df, report)
    df = apply_hard_ranges(df, sensor_columns, report)
    df = handle_missing_values(df, sensor_columns, report)
    df = flag_statistical_anomalies(df, sensor_columns, report)
    df = flag_flatline_sensors(df, sensor_columns, report)
    df = consolidate_flags(df)

    output_dir.mkdir(parents=True, exist_ok=True)

    cleaned_path = output_dir / f"{mission_name}_cleaned.csv"
    df.to_csv(cleaned_path, index=False)
    log.info(f"Wrote cleaned CSV: {cleaned_path}")

    summary = compute_summary(df, sensor_columns, mission_name)
    summary_path = output_dir / f"{mission_name}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info(f"Wrote summary JSON: {summary_path}")

    plot_data = generate_plots(df, sensor_columns, output_dir, mission_name)
    plot_data_path = output_dir / f"{mission_name}_plot_data.json"
    plot_data_path.write_text(json.dumps(plot_data, indent=2))
    log.info(f"Wrote plot data JSON: {plot_data_path}")

    log.info("--- Cleaning report ---")
    log.info(json.dumps(report.__dict__, indent=2, default=str))

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remote sensing data cleaning script")
    parser.add_argument("--input", type=Path, required=True, help="Path to raw mission CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("data/cleaned"),
                         help="Directory to write cleaned outputs into")
    parser.add_argument("--mission-name", type=str, required=True,
                         help="Short identifier used in output filenames")
    return parser.parse_args()


def main():
    args = parse_args()
    clean_mission_data(args.input, args.output_dir, args.mission_name)


if __name__ == "__main__":
    main() 
    
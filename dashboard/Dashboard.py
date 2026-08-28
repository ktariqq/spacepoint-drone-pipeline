"""
SpacePoint - Environmental Data Dashboard
Author: Kommal

Reads the cleaned CSV and summary JSON and shows a mission dashboard.
Sensor readings/charts adapt to whatever columns were actually
detected for this mission (see column_detection.py) - there's no
fixed list of expected sensor names, so this works whether the
mission has BME280-style readings or something else entirely.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

import os
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

sys.path.append(str(Path(__file__).resolve().parent))
from branding import apply_page_config, render_header, render_sidebar_logo, apply_custom_css

DATA_DIR = Path("data/cleaned")
DEFAULT_TEMP_THRESHOLD = 45.0


def get_available_missions() -> list[str]:
    files = DATA_DIR.glob("*_cleaned.csv")
    return sorted(f.name.replace("_cleaned.csv", "") for f in files)


@st.cache_data
def load_cleaned_data(mission_name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{mission_name}_cleaned.csv"
    return pd.read_csv(path, parse_dates=["timestamp"])


@st.cache_data
def load_summary(mission_name: str) -> dict:
    path = DATA_DIR / f"{mission_name}_summary.json"
    with open(path) as f:
        return json.load(f)


def find_temperature_column(sensor_columns: list[str]) -> str | None:
    """Looks for a column that's plausibly a temperature reading, by
    name, rather than assuming one is literally called 'temperature' -
    keeps the high-temperature warning working on datasets that named
    it something else (e.g. 'Temperature_C')."""
    for col in sensor_columns:
        if "temp" in col.lower():
            return col
    return None


def build_warnings(df: pd.DataFrame, sensor_columns: list[str], temp_threshold: float) -> list[str]:
    """Scans the cleaned data for anything worth flagging on the dashboard."""
    warnings = []

    temp_col = find_temperature_column(sensor_columns)
    if temp_col:
        high_temp_rows = df[df[temp_col] > temp_threshold]
        if len(high_temp_rows) > 0:
            warnings.append(f"High {temp_col}: {len(high_temp_rows)} readings above {temp_threshold}")

    if "flag_gps_loss" in df.columns:
        gps_loss_count = int(df["flag_gps_loss"].sum())
        if gps_loss_count > 0:
            warnings.append(f"Missing GPS: {gps_loss_count} readings had no GPS fix")

    flatline_cols = [c for c in df.columns if c.startswith("flag_flatline_")]
    if flatline_cols:
        flatline_count = int(df[flatline_cols].any(axis=1).sum())
        if flatline_count > 0:
            warnings.append(f"Sensor errors: {flatline_count} readings show a possibly stuck sensor")

    anomaly_cols = [c for c in df.columns if c.startswith("flag_anomaly_")]
    if anomaly_cols:
        anomaly_count = int(df[anomaly_cols].any(axis=1).sum())
        if anomaly_count > 0:
            warnings.append(f"Unusual readings: {anomaly_count} statistical anomalies flagged")

    return warnings


apply_page_config("SpacePoint Mission Dashboard")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Dashboard")

missions = get_available_missions()

if not missions:
    st.error("No cleaned mission data found. Run the Data Cleaning page first.")
    st.stop()

st.sidebar.header("Controls")

selected_mission = st.sidebar.selectbox("Mission", missions)

temp_threshold = st.sidebar.slider(
    "High temperature warning threshold",
    min_value=0.0,
    max_value=200.0,
    value=DEFAULT_TEMP_THRESHOLD,
    step=1.0,
)

show_flagged_only = st.sidebar.checkbox("Show only flagged rows in table")

df = load_cleaned_data(selected_mission)
summary = load_summary(selected_mission)
sensor_columns = summary.get("sensor_columns") or list(summary["sensor_stats"].keys())

st.subheader("Mission Summary")

duration_minutes = (summary["duration_seconds"] or 0) / 60
bbox = summary["bounding_box"]
location_text = "No GPS data"
if bbox:
    center_lat = (bbox["min_lat"] + bbox["max_lat"]) / 2
    center_lon = (bbox["min_lon"] + bbox["max_lon"]) / 2
    location_text = f"{center_lat:.4f}, {center_lon:.4f}"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Mission", summary["mission_name"])
col2.metric("Date", pd.to_datetime(summary["start_time"]).strftime("%Y-%m-%d"))
col3.metric("Location (center)", location_text)
col4.metric("Duration", f"{duration_minutes:.1f} min")

st.subheader("Sensor Readings")

if not sensor_columns:
    st.info("No numeric sensor columns were detected for this mission.")
else:
    metric_cols = st.columns(min(4, len(sensor_columns)))
    for i, col_name in enumerate(sensor_columns[:4]):
        stats = summary["sensor_stats"][col_name]
        metric_cols[i].metric(f"{col_name} (avg)", stats["mean"])

st.subheader("Readings Over Time")

if not sensor_columns:
    st.info("No numeric sensor columns to chart for this mission.")
else:
    chart_df = df.set_index("timestamp")
    cols = st.columns(2)
    for i, col_name in enumerate(sensor_columns):
        with cols[i % 2]:
            st.caption(col_name)
            st.line_chart(chart_df[col_name])

st.subheader("Warnings")

warnings = build_warnings(df, sensor_columns, temp_threshold)

if warnings:
    for message in warnings:
        st.warning(message)
else:
    st.success("No warnings for this mission.")

st.subheader("Cleaned Readings")

table_df = df[df["has_flag"]] if show_flagged_only else df
st.dataframe(table_df, width="stretch")

st.subheader("Export")

csv_bytes = table_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download cleaned CSV",
    data=csv_bytes,
    file_name=f"{selected_mission}_cleaned.csv",
    mime="text/csv",
)
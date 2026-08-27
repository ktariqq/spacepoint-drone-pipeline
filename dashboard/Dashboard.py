"""
SpacePoint - Environmental Data Dashboard
Author: Kommal

Reads the cleaned CSV and summary JSON and shows a mission dashboard:
summary, current readings, charts over time, warnings, a data table,
and a CSV download.

Run it with:
    streamlit run dashboard/Dashboard.py
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


def build_warnings(df: pd.DataFrame, temp_threshold: float) -> list[str]:
    """Scans the cleaned data for anything worth flagging on the dashboard."""
    warnings = []

    high_temp_rows = df[df["temperature"] > temp_threshold]
    if len(high_temp_rows) > 0:
        warnings.append(f"High temperature: {len(high_temp_rows)} readings above {temp_threshold}°C")

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
    "High temperature warning threshold (°C)",
    min_value=20.0,
    max_value=60.0,
    value=DEFAULT_TEMP_THRESHOLD,
    step=1.0,
)

show_flagged_only = st.sidebar.checkbox("Show only flagged rows in table")

df = load_cleaned_data(selected_mission)
summary = load_summary(selected_mission)

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

stats = summary["sensor_stats"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Temperature (avg)", f"{stats['temperature']['mean']} °C")
col2.metric("Humidity (avg)", f"{stats['humidity']['mean']} %")
col3.metric("Pressure (avg)", f"{stats['pressure']['mean']} hPa")
col4.metric("Air Quality (avg)", f"{stats['air_quality']['mean']}")

st.subheader("Readings Over Time")

chart_df = df.set_index("timestamp")

col1, col2 = st.columns(2)
with col1:
    st.caption("Temperature (°C)")
    st.line_chart(chart_df["temperature"])
    st.caption("Pressure (hPa)")
    st.line_chart(chart_df["pressure"])

with col2:
    st.caption("Humidity (%)")
    st.line_chart(chart_df["humidity"])
    st.caption("Air Quality")
    st.line_chart(chart_df["air_quality"])

st.subheader("Warnings")

warnings = build_warnings(df, temp_threshold)

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
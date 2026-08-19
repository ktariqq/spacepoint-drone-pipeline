"""
SpacePoint - Data Quality and Calibration Tool
Author: Kommal

Diagnostic view of a raw mission file - reports what's wrong so you
can decide what to do before cleaning it. Doesn't change any data.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from branding import (
    apply_page_config,
    render_header,
    render_sidebar_logo,
    render_sidebar_status,
    apply_custom_css,
    render_section_header,
    render_state_indicator,
)

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from quality_check import run_quality_check

RAW_DIR = Path("data/raw")

apply_page_config("Data Quality & Calibration")
render_sidebar_logo()
apply_custom_css()
render_header("Data Quality")

render_section_header("Choose a Raw Mission File")
source_mode = st.radio("Source", ["Existing file", "Upload new file"], horizontal=True)

if source_mode == "Existing file":
    raw_files = sorted(RAW_DIR.glob("*.csv"))
    if not raw_files:
        st.warning("No raw mission files found in data/raw.")
        st.stop()
    selected_name = st.selectbox("Raw mission file", [f.name for f in raw_files])
    input_source = RAW_DIR / selected_name
else:
    uploaded = st.file_uploader("Upload a raw mission CSV", type=["csv"])
    if not uploaded:
        st.info("Upload a CSV to run the quality check.")
        st.stop()
    save_copy = st.checkbox("Save this file to data/raw for reuse", value=True)
    if save_copy:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        save_path = RAW_DIR / uploaded.name
        save_path.write_bytes(uploaded.getvalue())
        st.success(f"Saved to {save_path}")
        input_source = save_path
    else:
        input_source = uploaded

report = run_quality_check(input_source)

render_section_header("Overview")
col1, col2, col3 = st.columns(3)
col1.metric("Total rows", report["total_rows"])
col2.metric("GPS loss rows", report["gps_loss_rows"])
col3.metric("Duplicate timestamps", report["duplicate_timestamps"])

render_section_header("Missing Values")
st.write(report["missing_values"])

render_section_header("Out-of-Range Values")
st.write(report["out_of_range_values"])

render_section_header("Sudden Jumps")
st.write(report["sudden_jumps"])

render_section_header("Sensor Drift")
for sensor, result in report["sensor_drift"].items():
    if isinstance(result, dict) and result["flagged"]:
        render_state_indicator(sensor, state="warning", detail=f"drifted {result['drift_amount']}")
    elif isinstance(result, dict):
        render_state_indicator(sensor, state="ok", detail=f"drift {result['drift_amount']}")
    else:
        render_state_indicator(sensor, state="neutral", detail=str(result))

render_sidebar_status()
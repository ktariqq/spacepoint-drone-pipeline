"""

SpacePoint - Data Cleaning

Author: Kommal

Runs the cleaning pipeline on a raw mission file from inside the app:
cleans the data, writes the cleaned CSV/summary/plots, and builds the
GeoJSON used by the Mission Map page.

Works both locally and on Streamlit Cloud.

"""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------
# __file__ = dashboard/pages/2_Data_Cleaning.py
# parents[0] = dashboard/pages
# parents[1] = dashboard
# parents[2] = Tasks 7-14 (project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"
GEO_DIR = PROJECT_ROOT / "data" / "geo"

# ---------------------------------------------------------------------
# Make project modules importable
# ---------------------------------------------------------------------
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------
from branding import (
    apply_page_config,
    render_header,
    render_sidebar_logo,
    render_sidebar_status,
    apply_custom_css,
    render_section_header,
    render_technical_metadata,
)
from clean_mission_data import clean_mission_data
from generate_geojson import build_geojson

# ---------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------
apply_page_config("Data Cleaning")
render_sidebar_logo()
apply_custom_css()
render_header("Data Cleaning")

# ---------------------------------------------------------------------
# Choose input source
# ---------------------------------------------------------------------
render_section_header("Choose a Raw Mission File")
source_mode = st.radio(
    "Source",
    ["Existing file", "Upload new file"],
    horizontal=True,
)

# ---------------------------------------------------------------------
# Existing local/repository file
# ---------------------------------------------------------------------
if source_mode == "Existing file":
    raw_files = sorted(RAW_DIR.glob("*.csv"))
    if not raw_files:
        st.warning(
            "No raw mission files found in data/raw. "
            "Upload a CSV instead."
        )
        st.stop()
    selected_name = st.selectbox(
        "Raw mission file",
        [f.name for f in raw_files],
    )
    input_path = RAW_DIR / selected_name
    default_mission_name = input_path.stem

# ---------------------------------------------------------------------
# Uploaded file
# ---------------------------------------------------------------------
else:
    uploaded = st.file_uploader(
        "Upload a raw mission CSV",
        type=["csv"],
    )
    if uploaded is None:
        st.info("Upload a CSV to continue.")
        st.stop()

    # Streamlit Cloud/local temporary storage.
    # Save the uploaded file into data/raw for this running instance.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    input_path = RAW_DIR / uploaded.name
    input_path.write_bytes(uploaded.getvalue())
    st.success(f"Loaded: {uploaded.name}")
    default_mission_name = Path(uploaded.name).stem

# ---------------------------------------------------------------------
# Mission name
# ---------------------------------------------------------------------
mission_name = st.text_input(
    "Mission name (used for output filenames)",
    value=default_mission_name,
)

# ---------------------------------------------------------------------
# Run cleaning
# ---------------------------------------------------------------------
if st.button("Run Cleaning", type="primary"):
    mission_name = mission_name.strip()
    if not mission_name:
        st.error("Enter a mission name.")
        st.stop()

    with st.spinner(
        "Cleaning data and generating map data..."
    ):
        # -------------------------------------------------------------
        # Run existing cleaning pipeline
        # -------------------------------------------------------------
        report = clean_mission_data(
            input_path,
            output_dir=CLEANED_DIR,
            mission_name=mission_name,
        )

        # -------------------------------------------------------------
        # Read cleaned CSV
        # -------------------------------------------------------------
        cleaned_path = (
            CLEANED_DIR
            / f"{mission_name}_cleaned.csv"
        )

        if not cleaned_path.exists():
            st.error(
                f"Cleaning completed but the expected file was not "
                f"created:\n\n{cleaned_path}"
            )
            st.stop()

        cleaned_df = pd.read_csv(
            cleaned_path,
            parse_dates=["timestamp"],
        )

        # -------------------------------------------------------------
        # Generate GeoJSON
        # -------------------------------------------------------------
        geojson_data = build_geojson(cleaned_df)

        GEO_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        geojson_path = (
            GEO_DIR
            / f"{mission_name}.geojson"
        )

        geojson_path.write_text(
            json.dumps(
                geojson_data,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------
    # Success
    # -----------------------------------------------------------------
    st.success(
        f"Cleaning complete for '{mission_name}'."
    )

    # -----------------------------------------------------------------
    # Cleaning report
    # -----------------------------------------------------------------
    render_section_header("Cleaning Report")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Rows in",
        report.total_rows_in,
    )

    col2.metric(
        "Empty rows dropped",
        report.fully_empty_rows_dropped,
    )

    col3.metric(
        "Duplicate timestamps removed",
        report.duplicate_timestamps_removed,
    )

    col1, col2 = st.columns(2)

    col1.metric(
        "GPS loss rows",
        report.gps_loss_rows,
    )

    col2.metric(
        "Points written to map",
        len(geojson_data["features"]),
    )

    # -----------------------------------------------------------------
    # Data quality information
    # -----------------------------------------------------------------
    if report.hard_range_violations:
        render_section_header(
            "Out-of-Range Values Nulled"
        )
        st.write(
            report.hard_range_violations
        )

    long_gaps = {
        k: v
        for k, v in report.long_gaps_remaining.items()
        if v
    }

    if long_gaps:
        render_section_header(
            "Long Gaps Left as Missing"
        )
        st.write(long_gaps)

    anomalies = {
        k: v
        for k, v in report.anomaly_flags.items()
        if v
    }

    if anomalies:
        render_section_header(
            "Statistical Anomalies Flagged"
        )
        st.write(anomalies)

    flatlines = {
        k: v
        for k, v in report.flatline_flags.items()
        if v
    }

    if flatlines:
        render_section_header(
            "Possible Stuck Sensors"
        )
        st.write(flatlines)

    # -----------------------------------------------------------------
    # Output metadata
    # -----------------------------------------------------------------
    render_technical_metadata(
        {
            "CLEANED CSV": str(
                cleaned_path.relative_to(PROJECT_ROOT)
            ),
            "SUMMARY JSON": str(
                (
                    CLEANED_DIR
                    / f"{mission_name}_summary.json"
                ).relative_to(PROJECT_ROOT)
            ),
            "GEOJSON": str(
                geojson_path.relative_to(PROJECT_ROOT)
            ),
        }
    )

    st.info(
        "This mission is now available on the Mission Dashboard, "
        "Mission Map, and Report Generator pages."
    )

# ---------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------
render_sidebar_status()
"""
SpacePoint - Mission Report Generator
Author: Kommal

Renders the mission's real data, charts, map, and image analysis
directly on the page - the four judgment sections are editable text
boxes placed right where they belong among that content, so you're
writing with the actual results in view, not in a separate box above
a disconnected preview. Generating produces the polished, downloadable
HTML version at the bottom.
"""

import json
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
)

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from generate_report import generate_report, generate_ai_sections, load_summary
from generate_pdf import html_to_pdf_bytes

DATA_DIR = Path("data/cleaned")
IMAGE_ANALYSIS_DIR = Path("data/image_analysis")
SECTION_KEYS = ["objective", "observations", "limitations", "conclusion"]

apply_page_config("Mission Report Generator")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Report")

missions = sorted(p.name.replace("_summary.json", "") for p in DATA_DIR.glob("*_summary.json"))

if not missions:
    st.warning("No mission summaries found. Run the Data Cleaning page first.")
    st.stop()

selected_mission = st.selectbox("Mission", missions)

# Reset the editable text whenever the mission changes, so text from a
# previous mission doesn't carry over
if st.session_state.get("report_sections_mission") != selected_mission:
    st.session_state.report_sections_mission = selected_mission
    st.session_state.report_sections = {key: "" for key in SECTION_KEYS}

summary = load_summary(selected_mission)


# ---------------------------------------------------------------------
# Overview - real numbers, laid out as metrics
# ---------------------------------------------------------------------

render_section_header("Mission Overview")
duration_minutes = round((summary["duration_seconds"] or 0) / 60, 1)
bbox = summary["bounding_box"]
location = "No GPS data"
if bbox:
    location = f"{(bbox['min_lat'] + bbox['max_lat']) / 2:.4f}, {(bbox['min_lon'] + bbox['max_lon']) / 2:.4f}"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Location", location)
col2.metric("Duration", f"{duration_minutes} min")
col3.metric("Samples", summary["sample_count"])
col4.metric("Flagged", summary["flagged_row_count"])


# ---------------------------------------------------------------------
# Objective - editable, right after the overview it's describing
# ---------------------------------------------------------------------

render_section_header("Objective")

if st.button("Draft all sections with AI (Gemini)"):
    with st.spinner("Drafting from this mission's data..."):
        drafted = generate_ai_sections(summary)
    for key in SECTION_KEYS:
        if drafted.get(key):
            st.session_state.report_sections[key] = drafted[key]
    if not any(drafted.values()):
        st.warning("No draft returned - check that GEMINI_API_KEY is set (environment variable or .streamlit/secrets.toml).")

st.session_state.report_sections["objective"] = st.text_area(
    "What was this mission trying to find out?",
    value=st.session_state.report_sections["objective"],
    height=80,
    label_visibility="collapsed",
    placeholder="What was this mission trying to find out?",
)


# ---------------------------------------------------------------------
# Sensor stats table
# ---------------------------------------------------------------------

render_section_header("Data Collected")
st.write(f"Sensors used: BME280, BMP388, SPS30, GPS, IMU, light sensor")
st.table({
    sensor: f"avg {stats['mean']}, min {stats['min']}, max {stats['max']}"
    for sensor, stats in summary["sensor_stats"].items()
})


# ---------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------

render_section_header("Charts")
plots_dir = DATA_DIR / f"{selected_mission}_plots"
if plots_dir.exists():
    chart_paths = sorted(plots_dir.glob("*.png"))
    cols = st.columns(2)
    for i, path in enumerate(chart_paths):
        with cols[i % 2]:
            st.image(str(path), caption=path.stem, use_container_width=True)
else:
    st.info("No charts found for this mission.")


# ---------------------------------------------------------------------
# Image analysis
# ---------------------------------------------------------------------

render_section_header("Image Analysis")
analysis_dir = IMAGE_ANALYSIS_DIR / selected_mission
if analysis_dir.exists():
    stats_files = sorted(analysis_dir.glob("*_stats.json"))
    for stats_path in stats_files:
        stem = stats_path.name.replace("_stats.json", "")
        image_path = analysis_dir / f"{stem}_annotated.png"
        with open(stats_path) as f:
            stats = json.load(f)
        col1, col2 = st.columns([1, 1])
        with col1:
            if image_path.exists():
                st.image(str(image_path), caption=stem, use_container_width=True)
        with col2:
            st.metric("Vegetation", f"{stats.get('vegetation_pct', '-')}%")
            st.metric("Bright surface", f"{stats.get('bright_surface_pct', '-')}%")
            st.write("Land cover:", stats.get("land_cover_breakdown", {}))
else:
    st.info("No saved image analysis for this mission — save one on the Image Tool page to include it here.")


# ---------------------------------------------------------------------
# Observations, Limitations, Conclusion - editable, at the end where
# they'd naturally be written after seeing everything above
# ---------------------------------------------------------------------

render_section_header("Observations")
st.session_state.report_sections["observations"] = st.text_area(
    "What stood out in the data above?",
    value=st.session_state.report_sections["observations"],
    height=110,
    label_visibility="collapsed",
    placeholder="What stood out in the data above?",
)

render_section_header("Limitations")
st.session_state.report_sections["limitations"] = st.text_area(
    "Anything that affects how much to trust this data?",
    value=st.session_state.report_sections["limitations"],
    height=110,
    label_visibility="collapsed",
    placeholder="Anything that affects how much to trust this data?",
)

render_section_header("Conclusion")
st.session_state.report_sections["conclusion"] = st.text_area(
    "What does this mission tell us, and what's next?",
    value=st.session_state.report_sections["conclusion"],
    height=80,
    label_visibility="collapsed",
    placeholder="What does this mission tell us, and what's next?",
)


# ---------------------------------------------------------------------
# Generate the polished, downloadable version
# ---------------------------------------------------------------------

render_section_header("Generate Final Report")
st.caption("Builds the polished, downloadable HTML version from what's written above.")

if st.button("Generate Report", type="primary"):
    report_path = generate_report(selected_mission, section_overrides=st.session_state.report_sections)
    html_content = report_path.read_text()

    pdf_bytes, pdf_error = html_to_pdf_bytes(html_content)

    if pdf_bytes:
        st.success(f"Report generated: {report_path.stem}.pdf")
        st.download_button(
            label="Download report (PDF)",
            data=pdf_bytes,
            file_name=f"{report_path.stem}.pdf",
            mime="application/pdf",
        )
    else:
        st.error(f"Could not convert the report to PDF: {pdf_error}")
        st.download_button(
            label="Download report (HTML) — PDF conversion failed",
            data=html_content,
            file_name=report_path.name,
            mime="text/html",
        )

render_sidebar_status()
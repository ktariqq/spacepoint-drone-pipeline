"""
SpacePoint - Mission Report Generator
Author: Kommal

Pick a mission, generate its HTML report with one click, preview it,
and download it.
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
)

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from generate_report import generate_report

DATA_DIR = Path("data/cleaned")

apply_page_config("Mission Report Generator")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Report")

missions = sorted(p.name.replace("_summary.json", "") for p in DATA_DIR.glob("*_summary.json"))

if not missions:
    st.warning("No mission summaries found. Run the Data Cleaning page first.")
    st.stop()

selected_mission = st.selectbox("Mission", missions)

use_ai = st.checkbox("Draft judgment sections with AI (Gemini)")
if use_ai:
    st.caption(
        "Drafts are grounded in this mission's actual numbers, but they're a starting "
        "point — review and edit before submitting. Requires GEMINI_API_KEY set as "
        "an environment variable or in .streamlit/secrets.toml."
    )

if st.button("Generate Report"):
    report_path = generate_report(selected_mission, use_ai=use_ai)
    st.success(f"Report generated: {report_path.name}")

    html_content = report_path.read_text()
    st.download_button(
        label="Download report (HTML)",
        data=html_content,
        file_name=report_path.name,
        mime="text/html",
    )

    render_section_header("Preview")
    st.components.v1.html(html_content, height=800, scrolling=True)

render_sidebar_status()
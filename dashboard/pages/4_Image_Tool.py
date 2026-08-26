"""
SpacePoint - Drone Image Processing Tool
Author: Kommal
"""

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from image_processing import analyze_image
from branding import (
    apply_page_config,
    render_header,
    render_sidebar_logo,
    render_sidebar_status,
    apply_custom_css,
    render_section_header,
    render_technical_metadata,
)

SAMPLE_IMAGE_DIR = Path("data/images")
ANALYSIS_OUTPUT_DIR = Path("data/image_analysis")
MISSION_DIR = Path("data/cleaned")

apply_page_config("Image Processing Tool")
render_sidebar_logo()
apply_custom_css()
render_header("Image Tool")

st.write(
    "Upload drone images to estimate vegetation coverage and get a rough "
    "land cover breakdown, using a real CV pipeline (Excess Green Index + "
    "Otsu thresholding + K-means land cover clustering) rather than a "
    "trained model - treat results as an educational estimate, not a "
    "precise survey."
)

uploaded_files = st.file_uploader(
    "Upload drone images",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
    image_sources = uploaded_files
else:
    sample_files = sorted(SAMPLE_IMAGE_DIR.glob("*.jpg")) + sorted(SAMPLE_IMAGE_DIR.glob("*.png"))
    if sample_files:
        st.info(f"No upload yet - showing {len(sample_files)} sample image(s) from data/images.")
        image_sources = sample_files
    else:
        st.warning("Upload at least one image, or add images to data/images.")
        st.stop()

results = []
for source in image_sources:
    if hasattr(source, "name"):
        name = source.name
    else:
        name = Path(source).name
    result = analyze_image(source)
    result["name"] = name
    results.append(result)

render_section_header("Image Analysis", caption=f"{len(results)} image(s)")

IMAGE_DISPLAY_WIDTH = "stretch"

for result in results:
    st.markdown(f"**{result['name']}**")
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        st.image(result["original"], caption="Original", width=IMAGE_DISPLAY_WIDTH)
    with col2:
        st.image(
            result["annotated"],
            caption="Annotated (purple = vegetation, red = bright surface)",
            width=IMAGE_DISPLAY_WIDTH,
        )
    with col3:
        st.metric("Vegetation", f"{result['stats']['vegetation_pct']}%")
        st.metric("Bright surface", f"{result['stats']['bright_surface_pct']}%")
        render_technical_metadata(
            {
                "VEG THRESHOLD (ExG)": f"{result['stats']['vegetation_threshold']:.1f}",
                "BRIGHTNESS THRESHOLD": f"{result['stats']['brightness_threshold']:.1f}",
            }
        )
        st.caption("K-means land cover breakdown")
        st.write(result['stats']['land_cover_breakdown'])

    st.divider()

if len(results) >= 2:
    render_section_header("Compare Two Images")

    names = [r["name"] for r in results]
    col_a, col_b = st.columns(2)
    with col_a:
        choice_a = st.selectbox("Image A", names, index=0)
    with col_b:
        choice_b = st.selectbox("Image B", names, index=1)

    result_a = next(r for r in results if r["name"] == choice_a)
    result_b = next(r for r in results if r["name"] == choice_b)

    col1, col2 = st.columns(2)
    with col1:
        st.image(result_a["annotated"], caption=choice_a, width=IMAGE_DISPLAY_WIDTH)
        st.write(result_a["stats"])
    with col2:
        st.image(result_b["annotated"], caption=choice_b, width=IMAGE_DISPLAY_WIDTH)
        st.write(result_b["stats"])

    veg_diff = result_b["stats"]["vegetation_pct"] - result_a["stats"]["vegetation_pct"]
    st.metric("Vegetation change (B minus A)", f"{veg_diff:+.1f} percentage points")

render_section_header("Save for Mission Report")

missions = sorted(p.name.replace("_summary.json", "") for p in MISSION_DIR.glob("*_summary.json"))

if not missions:
    st.info("No missions found yet — run the Data Cleaning page first if you want to attach these images to a report.")
else:
    selected_mission = st.selectbox("Attach these results to mission", missions)

    if st.button("Save analysis for this mission's report"):
        output_dir = ANALYSIS_OUTPUT_DIR / selected_mission
        output_dir.mkdir(parents=True, exist_ok=True)

        for result in results:
            stem = Path(result["name"]).stem
            result["annotated"].save(output_dir / f"{stem}_annotated.png")
            stats_path = output_dir / f"{stem}_stats.json"
            stats_path.write_text(json.dumps(result["stats"], indent=2))

        st.success(
            f"Saved {len(results)} analyzed image(s) for {selected_mission}. "
            "They'll now appear in that mission's generated report."
        )

render_sidebar_status()
"""
SpacePoint - Mission Report Generator
Author: Kommal

Fills in the HTML report template using the summary JSON. Charts and
the mission map are embedded as base64 images, not file paths, so the
report is fully self-contained - it works in Streamlit's sandboxed
iframe and still works if downloaded and opened elsewhere.
"""

import base64
import io
import json
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

DATA_DIR = Path("data/cleaned")
IMAGE_ANALYSIS_DIR = Path("data/image_analysis")
GEO_DIR = Path("data/geo")
TEMPLATE_DIR = Path("scripts")


def embed_image_as_base64(path: Path) -> str:
    """Reads an image file and returns it as a base64 data URI."""
    image_bytes = path.read_bytes()
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def render_mission_map_plot(mission_name: str) -> str | None:
    """Static plot of the mission's GPS points colored by temperature,
    as a stand-in for the interactive map in a downloaded/printed report.
    Returns None if this mission has no GeoJSON yet."""
    geojson_path = GEO_DIR / f"{mission_name}.geojson"
    if not geojson_path.exists():
        return None

    import matplotlib.pyplot as plt

    with open(geojson_path) as f:
        geojson_data = json.load(f)

    features = geojson_data["features"]
    if not features:
        return None

    lats = [f["geometry"]["coordinates"][1] for f in features]
    lons = [f["geometry"]["coordinates"][0] for f in features]
    temps = [f["properties"].get("temperature") for f in features]

    fig, ax = plt.subplots(figsize=(6, 5))
    scatter = ax.scatter(lons, lats, c=temps, cmap="plasma", s=25)
    fig.colorbar(scatter, label="Temperature (°C)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"{mission_name} - Flight Path")
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    buffer.seek(0)

    encoded = base64.b64encode(buffer.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def build_ai_prompt(summary: dict) -> str:
    """Turns the mission's real numbers into a prompt, so the model
    writes from actual data instead of inventing anything."""
    stats_text = "\n".join(
        f"- {sensor}: mean={stats['mean']}, min={stats['min']}, max={stats['max']}"
        for sensor, stats in summary["sensor_stats"].items()
    )

    return f"""You are drafting sections of an engineering mission report.
Base every statement strictly on the data below - do not invent numbers,
locations, or events not given here. Keep each section to 2-3 short
sentences, first-person plural ("we"), factual and professional.

Mission: {summary['mission_name']}
Samples collected: {summary['sample_count']}
Duration: {round((summary['duration_seconds'] or 0) / 60, 1)} minutes
Flagged/anomalous readings: {summary['flagged_row_count']}
GPS loss readings: {summary['gps_loss_row_count']}

Sensor statistics:
{stats_text}

Write exactly these four sections, each on its own line, prefixed exactly as shown:
OBJECTIVE: <one sentence on what this mission set out to measure>
OBSERVATIONS: <what the data actually shows, referencing the numbers above>
LIMITATIONS: <caveats based on the flagged/GPS-loss counts above only>
CONCLUSION: <a short, data-grounded takeaway>
"""


def generate_ai_sections(summary: dict) -> dict:
    """Drafts the four judgment sections via the Gemini API. Falls back
    to empty (placeholder) sections if no API key is set or the call fails."""
    api_key = os.environ.get("GEMINI_API_KEY")
    empty = {"objective": None, "observations": None, "limitations": None, "conclusion": None}
    if not api_key:
        return empty

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=build_ai_prompt(summary),
        )
        text = response.text

        sections = dict(empty)
        prefixes = {"objective": "OBJECTIVE:", "observations": "OBSERVATIONS:",
                    "limitations": "LIMITATIONS:", "conclusion": "CONCLUSION:"}
        for line in text.splitlines():
            for key, prefix in prefixes.items():
                if line.strip().startswith(prefix):
                    sections[key] = line.strip()[len(prefix):].strip()
        return sections

    except Exception as error:
        print(f"AI section generation failed, leaving placeholders: {error}")
        return empty


def load_image_analysis(mission_name: str) -> list[dict]:
    """Loads any saved image analysis results for this mission, embedding
    each annotated image as base64 so the report stays self-contained."""
    analysis_dir = IMAGE_ANALYSIS_DIR / mission_name
    if not analysis_dir.exists():
        return []

    entries = []
    for stats_path in sorted(analysis_dir.glob("*_stats.json")):
        stem = stats_path.name.replace("_stats.json", "")
        image_path = analysis_dir / f"{stem}_annotated.png"
        if not image_path.exists():
            continue
        with open(stats_path) as f:
            stats = json.load(f)
        entries.append({"name": stem, "image": embed_image_as_base64(image_path), "stats": stats})
    return entries


def generate_report(mission_name: str, use_ai: bool = False) -> Path:
    summary_path = DATA_DIR / f"{mission_name}_summary.json"
    with open(summary_path) as f:
        summary = json.load(f)

    bbox = summary["bounding_box"]
    location = "No GPS data"
    if bbox:
        center_lat = (bbox["min_lat"] + bbox["max_lat"]) / 2
        center_lon = (bbox["min_lon"] + bbox["max_lon"]) / 2
        location = f"{center_lat:.4f}, {center_lon:.4f}"

    duration_minutes = round((summary["duration_seconds"] or 0) / 60, 1)

    plots_dir = DATA_DIR / f"{mission_name}_plots"
    chart_images = []
    if plots_dir.exists():
        for png_path in sorted(plots_dir.glob("*.png")):
            chart_images.append(embed_image_as_base64(png_path))

    mission_map_image = render_mission_map_plot(mission_name)
    image_analysis = load_image_analysis(mission_name)

    ai_sections = generate_ai_sections(summary) if use_ai else {
        "objective": None, "observations": None, "limitations": None, "conclusion": None
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("report_template.html")

    html = template.render(
        mission_name=summary["mission_name"],
        location=location,
        start_time=summary["start_time"],
        duration_minutes=duration_minutes,
        sample_count=summary["sample_count"],
        flagged_row_count=summary["flagged_row_count"],
        sensors_used="BME280, BMP388, SPS30, GPS, IMU, light sensor",
        sensor_stats=summary["sensor_stats"],
        chart_images=chart_images,
        image_analysis=image_analysis,
        mission_map_image=mission_map_image,
        ai_generated=use_ai,
        **ai_sections,
    )

    output_path = DATA_DIR / f"{mission_name}_report.html"
    output_path.write_text(html)
    return output_path


if __name__ == "__main__":
    import sys
    mission_name = sys.argv[1] if len(sys.argv) > 1 else "sample_mission"
    use_ai = "--ai" in sys.argv
    path = generate_report(mission_name, use_ai=use_ai)
    print(f"Report written to {path}")
"""
SpacePoint - Mission Map

GeoLibre-based GIS viewer for SpacePoint drone missions.
Author: Kommal
"""

import json
import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np
import streamlit as st


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

# This file is: dashboard/pages/3_Mission_Map.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"

DATA_DIR = PROJECT_ROOT / "data"
GEO_DIR = DATA_DIR / "geo"
CLEANED_DIR = DATA_DIR / "cleaned"

# IMPORTANT (fixed):
# Streamlit's static serving only serves ./static relative to the file
# that was actually launched (dashboard/Dashboard.py), NOT the project
# root. See: https://docs.streamlit.io/develop/concepts/configuration/serving-static-files
STATIC_DIR = DASHBOARD_DIR / "static"
STATIC_GEO_DIR = STATIC_DIR / "geo"


# ---------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard.heat_interpolation import (
    compute_idw_grid,
    render_heat_overlay_png,
)

from dashboard.branding import (
    apply_page_config,
    render_header,
    render_sidebar_logo,
    render_sidebar_status,
    apply_custom_css,
    render_section_header,
    render_technical_metadata,
)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

apply_page_config("Mission Map")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Map")

# A simple, readable 5-stop ramp (magma-ish) used for point color-coding
COLOR_STOPS = ["#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]
COLORABLE_SENSORS = ["temperature", "humidity", "pressure", "light", "air_quality"]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def get_browser_origin() -> str:
    """Origin the app is currently being accessed through (localhost or Streamlit Cloud)."""
    try:
        headers = st.context.headers
    except Exception:
        headers = {}

    forwarded_host = headers.get("X-Forwarded-Host")
    host = forwarded_host or headers.get("Host") or "localhost:8501"

    forwarded_proto = headers.get("X-Forwarded-Proto")
    scheme = forwarded_proto.split(",")[0].strip() if forwarded_proto else "http"

    return f"{scheme}://{host}"


def get_static_url(filename: str) -> str:
    """Browser-accessible URL for a file placed in dashboard/static/geo/."""
    origin = get_browser_origin()
    return f"{origin}/app/static/geo/{quote(filename, safe='')}"


def copy_geojson_to_static(mission_name: str, geojson_data: dict) -> Path:
    """Copy the mission GeoJSON into dashboard/static/geo — the copy GeoLibre reads."""
    STATIC_GEO_DIR.mkdir(parents=True, exist_ok=True)
    static_path = STATIC_GEO_DIR / f"{mission_name}.geojson"
    static_path.write_text(
        json.dumps(geojson_data, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return static_path


def build_point_style(mission_name: str, property_name: str, vmin: float, vmax: float) -> dict:
    """
    MapLibre/GeoLibre style JSON that color-codes points by `property_name`.
    GeoLibre binds a style layer to loaded data by the GeoJSON's filename stem,
    so `source` must equal `mission_name` (no `sources` block needed).
    """
    if vmax <= vmin:
        vmax = vmin + 1  # avoid a degenerate interpolation range

    stops = []
    for i, color in enumerate(COLOR_STOPS):
        value = vmin + (vmax - vmin) * i / (len(COLOR_STOPS) - 1)
        stops.extend([value, color])

    return {
        "version": 8,
        "layers": [
            {
                "id": "mission-points",
                "type": "circle",
                "source": mission_name,
                "paint": {
                    "circle-radius": 5,
                    "circle-opacity": 0.9,
                    "circle-stroke-width": 0.6,
                    "circle-stroke-color": "#ffffff",
                    "circle-color": [
                        "case",
                        ["==", ["get", property_name], None],
                        "#888888",
                        ["interpolate", ["linear"], ["to-number", ["get", property_name]], *stops],
                    ],
                },
            }
        ],
    }


def copy_style_to_static(mission_name: str, style_data: dict) -> Path:
    STATIC_GEO_DIR.mkdir(parents=True, exist_ok=True)
    static_path = STATIC_GEO_DIR / f"{mission_name}.style.json"
    static_path.write_text(json.dumps(style_data, indent=2), encoding="utf-8")
    return static_path


def get_available_missions() -> list[str]:
    missions = set()
    if GEO_DIR.exists():
        for path in GEO_DIR.glob("*.geojson"):
            missions.add(path.stem)
    missions.update(st.session_state.get("mission_geojson", {}).keys())
    return sorted(missions)


def load_mission_geojson(mission_name: str) -> dict | None:
    geojson_path = GEO_DIR / f"{mission_name}.geojson"
    if geojson_path.exists():
        try:
            with open(geojson_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            st.error(f"Could not read mission GeoJSON: {exc}")
            return None

    session_geojson = st.session_state.get("mission_geojson", {})
    return session_geojson.get(mission_name)


def load_mission_summary(mission_name: str) -> dict | None:
    summary_path = CLEANED_DIR / f"{mission_name}_summary.json"
    if not summary_path.exists():
        return None
    try:
        with open(summary_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------
# Ensure required directories exist
# ---------------------------------------------------------------------

GEO_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_DIR.mkdir(parents=True, exist_ok=True)
STATIC_GEO_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Mission discovery + load
# ---------------------------------------------------------------------

missions = get_available_missions()

if not missions:
    st.warning("No mission GeoJSON data is available. Go to Data Cleaning and run a mission first.")
    render_sidebar_status()
    st.stop()

selected_mission = st.selectbox("Mission", missions)

geojson_data = load_mission_geojson(selected_mission)

if geojson_data is None:
    st.error(f"Could not load GeoJSON for mission '{selected_mission}'.")
    render_sidebar_status()
    st.stop()

if not isinstance(geojson_data, dict):
    st.error("The mission file is not a valid GeoJSON object.")
    render_sidebar_status()
    st.stop()

if not geojson_data.get("features"):
    st.info("This mission has no valid GPS points to plot. Spatial coordinates are required for the map.")
    render_sidebar_status()
    st.stop()

# Make the GeoJSON available to the browser (fixed path)
static_geojson_path = copy_geojson_to_static(selected_mission, geojson_data)

summary = load_mission_summary(selected_mission)


# ---------------------------------------------------------------------
# Mission bounds
# ---------------------------------------------------------------------

coordinates = []
for feature in geojson_data.get("features", []):
    geometry = feature.get("geometry")
    if not geometry:
        continue
    coords = geometry.get("coordinates")
    if not coords or len(coords) < 2:
        continue
    try:
        lon, lat = float(coords[0]), float(coords[1])
        if np.isfinite(lon) and np.isfinite(lat):
            coordinates.append([lon, lat])
    except (TypeError, ValueError):
        continue

if not coordinates:
    st.warning("No valid spatial coordinates were found.")
    render_sidebar_status()
    st.stop()

all_coords = np.array(coordinates, dtype=float)
lon_min, lon_max = float(all_coords[:, 0].min()), float(all_coords[:, 0].max())
lat_min, lat_max = float(all_coords[:, 1].min()), float(all_coords[:, 1].max())


# ---------------------------------------------------------------------
# View controls
# ---------------------------------------------------------------------

view_mode = st.radio("View", ["Points", "Heat Surface (IDW)"], horizontal=True)

heat_overlay_uri = None
heat_bounds = None
heat_min = None
heat_max = None
heat_sensor = None
style_url = None


def collect_sensor_values(property_name: str):
    values, feats = [], []
    for feature in geojson_data.get("features", []):
        properties = feature.get("properties", {})
        if property_name not in properties:
            continue
        value = properties.get(property_name)
        if value is None:
            continue
        try:
            value = float(value)
            if not np.isfinite(value):
                continue
        except (TypeError, ValueError):
            continue
        values.append(value)
        feats.append(feature)
    return feats, values


if view_mode == "Points":
    color_sensor = st.selectbox("Color points by", COLORABLE_SENSORS, index=0)
    _, values = collect_sensor_values(color_sensor)

    if values:
        style_data = build_point_style(selected_mission, color_sensor, min(values), max(values))
        style_path = copy_style_to_static(selected_mission, style_data)
        style_url = get_static_url(style_path.name)
    else:
        st.caption(f"No valid '{color_sensor}' readings to color by — showing default styling.")

else:
    heat_sensor = st.selectbox(
        "Interpolate", ["temperature", "humidity", "pressure", "light", "air_quality"], index=0
    )

    valid_features, _ = collect_sensor_values(heat_sensor)

    if len(valid_features) < 2:
        st.warning("Not enough valid readings to interpolate a heat surface for this sensor.")
        render_sidebar_status()
        st.stop()

    points = np.array(
        [[f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]] for f in valid_features],
        dtype=float,
    )
    values = np.array([float(f["properties"][heat_sensor]) for f in valid_features], dtype=float)

    valid = np.isfinite(values) & np.isfinite(points).all(axis=1)
    points, values = points[valid], values[valid]

    if len(points) < 2:
        st.warning("Not enough valid readings to interpolate a heat surface for this sensor.")
        render_sidebar_status()
        st.stop()

    bounds = (
        float(points[:, 0].min()), float(points[:, 0].max()),
        float(points[:, 1].min()), float(points[:, 1].max()),
    )
    grid = compute_idw_grid(points, values, bounds)
    heat_overlay_uri = render_heat_overlay_png(grid)
    heat_bounds = bounds
    heat_min = float(np.nanmin(grid))
    heat_max = float(np.nanmax(grid))

    # Still color-code the raw points on the GeoLibre map by the same sensor,
    # so it's not just a flat marker set while you interpret the IDW surface.
    style_data = build_point_style(selected_mission, heat_sensor, heat_min, heat_max)
    style_path = copy_style_to_static(selected_mission, style_data)
    style_url = get_static_url(style_path.name)


# ---------------------------------------------------------------------
# Technical metadata + summary (unchanged)
# ---------------------------------------------------------------------

render_technical_metadata(
    {
        "MISSION": selected_mission,
        "LAT RANGE": f"{lat_min:.4f}° to {lat_max:.4f}°",
        "LON RANGE": f"{lon_min:.4f}° to {lon_max:.4f}°",
        "SOURCE": "ONBOARD GPS + ENVIRONMENTAL TELEMETRY",
        "SAMPLES": len(geojson_data["features"]),
    },
    columns=2,
)

if summary:
    render_section_header("Mission Summary")
    duration_minutes = (summary.get("duration_seconds") or 0) / 60
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Mission", summary.get("mission_name", selected_mission))
    col2.metric("Samples", summary.get("sample_count", len(geojson_data["features"])))
    col3.metric("Duration", f"{duration_minutes:.1f} min")
    col4.metric("Flagged rows", summary.get("flagged_row_count", 0))


# ---------------------------------------------------------------------
# Map section
# ---------------------------------------------------------------------

render_section_header("Mission GIS Workspace" if view_mode == "Points" else "Interpolated Sensor Surface")
st.caption("Explore the mission data against satellite imagery and other GIS layers using GeoLibre.")

geojson_url = get_static_url(f"{selected_mission}.geojson")

params = [
    f"data={quote(geojson_url, safe=':/')}",
    "layout=viewer",
    "theme=dark",
    "welcome=0",
]
if style_url:
    params.append(f"style={quote(style_url, safe=':/')}")

geolibre_url = "https://web.geolibre.app/?" + "&".join(params)

with st.expander("GeoLibre connection details", expanded=False):
    st.write("Local GeoJSON path:")
    st.code(str(static_geojson_path), language="text")
    st.write("Browser-facing GeoJSON URL:")
    st.code(geojson_url, language="text")
    if style_url:
        st.write("Browser-facing style URL:")
        st.code(style_url, language="text")
    st.write("GeoLibre URL:")
    st.code(geolibre_url, language="text")
    st.caption(
        "On Streamlit Community Cloud, files written while the app is running "
        "aren't guaranteed to persist across sessions — if this breaks only on "
        "Cloud and not locally, that's why."
    )

st.iframe(geolibre_url, height=760)

if view_mode == "Heat Surface (IDW)":
    st.image(heat_overlay_uri, caption=f"IDW surface: {heat_sensor} (bounds {heat_bounds})")
    st.caption(f"IDW surface: {heat_sensor} (range {heat_min:.1f}–{heat_max:.1f})")
    st.caption(
        "This overlay is a flat PNG rendered by SpacePoint's own IDW pipeline — "
        "GeoLibre's `data`/`style` parameters don't have a simple way to place an "
        "arbitrary bounded PNG on the map (that needs a georeferenced COG), so it's "
        "shown alongside the map rather than draped on top of it."
    )

render_sidebar_status()
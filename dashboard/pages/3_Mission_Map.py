"""
SpacePoint - Mission Map

GeoLibre-based GIS viewer for SpacePoint drone missions.
Author: Kommal
"""

import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np
import streamlit as st

# ---------------------------------------------------------------------
# Project paths — resolved from this file's location, never from CWD
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"

DATA_DIR = PROJECT_ROOT / "data"
GEO_DIR = DATA_DIR / "geo"
CLEANED_DIR = DATA_DIR / "cleaned"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard.heat_interpolation import compute_idw_grid, render_heat_overlay_png
from dashboard.branding import (
    apply_page_config,
    render_header,
    render_sidebar_logo,
    render_sidebar_status,
    apply_custom_css,
    render_section_header,
    render_technical_metadata,
)
from dashboard.geolibre_static import validate_geojson, get_static_url
from dashboard.geolibre_project import style_geojson_features, build_project, OPENFREEMAP_STYLES
from dashboard.geolibre_publish import publish_project

apply_page_config("Mission Map")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Map")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

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
            import json
            with open(geojson_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            st.error(f"Could not read mission GeoJSON: {exc}")
            return None
    return st.session_state.get("mission_geojson", {}).get(mission_name)


def load_mission_summary(mission_name: str) -> dict | None:
    summary_path = CLEANED_DIR / f"{mission_name}_summary.json"
    if not summary_path.exists():
        return None
    try:
        import json
        with open(summary_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def collect_sensor_values(geojson_data: dict, property_name: str):
    feats, values = [], []
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


NON_SENSOR_PROPERTY_KEYS = {"timestamp", "has_flag", "flags_summary", "surface_type"}


def get_colorable_sensors(geojson_data: dict) -> list[str]:
    """Any numeric property present on the mission's points can be used
    to color them - not the fixed set from the original schema."""
    if not geojson_data.get("features"):
        return []
    sample_properties = geojson_data["features"][0].get("properties", {})
    return [
        key for key, value in sample_properties.items()
        if key not in NON_SENSOR_PROPERTY_KEYS and isinstance(value, (int, float))
    ]


# ---------------------------------------------------------------------
# Ensure required directories exist
# ---------------------------------------------------------------------

GEO_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_DIR.mkdir(parents=True, exist_ok=True)


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

is_valid, validation_error = validate_geojson(geojson_data)
if not is_valid:
    st.error(f"This mission's GeoJSON isn't valid, so it can't be sent to GeoLibre: {validation_error}")
    render_sidebar_status()
    st.stop()

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

colorable_sensors = get_colorable_sensors(geojson_data)

if not colorable_sensors:
    st.warning("No numeric sensor properties found on this mission's points.")
    render_sidebar_status()
    st.stop()

heat_overlay_uri = None
heat_bounds = None
heat_min = None
heat_max = None
heat_sensor = None

if view_mode == "Points":
    col_a, col_b = st.columns(2)
    with col_a:
        color_sensor = st.selectbox("Color points by", colorable_sensors, index=0)
    with col_b:
        basemap_choice = st.selectbox("Basemap", list(OPENFREEMAP_STYLES.keys()), index=0)

else:
    col_a, col_b = st.columns(2)
    with col_a:
        heat_sensor = st.selectbox("Interpolate", colorable_sensors, index=0)
    with col_b:
        basemap_choice = st.selectbox("Basemap", list(OPENFREEMAP_STYLES.keys()), index=0)

    valid_features, _ = collect_sensor_values(geojson_data, heat_sensor)

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

    # Existing IDW heatmap calculation — unchanged.
    grid = compute_idw_grid(points, values, bounds)
    heat_overlay_uri = render_heat_overlay_png(grid)
    heat_bounds = bounds
    heat_min = float(np.nanmin(grid))
    heat_max = float(np.nanmax(grid))


# ---------------------------------------------------------------------
# Technical metadata + summary — unchanged
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
# Build + publish the GeoLibre project
# ---------------------------------------------------------------------

render_section_header("Mission GIS Workspace" if view_mode == "Points" else "Interpolated Sensor Surface")
st.caption("Explore the mission data against satellite imagery and other GIS layers using GeoLibre. Click a point to see its details.")

color_property = heat_sensor if view_mode == "Heat Surface (IDW)" else color_sensor
_, color_values = collect_sensor_values(geojson_data, color_property)

if color_values:
    vmin, vmax = min(color_values), max(color_values)
else:
    vmin, vmax = 0.0, 1.0
    st.caption(f"No valid '{color_property}' readings to color by — points will show default styling.")

styled_geojson = style_geojson_features(geojson_data, color_property, vmin, vmax, selected_mission)

project_data = build_project(
    selected_mission,
    styled_geojson,
    OPENFREEMAP_STYLES[basemap_choice],
    lon_min, lon_max, lat_min, lat_max,
)

project_url, project_cors_ok = publish_project(selected_mission, project_data)

params = [
    f"url={quote(project_url, safe=':/')}",
    "layout=viewer",
    "panels=collapsed",
    "theme=dark",
    "welcome=0",
]
geolibre_url = "https://web.geolibre.app/?" + "&".join(params)

with st.expander("GeoLibre connection details", expanded=False):
    st.write("Project URL fed to GeoLibre:")
    st.code(project_url, language="text")

    if not project_cors_ok:
        st.warning(
            "No JSONBIN_MASTER_KEY is configured, so this is falling back to Streamlit's "
            "own static URL, which is not confirmed to work inside GeoLibre due to CORS. "
            "Add the secret to enable reliable hosting."
        )

    st.write("GeoLibre URL:")
    st.code(geolibre_url, language="text")

    st.write("Local debug copy (open this yourself to confirm the raw project JSON — not what GeoLibre fetches when JSONBin is configured):")
    st.code(get_static_url(f"{selected_mission}.geolibre.json"), language="text")

st.iframe(geolibre_url, height=760)

if view_mode == "Heat Surface (IDW)":
    st.image(heat_overlay_uri, caption=f"IDW surface: {heat_sensor} (bounds {heat_bounds})")
    st.caption(f"IDW surface: {heat_sensor} (range {heat_min:.1f}–{heat_max:.1f})")
    st.caption(
        "This overlay is a flat PNG from SpacePoint's own IDW pipeline, shown "
        "alongside GeoLibre rather than draped on the map — GeoLibre's data/style "
        "parameters don't have a simple way to place an arbitrary bounded PNG "
        "(that needs a georeferenced COG)."
    )

render_sidebar_status()
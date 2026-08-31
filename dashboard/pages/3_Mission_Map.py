"""
SpacePoint - Mission Map

GeoLibre-based GIS workspace. Works with or without a cleaned mission:
opens as a general GIS view (preloaded global satellite imagery) by
default, with an optional mission to layer on top. All layer show/hide,
reordering, and opacity happens inside GeoLibre's own Layers panel
(layout=compact) - there are no external Streamlit toggles.
Author: Kommal
"""

import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"

DATA_DIR = PROJECT_ROOT / "data"
GEO_DIR = DATA_DIR / "geo"
CLEANED_DIR = DATA_DIR / "cleaned"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard.heat_interpolation import compute_idw_grid, build_heat_contours_geojson
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
from dashboard.geolibre_project import (
    style_geojson_features,
    style_heat_contours,
    build_points_layer,
    build_flight_path_layer,
    build_heatmap_layer,
    build_satellite_reference_layer,
    build_sentinel2_layer,
    build_gibs_truecolor_layer,
    build_gibs_aerosol_layer,
    build_project,
    fit_project_to_size,
    OPENFREEMAP_STYLES,
    KNOWN_UNITS,
    COLOR_STOPS,
)
from dashboard.geolibre_publish import publish_project
from dashboard.components.geolibre_bridge import geolibre_bridge

apply_page_config("Mission Map")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Map")

NON_SENSOR_PROPERTY_KEYS = {"timestamp", "has_flag", "flags_summary", "surface_type", "altitude"}
NO_MISSION_OPTION = "None — GIS workspace only"

# A generous world view so satellite imagery has somewhere sensible to
# frame on when no mission is selected.
WORLD_LON_MIN, WORLD_LON_MAX = -170.0, 170.0
WORLD_LAT_MIN, WORLD_LAT_MAX = -55.0, 75.0
WORLD_ZOOM = 2.2


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


def get_colorable_sensors(geojson_data: dict) -> list[str]:
    if not geojson_data.get("features"):
        return []
    sample_properties = geojson_data["features"][0].get("properties", {})
    return [
        key for key, value in sample_properties.items()
        if key not in NON_SENSOR_PROPERTY_KEYS and isinstance(value, (int, float))
    ]


def preferred_sensor(colorable_sensors: list[str], preferred: str = "temperature") -> str:
    for sensor in colorable_sensors:
        if sensor.lower() == preferred:
            return sensor
    return colorable_sensors[0]


def _get_secret_bool(name: str) -> bool:
    try:
        return bool(st.secrets.get(name, False))
    except Exception:
        return False


@st.cache_data(show_spinner=False)
def _cached_heat_contours(mission_name: str, sensor_name: str, points_tuple, values_tuple, bounds):
    points_arr = np.array(points_tuple, dtype=float)
    values_arr = np.array(values_tuple, dtype=float)
    grid = compute_idw_grid(points_arr, values_arr, bounds)
    return build_heat_contours_geojson(grid, bounds)


GEO_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Mission selection - OPTIONAL. No cleaned data is not an error state.
# ---------------------------------------------------------------------

render_section_header("Mission Data (optional)")
st.caption(
    "This is a general GIS workspace with satellite imagery preloaded — a mission isn't "
    "required. Pick one below to overlay its drone observations, flight path, and heatmap."
)

missions = get_available_missions()
mission_choice = st.selectbox("Mission", [NO_MISSION_OPTION] + missions)
selected_mission = None if mission_choice == NO_MISSION_OPTION else mission_choice

geojson_data = None
summary = None
colorable_sensors = []
lon_min, lon_max, lat_min, lat_max = WORLD_LON_MIN, WORLD_LON_MAX, WORLD_LAT_MIN, WORLD_LAT_MAX
zoom = WORLD_ZOOM

if selected_mission:
    geojson_data = load_mission_geojson(selected_mission)

    if geojson_data is None:
        st.error(f"Could not load GeoJSON for mission '{selected_mission}'. Showing the GIS workspace without it.")
        selected_mission = None
    else:
        is_valid, validation_error = validate_geojson(geojson_data)
        if not is_valid:
            st.error(f"This mission's GeoJSON isn't valid: {validation_error}. Showing the GIS workspace without it.")
            selected_mission = None
            geojson_data = None

if selected_mission and geojson_data:
    summary = load_mission_summary(selected_mission)
    colorable_sensors = get_colorable_sensors(geojson_data)

    if not colorable_sensors:
        st.warning("No numeric sensor properties were found on this mission's points — showing location only.")

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

    if coordinates:
        all_coords = np.array(coordinates, dtype=float)
        lon_min, lon_max = float(all_coords[:, 0].min()), float(all_coords[:, 0].max())
        lat_min, lat_max = float(all_coords[:, 1].min()), float(all_coords[:, 1].max())
        zoom = 14
    else:
        st.warning("No valid spatial coordinates were found for this mission — showing world view.")
        selected_mission = None
        geojson_data = None


# ---------------------------------------------------------------------
# Mission-specific controls - sensor CHOICE only (what data feeds the
# heatmap / point color), not layer visibility. Only shown with a
# mission selected.
# ---------------------------------------------------------------------

color_sensor = None
heat_sensor = None

if selected_mission and colorable_sensors:
    col5, col6 = st.columns(2)
    with col5:
        color_sensor = st.selectbox(
            "Color points by", colorable_sensors,
            index=colorable_sensors.index(preferred_sensor(colorable_sensors)),
        )
    with col6:
        heat_sensor = st.selectbox(
            "Interpolate (heatmap)", colorable_sensors,
            index=colorable_sensors.index(preferred_sensor(colorable_sensors)),
        )
        if heat_sensor.lower() != "temperature":
            st.caption(f"No 'temperature' field on this mission — heatmap will show interpolated {heat_sensor} instead.")

    if summary:
        render_section_header("Mission Summary")
        duration_minutes = (summary.get("duration_seconds") or 0) / 60
        scol1, scol2, scol3, scol4 = st.columns(4)
        scol1.metric("Mission", summary.get("mission_name", selected_mission))
        scol2.metric("Samples", summary.get("sample_count", len(geojson_data["features"])))
        scol3.metric("Duration", f"{duration_minutes:.1f} min")
        scol4.metric("Flagged rows", summary.get("flagged_row_count", 0))

    render_technical_metadata(
        {
            "MISSION": selected_mission,
            "LAT RANGE": f"{lat_min:.4f}° to {lat_max:.4f}°",
            "LON RANGE": f"{lon_min:.4f}° to {lon_max:.4f}°",
            "SAMPLES": len(geojson_data["features"]),
        },
        columns=2,
    )


# ---------------------------------------------------------------------
# STRUCTURAL state: mission + sensors (only exists with a mission) is
# the only thing that changes what gets published. Everything about
# imagery visibility is fixed at publish time and controlled afterward
# entirely inside GeoLibre's own Layers panel.
# ---------------------------------------------------------------------

structural_key = f"{selected_mission or 'global'}::{color_sensor}::{heat_sensor}"

render_section_header("Mission GIS Workspace")
st.caption(
    "Global satellite imagery is preloaded below. Use GeoLibre's own Layers panel to show, "
    "hide, or reorder anything — including additional catalogs via Processing → Planetary "
    "Computer and Plugins → Web Services → NASA Earthdata."
)

heatmap_layer = None
heat_levels = None
heat_unit = ""
styled_points_geojson = None

if selected_mission and color_sensor:
    _, color_values = collect_sensor_values(geojson_data, color_sensor)
    vmin, vmax = (min(color_values), max(color_values)) if color_values else (0.0, 1.0)
    styled_points_geojson = style_geojson_features(geojson_data, color_sensor, vmin, vmax, selected_mission)

    valid_features, _ = collect_sensor_values(geojson_data, heat_sensor)
    if len(valid_features) >= 2:
        points_arr = np.array(
            [[f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]] for f in valid_features],
            dtype=float,
        )
        values_arr = np.array([float(f["properties"][heat_sensor]) for f in valid_features], dtype=float)
        valid_mask = np.isfinite(values_arr) & np.isfinite(points_arr).all(axis=1)
        points_arr, values_arr = points_arr[valid_mask], values_arr[valid_mask]

        if len(points_arr) >= 2:
            bounds = (lat_min, lat_max, lon_min, lon_max)
            contour_geojson, heat_levels = _cached_heat_contours(
                selected_mission, heat_sensor,
                tuple(map(tuple, points_arr)), tuple(values_arr.tolist()),
                bounds,
            )
            styled_contours = style_heat_contours(contour_geojson, heat_levels)
            # Heatmap starts hidden - toggle it on inside GeoLibre's Layers panel.
            heatmap_layer = build_heatmap_layer(selected_mission, styled_contours, visible=False)
            heat_unit = KNOWN_UNITS.get(heat_sensor, "")


def _build_full_layer_set():
    layers = []

    # Global satellite imagery - always present, bottom of the stack.
    # Fixed default visibility set here once; everything past this is
    # controlled inside GeoLibre's own Layers panel.
    layers.append(build_satellite_reference_layer(visible=True))
    layers.append(build_sentinel2_layer(visible=False))
    layers.append(build_gibs_truecolor_layer(visible=False))
    layers.append(build_gibs_aerosol_layer(visible=False))

    if heatmap_layer:
        layers.append(heatmap_layer)

    if selected_mission and geojson_data:
        layers.append(build_flight_path_layer(selected_mission, geojson_data, visible=True))
        points_layer = build_points_layer(
            selected_mission,
            styled_points_geojson if styled_points_geojson else geojson_data,
            visible=True,
        )
        layers.append(points_layer)
        return layers, points_layer["id"]

    return layers, None


if st.session_state.get("_geolibre_structural_key") != structural_key:
    layers, points_layer_id_for_thinning = _build_full_layer_set()
    project_name = selected_mission or "spacepoint-gis-workspace"

    project_data = build_project(
        project_name, layers, OPENFREEMAP_STYLES["Dark"],
        lon_min, lon_max, lat_min, lat_max,
        zoom=zoom,
    )
    project_data, was_thinned = fit_project_to_size(project_data, points_layer_id_for_thinning)
    if was_thinned:
        st.caption(
            "This mission has enough points that the hosted copy was automatically "
            "thinned to fit the free hosting size limit — your cleaned data and "
            "reports are unaffected, only what's shown in GeoLibre."
        )

    project_url, project_cors_ok, publish_error = publish_project(project_name, project_data)

    st.session_state["_geolibre_structural_key"] = structural_key
    st.session_state["_geolibre_project_url"] = project_url
    st.session_state["_geolibre_cors_ok"] = project_cors_ok
    st.session_state["_geolibre_publish_error"] = publish_error
    st.session_state["_geolibre_project_name"] = project_name

project_url = st.session_state["_geolibre_project_url"]
project_cors_ok = st.session_state["_geolibre_cors_ok"]
publish_error = st.session_state["_geolibre_publish_error"]
project_name = st.session_state["_geolibre_project_name"]

params = [
    f"url={quote(project_url, safe=':/')}",
    "layout=compact",
    "theme=dark",
    "welcome=0",
]
geolibre_url = "https://web.geolibre.app/?" + "&".join(params)

if _get_secret_bool("SPACEPOINT_DEBUG_MAP"):
    with st.expander("GeoLibre connection details", expanded=False):
        st.write("Project URL fed to GeoLibre:")
        st.code(project_url, language="text")

        if not project_cors_ok:
            st.warning(
                f"Falling back to Streamlit's own static URL, which is not confirmed to "
                f"work inside GeoLibre due to CORS. Reason hosted publishing didn't succeed: "
                f"{publish_error}"
            )

        st.write("GeoLibre URL:")
        st.code(geolibre_url, language="text")

        st.write("Local debug copy (open this yourself to confirm the raw project JSON):")
        st.code(get_static_url(f"{project_name}.geolibre.json"), language="text")

geolibre_bridge(
    geolibre_url=geolibre_url,
    structural_version=structural_key,
    height=820,
    key="spacepoint_geolibre_map",
)


# ---------------------------------------------------------------------
# Heatmap legend
# ---------------------------------------------------------------------

if heat_levels:
    label = "Temperature Heatmap" if heat_sensor.lower() == "temperature" else f"{heat_sensor.title()} Heatmap"
    render_section_header(f"{label} Legend")
    st.caption("Toggle the heatmap layer on inside GeoLibre's Layers panel to see it on the map.")

    legend_cols = st.columns(len(COLOR_STOPS))
    n = len(COLOR_STOPS)
    for i, color in enumerate(COLOR_STOPS):
        value_at_stop = heat_levels[0] + (heat_levels[-1] - heat_levels[0]) * i / (n - 1)
        with legend_cols[i]:
            st.markdown(
                f"<div style='background:{color};height:14px;border-radius:2px;'></div>"
                f"<div style='font-size:11px;text-align:center;color:#B4B8C6;'>{value_at_stop:.1f}{heat_unit}</div>",
                unsafe_allow_html=True,
            )

    st.caption(
        f"Interpolated {heat_sensor} — inverse-distance-weighted from each grid cell's "
        f"10 nearest readings (power=2). This is a deterministic spatial interpolation, "
        f"not an AI/ML output."
    )

render_sidebar_status()
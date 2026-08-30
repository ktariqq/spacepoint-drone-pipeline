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
    build_project,
    fit_project_to_size,
    KNOWN_UNITS,
    COLOR_STOPS,
    OPENFREEMAP_STYLES,
)
from dashboard.geolibre_publish import publish_project

apply_page_config("Mission Map")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Map")

# "altitude" is a real measurement but a flight parameter, not an
# environmental reading - excluded so it can't silently become the
# default colored/interpolated field instead of temperature.
NON_SENSOR_PROPERTY_KEYS = {"timestamp", "has_flag", "flags_summary", "surface_type", "altitude"}


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
    """Any numeric property present on the mission's points can be used
    to color/interpolate - detected from the data itself, not a fixed
    list, so this works for the original sensor-logger schema and for
    arbitrary CSVs picked up by column_detection.py."""
    if not geojson_data.get("features"):
        return []
    sample_properties = geojson_data["features"][0].get("properties", {})
    return [
        key for key, value in sample_properties.items()
        if key not in NON_SENSOR_PROPERTY_KEYS and isinstance(value, (int, float))
    ]


def preferred_sensor(colorable_sensors: list[str], preferred: str = "temperature") -> str:
    """Defaults to temperature if this mission has it - never assumes
    it does, and never silently falls back to whatever happens to be
    first in the properties dict (that was the altitude bug)."""
    for sensor in colorable_sensors:
        if sensor.lower() == preferred:
            return sensor
    return colorable_sensors[0]


@st.cache_data(show_spinner=False)
def _cached_heat_contours(mission_name: str, sensor_name: str, points_tuple, values_tuple, bounds):
    """Caches the IDW grid + contour extraction so toggling unrelated
    checkboxes (satellite layers, flight path, etc.) doesn't recompute
    this on every Streamlit rerun - only mission/sensor/data changes do."""
    points_arr = np.array(points_tuple, dtype=float)
    values_arr = np.array(values_tuple, dtype=float)
    grid = compute_idw_grid(points_arr, values_arr, bounds)
    return build_heat_contours_geojson(grid, bounds)


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
    st.error(f"This mission's GeoJSON isn't valid: {validation_error}")
    render_sidebar_status()
    st.stop()

summary = load_mission_summary(selected_mission)

colorable_sensors = get_colorable_sensors(geojson_data)

if not colorable_sensors:
    st.warning("No numeric sensor properties were found on this mission's points.")
    render_sidebar_status()
    st.stop()


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
# Layer controls
# ---------------------------------------------------------------------

render_section_header("Mission Data")
col1, col2 = st.columns(2)
with col1:
    show_points = st.checkbox("Drone Observations", value=True)
    show_flight_path = st.checkbox("Flight Path", value=True)
with col2:
    show_heatmap = st.checkbox("Temperature Heatmap", value=False)
    st.checkbox(
        "AI Classification",
        value=False,
        disabled=True,
        help=(
            "Not wired up yet: images uploaded on the Image Tool page aren't geotagged "
            "in the current pipeline, so there's no coordinate to place a classification "
            "result at on this map. Faking a location would be worse than leaving it off."
        ),
    )

render_section_header("Satellite Imagery")
col3, col4 = st.columns(2)
with col3:
    show_esri = st.checkbox("Esri Satellite", value=True)
    show_sentinel2 = st.checkbox("Sentinel-2 True Color", value=False)
with col4:
    st.checkbox("Sentinel-2 False Color / NIR", value=False, disabled=True)
    st.checkbox("Sentinel-2 NDVI", value=False, disabled=True)
    st.checkbox("Sentinel-2 SWIR", value=False, disabled=True)
    st.checkbox("Landsat Thermal", value=False, disabled=True)
    st.checkbox("Sentinel-1 SAR", value=False, disabled=True)
st.caption(
    "The disabled layers above need an authenticated service (Copernicus Data Space, "
    "Sentinel Hub, or USGS/NASA Earthdata) rather than a free keyless public tile "
    "endpoint, so they're shown but not implemented — see geolibre_project.py."
)

col5, col6 = st.columns(2)
with col5:
    color_sensor = st.selectbox(
        "Color points by", colorable_sensors,
        index=colorable_sensors.index(preferred_sensor(colorable_sensors)),
    )

heat_sensor = None
with col6:
    if show_heatmap:
        default_heat = preferred_sensor(colorable_sensors)
        heat_sensor = st.selectbox(
            "Interpolate", colorable_sensors,
            index=colorable_sensors.index(default_heat),
        )
        if heat_sensor.lower() != "temperature":
            st.caption(f"No 'temperature' field on this mission — showing interpolated {heat_sensor} instead.")


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
    scol1, scol2, scol3, scol4 = st.columns(4)
    scol1.metric("Mission", summary.get("mission_name", selected_mission))
    scol2.metric("Samples", summary.get("sample_count", len(geojson_data["features"])))
    scol3.metric("Duration", f"{duration_minutes:.1f} min")
    scol4.metric("Flagged rows", summary.get("flagged_row_count", 0))


# ---------------------------------------------------------------------
# Build layers (bottom to top: imagery -> heatmap -> flight path -> points)
# ---------------------------------------------------------------------

render_section_header("Mission GIS Workspace")
st.caption("Explore the mission data against satellite imagery and other GIS layers using GeoLibre. Click a point to see its details.")

layers = []

imagery_layers = []
if show_esri:
    imagery_layers.append(build_satellite_reference_layer(visible=True))
if show_sentinel2:
    imagery_layers.append(build_sentinel2_layer(visible=True))
if len(imagery_layers) > 1:
    # More than one opaque raster overlay makes them impossible to compare -
    # blend anything after the first so both remain visible together.
    for extra_layer in imagery_layers[1:]:
        extra_layer["opacity"] = 0.6
layers.extend(imagery_layers)

heat_levels = None
heat_unit = ""
if show_heatmap and heat_sensor:
    valid_features, _ = collect_sensor_values(geojson_data, heat_sensor)

    if len(valid_features) < 2:
        st.warning(f"Not enough valid '{heat_sensor}' readings to interpolate a heat surface.")
    else:
        points_arr = np.array(
            [[f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]] for f in valid_features],
            dtype=float,
        )
        values_arr = np.array([float(f["properties"][heat_sensor]) for f in valid_features], dtype=float)
        valid_mask = np.isfinite(values_arr) & np.isfinite(points_arr).all(axis=1)
        points_arr, values_arr = points_arr[valid_mask], values_arr[valid_mask]

        if len(points_arr) < 2:
            st.warning(f"Not enough valid '{heat_sensor}' readings to interpolate a heat surface.")
        else:
            bounds = (lat_min, lat_max, lon_min, lon_max)
            contour_geojson, heat_levels = _cached_heat_contours(
                selected_mission,
                heat_sensor,
                tuple(map(tuple, points_arr)),
                tuple(values_arr.tolist()),
                bounds,
            )
            styled_contours = style_heat_contours(contour_geojson, heat_levels)
            layers.append(build_heatmap_layer(selected_mission, styled_contours, visible=True))
            heat_unit = KNOWN_UNITS.get(heat_sensor, "")

if show_flight_path:
    layers.append(build_flight_path_layer(selected_mission, geojson_data, visible=True))

_, color_values = collect_sensor_values(geojson_data, color_sensor)
if color_values:
    vmin, vmax = min(color_values), max(color_values)
else:
    vmin, vmax = 0.0, 1.0
    st.caption(f"No valid '{color_sensor}' readings to color by — points will show default styling.")

styled_points_geojson = style_geojson_features(geojson_data, color_sensor, vmin, vmax, selected_mission)
points_layer = build_points_layer(selected_mission, styled_points_geojson, visible=show_points)
layers.append(points_layer)


# ---------------------------------------------------------------------
# Build + publish the GeoLibre project
# ---------------------------------------------------------------------

project_data = build_project(
    selected_mission,
    layers,
    OPENFREEMAP_STYLES["Dark"],
    lon_min, lon_max, lat_min, lat_max,
)

project_data, was_thinned = fit_project_to_size(project_data, points_layer["id"])
if was_thinned:
    st.caption(
        "This mission has enough points that the hosted copy was automatically "
        "thinned to fit the free hosting size limit — your cleaned data and "
        "reports are unaffected, only what's shown in GeoLibre."
    )

project_url, project_cors_ok, publish_error = publish_project(selected_mission, project_data)

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
            f"Falling back to Streamlit's own static URL, which is not confirmed to "
            f"work inside GeoLibre due to CORS. Reason hosted publishing didn't succeed: "
            f"{publish_error}"
        )

    st.write("GeoLibre URL:")
    st.code(geolibre_url, language="text")

    st.write("Local debug copy (open this yourself to confirm the raw project JSON):")
    st.code(get_static_url(f"{selected_mission}.geolibre.json"), language="text")

st.iframe(geolibre_url, height=760)


# ---------------------------------------------------------------------
# Heatmap legend
# ---------------------------------------------------------------------

if show_heatmap and heat_levels:
    label = "Temperature Heatmap" if heat_sensor.lower() == "temperature" else f"{heat_sensor.title()} Heatmap"
    render_section_header(f"{label} Legend")

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
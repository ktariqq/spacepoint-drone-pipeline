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
    points_layer_id,
    flight_path_layer_id,
    heatmap_layer_id,
    ESRI_LAYER_ID,
    EOX_TRUECOLOR_LAYER_ID,
    KNOWN_UNITS,
    COLOR_STOPS,
    OPENFREEMAP_STYLES,
)
from dashboard.geolibre_publish import publish_project
from dashboard.satellite_layers import (
    build_sentinel_hub_layer,
    build_landsat_thermal_layer,
    build_sentinel1_sar_layer,
    sentinel_hub_instance_id,
    SENTINEL2_FALSECOLOR_ID,
    SENTINEL2_NDVI_ID,
    SENTINEL2_SWIR_ID,
    LANDSAT_THERMAL_ID,
    SENTINEL1_SAR_ID,
)
from dashboard.components.geolibre_bridge import geolibre_bridge

apply_page_config("Mission Map")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Map")

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

def _get_secret_bool(name: str) -> bool:
    try:
        return bool(st.secrets.get(name, False))
    except Exception:
        return False

@st.cache_data(show_spinner=False)
def _cached_heat_contours(mission_name: str, sensor_name: str, points_tuple, values_tuple, bounds):
    """Caches the IDW grid + contour extraction. Now ALSO used to
    precompute the heatmap even while the "Temperature Heatmap"
    checkbox is unchecked, so that checking it later is a pure
    visibility toggle handled live by the geolibre_bridge component
    instead of a full project republish."""
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

# --- Satellite Imagery checkbox section: replace with: ---
render_section_header("Satellite Imagery")
col3, col4 = st.columns(2)
with col3:
    show_esri = st.checkbox("Esri Satellite", value=True)
    show_eox_truecolor = st.checkbox("Sentinel-2 True Color (EOX)", value=False)
with col4:
    sh_ready = sentinel_hub_instance_id() is not None

    show_falsecolor = st.checkbox(
        "Sentinel-2 False Color / NIR", value=False, disabled=not sh_ready,
        help=None if sh_ready else "Requires SENTINELHUB_INSTANCE_ID in secrets.",
    )
    show_ndvi = st.checkbox(
        "Sentinel-2 NDVI", value=False, disabled=not sh_ready,
        help=None if sh_ready else "Requires SENTINELHUB_INSTANCE_ID in secrets.",
    )
    show_swir = st.checkbox(
        "Sentinel-2 SWIR", value=False, disabled=not sh_ready,
        help=None if sh_ready else "Requires SENTINELHUB_INSTANCE_ID in secrets.",
    )
    # No key required for these two - Planetary Computer's STAC + SAS
    # APIs are anonymously accessible, so they're never disabled here.
    show_landsat_thermal = st.checkbox("Landsat Thermal", value=False)
    show_sentinel1_sar = st.checkbox("Sentinel-1 SAR", value=False)

if not sh_ready:
    st.caption(
        "Sentinel-2 False Color / NDVI / SWIR need SENTINELHUB_INSTANCE_ID "
        "(free — dataspace.copernicus.eu → Sentinel Hub dashboard → Configuration "
        "Utility). Landsat Thermal and Sentinel-1 SAR need no key — Planetary "
        "Computer's STAC and SAS APIs are public."
    )

col5, col6 = st.columns(2)
with col5:
    color_sensor = st.selectbox(
        "Color points by", colorable_sensors,
        index=colorable_sensors.index(preferred_sensor(colorable_sensors)),
    )
with col6:
    default_heat = preferred_sensor(colorable_sensors)
    heat_sensor = st.selectbox(
        "Interpolate (heatmap)", colorable_sensors,
        index=colorable_sensors.index(default_heat),
    )
    if heat_sensor.lower() != "temperature":
        st.caption(f"No 'temperature' field on this mission — heatmap will show interpolated {heat_sensor} instead.")


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
# STRUCTURAL state (mission / color-by / interpolate-by sensor):
# changing any of these actually alters the underlying data, so the
# project must be rebuilt + republished. Pure checkbox toggles below
# do NOT touch this and are instead applied live by geolibre_bridge.
# ---------------------------------------------------------------------

structural_key = f"{selected_mission}::{color_sensor}::{heat_sensor}"

render_section_header("Mission GIS Workspace")
st.caption("Explore the mission data against satellite imagery and other GIS layers using GeoLibre. Click a point to see its details.")

_, color_values = collect_sensor_values(geojson_data, color_sensor)
if color_values:
    vmin, vmax = min(color_values), max(color_values)
else:
    vmin, vmax = 0.0, 1.0
    st.caption(f"No valid '{color_sensor}' readings to color by — points will show default styling.")

styled_points_geojson = style_geojson_features(geojson_data, color_sensor, vmin, vmax, selected_mission)

# Heat contours are ALWAYS computed once a sensor is chosen (not gated
# behind show_heatmap) so that checking the box later is instant/live
# rather than triggering a rebuild.
valid_features, _ = collect_sensor_values(geojson_data, heat_sensor)
heat_levels = None
heat_unit = ""
heatmap_layer = None
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
        heatmap_layer = build_heatmap_layer(selected_mission, styled_contours, visible=show_heatmap)
        heat_unit = KNOWN_UNITS.get(heat_sensor, "")
elif show_heatmap:
    st.warning(f"Not enough valid '{heat_sensor}' readings to interpolate a heat surface.")


# ---------------------------------------------------------------------
# Build ALL layers (bottom to top). Every layer is ALWAYS included in
# the published project regardless of its checkbox - "visible" carries
# the checkbox state at publish time, and everything past this point
# only changes when structural_key changes.
# ---------------------------------------------------------------------

def _build_full_layer_set():
    layers = []

    # Imagery (bottom)
    imagery_layers = []
    imagery_layers.append(build_satellite_reference_layer(visible=show_esri))
    imagery_layers.append(build_sentinel2_layer(visible=show_eox_truecolor))

    for kind, layer_id, label, want in (
        ("false_color", SENTINEL2_FALSECOLOR_ID, "Sentinel-2 False Color / NIR", show_falsecolor),
        ("ndvi", SENTINEL2_NDVI_ID, "Sentinel-2 NDVI", show_ndvi),
        ("swir", SENTINEL2_SWIR_ID, "Sentinel-2 SWIR", show_swir),
    ):
        if sh_ready:
            layer, error = build_sentinel_hub_layer(kind, layer_id, label, visible=want)
            if layer:
                imagery_layers.append(layer)
            elif want:
                st.warning(f"{label}: {error}")

    # Always built (regardless of checkbox) so later toggling is a live,
    # zero-reload visibility change instead of a rebuild — same pattern
    # as the heatmap. bbox = this mission's current area, so the imagery
    # requested always matches wherever the student is looking, globally.
    bbox = (lon_min, lat_min, lon_max, lat_max)

    layer, error = build_landsat_thermal_layer(bbox, visible=show_landsat_thermal)
    if layer:
        imagery_layers.append(layer)
    elif show_landsat_thermal:
        st.warning(f"Landsat Thermal: {error}")

    layer, error = build_sentinel1_sar_layer(bbox, visible=show_sentinel1_sar)
    if layer:
        imagery_layers.append(layer)
    elif show_sentinel1_sar:
        st.warning(f"Sentinel-1 SAR: {error}")

    # More than one opaque raster overlay makes them impossible to compare -
    # blend anything after the first so both remain visible together.
    if len(imagery_layers) > 1:
        for extra_layer in imagery_layers[1:]:
            extra_layer["opacity"] = 0.6
    layers.extend(imagery_layers)

    if heatmap_layer:
        layers.append(heatmap_layer)

    layers.append(build_flight_path_layer(selected_mission, geojson_data, visible=show_flight_path))

    points_layer = build_points_layer(selected_mission, styled_points_geojson, visible=show_points)
    layers.append(points_layer)

    return layers, points_layer


# ---------------------------------------------------------------------
# Publish only when structural_key changed. Otherwise reuse the
# already-published URL and let geolibre_bridge apply the checkbox
# diff live via postMessage.
# ---------------------------------------------------------------------

if st.session_state.get("_geolibre_structural_key") != structural_key:
    layers, points_layer = _build_full_layer_set()

    project_data = build_project(
        selected_mission, layers, OPENFREEMAP_STYLES["Dark"],
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

    st.session_state["_geolibre_structural_key"] = structural_key
    st.session_state["_geolibre_project_url"] = project_url
    st.session_state["_geolibre_cors_ok"] = project_cors_ok
    st.session_state["_geolibre_publish_error"] = publish_error

project_url = st.session_state["_geolibre_project_url"]
project_cors_ok = st.session_state["_geolibre_cors_ok"]
publish_error = st.session_state["_geolibre_publish_error"]

params = [
    f"url={quote(project_url, safe=':/')}",
    "layout=viewer",
    "theme=dark",
    "welcome=0",
    # panels intentionally left unset (not "panels=collapsed") — with
    # panels collapsed, click-to-inspect results have nowhere to
    # display, which was very likely why points looked "unclickable."
    # If you still want a minimal chrome, try "panels=expanded" instead
    # and confirm popups appear before collapsing them again.
]
geolibre_url = "https://web.geolibre.app/?" + "&".join(params)

# Hidden from regular users on purpose: this panel exposes the published
# project URL and (if Supabase/JSONBin aren't configured) a fallback
# static-file URL — internal debugging info, not something to surface to
# students. Set SPACEPOINT_DEBUG_MAP = true in secrets to see it again
# (e.g. while diagnosing a publishing issue yourself).
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
        st.code(get_static_url(f"{selected_mission}.geolibre.json"), language="text")

        st.caption(
            "Live checkbox sync uses GeoLibre's postMessage embed API "
            "(https://geolibre.app/user-guide/embedding/), which only works if "
            "web.geolibre.app has allowlisted this app's origin via "
            "GEOLIBRE_EMBED_ORIGINS on their end — outside SpacePoint's control. "
            "If it's not allowlisted, layer toggles still update without a full "
            "page refresh, but reload just the map pane (camera resets)."
        )

# Deterministic ids -> current desired visibility, sent to the bridge
# on EVERY rerun. Only ids whose value actually changed get a live
# setLayerVisibility() call client-side.
layer_visibility = {
    points_layer_id(selected_mission): show_points,
    flight_path_layer_id(selected_mission): show_flight_path,
    heatmap_layer_id(selected_mission): show_heatmap,
    ESRI_LAYER_ID: show_esri,
    EOX_TRUECOLOR_LAYER_ID: show_eox_truecolor,
    SENTINEL2_FALSECOLOR_ID: show_falsecolor,
    SENTINEL2_NDVI_ID: show_ndvi,
    SENTINEL2_SWIR_ID: show_swir,
    LANDSAT_THERMAL_ID: show_landsat_thermal,
    SENTINEL1_SAR_ID: show_sentinel1_sar,
}

geolibre_bridge(
    geolibre_url=geolibre_url,
    layer_visibility=layer_visibility,
    structural_version=structural_key,
    height=760,
    key="spacepoint_geolibre_map",
)


# ---------------------------------------------------------------------
# Heatmap legend
# ---------------------------------------------------------------------

if heat_levels:
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
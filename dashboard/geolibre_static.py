"""
SpacePoint - GeoLibre static file helpers
Author: Kommal

Centralizes the one thing that has to be gotten right everywhere a mission
GeoJSON/style file is exposed to the browser for GeoLibre: Streamlit's
static file serving only serves ./static relative to the *launched* script
(dashboard/Dashboard.py), at the URL path /app/static/<file>. See:
https://docs.streamlit.io/develop/concepts/configuration/serving-static-files
"""

import json
from pathlib import Path
from urllib.parse import quote

import streamlit as st

# This file lives at dashboard/geolibre_static.py, so its own folder IS
# the app directory Streamlit launches from (dashboard/Dashboard.py).
DASHBOARD_DIR = Path(__file__).resolve().parent
STATIC_DIR = DASHBOARD_DIR / "static"
STATIC_GEO_DIR = STATIC_DIR / "geo"

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


def ensure_static_geo_dir() -> Path:
    STATIC_GEO_DIR.mkdir(parents=True, exist_ok=True)
    return STATIC_GEO_DIR


def get_browser_origin() -> str:
    """
    The scheme+host the visitor's browser is actually using.

    Reverse-proxy headers like X-Forwarded-Proto aren't reliably forwarded
    on every deployment target, and a stale "http" fallback is exactly what
    broke this in production (browsers block a https page from fetching
    mixed-content http data). So: trust an explicit forwarded scheme if one
    is present, otherwise infer it from whether the host looks like local
    dev — every real deployment target, Streamlit Community Cloud included,
    serves over HTTPS; only localhost genuinely uses HTTP.
    """
    try:
        headers = st.context.headers or {}
    except Exception:
        headers = {}

    host = headers.get("Host") or "localhost:8501"
    is_local = host.split(":")[0] in LOCAL_HOSTS

    forwarded_proto = headers.get("X-Forwarded-Proto")
    if forwarded_proto:
        scheme = forwarded_proto.split(",")[0].strip()
    else:
        scheme = "http" if is_local else "https"

    return f"{scheme}://{host}"


def get_static_url(filename: str) -> str:
    origin = get_browser_origin()
    return f"{origin}/app/static/geo/{quote(filename, safe='')}"


def write_geojson_to_static(mission_name: str, geojson_data: dict) -> Path:
    ensure_static_geo_dir()
    path = STATIC_GEO_DIR / f"{mission_name}.geojson"
    path.write_text(json.dumps(geojson_data, indent=2, allow_nan=False), encoding="utf-8")
    return path


def write_style_to_static(mission_name: str, style_data: dict) -> Path:
    ensure_static_geo_dir()
    path = STATIC_GEO_DIR / f"{mission_name}.style.json"
    path.write_text(json.dumps(style_data, indent=2), encoding="utf-8")
    return path


def validate_geojson(geojson_data) -> tuple[bool, str]:
    """Minimal structural check before handing a URL to GeoLibre."""
    if not isinstance(geojson_data, dict):
        return False, "Not a JSON object."
    if geojson_data.get("type") != "FeatureCollection":
        return False, "Missing or invalid 'type' (expected 'FeatureCollection')."
    features = geojson_data.get("features")
    if not isinstance(features, list) or not features:
        return False, "No features present."
    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not geometry or "coordinates" not in geometry:
            return False, "A feature is missing geometry/coordinates."
    return True, ""


def build_point_style(mission_name: str, property_name: str, vmin: float, vmax: float) -> dict:
    """
    MapLibre/GeoLibre style JSON that color-codes points by `property_name`.
    GeoLibre binds a style layer to loaded data by the GeoJSON's filename
    stem, so `source` must equal `mission_name` — no `sources` block needed
    (per GeoLibre's "Export GeoLibre URL style" behavior).
    """
    color_stops = ["#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]
    if vmax <= vmin:
        vmax = vmin + 1

    stops = []
    for i, color in enumerate(color_stops):
        value = vmin + (vmax - vmin) * i / (len(color_stops) - 1)
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
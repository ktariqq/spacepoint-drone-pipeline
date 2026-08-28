"""
SpacePoint - GeoLibre static file helpers
Author: Kommal

Centralizes the one thing that has to be gotten right everywhere a mission
file is exposed to the browser for GeoLibre: Streamlit's static file
serving only serves ./static relative to the *launched* script
(dashboard/Dashboard.py), at the URL path /app/static/<file>. See:
https://docs.streamlit.io/develop/concepts/configuration/serving-static-files

This module's URLs are a local debug/fallback path only. The URL actually
fed to GeoLibre comes from geolibre_publish.py (JSONBin) - see that file
for why.
"""

import json
from pathlib import Path
from urllib.parse import quote

import streamlit as st

DASHBOARD_DIR = Path(__file__).resolve().parent
STATIC_DIR = DASHBOARD_DIR / "static"
STATIC_GEO_DIR = STATIC_DIR / "geo"

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


def ensure_static_geo_dir() -> Path:
    STATIC_GEO_DIR.mkdir(parents=True, exist_ok=True)
    return STATIC_GEO_DIR


def get_browser_origin() -> str:
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


def write_project_to_static(mission_name: str, project_data: dict) -> Path:
    ensure_static_geo_dir()
    path = STATIC_GEO_DIR / f"{mission_name}.geolibre.json"
    path.write_text(json.dumps(project_data, indent=2), encoding="utf-8")
    return path


def validate_geojson(geojson_data) -> tuple[bool, str]:
    """Minimal structural check before it goes into a GeoLibre project."""
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
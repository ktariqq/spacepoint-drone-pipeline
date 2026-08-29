"""
SpacePoint - GeoLibre project (.geolibre.json) builder
Author: Kommal

Builds a GeoLibre project document rather than relying on data=/style=
URL parameters - that path never actually applied per-point color (the
style-layer/source matching didn't bind the way it needed to). Per
GeoLibre's documented project format
(https://github.com/opengeos/GeoLibre/blob/main/docs/project-format.md):

- mapView.bbox opens already framed on the mission's extent.
- basemapStyleUrl sets a specific basemap so it's consistent every time.
- A geojson layer's style.simpleStyleEnabled flag turns on per-feature
  simplestyle-spec overrides (marker-color, title, description) - this
  is the documented mechanism for per-point coloring and click labels.
- The `layers` array we build IS the entire set of layers GeoLibre shows
  on open - nothing else appears, so there's no "default view" to fight.

Per-feature properties are kept deliberately minimal (marker-color,
title, description showing only the colored sensor) because JSONBin's
free tier caps a single record at 100KB - a mission with a few hundred
points can hit that ceiling fast if every sensor field is duplicated
into every feature's description. fit_project_to_size() is a safety net
on top of that: if a mission is still too large after trimming, it
automatically thins the points in the HOSTED copy only (never the
underlying GeoJSON/CSV/reports) until it fits, so this can't silently
break again on a bigger dataset.
"""

import json
import uuid

import numpy as np

COLOR_STOPS = ["#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]

# Real, public, key-free OpenFreeMap basemap styles.
OPENFREEMAP_STYLES = {
    "Dark": "https://tiles.openfreemap.org/styles/dark",
    "Liberty": "https://tiles.openfreemap.org/styles/liberty",
    "Positron": "https://tiles.openfreemap.org/styles/positron",
    "Bright": "https://tiles.openfreemap.org/styles/bright",
    "Fiord": "https://tiles.openfreemap.org/styles/fiord",
}

NON_SENSOR_PROPERTY_KEYS = {"timestamp", "has_flag", "flags_summary", "surface_type"}

# Cosmetic units for sensors we recognize by name - purely decorative.
KNOWN_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "pressure": "hPa",
    "battery_voltage": "V",
}

# JSONBin's free tier hard-caps a record at 100KB, which is why this
# existed originally. Supabase's free tier allows 50MB per file, so this
# threshold is now a generous safety net for the JSONBin fallback path,
# not something that should ever trigger under normal use with Supabase
# configured.
MAX_HOSTED_BYTES = 45_000_000


def color_for_value(value: float, vmin: float, vmax: float) -> str:
    if vmax <= vmin:
        vmax = vmin + 1
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    n = len(COLOR_STOPS) - 1
    idx = min(int(t * n), n - 1)
    return COLOR_STOPS[idx]


def style_geojson_features(geojson_data: dict, property_name: str, vmin: float, vmax: float, mission_name: str) -> dict:
    """
    Returns a NEW geojson dict (does not mutate the input). Every feature
    gets simplestyle-spec marker-color/title/description properties -
    kept minimal on purpose (see module docstring for why).
    """
    unit = KNOWN_UNITS.get(property_name, "")
    styled_features = []

    for feature in geojson_data.get("features", []):
        properties = feature.get("properties", {})
        value = properties.get(property_name)

        color = "#888888"
        description = ""
        try:
            if value is not None:
                v = float(value)
                if np.isfinite(v):
                    color = color_for_value(v, vmin, vmax)
                    description = f"{property_name}: {round(v, 1)}{unit}"
        except (TypeError, ValueError):
            pass

        title = properties.get("timestamp") or mission_name

        trimmed_properties = {
            "marker-color": color,
            "title": title,
            "description": description,
        }

        styled_features.append({
            "type": feature.get("type", "Feature"),
            "geometry": feature.get("geometry"),
            "properties": trimmed_properties,
        })

    return {**geojson_data, "features": styled_features}


def build_satellite_reference_layer(visible: bool = False) -> dict:
    """
    Optional extra raster layer using Esri World Imagery - public, keyless,
    a standard reference-imagery source. Off by default; toggled on from
    Mission Map. To add a real SAR/hyperspectral/other source later (e.g.
    a Sentinel Hub or Copernicus WMS layer you have access to), copy this
    layer's shape and change "type" to "wms" or "cog" per GeoLibre's
    project format, with your own source URL.
    """
    return {
        "id": str(uuid.uuid4()),
        "name": "Satellite Imagery (Esri World Imagery)",
        "type": "xyz",
        "source": {
            "type": "xyz",
            "tiles": [
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ],
        },
        "visible": visible,
        "opacity": 1,
        "style": {},
        "metadata": {"attribution": "Esri, Maxar, Earthstar Geographics"},
    }


def build_project(
    mission_name: str,
    styled_geojson: dict,
    basemap_style_url: str,
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    extra_layers: list[dict] | None = None,
) -> dict:
    layer_id = str(uuid.uuid4())
    center = [(lon_min + lon_max) / 2, (lat_min + lat_max) / 2]

    mission_layer = {
        "id": layer_id,
        "name": mission_name,
        "type": "geojson",
        "source": {"type": "geojson"},
        "visible": True,
        "opacity": 1,
        "style": {
            "simpleStyleEnabled": True,
            "circleRadius": 5,
            "fillColor": "#fe9f6d",
            "strokeColor": "#ffffff",
            "strokeWidth": 1,
            "fillOpacity": 0.9,
        },
        "metadata": {},
        "geojson": styled_geojson,
    }

    layers = list(extra_layers or []) + [mission_layer]
    styles = {layer["id"]: layer["style"] for layer in layers if layer.get("style")}

    return {
        "version": "0.1.0",
        "name": mission_name,
        "mapView": {
            "center": center,
            "zoom": 14,
            "bearing": 0,
            "pitch": 0,
            "bbox": [lon_min, lat_min, lon_max, lat_max],
        },
        "basemapStyleUrl": basemap_style_url,
        "basemapVisible": True,
        "basemapOpacity": 1,
        "layers": layers,
        "styles": styles,
        "metadata": {"source": "SpacePoint Mission Map"},
    }


def _project_size_bytes(project_data: dict) -> int:
    return len(json.dumps(project_data).encode("utf-8"))


def fit_project_to_size(project_data: dict, max_bytes: int = MAX_HOSTED_BYTES) -> tuple[dict, bool]:
    """
    If the project (specifically its mission geojson layer - the one
    carrying a "geojson" key) is too large for JSONBin's free-tier limit,
    thin its points evenly until it fits. Only affects this hosted copy -
    the underlying data/geo/<mission>.geojson, cleaned CSV, and reports
    are never touched. Returns (project_data, was_thinned).
    """
    mission_layer = next((l for l in project_data["layers"] if "geojson" in l), None)
    if mission_layer is None:
        return project_data, False

    features = mission_layer["geojson"]["features"]
    original_count = len(features)
    was_thinned = False

    while _project_size_bytes(project_data) > max_bytes and len(features) > 20:
        was_thinned = True
        features = features[::2]  # keep every other point - halves size each pass
        mission_layer["geojson"] = {**mission_layer["geojson"], "features": features}

    if was_thinned:
        mission_layer["metadata"] = {
            **mission_layer.get("metadata", {}),
            "note": f"Downsampled from {original_count} to {len(features)} points to fit free hosting size limits.",
        }

    return project_data, was_thinned
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
"""

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
# Anything unrecognized still shows up in the description, just without
# a unit suffix, so this works for whatever columns a mission has.
KNOWN_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "pressure": "hPa",
    "battery_voltage": "V",
}


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
    gets simplestyle-spec marker-color/title/description properties.

    Properties are TRIMMED to only what GeoLibre needs to render and label
    each point (marker-color, marker-size, title, description) rather than
    keeping every original sensor field alongside them. The description
    already summarizes every numeric sensor reading, so re-publishing the
    raw fields too would roughly double payload size for no visual benefit
    - and JSONBin's free tier caps a single bin at 100KB, which a mission
    with a few hundred points can realistically exceed if every original
    property is duplicated on top of the new ones.
    """
    styled_features = []
    for feature in geojson_data.get("features", []):
        properties = feature.get("properties", {})
        value = properties.get(property_name)

        color = "#888888"
        try:
            if value is not None:
                v = float(value)
                if np.isfinite(v):
                    color = color_for_value(v, vmin, vmax)
        except (TypeError, ValueError):
            pass

        timestamp = properties.get("timestamp", "")
        title = f"{mission_name} — {timestamp}" if timestamp else mission_name

        summary_bits = []
        for key, val in properties.items():
            if key in NON_SENSOR_PROPERTY_KEYS or key.startswith("flag_"):
                continue
            if val is None or not isinstance(val, (int, float)):
                continue
            unit = KNOWN_UNITS.get(key, "")
            summary_bits.append(f"{key}: {val}{unit}")
        description = " · ".join(summary_bits) if summary_bits else ""

        trimmed_properties = {
            "marker-color": color,
            "marker-size": "small",
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
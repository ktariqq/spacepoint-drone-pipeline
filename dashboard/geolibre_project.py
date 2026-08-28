"""
SpacePoint - GeoLibre project (.geolibre.json) builder
Author: Kommal

Builds a GeoLibre project document instead of relying on data=/style= URL
parameters. Per GeoLibre's documented project format
(https://github.com/opengeos/GeoLibre/blob/main/docs/project-format.md):

- mapView.bbox lets us open already framed on the mission's extent.
- basemapStyleUrl points at a real basemap so it looks the same every time
  instead of whatever GeoLibre's own default happens to be.
- A geojson layer's style.simpleStyleEnabled flag turns on per-feature
  simplestyle-spec overrides (marker-color, etc.) — this is the documented
  mechanism, and doesn't depend on a separate style file being matched up
  correctly, which is what silently failed before.
"""

import uuid

import numpy as np

COLOR_STOPS = ["#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]

OPENFREEMAP_STYLES = {
    "Dark": "https://tiles.openfreemap.org/styles/dark",
    "Liberty": "https://tiles.openfreemap.org/styles/liberty",
    "Positron": "https://tiles.openfreemap.org/styles/positron",
    "Bright": "https://tiles.openfreemap.org/styles/bright",
    "Fiord": "https://tiles.openfreemap.org/styles/fiord",
}


def color_for_value(value: float, vmin: float, vmax: float) -> str:
    if vmax <= vmin:
        vmax = vmin + 1
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    n = len(COLOR_STOPS) - 1
    idx = min(int(t * n), n - 1)
    return COLOR_STOPS[idx]  # flat bucket color; good enough for a quick visual read


def style_geojson_features(geojson_data: dict, property_name: str, vmin: float, vmax: float, mission_name: str) -> dict:
    """
    Returns a NEW geojson dict (does not mutate the input) where every
    feature gets simplestyle-spec marker-color/title/description added
    to its properties, so GeoLibre's per-feature styling picks it up.
    """
    styled_features = []
    for feature in geojson_data.get("features", []):
        properties = dict(feature.get("properties", {}))
        value = properties.get(property_name)

        color = "#888888"
        try:
            if value is not None:
                v = float(value)
                if np.isfinite(v):
                    color = color_for_value(v, vmin, vmax)
        except (TypeError, ValueError):
            pass

        properties["marker-color"] = color
        properties["marker-size"] = "small"

        timestamp = properties.get("timestamp", "")
        properties["title"] = f"{mission_name} — {timestamp}" if timestamp else mission_name

        summary_bits = []
        for label, key, unit in [
            ("Temp", "temperature", "°C"),
            ("Humidity", "humidity", "%"),
            ("Pressure", "pressure", "hPa"),
            ("Air quality", "air_quality", ""),
        ]:
            v = properties.get(key)
            if v is not None:
                summary_bits.append(f"{label} {v}{unit}")
        properties["description"] = " · ".join(summary_bits) if summary_bits else ""

        styled_features.append({**feature, "properties": properties})

    return {**geojson_data, "features": styled_features}


def build_project(
    mission_name: str,
    styled_geojson: dict,
    basemap_style_url: str,
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
) -> dict:
    layer_id = str(uuid.uuid4())
    center = [(lon_min + lon_max) / 2, (lat_min + lat_max) / 2]

    layer = {
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
        "layers": [layer],
        "styles": {layer_id: layer["style"]},
        "metadata": {"source": "SpacePoint Mission Map"},
    }
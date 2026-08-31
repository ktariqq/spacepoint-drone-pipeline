"""
SpacePoint - GeoLibre project (.geolibre.json) builder
Author: Kommal

Builds a GeoLibre project document. Per GeoLibre's documented project
format (https://geolibre.app/project-format/):

- mapView.bbox opens already framed on the mission's extent (or, with no
  mission selected, a world view).
- basemapStyleUrl is the ONE permanent dark base map.
- A geojson layer's style.simpleStyleEnabled flag turns on per-feature
  simplestyle-spec overrides (marker-color/fill/stroke, title,
  description).
- The `layers` array we build IS the entire set of layers GeoLibre shows
  on open, in bottom-to-top order: satellite imagery first, then the
  heatmap, then the flight path, then drone observation points last (on
  top, so they stay clickable). Visibility is now set ONCE here, at
  publish time - there are no external Streamlit checkboxes anymore.
  Show/hide/reorder/opacity all happen inside GeoLibre's own Layers
  panel (layout=compact exposes it) instead.

IDs: every layer gets a DETERMINISTIC id (mission-scoped slug or a fixed
name for basemap-independent imagery layers), kept from earlier work even
though the live-toggle bridge no longer diffs by id - deterministic ids
are still useful for fit_project_to_size() and for anyone inspecting the
published JSON.

Satellite imagery sources, and why each one is included:

- Esri World Imagery: public, key-free, global, default-visible.
- EOX Sentinel-2 cloudless (https://s2maps.eu): key-free global WMTS
  mosaic, annual cloud-free composite. maxzoom capped - EOX's
  s2cloudless layer doesn't publish TileMatrix levels past the
  high-teens, so a tightly-zoomed drone mission was requesting tiles
  that don't exist -> 404s. Capped so MapLibre over-samples instead.
- NASA GIBS MODIS True Color / Aerosol Optical Depth: public, key-free,
  global daily satellite imagery. URL template and both layers' exact
  TileMatrixSet/format are verified against NASA's own GIBS docs
  (https://nasa-gibs.github.io/gibs-api-docs/access-basics/, which shows
  the exact working example URL for MODIS_Terra_Aerosol used here).
  GIBS_REFERENCE_DATE is a fixed, safely-in-the-past date rather than
  "today" - GIBS's most recent 1-3 days are frequently not yet processed
  for every layer, which would 404; a date months in the past is
  reliably available. This is intentionally NOT "live" imagery -
  update GIBS_REFERENCE_DATE occasionally, or (better) add a live/dated
  NASA layer through GeoLibre's own Plugins -> Web Services -> NASA
  Earthdata panel, which handles date selection itself.
- Broader catalogs (NDVI, thermal/LST, SAR, VIIRS false-color, NOAA):
  intentionally NOT hardcoded here. I don't have verified URL/parameter
  combinations for these the way I do for the two GIBS layers above, and
  guessing has repeatedly produced broken tiles in this project before.
  GeoLibre's own Processing -> Planetary Computer and Plugins -> Web
  Services -> NASA Earthdata panels (available now that layout=compact
  is set) are the maintained, correct way to browse and add these - see
  https://geolibre.app/user-guide/data-integrations/.
"""

import json

import numpy as np

COLOR_STOPS = ["#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]

OPENFREEMAP_STYLES = {
    "Dark": "https://tiles.openfreemap.org/styles/dark",
    "Liberty": "https://tiles.openfreemap.org/styles/liberty",
    "Positron": "https://tiles.openfreemap.org/styles/positron",
    "Bright": "https://tiles.openfreemap.org/styles/bright",
    "Fiord": "https://tiles.openfreemap.org/styles/fiord",
}

NON_SENSOR_PROPERTY_KEYS = {"timestamp", "has_flag", "flags_summary", "surface_type", "altitude"}

KNOWN_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "pressure": "hPa",
    "battery_voltage": "V",
}

MAX_HOSTED_BYTES = 45_000_000

EOX_S2CLOUDLESS_MAXZOOM = 14

# See module docstring - a fixed, reliably-processed historical date, not
# "today". Update occasionally for fresher imagery.
GIBS_REFERENCE_DATE = "2026-06-01"


def color_for_value(value: float, vmin: float, vmax: float) -> str:
    if vmax <= vmin:
        vmax = vmin + 1
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    n = len(COLOR_STOPS) - 1
    idx = min(int(t * n), n - 1)
    return COLOR_STOPS[idx]


def style_geojson_features(geojson_data: dict, property_name: str, vmin: float, vmax: float, mission_name: str) -> dict:
    """Returns a NEW geojson dict. Every feature gets simplestyle-spec
    marker-color/title/description properties AND a top-level GeoJSON
    "id" (needed for click-to-inspect - see prior fix)."""
    unit = KNOWN_UNITS.get(property_name, "")
    styled_features = []

    for index, feature in enumerate(geojson_data.get("features", [])):
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
            "id": index,
            "geometry": feature.get("geometry"),
            "properties": trimmed_properties,
        })

    return {**geojson_data, "features": styled_features}


def style_heat_contours(contour_geojson: dict, levels: list[float]) -> dict:
    vmin, vmax = levels[0], levels[-1]
    styled_features = []
    for feature in contour_geojson.get("features", []):
        props = feature.get("properties", {})
        band_min = props.get("value_min", vmin)
        band_max = props.get("value_max", vmax)
        mid = (band_min + band_max) / 2
        color = color_for_value(mid, vmin, vmax)
        styled_features.append({
            "type": feature.get("type", "Feature"),
            "geometry": feature.get("geometry"),
            "properties": {
                **props,
                "fill": color,
                "fill-opacity": 0.55,
                "stroke": color,
                "stroke-opacity": 0,
            },
        })
    return {**contour_geojson, "features": styled_features}


# ---------------------------------------------------------------------
# Deterministic layer ids
# ---------------------------------------------------------------------
def points_layer_id(mission_name: str) -> str:
    return f"{mission_name}::points"


def flight_path_layer_id(mission_name: str) -> str:
    return f"{mission_name}::flightpath"


def heatmap_layer_id(mission_name: str) -> str:
    return f"{mission_name}::heatmap"


ESRI_LAYER_ID = "esri-satellite"
EOX_TRUECOLOR_LAYER_ID = "sentinel2-truecolor-eox"
GIBS_TRUECOLOR_LAYER_ID = "gibs-modis-truecolor"
GIBS_AEROSOL_LAYER_ID = "gibs-modis-aerosol"


def build_points_layer(mission_name: str, styled_geojson: dict, visible: bool = True) -> dict:
    """Always last in the layers array - stays on top and clickable."""
    return {
        "id": points_layer_id(mission_name),
        "name": mission_name,
        "type": "geojson",
        "source": {"type": "geojson"},
        "visible": visible,
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


def build_flight_path_layer(mission_name: str, geojson_data: dict, visible: bool = True) -> dict:
    coordinates = [
        f["geometry"]["coordinates"]
        for f in geojson_data.get("features", [])
        if f.get("geometry", {}).get("coordinates")
    ]

    features = []
    if len(coordinates) >= 2:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {"stroke": "#8B5CF6", "stroke-width": 2, "stroke-opacity": 0.85},
        })

    return {
        "id": flight_path_layer_id(mission_name),
        "name": f"{mission_name} - Flight Path",
        "type": "geojson",
        "source": {"type": "geojson"},
        "visible": visible,
        "opacity": 1,
        "style": {
            "simpleStyleEnabled": True,
            "strokeColor": "#8B5CF6",
            "strokeWidth": 2,
        },
        "metadata": {},
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def build_heatmap_layer(mission_name: str, styled_contour_geojson: dict, visible: bool = False) -> dict:
    return {
        "id": heatmap_layer_id(mission_name),
        "name": f"{mission_name} - Temperature Heatmap",
        "type": "geojson",
        "source": {"type": "geojson"},
        "visible": visible,
        "opacity": 1,
        "style": {
            "simpleStyleEnabled": True,
            "fillColor": "#4FD1C5",
            "fillOpacity": 0.55,
            "strokeWidth": 0,
        },
        "metadata": {},
        "geojson": styled_contour_geojson,
    }


def build_satellite_reference_layer(visible: bool = True) -> dict:
    """Esri World Imagery - public, keyless, global. Default-visible."""
    return {
        "id": ESRI_LAYER_ID,
        "name": "Esri Satellite",
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


def build_sentinel2_layer(visible: bool = False) -> dict:
    """EOX Sentinel-2 cloudless global mosaic - annual composite."""
    return {
        "id": EOX_TRUECOLOR_LAYER_ID,
        "name": "Sentinel-2 True Color (EOX cloudless)",
        "type": "xyz",
        "source": {
            "type": "xyz",
            "tiles": ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg"],
            "maxzoom": EOX_S2CLOUDLESS_MAXZOOM,
        },
        "visible": visible,
        "opacity": 1,
        "style": {},
        "metadata": {
            "attribution": "Sentinel-2 cloudless — s2maps.eu by EOX IT Services GmbH "
                           "(Contains modified Copernicus Sentinel data 2024)"
        },
    }


def build_gibs_truecolor_layer(visible: bool = False) -> dict:
    """NASA GIBS MODIS/Terra Corrected Reflectance True Color. Public,
    keyless, global daily imagery. GoogleMapsCompatible_Level9/jpg is
    GIBS's documented standard combination for this specific layer."""
    tile_url = (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
        f"MODIS_Terra_CorrectedReflectance_TrueColor/default/{GIBS_REFERENCE_DATE}/"
        "GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"
    )
    return {
        "id": GIBS_TRUECOLOR_LAYER_ID,
        "name": f"MODIS Terra True Color (NASA GIBS, {GIBS_REFERENCE_DATE})",
        "type": "xyz",
        "source": {"type": "xyz", "tiles": [tile_url], "maxzoom": 9},
        "visible": visible,
        "opacity": 1,
        "style": {},
        "metadata": {"attribution": "NASA EOSDIS GIBS / MODIS Terra"},
    }


def build_gibs_aerosol_layer(visible: bool = False) -> dict:
    """NASA GIBS MODIS/Terra Aerosol Optical Depth. Public, keyless,
    global. URL shape and GoogleMapsCompatible_Level6/png verified
    directly against GIBS's own documented example request."""
    tile_url = (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
        f"MODIS_Terra_Aerosol/default/{GIBS_REFERENCE_DATE}/"
        "GoogleMapsCompatible_Level6/{z}/{y}/{x}.png"
    )
    return {
        "id": GIBS_AEROSOL_LAYER_ID,
        "name": f"MODIS Terra Aerosol Optical Depth (NASA GIBS, {GIBS_REFERENCE_DATE})",
        "type": "xyz",
        "source": {"type": "xyz", "tiles": [tile_url], "maxzoom": 6},
        "visible": visible,
        "opacity": 0.75,
        "style": {},
        "metadata": {"attribution": "NASA EOSDIS GIBS / MODIS Terra"},
    }


def build_project(
    project_name: str,
    layers: list[dict],
    basemap_style_url: str,
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    zoom: float = 14,
) -> dict:
    center = [(lon_min + lon_max) / 2, (lat_min + lat_max) / 2]
    styles = {layer["id"]: layer["style"] for layer in layers if layer.get("style")}

    return {
        "version": "0.1.0",
        "name": project_name,
        "mapView": {
            "center": center,
            "zoom": zoom,
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


def fit_project_to_size(project_data: dict, target_layer_id: str | None, max_bytes: int = MAX_HOSTED_BYTES) -> tuple[dict, bool]:
    """Thins the points layer only if present and needed (no-op when
    target_layer_id is None, e.g. the no-mission global view)."""
    if target_layer_id is None:
        return project_data, False

    target_layer = next((l for l in project_data["layers"] if l.get("id") == target_layer_id), None)
    if target_layer is None or "geojson" not in target_layer:
        return project_data, False

    features = target_layer["geojson"]["features"]
    original_count = len(features)
    was_thinned = False

    while _project_size_bytes(project_data) > max_bytes and len(features) > 20:
        was_thinned = True
        features = features[::2]
        target_layer["geojson"] = {**target_layer["geojson"], "features": features}

    if was_thinned:
        target_layer["metadata"] = {
            **target_layer.get("metadata", {}),
            "note": f"Downsampled from {original_count} to {len(features)} points to fit free hosting size limits.",
        }

    return project_data, was_thinned
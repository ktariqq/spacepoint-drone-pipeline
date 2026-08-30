"""
SpacePoint - GeoLibre project (.geolibre.json) builder
Author: Kommal

Builds a GeoLibre project document. Per GeoLibre's documented project
format (https://github.com/opengeos/GeoLibre/blob/main/docs/project-format.md):

- mapView.bbox opens already framed on the mission's extent.
- basemapStyleUrl is the ONE permanent dark base map - never a selectable
  option (per spec, there is no basemap picker; satellite imagery is a
  toggleable overlay ABOVE this base, not a replacement for it).
- A geojson layer's style.simpleStyleEnabled flag turns on per-feature
  simplestyle-spec overrides (marker-color/fill/stroke, title,
  description) - this is the documented mechanism used for points, the
  flight path line, and the heatmap contour polygons alike.
- The `layers` array we build IS the entire set of layers GeoLibre shows
  on open, in bottom-to-top order: imagery overlays first, then the
  heatmap, then the flight path, then drone observation points last (on
  top, so they stay clickable over everything beneath them).

IDs (NEW): every layer now gets a DETERMINISTIC id (mission-scoped slug
or a fixed name for basemap-independent imagery layers) instead of a
random uuid4(). This is required for live layer-visibility toggling: the
embed bridge (dashboard/components/geolibre_bridge) targets layers by id
via GeoLibre's postMessage `setLayerVisibility(id, visible)` command, and
random ids would be a different, untargetable id on every Streamlit rerun.

Satellite imagery sources, and why each one is or isn't included:

- Esri World Imagery: public, key-free, global, already working -
  unchanged. Default enabled imagery layer.
- EOX Sentinel-2 cloudless (https://s2maps.eu): a real, documented,
  key-free global WMTS mosaic (CC BY 4.0, attribution required). This is
  an annual CLOUD-FREE COMPOSITE, not a live single-date acquisition.
  FIXED: the layer now declares "maxzoom" on its raster source. EOX's
  s2cloudless WMTS layer does not publish TileMatrix levels past the
  high-teens (10 m native Sentinel-2 resolution has no more detail to
  give past that), so a mission zoomed in tight (drone missions are
  small-area, high zoom) was requesting z19/z20 tiles that simply don't
  exist -> consistent 404s. Capping maxzoom tells MapLibre to
  over-sample the deepest real tile instead of requesting one that isn't
  there.
- Sentinel-2 False Color/NIR, NDVI, SWIR: implemented via the Copernicus
  Data Space Ecosystem's Sentinel Hub OGC WMS service
  (sh.dataspace.copernicus.eu) - see dashboard/satellite_layers.py.
  Requires a free Sentinel Hub "configuration" (instance ID). Uses
  MapLibre's documented `{bbox-epsg-3857}` WMS tile-URL templating so
  requests are genuinely dynamic per viewport, globally - not a fixed
  bounding box.
- Landsat Thermal, Sentinel-1 SAR: implemented via Microsoft Planetary
  Computer's Data API dynamic mosaic tiler (STAC-search-backed, global,
  any pan/zoom) - see dashboard/satellite_layers.py. Requires a free
  Planetary Computer subscription key.
"""

import json

import numpy as np

COLOR_STOPS = ["#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]

# Real, public, key-free OpenFreeMap basemap styles. Only "Dark" is ever
# used now - kept as a dict (rather than a bare string) in case a future,
# explicitly-requested change wants a different single permanent base.
OPENFREEMAP_STYLES = {
    "Dark": "https://tiles.openfreemap.org/styles/dark",
    "Liberty": "https://tiles.openfreemap.org/styles/liberty",
    "Positron": "https://tiles.openfreemap.org/styles/positron",
    "Bright": "https://tiles.openfreemap.org/styles/bright",
    "Fiord": "https://tiles.openfreemap.org/styles/fiord",
}

# "altitude" is a real measurement but a flight parameter, not an
# environmental reading - excluded so it can't silently become the
# default colored/interpolated field instead of temperature (this was a
# real bug: column order put it first in some missions).
NON_SENSOR_PROPERTY_KEYS = {"timestamp", "has_flag", "flags_summary", "surface_type", "altitude"}

# Cosmetic units for sensors we recognize by name - purely decorative.
KNOWN_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "pressure": "hPa",
    "battery_voltage": "V",
}

# JSONBin's free tier hard-caps a record at 100KB, which is why this
# existed originally. Supabase's free tier allows 50MB per file, so this
# threshold is now a generous safety net for the JSONBin fallback path.
MAX_HOSTED_BYTES = 45_000_000

# EOX s2cloudless does not publish TileMatrix levels beyond this - see
# module docstring. Verified against https://tiles.maps.eox.at/wmts/1.0.0/WMTSCapabilities.xml;
# re-check that capabilities document if EOX ever changes their max level.
EOX_S2CLOUDLESS_MAXZOOM = 14


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
    kept minimal on purpose to stay well under hosting size limits.
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


def style_heat_contours(contour_geojson: dict, levels: list[float]) -> dict:
    """
    Colors each contour-band polygon by its value range. Returns a NEW
    geojson dict with simplestyle fill/stroke properties set, using the
    same color ramp as the drone points for visual consistency.
    """
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
# Mission-scoped layers (points/flight path/heatmap) are unique per
# mission. Imagery layers are basemap-style overlays and share one id
# across missions - that's fine, ids only need to be unique WITHIN one
# published project.
def points_layer_id(mission_name: str) -> str:
    return f"{mission_name}::points"


def flight_path_layer_id(mission_name: str) -> str:
    return f"{mission_name}::flightpath"


def heatmap_layer_id(mission_name: str) -> str:
    return f"{mission_name}::heatmap"


ESRI_LAYER_ID = "esri-satellite"
EOX_TRUECOLOR_LAYER_ID = "sentinel2-truecolor-eox"
# Ids for the new satellite layers live in satellite_layers.py, next to
# the code that builds them (SENTINEL2_FALSECOLOR_ID, SENTINEL2_NDVI_ID,
# SENTINEL2_SWIR_ID, LANDSAT_THERMAL_ID, SENTINEL1_SAR_ID).


def build_points_layer(mission_name: str, styled_geojson: dict, visible: bool = True) -> dict:
    """The drone observation points - always last in the layers array so
    it stays on top and clickable over any imagery/heatmap beneath it."""
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
    """A LineString connecting mission points in their existing
    (already time-sorted, per clean_mission_data.py) order."""
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
    """The IDW-interpolated surface, rendered as real georeferenced
    contour-band polygons - a genuine GeoLibre layer, not a separate
    image. Placed before the points/flight-path layers in the layers
    array so it renders beneath them."""
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


def build_satellite_reference_layer(visible: bool = False) -> dict:
    """
    Esri World Imagery - public, keyless, a standard reference-imagery
    source. Already working; kept unchanged. Default enabled imagery
    layer over the dark base map.
    """
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
    """
    EOX Sentinel-2 cloudless global mosaic (2024 edition) -
    https://s2maps.eu - a real, documented, key-free WMTS service,
    consumed here as XYZ-style tiles. Free for non-commercial use with
    attribution (CC BY 4.0; contains modified Copernicus Sentinel data).
    This is a cloud-free ANNUAL MOSAIC composited from Sentinel-2
    imagery, not a live/on-demand single-date acquisition.

    FIXED: added source.maxzoom. Without it, a tightly-zoomed drone
    mission requests TileMatrix levels EOX doesn't publish -> 404 on
    every tile. With maxzoom set, MapLibre stops requesting tiles past
    that level and stretches the deepest available tile instead.
    """
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


def build_project(
    mission_name: str,
    layers: list[dict],
    basemap_style_url: str,
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
) -> dict:
    center = [(lon_min + lon_max) / 2, (lat_min + lat_max) / 2]
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


def fit_project_to_size(project_data: dict, target_layer_id: str, max_bytes: int = MAX_HOSTED_BYTES) -> tuple[dict, bool]:
    """
    If the project is too large for JSONBin's free-tier fallback limit,
    thin the points in ONE specific layer (identified by id - always the
    drone-observations layer, never the flight path or heatmap contours,
    which are much smaller and shouldn't be touched). Only affects this
    hosted copy - the underlying data/geo/<mission>.geojson, cleaned CSV,
    and reports are never touched. Returns (project_data, was_thinned).
    """
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
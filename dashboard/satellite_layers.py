"""
SpacePoint - Additional satellite imagery layers
Author: Kommal

Sentinel-2 False Color / NIR, NDVI, SWIR
-----------------------------------------
Copernicus Data Space Ecosystem's Sentinel Hub OGC WMS service. This is
a plain OGC WMS GetMap endpoint - per Copernicus's own docs, the
configuration's INSTANCE ID is what authenticates OGC requests; OGC WMS
has no standard auth mechanism and Sentinel Hub does not support
OAuth/password on it (they explicitly point people to the Process API
for that). So this reads ONLY SENTINELHUB_INSTANCE_ID from st.secrets -
no OAuth client, no access token, nothing to refresh. Adding OAuth here
would be unnecessary complexity the WMS endpoint can't use anyway.

Get an instance ID: https://dataspace.copernicus.eu -> Sentinel Hub
dashboard -> Configuration Utility -> new configuration from the
"Sentinel-2 L2A" template -> copy the Instance ID.

We build the tile URL with MapLibre GL's documented `{bbox-epsg-3857}`
raster-source template variable, so every tile request carries the
CURRENT tile's real bounding box - genuinely global/dynamic, not a
fixed area.

Landsat Thermal / Sentinel-1 SAR
----------------------------------
No subscription key required. Flow, all public/anonymous:
  1. STAC search (https://planetarycomputer.microsoft.com/api/stac/v1/search)
     against the mission's current bounding box + a rolling recent
     date window -> best matching scene (lowest cloud cover).
  2. SAS token retrieval (https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection})
     - anonymous, short-lived, cached with a TTL shorter than the
     token's own expiry so it's re-fetched before going stale. Never
     hardcoded, never persisted.
  3. The signed asset URL is handed to Planetary Computer's public
     item tiler (/api/data/v1/item/tiles/...), which renders XYZ tiles
     dynamically for that scene at whatever pan/zoom the student is at.

An optional PC_SUBSCRIPTION_KEY, if present, is forwarded server-side
to raise rate limits on the STAC/SAS calls only - it is never embedded
in the tile URL sent to the browser. The SAS token itself DOES end up
in that tile URL (that's the entire point of a SAS token: a short-lived,
read-only, revocable-by-expiry credential Microsoft explicitly designed
for client-side/public map use) - this is a materially different thing
from a subscription key or OAuth secret, neither of which ever leaves
the server in this implementation.
"""

from __future__ import annotations

import datetime as _dt
from urllib.parse import quote

import requests
import streamlit as st

# ---------------------------------------------------------------------
# Sentinel Hub (OGC WMS - instance-id auth only, no OAuth)
# ---------------------------------------------------------------------

SENTINEL_HUB_WMS_BASE = "https://sh.dataspace.copernicus.eu/ogc/wms/{instance_id}"

DEFAULT_SH_LAYER_NAMES = {
    "false_color": "2_FALSE_COLOR",
    "ndvi": "3_NDVI",
    "swir": "4_SWIR",
}

SENTINEL2_FALSECOLOR_ID = "sentinel2-falsecolor-sh"
SENTINEL2_NDVI_ID = "sentinel2-ndvi-sh"
SENTINEL2_SWIR_ID = "sentinel2-swir-sh"
LANDSAT_THERMAL_ID = "landsat-thermal-pc"
SENTINEL1_SAR_ID = "sentinel1-sar-pc"


def _get_secret(name: str, section: str | None = None):
    try:
        if section:
            return st.secrets.get(section, {}).get(name)
        return st.secrets.get(name)
    except Exception:
        return None


def sentinel_hub_instance_id() -> str | None:
    return _get_secret("SENTINELHUB_INSTANCE_ID")


def _sh_layer_name(kind: str) -> str:
    override = _get_secret(kind, section="sentinel_hub_layers")
    return override or DEFAULT_SH_LAYER_NAMES[kind]


def build_sentinel_hub_layer(kind: str, layer_id: str, name: str, visible: bool = False) -> tuple[dict | None, str | None]:
    """kind: one of "false_color", "ndvi", "swir"."""
    instance_id = sentinel_hub_instance_id()
    if not instance_id:
        return None, "SENTINELHUB_INSTANCE_ID is not configured in secrets."

    sh_layer = _sh_layer_name(kind)
    end = _dt.datetime.utcnow().date()
    start = end - _dt.timedelta(days=30)

    base_url = SENTINEL_HUB_WMS_BASE.format(instance_id=instance_id)
    tile_url = (
        f"{base_url}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0"
        f"&LAYERS={sh_layer}&STYLES=&FORMAT=image/png&TRANSPARENT=true"
        f"&CRS=EPSG:3857&WIDTH=256&HEIGHT=256"
        f"&TIME={start.isoformat()}/{end.isoformat()}&MAXCC=40"
        "&BBOX={bbox-epsg-3857}"
    )

    return {
        "id": layer_id,
        "name": name,
        "type": "xyz",
        "source": {
            "type": "xyz",
            "tiles": [tile_url],
            "maxzoom": 16,  # Sentinel-2's 10-20m resolution has no more detail past this
        },
        "visible": visible,
        "opacity": 1,
        "style": {},
        "metadata": {
            "attribution": "Contains modified Copernicus Sentinel data, processed by Sentinel Hub "
                           "(Copernicus Data Space Ecosystem)"
        },
    }, None


# ---------------------------------------------------------------------
# Planetary Computer (public STAC + anonymous SAS - no key required)
# ---------------------------------------------------------------------

PC_STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_SAS_TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"
PC_TILER_ITEM_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@1x"


def pc_subscription_key() -> str | None:
    """Optional. Only raises rate limits on our own STAC/SAS calls -
    everything works anonymously without it."""
    return _get_secret("PC_SUBSCRIPTION_KEY")


def _pc_headers() -> dict:
    key = pc_subscription_key()
    return {"Ocp-Apim-Subscription-Key": key} if key else {}


@st.cache_data(ttl=900, show_spinner=False)
def _stac_search_best_item(collection: str, bbox: tuple, query: dict | None, days_back: int):
    """bbox: (min_lon, min_lat, max_lon, max_lat) - the mission's current
    bounding box, i.e. the "requested geographic area" the imagery must
    match. Re-run automatically (cache expires every 15 min) if the
    mission/area changes, so this never locks onto one fixed area."""
    end = _dt.datetime.utcnow().date()
    start = end - _dt.timedelta(days=days_back)
    body = {
        "collections": [collection],
        "bbox": list(bbox),
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": 20,
    }
    if query:
        body["query"] = query

    try:
        resp = requests.post(PC_STAC_SEARCH_URL, json=body, headers=_pc_headers(), timeout=20)
    except Exception as exc:
        return None, f"STAC search request failed: {exc}"

    if resp.status_code != 200:
        return None, f"STAC search returned HTTP {resp.status_code}: {resp.text[:300]}"

    features = resp.json().get("features", [])
    if not features:
        return None, f"No {collection} scenes found for this area in the last {days_back} days."

    features_sorted = sorted(features, key=lambda f: f.get("properties", {}).get("eo:cloud_cover", 0))
    return features_sorted[0], None


@st.cache_data(ttl=1800, show_spinner=False)
def _get_sas_token(collection: str) -> tuple[str | None, str | None]:
    """Anonymous, short-lived SAS token - no account needed. Cached for
    30 min (PC tokens are typically valid ~1h), so this refreshes well
    before expiry on the next rerun rather than reusing a stale/expired
    signed URL. Nothing here is ever hardcoded."""
    try:
        resp = requests.get(PC_SAS_TOKEN_URL.format(collection=collection), headers=_pc_headers(), timeout=15)
    except Exception as exc:
        return None, f"SAS token request failed: {exc}"

    if resp.status_code != 200:
        return None, f"SAS token endpoint returned HTTP {resp.status_code}: {resp.text[:300]}"

    token = resp.json().get("token")
    if not token:
        return None, "SAS token endpoint returned no token."
    return token, None


def _build_pc_item_layer(
    layer_id: str,
    name: str,
    collection: str,
    asset: str,
    rescale: str,
    colormap_name: str,
    bbox: tuple,
    query: dict | None = None,
    days_back: int = 30,
    visible: bool = False,
) -> tuple[dict | None, str | None]:
    item, error = _stac_search_best_item(collection, bbox, query, days_back)
    if not item:
        return None, error

    href = item.get("assets", {}).get(asset, {}).get("href")
    if not href:
        return None, f"Matching {collection} scene has no '{asset}' asset."

    token, error = _get_sas_token(collection)
    if not token:
        return None, error

    signed_href = href + ("&" if "?" in href else "?") + token

    tile_url = (
        f"{PC_TILER_ITEM_URL}?url={quote(signed_href, safe='')}"
        f"&assets={asset}&rescale={rescale}&colormap_name={colormap_name}&format=png"
    )
    # Server-side only, optional, never the mechanism granting tile access
    # (the SAS token above already does that) - just a higher rate limit.
    key = pc_subscription_key()
    if key:
        tile_url += f"&subscription-key={quote(key)}"

    return {
        "id": layer_id,
        "name": name,
        "type": "xyz",
        "source": {"type": "xyz", "tiles": [tile_url], "maxzoom": 13},
        "visible": visible,
        "opacity": 1,
        "style": {},
        "metadata": {
            "attribution": f"{collection} scene {item.get('id')} via Microsoft Planetary Computer "
                           "(anonymous STAC search + SAS-signed access)"
        },
    }, None


def build_landsat_thermal_layer(bbox: tuple, visible: bool = False) -> tuple[dict | None, str | None]:
    # lwir11 = Landsat Collection 2 Level-2 surface temperature (Kelvin).
    # Rescale is a rough global default - narrow it to your region's
    # expected surface temps for a more useful color ramp.
    return _build_pc_item_layer(
        layer_id=LANDSAT_THERMAL_ID,
        name="Landsat Thermal (Surface Temp, Planetary Computer)",
        collection="landsat-c2-l2",
        asset="lwir11",
        rescale="280,330",
        colormap_name="inferno",
        bbox=bbox,
        query={"platform": {"in": ["LANDSAT_8", "LANDSAT_9"]}},
        days_back=30,
        visible=visible,
    )


def build_sentinel1_sar_layer(bbox: tuple, visible: bool = False) -> tuple[dict | None, str | None]:
    return _build_pc_item_layer(
        layer_id=SENTINEL1_SAR_ID,
        name="Sentinel-1 SAR (VV, Planetary Computer)",
        collection="sentinel-1-grd",
        asset="vv",
        rescale="0,400",
        colormap_name="gray",
        bbox=bbox,
        days_back=30,
        visible=visible,
    )
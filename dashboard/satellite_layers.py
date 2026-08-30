"""
SpacePoint - Additional satellite imagery layers
Author: Kommal

Sentinel-2 False Color / NIR, NDVI, SWIR
-----------------------------------------
FIXED (this revision): switched from WMS GetMap (bbox-based) to Sentinel
Hub's WMTS GetTile. GeoLibre's own XYZ tile-URL resolver only substitutes
{z}/{x}/{y} - it does NOT implement MapLibre's WMS `{bbox-epsg-3857}`
raster-source templating, so the previous WMS approach sent the literal,
unsubstituted string "{bbox-epsg-3857}" to Sentinel Hub, which correctly
rejected it (400). WMTS addresses tiles by TILEMATRIX/TILEROW/TILECOL,
which map directly onto plain {z}/{y}/{x} - the same mechanism the
existing (working) Esri and EOX layers already use.

Reference request shape (Sentinel Hub docs):
https://services.sentinel-hub.com/ogc/wmts/<INSTANCE_ID>?REQUEST=GetTile
    &TILEMATRIXSET=PopularWebMercator512&LAYER=FALSE-COLOR
    &TILEMATRIX=14&TILEROW=3065&TILECOL=4758&TIME=...
We use PopularWebMercator256 (256px tiles, matching the tile size every
other layer in this project already uses) - override via the optional
SENTINELHUB_TILEMATRIXSET secret if your account's GetCapabilities
document names it differently.

Still reads ONLY SENTINELHUB_INSTANCE_ID - no OAuth client, no access
token. The instance id itself authenticates OGC (WMS/WMTS) requests per
Copernicus's own docs; Sentinel Hub does not support OAuth on OGC
endpoints (they point people to the Process API for that, which we don't
use), so adding OAuth here would be unnecessary complexity the OGC
endpoint can't use anyway.

Landsat Thermal / Sentinel-1 SAR
----------------------------------
FIXED (this revision): removed client-side SAS-token signing entirely.
Previously we fetched a SAS token, appended it to the raw asset URL, and
baked that *signed* URL into the published GeoLibre project - since SAS
tokens expire (~45-60 min) and the project is published once and reused
for the life of the browser session, any tile requested after expiry got
a 422 from the blob store. Root fix: Planetary Computer's own item tiler
accepts `collection=` + `item=` (a STAC item id) directly and performs
the asset signing server-side, per tile request - there is now no
client-held, expiring credential at all, so nothing can ever go stale.
This is the same mechanism Planetary Computer's own Explorer web app
uses. STAC search (to pick which scene/item to reference) is unchanged
and still runs against the mission's current bounding box - genuinely
dynamic/global, not a fixed area.

No subscription key required for either the STAC search or the tiler.
An optional PC_SUBSCRIPTION_KEY, if present, is forwarded server-side to
raise rate limits on our STAC search calls only.
"""

from __future__ import annotations

import datetime as _dt
from urllib.parse import quote

import requests
import streamlit as st

# ---------------------------------------------------------------------
# Sentinel Hub (OGC WMTS - instance-id auth only, no OAuth)
# ---------------------------------------------------------------------

SENTINEL_HUB_WMTS_BASE = "https://sh.dataspace.copernicus.eu/ogc/wmts/{instance_id}"

DEFAULT_SH_LAYER_NAMES = {
    "false_color": "2_FALSE_COLOR",
    "ndvi": "3_NDVI",
    "swir": "4_SWIR",
}

DEFAULT_SH_TILEMATRIXSET = "PopularWebMercator256"

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


def _sh_tilematrixset() -> str:
    return _get_secret("SENTINELHUB_TILEMATRIXSET") or DEFAULT_SH_TILEMATRIXSET


def build_sentinel_hub_layer(kind: str, layer_id: str, name: str, visible: bool = False) -> tuple[dict | None, str | None]:
    """kind: one of "false_color", "ndvi", "swir"."""
    instance_id = sentinel_hub_instance_id()
    if not instance_id:
        return None, "SENTINELHUB_INSTANCE_ID is not configured in secrets."

    sh_layer = _sh_layer_name(kind)
    tilematrixset = _sh_tilematrixset()
    end = _dt.datetime.utcnow().date()
    start = end - _dt.timedelta(days=30)

    base_url = SENTINEL_HUB_WMTS_BASE.format(instance_id=instance_id)
    tile_url = (
        base_url
        + "?REQUEST=GetTile&SERVICE=WMTS&VERSION=1.0.0"
        + "&LAYER=" + quote(sh_layer)
        + "&STYLE=default&FORMAT=image/png"
        + "&TILEMATRIXSET=" + quote(tilematrixset)
        + "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
        + f"&TIME={start.isoformat()}/{end.isoformat()}&MAXCC=40"
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
# Planetary Computer (public STAC search + server-signed item tiler)
# ---------------------------------------------------------------------

PC_STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_TILER_ITEM_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@1x"


def pc_subscription_key() -> str | None:
    """Optional. Only raises rate limits on our own STAC search calls -
    everything works anonymously without it. Never sent as part of the
    tile URL's asset-access mechanism (there's no client-side signing
    left to gate) - only as an optional param the tiler/STAC API accept
    for higher throughput."""
    return _get_secret("PC_SUBSCRIPTION_KEY")


def _pc_headers() -> dict:
    key = pc_subscription_key()
    return {"Ocp-Apim-Subscription-Key": key} if key else {}


@st.cache_data(ttl=900, show_spinner=False)
def _stac_search_best_item(collection: str, bbox: tuple, query: dict | None, days_back: int):
    """bbox: (min_lon, min_lat, max_lon, max_lat) - the mission's current
    bounding box, i.e. the "requested geographic area" the imagery must
    match. Re-run automatically (cache expires every 15 min) if the
    mission/area changes, so this never locks onto one fixed area.
    Returns (item_dict_or_None, error_message_or_None). We only need the
    item's id from here on - no asset href, no signing."""
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

    item_id = item.get("id")
    if not item_id:
        return None, f"Matching {collection} scene has no item id."

    # collection= + item= : Planetary Computer's tiler resolves and signs
    # the asset itself, server-side, on EVERY tile request. Nothing here
    # can ever go stale - there is no expiring token embedded in this URL.
    tile_url = (
        PC_TILER_ITEM_URL
        + f"?collection={quote(collection)}&item={quote(item_id)}"
        + f"&assets={quote(asset)}&rescale={rescale}&colormap_name={colormap_name}&format=png"
    )
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
            "attribution": f"{collection} scene {item_id} via Microsoft Planetary Computer "
                           "(asset signed fresh by PC's own tiler on every tile request)"
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
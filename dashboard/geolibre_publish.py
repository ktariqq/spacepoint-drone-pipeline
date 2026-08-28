"""
SpacePoint - GeoLibre data publishing
Author: Kommal

Why this file exists
---------------------
GeoLibre (https://web.geolibre.app) is a separate origin. For it to load a
mission's GeoJSON/style via its `data=`/`style=` parameters, the browser has
to fetch() those URLs cross-origin, which requires the response to carry
Access-Control-Allow-Origin. Streamlit's static file server has no
documented guarantee of that for a third-party fetch, and there's a
confirmed community report of exactly this pattern failing on Streamlit
Community Cloud (streamlit/streamlit#8808 — a Streamlit-hosted static JSON
fed into a third-party iframe app). Opening the static URL yourself in a
browser tab looks fine regardless, because a top-level navigation is never
subject to CORS in the first place — only a cross-origin fetch() is, which
is what GeoLibre actually does.

So: publish the mission JSON to JSONBin.io instead, which documents CORS
enabled on every endpoint (https://jsonbin.io/api-reference). One-time
setup: a free account + a Master Key stored as a secret. No per-mission
manual upload by the user, ever - publishing happens automatically here.

If no key is configured, this falls back to Streamlit's own static folder
so the app doesn't crash - but that fallback is NOT guaranteed to work
inside GeoLibre, only for opening the link yourself, and the UI says so.
"""

import streamlit as st
import requests

from geolibre_static import (
    write_geojson_to_static,
    write_style_to_static,
    get_static_url,
)

JSONBIN_BASE = "https://api.jsonbin.io/v3/b"


def _get_master_key() -> str | None:
    try:
        return st.secrets.get("JSONBIN_MASTER_KEY")
    except Exception:
        return None


def _publish_json(payload: dict, cache_key: str) -> str | None:
    """
    Create-or-update a public JSONBin bin for this payload. The bin id is
    cached in session_state per cache_key so re-viewing the same mission in
    the same session updates the existing bin instead of creating a new one
    on every rerun. Returns a public, CORS-enabled, meta-stripped read URL,
    or None if no key is configured or the request failed.
    """
    api_key = _get_master_key()
    if not api_key:
        return None

    bin_ids = st.session_state.setdefault("jsonbin_ids", {})
    existing_id = bin_ids.get(cache_key)
    headers = {"Content-Type": "application/json", "X-Master-Key": api_key}

    try:
        if existing_id:
            resp = requests.put(
                f"{JSONBIN_BASE}/{existing_id}", json=payload, headers=headers, timeout=10
            )
        else:
            headers["X-Bin-Private"] = "false"  # must be public: GeoLibre's fetch carries no auth header
            resp = requests.post(JSONBIN_BASE, json=payload, headers=headers, timeout=10)

        if resp.status_code not in (200, 201):
            return None

        bin_id = resp.json()["metadata"]["id"]
        bin_ids[cache_key] = bin_id
        return f"{JSONBIN_BASE}/{bin_id}?meta=false"

    except Exception:
        return None


def publish_geojson(mission_name: str, geojson_data: dict) -> tuple[str, bool]:
    """Returns (url, is_cors_verified)."""
    write_geojson_to_static(mission_name, geojson_data)  # local copy, for the debug link only
    hosted_url = _publish_json(geojson_data, f"geojson:{mission_name}")
    if hosted_url:
        return hosted_url, True
    return get_static_url(f"{mission_name}.geojson"), False


def publish_style(mission_name: str, style_data: dict) -> tuple[str, bool]:
    write_style_to_static(mission_name, style_data)
    hosted_url = _publish_json(style_data, f"style:{mission_name}")
    if hosted_url:
        return hosted_url, True
    return get_static_url(f"{mission_name}.style.json"), False
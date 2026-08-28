"""
SpacePoint - GeoLibre data publishing
Author: Kommal

GeoLibre (https://web.geolibre.app) is a separate origin, so loading a
project via its `url=` parameter requires the browser to fetch() it
cross-origin, which needs Access-Control-Allow-Origin on the response.
Streamlit's own static file server has no documented guarantee of that for
a third-party fetch (see streamlit/streamlit#8808 - a Streamlit-hosted
static JSON fed into a third-party iframe app, unresolved). JSONBin.io
documents CORS enabled on every endpoint, so we publish there instead -
automatically, from Python, with no manual upload by the user.

One-time setup: a free JSONBin.io account and a Master Key, stored as a
secret (JSONBIN_MASTER_KEY). If it's missing, everything falls back to
Streamlit's own static folder so the app doesn't crash - but that fallback
is only reliable for opening the link yourself, not for GeoLibre.
"""

import streamlit as st
import requests

from geolibre_static import write_project_to_static, get_static_url

JSONBIN_BASE = "https://api.jsonbin.io/v3/b"


def _get_master_key() -> str | None:
    try:
        return st.secrets.get("JSONBIN_MASTER_KEY")
    except Exception:
        return None


def _publish_json(payload: dict, cache_key: str) -> str | None:
    api_key = _get_master_key()
    if not api_key:
        return None

    bin_ids = st.session_state.setdefault("jsonbin_ids", {})
    existing_id = bin_ids.get(cache_key)
    headers = {"Content-Type": "application/json", "X-Master-Key": api_key}

    try:
        if existing_id:
            resp = requests.put(f"{JSONBIN_BASE}/{existing_id}", json=payload, headers=headers, timeout=10)
        else:
            headers["X-Bin-Private"] = "false"
            resp = requests.post(JSONBIN_BASE, json=payload, headers=headers, timeout=10)

        if resp.status_code not in (200, 201):
            return None

        bin_id = resp.json()["metadata"]["id"]
        bin_ids[cache_key] = bin_id
        return f"{JSONBIN_BASE}/{bin_id}?meta=false"

    except Exception:
        return None


def publish_project(mission_name: str, project_data: dict) -> tuple[str, bool]:
    """Returns (url, is_cors_verified)."""
    write_project_to_static(mission_name, project_data)  # local copy, debug link only
    hosted_url = _publish_json(project_data, f"project:{mission_name}")
    if hosted_url:
        return hosted_url, True
    return get_static_url(f"{mission_name}.geolibre.json"), False
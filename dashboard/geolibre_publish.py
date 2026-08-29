"""
SpacePoint - GeoLibre data publishing
Author: Kommal

GeoLibre (https://web.geolibre.app) is a separate origin, so loading a
project via its `url=` parameter requires the browser to fetch() it
cross-origin, which needs Access-Control-Allow-Origin on the response.
Streamlit's own static file server has no documented guarantee of that
for a third-party fetch (see streamlit/streamlit#8808 - unresolved).
JSONBin.io documents CORS enabled on every endpoint, so we publish there
instead - automatically, from Python, no manual upload by the user.

One-time setup: a free JSONBin.io account and a Master Key, stored as a
secret (JSONBIN_MASTER_KEY). If publishing fails for any reason - missing
key, bad key, payload too large, network error - this falls back to
Streamlit's own static folder so the app doesn't crash, and surfaces the
real reason rather than a generic message, since a fallback with no
explanation is nearly impossible to debug.
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


def _publish_json(payload: dict, cache_key: str) -> tuple[str | None, str | None]:
    """Returns (url, error_message). Exactly one of these is None."""
    api_key = _get_master_key()
    if not api_key:
        return None, "No JSONBIN_MASTER_KEY is configured."

    bin_ids = st.session_state.setdefault("jsonbin_ids", {})
    existing_id = bin_ids.get(cache_key)
    headers = {"Content-Type": "application/json", "X-Master-Key": api_key}

    try:
        if existing_id:
            resp = requests.put(f"{JSONBIN_BASE}/{existing_id}", json=payload, headers=headers, timeout=10)
        else:
            headers["X-Bin-Private"] = "false"
            resp = requests.post(JSONBIN_BASE, json=payload, headers=headers, timeout=10)
    except Exception as exc:
        return None, f"Request to JSONBin failed: {exc}"

    if resp.status_code not in (200, 201):
        return None, f"JSONBin returned HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        bin_id = resp.json()["metadata"]["id"]
    except Exception as exc:
        return None, f"Unexpected JSONBin response shape ({exc}): {resp.text[:300]}"

    bin_ids[cache_key] = bin_id
    return f"{JSONBIN_BASE}/{bin_id}?meta=false", None


def publish_project(mission_name: str, project_data: dict) -> tuple[str, bool, str | None]:
    """Returns (url, is_cors_verified, error_message_if_any)."""
    write_project_to_static(mission_name, project_data)  # local copy, debug link only
    hosted_url, error = _publish_json(project_data, f"project:{mission_name}")
    if hosted_url:
        return hosted_url, True, None
    return get_static_url(f"{mission_name}.geolibre.json"), False, error
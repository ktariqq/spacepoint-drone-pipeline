"""
SpacePoint - GeoLibre data publishing
Author: Kommal

GeoLibre (https://web.geolibre.app) is a separate origin, so loading a
project via its `url=` parameter requires the browser to fetch() it
cross-origin, which needs Access-Control-Allow-Origin on the response.

Primary host: Supabase Storage, public bucket. Plain GET reads from a
public Supabase Storage bucket are served with Access-Control-Allow-
Origin: * by default - no CORS configuration needed - and the free tier
allows files up to 50MB, so a full mission's points/descriptions never
need to be trimmed to fit.

Fallback: JSONBin.io (100KB/record on the free tier - fine for small
missions, but why sample_mission needed thinning before this existed).

Last resort: Streamlit's own static folder, which is not confirmed to
work inside GeoLibre due to CORS - the UI says so when this happens.

One-time setup for Supabase: a free project, a public Storage bucket,
and the project URL + service_role key stored as secrets
(SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_BUCKET).
"""

import streamlit as st
import requests

from geolibre_static import write_project_to_static, get_static_url

JSONBIN_BASE = "https://api.jsonbin.io/v3/b"


def _get_secret(name: str) -> str | None:
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def _publish_to_supabase(payload: dict, path: str) -> tuple[str | None, str | None]:
    """Returns (public_url, error_message). Returns (None, None) if
    Supabase simply isn't configured, so the caller can fall through
    to JSONBin without treating that as an error."""
    supabase_url = _get_secret("SUPABASE_URL")
    service_key = _get_secret("SUPABASE_SERVICE_KEY")
    bucket = _get_secret("SUPABASE_BUCKET") or "geolibre-projects"

    if not supabase_url or not service_key:
        return None, None

    upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "x-upsert": "true",  # overwrite if this mission was already published
    }

    try:
        resp = requests.post(upload_url, headers=headers, json=payload, timeout=15)
    except Exception as exc:
        return None, f"Request to Supabase failed: {exc}"

    if resp.status_code not in (200, 201):
        return None, f"Supabase returned HTTP {resp.status_code}: {resp.text[:300]}"

    public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{path}"
    return public_url, None


def _get_master_key() -> str | None:
    return _get_secret("JSONBIN_MASTER_KEY")


def _publish_json(payload: dict, cache_key: str) -> tuple[str | None, str | None]:
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
    path = f"{mission_name}.geolibre.json"

    supabase_url, supabase_error = _publish_to_supabase(project_data, path)
    if supabase_url:
        return supabase_url, True, None

    hosted_url, jsonbin_error = _publish_json(project_data, f"project:{mission_name}")
    if hosted_url:
        return hosted_url, True, None

    error = supabase_error or jsonbin_error or (
        "Neither Supabase (SUPABASE_URL/SUPABASE_SERVICE_KEY) nor "
        "JSONBin (JSONBIN_MASTER_KEY) is configured."
    )
    return get_static_url(path), False, error
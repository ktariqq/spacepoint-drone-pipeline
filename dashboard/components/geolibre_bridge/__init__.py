"""
SpacePoint - GeoLibre live-sync bridge (Streamlit Component)
Author: Kommal

Wraps the GeoLibre iframe in a real bidirectional Streamlit Component
instead of a raw st.iframe(). This is the key architectural change:
st.iframe()/components.v1.html() re-emit a brand-new iframe element on
every Streamlit rerun (which is why toggling a checkbox previously
forced a full GeoLibre reload). A DECLARED component, by contrast, is
mounted ONCE and receives updated `args` via postMessage on every
rerun WITHOUT remounting its iframe - the frontend script below reacts
to those updated args itself.

Frontend behavior (frontend/index.html):
  1. On mount: build the nested GeoLibre iframe once (src = geolibreUrl).
  2. Try to `connect()` to GeoLibre's documented embed postMessage API
     (https://geolibre.app/user-guide/embedding/). If it accepts the
     handshake, subsequent layer-visibility changes call
     `setLayerVisibility(id, visible)` directly - zero reload, camera
     position preserved.
  3. If that handshake doesn't complete within a few seconds (GeoLibre's
     public instance hasn't allowlisted this origin via
     GEOLIBRE_EMBED_ORIGINS - which SpacePoint doesn't control, since
     web.geolibre.app is a third-party hosted instance), it falls back
     to reloading ONLY the nested iframe's src with a cache-busting
     param. That still never touches the outer Streamlit page, so no
     browser/page refresh and no loss of sidebar/session state - only
     the map's own camera position resets on that fallback path.
"""

from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).parent / "frontend"

_geolibre_bridge = components.declare_component(
    "geolibre_bridge",
    path=str(_COMPONENT_DIR),
)


def geolibre_bridge(geolibre_url: str, layer_visibility: dict, structural_version: str, height: int = 760, key: str | None = None):
    """
    geolibre_url: the published .geolibre.json project's viewer URL.
    layer_visibility: {layer_id: bool} for every layer currently in the
        published project. Diffed client-side against the last-applied
        state; only CHANGED ids get a setLayerVisibility() call.
    structural_version: any string that changes only when the
        underlying project actually needs to be re-fetched (mission
        switch, color-by/interpolate-by sensor change). Unchanged
        structural_version + changed layer_visibility = live update.
        Changed structural_version = soft nested-iframe reload.
    """
    return _geolibre_bridge(
        geolibreUrl=geolibre_url,
        layerVisibility=layer_visibility,
        structuralVersion=structural_version,
        height=height,
        key=key,
        default=None,
    )
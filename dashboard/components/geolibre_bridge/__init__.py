"""
SpacePoint - GeoLibre live-sync bridge (Streamlit Component)
Author: Kommal

Wraps the GeoLibre iframe in a real bidirectional Streamlit Component
instead of a raw st.iframe() - a declared component mounts ONCE and
receives updated args via postMessage on rerun WITHOUT remounting its
iframe, so unrelated Streamlit reruns don't visibly reload the map.

SIMPLIFIED (this revision): there is no more per-layer visibility
diffing. All layer show/hide now happens inside GeoLibre's own Layers
panel (layout=compact), not from external Streamlit checkboxes, so the
only thing this bridge needs to react to is `structural_version`
changing (a different mission/sensor was picked) - in which case it
soft-reloads the nested iframe, cache-busted so a stale cached GeoLibre
build can't linger for the session (see frontend/index.html).
"""

from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).parent / "frontend"

_geolibre_bridge = components.declare_component(
    "geolibre_bridge",
    path=str(_COMPONENT_DIR),
)


def geolibre_bridge(geolibre_url: str, structural_version: str, height: int = 820, key: str | None = None):
    """
    geolibre_url: the published .geolibre.json project's viewer URL.
    structural_version: any string that changes only when the
        underlying project actually needs to be re-fetched (mission
        switch, color-by/interpolate-by sensor change). Unchanged =
        no reload, even across unrelated Streamlit reruns.
    """
    return _geolibre_bridge(
        geolibreUrl=geolibre_url,
        structuralVersion=structural_version,
        height=height,
        key=key,
        default=None,
    )
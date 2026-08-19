"""
SpacePoint - GPS-Based Mapping Tool
Author: Kommal

Map data (GeoJSON + mission summary) is embedded directly into the
page as JavaScript variables instead of being fetched over HTTP, so
no separate local web server is needed to view it.
"""

import json
import sys
from pathlib import Path

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

sys.path.append(str(Path(__file__).resolve().parent.parent))

from heat_interpolation import compute_idw_grid, render_heat_overlay_png
from branding import (
    apply_page_config,
    render_header,
    render_sidebar_logo,
    render_sidebar_status,
    apply_custom_css,
    render_status_bar,
    render_section_header,
    render_technical_metadata,
    TOKENS,
    DATA_RAMP,
)

GEO_DIR = Path("data/geo")
CLEANED_DIR = Path("data/cleaned")

apply_page_config("Mission Map")
render_sidebar_logo()
apply_custom_css()
render_header("Mission Map")

missions = sorted(p.stem for p in GEO_DIR.glob("*.geojson"))

if not missions:
    st.warning("No GeoJSON files found. Run the Data Cleaning page on a mission first.")
    st.stop()

selected_mission = st.selectbox("Mission", missions)

geojson_path = GEO_DIR / f"{selected_mission}.geojson"
summary_path = CLEANED_DIR / f"{selected_mission}_summary.json"

with open(geojson_path) as f:
    geojson_data = json.load(f)

summary = None
if summary_path.exists():
    with open(summary_path) as f:
        summary = json.load(f)

view_mode = st.radio("View", ["Points", "Heat Surface (IDW)"], horizontal=True)

heat_overlay_uri = None
heat_bounds = None

if view_mode == "Heat Surface (IDW)":
    heat_sensor = st.selectbox(
        "Interpolate", ["temperature", "humidity", "pressure", "light", "air_quality"], index=0
    )

    points = np.array([
        [f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]]
        for f in geojson_data["features"]
    ])
    values = np.array([f["properties"][heat_sensor] for f in geojson_data["features"]])
    valid = ~np.isnan(values)
    points, values = points[valid], values[valid]

    bounds = (points[:, 0].min(), points[:, 0].max(), points[:, 1].min(), points[:, 1].max())
    grid = compute_idw_grid(points, values, bounds)
    heat_overlay_uri = render_heat_overlay_png(grid)
    heat_bounds = bounds
    heat_min, heat_max = float(grid.min()), float(grid.max())

# Bounding box computed from this mission's own GPS track
all_coords = np.array([f["geometry"]["coordinates"] for f in geojson_data["features"]])
lon_min, lon_max = all_coords[:, 0].min(), all_coords[:, 0].max()
lat_min, lat_max = all_coords[:, 1].min(), all_coords[:, 1].max()

render_technical_metadata(
    {
        "MISSION": selected_mission,
        "LAT RANGE": f"{lat_min:.4f}\u00b0 to {lat_max:.4f}\u00b0",
        "LON RANGE": f"{lon_min:.4f}\u00b0 to {lon_max:.4f}\u00b0",
        "SOURCE": "ONBOARD GPS + ENVIRONMENTAL TELEMETRY",
        "SAMPLES": len(geojson_data["features"]),
    },
    columns=2,
)

if summary:
    render_section_header("Mission Summary")
    duration_minutes = (summary["duration_seconds"] or 0) / 60
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Mission", summary["mission_name"])
    col2.metric("Samples", summary["sample_count"])
    col3.metric("Duration", f"{duration_minutes:.1f} min")
    col4.metric("Flagged rows", summary["flagged_row_count"])

render_section_header("Flight Path & Sensor Readings" if view_mode == "Points" else "Interpolated Sensor Surface")

geojson_json = json.dumps(geojson_data)

controls_html = f"""
<div class="controls">
  <label>Color by:
    <select id="sensor-select">
      <option value="temperature">Temperature</option>
      <option value="humidity">Humidity</option>
      <option value="pressure">Pressure</option>
      <option value="light">Light</option>
      <option value="air_quality" selected>Air Quality</option>
    </select>
  </label>
  <label><input type="checkbox" id="route-toggle" checked> Show flight path</label>
  <div class="legend-row">
    <span id="legend-min"></span>
    <div class="legend-bar"></div>
    <span id="legend-max"></span>
  </div>
</div>
""" if view_mode == "Points" else f"""
<div class="controls">
  <div class="legend-row">
    <span>{heat_sensor} — low: {heat_min:.1f}</span>
    <div class="legend-bar"></div>
    <span>high: {heat_max:.1f}</span>
  </div>
</div>
"""

draw_call = (
    "drawMarkers(document.getElementById('sensor-select').value); drawRoute();"
    if view_mode == "Points"
    else f"L.imageOverlay('{heat_overlay_uri}', [[{heat_bounds[0]}, {heat_bounds[2]}], [{heat_bounds[1]}, {heat_bounds[3]}]], {{opacity: 0.75}}).addTo(map);"
)

RAMP_LOW, RAMP_MID, RAMP_HIGH = DATA_RAMP
PANEL = TOKENS["panel"]
BORDER = TOKENS["border_strong"]
TEXT = TOKENS["text_secondary"]
ACCENT = TOKENS["accent"]
FONT_SANS = TOKENS["font_sans"]

map_html = f"""
<style>
  #map {{ height: 600px; border-radius: 4px; border: 1px solid {BORDER}; }}
  body {{ font-family: {FONT_SANS}; color: {TEXT}; margin: 0; }}
  .controls {{ display: flex; gap: 20px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }}
  .controls label {{ font-size: 13px; }}
  select {{ padding: 5px 8px; background-color: {PANEL}; color: #E8EAF0; border: 1px solid {BORDER}; border-radius: 4px; font-size: 12px; }}
  .legend-bar {{ height: 8px; width: 140px; border-radius: 3px; background: linear-gradient(to right, {RAMP_LOW}, {RAMP_MID}, {RAMP_HIGH}); }}
  .legend-row {{ display: flex; align-items: center; gap: 8px; font-size: 11px; color: {TEXT}; }}
</style>

{controls_html}

<div id="map"></div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const geojsonData = {geojson_json};

  const COLOR_LOW = {list(int(RAMP_LOW.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))};
  const COLOR_MID = {list(int(RAMP_MID.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))};
  const COLOR_HIGH = {list(int(RAMP_HIGH.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))};

  let markerLayer = null;
  let routeLayer = null;

  const map = L.map("map").setView([0, 0], 15);
  L.tileLayer("https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png", {{
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    maxZoom: 19,
  }}).addTo(map);

  function mixColor(a, b, amount) {{
    const r = Math.round(a[0] + (b[0] - a[0]) * amount);
    const g = Math.round(a[1] + (b[1] - a[1]) * amount);
    const b2 = Math.round(a[2] + (b[2] - a[2]) * amount);
    return `rgb(${{r}}, ${{g}}, ${{b2}})`;
  }}

  function getColorForValue(value, min, max) {{
    if (value === null || value === undefined || max === min) return "rgb(124,129,148)";
    const ratio = (value - min) / (max - min);
    return ratio < 0.5
      ? mixColor(COLOR_LOW, COLOR_MID, ratio / 0.5)
      : mixColor(COLOR_MID, COLOR_HIGH, (ratio - 0.5) / 0.5);
  }}

  function getMinMax(sensorName) {{
    const values = geojsonData.features.map(f => f.properties[sensorName]).filter(v => v !== null && v !== undefined);
    return {{ min: Math.min(...values), max: Math.max(...values) }};
  }}

  function drawMarkers(sensorName) {{
    if (markerLayer) map.removeLayer(markerLayer);
    const {{ min, max }} = getMinMax(sensorName);
    document.getElementById("legend-min").textContent = min.toFixed(1);
    document.getElementById("legend-max").textContent = max.toFixed(1);

    markerLayer = L.geoJSON(geojsonData, {{
      pointToLayer: function (feature, latlng) {{
        const value = feature.properties[sensorName];
        const color = getColorForValue(value, min, max);
        const isFlagged = feature.properties.has_flag;
        return L.circleMarker(latlng, {{
          radius: isFlagged ? 8 : 6,
          fillColor: color,
          fillOpacity: 0.9,
          color: isFlagged ? "#E8EAF0" : color,
          weight: isFlagged ? 2 : 1,
          dashArray: isFlagged ? "3,3" : null,
        }});
      }},
      onEachFeature: function (feature, layer) {{
        const p = feature.properties;
        layer.bindPopup(
          `<b>${{new Date(p.timestamp).toLocaleString()}}</b><br>` +
          `Temperature: ${{p.temperature ?? "-"}} &deg;C<br>` +
          `Humidity: ${{p.humidity ?? "-"}} %<br>` +
          `Air Quality: ${{p.air_quality ?? "-"}}` +
          (p.surface_type ? `<br>Surface: ${{p.surface_type}}` : "") +
          (p.has_flag ? `<br><b style="color:{TOKENS['danger']};">Flagged: ${{p.flags_summary}}</b>` : "")
        );
      }},
    }}).addTo(map);
  }}

  function drawRoute() {{
    const coords = geojsonData.features.map(f => [f.geometry.coordinates[1], f.geometry.coordinates[0]]);
    routeLayer = L.polyline(coords, {{ color: "{ACCENT}", weight: 2, opacity: 0.6 }}).addTo(map);
  }}

  const bounds = L.geoJSON(geojsonData).getBounds();
  map.fitBounds(bounds, {{ padding: [30, 30] }});

  {draw_call}

  const sensorSelect = document.getElementById("sensor-select");
  if (sensorSelect) sensorSelect.addEventListener("change", e => drawMarkers(e.target.value));

  const routeToggle = document.getElementById("route-toggle");
  if (routeToggle) routeToggle.addEventListener("change", e => {{
    if (e.target.checked) drawRoute();
    else if (routeLayer) map.removeLayer(routeLayer);
  }});
</script>
"""

components.html(map_html, height=680, scrolling=False)

render_sidebar_status()
<div align="center">

<img src="assets/spacepoint_logo.png" width="200">

# SpacePoint — Drone Remote Sensing & GIS Intelligence Pipeline

**An end-to-end environmental monitoring platform that takes raw drone sensor logs from a CSV to a published GIS workspace and a self-contained mission report — all inside one Streamlit application.**

![Python](https://img.shields.io/badge/Python-3.10+-a855f7?style=flat-square&labelColor=231134&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.29+-8b5cf6?style=flat-square&labelColor=231134&logo=streamlit&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer_Vision-7c3aed?style=flat-square&labelColor=231134&logo=opencv&logoColor=white)
![GeoLibre](https://img.shields.io/badge/GeoLibre-GIS_Workspace-653F84?style=flat-square&labelColor=231134)
![Leaflet](https://img.shields.io/badge/Leaflet.js-Mapping-653F84?style=flat-square&labelColor=231134&logo=leaflet&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_API-AI_Drafting-6d28d9?style=flat-square&labelColor=231134)
![Status](https://img.shields.io/badge/Status-Active-6d28d9?style=flat-square&labelColor=231134)

**[Live Application](https://spacepoint-drone-pipeline.streamlit.app/) · [Repository](https://github.com/ktariqq/spacepoint-drone-pipeline)**

━━━━━━━━━━━━━━━━━━━━ ✦ ━━━━━━━━━━━━━━━━━━━━

</div>

<br/>

## 🛰️ Overview

SpacePoint is a drone environmental monitoring pipeline built as a single Streamlit application. It ingests raw sensor logs from a drone-mounted payload — temperature, humidity, pressure, light, air quality, and GPS — and carries them through diagnostics, cleaning, dashboarding, GIS visualization, computer-vision imagery analysis, and automated report generation, without requiring a single script to be run outside the browser.

The pipeline is schema-agnostic: it does not assume a fixed set of sensor names or column order. A lightweight column-detection layer identifies the timestamp, latitude/longitude, and numeric sensor columns from whatever CSV is uploaded, so the same application works on the original sensor-logger format or on an entirely different drone payload without code changes.

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ What Makes This Project Interesting

- **Schema-agnostic ingestion.** Every page — cleaning, dashboarding, mapping, reporting — reads columns from an auto-detected schema rather than hardcoded names, so the tool generalizes to arbitrary sensor CSVs.
- **A real GIS integration, not a toy map.** Mission data is published as a [GeoLibre](https://web.geolibre.app) project (`.geolibre.json`), rendered in an embedded, cross-origin GIS workspace with satellite reference imagery, basemap switching, and per-point styling — not a static Folium/Leaflet embed.
- **Resilient hosting fallback chain.** Publishing a project for cross-origin loading requires a CORS-enabled host. The app tries Supabase Storage first, falls back to JSONBin.io, and finally to Streamlit's own static file serving, automatically thinning point density only in the hosted copy if a mission is too large for the free-tier host — the underlying dataset is never touched.
- **A genuine computer-vision pipeline.** Vegetation and bright-surface detection use the Excess Green Index and a brightness index thresholded with Otsu's method on a fixed physical scale (not each image's own min/max), combined with K-means land-cover clustering labeled by HSV color rules.
- **IDW heat-surface interpolation.** Sensor readings are interpolated onto a spatial grid using inverse-distance weighting restricted to each cell's nearest neighbors, so local structure (e.g. asphalt vs. grass in an urban heat-island study) stays visible instead of blurring into a single mission-wide average.
- **AI-assisted, human-edited reporting.** Objective/observations/limitations/conclusion sections can be drafted by the Gemini API from a prompt built strictly from that mission's own statistics, but every section is an editable text box — nothing is written into the final report without being reviewed first.

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ Application Pages

### 🟣 1 · Data Quality & Calibration
Read-only diagnostic pass over a raw mission file before anything is modified.
- Missing-value counts per sensor and per GPS field
- Out-of-range detection against physically defined sensor bounds
- GPS loss and duplicate-timestamp counts
- Sudden-jump detection between consecutive readings, using a threshold scaled to each sensor's own standard deviation rather than a fixed unit
- Sensor drift check comparing early-mission vs. late-mission averages, with short missions (fewer than 40 samples) reported as too short to check rather than given a misleading result

### 🟣 2 · Data Cleaning
Runs the full cleaning pipeline from inside the app — no command line required.
- Drops fully empty rows and duplicate timestamps
- Nulls physically impossible readings, then time-interpolates gaps of five samples or fewer; longer gaps are left as missing and flagged rather than guessed
- Flags statistical anomalies (z-score threshold) and flatlined/stuck sensors (long runs of a repeated value)
- Writes the cleaned CSV, a summary JSON, per-sensor plot data, static PNG plots, and a GeoJSON file for the mapping tool, in a single run

### 🟣 3 · Mission Dashboard
- Mission summary (date, location, duration) computed from the cleaned data
- Live sensor averages and time-series charts, generated dynamically for whatever sensor columns were detected
- Automatic warnings (high temperature against an adjustable threshold, GPS loss, flatlined sensors, statistical anomalies)
- Filterable data table with CSV export

### 🟣 4 · GIS Mission Map
- A GeoLibre project is built and published on demand, then rendered in an embedded, cross-origin GIS workspace with a dark basemap (or one of several OpenFreeMap styles)
- **Heat Surface (IDW) view** — inverse-distance-weighted interpolation of any numeric sensor field, restricted to nearest neighbors, rendered as a transparent PNG overlay aligned to the mission's spatial bounds
- Optional Esri World Imagery satellite reference layer
- Per-point coloring and click-to-inspect labels via GeoLibre's simplestyle-spec styling
- A built-in heat-island sample dataset (asphalt, building, open, grass, shaded surface types with realistic midday temperature offsets) for demonstrating urban heat effects without needing real flight data

### 🟣 5 · Drone Image Processing
- Excess Green Index (vegetation) and a brightness index (bright/hot surfaces), each thresholded with Otsu's method on a fixed physical scale so results are comparable across images
- K-means land-cover clustering, with clusters labeled by color (vegetation, water, bare soil, asphalt, shadow, bright surface) using HSV rules rather than raw RGB
- Annotated overlays, side-by-side comparison between two images, and vegetation-coverage statistics
- Results can be saved and attached to a mission's generated report

### 🟣 6 · Mission Report Generator
- Builds the polished, downloadable HTML report directly from the mission's own data — no separate authoring step
- Charts, the flight-path plot, and any saved image analysis are embedded as base64, so the report is fully self-contained and works even after being downloaded and opened elsewhere
- Objective, observations, limitations, and conclusion can optionally be AI-drafted from a prompt grounded strictly in that mission's statistics (Gemini API); drafts are clearly labeled and remain editable before being included in the final export

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ Tech Stack

| Layer | Tools |
|---|---|
| Application framework | Streamlit (multipage app, session state, native caching) |
| Data processing | pandas, NumPy |
| Computer vision | OpenCV (ExG, Otsu thresholding, K-means clustering), Pillow |
| GIS / mapping | GeoLibre, Leaflet.js, GeoJSON, OpenFreeMap, Esri World Imagery |
| Spatial interpolation | Custom IDW implementation (NumPy), Matplotlib for overlay rendering |
| Cloud storage (map hosting) | Supabase Storage (primary), JSONBin.io (fallback), Streamlit static serving (last resort) |
| Reporting | Jinja2 (HTML templating), base64 asset embedding |
| AI-assisted drafting | Google Gemini API (optional, key-gated) |
| Charting | Matplotlib, Streamlit native charts |

<br/>

## 🛰️ Project Structure
```
dashboard/
├── Dashboard.py                 # Mission dashboard entry point
├── branding.py                  # Design tokens, custom mission-console theming
├── heat_interpolation.py        # IDW grid computation + overlay rendering
├── image_processing.py          # CV pipeline (ExG, brightness, K-means land cover)
├── geolibre_project.py          # GeoLibre .geolibre.json project builder
├── geolibre_publish.py          # Supabase → JSONBin → static hosting fallback chain
├── geolibre_static.py           # Local static serving + GeoJSON validation
├── pages/
│   ├── 1_Data_Quality.py
│   ├── 2_Data_Cleaning.py
│   ├── 3_Mission_Map.py
│   ├── 4_Image_Tool.py
│   └── 5_Report_Generator.py
└── static/
    └── geo/                     # Static GeoJSON fallback assets

scripts/
├── column_detection.py          # Schema-agnostic column detection
├── clean_mission_data.py        # Cleaning engine
├── quality_check.py             # Read-only diagnostic engine
├── generate_geojson.py          # Cleaned CSV → GeoJSON
├── generate_report.py           # Jinja2 report rendering + Gemini drafting
├── generate_sample_data.py      # Synthetic mission generator (with injected defects)
├── heat_island_sample.py        # Heat-island demo dataset generator
└── report_template.html

data/
├── raw/
├── cleaned/
├── geo/
├── images/
└── image_analysis/

.streamlit/
├── config.toml
└── secrets.toml                 # Not committed — see Configuration

requirements.txt
```

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ Getting Started

### Prerequisites
- Python 3.10+

### 1 — Clone the repository
```bash
git clone https://github.com/ktariqq/spacepoint-drone-pipeline.git
cd spacepoint-drone-pipeline
```

### 2 — Install dependencies
```bash
pip install -r requirements.txt
```

### 3 — (Optional) Generate sample mission data
The repository does not need any external data to run. Two generator scripts produce realistic sample missions locally:
```bash
python scripts/generate_sample_data.py     # sample_mission.csv, with injected data-quality issues
python scripts/heat_island_sample.py       # heat_island_sample.csv, for the heat-mapping demo
```

### 4 — Run the app
```bash
streamlit run dashboard/Dashboard.py
```
The app opens at `http://localhost:8501`. Use the sidebar to move between pages.

<br/>

## 🛰️ Using the App

The pages are ordered to match the pipeline:

1. **Data Quality** — pick or upload a raw mission CSV and review its diagnostic report.
2. **Data Cleaning** — run the cleaning pipeline on that file; this writes the cleaned CSV, summary, and map data.
3. **Mission Dashboard** — explore the cleaned mission's readings, charts, and warnings.
4. **Mission Map** — view sensor readings by location in the embedded GeoLibre workspace, including the heat-surface interpolation view.
5. **Image Tool** — upload drone imagery for vegetation and land-cover analysis; optionally attach results to a mission.
6. **Report Generator** — generate a complete, downloadable mission report.

Both the Data Quality and Data Cleaning pages accept a file already in `data/raw/`, or a fresh CSV upload — no manual file placement required.

<br/>

## 🛰️ Configuration

All of the following are optional. The app runs fully without any of them — features degrade gracefully rather than failing.

**AI-drafted report sections** require a Gemini API key.
```toml
# .streamlit/secrets.toml
GEMINI_API_KEY = "your-key-here"
```

**GeoLibre map publishing** prefers Supabase Storage (public bucket, 50 MB/file on the free tier — a full mission's points never need thinning):
```toml
SUPABASE_URL = "your-project-url"
SUPABASE_SERVICE_KEY = "your-service-role-key"
SUPABASE_BUCKET = "geolibre-projects"
```
If Supabase isn't configured, the app falls back to JSONBin.io (100 KB/record on the free tier — automatically thinned point-by-point if a mission exceeds this):
```toml
JSONBIN_MASTER_KEY = "your-key-here"
```
If neither is configured, the app falls back to Streamlit's own static file serving, with a clear in-app note that this path isn't guaranteed to work inside GeoLibre due to CORS.

**Streamlit Community Cloud** — set the above under your app's **Settings → Secrets** instead of a local `secrets.toml`.

<br/>

## 🛰️ Deployment

The live version is deployed on **Streamlit Community Cloud**, pointed at `dashboard/Dashboard.py` as the entry point.

To deploy your own copy: fork the repository, connect it in [Streamlit Community Cloud](https://streamlit.io/cloud), set `dashboard/Dashboard.py` as the main file, and add any of the secrets above under **Settings → Secrets** as needed.



<br/>
<br/>

<div align="center">

━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━

Built by **Kommal Tariq**

Copyright © 2026 SpacePoint. All rights reserved.

</div>


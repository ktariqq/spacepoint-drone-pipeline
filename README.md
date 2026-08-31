<div align="center">

<img src="assets/spacepoint_logo.png" width="200">

# SpacePoint — Drone Remote Sensing & GIS Intelligence Pipeline

**An end-to-end environmental monitoring platform that takes raw drone sensor logs from a CSV to a published GIS workspace and a self-contained mission report — all inside one Streamlit application.**

![Python](https://img.shields.io/badge/Python-3.10+-a855f7?style=flat-square&labelColor=231134&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.38+-8b5cf6?style=flat-square&labelColor=231134&logo=streamlit&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer_Vision-7c3aed?style=flat-square&labelColor=231134&logo=opencv&logoColor=white)
![GeoLibre](https://img.shields.io/badge/GeoLibre-GIS_Workspace-653F84?style=flat-square&labelColor=231134)
![Leaflet](https://img.shields.io/badge/Leaflet.js-Mapping-653F84?style=flat-square&labelColor=231134&logo=leaflet&logoColor=white)
![Component](https://img.shields.io/badge/Custom-Streamlit_Component-6d28d9?style=flat-square&labelColor=231134)
![Gemini](https://img.shields.io/badge/Gemini_API-AI_Drafting-6d28d9?style=flat-square&labelColor=231134)
![Status](https://img.shields.io/badge/Status-Active-6d28d9?style=flat-square&labelColor=231134)

**[Live Application](https://spacepoint-drone-pipeline.streamlit.app/) · [Repository](https://github.com/ktariqq/spacepoint-drone-pipeline)**

━━━━━━━━━━━━━━━━━━━━ ✦ ━━━━━━━━━━━━━━━━━━━━

</div>

<br/>

## 🛰️ Overview

This is a drone environmental monitoring pipeline built as a single Streamlit application. It ingests raw sensor logs from a drone-mounted payload — temperature, humidity, pressure, light, air quality, and GPS — and carries them through diagnostics, cleaning, dashboarding, GIS visualization, computer-vision imagery analysis, and automated report generation, without requiring a single script to be run outside the browser.

The pipeline is schema-agnostic: it does not assume a fixed set of sensor names or column order. A lightweight column-detection layer identifies the timestamp, latitude/longitude, and numeric sensor columns from whatever CSV is uploaded, so the same application works on the original sensor-logger format or on an entirely different drone payload without code changes.

The app's sidebar is organized into two groups that mirror how the tool is actually used: a **Mission Pipeline** (the sequential steps every mission passes through) and a set of **Specialized Tools** (the GIS workspace and image analyzer, which can be used independently at any point).

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ What Makes This Project Interesting

- **Schema-agnostic ingestion.** Every page — cleaning, dashboarding, mapping, reporting — reads columns from an auto-detected schema rather than hardcoded names, so the tool generalizes to arbitrary sensor CSVs.
- **A real GIS integration, not a toy map.** Mission data is published as a [GeoLibre](https://web.geolibre.app) project (`.geolibre.json`), rendered in an embedded, cross-origin GIS workspace with basemap switching and per-point styling — not a static Folium/Leaflet embed.
- **A curated multi-source imagery catalog.** Esri World Imagery is preloaded as the default satellite reference, alongside an EOX Sentinel-2 cloudless global mosaic and NASA GIBS MODIS true-color and aerosol-optical-depth layers — all public, keyless, and verified directly against each provider's own documented tile parameters rather than guessed at.
- **Resilient hosting fallback chain.** Publishing a project for cross-origin loading requires a CORS-enabled host. The app tries Supabase Storage first, falls back to JSONBin.io, and finally to Streamlit's own static file serving, automatically thinning point density only in the hosted copy if a mission is too large for the free-tier host — the underlying dataset is never touched.
- **A genuine GeoJSON heat surface, not a flat image.** Sensor readings are interpolated with k-nearest-neighbor inverse-distance weighting (with a local equirectangular correction for accurate ground distance) and converted into real, georeferenced filled-contour polygons — a first-class GeoLibre layer that can be toggled, reordered, and re-styled like any other, rather than a static raster overlay.
- **A flicker-free live map.** A custom, bidirectional Streamlit Component wraps the GeoLibre iframe so it mounts once and only reloads when the mission or interpolated sensor actually changes — unrelated Streamlit reruns elsewhere on the page never visibly reload the map.
- **A genuine computer-vision pipeline.** Vegetation and bright-surface detection use the Excess Green Index and a brightness index thresholded with Otsu's method on a fixed physical scale (not each image's own min/max), combined with K-means land-cover clustering labeled by HSV color rules.
- **AI-assisted, human-edited reporting.** Objective/observations/limitations/conclusion sections can be drafted by the Gemini API from a prompt built strictly from that mission's own statistics, but every section is an editable text box — nothing is written into the final report without being reviewed first.

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ Application Pages

### 🟣 Mission Pipeline

The sequential steps a mission moves through, from raw file to final report.

**1 · Quality Check**
Read-only diagnostic pass over a raw mission file before anything is modified.
- Missing-value counts per sensor and per GPS field
- Out-of-range detection against physically defined sensor bounds
- GPS loss and duplicate-timestamp counts
- Sudden-jump detection between consecutive readings, using a threshold scaled to each sensor's own standard deviation rather than a fixed unit
- Sensor drift check comparing early-mission vs. late-mission averages, with short missions (fewer than 40 samples) reported as too short to check rather than given a misleading result

**2 · Data Cleaning**
Runs the full cleaning pipeline from inside the app — no command line required.
- Drops fully empty rows and duplicate timestamps
- Nulls physically impossible readings, then time-interpolates gaps of five samples or fewer; longer gaps are left as missing and flagged rather than guessed
- Flags statistical anomalies (z-score threshold) and flatlined/stuck sensors (long runs of a repeated value)
- Writes the cleaned CSV, a summary JSON, per-sensor plot data, static PNG plots, and a GeoJSON file for the mapping tool, in a single run

**3 · Mission Dashboard**
- Mission summary (date, location, duration) computed from the cleaned data
- Live sensor averages and time-series charts, generated dynamically for whatever sensor columns were detected
- Automatic warnings (high temperature against an adjustable threshold, GPS loss, flatlined sensors, statistical anomalies)
- Filterable data table with CSV export

**4 · Mission Report**
- Builds the polished, downloadable HTML/PDF report directly from the mission's own data — no separate authoring step
- Charts, the flight-path plot, and any saved image analysis are embedded as base64, so the report is fully self-contained and works even after being downloaded and opened elsewhere
- Objective, observations, limitations, and conclusion can optionally be AI-drafted from a prompt grounded strictly in that mission's statistics (Gemini API); drafts are clearly labeled and remain editable before being included in the final export

### 🟣 Specialized Tools

Drop-in tools that can be used independently of where a mission is in the pipeline.

**5 · Mission Map**
- Opens by default as a general GIS workspace with global satellite imagery preloaded — a mission is optional, not required
- A GeoLibre project is built and published on demand, then rendered in an embedded, cross-origin GIS workspace with a dark basemap (or one of several OpenFreeMap styles)
- Multi-source reference imagery: Esri World Imagery (default), EOX Sentinel-2 cloudless, and NASA GIBS MODIS true-color and aerosol-optical-depth layers, all toggled inside GeoLibre's own compact Layers panel
- **Heat Surface (IDW) view** — inverse-distance-weighted interpolation of any numeric sensor field, restricted to nearest neighbors with a local equirectangular distance correction, rendered as genuine filled-contour GeoJSON polygons rather than a flat image
- Per-point coloring and click-to-inspect labels via GeoLibre's simplestyle-spec styling
- A custom live-sync bridge component keeps the embedded map from reloading on unrelated Streamlit reruns
- A built-in heat-island sample dataset (asphalt, building, open, grass, shaded surface types with realistic midday temperature offsets) for demonstrating urban heat effects without needing real flight data

**6 · Image Analysis**
- Excess Green Index (vegetation) and a brightness index (bright/hot surfaces), each denoised, thresholded with Otsu's method on a fixed physical scale so results are comparable across images
- K-means land-cover clustering, with clusters labeled by color (vegetation, water, bare soil, asphalt, shadow, bright surface) using HSV rules rather than raw RGB
- Annotated overlays, side-by-side comparison between two images, and vegetation-coverage statistics
- Results can be saved and attached to a mission's generated report

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ Tech Stack

| Layer | Tools |
|---|---|
| Application framework | Streamlit (`st.navigation` grouped multipage app, session state, native caching) |
| Data processing | pandas, NumPy |
| Computer vision | OpenCV (ExG, Otsu thresholding, K-means clustering), Pillow |
| GIS / mapping | GeoLibre, Leaflet.js, GeoJSON, OpenFreeMap, Esri World Imagery, EOX Sentinel-2 cloudless, NASA GIBS |
| Live map sync | Custom bidirectional Streamlit Component (declared component + postMessage bridge) |
| Spatial interpolation | Custom k-NN IDW implementation (NumPy) with local equirectangular correction, Matplotlib contour extraction |
| Cloud storage (map hosting) | Supabase Storage (primary), JSONBin.io (fallback), Streamlit static serving (last resort) |
| Reporting | Jinja2 (HTML templating), xhtml2pdf, base64 asset embedding |
| AI-assisted drafting | Google Gemini API (optional, key-gated) |
| Charting | Matplotlib, Streamlit native charts |

<br/>

## 🛰️ Project Structure
```
dashboard/
├── Dashboard.py # Navigation router - defines sidebar sections, page order, and icons
├── branding.py # Design tokens, mission-console theming, shared app header
├── heat_interpolation.py # IDW grid computation + GeoJSON filled-contour band generation
├── image_processing.py # CV pipeline (ExG, brightness, K-means land cover)
├── geolibre_project.py # GeoLibre .geolibre.json project builder + imagery layer catalog
├── geolibre_publish.py # Supabase → JSONBin → static hosting fallback chain
├── geolibre_static.py # Local static serving + GeoJSON validation
├── components/
│ └── geolibre_bridge/ # Custom bidirectional Streamlit Component wrapping the GeoLibre iframe
├── pages/
│ ├── 0_Mission_Dashboard.py # "Mission Dashboard"
│ ├── 1_Data_Quality.py # "Quality Check"
│ ├── 2_Data_Cleaning.py # "Data Cleaning"
│ ├── 3_Mission_Map.py # "Mission Map"
│ ├── 4_Image_Tool.py # "Image Analysis"
│ └── 5_Report_Generator.py # "Mission Report"
└── static/
└── geo/ # Static GeoJSON fallback assets

scripts/
├── column_detection.py # Schema-agnostic column detection
├── clean_mission_data.py # Cleaning engine
├── quality_check.py # Read-only diagnostic engine
├── generate_geojson.py # Cleaned CSV → GeoJSON
├── generate_report.py # Jinja2 report rendering + Gemini drafting
├── generate_pdf.py # HTML → PDF conversion
├── generate_sample_data.py # Synthetic mission generator (with injected defects)
├── heat_island_sample.py # Heat-island demo dataset generator
└── report_template.html

data/
├── raw/
├── cleaned/
├── geo/
├── images/
└── image_analysis/

.streamlit/
├── config.toml
└── secrets.toml # Not committed — see Configuration

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
The app opens at `http://localhost:8501`. The sidebar is grouped into **Mission Pipeline** and **Specialized Tools** — use it to move between pages.

<br/>

## 🛰️ Using the App

The **Mission Pipeline** pages are ordered to match the natural workflow:

1. **Quality Check** — pick or upload a raw mission CSV and review its diagnostic report.
2. **Data Cleaning** — run the cleaning pipeline on that file; this writes the cleaned CSV, summary, and map data.
3. **Mission Dashboard** — explore the cleaned mission's readings, charts, and warnings.
4. **Mission Report** — generate a complete, downloadable mission report.

The **Specialized Tools** can be used at any point once a mission has been cleaned (or, for the map, even without one):

5. **Mission Map** — opens as a general GIS workspace with satellite imagery preloaded; optionally layer on a mission's points, flight path, and heat-surface interpolation.
6. **Image Analysis** — upload drone imagery for vegetation and land-cover analysis; optionally attach results to a mission's report.

Both the Quality Check and Data Cleaning pages accept a file already in `data/raw/`, or a fresh CSV upload — no manual file placement required.

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

**Mission Map debug details** (project/GeoLibre URLs, CORS fallback status) can be shown with:
```toml
SPACEPOINT_DEBUG_MAP = true
```

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

<div align="center">

<img src="assets/spacepoint_logo.png" width="200">

# SpacePoint Drone Remote Sensing Pipeline

**A full drone-based environmental monitoring pipeline — from raw sensor CSVs to mission reports — built entirely as one Streamlit application.**

![Python](https://img.shields.io/badge/Python-3.10+-a855f7?style=flat-square&labelColor=231134&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.29+-8b5cf6?style=flat-square&labelColor=231134&logo=streamlit&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Image_Analysis-7c3aed?style=flat-square&labelColor=231134&logo=opencv&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet.js-Mapping-653F84?style=flat-square&labelColor=231134&logo=leaflet&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active-6d28d9?style=flat-square&labelColor=231134)

**[Live App](https://spacepoint-drone-pipeline.streamlit.app/) · [Repository](https://github.com/ktariqq/spacepoint-drone-pipeline)**

━━━━━━━━━━━━━━━━━━━━ ✦ ━━━━━━━━━━━━━━━━━━━━

</div>

<br/>

## 🛰️ Overview

This application takes raw sensor logs from a drone-mounted environmental payload (temperature, humidity, pressure, light, air quality, GPS) and carries them through the entire analysis pipeline — quality diagnostics, cleaning, mapping, image analysis, and reporting — without requiring a single script to be run outside the app.

Everything runs from one Streamlit interface: upload a raw mission file or pick one already on disk, and move through diagnostics, cleaning, visualization, and report generation entirely from the browser.

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ Features

### 🟣 Data Quality & Calibration
Runs a read-only diagnostic pass on a raw mission file before anything is changed.
- Missing value counts per sensor and per GPS field
- Out-of-range detection against physically defined sensor bounds
- GPS loss and duplicate timestamp counts
- Sudden-jump detection between consecutive readings
- Sensor drift check comparing early-mission vs. late-mission averages

### 🟣 Data Cleaning
Runs the full cleaning pipeline from inside the app — no CLI required.
- Drops fully empty rows, removes duplicate timestamps
- Nulls physically impossible readings, time-interpolates short gaps, leaves long gaps flagged
- Flags statistical anomalies (z-score) and flatlined/stuck sensors
- Writes the cleaned CSV, summary JSON, plot data, and GeoJSON in one run

### 🟣 Mission Dashboard
- Mission summary (date, location, duration)
- Live sensor averages and time-series charts
- Automatic warnings (high temperature, GPS loss, sensor errors)
- Filterable data table with CSV export

### 🟣 GPS Mission Map
- Interactive Leaflet map on a dark basemap
- Color-coded markers by sensor, with a flight-path toggle
- **Heat Surface (IDW) view** — inverse-distance-weighted interpolation restricted to each point's nearest neighbors, so local patterns (e.g. asphalt vs. grass) stay visible instead of blurring into one average
- Built-in Heat Island Mapping sample dataset for demonstrating urban heat effects across surface types

### 🟣 Drone Image Processing Tool
- Real computer-vision pipeline (OpenCV): Excess Green Index + Otsu adaptive thresholding for vegetation, brightness index for bright/hot surfaces, K-means land-cover clustering
- Annotated overlays, side-by-side image comparison, and vegetation coverage statistics
- Results can be attached to a mission's generated report

### 🟣 Mission Report Generator
- One-click, self-contained HTML report per mission (all charts and images embedded as base64)
- Optional AI-drafted judgment sections (objective / observations / limitations / conclusion) via the Gemini API, grounded strictly in that mission's own numbers and always shown as an editable draft
- In-app preview and download

<br/>

<div align="center">━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━</div>

<br/>

## 🛰️ Tech Stack

| Layer | Tools |
|---|---|
| App framework | Streamlit |
| Data processing | pandas, NumPy |
| Computer vision | OpenCV, Pillow |
| Mapping | Leaflet.js, GeoJSON |
| Charting / plots | Matplotlib, Streamlit native charts |
| Reporting | Jinja2 (HTML templating) |
| AI drafting (optional) | Google Gemini API |

<br/>

## 🛰️ Project Structure
```
dashboard/
  Dashboard.py
  branding.py
  heat_interpolation.py
  image_processing.py
  pages/
    1_Data_Quality.py
    2_Data_Cleaning.py
    3_Mission_Map.py
    4_Image_Tool.py
    5_Report_Generator.py
scripts/
  clean_mission_data.py
  generate_geojson.py
  generate_report.py
  generate_sample_data.py
  heat_island_sample.py
  quality_check.py
  report_template.html
data/
  raw/  cleaned/  geo/  images/  image_analysis/
assets/
  spacepoint_logo.png
.streamlit/
  config.toml
  secrets.toml
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

### 3 — (Optional) generate sample mission data

The repository does not need any external data to run — two generator scripts produce realistic sample missions locally:

```bash
python scripts/generate_sample_data.py     # sample_mission.csv, with injected data-quality issues
python scripts/heat_island_sample.py       # heat_island_sample.csv, for the heat-mapping activity
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
4. **Mission Map** — view sensor readings by location, including the heat-surface interpolation view.
5. **Image Tool** — upload drone imagery for vegetation and land-cover analysis; optionally attach results to a mission.
6. **Report Generator** — generate a complete, downloadable mission report.

Both the Data Quality and Data Cleaning pages accept a file already in `data/raw/`, or a fresh CSV upload — no manual file placement required.

<br/>

## 🛰️ Configuration

AI-drafted report sections are optional and require a Gemini API key.

**Local development** — add to `.streamlit/secrets.toml`:
```toml
GEMINI_API_KEY = "your-key-here"
```

**Streamlit Community Cloud** — set `GEMINI_API_KEY` under your app's **Settings → Secrets**.

The report generator works fully without a key — AI sections simply fall back to fill-in-the-blank placeholders.

<br/>

## 🛰️ Deployment

The live version is deployed on **Streamlit Community Cloud**, pointed at `dashboard/Dashboard.py` as the entry point:

**[spacepoint-drone-pipeline.streamlit.app](https://spacepoint-drone-pipeline.streamlit.app/)**

To deploy your own copy: fork the repository, connect it in [Streamlit Community Cloud](https://streamlit.io/cloud), set `dashboard/Dashboard.py` as the main file, and add `GEMINI_API_KEY` under Secrets if AI drafting is wanted.

<br/>


<div align="center">

━━━━━━━━━━━━━━ ✦ ✧ ✦ ━━━━━━━━━━━━━━

Copyright © 2026 SpacePoint. All rights reserved.

</div>


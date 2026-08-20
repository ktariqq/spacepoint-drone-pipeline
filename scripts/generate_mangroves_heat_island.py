"""
SpacePoint - Abu Dhabi Mangroves Heat Island Dataset Generator
Author: Kommal

Builds a heat-island teaching dataset across the same real mangrove
corridor, tagged by real coastal surface type (mangrove canopy, tidal
mudflat, open water/channel, sandy upland, boardwalk). Ambient
temperature and humidity come from real historical weather data via
Open-Meteo; the per-surface offsets are a documented physical model
(canopy shading, water thermal mass, exposed sand/boardwalk heating),
not raw sensor data - the app's Data Quality/Cleaning pages treat this
CSV exactly like a real mission file either way.
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

import requests

OUTPUT_PATH = Path("data/raw/mangroves_heat_island.csv")

SOUTH, NORTH = 24.440, 24.560
WEST, EAST = 54.370, 54.460

MISSION_DATE = "2026-06-15"  # midday summer heat, when surface contrast is strongest
MIDDAY_HOUR = 12

# Documented offsets relative to ambient air temperature at midday for
# coastal/wetland surface types (shading, thermal mass, exposed heating)
SURFACE_PROFILES = {
    "mangrove_canopy": -3.0,   # dense shade + transpiration cooling
    "tidal_mudflat": 6.0,      # dark, exposed, low thermal mass
    "open_water": -1.5,        # high thermal mass, slow to heat
    "sandy_upland": 9.0,       # bright, dry, high midday heating
    "boardwalk": 11.0,         # elevated timber/composite decking, full sun exposure
}

# Real zone centers within the mangrove corridor, spread across the
# larger bounding box rather than one tight cluster
ZONE_CENTERS = {
    "mangrove_canopy": [(24.475, 54.400), (24.510, 54.415), (24.530, 54.425)],
    "tidal_mudflat":    [(24.460, 54.390), (24.500, 54.408)],
    "open_water":       [(24.470, 54.420), (24.520, 54.440)],
    "sandy_upland":     [(24.450, 54.380), (24.545, 54.435)],
    "boardwalk":        [(24.4529, 54.4056)],  # Eastern Mangroves boardwalk, real coordinates
}

SAMPLES_PER_ZONE_CENTER = 8


def fetch_ambient(date: str, hour: int, lat: float, lon: float) -> dict:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date,
        "end_date": date,
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,shortwave_radiation",
        "timezone": "Asia/Dubai",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    hourly = response.json()["hourly"]
    return {
        "temperature": hourly["temperature_2m"][hour],
        "humidity": hourly["relative_humidity_2m"][hour],
        "pressure": hourly["surface_pressure"][hour],
        "light": hourly["shortwave_radiation"][hour] * 120,
    }


def fetch_air_quality(date: str, hour: int, lat: float, lon: float) -> float:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date,
        "end_date": date,
        "hourly": "us_aqi",
        "timezone": "Asia/Dubai",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()["hourly"]["us_aqi"][hour]


def main():
    center_lat = (SOUTH + NORTH) / 2
    center_lon = (WEST + EAST) / 2

    print("Fetching real midday ambient conditions for the mangrove corridor...")
    ambient = fetch_ambient(MISSION_DATE, MIDDAY_HOUR, center_lat, center_lon)
    aqi = fetch_air_quality(MISSION_DATE, MIDDAY_HOUR, center_lat, center_lon)

    start_time = datetime.fromisoformat(f"{MISSION_DATE}T{MIDDAY_HOUR:02d}:00:00")
    rows = []
    i = 0

    for surface_type, centers in ZONE_CENTERS.items():
        offset = SURFACE_PROFILES[surface_type]
        for center_lat_pt, center_lon_pt in centers:
            for _ in range(SAMPLES_PER_ZONE_CENTER):
                t = start_time + timedelta(seconds=i * 5)
                lat = center_lat_pt + random.uniform(-0.0015, 0.0015)
                lon = center_lon_pt + random.uniform(-0.0015, 0.0015)
                temperature = ambient["temperature"] + offset + random.uniform(-0.5, 0.5)

                rows.append({
                    "timestamp": t.isoformat(),
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "altitude": 20.0,
                    "temperature": round(temperature, 2),
                    "humidity": round(ambient["humidity"] + random.uniform(-2, 2), 2),
                    "pressure": round(ambient["pressure"] + random.uniform(-0.5, 0.5), 2),
                    "light": round(min(ambient["light"], 150000), 1),
                    "air_quality": round(aqi + random.uniform(-3, 3), 1),
                    "battery_voltage": 3.9,
                    "surface_type": surface_type,
                })
                i += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows across {len(ZONE_CENTERS)} surface types to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
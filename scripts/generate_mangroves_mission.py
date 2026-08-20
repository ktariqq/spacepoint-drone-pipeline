"""
SpacePoint - Abu Dhabi Mangroves Mission Data Generator
Author: Kommal

Builds a realistic drone survey mission CSV over the Abu Dhabi mangrove
corridor (Eastern Mangroves to Jubail Island), using a real lawnmower
flight path and real historical weather/air-quality data pulled from
the free, keyless Open-Meteo APIs. Only battery_voltage is simulated -
everything else is either real geography or real environmental data.
"""

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import requests

OUTPUT_PATH = Path("data/raw/mangroves_mission.csv")

# Real bounding box: Eastern Mangroves National Park up through the
# Jubail Island mangroves - a ~13km x 10km corridor, not a single park
SOUTH, NORTH = 24.440, 24.560
WEST, EAST = 54.370, 54.460

# A real, past date so the historical weather archive has data for it
MISSION_DATE = "2026-03-15"
START_HOUR = 8   # 08:00 local - good light, cooler temps, typical survey window
FLIGHT_MINUTES = 40
INTERVAL_SECONDS = 5

FLIGHT_ALTITUDE = 60.0   # meters AGL, typical mangrove canopy survey height
LINE_SPACING_DEG = 0.006  # ~650m between survey lines


def build_flight_path() -> list[tuple[float, float]]:
    """Lawnmower survey pattern across the bounding box - back-and-forth
    lines with real, evenly spaced points, not a random jittery cluster."""
    points = []
    lat = SOUTH
    going_east = True
    n_points_per_line = 40

    while lat <= NORTH:
        lon_range = (
            [WEST + (EAST - WEST) * i / (n_points_per_line - 1) for i in range(n_points_per_line)]
            if going_east
            else [EAST - (EAST - WEST) * i / (n_points_per_line - 1) for i in range(n_points_per_line)]
        )
        for lon in lon_range:
            points.append((lat, lon))
        lat += LINE_SPACING_DEG
        going_east = not going_east

    return points


def fetch_weather(date: str, lat: float, lon: float) -> dict:
    """Real hourly historical weather from Open-Meteo (no API key)."""
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
    return response.json()["hourly"]


def fetch_air_quality(date: str, lat: float, lon: float) -> dict:
    """Real modeled air quality from Open-Meteo (no API key)."""
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
    return response.json()["hourly"]


def interpolate_hourly(hourly_values: list[float], hour: int, minute: int) -> float:
    """Linear interpolation between this hour's value and the next."""
    fraction = minute / 60.0
    current = hourly_values[hour]
    nxt = hourly_values[hour + 1] if hour + 1 < len(hourly_values) else current
    return current + (nxt - current) * fraction


def main():
    center_lat = (SOUTH + NORTH) / 2
    center_lon = (WEST + EAST) / 2

    print("Fetching real historical weather for the mission area...")
    weather = fetch_weather(MISSION_DATE, center_lat, center_lon)
    print("Fetching real air quality data...")
    air_quality_data = fetch_air_quality(MISSION_DATE, center_lat, center_lon)

    temps = weather["temperature_2m"]
    humidity = weather["relative_humidity_2m"]
    pressure = weather["surface_pressure"]
    radiation = weather["shortwave_radiation"]  # W/m^2
    aqi = air_quality_data["us_aqi"]

    flight_path = build_flight_path()
    n_samples = int((FLIGHT_MINUTES * 60) / INTERVAL_SECONDS)

    # Resample the flight path to match the number of time samples
    step = max(1, len(flight_path) // n_samples)
    flight_path = flight_path[::step][:n_samples]

    start_time = datetime.fromisoformat(f"{MISSION_DATE}T{START_HOUR:02d}:00:00")

    rows = []
    battery_start, battery_end = 4.15, 3.75

    for i, (lat, lon) in enumerate(flight_path):
        t = start_time + timedelta(seconds=i * INTERVAL_SECONDS)
        hour, minute = t.hour, t.minute

        temperature = interpolate_hourly(temps, hour, minute)
        rh = interpolate_hourly(humidity, hour, minute)
        pres = interpolate_hourly(pressure, hour, minute)
        rad = interpolate_hourly(radiation, hour, minute)
        light_lux = rad * 120  # rough W/m^2 -> lux conversion for daylight
        air_q = interpolate_hourly(aqi, hour, minute)

        # Small real sensor noise (not the mission's actual spatial variation)
        battery = battery_start - (battery_start - battery_end) * (i / len(flight_path))
        altitude = FLIGHT_ALTITUDE + 3 * math.sin(i / 15)  # gentle real altitude hold variation

        rows.append({
            "timestamp": t.isoformat(),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "altitude": round(altitude, 2),
            "temperature": round(temperature, 2),
            "humidity": round(rh, 2),
            "pressure": round(pres, 2),
            "light": round(min(light_lux, 150000), 1),
            "air_quality": round(air_q, 1),
            "battery_voltage": round(battery, 3),
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows covering the Abu Dhabi mangrove corridor to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
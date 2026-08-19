"""
SpacePoint - Sample Mission Data Generator
Author: Kommal

Generates a synthetic mission CSV matching the sensor logger format,
with deliberately injected data-quality problems, so the cleaning and
quality-check pipeline can be tested before real flight data exists.

Schema (matches logger firmware output):
timestamp,latitude,longitude,altitude,temperature,humidity,pressure,
light,air_quality,battery_voltage
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_PATH = Path("data/raw/sample_mission.csv")

BASE_LAT = 24.4539   # Abu Dhabi area
BASE_LON = 54.3773
START_TIME = datetime(2026, 8, 1, 8, 0, 0)
N_SAMPLES = 300
INTERVAL_SECONDS = 2


def generate_row(i: int) -> dict:
    t = START_TIME + timedelta(seconds=i * INTERVAL_SECONDS)
    lat = BASE_LAT + 0.0006 * (i / N_SAMPLES) + random.uniform(-0.00003, 0.00003)
    lon = BASE_LON + 0.0008 * (i / N_SAMPLES) + random.uniform(-0.00003, 0.00003)
    altitude = 30 + 5 * random.uniform(-1, 1) + (i / N_SAMPLES) * 10
    temperature = 34 + 3 * random.uniform(-1, 1) + 4 * (i / N_SAMPLES)
    humidity = 45 + 10 * random.uniform(-1, 1)
    pressure = 1008 + random.uniform(-2, 2)
    light = 20000 + 5000 * random.uniform(-1, 1)
    air_quality = 35 + 10 * random.uniform(-1, 1)
    battery_voltage = 4.1 - 0.3 * (i / N_SAMPLES)

    return {
        "timestamp": t.isoformat(),
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "altitude": round(altitude, 2),
        "temperature": round(temperature, 2),
        "humidity": round(humidity, 2),
        "pressure": round(pressure, 2),
        "light": round(light, 1),
        "air_quality": round(air_quality, 1),
        "battery_voltage": round(battery_voltage, 3),
    }


def inject_problems(rows: list[dict]) -> list[dict]:
    # Fully empty readings (sensor read failure)
    for i in random.sample(range(len(rows)), 5):
        for key in ["temperature", "humidity", "pressure", "light", "air_quality"]:
            rows[i][key] = ""

    # Short run of missing GPS (satellite lock lost)
    for i in range(120, 126):
        rows[i]["latitude"] = ""
        rows[i]["longitude"] = ""

    # Physically-impossible spikes (sensor glitch)
    rows[60]["humidity"] = 342.0
    rows[180]["temperature"] = 145.0

    # Flatlined/stuck sensor
    for i in range(200, 215):
        rows[i]["air_quality"] = 35.0

    # Duplicated timestamp
    rows[50]["timestamp"] = rows[49]["timestamp"]

    return rows


def main():
    rows = [generate_row(i) for i in range(N_SAMPLES)]
    rows = inject_problems(rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
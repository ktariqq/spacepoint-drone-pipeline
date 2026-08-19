"""
SpacePoint - Heat Island Sample Dataset Generator
Author: Kommal

Creates a small teaching dataset with readings tagged by surface type
(asphalt, grass, shaded, open, building), with temperature differences
built in so the heat-island pattern is obvious on the map. Runs through
the same pipeline unchanged - the extra "surface_type" column just
rides along.
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_PATH = Path("data/raw/heat_island_sample.csv")
BASE_LAT = 24.4539
BASE_LON = 54.3773
START_TIME = datetime(2026, 8, 15, 12, 0, 0)  # midday, when the effect is strongest

# Typical midday surface temperature offsets relative to ambient air
SURFACE_PROFILES = {
    "asphalt": 12.0,
    "building": 8.0,
    "open": 4.0,
    "grass": 1.0,
    "shaded": -2.0,
}

AMBIENT_TEMP = 36.0  # hot UAE midday baseline


def generate_row(i, surface_type, lat_offset, lon_offset):
    t = START_TIME + timedelta(seconds=i * 5)
    offset = SURFACE_PROFILES[surface_type]
    temperature = AMBIENT_TEMP + offset + random.uniform(-0.5, 0.5)

    return {
        "timestamp": t.isoformat(),
        "latitude": round(BASE_LAT + lat_offset, 6),
        "longitude": round(BASE_LON + lon_offset, 6),
        "altitude": 15.0,
        "temperature": round(temperature, 2),
        "humidity": round(30 + random.uniform(-3, 3), 2),
        "pressure": round(1008 + random.uniform(-1, 1), 2),
        "light": round(80000 + random.uniform(-2000, 2000), 1),
        "air_quality": round(30 + random.uniform(-5, 5), 1),
        "battery_voltage": 3.9,
        "surface_type": surface_type,
    }


def main():
    rows = []
    i = 0
    for row_index, surface_type in enumerate(SURFACE_PROFILES):
        for col_index in range(6):
            lat_offset = row_index * 0.0004
            lon_offset = col_index * 0.0004
            rows.append(generate_row(i, surface_type, lat_offset, lon_offset))
            i += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
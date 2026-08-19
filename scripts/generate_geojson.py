"""
SpacePoint - GeoJSON Generator
Author: Kommal

Turns a cleaned mission CSV into a GeoJSON file that web maps
(Leaflet.js) can read directly. Also used as a library function by
the Data Cleaning page.

Usage:
    python generate_geojson.py --input data/cleaned/sample_mission_cleaned.csv --output data/geo/sample_mission.geojson
"""

import argparse
import json
from pathlib import Path

import pandas as pd

SENSOR_COLUMNS = ["temperature", "humidity", "pressure", "light", "air_quality", "battery_voltage"]


def build_geojson(df: pd.DataFrame) -> dict:
    """Turns a cleaned mission dataframe into a GeoJSON FeatureCollection."""
    features = []

    for _, row in df.iterrows():
        if pd.isna(row["latitude"]) or pd.isna(row["longitude"]):
            continue  # can't place a point on the map without GPS

        properties = {
            "timestamp": str(row["timestamp"]),
            "has_flag": bool(row.get("has_flag", False)),
            "flags_summary": row.get("flags_summary", ""),
        }
        if "surface_type" in row and pd.notna(row["surface_type"]):
            properties["surface_type"] = row["surface_type"]

        for column in SENSOR_COLUMNS:
            value = row.get(column)
            properties[column] = None if pd.isna(value) else float(value)

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["longitude"]), float(row["latitude"])],  # GeoJSON is [lon, lat]
            },
            "properties": properties,
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def main():
    parser = argparse.ArgumentParser(description="Build a GeoJSON file from cleaned mission data")
    parser.add_argument("--input", type=Path, required=True, help="Path to the cleaned CSV file")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the GeoJSON file to")
    args = parser.parse_args()

    df = pd.read_csv(args.input, parse_dates=["timestamp"])
    geojson_data = build_geojson(df)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(geojson_data, indent=2))

    total_points = len(geojson_data["features"])
    skipped = len(df) - total_points
    print(f"Wrote {total_points} points to {args.output}")
    if skipped:
        print(f"Skipped {skipped} rows that had no GPS fix")


if __name__ == "__main__":
    main()
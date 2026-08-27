"""
SpacePoint - GeoJSON Generator
Author: Kommal

Usage:
    python generate_geojson.py --input data/cleaned/sample_mission_cleaned.csv --output data/geo/sample_mission.geojson
"""

import argparse
import json
from pathlib import Path

import pandas as pd

# scripts/generate_geojson.py -> project root -> dashboard/static/geo
# (fixed: was a bare relative "static/geo", resolved against whatever the
# current working directory happened to be when you ran the script)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_GEO_DIR = PROJECT_ROOT / "dashboard" / "static" / "geo"

SENSOR_COLUMNS = ["temperature", "humidity", "pressure", "light", "air_quality", "battery_voltage"]


def build_geojson(df: pd.DataFrame) -> dict:
    features = []
    for _, row in df.iterrows():
        if pd.isna(row["latitude"]) or pd.isna(row["longitude"]):
            continue

        flags_summary = row.get("flags_summary", "")
        if pd.isna(flags_summary) or str(flags_summary).strip().lower() in {"nan", "none", "null"}:
            flags_summary = ""

        properties = {
            "timestamp": str(row["timestamp"]),
            "has_flag": bool(row.get("has_flag", False)),
            "flags_summary": str(flags_summary),
        }

        if "surface_type" in row and pd.notna(row["surface_type"]):
            properties["surface_type"] = str(row["surface_type"])

        for column in SENSOR_COLUMNS:
            value = row.get(column)
            properties[column] = None if pd.isna(value) else float(value)

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["longitude"]), float(row["latitude"])],
            },
            "properties": properties,
        })

    return {"type": "FeatureCollection", "features": features}


def main():
    parser = argparse.ArgumentParser(description="Build a GeoJSON file from cleaned mission data")
    parser.add_argument("--input", type=Path, required=True, help="Path to the cleaned CSV file")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the local GeoJSON file to")
    args = parser.parse_args()

    df = pd.read_csv(args.input, parse_dates=["timestamp"])
    geojson_data = build_geojson(df)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    geojson_text = json.dumps(geojson_data, indent=2, allow_nan=False)
    args.output.write_text(geojson_text, encoding="utf-8")

    STATIC_GEO_DIR.mkdir(parents=True, exist_ok=True)
    static_output = STATIC_GEO_DIR / args.output.name
    static_output.write_text(geojson_text, encoding="utf-8")

    total_points = len(geojson_data["features"])
    skipped = len(df) - total_points

    print(f"Wrote {total_points} points to {args.output}")
    print(f"Static GeoJSON available at {static_output}")
    if skipped:
        print(f"Skipped {skipped} rows that had no GPS fix")


if __name__ == "__main__":
    main()
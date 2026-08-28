"""
SpacePoint - Automatic Column Detection
Author: Kommal

Lets the app work with any CSV, not just the original fixed sensor-
logger schema. Detects a timestamp column, latitude/longitude columns,
and treats every other numeric column as a "sensor" reading - no
hardcoded column names, no manual mapping step for the user.
"""

import pandas as pd

# Common name fragments for GPS/time columns, checked case-insensitively
LAT_NAMES = ["latitude", "lat"]
LON_NAMES = ["longitude", "lon", "lng"]
TIME_NAMES = ["timestamp", "time", "date", "datetime"]

# ID-like / categorical columns that can look numeric (e.g. a 0/1 flag)
# but aren't real sensor readings - excluded from auto-detection
NON_SENSOR_HINTS = [
    "id", "_id", "code", "flag", "status", "event", "detected",
    "attempt", "access", "tamper",
]


def _find_column(columns, name_fragments) -> str | None:
    """Finds the first column whose name (lowercased, spaces/underscores
    stripped) exactly matches one of the given fragments, falling back
    to a substring match if no exact match exists."""
    normalized = {c: c.lower().replace(" ", "").replace("_", "") for c in columns}

    for fragment in name_fragments:
        target = fragment.replace("_", "")
        for col, norm in normalized.items():
            if norm == target:
                return col

    for fragment in name_fragments:
        target = fragment.replace("_", "")
        for col, norm in normalized.items():
            if target in norm:
                return col

    return None


def detect_schema(df: pd.DataFrame) -> dict:
    """Looks at whatever columns this CSV actually has and works out
    which one is the timestamp, which two are latitude/longitude, and
    which remaining columns are numeric sensor readings."""
    timestamp_col = _find_column(df.columns, TIME_NAMES)
    lat_col = _find_column(df.columns, LAT_NAMES)
    lon_col = _find_column(df.columns, LON_NAMES)

    used_columns = {c for c in [timestamp_col, lat_col, lon_col] if c}

    sensor_cols = []
    for col in df.columns:
        if col in used_columns:
            continue
        lowered = col.lower()
        if any(hint in lowered for hint in NON_SENSOR_HINTS):
            continue
        # A column only counts as a sensor if most of its values are
        # actually numeric - text columns (e.g. "Weather_Condition")
        # get skipped automatically here
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().mean() > 0.8:
            sensor_cols.append(col)

    return {
        "timestamp_col": timestamp_col,
        "lat_col": lat_col,
        "lon_col": lon_col,
        "sensor_cols": sensor_cols,
    }


def rename_to_standard(df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """Renames the detected timestamp/lat/lon columns to the standard
    names the rest of the pipeline expects. Sensor columns keep their
    own real names (e.g. 'Battery_pct' stays 'Battery_pct'), so labels
    in charts and reports stay meaningful."""
    rename_map = {}
    if schema["timestamp_col"]:
        rename_map[schema["timestamp_col"]] = "timestamp"
    if schema["lat_col"]:
        rename_map[schema["lat_col"]] = "latitude"
    if schema["lon_col"]:
        rename_map[schema["lon_col"]] = "longitude"
    return df.rename(columns=rename_map)
from datetime import timedelta
from typing import Optional

import pandas as pd

from aq.config import PPB_TO_UGM3, TARGET_UNITS, UGM3_SPELLINGS, log
from aq.models import Record

COLUMNS = [
    "city", "country", "location_id", "location_name", "sensor_id",
    "latitude", "longitude", "parameter", "units", "value",
    "ts_utc", "hour_local",
]
GROUP_KEYS = [c for c in COLUMNS if c not in ("value", "hour_local")]


def to_ugm3(parameter: str, units: str, value: float) -> Optional[float]:
    u = units.strip().lower().replace("μ", "µ")
    if u in UGM3_SPELLINGS:
        return value
    if u in ("ppb", "ppm") and parameter in PPB_TO_UGM3:
        return value * (1000 if u == "ppm" else 1) * PPB_TO_UGM3[parameter]
    return None


def transform(records: list[Record]) -> pd.DataFrame:
    """One row per sensor per hour, all values in µg/m³. Flagged readings are dropped."""
    rows = []
    flagged = bad_units = 0
    for r in records:
        m = r.measurement
        if m.flagInfo and m.flagInfo.hasFlags:
            flagged += 1
            continue
        value = to_ugm3(m.parameter.name, m.parameter.units, m.value)
        if value is None:
            bad_units += 1
            continue
        p = m.period.datetimeFrom
        offset = p.local.utcoffset() if p.local is not None else None
        rows.append(
            {
                "city": r.city,
                "country": r.country,
                "location_id": r.location_id,
                "location_name": r.location_name,
                "sensor_id": r.sensor_id,
                "latitude": r.coordinates.latitude,
                "longitude": r.coordinates.longitude,
                "parameter": m.parameter.name,
                "units": TARGET_UNITS,
                "value": value,
                "ts_utc": p.utc,
                "offset_min": (offset or timedelta(0)).total_seconds() / 60,
            }
        )
    if flagged:
        log.info("Dropped %d flagged readings", flagged)
    if bad_units:
        log.warning("Dropped %d readings with unknown units", bad_units)

    df = pd.DataFrame(rows, columns=GROUP_KEYS + ["value", "offset_min"])
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["ts_utc"] = (
        pd.to_datetime(df["ts_utc"], utc=True, errors="coerce").dt.tz_localize(None).dt.floor("h")
    )
    df = df.dropna(subset=["value", "ts_utc", "latitude", "longitude", "parameter"])
    df["location_name"] = df["location_name"].fillna("unknown").str.strip()
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["hour_local"] = (df["ts_utc"] + pd.to_timedelta(df["offset_min"], unit="min")).dt.hour

    # average sub-hourly readings (e.g. 15 min data) into hourly values
    df = df.groupby(GROUP_KEYS, as_index=False).agg(
        value=("value", "mean"), hour_local=("hour_local", "first")
    )
    df = df.drop_duplicates(subset=["sensor_id", "ts_utc"])

    df = df.astype(
        {
            "location_id": "int64", "sensor_id": "int64", "hour_local": "int8",
            "value": "float64", "latitude": "float64", "longitude": "float64",
        }
    )
    return df[COLUMNS].sort_values(["city", "location_id", "ts_utc"]).reset_index(drop=True)

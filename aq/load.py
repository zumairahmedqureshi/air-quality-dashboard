from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from aq.config import DB_PATH, log

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS measurements (
    city VARCHAR, country VARCHAR, location_id BIGINT, location_name VARCHAR,
    sensor_id BIGINT, latitude DOUBLE, longitude DOUBLE, parameter VARCHAR,
    units VARCHAR, value DOUBLE, ts_utc TIMESTAMP, hour_local TINYINT,
    PRIMARY KEY (sensor_id, ts_utc)
)
"""


def last_timestamps(db_path: str = DB_PATH) -> dict[int, datetime]:
    """Newest stored hour for each sensor."""
    if not Path(db_path).exists():
        return {}
    try:
        con = duckdb.connect(db_path, read_only=True)
        try:
            rows = con.execute(
                "SELECT sensor_id, max(ts_utc) FROM measurements GROUP BY sensor_id"
            ).fetchall()
        finally:
            con.close()
    except duckdb.Error:
        return {}
    return {sid: ts.replace(tzinfo=timezone.utc) for sid, ts in rows if ts is not None}


def load(df: pd.DataFrame, db_path: str = DB_PATH) -> int:
    """Insert rows (existing sensor + hour rows are replaced). Returns number of new rows."""
    if df.empty:
        log.warning("Nothing to load.")
        return 0
    con = duckdb.connect(db_path)
    try:
        con.execute(SCHEMA_SQL)
        con.register("incoming", df)
        before = con.execute("SELECT count(*) FROM measurements").fetchone()[0]
        con.execute("INSERT OR REPLACE INTO measurements BY NAME SELECT * FROM incoming")
        after = con.execute("SELECT count(*) FROM measurements").fetchone()[0]
        log.info("Loaded %d new rows (table now has %d)", after - before, after)
        return after - before
    finally:
        con.close()

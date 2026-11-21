"""
Air quality data pipeline using the OpenAQ v3 API.

extract -> validate (pydantic) -> transform (pandas) -> load (duckdb) -> charts

Usage:
    python pipeline.py              fetch last 48 hours and draw charts
    python pipeline.py --eda-only   only redraw charts

The API key is read from .streamlit/secrets.toml (OPENAQ_API_KEY = "...").
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from aq.api_key import env_api_key
from aq.client import AuthError, OpenAQClient
from aq.config import CITIES, DB_PATH, DEFAULT_HOURS, log
from aq.eda import eda
from aq.extract import extract_city
from aq.load import last_timestamps, load
from aq.transform import transform
from aq.validate import validate_records


def run_etl(
    client: OpenAQClient,
    hours: int,
    db_path: str = DB_PATH,
    progress: Optional[Callable[[str, int, int], None]] = None,
    cities: Optional[list[str]] = None,
) -> dict:
    """Run extract, validate, transform and load for each city."""
    cities = [c for c in (cities or CITIES) if c in CITIES]
    dt_to = datetime.now(timezone.utc)
    dt_from = dt_to - timedelta(hours=hours)
    run_at = dt_to.isoformat(timespec="seconds")
    last_ts = last_timestamps(db_path)
    stats = {"raw": 0, "valid": 0, "rejected": 0, "new_rows": 0}

    for i, city in enumerate(cities):
        if progress:
            progress(city, i, len(cities))
        raw = extract_city(client, city, dt_from, dt_to, last_ts)
        valid, rejected = validate_records(raw, run_at)
        stats["raw"] += len(raw)
        stats["valid"] += len(valid)
        stats["rejected"] += rejected
        stats["new_rows"] += load(transform(valid), db_path)
    if progress:
        progress("done", len(cities), len(cities))
    log.info("ETL finished: %s", stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAQ air quality pipeline")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS,
                        help="hours of history to fetch (default 48)")
    parser.add_argument("--eda-only", action="store_true", help="only redraw the charts")
    args = parser.parse_args()

    if not args.eda_only:
        try:
            run_etl(OpenAQClient(env_api_key()), args.hours)
        except AuthError as exc:
            log.error("%s", exc)
            return
    eda()


if __name__ == "__main__":
    main()

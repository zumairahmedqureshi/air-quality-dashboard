import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from aq.client import OpenAQClient, _parse_utc
from aq.config import (
    CITIES, LOCATION_PAGE_LIMIT, MAX_LOCATION_PAGES, MAX_LOCATIONS_PER_CITY,
    MAX_PAGES_PER_SENSOR, PAGE_LIMIT, POLLUTANTS, SEARCH_RADIUS_M, WINDOW_HOURS, log,
)
from aq.transform import to_ugm3


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def fetch_locations(
    client: OpenAQClient, lat: float, lon: float, active_since: datetime
) -> list[dict]:
    """Active stations near the city. Reference monitors first, then the closest ones."""
    candidates = []
    for page in range(1, MAX_LOCATION_PAGES + 1):
        data = client.get(
            "/locations",
            {
                "coordinates": f"{lat},{lon}",
                "radius": SEARCH_RADIUS_M,
                "limit": LOCATION_PAGE_LIMIT,
                "page": page,
            },
        )
        results = (data or {}).get("results", [])
        for loc in results:
            last_seen = _parse_utc((loc.get("datetimeLast") or {}).get("utc"))
            coords = loc.get("coordinates") or {}
            if last_seen is None or last_seen < active_since:
                continue  # station stopped reporting
            if coords.get("latitude") is None or coords.get("longitude") is None:
                continue
            sensors = [
                s for s in loc.get("sensors", [])
                if (s.get("parameter") or {}).get("name", "").lower() in POLLUTANTS
            ]
            if sensors:
                loc["sensors"] = sensors
                loc["_dist_km"] = _distance_km(lat, lon, coords["latitude"], coords["longitude"])
                candidates.append(loc)
        if len(results) < LOCATION_PAGE_LIMIT:
            break
    candidates.sort(key=lambda loc: (not loc.get("isMonitor", False), loc["_dist_km"]))
    return candidates[:MAX_LOCATIONS_PER_CITY]


def fetch_sensor_measurements(
    client: OpenAQClient, sensor_id: int, dt_from: datetime, dt_to: datetime
) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, MAX_PAGES_PER_SENSOR + 1):
        data = client.get(
            f"/sensors/{sensor_id}/measurements",
            {
                "datetime_from": dt_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "datetime_to": dt_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": PAGE_LIMIT,
                "page": page,
            },
        )
        if not data:
            break
        results = data.get("results", [])
        rows.extend(results)
        if len(results) < PAGE_LIMIT:
            break
    return rows


def extract_city(
    client: OpenAQClient,
    city: str,
    dt_from: datetime,
    dt_to: datetime,
    last_ts: Optional[dict[int, datetime]] = None,
) -> list[dict]:
    """Raw measurements for one city. Sensors already in the DB start from their last hour."""
    lat, lon, country = CITIES[city]
    last_ts = last_ts or {}
    raw_records: list[dict] = []

    locations = fetch_locations(client, lat, lon, active_since=dt_from)
    log.info("%s: %d active locations", city, len(locations))
    for loc in locations:
        loc_coords = loc.get("coordinates") or {}
        for sensor in loc["sensors"]:
            start = max(dt_from, last_ts.get(sensor["id"], dt_from))
            if start >= dt_to:
                continue
            for m in fetch_sensor_measurements(client, sensor["id"], start, dt_to):
                raw_records.append(
                    {
                        "city": city,
                        "country": country,
                        "location_id": loc.get("id"),
                        "location_name": loc.get("name"),
                        "sensor_id": sensor["id"],
                        "coordinates": m.get("coordinates") or loc_coords,
                        "measurement": m,
                    }
                )
    log.info("%s: extracted %d raw records", city, len(raw_records))
    return raw_records


def fetch_current(client: OpenAQClient, locations: dict[int, str]) -> pd.DataFrame:
    """Latest reading of each station and pollutant, directly from the API."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    rows = []
    for loc_id, name in locations.items():
        # /latest has no pollutant name or unit, so get them from the location
        meta = client.get(f"/locations/{loc_id}") or {}
        sensors = {
            s.get("id"): s.get("parameter") or {}
            for loc in meta.get("results", []) for s in loc.get("sensors", [])
        }
        latest = client.get(f"/locations/{loc_id}/latest") or {}
        for m in latest.get("results", []):
            param = sensors.get(m.get("sensorsId"), {})
            pname = str(param.get("name", "")).lower()
            value = m.get("value")
            ts = _parse_utc((m.get("datetime") or {}).get("utc"))
            if pname not in POLLUTANTS or value is None or value < 0 or ts is None or ts < cutoff:
                continue
            ugm3 = to_ugm3(pname, str(param.get("units", "")), float(value))
            if ugm3 is None:
                continue
            rows.append({"location_id": loc_id, "location_name": name, "parameter": pname,
                         "value": ugm3, "ts_utc": ts.replace(tzinfo=None)})
    df = pd.DataFrame(rows, columns=["location_id", "location_name", "parameter", "value", "ts_utc"])
    if df.empty:
        return df
    return (df.sort_values("ts_utc", ascending=False)
              .drop_duplicates(["location_id", "parameter"])
              .reset_index(drop=True))

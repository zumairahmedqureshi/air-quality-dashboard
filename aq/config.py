import logging
from pathlib import Path

BASE_URL = "https://api.openaq.org/v3"

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = str(BASE_DIR / "air_quality.db")
OUTPUT_DIR = BASE_DIR / "output"
REJECTED_PATH = OUTPUT_DIR / "rejected_records.jsonl"
SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"

POLLUTANTS = {"pm25", "pm10", "no2", "o3"}
POLLUTANT_LABELS = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO2", "o3": "O3"}

TARGET_UNITS = "µg/m³"
PPB_TO_UGM3 = {"no2": 1.88, "o3": 1.96}  # at 25 C, 1 atm
UGM3_SPELLINGS = {"µg/m³", "µg/m3", "ug/m3", "ug/m³"}

# city: (lat, lon, country)
CITIES = {
    "Lahore": (31.5204, 74.3587, "PK"),
    "Delhi": (28.6139, 77.2090, "IN"),
    "London": (51.5074, -0.1278, "GB"),
    "Los Angeles": (34.0522, -118.2437, "US"),
    "Karachi": (24.8607, 67.0011, "PK"),
    "Islamabad": (33.6844, 73.0479, "PK"),
    "Mumbai": (19.0760, 72.8777, "IN"),
    "Bangkok": (13.7563, 100.5018, "TH"),
    "Paris": (48.8566, 2.3522, "FR"),
    "New York": (40.7128, -74.0060, "US"),
}

SEARCH_RADIUS_M = 25_000          # max allowed by the API
MAX_LOCATIONS_PER_CITY = 5
LOCATION_PAGE_LIMIT = 100
MAX_LOCATION_PAGES = 5
PAGE_LIMIT = 1000
MAX_PAGES_PER_SENSOR = 3
MIN_SECONDS_BETWEEN_CALLS = 1.1   # free tier allows about 60 calls per minute
MIN_CORR_HOURS = 24
DEFAULT_HOURS = 48
WINDOW_HOURS = 48

# last 48 hours of data, counted from the newest reading
RECENT_SQL = f"""
    SELECT * FROM measurements
    WHERE ts_utc >= (SELECT max(ts_utc) FROM measurements) - INTERVAL {WINDOW_HOURS} HOUR
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("aq")

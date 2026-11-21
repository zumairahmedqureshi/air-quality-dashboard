# Air Quality Dashboard

Collects air quality data (PM2.5, PM10, NO2, O3) for 10 cities from the
[OpenAQ](https://openaq.org) API, cleans it, stores it in DuckDB and shows it in a
Streamlit dashboard.

Cities: Lahore, Karachi, Islamabad, Delhi, Mumbai, Bangkok, London, Paris, New York, Los Angeles.

## Pipeline

```
OpenAQ API -> extract -> validate (pydantic) -> transform (pandas) -> load (duckdb) -> charts
```

| File | What it does |
|---|---|
| `pipeline.py` | Runs the whole pipeline |
| `app.py` | Streamlit dashboard |
| `aq/config.py` | Cities, paths and settings |
| `aq/api_key.py` | Reads the API key and hides it in logs |
| `aq/client.py` | OpenAQ API client (retries, rate limit) |
| `aq/extract.py` | Finds stations and downloads measurements |
| `aq/models.py` | Pydantic models for one measurement |
| `aq/validate.py` | Checks records, saves rejected ones |
| `aq/transform.py` | Converts units to µg/m³, hourly averages |
| `aq/load.py` | Saves data into `air_quality.db` |
| `aq/eda.py` | Draws the charts in `output/` |

## Dashboard

- Highest value of each selected pollutant in the last 48 hours
- Current value: live readings for a city from the API
- Average by hour of day, correlation between pollutants, top stations
- Raw data table with CSV download

## Run locally

1. Install Python 3.11 or newer.
2. Get a free API key at [explore.openaq.org](https://explore.openaq.org).
3. Create `.streamlit/secrets.toml`:

   ```toml
   OPENAQ_API_KEY = "your_key"
   ```

4. Install and run:

   ```bash
   python -m venv venv
   venv\Scripts\python -m pip install -r requirements.txt
   venv\Scripts\python pipeline.py
   venv\Scripts\python -m streamlit run app.py
   ```

   On Windows you can also use `run setup`, `run fetch` and `run`.

## Deploy on Streamlit Community Cloud

1. Create the app from this repository with `app.py` as the main file.
2. In Advanced settings choose Python 3.12 and add the secret:

   ```toml
   OPENAQ_API_KEY = "your_key"
   ```

The repository includes a copy of `air_quality.db`, so the dashboard shows data right away.
Press **Fetch new data** in the sidebar to update it.

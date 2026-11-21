"""
Streamlit dashboard for the air quality data.
Run: streamlit run app.py
"""
import os

import duckdb
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

from aq.api_key import env_api_key, redact
from aq.client import AuthError, OpenAQClient
from aq.config import (
    CITIES, DB_PATH, DEFAULT_HOURS, MIN_CORR_HOURS, POLLUTANT_LABELS, RECENT_SQL, TARGET_UNITS,
    WINDOW_HOURS,
)
from aq.extract import fetch_current
from pipeline import run_etl

st.set_page_config(page_title="Air Quality Dashboard", layout="wide")
sns.set_theme(style="whitegrid")

# stop long metric values from being cut off
st.markdown(
    """<style>
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] div, [data-testid="stMetricValue"] p {
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
        font-size: clamp(1.1rem, 2.4vw, 2.25rem) !important; line-height: 1.2 !important;
    }
    </style>""",
    unsafe_allow_html=True,
)


def label(param: str) -> str:
    return POLLUTANT_LABELS.get(param, param)


def fmt_time(ts) -> str:
    return pd.Timestamp(ts).strftime("%d %b %Y, %H:%M")


def db_version() -> float | None:
    times = [os.path.getmtime(p) for p in (DB_PATH, DB_PATH + ".wal") if os.path.exists(p)]
    return max(times) if times else None


@st.cache_data(show_spinner=False)
def load_data(version: float) -> pd.DataFrame:
    # version is the file modified time, so the cache resets when the db changes
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(RECENT_SQL).df()
    finally:
        con.close()


def get_data() -> tuple[pd.DataFrame, str | None]:
    version = db_version()
    if version is None:
        return pd.DataFrame(), None
    try:
        return load_data(version), None
    except duckdb.CatalogException:
        return pd.DataFrame(), None
    except duckdb.Error as exc:
        return pd.DataFrame(), str(exc)


def station_label(frame: pd.DataFrame) -> pd.Series:
    return frame["location_name"] + " #" + frame["location_id"].astype(str)


def note_missing_cities(p: pd.DataFrame, param: str) -> None:
    missing = sorted(set(chosen_cities) - set(p["city"]))
    if missing:
        st.caption(f"No {label(param)} data for {', '.join(missing)} in the last {WINDOW_HOURS} hours.")


def highest_lines(frame: pd.DataFrame, params: list[str], where_cols: list[str]) -> None:
    for param in params:
        g = frame[frame["parameter"] == param]
        if g.empty:
            st.markdown(f"**{label(param)}**: no data")
            continue
        top = g.loc[g["value"].idxmax()]
        where = ", ".join(str(top[c]) for c in where_cols)
        st.markdown(f"**{label(param)}**: **{top['value']:.1f} {TARGET_UNITS}** at {where} "
                    f"({fmt_time(top['ts_utc'])} UTC)")


# sidebar: fetch data
st.sidebar.header("Get data")

api_key = env_api_key()
if not api_key:
    # on Streamlit Cloud the key is set in the app's Secrets settings
    try:
        api_key = str(st.secrets.get("OPENAQ_API_KEY", "")).strip()
    except Exception:
        api_key = ""
if not api_key:
    st.sidebar.warning("API key not found. Add OPENAQ_API_KEY to .streamlit/secrets.toml.")

fetch_cities = st.sidebar.multiselect("Cities to fetch", list(CITIES), default=list(CITIES))
st.sidebar.caption(f"Fetches the last {DEFAULT_HOURS} hours.")

if st.sidebar.button("Fetch new data", disabled=not (api_key and fetch_cities)):
    bar = st.sidebar.progress(0.0, text="Starting...")

    def on_progress(city: str, i: int, n: int) -> None:
        bar.progress(i / n, text="Done" if city == "done" else f"Fetching {city} ({i + 1}/{n})...")

    try:
        stats = run_etl(OpenAQClient(api_key), DEFAULT_HOURS, progress=on_progress, cities=fetch_cities)
        st.sidebar.success(f"Done: {stats['new_rows']} new rows, {stats['rejected']} rejected")
    except AuthError as exc:
        st.sidebar.error(redact(exc))
    except Exception as exc:
        st.sidebar.error(f"Error: {redact(exc)}")

df, db_error = get_data()

st.title("Air Quality Dashboard")

if db_error:
    st.warning(f"Could not read the database. Try again in a moment.\n\n{db_error}")
    st.stop()
if df.empty:
    st.info("No data yet. Press Fetch new data.")
    st.stop()

# sidebar: filters
st.sidebar.header("Filters")
cities = sorted(df["city"].unique())
chosen_cities = st.sidebar.multiselect("Cities", cities, default=cities)
all_params = [p for p in POLLUTANT_LABELS if p in set(df["parameter"])]
chosen_params = st.sidebar.multiselect(
    "Pollutants", all_params, default=["pm25"] if "pm25" in all_params else all_params[:1],
    format_func=label,
)

fdf = df[df["city"].isin(chosen_cities)]
if fdf.empty or not chosen_params:
    st.warning("Select at least one city and one pollutant.")
    st.stop()

# summary
st.caption(f"Data from {fmt_time(fdf['ts_utc'].min())} to {fmt_time(fdf['ts_utc'].max())} UTC")
c1, c2, c3, c4 = st.columns([1, 1, 1, 1.6])
c1.metric("Hourly readings", f"{len(fdf):,}")
c2.metric("Stations", fdf["location_id"].nunique())
c3.metric("Cities", fdf["city"].nunique())
c4.metric("Latest reading (UTC)", fmt_time(fdf["ts_utc"].max()))

st.subheader(f"Highest value in the last {WINDOW_HOURS} hours")
highest_lines(fdf, chosen_params, ["location_name", "city"])

tab0, tab1, tab2, tab3, tab4 = st.tabs(
    ["Current value", "Peak hours", "Correlation", "By location", "Data"]
)

# current value (live from the API)
with tab0:
    col_a, col_b = st.columns([2, 1])
    live_city = col_a.selectbox("City", chosen_cities, key="live_city")
    clicked = col_b.button("Get current value", disabled=not api_key, width="stretch")
    if clicked:
        stations = (fdf[fdf["city"] == live_city]
                    .drop_duplicates("location_id")
                    .set_index("location_id")["location_name"].to_dict())
        try:
            with st.spinner(f"Loading current values for {live_city}..."):
                cur = fetch_current(OpenAQClient(api_key), stations)
            st.session_state["live"] = (live_city, cur, pd.Timestamp.now(tz="UTC"))
        except AuthError as exc:
            st.error(redact(exc))
        except Exception as exc:
            st.error(f"Error: {redact(exc)}")

    live = st.session_state.get("live")
    if live and live[0] == live_city:
        _, cur, asked_at = live
        cur = cur[cur["parameter"].isin(chosen_params)]
        if cur.empty:
            st.info(f"No current readings for {live_city}.")
        else:
            st.markdown(f"**Current values in {live_city}** (updated {fmt_time(asked_at)} UTC)")
            highest_lines(cur, chosen_params, ["location_name"])
            show = cur.assign(pollutant=cur["parameter"].map(label)).sort_values(["pollutant", "value"],
                                                                                 ascending=[True, False])
            show = show[["pollutant", "location_name", "value", "ts_utc"]]
            show = show.assign(value=show["value"].round(1))
            show.columns = ["Pollutant", "Station", f"Value ({TARGET_UNITS})", "Reading time (UTC)"]
            st.dataframe(show, hide_index=True, width="stretch")

# peak hours
with tab1:
    for param in chosen_params:
        p = fdf[fdf["parameter"] == param]
        if p.empty:
            st.info(f"No {label(param)} data.")
            continue
        hourly = p.groupby(["city", "hour_local"], as_index=False)["value"].mean()
        fig, ax = plt.subplots(figsize=(10, 4.5))
        sns.lineplot(data=hourly, x="hour_local", y="value", hue="city", marker="o", ax=ax)
        ax.set(title=f"Average {label(param)} by hour", xlabel="Hour (local time)",
               ylabel=TARGET_UNITS, xticks=range(0, 24, 2))
        st.pyplot(fig)
        plt.close(fig)
        peaks = hourly.loc[hourly.groupby("city")["value"].idxmax(), ["city", "hour_local", "value"]]
        peaks.columns = ["City", "Peak hour (local)", f"Average ({TARGET_UNITS})"]
        st.dataframe(peaks.round(2), hide_index=True)
        note_missing_cities(p, param)

# correlation
with tab2:
    tmp = fdf.assign(hr=fdf["ts_utc"].dt.floor("h"))
    panels = []
    for city, g in tmp.groupby("city"):
        wide = g.pivot_table(index=["location_id", "hr"], columns="parameter", values="value", aggfunc="mean")
        usable = wide.dropna(thresh=2)
        if wide.shape[1] >= 2 and len(usable) >= MIN_CORR_HOURS:
            panels.append((city, wide.rename(columns=label).corr(), len(usable)))
    if not panels:
        st.info("Not enough data for a correlation chart.")
    else:
        for start in range(0, len(panels), 3):
            cols = st.columns(3)
            for col, (city, corr, n) in zip(cols, panels[start:start + 3]):
                fig, ax = plt.subplots(figsize=(5, 4.5))
                sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1, ax=ax)
                ax.set_title(f"{city} (n={n})")
                ax.set(xlabel="", ylabel="")
                col.pyplot(fig)
                plt.close(fig)

# by location
with tab3:
    for param in chosen_params:
        p = fdf[fdf["parameter"] == param]
        if p.empty:
            st.info(f"No {label(param)} data.")
            continue
        top = (p.groupby(["city", "location_id", "location_name"], as_index=False)["value"].mean()
                .sort_values("value", ascending=False).head(15))
        top["station"] = station_label(top)
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(data=top, y="station", x="value", hue="city", dodge=False, ax=ax)
        ax.set(title=f"Highest average {label(param)} by location", xlabel=TARGET_UNITS, ylabel="")
        st.pyplot(fig)
        plt.close(fig)
        note_missing_cities(p, param)

# raw data
with tab4:
    rows = fdf[fdf["parameter"].isin(chosen_params)].sort_values("ts_utc", ascending=False)
    st.dataframe(rows, hide_index=True, width="stretch")
    st.download_button("Download CSV", rows.to_csv(index=False).encode("utf-8"),
                       "air_quality_filtered.csv", "text/csv")

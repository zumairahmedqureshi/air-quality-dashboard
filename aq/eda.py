from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from aq.config import DB_PATH, MIN_CORR_HOURS, OUTPUT_DIR, RECENT_SQL, TARGET_UNITS, log


def eda(db_path: str = DB_PATH) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    if not Path(db_path).exists():
        log.warning("No database found, run the pipeline first.")
        return
    sns.set_theme(style="whitegrid")
    con = duckdb.connect(db_path, read_only=True)
    try:
        # average PM2.5 by hour of day
        peak_png = OUTPUT_DIR / "pm25_peak_hours.png"
        hourly = con.execute(
            f"""
            SELECT city, hour_local, avg(value) AS avg_pm25
            FROM ({RECENT_SQL}) WHERE parameter = 'pm25'
            GROUP BY city, hour_local ORDER BY city, hour_local
            """
        ).df()
        if hourly.empty:
            log.warning("No PM2.5 data, skipping peak hours chart.")
            peak_png.unlink(missing_ok=True)
        else:
            fig, ax = plt.subplots(figsize=(10, 5))
            sns.lineplot(data=hourly, x="hour_local", y="avg_pm25", hue="city", marker="o", ax=ax)
            for city, g in hourly.groupby("city"):
                peak = g.loc[g["avg_pm25"].idxmax()]
                ax.annotate(f"{city} peak {int(peak.hour_local):02d}:00",
                            (peak.hour_local, peak.avg_pm25), textcoords="offset points",
                            xytext=(0, 8), ha="center", fontsize=8)
            ax.set(title="Average PM2.5 by hour of day", xlabel="Hour (local time)",
                   ylabel=f"PM2.5 ({TARGET_UNITS})", xticks=range(0, 24, 2))
            fig.tight_layout()
            fig.savefig(peak_png, dpi=150)
            plt.close(fig)

        # correlation between pollutants, one heatmap per city
        corr_png = OUTPUT_DIR / "pollutant_correlation.png"
        long = con.execute(
            f"""
            SELECT city, location_id, date_trunc('hour', ts_utc) AS hr, parameter, avg(value) AS v
            FROM ({RECENT_SQL}) GROUP BY ALL
            """
        ).df()
        panels = []
        for city, g in long.groupby("city"):
            wide = g.pivot_table(index=["location_id", "hr"], columns="parameter", values="v")
            usable = wide.dropna(thresh=2)
            if wide.shape[1] >= 2 and len(usable) >= MIN_CORR_HOURS:
                panels.append((city, wide.corr(), len(usable)))
        if not panels:
            log.warning("Not enough data for the correlation chart.")
            corr_png.unlink(missing_ok=True)
        else:
            fig, axes = plt.subplots(1, len(panels), figsize=(5.5 * len(panels), 5), squeeze=False)
            for ax, (city, corr, n) in zip(axes[0], panels):
                sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1,
                            ax=ax, cbar=False)
                ax.set_title(f"{city} (n={n})")
                ax.set(xlabel="", ylabel="")
            fig.suptitle("Pollutant correlation")
            fig.tight_layout()
            fig.savefig(corr_png, dpi=150)
            plt.close(fig)

        # stations with the highest average PM2.5
        loc_png = OUTPUT_DIR / "pm25_by_location.png"
        by_loc = con.execute(
            f"""
            SELECT city, location_id, any_value(location_name) AS location_name,
                   avg(value) AS avg_pm25
            FROM ({RECENT_SQL}) WHERE parameter = 'pm25'
            GROUP BY city, location_id ORDER BY avg_pm25 DESC LIMIT 15
            """
        ).df()
        if by_loc.empty:
            log.warning("No PM2.5 data, skipping location chart.")
            loc_png.unlink(missing_ok=True)
        else:
            by_loc["station"] = by_loc["location_name"] + " #" + by_loc["location_id"].astype(str)
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.barplot(data=by_loc, y="station", x="avg_pm25", hue="city", dodge=False, ax=ax)
            ax.set(title="Highest average PM2.5 by location", xlabel=f"PM2.5 ({TARGET_UNITS})",
                   ylabel="")
            fig.tight_layout()
            fig.savefig(loc_png, dpi=150)
            plt.close(fig)
        log.info("Charts saved in %s", OUTPUT_DIR)
    finally:
        con.close()

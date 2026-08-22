"""Assemble the per-meeting macro panel (as-of vintages) and persist it."""

from __future__ import annotations

import polars as pl

from synthetic_council.collectors.macro import (
    fetch_ciss,
    fetch_ea_unemployment,
    fetch_rtd_gdp_with_history,
    fetch_rtd_hicp_with_history,
    fetch_sentiment,
)
from synthetic_council.config import PROCESSED_DIR, RAW_DIR


def _asof_from_vintages(
    v: pl.DataFrame, dates: pl.DataFrame, value_col: str, indicator: str, geo: str
) -> pl.DataFrame:
    """Vintage-correct as-of: a (period, value) row is valid from its revdate until
    the next revision of the SAME period. At meeting d take the latest valid
    reference period."""
    v = v.with_columns(pl.col("revdate").shift(-1).over("period").alias("next_revdate"))
    j = dates.join_where(
        v,
        pl.col("revdate") <= pl.col("announcement_date"),
        pl.col("next_revdate").is_null()
        | (pl.col("announcement_date") < pl.col("next_revdate")),
    )
    return (
        j.sort(["announcement_date", "period"], descending=[False, True])
        .unique(subset=["announcement_date"], keep="first")
        .select(
            "announcement_date",
            pl.lit(geo).alias("geo"),
            pl.lit(indicator).alias("indicator"),
            pl.col("period").alias("ref_period"),
            pl.col(value_col).alias("value"),
        )
    )


def build_macro_panel(meetings: pl.DataFrame) -> pl.DataFrame:
    """meetings: gc_decisions frame with announcement_date column.

    Returns long panel: announcement_date | geo (EA or ISO2) | indicator | ref_period | value
    """
    dates = (
        meetings.select(pl.col("announcement_date")).unique().sort("announcement_date")
    )
    out: list[pl.DataFrame] = []

    # --- EA HICP (true vintages, RTD) ---
    hicp = fetch_rtd_hicp_with_history().sort(["period", "revdate"])
    hicp = (
        hicp.with_columns(
            pl.col("hicp_ea")
            .shift(12)
            .over("__vintage__" if False else "period")
            .alias("__unused__")
        )
        if False
        else hicp
    )
    # compute yoy within each vintage window: index level 12 months earlier under
    # the vintage visible at the row's own validity interval
    hicp = hicp.with_columns(
        pl.col("revdate").shift(-1).over("period").alias("next_revdate")
    )
    # for each period, the index level 12m before *as known at that time*: join
    # period-12 row whose validity interval covers this row's revdate
    hicp = hicp.with_columns(
        (
            pl.col("period").str.slice(0, 4).cast(pl.Int32) * 12
            + pl.col("period").str.slice(5, 2).cast(pl.Int32)
        ).alias("pm")
    ).with_columns((pl.col("pm") - 12).alias("pm_prev"))
    lag = hicp.select("pm", "revdate", "next_revdate", pl.col("hicp_ea").alias("prev"))
    hicp = (
        hicp.join(
            lag,
            left_on=["pm_prev"],
            right_on=["pm"],
            how="left",
        )
        .filter(
            (pl.col("revdate_right") <= pl.col("revdate"))
            & (
                pl.col("next_revdate_right").is_null()
                | (pl.col("revdate") < pl.col("next_revdate_right"))
            )
        )
        .with_columns(
            ((pl.col("hicp_ea") / pl.col("prev") - 1) * 100).alias("hicp_yoy")
        )
    )
    ea_hicp = _asof_from_vintages(
        hicp.filter(pl.col("hicp_yoy").is_not_null()).select(
            "revdate", "period", "hicp_yoy"
        ),
        dates,
        "hicp_yoy",
        "hicp_yoy",
        "EA",
    )
    out.append(ea_hicp)

    # --- EA GDP growth (true vintages, ECB RTD G_GDPM_TO_C; 2001-01 ->) ---
    gdp = fetch_rtd_gdp_with_history().sort(["period", "revdate"])
    gdp = gdp.with_columns(
        pl.col("revdate").shift(-1).over("period").alias("next_revdate")
    )
    gdp = gdp.with_columns(
        pl.col("period").str.slice(0, 4).cast(pl.Int32).alias("_y"),
        pl.col("period").str.slice(-1).cast(pl.Int32).alias("_q"),
    ).with_columns((pl.col("_y") * 4 + pl.col("_q")).alias("qmi"))
    lag_g = gdp.select("qmi", "revdate", "next_revdate", pl.col("gdp_ea").alias("prev"))
    gdp = gdp.with_columns((pl.col("qmi") - 4).alias("qmi_prev")).join(
        lag_g, left_on=["qmi_prev"], right_on=["qmi"], how="left"
    ).filter(
        (pl.col("revdate_right") <= pl.col("revdate"))
        & (
            pl.col("next_revdate_right").is_null()
            | (pl.col("revdate") < pl.col("next_revdate_right"))
        )
    ).with_columns(((pl.col("gdp_ea") / pl.col("prev") - 1) * 100).alias("gdp_yoy"))
    ea_gdp = _asof_from_vintages(
        gdp.filter(pl.col("gdp_yoy").is_not_null())
        .select("revdate", "period", "gdp_yoy"),
        dates, "gdp_yoy", "gdp_yoy", "EA",
    )
    out.append(ea_gdp)

    # --- CISS (daily as-of) ---
    ciss = fetch_ciss()
    ea_ciss = (
        dates.sort("announcement_date")
        .join_asof(
            ciss.sort("date"),
            left_on="announcement_date",
            right_on="date",
            strategy="backward",
        )
        .select(
            "announcement_date",
            pl.lit("EA").alias("geo"),
            pl.lit("ciss").alias("indicator"),
            pl.col("date").cast(pl.String).alias("ref_period"),
            pl.col("ciss").alias("value"),
        )
    )
    out.append(ea_ciss)

    # --- EA unemployment (LFSI monthly, 1-month lag) ---
    unemp = fetch_ea_unemployment().with_columns(
        (
            pl.col("period").str.slice(0, 4).cast(pl.Int32) * 12
            + pl.col("period").str.slice(5, 2).cast(pl.Int32)
        ).alias("pm")
    )
    dates_m = dates.with_columns(
        (
            (
                pl.col("announcement_date").dt.year() * 12
                + pl.col("announcement_date").dt.month()
            )
            - 1
        ).alias("pm_avail")
    ).sort("pm_avail")
    ea_unemp = dates_m.join_asof(
        unemp.sort("pm"), left_on="pm_avail", right_on="pm", strategy="backward"
    ).select(
        "announcement_date",
        pl.lit("EA").alias("geo"),
        pl.lit("unemp").alias("indicator"),
        pl.col("period").alias("ref_period"),
        pl.col("unemp_ea").alias("value"),
    )
    out.append(ea_unemp)

    # --- Sentiment (DG-ECFIN; reference month available within the month) ---
    EA_MEMBERS = {
        "AT",
        "BE",
        "CY",
        "DE",
        "EE",
        "ES",
        "FI",
        "FR",
        "EL",
        "GR",
        "HR",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PT",
        "SI",
        "SK",
    }
    sent = fetch_sentiment().filter(
        pl.col("indic").is_in(["ESI", "CONS"])
        & (pl.col("geo").is_in(sorted(EA_MEMBERS)) | (pl.col("geo") == "EA"))
    )
    for geo in ["EA"] + sorted(set(sent["geo"].unique().to_list()) - {"EA"}):
        s = sent.filter(pl.col("geo") == geo).sort("period")
        if s.height == 0:
            continue
        for indic in ["ESI", "CONS"]:
            si = s.filter(pl.col("indic") == indic)
            if si.height == 0:
                continue
            asof = (
                dates.sort("announcement_date")
                .with_columns(
                    pl.col("announcement_date").dt.truncate("1mo").alias("am")
                )
                .join_asof(
                    si.sort("period"),
                    left_on="am",
                    right_on="period",
                    strategy="backward",
                )
                .filter(pl.col("value").is_not_null())
                .select(
                    "announcement_date",
                    pl.lit(geo).alias("geo"),
                    pl.lit(f"sent_{indic.lower()}").alias("indicator"),
                    pl.col("period").cast(pl.String).alias("ref_period"),
                    pl.col("value"),
                )
            )
            out.append(asof)

    panel = pl.concat(out)
    return panel.sort("announcement_date", "geo", "indicator")


def collect(meetings: pl.DataFrame) -> pl.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    panel = build_macro_panel(meetings)
    panel.write_parquet(PROCESSED_DIR / "macro_asof_panel.parquet")
    panel.write_csv(PROCESSED_DIR / "macro_asof_panel.csv")
    return panel


if __name__ == "__main__":
    m = pl.read_parquet(PROCESSED_DIR / "gc_decisions.parquet")
    p = collect(m)
    print("panel rows:", p.height)
    print(p.filter(pl.col("announcement_date") == pl.lit("2022-07-21").str.to_date()))

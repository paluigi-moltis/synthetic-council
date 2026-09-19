"""Vintage-correct growth-rate computation for real-time databases.

Semantics (documented once, reused for HICP and GDP):

  level_t(q)  = observation of reference period q from the latest release with
                revdate <= t (release events; later releases revise it).
  yoy_t(p)    = level_t(p) / level_t(p - k) - 1, with k = 4 quarters / 12 months.
  at meeting d: pick the latest release event with revdate <= d and report its
                (p, yoy_d(p)) — i.e. the newest reference period whose first or
                revised value was already public at d.
"""

from __future__ import annotations

import polars as pl


def _period_index(df: pl.DataFrame, period_col: str, freq: str) -> pl.DataFrame:
    """Add a zero-based sequential index (qmi) to YYYY-Qn / YYYY-MM periods."""
    if freq == "Q":
        return df.with_columns(
            (
                pl.col(period_col).str.slice(0, 4).cast(pl.Int32) * 4
                + pl.col(period_col).str.slice(-1).cast(pl.Int32)
            ).alias("qmi")
        )
    return df.with_columns(
        (
            pl.col(period_col).str.slice(0, 4).cast(pl.Int32) * 12
            + pl.col(period_col).str.slice(5, 2).cast(pl.Int32)
        ).alias("qmi")
    )


def vintage_growth(
    releases: pl.DataFrame,
    period_col: str,
    value_col: str,
    revdate_col: str = "revdate",
    lag: int = 4,
    pct: bool = True,
) -> pl.DataFrame:
    """From a real-time release table -> DataFrame(period, revdate, growth).

    releases: one row per release event (period, value, revdate).
    Returns the same events annotated with growth_t(p) vs the lagged period's
    level *as known at t*.
    """
    df = (
        releases.rename({period_col: "period", value_col: "value", revdate_col: "revdate"})
        .filter(pl.col("revdate").is_not_null() & pl.col("value").is_not_null())
        .unique(subset=["period", "revdate"], keep="last")
    )
    freq = "Q" if df["period"].str.contains("-Q").any() else "M"
    df = _period_index(df, "period", freq)

    levels = df.select("qmi", "revdate", pl.col("value").alias("lag_lvl")).sort("revdate")
    ev = df.select("revdate", "qmi", "period", "value").sort("revdate")

    # level of lag_qmi as known at each event's revdate: last release <= revdate
    lagged = (
        ev.with_columns((pl.col("qmi") - lag).alias("lag_qmi"))
        .join_where(
            levels,
            pl.col("lag_qmi") == pl.col("qmi_right"),
            pl.col("revdate_right") <= pl.col("revdate"),
        )
        .sort(["revdate", "revdate_right"], descending=[False, True])
        .unique(subset=["revdate", "qmi"], keep="first")
    )
    growth = (pl.col("value") / pl.col("lag_lvl") - 1) * (100 if pct else 1)
    return (
        lagged.with_columns(growth.alias("growth"))
        .filter(pl.col("growth").is_not_null())
        .select("period", "revdate", "growth")
    )


def asof_growth(growth_events: pl.DataFrame, meetings: pl.DataFrame) -> pl.DataFrame:
    """Latest growth event per meeting date -> (announcement_date, period, growth).

    'Latest' = the event with the greatest (revdate, qmi): newest release first,
    and among same-day releases the newest reference period.
    """
    ev = _period_index(growth_events, "period", "Q")
    return (
        meetings.select(pl.col("announcement_date").unique())
        .join_where(ev, pl.col("revdate") <= pl.col("announcement_date"))
        .sort(["announcement_date", "revdate", "qmi"], descending=[False, True, True])
        .unique(subset=["announcement_date"], keep="first")
        .select("announcement_date", "period", "growth")
    )

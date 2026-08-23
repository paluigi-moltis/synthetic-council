"""Country macro collector tests (availability model, vintage as-of)."""

from __future__ import annotations

import datetime as dt

import polars as pl

from synthetic_council.collectors.country_macro import (
    _asof_latest_published,
    _asof_unemp_vintage,
    _month_avail,
    _quarter_avail,
)


def _dates(*ds: str) -> pl.DataFrame:
    return pl.DataFrame(
        {"announcement_date": [dt.date.fromisoformat(x) for x in ds]}
    )


def test_month_avail_mid_next_month():
    df = pl.DataFrame({"period": ["2022-06"]})
    out = df.select(_month_avail("period", 17).alias("a"))
    # June ends 2022-06-30; +17d = 2022-07-17
    assert out["a"][0] == dt.date(2022, 7, 17)


def test_quarter_avail_after_flash():
    df = pl.DataFrame({"period": ["2022-Q2"]})
    out = df.select(_quarter_avail("period", 31).alias("a"))
    # Q2 ends 2022-06-30; +31d = 2022-07-31 -> NOT visible at 2022-07-21
    assert out["a"][0] == dt.date(2022, 7, 31)


def test_asof_no_lookahead():
    """Q2-2022 GDP flash (avail 2022-07-31) invisible at 2022-07-21 meeting."""
    series = pl.DataFrame(
        {
            "geo": ["DE", "DE"],
            "period": ["2022-Q1", "2022-Q2"],
            "value": [3.7, 1.5],
        }
    )
    out = _asof_latest_published(
        series, _dates("2022-07-21"), "gdp_yoy", freq="Q", avail_days=31
    )
    assert out.height == 1
    assert out["ref_period"][0] == "2022-Q1"
    assert out["value"][0] == 3.7


def test_asof_per_geo():
    """Each country gets its own row (regression: missing by=geo join)."""
    series = pl.DataFrame(
        {
            "geo": ["DE", "IT"],
            "period": ["2022-06", "2022-06"],
            "value": [8.3, 8.5],
        }
    )
    out = _asof_latest_published(
        series, _dates("2022-07-21"), "hicp_yoy", freq="M", avail_days=17
    )
    assert out.height == 2
    by_geo = dict(zip(out["geo"].to_list(), out["value"].to_list(), strict=False))
    assert by_geo == {"DE": 8.3, "IT": 8.5}


def test_unemp_vintage_asof():
    vtg = pl.DataFrame(
        {
            "revdate": [dt.date(2022, 6, 1), dt.date(2022, 7, 1)],
            "geo": ["DE", "DE"],
            "period": ["2022-04", "2022-05"],
            "value": [3.0, 2.8],
        }
    )
    out = _asof_unemp_vintage(vtg, _dates("2022-07-21"))
    assert out.height == 1
    assert out["ref_period"][0] == "2022-05"
    assert out["value"][0] == 2.8
    # before the July vintage: April visible at the June meeting
    out2 = _asof_unemp_vintage(vtg, _dates("2022-06-15"))
    assert out2["ref_period"][0] == "2022-04"

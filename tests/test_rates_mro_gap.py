"""Regression tests for the MRO variable-rate-tender gap (2026-09 review).

The MRO fixed-rate series (MRR_FR) does not exist for 2000-06-28 → 2008-10-14
(variable rate tenders; the operative rate was the minimum bid rate, MRR_MBR).
The old pipeline produced null MRO levels and missed rate changes in that
window; these tests pin the splice and the cross-check table parsing.
"""

from __future__ import annotations

import polars as pl

from synthetic_council.collectors.rates import (
    decisions_from_daily_rates,
    fetch_rate_change_table,
    splice_mro_mbr,
)

MBR_ROW = pl.DataFrame(
    {"date": ["2001-11-09", "2001-11-10"], "mro_mbr": [3.75, 3.75]},
    schema={"date": pl.String, "mro_mbr": pl.Float64},
)


def test_splice_mro_mbr_fills_fixed_rate_gap():
    daily = pl.DataFrame(
        {
            "date": ["2001-11-07", "2001-11-08", "2001-11-09", "2001-11-10"],
            "mro": [None, None, None, None],
            "dfr": [2.75] * 4,
            "mlf": [4.25] * 4,
        },
        schema={
            "date": pl.String,
            "mro": pl.Float64,
            "dfr": pl.Float64,
            "mlf": pl.Float64,
        },
    ).with_columns(pl.col("date").str.to_date())
    out = splice_mro_mbr(daily, MBR_ROW.with_columns(pl.col("date").str.to_date()))
    assert out["mro"].to_list() == [None, None, 3.75, 3.75]
    assert "mro_mbr" not in out.columns  # working column dropped
    assert out["mro_fr"].null_count() == 4  # provenance: fixed rate absent


def test_splice_keeps_fixed_rate_when_both_present():
    daily = pl.DataFrame(
        {
            "date": ["2016-03-15", "2016-03-16"],
            "mro": [0.05, 0.0],
            "dfr": [-0.3, -0.4],
            "mlf": [0.3, 0.25],
        },
        schema={
            "date": pl.String,
            "mro": pl.Float64,
            "dfr": pl.Float64,
            "mlf": pl.Float64,
        },
    ).with_columns(pl.col("date").str.to_date())
    out = splice_mro_mbr(daily, MBR_ROW.with_columns(pl.col("date").str.to_date()))
    # fixed-rate era: MBR (which has no rows here anyway) must not override
    assert out["mro"].to_list() == [0.05, 0.0]


def test_change_detection_sees_min_bid_rate_change():
    """A min-bid-rate change inside the gap must register as a rate change."""
    daily = pl.DataFrame(
        {
            "date": ["2001-11-08", "2001-11-09", "2001-11-10"],
            # spliced series: min bid level 4.25 until the 9 Nov cut
            "mro": [4.25, 3.75, 3.75],
            "dfr": [2.75] * 3,
            "mlf": [4.75, 4.75, 4.25],
        },
        schema={
            "date": pl.String,
            "mro": pl.Float64,
            "dfr": pl.Float64,
            "mlf": pl.Float64,
        },
    ).with_columns(pl.col("date").str.to_date())
    chg = decisions_from_daily_rates(daily.with_columns(pl.col("date").cast(pl.String)))
    # 11-09: min bid cut 4.25→3.75 (spliced into mro); 11-10: mlf cut 4.75→4.25
    assert chg["date"].to_list() == [daily["date"][1], daily["date"][2]]


def test_rate_change_table_variable_tender_rows():
    """Rows where the MRO fixed-rate column is '-' must still parse, taking the
    minimum bid rate (2000-06-28: dfr 3.25, min bid 4.25, mlf 5.25); '−' is the
    Unicode minus used for negative rates, not a missing value."""
    table = fetch_rate_change_table()
    jun2000 = table.filter(pl.col("date") == "2000-06-28")
    assert jun2000.height == 1
    assert jun2000["mro"][0] == 4.25
    assert jun2000["dfr"][0] == 3.25
    # negative rates parse through the Unicode minus
    assert table.filter(pl.col("date") == "2019-09-18")["dfr"][0] == -0.5
    # the whole 2000-2008 window is now present (was dropped before the fix)
    assert (
        table.filter((pl.col("date") >= "2000-06-28") & (pl.col("date") <= "2008-10-14")).height
        >= 13
    )

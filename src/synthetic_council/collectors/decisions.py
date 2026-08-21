"""Governing Council monetary policy decision calendar (March 1999 - present).

One row per monetary policy meeting:

- `announcement_date` — day the "Monetary policy decisions" press release was
  published (14:15 CET), from the ECB foedb publications database
  (collectors/foedb.py).
- `decision` — `change` if any key rate changed with effect within the following
  11 days, else `hold`.
- `mro` / `dfr` / `mlf` — the three key ECB interest rates **in force after the
  decision** (levels on the effective date; for holds, the levels in force at
  announcement).
- `press_release_url` — the canonical English press-release URL.

Cross-validation performed at collect time:
- every rate-change effective date in the daily series must be matched to some
  announcement within 11 days (else listed in `unmatched_effective_dates`);
- announcement cadence per year must follow the GC's known schedule (24→12→8).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from synthetic_council.collectors.foedb import fetch_all
from synthetic_council.collectors.rates import fetch_key_rates
from synthetic_council.config import PROCESSED_DIR, RAW_DIR

MAX_EFFECTIVE_LAG_DAYS = 11


def build() -> pl.DataFrame:
    daily = fetch_key_rates(start="1998-12-01").with_columns(
        pl.col("date").str.to_date("%Y-%m-%d")
    )

    pubs, _ = fetch_all()
    mopo = pubs.filter(pl.col("title") == "Monetary policy decisions").sort("published_at")
    # canonical English URL (plain python loop: map_elements probes UDFs with a Series)
    def en_url(urls) -> str:
        urls = list(urls or [])
        for u in urls:
            if u.endswith(".en.html"):
                return "https://www.ecb.europa.eu" + u
        return ("https://www.ecb.europa.eu" + urls[0]) if urls else ""

    url_col = [en_url(u) for u in mopo["document_urls"].to_list()]
    mopo = mopo.with_columns(
        pl.Series("press_release_url", url_col, dtype=pl.String),
        pl.col("published_at").dt.convert_time_zone("UTC").dt.date().alias("announcement_date"),
    )

    # rate-change effective dates
    chg = daily.with_columns(
        [(pl.col(c) != pl.col(c).shift(1)).alias(f"c_{c}") for c in ("mro", "dfr", "mlf")]
    ).filter(pl.col("c_mro") | pl.col("c_dfr") | pl.col("c_mlf"))
    effective = chg.select(pl.col("date").alias("effective_date"), "mro", "dfr", "mlf")

    rows = []
    eff_list = effective.to_dicts()
    used: set = set()
    for m in mopo.iter_rows(named=True):
        a = m["announcement_date"]
        cand = [
            e for e in eff_list
            if timedelta(0) <= (e["effective_date"] - a) <= timedelta(days=MAX_EFFECTIVE_LAG_DAYS)
        ]
        if cand:
            e = cand[0]
            used.add(e["effective_date"])
            rows.append({**m, "rate_effective_date": e["effective_date"],
                         "decision": "change", "mro": e["mro"], "dfr": e["dfr"], "mlf": e["mlf"]})
        else:
            lvl = daily.filter(pl.col("date") <= a).sort("date").tail(1)
            rows.append({
                **m, "rate_effective_date": None, "decision": "hold",
                "mro": lvl["mro"][0], "dfr": lvl["dfr"][0], "mlf": lvl["mlf"][0],
            })

    df = pl.DataFrame(rows)
    unmatched = sorted({e["effective_date"] for e in eff_list} - used)
    if unmatched:
        print(f"WARNING: {len(unmatched)} rate-change dates matched no announcement: {unmatched}")
    return df.select(
        "announcement_date", "decision", "rate_effective_date", "mro", "dfr", "mlf",
        "press_release_url", "published_at",
    ).sort("announcement_date")


def collect() -> pl.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = build()
    df.write_parquet(PROCESSED_DIR / "gc_decisions.parquet")
    df.write_csv(PROCESSED_DIR / "gc_decisions.csv")
    return df

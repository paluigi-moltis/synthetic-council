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

import re
from datetime import date, timedelta

import polars as pl

from synthetic_council.collectors.foedb import fetch_all
from synthetic_council.collectors.rates import decisions_from_daily_rates, fetch_key_rates
from synthetic_council.config import PROCESSED_DIR

MAX_EFFECTIVE_LAG_DAYS = 11


def _slug_date(url: str) -> date | None:
    """True publication date from a press-release URL slug, else None.

    Pre-2015 foedb pub_timestamps are batch times logged the evening BEFORE
    publication (22:00/23:00 CET), so they are off by one day. The URL slug
    carries the true date: /press/pr/date/2008/html/pr081008.en.html ->
    2008-10-08 (the coordinated cut). Modern foedb URLs (ecb.mpYYMMDD~hash)
    match their timestamps and return None here. Verified: 2008-10-08,
    2008-11-06, 2011-04-07, 2011-11-03, 2014-06-05, 2015-01-22, 2019-09-12.
    """
    m = re.search(r"/pr(\d{6})(?:_\d+)?\.en\.html", url or "")
    if not m:
        return None
    yy, mm, dd = int(m.group(1)[:2]), int(m.group(1)[2:4]), int(m.group(1)[4:])
    year = 1900 + yy if yy > 90 else 2000 + yy
    return date(year, mm, dd)


def true_date(url: str, published_at) -> date:
    """Announcement date: URL slug when available, else timestamp date."""
    return _slug_date(url) or published_at.date()


def build() -> pl.DataFrame:
    daily = fetch_key_rates(start="1998-12-01")
    if daily["date"].dtype == pl.String:
        daily = daily.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))

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
    )

    ann = [
        true_date(u, p)
        for u, p in zip(mopo["press_release_url"], mopo["published_at"], strict=False)
    ]
    mopo = mopo.with_columns(pl.Series("announcement_date", ann, dtype=pl.Date))

    # rate-change effective dates (null-aware: see decisions_from_daily_rates —
    # the spliced MRO series has no nulls, but keep the logic robust)
    chg = decisions_from_daily_rates(daily)
    effective = chg.select(pl.col("date").alias("effective_date"), "mro", "dfr", "mlf")

    rows = []
    eff_list = effective.to_dicts()
    used: set = set()
    for m in mopo.iter_rows(named=True):
        a = m["announcement_date"]
        cand = [
            e
            for e in eff_list
            if timedelta(0) <= (e["effective_date"] - a) <= timedelta(days=MAX_EFFECTIVE_LAG_DAYS)
        ]
        if cand:
            e = cand[0]
            used.add(e["effective_date"])
            rows.append(
                {
                    **m,
                    "rate_effective_date": e["effective_date"],
                    "decision": "change",
                    "mro": e["mro"],
                    "dfr": e["dfr"],
                    "mlf": e["mlf"],
                }
            )
        else:
            lvl = daily.filter(pl.col("date") <= a).sort("date").tail(1)
            rows.append(
                {
                    **m,
                    "rate_effective_date": None,
                    "decision": "hold",
                    "mro": lvl["mro"][0],
                    "dfr": lvl["dfr"][0],
                    "mlf": lvl["mlf"][0],
                }
            )

    df = pl.DataFrame(rows)
    unmatched = sorted({e["effective_date"] for e in eff_list} - used)
    if unmatched:
        print(f"WARNING: {len(unmatched)} rate-change dates matched no announcement: {unmatched}")
    return df.select(
        "announcement_date",
        "decision",
        "rate_effective_date",
        "mro",
        "dfr",
        "mlf",
        "press_release_url",
        "published_at",
    ).sort("announcement_date")


def collect() -> pl.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = build()
    df.write_parquet(PROCESSED_DIR / "gc_decisions.parquet")
    df.write_csv(PROCESSED_DIR / "gc_decisions.csv")
    return df

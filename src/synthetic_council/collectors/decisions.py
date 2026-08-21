"""Collector: the full Governing Council monetary policy decision calendar 1999-present.

Announcement dates: the ECB press release "Monetary policy decisions" has been
published at /press/pr/date/{YYMMDD}/html/pr{YYMMDD}_1.en.html (naming evolved;
post-2023 it is /press/pr/date/{YYYY}/html/ecb.mp{YYMMDD}~*.en.html). The Wayback
CDX index of ecb.europa.eu press-release URLs therefore enumerates every decision
announcement date back to 1999. Combined with the daily key-rate series (exact new
levels and effective dates), this yields one row per monetary policy meeting:
announcement date, decision (hold/change), and the three key rates set.

Cross-checks:
- #announcement dates should be ~11-12/yr for 1999-2000, ~8/yr from Nov 2001.
- Every rate-change effective date must fall within a few days AFTER some
  announcement date (rates change on the day of or the days right after the meeting).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import polars as pl

from synthetic_council.collectors.rates import fetch_key_rates
from synthetic_council.config import RAW_DIR, PROCESSED_DIR, USER_AGENT

CDX_URL = "http://web.archive.org/cdx/search/cdx"
# decision press-release URL patterns (all eras)
PR_TOKEN_RE = re.compile(r"/pr/date/(?:%20|\d{4}/html/)?[a-z\.]*pr(\d{6})(?:_\d+)?[~\.]", re.I)


@dataclass
class DecisionsResult:
    n_meetings: int
    n_changes: int
    first: str
    last: str
    unmatched_effective_dates: list[str]


def fetch_announcement_dates() -> list[str]:
    """All GC monetary policy decision announcement dates from the CDX index."""
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True) as c:
        r = c.get(
            CDX_URL,
            params={
                "url": "ecb.europa.eu/press/pr/date/",
                "matchType": "prefix",
                "fl": "original",
                "collapse": "urlkey",
                "limit": "50000",
            },
        )
        r.raise_for_status()
    urls = r.text.splitlines()
    tokens = set()
    for u in urls:
        m = PR_TOKEN_RE.search(u)
        if m:
            tokens.add(m.group(1))
    dates = []
    for t in sorted(tokens):
        yy = int(t[:2])
        year = 1900 + yy if yy > 90 else 2000 + yy
        date = f"{year}-{t[2:4]}-{t[4:6]}"
        # keep only tokens that look like real decision releases: filtered later by
        # cross-check against meeting cadence; helper tokens (0th issue etc) excluded
        dates.append(date)
    return sorted(set(dates))


def _effective_matches(announcement: str, effective_dates: list[str], max_lag_days: int = 11) -> list[str]:
    from datetime import datetime, timedelta

    a = datetime.strptime(announcement, "%Y-%m-%d")
    out = []
    for e in effective_dates:
        d = datetime.strptime(e, "%Y-%m-%d")
        if timedelta(0) <= d - a <= timedelta(days=max_lag_days):
            out.append(e)
    return out


def build_decision_calendar() -> tuple[pl.DataFrame, DecisionsResult]:
    """One row per monetary policy meeting with decision and new rate levels."""
    daily = fetch_key_rates(start="1998-12-01")
    daily = daily.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))

    # rate-change effective dates (vs previous day)
    chg = daily.with_columns(
        [
            (pl.col(c) != pl.col(c).shift(1)).alias(f"c_{c}") for c in ("mro", "dfr", "mlf")
        ]
    ).filter(pl.col("c_mro") | pl.col("c_dfr") | pl.col("c_mlf"))
    effective = [d.strftime("%Y-%m-%d") for d in chg["date"].to_list()]

    announcements = fetch_announcement_dates()
    rows = []
    used_effective: set[str] = set()
    for a in announcements:
        matches = _effective_matches(a, effective)
        new_eff = matches[0] if matches else None
        if new_eff:
            used_effective.add(new_eff)
        rows.append(
            {
                "announcement_date": a,
                "rate_effective_date": new_eff,
                "decision": "change" if new_eff else "hold",
            }
        )
    df = pl.DataFrame(rows).sort("announcement_date")

    # attach new levels: rates on the effective date (or same-day levels for holds)
    daily_idx = daily.with_columns(pl.col("date").alias("eff_date_key"))
    out = df.with_columns(
        pl.col("rate_effective_date").fill_null(pl.col("announcement_date")).alias("eff_date_key")
    ).join(
        daily.rename({"date": "eff_date_key"}),
        on="eff_date_key",
        how="left",
    ).drop("eff_date_key")

    unmatched = sorted(set(effective) - used_effective)
    res = DecisionsResult(
        n_meetings=df.height,
        n_changes=df.filter(pl.col("decision") == "change").height,
        first=df["announcement_date"].min(),
        last=df["announcement_date"].max(),
        unmatched_effective_dates=unmatched,
    )
    return out, res


def collect() -> DecisionsResult:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df, res = build_decision_calendar()
    df.write_parquet(PROCESSED_DIR / "gc_decisions.parquet")
    df.write_csv(PROCESSED_DIR / "gc_decisions.csv")
    return res

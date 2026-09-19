"""Collector: ECB Governing Council monetary policy meetings and rate decisions.

Combines three authoritative ECB sources:

1. Key interest rates daily series (ECB Data Portal SDMX, FM dataflow) — gives the
   exact level of MRO/DFR/MLF on every day, from which decisions are derived by
   change-point detection.
2. The ECB "key ECB interest rates" historical table page — effective dates of every
   rate change (cross-check).
3. The GC meeting schedule page — distinguishes monetary policy meetings (Day 1/Day 2
   with press conference) from non-monetary policy meetings, current and future.

Output: data/processed/gc_meetings.parquet + .csv (small enough for CSV review).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import httpx
import polars as pl

from synthetic_council.config import (
    ECB_FM_CSV,
    GC_CALENDAR_URL,
    KEY_RATE_SERIES,
    KEY_RATES_TABLE_URL,
    PROCESSED_DIR,
    RAW_DIR,
    USER_AGENT,
)


@dataclass
class RatesCollectResult:
    n_days: int
    n_changes: int
    n_meetings: int


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=120,
        follow_redirects=True,
    )


def splice_mro_mbr(daily: pl.DataFrame, mbr: pl.DataFrame) -> pl.DataFrame:
    """Splice the minimum-bid-rate series into the MRO fixed-rate column.

    `daily` needs a `mro` column (the fixed rate, null during the variable-rate
    tender era); `mbr` has columns date + `mro_mbr`. The fixed rate wins where
    it exists; the min bid rate fills the rest. The raw fixed-rate column is
    kept as `mro_fr` for provenance and the working `mro_mbr` column dropped.
    """
    out = daily.join(mbr, on="date", how="left", coalesce=True)
    return (
        out.with_columns(pl.col("mro").alias("mro_fr"))
        .with_columns(pl.coalesce(["mro", "mro_mbr"]).alias("mro"))
        .drop("mro_mbr")
    )


def fetch_key_rates(start: str = "1997-01-01") -> pl.DataFrame:
    """Daily MRO/DFR/MLF levels from the ECB Data Portal (FM dataflow).

    The MRO key (MRR_FR) is the *fixed-rate tender* rate: it does not exist for
    the variable-rate-tender era 2000-06-28 → 2008-10-14 (MROs were allotted at
    discretionary rates; the operative policy rate was the *minimum bid rate*,
    series MRR_MBR — verified: MRR_FR is empty exactly on 2000-06-28 →
    2008-10-14, and MRR_MBR covers exactly that window, handshaking with
    MRR_FR at 3.75 on 2008-10-15). The two are spliced into a single `mro`
    column; the raw fixed-rate series is kept as `mro_fr` for provenance.
    """
    frames = []
    with _client() as c:
        for name, key in KEY_RATE_SERIES.items():
            r = c.get(ECB_FM_CSV.format(key=key, start=start))
            r.raise_for_status()
            df = pl.read_csv(io.BytesIO(r.content))
            df = (
                df.select(
                    pl.col("TIME_PERIOD").alias("date"),
                    pl.col("OBS_VALUE").cast(pl.Float64).alias(name),
                )
                .sort("date")
                .filter(pl.col(name).is_not_null())
            )
            frames.append(df)
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on="date", how="outer", coalesce=True)
    out = out.sort("date")
    if "mro_mbr" in out.columns:
        mbr = out.select("date", "mro_mbr")
        out = splice_mro_mbr(out.drop("mro_mbr"), mbr)
    return out


def fetch_rate_change_table() -> pl.DataFrame:
    """Historical 'with effect from' rate-change table from the ECB website.

    Table layout per row: [year] | date | DFR | MRO fixed | MRO min bid | MLF.
    The year cell is present only on the first row of each year group and is
    blank (&nbsp;) on continuation rows — the date may therefore sit in
    cells[0] (year popped) or cells[1] (year cell blank). The '-' in one of the
    two MRO columns marks the tender procedure not in use (fixed-rate tenders
    before/after the 2000-06-28 → 2008-10-14 variable-rate-tender era, where
    the operative rate was the minimum bid rate).
    """
    with _client() as c:
        r = c.get(KEY_RATES_TABLE_URL)
        r.raise_for_status()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S)
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    recs: list[tuple[str, float | None, float | None, float | None]] = []
    year = None
    for row in rows:
        cells = [
            re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        ]
        if not cells:
            continue
        if re.fullmatch(r"(19|20)\d{2}", cells[0]):  # year group header
            year = int(cells[0])
            cells = cells[1:]
        if year is None:
            continue
        # date cell: first cell that looks like '28 Jun.' (year cell may be blank)
        date_cell_idx = next(
            (i for i, c in enumerate(cells) if re.match(r"\d{1,2}\s+\w{3}", c)),
            None,
        )
        if date_cell_idx is None or len(cells) - date_cell_idx < 4:
            continue
        m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})", cells[date_cell_idx])
        if m is None:
            continue
        day, mon = int(m.group(1)), months.get(m.group(2).lower())
        if mon is None:
            continue
        vals = cells[date_cell_idx + 1 :]

        def _num(s: str) -> float | None:
            # '-' marks "not applicable" (the tender procedure not in use);
            # '−' is the Unicode minus used for negative rates.
            if s in {"-", ""}:
                return None
            return float(s.replace("−", "-"))

        try:
            # value layout: DFR | MRO fixed | MRO min bid | MLF — exactly one
            # of the two MRO columns is filled; take whichever it is.
            dfr = _num(vals[0])
            mro = _num(vals[1]) if _num(vals[1]) is not None else _num(vals[2])
            mlf = _num(vals[-1])
        except ValueError:
            continue
        recs.append((f"{year}-{mon:02d}-{day:02d}", dfr, mro, mlf))
    return pl.DataFrame(
        {
            "date": [r[0] for r in recs],
            "dfr": [r[1] for r in recs],
            "mro": [r[2] for r in recs],
            "mlf": [r[3] for r in recs],
        },
        schema={
            "date": pl.String,
            "dfr": pl.Float64,
            "mro": pl.Float64,
            "mlf": pl.Float64,
        },
    ).sort("date")


def fetch_meeting_calendar() -> pl.DataFrame:
    """GC meeting schedule page: all listed meetings (mostly current/future)."""
    with _client() as c:
        r = c.get(GC_CALENDAR_URL)
        r.raise_for_status()
    body = _main_content(r.text)
    items = re.findall(r"<dt>\s*(\d{2}/\d{2}/\d{4})\s*</dt>\s*<dd>(.*?)</dd>", body, re.S)
    recs = []
    for date_raw, desc in items:
        d = f"{date_raw[6:]}-{date_raw[3:5]}-{date_raw[:2]}"
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        is_mp = "monetary policy meeting" in desc
        is_day2 = "Day 2" in desc or "press conference" in desc
        recs.append(
            {
                "date": d,
                "description": desc,
                "is_monetary_policy": is_mp,
                "is_decision_day": is_mp and is_day2,
            }
        )
    return pl.DataFrame(recs).sort("date")


def _main_content(html: str) -> str:
    m = re.search(r"<main[^>]*>(.*?)</main>", html, re.S)
    return m.group(1) if m else html


def decisions_from_daily_rates(daily: pl.DataFrame) -> pl.DataFrame:
    """Derive decision events: first day each facility level changes vs prior day.

    Null-aware: a null → value transition counts as a change (the MRO series
    starts null on the days before the first fixed-rate/min-bid observation,
    and unspliced gap boundaries would otherwise swallow real changes).
    """
    df = daily
    if df["date"].dtype == pl.String:
        df = df.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
    for c in ("mro", "dfr", "mlf"):
        df = df.with_columns(
            (
                pl.col(c).is_not_null()
                & pl.col(c).ne_missing(pl.col(c).shift(1))
                & pl.col(c).shift(1).is_not_null()
            ).alias(f"_chg_{c}")
        )
    df = df.with_columns(
        (pl.col("_chg_mro") | pl.col("_chg_dfr") | pl.col("_chg_mlf")).alias("changed")
    )
    return df.filter(pl.col("changed"))


def collect(start: str = "1997-01-01") -> RatesCollectResult:
    """Run the full rates/meetings collection and persist outputs."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    daily = fetch_key_rates(start=start)
    daily.write_parquet(RAW_DIR / "key_rates_daily.parquet")

    table = fetch_rate_change_table()
    table.write_parquet(RAW_DIR / "key_rates_change_table.parquet")

    cal = fetch_meeting_calendar()
    cal.write_parquet(RAW_DIR / "gc_calendar_page.parquet")

    decisions = decisions_from_daily_rates(daily)
    decisions.write_parquet(PROCESSED_DIR / "rate_decisions.parquet")

    return RatesCollectResult(
        n_days=daily.height,
        n_changes=decisions.height,
        n_meetings=cal.height,
    )

"""Collector: ECB speeches (official all-speeches CSV) + last-speech-before-meeting.

The ECB publishes a precompiled dataset with the full text of all speeches by
Executive Board members (and EMI-era speeches) at
https://www.ecb.europa.eu/press/key/html/downloads.en.html

NOTE ON NCB GOVERNORS: this dataset covers ECB Executive Board speakers only.
Speeches by national central bank governors are published on the NCBs' own
websites; collecting those is left as a TODO (see docs/TODO.md) — for now the
memo pipeline falls back to the most recent ECB-level speech content.

Output:
- data/raw/speeches/speeches.parquet  (full corpus)
- data/processed/last_speech_before_meeting.parquet (one row per meeting x speaker)
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import httpx
import polars as pl

from synthetic_council.config import (
    ECB_SPEECHES_CSV_PAGE,
    PROCESSED_DIR,
    RAW_DIR,
    USER_AGENT,
)

SPEECHES_RAW_PATH = RAW_DIR / "speeches" / "speeches.parquet"


@dataclass
class SpeechesResult:
    n_speeches: int
    n_speakers: int
    date_min: str
    date_max: str


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True)


def download_csv() -> bytes:
    """Find and download the current all-speeches CSV from the downloads page."""
    with _client() as c:
        r = c.get(ECB_SPEECHES_CSV_PAGE)
        r.raise_for_status()
    m = re.search(r'href="([^"]*all_ECB_speeches\.csv[^"]*)"', r.text)
    if not m:
        raise RuntimeError("all_ECB_speeches.csv link not found on downloads page")
    href = m.group(1)
    url = href if href.startswith("http") else "https://www.ecb.europa.eu" + href
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    return r.content


def parse_pipe_csv(raw: bytes) -> pl.DataFrame:
    """Parse the date-anchored pipe-separated speeches CSV.

    The file contains embedded newlines inside quoted fields and occasional stray
    quote characters, which break strict CSV parsers; records are instead anchored
    on '^\\d{4}-\\d{2}-\\d{2}\\|' line starts.
    """
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    rows: list[list[str]] = []
    buf: list[str] = []
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}\|")
    for ln in lines[1:]:  # skip header
        if date_re.match(ln):
            if buf:
                rows.append("\n".join(buf).split("|", 4))
            buf = [ln]
        else:
            buf.append(ln)
    if buf:
        rows.append("\n".join(buf).split("|", 4))
    recs = [r for r in rows if len(r) == 5 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[0])]
    return pl.DataFrame(
        {
            "date": [r[0] for r in recs],
            "speakers": [r[1] for r in recs],
            "title": [r[2] for r in recs],
            "subtitle": [r[3] for r in recs],
            "contents": [r[4] for r in recs],
        },
        schema={"date": pl.String, "speakers": pl.String, "title": pl.String,
                "subtitle": pl.String, "contents": pl.String},
    ).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))


def last_speech_before_meetings(
    speeches: pl.DataFrame, meetings: pl.DataFrame, max_age_days: int = 120
) -> pl.DataFrame:
    """For each (meeting date, speaker), the most recent speech before the meeting.

    `meetings` must have columns: date (Date), is_decision_day (bool).
    """
    sp = (
        speeches
        .filter(pl.col("contents").str.len_bytes() > 200)  # substantive texts only
        .with_columns(pl.col("speakers").str.split("|").list.first().alias("speaker"))
        .select("date", "speaker", "title", "subtitle", "contents")
        .sort("date")
    )
    decisions = meetings.filter(pl.col("is_decision_day")).select("date").unique()
    out = sp.join_where(
        decisions,
        pl.col("date") < pl.col("date_right"),
        (pl.col("date_right") - pl.col("date")).dt.total_days() <= max_age_days,
    )
    # keep only the latest speech per (meeting, speaker)
    return (
        out.sort("date_right", descending=True)
        .unique(subset=["date_right", "speaker"], keep="first")
        .rename({"date": "speech_date", "date_right": "meeting_date"})
        .sort("meeting_date", "speaker")
    )


def collect() -> SpeechesResult:
    raw = download_csv()
    df = parse_pipe_csv(raw)
    (RAW_DIR / "speeches").mkdir(parents=True, exist_ok=True)
    df.write_parquet(SPEECHES_RAW_PATH)
    return SpeechesResult(
        n_speeches=df.height,
        n_speakers=df.select(pl.col("speakers").n_unique()).item(),
        date_min=str(df.select(pl.col("date").min()).item()),
        date_max=str(df.select(pl.col("date").max()).item()),
    )

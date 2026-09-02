"""Collector: ECB "foedb" publications database (full corpus since 1992).

Discovers the current database version/hash from versions.json, then walks all
data chunks (data/0/chunk_{i}.json, flat arrays of 13 columns per record).

Primary use in this project: the complete list of Governing Council "Monetary
policy decisions" press releases (announcement dates + press release URLs,
March 1999 - present).

See docs/data-sources/ecb-foedb.md for the full write-up of the endpoint
discovery, URL scheme and verified counts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import polars as pl

from synthetic_council.config import RAW_DIR, USER_AGENT

FOEDB_BASE = "https://www.ecb.europa.eu/foedb/dbs/foedb/publications.en"
RECORD_COLUMNS = [
    "id",
    "pub_timestamp",
    "year",
    "issue_number",
    "type",
    "JEL_Code",
    "Taxonomy",
    "boardmember",
    "Authors",
    "documentTypes",
    "publicationProperties",
    "childrenPublication",
    "relatedPublications",
]
CHUNK_SIZE = 250


@dataclass
class FoedbResult:
    n_records: int
    n_chunks: int
    version: str
    mopo_releases: int = 0
    first_decision: str = ""
    last_decision: str = ""
    extra: dict = field(default_factory=dict)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120)


def resolve_version(c: httpx.Client) -> tuple[str, str]:
    r = c.get(f"{FOEDB_BASE}/versions.json")
    r.raise_for_status()
    v = r.json()[0]
    return v["version"], v["hash"]


def fetch_all(sleep_s: float = 0.25) -> tuple[pl.DataFrame, FoedbResult]:
    """Walk every data chunk; return tidy DataFrame + stats."""
    with _client() as c:
        version, h = resolve_version(c)
        base = f"{FOEDB_BASE}/{version}/{h}"
        md = c.get(f"{base}/metadata.json")
        md.raise_for_status()
        total = md.json()["total_records"]

        raw: list[list] = []
        n_chunks = 0
        for i in range((total // CHUNK_SIZE) + 2):
            r = c.get(f"{base}/data/0/chunk_{i}.json")
            if r.status_code != 200:
                break
            chunk = r.json()
            if not chunk:
                break
            raw.extend(chunk)
            n_chunks += 1
            time.sleep(sleep_s)

    records = []
    for j in range(0, len(raw), len(RECORD_COLUMNS)):
        records.append(dict(zip(RECORD_COLUMNS, raw[j : j + len(RECORD_COLUMNS)], strict=False)))

    df = pl.DataFrame(
        {
            "id": [r["id"] for r in records],
            "pub_timestamp": [r["pub_timestamp"] for r in records],
            "year": [r["year"] for r in records],
            "type": [r["type"] for r in records],
            "boardmember": [r["boardmember"] for r in records],
            "document_urls": [r["documentTypes"] for r in records],
            "title": [
                ((r["publicationProperties"] or {}).get("Title")) or "" for r in records
            ],
            "subtitle": [
                "; ".join((r["publicationProperties"] or {}).get("Subtitle") or [])
                for r in records
            ],
        }
    ).with_columns(
        (pl.col("pub_timestamp") * 1000)
        .cast(pl.Datetime("ms"))
        .dt.replace_time_zone("Europe/Berlin")
        .alias("published_at"),
        pl.col("pub_timestamp").cast(pl.Int64),
    )
    df = df.sort("published_at", descending=True)

    mopo = df.filter(pl.col("title") == "Monetary policy decisions")
    res = FoedbResult(
        n_records=df.height,
        n_chunks=n_chunks,
        version=version,
        mopo_releases=mopo.height,
        first_decision=str(mopo["published_at"].min().date()) if mopo.height else "",
        last_decision=str(mopo["published_at"].max().date()) if mopo.height else "",
    )
    return df, res


def collect() -> FoedbResult:
    df, res = fetch_all()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.write_parquet(RAW_DIR / "foedb_publications.parquet")
    mopo = df.filter(pl.col("title") == "Monetary policy decisions")
    mopo.write_parquet(RAW_DIR / "foedb_mopo_decisions.parquet")
    return res

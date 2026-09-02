"""Collector: ECB/Eurosystem staff macroeconomic projections (MPD, full vintages).

The ECB Data Portal's Macroeconomic Projection Database (MPD, dataset id MPD)
contains every staff/Eurosystem projection round since 2000: euro area annual +
quarterly projections for HICP, real GDP and many other variables, June/December
Eurosystem rounds also with country-level annual projections, plus global economy
and technical assumptions. Dimensions include PD_ORIGIN (ECB staff vs Eurosystem
staff) and PD_ITEM (variable). TIME_PERIOD = projection vintage publication
quarter; the OBS rows carry per-target-period forecasts in wide per-target-year
series (REF_AREA + PD_ITEM + vintage).

Endpoint (verified 2026-08-21):
  https://data-api.ecb.europa.eu/service/data/MPD?format=csvdata&startPeriod=2000
  → ~33 MB CSV, one row per (series, target period, value).

Vintage → meeting mapping: a projection round published in month m (March/June/
September/December) is available to meetings on/after the publication date; rounds
are dated by quarter in the data (e.g. 2024-Q2 = June 2024 round). Publication
typically accompanies the first monetary policy meeting of the round's month
(results announced at that meeting), so we treat vintage quarter q as available
from the first day of the LAST month of q (conservative) — configurable.

Output: data/raw/mpd_projections.parquet (full), data/processed/staff_projections.parquet
(EA headline: hicp/gdp growth/unemployment, annual targets).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import httpx
import polars as pl

from synthetic_council.config import PROCESSED_DIR, RAW_DIR, USER_AGENT

MPD_CSV = (
    "https://data-api.ecb.europa.eu/service/data/MPD?format=csvdata&startPeriod=2000"
)

# headline items (PD_ITEM codes discovered from data; see exploratory notes)
HEADLINE_ITEMS = {
    "HICP": "hicp",
    "GDP_R": "gdp_growth",  # real GDP growth (to verify against data)
    "UNEMP": "unemployment",
}


@dataclass
class ProjectionsResult:
    n_rows: int
    n_vintages: int
    n_items: int


def collect() -> ProjectionsResult:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=600, follow_redirects=True
    ) as c:
        r = c.get(MPD_CSV)
        r.raise_for_status()
    df = pl.read_csv(io.BytesIO(r.content), infer_schema_length=0)
    df.write_parquet(RAW_DIR / "mpd_projections.parquet")

    keep = df.select(
        pl.col("REF_AREA").alias("ref_area"),
        pl.col("PD_ITEM").alias("item"),
        pl.col("PD_ORIGIN").alias("origin"),
        pl.col("TIME_PERIOD").alias("vintage"),
        pl.col("OBS_VALUE").cast(pl.Float64).alias("value"),
    )
    keep.write_parquet(PROCESSED_DIR / "staff_projections.parquet")
    return ProjectionsResult(
        n_rows=keep.height,
        n_vintages=keep["vintage"].n_unique(),
        n_items=keep["item"].n_unique(),
    )


if __name__ == "__main__":
    print(collect())

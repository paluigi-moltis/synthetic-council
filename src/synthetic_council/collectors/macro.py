"""Collector: macroeconomic vintages as of each Governing Council decision date.

For each GC monetary policy decision date, build the information set a member
plausibly had: the latest *released* data for euro area aggregates and member
countries.

Sources:
- ECB Real-Time Database (RTD, SDMX): HICP, industrial production with true
  vintages (include_history) for the euro area (S0 = changing composition).
- ECB SDMX (LFSI): unemployment, monthly.
- ECB SDMX (FM): CISS daily.
- Eurostat (prc_hicp_midx, namq_10_gdp, une_rt_m, EI_BSSI/EI_BSCI): country-level
  HICP, GDP growth, unemployment, sentiment (latest vintage; true vintages are
  only available for the EA aggregates via RTD).

Real-time discipline:
- Monthly data: observation month m is considered available at the meeting if
  m + publication lag <= meeting month. Lags: HICP ~1 month (flash), unemployment
  ~1 month, IP ~6 weeks, sentiment: same month available at month end.
- Quarterly GDP: quarter q available if q-end + ~45 days <= meeting date.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import polars as pl

from synthetic_council.config import PROCESSED_DIR, RAW_DIR, USER_AGENT

DATA_API = "https://data-api.ecb.europa.eu/service/data"
ESTAT_API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

EA_COUNTRIES = ["AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE",
                "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK"]

# Publication lag in months: observation available at meetings >= obs_month + lag
MONTHLY_LAGS = {
    "hicp": 1,       # flash estimate ~end of following month
    "unemp": 1,      # LFS monthly ~ end of following month
    "ip": 2,         # industrial production ~6 weeks
    "sentiment": 0,  # published within the reference month
}
GDP_LAG_DAYS = 45


@dataclass
class MacroResult:
    n_rows: int
    series: list[str]


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=180)


def fetch_ecb_csv(dataflow: str, key: str, start: str = "1997-01") -> pl.DataFrame:
    url = f"{DATA_API}/{dataflow}/{key}?format=csvdata&startPeriod={start}"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    return pl.read_csv(io.BytesIO(r.content)) if (io := __import__("io")) else None


def fetch_ciss() -> pl.DataFrame:
    """CISS daily index (D.U2.Z0Z.4F.EC.SS_CIN.IDX)."""
    import io

    url = f"{DATA_API}/FM/D.U2.Z0Z.4F.EC.SS_CIN.IDX?format=csvdata&startPeriod=1999-01"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    df = pl.read_csv(io.BytesIO(r.content))
    return (
        df.select(pl.col("TIME_PERIOD").alias("date"), pl.col("OBS_VALUE").cast(pl.Float64).alias("ciss"))
        .with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
        .sort("date")
    )


def as_of_monthly(
    obs: pl.DataFrame, meetings: pl.DataFrame, lag_months: int, value_col: str,
) -> pl.DataFrame:
    """For each meeting, take the observation from the latest available month."""
    m = meetings.select(pl.col("date").alias("meeting_date")).with_columns(
        (pl.col("meeting_date").dt.offset_by(f"-{lag_months}mo")).dt.strftime("%Y-%m").alias("avail_month")
    )
    o = obs.with_columns(pl.col("ref_month").str.strftime("%Y-%m").alias("om"))
    # latest obs month <= avail month
    joined = m.join(o, left_on="avail_month", right_on="om", how="left")
    # fix: need latest available, not exact match -> use join_asof on month strings
    o2 = o.sort("om")
    out = (
        pl.DataFrame({"meeting_date": m["meeting_date"], "avail_month": m["avail_month"]})
        .sort("avail_month")
        .join_asof(o2.sort("om"), left_on="avail_month", right_on="om", strategy="backward")
    )
    return out.select("meeting_date", pl.all().exclude("meeting_date")).rename(
        {"om": "ref_month", value_col: value_col}
    )


def collect(meetings: pl.DataFrame) -> MacroResult:
    """Build the as-of macro panel for the given decision meetings."""
    raise NotImplementedError("assembled in build_macro.py; kept for API symmetry")

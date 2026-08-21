"""Collector: real-time macroeconomic vintages for each GC meeting (EA + countries).

Builds, for every Governing Council monetary policy announcement date, the
information set available that day:

- HICP inflation (EA): ECB RTD true vintages (includeHistory release dates)
- GDP growth (EA): Eurostat PEEI ei_na_q_vtg true vintages (revdate dimension)
- Unemployment: PEEI ei_lm_m_vtg(+fix) true vintages for countries + ECB LFSI for EA
- Industrial production: PEEI ei_is_m_vtg(+fix) true vintages (EA + countries)
- CISS: daily, exact as-of value
- Sentiment (ESI, consumer confidence, sector confidences): DG-ECFIN monthly
  (published within reference month → available in the same month)

Method for vintage datasets: a value for reference period p at meeting date d is
the observation from the latest vintage row with revdate <= d (vintages store only
changes; missing = unchanged → carry forward last non-missing value).

See docs/data-sources/eurostat-peei-vintages.md for endpoints and caveats.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

import httpx
import polars as pl

from synthetic_council.config import USER_AGENT

ESTAT_SDMX = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}"
ECB_API = "https://data-api.ecb.europa.eu/service/data"
ECFIN_ZIP = (
    "https://ec.europa.eu/economy_finance/db_indicators/surveys/documents/"
    "series/nace2_ecfin_{stamp}/main_indicators_sa_nace2.zip"
)
EA_COUNTRIES = [
    "AT",
    "BE",
    "CY",
    "DE",
    "EE",
    "ES",
    "FI",
    "FR",
    "GR",
    "HR",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PT",
    "SI",
    "SK",
]
# Eurostat geo uses EL for Greece, DG-ECFIN uses EL too
ESTAT_GEOS = [
    "AT",
    "BE",
    "CY",
    "DE",
    "EE",
    "ES",
    "FI",
    "FR",
    "EL",
    "HR",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PT",
    "SI",
    "SK",
]


@dataclass
class MacroVintagesResult:
    n_meetings: int
    series: list[str]


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=600, follow_redirects=True
    )


# ---------------------------------------------------------------------------
# PEEI vintage datasets (TSV wide -> tidy)
# ---------------------------------------------------------------------------


def _parse_vtg_tsv(raw: bytes) -> pl.DataFrame:
    """Eurostat vintage TSV: key-dims \\ time columns; tidy to long format."""
    df = pl.read_csv(io.BytesIO(raw), separator="\t", infer_schema=False)
    key_col = df.columns[0]
    dim_names = key_col.split(",")
    dim_names = [d.split("\\")[0] for d in dim_names]
    records = []
    keys = df[key_col].to_list()
    value_cols = df.select(df.columns[1:]).to_dict(as_series=False)
    for row_i, key_str in enumerate(keys):
        parts = key_str.split(",")
        dims = dict(zip(dim_names, parts, strict=False))
        for col in df.columns[1:]:
            v = value_cols[col][row_i]
            if v is None:
                continue
            v = str(v).strip()
            if not v or set(v) <= {" ", ":", "u", "p", "e", "b", "r", "d", "f"}:
                continue
            # strip trailing flags after space
            m = re.match(r"^(-?\d+(?:\.\d+)?)", v)
            if not m:
                continue
            records.append({**dims, "period": col.strip(), "value": float(m.group(1))})
    return pl.DataFrame(
        {
            "revdate": [r["revdate"] for r in records],
            "geo": [r.get("geo", "") for r in records],
            "unit": [r.get("unit", "") for r in records],
            "s_adj": [r.get("s_adj", "") for r in records],
            "nace_r2": [r.get("nace_r2", "") for r in records],
            "period": [r["period"] for r in records],
            "value": [r["value"] for r in records],
        },
        schema_overrides={"value": pl.Float64},
    )


def download_peei(ds: str) -> pl.DataFrame:
    with _client() as c:
        r = c.get(
            ESTAT_SDMX.format(ds=ds), params={"format": "TSV", "compressed": "true"}
        )
        r.raise_for_status()
    return _parse_vtg_tsv(gzip_decompress(r.content))


def gzip_decompress(b: bytes) -> bytes:
    import gzip

    return gzip.decompress(b)


def asof_vintage(
    vtg: pl.DataFrame, meetings: pl.DataFrame, geo: str, filters: dict | None = None
) -> pl.DataFrame:
    """Latest vintage <= meeting date for each reference period (one geo)."""
    df = vtg.filter(pl.col("geo") == geo)
    if filters:
        for k, v in filters.items():
            df = df.filter(pl.col(k) == v)
    df = df.with_columns(pl.col("revdate").str.to_date("%Y-%m-%d")).sort("revdate")
    # for each period: value at latest revdate <= meeting
    out = (
        meetings.select(pl.col("announcement_date"))
        .unique()
        .join_where(
            df,
            pl.col("revdate") <= pl.col("announcement_date"),
        )
    )
    latest = out.sort(
        ["announcement_date", "revdate"], descending=[False, True]
    ).unique(subset=["announcement_date", "period"], keep="first")
    return latest


# ---------------------------------------------------------------------------
# ECB sources
# ---------------------------------------------------------------------------


def fetch_ciss() -> pl.DataFrame:
    with _client() as c:
        r = c.get(
            f"{ECB_API}/CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX",
            params={"format": "csvdata", "startPeriod": "1999-01"},
        )
        r.raise_for_status()
    df = pl.read_csv(io.BytesIO(r.content))
    return df.select(
        pl.col("TIME_PERIOD").str.to_date("%Y-%m-%d").alias("date"),
        pl.col("OBS_VALUE").cast(pl.Float64).alias("ciss"),
    ).sort("date")


def fetch_ea_unemployment() -> pl.DataFrame:
    with _client() as c:
        r = c.get(
            f"{ECB_API}/LFSI/M.U2.S.UNEHRT.TOTAL0.15_74.T",
            params={"format": "csvdata", "startPeriod": "1997-01"},
        )
        r.raise_for_status()
    df = pl.read_csv(io.BytesIO(r.content))
    return df.select(
        pl.col("TIME_PERIOD").alias("period"),
        pl.col("OBS_VALUE").cast(pl.Float64).alias("unemp_ea"),
    ).sort("period")


def fetch_rtd_hicp_with_history() -> pl.DataFrame:
    """EA HICP inflation with true vintages.

    With includeHistory=true the RTD CSV returns one row per revision: ACTION
    (Replace/Delete), VALID_FROM = release timestamp of that vintage. The vintage
    visible at date d for reference period p = the row with the latest
    VALID_FROM <= d. (Verified: 2020-02 first released 2020-03-11, revised
    2020-04-29, rebased 2026-02-04.)
    """
    with _client() as c:
        r = c.get(
            f"{ECB_API}/RTD/M.S0.N.P_C_OV.X",
            params={
                "format": "csvdata",
                "startPeriod": "1997-01",
                "includeHistory": "true",
            },
        )
        r.raise_for_status()
    df = pl.read_csv(io.BytesIO(r.content), infer_schema=False)
    return (
        df.select(
            pl.col("TIME_PERIOD").alias("period"),
            pl.col("OBS_VALUE").cast(pl.Float64).alias("hicp_ea"),
            pl.col("ACTION").alias("action"),
            pl.col("VALID_FROM").alias("valid_from"),
        )
        .with_columns(
            pl.col("valid_from")
            .str.slice(0, 10)
            .str.to_date("%Y-%m-%d")
            .alias("revdate")
        )
        .filter(pl.col("action") != "Delete")
    )


# ---------------------------------------------------------------------------
# DG-ECFIN sentiment
# ---------------------------------------------------------------------------


def fetch_sentiment() -> pl.DataFrame:
    """Download main_indicators xlsx, tidy to (period, geo, indicator, value)."""
    import datetime

    with _client() as c:
        raw = None
        now = datetime.datetime.now(datetime.UTC)
        for k in range(0, 8):
            stamp = (now.year % 100) * 100 + now.month - k
            yy = stamp // 100
            mm = stamp % 100
            code = f"{yy:02d}{mm:02d}"
            r = c.get(ECFIN_ZIP.format(stamp=code))
            # verify zip magic: some months return an HTML error page with 200
            if r.status_code == 200 and r.content[:2] == b"PK":
                raw = r.content
                break
        if raw is None:
            raise RuntimeError("DG-ECFIN surveys zip not found in last 8 months")
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if n.endswith(".xlsx"))
    df = pl.read_excel(
        io.BytesIO(z.read(name)), sheet_name="MONTHLY", infer_schema_length=0
    )
    df = df.rename({df.columns[0]: "period"})
    records = []
    cols = df.columns[1:]
    data = df.to_dicts()
    for row in data:
        p = row["period"]
        if p is None:
            continue
        for c in cols:
            v = row.get(c)
            if v is None or c == "period":
                continue
            s = str(v).strip()
            m = re.match(r"^(-?\d+(?:\.\d+)?)", s)
            if not m:
                continue
            geo, indic = str(c).split(".", 1)
            records.append(
                {
                    "period": str(p)[:10],
                    "geo": geo,
                    "indic": indic,
                    "value": float(m.group(1)),
                }
            )
    out = pl.DataFrame(records)
    # normalize end-of-month dates to month start
    return out.with_columns(
        pl.col("period").str.to_date("%Y-%m-%d").dt.truncate("1mo").alias("period")
    )

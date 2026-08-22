"""MPD round code decoding + headline item mapping.

PD_SEAS_EX = {W,G,S,A}{yy} encodes the projection round:
  W = March, G = June, S = September, A = December of 20yy.

Verified against published ECB/Eurosystem staff projections (2026-08-21):
- W22 HICP target 2022 = 5.1  -> March 2022 round ✓
- W23 HICP target 2023 = 5.3  -> March 2023 round ✓
- W24 HICP target 2024 = 2.3  -> March 2024 round ✓
- G22 HICP target 2023 = 3.5  -> June 2022 round ✓
- A22 HICP target 2022 = 8.4, target 2023 = 6.3 -> December 2022 round ✓
- G26 HICP target 2026 = 3.03 ≈ 3.0 -> June 2026 round ✓
- S23 HICP target 2023 = 5.6  -> September 2023 round ✓ (S=Sept by elimination)

NOTE: MPD annual values are averages of the quarterly projected path (long
decimals); published headline figures are these rounded. Rows with
TIME_PERIOD < round year are interpolated backdata, not forecasts.
99 suffix = legacy/undatable rounds; excluded.
"""

from __future__ import annotations

import polars as pl

ROUND_MONTH = {"W": 3, "G": 6, "S": 9, "A": 12}

ITEM_LABELS = {
    "HIC": "HICP inflation (%)",
    "YER": "Real GDP growth (%)",
    "URX": "Unemployment rate (%)",
    "DDR": "Domestic demand growth (%)",
    "PCR": "Private consumption growth (%)",
    "HEF": "HICP ex food & energy (%)",
    "HEG": "HICP food inflation (%)",
    "LTR": "Long-term interest rate (%)",
}

# Official CL_PD_ITEM meanings (ECB SDMX dataflow/ECB/MPD structure):
#   HIC = HICP overall index; YER = real GDP; URX = unemployment rate;
#   PCR = private consumption; DDR = domestic demand excl. inventory changes.
HEADLINE = ["HIC", "YER", "URX"]


def round_date(seas: str) -> str | None:
    """Publication date (first of round month) for a PD_SEAS_EX code."""
    if len(seas) != 3 or seas[0] not in ROUND_MONTH:
        return None
    try:
        yy = int(seas[1:])
    except ValueError:
        return None
    if yy == 99:
        return None  # legacy rounds, undatable
    return f"{2000 + yy:04d}-{ROUND_MONTH[seas[0]]:02d}-01"


def rounds_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Annotate MPD rows with round publication dates; keep headline items."""
    out = (
        df.filter(pl.col("PD_SEAS_EX").str.contains(r"^[WASG](0[0-9]|1[0-9]|2[0-9])$"))
        .with_columns(
            pl.col("PD_SEAS_EX")
            .map_elements(round_date, return_dtype=pl.String)
            .alias("round_date")
        )
        .filter(pl.col("round_date").is_not_null())
    )
    return out

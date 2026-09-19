"""Shared configuration: paths, endpoints, constants."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PACKAGE_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

USER_AGENT = "synthetic-council/0.1 (research; https://github.com/paluigi/synthetic-council)"

# --- ECB endpoints -----------------------------------------------------------
ECB_FM_CSV = (
    "https://data-api.ecb.europa.eu/service/data/FM/{key}?format=csvdata&startPeriod={start}"
)
KEY_RATE_SERIES = {
    # MRO fixed rate (tender procedure). Variable-rate-tender era (2000-06-28 →
    # 2008-10-14) has NO fixed rate: splice in the minimum bid rate (MRR_MBR),
    # the operative policy rate for that window — see rates.fetch_key_rates.
    "mro": "D.U2.EUR.4F.KR.MRR_FR.LEV",
    "mro_mbr": "D.U2.EUR.4F.KR.MRR_MBR.LEV",  # min bid rate (variable-tender era)
    "dfr": "D.U2.EUR.4F.KR.DFR.LEV",  # deposit facility rate
    "mlf": "D.U2.EUR.4F.KR.MLFR.LEV",  # marginal lending facility rate
}
KEY_RATES_TABLE_URL = (
    "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
    "key_ecb_interest_rates/html/index.en.html"
)
# CISS (Composite Indicator of Systemic Stress), daily
CISS_KEY = "D.U2.Z0Z.4F.EC.SS_CIN.IDX"
ACCOUNTS_INDEX = "https://www.ecb.europa.eu/press/accounts/html/index.en.html"
GC_CALENDAR_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
ECB_SPEECHES_CSV_PAGE = "https://www.ecb.europa.eu/press/key/html/downloads.en.html"

# --- Euro area members (changing composition note) ---------------------------
# Euro adoption dates (for composition-aware membership logic)
EURO_ADOPTION = {
    "AT": "1999-01-01",
    "BE": "1999-01-01",
    "DE": "1999-01-01",
    "ES": "1999-01-01",
    "FI": "1999-01-01",
    "FR": "1999-01-01",
    "IE": "1999-01-01",
    "IT": "1999-01-01",
    "LU": "1999-01-01",
    "NL": "1999-01-01",
    "PT": "1999-01-01",
    "GR": "2001-01-01",
    "SI": "2007-01-01",
    "CY": "2008-01-01",
    "MT": "2008-01-01",
    "SK": "2009-01-01",
    "EE": "2011-01-01",
    "LV": "2014-01-01",
    "LT": "2015-01-01",
    "HR": "2023-01-01",
}

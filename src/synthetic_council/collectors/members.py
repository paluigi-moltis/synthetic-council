"""Collector: ECB Governing Council membership over time (role-consistent person records).

A *person* can serve multiple roles (e.g. Mario Draghi: Governor of Banca d'Italia
2006-2011, then ECB President 2011-2019). Each (person, role) pair is a distinct
"member profile" so that simulation personas are consistent within a role period.

Sources (merged in this order of authority):
1. Wayback Machine monthly snapshots of the ECB "Governing Council" members page
   (2007-present, exact per-snapshot membership lists).
2. ECB monetary policy accounts attendee lists (2015-present) — adds voting-rights
   flags and temporary replacements per meeting.
3. Manual seed table (verified from ECB press releases) for 1998-2006, where no
   web archive of the members page exists.

Output: data/processed/gc_memberships.parquet with one row per (person, role, tenure).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import polars as pl

from synthetic_council.config import USER_AGENT

WAYBACK_CDX = "http://web.archive.org/cdx/search/cdx"
GC_PAGE_CANDIDATES = [
    "ecb.europa.eu/ecb/orga/decisions/govc/html/index.en.html",
    "www.ecb.europa.eu/ecb/orga/decisions/govc/html/index.en.html",
]

# Normalised role labels
ROLE_PRESIDENT = "ECB President"
ROLE_VICE_PRESIDENT = "ECB Vice-President"
ROLE_EXEC_BOARD = "ECB Executive Board member"

CENTRAL_BANK_BY_COUNTRY = {
    "AT": "Oesterreichische Nationalbank", "BE": "National Bank of Belgium",
    "CY": "Central Bank of Cyprus", "DE": "Deutsche Bundesbank",
    "EE": "Bank of Estonia", "ES": "Banco de España", "FI": "Bank of Finland",
    "FR": "Banque de France", "GR": "Bank of Greece", "HR": "Croatian National Bank",
    "IE": "Central Bank of Ireland", "IT": "Banca d'Italia", "LT": "Bank of Lithuania",
    "LU": "Banque centrale du Luxembourg", "LV": "Bank of Latvia", "MT": "Central Bank of Malta",
    "NL": "De Nederlandsche Bank", "PT": "Banco de Portugal", "SI": "Banka Slovenije",
    "SK": "National Bank of Slovakia",
}


@dataclass
class MembershipRow:
    person: str
    role: str
    country: str | None  # ISO2 for NCB governors, None for ECB executive roles
    start: str  # ISO date (first seen / known start)
    end: str  # ISO date (last seen / known end, exclusive)
    source: str


def http() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True)


def wayback_snapshots(year_from: int = 1999, year_to: int = 2026) -> list[str]:
    """Monthly-collapsed snapshot timestamps of the GC members page (both hosts)."""
    import time

    stamps: list[str] = []
    urls = list(GC_PAGE_CANDIDATES) + ["ecb.int/ecb/orga/decisions/govc/html/index.en.html"]
    with http() as c:
        for url in urls:
            try:
                r = c.get(
                    WAYBACK_CDX,
                    params={
                        "url": url, "output": "json", "from": str(year_from),
                        "to": str(year_to), "collapse": "timestamp:6", "limit": "400",
                    },
                )
            except httpx.HTTPError:
                continue
            if r.status_code == 200 and r.text.strip().startswith("["):
                try:
                    rows = r.json()
                except ValueError:
                    continue
                stamps.extend(row[1] for row in rows[1:])
            time.sleep(1.0)
    # dedupe by YYYY-MM keeping the first snapshot of each month (any host)
    by_month: dict[str, str] = {}
    for s in sorted(set(stamps)):
        by_month.setdefault(s[:6], s)
    return sorted(by_month.values())


def parse_members_page(html: str) -> list[tuple[str, str]]:
    """Extract (name, role-description) pairs from an ECB GC members page.

    Handles both the legacy layout (<strong>Name</strong>...<br/> ROLE) and the
    current card layout (<div class="title">Name</div>...<p>ROLE</p>).
    """
    entries: list[tuple[str, str]] = []
    # legacy layout (<strong>Name</strong> ... <br/> ROLE)
    for m in re.finditer(r"<strong>([^<]+)</strong>.*?<br/>\s*([^<]+?)\s*</div>", html, re.S):
        entries.append((m.group(1).strip(), m.group(2).strip()))
    # 2015-2020 layout: <p class="ecb-imgTitle">Name</p> ... <p class="ecb-imgDesc">ROLE</p>
    if not entries:
        for m in re.finditer(
            r'class="ecb-imgTitle">\s*([^<]+?)\s*</p>\s*<p class="ecb-imgDesc">\s*([^<]+?)\s*</p>',
            html, re.S,
        ):
            entries.append((m.group(1).strip(), m.group(2).strip()))
    # current card layout
    if not entries:
        for m in re.finditer(
            r'class="title">([^<]+)</div>.*?<p>([^<]+)</p>', html, re.S
        ):
            entries.append((m.group(1).strip(), m.group(2).strip()))
    # unescape entities
    out = []
    for name, role in entries:
        for ent, ch in {"&euml;": "ë", "&ntilde;": "ñ", "&aacute;": "á", "&eacute;": "é",
                        "&iacute;": "í", "&oacute;": "ó", "&uacute;": "ú", "&uuml;": "ü",
                        "&ouml;": "ö", "&amp;": "&", "&nbsp;": " "}.items():
            name = name.replace(ent, ch)
            role = role.replace(ent, ch)
        out.append((name, role))
    return out


def normalise_role(name: str, role_desc: str) -> tuple[str, str | None]:
    """Map a free-text role to (normalised_role, country_iso2)."""
    rd = role_desc.lower()
    if "president of the ecb" in rd and "vice" not in rd:
        return ROLE_PRESIDENT, None
    if "vice-president of the ecb" in rd or "vice-president of the european central bank" in rd:
        return ROLE_VICE_PRESIDENT, None
    if "executive board" in rd:
        return ROLE_EXEC_BOARD, None
    # NCB governor: match bank name back to country
    for iso, bank in CENTRAL_BANK_BY_COUNTRY.items():
        if _bank_match(role_desc, bank):
            return f"Governor, {bank}", iso
    return role_desc, None


def _bank_match(role_desc: str, bank: str) -> bool:
    """Fuzzy match a central bank name inside a role description."""
    d = role_desc.lower()
    key = bank.lower()
    aliases = {
        "Oesterreichische Nationalbank": ["oesterreichische", "austrian national bank"],
        "National Bank of Belgium": ["nationale bank van belgi", "banque nationale de belgique",
                                      "national bank of belgium"],
        "Deutsche Bundesbank": ["bundesbank"],
        "Banco de España": ["banco de espa", "bank of spain"],
        "Banque de France": ["banque de france"],
        "Banca d'Italia": ["banca d'italia", "banca d’italia"],
        "Central Bank of Ireland": ["central bank of ireland", "central bank and financial"],
        "Bank of Greece": ["bank of greece"],
        "Central Bank of Cyprus": ["central bank of cyprus"],
        "Banque centrale du Luxembourg": ["luxembourg"],
        "Central Bank of Malta": ["malta"],
        "De Nederlandsche Bank": ["nederlandsche"],
        "Banco de Portugal": ["banco de portugal"],
        "Banka Slovenije": ["slovenije", "slovenia"],
        "National Bank of Slovakia": ["slovenska", "slovakia"],
        "Bank of Finland": ["suomen pankki", "finlands bank", "finland"],
        "Bank of Estonia": ["estonia", "eesti pank"],
        "Bank of Latvia": ["latvijas banka", "latvia"],
        "Bank of Lithuania": ["lietuvos bankas", "lithuania"],
        "Croatian National Bank": ["hrvatska narodna banka", "croatia"],
    }
    for a in aliases.get(bank, [key]):
        if a in d:
            return True
    return False


def build_memberships(snapshots: list[str], max_snaps: int | None = None) -> list[MembershipRow]:
    """Walk snapshots in time order, merging consecutive (person, role) observations
    into tenures."""
    from datetime import datetime, timedelta

    snaps = snapshots if max_snaps is None else snapshots[:: max(1, len(snapshots) // max_snaps)]
    observations: list[tuple[str, str, str, str | None, str]] = []  # date, person, role, iso, source
    from synthetic_council.collectors.persons import canonicalise, person_id

    with http() as c:
        for ts in snaps:
            date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            page = None
            for tmpl in (
                f"http://web.archive.org/web/{ts}/http://www.ecb.europa.eu/ecb/orga/decisions/govc/html/index.en.html",
                f"http://web.archive.org/web/{ts}/https://www.ecb.europa.eu/ecb/orga/decisions/govc/html/index.en.html",
                f"http://web.archive.org/web/{ts}/http://www.ecb.int/ecb/orga/decisions/govc/html/index.en.html",
            ):
                try:
                    r = c.get(tmpl)
                except httpx.HTTPError:
                    continue
                if r.status_code == 200 and r.text:
                    page = r.text
                    break
            if not page:
                continue
            entries = parse_members_page(page)
            if not entries:
                continue
            for name, role_desc in entries:
                role, iso = normalise_role(name, role_desc)
                observations.append((date, canonicalise(name), role, iso, f"wayback:{ts}"))
    # merge observations into tenures (drop junk person names at source)
    _junk = (
        lambda n: not n
        or len(n) < 5
        or len(n) > 60
        or any(ch.isdigit() for ch in n)
        or any(s in n for s in ("<", ">", "{", "}", "+", "innerHTML", "Council",
                                "stability", "Insights"))
    )
    tenures: dict[tuple[str, str], dict] = {}
    for date, person, role, iso, source in sorted(observations):
        if _junk(person):
            continue
        key = (person, role)
        t = tenures.get(key)
        if t is None:
            tenures[key] = {"person": person, "role": role, "country": iso,
                            "start": date, "end": date, "source": source}
        else:
            t["end"] = date
    # extend end to the next snapshot boundary (+45 days after last sighting)
    rows = []
    for t in tenures.values():
        end = datetime.strptime(t["end"], "%Y-%m-%d") + timedelta(days=45)
        rows.append({**t, "end": end.strftime("%Y-%m-%d")})
    return [MembershipRow(**r) for r in rows]

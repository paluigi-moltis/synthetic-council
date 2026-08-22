"""Memo builder: per-member briefing for each GC monetary policy meeting.

For every Governing Council member (person x role profile active at the meeting
date) and every monetary policy decision meeting, produce a 1-2 page markdown memo:

1. Header — member, role, country (for governors), meeting date, current rates.
2. Euro area situation — as-of vintage macro data (HICP, GDP, unemployment, CISS,
   sentiment) + latest staff projections available at that date.
3. Country annex (governors only) — country sentiment, and (where vintages exist)
   country unemployment/industrial production.
4. Last speech by the member before the meeting (title, date, excerpt) — the
   member's most recent public positioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jinja2
import polars as pl

from synthetic_council.collectors.mpd_rounds import (
    HEADLINE,
    ITEM_LABELS,
    rounds_frame,
)
from synthetic_council.config import PROCESSED_DIR, RAW_DIR

COUNTRY_NAMES = {
    "AT": "Austria",
    "BE": "Belgium",
    "CY": "Cyprus",
    "DE": "Germany",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "EL": "Greece",
    "GR": "Greece",
    "HR": "Croatia",
    "IE": "Ireland",
    "IT": "Italy",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "MT": "Malta",
    "NL": "Netherlands",
    "PT": "Portugal",
    "SI": "Slovenia",
    "SK": "Slovakia",
}

MEMO_TEMPLATE = """# Briefing memo — {{ member.person }}

**Role:** {{ member.role }}
{% if member.country %}**Country:** {{ country_name }}
{% endif %}**Meeting:** GC monetary policy meeting, {{ meeting.announcement_date }}
**Current rates:** MRO {{ meeting.mro }}% · DFR {{ meeting.dfr }}% · MLF {{ meeting.mlf }}%

## Euro area economic situation (data available at the meeting)

| Indicator | Reference | Value |
|---|---|---|
{% for row in ea_rows %}| {{ row.indicator }} | {{ row.ref_period }} | {{ row.value }} |
{% endfor %}

## Latest staff projections available at the meeting

{% for proj in projections %}- **{{ proj.round }}**
  ({{ proj.item }}):
  {% for t in proj.targets %}{{ t.year }}: {{ t.value }} {% endfor %}
{% endfor %}

{% if country_rows %}
## {{ country_name }} — country situation

| Indicator | Reference | Value |
|---|---|---|
{% for row in country_rows %}| {{ row.indicator }} | {{ row.ref_period }} | {{ row.value }} |
{% endfor %}
{% endif %}

{% if last_speech %}
## Your most recent speech before the meeting

**"{{ last_speech.title }}"** — {{ last_speech.speech_date }}

{{ last_speech.excerpt }}
{% else %}
## Your most recent speech before the meeting

No ECB-website speech on record in the 120 days before the meeting.
{% endif %}
"""


@dataclass
class MemoResult:
    n_memos: int
    out_dir: Path


def _indicator_label(ind: str) -> str:
    return {
        "hicp_yoy": "HICP inflation (y/y %)",
        "gdp_yoy": "Real GDP growth (y/y %)",
        "unemp": "Unemployment rate (%)",
        "ciss": "CISS (systemic stress)",
        "sent_esi": "Economic Sentiment Indicator",
        "sent_cons": "Consumer confidence",
    }.get(ind, ind)


def _fmt(v) -> str:
    """Format a numeric value for the memo tables."""
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def _proj_round_available(projections: pl.DataFrame, meeting_date) -> pl.DataFrame:
    """Latest MPD projection rounds published on/before the meeting.

    MPD rounds are coded in PD_SEAS_EX as {W,A,S,G}{yy} = March/June/September/
    December of 20yy (decoding verified against published projections, see
    collectors/mpd_rounds.py). A round is available from the first of its month.
    """
    df = rounds_frame(projections)
    df = df.with_columns(pl.col("round_date").str.to_date("%Y-%m-%d"))
    return df.filter(pl.col("round_date") <= meeting_date)


def build_memos(
    meetings: pl.DataFrame,
    memberships: pl.DataFrame,
    macro: pl.DataFrame,
    projections: pl.DataFrame,
    last_speech: pl.DataFrame,
    out_dir: Path,
    meetings_limit: int | None = None,
) -> MemoResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)
    tpl = env.from_string(MEMO_TEMPLATE)

    meets = meetings.sort("announcement_date")
    if meetings_limit:
        meets = meets.tail(meetings_limit)

    n = 0
    for m in meets.iter_rows(named=True):
        d = m["announcement_date"]
        # active tenures, with a +45d grace past 'end' (Wayback sighting gaps).
        # A person can qualify twice near handovers (old role in grace, new role
        # started) — keep ONE memo per person: the tenure already started at d,
        # else the latest one.
        attendees = memberships.filter(
            (pl.col("start").str.to_date() <= d)
            & (pl.col("end").str.to_date() + pl.duration(days=45) >= d)
        ).with_columns(
            (
                (pl.col("end").str.to_date() >= d).alias("_active")
                & (pl.col("start").str.to_date() <= d)
            ).alias("_started")
        ).sort(["person", "_started", "start"], descending=[False, True, True]).unique(
            subset=["person"], keep="first"
        )
        ea_rows = macro.filter(
            (pl.col("announcement_date") == d) & (pl.col("geo") == "EA")
        ).sort("indicator")
        ea_out = [
            {
                "indicator": _indicator_label(r["indicator"]),
                "ref_period": r["ref_period"],
                "value": _fmt(r["value"]),
            }
            for r in ea_rows.iter_rows(named=True)
        ]
        # projections: latest round before meeting, EA, headline items
        avail = _proj_round_available(projections, d)
        proj_out = []
        if avail.height:
            last_round = avail["round_date"].max()
            round_year = int(str(last_round)[:4])
            ea_proj = avail.filter(
                (pl.col("round_date") == last_round)
                & (pl.col("REF_AREA") == "U2")
                & (pl.col("FREQ") == "A")
                & (pl.col("PD_ITEM").is_in(HEADLINE))
                & pl.col("TIME_PERIOD").str.contains(r"^\d{4}$")
            ).filter(
                # forward-looking targets only (MPD includes interpolated backdata)
                pl.col("TIME_PERIOD").cast(pl.Int32)
                >= round_year
            )
            for item in HEADLINE:
                rows = ea_proj.filter(pl.col("PD_ITEM") == item).sort("TIME_PERIOD")
                if not rows.height:
                    continue
                proj_out.append(
                    {
                        "round": last_round,
                        "item": ITEM_LABELS.get(item, item),
                        "targets": [
                            {"year": r["TIME_PERIOD"], "value": r["OBS_VALUE"]}
                            for r in rows.iter_rows(named=True)
                        ],
                    }
                )
        for a in attendees.iter_rows(named=True):
            country_rows = []
            if a["country"]:
                cgeo = "EL" if a["country"] == "GR" else a["country"]
                crows = macro.filter(
                    (pl.col("announcement_date") == d) & (pl.col("geo") == cgeo)
                ).sort("indicator")
                country_rows = [
                    {
                        "indicator": _indicator_label(r["indicator"]),
                        "ref_period": r["ref_period"],
                        "value": _fmt(r["value"]),
                    }
                    for r in crows.iter_rows(named=True)
                ]
            sp = last_speech.filter(
                (pl.col("meeting_date") == d)
                & (pl.col("speaker") == pl.lit(a["person"]))
            )
            sp_row = sp.row(0, named=True) if sp.height else None
            last_speech_ctx = None
            if sp_row:
                text = (sp_row.get("contents") or "").strip()
                words = text.split()
                excerpt = " ".join(words[:150]) + ("…" if len(words) > 150 else "")
                last_speech_ctx = {
                    "title": sp_row["title"],
                    "speech_date": str(sp_row["speech_date"]),
                    "excerpt": excerpt,
                }
            md = tpl.render(
                member=a,
                country_name=COUNTRY_NAMES.get(a["country"] or "", ""),
                meeting={
                    "announcement_date": str(d),
                    "mro": m["mro"] or 0,
                    "dfr": m["dfr"] or 0,
                    "mlf": m["mlf"] or 0,
                },
                ea_rows=ea_out,
                projections=proj_out,
                country_rows=country_rows,
                last_speech=last_speech_ctx,
            )
            fname = f"{d}_{a['person'].replace(' ', '_')}.md"
            (out_dir / fname).write_text(md, encoding="utf-8")
            n += 1
    return MemoResult(n_memos=n, out_dir=out_dir)


if __name__ == "__main__":
    meetings = pl.read_parquet(PROCESSED_DIR / "gc_decisions.parquet")
    memberships = pl.read_parquet("data/raw/gc_memberships_wayback.parquet")
    macro = pl.read_parquet(PROCESSED_DIR / "macro_asof_panel.parquet")
    projections = pl.read_parquet(RAW_DIR / "mpd_projections.parquet")
    last_speech = pl.read_parquet(PROCESSED_DIR / "last_speech_before_meeting.parquet")
    res = build_memos(
        meetings,
        memberships,
        macro,
        projections,
        last_speech,
        Path("data/processed/memos"),
        meetings_limit=3,
    )
    print(res)

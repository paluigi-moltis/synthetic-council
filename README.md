# synthetic-council

Agent-based simulations of the ECB Governing Council (GC) for interest rate
decisions. This repository currently contains the **data foundation**: collectors
and curated datasets that reconstruct, for every GC monetary policy meeting since
1999, (i) the decision and rate levels, (ii) who sat on the Council and in what
role, (iii) the macroeconomic information available *at that time* (true vintages
where they exist), (iv) each member's last public speech before the meeting, and
(v) per-member briefing memos suitable as LLM-agent inputs.

## Layout

```
src/synthetic_council/
  config.py                 endpoints, paths, constants
  collectors/
    foedb.py                ECB publications database (all press releases 1992→)
    rates.py                daily key rates + rate-change table
    decisions.py            GC decision calendar 1999→ (announcement dates)
    members.py              GC membership tenures from Wayback snapshots
    persons.py              name canonicalisation / person ids
    speeches.py             official ECB speeches dataset + last-speech join
    macro.py                PEEI vintages, RTD HICP vintages, CISS, sentiment
    macro_panel.py          as-of macro panel per meeting
    projections.py          ECB/Eurosystem staff projections (MPD)
  memo.py                   per-member markdown briefing builder
data/
  raw/                      source dumps (parquet)
  processed/                curated datasets + memos/
docs/
  data-sources/             per-source explainer documents (reproducibility)
  literature-review.md      OpenAlex-compiled review
references/references.bib   curated bibliography with abstracts
```

## Reproducing

```bash
uv sync
uv run python -m synthetic_council.collectors.foedb
uv run python -m synthetic_council.collectors.decisions
uv run python -m synthetic_council.collectors.macro_panel
uv run python -m synthetic_council.collectors.projections
uv run python -m synthetic_council.memo
# memberships + speeches via scripts (see docs/data-sources/)
```

Every dataset documents its endpoints, discovery path and verification in
`docs/data-sources/`. No API keys required.

## Datasets (verified 2026-08-21)

| dataset | rows | span | source |
|---|---|---|---|
| `gc_decisions.parquet` | 317 meetings | 1999-03 → 2026-07 | ECB foedb (URL-slug dates) + SDMX FM |
| `gc_memberships_wayback.parquet` | 93 tenures / 87 persons | 2004 → 2026 | Wayback GC pages (3 layouts) |
| `speeches.parquet` | 3,052 | 1997 → 2026-07 | ECB speeches CSV |
| `last_speech_before_meeting.parquet` | 1,888 meeting×speaker links | 1999 → 2026 | idem |
| `macro_asof_panel.parquet` | ~39.5k rows | 1999 → 2026; EA vintages 2001+; country HICP/GDP/unemp (21 geos) | ECB RTD + PEEI + Eurostat + CISS + DG-ECFIN |
| `staff_projections.parquet` | 154,686 | 2000 → 2026 | ECB MPD |
| `memos/` | 5,148 briefings (all meetings 2004→2026) | — | assembled |

## Reproducing everything

```bash
uv sync
uv run python scripts/collect_all.py            # full pipeline (~30-40 min, no keys)
uv run pytest                                   # 21 tests
uv run ruff check src/ scripts/ tests/
```

The pipeline is deterministic given upstream sources; each collector prints its
own verification stats (meeting counts, vintage spans, tenure counts).

## Status & next steps

See `docs/TODO.md` and `docs/QUESTIONS.md`.

# TODO

## Done (this PR)
- [x] GC decision calendar 1999→2026 (announcement dates, decisions, rate levels) — foedb + SDMX
- [x] Daily key rates + rate-change cross-check table
- [x] Membership tenures (person × role, canonical names) from Wayback snapshots (2004→)
- [x] Official ECB speeches corpus (3,052) + last-speech-before-meeting join (1,888)
- [x] As-of macro panel per meeting: EA HICP + GDP true vintages, CISS, EA unemployment, country+EA sentiment
- [x] ECB/Eurosystem staff projections (MPD, 145 vintages since 2000)
- [x] Memo builder (markdown, EA + country + last speech + projections)
- [x] Literature review + references.bib (95 entries, abstracts)
- [x] Data-source explainers (foedb, PEEI vintages)

## Next (proposed)
- [ ] 1999–2004 membership seed: ecb.int Wayback snapshots exist but pages pre-2004 use a different layout — parse or hand-seed from ECB annual reports
- [ ] Country-level true vintages: PEEI unemployment (`ei_lm_m_vtg`) + IP (`ei_is_m_vtg`) vintages are downloaded-but-not-yet-joined into the panel (currently sentiment-only for countries)
- [ ] Country GDP vintages: not on Eurostat (PEEI is EA/EU only) — decide fallback (latest-vintage + t+45 mask documented, or national RTD sources)
- [ ] Voting rights: accounts asterisks → per-meeting voting-rotation table (2015+)
- [ ] Accounts-based attendance cross-check for memberships (2015+)
- [ ] Memo calibration: eval vs Kazinnik–Sinclair priors (hawkishness scores from speeches via LLM classification)
- [ ] Simulation engine (out of scope per user decision, pending evaluation)
- [ ] CI: pytest for parsers with fixture HTML snapshots
- [ ] Packaging: make `scripts/` entry points for each collector run

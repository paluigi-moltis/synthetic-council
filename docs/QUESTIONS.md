# Open questions

## Data
1. **Country GDP vintages**: Eurostat's PEEI vintage database only covers EA/EU
   aggregates for GDP. Options: (a) latest-vintage country GDP with the t+20/45/65/110
   release calendar as an availability mask (approximation, reproducible);
   (b) per-country national real-time databases (big effort, heterogeneous);
   (c) drop country GDP from memos, keep sentiment/unemployment/IP. Preference?
2. **Pre-2015 unemployment/IP country vintages**: PEEI `*_vtgfix` static datasets
   hold 2001–2020 vintages — join them into the panel (recommended), or restrict
   country vintages to 2021+?
3. **1999–2004 membership**: earliest Wayback GC-members page is 2004-07. Seed
   from ECB Annual Report appendices (hand-curated, ~25 people) or restrict the
   simulation sample to 2004+?

## Design
4. **Target variable**: simulate direction (hold/hike/cut) or magnitude (bp)?
   FOMC in silico does magnitude; ECB accounts only reveal direction + dissent.
5. **Voting rights**: model the rotation system explicitly (needs the
   asterisk table from accounts, 2015+) or treat all attendees as voters?
6. **Hawkishness priors**: derive from speeches via LLM classification
   (Hansen–Kazinnik style) as agent priors — include in v1 memos or later?
7. **Memo audience**: current memos are neutral briefings; should they be
   written *in the voice of the member's institution* (e.g. Bundesbank-style
   conservatism) once profiles gain a tone dimension?

## Scope
8. **Simulation engine**: still being evaluated by the user (llm-pycascade,
   LangGraph-style orchestration, custom) — data layer is engine-agnostic.
9. **Evaluation harness**: which metrics matter most? (dissent rate, direction
   accuracy, rate-path RMSE, hawkishness correlation)

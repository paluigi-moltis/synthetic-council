# Literature review — LLM-based simulation of monetary policy committees

*Compiled 2026-08-21 via OpenAlex (keyword-relevance curated, N=95 entries in
`references.bib`, abstracts included where indexed). Companion file:
`references.bib`.*

## The anchor work

**Kazinnik & Sinclair (2025), "FOMC In Silico: A Multi-Agent System for Monetary
Policy Decision Modeling"** (SSRN 5424097; also GW econ WP 2025-005) is the main
reference for this project. It simulates the FOMC with two parallel tracks — an
LLM-based multi-agent deliberation and a Monte-Carlo generalized Bayesian voting
model — both seeded with *identical prior beliefs* about each committee member's
appropriate rate, formed from **real-time data and member profiles**. In a July
2025 FOMC replication both tracks land at the top of the 4.25–4.50% range (4.42%
LLM vs 4.38% MC); scenario shocks (political pressure, negative jobs revisions)
raise dissent and move rates within the range. Two design lessons we adopt: (i)
member-specific priors from real-time information sets (exactly what our memo
pipeline produces), and (ii) keeping a non-LLM behavioral benchmark alongside the
LLM agents for validation.

## Strands of the literature

### 1. LLM agents simulating committees and economic actors
- **Generative agents** (Park et al. 2023, UIST) — the architectural template:
  persona + memory + reflection; cited by virtually all committee simulators.
- **MiniFed** (Seok et al. 2024) — five-stage discussion/persuasion/voting
  pipeline reproducing realistic FOMC outcomes.
- **FedAgent** (2025) — institution-constrained deliberation; stresses that
  coarse cut/hold/hike labels miss *magnitude* disagreement.
- **Simulating the Survey of Professional Forecasters** (Hansen, Horton,
  Kazinnik, Puzzello, Zarifhonarvar 2026) — LLM agents reproducing forecast
  distributions; relevant to seeding agents with staff projections.

### 2. Measuring the policy stance in central-bank text
- **Hansen & Kazinnik (2024), "Can ChatGPT Decipher Fedspeak?"** — GPT
  translates and hawkish/dovish-classifies FOMC statements at human parity;
  the standard tool for calibrating memberhawkishness from speeches.
- Text-as-data hawkishness indices (multiple entries) — basis for deriving
  time-varying member priors from the speeches corpus we collect.
- ECB-specific communication studies (press-conference vs release impact,
  GC account tone) — several Economic Bulletin / journal entries in the bib.

### 3. GC/FOMC heterogeneity, voting and careers
- Empirical work on national-central-bank governor heterogeneity in the ECB GC
  (hawkish/dovish persistence, home-country macro conditions in voting) — the
  behavioural target our simulation must reproduce.
- FOMC dissent/voting studies — ground truth for dissent rates.

### 4. LLMs for macro forecasting and economics
- LLM macro-forecasting papers (nowcasting, expectation formation) — justify
  using vintage data + staff projections as agent inputs.

## Implications for synthetic-council design

1. **Information sets**: Kazinnik & Sinclair use real-time data + member
   profiles → our as-of vintage macro panel + per-member last speech is the
   direct analogue for the ECB GC.
2. **Profiles are role-consistent**: our membership data keeps (person, role)
   tenures separate (e.g. Draghi-BoI vs Draghi-President), matching the
   framework's member-profile priors.
3. **Benchmark**: keep a non-LLM voting model as a sanity baseline.
4. **Evaluation**: dissent frequency, rate-path distance, hawkishness drift —
   all measurable against accounts/decisions from 2015+.

## Gaps / questions for the user
- Whether to model the GC's rotation of voting rights explicitly (post-2015
  data allows it via accounts asterisks).
- Whether magnitude (bp) or direction (hold/hike/cut) is the target variable.

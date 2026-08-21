# Eurostat PEEI vintage database + macro sources

## Goal

For every ECB Governing Council monetary policy meeting, reconstruct the
macroeconomic information actually available at that date (true real-time
vintages, not revised data).

## PEEI vintages (Eurostat) — the core real-time source

The [PEEIs vintage database](https://ec.europa.eu/eurostat/cache/metadata/en/euroind_vtg_esms.htm)
("Euro indicators - vintages of data", theme `euroind_vtg`) stores every published
**revision** of three indicators, each keyed by a `revdate` dimension = the day the
vintage appeared on Eurostat's website:

| dataset | indicator | coverage | span |
|---|---|---|---|
| `ei_na_q_vtg` | Quarterly GDP (chain-linked volumes) | **EA and EU aggregates only** | vintages 2014-10 → today, ref quarters 1995-Q1+ |
| `ei_lm_m_vtg` | Monthly unemployment rate (ILO) | **38 geos incl. all EA countries** | vintages 2021-01 → today (ref months 1983+) |
| `ei_lm_m_vtgfix` | same, static | countries | vintages 2001 → 2020 |
| `ei_is_m_vtg` | Monthly industrial production | **countries + EA** | vintages 2021-01 → today (ref months 1980+) |
| `ei_is_m_vtgfix` | same, static | countries | vintages ≤2020 |

Discovery path (reproducible): the datasets are NOT listed under a `euroind_vtg`
dataflow id; enumerate them via the databrowser backend:

```
GET https://ec.europa.eu/eurostat/databrowser-backend/api/public/navtree/en/
    getProductPositionForCategory/general/euroind_vtg?notFullId=true&showProduct=all
→ codes: ei_is_m_vtg, ei_is_m_vtgfix, ei_lm_m_vtg, ei_lm_m_vtgfix, ei_na_q_vtg
```

Bulk download (works without auth; note `format=TSV` — JSON-stat 1.0 refuses these
datasets and SDMX-CSV needs version=2.0.0 + format params that the API rejects):

```
GET https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{ds}?format=TSV&compressed=true
→ gzip TSV, wide format: key-dims \ TIME_PERIOD columns, cell = value or ' :' flag
```

Vintage construction rule: for a meeting on date *d*, use for each reference period
the value from the latest vintage with `revdate <= d`. (The database stores only
changed series, so absent = unchanged; carry the last non-missing vintage forward.)

GDP vintages are published ≈ t+20/t+45/t+65/t+110 days after quarter end.

### Country GDP vintages — status

`ei_na_q_vtg` carries **EA/EU aggregates only**. Country-level quarterly GDP
vintages are not part of the PEEI set. Options (documented, not yet wired):
1. ECB RTD `M.S0.*` series (EA-only, with `includeHistory=true` release dates);
2. national real-time databases (per-NCB, heterogeneous);
3. latest-vintage country GDP with the t+20/45/65/110 Eurostat release calendar
   applied as an availability mask (approximation).

## Other series

| series | source | key | notes |
|---|---|---|---|
| HICP inflation (EA, true vintages) | ECB RTD | `RTD/M.S0.N.P_C_OV.X` + `includeHistory=true` | S0 = changing composition; history rows carry `ReleaseDate` |
| Key rates MRO/DFR/MLF daily | ECB SDMX FM | `D.U2.EUR.4F.KR.*.LEV` | verified 1999→2026 |
| CISS (systemic stress, daily) | ECB SDMX | dataflow `CISS`, `D.U2.Z0Z.4F.EC.SS_CIN.IDX` | NOT in FM (404); own dataflow since 2025; 1999→now |
| Unemployment rate EA monthly | ECB SDMX LFSI | `M.U2.S.UNEHRT.TOTAL0.15_74.T` | changing-composition U2 |
| Sentiment (ESI, consumer conf., sector confidence), EA + all countries | DG-ECFIN | `main_indicators_sa_nace2.zip` (monthly stamp) | wide xlsx, columns `EA.ESI`, `DE.CONS`, …; ~1985→now; DG-ECFIN publishes end-of-month |

### DG-ECFIN download URL pattern

```
https://ec.europa.eu/economy_finance/db_indicators/surveys/documents/series/
    nace2_ecfin_{YYMM}/main_indicators_sa_nace2.zip
```
Try the current month first, fall back to previous months (2608 empty as of
2026-08-21; 2607 OK).

## Release-lag assumptions (when true vintages are unavailable)

| indicator | availability at meeting |
|---|---|
| HICP | flash of month m-1 available at end of m → meetings in m see m-1 |
| unemployment | m-1 published ~end of m |
| industrial production | m-2 (6-week lag) |
| sentiment | reference month itself (published within month) |
| GDP | quarter q available if meeting ≥ q-end + 45d (t+45 vintage) |

## Verified (2026-08-21)

- `ei_na_q_vtg`: 526 rows (revdate × s_adj), vintages 2014-10-17 → 2026-07-30,
  ref quarters 1995-Q1 → 2026-Q2, units `CLV05_MEUR`, geos {EA, EU}.
- `ei_lm_m_vtg`: 38 geos incl. all EA members; revdates 2021-01 → now.
- `ei_is_m_vtg`: 23.6 MB uncompressed; geos incl. EA + countries; revdates 2021+.
- CISS: 7,214 daily obs 1999-01-01 → 2026-08-14.
- DG-ECFIN xlsx: 499 months × 246 series; EA.ESI… + all EA countries; ends 2026-07-31.

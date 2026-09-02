# MPD staff projections — complete information inventory

**Purpose**: single authoritative note of *everything* the ECB
Macroeconomic Projection database (MPD) offers, what we extract, and what goes
into the memos. Keep in sync with `src/synthetic_council/collectors/mpd_items.py`.

Source: `GET https://data-api.ecb.europa.eu/service/data/MPD?format=csvdata&startPeriod=2000`
(~33 MB, no key). Semantics: see `ecb-rtd-mpd.md`.

## Dimensions (bulk extract: 154,686 rows)

| dimension | values | notes |
|---|---|---|
| `FREQ` | A, Q | annual / quarterly paths |
| `REF_AREA` | U2 + country codes | U2 = euro area aggregate; country rounds (Jun/Dec) |
| `PD_ITEM` | 227 codes in CL_PD_ITEM | 44 have EA annual data; full codelist in DSD |
| `PD_SEAS_EX` | 110 round codes | {W,G,S,A}{yy} = Mar/Jun/Sep/Dec; `*99` = legacy |
| `TIME_PERIOD` | 1996→2028 | values before the round year = interpolated backdata |

Also available but unused: quarterly paths (FREQ=Q), country-level rounds
(June/December since 2001, ~20 economies), technical-assumption detail
(DG-AGRI food prices: CEREAL/DAIRY/FATS; competitors' import/export prices by
intra/extra-EA: CMD/CMDIN/CMDEX/CXD/CXDIN/CXDEX), fiscal detail (CPB/CYB
cyclically adjusted balances, FSTN fiscal stance, GYN government income),
income-side detail (GON gross operating surplus, WIN/WON wages), output-gap
variants, ETS2 carbon, EER12/EER19/EER38 NEER vintages.

## EA annual items used in the memo (44 known, all rendered when present)

Categories and units per official CL_PD_ITEM + ECB data-information page.

### Headline
| code | label | unit | coverage |
|---|---|---|---|
| HIC | HICP inflation | % | 110 rounds, 2000→ |
| YER | Real GDP growth | % | 110 rounds |
| URX | Unemployment rate | % of labour force | 110 rounds |

### Economic activity
| code | label | unit | rounds |
|---|---|---|---|
| PCR | Private consumption | % growth | 110 |
| GCR | Government consumption | % growth | 110 |
| ITR | Gross fixed capital formation | % growth | 110 |
| PYR | Real disposable household income | % growth | 12 |
| SAX | Household saving ratio | % | 12 |
| DDR | Domestic demand (excl. stocks) | % growth | 10 |
| SCR | Changes in inventories | pp of GDP | 10 |
| XTR | Exports (goods & services) | % growth | 110 |
| MTR | Imports (goods & services) | % growth | 110 |
| NER | Net exports | pp of GDP | 10 |
| CAN | Current account balance | % of GDP | 107 |

### Labour market
| code | label | unit | rounds |
|---|---|---|---|
| LNN | Total employment | % growth | 110 |

### Prices and costs
| code | label | unit | rounds |
|---|---|---|---|
| YED | GDP deflator | % growth | 13 |
| CEX | Compensation per employee | % growth | 110 |
| PRO | Productivity (whole economy) | % growth | 110 |
| UTAX | Unit taxes (whole economy) | % growth | 6 |
| ULA | Unit labour costs (whole economy) | % growth | 110 |
| UPFA | Unit profits (whole economy) | % growth | 12 |
| HEX | HICP ex energy | % | 105 |
| HEF | HICP ex food & energy | % | 69 |
| HEFT | HICP ex energy/food/ind. taxes | % | 52 |
| HIF | HICP food | % | 13 |
| HEG | HICP energy | % | 13 |
| HSE | HICP services | % | 2 |
| HNE | HICP non-energy industrial goods | % | 2 |

### Public finance
| code | label | unit | rounds |
|---|---|---|---|
| SED | Government budget balance | % of GDP | 104 |
| MAL | Government debt (Maastricht) | % of GDP | 110 |
| STB | Structural budget balance | % of GDP | 54 |

### External sector & technical assumptions
| code | label | unit | rounds |
|---|---|---|---|
| FOD | Foreign demand for EA exports | % growth | 99 |
| MTD | Import deflator | % growth | 13 |
| CPX | Competitor export prices (n.c.) | % growth | 12 |
| EERB | Nominal effective exchange rate EER38 | level | 43 |
| GAS | Gas price (TTF) | EUR/MWh | 17 |
| ELEC | Wholesale electricity price | EUR/MWh | 15 |
| ETS | EU carbon allowance (ETS) | EUR/t | 19 |
| LTN | Long-term interest rate (10y) | % | 100 |
| STN | Short-term interest rate (3m) | % | 100 |

Also in CL_PD_ITEM but **no EA annual observations** (skipped automatically):
EXR, GCD, GID, GIR, LAN, LAX, LEN, LFN, LNNM, LSN, OIL, YEG.

## Memo behaviour

- The memo shows **every item available in the round**, grouped by the
  categories above, forward-looking target years only (round year onward;
  MPD rows with `TIME_PERIOD` < round year are interpolated backdata).
- Availability varies by era: modern rounds carry ~35 items; pre-2016 rounds
  fewer (e.g. no HSE/HNE before 2024, no ETS/GAS/ELEC before ~2020).
- Annual values are averages of the quarterly projected path; published
  headline figures are rounded versions of these.

## Verification anchors (round code → published figures)

- W22 (Mar 2022): HICP 2022=5.1 ✓; A22 (Dec 2022): HICP 2022=8.4, 2023=6.3 ✓
- W23 (Mar 2023): HICP 2023=5.3 ✓; W24 (Mar 2024): HICP 2024=2.3 ✓
- G22 (Jun 2022): HICP 2023=3.5 ✓; G26 (Jun 2026): HICP 2026=3.0, GDP=1.2 ✓
- W26 (Mar 2026): HICP 2026=2.6, 2027=2.0, 2028=2.1 ✓
- Full check: 318/318 archive cells match (scripts validate via
  `docs/data-sources/ecb-rtd-mpd.md` method).

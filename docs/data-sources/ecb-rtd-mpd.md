# ECB Data Portal — Real-Time Database (RTD) and Macroeconomic Projection Database (MPD)

## RTD: true vintages for EA macro series

The ECB Data Portal hosts a **Real-Time Database** (dataflow `RTD`) with full
revision histories: pass `includeHistory=true` and each row becomes a *release
event* with `VALID_FROM` (release timestamp), `ACTION` (Replace/Delete). The
vintage visible on date *d* for reference period *p* = the row for *p* with the
latest `VALID_FROM <= d`.

```
GET https://data-api.ecb.europa.eu/service/data/RTD/{series}?format=csvdata&includeHistory=true
```

Series used here (euro area, changing composition `S0`):

| series | content | vintages | reference periods |
|---|---|---|---|
| `M.S0.N.P_C_OV.X` | HICP all-items index | 2001-01-03 → | 1997-01 → |
| `Q.S0.S.G_GDPM_TO_C.E` | GDP at market prices, chain-linked volumes, SA | 2001-01-03 → | 1995-Q1 → |

**Pitfalls verified during development:**

1. **Key format matters**: 4-component keys (`RTD/M.S0.N.P_C_OV.X`) work; malformed
   keys trigger the Data Portal WAF ("access blocked due to security concerns").
2. The RTD covers the **euro area aggregate only** (S0 = changing composition) —
   no country series with history.
3. 1999–2000 meetings have **no true HICP/GDP vintages** in any source we found
   (RTD starts 2001-01). Options: accept a shorter sample (2001+), or approximate
   the 1999–2000 information set with first-available vintages.
4. YoY growth from index levels must be computed **per release event**: for the
   event (p, t), divide level_t(p) by level_t(p−k) where level_t(q) is the latest
   release of q with revdate <= t — *not* the vintage-mate row (earlier quarters
   get revised on independent schedules). See
   `collectors/vintage_growth.py` (`vintage_growth`, `asof_growth`).

## MPD: staff macroeconomic projections

Full history of ECB/Eurosystem staff projection rounds:

```
GET https://data-api.ecb.europa.eu/service/data/MPD?format=csvdata&startPeriod=2000
→ ~33 MB CSV
```

- **Round codes** (`PD_SEAS_EX`): `{W,G,S,A}{yy}` = **M**arch, **June**,
  **September**, **December** of 20yy. Verified against published rounds:
  W22 HICP 2022=5.1, W23 2023=5.3, W24 2024=2.3, G22 2023=3.5,
  A22 2022=8.4/2023=6.3, G26 2026≈3.0. `*99` codes are legacy/undatable.
- **Item codes** (`PD_ITEM`, official codelist `CL_PD_ITEM` via
  `GET .../service/dataflow/ECB/MPD/latest?references=all`): key items
  `HIC` = HICP overall, `YER` = real GDP, `URX` = unemployment rate,
  `PCR` = private consumption, `DDR` = domestic demand excl. stocks.
  ⚠️ Intuitive guesses are wrong: DDR ≠ unemployment, PCR ≠ GDP.
- `REF_AREA=U2` = euro area; `FREQ=A` annual, `Q` quarterly.
- **Annual values are averages of the quarterly projected path** (long decimals);
  published headline figures are these rounded. Rows with `TIME_PERIOD` < round
  year are interpolated backdata, not forecasts — exclude them.
- Cross-validation: 318/318 round×item×year cells match the official archive
  page <https://www.ecb.europa.eu/mopo/devel/ecana/html/table.en.html> within
  rounding (scrape script: `scripts/validate_mpd.py`).

## Related decisions

- EA GDP vintages: RTD (2001→) is the primary source; Eurostat PEEI
  `ei_na_q_vtg` (2014-10→) retained for cross-checking only.
- Announcement dates pre-2015: see `ecb-foedb.md` § "off-by-one timestamps".

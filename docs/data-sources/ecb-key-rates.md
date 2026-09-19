# ECB key interest rates — MRO fixed rate vs minimum bid rate

## The series and its gap

The pipeline derives decision levels from the ECB Data Portal (FM dataflow)
daily series in `config.KEY_RATE_SERIES`:

| name | key | meaning |
|---|---|---|
| `mro` | `FM.D.U2.EUR.4F.KR.MRR_FR.LEV` | MRO fixed-rate tender rate |
| `mro_mbr` | `FM.D.U2.EUR.4F.KR.MRR_MBR.LEV` | MRO minimum bid rate (variable-rate tenders) |
| `dfr` | `FM.D.U2.EUR.4F.KR.DFR.LEV` | deposit facility rate |
| `mlf` | `FM.D.U2.EUR.4F.KR.MLFR.LEV` | marginal lending facility rate |

**Critical pitfall (found in the 2026-09 review):** `MRR_FR` does not exist
for **2000-06-28 → 2008-10-14**. On 8 June 2000 the ECB announced that, from
the operation settled on 28 June 2000, MROs would be conducted as *variable
rate tenders* — there is no fixed rate, and the operative policy rate was the
**minimum bid rate** (`MRR_MBR`). Fixed-rate tenders returned on 15 October
2008 (full allotment, decision of 8 October 2008).

Verified live:
- `MRR_FR` has observations 1999-01-01 → 2000-06-27 and 2008-10-15 → today;
  nothing in between (3,031-day hole).
- `MRR_MBR` has observations exactly on 2000-06-28 → 2008-10-14.
- Handshake is clean: `MRR_MBR` last value 4.25 (2008-10-14), `MRR_FR` first
  value 3.75 (2008-10-15) — the 8 Oct cut took effect 9/15 Oct.

## The splice

`rates.fetch_key_rates()` fetches both series and `rates.splice_mro_mbr()`
coalesces them into a single `mro` column (fixed rate wins where it exists,
min bid rate fills the gap). The raw fixed-rate series is kept as `mro_fr`
for provenance. Rates on the ECB's historical
[key rates table](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html)
show the same structure: one of the two MRO columns is always `-` (n/a).

## Bugs this caused before the fix

1. `gc_decisions.parquet`: null MRO levels for 118 decisions in the gap
   window; 21 rate changes in that window were invisible to change detection
   (only DFR/MLF changes were seen).
2. `rates.fetch_rate_change_table()`: the HTML parser only matched dates in
   `cells[0]`, dropping the ~30 continuation rows whose year cell is blank
   (`&nbsp;`) — which wiped out the entire 2000–2003 change history from the
   cross-check table. The parser now locates the date cell wherever it sits.
3. `decisions_from_daily_rates()`: null-vs-value transitions compared with
   `!=` evaluate to null and were filtered out; change detection is now
   null-aware (`ne_missing` + explicit null checks on both sides).
4. `memo.py`: null rate levels rendered as `0%` (via `x or 0`); now `n/a`.

Regression tests: `tests/test_rates_mro_gap.py`.

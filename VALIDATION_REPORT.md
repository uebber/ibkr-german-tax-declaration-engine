# Test Suite Validation Report

**Date:** 2026-04-04
**Scope:** Complete test suite cross-checked against curated reference library (`reference/`)
**Method:** Every test file's assertions compared against authoritative German tax law sources (EStG, InvStG, BMF-Schreiben, official form instructions)

---

## Confirmed Errors

### 1. Derivative Loss Cap Still Applied for Tax Year 2024 -- RESOLVED

**Status:** fixed. `derivative_loss_cap_applies` is now False for every year in
`src/tax_law/registry.py`, and the four fixture expectations below carry the
values this finding predicted. The application rule is quoted verbatim in
`reference/tax-law/estg-20-abs6-verlustverrechnung.md`: 52 Abs. 28 Satz 25 EStG
n.F., *"ist auf alle offenen Faelle nicht mehr anzuwenden"*. The description
below is kept as the original finding.

**Severity:** HIGH
**Legal basis:** EStG 20 Abs. 6 Satz 5 a.F., abolished by JStG 2024 (BGBl. I 2024 Nr. 387, Art. 1 Nr. 10)
**Reference file:** `reference/tax-law/estg-20-abs6-verlustverrechnung.md`

The EUR 20,000 annual cap on derivative losses (Verlustverrechnungsbeschraenkung fuer Termingeschaefte) was abolished with **retroactive effect to all open cases** (52 Abs. 28 EStG n.F., effective 02.12.2024). Tax year 2024 is an open case at that date, so the cap must not apply.

**Affected code:**
- `src/reporting/form_rules.py:41` -- `derivative_loss_cap_applies=True` for 2024 (should be `False`)
- `src/config.py:76` -- `APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING: bool = True` (default compounds the issue)

**Affected test expectations** (all in `tests/fixtures/loss_offsetting_data.py`):

| Test ID | Field | Current Value | Correct Value | Line |
|---------|-------|---------------|---------------|------|
| LO_TERM_004 | `conceptual_net_derivatives_capped` | `-20000.00` | `-30000.00` | 254 |
| LO_TERM_007 | `conceptual_net_derivatives_capped` | `-20000.00` | `-25000.00` | 318 |
| LO_MIX_002 | `conceptual_net_derivatives_capped` | `-20000.00` | `-29000.00` | 594 |
| LO_MIX_004 | `conceptual_net_derivatives_capped` | `-20000.00` | `-25000.00` | 646 |

The form line values (Z24) are unaffected -- they always report gross uncapped amounts. Only the conceptual summary field is wrong.

---

### 2. `is_taxable_under_section_23` Incorrectly Defaults to True

**Severity:** LOW (no current calculation impact)
**Legal basis:** Options/stocks/bonds/funds are taxed under EStG 20, not EStG 23
**Reference file:** `reference/tax-law/estg-20-kapitalvermoegen.md`

In `src/engine/fifo_manager.py`, the `is_taxable_under_section_23_flag` defaults to `True` at three locations (lines 608, 732, 879) and is only corrected for `AssetCategory.PRIVATE_SALE_ASSET`. For all other categories (STOCK, BOND, OPTION, CFD, INVESTMENT_FUND), the flag remains `True` -- semantically wrong.

Additionally, `src/engine/event_processors/option_processor.py:223` explicitly sets `is_taxable_under_section_23=True` for option expiration RGLs, with a comment acknowledging the contradiction: "Options are Termingeschaefte, not 23".

**Why low impact:** The loss offsetting engine (`src/engine/loss_offsetting.py:99-101`) only checks this flag when `asset_category_at_realization == AssetCategory.PRIVATE_SALE_ASSET`, so the incorrect default does not affect tax calculations. However, it would cause incorrect behavior if the guard logic changes in the future.

---

### 3. Stock Dividend Tax Treatment May Be Incorrect

**Severity:** MEDIUM
**Legal basis:** EStG 20 Abs. 4a Satz 5
**Reference file:** `reference/tax-law/estg-20-kapitalvermoegen.md`

`tests/test_dividend_handling.py:367-460` (test_d05) treats a stock dividend ("SD" corporate action type) as:
- Taxable income of EUR 349 (FMV of received shares)
- New FIFO lot with cost basis = FMV (EUR 34.90 per share)

EStG 20 Abs. 4a Satz 5 states: shares allocated by a foreign corporation **without consideration** (ohne Gegenleistung) have **income = EUR 0** and **acquisition cost = EUR 0**. The original shares' cost basis remains unchanged.

The correct treatment depends on the nature of the corporate action:

| Type | German Term | Income | Cost Basis | Statutory Ref |
|------|-------------|--------|------------|---------------|
| Bonus shares from capital increase | Gratisaktien | EUR 0 | EUR 0 | 20 Abs. 4a Satz 5 |
| Scrip dividend (distribution in shares) | Sachdividende | FMV | FMV | 20 Abs. 1 Nr. 1 |

The test does not clearly distinguish which scenario it models. If IBKR's "SD" corporate action represents a Gratisaktie (which is the more common interpretation for "STOCK DIVIDEND" in IBKR's terminology), the test expectations and the `StockDividendProcessor` cost basis assignment are both wrong.

**Recommendation:** Clarify with IBKR documentation or real examples whether "SD" type stock dividends represent bonus shares (Gratisaktien) or scrip dividends (Sachdividenden). Adjust treatment accordingly, potentially requiring two separate code paths.

---

## Potential Errors

### 4. Negative Dividends and Interest Silently Ignored

**Severity:** MEDIUM
**Location:** `src/engine/loss_offsetting.py:121-126`
**Reference:** Dividend corrections, reversals, and payment-in-lieu adjustments can produce negative amounts.

The loss offsetting engine only accumulates **positive** dividend and interest amounts:

```python
if event.event_type == FinancialEventType.DIVIDEND_CASH and ...:
    if event_gross_eur > Decimal('0'):          # <-- negative amounts skipped
        kap_other_income_positive = ...
elif event.event_type == FinancialEventType.INTEREST_RECEIVED:
    if event_gross_eur > Decimal('0'):          # <-- negative amounts skipped
        kap_other_income_positive = ...
```

Negative dividends (e.g., dividend corrections, reversals) are silently discarded, which would **overstate Z19** (Auslaendische Kapitalertraege). No test covers this scenario.

---

### 5. Vorabpauschale: Partial Year Reduction Not Implemented

**Severity:** MEDIUM
**Location:** `src/engine/calculation_engine.py:703-830`
**Legal basis:** InvStG 18 Abs. 3
**Reference file:** `reference/investment-tax-law/invstg-18-vorabpauschale.md`

InvStG 18 Abs. 3 requires the Vorabpauschale to be reduced by 1/12 for each **full calendar month** before the month of acquisition within the tax year. For example, a fund acquired in April would have VP reduced by 3/12 (January, February, March).

The implementation contains:
- No acquisition date tracking for fund positions
- No monthly proration logic
- No test coverage for this scenario

This means funds acquired mid-year will have an **overstated Vorabpauschale**.

---

### 6. Cross-Year Option Premium Timing (Zuflussprinzip)

**Severity:** LOW (test coverage gap, not an assertion error)
**Location:** `src/engine/event_processors/option_processor.py:132-230`
**Legal basis:** EStG 20 Abs. 1 Nr. 11, EStG 11 (Zuflussprinzip)
**Reference file:** `reference/tax-law/estg-20-kapitalvermoegen.md`

EStG 20 Abs. 1 Nr. 11 provides that Stillhalterpraemien (option premiums received by the writer) are taxable **upon receipt**. The engine uses a lot-based approach that defers premium recognition until position close (expiration, assignment, or buy-to-close).

For options opened and closed in the same tax year, the net result is identical. For options **spanning tax years** (sold in year N, closed in year N+1), the premium income is attributed to the wrong year.

All Group 8 test specs (`tests/fixtures/group8_options.yaml`) use dates within 2023 only -- no cross-year scenario exists. This is a coverage gap rather than an incorrect assertion.

---

## Verified Correct

The following areas were validated against the reference library and found to be correct:

### Teilfreistellung Rates (InvStG 20)
All five rates in `src/utils/tax_utils.py` match the statutory provisions exactly:

| Fund Type | Code Rate | Reference Rate | Statutory Ref |
|-----------|-----------|---------------|---------------|
| Aktienfonds | 30% | 30% | InvStG 20 Abs. 1 S. 1 |
| Mischfonds | 15% | 15% | InvStG 20 Abs. 2 |
| Immobilienfonds | 60% | 60% | InvStG 20 Abs. 3 S. 1 Nr. 1 |
| Auslands-Immobilienfonds | 80% | 80% | InvStG 20 Abs. 3 S. 1 Nr. 2 |
| Sonstige Fonds | 0% | 0% | (no provision) |

Symmetric application for negative amounts (loss reversal) is tested and correct.

### Vorabpauschale Formula (InvStG 18)
- Basisertrag = SoY x Basiszins x 0.70 -- correct (calculation_engine.py:778)
- Basisertrag capped at value gain (EoY - SoY) -- correct (calculation_engine.py:792-795)
- VP = max(0, Basisertrag - distributions) -- correct (calculation_engine.py:786-790)
- Negative distributions excluded from reduction -- correct
- Basiszins 2024 = 2.29% -- correct per BMF 02.01.2024

### Anlage KAP Form Lines Z19-Z24
**2024 formula** (separate_derivative_lines = True):
- Z19 = stock_g - stock_v + other_g - other_v + deriv_g (derivative losses NOT subtracted) -- correct
- Z20 = gross stock gains -- correct
- Z21 = gross derivative gains -- correct
- Z22 = other losses (non-stock, non-derivative only) -- correct
- Z23 = stock losses (absolute) -- correct
- Z24 = derivative losses (absolute, uncapped for form) -- correct

**2025 formula** (separate_derivative_lines = False):
- Z19 now subtracts derivative losses -- correct
- Z21 = 0.00, Z24 = 0.00 (lines removed) -- correct
- Z22 includes derivative losses -- correct

All 28 loss offsetting test cases (LO_ALL_001 through LO_FUND_MISCH_002) were spot-checked against the reference Z19 formula. All Z19, Z20-Z24, and Z54 assertions are arithmetically correct (apart from the derivative cap issue in finding 1).

### Other Verified Areas

| Area | Reference | Verdict |
|------|-----------|---------|
| Z55 = sum of gross VP (before TF) | InvStG 19 Abs. 1 S. 3-4 | Correct |
| KAP-INV amounts reported as gross | anlage-kap-inv-zeilen.md | Correct |
| Fund income isolated from Z19 | InvStG 16 | Correct |
| WHT sign convention (positive for Z41) | EStG 32d Abs. 5 | Correct (parser uses copy_abs) |
| FX gains/losses mapped to 20 EStG | BMF fremdwaehrung-konten.md | Correct |
| Stock loss ring-fencing (Z23 separate) | EStG 20 Abs. 6 S. 4 | Correct |
| Stock-for-stock merger tax-neutral | EStG 20 Abs. 4a S. 1-2 | Correct |
| Cash merger = taxable disposal | EStG 20 Abs. 2 Nr. 1 | Correct |
| FIFO method per asset per depot | EStG 20 Abs. 4 | Correct |
| 23 EStG losses isolated from 20 EStG | EStG 23 Abs. 3 S. 7-8 | Correct |
| 2025 form rules (derivative lines removed) | anlage-kap-zeilen.md | Correct |

---

## Summary

| # | Finding | Severity | Type |
|---|---------|----------|------|
| 1 | Derivative loss cap applied for 2024 (abolished retroactively) | HIGH | Test + code error -- RESOLVED |
| 2 | `is_taxable_under_section_23` defaults True for non-23 assets | LOW | Code error (dormant) |
| 3 | Stock dividend treated as taxable income (may conflict with Satz 5) | MEDIUM | Ambiguous test |
| 4 | Negative dividends/interest ignored in loss offsetting | MEDIUM | Missing handling |
| 5 | Vorabpauschale partial year reduction not implemented | MEDIUM | Missing feature |
| 6 | Cross-year option premium timing not tested | LOW | Coverage gap |

---

# Real-data validation log

Ledger reconciliation and output parity against the maintainer's own IBKR export. Instance data —
holdings, identifiers, amounts — stays in gitignored working copies; only outcomes are recorded here.

## 2026-08-07

**Supersedes the 2026-08-06 row reading "2024 | aborts on
`VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN`".** Issue #56 — the root cause recorded below — is
fixed on this branch by `efb0d97` (a historical merger applies at its own date) and `13f6b6d`
(reconcile at every yearly snapshot). **VZ 2024 no longer aborts there.**

| VZ | Result |
|---|---|
| 2023 | **runs clean**, and declares **no Vorabpauschale**: it carries calendar 2022, whose Basiszins was −0.05 % — negative, so none arises. Zeilen 9–13 all zero. |
| 2024 | aborts **earlier than before**, during classification |
| 2025 | aborts during classification |

**Both remaining runs stop on the same instrument** — `CONID:69067924` / `XAUUSD` / `CMDTY` has
category `UNKNOWN` and cannot be auto-classified, so `DataIntegrityError` fires before any figure
is produced. The classification it needs is Q11 Reading C, a sonstige Kapitalforderung under
§ 20 Abs. 2 Satz 1 Nr. 7, and no such category exists: **issue #53.** VZ 2024 and VZ 2025 are also
the first two years in which a Vorabpauschale can be non-zero at all.

**But #53 is not the only thing between here and those two declarations, and an earlier version of
this entry said it was.** The classification cache was rebuilt on 2026-08-07 against a VZ 2023 run,
so it covers that year's instruments and no others. Measured by comparing cache keys against the
instruments each year's window contains:

| VZ | instrument keys in window | not in cache | composition of the uncached |
|---|---|---|---|
| 2023 | 169 | **0** | — |
| 2024 | 265 | **96** | 68 `OPT`, 24 `STK`, 1 `CMDTY`, 1 `CASH`, 2 blank |
| 2025 | 408 | **239** | 175 `OPT`, 58 `STK`, 1 `CMDTY`, 3 `CASH`, 2 blank |

Only about three per year refuse outright and stop the run. **The quieter risk is the `STK`
rows:** they auto-classify to `STOCK` without prompting, and this account's fund descriptions
contain no "ETF" marker, so a fund among them is silently declared as a share — wrong form lines
and no Teilfreistellung, with nothing failing. Both years therefore need an interactive
classification pass, not just #53.

**Not re-verified, and not claimed:** whether the Swiss Gold Vorabpauschale chain is now clean.
The run stops before reaching it.

**The input carries no duplicate trade rows.** Measured across `Trades-2021.csv` …
`Trades-2025.csv`: 6 976 rows, 6 976 distinct `TransactionID`s, none repeated within a file or
across files. A working note had described the VZ 2024 failure as caused by "duplicated 2022 trade
rows"; that is wrong, and the 2026-08-06 entry below already states the correct mechanism —
phantom units from replay *ordering*, not from the input.

**Classification cache.** Destroyed on this date by the clean-clone protocol
(`rm -rf cache`, see issue #51) and rebuilt by the maintainer. `XAUUSD` was not reclassified,
which is why the two aborts above are reachable. No other run state was lost.

## 2026-08-06

**Supersedes the 2026-08-05 statement that "VZ 2023 cannot be computed and VZ 2022 cannot be run
at all."** The snapshots called absent that day are present in `data_import/` now, and the
picture has moved. Measured by running the full pipeline for each year and reading the logs; the
working tree carried unrelated in-flight Vorabpauschale changes at the time.

| VZ | Result |
|---|---|
| 2021 | cannot be run — `Positions-2020-EoY.csv` absent, and it is the opening position |
| 2022 | aborts on `VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING` (needs `Positions-2021-SoY.csv`) |
| 2023 | **runs clean** |
| 2024 | aborts on `VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN` |
| 2025 | **runs clean** |

**How far back the ledger depends on data we do not have.** The 2021-01-01 opening quantities
were derived (EoY-2021 snapshot minus every 2021 trade, corporate action and option
exercise/expiry) and real FIFO replayed over every observed event. Five securities carried a
pre-2021 tranche; four clear during 2021, the last on **2022-04-07**. Sixteen option contracts
open at 2021-01-01 all expired by 2021-07-23. From 2022-04-07 every lot in every securities
ledger traces to a recorded trade, so **VZ 2023 is the first assessment year whose opening lots
are all observed** — which is the measurement behind the VZ 2023 floor now stated in `CLAUDE.md`.

Currency ledgers are a separate matter: they take a `SOY_RECONCILIATION_*` plug lot dated
`{tax_year-1}-12-31` whenever cash FIFO disagrees with the reported balance, by design and every
year. Two currencies still carry a constant residual in VZ 2025.

**The VZ 2024 abort is a defect, not a data gap.** A stock-for-stock merger delivers its lots
after every trade in the historical window, so shares sold on the merger date oversell against a
ledger that does not hold them yet; the reconstruction ends up over the reported SoY by exactly
the transferred quantity, reconciliation discards it, and the synthesised lot has no real
acquisition date for § 18 Abs. 2 InvStG. Filed as issue #56. This one is independent of the
pre-2021 gap and would fire on any merger whose shares are disposed of inside the replay window.

## 2026-08-05

**Ledger reconciliation** (`validate_ledgers.py`), 3 assessment years tested:

| VZ | Result | Assets | RGL records |
|---|---|---|---|
| 2023 | **FAIL** — expected | — | — |
| 2024 | **PASS** | 276 | 6 346 |
| 2025 | **PASS** | 421 | 4 128 |

**Asset EOY mismatches: 0.** The SoY → EoY invariant holds on real input for every year that can
be computed.

**Currency EOY mismatches: 0 — and that verdict is vacuous for VZ 2024.** A cash-balance export
exists for 2025 only, so for 2024 the currency check has nothing to compare the ledger against and
reports zero because it compared nothing. Read the currency result as meaningful for VZ 2025 and
as *unmeasured* for VZ 2024. Supplying `Cash_Balance-2024.csv` would make it real.

### Provenance of the position snapshots

`Positions-2023-*` and `Positions-2024-*` were recovered from older working trees on 2026-08-03
and identified **by content, not by filename** — filenames in those trees are unreliable, one
labelled as end-of-2024 being in fact end-of-2025. The verification anchor was that the recovered
EoY-2024 matches the authoritative `Positions-2025-SoY.csv` symbol for symbol.

**No snapshot exists anywhere for end-2021 / start-2022.** That is why VZ 2023 cannot be computed
and why VZ 2022 cannot be run at all, and it is a property of the available input rather than
something a code change can fix.

VZ 2023 fails on `VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING` and the failure is correct: the
Vorabpauschale declared in VZ 2023 is the one computed for calendar 2022 (§ 18 Abs. 3 InvStG), and
the 2022 position snapshots are genuinely absent from the input. This is a data gap, not a defect.
Supplying `Positions-2022-SoY.csv` and `Positions-2022-EoY.csv` would close it.

Until this run the validator had been unable to validate any year since 2026-08-03; it called the
pipeline without the prior-year snapshot paths and reported the cause as missing files.

**Output parity**, German-KESt fix on Anlage KAP Zeile 41:

| Capture | Result |
|---|---|
| Control, same tree twice, VZ 2024 | console, log and PDF IDENTICAL |
| Pre- vs post-fix, **VZ 2024** | 3 console lines changed — intended |
| Pre- vs post-fix, **VZ 2025** | console and PDF IDENTICAL |

VZ 2024 moves exactly as designed: Zeile 41 falls by the amount of one withholding row identified
as German Kapitalertragsteuer, and a data-gap line appears naming that amount and the
Steuerbescheinigung requirement. The reduction equals the excluded row to the cent. VZ 2025 does
not move, because every withholding row that year carries a non-German issuer country and is
correctly retained as foreign tax.

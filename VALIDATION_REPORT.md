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

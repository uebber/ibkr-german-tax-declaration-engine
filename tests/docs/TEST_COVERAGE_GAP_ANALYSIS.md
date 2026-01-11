# Test Coverage Gap Analysis

## Overview

This document analyzes the test suite's coverage of typical pitfalls in complex tax calculations, based on research of the codebase structure, PRD requirements, and the Legal Validation Report (1Q25).

**Analysis Date:** 2026-01-11
**Last Updated:** 2026-01-11
**Test Groups Reviewed:** Groups 1-6, plus dividend handling tests (66+ validated scenarios per Legal Validation Report)

---

## Summary Table

| Pitfall Category | Coverage | Risk Level | Notes |
|-----------------|----------|------------|-------|
| FIFO Lot Ordering | Good | Low | Groups 1-5 extensively test FIFO scenarios |
| SOY/EOY Reconciliation | Good | Low | Tested with mismatch error counting |
| Loss Offsetting Rules | Good | Low | Group 6 covers stock/derivative/other pots |
| Negative Position Protection | Good | Low | Code raises ValueError on insufficient lots |
| Corporate Actions (Splits/Mergers) | Partial | **MEDIUM** | Stock dividends tested; splits/mergers GAP |
| Option Exercise/Assignment | Gap | **HIGH** | Premium adjustments not tested |
| Currency Conversion Timing | **Good** | Low | ✅ Variable FX rates now supported via `MockECBExchangeRateProvider` |
| Rounding/Precision Accumulation | **Good** | Low | ✅ `test_precision.py` stress-tests many-lot accumulation |
| Fund Type Teilfreistellung | **Good** | Low | ✅ All fund types tested (30%, 15%, 60%, 80%, 0%) |
| Capital Repayments / Cost Basis Reduction | **Good** | Low | ✅ `test_dividend_handling.py` covers via dividend rights |
| Short Position Handling | Partial | Low | SOY shorts tested, limited intra-year |
| Holding Period Boundaries | **Good** | Low | ✅ §23 EStG boundary tests in Group 5 |
| Multi-Lot Sale Splitting | Good | Low | Groups test FIFO across multiple lots |
| Historical Trade Reconstruction | Good | Low | SOY initialization from historical trades tested |
| Stock Dividend FIFO Lot Creation | **Good** | Low | ✅ `test_dividend_handling.py` covers FMV cost basis |
| Dividend Rights Expiry | **Good** | Low | ✅ `test_dividend_handling.py` covers DI/ED actions |

---

## Detailed Analysis

### 1. FIFO Lot Ordering (Coverage: Good)

**What Could Go Wrong:**
- Lots consumed out of acquisition order
- Date parsing inconsistencies
- Same-day trade ordering ambiguity

**Current Coverage:**
- Groups 1-5 extensively test FIFO scenarios
- Test helpers support `time` field for same-day ordering
- Code sorts lots by `(acquisition_date, source_transaction_id)`

**Recommendation:** None - well covered.

---

### 2. SOY/EOY Position Reconciliation (Coverage: Good)

**What Could Go Wrong:**
- Computed EOY quantity differs from broker report
- Missing positions not detected
- Extra positions not flagged

**Current Coverage:**
- `expected_eoy_mismatch_error_count` in test specs
- `FifoTestCaseBase.assert_results()` checks mismatch counts
- Test scenarios include explicit EOY quantity expectations

**Recommendation:** None - well covered.

---

### 3. Loss Offsetting Rules (Coverage: Good)

**What Could Go Wrong:**
- Stock losses incorrectly offsetting non-stock gains
- Derivative 20k cap misapplied
- Form line values incorrect

**Current Coverage:**
- Group 6 (`test_group6_loss_offsetting.py`) covers:
  - Stock pot isolation (akt_g/akt_v)
  - Derivative pot with 20k cap conceptual tracking
  - Fund income isolation from Z19
  - 23 EStG separate pot

**Recommendation:** None - well covered by spec-driven tests.

---

### 4. Corporate Actions - Splits/Mergers/Dividends (Coverage: PARTIAL)

**What Could Go Wrong:**
- Split ratio applied incorrectly to quantity
- Cost basis per share not recalculated after split
- Cash merger proceeds not using correct per-share value
- Stock dividend FMV not applied as cost basis
- Dividend rights not properly linked to underlying stock
- Tax-free dividend not reducing cost basis correctly

**Current Coverage:**
- `fifo_manager.py` has full implementation:
  - `adjust_lots_for_split()` - **NOT TESTED**
  - `consume_all_lots_for_cash_merger()` - **NOT TESTED**
  - `add_lot_for_stock_dividend()` - ✅ **TESTED via test_dividend_handling.py**
  - `reduce_cost_basis_for_capital_repayment()` - ✅ **TESTED via test_dividend_handling.py**

- ✅ `tests/test_dividend_handling.py` provides comprehensive dividend handling coverage (6 tests):
  - `test_dividend_rights_fifo_adjustment_via_sale_gains`: Tax-free dividend rights (DI/ED) adjusting first FIFO lot cost basis
  - `test_dividend_rights_first_fifo_lot_to_zero_second_reduced`: Dividend reducing first lot to zero, second lot partially reduced
  - `test_d05_stock_dividend_fifo_lot_creation_and_tax_impact`: Stock dividend (SD) creating new FIFO lot with FMV as cost basis + taxable income
  - `test_dividend_rights_both_fifo_lots_to_zero_with_tax_impact`: Both lots going to zero with excess becoming taxable income
  - `test_dividend_rights_payment_in_lieu_fifo_adjustment_via_sale_gains`: "Payment In Lieu Of Dividends" transaction type handling
  - `test_dividend_rights_both_fifo_lots_to_zero_with_tax_impact_abc`: Variant with different asset symbols

**Risk Level:** MEDIUM (stock dividends well covered; splits/mergers still gap)

**Remaining Gap:** Create tests for splits and mergers:
```yaml
# Example test cases still needed:
- CA_SPLIT_001: 2:1 split adjusts quantity and cost/share
- CA_SPLIT_002: Fractional split ratio (3:2)
- CA_MERGER_001: Cash merger realizes all lots
```

---

### 5. Option Exercise/Assignment (Coverage: GAP)

**What Could Go Wrong:**
- Call exercise: Premium not added to stock cost basis
- Put assignment: Premium not added to stock cost basis
- Option lot not consumed when exercised
- Multiplier (100 shares/contract) miscalculated

**Current Coverage:**
- `fifo_manager.py` has:
  - `consume_long_option_get_cost()`
  - `consume_short_option_get_proceeds()`
  - `asset_multiplier_info` for options
- `option_trade_linker.py` exists for linking
- **NO dedicated test group for option lifecycle found**

**Risk Level:** HIGH

**Recommendation:** Create Group 8 for options:
```yaml
# Example test cases needed:
- OPT_CALL_EXERCISE_001: Long call exercise, premium added to stock cost
- OPT_PUT_ASSIGN_001: Short put assigned, premium reduces stock cost
- OPT_EXPIRE_001: Worthless expiration realizes full loss
- OPT_CLOSE_001: Closing trade with FIFO lot matching
```

---

### 6. Currency Conversion Timing (Coverage: Good) ✅ ADDRESSED

**What Could Go Wrong:**
- Wrong ECB rate date used (should be transaction date)
- Weekend/holiday rate lookup failing
- Rate caching issues across sessions

**Current Coverage:**
- ✅ `MockECBExchangeRateProvider` enhanced with date-based variable rates
- ✅ New `tests/test_mock_providers.py` with comprehensive coverage:
  - `TestConstantRateProvider`: Backward compatibility tests
  - `TestVariableRateProvider`: Date-based rate schedules
  - `TestMultiCurrencyProvider`: Currency-specific rate progressions
  - `TestEdgeCases`: Same-day rate changes, old/future dates
- ✅ Factory functions: `create_constant_rate_provider()`, `create_variable_rate_provider()`, `create_multi_currency_provider()`
- Production code uses `ECBExchangeRateProvider` with real rates

**Risk Level:** Low

**Example Usage:**
```python
from tests.helpers.mock_providers import create_variable_rate_provider

provider = create_variable_rate_provider([
    (date(2023, 1, 1), Decimal("1.05")),   # 1 USD = 1.05 EUR from Jan 1
    (date(2023, 6, 1), Decimal("1.10")),   # 1 USD = 1.10 EUR from Jun 1
])
```

---

### 7. Rounding/Precision Accumulation (Coverage: Good) ✅ ADDRESSED

**What Could Go Wrong:**
- Small rounding errors accumulating over many lots
- Final total differs from sum of parts
- Quantization applied inconsistently

**Current Coverage:**
- ✅ Code uses `INTERNAL_CALCULATION_PRECISION = 28`
- ✅ `FifoLot.__post_init__` validates total vs qty*unit
- ✅ New `tests/test_precision.py` with comprehensive stress tests:
  - `TestFifoLotPrecision`: Fractional quantities, repeating decimals, very small/large values
  - `TestShortFifoLotPrecision`: Short position precision validation
  - `TestDecimalPrecision`: Addition/multiplication precision, commission allocation
  - `TestManyLotsAccumulation`: 12 monthly lots, 100 lots accumulation
  - `TestGainLossCalculationPrecision`: Small profits on large positions, breakeven accuracy
  - `TestEdgeCases`: 28-decimal precision, penny stocks, crypto satoshi-level amounts

**Risk Level:** Low

**Test Examples:**
- 12 monthly fractional lots (0.333 qty @ 100.10/unit) with exact sum verification
- 100 lots accumulated with no precision drift
- Repeating decimal cost basis (100/3) handling

---

### 8. Fund Type Teilfreistellung Rates (Coverage: Good) ✅ ADDRESSED

**What Could Go Wrong:**
- Aktienfonds using wrong 30% rate
- Mischfonds 15% rate not applied
- Immobilienfonds 60%/80% distinction incorrect
- Fund type changing mid-year

**Current Coverage:**
- ✅ Group 6 (`tests/specs/group6_loss_offsetting.py`) now covers all fund types:
  - `LO_FUND_001/002`: Aktienfonds (30% TF) - gains and losses
  - `LO_FUND_MISCH_001`: Mischfonds with 15% TF
  - `LO_FUND_MISCH_002`: Mischfonds loss with 15% TF
  - `LO_FUND_IMMO_001`: Immobilienfonds with 60% TF
  - `LO_FUND_AUSLAND_001`: Auslands-Immobilienfonds with 80% TF
  - `LO_FUND_SONST_001`: Sonstige Fonds with 0% TF
- `get_teilfreistellung_rate_for_fund_type()` in code

**Risk Level:** Low

**Fund Type Coverage:**
| Fund Type | TF Rate | Test ID |
|-----------|---------|---------|
| Aktienfonds | 30% | LO_FUND_001, LO_FUND_002 |
| Mischfonds | 15% | LO_FUND_MISCH_001, LO_FUND_MISCH_002 |
| Immobilienfonds | 60% | LO_FUND_IMMO_001 |
| Auslands-Immobilienfonds | 80% | LO_FUND_AUSLAND_001 |
| Sonstige Fonds | 0% | LO_FUND_SONST_001 |

---

### 9. Capital Repayments / Cost Basis Reduction (Coverage: Good) ✅ ADDRESSED

**What Could Go Wrong:**
- Tax-free repayment not reducing cost basis
- Excess over cost basis not taxed
- Multiple lots reduction order incorrect

**Current Coverage:**
- ✅ `fifo_manager.py` has `reduce_cost_basis_for_capital_repayment()` - **TESTED**
- ✅ `tests/test_dividend_handling.py` covers the same mechanism via "Exempt From Withholding" dividend rights:
  - `test_dividend_rights_fifo_adjustment_via_sale_gains`: Cost basis reduction applied to first lot, verified via realized gains on sale
  - `test_dividend_rights_first_fifo_lot_to_zero_second_reduced`: First lot reduced to zero (€100→€0), second lot partially reduced (€2750→€2605)
  - `test_dividend_rights_both_fifo_lots_to_zero_with_tax_impact`: Both lots reduced to zero, excess (€245 - €150 = €95) becomes taxable income

**Risk Level:** Low

**Test Coverage Summary:**
| Scenario | Test | Verified Via |
|----------|------|--------------|
| Repayment < cost basis | `test_dividend_rights_fifo_adjustment_via_sale_gains` | Realized gain calculation |
| Repayment exhausts first lot | `test_dividend_rights_first_fifo_lot_to_zero_second_reduced` | FIFO lot cost = €0 |
| Repayment across multiple lots | `test_dividend_rights_first_fifo_lot_to_zero_second_reduced` | €245 across €100 + €2750 lots |
| Repayment exceeds total cost | `test_dividend_rights_both_fifo_lots_to_zero_with_tax_impact` | €95 excess → taxable income |

**Note:** These tests use "Exempt From Withholding" dividend rights which internally call `reduce_cost_basis_for_capital_repayment()`. The mechanism is identical to direct capital repayments.

---

### 10. Short Position Handling (Coverage: Partial)

**What Could Go Wrong:**
- Short sale proceeds not recorded correctly
- Cover cost basis wrong
- Short lot FIFO order incorrect
- Negative SOY position initialization

**Current Coverage:**
- `ShortFifoLot` dataclass with validation
- SOY short initialization tested (fallback logic)
- Group 1-5 specs have `SSO`/`BSC` trade types
- Limited dedicated short-specific scenarios

**Risk Level:** Low (basic coverage exists)

**Recommendation:** Expand short scenarios:
```yaml
- SHORT_MULTI_001: Multiple short lots, partial cover
- SHORT_SOY_001: Short position at SOY, cover intra-year
```

---

### 11. 23 EStG Holding Period (Coverage: Good) ✅ ADDRESSED

**What Could Go Wrong:**
- 365-day boundary off-by-one error
- Leap year handling
- Date parsing edge cases

**Current Coverage:**
- ✅ Code checks `holding_period_days <= 365`
- ✅ `PRIVATE_SALE_ASSET` category exists
- ✅ Loss offsetting has `p23_g`/`p23_v` pots
- ✅ Group 5 (`tests/specs/group5_complex_sequences.yaml`) now includes boundary tests:
  - `CTX_P23_001`: Sold exactly on day 365 (taxable) - Buy 2022-03-15, sell 2023-03-15
  - `CTX_P23_002`: Sold on day 366 (exempt) - Buy 2022-03-15, sell 2023-03-16
  - `CTX_P23_003`: Leap year handling - Feb 28 to Feb 28 next year (365 days, taxable)
  - `CTX_P23_004`: Year-end boundary - Dec 31 to Jan 1 crossing (364 days, taxable)
  - `CTX_P23_005`: Loss on taxable sale (quick flip with loss)

**Risk Level:** Low

**Boundary Test Coverage:**
| Test ID | Scenario | Days | Expected |
|---------|----------|------|----------|
| CTX_P23_001 | Exact 365 days | 365 | TAXABLE_GAIN |
| CTX_P23_002 | Day 366 | 366 | EXEMPT_HOLDING_PERIOD_MET |
| CTX_P23_003 | Feb 28→Feb 28 | 365 | TAXABLE_GAIN |
| CTX_P23_004 | Jan 2→Jan 1 | 364 | TAXABLE_GAIN |
| CTX_P23_005 | Short hold loss | <365 | TAXABLE_LOSS |

---

## Key Recommendations (Priority Order)

### 1. MEDIUM PRIORITY: Stock Splits/Mergers Test Group

Create `tests/specs/group7_corporate_actions.yaml` with scenarios for:
- Forward/reverse splits with various ratios
- Cash mergers with full position liquidation
- Corporate action + same-day trade ordering

**Note:** Stock dividends are now well-covered by `test_dividend_handling.py` (see section 4).

### 2. HIGH PRIORITY: Option Strategy Test Group

Create `tests/specs/group8_options.yaml` with scenarios for:
- Call/put exercise with premium adjustment
- Covered call assignment
- Cash-secured put assignment
- Option expiration (worthless)
- Option closing trades with FIFO matching

### 3. ~~MEDIUM PRIORITY: Variable FX Rate Tests~~ ✅ COMPLETED

~~Enhance mock exchange rate provider to support:~~
- ~~Different rates for different dates~~
- ~~Rate lookup for weekends/holidays~~
- ~~Cross-currency pairs (USD/EUR, GBP/EUR)~~

**Status:** Implemented in `tests/helpers/mock_providers.py` with `create_variable_rate_provider()` and `create_multi_currency_provider()`. Tests in `tests/test_mock_providers.py`.

### 4. ~~MEDIUM PRIORITY: Teilfreistellung Per-Fund-Type Tests~~ ✅ COMPLETED

~~Expand Group 6 to cover all fund types:~~
- ~~Mischfonds (15%)~~
- ~~Immobilienfonds (60%)~~
- ~~Auslands-Immobilienfonds (80%)~~
- ~~Sonstige Fonds (0%)~~

**Status:** All fund types now covered in `tests/specs/group6_loss_offsetting.py` (LO_FUND_MISCH_001, LO_FUND_IMMO_001, LO_FUND_AUSLAND_001, LO_FUND_SONST_001).

### 5. ~~LOW PRIORITY: 23 EStG Boundary Tests~~ ✅ COMPLETED

~~Add explicit holding period boundary tests to prevent off-by-one errors at the 365-day threshold.~~

**Status:** Boundary tests added to `tests/specs/group5_complex_sequences.yaml` (CTX_P23_001 through CTX_P23_005).

### 6. ~~MEDIUM PRIORITY: Capital Repayments Test Group~~ ✅ COMPLETED

~~Create tests for capital repayment scenarios:~~
- ~~CAPREP_001: Repayment less than cost basis (fully reduces)~~
- ~~CAPREP_002: Repayment exceeds cost basis (excess taxed)~~
- ~~CAPREP_003: Repayment across multiple FIFO lots~~

**Status:** Addressed via `tests/test_dividend_handling.py` which tests the `reduce_cost_basis_for_capital_repayment()` function through "Exempt From Withholding" dividend rights scenarios. All three scenarios are covered (see section 9).

---

## Appendix: Test Group Summary

| Group | Focus | Scenario Count | Location |
|-------|-------|----------------|----------|
| 1 | Basic FIFO Long | ~10 | `group1_core_fifo.yaml` |
| 2 | SOY Handling | ~10 | `group2_soy_handling.yaml` |
| 3 | EOY Validation | ~10 | `group3_eoy_validation.yaml` |
| 4 | Multi-Year | ~10 | `group4_multi_year.yaml` |
| 5 | Complex Scenarios + §23 EStG | ~15 | `group5_complex_sequences.yaml` |
| 6 | Loss Offsetting + Fund Types | 34 | `group6_loss_offsetting.py` |
| 7 | Corporate Actions (Splits/Mergers) | **MISSING** | Recommended |
| 8 | Options Lifecycle | **MISSING** | Recommended |
| - | Dividend Handling | 6 | `test_dividend_handling.py` |
| - | Precision Tests | 21 | `test_precision.py` |
| - | Mock Provider Tests | 20+ | `test_mock_providers.py` |
| - | Withholding Tax Linker | 17 | `test_withholding_tax_linker.py` |

---

## Recent Improvements (2026-01-11)

The following gaps have been addressed in the current working directory:

1. **Currency Conversion Timing**: Enhanced `MockECBExchangeRateProvider` with variable rate schedules and multi-currency support
2. **Rounding/Precision**: New `test_precision.py` with FifoLot validation and many-lot accumulation stress tests
3. **Fund Type Teilfreistellung**: All 5 fund types now tested (30%, 15%, 60%, 80%, 0%)
4. **§23 EStG Boundaries**: 5 new holding period boundary tests in Group 5
5. **Dividend Handling & Capital Repayments**: `test_dividend_handling.py` provides 6 tests covering:
   - Stock dividend FIFO lot creation with FMV as cost basis (D05 scenario)
   - Tax-free dividend rights (DI/ED corporate actions) reducing cost basis
   - Multi-lot cost basis reduction (first lot to zero, second lot partial)
   - Excess dividend over cost basis becoming taxable income
   - "Payment In Lieu Of Dividends" transaction type handling
   - Tax impact verification via `LossOffsettingEngine`

---

## Conclusion

The test suite now provides comprehensive coverage for:
- Core FIFO mechanics (Groups 1-5)
- Loss offsetting rules (Group 6)
- All fund type Teilfreistellung rates
- §23 EStG holding period boundaries
- Numerical precision and rounding
- Variable FX rate handling
- **Stock dividends with FMV cost basis** (`test_dividend_handling.py`)
- **Dividend rights (DI/ED) with cost basis reduction** (`test_dividend_handling.py`)
- **Capital repayments / cost basis reduction** (`test_dividend_handling.py`)
- **Excess dividend over cost basis taxation** (`test_dividend_handling.py`)

**Remaining HIGH priority gap:**
1. Option exercise/assignment scenarios (premium adjustments, expiration)

**Remaining MEDIUM priority gaps:**
1. Stock splits (forward/reverse) - `adjust_lots_for_split()` not tested
2. Cash mergers - `consume_all_lots_for_cash_merger()` not tested

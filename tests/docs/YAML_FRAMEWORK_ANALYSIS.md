# YAML Framework Constraint Analysis

## Current Framework Capabilities

### Data Structures Available

| Structure | Fields | Notes |
|-----------|--------|-------|
| **TradeSpec** | `type`, `qty`, `price`, `date`, `currency`, `time`, `asset` | Types: BL, SL, SSO, BSC |
| **PositionSpec** | `quantity`, `cost_basis`, `currency` | For SOY/EOY positions |
| **ExpectedRGLSpec** | `realization_type`, `quantity`, dates, cost/proceeds/gain, `tax_category`, `asset` | Types: SOLD_LONG, COV_SHORT |
| **FifoTestSpec** | Full test case with trades, positions, expectations | Groups 1-5 use this |

### CSV Creators Available

| CSV Type | Purpose | Used By Tests |
|----------|---------|---------------|
| Trades | Buy/sell trades with Open/CloseIndicator | Yes |
| Positions | SOY/EOY position snapshots | Yes |
| Cash Transactions | Dividends, distributions, fees | **No** |
| Corporate Actions | Splits, mergers, stock dividends | **No** |

### Test Runner Constraints

- Single `MockECBExchangeRateProvider` with fixed rate per test
- Pipeline reads CSVs from mocked file paths
- Only STOCK category demonstrated in existing YAML specs
- Trade types limited to: BL, SL, SSO, BSC

---

## Gap Analysis: What Can Be Represented?

### 1. Corporate Actions - Splits/Mergers (HIGH Priority Gap)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| CA_SPLIT_001: 2:1 split | **NO** | No `CorporateActionSpec` in schema |
| CA_SPLIT_002: Fractional split | **NO** | No split ratio field |
| CA_MERGER_001: Cash merger | **NO** | No merger event type |
| CA_STOCKDIV_001: Stock dividend | **NO** | No stock dividend event type |

**What Would Be Needed:**
```yaml
# New CorporateActionSpec structure needed:
corporate_actions:
  - type: SPLIT_FORWARD  # or MERGER_CASH, STOCK_DIVIDEND
    date: "2023-06-01"
    ratio: 2.0           # For splits
    cash_per_share: 50.0 # For cash mergers
    new_shares: 10       # For stock dividends
    fmv_per_share: 25.0  # For stock dividends
```

**Effort to Add:** Medium
- Add `CorporateActionSpec` dataclass to `__init__.py`
- Add `_parse_corporate_action()` function
- Extend `FifoTestSpec` with `corporate_actions` field
- Extend `spec_to_corporate_actions_data()` helper
- Update test runner to write corporate actions CSV

---

### 2. Option Exercise/Assignment (HIGH Priority Gap)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| OPT_CALL_EXERCISE_001 | **NO** | No option-specific fields (strike, expiry, P/C) |
| OPT_PUT_ASSIGN_001 | **NO** | No EXERCISE/ASSIGNMENT event types |
| OPT_EXPIRE_001 | **NO** | No EXPIRATION event type |
| OPT_CLOSE_001 | **PARTIAL** | Could use BL/SL with `asset_category: OPTION` |

**What Would Be Needed:**
```yaml
# Extended TradeSpec for options:
inputs:
  asset:
    symbol: AAPL230120C00150000
    category: OPTION
    underlying: AAPL
    strike: 150.00
    expiry: "2023-01-20"
    put_call: C
    multiplier: 100

# New OptionLifecycleSpec:
option_events:
  - type: EXERCISE  # or ASSIGNMENT, EXPIRATION
    date: "2023-01-20"
    quantity: 1
    underlying_trade_id: T_001  # Link to resulting stock trade
```

**Effort to Add:** High
- Requires option-specific fields in TradeSpec
- Requires new `OptionLifecycleSpec` dataclass
- Requires linking logic between option events and stock trades
- Test runner needs option exercise/assignment handling

---

### 3. Variable FX Rates (MEDIUM Priority Gap)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| FX_MULTI_001: Different rates per trade | **PARTIAL** | MockProvider supports single rate only |
| FX_WEEKEND_001: Weekend rate lookup | **NO** | Mock doesn't simulate date-based lookups |

**What Would Be Needed:**
```yaml
# FX rate schedule in metadata or inputs:
fx_rates:
  - date: "2023-03-01"
    usd_eur: 1.05
  - date: "2023-09-15"
    usd_eur: 1.08
```

**Effort to Add:** Low-Medium
- Extend `MockECBExchangeRateProvider` to accept date-rate map
- Add `fx_rates` field to YAML metadata
- Update test runner to construct mock with rate schedule

**Note:** This is primarily a test infrastructure change, not schema change.

---

### 4. Fund Type Teilfreistellung (MEDIUM Priority Gap)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| FUND_AKTIEN_001: Aktienfonds 30% | **YES** | `asset_category: INVESTMENT_FUND` + expected values |
| FUND_MISCH_001: Mischfonds 15% | **YES** | Same structure, different expected TF |
| FUND_IMMO_001: Immobilienfonds 60% | **YES** | Same structure |

**What Would Be Needed:**
```yaml
inputs:
  asset:
    symbol: FUND.A.EUR
    isin: DE000AAAA001
    category: INVESTMENT_FUND
    fund_type: AKTIENFONDS  # or MISCHFONDS, IMMOBILIENFONDS, etc.
```

**Effort to Add:** Low
- Add `fund_type` field to asset in YAML
- Map to `InvestmentFundType` enum in parser
- Existing FIFO logic already handles TF rates

**This is YAML-representable with minor schema extension.**

---

### 5. Capital Repayments (MEDIUM Priority Gap)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| CAPREP_001: Repayment < cost basis | **NO** | No cash transaction spec |
| CAPREP_002: Repayment > cost basis | **NO** | No `Type: Capital Repayment` support |

**What Would Be Needed:**
```yaml
# New CashTransactionSpec:
cash_transactions:
  - type: CAPITAL_REPAYMENT
    date: "2023-07-15"
    amount: 500.00
    currency: EUR
    asset: ASSET.A.EUR
```

**Effort to Add:** Medium
- Add `CashTransactionSpec` dataclass
- Add `cash_transactions` field to FifoTestSpec
- Extend test runner to write cash transactions CSV
- Expected RGL spec may need `is_capital_repayment_excess` field

---

### 6. §23 EStG Boundary Tests (LOW Priority Gap)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| P23_BOUNDARY_001: Day 365 | **YES** | Use `asset_category: PRIVATE_SALE_ASSET` + dates |
| P23_BOUNDARY_002: Day 366 | **YES** | Same structure |
| P23_LEAP_001: Leap year | **YES** | Same structure |

**What Would Be Needed:**
```yaml
inputs:
  asset:
    category: PRIVATE_SALE_ASSET
  intra_year_trades:
    - type: BL
      date: "2022-01-15"  # Acquisition
    - type: SL
      date: "2023-01-15"  # 365 days later
expected:
  rgls:
    - tax_category: SECTION_23_ESTG_TAXABLE_GAIN  # or EXEMPT
```

**Effort to Add:** Very Low
- Existing schema supports this
- Just need to add test cases with appropriate dates and expected categories

**This is FULLY YAML-representable today.**

---

### 7. Short Position Scenarios (Already Partial)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| SHORT_MULTI_001 | **YES** | SSO/BSC types already supported |
| SHORT_SOY_001 | **YES** | `positions_soy` with negative quantity |

**Already representable.** Group 1 has CFM_S_* tests for shorts.

---

### 8. Rounding/Precision Tests (LOW Priority)

| Test Case | YAML Representable | Reason |
|-----------|-------------------|--------|
| PRECISION_001: Many small lots | **YES** | Just many trades |
| PRECISION_002: Fractional shares | **YES** | Decimal quantities supported |

**Already representable.** Just need test cases with appropriate values.

---

## Summary: Representability Matrix

| Gap Category | YAML Today | With Minor Extension | Requires Major Work |
|--------------|------------|---------------------|---------------------|
| Corporate Actions | | | X |
| Option Lifecycle | | | X |
| Variable FX Rates | | X | |
| Fund Type TF | | X | |
| Capital Repayments | | | X |
| §23 Boundaries | X | | |
| Short Positions | X | | |
| Rounding/Precision | X | | |

---

## Recommendations

### Immediately Doable (No Schema Changes)

1. **§23 EStG Boundary Tests** - Add to Group 5 or new Group 7
2. **More Short Position Tests** - Expand Group 1 CFM_S_* series
3. **Rounding Stress Tests** - Add high-precision fractional trades

### Minor Schema Extensions (Low Effort)

4. **Fund Type Tests** - Add `fund_type` to asset spec, create fund tests
5. **Variable FX Rates** - Extend MockProvider, add `fx_rates` to metadata

### Requires New Infrastructure (Medium-High Effort)

6. **Corporate Actions** - New `CorporateActionSpec`, CSV creator integration
7. **Cash Transactions** - New `CashTransactionSpec` for capital repayments
8. **Option Lifecycle** - Requires significant schema and test runner changes

---

## Proposed Action Plan

**Phase 1: Quick Wins (Fully YAML-representable)**
- Add 3-5 §23 EStG boundary tests to `group5_complex_sequences.yaml`
- Add 2-3 precision/rounding tests with fractional quantities

**Phase 2: Minor Extensions**
- Add `fund_type` field to schema
- Create `group7_fund_types.yaml` with TF rate tests for each fund type
- Extend `MockECBExchangeRateProvider` to support date-based rate map

**Phase 3: New Event Types (Future)**
- Design `CorporateActionSpec` and integrate with test runner
- Evaluate whether option lifecycle testing requires YAML or Python-only approach

# Options Test Plan

## Executive Summary

This document outlines a comprehensive plan to test options expiration, assignment, exercise, buy/sell, and long/short scenarios. Options testing is currently identified as a **HIGH priority gap** in the test coverage analysis.

**Analysis Date:** 2026-01-11

---

## 1. Options Domain Model Review

### 1.1 Option Asset Structure

From `src/domain/assets.py`:
```python
@dataclass
class Option(Derivative):
    option_type: Optional[str] = None  # 'P' for Put, 'C' for Call
    strike_price: Optional[Decimal] = None
    expiry_date: Optional[str] = None  # YYYY-MM-DD
    # Inherited from Derivative:
    underlying_asset_internal_id: Optional[uuid.UUID]
    underlying_ibkr_conid: Optional[str]
    multiplier: Decimal = Decimal('100')  # Standard: 100 shares per contract
```

### 1.2 Option Lifecycle Events

From `src/domain/events.py`:
- `OptionExerciseEvent` - Holder exercises their right
- `OptionAssignmentEvent` - Writer is assigned
- `OptionExpirationWorthlessEvent` - Option expires OTM

### 1.3 Realization Types

From `src/domain/enums.py`:
- `OPTION_EXPIRED_LONG` - Long option expired worthless (loss)
- `OPTION_EXPIRED_SHORT` - Short option expired worthless (Stillhalter income)
- `OPTION_TRADE_CLOSE_LONG` - Sold option previously bought
- `OPTION_TRADE_CLOSE_SHORT` - Bought back option previously sold short

---

## 2. Economic Scenarios to Test

### 2.1 Option Premium Adjustment Matrix

When options are exercised or assigned, the premium must be incorporated into the resulting stock position's cost basis or sale proceeds:

| Scenario | Option Position | Action | Stock Action | Premium Treatment |
|----------|-----------------|--------|--------------|-------------------|
| Long Call Exercise | Long Call | Exercise | Buy Stock | Premium ADDS to stock cost |
| Short Put Assignment | Short Put | Assigned | Buy Stock | Premium REDUCES stock cost |
| Short Call Assignment | Short Call | Assigned | Sell Stock | Premium ADDS to stock proceeds |
| Long Put Exercise | Long Put | Exercise | Sell Stock | Premium REDUCES stock proceeds |

### 2.2 Worthless Expiration

| Scenario | Option Position | Outcome | Tax Treatment |
|----------|-----------------|---------|---------------|
| Long Call Expires OTM | Long | Full premium = LOSS | Termingeschäft Loss (Z24) |
| Long Put Expires OTM | Long | Full premium = LOSS | Termingeschäft Loss (Z24) |
| Short Call Expires OTM | Short | Full premium = GAIN | Stillhalter Income (Z21) |
| Short Put Expires OTM | Short | Full premium = GAIN | Stillhalter Income (Z21) |

### 2.3 Option Closing Trades (No Exercise/Assignment)

| Scenario | Action | Treatment |
|----------|--------|-----------|
| Buy call, sell to close | Sell - Buy = G/L | Normal FIFO for options |
| Sell put, buy to close | Original proceeds - cover cost = G/L | Short cover FIFO |

---

## 3. Test Scenarios

### Group 8: Options Lifecycle

**Subgroup A: Long Call Exercise**

| ID | Description | Steps | Verification |
|----|-------------|-------|--------------|
| OPT_CALL_EX_001 | Basic long call exercise | 1. Buy 1 AAPL Jan50C @ $5<br>2. Exercise call<br>3. Receive 100 AAPL @ $50<br>4. Sell 100 AAPL @ $60 | Stock cost = $5000 + $500 = $5500<br>Stock proceeds = $6000<br>Gain = $500 |
| OPT_CALL_EX_002 | Multi-lot call exercise | 1. Buy 2 AAPL Jan50C @ $5 (lot A)<br>2. Buy 1 AAPL Jan50C @ $3 (lot B)<br>3. Exercise 2 contracts<br>4. FIFO: consume lot A (2) | Premium from lot A ($1000) adds to stock cost |
| OPT_CALL_EX_003 | Partial lot exercise | 1. Buy 3 contracts<br>2. Exercise 2 contracts<br>3. Sell 1 contract | FIFO splits: 2 exercised, 1 traded |

**Subgroup B: Short Put Assignment**

| ID | Description | Steps | Verification |
|----|-------------|-------|--------------|
| OPT_PUT_ASGN_001 | Basic short put assignment | 1. Sell 1 AAPL Jan50P @ $3<br>2. Assigned<br>3. Forced to buy 100 AAPL @ $50<br>4. Sell 100 AAPL @ $45 | Stock cost = $5000 - $300 = $4700<br>Stock proceeds = $4500<br>Loss = $200 |
| OPT_PUT_ASGN_002 | Multi-lot put assignment | 1. Sell 2 puts @ $3 (lot A)<br>2. Sell 1 put @ $4 (lot B)<br>3. Assigned on 2 contracts | FIFO: consume lot A, premium $600 reduces stock cost |

**Subgroup C: Short Call Assignment (Covered Call)**

| ID | Description | Steps | Verification |
|----|-------------|-------|--------------|
| OPT_CCALL_ASGN_001 | Covered call assignment | 1. Own 100 AAPL (cost $50/share)<br>2. Sell 1 AAPL Jan55C @ $2<br>3. Assigned, must sell stock @ $55 | Stock proceeds = $5500 + $200 = $5700<br>Cost = $5000<br>Gain = $700 |
| OPT_CCALL_ASGN_002 | Naked call assignment | 1. Sell 1 AAPL Jan55C @ $2 (naked)<br>2. Assigned, short sell stock @ $55 | Short sale proceeds = $5500 + $200 = $5700 |

**Subgroup D: Long Put Exercise (Protective Put)**

| ID | Description | Steps | Verification |
|----|-------------|-------|--------------|
| OPT_PUT_EX_001 | Long put exercise with stock | 1. Own 100 AAPL (cost $60/share)<br>2. Buy 1 AAPL Jan55P @ $4<br>3. Exercise put, sell stock @ $55 | Stock proceeds = $5500 - $400 = $5100<br>Cost = $6000<br>Loss = $900 |
| OPT_PUT_EX_002 | Long put exercise without stock | 1. Buy 1 AAPL Jan55P @ $4<br>2. Exercise, short sell @ $55 | Short proceeds = $5500 - $400 = $5100 |

**Subgroup E: Worthless Expiration**

| ID | Description | Steps | Verification |
|----|-------------|-------|--------------|
| OPT_EXP_LONG_001 | Long call expires worthless | 1. Buy 1 AAPL Jan50C @ $5<br>2. Expires OTM | Loss = $500<br>RealizationType = OPTION_EXPIRED_LONG<br>TaxCat = ANLAGE_KAP_TERMIN_VERLUST |
| OPT_EXP_LONG_002 | Long put expires worthless | 1. Buy 1 AAPL Jan45P @ $3<br>2. Expires OTM | Loss = $300<br>RealizationType = OPTION_EXPIRED_LONG |
| OPT_EXP_SHORT_001 | Short call expires worthless (Stillhalter) | 1. Sell 1 AAPL Jan60C @ $2<br>2. Expires OTM | Gain = $200<br>RealizationType = OPTION_EXPIRED_SHORT<br>is_stillhalter_income = True |
| OPT_EXP_SHORT_002 | Short put expires worthless (Stillhalter) | 1. Sell 1 AAPL Jan40P @ $1<br>2. Expires OTM | Gain = $100<br>is_stillhalter_income = True |
| OPT_EXP_MULTI_001 | Multiple contracts expire | 1. Buy 3 calls @ $5, $4, $3<br>2. All expire | Total loss = $1200 (3 RGLs, FIFO order) |

**Subgroup F: Option Closing Trades**

| ID | Description | Steps | Verification |
|----|-------------|-------|--------------|
| OPT_CLOSE_LONG_001 | Profitable long call close | 1. Buy 1 call @ $5<br>2. Sell 1 call @ $8 | Gain = $300<br>RealizationType = OPTION_TRADE_CLOSE_LONG |
| OPT_CLOSE_LONG_002 | Losing long put close | 1. Buy 1 put @ $4<br>2. Sell 1 put @ $2 | Loss = $200 |
| OPT_CLOSE_SHORT_001 | Buy back short call at loss | 1. Sell 1 call @ $3<br>2. Buy to close @ $5 | Loss = $200<br>RealizationType = OPTION_TRADE_CLOSE_SHORT |
| OPT_CLOSE_SHORT_002 | Buy back short put at profit | 1. Sell 1 put @ $4<br>2. Buy to close @ $1 | Gain = $300 |
| OPT_CLOSE_FIFO_001 | Multi-lot option FIFO | 1. Buy 2 calls @ $5 (lot A)<br>2. Buy 1 call @ $3 (lot B)<br>3. Sell 2 calls @ $7 | FIFO: lot A consumed, gain = $400 |

**Subgroup G: Edge Cases**

| ID | Description | Steps | Verification |
|----|-------------|-------|--------------|
| OPT_EDGE_001 | Same-day trade and exercise | 1. Buy call at 10:00<br>2. Exercise at 14:00 | Time ordering ensures proper lot matching |
| OPT_EDGE_002 | Multiplier != 100 | 1. Mini option (10 shares/contract) | Correct share quantity in stock trade |
| OPT_EDGE_003 | USD option with FX | 1. USD-denominated option<br>2. Convert premium to EUR | ECB rate applied correctly |
| OPT_EDGE_004 | Partial assignment | 1. Short 3 puts<br>2. Assigned on 2 | FIFO: 2 lots consumed, 1 remains |
| OPT_EDGE_005 | Roll strategy | 1. Sell put @ strike 50<br>2. Buy back @ $2<br>3. Sell new put @ strike 45 | Two separate trades, correct FIFO |

---

## 4. Implementation Approach

### 4.1 Test Infrastructure Requirements

The current test infrastructure needs extensions for options:

#### A. New CSV Creator for Options

```python
def create_option_trades_csv_string(
    trades_data: List[List],
    include_header: bool = True,
) -> str:
    """
    Create CSV string for option trades.

    Required columns:
    - Asset Class: "OPT"
    - Symbol: e.g., "AAPL  230120C00050000" (OCC format)
    - Underlying Symbol: "AAPL"
    - Underlying CONID: "265598"
    - Put/Call: "C" or "P"
    - Strike: "50.00"
    - Expiry: "2023-01-20"
    - Multiplier: "100"
    """
```

#### B. Option Event Factory

```python
def create_option_lifecycle_event(
    event_type: str,  # "EXERCISE", "ASSIGNMENT", "EXPIRATION"
    option_asset_id: uuid.UUID,
    quantity_contracts: Decimal,
    event_date: str,
) -> OptionLifecycleEvent:
    """Factory for option lifecycle events."""
```

#### C. Stock Trade Linker Setup

The `OptionTradeLinker` requires:
- Option event lookup keyed by `(date, underlying_conid, abs_qty)`
- Stock trades with matching keys get linked

### 4.2 Test File Structure

```
tests/
├── fixtures/
│   └── group8_options.yaml         # YAML specs for option scenarios
├── test_options_lifecycle.py       # Main test file for Group 8
└── support/
    └── option_helpers.py           # Option-specific test helpers
```

### 4.3 Phased Implementation

**Phase 1: Foundation (Unit Tests)**
1. Test `consume_long_option_get_cost()` directly on FifoLedger
2. Test `consume_short_option_get_proceeds()` directly
3. Test `OptionExpirationWorthlessProcessor` in isolation

**Phase 2: Processor Tests**
1. Test `OptionExerciseProcessor` with mock context
2. Test `OptionAssignmentProcessor` with mock context
3. Verify `pending_option_adjustments` dict populated correctly

**Phase 3: Trade Linker Tests**
1. Test `OptionTradeLinker._build_option_event_lookup()`
2. Test `OptionTradeLinker.link_trades()`
3. Verify `related_option_event_id` set on stock trades

**Phase 4: Integration Tests (Full Pipeline)**
1. CSV → Parsing → Enrichment → Calculation → RGL
2. End-to-end scenarios from Group 8 specs
3. Loss offsetting verification (Z21/Z24)

**Phase 5: Tax Reporting Tests**
1. Verify Stillhalter income flag on RGLs
2. Verify correct tax categories (TERMIN_GEWINN/VERLUST)
3. Integration with `LossOffsettingEngine`

---

## 5. YAML Spec Format for Options

```yaml
metadata:
  group: 8
  name: "Options Lifecycle"
  description: "Tests for option exercise, assignment, expiration, and closing trades"

tests:
  - id: OPT_CALL_EX_001
    description: "Basic long call exercise with stock sale"
    inputs:
      option_asset:
        symbol: "AAPL  230120C00050000"
        underlying_symbol: "AAPL"
        underlying_conid: "265598"
        option_type: "C"
        strike: "50.00"
        expiry: "2023-01-20"
        multiplier: "100"
      stock_asset:
        symbol: "AAPL"
        isin: "US0378331005"
        conid: "265598"
      option_trades:
        - type: "BL"      # Buy long option
          qty: 1          # 1 contract
          price: "5.00"   # $5 per share = $500 total
          date: "2023-01-05"
      option_events:
        - type: "EXERCISE"
          qty: 1
          date: "2023-01-15"
      stock_trades:
        - type: "SL"      # Sell long stock (from exercise)
          qty: 100
          price: "60.00"
          date: "2023-01-20"
          linked_to_option_event: 0  # Index into option_events
    expected:
      rgls:
        - asset: "AAPL"
          realization_type: "LONG_POSITION_SALE"
          quantity: 100
          # Stock cost = (100 * $50) + $500 premium = $5500
          total_cost_basis_eur: "5500.00"
          # Stock proceeds = 100 * $60 = $6000
          total_proceeds_eur: "6000.00"
          gain_loss_eur: "500.00"
          tax_category: "ANLAGE_KAP_AKTIEN_GEWINN"
      option_eoy_quantity: 0
      stock_eoy_quantity: 0
```

---

## 6. Dependencies and Prerequisites

### 6.1 Code Understanding Complete
- [x] `Option` domain model
- [x] `OptionExerciseEvent`, `OptionAssignmentEvent`, `OptionExpirationWorthlessEvent`
- [x] `consume_long_option_get_cost()`, `consume_short_option_get_proceeds()`
- [x] `OptionExerciseProcessor`, `OptionAssignmentProcessor`, `OptionExpirationWorthlessProcessor`
- [x] `OptionTradeLinker` and `perform_option_trade_linking()`
- [x] Premium adjustment logic in `TradeProcessor`

### 6.2 Test Infrastructure Available
- [x] `FifoTestCaseBase` - Pipeline runner
- [x] `MockECBExchangeRateProvider` - FX rates
- [x] `create_trades_csv_string()` - Trade CSV generation
- [ ] Option-specific CSV creator (needs creation)
- [ ] Option lifecycle event injection (needs design)

### 6.3 Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Option parsing not implemented | May need to extend trade parser for OPT asset class |
| Option event generation from CSV unclear | Review `corporate_action_parser.py` or create synthetic events |
| Complex linking logic | Start with unit tests, verify linking separately |

---

## 7. Success Criteria

1. **Unit Test Coverage**
   - `consume_long_option_get_cost()` tested for single/multi-lot
   - `consume_short_option_get_proceeds()` tested for single/multi-lot
   - All three option processors tested in isolation

2. **Integration Test Coverage**
   - All 4 exercise/assignment scenarios passing
   - All 4 worthless expiration scenarios passing
   - Option closing trade FIFO scenarios passing

3. **Tax Reporting Accuracy**
   - Stillhalter income correctly flagged
   - TERMIN_GEWINN/VERLUST categories assigned
   - Premium adjustments verified via realized gains

4. **Edge Case Coverage**
   - USD options with FX conversion
   - Non-standard multipliers
   - Same-day ordering
   - Partial exercises/assignments

---

## 8. Recommended Next Steps

1. **Create `tests/support/option_helpers.py`**
   - Option trade CSV creator
   - Option event factories
   - Helper functions for linking setup

2. **Create `tests/test_options_unit.py`** (Phase 1)
   - Direct tests on FifoLedger option methods
   - Direct tests on option processors

3. **Create `tests/fixtures/group8_options.yaml`** (Phase 2-4)
   - YAML specs for all scenarios listed above
   - Start with basic scenarios, add edge cases

4. **Create `tests/test_options_lifecycle.py`** (Phase 4-5)
   - Full pipeline integration tests
   - Parametrized from YAML specs

5. **Update `TEST_COVERAGE_GAP_ANALYSIS.md`**
   - Mark Option Exercise/Assignment as addressed
   - Update coverage table

---

## Appendix A: IBKR Option Symbol Format

IBKR uses OCC (Options Clearing Corporation) symbology:
```
AAPL  230120C00050000
│     │     ││       │
│     │     ││       └── Strike price (5 decimal places, no decimal point)
│     │     │└── Put/Call indicator (C or P)
│     │     └── Expiration date (YYMMDD)
│     └── Spaces (padding to 6 chars for underlying)
└── Underlying symbol
```

Example parsing:
- `AAPL  230120C00050000` → AAPL Call, Jan 20 2023, Strike $50.00

---

## Appendix B: German Tax Treatment Reference

**Termingeschäfte (§20 Abs. 2 Satz 1 Nr. 3 EStG)**
- Options are classified as Termingeschäfte
- Gains: Anlage KAP Zeile 21 (Gewinne aus Termingeschäften)
- Losses: Anlage KAP Zeile 24 (Verluste aus Termingeschäften)
- Loss cap: €20,000 per year on offsetting (since 2021)

**Stillhalterprämien (§20 Abs. 1 Nr. 11 EStG)**
- Premium received from writing options is Stillhalter income
- Taxable as "sonstige Kapitaleinkünfte" when option expires worthless
- The `is_stillhalter_income` flag on RGL identifies this

**Premium Adjustment on Exercise/Assignment**
- When option is exercised/assigned, it doesn't generate a separate RGL
- Instead, the premium adjusts the stock's cost basis or proceeds
- This is economically correct: you paid/received premium as part of acquiring/disposing of stock

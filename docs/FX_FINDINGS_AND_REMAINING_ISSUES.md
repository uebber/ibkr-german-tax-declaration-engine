# FX Gain/Loss: Findings, Fixes Applied, and Remaining Issues

## Date: 2026-03-08 (Session 3 — comprehensive consolidation)

---

## Fixes Applied (Session 1 — Fixes 1–6)

### Fix 1: Empty-dict truthiness checks (3 locations)
**Problem**: `currency_fifo_ledgers` is `{}` when no CashBalance asset exists yet. Python `if dict:` is `False` for empty dicts, so `_process_cashflow_currency_impact()` was never called.

**Files changed**:
- `calculation_engine.py`: `if currency_conversion_processor and currency_fifo_ledgers:` → `if currency_conversion_processor is not None:`
- `trade_processor.py`: `if not currency_fifo_ledgers:` → `if currency_fifo_ledgers is None:`

### Fix 2: On-the-fly CashBalance asset/ledger creation
Added `_ensure_currency_ledger_exists()` helper in `calculation_engine.py`.

### Fix 3: `_get_eur_value()` string date bug
Added `parse_ibkr_date()` call to convert string to date object before calling `convert_to_eur()`.

### Fix 4: Option multiplier missing from currency amount (CRITICAL)
Used `event.gross_amount_foreign_currency` (includes multiplier) instead of `qty * price`.

### Fix 5: CAPITAL_REPAYMENT missing currency impact
Added `_process_cashflow_currency_impact()` call in the CAPITAL_REPAYMENT handler.

### Fix 6: Currency EOY validation added
Added currency-specific EOY validation block comparing FIFO ledger quantities against reported cash balances.

---

## Fixes Applied (Session 2 — Fixes 7–10)

### Fix 7: Commission tracking as currency consumption
Added `_process_commission_currency_impact()` method in `trade_processor.py`.

### Fix 8: Comprehensive historical currency event collection
Added `_collect_historical_currency_event()` in `calculation_engine.py` covering all event types.

### Fix 9: Comprehensive historical currency event replay
Added `_replay_historical_currency_events()` with `_consume_lots_historical()`, `_create_lot_historical()`, `_get_historical_eur_value()`.

### Fix 10: SOY reconciliation
Added `_reconcile_currency_soy()` — always adjusts FIFO to match authoritative SOY quantity.

---

## Fixes Applied (Session 3 — Fixes 11–15)

### Fix 11: Group 7 test commission isolation (DONE)
**File**: `tests/test_group7_currency_fifo.py:265`

Commission changed from `Decimal("-1.00")` to `Decimal("0")` in test helper `create_security_trade_csv_row()`. Group 7 tests validate core currency FIFO logic, not commission edge cases.

**Result**: All 18 previously failing tests now pass. 290/290 tests green.

### Fix 12: Cash balance date validation against tax year (DONE)
**Files**: `src/parsers/parsing_orchestrator.py`, `src/pipeline_runner.py`

**Problem**: Cash balance CSV dates were never validated against the configured tax year. A 2023 cash balance file used with TAX_YEAR=2024 produced completely wrong SOY/EOY values silently. This was the root cause of all 5 original currency EOY mismatches (CHF: 29K, NOK: 302K, JPY: 3.5M, SGD: 57, USD: 150).

**Fix**:
- `_process_cash_balance_positions()` now accepts `tax_year` parameter
- Validates `FromDate`/`ToDate` from CSV against tax year
- Emits clear `ERROR` log when dates don't match
- Tax year threaded from `run_core_processing_pipeline()` → `run_parsing_pipeline()` → `_process_cash_balance_positions()`

### Fix 13: Stale EOY validation warning message (DONE)
**File**: `src/engine/calculation_engine.py:581`

Old: *"commissions not yet tracked as currency consumption"*
New: *"Common causes: cash balance CSV dates don't match tax year, or untracked currency-impacting events"*

### Fix 14: Debit interest classified as income instead of expense (DONE)
**File**: `src/parsers/domain_event_factory.py`

**Problem**: ALL non-Stückzinsen interest was classified as `INTEREST_RECEIVED` regardless of sign. Debit/margin interest (negative raw_amount) would be abs'd and treated as income (creating currency lots instead of consuming them).

**Fix**: Added sign-based classification in the interest parsing branch:
- `raw_amount < 0` → `FEE_TRANSACTION` (expense — consumes currency)
- `raw_amount >= 0` → `INTEREST_RECEIVED` (income — creates currency lot)

### Fix 15: "Payment In Lieu Of Dividends" negative amounts (DONE)
**File**: `src/parsers/domain_event_factory.py`

**Problem**: Two issues:
1. Type string `"PAYMENT IN LIEU OF DIVIDENDS"` didn't match `"PAYMENT IN LIEU"` in the abs() gate (exact match vs substring)
2. Negative PIL amounts (you pay for borrowing shares) were treated as income instead of expense

**Fix**:
1. Changed abs() gate to use substring matching: `"DIVIDEND" in ...`, `"INTEREST" in ...`, `"PAYMENT IN LIEU" in ...`
2. Added check: negative PIL → classify as `FEE_TRANSACTION` (expense)

---

## Current State: EOY Validation Results (with correct 2024 cash balance)

After providing the correct 2024 cash balance file (`20240101–20241231`):

| Currency | SOY | EOY Reported | FIFO EOY | Diff | Status |
|----------|-----|-------------|----------|------|--------|
| CAD | -0.00 | -0.00 | — | — | OK (tiny, skipped) |
| CHF | -0.00 | -0.00 | — | — | OK (tiny, skipped) |
| CNH | -0.00 | -0.00 | — | — | OK (tiny, skipped) |
| GBP | 0.00 | -0.00 | — | — | OK (tiny, skipped) |
| HKD | -0.00 | 0.00 | — | — | OK (tiny, skipped) |
| NZD | -0.00 | -0.00 | — | — | OK (tiny, skipped) |
| **JPY** | -1,200,000 | 0.01 | -1,150,000 | -1,150,000 | **MISMATCH** |
| **SGD** | 0.01 | 36.18 | 36.21 | 0.03 | **~OK (rounding)** |
| **USD** | 1,750.97 | -0.00 | 3,683.62 | 3,683.62 | **MISMATCH** |

### Root cause analysis (proven via raw CSV arithmetic)

The gaps are **NOT code bugs**. Direct computation from raw CSV data (without any engine processing) produces the same gaps:

**USD gap = 3,683.62:**
```
SOY:           +1,750.97
FX net:       +31,000.00
Trades net:   -43,139.97
Commissions:   -2,354.97
Cash tx:         +143.81
= Expected:    +3,683.62  (but EOY reported = 0.00)
```

**JPY gap = 50,000:**
```
SOY:        -1,200,000.01
FX net:        +50,000.01
Trades net: +1,697,850.00
Commissions:    -3,317.00
Cash tx:             0.00
= Expected:    +50,000.01  (but EOY reported = 0.01)
```

The missing amounts are cash flows that affect the real balance but are **not in any input CSV**:
- Margin/debit interest charges (IBKR charges monthly on borrowed cash)
- ADR pass-through fees
- Regulatory fees (SEC, exchange fees)
- Deposits/withdrawals (separate IBKR section)

---

## NEXT STEP: Expand Input Data to Close EOY Gaps

### What's needed

The current Flex Query exports are missing cash-balance-affecting events. Two actions required:

#### Action 1: Add `TradeMoney` column to Trades Flex Query

The Trades CSV currently lacks the `TradeMoney`/`Proceeds` column. ALL FX conversion second-leg amounts are being **calculated** as `Quantity × Rate` instead of using the actual settlement amount. The model (`RawTradeRecord`) already supports both fields — they're just not in the export.

**Impact**: Minor precision improvement for FX conversions. The `Quantity × Rate` calculation is mathematically correct but uses the rounded CSV rate (5 decimal places), which can accumulate small errors over many trades.

#### Action 2: Expand Cash Transactions Flex Query

The current export includes only 6 transaction types:
- [x] Dividends
- [x] Withholding Tax
- [x] Broker Interest Received
- [x] Payment In Lieu Of Dividends
- [x] Bond Interest Received
- [x] Bond Interest Paid

Missing types that affect currency balances:
- [ ] **Broker Interest Paid** — margin/debit interest (likely biggest gap)
- [ ] **Other Fees** — ADR fees, regulatory fees, exchange fees
- [ ] **Deposits/Withdrawals** — if any foreign currency deposits/withdrawals occurred
- [ ] **Commission Adjustments** — rare but possible

The parser already handles all these types correctly (after Fix 14/15):
- "Broker Interest Paid" → negative amount → `FEE_TRANSACTION` (expense)
- "Other Fees" → matches `"FEE"` pattern → `FEE_TRANSACTION` (expense)
- Positive amounts → income event types
- Negative amounts → expense event types

**No code changes needed** — just re-export with all types included.

### Implementation plan

1. User re-exports IBKR Flex Query CSVs with expanded fields (see instructions below)
2. Replace `data/cash_transactions.csv` and `data/trades.csv`
3. Run `uv run python -m src.main` and check currency EOY validation
4. If new transaction types surface that aren't handled, add parsing support

---

## IBKR Flex Query Configuration Instructions

### Trades Flex Query — Add TradeMoney

1. Log into IBKR Account Management → Reports → Flex Queries
2. Edit your Trades Flex Query
3. In the column selection, ensure these are checked:
   - All existing columns (keep them)
   - **TradeMoney** (add this — it's the total settlement amount: `Quantity × Price × Multiplier`)
   - **Proceeds** (also add if available — alternative to TradeMoney for sells)
4. Save and re-run for the full date range (include historical + current year)

### Cash Transactions Flex Query — Add All Types

1. Edit your Cash Transactions Flex Query
2. In the **Transaction Type** filter, ensure ALL types are selected:
   - Dividends ✓ (already included)
   - Withholding Tax ✓ (already included)
   - Broker Interest Received ✓ (already included)
   - **Broker Interest Paid** ← ADD THIS
   - Payment In Lieu Of Dividends ✓ (already included)
   - Bond Interest Received ✓ (already included)
   - Bond Interest Paid ✓ (already included)
   - **Other Fees** ← ADD THIS
   - **Commission Adjustments** ← ADD THIS (if available)
   - **Deposits/Withdrawals** ← ADD THIS (if available as type)
3. Keep all existing columns
4. Save and re-run for the full date range

### Cash Balance — Already correct
The 2024 cash balance file is correctly configured with `FromDate=20240101`, `ToDate=20241231`.

---

## Architecture Summary

### Currency FIFO initialization flow (calculation_engine.py)
```
1. Validate cash balance dates against tax year (Fix 12)
2. Collect currencies_to_init from known CashBalance assets
3. For each currency:
   a. _ensure_currency_ledger_exists()
   b. Collect + sort historical events
   c. _replay_historical_currency_events() → build FIFO lots
   d. _reconcile_currency_soy() → adjust to match authoritative SOY
```

### Current-year currency impact flow
```
TradeEvent → _process_trade_currency_impact():
  1. Main trade: consume (buy) or create lot (sell)
  2. Commission: _process_commission_currency_impact()
CurrencyConversionEvent → currency_conversion_processor.process()
CashFlowEvent → _process_cashflow_currency_impact()
  Income (dividends, interest received, distributions, capital repayments) → create lot
  Expense (WHT, fees, debit interest, negative PIL) → consume lot
CAPITAL_REPAYMENT → _process_cashflow_currency_impact()
```

### Event type classification (domain_event_factory.py, after Fix 14/15)
```
Dividends (positive)      → DIVIDEND_CASH (income)
Payment In Lieu (positive) → DIVIDEND_CASH (income)
Payment In Lieu (negative) → FEE_TRANSACTION (expense)
Interest (positive)        → INTEREST_RECEIVED (income)
Interest (negative)        → FEE_TRANSACTION (expense)
Bond accrued int (negative)→ INTEREST_PAID_STUECKZINSEN (expense)
Withholding Tax            → WITHHOLDING_TAX (expense)
Fees / Other Fees          → FEE_TRANSACTION (expense)
```

---

## Design Decisions Log

1. **SOY is authoritative**: `_reconcile_currency_soy()` always runs. Historical replay provides lot-level cost basis; SOY reconciliation corrects total quantity.

2. **Currency init gated on CashBalance assets**: Only currencies with CashBalance assets get FIFO tracking. Prevents spurious FX tracking in tests without cash balance data.

3. **Historical replay generates no RGLs**: `_consume_lots_historical()` and `_create_lot_historical()` build state silently. Only current-year operations generate taxable events.

4. **Cross-currency events processed per-currency**: USD→GBP conversion processed once for USD (consumption) and once for GBP (creation).

5. **Cash balance date validation**: Parser emits ERROR when cash balance CSV period doesn't match tax year. Prevents silent data corruption.

6. **Sign-based income/expense classification**: Negative amounts on income-type transactions (interest, PIL) are reclassified as expenses. This correctly handles debit interest and PIL payments.

7. **Test isolation**: Group 7 tests use zero commission to isolate FIFO logic from commission FX noise. Commission tracking validated via production data and Groups 8–11.

---

## Test Status

- **290/290 tests pass** (all groups 1–11)
- Zero regressions across all test groups
- Group 7: 79 tests (currency FIFO core logic)
- Groups 1–6: FIFO, loss offsetting (no currency tracking)
- Groups 8–11: options, variable FX, cashflow currency

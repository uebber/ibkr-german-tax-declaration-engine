# Options Lifecycle Tests - Implementation Status

Created: 2026-01-11
Updated: 2026-01-11

## Summary

All 19 options lifecycle tests (Group 8) now pass. The implementation required fixing one production code bug and updating test expected values.

## Files Modified

1. **src/parsers/domain_event_factory.py** - Fixed assignment detection bug
2. **tests/fixtures/group8_options.yaml** - Updated expected values to include option commission

## Test Results

### All Tests Passing (19)

| Test ID | Description |
|---------|-------------|
| OPT_CALL_EX_001 | Long call exercise - buy call, exercise, sell stock |
| OPT_PUT_ASGN_001 | Short put assignment - sell put, get assigned, sell stock |
| OPT_CCALL_ASGN_001 | Covered call assignment - own stock, sell call, get assigned |
| OPT_PUT_EX_001 | Long put exercise - own stock, buy put, exercise |
| OPT_EXP_LONG_001 | Long call expires worthless - full premium loss |
| OPT_EXP_LONG_002 | Long put expires worthless - full premium loss |
| OPT_EXP_SHORT_001 | Short call expires worthless - Stillhalter income |
| OPT_EXP_SHORT_002 | Short put expires worthless - Stillhalter income |
| OPT_CLOSE_LONG_001 | Profitable long call close |
| OPT_CLOSE_LONG_002 | Losing long put close |
| OPT_CLOSE_SHORT_001 | Buy back short call at loss |
| OPT_CLOSE_SHORT_002 | Buy back short put at profit |
| OPT_CLOSE_FIFO_001 | Multi-lot option FIFO |
| OPT_EDGE_003 | EUR-denominated option |
| OPT_EXP_MULTI_001 | Multiple contracts expire worthless - FIFO from multiple lots |
| TestOptionsSpecsLoaded::* | Spec loading verification tests (4 tests) |

## Root Causes and Fixes

### Fix 1: Production Code Bug - Assignment Detection

**Location:** `src/parsers/domain_event_factory.py:121`

**Bug:** The condition for detecting option assignments was:
```python
if 'A' in notes_codes_parts and open_close_ind != 'C':
    option_event_type = FinancialEventType.OPTION_ASSIGNMENT
```

This prevented assignments from being detected because IBKR assignment trades **always** have `Open/CloseIndicator='C'` (they close the short option position).

**Fix:** Removed the erroneous `open_close_ind != 'C'` check:
```python
if 'A' in notes_codes_parts:
    option_event_type = FinancialEventType.OPTION_ASSIGNMENT
```

**Validation:** Real IBKR data confirms assignments have 'C' indicator:
```csv
"U7542366","EUR","OPT","P","P LEG 20230317 69 M","LEG 17MAR23 69 P",...,"A","LEG",...,"C"
```

### Fix 2: Test Expected Values - Option Commission Inclusion

**Issue:** Test expected values didn't include the option trade commission in the adjusted stock cost basis or proceeds.

**Reasoning:** When an option is exercised/assigned, the full option cost (premium + commission) becomes part of the stock cost/proceeds adjustment. This is economically correct and matches German tax treatment for Termingeschäfte.

**Updated Expected Values:**

| Test | Field | Before | After | Reason |
|------|-------|--------|-------|--------|
| OPT_CALL_EX_001 | cost_basis | 5501 | 5502 | +1 option commission |
| OPT_CALL_EX_001 | gain_loss | 498 | 497 | |
| OPT_PUT_ASGN_001 | cost_basis | 4701 | 4702 | +1 (net premium reduced by commission) |
| OPT_PUT_ASGN_001 | gain_loss | -202 | -203 | |
| OPT_CCALL_ASGN_001 | proceeds | 5699 | 5698 | -1 (net premium reduced by commission) |
| OPT_CCALL_ASGN_001 | gain_loss | 698 | 697 | |
| OPT_PUT_EX_001 | proceeds | 5099 | 5098 | -1 option commission |
| OPT_PUT_EX_001 | gain_loss | -902 | -903 | |

## Commission Handling Logic

For option exercise/assignment, the engine correctly includes all costs:

**Long Option Exercise (adds to stock cost):**
- Stock cost = (Strike × Qty) + Stock_Commission + (Premium + Option_Commission)

**Short Option Assignment (reduces stock cost):**
- Stock cost = (Strike × Qty) + Stock_Commission - (Premium - Option_Commission)

**Short Option Assignment (adds to stock proceeds):**
- Stock proceeds = (Strike × Qty) - Stock_Commission + (Premium - Option_Commission)

**Long Option Exercise with Put (reduces stock proceeds):**
- Stock proceeds = (Strike × Qty) - Stock_Commission - (Premium + Option_Commission)

## Commands

```bash
# Run all option tests
uv run pytest tests/test_options_lifecycle.py -v

# Run full test suite
uv run pytest

# Run specific test
uv run pytest tests/test_options_lifecycle.py -k "OPT_CALL_EX_001" -v
```

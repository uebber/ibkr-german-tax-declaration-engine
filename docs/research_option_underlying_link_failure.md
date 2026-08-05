# Research: Option Underlying Link Failure (2025 Validation)

## Problem Statement

Running `validate_ledgers.py --year 2025` fails with:

```
CRITICAL Option asset CONID:CONID_OPT (ID: e68815a6-e046-44c0-91e5-a512c189b064)
  is missing underlying link. Cannot process exercise event 2a273fb5-...
ValueError: Option asset e68815a6-... missing underlying link for exercise.
```

The pipeline aborts entirely — no results are produced for 2025.

---

## Root Cause

The option CONID:CONID_OPT (an ESTX50 call, strike 4950, expiry 2025-07-18) is exercised, but its `underlying_asset_internal_id` is `None`. The engine cannot process the exercise without knowing which stock the option resolves to.

The underlying stock (ESTX50, CONID:CONID_UND) is never created as an asset because no trade, position, or corporate action row in the CSV data references it directly. The option's CSV row carries `UnderlyingConid=CONID_UND` and `UnderlyingSymbol=ESTX50`, but these are only stored as metadata on the Option object — they are not used to pre-create the underlying asset.

---

## How Underlying Links Are Resolved

### Step 1: Option asset creation (`asset_resolver.py:212-218`)

When a trade CSV row for an option is parsed, `get_or_create_asset()` creates an `Option` with:
- `underlying_ibkr_conid = "CONID_UND"` (from CSV `UnderlyingConid`)
- `underlying_ibkr_symbol = "ESTX50"` (from CSV `UnderlyingSymbol`)
- `underlying_asset_internal_id = None` (not yet resolved)

These IBKR-level identifiers are stored but the UUID link is deferred.

### Step 2: `link_derivatives()` (`asset_resolver.py:348-371`)

Called after all CSV files are parsed (`parsing_orchestrator.py:583`). For each Option with `underlying_asset_internal_id is None`:

1. **CONID lookup** (line 352-355): looks up `f"CONID:{underlying_ibkr_conid}"` in `alias_map`
2. **Symbol fallback** (line 358-367): looks up `f"SYMBOL:{underlying_ibkr_symbol}"` — requires exactly one non-CashBalance match

If neither lookup finds an asset, `underlying_asset_internal_id` stays `None`.

### Why it fails for CONID:CONID_OPT

The underlying ESTX50 stock (CONID:CONID_UND) never appears in any CSV as a direct trade, position, or corporate action. Therefore:
- `alias_map["CONID:CONID_UND"]` does not exist
- `alias_map["SYMBOL:ESTX50"]` either doesn't exist or is ambiguous (the Option itself may have registered `SYMBOL:ESTX50`)

Result: `underlying_asset_internal_id` remains `None`.

---

## Where the Error Is Raised

### `option_processor.py:45-48` (OptionExerciseProcessor)

```python
if option_asset.underlying_asset_internal_id is None:
    logger.critical(...)
    raise ValueError(f"Option asset {option_asset.internal_asset_id} missing underlying link for exercise.")
```

This is a hard failure — `raise ValueError` — which propagates up to `calculation_engine.py` and aborts the entire pipeline. The same pattern exists for assignments at `option_processor.py:99-102`.

---

## Additional Complication: Duplicate Lookup Keys

The 2025 validation log shows six "Duplicate key" warnings, all involving CONID:CONID_UND (ESTX50 underlying):

```
Duplicate key ('2025-07-18', 'CONID_UND', '20')   — OPTION_ASSIGNMENT overwritten by OPTION_EXERCISE
Duplicate key ('2025-07-18', 'CONID_UND', '200')  — OPTION_ASSIGNMENT overwritten by OPTION_ASSIGNMENT
Duplicate key ('2025-10-31', 'CONID_UND', '300')  — OPTION_ASSIGNMENT overwritten by OPTION_ASSIGNMENT
Duplicate key ('2025-11-21', 'CONID_UND', '200')  — OPTION_ASSIGNMENT overwritten by OPTION_ASSIGNMENT
Duplicate key ('2025-12-19', 'CONID_UND', '1400') — OPTION_ASSIGNMENT overwritten by OPTION_ASSIGNMENT
Duplicate key ('2025-12-19', 'CONID_UND', '400')  — OPTION_ASSIGNMENT overwritten by OPTION_ASSIGNMENT
```

The option trade linker (`option_trade_linker.py:45-52`) uses a dict keyed by `(date, underlying_conid, qty)`. When two option events produce the same key, the last one wins. This means some option events lose their link to the corresponding stock trade, which may cause incorrect premium adjustments even when the underlying link is otherwise resolved.

This is a **separate but related issue** — even if the underlying link failure is fixed, the duplicate-key problem will cause silent data loss for multi-contract option scenarios on the same underlying on the same day.

---

## Affected Code Paths (with line numbers)

| File | Lines | Role |
|------|-------|------|
| `src/identification/asset_resolver.py` | 212-218 | Option creation with underlying IBKR fields |
| `src/identification/asset_resolver.py` | 321-333 | Derivative attribute update on re-encounter |
| `src/identification/asset_resolver.py` | 348-371 | `link_derivatives()` — UUID resolution via alias_map |
| `src/parsers/parsing_orchestrator.py` | 583 | Call site for `link_derivatives()` |
| `src/processing/option_trade_linker.py` | 16-55 | `_build_option_event_lookup()` — builds 3-tuple key map |
| `src/processing/option_trade_linker.py` | 45-52 | Duplicate key handling (last-wins overwrite) |
| `src/processing/option_trade_linker.py` | 57-106 | `link_trades()` — matches stock trades to option events |
| `src/engine/event_processors/option_processor.py` | 22-74 | `OptionExerciseProcessor.process()` — raises if no link |
| `src/engine/event_processors/option_processor.py` | 76-128 | `OptionAssignmentProcessor.process()` — raises if no link |
| `src/engine/event_processors/trade_processor.py` | 88-109 | Stock trade premium adjustment — validates link integrity |
| `src/parsers/domain_event_factory.py` | 185-214 | Trade parsing and option lifecycle event creation |

---

## Potential Fix Strategies

### Strategy A: Pre-create underlying assets from option metadata

In `link_derivatives()` (or a new method called before it), when the underlying cannot be found in the alias_map, use the option's `underlying_ibkr_conid` and `underlying_ibkr_symbol` to create a minimal Stock asset and register it.

**Pros:** Simple, solves the immediate problem.
**Cons:** Creates a "phantom" asset with no trade history, potentially confusing in reports. Needs careful handling — the asset should probably be flagged as synthetic.

### Strategy B: Create the underlying during `get_or_create_asset()` for options

When creating an Option asset and `raw_underlying_conid` / `raw_underlying_symbol` are provided, immediately create or look up the underlying Stock asset and set the link.

**Pros:** Link is established at creation time, no deferred resolution needed.
**Cons:** May create assets prematurely from partial data. The underlying's full details (ISIN, currency, etc.) may not be available from the option's CSV row alone.

### Strategy C: Graceful degradation instead of hard failure

Change `option_processor.py:45-48` and `99-102` from `raise ValueError` to a warning + skip. The exercise/assignment event would be logged but not processed.

**Pros:** Pipeline no longer aborts; other 2025 data is still processed.
**Cons:** Incorrect tax figures — the option premium is not folded into the stock's cost basis. Should only be a fallback, not the primary fix.

### Strategy D: Fix the duplicate-key problem in option_trade_linker

Change the lookup from `Dict[Tuple, Event]` to `Dict[Tuple, List[Event]]` so multiple events with the same key are preserved. Match stock trades to option events using additional criteria (e.g., option conid, strike, put/call) to disambiguate.

**Pros:** Fixes the silent data loss for multi-contract scenarios.
**Cons:** More complex matching logic; doesn't solve the missing underlying asset problem by itself.

### Recommended approach

Combine **Strategy B** (create underlying during option asset creation) with **Strategy D** (fix duplicate-key deduplication). Strategy C could be added as a safety net to prevent pipeline aborts for edge cases.

---

## How to Reproduce

```bash
uv run python validate_ledgers.py --year 2025
```

The error occurs during the calculation engine phase. To see detailed logs:

```bash
uv run python -m src.main --tax-year 2025 2>&1 | grep -i "underlying\|CONID_OPT\|CONID_UND\|duplicate key"
```

---

## Validation Status (as of 2026-03-08)

| Year | Status | Notes |
|------|--------|-------|
| 2021 | Unknown | Not validated this session |
| 2022 | FAIL | a merger lot issue (see the maintainer's private notes) + USD currency gap (unrelated) |
| 2023 | PASS | Commission rebate fix resolved USD -55.32 gap |
| 2024 | WARN | USD -0.51 residual (down from -21.18 after commission fix) |
| 2025 | FAIL | This issue — option underlying link failure aborts pipeline |

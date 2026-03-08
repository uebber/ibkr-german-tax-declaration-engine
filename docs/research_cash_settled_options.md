# Research: Cash-Settled Options — Missing Data & Flex Query Fix

## Problem

Cash-settled index options (SPX, ESTX50) are traded in the account but never produce proper RealizedGainLoss entries. The engine was built entirely for physically-delivered options, where an exercise/assignment results in a stock trade. For cash-settled index options, no stock trade ever occurs — the settlement is a cash payment equal to the intrinsic value.

## Findings

### 1. Cash-settled options ARE in the CSV data

The Trades-2025.csv contains:
- **168 SPX trades** (multiplier 100, USD)
- **136 ESTX50 trades** (multiplier 10, EUR)

Exercises and assignments appear as regular trade rows with `TradePrice=0` and `Notes/Codes` = "A" (assignment) or "Ex" (exercise). Example:

```
AssetClass=OPT, Symbol="SPX 251219C05200000", TradeDate=2025-12-19,
Quantity=40, TradePrice=0, Notes/Codes=A, UnderlyingSymbol=SPX
```

### 2. The settlement cash amount is NOT captured anywhere

- **Trades CSV**: Has `TradePrice=0` for exercises/assignments — no Proceeds column exists
- **Cash_Transactions CSV**: Contains NO option settlement entries (only dividends, interest, fees, WHT)
- **No other CSV** captures the intrinsic value payout

### 3. The code fails on these options

The engine requires `underlying_asset_internal_id` for exercises/assignments (to link to a stock trade). For index options like SPX/ESTX50, no underlying stock trade exists, causing a `ValueError`. This is the 2025 validation failure documented in `docs/research_option_underlying_link_failure.md`.

### 4. IBKR has a dedicated Flex Query section for this

**"Option Exercises, Assignments and Expirations"** (XML element: `OptionEAE`) is a separate Activity Flex Query section that includes:

| Field | Description |
|-------|-------------|
| Transaction Type | Assignment, Exercise, or Expiration |
| Quantity | Number of contracts |
| Trade Price | Exercise/settlement price |
| **Proceeds** | **Quantity x Transaction Price — this is the cash settlement amount** |
| Basis | Cost basis of the option position |
| **Realized P/L** | **Net gain/loss including premium paid/received** |
| Comm/Tax | Commissions and taxes |
| Strike, Expiry, Put/Call | Option contract details |
| Conid, Underlying Conid/Symbol | Contract identifiers |
| Currency, FX Rate to Base | Currency info |
| Asset Class, ISIN, CUSIP, FIGI | Security identifiers |

This section explicitly states it handles **"cash settlement for index options and structured products"**.

Sources:
- [IBKR OptionEAE Field Reference](https://www.ibkrguides.com/reportingreference/reportguide/options_exercises_expirations_fq.htm)
- [Activity Flex Query Reference](https://www.ibkrguides.com/reportingreference/reportguide/activity%20flex%20query%20reference.htm)
- [Cash Settlement Definition](https://www.interactivebrokers.com/campus/glossary-terms/cash-settlement-amount/)

## OptionEAE Data Analysis (from `Gemini_Options_EAE-*.csv`)

The OptionEAE Flex Query data has been downloaded. Files: `data_import/Gemini_Options_EAE-{2021..2025}.csv`

### CSV Header (22 columns)

```
ClientAccountID, CurrencyPrimary, FXRateToBase, AssetClass, Symbol, Description,
Conid, ISIN, UnderlyingConid, UnderlyingSymbol, Multiplier, Strike, Expiry,
Put/Call, Date, Transaction Type, Quantity, Trade Price, Proceeds, Comm/Tax,
Basis, RealizedPnl
```

### Data Structure — Three Transaction Types

Each option lifecycle event produces **different row patterns** depending on settlement type:

#### 1. Cash-Settled Options (SPX, ESTX50) — TWO rows per event

**Row 1: Assignment/Exercise** — closes the option position
```
TransactionType=Assignment, Quantity=40, TradePrice=0, Proceeds=0, Comm/Tax=0, Basis=0
```

**Row 2: Cash Settlement** — records the actual cash payout
```
TransactionType="Cash Settlement", Quantity=0, TradePrice=0, Proceeds=-6386160, Comm/Tax=0
```

The Proceeds in the "Cash Settlement" row is the cash amount paid/received. Negative = paid out (short position was assigned), positive = received (long position was exercised).

**Example — SPX 5200 Call assigned (short 40 contracts):**
- Row 1: `Assignment, Qty=40, Proceeds=0`
- Row 2: `Cash Settlement, Qty=0, Proceeds=-6,386,160` (paid out: settlement value above strike × 100 × 40)

**Example — ESTX50 4950 Call exercised (long 2 contracts):**
- Row 1: `Exercise, Qty=-2, Proceeds=0`
- Row 2: `Cash Settlement, Qty=0, Proceeds=8,982.80` (received: settlement value above strike × 10 × 2)

#### 2. Physically-Settled Options (IBIT, MU, TLT, GME, LEG, etc.) — TWO rows per event

**Row 1: Assignment/Exercise** — closes the option position
```
TransactionType=Assignment, Qty=3, TradePrice=0, Proceeds=0
```

**Row 2: Stock Buy/Sell** — the underlying stock delivery
```
AssetClass=STK, TransactionType=Buy/Sell, Qty=300, TradePrice=64, Proceeds=-19200
```

The stock delivery row has `AssetClass=STK` and includes the strike as `TradePrice` with proper Proceeds.

#### 3. Expirations (all types) — ONE row

```
TransactionType=Expiration, Qty=±N, TradePrice=0, Proceeds=0, Basis=0, RealizedPnl=0
```

Positive quantity = long position expired worthless. Negative = short position expired worthless.

### Key Observations

1. **"Cash Settlement" is a distinct Transaction Type** — not Assignment or Exercise. It always appears as a companion row immediately after the Assignment/Exercise row.

2. **Basis and RealizedPnl are always 0** in this report — IBKR does not populate these fields. The premium cost basis must still come from the Trades CSV FIFO tracking.

3. **Proceeds sign convention for cash settlements:**
   - Negative = money paid out (you were short and assigned, intrinsic value owed)
   - Positive = money received (you were long and exercised, intrinsic value received)

4. **No cash-settled options exist before 2025** in this account — years 2021-2024 contain only physically-settled exercises/assignments and expirations.

5. **Physical delivery rows duplicate Trades CSV data** — the STK rows in OptionEAE match what already appears in the Trades file. Only the "Cash Settlement" rows contain truly new information.

### Data Summary by Year

| Year | Assignments | Exercises | Cash Settlements | Expirations | Total Rows |
|------|-------------|-----------|------------------|-------------|------------|
| 2021 | 0 | 0 | 0 | 17 | 17 |
| 2022 | 1 | 2 | 0 | 6 | 13 (incl STK rows) |
| 2023 | 6 | 2 | 0 | 17 | 40 (incl STK rows) |
| 2024 | 7 | 0 | 0 | 19 | 33 (incl STK rows) |
| 2025 | 18 | 2 | 12 | 24 | 72 (incl STK rows) |

## Future Code Changes Needed

Once parsing is implemented, the following code areas need updates:
- `src/config.py` — add query ID to `FLEX_QUERY_IDS`
- `src/flex_downloader.py` — add to download list
- `src/data_preparation.py` — add file handling for `Gemini_Options_EAE-{YYYY}.csv`
- `src/parsers/` — new parser for OptionEAE CSV format, extracting "Cash Settlement" rows
- `src/engine/event_processors/option_processor.py` — handle cash-settled exercises: generate RGL from Cash Settlement Proceeds instead of requiring underlying stock trade
- `src/processing/option_trade_linker.py` — skip linking for cash-settled options

### Critical Design Decision

The "Cash Settlement" Proceeds field provides the **total intrinsic value** exchanged, not the net P/L. To compute the taxable gain/loss, the engine must still:
1. Track the option premium via FIFO (from Trades CSV open/close trades)
2. Use the Cash Settlement Proceeds as the realization value
3. Calculate: `Gain/Loss = Cash Settlement Proceeds - Option Premium Cost Basis ± Commissions`

Sources:
- [IBKR OptionEAE Field Reference](https://www.ibkrguides.com/reportingreference/reportguide/options_exercises_expirations_fq.htm)
- [Activity Flex Query Reference](https://www.ibkrguides.com/reportingreference/reportguide/activity%20flex%20query%20reference.htm)
- [Cash Settlement Definition](https://www.interactivebrokers.com/campus/glossary-terms/cash-settlement-amount/)

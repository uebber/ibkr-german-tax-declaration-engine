## General Information
- **CSV Encoding:** All input CSV files are expected to be `utf-8-sig` encoded.
- **Decimal Parsing:** Numerical monetary values and quantities are parsed into Python's `Decimal` type, preserving precision from the string representation. A blank **optional** decimal is `None` — absent, not zero. A blank **required** decimal fails validation, and by the row rule below that stops the run. There is no `Decimal("1.0")` default; the description that claimed one predates issue #47.
- **`Optional` in the tables below is the Pydantic annotation, not a claim that IBKR omits the column.** What the exports actually contain is settled in `data_import/`, and measured over 2021–2025, every file:
  - **No `Decimal` column has ever been blank, in any of the six exports. Not once.**
  - **Blanks are descriptor columns only, and mean *not applicable*, not *missing*.** Trades: `Strike` / `Expiry` / `Put/Call` / `UnderlyingConid` ~75% (the non-options), `UnderlyingSymbol` ~47%, `ISIN` ~32%, `Notes/Codes` ~23%, `SubCategory` and `Open/CloseIndicator` ~8% (currency trades). Cash transactions: every instrument identifier, 88–98%. Positions: `ISIN` ~20%, `UnderlyingSymbol` ~48%, `UnderlyingConid` ~79%. Corporate actions: `Code` and the underlying pair, always. Options EAE: `ISIN` ~82%, option terms and underlying identifiers 11–17%. Cash balance: never.
  - Regenerate rather than quoting these forever — the window is the input window. **Count before treating a blank column as a case to handle** (CLAUDE.md, Gates).
- **Date Parsing:** Date strings are parsed from various common formats (e.g., YYYY-MM-DD, YYYYMMDD) into Python `datetime.date` or `datetime.datetime` objects.
- **Column Validation:** Each parser validates that the CSV header row contains exactly the columns defined in `src/parsers/column_validator.py`. Missing or unexpected columns cause a `ValueError` before any rows are parsed. This ensures the IBKR Flex Query export configuration matches what the engine expects. This sentence was true of `validate_csv_columns` and false of the parsers until August 2026: each caught the `ValueError` one frame later, printed it and returned an empty record list.
- **Row failures are fatal, and reported together.** A row that fails model validation is not skipped. `src/parsers/csv_reader.py` collects every such row in a file and raises `DataIntegrityError` naming each one — its line number, its `TransactionID`/`ActionID` where the export carries one, and the columns that failed with the values they contained. A missing file raises `FileNotFoundError` rather than reading as empty.

---

## 1. Trades File
- **Input:** `data_import/Trades-{YYYY}.csv`, concatenated across every year <= the tax year
- **Associated Pydantic Model:** `RawTradeRecord`

**Column Specifications** — `TRADES_COLUMNS` in `src/parsers/column_validator.py`, checked
against every real export by `tests/test_raw_model_fields.py`:

| CSV Header             | Model Field Name (Pydantic) | Model Data Type             | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                                                               |
|------------------------|-----------------------------|-----------------------------|-----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`      | `client_account_id`         | `Optional[str]`             | The client's account identifier.                                            | Optional. Example: "U1234567"                                                                                                                                              |
| `CurrencyPrimary`      | `currency_primary`          | `str`                       | The primary currency of the transaction or asset.                           | Required. Example: "EUR", "USD"                                                                                                                                            |
| `AssetClass`           | `asset_class`               | `str`                       | The asset class of the instrument (e.g., STK, OPT, CASH, BOND, CFD).        | Required. Example: "BOND", "CASH", "CFD", "OPT", "STK"                                                                                                                      |
| `SubCategory`          | `sub_category`              | `Optional[str]`             | Sub-category of the asset (e.g., COMMON, ETF, ADR for STK).                 | Optional. Example: "Corp", "COMMON", "ADR", "ETF"                                                                                                                          |
| `Symbol`               | `symbol`                    | `str`                       | The trading symbol of the instrument.                                       | Required. Example: "VW 0 3/4 06/15/23", "EUR.USD", "IWO", "TIO   230616C00001000"                                                                                          |
| `Description`          | `description`               | `str`                       | A textual description of the instrument or transaction.                     | Required. Example: "VW 0 3/4 06/15/23", "EUR.USD", "USD IWO"                                                                                                               |
| `ISIN`                 | `isin`                      | `Optional[str]`             | International Securities Identification Number.                             | Optional. Example: "XS0000000003", "US0000000004"                                                                                                                          |
| `Strike`               | `strike`                    | `Optional[Decimal]`         | The strike price of an option.                                              | Optional, relevant for OPT. Example: "1.0", "111.0"                                                                                                                        |
| `Expiry`               | `expiry`                    | `Optional[str]`             | The expiry date of an option or future (YYYY-MM-DD).                        | Optional, relevant for OPT/FUT. Parsed as string. Example: "2023-06-16"                                                                                                     |
| `Put/Call`             | `put_call`                  | `Optional[str]`             | Indicates if an option is a Put ('P') or Call ('C').                        | Optional, relevant for OPT. Example: "C", "P"                                                                                                                              |
| `TradeDate`            | `trade_date`                | `str`                       | The **contract** date (YYYY-MM-DD) — the obligatorisches Rechtsgeschäft, and the only date of a trade this engine recognises. | Required. Parsed as string. Example: "2023-03-13". **Do not add `SettleDateTarget` to this query** — see the note under this table.                                        |
| `Quantity`             | `quantity`                  | `Decimal`                   | The number of units traded. Positive for buy, negative for sell.            | Required. Example: "20000.0", "-11.0"                                                                                                                                      |
| `TradePrice`           | `trade_price`               | `Decimal`                   | The price per unit for the trade.                                           | Required. Example: "11.00", "1.00000", "1.00"                                                                                                                              |
| `IBCommission`         | `ib_commission`             | `Optional[Decimal]`         | Commission charged by Interactive Brokers for the trade.                    | Optional. Usually negative. Example: "-11.0", "-1.00000"                                                                                                                   |
| `IBCommissionCurrency` | `ib_commission_currency`    | `Optional[str]`             | The currency of the IB commission.                                          | Optional. Example: "EUR", "USD"                                                                                                                                            |
| `Buy/Sell`             | `buy_sell`                  | `Optional[str]`             | Indicates if the trade was a buy or sell.                                   | Optional. "BUY" or "SELL". Crucial for determining `FinancialEventType`. Code has fallbacks if missing.                                                                    |
| `TransactionID`        | `transaction_id`            | `Optional[str]`             | IBKR's unique identifier for the transaction.                               | Optional, but highly recommended. Example: "9000000000"                                                                                                                    |
| `Notes/Codes`          | `notes_codes`               | `Optional[str]`             | Codes related to the trade (e.g., P, A, Ex, Ep).                            | Optional. Used to identify exercises, assignments, expirations. Example: "P", "A", "Ep", "Ex"                                                                               |
| `UnderlyingSymbol`     | `underlying_symbol`         | `Optional[str]`             | The symbol of the underlying asset for derivatives.                         | Optional, relevant for OPT/FUT/CFD. Example: "TIO", "IWO"                                                                                                                  |
| `Conid`                | `conid`                     | `Optional[str]`             | IBKR's contract identifier for the instrument.                              | Optional. Example: "900003167", "90000633"                                                                                                                                 |
| `UnderlyingConid`      | `underlying_conid`          | `Optional[str]`             | IBKR's contract identifier for the underlying asset.                        | Optional, relevant for OPT/FUT/CFD. Example: "900003959.0" (parsed as string)                                                                                              |
| `Multiplier`           | `multiplier`                | `Optional[Decimal]`         | The contract multiplier (e.g., for options, futures).                     | Optional. Example: "1", "100"                                                                                                                                              |
| `Open/CloseIndicator`  | `open_close_indicator`      | `Optional[str]`             | Indicates if trade opens or closes a position ('O' or 'C').                 | Crucial for determining `FinancialEventType` for standard financial instrument trades in conjunction with `Buy/Sell` (refer to PRD Section 5, Step 7). Expected values: 'O' (Open), 'C' (Close). Missing or invalid values for relevant trades constitute a data inconsistency. Not applicable to currency pair trades (e.g., FX 'CASH' asset class trades like EUR.USD). The exports carry the column. Measured 2021–2025: blank on 586 rows, 584 of them `AssetClass=CASH` — **the other two are the data inconsistency this note describes, and they are real rows, not a hypothetical.** |

### A trade has one date, and it is the contract date

`TradeDate` is the only date of a trade this engine uses, and it is used because the law names it,
not because it is the field that happens to be present. The obligatorisches Rechtsgeschäft fixes
the assessment year, the ECB rate the amounts are converted at, the § 23 Jahresfrist and the month
the § 18 Abs. 2 InvStG twelfths count from — see `[GT-ESTG20-039]` and `[GT-ESTG20-040]` in
`reference/bmf-guidance/abgeltungsteuer-einzelfragen.md`.

**Do not add `SettleDateTarget` to the Flex Query.** It is not in `TRADES_COLUMNS`, the trades
parser validates with `allow_extra=False`, and the field was removed from the raw model in August
2026. Before that the engine ordered settlement ahead of trade date and produced the right answer
only because IBKR does not export the column — a declared-but-unread date field is how that
happened, and there is now nowhere for a settlement date to land.

`TradeTime` and `ReportDate` went the same way in the sweep that followed (issue #64). Neither is
exported, and both were declared on `RawTradeRecord`; the trade rule now takes a single parameter,
so there is no slot for either even if a future query started carrying them.

A settlement date is the right date for a **cash transaction**, where the taxable moment is the
Zufluss; that is the `SettleDate` column of the next file, and the distinction is deliberate.

### Adding a column means two edits, not one

Every field on a raw model must have its header in the matching `*_COLUMNS` tuple, and
`tests/test_raw_model_fields.py` fails if one does not. A field declared for a column no query
requests can never be populated, but it reads as a supported input at every call site, so the next
person wires a fallback to it and the fallback is dead in a way nothing fails on — which is exactly
how the settlement date became the engine's default. Adding a column therefore means adding it to
the Flex Query **and** to the tuple **and** to the model, together.

---

## 2. Cash Transactions File
- **Input:** `data_import/Cash_Transactions-{YYYY}.csv`, concatenated across every year <= the tax year
- **Associated Pydantic Model:** `RawCashTransactionRecord`

**Column Specifications** — `CASH_TRANSACTIONS_COLUMNS`, checked against every real export:

| CSV Header         | Model Field Name (Pydantic) | Model Data Type   | Description                                                                          | Notes (Optionality, Example, Parsing Detail)                                                                                                |
|--------------------|-----------------------------|-------------------|--------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`  | `client_account_id`         | `Optional[str]`   | The client's account identifier.                                                     | Optional. Example: "U1234567"                                                                                                               |
| `CurrencyPrimary`  | `currency_primary`          | `str`             | The currency of the cash transaction.                                                | Required. Example: "CAD", "JPY", "EUR"                                                                                                      |
| `AssetClass`       | `asset_class`               | `Optional[str]`   | Asset class related to the cash transaction (e.g., STK, BOND). Can be empty/null.    | Optional. Example: "STK", "BOND", or empty.                                                                                                 |
| `SubCategory`      | `sub_category`              | `Optional[str]`   | Sub-category of the asset (e.g., COMMON). Can be empty/null.                         | Optional. Example: "COMMON", or empty.                                                                                                      |
| `Symbol`           | `symbol`                    | `Optional[str]`   | Symbol of the instrument related to the cash flow. Can be empty/null.                | Optional. Example: "BNS", "9022.T", or empty.                                                                                               |
| `Description`      | `description`               | `str`             | Detailed description of the cash transaction. Crucial for type determination.        | Required. Example: "ABC (CA0000000006) CASH DIVIDEND CAD 1.03 - CA TAX"                                                                   |
| `SettleDate`       | `settle_date`               | `str`             | The settlement date of the cash transaction (YYYY-MM-DD).                            | Required. Parsed as string. Example: "2023-01-27"                                                                                           |
| `Amount`           | `amount`                    | `Decimal`         | The monetary amount of the cash transaction. Positive for inflow, negative for outflow. | Required. Example: "-11.0", "1.00", "7000.0"                                                                                                |
| `Type`             | `type`                      | `str`             | The type of cash transaction (e.g., Dividends, Withholding Tax).                     | Required. Example: "Withholding Tax", "Dividends", "Broker Interest Received"                                                               |
| `Conid`            | `conid`                     | `Optional[str]`   | IBKR's contract identifier for the related instrument. Can be empty/null.            | Optional. Example: "4457153.0" (parsed as string), or empty.                                                                                |
| `UnderlyingConid`  | `underlying_conid`          | `Optional[str]`   | IBKR Conid of the underlying for derivative-related cash flows. Can be empty/null.   | Optional. Empty in sample.                                                                                                                  |
| `ISIN`             | `isin`                      | `Optional[str]`   | ISIN of the related instrument. Can be empty/null.                                   | Optional. Example: "CA0000000006", or empty.                                                                                               |
| `IssuerCountryCode`| `issuer_country_code`       | `Optional[str]`   | ISO country code of the issuer or tax authority.                                     | Optional. Example: "CA", "JP", or empty. Used for WHT source country.                                                                       |
| `TransactionID`    | `transaction_id`            | `Optional[str]`   | IBKR's unique identifier for the transaction.                                        | Optional, but highly recommended. Example: "9000007919"                                                                                     |

**Required IBKR Transaction Types (Flex Query Configuration):**

The Flex Query must include **all** of the following transaction types to ensure complete currency balance tracking:

| Transaction Type              | Engine Classification                       | Currency Impact                            |
|-------------------------------|---------------------------------------------|--------------------------------------------|
| Dividends                     | `DIVIDEND_CASH` (income)                    | Creates currency lot                       |
| Withholding Tax               | `WITHHOLDING_TAX` (expense)                 | Consumes currency lot                      |
| Broker Interest Received      | `INTEREST_RECEIVED` (income)                | Creates currency lot                       |
| Broker Interest Paid          | `FEE_TRANSACTION` (expense)                 | Consumes currency lot                      |
| Payment In Lieu Of Dividends  | `DIVIDEND_CASH` or `FEE_TRANSACTION`        | Creates or consumes lot (sign-based)       |
| Bond Interest Received        | `INTEREST_RECEIVED` (income)                | Creates currency lot                       |
| Bond Interest Paid            | `INTEREST_PAID_STUECKZINSEN` (expense)      | Consumes currency lot                      |
| Other Fees                    | `FEE_TRANSACTION` (expense)                 | Consumes currency lot                      |
| Deposits/Withdrawals          | Handled by sign-based classification        | Creates or consumes lot                    |
| Commission Adjustments        | `FEE_TRANSACTION` (expense)                 | Consumes currency lot                      |

Missing transaction types cause currency EOY balance mismatches (FIFO-tracked balance diverges from IBKR-reported balance).

---

## 3. Positions File (Start of Year / End of Year)
- **Input:** `data_import/Positions-{YYYY}-SoY.csv` and `-EoY.csv`, one snapshot per year, never
  concatenated; `src/data_preparation.py` writes the working copies `positions_start_of_year.csv`
  and `positions_end_of_year.csv` under `data/`
- **Associated Pydantic Model:** `RawPositionRecord`

**Column Specifications** — `POSITIONS_COLUMNS`, checked against every real export:

| CSV Header         | Model Field Name (Pydantic) | Model Data Type   | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                                                                           |
|--------------------|-----------------------------|-------------------|-----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`  | `client_account_id`         | `Optional[str]`   | The client's account identifier.                                            | Optional. **Load-bearing:** it decides which account's FIFO ledger the row reconciles against, per Depot ([GT-ESTG20-013]). Mapped since per-Depot lot tracking gave it a caller; before that `RawPositionRecord` declared no field and `Config.extra = 'ignore'` discarded it. Example: "U1234567" |
| `CurrencyPrimary`  | `currency_primary`          | `str`             | The currency of the position.                                               | Required. Example: "CAD", "EUR", "SGD"                                                                                                                                                 |
| `AssetClass`       | `asset_class`               | `str`             | The asset class of the instrument (e.g., STK, OPT).                         | Required. Example: "STK", "OPT"                                                                                                                                                        |
| `SubCategory`      | (Ignored by model)          | `N/A`             | Sub-category of the asset (e.g., COMMON, ETF).                              | Present in CSV. Ignored by `RawPositionRecord` due to `Config.extra = 'ignore'`. Example: "COMMON", "ETF"                                                                                |
| `Symbol`           | `symbol`                    | `str`             | The trading symbol of the instrument.                                       | Required. Example: "ABC", "XAUd", "P ABC  20230120 63 M"                                                                                                                              |
| `Description`      | `description`               | `str`             | A textual description of the instrument.                                    | Required. Example: "EXAMPLE BANK CORP", "EXAMPLE GOLD ETC"                                                                                                                                 |
| `ISIN`             | `isin`                      | `Optional[str]`   | International Securities Identification Number.                             | Optional. Example: "CA0000000006", "DE0000000005"                                                                                                                                      |
| `Quantity`         | `position`                  | `Decimal`         | The number of units held. Positive for long, negative for short.            | Required. (Aliased from `Quantity` in CSV to `position` in model). Example: "100", "-100"                                                                                                 |
| `PositionValue`    | `position_value`            | `Optional[Decimal]`| The market value of the position in `CurrencyPrimary`.                      | Optional. Example: "10000", "10000"                                                                                                                                                    |
| `MarkPrice`        | `mark_price`                | `Optional[Decimal]`| The mark-to-market price per unit.                                          | Optional. Example: "60.00", "50.00", "1.00"                                                                                                                                            |
| `CostBasisMoney`   | `cost_basis_money`          | `Optional[Decimal]`| The total cost basis of the position in `CurrencyPrimary`.                  | Optional. Example: "10000", "20100.500", "-750.00" (negative for short proceeds)                                                                                                      |
| `UnderlyingSymbol` | `underlying_symbol`         | `Optional[str]`   | The symbol of the underlying asset for derivatives.                         | Optional, relevant for OPT. Example: "ABC"                                                                                                                                             |
| `Conid`            | `conid`                     | `Optional[str]`   | IBKR's contract identifier for the instrument.                              | Optional. Example: "4457153", "90000950", "604172754"                                                                                                                                  |
| `UnderlyingConid`  | `underlying_conid`          | `Optional[str]`   | IBKR's contract identifier for the underlying asset.                        | Optional, relevant for OPT. Example: "121764205"                                                                                                                                       |
| `Multiplier`       | `multiplier`                | `Optional[Decimal]`| The contract multiplier (e.g., for options).                              | Optional. Example: "1", "100"                                                                                                                                                          |

---

## 4. Corporate Actions File
- **Input:** `data_import/Corporate_Actions-{YYYY}.csv`, concatenated across every year <= the tax year
- **Associated Pydantic Model:** `RawCorporateActionRecord`

**Column Specifications** — `CORPORATE_ACTIONS_COLUMNS`, checked against every real export:

| CSV Header         | Model Field Name (Pydantic) | Model Data Type   | Description                                                                   | Notes (Optionality, Example, Parsing Detail)                                                                                                |
|--------------------|-----------------------------|-------------------|-------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`  | `client_account_id`         | `Optional[str]`   | The client's account identifier.                                              | Optional. Example: "U1234567"                                                                                                               |
| `Symbol`           | `symbol`                    | `str`             | The trading symbol of the instrument affected by the corporate action.        | Required. Example: "1234.T", "DEF", "GHI"                                                                                                  |
| `Description`      | `description`               | `str`             | Detailed description of the corporate action and the instrument.              | Required. Example: "1234.T(JP0000000001) SPLIT 5 FOR 1..."                                                                                 |
| `ISIN`             | `isin`                      | `Optional[str]`   | ISIN of the affected instrument.                                              | Optional. Example: "JP0000000001", "US0000000002"                                                                                           |
| `Report Date`      | `report_date`               | `str`             | The date the corporate action was reported (YYYY-MM-DD).                      | Required. Parsed as string. Example: "2023-09-28"                                                                                           |
| `Code`             | `code`                      | `Optional[str]`   | IBKR code related to the corporate action (e.g., for specific CA subtypes).   | Optional. Empty in sample.                                                                                                                  |
| `Type`             | `type_ca`                   | `str`             | IBKR's type code for the corporate action (e.g., FS, TC, HI, BM).             | Required (model field `type_ca`). Example: "FS", "TC", "HI", "BM" (Bond Maturity). For BM, `Proceeds` holds the total redemption cash and `Quantity` is negative (bonds removed). |
| `ActionID`         | `action_id_ibkr`            | `Optional[str]`   | IBKR's unique identifier for the corporate action event.                      | Optional. Example: "900004751"                                                                                                              |
| `Conid`            | `conid`                     | `Optional[str]`   | IBKR's contract identifier for the affected instrument.                       | Optional. Example: "90000712", "90000791"                                                                                                   |
| `UnderlyingConid`  | `underlying_conid`          | `Optional[str]`   | IBKR Conid of the underlying if the CA affects a derivative.                  | Optional. Empty in sample.                                                                                                                  |
| `UnderlyingSymbol` | `underlying_symbol`         | `Optional[str]`   | Symbol of the underlying if the CA affects a derivative.                      | Optional. Empty in sample.                                                                                                                  |
| `CurrencyPrimary`  | `currency_primary`          | `Optional[str]`   | The currency of monetary amounts involved in the CA.                          | Optional (model allows None). Example: "JPY", "USD", "EUR"                                                                                  |
| `Amount`           | (Ignored by model)          | `N/A`             | A monetary amount related to the CA.                                          | Present in CSV. Ignored by `RawCorporateActionRecord`; `Value` or `Proceeds` are used for monetary impact. **Not always zero** — see the note below and issue #69. |
| `Proceeds`         | `proceeds`                  | `Optional[Decimal]`| Monetary proceeds from the CA (e.g., cash from merger).                       | Optional. Example: "0", "10000"                                                                                                             |
| `Value`            | `value`                     | `Optional[Decimal]`| Monetary value related to the CA (e.g., FMV of stock dividend).               | Optional. Example: "0", "-10000", "111.00" (negative value seems to indicate cost/value given up in sample)                                   |
| `Quantity`         | `quantity`                  | `Optional[Decimal]`| Quantity of shares/units involved (e.g., new shares from split/dividend).   | Optional. Example: "100", "-100" (negative for shares disposed in merger), "5"                                                              |

### `Amount` is discarded, and that is not yet a decided position

This row used to read *"Present in CSV (value `0`)"*, which invited the conclusion that the
column is always zero and therefore safe to drop. **It is not always zero.** Across the 2021–2025
history most corporate actions do carry `0`, but at least one `TC` (merger for cash) row has a
non-zero `Amount` that disagrees with **both** `Proceeds` and `Value` on the same row — in sign
with one and in magnitude with the other. So on the single row where the three columns disagree,
the engine takes `Proceeds` and silently discards the one that dissents.

The engine also already picks between `Proceeds` and `Value` by CA type (`TC` + "CASH" →
`Proceeds`; `HI`/`SD` → `Value`) without a cited basis. Which of IBKR's three money columns is the
Veräußerungserlös for a Barabfindung is a `reference/` question, not a code question — see the
Ground Truth Rule in `CLAUDE.md`. Tracked as issue #69; do not add the field before the store
settles it.

---

## 5. Cash Balance File (Currency Balances)
- **Input:** `data_import/Cash_Balance-{YYYY}.csv`, one per year; `src/data_preparation.py` writes
  the working copy `cash_balance.csv` under `data/`
- **Purpose:** Records currency holdings at start and end of year for tracking FX positions and potential currency gains/losses under §23 EStG.
- **Associated Pydantic Model:** `RawCashBalanceRecord`

**Column Specifications (based on IBKR Cash Report Flex Query):**

| CSV Header              | Model Field Name (Pydantic) | Model Data Type     | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                               |
|-------------------------|-----------------------------|---------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`       | `client_account_id`         | `Optional[str]`     | The client's account identifier.                                            | Optional. **Load-bearing:** each account's balance in a currency is its own Kapitalforderung ([GT-FX-009]), so this decides which ledger the row builds and reconciles against. Ticking several accounts in one query puts them all in one file. Example: "U1234567" |
| `CurrencyPrimary`       | `currency_primary`          | `str`               | The currency code (ISO 4217).                                               | Required. Example: "EUR", "USD", "CHF", "JPY"                                                                                              |
| `FromDate`              | `from_date`                 | `str`               | Start date of the report period (YYYYMMDD).                                 | Required. Example: "10000000"                                                                                                              |
| `ToDate`                | `to_date`                   | `str`               | End date of the report period (YYYYMMDD).                                   | Required. Example: "10000000"                                                                                                              |
| `StartingCash`          | `starting_cash`             | `Decimal`           | Trade date cash balance at start of period.                                 | Required. Can be negative (margin/borrowed). Example: "29230.90000871", "-331.900002375"                                                   |
| `EndingCash`            | `ending_cash`               | `Decimal`           | Trade date cash balance at end of period.                                   | Required. Can be negative (margin/borrowed). Example: "-0.900001583", "1750.900005543"                                                     |

**Notes on Currency Taxation (§23 EStG):**
- Currency holdings held for less than 1 year are subject to private sale taxation under German tax law.
- Gains/losses are calculated using FIFO method against acquisition costs.
- The base currency (typically EUR) is not taxable; only foreign currency holdings are relevant.
- FX trade data from the Trades file is required to build the FIFO lot history for accurate gain/loss calculation.

**Reference:** [IBKR Cash Report Flex Statement](https://www.ibkrguides.com/reportingreference/reportguide/cash%20reportfq.htm)

---

## 6. Options Exercises, Assignments & Expirations File (Optional)
- **Input:** `data_import/Options_EAE-{YYYY}.csv`, concatenated across every year <= the tax year
- **Purpose:** Records option exercises, assignments, expirations, and cash settlements. Required for cash-settled index options (e.g. SPX, ESTX50) where no underlying stock trade exists. If you don't trade index options, this file is not needed.
- **When it is required is decided from the data, not from the filename.** Only the `Cash Settlement` rows carry information found nowhere else — the physical-delivery and Assignment/Exercise rows duplicate the Trades export. `ParsingOrchestrator._require_option_cash_settlements` pairs every assignment/exercise of an option with no resolvable underlying against its settlement row, and stops the run naming each unpaired contract. A `Cash Settlement` row whose `Proceeds` are zero is skipped at parse time and counts as absent.
- **Associated Pydantic Model:** `RawOptionsEAERecord`

**Column Specifications (based on IBKR Option Exercises, Assignments and Expirations Flex Query):**

| CSV Header              | Model Field Name (Pydantic) | Model Data Type     | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                               |
|-------------------------|-----------------------------|---------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`       | `client_account_id`         | `Optional[str]`     | The client's account identifier.                                            | Optional. Example: "U1234567"                                                                                                              |
| `CurrencyPrimary`       | `currency_primary`          | `str`               | Transaction currency.                                                       | Required. Example: "USD", "EUR"                                                                                                            |
| `FXRateToBase`          | `fx_rate_to_base`           | `Optional[Decimal]` | FX rate to base currency at time of transaction.                            | Optional. Example: "1.00"                                                                                                                  |
| `AssetClass`            | `asset_class`               | `str`               | Asset class (always OPT for this file).                                     | Required. Example: "OPT"                                                                                                                   |
| `Symbol`                | `symbol`                    | `str`               | Option contract symbol.                                                     | Required. Example: "SPX   241220C05900000"                                                                                                 |
| `Description`           | `description`               | `str`               | Contract description.                                                       | Required. Example: "SPX 20DEC24 5900.0 C"                                                                                                  |
| `Conid`                 | `conid`                     | `Optional[str]`     | Contract identifier.                                                        | Optional. Example: "604172754"                                                                                                             |
| `ISIN`                  | `isin`                      | `Optional[str]`     | ISIN of the option contract.                                                | Optional. Often empty for index options.                                                                                                   |
| `UnderlyingConid`       | `underlying_conid`          | `Optional[str]`     | Underlying contract ID.                                                     | Optional. Example: "100000"                                                                                                                |
| `UnderlyingSymbol`      | `underlying_symbol`         | `Optional[str]`     | Underlying symbol.                                                          | Optional. Example: "SPX", "ESTX50"                                                                                                         |
| `Multiplier`            | `multiplier`                | `Optional[Decimal]` | Contract multiplier.                                                        | Optional. Example: "100"                                                                                                                   |
| `Strike`                | `strike`                    | `Optional[Decimal]` | Strike price.                                                               | Optional. Example: "5900.0"                                                                                                                |
| `Expiry`                | `expiry`                    | `Optional[str]`     | Expiration date.                                                            | Optional. Example: "2024-12-20"                                                                                                            |
| `Put/Call`              | `put_call`                  | `Optional[str]`     | C or P.                                                                     | Optional. Example: "C", "P"                                                                                                                |
| `Date`                  | `date`                      | `str`               | Transaction date.                                                           | Required. Example: "2024-12-20"                                                                                                            |
| `Transaction Type`      | `transaction_type`          | `str`               | Type of option lifecycle event.                                             | Required. Values: "Assignment", "Exercise", "Expiration", "Cash Settlement". Only "Cash Settlement" rows are used; others duplicate Trades. |
| `Quantity`              | `quantity`                  | `Decimal`           | Number of contracts.                                                        | Required. Example: "-1", "2"                                                                                                               |
| `Trade Price`           | `trade_price`               | `Optional[Decimal]` | Transaction price.                                                          | Optional. Example: "0", "150.50"                                                                                                           |
| `Proceeds`              | `proceeds`                  | `Optional[Decimal]` | Cash proceeds.                                                              | Optional. Example: "15050.00"                                                                                                              |
| `Comm/Tax`              | `comm_tax`                  | `Optional[Decimal]` | Commission and tax.                                                         | Optional. Usually negative. Example: "-1.00"                                                                                               |
| `Basis`                 | `basis`                     | `Optional[Decimal]` | Cost basis.                                                                 | Optional. Example: "12000.00"                                                                                                              |
| `RealizedPnl`           | `realized_pnl`              | `Optional[Decimal]` | Realized P&L as reported by IBKR.                                           | Optional. Example: "3050.00"                                                                                                               |

**Notes:**
- Only rows with `TransactionType = "Cash Settlement"` are processed by the engine. Other rows (Exercise, Assignment, Expiration) duplicate information already present in the Trades CSV.
- Cash-settled options (e.g. SPX, ESTX50 index options) have no underlying stock delivery; the settlement amount is the option's intrinsic value at expiration.

---

## 7. Transfers File (Optional)
- **Input:** `data_import/Transfers-{YYYY}.csv`, concatenated across every year <= the tax year
- **Purpose:** Records moves of a holding or a cash balance between accounts. A move between the
  taxpayer's own accounts is not a disposal ([GT-ESTG20-014]), so the lots relocate carrying their
  acquisition date and cost. Nothing else in the input records that a move happened, so without
  this file the receiving account holds units the engine has to rebuild from the position snapshot
  — right quantity, invented acquisition date.
- **Optional as a whole, but not per year.** A person who has never exported the report has no
  rows; the engine says so to the reader rather than assuming nothing moved, and continues. What it
  does **not** do is continue past a window with a hole: an export covering 2023 and 2024 but not
  2025 means the query exists and a year of it is missing, and a move in that year would be
  invisible in that year and every year after it. `prepare_data_for_tax_year` counts the missing
  years into `transfers_missing_years` and the run stops naming them
  (`TRANSFERS_WINDOW_INCOMPLETE`, FAIL_FAST). Absence is a warning; a hole is a refusal. Only for a
  run that sees more than one account — a move between your own accounts needs two of them.
- **Every account you hold must be ticked in the query.** A move is applied as tax-neutral because
  it stays within the taxpayer's own depots ([GT-ESTG20-014]), and `Type=INTERNAL` does not
  establish that — it means the counterparty is an IBKR account, not that it is yours. The engine
  tests ownership against the input instead: an account you hold is one your own exports report.
  A transfer naming an account that appears nowhere else stops the run
  (`TRANSFER_COUNTERPARTY_UNKNOWN`, FAIL_FAST).
- **Associated Pydantic Model:** `RawTransferRecord`

**How the rows relate to the moves.** One move is written as several rows and summing them moves
the holding more than once:

- a **summary** row per side, carrying `TransactionID` and `PositionAmount` — `Direction` "OUT" on
  the sending account and "IN" on the receiving one. Each names both accounts, so either side
  alone describes the whole move.
- a **lot-detail** row per lot, carrying `Code` "ST" and no `TransactionID`.

`DomainEventFactory.create_events_from_transfers` keeps the summary rows, normalises each through
`Direction` into `(from, to, asset, date, quantity)` and deduplicates, so each move becomes one
event whichever sides are present.

**`Direction` carries the direction; the sign of `Quantity` does not.** The two sides of one move
carry opposite signs and which side is negative varies by instrument, so the sign identifies
neither the direction nor a short position. The engine reads `abs(Quantity)` and reads long versus
short from the sending ledger.

**Column Specifications** — `TRANSFERS_COLUMNS` in `src/parsers/column_validator.py` declares the
export's full header so that a column appearing or disappearing is caught at the boundary, and it
is checked against every real export by `tests/test_raw_model_fields.py`. The model maps the
subset below; the rest are listed in that test as deliberate drops.

| CSV Header          | Model Field Name (Pydantic) | Model Data Type     | Description                                                        | Notes                                                                             |
|---------------------|-----------------------------|---------------------|--------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| `ClientAccountID`   | `client_account_id`         | `Optional[str]`     | The account this row is written from the point of view of.         | Optional. Example: "U1234567"                                                     |
| `CurrencyPrimary`   | `currency_primary`          | `str`               | The instrument's currency, or the currency moved on a cash row.    | Required. Example: "EUR", "USD"                                                   |
| `AssetClass`        | `asset_class`               | `str`               | Asset class. A `CASH` row is a move of a balance and becomes a disposal ([GT-FX-009]); everything else is a move of a holding and relocates lots ([GT-ESTG20-014]). | Required. Example: "STK", "CASH"                                             |
| `Symbol`            | `symbol`                    | `Optional[str]`     | Instrument symbol.                                                 | Optional. Blank on a cash row.                                                    |
| `Description`       | `description`               | `Optional[str]`     | Instrument description.                                            | Optional.                                                                         |
| `Conid`             | `conid`                     | `Optional[str]`     | IBKR contract identifier.                                          | Optional. Blank on a cash row.                                                    |
| `ISIN`              | `isin`                      | `Optional[str]`     | ISIN.                                                              | Optional. Blank on a cash row.                                                    |
| `Multiplier`        | `multiplier`                | `Optional[Decimal]` | Contract multiplier.                                               | Optional. Blank on a cash row. A blank is absent, not zero.                       |
| `Date`              | `date`                      | `str`               | The date the move was booked (YYYYMMDD).                           | Required. The move is applied at this date in the chronological replay.           |
| `Type`              | `transfer_type`             | `Optional[str]`     | Kind of transfer.                                                  | Only `INTERNAL` is covered; anything else stops the run, because it may be a disposal and no rule in `reference/` decides which. |
| `Direction`         | `direction`                 | `Optional[str]`     | "OUT" or "IN". The sole carrier of which way the units went.       | A row with neither stops the run.                                                 |
| `TransferAccount`   | `transfer_account`          | `Optional[str]`     | The counterparty account of this row.                              | Required in effect: a row naming only one account stops the run.                  |
| `Quantity`          | `quantity`                  | `Decimal`           | Units moved. Read as an absolute value.                            | Required. Zero stops the run on a securities row — a move of nothing would leave the holding where it was while the broker reported it elsewhere. Zero is the ordinary value on a cash row, where the amount is in `CashTransfer`. |
| `CashTransfer`      | `cash_transfer`             | `Optional[Decimal]` | The amount moved, on a cash row. Read as an absolute value.        | Blank on a securities row. **The only column carrying a cash amount**: `Quantity`, `PositionAmount` and `TransferPrice` are all zero on a cash row, because a balance has no units. Zero or blank on a cash row stops the run. |
| `TransactionID`     | `transaction_id`            | `Optional[str]`     | Present on a summary row, blank on a lot-detail row.               | The discriminator between the two kinds, and — measured across every summary row of the export — **the same on both sides of one move**, one OUT and one IN per id. The cash path collapses the two sides on it. It does NOT reach the event either way: `get_event_sort_key` puts `ibkr_transaction_id` ahead of the intra-day band, so an id there would let a broker's string decide whether a move lands before or after that day's trades. |

**Notes:**
- **`TransferPrice` is deliberately unmapped.** It is zero on every row of the standard export, so
  it is not a cost basis, and a field for it would read as a supported input at every call site.
  The Flex Query's lot-detail option is what would make it one.
- **The securities path still collapses on the move's shape, not on the id.** The sentence above
  said the two sides carried different ids until it was measured; they do not. Changing that path
  moves lots and belongs with a change that means to, and it has the whole-position refusal standing
  behind the collision the shape key cannot see. The cash path has no such backstop, so it keys on
  the id.
- **A cash move in EUR produces no event.** § 20 Abs. 2 Satz 1 Nr. 7 reaches a
  Fremdwährungsguthaben and the declaration is written in euros, so there is no currency gain to
  declare. Read and deliberately without effect, which is not the same as dropped unseen.
- **Only a move of a whole position is applied.** A partial move is refused through the data-gap
  channel (`INTERNAL_TRANSFER_PARTIAL`, FAIL_FAST) naming the instrument, the account, the date,
  the quantity moved and the quantity held — because nothing here says which lots moved, and the
  oldest and the newest give different gains and different holding periods.

---

## 8. Grants File (Optional)
- **Input:** `data_import/Grants-{YYYY}.csv`, concatenated across every year <= the tax year
- **Purpose:** Records shares a broker awarded for capital placed with it. The award is the only
  record that those shares arrived and what they were worth; no other export carries it. Without
  this file the historical replay reconstructs a holding smaller than the broker reports. **What
  happens then depends on the interval**, and only one of the two cases is a stop:
  - the interval **began at a reported snapshot** — `REPLAY_MARK_MISMATCH`, FAIL_FAST, and the run
    produces no figures at all;
  - the interval is the **earliest one**, with nothing confirming its start —
    `REPLAY_MARK_UNCONFIRMED_START`, severity WARNING. The broker's quantity is taken, a lot is
    synthesised dated `{tax_year-1}-12-31`, and **the run completes**. A user whose award falls in
    the first year of their input window gets a figure, not a refusal, and the acquisition date
    behind it is invented. This is the fallback rule's case, and the report is what avoids it.
- **Legal ground:** shares granted for placing capital are a *Leistung* under § 22 Nr. 3 EStG, not
  Kapitalertrag ([GT-ESTG20-063]). Zufluss falls where wirtschaftliche Verfügungsmacht arrives,
  which while the grantor may still take the shares back is not the booking ([GT-ESTG20-064]), and
  the amount brought to tax then is the Anschaffungskosten on a later disposal ([GT-ESTG20-065]).
- **What this engine does and does not do with it.** It supplies the **acquisition** — the lot, its
  date and its cost basis — so a later disposal is measured correctly on Anlage KAP. It does **not**
  declare the **receipt** as income in the year it accrued: that belongs on Anlage SO under
  *Einkünfte aus Leistungen*, the reporting layer has no such category, and this library holds no
  Zeilen for that half of the form. Tracked as issue #76, which closes it for this and for the
  securities-lending fee together.
- **Optional as a whole, but not per year.** A person whose broker has never awarded them shares
  has no rows. A window with a hole is different: a year of awards that does not arrive is a year
  whose holding cannot be reconstructed. `prepare_data_for_tax_year` counts the missing years the
  same way it does for Transfers.
- **Associated Pydantic Model:** `RawGrantRecord`

**Three activity kinds share the file and only two move the position.**

| `ActivityDescription` contains | Meaning | Moves the position? |
|---|---|---|
| `Stock Award Grant` | Shares booked into the account | Yes, positive |
| `Stock Award Return` | Taken back when the condition fails | Yes, negative |
| `Stock Award Vesting` | The condition lapsed; value restated | **No** |

Adding the vesting quantities to the position roughly doubles the holding against the broker's
snapshot. `parse_grants_csv` therefore **raises** on an `ActivityDescription` it does not
recognise rather than skipping it: an award and a vesting differ in nothing a parser can see
except this text, so an unclassified kind is as likely to move the position as not, and a run that
dropped one would reconcile until the year the dropped kind mattered.

**Each kind takes its date from a different column.**

- An **award** is dated on `AwardDate` — the day the shares entered the account, which is what the
  position snapshot counts and what the ledger reconciles against.
- A **reversal** is dated on `ReportDate`. Its `AwardDate` names the *original* award and is the
  matching key, not its own date.
- A **vesting** is dated on `VestingDate`, **not** `ReportDate`. The broker books the row a day or
  more later, and booking is not the legal event. Taking `ReportDate` here would silently move the
  acquisition date and the year it falls in.

**The award creates the lot; the vesting restates it.** The position and the tax acquisition part
company between the two dates, so neither alone works: creating lots at vesting reconstructs short
of every snapshot in between, and creating them at the award price carries a cost basis the store
rejects. A reversal reduces the matching lot **at that lot's own unit cost** and realises nothing —
it is not a disposal and produces no `RealizedGainLoss`.

**Column Specifications** — `GRANTS_COLUMNS` in `src/parsers/column_validator.py` declares the
export's full header so that a column appearing or disappearing is caught at the boundary.

| CSV Column            | Model Field            | Type                | Description                                    | Notes |
|-----------------------|------------------------|---------------------|------------------------------------------------|-------|
| `ClientAccountID`     | `client_account_id`    | `Optional[str]`     | The account the shares were awarded into.      | Decides which account's ledger holds the lot. A single-account export would not notice it being dropped, which is what makes getting it wrong latent. |
| `CurrencyPrimary`     | `currency_primary`     | `str`               | Currency of `Price` and `Value`.               | Required. The award price is converted at the ECB rate for the event's own date, never at a broker rate. |
| `AssetClass`          | `asset_class`          | `str`               | `STK` on every observed row.                   | Required. |
| `SubCategory`         | `sub_category`         | `Optional[str]`     | e.g. `COMMON`.                                 | |
| `Symbol`              | `symbol`               | `Optional[str]`     | Instrument symbol.                             | |
| `Description`         | `description`          | `Optional[str]`     | Instrument name.                               | |
| `Conid`               | `conid`                | `Optional[str]`     | IBKR contract identifier.                      | |
| `ISIN`                | `isin`                 | `Optional[str]`     | Instrument ISIN.                               | |
| `Multiplier`          | `multiplier`           | `Optional[Decimal]` | 1 for shares.                                  | |
| `ReportDate`          | `report_date`          | `str`               | The day the broker booked the row.             | Required. The event date for a **reversal** only; for a vesting it is the booking day and is deliberately not used. |
| `ActivityDescription` | `activity_description` | `str`               | Which of the three kinds this row is.          | Required, and the **only** thing distinguishing them. An unrecognised value stops the run. |
| `AwardDate`           | `award_date`           | `str`               | The originating award's date.                  | Required. **The matching key** on all three kinds, since `SerialNumber` is blank. The event date for an **award**. |
| `VestingDate`         | `vesting_date`         | `str`               | The day the condition lapses.                  | Required. The event date for a **vesting** — where Zufluss falls. |
| `Quantity`            | `quantity`             | `Decimal`           | Shares. Negative on a reversal.                | Required. Read as an absolute value, with the direction carried by the kind. Zero stops the run. |
| `Price`               | `price`                | `Decimal`           | Per-share value the broker assigned.           | Required. On a vesting this is the übliche Endpreis at Zufluss (§ 8 Abs. 2 Satz 1) and becomes the Anschaffungskosten. |
| `Value`               | `value`                | `Decimal`           | `Quantity` x `Price`, to the cent.             | Required. Mapped although derivable: the two disagree by rounding, and the cross-check is what shows which of them the broker's own cost basis was built from. |
| `SerialNumber`        | *(not mapped)*         | —                   | Row identifier.                                | **Blank on every row measured.** Declared in the tuple so that its ever being populated is caught at the boundary, and deliberately absent from the model so nothing reads an identity that is not there. |

**Notes:**
- **The price's own date is not stated.** § 8 Abs. 2 Satz 1 wants the übliche Endpreis on the day of
  Zufluss, and no column says which day `Price` was struck on. Where `ReportDate` and `VestingDate`
  differ it may be either day's. It is used as given — it is a measurement, and the alternative is
  to invent one from market data this engine does not hold — and the residual uncertainty is
  recorded against [GT-ESTG20-064] rather than left for a reader to notice.
- **Two awards sharing an award date stop the run.** That date is the only key a vesting or a
  reversal has, so a duplicate would let one restate or reverse the wrong award's shares.
- **A lot is never created without a EUR cost basis.** The award price is a foreign amount the
  enrichment step converts; an unconvertible award stops the run rather than acquiring shares at an
  invented price.

## General Information
- **CSV Encoding:** All input CSV files are expected to be `utf-8-sig` encoded.
- **Decimal Parsing:** Numerical monetary values and quantities are parsed into Python's `Decimal` type, preserving precision from the string representation. Empty strings or unparsable numeric values typically default to `None` or `Decimal("0.0")` based on field definition and parsing logic (`safe_decimal` utility).
- **Date Parsing:** Date strings are parsed from various common formats (e.g., YYYY-MM-DD, YYYYMMDD) into Python `datetime.date` or `datetime.datetime` objects.
- **Column Validation:** Each parser validates that the CSV header row contains exactly the columns defined in `src/parsers/column_validator.py`. Missing or unexpected columns cause a `ValueError` before any rows are parsed. This ensures the IBKR Flex Query export configuration matches what the engine expects.

---

## 1. Trades File
- **Default Name (from `config.py`):** `trades.csv`
- **Sample File Provided:** `input_file_2.csv`
- **Associated Pydantic Model:** `RawTradeRecord`

**Column Specifications (based on `input_file_2.csv` headers):**

| CSV Header             | Model Field Name (Pydantic) | Model Data Type             | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                                                               |
|------------------------|-----------------------------|-----------------------------|-----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`      | `client_account_id`         | `Optional[str]`             | The client's account identifier.                                            | Optional. Example: "U1234567"                                                                                                                                              |
| `CurrencyPrimary`      | `currency_primary`          | `str`                       | The primary currency of the transaction or asset.                           | Required. Example: "EUR", "USD"                                                                                                                                            |
| `AssetClass`           | `asset_class`               | `str`                       | The asset class of the instrument (e.g., STK, OPT, CASH, BOND, CFD).        | Required. Example: "BOND", "CASH", "CFD", "OPT", "STK"                                                                                                                      |
| `SubCategory`          | `sub_category`              | `Optional[str]`             | Sub-category of the asset (e.g., COMMON, ETF, ADR for STK).                 | Optional. Example: "Corp", "COMMON", "ADR", "ETF"                                                                                                                          |
| `Symbol`               | `symbol`                    | `str`                       | The trading symbol of the instrument.                                       | Required. Example: "VW 0 3/4 06/15/23", "EUR.USD", "IWO", "TIO   230616C00001000"                                                                                          |
| `Description`          | `description`               | `str`                       | A textual description of the instrument or transaction.                     | Required. Example: "VW 0 3/4 06/15/23", "EUR.USD", "USD IWO"                                                                                                               |
| `ISIN`                 | `isin`                      | `Optional[str]`             | International Securities Identification Number.                             | Optional. Example: "XS1734548487", "US23292E1082"                                                                                                                          |
| `Strike`               | `strike`                    | `Optional[Decimal]`         | The strike price of an option.                                              | Optional, relevant for OPT. Example: "1.0", "225.0"                                                                                                                        |
| `Expiry`               | `expiry`                    | `Optional[str]`             | The expiry date of an option or future (YYYY-MM-DD).                        | Optional, relevant for OPT/FUT. Parsed as string. Example: "2023-06-16"                                                                                                     |
| `Put/Call`             | `put_call`                  | `Optional[str]`             | Indicates if an option is a Put ('P') or Call ('C').                        | Optional, relevant for OPT. Example: "C", "P"                                                                                                                              |
| `TradeDate`            | `trade_date`                | `str`                       | The date of the trade (YYYY-MM-DD).                                         | Required. Parsed as string. Example: "2023-03-13"                                                                                                                          |
| `Quantity`             | `quantity`                  | `Decimal`                   | The number of units traded. Positive for buy, negative for sell.            | Required. Example: "20000.0", "-22.0"                                                                                                                                      |
| `TradePrice`           | `trade_price`               | `Decimal`                   | The price per unit for the trade.                                           | Required. Example: "99.42", "1.05675", "0.03"                                                                                                                              |
| `IBCommission`         | `ib_commission`             | `Optional[Decimal]`         | Commission charged by Interactive Brokers for the trade.                    | Optional. Usually negative. Example: "-12.5", "-1.89394"                                                                                                                   |
| `IBCommissionCurrency` | `ib_commission_currency`    | `Optional[str]`             | The currency of the IB commission.                                          | Optional. Example: "EUR", "USD"                                                                                                                                            |
| `Buy/Sell`             | `buy_sell`                  | `Optional[str]`             | Indicates if the trade was a buy or sell.                                   | Optional. "BUY" or "SELL". Crucial for determining `FinancialEventType`. Code has fallbacks if missing.                                                                    |
| `TransactionID`        | `transaction_id`            | `Optional[str]`             | IBKR's unique identifier for the transaction.                               | Optional, but highly recommended. Example: "1728910410"                                                                                                                    |
| `Notes/Codes`          | `notes_codes`               | `Optional[str]`             | Codes related to the trade (e.g., P, A, Ex, Ep).                            | Optional. Used to identify exercises, assignments, expirations. Example: "P", "A", "Ep", "Ex"                                                                               |
| `UnderlyingSymbol`     | `underlying_symbol`         | `Optional[str]`             | The symbol of the underlying asset for derivatives.                         | Optional, relevant for OPT/FUT/CFD. Example: "TIO", "IWO"                                                                                                                  |
| `Conid`                | `conid`                     | `Optional[str]`             | IBKR's contract identifier for the instrument.                              | Optional. Example: "298918183", "12087792"                                                                                                                                 |
| `UnderlyingConid`      | `underlying_conid`          | `Optional[str]`             | IBKR's contract identifier for the underlying asset.                        | Optional, relevant for OPT/FUT/CFD. Example: "325898828.0" (parsed as string)                                                                                              |
| `Multiplier`           | `multiplier`                | `Optional[Decimal]`         | The contract multiplier (e.g., for options, futures).                     | Optional. Example: "1", "100"                                                                                                                                              |
| `Open/CloseIndicator`  | `open_close_indicator`      | `Optional[str]`             | Indicates if trade opens or closes a position ('O' or 'C').                 | Crucial for determining `FinancialEventType` for standard financial instrument trades in conjunction with `Buy/Sell` (refer to PRD Section 5, Step 7). Expected values: 'O' (Open), 'C' (Close). Missing or invalid values for relevant trades constitute a data inconsistency. Not applicable to currency pair trades (e.g., FX 'CASH' asset class trades like EUR.USD). The provided sample `input_file_2.csv` does not include this column; real input data for accurate trade classification requires it. Model field `open_close_indicator` maps to this. |

---

## 2. Cash Transactions File
- **Default Name (from `config.py`):** `cash_transactions.csv`
- **Sample File Provided:** `input_file_1.csv` (structure inferred from image and code)
- **Associated Pydantic Model:** `RawCashTransactionRecord`

**Column Specifications (based on `input_file_1.csv` headers):**

| CSV Header         | Model Field Name (Pydantic) | Model Data Type   | Description                                                                          | Notes (Optionality, Example, Parsing Detail)                                                                                                |
|--------------------|-----------------------------|-------------------|--------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`  | `client_account_id`         | `Optional[str]`   | The client's account identifier.                                                     | Optional. Example: "U1234567"                                                                                                               |
| `CurrencyPrimary`  | `currency_primary`          | `str`             | The currency of the cash transaction.                                                | Required. Example: "CAD", "JPY", "EUR"                                                                                                      |
| `AssetClass`       | `asset_class`               | `Optional[str]`   | Asset class related to the cash transaction (e.g., STK, BOND). Can be empty/null.    | Optional. Example: "STK", "BOND", or empty.                                                                                                 |
| `SubCategory`      | `sub_category`              | `Optional[str]`   | Sub-category of the asset (e.g., COMMON). Can be empty/null.                         | Optional. Example: "COMMON", or empty.                                                                                                      |
| `Symbol`           | `symbol`                    | `Optional[str]`   | Symbol of the instrument related to the cash flow. Can be empty/null.                | Optional. Example: "BNS", "9022.T", or empty.                                                                                               |
| `Description`      | `description`               | `str`             | Detailed description of the cash transaction. Crucial for type determination.        | Required. Example: "BNS (CA0641491075) CASH DIVIDEND CAD 1.03 - CA TAX"                                                                   |
| `SettleDate`       | `settle_date`               | `str`             | The settlement date of the cash transaction (YYYY-MM-DD).                            | Required. Parsed as string. Example: "2023-01-27"                                                                                           |
| `Amount`           | `amount`                    | `Decimal`         | The monetary amount of the cash transaction. Positive for inflow, negative for outflow. | Required. Example: "-30.9", "0.12", "7000.0"                                                                                                |
| `Type`             | `type`                      | `str`             | The type of cash transaction (e.g., Dividends, Withholding Tax).                     | Required. Example: "Withholding Tax", "Dividends", "Broker Interest Received"                                                               |
| `Conid`            | `conid`                     | `Optional[str]`   | IBKR's contract identifier for the related instrument. Can be empty/null.            | Optional. Example: "4457153.0" (parsed as string), or empty.                                                                                |
| `UnderlyingConid`  | `underlying_conid`          | `Optional[str]`   | IBKR Conid of the underlying for derivative-related cash flows. Can be empty/null.   | Optional. Empty in sample.                                                                                                                  |
| `ISIN`             | `isin`                      | `Optional[str]`   | ISIN of the related instrument. Can be empty/null.                                   | Optional. Example: "CA0641491075", or empty.                                                                                               |
| `IssuerCountryCode`| `issuer_country_code`       | `Optional[str]`   | ISO country code of the issuer or tax authority.                                     | Optional. Example: "CA", "JP", or empty. Used for WHT source country.                                                                       |
| `TransactionID`    | `transaction_id`            | `Optional[str]`   | IBKR's unique identifier for the transaction.                                        | Optional, but highly recommended. Example: "2865449245"                                                                                     |

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
- **Default Names (from `config.py`):** `positions_start_of_year.csv`, `positions_end_of_year.csv`
- **Sample Files Provided:** `input_file_3.csv` (Start), `input_file_4.csv` (End)
- **Associated Pydantic Model:** `RawPositionRecord`

**Column Specifications (based on `input_file_3.csv` / `input_file_4.csv` headers):**

| CSV Header         | Model Field Name (Pydantic) | Model Data Type   | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                                                                           |
|--------------------|-----------------------------|-------------------|-----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`  | (Effectively ignored)       | `N/A`             | The client's account identifier.                                            | Present in CSV. `RawPositionRecord.account_id` (alias `AccountId`) does not map to this header. `ClientAccountID` data from CSV is ignored by the Pydantic model as currently defined. Example: "U1234567" |
| `CurrencyPrimary`  | `currency_primary`          | `str`             | The currency of the position.                                               | Required. Example: "CAD", "EUR", "SGD"                                                                                                                                                 |
| `AssetClass`       | `asset_class`               | `str`             | The asset class of the instrument (e.g., STK, OPT).                         | Required. Example: "STK", "OPT"                                                                                                                                                        |
| `SubCategory`      | (Ignored by model)          | `N/A`             | Sub-category of the asset (e.g., COMMON, ETF).                              | Present in CSV. Ignored by `RawPositionRecord` due to `Config.extra = 'ignore'`. Example: "COMMON", "ETF"                                                                                |
| `Symbol`           | `symbol`                    | `str`             | The trading symbol of the instrument.                                       | Required. Example: "BNS", "4GLDd", "P LEG  20230120 63 M"                                                                                                                              |
| `Description`      | `description`               | `str`             | A textual description of the instrument.                                    | Required. Example: "BANK OF NOVA SCOTIA", "XETRA-GOLD"                                                                                                                                 |
| `ISIN`             | `isin`                      | `Optional[str]`   | International Securities Identification Number.                             | Optional. Example: "CA0641491075", "DE000A0S9GB0"                                                                                                                                      |
| `Quantity`         | `position`                  | `Decimal`         | The number of units held. Positive for long, negative for short.            | Required. (Aliased from `Quantity` in CSV to `position` in model). Example: "200", "-100"                                                                                                 |
| `PositionValue`    | `position_value`            | `Optional[Decimal]`| The market value of the position in `CurrencyPrimary`.                      | Optional. Example: "13268", "22032"                                                                                                                                                    |
| `MarkPrice`        | `mark_price`                | `Optional[Decimal]`| The mark-to-market price per unit.                                          | Optional. Example: "66.34", "55.08", "2.31"                                                                                                                                            |
| `CostBasisMoney`   | `cost_basis_money`          | `Optional[Decimal]`| The total cost basis of the position in `CurrencyPrimary`.                  | Optional. Example: "13527", "22279.134", "-787.8" (negative for short proceeds)                                                                                                      |
| `UnderlyingSymbol` | `underlying_symbol`         | `Optional[str]`   | The symbol of the underlying asset for derivatives.                         | Optional, relevant for OPT. Example: "LEG"                                                                                                                                             |
| `Conid`            | `conid`                     | `Optional[str]`   | IBKR's contract identifier for the instrument.                              | Optional. Example: "4457153", "50784405", "604172754"                                                                                                                                  |
| `UnderlyingConid`  | `underlying_conid`          | `Optional[str]`   | IBKR's contract identifier for the underlying asset.                        | Optional, relevant for OPT. Example: "121764205"                                                                                                                                       |
| `Multiplier`       | `multiplier`                | `Optional[Decimal]`| The contract multiplier (e.g., for options).                              | Optional. Example: "1", "100"                                                                                                                                                          |

---

## 4. Corporate Actions File
- **Default Name (from `config.py`):** `corporate_actions.csv`
- **Sample File Provided:** `input_file_0.csv`
- **Associated Pydantic Model:** `RawCorporateActionRecord`

**Column Specifications (based on `input_file_0.csv` headers):**

| CSV Header         | Model Field Name (Pydantic) | Model Data Type   | Description                                                                   | Notes (Optionality, Example, Parsing Detail)                                                                                                |
|--------------------|-----------------------------|-------------------|-------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`  | `client_account_id`         | `Optional[str]`   | The client's account identifier.                                              | Optional. Example: "U1234567"                                                                                                               |
| `Symbol`           | `symbol`                    | `str`             | The trading symbol of the instrument affected by the corporate action.        | Required. Example: "9022.T", "ATVI", "D05"                                                                                                  |
| `Description`      | `description`               | `str`             | Detailed description of the corporate action and the instrument.              | Required. Example: "9022.T(JP3566800003) SPLIT 5 FOR 1..."                                                                                 |
| `ISIN`             | `isin`                      | `Optional[str]`   | ISIN of the affected instrument.                                              | Optional. Example: "JP3566800003", "US00507V1098"                                                                                           |
| `Report Date`      | `report_date`               | `str`             | The date the corporate action was reported (YYYY-MM-DD).                      | Required. Parsed as string. Example: "2023-09-28"                                                                                           |
| `Code`             | `code`                      | `Optional[str]`   | IBKR code related to the corporate action (e.g., for specific CA subtypes).   | Optional. Empty in sample.                                                                                                                  |
| `Type`             | `type_ca`                   | `str`             | IBKR's type code for the corporate action (e.g., FS, TC, HI, BM).             | Required (model field `type_ca`). Example: "FS", "TC", "HI", "BM" (Bond Maturity). For BM, `Proceeds` holds the total redemption cash and `Quantity` is negative (bonds removed). |
| `ActionID`         | `action_id_ibkr`            | `Optional[str]`   | IBKR's unique identifier for the corporate action event.                      | Optional. Example: "126233647"                                                                                                              |
| `Conid`            | `conid`                     | `Optional[str]`   | IBKR's contract identifier for the affected instrument.                       | Optional. Example: "14018918", "52424577"                                                                                                   |
| `UnderlyingConid`  | `underlying_conid`          | `Optional[str]`   | IBKR Conid of the underlying if the CA affects a derivative.                  | Optional. Empty in sample.                                                                                                                  |
| `UnderlyingSymbol` | `underlying_symbol`         | `Optional[str]`   | Symbol of the underlying if the CA affects a derivative.                      | Optional. Empty in sample.                                                                                                                  |
| `CurrencyPrimary`  | `currency_primary`          | `Optional[str]`   | The currency of monetary amounts involved in the CA.                          | Optional (model allows None). Example: "JPY", "USD", "EUR"                                                                                  |
| `Amount`           | (Ignored by model)          | `N/A`             | A monetary amount related to the CA.                                          | Present in CSV (value "0"). Ignored by `RawCorporateActionRecord`; `Value` or `Proceeds` are used for monetary impact.                  |
| `Proceeds`         | `proceeds`                  | `Optional[Decimal]`| Monetary proceeds from the CA (e.g., cash from merger).                       | Optional. Example: "0", "19000"                                                                                                             |
| `Value`            | `value`                     | `Optional[Decimal]`| Monetary value related to the CA (e.g., FMV of stock dividend).               | Optional. Example: "0", "-18884", "149.85" (negative value seems to indicate cost/value given up in sample)                                   |
| `Quantity`         | `quantity`                  | `Optional[Decimal]`| Quantity of shares/units involved (e.g., new shares from split/dividend).   | Optional. Example: "400", "-200" (negative for shares disposed in merger), "5"                                                              |

---

## 5. Cash Balance File (Currency Balances)
- **Default Name (from `config.py`):** `cash_balance.csv`
- **Sample File Provided:** `Gemini_Cash_Balance.csv`
- **Purpose:** Records currency holdings at start and end of year for tracking FX positions and potential currency gains/losses under §23 EStG.
- **Associated Pydantic Model:** `RawCashBalanceRecord` (to be implemented)

**Column Specifications (based on IBKR Cash Report Flex Query):**

| CSV Header              | Model Field Name (Pydantic) | Model Data Type     | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                               |
|-------------------------|-----------------------------|---------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`       | `client_account_id`         | `Optional[str]`     | The client's account identifier.                                            | Optional. Example: "U1234567"                                                                                                              |
| `CurrencyPrimary`       | `currency_primary`          | `str`               | The currency code (ISO 4217).                                               | Required. Example: "EUR", "USD", "CHF", "JPY"                                                                                              |
| `FromDate`              | `from_date`                 | `str`               | Start date of the report period (YYYYMMDD).                                 | Required. Example: "20230102"                                                                                                              |
| `ToDate`                | `to_date`                   | `str`               | End date of the report period (YYYYMMDD).                                   | Required. Example: "20231229"                                                                                                              |
| `StartingCash`          | `starting_cash`             | `Decimal`           | Trade date cash balance at start of period.                                 | Required. Can be negative (margin/borrowed). Example: "29230.65000374", "-331.370344641"                                                   |
| `EndingCash`            | `ending_cash`               | `Decimal`           | Trade date cash balance at end of period.                                   | Required. Can be negative (margin/borrowed). Example: "-0.000014368", "1750.969333782"                                                     |

**Notes on Currency Taxation (§23 EStG):**
- Currency holdings held for less than 1 year are subject to private sale taxation under German tax law.
- Gains/losses are calculated using FIFO method against acquisition costs.
- The base currency (typically EUR) is not taxable; only foreign currency holdings are relevant.
- FX trade data from the Trades file is required to build the FIFO lot history for accurate gain/loss calculation.

**Reference:** [IBKR Cash Report Flex Statement](https://www.ibkrguides.com/reportingreference/reportguide/cash%20reportfq.htm)

---

## 6. Options Exercises, Assignments & Expirations File (Optional)
- **Default Name:** `options_eae.csv`
- **Purpose:** Records option exercises, assignments, expirations, and cash settlements. Required for cash-settled index options (e.g. SPX, ESTX50) where no underlying stock trade exists. If you don't trade index options, this file is not needed.
- **Associated Pydantic Model:** `RawOptionsEAERecord`

**Column Specifications (based on IBKR Option Exercises, Assignments and Expirations Flex Query):**

| CSV Header              | Model Field Name (Pydantic) | Model Data Type     | Description                                                                 | Notes (Optionality, Example, Parsing Detail)                                                                                               |
|-------------------------|-----------------------------|---------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| `ClientAccountID`       | `client_account_id`         | `Optional[str]`     | The client's account identifier.                                            | Optional. Example: "U1234567"                                                                                                              |
| `CurrencyPrimary`       | `currency_primary`          | `str`               | Transaction currency.                                                       | Required. Example: "USD", "EUR"                                                                                                            |
| `FXRateToBase`          | `fx_rate_to_base`           | `Optional[Decimal]` | FX rate to base currency at time of transaction.                            | Optional. Example: "0.92"                                                                                                                  |
| `AssetClass`            | `asset_class`               | `str`               | Asset class (always OPT for this file).                                     | Required. Example: "OPT"                                                                                                                   |
| `Symbol`                | `symbol`                    | `str`               | Option contract symbol.                                                     | Required. Example: "SPX   241220C05900000"                                                                                                 |
| `Description`           | `description`               | `str`               | Contract description.                                                       | Required. Example: "SPX 20DEC24 5900.0 C"                                                                                                  |
| `Conid`                 | `conid`                     | `Optional[str]`     | Contract identifier.                                                        | Optional. Example: "604172754"                                                                                                             |
| `ISIN`                  | `isin`                      | `Optional[str]`     | ISIN of the option contract.                                                | Optional. Often empty for index options.                                                                                                   |
| `UnderlyingConid`       | `underlying_conid`          | `Optional[str]`     | Underlying contract ID.                                                     | Optional. Example: "416904"                                                                                                                |
| `UnderlyingSymbol`      | `underlying_symbol`         | `Optional[str]`     | Underlying symbol.                                                          | Optional. Example: "SPX", "ESTX50"                                                                                                         |
| `Multiplier`            | `multiplier`                | `Optional[Decimal]` | Contract multiplier.                                                        | Optional. Example: "100"                                                                                                                   |
| `Strike`                | `strike`                    | `Optional[Decimal]` | Strike price.                                                               | Optional. Example: "5900.0"                                                                                                                |
| `Expiry`                | `expiry`                    | `Optional[str]`     | Expiration date.                                                            | Optional. Example: "2024-12-20"                                                                                                            |
| `Put/Call`              | `put_call`                  | `Optional[str]`     | C or P.                                                                     | Optional. Example: "C", "P"                                                                                                                |
| `Date`                  | `date`                      | `str`               | Transaction date.                                                           | Required. Example: "2024-12-20"                                                                                                            |
| `TransactionType`       | `transaction_type`          | `str`               | Type of option lifecycle event.                                             | Required. Values: "Assignment", "Exercise", "Expiration", "Cash Settlement". Only "Cash Settlement" rows are used; others duplicate Trades. |
| `Quantity`              | `quantity`                  | `Decimal`           | Number of contracts.                                                        | Required. Example: "-1", "2"                                                                                                               |
| `TradePrice`            | `trade_price`               | `Optional[Decimal]` | Transaction price.                                                          | Optional. Example: "0", "150.50"                                                                                                           |
| `Proceeds`              | `proceeds`                  | `Optional[Decimal]` | Cash proceeds.                                                              | Optional. Example: "15050.00"                                                                                                              |
| `Comm/Tax`              | `comm_tax`                  | `Optional[Decimal]` | Commission and tax.                                                         | Optional. Usually negative. Example: "-1.50"                                                                                               |
| `Basis`                 | `basis`                     | `Optional[Decimal]` | Cost basis.                                                                 | Optional. Example: "12000.00"                                                                                                              |
| `RealizedPnl`           | `realized_pnl`              | `Optional[Decimal]` | Realized P&L as reported by IBKR.                                           | Optional. Example: "3050.00"                                                                                                               |

**Notes:**
- Only rows with `TransactionType = "Cash Settlement"` are processed by the engine. Other rows (Exercise, Assignment, Expiration) duplicate information already present in the Trades CSV.
- Cash-settled options (e.g. SPX, ESTX50 index options) have no underlying stock delivery; the settlement amount is the option's intrinsic value at expiration.

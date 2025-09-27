# Product Requirements Document (PRD): IBKR German Tax Declaration Engine (v3.3.1)

**Revision Note (September 2025):**
- v3.3.1: Enhanced error handling and event processing reliability. Improved FIFO processing validation with comprehensive error logging. Fixed option assignment classification for closing transactions. Enhanced chronological event ordering using transaction IDs for accurate FIFO calculations.
- v3.3.0: Added comprehensive capital repayments (Einlagenrückgewähr) and dividend rights processing. Updated system to support configurable tax years. Enhanced PDF reporting with detailed component breakdowns.
- v3.2.3: Explicitly clarified that all financial events processed for income aggregation and reporting (including simple income like dividends and interest) must have an `event_date` within the specified tax year. This applies to both internal calculations and the detailed PDF report.
- v3.2.2: Complete revision of variable naming conventions for clarity and semantic accuracy. Corrected the description of Anlage KAP Zeile 19 to accurately reflect that it represents foreign capital income after netting (excluding fund-related items and derivative losses).
- v3.2.1: The definition of figures for *Anlage KAP Zeile 19* has been aligned with the official form instructions.

## 1. Introduction

### Problem
German tax residents using Interactive Brokers (IBKR) face considerable difficulties in accurately completing their German tax declaration forms, specifically Anlage KAP, Anlage KAP-INV, and Anlage SO. The primary challenges include:

- Mapping diverse IBKR transaction data (trades, dividends, interest, option activities, corporate actions) to the specific line items required by these forms.
- Correctly calculating capital gains/losses using the FIFO method in EUR (using precise `Decimal` arithmetic) for various asset types, including adjustments due to corporate actions.
- Identifying and separately declaring income and gains/losses from investment funds (ETFs, Fonds) on Anlage KAP-INV, distinguishing between different fund types (e.g., `AKTIENFONDS`, `MISCHFONDS` as per `InvestmentFundType`).
- Accurately calculating and applying German Teilfreistellung (partial tax exemption) for investment fund income and gains and reporting the correct net figures for internal summaries and the correct gross figures for KAP-INV declaration.
- Calculating the Vorabpauschale for investment funds and allocating it to the correct declaration category.
- Properly handling income like dividends (distinguishing between stock dividends, cash dividends from corporate actions, and fund distributions), interest, and Stückzinsen for correct form placement.
- Accurately preparing figures for German loss offsetting rules by declaring specific gross gains and gross losses (for stocks and derivatives) and specific categories of other losses, and calculating foreign capital income after netting for Anlage KAP Zeile 19, allowing the Finanzamt to apply the offsetting rules.
- Reliably managing currency conversions (to EUR using `Decimal` arithmetic and daily ECB rates), corporate actions (like stock splits, mergers, acquisitions, stock dividends), and option exercises/assignments to ensure accurate input for tax calculations.
- Ensuring data consistency across various input files and providing clear documentation to support declared figures.

### Solution
This tool will automate the generation of figures required for German tax declaration forms (Anlage KAP, Anlage KAP-INV, and Anlage SO for the current tax year). The system supports configurable tax years via the TAX_YEAR setting in config.py. It will achieve this by:

- Parsing IBKR financial data (including corporate actions)
- Consolidating asset identification using a robust alias-based system
- Enriching data (e.g., EUR conversion using `Decimal`)
- Classifying assets into categories like `STOCK`, `INVESTMENT_FUND`, `PRIVATE_SALE_ASSET` (§23 EStG) for correct tax treatment and form placement
- Performing FIFO calculations (using `Decimal` quantities and monetary values) with corporate action adjustments
- Specifying the `RealizationType` for each gain/loss
- Applying Teilfreistellung
- Calculating Vorabpauschale (which will be €0 for 2023)
- Preparing figures for declaration according to German tax form requirements (reporting specific gross gains, gross losses, and foreign capital income after netting for Anlage KAP, and gross figures for KAP-INV)

The system will output clearly structured summaries directly corresponding to the line items on the German tax forms, along with detailed PDF reports for record-keeping and submission to tax authorities if required. This version specifically excludes handling for "Alt-Anteile" (investment fund shares acquired before 01.01.2018).

### Goal
To provide an automated, rule-based system that generates accurate and directly usable figures for German tax residents to complete their Anlage KAP, Anlage KAP-INV, and Anlage SO forms for the current tax year, focusing on shares acquired from 01.01.2018 onwards for investment funds. The tool aims to significantly reduce the manual effort and complexity involved in preparing these tax declarations based on IBKR data, ensuring compliance with German tax regulations concerning capital gains, investment fund income, other capital income, and the tax implications of corporate actions, by providing correctly aggregated figures as required by the respective form lines. All financial calculations will use `Decimal` for precision, adhering to specified internal working precisions.

### Target Audience
German tax residents using Interactive Brokers who need automated assistance in preparing figures for their annual tax declaration (Anlage KAP, Anlage KAP-INV, and Anlage SO for the current tax year) and **do not hold investment fund shares acquired before January 1, 2018 ("Alt-Anteile")**. Suitable for self-preparation or for providing structured data and supporting documentation to a tax advisor.

## 2. Key Requirements & Functionality

### 2.0. Numerical Precision and Intermediate Calculations

#### 2.0.1. Commitment to High Precision
All financial calculations within the system, especially intermediate steps that are not yet intended for final reporting, must be performed using a high degree of numerical precision to prevent the accumulation of rounding errors. The goal is to ensure that final reported figures, after any required quantization, are as accurate as possible.

#### 2.0.2. Internal Working Precision
- The system shall utilize Python's `Decimal` type for all monetary values and other quantities requiring precise arithmetic (e.g., share counts, ratios).
- A configurable **internal calculation precision** (e.g., `INTERNAL_CALCULATION_PRECISION` in `config.py`) shall be defined and used for the `Decimal` context during all intermediate calculations. This precision **must be significantly higher** than the precision required for any final output value (e.g., 2 decimal places for EUR amounts on tax forms, or 6 decimal places for per-share values). A recommended minimum for `INTERNAL_CALCULATION_PRECISION` is at least 28 decimal places.
- This internal calculation precision should be applied globally or via explicit `Decimal.Context` management for critical calculation blocks.

#### 2.0.3. Rounding Mode
A consistent rounding mode (e.g., `ROUND_HALF_UP` or `ROUND_HALF_EVEN`, configurable as `DECIMAL_ROUNDING_MODE` in `config.py`) shall be applied when intermediate calculations inherently require rounding to the internal calculation precision, and more importantly, when quantizing values to their final reporting precision. The default rounding mode for intermediate calculations should be chosen to minimize bias where possible.

#### 2.0.4. Initialization from Strings
When parsing monetary values or precise quantities from input files or external sources, `Decimal` objects must be initialized directly from their string representations (or integer representations) rather than from floating-point numbers (`float`) to preserve the original precision.

#### 2.0.5. Distinction from Output Precision
The internal calculation precision is distinct from and higher than output precisions like `OUTPUT_PRECISION_AMOUNTS` (e.g., `Decimal("0.01")`) or `OUTPUT_PRECISION_PER_SHARE` (e.g., `Decimal("0.000001")`). These output precisions are used for final quantization of values before reporting or display, whereas the internal calculation precision applies to the calculations *leading up to* that quantization.

### 2.1. Input Data Handling & Asset Identification

The system must parse IBKR data from CSV reports: Trades (including the `Open/CloseIndicator` column used for trade classification as detailed in Section 5, Step 7), Cash Transactions, Positions (Start/End of Year), and Corporate Actions (`corpact*.csv`). Input monetary values and quantities will be converted to `Decimal` type upon parsing. Initialization of these `Decimal` objects from input strings will adhere to the principle outlined in Section 2.0.4 to maintain source precision. The system uses configurable file paths (e.g., `TRADES_FILE_PATH`, `CASH_TRANSACTIONS_FILE_PATH` from `config.py`).

#### Note on Start-of-Year Positions and Quantities
- The `POSITIONS_START_FILE_PATH` is crucial for establishing initial inventory quantities (as `Decimal`) and potentially cost basis (`Decimal`) at the beginning of the tax year.
- **SOY Quantity Precedence:** The `soy_quantity` reported in the positions start file for each `Asset` (excluding `AssetCategory.CASH_BALANCE` types) is considered **factually correct and has absolute priority** over any quantity that might be derived from analyzing pre-tax-year historical trades.
- **Assets Not in SOY Report:** For any `Asset` (excluding `AssetCategory.CASH_BALANCE` types) that is **not present** in the positions start file, its `soy_quantity` at the beginning of the tax year **must be assumed to be `Decimal(0)`.**
- The detailed logic for determining the SOY cost basis, which may involve historical FIFO calculations or data from the positions start file, is specified in Section 2.4.

It must handle various CSV dialects and potential character encodings (e.g., BOMs).

#### Asset Identification (Alias Map System)
The system maintains a global `alias_map` (e.g., `Dict[str, Asset]`) where keys are identifier strings (e.g., "ISIN:DE000...", "CONID:123...", "SYMBOL:AAPL", "CASH_BALANCE:EUR") and values are unique `Asset` objects (see Section 4 for `Asset` structure).

For each row processed from any input file:
1. Generate all available aliases from the row (ISIN, Conid, Symbol). For generic cash balances (IBKR asset class "CASH" where symbol matches currency), a key based on the currency (e.g., `CASH_BALANCE:EUR`) is generated, corresponding to an `Asset` of `AssetCategory.CASH_BALANCE`. For FX trading pairs (e.g., symbol "EUR.USD" with IBKR asset class "CASH"), standard symbol aliases are generated, and these are typically classified initially as `AssetCategory.UNKNOWN`.
2. Look up these aliases in the `alias_map`.
3. If multiple distinct `Asset` objects are found, merge them into a single survivor `Asset` object (preferring more specific types like `CashBalance` or `InvestmentFund` over generic `Asset`, and those with more identifiers). The surviving object consolidates all aliases from the merged objects. Attributes are updated based on the current row.
4. If one `Asset` object is found, use it.
5. If no `Asset` object is found, create a new `Asset` object.
6. Update the attributes of the (survivor or new) `Asset` object using the data from the current row, preferring more specific or recent information. The `Asset.description` is updated based on `description_source_type` (e.g., "trade", "position", "corp_act_asset") with a preference for descriptions from trades and positions over more generic ones; cash transaction event descriptions are not used to update `Asset.description`. Store IBKR's raw asset class and sub-category for reference.
7. Ensure all aliases derived from the row and the asset's current state are registered in the `alias_map` and point to the single (survivor or new) `Asset` object. The `Asset` object itself also stores its set of known aliases.

The `Description` field from IBKR reports is stored for informational purposes. Its update logic on the `Asset` object prioritizes sources like trades and positions. It is **not** used as a primary fallback for generating asset identification aliases if structured identifiers (ISIN, Conid, Symbol) are missing for a specific financial instrument.

If a non-generic-cash item (i.e., an actual financial instrument) lacks an ISIN, Conid, and a specific Symbol after parsing all available data, a minimal `Asset` object is still created for tracking, rather than flagging it as a fatal data error. The system relies on the available data for classification.

It must use IBKR's `Conid` and `Underlying Conid` (stored in `Derivative` asset types) for reliable asset and derivative linkage where available. `AssetResolver.link_derivatives()` performs this linkage.

For corporate actions, it must use `ActionID` (stored as `ca_action_id_ibkr` in `CorporateActionEvent`) to link related events if necessary.

### 2.2. Data Enrichment & Preparation

The system must fetch and cache daily ECB EUR exchange rates for converting all relevant monetary values (stored as `Decimal`) to EUR. All calculations involving money will use `Decimal` arithmetic. These calculations, including currency conversions and the derivation of `net_proceeds_or_cost_basis_eur`, will be performed using the `INTERNAL_CALCULATION_PRECISION` (see Section 2.0.2) before any final quantization to `OUTPUT_PRECISION_AMOUNTS` or `OUTPUT_PRECISION_PER_SHARE`. Caching uses `ECB_RATES_CACHE_FILE_PATH` (from `config.py`). The `ECBExchangeRateProvider` uses `MAX_FALLBACK_DAYS` (e.g., 7 days) if a rate for a specific day is unavailable and `CURRENCY_CODE_MAPPING` (e.g., CNH to CNY) for specific currency codes.

The `enrich_financial_events` function converts amounts in `FinancialEvent` objects. It uses defined precisions (e.g., `OUTPUT_PRECISION_AMOUNTS = Decimal("0.01")`, `OUTPUT_PRECISION_PER_SHARE = Decimal("0.000001")`) for EUR values after internal calculations are complete.

It must calculate cost basis and proceeds in EUR (as `Decimal`) for all transactions. (`enrich_financial_events` calculates `net_proceeds_or_cost_basis_eur` for `TradeEvent`s).

`TradeEvent.__post_init__` defaults `commission_currency` to the trade's `local_currency` if the commission is non-zero and its currency is not specified, aiding conversion.

For `CurrencyConversionEvent`, the parent `FinancialEvent`'s `gross_amount_foreign_currency` and `local_currency` fields are populated with the `to_amount` and `to_currency` of the conversion, respectively.

It must identify the source country for withholding tax purposes based on available data (e.g., ISIN, descriptions from cash transaction reports, `issuer_country_code` from IBKR data). For broker interest, the source country may be heuristically set (e.g., to "IE"). A regex (`wht_on_interest_pattern`) aids in identifying WHT on interest from event descriptions.

#### Enhanced Data Validation & Error Handling (v3.3.1)

The system includes comprehensive validation and error handling mechanisms to ensure data integrity throughout the processing pipeline:

**FIFO Processing Validation:**
- Before FIFO lot creation, the system validates that all required fields are properly enriched, particularly `net_proceeds_or_cost_basis_eur` for `TradeEvent` objects.
- Missing enrichment data triggers explicit error logging with detailed information about the failing transaction, including the `ibkr_transaction_id` and specific missing field.
- Prevents silent failures during FIFO processing that could lead to incorrect gain/loss calculations.

**Option Trade Classification:**
- Enhanced classification logic for option assignments distinguishes between opening and closing transactions using the `Open/CloseIndicator` field.
- Only trades marked with 'A' (Assignment) notes codes **and** not flagged as closing transactions (`open_close_indicator != 'C'`) are classified as new option assignments.
- Prevents misclassification of option assignment events when closing existing positions, avoiding double-processing of option premiums.

**Chronological Event Ordering:**
- Event sorting algorithm enhanced to use IBKR transaction IDs as the primary secondary sort key for same-date events.
- Ensures chronological processing order is maintained, leveraging IBKR's sequential transaction ID assignment.
- Critical for accurate FIFO calculations, particularly in high-frequency trading scenarios or complex option strategies involving multiple same-date transactions.

### 2.3. Asset Classification for Tax Declaration

The system must classify assets to determine their correct treatment and placement on tax forms. Classification is performed on the unique `Asset` objects by the `AssetClassifier`, setting their `asset_category` attribute (of type `AssetCategory`). Key classifications include:

- **`AssetCategory.INVESTMENT_FUND` (for Anlage KAP-INV):** Identify assets like ETFs and mutual funds. Exclude ETCs/ETPs intended for Anlage SO. **Assumes all investment fund shares were acquired on or after 01.01.2018.**
  - **Fund Type (for KAP-INV lines & Teilfreistellung):** Further classify `InvestmentFund` assets by setting their `fund_type` attribute (of type `InvestmentFundType`) into "Aktienfonds," "Mischfonds," "Immobilienfonds," "Auslands-Immobilienfonds," and "Sonstige Fonds" as per German tax law definitions (§ 2 InvStG) and *Anleitung zur Anlage KAP-INV 2023*. This dictates Teilfreistellung rates.
- **`AssetCategory.STOCK` (Aktien):** Equity shares not classified as investment funds. Includes common stock and ADRs. For Anlage KAP.
- **`AssetCategory.BOND` (Anleihen, sonstige Kapitalforderungen):** For Anlage KAP.
- **`AssetCategory.OPTION` & `AssetCategory.CFD` (Termingeschäfte):** Includes listed options and CFDs/FXCFDs. For Anlage KAP.
- **`AssetCategory.PRIVATE_SALE_ASSET` (Anlage SO):** Identify assets subject to §23 EStG tax if sold within the statutory period (typically 1 year). Examples include physical Gold ETCs (if they offer a claim to physical gold) and Crypto Asset ETPs/ETCs. *These are explicitly NOT investment funds for KAP-INV.*
- **`AssetCategory.CASH_BALANCE`:** Actual currency holdings.
- **`AssetCategory.UNKNOWN`:** For assets that couldn't be definitively categorized or for instruments like FX trading pairs (e.g., "EUR.USD" from IBKR "CASH" asset class) which are not cash balances but instruments whose trades result in `CurrencyConversionEvent`s.

Classification results are cached (using `CLASSIFICATION_CACHE_FILE_PATH` from `config.py`) using a stable key generated by `Asset.get_classification_key()`.

Interactive classification (`IS_INTERACTIVE_CLASSIFICATION` flag in `config.py`) is available for ambiguous assets. The system prevents FX trading pairs from being interactively misclassified as `CASH_BALANCE`.

If an asset's classification changes its Python type (e.g., generic `Asset` to `InvestmentFund`), `AssetResolver.replace_asset_type()` handles this, preserving the `internal_asset_id` and aliases.

### 2.4. FIFO Calculation & Gain/Loss Determination (with Corporate Actions)

The system must implement the First-In, First-Out (FIFO) method in EUR (using `Decimal` for quantities and cost basis) to calculate realized capital gains and losses for all relevant asset realizations. Each such realization results in a `RealizedGainLoss` object which specifies the `RealizationType` (e.g., `RealizationType.LONG_POSITION_SALE` for sales, `RealizationType.SHORT_POSITION_COVER` for covering short positions). All intermediate calculations within the FIFO logic, cost basis adjustments due to corporate actions, and gain/loss computations will operate using the `INTERNAL_CALCULATION_PRECISION` (Section 2.0.2). Asset lots must store acquisition date, quantity (`Decimal`), and EUR cost basis (`Decimal`). Final realized gain/loss figures will be quantized to appropriate reporting precisions only at the aggregation or reporting stage.

#### Initialization of FIFO Ledgers at Start-of-Year (SOY) and EOY Validation

**SOY Quantity:** The `soy_quantity` (`Decimal`) for an `Asset` (as established per Section 2.1, i.e., primarily from positions start file, or `Decimal(0)` if not listed for non-cash assets) is the definitive starting quantity for its FIFO ledger at the beginning of the tax year. This applies to both long (`soy_quantity` > 0) and short (`soy_quantity` < 0) positions.

**SOY Cost Basis Determination:**
1. **Historical FIFO Simulation:** The system will simulate the FIFO state by processing historical trade data (transactions like `TradeEvent` and relevant corporate actions such as `CorpActionSplitForward`, `CorpActionStockDividend` occurring *before* the start of the current tax year), using the `INTERNAL_CALCULATION_PRECISION`.
2. **Prioritization of Reconstructed Data:** The cost basis (or proceeds for initial short positions) for the `soy_quantity` will be derived from this historical simulation if:
   - The simulation process did not encounter internal inconsistencies (e.g., attempting to sell more shares than available based on prior simulated buys).
   - The net quantity (long or short) derived from the simulation aligns with the sign of the `soy_quantity`.
   - The total quantity of simulated historical lots (long or short) is sufficient to cover the absolute value of `soy_quantity`.
3. **Fallback to Reported SOY Cost Basis:** If the conditions for using the historically simulated FIFO lots are not met (e.g., insufficient historical data, simulation inconsistencies, or misalignment with reported SOY quantity sign/magnitude), then the cost basis (or proceeds) for the *entire* `soy_quantity` **must** be taken from the `soy_cost_basis_amount` and `soy_cost_basis_currency` fields reported in the positions start file. This reported cost basis is then converted to EUR if necessary, using the `INTERNAL_CALCULATION_PRECISION`. If this reported SOY cost basis information is also missing, a zero-value FIFO lot (zero cost for long, zero proceeds for short) will be created with an acquisition/opening date of December 31st of the preceding tax year (e.g., "YYYY-1-12-31").

**EOY Quantity Validation:** After processing all `FinancialEvent` objects for the tax year, the calculated end-of-year (EOY) quantity for each `Asset` in its FIFO ledger **must be identical**, within a small numerical tolerance, to the `eoy_quantity` (`Decimal`) reported in the `POSITIONS_END_FILE_PATH` (if the asset is listed).
- Any discrepancy (beyond the tolerance) between the FIFO-calculated EOY quantity and the reported `eoy_quantity` (for assets present in the end-of-year position report) **must be flagged as a critical error** and reported to the user.
- If an asset is not present in the positions end file, its authoritative quantity is `Decimal(0)`. If its calculated EOY quantity differs significantly (beyond the tolerance) from zero, this must also be treated as a critical error.

#### Corporate Action Handling

Corporate actions (specific subtypes of `CorporateActionEvent`) must be processed chronologically alongside trades to correctly adjust FIFO lots *before* subsequent sales. Cost basis adjustments will use `INTERNAL_CALCULATION_PRECISION`.

- **`FinancialEventType.CORP_SPLIT_FORWARD` (Forward Splits FS):** Adjust quantity and cost basis per share in existing FIFO lots. Not taxable.
- **`FinancialEventType.CORP_MERGER_CASH` (Acquisition for Cash TC):** Treated as a sale of existing FIFO lots. Realized G/L reported in Anlage KAP (with `RealizationType.CASH_MERGER_PROCEEDS`).
- **`FinancialEventType.CORP_MERGER_STOCK` (Stock-for-Stock Merger TC):** Assume tax-neutral. While a `MergerStockProcessor` class may exist, the detailed FIFO lot conversion logic within `FifoLedger` (i.e., transforming lots of an old asset into lots of a new asset while preserving original acquisition dates and pro-rated cost bases) for tax-neutral stock-for-stock mergers is NOT YET IMPLEMENTED.
- **`FinancialEventType.CORP_STOCK_DIVIDEND` (Stock Dividends HI/SD):** Support both HI and SD corporate action types. German tax treatment: new shares receive zero cost basis. For taxable stock dividends: FMV of new shares is dividend income (contributes to `kap_other_income_positive` described in Sec 2.7) and new shares form a new FIFO lot with zero cost basis. Skip IBKR receivable assets (.REC) to avoid duplication. (`new_shares_per_existing_share` attribute is initialized as a placeholder if not directly calculable from report).

#### Dividend Rights (DI/ED) Processing

For dividend rights scenarios where rights are issued (DI) and expire (ED) with cash payments:

**Event Processing:**
- DI events: Parsed as `CorpActionStockDividend` with `quantity_new_shares_received = 0`
- ED events: Parsed as `FinancialEventType.CORP_EXPIRE_DIVIDEND_RIGHTS`

**Post-Processing Pipeline (`_process_dividend_rights_matching`):**
1. Match DI/ED pairs by asset identifiers (CONID/ISIN/Symbol)
2. Extract underlying stock ISIN from DI event description
3. Re-link associated cash events to underlying stock (not dividend rights)
4. Prevent creation of phantom dividend shares

**Tax Impact:**
- Cash payments process as capital repayments against underlying stock FIFO ledger
- No taxable income from rights expiry itself

#### Option Exercise and Assignment Processing

It must reliably process option exercises (`FinancialEventType.OPTION_EXERCISE`) and assignments (`FinancialEventType.OPTION_ASSIGNMENT`). This involves:

**Parsing and Event Creation:**
- An option exercise or assignment (e.g., `AssetClass` "OPT" with `Notes/Codes` 'Ex' or 'A' in the Trades CSV) is parsed into an `OptionExerciseEvent` or `OptionAssignmentEvent`.
- The corresponding movement of the underlying stock is parsed from a *separate row* in the Trades CSV as a standard `TradeEvent`.

**Identifying and Linking Related Events (Post-Event Creation):** After initial event parsing, the system links the `OptionExerciseEvent` or `OptionAssignmentEvent` to its corresponding stock `TradeEvent`. This is handled by the `OptionTradeLinker` using the following mechanism:

1. **Candidate Selection:**
   - `OptionExerciseEvent` and `OptionAssignmentEvent` objects created from option trades are collected as candidates for linking.
   - Stock `TradeEvent` objects are pre-filtered as candidates for linking if their `ibkr_notes_codes` field contains 'A' (Assignment/Auto-Exercise) or 'EX' (Exercise) indicators.
   - Exclude "IA" (Internalized + Automatically Allocated) codes from option assignment detection to prevent false positives.

2. **Option Event Lookup Map Construction:** A lookup map is built for the candidate option lifecycle events. The key for this map is a tuple:
   - `(event_date_str, option_asset.underlying_ibkr_conid, abs_expected_stock_qty_str)`

3. **Stock Trade Matching:** Each candidate stock `TradeEvent` attempts to find a match in the option event lookup map using a similarly structured key:
   - `(stock_trade.event_date, stock_asset.ibkr_conid, stock_trade.quantity.copy_abs().to_eng_string())`

4. **Link Establishment:** If a stock trade's key matches a key in the option event lookup map, the stock `TradeEvent`'s `related_option_event_id` field is populated with the `event_id` of the matched `OptionLifecycleEvent`.

**Implicit Matching Criteria through Key Structure:** This linking mechanism inherently relies on:
- **Identical `event_date`**.
- **Underlying Asset Match:** The `Option` asset's `underlying_ibkr_conid` (used in the option event key) must effectively match the `Stock` asset's `ibkr_conid` (used in the stock trade key) for the keys to be identical.
- **Quantity Consistency:** The absolute quantity of the stock `TradeEvent` must match the calculated expected stock quantity from the option event (option contracts * multiplier).

**Handling Ambiguity and Failures during Linking:**
- If the option event lookup map construction encounters duplicate keys (e.g., multiple option events on the same day for the same underlying predicting the same stock movement), a warning is logged, and the later event typically overwrites the earlier one in the lookup.
- If a candidate stock `TradeEvent` (pre-filtered by `Notes/Codes`) fails to find a match in the option event lookup map, a warning is logged, indicating a potential linking failure that might require investigation.

**Price Consistency (Not Used for Linking):** The current linking mechanism does *not* use the stock trade price versus the option strike price as part of the key for matching.

**Adjusting Stock Trade Economics:** Once an option exercise/assignment event is linked to the corresponding stock `TradeEvent` (via `related_option_event_id` on the stock `TradeEvent`), the system must adjust the economics of the stock trade to incorporate the option premium (cost or proceeds, in EUR). Option lifecycle event processors (e.g., for exercise or assignment) calculate and temporarily store the total EUR premium of the option leg (e.g., in a context dictionary like `pending_option_adjustments`, keyed by the option event's ID). The `TradeProcessor`, when processing the linked stock `TradeEvent`, retrieves this stored premium and applies the adjustment. All adjustments use `INTERNAL_CALCULATION_PRECISION`. The specific adjustments are as follows:

- **When the Stock Trade is a Purchase (event types `TRADE_BUY_LONG` or `TRADE_BUY_SHORT_COVER`):**
  - **If due to Long Call Exercise:** The premium *paid* for the call option effectively increases the cost basis of the stock purchased (or increases the cost to cover an existing short stock position).
    - `Adjusted Stock Cost (EUR) = Original Stock Cost (EUR) + Option Premium Paid (EUR)`
  - **If due to Short Put Assignment:** The premium *received* for the put option effectively decreases the cost basis of the stock purchased (or decreases the cost to cover an existing short stock position).
    - `Adjusted Stock Cost (EUR) = Original Stock Cost (EUR) - Option Premium Received (EUR)`

- **When the Stock Trade is a Sale (event types `TRADE_SELL_LONG` or `TRADE_SELL_SHORT_OPEN`):**
  - **If due to Short Call Assignment:** The premium *received* for the call option effectively increases the proceeds from the stock sold (or increases the proceeds recognized from opening a new short stock position).
    - `Adjusted Stock Proceeds (EUR) = Original Stock Proceeds (EUR) + Option Premium Received (EUR)`
  - **If due to Long Put Exercise:** The premium *paid* for the put option effectively decreases the proceeds from the stock sold (or decreases the proceeds recognized from opening a new short stock position).
    - `Adjusted Stock Proceeds (EUR) = Original Stock Proceeds (EUR) - Option Premium Paid (EUR)`

The `net_proceeds_or_cost_basis_eur` field of the stock `TradeEvent` shall be updated to reflect this adjusted economic value. The original (unadjusted) value is derived from the stock trade's price and quantity, plus commissions. The adjustment then modifies this net value. The temporary storage for the premium is cleared after use.

It must realize gains/losses on worthless option expirations (`FinancialEventType.OPTION_EXPIRATION_WORTHLESS`). The `RealizedGainLoss` object will have `RealizationType.OPTION_EXPIRED_LONG` or `RealizationType.OPTION_EXPIRED_SHORT`. These G/L contribute to `derivative_gains_gross` or `derivative_losses_abs` (Sec 2.7).

Correctly calculate gains/losses from covering short stock positions (`FinancialEventType.TRADE_BUY_SHORT_COVER`) using FIFO principles, reported in Anlage KAP (with `RealizationType.SHORT_POSITION_COVER`). These G/L contribute to `stock_gains_gross` or `stock_losses_abs` (Sec 2.7).

For assets classified as `AssetCategory.PRIVATE_SALE_ASSET`, it must check the holding period (calculated from acquisition and realization dates of FIFO lots). Gains/losses are only taxable under §23 EStG if the holding period is <= 1 year (realization type `RealizationType.LONG_POSITION_SALE`).

Trades of instruments identified as FX trading pairs (e.g., 'EUR.USD' where IBKR asset class is "CASH") directly result in `CurrencyConversionEvent` objects, not `TradeEvent`s requiring FIFO.

### 2.5. Income Calculation & Teilfreistellung (Partial Exemption) for Investment Funds

**General Principle for Anlage KAP-INV Reporting:** All income (distributions) and capital gains/losses from investment funds are reported **GROSS (i.e., before Teilfreistellung, as `Decimal`)** on the Anlage KAP-INV form lines. Teilfreistellung is calculated to determine *net taxable amounts* (`Decimal`). These net amounts are then used as components for calculating `kap_other_income_positive` and `kap_other_losses_abs` (see Sec 2.7) for Anlage KAP. All intermediate calculations for gross income, Teilfreistellung amounts, and net taxable amounts will use the `INTERNAL_CALCULATION_PRECISION` before final figures are determined for reporting and quantized to appropriate precisions. **This section assumes all fund shares were acquired on or after 01.01.2018.**

#### 2.5.1. Distributions (`FinancialEventType.DISTRIBUTION_FUND`)
- Identify gross distributions from `InvestmentFund` assets (with an `event_date` within the 2023 tax year).
- Calculate applicable Teilfreistellung amount (`Decimal`) based on `InvestmentFund.fund_type`.
- Store: Gross Distribution, Fund Type, Teilfreistellung Rate (%), Teilfreistellung Amount EUR, Net Taxable Distribution Amount (all as `Decimal`). The Net Taxable Distribution Amount (positive or negative) contributes to `fund_income_net_taxable` which is used for internal calculations but NOT included in Anlage KAP Zeile 19.
- **For reporting on Anlage KAP-INV (Zeilen 4-8), the GROSS Distribution is used.**

#### 2.5.2. Capital Gains from Sale of Investment Funds
- Calculate gross gains/losses (FIFO, `Decimal`, adjusted for CAs, realization type `RealizationType.LONG_POSITION_SALE`) for sales occurring within the 2023 tax year.
- Apply appropriate Teilfreistellung based on `InvestmentFund.fund_type` to the gross gain/loss.
- Store: Gross Gain/Loss, Fund Type, Teilfreistellung Rate (%), Teilfreistellung Amount EUR, Net Taxable Gain/Loss (all as `Decimal`) in `RealizedGainLoss`. The `RealizedGainLoss.net_gain_loss_after_teilfreistellung_eur` (positive or negative) contributes to `fund_income_net_taxable` which is used for internal calculations but NOT included in Anlage KAP Zeile 19.
- **For reporting on Anlage KAP-INV (Zeilen 14, 17, 20, 23, 26), the GROSS Gain/Loss is used.**

#### 2.5.3. Vorabpauschale (Advance Lump-Sum Tax)
- For tax year 2023, this will be €0. KAP-INV lines 9-13 will be €0. Details stored in `VorabpauschaleData`.
- Calculation logic should still consider `InvestmentFund.fund_type` for Teilfreistellung on the (zero) base.
- The result is a €0 net taxable Vorabpauschale. The `VorabpauschaleData.net_taxable_vorabpauschale_eur` contributes to `fund_income_net_taxable` (as €0).

### 2.6. Other Income Calculation (Components for Anlage KAP)

**All income calculations in this section are strictly for events occurring within the current tax year. Financial events with an `event_date` outside this period are excluded from these aggregations.** Calculations to use `INTERNAL_CALCULATION_PRECISION`.

### 2.6. Capital Repayments (Einlagenrückgewähr)

The system must distinguish between taxable dividends and tax-free capital repayments based on IBKR's "Exempt From Withholding" indicator.

**Detection & Classification:**
- Cash events with "Exempt From Withholding" → `FinancialEventType.CAPITAL_REPAYMENT`
- Regular dividend events → `FinancialEventType.DIVIDEND_CASH`

**FIFO Cost Basis Reduction:**
- Apply repayment amount to reduce acquisition cost of existing FIFO lots (oldest first)
- If repayment exceeds total cost basis, excess becomes taxable dividend income
- Method: `FifoLedger.reduce_cost_basis_for_capital_repayment()`

**Tax Treatment:**
- Cost basis reduction: No taxable income
- Excess amounts: Create separate `DIVIDEND_CASH` events, contribute to `kap_other_income_positive`

**Dividends (Non-Funds, `FinancialEventType.DIVIDEND_CASH`):** Taxable dividend distributions from `AssetCategory.STOCK` assets (with `event_date` in current tax year). These contribute to `kap_other_income_positive`.

**Taxable Income from Corporate Actions:**
- Cash received in `FinancialEventType.CORP_MERGER_CASH` (with `event_date` in 2023) is part of proceeds for G/L calculation (see `RealizationType.CASH_MERGER_PROCEEDS`). The G/L contributes to stock G/L pools.
- The FMV of shares from taxable `FinancialEventType.CORP_STOCK_DIVIDEND` (with `event_date` in current tax year) is dividend income, contributing to `kap_other_income_positive`.

**Interest (`FinancialEventType.INTEREST_RECEIVED`):** Identify and aggregate gross interest income from `AssetCategory.BOND` or `AssetCategory.CASH_BALANCE` (with `event_date` in current tax year). These contribute to `kap_other_income_positive`.

**Stückzinsen (Accrued Interest on Bonds):**
- Stückzinsen *received* (from `FinancialEventType.INTEREST_RECEIVED` events marked as Stückzinsen, with `event_date` in current tax year) are positive income.
- Stückzinsen *paid* (`FinancialEventType.INTEREST_PAID_STUECKZINSEN`, with `event_date` in current tax year) are negative income.
- The net sum of Stückzinsen (`stueckzinsen_net = stueckzinsen_received - stueckzinsen_paid`, considering only current tax year events) is calculated. If `stueckzinsen_net > 0`, it contributes to `kap_other_income_positive`. If `stueckzinsen_net < 0`, its absolute value contributes to `kap_other_losses_abs`.

**Option Premiums:** Realized premiums from short option positions (e.g., from `FinancialEventType.OPTION_EXPIRATION_WORTHLESS` resulting in `RealizationType.OPTION_EXPIRED_SHORT`, or closing short option trades resulting in `RealizationType.OPTION_TRADE_CLOSE_SHORT`, all with `event_date` in current tax year) are gains from Termingeschäfte. Stored in `RealizedGainLoss` with the `is_stillhalter_income` flag set to `True`. These contribute to `derivative_gains_gross`. Losses from closing long option positions or worthless long expirations (with `event_date` in current tax year) contribute to `derivative_losses_abs`.

### 2.7. Aggregation into Declaration-Specific Categories (Tax Form Line Items for 2023 - NO ALT-ANTEILE)

For Anlage KAP-INV, **form lines receive GROSS figures (before Teilfreistellung)**.
For Anlage KAP, specific lines (20, 21, 22, 23, 24) report specific gross gain/loss components, and line 19 reports foreign capital income after netting (excluding fund-related items and derivative losses).

All aggregations from `Decimal` source values (derived from 2023 tax year events) must maintain precision until final quantization for reporting.

#### Internal Component Calculation for Anlage KAP

The system will first calculate the following fundamental components, based on events and realizations within the 2023 tax year:

1. **`stock_gains_gross`**: Sum of GROSS positive gains from selling stocks (from `RealizedGainLoss` where `asset_category_at_realization == STOCK`, `gross_gain_loss_eur > 0`, and `realization_date` is in 2023).

2. **`stock_losses_abs`**: Sum of GROSS (absolute) losses from selling stocks (from `RealizedGainLoss` where `asset_category_at_realization == STOCK`, `gross_gain_loss_eur < 0`, take absolute value, and `realization_date` is in 2023).

3. **`derivative_gains_gross`**: Sum of GROSS positive gains from derivatives (options, CFDs, including `is_stillhalter_income`) (from `RealizedGainLoss` where `asset_category_at_realization` is `OPTION` or `CFD`, `gross_gain_loss_eur > 0`, and `realization_date` is in 2023).

4. **`derivative_losses_abs`**: Sum of GROSS (absolute) losses from derivatives (from `RealizedGainLoss` where `asset_category_at_realization` is `OPTION` or `CFD`, `gross_gain_loss_eur < 0`, take absolute value, and `realization_date` is in 2023).

5. **`kap_other_income_positive`**: Algebraic sum of (all from events with `event_date` in 2023):
   - Gross positive Interest Received (`FinancialEventType.INTEREST_RECEIVED`).
   - Gross positive Non-Fund Dividends (`FinancialEventType.DIVIDEND_CASH` from `STOCK` assets, FMV of taxable `FinancialEventType.CORP_STOCK_DIVIDEND`).
   - Gross positive Bond Gains (from `RealizedGainLoss` where `asset_category_at_realization == BOND`, `gross_gain_loss_eur > 0`, and `realization_date` is in 2023).
   - Net Stückzinsen (`stueckzinsen_received` minus `stueckzinsen_paid`); only if result > 0.
   - **Note: Fund-related items (distributions, gains, Vorabpauschale) are NOT included here as they belong on KAP-INV**

6. **`kap_other_losses_abs`**: Sum of absolute values of (all from events/realizations with `event_date`/`realization_date` in 2023):
   - Gross Bond Losses (from `RealizedGainLoss` where `asset_category_at_realization == BOND`, `gross_gain_loss_eur < 0`, take absolute value).
   - Net Stückzinsen (`stueckzinsen_received` minus `stueckzinsen_paid`); take absolute value if result < 0.
   - **Note: Fund-related losses are NOT included here as they belong on KAP-INV**

7. **`fund_income_net_taxable`** (for internal calculations only, NOT for Anlage KAP, based on 2023 events/realizations):
   - Sum of all net taxable fund-related items after Teilfreistellung:
     - Net fund distributions (gross - Teilfreistellung)
     - Net fund sale gains/losses (gross - Teilfreistellung)
     - Net Vorabpauschale (€0 for 2023)

#### Anlage KAP (Einkünfte aus Kapitalvermögen) - 2023 Form Lines

Assuming Zeile 18 (Inländische Kapitalerträge) = 0:

- **Zeile 19 (Ausländische Kapitalerträge):** Foreign capital income after netting (excluding fund-related items and derivative losses). Calculated as:
  ```
  zeile_19_amount = stock_gains_gross + derivative_gains_gross + kap_other_income_positive - stock_losses_abs - kap_other_losses_abs
  ```
  Mapped via `TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT`.
  **Note:** Derivative losses are NOT subtracted here due to special offsetting rules. Fund-related items are NOT included as they belong on KAP-INV.

- **Zeile 20 (Gewinne aus Aktienveräußerungen):** Declares `stock_gains_gross`. Mapped via `TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN`.

- **Zeile 21 (Einkünfte aus Stillhalterprämien und Gewinne aus Termingeschäften):** Declares `derivative_gains_gross`. Mapped via `TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN`.

- **Zeile 22 (Verluste aus Kapitalerträgen ohne Aktienveräußerungen und ohne Verluste aus Termingeschäften):** Declares `kap_other_losses_abs`. Mapped via `TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE`.

- **Zeile 23 (Verluste aus der Veräußerung von Aktien):** Declares `stock_losses_abs`. Mapped via `TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST`.

- **Zeile 24 (Verluste aus Termingeschäften):** Declares `derivative_losses_abs`. The €20,000 offsetting limit is applied by the Finanzamt based on this declared gross figure. Mapped via `TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST`.

- **Zeile 41 (Anrechenbare noch nicht angerechnete ausländische Steuern):** Aggregated foreign WHT from `WithholdingTaxEvent` (with `event_date` in 2023).

#### Anlage KAP-INV (Investmenterträge) - 2023 Form Lines (NO ALT-ANTEILE)

**IMPORTANT:** Amounts for lines 4-8 and 14, 17, 20, 23, 26 are **GROSS (vor Teilfreistellung)**, from events/realizations in 2023.

*Distributions (Ausschüttungen) - Gross (from `CashFlowEvent` for fund distributions with `event_date` in 2023):*
- **Zeile 4:** Aktienfonds (`TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_AUSSCHUETTUNG_GROSS`).
- **Zeile 5:** Mischfonds (`TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_AUSSCHUETTUNG_GROSS`).
- **Zeile 6:** Immobilienfonds (`TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS`).
- **Zeile 7:** Auslands-Immobilienfonds (`TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS`).
- **Zeile 8:** Sonstige Investmentfonds (`TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_AUSSCHUETTUNG_GROSS`).

*Vorabpauschale (Lines 9-13, from `VorabpauschaleData`):* €0 for 2023.

*Gains/Losses from Sale of Investment Fund Shares (acquired on/after 01.01.2018) - Gross (from `RealizedGainLoss` with `realization_date` in 2023):*
- **Zeile 14:** Aktienfonds (`TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS`).
- **Zeile 17:** Mischfonds (`TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS`).
- **Zeile 20:** Immobilienfonds (`TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS`).
- **Zeile 23:** Auslands-Immobilienfonds (`TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS`).
- **Zeile 26:** Sonstige Investmentfonds (`TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS`).

#### Anlage SO (Sonstige Einkünfte - §23 EStG Private Sales Transactions) - 2023 Form Structure

Applies to `AssetCategory.PRIVATE_SALE_ASSET` if sold within 1 year (holding period check), with `realization_date` in 2023.

*For each taxable transaction (from `RealizedGainLoss` with `realization_date` in 2023 and `TaxReportingCategory.SECTION_23_ESTG_TAXABLE_GAIN` or `_LOSS`):*
- **Zeile 42 / 48 (Bezeichnung / Art des Wirtschaftsguts):** `Asset.description`.
- **Zeile 43 / 49 (Veräußerung am; Anschaffung am):** `RealizedGainLoss.realization_date`, `RealizedGainLoss.acquisition_date`.
- **Zeile 44 / 50 (Veräußerungspreis):** `RealizedGainLoss.total_realization_value_eur`.
- **Zeile 45 / 51 (Anschaffungskosten):** `RealizedGainLoss.total_cost_basis_eur`.
- **Zeile 46 / 52 (Werbungskosten):** Expenses EUR (Note: Trade commissions are part of cost basis/proceeds. Other Werbungskosten are not currently handled beyond this).
- **Zeile 47 / 53 (Gewinn / Verlust):** `RealizedGainLoss.gross_gain_loss_eur`.

*Aggregated §23 EStG Results (from 2023 realizations):*
- **Zeile 54 (Zurechnung der Beträge aus den Zeilen 47 und 53):** Total net G/L from §23 EStG transactions.

### 2.8. Loss Offsetting for Declaration

The primary function for declaration is to prepare the figures for Anlage KAP lines 19-24 and Anlage SO Zeile 54 as detailed in Section 2.7, based on 2023 tax year events and realizations.

**Anlage KAP Line Figures:**
- Zeile 19: Foreign capital income after netting (calculated as shown above)
- Zeile 20: `stock_gains_gross` (Gross Stock Gains)
- Zeile 21: `derivative_gains_gross` (Gross Derivative Gains)
- Zeile 22: `kap_other_losses_abs` (Gross "Other" Losses - Absolute)
- Zeile 23: `stock_losses_abs` (Gross Stock Losses - Absolute)
- Zeile 24: `derivative_losses_abs` (Gross Derivative Losses - Absolute)

The Finanzamt will apply the actual loss offsetting rules based on these declared figures (e.g., offsetting stock gains/losses, offsetting other income/losses, applying the €20,000 derivative loss limitation against derivative gains and then other income).

**Conceptual Net Balances (for User Information):** The system will also calculate and can display the conceptual net balances of each tax pot for user information, based on 2023 tax year data:
- Stocks Net: `stock_gains_gross - stock_losses_abs`.
- Derivatives Net: `derivative_gains_gross - derivative_losses_abs` (the €20,000 offsetting limit for net derivative losses can be conceptually applied and shown for this summary).
- Other Capital Income Net (KAP only): `kap_other_income_positive - kap_other_losses_abs`.
- Fund Income Net (KAP-INV): `fund_income_net_taxable` (after Teilfreistellung).
- §23 EStG Net: Sum of `RealizedGainLoss.gross_gain_loss_eur` for taxable §23 transactions.

All calculations to use `INTERNAL_CALCULATION_PRECISION` until final net amounts for declaration are determined.

### 2.9. Foreign Withholding Tax (WHT) Aggregation

Foreign withholding tax is calculated centrally in `LossOffsettingEngine` with proper tax year filtering. Uses `TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID` for consistent reporting across console and PDF outputs. This single-source-of-truth approach eliminates discrepancies between different report formats.

Aggregate total gross income subject to WHT and total WHT paid (from `WithholdingTaxEvent.gross_amount_eur` where `event_date` is in current tax year) per source country for Anlage KAP Zeile 41.
Does not calculate *creditable* WHT.

### 2.10. Reporting & Output

#### Console Tax Declaration Summary
Figures for **direct entry onto current tax year forms**.
- Anlage KAP: Values for Zeile 19, 20, 21, 22, 23, 24 as calculated per Section 2.7.
- Anlage KAP-INV: GROSS amounts for Zeilen 4-8 and 14, 17, 20, 23, 26.
- Anlage SO: Net G/L for Zeile 54.

Values will be quantized to `OUTPUT_PRECISION_AMOUNTS` for display.

Example output:
```
Anlage KAP:
  Zeile 19 (Ausländische Kapitalerträge nach Saldierung): €X,XXX.XX
    [Foreign capital income after netting, excluding fund items and derivative losses]
  Zeile 20 (Aktiengewinne): €X,XXX.XX
  Zeile 21 (Termingeschäftsgewinne): €X,XXX.XX
  Zeile 22 (Sonstige Verluste): €X,XXX.XX
  Zeile 23 (Aktienverluste): €X,XXX.XX
  Zeile 24 (Termingeschäftsverluste): €X,XXX.XX
  Zeile 41 (Ausländische Steuern): €X,XXX.XX
```

Separate summary of **conceptual net taxable capital income per category** (e.g., Stocks net, Derivatives net after internal offsetting and €20k cap consideration, Other Capital Income net) can be provided for user understanding, distinct from direct form line entries.

Aggregated WHT for Anlage KAP Zeile 41.

Warnings/inconsistencies.
- **Critical Error Report: EOY Quantity Mismatch:** Any discrepancies found during EOY Quantity Validation (Section 2.4) must be clearly reported, indicating the affected `Asset` and the differing quantities (calculated vs. reported).

#### Detailed PDF Report
- Lists individual `FinancialEvent` records *from the current tax year* leading to taxable outcomes and `RealizedGainLoss` records (from realizations in current tax year). All monetary values to be appropriately quantized.
- Details **Gross Amounts, Teilfreistellung calculations, and Net Taxable Amounts** (esp. for Investment Funds from current tax year events/realizations).
- Details impact of `CorporateActionEvent` types (from current tax year events).
- For `AssetCategory.PRIVATE_SALE_ASSET` transactions (from current tax year realizations), lists details mapping to Anlage SO structure, including non-taxable ones due to holding period.
- German headers, formatted for clarity.
- Include a section detailing any EOY quantity mismatches if detected.

#### Enhanced PDF Features
- **Component Breakdowns:** Detailed income component analysis with section references
- **Zeile 19 Transparency:** Always show calculation breakdown with all five components (even when 0 EUR)
- **Capital Repayments:** Comprehensive tables showing received repayments, cost basis adjustments, and excess amounts
- **Calculation Consistency:** Uses pre-calculated values from calculation engine for accuracy

#### Diagnostic Reports
- `main.py` currently includes functions (`_print_grouped_event_details`, `print_asset_positions`, `print_assets_by_category`) for diagnostic output of parsed and enriched data when run with `--group-by-type`.
- Modes for identifier conflicts (logged during merge) or position validation.
- **EOY Quantity Mismatch Details:** If EOY quantity mismatches occur, provide detailed diagnostic output comparing the FIFO ledger's final state against the positions end file for the problematic assets.

## 3. System Architecture (Conceptual Overview)

- **Input & Parsing Layer:** (`parsers` module) Reads IBKR CSVs. Employs alias map (`AssetResolver`) for consistent `Asset` identification. Converts string inputs to `Decimal` (adhering to Section 2.0.4). Generates unique `FinancialEvent` subtype objects; each logical financial event record from an input file results in a distinct `FinancialEvent` object internally (identified by a unique `event_id`), even if certain fields like `ibkr_transaction_id` are duplicated across different records in the source data (e.g., option exercise and resulting stock trade). `ParsingOrchestrator` manages this flow.

- **Data Enrichment Layer:** (`processing.enrichment`, `utils.currency_converter`, `utils.exchange_rate_provider`) Currency conversion (all monetary values to EUR as `Decimal` using `INTERNAL_CALCULATION_PRECISION`). `enrich_financial_events` populates EUR fields in `FinancialEvent` objects, quantizing only upon final field assignment if needed.

- **Classification Engine:** (`classification.asset_classifier`) Categorizes unique `Asset` objects (sets `Asset.asset_category`, `InvestmentFund.fund_type`), potentially involving interactive user input.

- **Calculation Engine:**
  - **FIFO & G/L Module:** Manages ledgers (per `Asset`), FIFO logic, option event processing (including linking and economic adjustments as per Section 2.4), corporate action processing. Generates `RealizedGainLoss` records with appropriate `RealizationType`. Uses `Decimal` with `INTERNAL_CALCULATION_PRECISION` for all financial math.
  - **Income & Teilfreistellung Module:** Calculates fund distributions, Vorabpauschale (generates `VorabpauschaleData`), Teilfreistellung, other income from `FinancialEvent` data (all from 2023 tax year events), using `INTERNAL_CALCULATION_PRECISION`.

- **Aggregation & Offsetting Layer (`LossOffsettingEngine`):**
  - Aggregates figures (from 2023 tax year events/realizations) into internal components (`stock_gains_gross`, `stock_losses_abs`, `derivative_gains_gross`, `derivative_losses_abs`, `kap_other_income_positive`, `kap_other_losses_abs`) and then calculates final figures for each `TaxReportingCategory` / form line (e.g., KAP Zeile 19-24 as per Sec 2.7), maintaining `INTERNAL_CALCULATION_PRECISION`.
  - Calculates conceptual net figures (after Teilfreistellung and Finanzamt-style offsetting) for internal summaries and user information, based on 2023 data.

- **Reporting Layer:** Generates console summaries and PDF reports, quantizing final figures to reporting precisions (e.g., `OUTPUT_PRECISION_AMOUNTS`).

- **Supporting Utilities:** (`utils` module) Exchange rate provider, configuration/cache persistence (`config.py` including `INTERNAL_CALCULATION_PRECISION`, `DECIMAL_ROUNDING_MODE`), type conversion utilities (`type_utils.py`).

- **Core Data Store:** A global `alias_map: Dict[str, Asset]` in `AssetResolver` serves as the central repository for unique `Asset` objects. `FinancialEvent` records and derived data (like `RealizedGainLoss`) are linked to these `Asset` objects via their `internal_asset_id`.

## 4. Data Structures (Key Elements based on Type Specification)

All monetary values and precise quantities (e.g., share counts, prices, costs, gains, losses) will be stored and processed using the `Decimal` type. Intermediate arithmetic operations on these `Decimal` values will adhere to the `INTERNAL_CALCULATION_PRECISION` and rounding rules defined in Section 2.0 to ensure accuracy before any final quantization for reporting.

### Core Asset Types (subclasses of `Asset` in `domain.assets`)

- `Asset`: Base class with `internal_asset_id`, `aliases`, `description`, `currency`, `asset_category` (`AssetCategory` enum), IBKR identifiers, SOY/EOY position data (`Decimal` quantities and values like `soy_quantity`, `soy_cost_basis_amount`, `eoy_quantity`, `eoy_market_price`, `eoy_position_value`). Each subclass correctly sets its `asset_category`.
- Specific types: `Stock`, `Bond`, `InvestmentFund` (with `fund_type` of `InvestmentFundType` enum, defaults to `InvestmentFundType.NONE`), `Option` (with `strike_price`, `expiry_date`, etc.), `Cfd`, `PrivateSaleAsset`, `CashBalance` (requires `currency` in constructor).
- `Derivative` as a base for `Option` and `Cfd`, containing `underlying_asset_internal_id`, `underlying_ibkr_conid`, `underlying_ibkr_symbol` and `multiplier`.

### Global Asset Map
`AssetResolver.alias_map: Dict[str, Asset]`

### FIFO Lots
Internal structures associated with an `Asset.internal_asset_id`.
- **`FifoLot` (for long positions):** Stores `acquisition_date` (YYYY-MM-DD string), `quantity` (`Decimal`), `unit_cost_basis_eur` (`Decimal`), `total_cost_basis_eur` (`Decimal`), and `source_transaction_id` (string, e.g., IBKR Transaction ID or a fallback identifier like "SOY_FALLBACK"). Includes internal consistency checks (e.g., between per-unit and total cost).
- **`ShortFifoLot` (for short positions):** Stores `opening_date` (YYYY-MM-DD string), `quantity_shorted` (`Decimal`, always positive), `unit_sale_proceeds_eur` (`Decimal`), `total_sale_proceeds_eur` (`Decimal`), and `source_transaction_id` (string). Also includes internal consistency checks.

### Core Event Types (subclasses of `FinancialEvent` in `domain.events`)

- `FinancialEvent`: Base class with `event_id`, `asset_internal_id`, `event_type` (`FinancialEventType` enum), `event_date` (YYYY-MM-DD string), monetary amounts (`Decimal` for `gross_amount_foreign_currency`, `gross_amount_eur`), IBKR details. Parent constructor requires `asset_internal_id`, `event_date`, and keyword args including `event_type`.
- Specific types: `TradeEvent` (with `quantity`, `price_foreign_currency`, `commission_foreign_currency` all `Decimal`, and an optional `related_option_event_id`), `CashFlowEvent` (with `source_country_code`), `WithholdingTaxEvent`, `CorporateActionEvent` (and its subtypes like `CorpActionSplitForward`, `CorpActionMergerCash`, `CorpActionMergerStock`, `CorpActionStockDividend` with their specific attributes like ratios and values as `Decimal`), `OptionLifecycleEvent` (and subtypes `OptionExerciseEvent`, `OptionAssignmentEvent`, `OptionExpirationWorthlessEvent`), `CurrencyConversionEvent` (with `from_amount`, `to_amount`, etc.), `FeeEvent`. Each subtype passes its specific `FinancialEventType` to the parent. Note: `OptionExerciseEvent` and `OptionAssignmentEvent` do not store a direct link to the stock trade event; the stock `TradeEvent` stores a `related_option_event_id`.

### Calculated Result Structures (defined in `domain.results`)

**`RealizedGainLoss`**: Contains detailed G/L calculation results. Key fields include:
- `originating_event_id` (UUID of the event triggering the G/L).
- `asset_internal_id` (UUID of the asset).
- `asset_category_at_realization` (`AssetCategory` at the time of realization).
- `acquisition_date` (YYYY-MM-DD string; for short positions, this is the open date).
- `realization_date` (YYYY-MM-DD string; e.g., sale date, expiration date, cover date).
- `realization_type` (`RealizationType` enum, specifies how the G/L occurred).
- `quantity_realized` (`Decimal`, absolute quantity realized, always positive).
- `unit_cost_basis_eur` (`Decimal`):
  - For long sales: Original cost per unit.
  - For short covers: Cover cost per unit.
  - For long option expiry worthless: Premium paid per unit.
  - For short option expiry worthless: `Decimal('0')`.
- `unit_realization_value_eur` (`Decimal`):
  - For long sales: Sale price per unit.
  - For short covers: Original short sale proceeds per unit.
  - For long option expiry worthless: `Decimal('0')`.
  - For short option expiry worthless: Premium received per unit.
- `total_cost_basis_eur` (`Decimal`, calculated as `quantity_realized` * `unit_cost_basis_eur`).
- `total_realization_value_eur` (`Decimal`, calculated as `quantity_realized` * `unit_realization_value_eur`).
- `gross_gain_loss_eur` (`Decimal`, calculated as `total_realization_value_eur` - `total_cost_basis_eur`).
- Also includes `holding_period_days`, `is_within_speculation_period`, `is_taxable_under_section_23`, `tax_reporting_category`, Teilfreistellung details (`fund_type_at_sale`, `teilfreistellung_rate_applied`, `teilfreistellung_amount_eur`, `net_gain_loss_after_teilfreistellung_eur`), and `is_stillhalter_income` (boolean).
- `__post_init__` performs type checks, sets `is_within_speculation_period`, and calculates `net_gain_loss_after_teilfreistellung_eur` if applicable.

**`VorabpauschaleData`**: Conceptual structure for Vorabpauschale calculation details (base return, rates, gross amount for form, Teilfreistellung, net taxable amount, all `Decimal`).

### Aggregated Declaration Figures (for Form Lines)

Summed income/G/L per `TaxReportingCategory`, representing direct form line entries. For KAP-INV, these are GROSS figures. For KAP, lines 20‑24 are specific gross components, and line 19 is foreign capital income after netting as described above.

### Conceptual Net Taxable Figures (For internal summary/user info)

Summed net income/G/L per tax pot after local calculations and Finanzamt-style offsetting.

## 5. Core Logic Flow (Conceptual for Declaration)

1. Initialize global `alias_map: Dict[str, Asset]` in `AssetResolver`.

2. Parse IBKR input data files (`ParsingOrchestrator.load_all_raw_data`). For each row:
   - Generate aliases. Resolve or create a unique `Asset` object via `AssetResolver.get_or_create_asset`. Update `Asset` attributes (including `description` based on `description_source_type`). `Decimal` values initialized per Section 2.0.4.

3. Process position files (`ParsingOrchestrator.process_positions`) to populate SOY/EOY data on `Asset` objects. **Crucially, `soy_quantity` and related SOY cost basis fields are recorded here. Per Section 2.1, `soy_quantity` from this file (or `Decimal(0)` if not listed for non-cash assets) is authoritative for starting quantities.**

4. Discover assets from transaction files (`ParsingOrchestrator.discover_assets_from_transactions`).

5. Link derivatives to their underlyings (`AssetResolver.link_derivatives`).

6. Finalize asset classifications (`ParsingOrchestrator.finalize_asset_classifications` using `AssetClassifier`), potentially involving interactive user input and type replacement via `AssetResolver.replace_asset_type`.

7. Create `FinancialEvent` subtype objects from raw data (`DomainEventFactory`), linking them to `Asset` objects via `internal_asset_id`. Convert string monetary/quantity values to `Decimal` (per Section 2.0.4).
   - **For `TradeEvent` creation from the Trades CSV (standard trades):** When processing rows that represent standard trades of financial instruments (not currency conversions, which become `CurrencyConversionEvent`s, and not option exercises/assignments which become specific `OptionLifecycleEvent` subtypes), the system **must** use the 'Buy/Sell' indicator (e.g., `BUY`, `SELL`) in conjunction with the 'Open/CloseIndicator' column (containing 'O' for Open or 'C' for Close) from the Trades CSV to accurately determine the `FinancialEventType`. The mapping is as follows:
     - `BUY` + 'O' (Open) -> `FinancialEventType.TRADE_BUY_LONG`
     - `BUY` + 'C' (Close) -> `FinancialEventType.TRADE_BUY_SHORT_COVER`
     - `SELL` + 'O' (Open) -> `FinancialEventType.TRADE_SELL_SHORT_OPEN`
     - `SELL` + 'C' (Close) -> `FinancialEventType.TRADE_SELL_LONG`
   - **For `OptionExerciseEvent` / `OptionAssignmentEvent` creation from the Trades CSV:** If a row in the Trades CSV corresponds to an option (`AssetClass` "OPT") and its `Notes/Codes` field indicates an exercise (e.g., 'Ex') or assignment (e.g., 'A'), typically with an `Open/CloseIndicator` of 'C', this row should be parsed into an `OptionExerciseEvent` or `OptionAssignmentEvent`. The corresponding stock transaction will be a separate row in the Trades CSV, parsed as a standard `TradeEvent`. The linking of these two events is described in Section 2.4.
   - The 'Open/CloseIndicator' is reported by IBKR as reliable and consistently present for trades of financial instruments (e.g., stocks, options, bonds). It is not applicable to currency pair transactions (e.g., symbol "EUR.USD" with IBKR asset class "CASH"), which are processed as `CurrencyConversionEvent`s.
   - The classification of standard trade direction **must not** rely on parsing the 'Notes/Codes' column of the Trades CSV, except for identifying specific event types like option exercises/assignments.
   - If the 'Open/CloseIndicator' is missing or contains an unexpected value for a transaction identified as a financial instrument trade (and not an exercise/assignment), this should be treated as a data inconsistency, logged prominently, and potentially flagged as an error requiring user attention.

8. **Process dividend rights matching** (`_process_dividend_rights_matching`): Match DI/ED pairs and re-link associated cash events to underlying stocks.

9. Sort all `FinancialEvent` objects chronologically (`ParsingOrchestrator.get_all_financial_events`). **Only events whose `event_date` falls within the current tax year are considered for further processing and reporting.** Enhanced tax year end date filtering excludes events after tax year. This filtering should ideally occur when events are first created or retrieved by `get_all_financial_events`, before enrichment and FIFO processing.
   - **Deterministic Sorting Requirement:** Event sorting must be stable and deterministic to ensure correct FIFO processing and calculation results. Each `FinancialEvent` object is unique due to its `event_id` (UUID). Parsers ensure one event object per logical entry from IBKR reports, even if identifiers like `ibkr_transaction_id` are shared across entries.
   - **Enhanced Chronological Ordering (v3.3.1):** The sorting algorithm prioritizes IBKR transaction IDs as the primary secondary sort key for same-date events, leveraging IBKR's sequential transaction ID assignment to maintain accurate chronological order critical for FIFO calculations.
   - **Primary Sort Key Component: `event_date`** (parsed to `datetime.date` object). Events with unparseable dates are flagged as errors.
   - **Secondary Sort Key Components (for Tie-breaking on the same `event_date`):** A tuple of subsequent keys is used, constructed based on the `FinancialEventType`. The `event.event_id` (UUID) is always the last element in this tuple to guarantee uniqueness and deterministic order.
     - **For `TradeEvent`, `OptionLifecycleEvent` subtypes (e.g., `OptionExerciseEvent`, `OptionAssignmentEvent`), and `CurrencyConversionEvent`:**
       - Sort Key Tuple: `(event.ibkr_transaction_id, asset.asset_category, event.event_id)`
       - `event.ibkr_transaction_id`: The Transaction ID from IBKR. A placeholder (e.g., empty string or `None` that sorts predictably) is used if not applicable.
       - `asset.asset_category`: The `AssetCategory` of the `Asset` linked to the `FinancialEvent` (via `event.asset_internal_id`). This is crucial for distinguishing events like an option exercise (e.g., `AssetCategory.OPTION`) from its resulting stock trade (e.g., `AssetCategory.STOCK`) when they share the same `event_date` and `ibkr_transaction_id`.
       - `event.event_id`: The unique UUID of the event, ensuring deterministic order if all prior fields are identical.
     - **For `CashFlowEvent` (e.g., dividends, interest), `WithholdingTaxEvent`, and `FeeEvent`:**
       - Sort Key Tuple: `(event.ibkr_transaction_id, asset.asset_category, event.gross_amount_foreign_currency, event.event_id)`
       - `event.ibkr_transaction_id` and `asset.asset_category` as above.
       - `event.gross_amount_foreign_currency`: The gross amount of the event. This helps differentiate multiple cash-related events that might share the same `ibkr_transaction_id` and `asset_category` on the same day.
       - `event.event_id`: The unique UUID of the event.
     - **For `CorporateActionEvent` subtypes:**
       - Sort Key Tuple: `(asset.ibkr_symbol, event.ca_action_id_ibkr, event.description, event.event_id)`
       - `asset.ibkr_symbol`: The IBKR symbol of the `Asset` associated with the corporate action.
       - `event.ca_action_id_ibkr`: The IBKR Action ID for the corporate action, if available.
       - `event.description`: The description of the corporate action event (e.g., from the `corpact*.csv`) can provide further differentiation for CAs on the same asset and date if `ca_action_id_ibkr` is missing or identical.
       - `event.event_id`: The unique UUID of the event.
   - **Null/None Handling:** Placeholders for missing optional key components (like `ibkr_transaction_id` or `ca_action_id_ibkr`) must be handled consistently to ensure correct sort order (e.g., `None` typically sorts before strings/numbers, or a specific sentinel value can be used).
   - **Ensuring Determinism:** The inclusion of `event.event_id` as the final component in each sort key tuple guarantees that the overall sorting order is strictly deterministic, as each `FinancialEvent` object has a unique `event_id`.

10. Enrich data (`enrich_financial_events`): Convert all financial amounts in the filtered (current tax year) `FinancialEvent` objects to EUR using `Decimal` arithmetic (with `INTERNAL_CALCULATION_PRECISION`) and ECB rates, storing results in EUR-specific fields (e.g., `gross_amount_eur`, `commission_eur`). Enhanced asset information formatting in log messages.

11. Perform Option-to-Stock Trade Linking (`perform_option_trade_linking`): Link `OptionExerciseEvent`/`OptionAssignmentEvent` objects (from the current tax year) to their corresponding stock `TradeEvent` objects by populating `TradeEvent.related_option_event_id`, as detailed in Section 2.4.

12. Initialize FIFO Ledgers for each `Asset`:
    - **Set initial quantities based on `Asset.soy_quantity` (as determined per Section 2.1).**
    - **Determine initial cost basis for these SOY lots according to the detailed logic in Section 2.4 (SOY Cost Basis Determination), using `INTERNAL_CALCULATION_PRECISION` for any calculations.**

13. Process sorted `FinancialEvent` objects (all confirmed to be within the current tax year) chronologically, updating FIFO ledgers (all calculations using `INTERNAL_CALCULATION_PRECISION`):
    - **`CAPITAL_REPAYMENT` events:** Process directly in calculation engine main loop to reduce cost basis using FifoLedger method and store excess amounts on events.
    - **`CorporateActionEvent` subtypes:** Adjust FIFO lots for the affected `Asset` or trigger taxable events (e.g., taxable stock dividend income contributes to `kap_other_income_positive`).
    - **`TradeEvent` (Sell/Cover types):** Calculate gross G/L (FIFO) for the relevant `Asset`. Generate `RealizedGainLoss` record with the appropriate `RealizationType`.
      - For `STOCK` sales/covers, G/L contributes to `stock_gains_gross` or `stock_losses_abs`.
      - For `BOND` sales/covers, G/L contributes to `kap_other_income_positive` or `kap_other_losses_abs`.
      - For `INVESTMENT_FUND` sales, calculate Teilfreistellung on G/L. The `net_gain_loss_after_teilfreistellung_eur` contributes to `fund_income_net_taxable` (for internal calculations only, not included in Anlage KAP Zeile 19).
      - For `PRIVATE_SALE_ASSET`, check holding period for taxability and G/L contributes to Anlage SO.
      - Stock trades linked to option events will have their economics adjusted by the option premium before FIFO processing (using the `related_option_event_id` link).
    - **`CashFlowEvent`:** Record gross income.
      - For fund distributions, calculate Teilfreistellung; the net taxable amount contributes to `fund_income_net_taxable` (for internal calculations only, not included in Anlage KAP Zeile 19).
      - For non-fund dividends, interest, Stückzinsen, these contribute to `kap_other_income_positive` or `kap_other_losses_abs` (after netting for Stückzinsen).
    - **`OptionLifecycleEvent` subtypes:** Process these events.
      - For exercises/assignments, this involves:
        1. Consuming the option lots from the option's FIFO ledger.
        2. Calculating the total EUR premium of the consumed option leg.
        3. Storing this premium in a temporary context (e.g., `pending_option_adjustments`) associated with the option event's ID, for later use by the linked stock `TradeEvent`.
        4. The linked stock `TradeEvent` (processed separately via `TradeProcessor`) will then retrieve this premium to adjust its own economic basis/proceeds (as detailed in Section 2.4).
      - For expirations or closing option trades not resulting in stock delivery, generate `RealizedGainLoss` for option premiums with the correct `RealizationType`. These G/L contribute to `derivative_gains_gross` or `derivative_losses_abs`.
    - Calculate gross and net Vorabpauschale (€0 for current tax year), creating `VorabpauschaleData`. The net Vorabpauschale contributes to `fund_income_net_taxable` (as €0).

14. Perform EOY Quantity Validation (as per Section 2.4): Compare calculated EOY quantities in FIFO ledgers against `Asset.eoy_quantity` (from `POSITIONS_END_FILE_PATH`) using a small numerical tolerance. Report any errors.

15. Aggregate figures into the internal components (`stock_gains_gross`, `stock_losses_abs`, `derivative_gains_gross`, `derivative_losses_abs`, `kap_other_income_positive`, `kap_other_losses_abs`) and then calculate the final values for each tax form line (Anlage KAP Zeilen 19-24, KAP-INV, SO) as per Section 2.7, maintaining `INTERNAL_CALCULATION_PRECISION`. This is handled by the `LossOffsettingEngine`. All aggregations are based on the current tax year events and realizations.

16. The `LossOffsettingEngine` will also calculate conceptual net figures for each tax pot (Stocks, Derivatives, Other Capital Income, Fund Income, §23 EStG) for internal summaries or user information, applying Finanzamt-style offsetting logic to these net figures, based on current tax year data.

17. Generate console and PDF reports, quantizing final figures to appropriate reporting precisions (e.g., `OUTPUT_PRECISION_AMOUNTS`) and **including any critical EOY quantity mismatch errors.**

## 6. Output Requirements

### Primary Output (Console Summary)

Figures for **direct entry onto current tax year forms**.
- Anlage KAP: Values for Zeile 19 (Ausländische Kapitalerträge nach Saldierung), Zeile 20 (Gewinne Aktien), Zeile 21 (Gewinne Termingeschäfte), Zeile 22 (Sonstige Verluste), Zeile 23 (Verluste Aktien), Zeile 24 (Verluste Termingeschäfte) as calculated per Section 2.7.
- Anlage KAP-INV: GROSS amounts for lines 4-8 (Distributions) and 14, 17, 20, 23, 26 (Gains/Losses).
- Anlage SO: Net G/L for Zeile 54.

Values will be `Decimal` formatted and quantized to 2 decimal places (e.g., using `OUTPUT_PRECISION_AMOUNTS`).

Examples:
```
Anlage KAP:
  Zeile 19 (Ausländische Kapitalerträge nach Saldierung): €X,XXX.XX
  Zeile 20 (Aktiengewinne brutto): €X,XXX.XX
  Zeile 21 (Termingeschäftsgewinne brutto): €X,XXX.XX
  Zeile 22 (Sonstige Verluste absolut): €X,XXX.XX
  Zeile 23 (Aktienverluste absolut): €X,XXX.XX
  Zeile 24 (Termingeschäftsverluste absolut): €X,XXX.XX
```

Separate summary of **conceptual net taxable income per category** (e.g., Stocks net, Derivatives net after Finanzamt-style offsetting including €20k cap consideration, Other Capital Income net after Finanzamt-style offsetting) can be provided for user understanding, distinct from direct form line entries.

### Supporting Output (PDF Details)

- Detailed transaction lists (`FinancialEvent` *from the current tax year* leading to taxable income/loss) and summaries (`RealizedGainLoss` from current tax year realizations, `VorabpauschaleData`). Values appropriately quantized. `RealizedGainLoss` details will reflect the updated field names and include `realization_type`.
- For investment funds (from current tax year events/realizations): Gross Amount, Fund Type, Teilfreistellung (Rate, Amount), Net Taxable Amount (all `Decimal`, quantized).
- For `AssetCategory.PRIVATE_SALE_ASSET` (from current tax year realizations): Individual transactions mapping to Anlage SO, including holding period and taxability status.
- Details of processed corporate actions (from current tax year events) and their impact.

Aggregated foreign WHT (from current tax year events) for Anlage KAP Zeile 41 (`Decimal` formatted and quantized).

Diagnostic messages (current implementation provides detailed event/asset printing via `--group-by-type` in `main.py`). Critical errors like EOY quantity mismatches must be prominent.

## 7. Assumptions & Limitations

- Assumes correctly formatted IBKR Flex Queries. Relies on ISIN, Conid, or specific Symbol for non-`CashBalance` `Asset` identification. If all are missing, a minimal asset object is created.
- **All investment fund shares are assumed to be acquired on or after January 1, 2018. No "Alt-Anteile" handling.**
- Accuracy of `InvestmentFund.fund_type` classification is crucial (supported by interactive classification and caching).
- Tool calculates figures; does **not** provide tax advice. Results must be verified.
- Calculation of *creditable* foreign WHT is **not performed**.
- Loss carry-forward/backward across tax years is **not calculated**.
- Final tax liability calculation (Sparer-Pauschbetrag, rates, Soli, KiSt) is **not performed**.
- **Corporate Action Handling Scope:**
  - Handles common CAs as defined by `FinancialEventType`: `CORP_SPLIT_FORWARD`, `CORP_MERGER_CASH`, `CORP_STOCK_DIVIDEND` (default taxable for foreign).
  - `CORP_MERGER_STOCK` is parsed as an event. While a `MergerStockProcessor` class may exist, the detailed FIFO lot conversion logic within `FifoLedger` (i.e., transforming lots of an old asset into lots of a new asset while preserving original acquisition dates and pro-rated cost bases) for tax-neutral stock-for-stock mergers is NOT YET IMPLEMENTED.
  - More complex CAs not explicitly typed are **not automatically handled**.
- Interprets IBKR 'Notes/Codes' based on common usage (e.g., for identifying Stückzinsen, WHT details from cash transaction descriptions, or for identifying option exercises/assignments as per Section 2.4 and Section 5, Step 7). However, for the primary classification of *standard trade direction* (opening/closing, long/short of a financial instrument trade itself, as opposed to an exercise/assignment event derived from an option trade line), the system relies primarily on the 'Open/CloseIndicator' column from the Trades CSV (as detailed in Section 5, Step 7).
- Stückzinsen are netted, and the net result contributes to `kap_other_income_positive` or `kap_other_losses_abs`.
- **Currency Conversion:** FX trading pair instruments (e.g., IBKR asset class "CASH", symbol "EUR.USD") are identified, and their trades directly generate `CurrencyConversionEvent` objects.
- **Fees:** Trade commissions are part of cost basis/proceeds. `FinancialEventType.FEE_TRANSACTION` can capture other fees, but their direct mapping to specific lines on Anlage KAP/KAP-INV (beyond potential Werbungskosten for Anlage SO if applicable) is not in scope for tax form line item generation.
- **Numerical Precision:** All financial calculations and storage of monetary values and quantities use the `Decimal` type with a high internal calculation precision as specified in Section 2.0. EUR values are quantized to specific output precisions (e.g., `OUTPUT_PRECISION_AMOUNTS`) only for final reporting.
- **Tax Year Scope:** The tool supports configurable tax years via TAX_YEAR setting in config.py. All financial events considered for calculations and reporting (e.g., dividends, interest, sales, corporate actions) must have an `event_date` or `realization_date` within the configured tax year period, inclusive.

## 8. Future Considerations

- Support for more complex corporate actions via new `CorporateActionEvent` subtypes (e.g., `CorpActionMergerStock` full FIFO lot conversion logic).
- User interface for configuration, input, review, and overrides.
- Calculation of creditable WHT.
- Calculation of loss carry-forwards.
- Integration with tax filing software APIs.
- Adaptation for future tax years/forms.

## 9. Appendix: Improved Variable Naming Conventions

### Configuration Variables
- `INTERNAL_CALCULATION_PRECISION` instead of `INTERNAL_WORKING_PRECISION`
- `OUTPUT_PRECISION_AMOUNTS` instead of `PRECISION_TOTAL_AMOUNTS`
- `OUTPUT_PRECISION_PER_SHARE` instead of `PRECISION_PER_SHARE_AMOUNTS`
- `IS_INTERACTIVE_CLASSIFICATION` instead of `INTERACTIVE_CLASSIFICATION`
- All file paths end with `_FILE_PATH` consistently

### Asset Position Fields
- `soy_quantity` instead of `initial_quantity_soy`
- `soy_cost_basis_amount` instead of `initial_cost_basis_money_soy`
- `soy_cost_basis_currency` instead of `initial_cost_basis_currency_soy`
- `eoy_market_price` instead of `eoy_mark_price`

### Financial Event Types (simplified)
- `FinancialEventType.CORP_SPLIT_FORWARD` instead of `CORP_ACTION_SPLIT_FORWARD`
- `FinancialEventType.CORP_MERGER_CASH` instead of `CORP_ACTION_MERGER_CASH`
- `FinancialEventType.CORP_MERGER_STOCK` instead of `CORP_ACTION_MERGER_STOCK`
- `FinancialEventType.CORP_STOCK_DIVIDEND` instead of `CORP_ACTION_STOCK_DIVIDEND`

### Realization Types (clearer semantics)
- `RealizationType.LONG_POSITION_SALE`
- `RealizationType.SHORT_POSITION_COVER`
- `RealizationType.CASH_MERGER_PROCEEDS`
- `RealizationType.OPTION_EXPIRED_LONG`
- `RealizationType.OPTION_EXPIRED_SHORT`
- `RealizationType.OPTION_PREMIUM_COLLECTED`

### Tax Calculation Components
- `stock_gains_gross` instead of `Internal_Stock_Gains_Gross`
- `stock_losses_abs` instead of `Internal_Stock_Losses_Gross_Abs`
- `derivative_gains_gross` instead of `Internal_Derivative_Gains_Gross`
- `derivative_losses_abs` instead of `Internal_Derivative_Losses_Gross_Abs`
- `kap_other_income_positive` instead of `Internal_O_Positive_Component_Sum`
- `kap_other_losses_abs` instead of `Internal_O_Loss_Component_Abs_Sum`
- `fund_income_net_taxable` (new, for clarity)

### Asset Categories
- `AssetCategory.PRIVATE_SALE_ASSET` instead of `SECTION_23_ESTG_ASSET`

### FIFO Lot Fields
- `unit_cost_basis_eur` instead of `cost_basis_eur_per_unit`
- `unit_sale_proceeds_eur` instead of `sale_proceeds_eur_per_unit`

### RealizedGainLoss Fields
- `unit_cost_basis_eur` instead of `cost_basis_eur_per_unit_realized`
- `unit_realization_value_eur` instead of `realization_value_eur_per_unit`
- `total_cost_basis_eur` instead of `total_cost_basis_eur_realized`
- `is_within_speculation_period` instead of `is_section_23_estg_relevant_transaction`
- `is_taxable_under_section_23` instead of `is_taxable_under_applicable_rules`
- `is_stillhalter_income` instead of `is_option_premium_gain`

### Corporate Action Fields
- `new_shares_per_existing_share` instead of `quantity_new_shares_received_per_old`

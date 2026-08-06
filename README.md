# IBKR German Tax Declaration Engine

**Automate the generation of figures for your German tax declaration (Anlage KAP, KAP-INV, SO) based on Interactive Brokers (IBKR) Flex Query CSV reports.**

## What is this?

German tax residents using Interactive Brokers (IBKR) often face significant challenges in accurately completing their tax declaration forms, especially Anlage KAP, Anlage KAP-INV, and Anlage SO. This tool aims to simplify this process by:

1.  Parsing your IBKR Flex Query CSV reports (with full historical data for FIFO cost basis).
2.  Identifying and classifying your assets (stocks, bonds, ETFs, options, CFDs, etc.).
3.  Performing currency conversions to EUR using daily ECB rates.
4.  Calculating capital gains/losses using the FIFO method (with `Decimal` precision).
5.  Handling corporate actions (splits, cash mergers, stock-for-stock mergers, taxable stock dividends).
6.  Processing option exercises, assignments, expirations, and cash settlements (index options).
7.  Tracking position flips (IBKR `C;O` / `O;C` indicators) with automatic FIFO lot splitting.
8.  Calculating income from dividends, interest, and fees within the tax year.
9.  Applying German Teilfreistellung (partial tax exemption) for investment funds.
10. Calculating Vorabpauschale for investment funds.
11. Tracking foreign currency positions and FX gains/losses under section 23 EStG.
12. Aggregating figures required for specific lines on the German tax forms.
13. Generating a console summary and a detailed PDF report for your records.

## Prerequisites

*   **Python 3.10 or higher.**
*   **`uv`** (Python package manager). Install from: https://docs.astral.sh/uv/getting-started/installation/
*   **IBKR Flex Query Reports (CSV format)** -- see [Setting Up IBKR Flex Queries](#setting-up-ibkr-flex-queries) below.

## Installation

1.  Clone the repository:
    ```bash
    git clone <repo-url>
    cd ibkr-german-tax-declaration-engine
    ```

2.  Install dependencies:
    ```bash
    uv sync
    ```

## Setting Up IBKR Flex Queries

Before you can use this tool, you need to create several Flex Queries in the IBKR Client Portal that export exactly the columns the engine expects. This section walks you through the full setup.

### Navigating to Flex Queries

1. Log into the [IBKR Client Portal](https://www.interactivebrokers.com/portal).
2. Navigate to **Performance & Reports > Flex Queries** (or **Menu > Reporting > Flex Queries**).
3. In the **Activity Flex Query** section, click the **+** icon to create a new query.

### General Configuration (same for all queries)

For each query, configure these general settings:

| Setting | Value |
|---------|-------|
| **Format** | CSV |
| **Include column headers** | Yes |
| **Date Format** | yyyy-MM-dd |
| **Time Format** | HH:mm:ss |
| **Date/Time Separator** | `;` (semicolon) |
| **Period** | Last 365 Calendar Days (overridden via API for specific years) |

### Query 1: Trades

Create an Activity Flex Query with only the **Trades** section enabled.

Select these fields (order matters for readability, but the parser matches by header name):

| # | Field to Select | Description |
|---|-----------------|-------------|
| 1 | ClientAccountID | Account identifier |
| 2 | CurrencyPrimary | Transaction currency |
| 3 | AssetClass | STK, OPT, BOND, CFD, CASH |
| 4 | SubCategory | COMMON, ETF, ADR, Corp, etc. |
| 5 | Symbol | Trading symbol |
| 6 | Description | Instrument description |
| 7 | ISIN | International Securities Identification Number |
| 8 | Strike | Option strike price |
| 9 | Expiry | Option/future expiration date |
| 10 | Put/Call | C or P for options |
| 11 | TradeDate | Date of the trade |
| 12 | Quantity | Units traded (positive=buy, negative=sell) |
| 13 | TradePrice | Price per unit |
| 14 | IBCommission | Commission charged (usually negative) |
| 15 | IBCommissionCurrency | Currency of commission |
| 16 | Buy/Sell | BUY or SELL |
| 17 | TransactionID | Unique transaction identifier |
| 18 | Notes/Codes | Trade codes (P=partial, A=assignment, Ex=exercise, Ep=expiration) |
| 19 | UnderlyingSymbol | Underlying for derivatives |
| 20 | Conid | Contract identifier |
| 21 | UnderlyingConid | Contract ID of the underlying |
| 22 | Multiplier | Contract multiplier (e.g. 100 for options) |
| 23 | **Open/CloseIndicator** | **O** (open) or **C** (close) -- **CRITICAL** |

**CRITICAL:** The `Open/CloseIndicator` field is essential for accurate trade classification. Without it, the engine cannot distinguish opening from closing trades. IBKR also uses composite values like `C;O` for position flips (a single trade that closes one position and opens the opposite direction), which the engine handles automatically.

### Query 2: Cash Transactions

Create an Activity Flex Query with only the **Cash Transactions** section enabled.

Select these fields:

| # | Field to Select | Description |
|---|-----------------|-------------|
| 1 | ClientAccountID | Account identifier |
| 2 | CurrencyPrimary | Transaction currency |
| 3 | AssetClass | Related asset class (STK, BOND, etc.) |
| 4 | SubCategory | Asset sub-category |
| 5 | Symbol | Related instrument symbol |
| 6 | Description | Transaction description (used for type determination) |
| 7 | SettleDate | Settlement date |
| 8 | Amount | Monetary amount (positive=inflow, negative=outflow) |
| 9 | Type | Transaction type (Dividends, Withholding Tax, etc.) |
| 10 | Conid | Contract identifier |
| 11 | UnderlyingConid | Underlying contract ID |
| 12 | ISIN | ISIN of related instrument |
| 13 | IssuerCountryCode | ISO country code of issuer (for WHT source) |
| 14 | TransactionID | Unique transaction identifier |

**Transaction Types to Include:** When configuring the Cash Transactions section, ensure **all** of the following transaction types are selected. Missing types cause currency EOY balance mismatches.

| Transaction Type | Why It's Needed |
|------------------|-----------------|
| Dividends | Dividend income |
| Withholding Tax | Foreign withholding tax |
| Broker Interest Received | Interest income |
| Broker Interest Paid | Interest expense |
| Payment In Lieu Of Dividends | Substitute dividend payments |
| Bond Interest Received | Bond coupon income |
| Bond Interest Paid | Stueckzinsen (accrued interest paid on purchase) |
| Other Fees | Miscellaneous fees |
| Deposits/Withdrawals | Cash movements |
| Commission Adjustments | Commission corrections |

### Query 3: Corporate Actions

Create an Activity Flex Query with only the **Corporate Actions** section enabled.

Select these fields:

| # | Field to Select | Description |
|---|-----------------|-------------|
| 1 | ClientAccountID | Account identifier |
| 2 | Symbol | Affected instrument symbol |
| 3 | Description | Corporate action description (parsed for merger ratios, etc.) |
| 4 | ISIN | ISIN of affected instrument |
| 5 | Report Date | Date the action was reported |
| 6 | Code | IBKR sub-type code |
| 7 | Type | Corporate action type code (FS=forward split, TC=merger, HI=stock dividend) |
| 8 | ActionID | Unique corporate action identifier |
| 9 | Conid | Contract identifier |
| 10 | UnderlyingConid | Underlying contract ID |
| 11 | UnderlyingSymbol | Underlying symbol |
| 12 | CurrencyPrimary | Currency of monetary amounts |
| 13 | Amount | Monetary amount |
| 14 | Proceeds | Cash proceeds |
| 15 | Value | Fair market value |
| 16 | Quantity | Shares involved (negative=dispose, positive=receive) |

### Query 4: Positions (used for both SOY and EOY)

Create an Activity Flex Query with only the **Open Positions** section enabled. A single query is used for both start-of-year and end-of-year snapshots -- the date is overridden via the API.

Select these fields:

| # | Field to Select | Description |
|---|-----------------|-------------|
| 1 | ClientAccountID | Account identifier |
| 2 | CurrencyPrimary | Position currency |
| 3 | AssetClass | STK, OPT, BOND, etc. |
| 4 | SubCategory | COMMON, ETF, ADR, etc. |
| 5 | Symbol | Instrument symbol |
| 6 | Description | Instrument description |
| 7 | ISIN | ISIN |
| 8 | Quantity | Units held (positive=long, negative=short) |
| 9 | PositionValue | Market value in position currency |
| 10 | MarkPrice | Mark-to-market price per unit |
| 11 | CostBasisMoney | Total cost basis in position currency |
| 12 | UnderlyingSymbol | Underlying for derivatives |
| 13 | Conid | Contract identifier |
| 14 | UnderlyingConid | Underlying contract ID |
| 15 | Multiplier | Contract multiplier |

### Query 5: Cash Balance

Create an Activity Flex Query with only the **Cash Report** section enabled.

Select these fields:

| # | Field to Select | Description |
|---|-----------------|-------------|
| 1 | ClientAccountID | Account identifier |
| 2 | CurrencyPrimary | Currency code (ISO 4217) |
| 3 | FromDate | Report period start date |
| 4 | ToDate | Report period end date |
| 5 | StartingCash | Cash balance at start of period |
| 6 | EndingCash | Cash balance at end of period |

### Query 6: Option Exercises, Assignments & Expirations (Optional)

This query is needed for **cash-settled index options** (e.g. SPX, ESTX50). If you don't trade index options, this query is not required.

Create an Activity Flex Query with only the **Option Exercises, Assignments and Expirations** section enabled.

Select these fields:

| # | Field to Select | Description |
|---|-----------------|-------------|
| 1 | ClientAccountID | Account identifier |
| 2 | CurrencyPrimary | Transaction currency |
| 3 | FXRateToBase | FX rate to base currency |
| 4 | AssetClass | OPT |
| 5 | Symbol | Option contract symbol |
| 6 | Description | Contract description |
| 7 | Conid | Contract identifier |
| 8 | ISIN | ISIN |
| 9 | UnderlyingConid | Underlying contract ID |
| 10 | UnderlyingSymbol | Underlying symbol |
| 11 | Multiplier | Contract multiplier |
| 12 | Strike | Strike price |
| 13 | Expiry | Expiration date |
| 14 | Put/Call | C or P |
| 15 | Date | Transaction date |
| 16 | Transaction Type | Assignment, Exercise, Expiration, or Cash Settlement |
| 17 | Quantity | Number of contracts |
| 18 | Trade Price | Transaction price |
| 19 | Proceeds | Cash proceeds |
| 20 | Comm/Tax | Commission and tax |
| 21 | Basis | Cost basis |
| 22 | RealizedPnl | Realized P&L |

### Enabling the Flex Web Service (for automated download)

To use the automated download feature (`--download`), you need to enable the Flex Web Service and generate an access token:

1. In the Client Portal, go to **Performance & Reports > Flex Queries > Flex Web Service Configuration**.
2. Check **Flex Web Service Status** to enable it.
3. Choose a token expiration duration from the **Should Expire After** dropdown.
4. Optionally restrict to a specific IP address.
5. Click **Generate New Token** and copy the token.
6. Store the token in one of these locations (checked in order):
   - Environment variable `IBKR_FLEX_TOKEN`
   - File `~/.ibkr_flex_token`
   - File `./ibkr_token` in the project directory

**Note:** Generating a new token invalidates the previous one. Tokens can expire (default: 6 hours unless configured longer).

### Recording Query IDs

After creating each query, IBKR assigns a numeric **Query ID**. You can find it in the Flex Queries list. Enter these IDs in `src/config.py`:

```python
FLEX_QUERY_IDS: dict[str, int | None] = {
    "trades": 123456,            # Your Trades query ID
    "cash_transactions": 123457, # Your Cash Transactions query ID
    "positions": 123458,         # Your Positions query ID (used for both SOY/EOY)
    "corporate_actions": 123459, # Your Corporate Actions query ID
    "cash_balance": 123460,      # Your Cash Balance query ID
    "options_eae": None,         # Your Options EAE query ID (or None if not needed)
}
```

## Preparing Input Data

Place your IBKR Flex Query CSV files in the `data_import/` directory using this naming scheme:

```
Trades-{YYYY}.csv               # One file per year
Cash_Transactions-{YYYY}.csv    # One file per year
Corporate_Actions-{YYYY}.csv    # One file per year
Cash_Balance-{YYYY}.csv         # One file per year
Options_EAE-{YYYY}.csv          # One file per year (optional, for cash-settled index options)
Positions-{YYYY}-SoY.csv        # Start-of-year positions snapshot
Positions-{YYYY}-EoY.csv        # End-of-year positions snapshot
```

The `data_import/` directory is **read-only** and never modified by the application.

**History concatenation:** Transaction files (Trades, Cash_Transactions, Corporate_Actions, Options_EAE) for all available years up to the tax year are automatically concatenated to provide full FIFO history. Position and Cash Balance files are used only for the selected tax year.

### Automatic Download

You can download data directly from IBKR's Flex Web Service if you have configured your Flex Query IDs and access token:

```bash
# Download and process
uv run python -m src.main --tax-year 2024 --download

# Download only (no processing)
uv run python -m src.main --tax-year 2024 --download-only
```

The download uses a two-step API workflow:
1. **SendRequest** -- triggers report generation, returns a reference code.
2. **GetStatement** -- polls with the reference code until the CSV is ready.

Date ranges are overridden per query to cover the exact calendar year.

**Important limitation:** The IBKR Flex Web Service API only retains approximately the last 2 calendar years of data. Requests for older years return error 1003 ("Statement is not available"). This means the automatic download can only fetch recent data -- it cannot retrieve the full trading history needed for accurate FIFO cost basis calculations. For older years, use the [Client Portal download](#client-portal-download-for-older-years) below, which has no such limit.

### Client Portal Download (For Older Years)

The Client Portal runs the same Flex Queries over any date range, with no
two-year limit. `src/web_portal/` drives it in a real browser, so older years
can be fetched without clicking through the portal by hand.

```bash
uv sync --extra web                                              # one-off: installs Playwright
uv run python -m src.web_portal.download --years 2021-2023
```

A browser window opens. **You log in yourself, including two-factor.** The tool
never asks for, stores, or records your password; the browser profile it uses
has Chrome's password manager disabled so the browser cannot save it either.
Your username can be remembered with `--username`, which writes it to the
gitignored `private/portal_username`.

Once the portal answers as a logged-in user, each query runs for each requested
year. The portal answers small reports immediately and queues larger ones for
batch processing; the downloader waits for those instead of needing a manual
page refresh. Results are written to `data_import/` under the naming scheme
below. **Existing files are never replaced** unless you pass `--overwrite`.

Useful options:

| Option | Effect |
|--------|--------|
| `--years 2021 2023` or `--years 2021-2023` | Which years to fetch |
| `--queries trades positions` | Only some reports (default: all configured) |
| `--query-name-prefix MyTax` | Resolve query IDs from the portal by name instead of `FLEX_QUERY_IDS` |
| `--overwrite` | Replace files already in `data_import/` |
| `--timeout-seconds` | How long to wait for one report (default 900). A report that outlives it keeps generating; re-run to collect it |
| `--reset-profile` | Delete the saved browser profile and log in fresh. Use if the portal keeps saying "Your Session Has Expired" |

**Positions snapshot dates.** `Positions-{YYYY}-SoY.csv` is fetched as of the
**first trading day** of the year and `Positions-{YYYY}-EoY.csv` as of the last
(31 December, or the Friday before if it falls on a weekend).

The start-of-year file supplies the price that drives the Vorabpauschale, and
which day that price comes from is a legal question, not a convenience: it is
recorded as open question Q12 in
[`reference/research/open-legal-questions.md`](reference/research/open-legal-questions.md)
and decided against `GT-INVSTG-010` in
[`docs/legal-implementation-map.md`](docs/legal-implementation-map.md). Asking
the portal for 1 January returns the *preceding* 31 December close instead,
which is the reading that was not chosen — so if you have start-of-year files
exported by hand for 1 January, they carry different prices from the ones this
tool fetches, and re-fetching them with `--overwrite` is what makes the corpus
consistent. Quantities are unaffected either way, so the end-of-year
reconciliation will not flag the difference.

**Resolving queries by name.** If you gave your six Flex Queries a common
naming prefix — `MyTax Trades`, `MyTax_Cash_Transactions`, and so on — set
`FLEX_QUERY_NAME_PREFIX` in `src/config.py` and the downloader looks the IDs up
in the portal. Case and separators do not matter. This survives recreating a
query, which changes its numeric ID but not its name; a stale ID in
`FLEX_QUERY_IDS` would otherwise download the wrong report shape without
complaining.

**If the portal changes.** `python -m src.web_portal.discover` opens a recorded
session: you drive the portal by hand while it logs what it does, redacted, to
the gitignored `private/portal_discovery/`. That recording is how the protocol
above was established, and re-running it is how to re-establish it.

### Manual Download (Fallback)

The same thing by hand, if you prefer it or the automated path breaks.

**Step-by-step:**

1. Log into the [IBKR Client Portal](https://www.interactivebrokers.com/portal).
2. Navigate to **Performance & Reports > Flex Queries**.
3. For each Flex Query you created (Trades, Cash Transactions, etc.), click the **Run** (arrow) icon.
4. Set the **Period** to **Custom Date Range** and enter the desired calendar year (e.g., 2021-01-01 to 2021-12-31).
5. Click **Run** and download the resulting CSV file.
6. Rename the downloaded file to match the naming scheme and place it in `data_import/`:

   | Query | Filename |
   |-------|----------|
   | Trades | `Trades-{YYYY}.csv` |
   | Cash Transactions | `Cash_Transactions-{YYYY}.csv` |
   | Corporate Actions | `Corporate_Actions-{YYYY}.csv` |
   | Cash Balance | `Cash_Balance-{YYYY}.csv` |
   | Options EAE | `Options_EAE-{YYYY}.csv` |
   | Positions (Jan 1) | `Positions-{YYYY}-SoY.csv` |
   | Positions (Dec 31) | `Positions-{YYYY}-EoY.csv` |

7. For **Positions**, run the same query twice per year: once with the date set to **January 1** (SoY) and once with **December 31** (EoY).
8. Repeat for each historical year back to your first year of trading at IBKR.

**Example:** If your tax year is 2025 and you started trading in 2021, you need files for 2021-2025. The Flex Web Service download may cover 2024-2025; 2021-2023 come from the Client Portal.

## Configuration

Edit `src/config.py` before running:

*   `TAX_YEAR` -- Default year to process (overridable with `--tax-year`).
*   `TAXPAYER_NAME`, `ACCOUNT_ID` -- For PDF reports.
*   `IS_INTERACTIVE_CLASSIFICATION` -- Enable/disable interactive asset classification.
*   `FLEX_QUERY_IDS` -- IBKR Flex Query IDs for automatic download.
*   `APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING` -- Whether to apply the 20,000 EUR cap on derivative losses in the conceptual summary (form reporting is always un-capped).

## Running the Engine

```bash
# Basic run (uses TAX_YEAR from config.py)
uv run python -m src.main

# Specify tax year
uv run python -m src.main --tax-year 2024

# Interactive asset classification
uv run python -m src.main --interactive

# Generate tax declaration report and PDF
uv run python -m src.main --report-tax-declaration

# Custom PDF output
uv run python -m src.main --report-tax-declaration --pdf-output-file my_report.pdf

# Diagnostic output
uv run python -m src.main --group-by-type

# View all CLI options
uv run python -m src.main --help
```

### Ledger Validation

Validate SOY/EOY consistency across all available years:

```bash
uv run python validate_ledgers.py
uv run python validate_ledgers.py --year 2024
uv run python validate_ledgers.py --verbose --quiet
```

**A securities EoY mismatch aborts the run.** The start-of-year quantity is taken from the
`Positions-{YYYY}-SoY.csv` snapshot, not reconstructed from earlier years, so the end-of-year
quantity is determined by that snapshot plus the tax year's own events and has exactly one
correct answer. If the engine's answer differs from the broker's, an event is missing or was
processed incorrectly — an absent trade or corporate action, an option exercise that was not
linked to its stock leg, or one instrument resolved under two identifiers. At least one
disposal is then matched against the wrong lots, which makes the reported gain wrong and not
just the quantity, so the engine refuses to emit figures. The error names every affected
position.

Note what this does **not** mean: a trade history that does not reach far enough back cannot
cause it. Missing earlier years affect the cost basis and acquisition dates the engine derives
for carried-in positions, never the running quantity. If you hit this, look for a missing or
mis-processed event in the tax year itself.

Cash-balance (currency) divergences are **not** fatal — their usual causes are the date range
of the cash-balance export or transaction types missing from the Cash Transactions query (see
the note above). They are reported as `CURRENCY_EOY_MISMATCH` in the console and PDF.

## Output

1.  **Console:** Processing logs and, with `--report-tax-declaration`, a summary of figures for direct tax form entry.
2.  **PDF Report:** Detailed report with taxpayer info, Anlage KAP/KAP-INV/SO summaries, income events, realized gains/losses, and corporate actions.
3.  **Cache Files:** `cache/user_classifications.json` and `cache/ecb_exchange_rates.json`.

## German Tax Form Mapping

*   **Anlage KAP:** capital income, gains and losses from stocks and derivatives, and creditable
    foreign withholding tax.
*   **Anlage KAP-INV:** investment fund distributions, Vorabpauschale and disposal gains, entered
    gross (before Teilfreistellung).
*   **Anlage SO:** private sales under § 23 EStG disposed of within the one-year period.

**Line numbers are deliberately not listed here.** They are legal facts, they are year-specific,
and CLAUDE.md permits them in exactly one place: `reference/`. See
[`reference/tax-forms/`](reference/tax-forms/) for the per-year line mappings with their sources,
and [`docs/legal-implementation-map.md`](docs/legal-implementation-map.md) for which of them this
engine actually produces — several it does not.

## Architecture

### Core Processing Flow

1. **Data Preparation** (`src/data_preparation.py`) -- Resolves and concatenates files from `data_import/` by tax year.
2. **Parsing Layer** (`src/parsers/`) -- Parses IBKR CSV files, builds asset alias map via `AssetResolver`.
3. **Domain Layer** (`src/domain/`) -- Data structures for assets, events, and calculation results.
4. **Enrichment** (`src/processing/enrichment.py`) -- Currency conversion to EUR using ECB rates.
5. **Classification** (`src/classification/`) -- Categorizes assets (STOCK, INVESTMENT_FUND, OPTION, etc.).
6. **Calculation Engine** (`src/engine/`) -- FIFO ledger management, gain/loss calculations, corporate action processing.
7. **Loss Offsetting** (`src/engine/loss_offsetting.py`) -- Aggregates figures for tax form lines.
8. **Reporting** (`src/reporting/`) -- Console and PDF report generation.

### Key Modules

- `src/identification/asset_resolver.py` -- Global alias map maintaining unique Asset objects across all input files.
- `src/engine/fifo_manager.py` -- FIFO lot tracking for long/short positions, including drain/receive for stock mergers and position flip splitting.
- `src/engine/calculation_engine.py` -- Main calculation orchestration with three-pass historical replay for mergers.
- `src/engine/event_processors/` -- Processors for trades, corporate actions, options, and currency conversions.
- `src/processing/option_trade_linker.py` -- Links option exercises/assignments to stock trades.
- `src/pipeline_runner.py` -- Orchestrates the full processing pipeline.

### Domain Model

- **Assets** (`domain/assets.py`): `Asset`, `Stock`, `Bond`, `InvestmentFund`, `Option`, `Cfd`, `PrivateSaleAsset`, `CashBalance`.
- **Events** (`domain/events.py`): `FinancialEvent` base class with subtypes `TradeEvent`, `CashFlowEvent`, `CorporateActionEvent`, `OptionLifecycleEvent`, `OptionCashSettlementEvent`, `CurrencyConversionEvent`, etc.
- **Results** (`domain/results.py`): `RealizedGainLoss`, `VorabpauschaleData`.
- **Enums** (`domain/enums.py`): `AssetCategory`, `FinancialEventType`, `RealizationType`, `TaxReportingCategory`.

## Running Tests

```bash
uv run pytest
uv run pytest -v
uv run pytest tests/test_fifo_groups.py -v          # FIFO tests (Groups 1-5)
uv run pytest tests/test_group6_loss_offsetting.py -v # Loss offsetting
uv run pytest tests/test_stock_merger_fifo.py -v      # Stock merger FIFO lot transfer
uv run pytest tests/test_options_lifecycle.py -v      # Options lifecycle
uv run pytest tests/test_group7_currency_fifo.py -v   # Currency FIFO
```

## Known Limitations

*   **IBKR API history:** The Flex Web Service API only retains ~2 calendar years of data. Older years come from the Client Portal instead, either with the browser downloader or by hand (see [Client Portal Download](#client-portal-download-for-older-years)).
*   **No "Alt-Anteile":** Assumes all investment fund shares were acquired on or after January 1, 2018.
*   **Foreign WHT:** Aggregates WHT paid (Anlage KAP Zeile 41) but does not calculate creditable WHT.
*   **No loss carry-forward/backward:** Calculations are limited to the specified tax year.
*   **No final tax liability:** Does not calculate Sparer-Pauschbetrag, solidarity surcharge, or church tax.
*   **Not tax advice:** The output is for informational purposes only. Always verify results and consult a qualified tax advisor.

## Disclaimer

This software is provided "as is," without warranty of any kind, express or implied. The authors and contributors are not liable for any claim, damages, or other liability arising from the use of this software. The output is intended for informational purposes only and does not constitute tax advice.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

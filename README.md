# IBKR German Tax Declaration Engine

**Automate the generation of figures for your German tax declaration (Anlage KAP, KAP-INV, SO) based on Interactive Brokers (IBKR) Flex Query CSV reports.**

## What is this?

German tax residents using Interactive Brokers (IBKR) often face significant challenges in accurately completing their tax declaration forms, especially Anlage KAP, Anlage KAP-INV, and Anlage SO. This tool aims to simplify this process by:

1.  Parsing your IBKR Flex Query CSV reports (with full historical data for FIFO cost basis).
2.  Identifying and classifying your assets (stocks, bonds, ETFs, options, etc.).
3.  Performing currency conversions to EUR using daily ECB rates.
4.  Calculating capital gains/losses using the FIFO method (with `Decimal` precision).
5.  Handling corporate actions (splits, cash mergers, taxable stock dividends).
6.  Processing option exercises, assignments, and expirations.
7.  Calculating income from dividends, interest, and fees within the tax year.
8.  Applying German Teilfreistellung (partial tax exemption) for investment funds.
9.  Calculating Vorabpauschale for investment funds.
10. Aggregating figures required for specific lines on the German tax forms.
11. Generating a console summary and a detailed PDF report for your records.

## Prerequisites

*   **Python 3.10 or higher.**
*   **`uv`** (Python package manager). Install from: https://docs.astral.sh/uv/getting-started/installation/
*   **IBKR Flex Query Reports (CSV format).**

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

## Preparing Input Data

Place your IBKR Flex Query CSV files in the `data_import/` directory using this naming scheme:

```
Trades-{YYYY}.csv               # One file per year
Cash_Transactions-{YYYY}.csv    # One file per year
Corporate_Actions-{YYYY}.csv    # One file per year
Cash_Balance-{YYYY}.csv         # One file per year
Positions-{YYYY}-SoY.csv        # Start-of-year positions snapshot
Positions-{YYYY}-EoY.csv        # End-of-year positions snapshot
```

The `data_import/` directory is **read-only** and never modified by the application. Transaction files (Trades, Cash_Transactions, Corporate_Actions) for all available years up to the tax year are automatically concatenated to provide full FIFO history.

**Critical:** The Trades file **must** include the `Open/CloseIndicator` column (`O`/`C`) for accurate trade classification. See `input_data_spec.md` for detailed column specifications.

### Automatic Download

You can download data directly from IBKR Flex Web Service if you configure your Flex Query IDs in `src/config.py` and provide your IBKR Flex token:

```bash
# Download and process
uv run python -m src.main --tax-year 2024 --download

# Download only (no processing)
uv run python -m src.main --tax-year 2024 --download-only
```

The token is resolved from: env var `IBKR_FLEX_TOKEN` > `~/.ibkr_flex_token` > `./ibkr_token`.

## Configuration

Edit `src/config.py` before running:

*   `TAX_YEAR` — Default year to process (overridable with `--tax-year`).
*   `TAXPAYER_NAME`, `ACCOUNT_ID` — For PDF reports.
*   `IS_INTERACTIVE_CLASSIFICATION` — Enable/disable interactive asset classification.
*   `FLEX_QUERY_IDS` — IBKR Flex Query IDs for automatic download.

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

## Output

1.  **Console:** Processing logs and, with `--report-tax-declaration`, a summary of figures for direct tax form entry.
2.  **PDF Report:** Detailed report with taxpayer info, Anlage KAP/KAP-INV/SO summaries, income events, realized gains/losses, and corporate actions.
3.  **Cache Files:** `cache/user_classifications.json` and `cache/ecb_exchange_rates.json`.

## German Tax Form Mapping

*   **Anlage KAP:** Stock/derivative gains/losses (Zeilen 19-24), foreign WHT (Zeile 41).
*   **Anlage KAP-INV:** Investment fund distributions and gains (GROSS figures, Zeilen 4-8, 14, 17, 20, 23, 26).
*   **Anlage SO:** Private sales under §23 EStG (holding period < 1 year).

## Running Tests

```bash
uv run pytest
uv run pytest -v
uv run pytest tests/test_fifo_groups.py -v
```

## Known Limitations

*   **Stock-for-stock mergers:** FIFO lot transfer for tax-neutral stock mergers is not yet implemented (see `docs/TODO_stock_merger_fifo.md`).
*   **No "Alt-Anteile":** Assumes all investment fund shares were acquired on or after January 1, 2018.
*   **Foreign WHT:** Aggregates WHT paid (Anlage KAP Zeile 41) but does not calculate creditable WHT.
*   **No loss carry-forward/backward:** Calculations are limited to the specified tax year.
*   **No final tax liability:** Does not calculate Sparer-Pauschbetrag, solidarity surcharge, or church tax.
*   **Not tax advice:** The output is for informational purposes only. Always verify results and consult a qualified tax advisor.

## Disclaimer

This software is provided "as is," without warranty of any kind, express or implied. The authors and contributors are not liable for any claim, damages, or other liability arising from the use of this software. The output is intended for informational purposes only and does not constitute tax advice.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

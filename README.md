# IBKR German Tax Declaration Engine (v3.2.3) 🇩🇪💰

**Automate the generation of figures for your German tax declaration (Anlage KAP, KAP-INV, SO) based on Interactive Brokers (IBKR) Flex Query reports.**

## What is this?

German tax residents using Interactive Brokers (IBKR) often face significant challenges in accurately completing their tax declaration forms, especially Anlage KAP, Anlage KAP-INV, and Anlage SO. This tool aims to simplify this process by:

1.  Parsing your IBKR Flex Query CSV reports (including historical data for SOY cost basis if needed).
2.  Identifying and classifying your assets (stocks, bonds, ETFs, options, etc.).
3.  Performing currency conversions to EUR using daily ECB rates.
4.  Calculating capital gains/losses using the FIFO method (with `Decimal` precision), considering the SOY state.
5.  Handling common corporate actions (splits, cash mergers, taxable stock dividends).
6.  Calculating income from dividends, interest, and Stückzinsen occurring within the `TAX_YEAR`.
7.  Applying German Teilfreistellung (partial tax exemption) for investment funds.
8.  Calculating Vorabpauschale (e.g., this resulted in €0 for the 2023 tax year, but the logic is present for other years).
9.  Aggregating figures required for specific lines on the German tax forms relevant to the configured `TAX_YEAR`.
10. Generating a console summary and a detailed PDF report for your records.

The goal is to provide accurate, directly usable figures to significantly reduce manual effort and complexity.

## Key Features

*   **Direct Tax Form Figures:** Generates values for relevant lines in:
    *   **Anlage KAP**
    *   **Anlage KAP-INV** (Gross figures for distributions and G/L from funds)
    *   **Anlage SO** (for §23 EStG private sales)
*   **FIFO Calculations:** Implements First-In, First-Out accounting for gains/losses in EUR, properly initialized with Start-of-Year data.
*   **Corporate Action Handling:** Processes forward splits, cash mergers, and taxable foreign stock dividends, adjusting FIFO lots.
*   **Option Processing:** Handles option exercises, assignments, and worthless expirations, including adjusting stock trade economics for premiums.
*   **Investment Fund Taxation:**
    *   Classifies funds (Aktienfonds, Mischfonds, etc.).
    *   Calculates Teilfreistellung.
    *   Calculates Vorabpauschale (e.g., resulted in €0 for 2023).
    *   Reports **GROSS** figures for Anlage KAP-INV as required.
*   **Currency Conversion:** Uses daily ECB exchange rates (cached) and `Decimal` for high precision.
*   **Asset Classification:** Interactive or cache-based classification of financial assets.
*   **EOY Validation:** Compares calculated end-of-year positions against your EOY IBKR report for the configured `TAX_YEAR`.
*   **Detailed Reporting:**
    *   Console summary for quick overview and direct form entry.
    *   PDF report with detailed transactions (from the `TAX_YEAR`), G/L, income, and Teilfreistellung calculations.
*   **Numerical Precision:** All financial calculations use Python's `Decimal` type with high internal precision (`INTERNAL_CALCULATION_PRECISION`) to minimize rounding errors.

## Prerequisites

*   **Python 3.8 or higher.**
*   **`pip`** (Python package installer).
*   **IBKR Flex Query Reports (CSV format):** You will need reports covering your activity for the `TAX_YEAR` you are processing, *and potentially historical trade data if you want the system to simulate SOY cost basis rather than relying solely on the SOY positions file for cost basis.*
    1.  **Trades:** Your trade activity. *Crucially, this file **MUST** include the `Open/CloseIndicator` column for accurate trade classification.*
    2.  **Cash Transactions:** Dividends, interest, withholding tax, fees, etc.
    3.  **Positions (Start of Year):** Your portfolio holdings at the beginning of the `TAX_YEAR`. This file is key for establishing SOY quantities and can provide fallback SOY cost basis.
    4.  **Positions (End of Year):** Your portfolio holdings at the end of the `TAX_YEAR`.
    5.  **Corporate Actions:** Details of splits, mergers, stock dividends, etc.

    Refer to `input_data_spec.md` for detailed column specifications.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/ibkr-german-tax-engine.git # Replace with your repo URL
    cd ibkr-german-tax-engine
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Before running, you need to configure the application:

1.  **Edit `src/config.py`:**
    *   **Crucial:** Update `TAXPAYER_NAME` and `ACCOUNT_ID` with your information. These are used in the PDF report.
    *   **Crucial:** Set `TAX_YEAR` to the calendar year you are processing (e.g., `2023`, `2024`).
    *   Adjust file paths (`TRADES_FILE_PATH`, `CASH_TRANSACTIONS_FILE_PATH`, etc.) if your input files are not in the default `data/` directory or have different names. These can also be overridden by CLI arguments.
    *   Set `IS_INTERACTIVE_CLASSIFICATION` to `True` for your first run to classify unknown assets. Set to `False` to run non-interactively using cached classifications.
    *   Review other settings like `INTERNAL_CALCULATION_PRECISION` if needed (defaults are generally fine).

2.  **Cache Directories:** Ensure `cache/` directory exists in the project root (or where `CLASSIFICATION_CACHE_FILE_PATH` and `ECB_RATES_CACHE_FILE_PATH` point). The application will create files here.

## Preparing Input Data

1.  **Generate your IBKR Flex Query reports** in CSV format. For the current `TAX_YEAR`, ensure you have all relevant reports. For establishing the Start-of-Year cost basis through historical simulation, ensure your Trades and Corporate Actions reports extend back as needed.
2.  **Ensure filenames match** those in `src/config.py` or provide paths via CLI arguments. The default location is the `data/` directory in the project root.
3.  **Verify CSV Format:**
    *   Files should be `utf-8-sig` encoded.
    *   Column headers should match the specifications in `input_data_spec.md`.
    *   **Critical for `trades.csv`:** Ensure the `Open/CloseIndicator` column is present and contains 'O' or 'C' for trades of financial instruments. This is vital for correct classification of trades (e.g., distinguishing a buy-to-open from a buy-to-cover).
4.  Place your CSV files in the configured `data/` directory (or the paths you'll specify via CLI).

## Running the Engine

Navigate to the project's root directory in your terminal (where `src/` is located).

**Basic run (using defaults from `config.py`):**
```bash
python src/main.py
```

**Common options:**

*   **Enable interactive classification (overrides config):**
    ```bash
    python src/main.py --interactive
    ```
*   **Disable interactive classification (overrides config):**
    ```bash
    python src/main.py --no-interactive
    ```
*   **Generate console tax summary and PDF report:**
    ```bash
    python src/main.py --report-tax-declaration
    ```
    (This will also create `tax_report_<TAX_YEAR>.pdf` by default, e.g., `tax_report_2023.pdf` if `TAX_YEAR` is 2023)

*   **Specify a custom PDF output file name:**
    ```bash
    python src/main.py --report-tax-declaration --pdf-output-file my_tax_details_<TAX_YEAR>.pdf
    ```

*   **Specify input file paths (example for trades file):**
    ```bash
    python src/main.py --trades path/to/your/trades_report.csv
    ```
    (Similar arguments exist for `--cash`, `--pos_start`, `--pos_end`, `--corp_actions`)

*   **View all available options:**
    ```bash
    python src/main.py --help
    ```

## Output

The engine produces:

1.  **Console Output:**
    *   Logging information about the processing steps.
    *   If requested (`--report-tax-declaration`), a summary of figures for direct entry into German tax forms for the configured `TAX_YEAR`.
    *   If requested (`--group-by-type`, `--count-objects`), diagnostic information.
2.  **PDF Report:**
    *   If requested (`--report-tax-declaration` or if `--pdf-output-file` is specified), a detailed PDF report is generated for the configured `TAX_YEAR`.
    *   This includes taxpayer information, summaries for Anlage KAP/KAP-INV/SO, detailed lists of income events (from the `TAX_YEAR`), realized gains/losses (from the `TAX_YEAR`), corporate actions (from the `TAX_YEAR`), and EOY mismatch warnings if any.
3.  **Cache Files:**
    *   `cache/user_classifications.json`: Stores your asset classifications to avoid re-classifying known assets on subsequent runs.
    *   `cache/ecb_exchange_rates.json`: Caches downloaded ECB exchange rates.

## Important Limitations & Scope

*   **No "Alt-Anteile":** This tool assumes all investment fund shares were acquired on or after January 1, 2018.
*   **Not Tax Advice:** The output is for informational purposes and to assist in preparing your tax declaration. It is **not** professional tax advice. Always verify the results and consult a qualified tax advisor.
*   **Foreign Withholding Tax (WHT):** The tool aggregates WHT paid (for Anlage KAP Zeile 41) but **does not** calculate *creditable* WHT.
*   **No Loss Carry-Forward/Backward:** Calculations are limited to the specified `TAX_YEAR`.
*   **No Final Tax Liability:** Does not calculate Sparer-Pauschbetrag, final tax owed, solidarity surcharge, or church tax.
*   **Corporate Actions:** Handles common types (Forward Splits, Cash Mergers, taxable Stock Dividends for foreign stocks). The detailed FIFO lot conversion logic for tax-neutral stock-for-stock mergers (`CORP_MERGER_STOCK`) is **NOT YET FULLY IMPLEMENTED** within the `FifoLedger`. Complex or rare corporate actions may not be handled correctly.
*   **Data Accuracy:** The accuracy of the output depends entirely on the accuracy and completeness of your IBKR Flex Query reports. Ensure all required columns are present and correctly formatted, especially `Open/CloseIndicator` in the trades file.
*   **FX Trading Pairs:** Trades of FX pairs (e.g., EUR.USD) are processed as `CurrencyConversionEvent`s and do not undergo FIFO G/L calculation themselves.
*   **Fees:** Trade commissions are incorporated into cost basis/proceeds. Other specific fees (`FinancialEventType.FEE_TRANSACTION`) are parsed but not automatically allocated to specific tax form lines beyond potential manual consideration as Werbungskosten.
*   **Tax Law Changes:** Tax laws and forms can change annually. While designed for flexibility, ensure the tool's logic aligns with the requirements of the specific `TAX_YEAR` you are processing, especially if it's a year beyond its last explicit validation.

## Tax Year & Scope Information

*   **Designed for Flexibility:** This tool is designed to be usable for any tax year by configuring the `TAX_YEAR` variable in `src/config.py`.
*   **Current Validation:** It has been primarily developed and validated for the **German tax year 2023**.
*   **Future Year Support:** Future versions will be explicitly released and announced with support for subsequent tax years (e.g., 2024) once they have been thoroughly tested and validated against the respective year's tax laws and forms.
*   **Data Processing & Filtering:**
    *   The system first parses all available transaction data from your input files.
    *   It establishes the **Start-of-Year (SOY) financial state** (positions and their cost bases). Quantities from your `positions_start_of_year.csv` are considered authoritative. For cost basis, the system may simulate based on historical transactions (events *before* the `TAX_YEAR`) or use the cost basis reported in the SOY file, prioritizing consistency and data availability (refer to PRD Section 2.4 for detailed logic).
    *   Then, for calculating all **income, gains, losses, and other reportable figures for the configured `TAX_YEAR`**, the engine processes only those financial events and realizations whose `event_date` or `realization_date` falls *within* that specific calendar year.
*   **No "Alt-Anteile":** It **DOES NOT** handle "Alt-Anteile" (investment fund shares acquired before January 1, 2018).
*   **Not Tax Advice:** It provides figures for declaration; **it is NOT tax advice.** Always verify results and consult a tax advisor if unsure.


## Understanding the PRD

For a deep dive into the system's requirements, logic, data structures, and calculation details (primarily based on 2023 tax law and forms), please refer to the [Product Requirements Document (PRD.md)](PRD.md). The PRD will be updated as the tool is validated for newer tax years.

## Troubleshooting / Common Issues

*   **EOY Quantity Mismatches:** If the logs or reports indicate "EOY quantity mismatch errors," carefully review:
    *   Your `positions_start_of_year.csv` and `positions_end_of_year.csv` files for correctness for the configured `TAX_YEAR`.
    *   All transaction files (`trades.csv`, `corporate_actions.csv`) for completeness and accuracy, including historical data if relied upon for SOY cost basis.
    *   Ensure all corporate actions affecting quantities have been correctly reported by IBKR and parsed by the tool.
*   **Parsing Errors:** Check your CSV files for correct formatting, encoding (UTF-8 with BOM, i.e., `utf-8-sig`), and ensure all expected columns are present. Refer to `input_data_spec.md`.
*   **Missing Exchange Rates:** Ensure you have an internet connection for the initial download of ECB rates. If issues persist, check write permissions for the `cache/` directory.
*   **Asset Classification Issues:** If an asset is misclassified, try running with `--interactive` to correct it. The classification will be cached.

## Disclaimer

This software is provided "as is," without warranty of any kind, express or implied. The authors and contributors are not liable for any claim, damages, or other liability arising from the use of this software. Use this tool at your own risk. The output generated is intended for informational purposes only and does not constitute tax advice. Always verify the figures and consult with a qualified tax professional before submitting your tax declaration.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs, feature requests, or improvements.
(Consider adding a `CONTRIBUTING.md` file with more details).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
(Create a LICENSE file with the MIT license text if you choose MIT).

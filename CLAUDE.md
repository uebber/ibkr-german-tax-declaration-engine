# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IBKR German Tax Declaration Engine - A Python tool that automates generation of figures for German tax declarations (Anlage KAP, KAP-INV, SO) based on Interactive Brokers Flex Query CSV reports. It handles FIFO calculations, currency conversion (ECB rates), corporate actions, option processing, and investment fund taxation (Teilfreistellung).

## Development Setup

This project uses `uv` for Python package management. Install uv first: https://docs.astral.sh/uv/getting-started/installation/

```bash
# Install dependencies (creates .venv automatically)
uv sync
```

## Common Commands

```bash
# Run the engine (uses settings from src/config.py)
uv run python -m src.main

# Run with interactive asset classification
uv run python -m src.main --interactive

# Generate tax declaration report and PDF
uv run python -m src.main --report-tax-declaration

# Custom PDF output
uv run python -m src.main --report-tax-declaration --pdf-output-file my_report.pdf

# Diagnostic output
uv run python -m src.main --group-by-type

# View all CLI options
uv run python -m src.main --help

# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run spec-driven FIFO tests (Groups 1-5)
uv run pytest tests/test_fifo_groups.py -v

# Run loss offsetting tests (Group 6)
uv run pytest tests/test_group6_loss_offsetting.py -v

# Run currency FIFO tests (Group 7)
uv run pytest tests/test_group7_currency_fifo.py -v

# Run stock merger FIFO lot transfer tests
uv run pytest tests/test_stock_merger_fifo.py -v

# Run options lifecycle tests
uv run pytest tests/test_options_lifecycle.py -v
```

## Architecture

### Core Processing Flow

1. **Data Preparation** (`src/data_preparation.py`) - Resolves and concatenates files from `data_import/` by tax year
2. **Parsing Layer** (`src/parsers/`) - Parses IBKR CSV files, builds asset alias map via `AssetResolver`
3. **Domain Layer** (`src/domain/`) - Data structures for assets, events, and calculation results
4. **Enrichment** (`src/processing/enrichment.py`) - Currency conversion to EUR using ECB rates
5. **Classification** (`src/classification/`) - Categorizes assets (STOCK, INVESTMENT_FUND, OPTION, etc.)
6. **Calculation Engine** (`src/engine/`) - FIFO ledger management, gain/loss calculations, corporate action processing
7. **Loss Offsetting** (`src/engine/loss_offsetting.py`) - Aggregates figures for tax form lines
8. **Reporting** (`src/reporting/`) - Console and PDF report generation

### Key Modules

- `src/identification/asset_resolver.py` - Global alias map maintaining unique Asset objects across all input files
- `src/engine/fifo_manager.py` - FIFO lot tracking for long/short positions, including drain/receive for stock mergers and position flip splitting
- `src/engine/calculation_engine.py` - Main calculation orchestration with three-pass historical replay for mergers
- `src/engine/event_processors/` - Processors for trades, corporate actions, options, and currency conversions
- `src/processing/option_trade_linker.py` - Links option exercises/assignments to stock trades
- `src/pipeline_runner.py` - Orchestrates the full processing pipeline

### Domain Model

- **Assets** (`domain/assets.py`): `Asset`, `Stock`, `Bond`, `InvestmentFund`, `Option`, `Cfd`, `PrivateSaleAsset`, `CashBalance`
- **Events** (`domain/events.py`): `FinancialEvent` base class with subtypes `TradeEvent`, `CashFlowEvent`, `CorporateActionEvent`, `OptionLifecycleEvent`, etc.
- **Results** (`domain/results.py`): `RealizedGainLoss`, `VorabpauschaleData`
- **Enums** (`domain/enums.py`): `AssetCategory`, `FinancialEventType`, `RealizationType`, `TaxReportingCategory`

## Configuration

Edit `src/config.py` before running:
- `TAX_YEAR` - Default year to process (can be overridden with `--tax-year`)
- `TAXPAYER_NAME`, `ACCOUNT_ID` - For PDF reports
- `IS_INTERACTIVE_CLASSIFICATION` - Enable/disable interactive asset classification
- `FLEX_QUERY_IDS` - IBKR Flex Query IDs for automatic download

## Numerical Precision

All financial calculations use Python's `Decimal` type with `INTERNAL_CALCULATION_PRECISION` (28 decimal places). Initialize Decimals from strings, not floats:
```python
# Correct
amount = Decimal("123.45")
# Wrong - loses precision
amount = Decimal(123.45)
```

## German Tax Form Mapping

- **Anlage KAP**: Stock/derivative gains/losses (Zeilen 19-24), foreign WHT (Zeile 41)
- **Anlage KAP-INV**: Investment fund distributions and gains (GROSS figures, Zeilen 4-8, 14, 17, 20, 23, 26)
- **Anlage SO**: Private sales under §23 EStG (holding period < 1 year)

## Input Data

CSV files from IBKR Flex Query reports are placed in the `data_import/` directory using a standardized naming scheme. The application reads from `data_import/` and prepares working copies in `data/`.

**IMPORTANT: Files in `data_import/` must NEVER be modified by the application. It is a read-only source directory.**

### Naming Scheme (`data_import/`)

```
Trades-{YYYY}.csv               # One file per year
Cash_Transactions-{YYYY}.csv    # One file per year
Corporate_Actions-{YYYY}.csv    # One file per year
Cash_Balance-{YYYY}.csv         # One file per year
Options_EAE-{YYYY}.csv          # One file per year (optional, for cash-settled index options)
Positions-{YYYY}-SoY.csv        # Start-of-year positions snapshot
Positions-{YYYY}-EoY.csv        # End-of-year positions snapshot
```

Transaction files (Trades, Cash_Transactions, Corporate_Actions, Options_EAE) for all years up to and including the tax year are concatenated automatically to provide full historical FIFO cost basis. Position and Cash Balance files are used for the selected tax year; additionally, the prior year's start-of-year positions snapshot (`Positions-{YYYY-1}-SoY.csv`), if present, is used to compute the prior calendar year's Vorabpauschale that is deemed to flow into and is declared on the selected year's return (§18 Abs. 3 InvStG).

Critical requirement: Trades file **must** include `Open/CloseIndicator` column ('O'/'C') for accurate trade classification.

See `input_data_spec.md` for detailed column specifications.

## Tax Law Reference Library

The `reference/` directory contains curated, authoritative German tax and legal sources that serve as ground truth for this engine. See `reference/INDEX.md` for the full directory.

**When writing or modifying tax logic, tests, or form mappings:**
1. Consult the relevant reference file BEFORE implementing. Read it — don't assume.
2. If a reference file covers the topic, treat it as authoritative over general knowledge.
3. Key files by area:
   - Loss offsetting / form lines: `reference/tax-law/estg-20-abs6-verlustverrechnung.md`, `reference/tax-forms/anlage-kap-zeilen.md`
   - Investment funds: `reference/investment-tax-law/` (InvStG 16, 18, 19, 20)
   - Private sales (Gold ETC, Crypto): `reference/tax-law/estg-23-private-veraeusserung.md`
   - Options / derivatives: `reference/tax-law/estg-20-kapitalvermoegen.md` (Abs. 1 Nr. 11, Abs. 2 Nr. 3)
   - FX / currency gains: `reference/bmf-guidance/fremdwaehrung-konten.md`
   - Vorabpauschale / Basiszins: `reference/investment-tax-law/invstg-18-vorabpauschale.md`, `reference/bmf-guidance/basiszins-vorabpauschale.md`
4. The coverage matrix at `reference/research/coverage-matrix.md` maps every supported event/asset to its legal source.
5. If a conflict arises between engine code and reference files, flag it to the user — do not silently follow the code.

## Ground Rules

After modifying or extending application code: Never change pre-existing tests without asking the user and explaining why this is, without doubt, necessary!!

After modifying or extending test code: Never change pre-existing application code without asking the user and explaining why this is, without doubt, necessary!!

Never fit tests to the application, always fit them to the requirements, ask the user in case of ambiguity, don't just try to make tests pass for the sake of it.

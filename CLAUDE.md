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
```

## Architecture

### Core Processing Flow

1. **Parsing Layer** (`src/parsers/`) - Parses IBKR CSV files, builds asset alias map via `AssetResolver`
2. **Domain Layer** (`src/domain/`) - Data structures for assets, events, and calculation results
3. **Enrichment** (`src/processing/enrichment.py`) - Currency conversion to EUR using ECB rates
4. **Classification** (`src/classification/`) - Categorizes assets (STOCK, INVESTMENT_FUND, OPTION, etc.)
5. **Calculation Engine** (`src/engine/`) - FIFO ledger management, gain/loss calculations, corporate action processing
6. **Loss Offsetting** (`src/engine/loss_offsetting.py`) - Aggregates figures for tax form lines
7. **Reporting** (`src/reporting/`) - Console and PDF report generation

### Key Modules

- `src/identification/asset_resolver.py` - Global alias map maintaining unique Asset objects across all input files
- `src/engine/fifo_manager.py` - FIFO lot tracking for long/short positions
- `src/engine/calculation_engine.py` - Main calculation orchestration
- `src/processing/option_trade_linker.py` - Links option exercises/assignments to stock trades
- `src/pipeline_runner.py` - Orchestrates the full processing pipeline

### Domain Model

- **Assets** (`domain/assets.py`): `Asset`, `Stock`, `Bond`, `InvestmentFund`, `Option`, `Cfd`, `PrivateSaleAsset`, `CashBalance`
- **Events** (`domain/events.py`): `FinancialEvent` base class with subtypes `TradeEvent`, `CashFlowEvent`, `CorporateActionEvent`, `OptionLifecycleEvent`, etc.
- **Results** (`domain/results.py`): `RealizedGainLoss`, `VorabpauschaleData`
- **Enums** (`domain/enums.py`): `AssetCategory`, `FinancialEventType`, `RealizationType`, `TaxReportingCategory`

## Configuration

Edit `src/config.py` before running:
- `TAX_YEAR` - Year to process
- `TAXPAYER_NAME`, `ACCOUNT_ID` - For PDF reports
- File paths for trades, cash transactions, positions (SOY/EOY), corporate actions
- `IS_INTERACTIVE_CLASSIFICATION` - Enable/disable interactive asset classification

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

CSV files from IBKR Flex Query reports. Critical requirement: Trades file **must** include `Open/CloseIndicator` column ('O'/'C') for accurate trade classification.

See `input_data_spec.md` for detailed column specifications.

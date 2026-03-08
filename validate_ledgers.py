#!/usr/bin/env python3
"""
End-to-end ledger validation script.

Runs the full processing pipeline for each year with complete data in data_import/,
captures SOY/EOY mismatch details, and prints an aggregated validation report.

Usage:
    uv run python validate_ledgers.py
    uv run python validate_ledgers.py --year 2024
    uv run python validate_ledgers.py --verbose
"""

import argparse
import logging
import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from pathlib import Path

import src.config as config
from src.data_preparation import prepare_data_for_tax_year, IMPORT_DIR, _find_years_available
from src.domain.assets import AssetCategory, CashBalance
from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput


@dataclass
class Mismatch:
    asset_name: str
    asset_id: str
    category: str
    soy_qty: Decimal
    calculated_eoy_qty: Decimal
    reported_eoy_qty: Decimal | None
    difference: Decimal


@dataclass
class YearResult:
    year: int
    success: bool
    error_message: str = ""
    asset_mismatches: list[Mismatch] = field(default_factory=list)
    currency_mismatches: list[Mismatch] = field(default_factory=list)
    total_assets: int = 0
    total_rgl_records: int = 0


def find_complete_years() -> list[int]:
    """Find years that have Trades + SoY positions + EoY positions in data_import/."""
    trade_years = set(_find_years_available("Trades"))
    soy_years = set()
    eoy_years = set()
    for f in sorted(IMPORT_DIR.glob("Positions-*-SoY.csv")):
        parts = f.stem.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            soy_years.add(int(parts[1]))
    for f in sorted(IMPORT_DIR.glob("Positions-*-EoY.csv")):
        parts = f.stem.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            eoy_years.add(int(parts[1]))

    complete = sorted(trade_years & soy_years & eoy_years)
    return complete


def run_validation_for_year(year: int) -> YearResult:
    """Run pipeline for a single year and collect mismatch details."""
    result = YearResult(year=year, success=True)

    try:
        data_paths = prepare_data_for_tax_year(year)
    except FileNotFoundError as e:
        result.success = False
        result.error_message = str(e)
        return result

    try:
        output: ProcessingOutput = run_core_processing_pipeline(
            trades_file_path=data_paths["trades"],
            cash_transactions_file_path=data_paths["cash_transactions"],
            positions_start_file_path=data_paths["positions_start"],
            positions_end_file_path=data_paths["positions_end"],
            corporate_actions_file_path=data_paths["corporate_actions"],
            interactive_classification_mode=False,
            tax_year_to_process=year,
            cash_balance_file_path=data_paths.get("cash_balance", ""),
        )
    except Exception as e:
        result.success = False
        # Extract the core error message (first line only)
        result.error_message = str(e).split("\n")[0]
        return result

    result.total_assets = len(output.asset_resolver.assets_by_internal_id)
    result.total_rgl_records = len(output.realized_gains_losses)

    # Collect structured mismatch details captured from the engine's log output
    result.asset_mismatches = _captured_mismatches.get(year, {}).get("asset", [])
    result.currency_mismatches = _captured_mismatches.get(year, {}).get("currency", [])

    if output.eoy_mismatch_error_count > 0:
        result.success = False
        result.error_message = f"{output.eoy_mismatch_error_count} asset EOY mismatch(es)"

    return result


# Global store for captured mismatch details from log messages
_captured_mismatches: dict[int, dict[str, list[Mismatch]]] = {}


class MismatchCaptureHandler(logging.Handler):
    """Captures structured mismatch data from calculation engine log messages."""

    def __init__(self, year: int):
        super().__init__()
        self.year = year
        _captured_mismatches[year] = {"asset": [], "currency": []}

    def emit(self, record: logging.LogRecord):
        msg = record.getMessage()

        if "CRITICAL EOY MISMATCH" in msg or ("EOY MISMATCH" in msg and "CURRENCY" not in msg):
            mismatch = self._parse_asset_mismatch(msg)
            if mismatch:
                _captured_mismatches[self.year]["asset"].append(mismatch)

        elif "CURRENCY EOY MISMATCH" in msg:
            mismatch = self._parse_currency_mismatch(msg)
            if mismatch:
                _captured_mismatches[self.year]["currency"].append(mismatch)

    def _parse_asset_mismatch(self, msg: str) -> Mismatch | None:
        try:
            # "CRITICAL EOY MISMATCH for DESC (ID: id): Calculated EOY Qty: X, Reported EOY Qty (from file): Y. Difference: Z"
            # or "EOY MISMATCH for DESC (ID: id): Calculated EOY Qty: X, but asset NOT found..."
            name = ""
            asset_id = ""
            calc_qty = Decimal(0)
            reported_qty = None
            diff = Decimal(0)

            if "(ID: " in msg:
                before_id = msg.split("(ID: ")[0]
                name = before_id.split("for ", 1)[-1].strip()
                asset_id = msg.split("(ID: ")[1].split(")")[0]

            if "Calculated EOY Qty: " in msg:
                calc_str = msg.split("Calculated EOY Qty: ")[1].split(",")[0].strip()
                calc_qty = Decimal(calc_str)

            if "Reported EOY Qty (from file): " in msg:
                rep_str = msg.split("Reported EOY Qty (from file): ")[1].split(".")[0].strip()
                reported_qty = Decimal(rep_str)

            if "Difference: " in msg:
                diff_str = msg.split("Difference: ")[1].strip()
                diff = Decimal(diff_str)
            elif reported_qty is None:
                reported_qty = Decimal(0)
                diff = calc_qty

            return Mismatch(
                asset_name=name,
                asset_id=asset_id,
                category="asset",
                soy_qty=Decimal(0),
                calculated_eoy_qty=calc_qty,
                reported_eoy_qty=reported_qty,
                difference=diff,
            )
        except Exception:
            return None

    def _parse_currency_mismatch(self, msg: str) -> Mismatch | None:
        try:
            # "CURRENCY EOY MISMATCH USD: FIFO ledger=-21.18, Reported=-0.00, Diff=-21.18"
            parts = msg.split("CURRENCY EOY MISMATCH ")[1]
            currency = parts.split(":")[0].strip()
            fifo_str = parts.split("FIFO ledger=")[1].split(",")[0]
            reported_str = parts.split("Reported=")[1].split(",")[0]
            diff_str = parts.split("Diff=")[1].strip()

            return Mismatch(
                asset_name=currency,
                asset_id=currency,
                category="currency",
                soy_qty=Decimal(0),
                calculated_eoy_qty=Decimal(fifo_str),
                reported_eoy_qty=Decimal(reported_str),
                difference=Decimal(diff_str),
            )
        except Exception:
            return None


def print_report(results: list[YearResult], verbose: bool = False) -> None:
    """Print aggregated validation report."""
    print()
    print("=" * 78)
    print("  LEDGER VALIDATION REPORT — SOY/EOY Consistency Check")
    print("=" * 78)

    all_passed = True

    for r in results:
        status = "PASS" if (r.success and not r.currency_mismatches) else "FAIL" if not r.success else "WARN"
        if status != "PASS":
            all_passed = False

        icon = {"PASS": "[OK]", "FAIL": "[!!]", "WARN": "[~~]"}[status]
        print(f"\n  {icon} {r.year}  |  {r.total_assets} assets  |  {r.total_rgl_records} RGL records  |  {status}")

        if r.error_message and not r.success:
            print(f"       Pipeline: {r.error_message}")

        if r.asset_mismatches:
            print(f"       Asset EOY mismatches ({len(r.asset_mismatches)}):")
            for m in r.asset_mismatches:
                rep = f"{m.reported_eoy_qty}" if m.reported_eoy_qty is not None else "not in EOY report"
                print(f"         - {m.asset_name}")
                print(f"           Calculated: {m.calculated_eoy_qty}  Reported: {rep}  Diff: {m.difference}")

        if r.currency_mismatches:
            print(f"       Currency EOY mismatches ({len(r.currency_mismatches)}):")
            for m in r.currency_mismatches:
                print(f"         - {m.asset_name}: FIFO={m.calculated_eoy_qty}, Reported={m.reported_eoy_qty}, Diff={m.difference}")

        if verbose and not r.asset_mismatches and not r.currency_mismatches and r.success:
            print("       All asset and currency EOY quantities match.")

    # Summary
    print()
    print("-" * 78)
    years_passed = sum(1 for r in results if r.success and not r.currency_mismatches)
    years_warn = sum(1 for r in results if r.success and r.currency_mismatches)
    years_failed = sum(1 for r in results if not r.success)
    total_asset_mismatches = sum(len(r.asset_mismatches) for r in results)
    total_currency_mismatches = sum(len(r.currency_mismatches) for r in results)

    print(f"  Years tested:  {len(results)}  (PASS: {years_passed}  WARN: {years_warn}  FAIL: {years_failed})")
    print(f"  Asset EOY mismatches:    {total_asset_mismatches}")
    print(f"  Currency EOY mismatches: {total_currency_mismatches}")

    if all_passed:
        print("\n  RESULT: ALL YEARS PASSED")
    else:
        print("\n  RESULT: ISSUES FOUND — review details above")

    print("=" * 78)
    print()


def main():
    parser = argparse.ArgumentParser(description="Validate ledger SOY/EOY consistency across all available years")
    parser.add_argument("--year", type=int, help="Validate a single year only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show details for passing years too")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress pipeline log output")
    args = parser.parse_args()

    # Setup decimal context
    getcontext().prec = config.INTERNAL_CALCULATION_PRECISION
    getcontext().rounding = config.DECIMAL_ROUNDING_MODE

    # Suppress noisy pipeline logging unless verbose
    if args.quiet:
        logging.basicConfig(level=logging.CRITICAL, format="%(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

    # Ensure the calculation engine logger emits WARNING+ regardless of root level,
    # so the capture handler can intercept mismatch messages.
    # Prevent propagation to root logger to avoid noisy console output in -q mode.
    calc_logger = logging.getLogger("src.engine.calculation_engine")
    calc_logger.setLevel(logging.WARNING)
    if args.quiet:
        calc_logger.propagate = False
        # Also suppress tracebacks from pipeline_runner and event processors
        for name in ["src.pipeline_runner", "src.engine.event_processors",
                     "src.engine.event_processors.trade_processor",
                     "src.engine.event_processors.option_processor",
                     "src.parsers"]:
            logging.getLogger(name).setLevel(logging.CRITICAL)

    if args.year:
        years = [args.year]
    else:
        years = find_complete_years()
        if not years:
            print(f"No complete years found in {IMPORT_DIR}/. Need at least Trades-YYYY.csv + Positions-YYYY-EoY.csv.")
            sys.exit(1)

    print(f"Validating {len(years)} year(s): {', '.join(str(y) for y in years)}")
    print(f"Source: {IMPORT_DIR}/")

    results = []
    for year in years:
        # Install capture handler for this year
        handler = MismatchCaptureHandler(year)
        calc_logger.addHandler(handler)

        print(f"\nProcessing {year}...", end="", flush=True)
        r = run_validation_for_year(year)
        results.append(r)

        status = "OK" if r.success and not r.currency_mismatches else "ISSUES"
        print(f" {status}")

        calc_logger.removeHandler(handler)

    print_report(results, verbose=args.verbose)

    # Exit code: 0 if no asset mismatches, 1 otherwise
    has_asset_failures = any(not r.success for r in results)
    sys.exit(1 if has_asset_failures else 0)


if __name__ == "__main__":
    main()

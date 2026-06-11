"""
Regression tests for the current (2025) IBKR Flex export format.

Real exports differ from the engine's original assumptions in three ways:
1. IBKR inserts REPEATED HEADER ROWS mid-file (and when concatenating yearly
   files, every file brings its own header) — a repeated header parsed as data
   corrupts the row stream.
2. Cash Balance files carry EXTRA columns (new EndingCash* fields) — strict
   column validation rejected the whole file.
3. Cash Balance files contain a BASE_SUMMARY aggregate row — parsing it as a
   currency would create a phantom "BASE_SUMMARY" cash asset.

These are data-integrity prerequisites for every tax figure downstream.
"""
import csv
import io
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data_preparation import _concatenate_csvs, _copy_file
from src.parsers.cash_balance_parser import parse_cash_balance_csv
from src.parsers.column_validator import validate_csv_columns, CASH_BALANCE_COLUMNS
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from src.parsers.raw_models import RawCashBalanceRecord
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.domain.enums import AssetCategory


HEADER = '"ClientAccountID","CurrencyPrimary","FromDate","ToDate","StartingCash","EndingCash"'
ROW_USD = '"U1234567","USD","20250101","20251231","1000","900"'
ROW_CHF = '"U1234567","CHF","20250101","20251231","50","50"'


# ---------------------------------------------------------------------------
# 1. Duplicate header rows
# ---------------------------------------------------------------------------

class TestDuplicateHeaderRows:

    def test_concatenate_skips_repeated_header_rows(self, tmp_path):
        """Concatenating yearly files must not turn the later files' header
        lines into data rows; headers repeated MID-file are dropped too."""
        f1 = tmp_path / "Trades-2024.csv"
        f1.write_text(f"{HEADER}\n{ROW_USD}\n", encoding="utf-8-sig")
        f2 = tmp_path / "Trades-2025.csv"
        # repeated header mid-file (as in real exports) + own leading header
        f2.write_text(f"{HEADER}\n{ROW_CHF}\n{HEADER}\n{ROW_USD}\n", encoding="utf-8-sig")
        out = tmp_path / "out.csv"

        _concatenate_csvs([f1, f2], out)

        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8-sig"))))
        assert rows[0] == list(csv.reader(io.StringIO(HEADER)))[0]
        # exactly 3 data rows, none of which is a header
        assert len(rows) == 4
        assert all(r[0] != "ClientAccountID" for r in rows[1:])

    def test_copy_file_strips_repeated_header_rows(self, tmp_path):
        """Single-file copy (positions/cash balance) must also drop repeated
        header lines that IBKR inserts mid-file."""
        src = tmp_path / "Cash_Balance-2025.csv"
        src.write_text(f"{HEADER}\n{ROW_USD}\n{HEADER}\n{ROW_CHF}\n", encoding="utf-8-sig")
        dest = tmp_path / "work" / "cash_balance.csv"

        _copy_file(src, dest)

        rows = list(csv.reader(io.StringIO(dest.read_text(encoding="utf-8-sig"))))
        assert len(rows) == 3  # header + 2 data rows, repeated header gone
        assert rows[1][1] == "USD" and rows[2][1] == "CHF"


# ---------------------------------------------------------------------------
# 2. Extra columns in Cash Balance files
# ---------------------------------------------------------------------------

class TestCashBalanceExtraColumns:

    def test_parser_accepts_new_endingcash_columns(self, tmp_path):
        """Current exports append extra EndingCash* fields; the parser must
        accept them (required columns present) instead of rejecting the file."""
        p = tmp_path / "cash.csv"
        p.write_text(
            '"ClientAccountID","CurrencyPrimary","FromDate","ToDate","StartingCash","EndingCash","EndingCashSec","EndingCashCom"\n'
            '"U1234567","USD","20250101","20251231","1000","900","800","100"\n',
            encoding="utf-8-sig",
        )
        records = parse_cash_balance_csv(str(p))
        assert len(records) == 1
        assert records[0].currency_primary == "USD"
        assert records[0].ending_cash == Decimal("900")

    def test_validator_still_rejects_missing_columns(self):
        """allow_extra must not weaken the missing-column check."""
        with pytest.raises(ValueError, match="Missing columns"):
            validate_csv_columns(
                ["ClientAccountID", "CurrencyPrimary"],  # most columns missing
                CASH_BALANCE_COLUMNS, "Cash Balance (test)", allow_extra=True,
            )

    def test_validator_default_still_rejects_extra_columns(self):
        """Strict files (default allow_extra=False) keep rejecting extras."""
        with pytest.raises(ValueError, match="Unexpected columns"):
            validate_csv_columns(
                list(CASH_BALANCE_COLUMNS) + ["Surprise"],
                CASH_BALANCE_COLUMNS, "Cash Balance (test)",
            )


# ---------------------------------------------------------------------------
# 3. BASE_SUMMARY aggregate row
# ---------------------------------------------------------------------------

def _orchestrator():
    classifier = MagicMock(spec=AssetClassifier)
    classifier.preliminary_classify.return_value = (AssetCategory.CASH_BALANCE, None)
    resolver = AssetResolver(classifier)
    return ParsingOrchestrator(resolver, classifier, interactive_classification=False)


def _cash(ccy, soy, eoy):
    return RawCashBalanceRecord(**{
        "ClientAccountID": "U1234567", "CurrencyPrimary": ccy,
        "FromDate": "20250101", "ToDate": "20251231",
        "StartingCash": Decimal(soy), "EndingCash": Decimal(eoy),
    })


class TestBaseSummaryRowSkipped:

    def test_base_summary_row_creates_no_currency_asset(self):
        """The BASE_SUMMARY row is IBKR's report aggregate, not a currency —
        it must be skipped like the EUR base-currency row."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("USD", "1000", "900"),
            _cash("BASE_SUMMARY", "9999", "9999"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)

        currencies = {
            (a.currency or "").upper()
            for a in orch.asset_resolver.assets_by_internal_id.values()
            if a.asset_category == AssetCategory.CASH_BALANCE
        }
        assert "USD" in currencies
        assert "BASE_SUMMARY" not in currencies

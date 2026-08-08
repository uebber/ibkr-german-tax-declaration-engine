# src/parsers/cash_balance_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawCashBalanceRecord
from .column_validator import CASH_BALANCE_COLUMNS


def parse_cash_balance_csv(file_path: str, encoding='utf-8-sig') -> List[RawCashBalanceRecord]:
    """Parse the IBKR Cash Report export.

    `allow_extra=True`, and the reason is the segment breakdown: the IBKR Cash Report
    can append `EndingCashSec` / `EndingCashCom` beside `EndingCash`, which the engine
    does not model. `tests/test_ibkr_format_parsing.py::TestCashBalanceExtraColumns`
    pins that, and pinned it against an attempt to remove the tolerance on 2026-08-09.

    The docstring said "this is the one export whose header carries columns the engine
    does not model", in the present tense, which every real header contradicts:
    `Cash_Balance-{2021..2025}` each carry exactly `CASH_BALANCE_COLUMNS`. The tolerance
    is for a query configuration this account does not use, not for the files on disk --
    a distinction worth keeping, because it is the only parser that cannot report an
    export growing a column.
    """
    return parse_records(file_path, RawCashBalanceRecord, CASH_BALANCE_COLUMNS,
                         "Cash Balance", encoding=encoding, allow_extra=True)

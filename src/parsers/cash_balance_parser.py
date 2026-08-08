# src/parsers/cash_balance_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawCashBalanceRecord
from .column_validator import CASH_BALANCE_COLUMNS


def parse_cash_balance_csv(file_path: str, encoding='utf-8-sig') -> List[RawCashBalanceRecord]:
    """Parse the IBKR Cash Report export.

    `allow_extra=True`: this is the one export whose header carries columns the
    engine does not model, and the tolerance predates this reader.
    """
    return parse_records(file_path, RawCashBalanceRecord, CASH_BALANCE_COLUMNS,
                         "Cash Balance", encoding=encoding, allow_extra=True)

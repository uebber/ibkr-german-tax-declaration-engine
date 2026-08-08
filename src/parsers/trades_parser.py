# src/parsers/trades_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawTradeRecord
from .column_validator import TRADES_COLUMNS


def parse_trades_csv(file_path: str, encoding='utf-8-sig') -> List[RawTradeRecord]:
    """Parse the IBKR Trades export. Raises rather than dropping a row -- see csv_reader."""
    return parse_records(file_path, RawTradeRecord, TRADES_COLUMNS, "Trades",
                         encoding=encoding)

# src/parsers/cash_transactions_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawCashTransactionRecord
from .column_validator import CASH_TRANSACTIONS_COLUMNS


def parse_cash_transactions_csv(file_path: str, encoding='utf-8-sig') -> List[RawCashTransactionRecord]:
    """Parse the IBKR Cash Transactions export.

    A dropped row here is the worst case the reader guards: dividends, interest
    and withholding tax touch no share quantity, so the securities reconciliation
    stays green and the income is simply not declared.
    """
    return parse_records(file_path, RawCashTransactionRecord, CASH_TRANSACTIONS_COLUMNS,
                         "Cash Transactions", encoding=encoding)

# tests/helpers/csv_creators.py
import io
import csv
from decimal import Decimal
from typing import List, Dict, Any, Union

from src.parsers.column_validator import (
    TRADES_COLUMNS,
    CASH_TRANSACTIONS_COLUMNS,
    POSITIONS_COLUMNS,
    CORPORATE_ACTIONS_COLUMNS,
    CASH_BALANCE_COLUMNS,
    TRANSFERS_COLUMNS,
    GRANTS_COLUMNS,
)

def create_csv_string(headers: List[str], data_rows: List[List[Union[str, Decimal, int, float, None]]]) -> str:
    """
    Generates a CSV formatted string from headers and data rows.
    Handles Decimal types by converting them to strings.
    None values are converted to empty strings.
    Floats are also converted to strings.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in data_rows:
        processed_row = []
        for item in row:
            if isinstance(item, Decimal):
                processed_row.append(str(item))
            elif item is None:
                processed_row.append("")
            elif isinstance(item, float): # Ensure floats are also stringified
                processed_row.append(str(item))
            else:
                processed_row.append(str(item))
        writer.writerow(processed_row)
    return output.getvalue()

# Column headers imported from canonical source (src/parsers/column_validator.py)
TRADES_FILE_HEADERS = list(TRADES_COLUMNS)
POSITIONS_FILE_HEADERS = list(POSITIONS_COLUMNS)
CASH_TRANSACTIONS_HEADERS = list(CASH_TRANSACTIONS_COLUMNS)
CORPORATE_ACTIONS_HEADERS = list(CORPORATE_ACTIONS_COLUMNS)
CASH_BALANCE_HEADERS = list(CASH_BALANCE_COLUMNS)
TRANSFERS_FILE_HEADERS = list(TRANSFERS_COLUMNS)
GRANTS_FILE_HEADERS = list(GRANTS_COLUMNS)

def create_trades_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(TRADES_FILE_HEADERS, data_rows)

def create_positions_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(POSITIONS_FILE_HEADERS, data_rows)

def create_cash_transactions_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(CASH_TRANSACTIONS_HEADERS, data_rows)

def create_corporate_actions_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(CORPORATE_ACTIONS_HEADERS, data_rows)

def create_cash_balance_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(CASH_BALANCE_HEADERS, data_rows)

def create_transfers_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(TRANSFERS_FILE_HEADERS, data_rows)


def create_grants_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(GRANTS_FILE_HEADERS, data_rows)

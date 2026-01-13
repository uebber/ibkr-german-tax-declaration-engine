# src/parsers/cash_balance_parser.py
import csv
from typing import List
from pydantic import ValidationError

from .raw_models import RawCashBalanceRecord


def parse_cash_balance_csv(file_path: str, encoding='utf-8-sig') -> List[RawCashBalanceRecord]:
    """Parse IBKR Cash Report CSV into raw cash balance records."""
    raw_balances: List[RawCashBalanceRecord] = []
    try:
        with open(file_path, mode='r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row_dict in enumerate(reader):
                try:
                    raw_balances.append(RawCashBalanceRecord(**row_dict))
                except ValidationError as e:
                    print(f"Validation Error parsing cash balance row {i+2}: {row_dict}. Error: {e.errors()}")
                except Exception as e:
                    print(f"Unexpected error parsing cash balance row {i+2}: {row_dict}. Error: {e}")
    except FileNotFoundError:
        print(f"Cash balance file not found: {file_path}")
    except Exception as e:
        print(f"Error reading cash balance file {file_path}: {e}")
    return raw_balances

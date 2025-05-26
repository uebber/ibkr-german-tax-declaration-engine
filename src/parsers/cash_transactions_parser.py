# src/parsers/cash_transactions_parser.py
import csv
from typing import List
from pydantic import ValidationError

from .raw_models import RawCashTransactionRecord

def parse_cash_transactions_csv(file_path: str, encoding='utf-8-sig') -> List[RawCashTransactionRecord]:
    raw_cash_transactions: List[RawCashTransactionRecord] = []
    try:
        with open(file_path, mode='r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row_dict in enumerate(reader):
                try:
                    raw_cash_transactions.append(RawCashTransactionRecord(**row_dict))
                except ValidationError as e:
                    print(f"Validation Error parsing cash transaction row {i+2}: {row_dict}. Error: {e.errors()}")
                except Exception as e:
                    print(f"Unexpected error parsing cash transaction row {i+2}: {row_dict}. Error: {e}")
    except FileNotFoundError:
        print(f"Cash transactions file not found: {file_path}")
    except Exception as e:
        print(f"Error reading cash transactions file {file_path}: {e}")
    return raw_cash_transactions

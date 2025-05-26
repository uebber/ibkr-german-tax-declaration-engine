# src/parsers/trades_parser.py
import csv
from typing import List
from pydantic import ValidationError

from .raw_models import RawTradeRecord
from src.utils.type_utils import parse_ibkr_datetime # For trade_time if needed to combine with date

def parse_trades_csv(file_path: str, encoding='utf-8-sig') -> List[RawTradeRecord]:
    raw_trades: List[RawTradeRecord] = []
    try:
        with open(file_path, mode='r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row_dict in enumerate(reader):
                try:
                    # Pydantic will use Field aliases for mapping
                    raw_trades.append(RawTradeRecord(**row_dict))
                except ValidationError as e:
                    print(f"Validation Error parsing trade row {i+2}: {row_dict}. Error: {e.errors()}")
                except Exception as e:
                    print(f"Unexpected error parsing trade row {i+2}: {row_dict}. Error: {e}")
    except FileNotFoundError:
        print(f"Trades file not found: {file_path}")
    except Exception as e:
        print(f"Error reading trades file {file_path}: {e}")
    return raw_trades

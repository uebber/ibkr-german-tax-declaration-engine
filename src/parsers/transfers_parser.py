# src/parsers/transfers_parser.py
"""
Parse IBKR Transfers (Depotübertragung) CSV into raw transfer records.

Each transfer leg is exported as two rows: a position-bearing row (with a TransactionID and
SettleDate) and a 'ST' settlement-marker row (empty TransactionID). Only the position-bearing
rows are kept here; downstream the OUT leg of an INTERNAL transfer drives a tax-neutral move
(drain lots from the source account ledger, receive into the target account ledger).
"""
import csv
from typing import List

from pydantic import ValidationError

from .raw_models import RawTransferRecord
from .column_validator import validate_csv_columns, TRANSFERS_COLUMNS


def parse_transfers_csv(file_path: str, encoding: str = "utf-8-sig") -> List[RawTransferRecord]:
    records: List[RawTransferRecord] = []
    try:
        with open(file_path, mode="r", encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            validate_csv_columns(reader.fieldnames or [], TRANSFERS_COLUMNS, f"Transfers ({file_path})", allow_extra=True)
            for i, row_dict in enumerate(reader):
                try:
                    rec = RawTransferRecord(**row_dict)
                except ValidationError as e:
                    print(f"Validation Error parsing transfer row {i+2}: {row_dict}. Error: {e.errors()}")
                    continue
                except Exception as e:
                    print(f"Unexpected error parsing transfer row {i+2}: {row_dict}. Error: {e}")
                    continue
                # Drop the paired 'ST' settlement-marker rows (no TransactionID): keep only the
                # position-bearing rows so a transfer is not double-counted.
                if not (rec.transaction_id and rec.transaction_id.strip()):
                    continue
                # Skip a repeated header line read as data (IBKR exports duplicate the header):
                # a real row always has a valid Direction.
                if (rec.direction or "").upper() not in ("IN", "OUT"):
                    continue
                records.append(rec)
    except FileNotFoundError:
        print(f"Transfers file not found: {file_path}")
    except Exception as e:
        print(f"Error reading transfers file {file_path}: {e}")
    return records

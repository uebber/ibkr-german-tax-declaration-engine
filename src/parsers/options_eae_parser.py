# src/parsers/options_eae_parser.py
import csv
from typing import List
from pydantic import ValidationError

from .raw_models import RawOptionsEAERecord
from .column_validator import validate_csv_columns, OPTIONS_EAE_COLUMNS


def parse_options_eae_csv(file_path: str, encoding='utf-8-sig') -> List[RawOptionsEAERecord]:
    """Parse IBKR OptionEAE Flex Query CSV into raw records."""
    raw_records: List[RawOptionsEAERecord] = []
    try:
        with open(file_path, mode='r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            validate_csv_columns(reader.fieldnames or [], OPTIONS_EAE_COLUMNS, f"Options EAE ({file_path})")
            for i, row_dict in enumerate(reader):
                try:
                    raw_records.append(RawOptionsEAERecord(**row_dict))
                except ValidationError as e:
                    print(f"Validation Error parsing Options EAE row {i+2}: {row_dict}. Error: {e.errors()}")
                except Exception as e:
                    print(f"Unexpected error parsing Options EAE row {i+2}: {row_dict}. Error: {e}")
    except FileNotFoundError:
        print(f"Options EAE file not found: {file_path}")
    except Exception as e:
        print(f"Error reading Options EAE file {file_path}: {e}")
    return raw_records

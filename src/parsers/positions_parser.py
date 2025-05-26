# src/parsers/positions_parser.py
import csv
from typing import List
from pydantic import ValidationError

from .raw_models import RawPositionRecord

def parse_positions_csv(file_path: str, encoding='utf-8-sig') -> List[RawPositionRecord]:
    raw_positions: List[RawPositionRecord] = []
    try:
        with open(file_path, mode='r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row_dict in enumerate(reader):
                try:
                    # Assuming 'Quantity' in CSV maps to 'Position' in RawPositionRecord via alias or direct name
                    # If 'Position' is the CSV header, then RawPositionRecord.position will map directly.
                    # Current RawPositionRecord uses 'Position' for the field name and alias.
                    raw_positions.append(RawPositionRecord(**row_dict))
                except ValidationError as e:
                    print(f"Validation Error parsing position row {i+2}: {row_dict}. Error: {e.errors()}")
                except Exception as e:
                    print(f"Unexpected error parsing position row {i+2}: {row_dict}. Error: {e}")
    except FileNotFoundError:
        print(f"Positions file not found: {file_path}")
    except Exception as e:
        print(f"Error reading positions file {file_path}: {e}")
    return raw_positions

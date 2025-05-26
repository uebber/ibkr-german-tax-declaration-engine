# src/parsers/corporate_actions_parser.py
import csv
from typing import List
from pydantic import ValidationError

from .raw_models import RawCorporateActionRecord

def parse_corporate_actions_csv(file_path: str, encoding='utf-8-sig') -> List[RawCorporateActionRecord]:
    raw_corporate_actions: List[RawCorporateActionRecord] = []
    try:
        with open(file_path, mode='r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row_dict in enumerate(reader):
                try:
                    # Pydantic handles the alias mapping defined in RawCorporateActionRecord
                    raw_corporate_actions.append(RawCorporateActionRecord(**row_dict))
                except ValidationError as e:
                    print(f"Validation Error parsing corporate action row {i+2}: {row_dict}. Error: {e.errors()}")
                except Exception as e:
                    print(f"Unexpected error parsing corporate action row {i+2}: {row_dict}. Error: {e}")
    except FileNotFoundError:
        print(f"Corporate actions file not found: {file_path}")
    except Exception as e:
        print(f"Error reading corporate actions file {file_path}: {e}")
    return raw_corporate_actions

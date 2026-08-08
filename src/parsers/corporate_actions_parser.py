# src/parsers/corporate_actions_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawCorporateActionRecord
from .column_validator import CORPORATE_ACTIONS_COLUMNS


def parse_corporate_actions_csv(file_path: str, encoding='utf-8-sig') -> List[RawCorporateActionRecord]:
    """Parse the IBKR Corporate Actions export."""
    return parse_records(file_path, RawCorporateActionRecord, CORPORATE_ACTIONS_COLUMNS,
                         "Corporate Actions", encoding=encoding)

# src/parsers/positions_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawPositionRecord
from .column_validator import POSITIONS_COLUMNS


def parse_positions_csv(file_path: str, encoding='utf-8-sig') -> List[RawPositionRecord]:
    """Parse an IBKR Positions snapshot (SoY, EoY, or a checkpoint mark)."""
    return parse_records(file_path, RawPositionRecord, POSITIONS_COLUMNS, "Positions",
                         encoding=encoding)

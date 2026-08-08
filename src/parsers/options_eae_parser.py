# src/parsers/options_eae_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawOptionsEAERecord
from .column_validator import OPTIONS_EAE_COLUMNS


def parse_options_eae_csv(file_path: str, encoding='utf-8-sig') -> List[RawOptionsEAERecord]:
    """Parse the IBKR OptionEAE export (exercises, assignments, expirations).

    Optional as a file, but not optional once a cash settlement happened -- the
    requirement is decided from the trades in
    `ParsingOrchestrator._require_option_cash_settlements`.
    """
    return parse_records(file_path, RawOptionsEAERecord, OPTIONS_EAE_COLUMNS,
                         "Options EAE", encoding=encoding)

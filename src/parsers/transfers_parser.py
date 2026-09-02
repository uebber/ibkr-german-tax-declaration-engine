# src/parsers/transfers_parser.py
from typing import List

from .csv_reader import parse_records
from .raw_models import RawTransferRecord
from .column_validator import TRANSFERS_COLUMNS


def parse_transfers_csv(file_path: str, encoding='utf-8-sig') -> List[RawTransferRecord]:
    """Parse the IBKR Transfers export -- moves between the taxpayer's own accounts.

    Read strictly, with no `allow_extra`: the export's shape is a required input and a
    column appearing or disappearing must stop the run rather than be tolerated. In
    particular the lot-detail columns `LevelOfDetail`, `CostBasis` and `OpenDateTime`
    are required -- without them the run cannot say which lots moved (see
    `RawTransferRecord`).

    An empty file is ordinary input -- a person who has never moved a holding between
    their own accounts has no rows -- and the engine reads absence as "nothing moved".
    """
    return parse_records(file_path, RawTransferRecord, TRANSFERS_COLUMNS,
                         "Transfers", encoding=encoding)

# src/parsers/grants_parser.py
from typing import List

from src.domain.exceptions import DataIntegrityError

from .csv_reader import parse_records
from .raw_models import RawGrantRecord
from .column_validator import GRANTS_COLUMNS

# The three activity kinds this export is known to carry, and whether each moves the
# position. Measured against the export before this module was written; the count is in
# `VALIDATION_REPORT.md`.
#
# Matching is on a substring rather than the whole string because the broker appends the
# reason to the kind -- an award reads "... for Cash Deposit", a reversal "... for Cash
# Withdrawal" -- and the reason names the customer's conduct, not a different tax event.
AWARD_MARKER = "Stock Award Grant"
REVERSAL_MARKER = "Stock Award Return"
VESTING_MARKER = "Stock Award Vesting"

KNOWN_ACTIVITY_MARKERS = (AWARD_MARKER, REVERSAL_MARKER, VESTING_MARKER)


def parse_grants_csv(file_path: str, encoding='utf-8-sig') -> List[RawGrantRecord]:
    """Parse the IBKR Stock Grant Activity export -- shares awarded for placing capital.

    Read strictly, with no `allow_extra`, for the reason `parse_transfers_csv` gives: no
    code path read this export until an award had to reach the ledger, so nothing has yet
    established which shapes of it occur.

    An empty file is ordinary input -- a person whose broker has never awarded them
    shares has no rows -- and absence reads as "nothing was awarded".

    **An unrecognised `ActivityDescription` stops the run.** The alternative is to ignore
    the row, and ignoring is what makes a new activity kind invisible: two of the three
    known kinds move the position and one does not, so a kind nobody has classified is as
    likely to move it as not. A run that silently dropped one would reconcile against the
    broker's snapshot until the year the dropped kind mattered, and then produce a wrong
    cost basis rather than a failure. Every offending row is collected before raising, so
    one run names the whole problem.
    """
    records = parse_records(file_path, RawGrantRecord, GRANTS_COLUMNS,
                            "Grants", encoding=encoding)

    unknown = [
        r for r in records
        if not any(marker in r.activity_description for marker in KNOWN_ACTIVITY_MARKERS)
    ]
    if unknown:
        seen = sorted({r.activity_description for r in unknown})
        raise DataIntegrityError(
            f"{len(unknown)} row(s) of the Grants export carry an activity kind this "
            f"engine does not classify: {seen}. Each known kind either moves the "
            f"position or deliberately does not, and which of the two an unclassified "
            f"kind is cannot be guessed -- an award and a vesting differ in nothing a "
            f"parser can see except this text. Classify it against "
            f"reference/tax-law/estg-22-nr3-leistungen.md before running again."
        )

    return records

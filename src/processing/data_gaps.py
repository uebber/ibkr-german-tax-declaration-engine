# src/processing/data_gaps.py
"""
Data-gap channel (rework2-plan AR6) — ONE path for "the input could not fully
support the computation" instead of scattered ad-hoc fallbacks.

Why: the legal review found two failure classes born from local convenience
decisions about missing data — silent zeros that UNDERSTATE income (missing
Basiszins, missing fund NAV → finding F4/F6) and quiet evidentiary mismatches
(SoY/EOY reconciliation). Every such condition now flows through a collector
with an explicit severity policy:

- ``FAIL_FAST``  — conditions under which continuing would risk UNDERSTATING
  taxable income (e.g. an unresolvable year-start NAV for the Vorabpauschale
  in a non-interactive run). Raises immediately: a tax engine must not emit a
  plausible-looking but incomplete declaration.
- ``WARNING``    — evidentiary divergences that do not silently change the
  declared figures (e.g. EOY quantity mismatches against the broker report).
  Recorded, logged, and surfaced as an explicit report section so the user
  reviews them instead of finding them in a log file.

The collector travels with the pipeline result (``ProcessingOutput.data_gaps``)
and the reporting layer renders all collected gaps.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class GapSeverity(Enum):
    WARNING = "WARNING"
    FAIL_FAST = "FAIL_FAST"


class DataGapError(RuntimeError):
    """Raised when a FAIL_FAST gap is recorded: continuing would risk an
    incomplete (income-understating) tax computation."""


@dataclass(frozen=True)
class DataGap:
    code: str           # stable machine code, e.g. "EOY_QTY_MISMATCH"
    subject: str        # what it concerns (asset / currency / year)
    detail: str         # human-readable description for the report
    severity: GapSeverity = GapSeverity.WARNING


@dataclass
class DataGapCollector:
    gaps: List[DataGap] = field(default_factory=list)

    def record(self, code: str, subject: str, detail: str,
               severity: GapSeverity = GapSeverity.WARNING) -> DataGap:
        gap = DataGap(code=code, subject=subject, detail=detail, severity=severity)
        self.gaps.append(gap)
        if severity is GapSeverity.FAIL_FAST:
            logger.critical(f"DATA GAP (fail-fast) [{code}] {subject}: {detail}")
            raise DataGapError(f"[{code}] {subject}: {detail}")
        logger.warning(f"Data gap [{code}] {subject}: {detail}")
        return gap

    def __len__(self) -> int:
        return len(self.gaps)

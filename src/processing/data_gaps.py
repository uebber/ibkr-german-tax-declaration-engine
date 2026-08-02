# src/processing/data_gaps.py
"""
Data-gap channel — one path for "the input could not fully support the
computation", replacing per-site ad-hoc decisions about missing data.

Why: conditions of this kind used to be settled locally, each in its own way —
a silent zero here, a log line there — and the two ways of getting it wrong
have very different costs. A silent substitute value UNDERSTATES income and is
invisible in the output; an unreconciled divergence is visible only to whoever
reads the log. The collector makes the choice explicit and reviewable:

- ``FAIL_FAST``  — continuing would risk UNDERSTATING taxable income (e.g. an
  unresolvable year-start NAV for the Vorabpauschale in a non-interactive run,
  where the deemed income simply cannot be computed). Raises immediately: a tax
  engine must not emit a plausible-looking but incomplete declaration. This is
  the same policy CLAUDE.md states for the engine at large.
- ``WARNING``    — the run can produce a complete set of figures, but the input
  leaves a divergence the taxpayer has to resolve before filing. Recorded,
  logged, and surfaced as an explicit report section rather than a log line.

Scope, stated precisely because the severity words above are easy to over-read:
today exactly one condition is routed through this channel — the End-of-Year
quantity mismatch against the broker's positions report, at WARNING. That
choice preserves the engine's pre-existing behaviour (log, count, continue),
which is deliberate: an EoY mismatch here is normally the pre-2021 data-floor
artefact, and aborting would make early tax years unprocessable.

**A WARNING is not a statement that the declared figures are unaffected.** An
EoY quantity mismatch is the very signature of a disposal the engine did not
process: if the calculated position exceeds the reported one, a sale is missing
and with it its realised gain, so income is understated by exactly the amount
nobody can see. WARNING here means "the engine cannot decide this for you and
will not pretend it did" — the figures must be reconciled by hand before the
declaration is filed.

Conditions NOT routed through this channel (each still handled at its own site,
each recorded as an open item in docs/pr-train-review.md): the event-separation
loop's silent drop of an unsortable event, ``_apply_historical_currency_event``
swallowing every exception at DEBUG level, and Pass 2's warn-and-continue on a
missing merger source ledger. Wiring those up is future work, not a property of
this module.

The collector travels with the pipeline result (``ProcessingOutput.data_gaps``)
and the reporting layer renders all collected gaps.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from src.domain.exceptions import ProcessingError

logger = logging.getLogger(__name__)


class GapSeverity(Enum):
    WARNING = "WARNING"
    FAIL_FAST = "FAIL_FAST"


class DataGapError(ProcessingError):
    """Raised when a FAIL_FAST gap is recorded: continuing would risk an
    incomplete (income-understating) tax computation.

    Subclasses ``ProcessingError`` so it lands in the exception taxonomy
    CLAUDE.md defines for the engine, and so an ``except ProcessingError``
    handler cannot miss it. ``ProcessingError`` is itself a ``RuntimeError``,
    so nothing that caught the original type stops catching this one.
    """


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

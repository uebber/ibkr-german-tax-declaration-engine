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

**These two words rank a gap. They do not license computing through one.** The
severities say how loudly the report complains about a condition already
recorded here; they are not a scale on which one wrong figure beats another.
An argument of the form "assuming X can only overstate, which is the safer
side" has already left this channel — it computes a number nobody can check
instead of recording that the input could not support one. The choice this
module offers is between a figure and no figure, never between two figures.
CLAUDE.md, "There is no safe direction to be wrong", states the same rule for
the engine at large.

Scope, stated precisely because the severity words above are easy to over-read.
The conditions routed through this channel, as of 2026-08-08:

    ANLAGE_KAP_GERMAN_KEST_NOT_DECLARABLE              WARNING
    CURRENCY_EOY_MISMATCH                              WARNING
    EOY_QTY_MISMATCH                                   WARNING
    KAP_INV_Z53_VORABPAUSCHALE_DEDUCTION_NOT_COMPUTED  WARNING
    REPLAY_MARK_UNCONFIRMED_START                      WARNING
    VORABPAUSCHALE_PRICE_ISSUER_NAV                    WARNING
    VORABPAUSCHALE_PRICE_MARKET_FALLBACK               WARNING
    VORABPAUSCHALE_PRICE_USER_SUPPLIED                 WARNING
    VORABPAUSCHALE_PRICE_WRONG_DAY                     WARNING
    EOY_RECONCILIATION_FAILED                          FAIL_FAST
    REPLAY_MARK_MISMATCH                               FAIL_FAST
    VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN            FAIL_FAST
    VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING         FAIL_FAST
    VORABPAUSCHALE_YEAR_START_PRICE_UNKNOWN            FAIL_FAST

This paragraph said "today exactly one condition" until 2026-08-08, by which
time there were eleven. Keep it in step or delete it; a list that undercounts
the channel invites the next reader to conclude it is barely used and settle
their condition locally, which is the habit it exists to end. The list above was
extracted by parsing every `record(` call in `src/`, not written from memory —
a first attempt at it from memory missed three.

**`EOY_QTY_MISMATCH` being a WARNING does not mean the run continues.** It is
recorded once per affected position, and after the loop
`EOY_RECONCILIATION_FAILED` is recorded FAIL_FAST naming all of them, so a
securities mismatch always aborts — CLAUDE.md's non-negotiable SoY→EoY rule.
The WARNING entries are the itemisation the fatal one points at, not a policy
of tolerating the condition. This paragraph said the opposite until 2026-08-08,
describing the "log, count, continue" behaviour that predates the abort.

`CURRENCY_EOY_MISMATCH` is the one that genuinely does continue: a cash-balance
divergence is about input completeness rather than a ledger disagreeing about a
holding, so it is recorded and the run proceeds.

Two of the WARNING entries record something the run then *uses* rather than
something it lacks: a Vorabpauschale price taken from the wrong day, and one the
taxpayer supplied by hand. They are here because a figure resting on an input
the broker never reported is exactly what the taxpayer must check before filing,
and the report section is the only place that reaches them.

**A WARNING is not a statement that the declared figures are unaffected.** An
EoY quantity mismatch is the very signature of a disposal the engine did not
process: if the calculated position exceeds the reported one, a sale is missing
and with it its realised gain, so income is understated by exactly the amount
nobody can see. WARNING here means "the engine cannot decide this for you and
will not pretend it did" — the figures must be reconciled by hand before the
declaration is filed.

Conditions NOT routed through this channel, each still handled at its own site:
``_apply_historical_currency_event`` swallowing every exception at DEBUG level
(issue #49), and ``_replay_historical_merger``'s warn-and-continue on a
missing merger source ledger
(issue #50). Wiring those up is future work, not a property of this module.

The collector travels with the pipeline result (``ProcessingOutput.data_gaps``)
and the reporting layer renders all collected gaps.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List

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

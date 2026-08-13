# src/engine/event_processors/stock_award_processor.py
"""Shares a broker awarded for capital placed with it, in the tax year.

**The whole reason this file exists is that a vesting can fall inside the declared
year.** The historical replay applies awards dated before the tax year
(`FifoLedger.apply_historical_event`), and for a while that was the only dispatch there
was. An award event dated inside the year then reached the current-year table, found no
processor, and produced a log line -- and the run continued.

For an award or a reversal that is loud: the quantity is wrong and the end-of-year
reconciliation refuses it. **For a vesting it was silent**, because a vesting moves no
shares. The quantity reconciled, no gap was recorded, and a disposal later that year was
measured against the PROVISIONAL award price instead of the value at Zufluss -- a wrong
figure that looks exactly like a right one, which is the failure this repository exists
to prevent. It is also precisely the blind spot CLAUDE.md names: a green reconciliation
compares net quantity and cannot see a wrong basis.

The three kinds do here what they do in the replay, and the two paths call the same
`FifoLedger` methods so they cannot disagree about what an award means.

None of the three declares anything by itself. An award and a reversal are not disposals,
and a vesting is a receipt under § 22 Nr. 3 EStG ([GT-ESTG20-063]) which belongs on
Anlage SO -- a category the reporting layer does not have, tracked as issue #76. What a
vesting does affect is the Anschaffungskosten of the lot ([GT-ESTG20-065]), and that
reaches a declared figure through the disposal, not through this processor.
"""
import logging
from typing import Any, Dict, List

from src.domain.enums import FinancialEventType
from src.domain.events import FinancialEvent, StockAwardEvent
from src.domain.exceptions import ProcessingError
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger

from .base_processor import EventProcessor

logger = logging.getLogger(__name__)


class StockAwardProcessor(EventProcessor):
    """The tax year's half of an award. The historical replay applies the same methods."""

    def process(self, event: FinancialEvent, ledger: FifoLedger,
                context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, StockAwardEvent):
            raise ProcessingError(
                f"StockAwardProcessor received {type(event).__name__}, which carries no "
                f"award date -- the only key an award has to its lot.")

        if event.event_type == FinancialEventType.STOCK_AWARD_GRANTED:
            ledger.add_lot_for_stock_award(event)
        elif event.event_type == FinancialEventType.STOCK_AWARD_REVERSED:
            ledger.reverse_stock_award_lot(event)
        elif event.event_type == FinancialEventType.STOCK_AWARD_VESTED:
            ledger.restate_stock_award_lot_on_vesting(event)
        else:
            # A fourth kind must stop the run rather than fall through. Falling through
            # is what left the vesting unapplied in the first place, and the cost of it
            # was a wrong cost basis nothing reported.
            raise ProcessingError(
                f"StockAwardProcessor has no handler for {event.event_type.name} on "
                f"{event.event_date}. It reached the current-year dispatch, so it is "
                f"expected to affect the ledger; leaving it unapplied would put a "
                f"provisional acquisition cost on a lot that a disposal then measures "
                f"against.")

        # No RealizedGainLoss from any of the three. See the module docstring: the
        # receipt is Anlage SO income this engine does not yet declare, and the effect on
        # a declared figure runs through the lot's cost basis.
        return []

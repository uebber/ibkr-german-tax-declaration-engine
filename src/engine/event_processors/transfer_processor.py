# src/engine/event_processors/transfer_processor.py
"""Moving a holding between the taxpayer's own accounts.

Not a Veraeusserung under § 20 Abs. 2 EStG: no change of beneficial owner and no
consideration, so acquisition date and acquisition cost carry over to the receiving
depot and the lots RELOCATE rather than being closed and reopened -- [GT-ESTG20-014],
reference/tax-law/estg-20-kapitalvermoegen.md, "Abs. 2". Reopening would reset the
holding period (§ 23 EStG, § 18 Abs. 2 InvStG) and the basis.

Both the historical replay and the tax year call `apply_internal_transfer` below. The
merger, which is the other event that touches two ledgers, has one implementation per
path (`calculation_engine._replay_historical_merger` and `MergerStockProcessor`); this
has one for both, because the two paths must not be able to disagree about which lots
moved.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List

from src.domain.events import FinancialEvent, InternalTransferEvent
from src.domain.exceptions import ProcessingError
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger
from src.processing.data_gaps import DataGapError, GapSeverity
from src.utils.account_utils import account_key

from .base_processor import EventProcessor

logger = logging.getLogger(__name__)

INTERNAL_TRANSFER_PARTIAL = "INTERNAL_TRANSFER_PARTIAL"


def apply_internal_transfer(event: InternalTransferEvent,
                            fifo_ledgers: Dict[Any, FifoLedger],
                            asset_resolver,
                            data_gap_collector=None) -> None:
    """Relocate one move's lots from the sending account's ledger to the receiving one.

    **Only a move of the sending account's WHOLE holding is applied. Anything else stops
    the run.** Which lots left is not in the standard export -- `TransferPrice` is zero
    on every row and the lot-detail rows carry no basis -- and the cheap lots and the
    expensive ones give different tax, so choosing between them would be inventing the
    figure rather than computing it. Refusing names the instrument, the account, the
    date, the quantity moved and the quantity held, so the reader can see the size of
    what is missing. The Flex Query's lot-detail option is what would supply it.

    It goes through the data-gap channel at FAIL_FAST rather than raising directly, so
    the condition reaches the report and not only the log. **One move, not all of them**,
    which is the exception to CLAUDE.md's report-together rule and not an oversight:
    whether a move is whole depends on the ledger at that instant, so there is no state
    in which the later moves could be judged once this one has been refused.

    Long or short is read from the sending ledger, never from the export's sign: the two
    sides of one move carry opposite signs and which side is negative varies by
    instrument (see `RawTransferRecord`). A ledger holding both at once is refused for
    the same reason a partial move is -- nothing says which of the two moved.
    """
    from_account = account_key(event.account_id)
    to_account = account_key(event.to_account_id)
    asset = asset_resolver.get_asset_by_id(event.asset_internal_id) if asset_resolver else None
    name = asset.get_classification_key() if asset else str(event.asset_internal_id)

    source_ledger = fifo_ledgers.get((from_account, event.asset_internal_id))
    target_ledger = fifo_ledgers.get((to_account, event.asset_internal_id))

    if source_ledger is None or target_ledger is None:
        # Both ledgers are registered from the event itself before any ledger is built
        # (`calculation_engine`, `_register_event_accounts`), so a miss here means that
        # registration and this lookup have drifted apart. It is not something to
        # continue through: the units would leave one account and arrive nowhere.
        missing = "sending" if source_ledger is None else "receiving"
        raise ProcessingError(
            f"Internal transfer of {name} on {event.event_date}: no ledger for the "
            f"{missing} account. The move cannot be applied, and applying half of it "
            f"would delete the holding.")

    held_long = sum((lot.quantity for lot in source_ledger.lots), Decimal(0))
    held_short = sum((lot.quantity_shorted for lot in source_ledger.short_lots), Decimal(0))

    if held_long == event.quantity and held_short == Decimal(0):
        moved_long = source_ledger.drain_all_long_lots()
        moved_short: List = []
    elif held_short == event.quantity and held_long == Decimal(0):
        moved_long = []
        moved_short = source_ledger.drain_all_short_lots()
    else:
        subject = f"{name}: {event.quantity} unit(s) moved on {event.event_date}"
        detail = (
            f"Account {event.account_id} held {held_long} long and {held_short} short "
            f"at that moment, so this is not a move of a whole position. Only a whole "
            f"position is supported: the export does not say WHICH units moved -- "
            f"TransferPrice is zero on every row -- and the oldest and the newest lots "
            f"give different gains and different holding periods, so the engine would "
            f"have to invent the answer. Enable the Transfers report's lot-detail "
            f"option so the export carries a basis per lot.")
        if data_gap_collector is not None:
            data_gap_collector.record(
                code=INTERNAL_TRANSFER_PARTIAL, subject=subject, detail=detail,
                severity=GapSeverity.FAIL_FAST,
            )  # records, logs CRITICAL and raises DataGapError
        else:
            raise DataGapError(f"[{INTERNAL_TRANSFER_PARTIAL}] {subject}: {detail}")

    target_ledger.receive_all_lots_from_transfer(moved_long, moved_short)
    logger.info(
        "Internal transfer: relocated %d long + %d short lot(s) of %s from %s to %s on %s.",
        len(moved_long), len(moved_short), name, from_account, to_account, event.event_date)


class InternalTransferProcessor(EventProcessor):
    """The tax year's half of the move. The historical replay calls the same function."""

    def process(self, event: FinancialEvent, ledger: FifoLedger,
                context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, InternalTransferEvent):
            raise ProcessingError(
                f"InternalTransferProcessor received {type(event).__name__}, which "
                f"names no receiving account.")
        apply_internal_transfer(event, context['fifo_ledgers'],
                                context.get('asset_resolver'),
                                context.get('data_gap_collector'))
        # No RealizedGainLoss, and that is the whole point of the change: the move is
        # not a disposal ([GT-ESTG20-014]), so it declares nothing.
        return []

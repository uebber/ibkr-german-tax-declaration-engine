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

The move is placed like the merger: an ordinary member of the chronological stream, at
its own sort position (`sorting_utils.get_event_sort_key` gives it the corporate-action
band so it lands before that day's trades). The one cross-account act is this handover,
and all it does is relocate lot objects -- it reads no figure from the receiving account
and computes nothing in it. Both ledgers exist before it runs
(`calculation_engine._register_event_accounts` registers the sending and receiving
accounts from the event itself).
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from src.domain.events import FinancialEvent, InternalTransferEvent, TransferLot
from src.domain.exceptions import ProcessingError
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger, FifoLot, ShortFifoLot
from src.processing.data_gaps import DataGapError, GapSeverity
from src.utils.account_utils import account_key

from .base_processor import EventProcessor

logger = logging.getLogger(__name__)

INTERNAL_TRANSFER_PARTIAL = "INTERNAL_TRANSFER_PARTIAL"


def _refuse_partial(name: str, event: InternalTransferEvent, detail: str,
                    data_gap_collector) -> None:
    """Route a partial move that cannot be resolved to the report at FAIL_FAST.

    **One move, not all of them**, which is the exception to CLAUDE.md's report-together
    rule and not an oversight: whether a move is applicable depends on the ledger at that
    instant, so there is no state in which the later moves could be judged once this one
    has been refused.
    """
    subject = f"{name}: {event.quantity} unit(s) moved on {event.event_date}"
    if data_gap_collector is not None:
        data_gap_collector.record(
            code=INTERNAL_TRANSFER_PARTIAL, subject=subject, detail=detail,
            severity=GapSeverity.FAIL_FAST,
        )  # records, logs CRITICAL and raises DataGapError
    else:
        raise DataGapError(f"[{INTERNAL_TRANSFER_PARTIAL}] {subject}: {detail}")


def _prepare_by_lot_detail(
        event: InternalTransferEvent, source: FifoLedger, name: str,
        data_gap_collector) -> Tuple[List[FifoLot], List[ShortFifoLot]]:
    """Choose the exact lot objects to move, from the export's per-day lot detail.

    The export writes one `LOT` row per acquisition day. Matching is therefore day-level:
    each row must move a WHOLE acquisition day's holding in the sending ledger. Where a
    row's quantity is less than the day's holding the export has split a day the ledger
    keeps as several lots and does not say which sub-lot went -- inventing it would pick
    the figure (CLAUDE.md's fallback rule), so the run stops. Zero incidence in the
    measured data; the refusal is the residual of what used to reject every partial move.

    Long-versus-short is taken from the sending ledger, which is authoritative; the
    export's per-lot sign is cross-checked against it and a disagreement is logged.
    """
    move_long: List[FifoLot] = []
    move_short: List[ShortFifoLot] = []
    for tl in event.moved_lots:
        day_long = [lot for lot in source.lots if lot.acquisition_date == tl.acquisition_date]
        day_short = [lot for lot in source.short_lots if lot.opening_date == tl.acquisition_date]

        if day_long and not day_short:
            side_short = False
        elif day_short and not day_long:
            side_short = True
        elif day_long and day_short:
            # The ledger holds both a long and a short opened on that day (never observed).
            # The export's sign is the only thing that says which moved; trust it here.
            side_short = tl.is_short
        else:
            _refuse_partial(
                name, event,
                f"the export names a lot acquired {tl.acquisition_date}, but the sending "
                f"account {event.account_id} holds nothing acquired that day. Either the "
                f"move is not from this account or the input is missing a trade.",
                data_gap_collector)
            return move_long, move_short  # unreachable: _refuse_partial raises

        if side_short != tl.is_short:
            logger.warning(
                "Internal transfer of %s on %s: the export marks the %s lot as %s, but "
                "the sending ledger holds it as %s. Using the ledger.",
                name, event.event_date, tl.acquisition_date,
                "short" if tl.is_short else "long", "short" if side_short else "long")

        if side_short:
            day_total = sum((lot.quantity_shorted for lot in day_short), Decimal(0))
            matched = day_short
        else:
            day_total = sum((lot.quantity for lot in day_long), Decimal(0))
            matched = day_long

        if day_total != tl.quantity:
            _refuse_partial(
                name, event,
                f"the export moves {tl.quantity} unit(s) acquired {tl.acquisition_date}, "
                f"but the sending account holds {day_total} acquired that day. A move of "
                f"part of one acquisition day cannot say which units went, and the oldest "
                f"and newest give different gains -- enable the Transfers report's "
                f"lot-detail option per lot, or the move must be of a whole day's holding.",
                data_gap_collector)
            return move_long, move_short  # unreachable

        if side_short:
            move_short.extend(matched)
        else:
            move_long.extend(matched)

    return move_long, move_short


def _prepare_whole_position(
        event: InternalTransferEvent, source: FifoLedger, name: str,
        data_gap_collector) -> Tuple[List[FifoLot], List[ShortFifoLot]]:
    """Move the sending account's whole holding, when the export carried no lot detail.

    The lot-detail columns are required input, so a real export always carries them and
    this path is not reached by one. It remains for a move whose summary stands alone:
    with no lot detail the only unambiguous move is the whole position, and anything else
    stops the run for the same reason a sub-day split does.
    """
    held_long = sum((lot.quantity for lot in source.lots), Decimal(0))
    held_short = sum((lot.quantity_shorted for lot in source.short_lots), Decimal(0))

    if held_long == event.quantity and held_short == Decimal(0):
        return list(source.lots), []
    if held_short == event.quantity and held_long == Decimal(0):
        return [], list(source.short_lots)

    _refuse_partial(
        name, event,
        f"account {event.account_id} held {held_long} long and {held_short} short at that "
        f"moment, so this is not a move of a whole position, and the export carried no "
        f"lot detail to say which units moved. Enable the Transfers report's lot-detail "
        f"option so the export names the lots per acquisition day.",
        data_gap_collector)
    return [], []  # unreachable


def apply_internal_transfer(event: InternalTransferEvent,
                            fifo_ledgers: Dict[Any, FifoLedger],
                            asset_resolver,
                            data_gap_collector=None) -> None:
    """Relocate one move's lots from the sending account's ledger to the receiving one.

    Atomic by construction: the lot objects to move are chosen and validated first
    (`_prepare_*`), touching nothing; only then are they removed from the sending ledger
    and received into the receiving one, and both are pure list operations that cannot
    fail. So a refusal leaves every ledger exactly as it was.
    """
    from_account = account_key(event.account_id)
    to_account = account_key(event.to_account_id)
    asset = asset_resolver.get_asset_by_id(event.asset_internal_id) if asset_resolver else None
    name = asset.get_classification_key() if asset else str(event.asset_internal_id)

    source_ledger = fifo_ledgers.get((from_account, event.asset_internal_id))
    target_ledger = fifo_ledgers.get((to_account, event.asset_internal_id))

    if source_ledger is None or target_ledger is None:
        # Both ledgers are registered from the event itself before any ledger is built
        # (`calculation_engine._register_event_accounts`), so a miss here means that
        # registration and this lookup have drifted apart. It is not something to
        # continue through: the units would leave one account and arrive nowhere.
        missing = "sending" if source_ledger is None else "receiving"
        raise ProcessingError(
            f"Internal transfer of {name} on {event.event_date}: no ledger for the "
            f"{missing} account. The move cannot be applied, and applying half of it "
            f"would delete the holding.")

    # PREPARE (no ledger mutation; raises/records a gap on a move it cannot resolve).
    if event.moved_lots:
        move_long, move_short = _prepare_by_lot_detail(
            event, source_ledger, name, data_gap_collector)
    else:
        move_long, move_short = _prepare_whole_position(
            event, source_ledger, name, data_gap_collector)

    # COMMIT (pure list ops, cannot fail). The objects move intact, so acquisition date,
    # basis, acquisition_date_is_known and accumulated Vorabpauschale travel with them --
    # [GT-ESTG20-014]'s "relocate, don't close and reopen", satisfied structurally.
    source_ledger.remove_relocated_lots(move_long, move_short)
    target_ledger.receive_relocated_lots(move_long, move_short)
    logger.info(
        "Internal transfer: relocated %d long + %d short lot(s) of %s from %s to %s on %s.",
        len(move_long), len(move_short), name, from_account, to_account, event.event_date)


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

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

from src.domain.events import (
    FinancialEvent, InternalTransferEvent, InternalCashTransferEvent)
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


class InternalCashTransferProcessor(EventProcessor):
    """A currency BALANCE moved between the taxpayer's own accounts, in the tax year.

    **The opposite of the class above, and deliberately in the same file so the contrast
    is visible.** A securities move relocates lots and declares nothing
    ([GT-ESTG20-014]); an Umbuchung of a Fremdwaehrungsguthaben is a Veraeusserung of the
    sending account's Kapitalforderung and an Anschaffung of the receiving account's, so
    it realises the currency movement accrued up to that day ([GT-FX-009]).

    **What the two legs are worth.** Both are the gemeiner Wert of the Kapitalforderung
    received, which for an equal amount of one currency is the amount moved
    ([GT-FX-010]); § 20 Abs. 4 Satz 1 zweiter Halbsatz converts it at the day of the move
    ([GT-ESTG20-022]). So the sending account disposes at that EUR value and the
    receiving account acquires at it -- one rate, both sides, no gain created or
    destroyed by the conversion itself.

    That valuation is an **extension** of a principle the administration states only for
    cases it does not name here; Q15 in the store carries both readings, and the map
    records which was taken. It is not a substituted input: the amount and the date are
    both in the export, so nothing about the figure is invented.
    """

    def process(self, event: FinancialEvent, ledger: FifoLedger,
                context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, InternalCashTransferEvent):
            raise ProcessingError(
                f"InternalCashTransferProcessor received {type(event).__name__}, which "
                f"names no receiving account and no amount.")

        asset_resolver = context.get('asset_resolver')
        currency_fifo_ledgers = context.get('currency_fifo_ledgers')
        currency_processor = context.get('currency_processor')
        if asset_resolver is None or currency_fifo_ledgers is None or currency_processor is None:
            raise ProcessingError(
                f"Internal cash transfer {event.event_id} cannot be applied: the currency "
                f"infrastructure is not in the processing context. Skipping it would drop "
                f"a disposal and leave both accounts' balances wrong.")

        currency = (event.local_currency or "").upper()
        currency_asset = asset_resolver.get_cash_balance_asset(currency)
        if currency_asset is None:
            raise ProcessingError(
                f"Internal cash transfer {event.event_id} moves {currency}, for which no "
                f"cash-balance asset exists. The disposal cannot be measured.")

        from_account = account_key(event.account_id)
        to_account = account_key(event.to_account_id)
        source_ledger = currency_fifo_ledgers.get((from_account, currency_asset.internal_asset_id))
        target_ledger = currency_fifo_ledgers.get((to_account, currency_asset.internal_asset_id))
        if source_ledger is None or target_ledger is None:
            # Both are registered from the event itself before any ledger is built
            # (`calculation_engine`, `_register_currency_event_account`), so a miss here
            # means registration and this lookup have drifted apart. Applying half of it
            # would delete the balance.
            missing = "sending" if source_ledger is None else "receiving"
            raise ProcessingError(
                f"Internal cash transfer of {currency} on {event.event_date}: no currency "
                f"ledger for the {missing} account. Applying half the move would make the "
                f"balance disappear.")

        # The amount moved, in EUR at the day of the move. Enrichment already converted
        # it -- the event carries the amount in `gross_amount_foreign_currency` for
        # exactly that reason -- so this is the same figure and the same ECB rate every
        # other event's EUR leg is measured at, not a second conversion path that could
        # disagree with it.
        eur_value = event.gross_amount_eur
        if eur_value is None:
            # No rate, no figure. Raising rather than skipping: a skipped move leaves the
            # sending account holding a balance it no longer has and the receiving one
            # short of what it received, and every later disposal in both is then
            # measured against the wrong lots.
            raise ProcessingError(
                f"Internal cash transfer of {currency} on {event.event_date}: no exchange "
                f"rate for that day, so the disposal and the acquisition cannot be valued "
                f"([GT-FX-010]).")

        eur_per_unit = currency_processor.ctx.divide(eur_value.copy_abs(), event.quantity)

        results: List[RealizedGainLoss] = []
        # The sending side: the balance is disposed of at that EUR value. Reuses the
        # cash-flow expense path, which is the same operation -- long lots consumed FIFO
        # at a given EUR per unit, a short position opened if the account is overdrawn.
        results.extend(currency_processor.realize_long_lots_for_cashflow_expense(
            source_ledger, currency_asset.internal_asset_id, event.event_date,
            event.event_id, event.ibkr_transaction_id,
            min(event.quantity,
                sum((lot.quantity for lot in source_ledger.lots), Decimal(0))),
            eur_per_unit,
        ))
        shortfall = event.quantity - sum(
            (rgl.quantity_realized for rgl in results), Decimal(0))
        if shortfall > Decimal("1e-10"):
            currency_processor.open_short_position_for_cashflow_expense(
                source_ledger, event.event_date, event.ibkr_transaction_id,
                shortfall, eur_per_unit)

        # The receiving side: a new Kapitalforderung acquired at the same value. A short
        # balance there is covered first, which realises its own gain, exactly as an
        # income cash flow does.
        remaining = event.quantity
        open_short = sum((lot.quantity_shorted for lot in target_ledger.short_lots),
                         Decimal(0))
        if open_short > Decimal("0"):
            to_cover = min(remaining, open_short)
            results.extend(currency_processor.cover_short_lots_for_cashflow_income(
                target_ledger, currency_asset.internal_asset_id, event.event_date,
                event.event_id, event.ibkr_transaction_id, to_cover, eur_per_unit))
            remaining -= to_cover
        if remaining > Decimal("1e-10"):
            currency_processor.create_long_lot_for_cashflow_income(
                target_ledger, event.event_date, event.ibkr_transaction_id,
                remaining, eur_per_unit)

        logger.info(
            "Internal cash transfer: %s moved from %s to %s on %s, %d realisation(s).",
            currency, from_account, to_account, event.event_date, len(results))
        return results

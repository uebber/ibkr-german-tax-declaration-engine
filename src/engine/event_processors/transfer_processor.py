"""Coordinate account-local delivery and receipt (GT-ESTG20-014).

Both replay paths use this coordinator. Each ledger prepares only its own state.
All validation and sorting finish before either prepared state is committed.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List

from src.domain.events import (
    FinancialEvent, InternalTransferEvent, InternalCashTransferEvent)
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger
from src.domain.exceptions import ProcessingError
from src.utils.account_utils import account_key
from .base_processor import EventProcessor

logger = logging.getLogger(__name__)


def apply_internal_transfer(event, fifo_ledgers, asset_resolver, data_gap_collector=None):
    source_key = (account_key(event.account_id), event.asset_internal_id)
    target_key = (account_key(event.to_account_id), event.asset_internal_id)
    if source_key == target_key:
        raise ProcessingError('A transfer must name two different accounts')
    source = fifo_ledgers.get(source_key)
    target = fifo_ledgers.get(target_key)
    if source is None or target is None:
        raise ProcessingError('Internal transfer has no sending or receiving ledger')
    asset = asset_resolver.get_asset_by_id(event.asset_internal_id) if asset_resolver else None
    name = asset.get_classification_key() if asset else str(event.asset_internal_id)
    delivery, source_state = source.prepare_transfer_delivery(event, name, data_gap_collector)
    target_state = target.prepare_transfer_receipt(delivery)
    source.commit_transfer_state(source_state)
    target.commit_transfer_state(target_state)


class InternalTransferProcessor(EventProcessor):
    def process(self, event, ledger, context):
        if not isinstance(event, InternalTransferEvent):
            raise ProcessingError('InternalTransferProcessor requires an internal transfer')
        # The processor submits a move to the coordinator; it receives no peer ledger.
        context['transfer_coordinator'](event)
        return []


class InternalCashTransferProcessor(EventProcessor):
    """A currency BALANCE moved between the taxpayer's own accounts, in the tax year.

    **The opposite of the class above, and deliberately in the same file so the contrast
    is visible.** A securities move relocates lots and declares nothing
    ([GT-ESTG20-014]); an Umbuchung of a Fremdwaehrungsguthaben is a Veraeusserung of the
    sending account's Kapitalforderung and an Anschaffung of the receiving account's, so
    it realises the currency movement accrued up to that day ([GT-FX-009]).

    **What the two legs are worth is NOT settled law, and this code takes a side.**
    [GT-FX-010] is an open question, not a rule: no Tier 1 or Tier 2 source values an
    Umbuchung. Reading A is applied -- both legs are the gemeiner Wert of the
    Kapitalforderung received, which for an equal amount of one currency is the amount
    moved, converted at the day of the move (§ 20 Abs. 4 Satz 1 zweiter Halbsatz,
    [GT-ESTG20-022]). So the sending account disposes at that EUR value and the receiving
    account acquires at it -- one rate, both sides, no gain created or destroyed by the
    conversion itself. Reading B, and why it is the weaker, are in the store beside the
    question; the map records the choice and the reason against [GT-FX-010].

    It is a choice between two readings, not a substituted input: the amount and the date
    are both in the export, so nothing about the figure is invented. What is uncertain is
    the law, not the data.
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

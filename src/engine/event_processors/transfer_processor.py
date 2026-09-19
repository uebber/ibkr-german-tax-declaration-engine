"""Coordinate account-local delivery and receipt (GT-ESTG20-014).

Both replay paths use this coordinator. Each ledger prepares only its own state.
All validation and sorting finish before either prepared state is committed.
"""
import logging
from copy import deepcopy
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


class _PreparedCurrencyState:
    """A currency ledger's lot lists, copied so one side of a cash Umbuchung can be
    computed and validated before the real ledger is touched.

    The currency processor's cash-flow methods read and mutate only `.lots` and
    `.short_lots`, so a stand-in carrying copies of those two lists is enough to run a
    disposal or an acquisition without committing it. `commit` assigns the validated lists
    back to the real ledger; it does no work that can fail.
    """

    def __init__(self, ledger: FifoLedger):
        self.lots = deepcopy(ledger.lots)
        self.short_lots = deepcopy(ledger.short_lots)

    def commit(self, ledger: FifoLedger) -> None:
        ledger.lots = self.lots
        ledger.short_lots = self.short_lots


def _dispose_sending_side(currency_processor, state, asset_id, event, eur_per_unit):
    """The sending account disposes its balance at the move's EUR value -- long lots
    consumed FIFO, a short opened if the account is overdrawn. The same operation as a
    cash-flow expense, run on the prepared copy."""
    results = list(currency_processor.realize_long_lots_for_cashflow_expense(
        state, asset_id, event.event_date, event.event_id, event.ibkr_transaction_id,
        min(event.quantity, sum((lot.quantity for lot in state.lots), Decimal(0))),
        eur_per_unit))
    shortfall = event.quantity - sum(
        (rgl.quantity_realized for rgl in results), Decimal(0))
    if shortfall > Decimal("1e-10"):
        currency_processor.open_short_position_for_cashflow_expense(
            state, event.event_date, event.ibkr_transaction_id, shortfall, eur_per_unit)
    return results


def _acquire_receiving_side(currency_processor, state, asset_id, event, eur_per_unit):
    """The receiving account acquires a new Kapitalforderung at the same value; an open
    short there is covered first, exactly as an income cash flow does. Run on the prepared
    copy."""
    results: List[RealizedGainLoss] = []
    remaining = event.quantity
    open_short = sum((lot.quantity_shorted for lot in state.short_lots), Decimal("0"))
    if open_short > Decimal("0"):
        to_cover = min(remaining, open_short)
        results.extend(currency_processor.cover_short_lots_for_cashflow_income(
            state, asset_id, event.event_date, event.event_id, event.ibkr_transaction_id,
            to_cover, eur_per_unit))
        remaining -= to_cover
    if remaining > Decimal("1e-10"):
        currency_processor.create_long_lot_for_cashflow_income(
            state, event.event_date, event.ibkr_transaction_id, remaining, eur_per_unit)
    return results


def _coordinate_cash_umbuchung(source_ledger, target_ledger, dispose_fn, acquire_fn):
    """Prepare both sides of a cash Umbuchung on isolated copies, run each side's lot
    operation on its own copy, and commit both only once both have succeeded.

    The single account-local prepare-then-commit boundary for a currency move -- the mirror
    of `apply_internal_transfer` for securities -- shared by both replay paths. The tax-year
    path (`apply_internal_cash_transfer`) passes the currency processor's cash-flow methods
    and receives the realised results; the historical replay (`apply_historical_cash_transfer`)
    passes the historical consume/create operations, which declare nothing and return no
    results. Which lot operation runs is the caller's; the isolation is here.

    `dispose_fn` and `acquire_fn` each run on a `_PreparedCurrencyState` copy and may raise.
    A receiving-side raise happens before either state is committed, so the sending balance
    is never left disposed of on an aborted run.
    """
    source_state = _PreparedCurrencyState(source_ledger)
    target_state = _PreparedCurrencyState(target_ledger)
    results: List[RealizedGainLoss] = []
    results.extend(dispose_fn(source_state))
    results.extend(acquire_fn(target_state))
    source_state.commit(source_ledger)
    target_state.commit(target_ledger)
    return results


def apply_internal_cash_transfer(event, currency_fifo_ledgers, asset_resolver,
                                 currency_processor) -> List[RealizedGainLoss]:
    """Coordinate a cash Umbuchung account-locally: prepare both sides, then commit.

    The mirror of `apply_internal_transfer` for currency. A cash Umbuchung disposes the
    sending account's Kapitalforderung and acquires the receiving account's ([GT-FX-009],
    [GT-FX-010]); the two effects fall on two ledgers. Each side is computed and validated
    on an ISOLATED copy of its own ledger's lots, and both are committed only once both have
    succeeded -- the same prepare-then-commit boundary the securities transfer uses. A
    failure on the receiving side can no longer leave the sending balance already disposed.

    The valuation (`eur_per_unit`, from `gross_amount_eur` at the day of the move) is the
    same figure the historical replay uses, so the two paths cannot disagree about what a
    move is worth. The historical replay (`apply_historical_cash_transfer`) goes through the
    same prepare-then-commit boundary (`_coordinate_cash_umbuchung`) with the historical lot
    operations, which declare nothing and tag their lots `HIST_`.
    """
    currency = (event.local_currency or "").upper()
    currency_asset = asset_resolver.get_cash_balance_asset(currency)
    if currency_asset is None:
        raise ProcessingError(
            f"Internal cash transfer {event.event_id} moves {currency}, for which no "
            f"cash-balance asset exists. The disposal cannot be measured.")

    from_account = account_key(event.account_id)
    to_account = account_key(event.to_account_id)
    asset_id = currency_asset.internal_asset_id
    source_ledger = currency_fifo_ledgers.get((from_account, asset_id))
    target_ledger = currency_fifo_ledgers.get((to_account, asset_id))
    if source_ledger is None or target_ledger is None:
        # Both are registered from the event itself before any ledger is built
        # (`calculation_engine._register_currency_event_account`), so a miss here means
        # registration and this lookup have drifted apart. Applying half the move would
        # delete the balance.
        missing = "sending" if source_ledger is None else "receiving"
        raise ProcessingError(
            f"Internal cash transfer of {currency} on {event.event_date}: no currency "
            f"ledger for the {missing} account. Applying half the move would make the "
            f"balance disappear.")

    # The amount moved, in EUR at the day of the move. Enrichment already converted it --
    # the event carries it in `gross_amount_foreign_currency` for exactly that reason -- so
    # this is the same figure and the same ECB rate every other event's EUR leg uses.
    eur_value = event.gross_amount_eur
    if eur_value is None:
        # No rate, no figure. Raising rather than skipping: a skipped move leaves the
        # sending account holding a balance it no longer has and the receiving one short of
        # what it received, and every later disposal in both is then measured against the
        # wrong lots.
        raise ProcessingError(
            f"Internal cash transfer of {currency} on {event.event_date}: no exchange rate "
            f"for that day, so the disposal and the acquisition cannot be valued "
            f"([GT-FX-010]).")
    eur_per_unit = currency_processor.ctx.divide(eur_value.copy_abs(), event.quantity)

    results = _coordinate_cash_umbuchung(
        source_ledger, target_ledger,
        dispose_fn=lambda state: _dispose_sending_side(
            currency_processor, state, asset_id, event, eur_per_unit),
        acquire_fn=lambda state: _acquire_receiving_side(
            currency_processor, state, asset_id, event, eur_per_unit))

    logger.info(
        "Internal cash transfer: %s moved from %s to %s on %s, %d realisation(s).",
        currency, from_account, to_account, event.event_date, len(results))
    return results


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

        # The cross-account coordination and the prepare-both-then-commit boundary live in
        # `apply_internal_cash_transfer`, so this processor owns only dispatch. Each side
        # runs on an isolated copy of its ledger and neither is committed until both have
        # succeeded -- a receiving-side failure cannot leave the sending balance disposed.
        return apply_internal_cash_transfer(
            event, currency_fifo_ledgers, asset_resolver, currency_processor)

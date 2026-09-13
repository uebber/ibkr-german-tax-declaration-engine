"""The three stock-award operations on a FIFO ledger.

Every figure here is invented. The real export is not copied, per CLAUDE.md's
public-repo rule; what is reproduced is the SHAPE the broker's export has -- an award
and a partial reversal of it -- because that shape is what the operations are built for.

A vesting has no operation: Zufluss is the booking ([GT-ESTG20-064], BFH VI R 37/09), so
the lot an award creates is already final when the condition later lapses.

Calibration -- run against a deliberately broken tree, with the counts measured rather
than assumed:

* replacing the `quantity > lot.quantity` guard in `reverse_stock_award_lot` with a
  constant false turns **1** red: `test_reversing_more_than_was_awarded_stops_the_run`;
* pricing the reversal at the reversal row's price rather than the lot's own turns **1**
  red: `test_reversal_takes_units_at_the_awarded_cost_and_realises_nothing`.

Each mutant was reverted and the file re-run green before this was written.
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.domain.enums import AssetCategory, FinancialEventType
from src.domain.events import StockAwardEvent
from src.domain.exceptions import ProcessingError
from src.engine.fifo_manager import FifoLedger
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider


ASSET_ID = uuid.uuid4()


def _ledger():
    return FifoLedger(
        asset_internal_id=ASSET_ID,
        asset_category=AssetCategory.STOCK,
        asset_multiplier_from_asset=None,
        currency_converter=MagicMock(spec=CurrencyConverter),
        exchange_rate_provider=MagicMock(spec=ECBExchangeRateProvider),
        internal_working_precision=28,
        decimal_rounding_mode="ROUND_HALF_UP",
    )


def _award(date, award_date, qty, eur_per_unit,
           kind=FinancialEventType.STOCK_AWARD_GRANTED):
    ev = StockAwardEvent(
        ASSET_ID, date, event_type=kind, award_date=award_date,
        quantity=Decimal(qty), unit_price_foreign=Decimal("1"), currency="USD",
        account_id="U_TEST",
    )
    ev.unit_cost_basis_eur = Decimal(eur_per_unit)
    return ev


def test_award_creates_a_lot_on_the_day_the_shares_arrived():
    """Not on the vesting day. The shares are in the account from the award, and a
    ledger that waited would reconstruct short of the broker's snapshot."""
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))

    assert len(led.lots) == 1
    assert led.lots[0].acquisition_date == "2020-03-02"
    assert led.lots[0].quantity == Decimal("10")
    assert led.lots[0].total_cost_basis_eur == Decimal("40")


def test_the_award_lot_is_final_and_no_vesting_operation_exists():
    """Zufluss is the booking ([GT-ESTG20-064], BFH VI R 37/09), so the lot the award
    creates carries its FINAL date and cost. There is deliberately no ledger operation
    for a vesting -- the earlier design restated the lot at vesting, and that reading was
    retired when the Zufluss test was sourced."""
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))

    assert led.lots[0].acquisition_date == "2020-03-02"
    assert led.lots[0].unit_cost_basis_eur == Decimal("4")
    assert not hasattr(led, "restate_stock_award_lot_on_vesting"), (
        "a restatement operation would reintroduce the retired reading")


def test_reversal_takes_units_at_the_awarded_cost_and_realises_nothing():
    """The condition failed, so the award is undone rather than sold. The units leave at
    the lot's own cost, which is what the broker does."""
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))
    result = led.reverse_stock_award_lot(
        _award("2020-09-01", "2020-03-02", "4", "9",
               kind=FinancialEventType.STOCK_AWARD_REVERSED))

    assert result is None, "a reversal is not a disposal and returns no gain"
    assert led.lots[0].quantity == Decimal("6")
    assert led.lots[0].unit_cost_basis_eur == Decimal("4"), "at the awarded cost, not 9"
    assert led.lots[0].total_cost_basis_eur == Decimal("24")


def test_a_full_reversal_removes_the_lot():
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))
    led.reverse_stock_award_lot(
        _award("2020-09-01", "2020-03-02", "10", "4",
               kind=FinancialEventType.STOCK_AWARD_REVERSED))
    assert led.lots == []


def test_two_awards_keep_their_own_costs():
    """Each award is its own lot at its own price. The award date is still the matching
    key, because a reversal names the award it undoes."""
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))
    led.add_lot_for_stock_award(_award("2020-06-01", "2020-06-01", "20", "5"))

    by_award = {lot.source_transaction_id: lot for lot in led.lots}
    assert by_award["STOCK_AWARD:2020-03-02"].unit_cost_basis_eur == Decimal("4")
    assert by_award["STOCK_AWARD:2020-06-01"].unit_cost_basis_eur == Decimal("5")


def test_the_whole_sequence_leaves_the_broker_s_quantity_and_the_awarded_cost():
    """Award, award, partial reversal -- the shape the export has, minus the vestings,
    which no longer touch the ledger.

    Quantity follows the awards and reversals; cost follows the AWARD prices, because
    that is where Zufluss fell.
    """
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))
    led.add_lot_for_stock_award(_award("2020-06-01", "2020-06-01", "20", "5"))
    led.reverse_stock_award_lot(
        _award("2020-09-01", "2020-03-02", "4", "4",
               kind=FinancialEventType.STOCK_AWARD_REVERSED))

    assert sum(lot.quantity for lot in led.lots) == Decimal("26"), "10 + 20 - 4"
    assert sum(lot.total_cost_basis_eur for lot in led.lots) == Decimal("124"), \
        "6 x 4 + 20 x 5 -- the awarded values"


def test_reversing_more_than_was_awarded_stops_the_run():
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))
    with pytest.raises(ProcessingError, match="Reversing more than was awarded"):
        led.reverse_stock_award_lot(
            _award("2020-09-01", "2020-03-02", "11", "4",
                   kind=FinancialEventType.STOCK_AWARD_REVERSED))


def test_two_awards_sharing_an_award_date_stop_the_run():
    """The award date is the matching key, so a duplicate would let a later vesting
    restate the wrong award's shares."""
    led = _ledger()
    led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "10", "4"))
    with pytest.raises(ProcessingError, match="share the award"):
        led.add_lot_for_stock_award(_award("2020-03-02", "2020-03-02", "5", "4"))


def test_a_lot_is_never_created_without_a_eur_cost():
    """The award price is a foreign amount; a lot created before conversion would carry
    an invented acquisition cost into a later disposal."""
    led = _ledger()
    ev = StockAwardEvent(
        ASSET_ID, "2020-03-02", event_type=FinancialEventType.STOCK_AWARD_GRANTED,
        award_date="2020-03-02", quantity=Decimal("10"),
        unit_price_foreign=Decimal("4"), currency="USD", account_id="U_TEST")
    with pytest.raises(ProcessingError, match="without a EUR cost basis"):
        led.add_lot_for_stock_award(ev)

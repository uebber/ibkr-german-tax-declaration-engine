# tests/test_cancelled_trades.py
"""
Cancelled bookings, and the silent default that used to swallow them.

IBKR books a cancellation as its own row: `Buy/Sell` carries the ORIGINAL
trade's direction word with a `(Ca.)` suffix, the quantity is the original's
negated, `Notes/Codes` is `Ca`, and the transaction id is later. A rebooked row
normally follows.

`_determine_trade_event_type` compares `buy_sell` to "BUY" and "SELL" exactly,
so `"BUY (Ca.)"` matched neither and fell through to a branch that logs
"Buy/Sell indicator missing" -- false; the indicator was present and
unrecognised -- and infers direction from the quantity sign. A cancelled
purchase of 200 therefore became a **sale** of 200.

Why that is worse than it sounds. The rebooked row restores the count, so the
end-of-year quantity still reconciles and the engine's one fatal check sees
nothing. What reaches the return is a disposal that never happened, measured
against whichever lots FIFO consumed first.

Both rows in this repository's input sit in 2021, which is imported as history
for every run but declared in none, so no figure was ever wrong. These tests
exist because nothing stops a cancellation appearing in a declared year.
"""
from decimal import Decimal

import pytest

from src.domain.exceptions import DataIntegrityError
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

_ACCOUNT = "U_CANCELLED"
_ISIN = "DE0000000041"


def _trade(date_str, qty, tx_id, buy_sell, open_close, notes=""):
    return [_ACCOUNT, "EUR", "STK", "", "CNCL", "CNCL Stock", _ISIN,
            "", "", "", date_str, qty, "40.00", "-1.00", "EUR",
            buy_sell, tx_id, notes, "", "CON_CNCL", "", "1", open_close]


def _position(qty, position_value, mark_price, cost_basis):
    return [_ACCOUNT, "EUR", "STK", "", "CNCL", "CNCL Stock", _ISIN,
            qty, position_value, mark_price, cost_basis, "", "CON_CNCL", "", "1"]


class TestCancelledBookings(FifoTestCaseBase):

    def test_a_cancelled_purchase_is_not_a_disposal(self, mock_config_paths):
        """
        BUY 100, cancel it, rebook it. Nothing was sold.

        Under the old sign inference the `BUY (Ca.) -100` row became a
        `TRADE_SELL_LONG`, consuming the 2023-02-01 lot and emitting a realised
        gain. The rebooked purchase then restored the quantity, so EOY
        reconciled and the phantom gain went undetected.
        """
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        results = self._run_pipeline(
            trades_data=[
                _trade("2023-02-01", "100", "1000", "BUY", "O"),
                _trade("2023-02-01", "-100", "2000", "BUY (Ca.)", "", notes="Ca"),
                _trade("2023-02-01", "100", "2001", "BUY", "O"),
            ],
            positions_start_data=[],
            positions_end_data=[_position("100", "4500.00", "45.00", "4001.00")],
            custom_rate_provider=mock_provider,
            tax_year=2023,
        )

        assert results.realized_gains_losses == [], (
            "a cancelled purchase produced a disposal: "
            f"{results.realized_gains_losses}")


def _raw(qty, tx_id, buy_sell, open_close=""):
    """A RawTradeRecord with only the fields these two rules read."""
    from src.parsers.raw_models import RawTradeRecord
    return RawTradeRecord.parse_obj({
        "CurrencyPrimary": "EUR", "AssetClass": "STK", "Symbol": "CNCL",
        "Description": "CNCL Stock", "ISIN": _ISIN, "Conid": "CON_CNCL",
        "TradeDate": "2023-02-01", "Quantity": qty, "TradePrice": "40.00",
        "Buy/Sell": buy_sell, "TransactionID": tx_id,
        "Open/CloseIndicator": open_close,
    })


class TestTheRulesThemselves:
    """
    Asserted directly rather than through the pipeline: the shared test harness
    converts a `DataIntegrityError` into `pytest.fail`, so `pytest.raises`
    cannot see one raised inside a run.
    """

    def test_an_unmatched_cancellation_stops_the_run(self):
        """
        A cancellation whose booking is absent cannot be applied, and guessing
        its direction is the defect this change removes. It raises instead.
        """
        from src.parsers.parsing_orchestrator import _drop_cancelled_trade_pairs

        with pytest.raises(DataIntegrityError, match="no booking to cancel"):
            _drop_cancelled_trade_pairs([
                _raw("100", "1000", "BUY", "O"),
                _raw("-250", "2000", "BUY (Ca.)"),   # cancels 250, never booked
            ])

    def test_a_matched_cancellation_removes_both_rows(self):
        from src.parsers.parsing_orchestrator import _drop_cancelled_trade_pairs

        kept = _drop_cancelled_trade_pairs([
            _raw("100", "1000", "BUY", "O"),
            _raw("-100", "2000", "BUY (Ca.)"),
            _raw("100", "2001", "BUY", "O"),
        ])
        assert [r.transaction_id for r in kept] == ["2001"]

    def test_a_cancellation_matches_only_an_earlier_booking(self):
        """
        The rebooked row carries the same direction and quantity as the
        original, so ordering is what makes the match unique. Both real
        instances in this repository's input rely on it.
        """
        from src.parsers.parsing_orchestrator import _drop_cancelled_trade_pairs

        kept = _drop_cancelled_trade_pairs([
            _raw("100", "1000", "BUY", "O"),     # the original
            _raw("-100", "2000", "BUY (Ca.)"),
            _raw("100", "3000", "BUY", "O"),     # the rebook, later than the cancellation
        ])
        assert [r.transaction_id for r in kept] == ["3000"]

    def test_an_unrecognised_direction_stops_the_run(self):
        """
        Present-but-unrecognised is not the same as absent. A booking kind the
        engine has never seen must not have its direction guessed from a sign:
        the direction decides acquisition versus disposal.
        """
        from src.parsers.domain_event_factory import DomainEventFactory

        factory = DomainEventFactory.__new__(DomainEventFactory)
        with pytest.raises(DataIntegrityError, match="unrecognised Buy/Sell value"):
            factory._determine_trade_event_type(_raw("-100", "1001", "TRANSFER OUT", "C"))

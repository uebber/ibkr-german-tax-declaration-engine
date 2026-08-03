"""
Tests for FX RGL Hardening (Issues A–D)

Tests for defensive guards on currency FIFO ledger initialization, sign convention
enforcement, and cross-currency documentation compliance.

Issue A: SOY rate fallback raises ValueError instead of using 1:1
Issue B: Commission FX parity (existing behavior, test coverage only)
Issue C: Cross-currency independent EUR valuations (documentation, no code change)
Issue D: gross_amount_foreign_currency sign convention guard
"""

import pytest
import uuid
import logging
from decimal import Decimal, Context
from datetime import date
from unittest.mock import MagicMock

from src.domain.assets import CashBalance
from src.domain.enums import AssetCategory, FinancialEventType
from src.engine.fifo_manager import FifoLedger, FifoLot
from src.engine.calculation_engine import (
    _initialize_currency_soy_ledger,
    _reconcile_currency_soy,
)


# =============================================================================
# Helpers
# =============================================================================

CTX = Context(prec=28, rounding="ROUND_HALF_UP")


def _make_cash_balance(currency: str, soy_quantity: Decimal,
                       soy_cost_basis: Decimal = None) -> CashBalance:
    """Create a CashBalance asset for testing."""
    return CashBalance(
        currency=currency,
        soy_quantity=soy_quantity,
        soy_cost_basis_amount=soy_cost_basis,
    )


def _make_empty_ledger() -> FifoLedger:
    """Create an empty FifoLedger with minimal mocking."""
    mock_converter = MagicMock()
    mock_provider = MagicMock()
    return FifoLedger(
        asset_internal_id=uuid.uuid4(),
        asset_category=AssetCategory.CASH_BALANCE,
        asset_multiplier_from_asset=None,
        currency_converter=mock_converter,
        exchange_rate_provider=mock_provider,
        internal_working_precision=28,
        decimal_rounding_mode="ROUND_HALF_UP",
    )


class NoneRateProvider:
    """Exchange rate provider that always returns None (simulates missing ECB data)."""
    def get_rate(self, date_of_conversion, currency_code):
        return None

    def prefetch_rates(self, *args, **kwargs):
        pass


class SelectiveRateProvider:
    """Exchange rate provider that returns None for specific currencies."""
    def __init__(self, rates: dict):
        self._rates = rates  # {currency: rate_value_or_None}

    def get_rate(self, date_of_conversion, currency_code):
        return self._rates.get(currency_code.upper())

    def prefetch_rates(self, *args, **kwargs):
        pass


# =============================================================================
# Issue A: SOY Rate Fallback Raises ValueError
# =============================================================================

class TestIssueA_SoyRateFallback:
    """_initialize_currency_soy_ledger and _reconcile_currency_soy must raise
    ValueError when ECB rate is unavailable, instead of silently using 1:1."""

    def test_initialize_soy_raises_when_ecb_rate_is_none(self):
        """SOY initialization must fail loudly when ECB rate is None."""
        asset = _make_cash_balance("USD", Decimal("10000"))
        ledger = _make_empty_ledger()

        with pytest.raises(ValueError, match="No ECB rate available for SOY date"):
            _initialize_currency_soy_ledger(ledger, asset, 2023, NoneRateProvider(), CTX)

    def test_initialize_soy_raises_when_ecb_rate_is_zero(self):
        """SOY initialization must fail loudly when ECB rate is zero."""
        asset = _make_cash_balance("USD", Decimal("10000"))
        ledger = _make_empty_ledger()
        provider = SelectiveRateProvider({"USD": Decimal("0")})

        with pytest.raises(ValueError, match="No ECB rate available for SOY date"):
            _initialize_currency_soy_ledger(ledger, asset, 2023, provider, CTX)

    def test_initialize_soy_succeeds_with_valid_rate(self):
        """SOY initialization works normally when ECB rate is available."""
        asset = _make_cash_balance("USD", Decimal("10000"))
        ledger = _make_empty_ledger()
        # 1 EUR = 1.10 USD => rate returned is 1.10
        provider = SelectiveRateProvider({"USD": Decimal("1.10")})

        _initialize_currency_soy_ledger(ledger, asset, 2023, provider, CTX)

        assert len(ledger.lots) == 1
        assert ledger.lots[0].quantity == Decimal("10000")

    def test_initialize_soy_skips_zero_quantity(self):
        """SOY initialization does nothing for zero quantity (no error needed)."""
        asset = _make_cash_balance("USD", Decimal("0"))
        ledger = _make_empty_ledger()

        # Should not raise even with NoneRateProvider since qty is 0
        _initialize_currency_soy_ledger(ledger, asset, 2023, NoneRateProvider(), CTX)
        assert len(ledger.lots) == 0

    def test_reconcile_soy_raises_when_ecb_rate_is_none(self):
        """SOY reconciliation must fail loudly when ECB rate is None."""
        asset = _make_cash_balance("USD", Decimal("5000"))
        ledger = _make_empty_ledger()
        # Ledger has no lots, SOY says 5000 => diff of 5000 => needs rate

        with pytest.raises(ValueError, match="No ECB rate available for SOY reconciliation"):
            _reconcile_currency_soy(ledger, asset, 2023, NoneRateProvider(), CTX)

    def test_reconcile_soy_raises_when_ecb_rate_is_zero(self):
        """SOY reconciliation must fail loudly when ECB rate is zero."""
        asset = _make_cash_balance("USD", Decimal("5000"))
        ledger = _make_empty_ledger()
        provider = SelectiveRateProvider({"USD": Decimal("0")})

        with pytest.raises(ValueError, match="No ECB rate available for SOY reconciliation"):
            _reconcile_currency_soy(ledger, asset, 2023, provider, CTX)

    def test_reconcile_soy_skips_when_balanced(self):
        """SOY reconciliation does nothing when FIFO matches reported SOY."""
        asset = _make_cash_balance("USD", Decimal("5000"))
        ledger = _make_empty_ledger()
        # Pre-populate ledger to match SOY
        ledger.lots.append(FifoLot(
            acquisition_date="2022-12-31",
            quantity=Decimal("5000"),
            unit_cost_basis_eur=Decimal("0.90"),
            total_cost_basis_eur=Decimal("4500"),
            source_transaction_id="EXISTING",
        ))

        # Should not raise even with NoneRateProvider since diff is 0
        _reconcile_currency_soy(ledger, asset, 2023, NoneRateProvider(), CTX)


# =============================================================================
# Issue D: Sign Convention Guard
# =============================================================================

class TestIssueD_SignConventionGuard:
    """Sign convention: gross_amount_foreign_currency on a TradeEvent is ALWAYS
    non-negative — direction is encoded in event_type. The factory normalizes the
    sign with copy_abs(), so a SELL row's negative qty*price becomes a positive
    gross.

    The `raise ValueError` below that construction is unreachable: copy_abs() on
    the preceding line makes its condition unsatisfiable, and deleting the whole
    block leaves the suite green. It is not exercised here because it cannot be.
    Removing it would be an application-code change and is raised for the
    maintainer rather than made here."""

    def test_factory_normalizes_sell_row_to_positive_gross(self):
        """A SELL trade row must yield a TradeEvent whose direction lives in
        event_type, whose quantity stays signed, and whose gross is POSITIVE —
        exercised through the real parse_trades_csv → DomainEventFactory path.

        legal_basis: infrastructure. No declared figure depends on this test:
        it pins an internal sign convention, not a tax outcome.

        Scope, measured rather than assumed: the abs is applied twice on this
        path (once when gross is derived from |qty| * price, once again at
        construction). Removing either alone changes nothing, and removing both
        fails a large part of the suite. So this test adds no detection the suite
        lacks; what it adds is fidelity — the previous version constructed a
        TradeEvent by hand and asserted the value it had just passed in,
        exercising no part of the factory."""
        from src.parsers.trades_parser import parse_trades_csv
        from src.parsers.domain_event_factory import DomainEventFactory
        from src.identification.asset_resolver import AssetResolver
        from src.classification.asset_classifier import AssetClassifier
        from src.domain.events import TradeEvent
        from tests.support.csv_creators import create_trades_csv_string
        import tempfile, os

        sell_row = [
            "U_TEST", "USD", "STK", "COMMON", "ABC", "ABC Inc", "US000000ABC1",
            "", "", "", "20230615", "-100", "50.00", "1.00", "USD",
            "SELL", "T_SELL_1", "", "", "CONABC", "", "1", "C",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trades.csv")
            with open(path, "w", encoding="utf-8-sig") as fh:
                fh.write(create_trades_csv_string([sell_row]))
            raw = parse_trades_csv(path)
            resolver = AssetResolver(asset_classifier=AssetClassifier(
                cache_file_path=os.path.join(tmp, "cls.json")))
            events, _candidates, _stock = DomainEventFactory(resolver).create_events_from_trades(raw)

        trades = [e for e in events if isinstance(e, TradeEvent)]
        assert len(trades) == 1
        ev = trades[0]
        assert ev.event_type == FinancialEventType.TRADE_SELL_LONG  # direction lives here
        assert ev.quantity < Decimal("0")                            # signed quantity kept
        assert ev.gross_amount_foreign_currency == Decimal("5000.00")  # |qty| * price, POSITIVE

    def test_historical_replay_warns_on_negative_foreign_amount(self, caplog):
        """Historical replay logs warning for negative gross_amount_foreign_currency."""
        from src.engine.calculation_engine import _replay_historical_currency_events

        # Create a TradeEvent with negative gross (bypassing factory guard)
        from src.domain.events import TradeEvent
        trade = TradeEvent(
            asset_internal_id=uuid.uuid4(),
            event_date="2023-03-15",
            event_type=FinancialEventType.TRADE_BUY_LONG,
            quantity=Decimal("100"),
            price_foreign_currency=Decimal("50.00"),
            commission_foreign_currency=Decimal("0"),
            commission_currency="USD",
            local_currency="USD",
            gross_amount_foreign_currency=Decimal("-5000"),  # negative!
            gross_amount_eur=Decimal("-4500"),
            ibkr_transaction_id="BAD_TRADE",
        )

        ledger = _make_empty_ledger()
        mock_converter = MagicMock()
        with caplog.at_level(logging.WARNING):
            _replay_historical_currency_events([trade], ledger, "USD", mock_converter, CTX)

        assert any("negative" in msg.lower() and "gross_amount_foreign_currency" in msg
                    for msg in caplog.messages), \
            f"Expected warning about negative gross_amount_foreign_currency, got: {caplog.messages}"

    def test_historical_replay_skips_negative_without_corruption(self):
        """Historical replay skips negative-amount trades without modifying ledger."""
        from src.engine.calculation_engine import _replay_historical_currency_events
        from src.domain.events import TradeEvent

        trade = TradeEvent(
            asset_internal_id=uuid.uuid4(),
            event_date="2023-03-15",
            event_type=FinancialEventType.TRADE_SELL_LONG,
            quantity=Decimal("100"),
            price_foreign_currency=Decimal("50.00"),
            commission_foreign_currency=Decimal("0"),
            commission_currency="USD",
            local_currency="USD",
            gross_amount_foreign_currency=Decimal("-5000"),
            gross_amount_eur=Decimal("-4500"),
            ibkr_transaction_id="BAD_SELL",
        )

        ledger = _make_empty_ledger()
        # Pre-populate a lot
        ledger.lots.append(FifoLot(
            acquisition_date="2023-01-01",
            quantity=Decimal("10000"),
            unit_cost_basis_eur=Decimal("0.90"),
            total_cost_basis_eur=Decimal("9000"),
            source_transaction_id="EXISTING",
        ))

        mock_converter = MagicMock()
        replayed = _replay_historical_currency_events([trade], ledger, "USD", mock_converter, CTX)

        # The negative trade should have been skipped
        assert replayed == 0
        # Ledger should be unchanged
        assert len(ledger.lots) == 1
        assert ledger.lots[0].quantity == Decimal("10000")

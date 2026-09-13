"""
A share purchase's transaction tax (stamp duty) is part of what the shares cost.

legal_basis: § 20 Abs. 4 Satz 1 EStG computes the gain as proceeds minus
Anschaffungskosten; § 255 Abs. 1 Satz 2 HGB includes the Nebenkosten in the
Anschaffungskosten. So a transaction tax paid to acquire a security -- UK Stamp
Duty, Hong Kong stamp duty -- raises the cost basis of the acquired lot and, being
a foreign-cash outflow, the currency the purchase consumed ([GT-ESTG20-066]).

All identifiers and amounts are invented.
"""
from decimal import Decimal

import pytest

from src.domain.enums import RealizationType
from src.domain.events import TradeEvent
from src.domain.exceptions import DataIntegrityError
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import (
    cash_balance_row, fx_trade_row, position_row, trade_row)

ACCOUNT = "U10000001"
TAX_YEAR = 2025


class _RatePerDate(MockECBExchangeRateProvider):
    """EUR per unit of the foreign currency, per date (ECB's reciprocal is stored)."""

    def __init__(self, eur_per_unit_by_date, default=Decimal("1.00")):
        super().__init__(default)
        self._by_date = {d: Decimal("1") / Decimal(str(r))
                         for d, r in eur_per_unit_by_date.items()}

    def get_rate(self, rate_date, currency):
        if currency and currency.upper() == "EUR":
            return Decimal("1")
        return self._by_date.get(rate_date.isoformat(),
                                 super().get_rate(rate_date, currency))


def _usd_cash_position(account, quantity, cost_basis_eur):
    """A USD cash balance in a Positions snapshot -- where a balance's cost comes from."""
    q = Decimal(str(quantity))
    unit = Decimal(str(cost_basis_eur)) / q if q else Decimal("1")
    return [account, "USD", "CASH", "", "USD", "Cash Balance USD", "", q,
            q * unit, unit, Decimal(str(cost_basis_eur)), None, None, None, Decimal("1")]


class TestTheTaxJoinsTheCostBasis(FifoTestCaseBase):
    """A EUR buy with a stamp tax: the tax raises the lot cost and lowers the sale gain."""

    ISIN = "DE000000TAX1"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(ACCOUNT, self.ISIN, "2025-01-10", "100", "10", "BUY", "O",
                          "T_BUY", currency="EUR", commission="-1", taxes="-5"),
                trade_row(ACCOUNT, self.ISIN, "2025-06-10", "-100", "12", "SELL", "C",
                          "T_SELL", currency="EUR", commission="-1", taxes="0"),
            ],
            positions_end_data=[],
            tax_year=TAX_YEAR,
        )

    def test_the_sale_gain_is_reduced_by_the_purchase_tax(self):
        out = self._run()
        sales = [r for r in out.realized_gains_losses
                 if r.realization_type == RealizationType.LONG_POSITION_SALE]
        assert len(sales) == 1, out.realized_gains_losses
        # cost basis = 100*10 + 1 commission + 5 tax = 1006 (without the tax it is 1001)
        assert sales[0].total_cost_basis_eur == Decimal("1006")
        # proceeds = 100*12 - 1 commission = 1199; gain = 1199 - 1006 = 193 (else 198)
        assert sales[0].gross_gain_loss_eur == Decimal("193")


class TestTheTaxConsumesForeignCurrency(FifoTestCaseBase):
    """A USD buy's tax draws USD like the commission does, realising FX on the balance."""

    ISIN = "US000000TAX1"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                # buy 1 share @ 100 USD, no commission, 10 USD stamp tax, rate 1.00
                trade_row(ACCOUNT, self.ISIN, "2025-06-01", "1", "100", "BUY", "O",
                          "T_BUY", currency="USD", commission="0", taxes="-10"),
            ],
            positions_start_data=[_usd_cash_position(ACCOUNT, "1000", "800")],  # 0.80 EUR/USD
            positions_end_data=[
                position_row(ACCOUNT, self.ISIN, "1", "110", currency="USD", price="100"),
                _usd_cash_position(ACCOUNT, "890", "712"),  # 1000 - 110 consumed
            ],
            cash_balance_data=[cash_balance_row(ACCOUNT, "USD", "1000", "890", year=TAX_YEAR)],
            custom_rate_provider=_RatePerDate({"2025-06-01": "1.00"}),
            tax_year=TAX_YEAR,
        )

    def test_the_tax_is_part_of_the_currency_consumed(self):
        out = self._run()
        # The tax's currency consumption realises FX under the cashflow-expense type, like
        # the commission's, not the security-purchase type -- so sum all FX on the USD
        # balance rather than filtering by one realisation type.
        usd_ids = {a.internal_asset_id
                   for a in out.asset_resolver.assets_by_internal_id.values()
                   if a.__class__.__name__ == "CashBalance"
                   and getattr(a, "currency", None) == "USD"}
        fx = [r for r in out.realized_gains_losses if r.asset_internal_id in usd_ids]
        # consumed 100 (gross) + 10 (tax) = 110 USD, at (1.00 - 0.80) = +0.20 EUR/USD -> +22 EUR.
        # Without the tax only 100 USD is consumed -> +20 EUR.
        total = sum((r.gross_gain_loss_eur for r in fx), Decimal(0))
        assert total == Decimal("22"), fx


class TestAHistoricalPurchaseTaxReachesTheGain(FifoTestCaseBase):
    """The real case: a prior-year buy carrying a tax, sold in the tax year.

    The buy is reconstructed in the historical replay -- a different path from the
    current-year one -- so this guards that a historical lot's cost basis carries the
    tax too. Without it the gain on the tax-year sale is overstated by the tax.
    """

    ISIN = "DE000000TAX2"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                # Prior-year buy with a 5 EUR stamp tax, held into the tax year.
                trade_row(ACCOUNT, self.ISIN, "2024-06-01", "100", "10", "BUY", "O",
                          "H_BUY", currency="EUR", commission="0", taxes="-5"),
                # Tax-year sale of the whole holding.
                trade_row(ACCOUNT, self.ISIN, "2025-06-10", "-100", "12", "SELL", "C",
                          "T_SELL", currency="EUR", commission="0", taxes="0"),
            ],
            positions_start_data=[position_row(ACCOUNT, self.ISIN, "100", "1005",
                                               currency="EUR", price="10")],
            positions_end_data=[],
            tax_year=TAX_YEAR,
        )

    def test_the_historical_tax_lowers_the_tax_year_gain(self):
        out = self._run()
        sales = [r for r in out.realized_gains_losses
                 if r.realization_type == RealizationType.LONG_POSITION_SALE]
        assert len(sales) == 1, out.realized_gains_losses
        # cost basis = 100*10 + 5 tax = 1005 (without the tax it is 1000)
        assert sales[0].total_cost_basis_eur == Decimal("1005")
        # proceeds 1200 - cost 1005 = 195 (without the tax, 200)
        assert sales[0].gross_gain_loss_eur == Decimal("195")


class TestAHistoricalPurchaseTaxLeavesNoCurrencyGap(FifoTestCaseBase):
    """The GBP case in miniature: a prior-year foreign buy's tax, consumed in the
    historical currency replay, so the reconstructed opening balance matches the
    broker's and the start-of-year reconciliation has nothing to sweep.

    This moves no declared figure -- the reconciliation would otherwise trim the same
    FIFO lots -- so it is asserted on the reconciliation itself: without the
    historical-replay tax the ledger over-reconstructs by the tax and logs a
    start-of-year reconciliation gap for the currency.
    """

    ISIN = "US000000TAX2"

    def test_no_soy_reconciliation_gap_for_the_currency(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="src.engine.calculation_engine"):
            self._run_pipeline(
                trades_data=[
                    # 2024: convert EUR into 1000 USD, then buy a USD share for 500 USD
                    # plus a 50 USD stamp tax -> 550 USD consumed, 450 USD left.
                    fx_trade_row(ACCOUNT, "USD", "BUY", "1000", "1000", "1.00",
                                 "2024-01-15", "H_FX"),
                    trade_row(ACCOUNT, self.ISIN, "2024-06-01", "5", "100", "BUY", "O",
                              "H_BUY", currency="USD", commission="0", taxes="-50"),
                ],
                positions_start_data=[
                    position_row(ACCOUNT, self.ISIN, "5", "550", currency="USD", price="100"),
                    _usd_cash_position(ACCOUNT, "450", "450"),
                ],
                positions_end_data=[
                    position_row(ACCOUNT, self.ISIN, "5", "550", currency="USD", price="100"),
                    _usd_cash_position(ACCOUNT, "450", "450"),
                ],
                cash_balance_data=[cash_balance_row(ACCOUNT, "USD", "450", "450",
                                                    year=TAX_YEAR)],
                custom_rate_provider=_RatePerDate({"2024-01-15": "1.00",
                                                   "2024-06-01": "1.00"}),
                tax_year=TAX_YEAR,
            )
        gaps = [r.message for r in caplog.records
                if "SOY reconciliation" in r.message and "USD" in r.message]
        assert gaps == [], gaps


class TestAPositionFlipSplitsTheTax:
    """A position-flip trade (C;O) carrying a tax must split the tax onto both sub-events,
    like the commission -- otherwise the flip's sub-events lose the tax's currency
    consumption (the cost basis rides in the split net, but the tax fields do not unless
    propagated). Zero incidence in the data; guarded so it cannot regress silently.
    """

    def test_the_flip_split_carries_the_tax_proportionally(self):
        import uuid
        from src.domain.enums import FinancialEventType
        from src.engine.fifo_manager import split_position_flip_event

        ev = TradeEvent(
            asset_internal_id=uuid.uuid4(),
            event_date="2025-06-01",
            event_type=FinancialEventType.TRADE_BUY_SHORT_COVER,
            quantity=Decimal("10"),
            price_foreign_currency=Decimal("100"),
            commission_foreign_currency=Decimal("-2"),
            commission_currency="USD",
            transaction_tax_foreign=Decimal("-10"),
            transaction_tax_eur=Decimal("-10"),
            local_currency="USD",
            gross_amount_foreign_currency=Decimal("1000"),
            gross_amount_eur=Decimal("1000"),
            net_proceeds_or_cost_basis_eur=Decimal("1012"),
            is_position_flip=True,
        )
        # 4 of 10 covers the short (close), 6 opens the new long.
        subs = split_position_flip_event(ev, available_long_qty=Decimal("0"),
                                         available_short_qty=Decimal("4"))
        assert len(subs) == 2
        by_qty = {s.quantity.copy_abs(): s for s in subs}
        assert by_qty[Decimal("4")].transaction_tax_foreign == Decimal("-4")
        assert by_qty[Decimal("6")].transaction_tax_foreign == Decimal("-6")
        # the split is exhaustive, in EUR too
        assert (by_qty[Decimal("4")].transaction_tax_eur
                + by_qty[Decimal("6")].transaction_tax_eur) == Decimal("-10")


class TestASellSideTaxStopsTheRun:
    """No sale in the data carries a tax; one raises rather than guessing a sign.

    Tested at the factory: the scenario harness converts an exception into a test
    failure, which would make the refusal unassertable (the grants refusals are tested
    the same way).
    """

    def test_a_non_zero_tax_on_a_sale_raises(self):
        from unittest.mock import MagicMock
        from src.domain.enums import AssetCategory
        from src.identification.asset_resolver import AssetResolver
        from src.parsers.column_validator import TRADES_COLUMNS
        from src.parsers.domain_event_factory import DomainEventFactory
        from src.parsers.raw_models import RawTradeRecord

        classifier = MagicMock()
        classifier.preliminary_classify.return_value = (AssetCategory.STOCK, None)
        factory = DomainEventFactory(AssetResolver(classifier))
        row = RawTradeRecord(**dict(zip(
            TRADES_COLUMNS,
            trade_row(ACCOUNT, "GB000000TAX1", "2025-06-10", "-100", "12", "SELL", "C",
                      "T_SELL", currency="EUR", taxes="-5"))))

        with pytest.raises(DataIntegrityError, match="on a SALE"):
            factory.create_events_from_trades([row])

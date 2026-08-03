"""
Guards around the §23 Jahresfrist rule introduced by the HoldingPeriod domain rule.

Three properties, none of which the shipped rule had:

1. The domain rule refuses a disposal that precedes the acquisition instead of
   answering "within the period" for it. §23 measures *"der Zeitraum zwischen
   Anschaffung und Veraeusserung"*; that is undefined in the other direction, and a
   disposal genuinely preceding an acquisition is §23 Abs. 1 S. 1 Nr. 3 (short
   sale), a separate rule with no holding period at all.

2. `FifoLedger` raises rather than reporting EXEMPT when the dates cannot decide the
   question. The previous behaviour — carried over unchanged from the day-count code
   — was to fall through to
   `SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET`, i.e. to leave a taxable disposal out
   of Anlage SO on the strength of a date the engine could not read. CLAUDE.md's
   error-handling rule: a wrong number that looks plausible is worse than a crash.

3. `RealizedGainLoss.is_within_speculation_period` reports the Jahresfrist answer.
   `__post_init__` used to overwrite it with an unconditional True for every
   PRIVATE_SALE_ASSET, so it read "within the speculation period" on the very
   disposals the engine had just classified as exempt — while
   reference/tax-law/estg-23-private-veraeusserung.md documented that field as what
   drives the §23 category.

legal_basis: GT-ESTG23-003 (§108 Abs. 1 AO i.V.m. §§187 Abs. 1, 188 Abs. 2-3
BGB) and GT-ESTG23-012 (an undecidable §23 case raises rather than defaulting
to exempt); reference/tax-law/estg-23-private-veraeusserung.md.
"""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.domain.enums import AssetCategory, FinancialEventType, TaxReportingCategory
from src.domain.events import TradeEvent
from src.domain.exceptions import ProcessingError
from src.engine.fifo_manager import FifoLedger, FifoLot
from src.tax_law.holding_period import is_within_section23_speculation_period
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider


def _ledger(category: AssetCategory) -> FifoLedger:
    return FifoLedger(
        asset_internal_id=uuid.uuid4(),
        asset_category=category,
        asset_multiplier_from_asset=None,
        currency_converter=MagicMock(spec=CurrencyConverter),
        exchange_rate_provider=MagicMock(spec=ECBExchangeRateProvider),
        internal_working_precision=28,
        decimal_rounding_mode="ROUND_HALF_UP",
    )


def _sell(asset_id, date_str: str, qty: str, proceeds_eur: str) -> TradeEvent:
    return TradeEvent(
        asset_internal_id=asset_id,
        event_date=date_str,
        event_type=FinancialEventType.TRADE_SELL_LONG,
        quantity=-Decimal(qty),
        price_foreign_currency=Decimal("0"),
        net_proceeds_or_cost_basis_eur=Decimal(proceeds_eur),
    )


def _lot(acq_date: str, qty: str, unit_cost: str) -> FifoLot:
    q, u = Decimal(qty), Decimal(unit_cost)
    return FifoLot(acquisition_date=acq_date, quantity=q, unit_cost_basis_eur=u,
                   total_cost_basis_eur=q * u, source_transaction_id="BUY1")


class TestRuleRejectsUndefinedDirection:

    def test_disposal_before_acquisition_raises(self):
        with pytest.raises(ProcessingError, match="precedes the acquisition"):
            is_within_section23_speculation_period(date(2024, 1, 1), date(2023, 12, 31))

    def test_same_day_is_still_answered(self):
        """The boundary the guard must not swallow: a same-day flip is within."""
        assert is_within_section23_speculation_period(date(2023, 5, 10), date(2023, 5, 10)) is True


class TestLedgerRefusesUndecidableSection23:

    def test_unparseable_acquisition_date_raises_instead_of_exempting(self):
        ledger = _ledger(AssetCategory.PRIVATE_SALE_ASSET)
        ledger.lots.append(_lot("not-a-date", "10", "100"))
        with pytest.raises(ProcessingError, match="Cannot decide §23 taxability"):
            ledger.consume_long_lots_for_sale(
                _sell(ledger.asset_internal_id, "2024-07-01", "10", "1200"))

    def test_disposal_dated_before_the_lot_raises_instead_of_exempting(self):
        ledger = _ledger(AssetCategory.PRIVATE_SALE_ASSET)
        ledger.lots.append(_lot("2024-01-01", "10", "100"))
        with pytest.raises(ProcessingError, match="Cannot decide §23 taxability"):
            ledger.consume_long_lots_for_sale(
                _sell(ledger.asset_internal_id, "2023-12-31", "10", "1200"))

    def test_guard_is_scoped_to_section23_assets(self):
        """A STOCK disposal with the same unusable dates is unaffected: no §23
        decision is being made, holding_period_days is simply unknown."""
        ledger = _ledger(AssetCategory.STOCK)
        ledger.lots.append(_lot("not-a-date", "10", "100"))
        rgls = ledger.consume_long_lots_for_sale(
            _sell(ledger.asset_internal_id, "2024-07-01", "10", "1200"))
        assert len(rgls) == 1
        assert rgls[0].holding_period_days is None
        assert rgls[0].is_within_speculation_period is False


class TestSpeculationPeriodFlagIsTruthful:

    def test_flag_is_true_on_a_taxable_disposal(self):
        ledger = _ledger(AssetCategory.PRIVATE_SALE_ASSET)
        ledger.lots.append(_lot("2023-07-01", "10", "100"))
        rgl = ledger.consume_long_lots_for_sale(
            _sell(ledger.asset_internal_id, "2024-07-01", "10", "1200"))[0]
        assert rgl.tax_reporting_category == TaxReportingCategory.SECTION_23_ESTG_TAXABLE_GAIN
        assert rgl.is_within_speculation_period is True

    def test_flag_is_false_on_an_exempt_disposal(self):
        """This is the assertion that fails against the unconditional True."""
        ledger = _ledger(AssetCategory.PRIVATE_SALE_ASSET)
        ledger.lots.append(_lot("2023-07-01", "10", "100"))
        rgl = ledger.consume_long_lots_for_sale(
            _sell(ledger.asset_internal_id, "2024-07-02", "10", "1200"))[0]
        assert rgl.tax_reporting_category == TaxReportingCategory.SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET
        assert rgl.is_within_speculation_period is False

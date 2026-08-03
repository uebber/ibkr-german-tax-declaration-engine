"""
§23 Abs. 1 Nr. 2 EStG — the one-year speculation period (Jahresfrist).

legal_basis: GT-ESTG23-003 (reference/tax-law/estg-23-private-veraeusserung.md).
The period is
computed per §108 AO in conjunction with §§187 Abs. 1, 188 Abs. 2 BGB. It ends
with the EXPIRY OF THE ANNIVERSARY DAY of the acquisition in the following
year: a disposal ON the anniversary day is still within the period (taxable);
the first exempt day is the day after. If the anniversary day does not exist
(acquisition on 29 February), the period ends with the last day of February
(§188 Abs. 3 BGB).

This is NOT equivalent to counting calendar days: across a leap day the
anniversary lies 366 days after acquisition and the disposal is STILL taxable.
A `days <= 365` shortcut therefore wrongly exempts an anniversary-day sale
whenever the holding spans 29 February — the bug these tests pin.

Existing CTX_P23_001..005 specs (group 5) cover only non-leap spans, where the
day-count shortcut and the statutory rule coincide; they remain valid.
"""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.engine.fifo_manager import FifoLedger, FifoLot
from src.tax_law.holding_period import is_within_section23_speculation_period
from src.domain.enums import AssetCategory, FinancialEventType, TaxReportingCategory
from src.domain.events import TradeEvent
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider


# ---------------------------------------------------------------------------
# Unit level: the Jahresfrist rule itself
# ---------------------------------------------------------------------------

class TestSpeculationPeriodRule:

    @pytest.mark.parametrize("acq, real, within", [
        # Non-leap span: anniversary day taxable, day after exempt
        (date(2022, 3, 15), date(2023, 3, 15), True),
        (date(2022, 3, 15), date(2023, 3, 16), False),
        # THE bug: leap span (29.02.2024 in between) — anniversary is 366 days
        # after acquisition and STILL within the period.
        (date(2023, 7, 1), date(2024, 7, 1), True),
        (date(2023, 7, 1), date(2024, 7, 2), False),
        # Acquisition on 29 February: period ends 28.02 of the following year
        # (§188 Abs. 3 BGB — last day of the month when the day is missing).
        (date(2024, 2, 29), date(2025, 2, 28), True),
        (date(2024, 2, 29), date(2025, 3, 1), False),
        # Same-day flip is trivially within the period.
        (date(2023, 5, 10), date(2023, 5, 10), True),
        # Feb-28 acquisition in a pre-leap year: anniversary 28.02 next year.
        (date(2023, 2, 28), date(2024, 2, 28), True),
        (date(2023, 2, 28), date(2024, 2, 29), False),
    ])
    def test_anniversary_rule(self, acq, real, within):
        assert is_within_section23_speculation_period(acq, real) is within


# ---------------------------------------------------------------------------
# Ledger level: the rule drives the §23 tax category on the RGL
# ---------------------------------------------------------------------------

def _private_sale_ledger() -> FifoLedger:
    return FifoLedger(
        asset_internal_id=uuid.uuid4(),
        asset_category=AssetCategory.PRIVATE_SALE_ASSET,
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


class TestSection23LedgerClassification:

    def test_leap_year_anniversary_sale_is_taxable(self):
        """Buy 2023-07-01, sell 2024-07-01 (366 days, spans 29.02.2024): the
        anniversary-day sale is WITHIN the Jahresfrist -> taxable."""
        ledger = _private_sale_ledger()
        ledger.lots.append(_lot("2023-07-01", "10", "100"))
        rgls = ledger.consume_long_lots_for_sale(
            _sell(ledger.asset_internal_id, "2024-07-01", "10", "1200"))
        assert len(rgls) == 1
        assert rgls[0].is_taxable_under_section_23 is True
        assert rgls[0].tax_reporting_category == TaxReportingCategory.SECTION_23_ESTG_TAXABLE_GAIN

    def test_day_after_leap_year_anniversary_is_exempt(self):
        """Sell one day later (2024-07-02): outside the period -> exempt."""
        ledger = _private_sale_ledger()
        ledger.lots.append(_lot("2023-07-01", "10", "100"))
        rgls = ledger.consume_long_lots_for_sale(
            _sell(ledger.asset_internal_id, "2024-07-02", "10", "1200"))
        assert len(rgls) == 1
        assert rgls[0].is_taxable_under_section_23 is False
        assert rgls[0].tax_reporting_category == TaxReportingCategory.SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET

    def test_non_leap_anniversary_still_taxable(self):
        """Regression guard for the already-correct non-leap case
        (mirrors CTX_P23_001): buy 2022-03-15, sell 2023-03-15 -> taxable."""
        ledger = _private_sale_ledger()
        ledger.lots.append(_lot("2022-03-15", "10", "100"))
        rgls = ledger.consume_long_lots_for_sale(
            _sell(ledger.asset_internal_id, "2023-03-15", "10", "1200"))
        assert rgls[0].is_taxable_under_section_23 is True
        assert rgls[0].tax_reporting_category == TaxReportingCategory.SECTION_23_ESTG_TAXABLE_GAIN

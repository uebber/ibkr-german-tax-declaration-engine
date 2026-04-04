# tests/test_vorabpauschale.py
"""Tests for Vorabpauschale calculation (§ 18 InvStG)."""
import uuid
import pytest
from decimal import Decimal, Context
from datetime import date
from unittest.mock import MagicMock
from collections import defaultdict

from src.domain.assets import InvestmentFund, Asset
from src.domain.enums import (
    AssetCategory, InvestmentFundType, FinancialEventType, TaxReportingCategory,
)
from src.domain.events import CashFlowEvent
from src.domain.results import VorabpauschaleData, LossOffsettingResult
from src.engine.calculation_engine import _calculate_vorabpauschale, _get_vp_reporting_category
from src.engine.loss_offsetting import LossOffsettingEngine
from src.identification.asset_resolver import AssetResolver
from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type
import src.config as config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fund(
    fund_type=InvestmentFundType.AKTIENFONDS,
    soy_qty=Decimal("100"),
    soy_position_value=Decimal("10000"),
    soy_mark_price_currency="EUR",
    eoy_position_value=Decimal("11000"),
    eoy_mark_price_currency="EUR",
    eoy_qty=Decimal("100"),
    currency="EUR",
    description="Test Fund",
) -> InvestmentFund:
    fund = InvestmentFund(
        fund_type=fund_type,
        description=description,
        currency=currency,
        ibkr_isin="IE00TEST1234",
        ibkr_symbol="TFUND",
    )
    fund.soy_quantity = soy_qty
    fund.soy_position_value = soy_position_value
    fund.soy_mark_price_currency = soy_mark_price_currency
    fund.soy_market_price = soy_position_value / soy_qty if soy_qty else None
    fund.eoy_quantity = eoy_qty
    fund.eoy_position_value = eoy_position_value
    fund.eoy_mark_price_currency = eoy_mark_price_currency
    fund.eoy_market_price = eoy_position_value / eoy_qty if eoy_qty else None
    return fund


def _make_distribution(asset_id: uuid.UUID, gross_eur: Decimal, event_date: str = "2024-06-15") -> CashFlowEvent:
    ev = CashFlowEvent(
        asset_internal_id=asset_id,
        event_date=event_date,
        event_type=FinancialEventType.DISTRIBUTION_FUND,
        gross_amount_foreign_currency=gross_eur,
        local_currency="EUR",
    )
    ev.gross_amount_eur = gross_eur
    return ev


def _eur_converter():
    """Currency converter that returns amounts as-is for EUR."""
    converter = MagicMock()
    converter.convert_to_eur.side_effect = lambda amount, currency, dt: amount if currency == "EUR" else None
    return converter


def _fx_converter(rate: Decimal):
    """Currency converter that divides by `rate` for non-EUR currencies."""
    converter = MagicMock()
    def _convert(amount, currency, dt):
        if currency == "EUR":
            return amount
        return amount / rate
    converter.convert_to_eur.side_effect = _convert
    return converter


def _make_resolver_with_fund(fund: InvestmentFund) -> AssetResolver:
    resolver = MagicMock(spec=AssetResolver)
    resolver.assets_by_internal_id = {fund.internal_asset_id: fund}
    return resolver


def _run_vp(fund, events=None, tax_year=2024, converter=None):
    resolver = _make_resolver_with_fund(fund)
    if converter is None:
        converter = _eur_converter()
    ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION, rounding=config.DECIMAL_ROUNDING_MODE)
    return _calculate_vorabpauschale(
        asset_resolver=resolver,
        current_year_events=events or [],
        currency_converter=converter,
        tax_year=tax_year,
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Tests: _get_vp_reporting_category
# ---------------------------------------------------------------------------

class TestGetVpReportingCategory:
    def test_aktienfonds(self):
        assert _get_vp_reporting_category(InvestmentFundType.AKTIENFONDS) == TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO

    def test_mischfonds(self):
        assert _get_vp_reporting_category(InvestmentFundType.MISCHFONDS) == TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_VORABPAUSCHALE_BRUTTO

    def test_immobilienfonds(self):
        assert _get_vp_reporting_category(InvestmentFundType.IMMOBILIENFONDS) == TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO

    def test_auslands_immobilienfonds(self):
        assert _get_vp_reporting_category(InvestmentFundType.AUSLANDS_IMMOBILIENFONDS) == TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO

    def test_sonstige(self):
        assert _get_vp_reporting_category(InvestmentFundType.SONSTIGE_FONDS) == TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO

    def test_none_maps_to_sonstige(self):
        assert _get_vp_reporting_category(InvestmentFundType.NONE) == TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO


# ---------------------------------------------------------------------------
# Tests: _calculate_vorabpauschale
# ---------------------------------------------------------------------------

class TestVorabpauschaleCalculation:
    """Core VP calculation tests."""

    def test_positive_value_gain_no_distributions(self):
        """VP = Basisertrag (capped by value gain)."""
        # SoY=10000, EoY=11000 -> value gain=1000
        # Basiszins 2024=2.29%, rate=0.0229, Basisertrag=10000*0.0229*0.7=160.30
        # No distributions -> VP = min(160.30, 1000) = 160.30
        fund = _make_fund()
        results = _run_vp(fund)
        assert len(results) == 1
        vp = results[0]
        assert vp.gross_vorabpauschale_eur == Decimal("160.30")
        assert vp.tax_year == 2024

    def test_distributions_exceed_basisertrag(self):
        """If distributions >= Basisertrag, VP = 0."""
        fund = _make_fund()
        dist = _make_distribution(fund.internal_asset_id, Decimal("200"))
        results = _run_vp(fund, events=[dist])
        assert len(results) == 0

    def test_distributions_less_than_basisertrag(self):
        """VP = Basisertrag - distributions."""
        fund = _make_fund()
        # Basisertrag = 160.30, distribution = 50 -> VP = 110.30
        dist = _make_distribution(fund.internal_asset_id, Decimal("50"))
        results = _run_vp(fund, events=[dist])
        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur == Decimal("110.30")

    def test_negative_value_gain_caps_vp_to_zero(self):
        """If EoY < SoY (negative value gain), VP = 0 due to cap."""
        fund = _make_fund(eoy_position_value=Decimal("9000"))  # value loss
        results = _run_vp(fund)
        assert len(results) == 0

    def test_value_gain_caps_vp(self):
        """VP capped at value gain when value gain < Basisertrag."""
        # SoY=10000, EoY=10050 -> value gain=50
        # Basisertrag=160.30 > 50, so VP = 50
        fund = _make_fund(eoy_position_value=Decimal("10050"))
        results = _run_vp(fund)
        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur == Decimal("50.00")

    def test_no_soy_position_no_vp(self):
        """Fund not held at SoY -> no VP."""
        fund = _make_fund(soy_qty=Decimal("0"))
        results = _run_vp(fund)
        assert len(results) == 0

    def test_no_eoy_position_no_vp(self):
        """Fund sold during year (no EoY position) -> no VP."""
        fund = _make_fund(eoy_position_value=None, eoy_qty=None)
        results = _run_vp(fund)
        assert len(results) == 0

    def test_no_basiszins_configured(self):
        """Tax year without basiszins -> no VP."""
        fund = _make_fund()
        results = _run_vp(fund, tax_year=2020)
        assert len(results) == 0

    def test_teilfreistellung_applied_aktienfonds(self):
        """TF rate of 30% applied for Aktienfonds."""
        fund = _make_fund(fund_type=InvestmentFundType.AKTIENFONDS)
        results = _run_vp(fund)
        assert len(results) == 1
        vp = results[0]
        assert vp.teilfreistellung_rate_applied == Decimal("0.30")
        expected_tf = (vp.gross_vorabpauschale_eur * Decimal("0.30")).quantize(Decimal("0.01"))
        assert vp.teilfreistellung_amount_eur == expected_tf
        expected_net = vp.gross_vorabpauschale_eur - expected_tf
        assert vp.net_taxable_vorabpauschale_eur == expected_net

    def test_teilfreistellung_applied_mischfonds(self):
        """TF rate of 15% applied for Mischfonds."""
        fund = _make_fund(fund_type=InvestmentFundType.MISCHFONDS)
        results = _run_vp(fund)
        assert len(results) == 1
        assert results[0].teilfreistellung_rate_applied == Decimal("0.15")

    def test_teilfreistellung_applied_immobilienfonds(self):
        """TF rate of 60% applied for Immobilienfonds."""
        fund = _make_fund(fund_type=InvestmentFundType.IMMOBILIENFONDS)
        results = _run_vp(fund)
        assert len(results) == 1
        assert results[0].teilfreistellung_rate_applied == Decimal("0.60")

    def test_teilfreistellung_applied_sonstige(self):
        """TF rate of 0% for Sonstige Fonds."""
        fund = _make_fund(fund_type=InvestmentFundType.SONSTIGE_FONDS)
        results = _run_vp(fund)
        assert len(results) == 1
        assert results[0].teilfreistellung_rate_applied == Decimal("0.00")
        assert results[0].net_taxable_vorabpauschale_eur == results[0].gross_vorabpauschale_eur

    def test_non_eur_fund_currency_conversion(self):
        """VP for USD-denominated fund with currency conversion."""
        # USD/EUR rate = 1.10 (1 EUR = 1.10 USD)
        fund = _make_fund(
            soy_position_value=Decimal("11000"),  # 11000 USD
            soy_mark_price_currency="USD",
            eoy_position_value=Decimal("12100"),  # 12100 USD
            eoy_mark_price_currency="USD",
            currency="USD",
        )
        rate = Decimal("1.10")
        converter = _fx_converter(rate)
        results = _run_vp(fund, converter=converter)
        assert len(results) == 1
        vp = results[0]
        # SoY EUR = 11000/1.10 = 10000, EoY EUR = 12100/1.10 = 11000
        # Same as EUR test: Basisertrag = 10000*0.0229*0.7 = 160.30
        assert vp.gross_vorabpauschale_eur == Decimal("160.30")

    def test_reporting_category_set(self):
        """tax_reporting_category_gross is correctly set."""
        fund = _make_fund(fund_type=InvestmentFundType.AKTIENFONDS)
        results = _run_vp(fund)
        assert len(results) == 1
        assert results[0].tax_reporting_category_gross == TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO

    def test_distributions_during_year_recorded(self):
        """distributions_during_year_eur field populated correctly."""
        fund = _make_fund()
        dist = _make_distribution(fund.internal_asset_id, Decimal("50"))
        results = _run_vp(fund, events=[dist])
        assert len(results) == 1
        assert results[0].distributions_during_year_eur == Decimal("50.00")

    def test_basiszins_and_base_return_rate_stored(self):
        """Basiszins and base_return_rate fields populated."""
        fund = _make_fund()
        results = _run_vp(fund)
        assert results[0].basiszins == Decimal("2.29")
        assert results[0].base_return_rate == Decimal("0.0229")

    def test_only_positive_distributions_reduce_basisertrag(self):
        """Negative distributions (reversals) should not reduce Basisertrag."""
        fund = _make_fund()
        neg_dist = _make_distribution(fund.internal_asset_id, Decimal("-20"))
        results = _run_vp(fund, events=[neg_dist])
        assert len(results) == 1
        # Negative distribution not counted, so VP = full Basisertrag (capped)
        assert results[0].gross_vorabpauschale_eur == Decimal("160.30")


# ---------------------------------------------------------------------------
# Tests: TF on negative distributions (loss_offsetting fix)
# ---------------------------------------------------------------------------

class TestTeilfreistellungNegativeDistribution:
    """Verify TF is applied symmetrically for negative distributions."""

    def _run_net_distribution(self, gross_eur: Decimal, fund_type=InvestmentFundType.AKTIENFONDS):
        fund = _make_fund(fund_type=fund_type)
        resolver = MagicMock(spec=AssetResolver)
        resolver.assets_by_internal_id = {fund.internal_asset_id: fund}
        resolver.get_asset_by_id.return_value = fund

        engine = LossOffsettingEngine(
            realized_gains_losses=[],
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=resolver,
            tax_year=2024,
        )
        event = _make_distribution(fund.internal_asset_id, gross_eur)
        return engine._calculate_net_fund_distribution(event, fund)

    def test_positive_distribution_tf(self):
        """Positive distribution: net = gross - TF."""
        net = self._run_net_distribution(Decimal("100"))
        # 100 - 100*0.30 = 70
        assert net == Decimal("70.00")

    def test_negative_distribution_tf(self):
        """Negative distribution: net = gross + TF (symmetric)."""
        net = self._run_net_distribution(Decimal("-100"))
        # -100 + 100*0.30 = -70
        assert net == Decimal("-70.00")

    def test_zero_distribution(self):
        net = self._run_net_distribution(Decimal("0"))
        assert net == Decimal("0.00")


# ---------------------------------------------------------------------------
# Tests: Z55 in loss offsetting
# ---------------------------------------------------------------------------

class TestZ55VorabpauschaleAbzug:
    """Verify Z55 correctly sums all gross VP."""

    def test_z55_sums_gross_vp(self):
        """Z55 = sum of all gross VP for the tax year."""
        vp1 = VorabpauschaleData(
            asset_internal_id=uuid.uuid4(), tax_year=2024,
            fund_value_start_year_eur=Decimal("10000"), fund_value_end_year_eur=Decimal("11000"),
            distributions_during_year_eur=Decimal("0"), base_return_rate=Decimal("0.0229"),
            basiszins=Decimal("2.29"), calculated_base_return_eur=Decimal("160.30"),
            gross_vorabpauschale_eur=Decimal("160.30"),
            fund_type=InvestmentFundType.AKTIENFONDS,
            teilfreistellung_rate_applied=Decimal("0.30"),
            teilfreistellung_amount_eur=Decimal("48.09"),
            net_taxable_vorabpauschale_eur=Decimal("112.21"),
            tax_reporting_category_gross=TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO,
        )
        vp2 = VorabpauschaleData(
            asset_internal_id=uuid.uuid4(), tax_year=2024,
            fund_value_start_year_eur=Decimal("5000"), fund_value_end_year_eur=Decimal("5500"),
            distributions_during_year_eur=Decimal("0"), base_return_rate=Decimal("0.0229"),
            basiszins=Decimal("2.29"), calculated_base_return_eur=Decimal("80.15"),
            gross_vorabpauschale_eur=Decimal("80.15"),
            fund_type=InvestmentFundType.MISCHFONDS,
            teilfreistellung_rate_applied=Decimal("0.15"),
            teilfreistellung_amount_eur=Decimal("12.02"),
            net_taxable_vorabpauschale_eur=Decimal("68.13"),
            tax_reporting_category_gross=TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_VORABPAUSCHALE_BRUTTO,
        )

        resolver = MagicMock(spec=AssetResolver)
        resolver.get_asset_by_id.return_value = None

        engine = LossOffsettingEngine(
            realized_gains_losses=[],
            vorabpauschale_items=[vp1, vp2],
            current_year_financial_events=[],
            asset_resolver=resolver,
            tax_year=2024,
        )
        result = engine.calculate_reporting_figures()

        z55 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z55, Decimal("0"))
        assert z55 == Decimal("240.45")

    def test_z55_zero_when_no_vp(self):
        """Z55 = 0 when no VP items."""
        resolver = MagicMock(spec=AssetResolver)
        resolver.get_asset_by_id.return_value = None

        engine = LossOffsettingEngine(
            realized_gains_losses=[],
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=resolver,
            tax_year=2024,
        )
        result = engine.calculate_reporting_figures()

        z55 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z55, Decimal("0"))
        assert z55 == Decimal("0.00")

    def test_fund_income_includes_net_vp(self):
        """conceptual_fund_income_net_taxable includes net VP."""
        vp = VorabpauschaleData(
            asset_internal_id=uuid.uuid4(), tax_year=2024,
            fund_value_start_year_eur=Decimal("10000"), fund_value_end_year_eur=Decimal("11000"),
            distributions_during_year_eur=Decimal("0"), base_return_rate=Decimal("0.0229"),
            basiszins=Decimal("2.29"), calculated_base_return_eur=Decimal("160.30"),
            gross_vorabpauschale_eur=Decimal("160.30"),
            fund_type=InvestmentFundType.AKTIENFONDS,
            teilfreistellung_rate_applied=Decimal("0.30"),
            teilfreistellung_amount_eur=Decimal("48.09"),
            net_taxable_vorabpauschale_eur=Decimal("112.21"),
            tax_reporting_category_gross=TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO,
        )

        resolver = MagicMock(spec=AssetResolver)
        resolver.get_asset_by_id.return_value = None

        engine = LossOffsettingEngine(
            realized_gains_losses=[],
            vorabpauschale_items=[vp],
            current_year_financial_events=[],
            asset_resolver=resolver,
            tax_year=2024,
        )
        result = engine.calculate_reporting_figures()
        assert result.conceptual_fund_income_net_taxable == Decimal("112.21")

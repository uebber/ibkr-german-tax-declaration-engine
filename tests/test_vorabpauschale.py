# tests/test_vorabpauschale.py
"""Tests for the Vorabpauschale (§ 18 InvStG).

legal_basis: GT-INVSTG-010 (Basisertrag and its cap), GT-INVSTG-012 and
GT-INVSTG-014 (the VZ Y return carries the figure for calendar Y-1),
GT-INVSTG-015 (declared gross), GT-INVSTG-033 and GT-FORM-033 (the deduction
on disposal is Zeile 53, and is not computed), GT-INVSTG-050/053 (Basiszins).
See reference/investment-tax-law/invstg-18-vorabpauschale.md and
docs/legal-implementation-map.md.
"""
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
from src.domain.results import VorabpauschaleData, LossOffsettingResult, RealizedGainLoss
from src.domain.enums import RealizationType
from src.processing.data_gaps import DataGapCollector, GapSeverity
from datetime import date as dt_date

from src.engine.calculation_engine import (
    FundUnitTranche,
    _calculate_vorabpauschale,
    _collect_fund_distributions_for_year,
    _get_vp_reporting_category,
)
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
    # The Vorabpauschale reads the PRECEDING calendar year's snapshot: the VP declared in
    # VZ Y is the one for calendar Y-1 (18 Abs. 3 InvStG). These fixtures therefore populate
    # `prior_year_*` and deliberately leave `soy_*` / `eoy_*` unset -- if the engine ever
    # reverts to reading the tax year's own snapshot, every test in this module fails.
    fund.prior_year_soy_quantity = soy_qty
    fund.prior_year_soy_position_value = soy_position_value
    fund.prior_year_soy_mark_price = (soy_position_value / soy_qty
                                      if soy_position_value is not None and soy_qty else None)
    fund.prior_year_soy_mark_price_currency = soy_mark_price_currency
    fund.prior_year_eoy_position_value = eoy_position_value
    fund.prior_year_eoy_mark_price = (eoy_position_value / eoy_qty
                                      if eoy_position_value is not None and eoy_qty else None)
    fund.prior_year_eoy_mark_price_currency = eoy_mark_price_currency
    fund.prior_year_eoy_quantity = eoy_qty
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


def _make_vp_item(vorabpauschale_year: int,
                  fund_type=InvestmentFundType.AKTIENFONDS) -> VorabpauschaleData:
    """A Vorabpauschale FOR calendar `vorabpauschale_year` (declared the following VZ)."""
    return VorabpauschaleData(
        asset_internal_id=uuid.uuid4(),
        vorabpauschale_year=vorabpauschale_year,
        fund_value_start_year_eur=Decimal("10000"), fund_value_end_year_eur=Decimal("11000"),
        distributions_during_year_eur=Decimal("0"), base_return_rate=Decimal("0.0229"),
        basiszins=Decimal("2.29"), calculated_base_return_eur=Decimal("160.30"),
        gross_vorabpauschale_eur=Decimal("160.30"),
        fund_type=fund_type,
        teilfreistellung_rate_applied=Decimal("0.30"),
        teilfreistellung_amount_eur=Decimal("48.09"),
        net_taxable_vorabpauschale_eur=Decimal("112.21"),
        tax_reporting_category_gross=TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO,
    )


def _make_fund_disposal(category=AssetCategory.INVESTMENT_FUND) -> RealizedGainLoss:
    """A minimal realised disposal, used to make Zeile 53 relevant."""
    rgl = RealizedGainLoss(
        originating_event_id=uuid.uuid4(),
        asset_internal_id=uuid.uuid4(),
        asset_category_at_realization=category,
        acquisition_date="2022-01-01",
        realization_date="2024-06-01",
        realization_type=RealizationType.LONG_POSITION_SALE,
        quantity_realized=Decimal("1"),
        unit_cost_basis_eur=Decimal("100"),
        unit_realization_value_eur=Decimal("150"),
        total_cost_basis_eur=Decimal("100"),
        total_realization_value_eur=Decimal("150"),
        gross_gain_loss_eur=Decimal("50"),
    )
    if category == AssetCategory.INVESTMENT_FUND:
        rgl.fund_type_at_sale = InvestmentFundType.AKTIENFONDS
        rgl.__post_init__()
    return rgl


def _make_resolver_with_fund(fund: InvestmentFund) -> AssetResolver:
    resolver = MagicMock(spec=AssetResolver)
    resolver.assets_by_internal_id = {fund.internal_asset_id: fund}
    return resolver


def _run_vp(fund, events=None, vorabpauschale_year=2024, converter=None,
            acquisition_date=None, collector=None):
    """Compute the Vorabpauschale FOR calendar `vorabpauschale_year`.

    Note this is the year the VP is *for*, not the Veranlagungszeitraum it is declared in --
    those differ by one (18 Abs. 3 InvStG). Distributions are routed through the production
    collector rather than a hand-built dict, so its calendar-year filter and its
    positive-amounts-only rule remain covered by these tests.
    """
    resolver = _make_resolver_with_fund(fund)
    if converter is None:
        converter = _eur_converter()
    ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION, rounding=config.DECIMAL_ROUNDING_MODE)
    distributions = _collect_fund_distributions_for_year(
        events or [], vorabpauschale_year, resolver, ctx
    )
    # Units held at the close of the Vorabpauschale year (Rz. 18.4). `acquisition_date`
    # defaults to well before the year, so no 18 Abs. 2 reduction applies -- the shape
    # every test here assumed when the count came from the snapshot. Pass it to exercise
    # a mid-year purchase, which is the only way Abs. 2 reaches a declared figure.
    held_at_year_end = fund.prior_year_eoy_quantity
    if acquisition_date is None:
        acquisition_date = dt_date(vorabpauschale_year - 3, 5, 20)
    lots = {fund.internal_asset_id: [FundUnitTranche(
        quantity=held_at_year_end,
        acquisition_date=acquisition_date)]} if held_at_year_end else {}
    return _calculate_vorabpauschale(
        asset_resolver=resolver,
        distributions_by_asset=distributions,
        currency_converter=converter,
        vorabpauschale_year=vorabpauschale_year,
        opening_lots_by_asset=lots,
        ctx=ctx,
        data_gap_collector=collector,
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
        assert vp.vorabpauschale_year == 2024

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

    def test_no_eoy_position_no_vp(self):
        """Fund sold during year (no EoY position) -> no VP.

        legal_basis: Rz. 18.4 [GT-INVSTG-017], and [GT-INVSTG-016] as its
        consequence — the multiplier is the holding at the close of
        31 December, so a fund disposed of in full is multiplied by nothing.
        Settled 2026-08-07; formerly open question Q5. **This one is correct**,
        unlike the year-*start* case in TestAFundAcquiredDuringTheYear below.
        """
        fund = _make_fund(eoy_position_value=None, eoy_qty=None)
        results = _run_vp(fund)
        assert len(results) == 0

    def test_unconfigured_basiszins_year_skips_with_loud_warning(self, caplog):
        """A tax year INSIDE the InvStG-2018 regime with no configured Basiszins
        must skip VP computation with a WARNING (skipping silently could
        understate income — the VP is deemed income under §18 InvStG).
        (Previously this used 2020, which HAS a published positive Basiszins of
        0.07% — see BMF table — and logged only at INFO level.)"""
        import logging
        fund = _make_fund()
        with caplog.at_level(logging.INFO):
            results = _run_vp(fund, vorabpauschale_year=2030)
        assert len(results) == 0
        assert any("Basiszins" in r.message and r.levelname == "WARNING" for r in caplog.records), \
            "missing Basiszins must be surfaced as a WARNING, not silently skipped"

    def test_pre_2018_year_skips_without_a_false_alarm(self, caplog):
        """1999 predates the InvStG 2018 regime (§56 Abs. 1 S. 1 InvStG): there
        was no Vorabpauschale, so the skip is correct and must not be reported
        as a missing rate."""
        import logging
        fund = _make_fund()
        with caplog.at_level(logging.INFO):
            results = _run_vp(fund, vorabpauschale_year=1999)
        assert len(results) == 0
        assert not any(r.levelname == "WARNING" for r in caplog.records)

    def test_2020_positive_basiszins_yields_vp(self):
        """2020 had a POSITIVE Basiszins (0.07%, BMF) — a fund held through
        2020 owes VP: 10000 * 0.0007 * 0.7 = 4.90 (cap 1000 not binding)."""
        fund = _make_fund()
        results = _run_vp(fund, vorabpauschale_year=2020)
        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur == Decimal("4.90")

    def test_2021_negative_basiszins_yields_zero_vp_not_skip(self, caplog):
        """2021 Basiszins was NEGATIVE (-0.45%, BMF): the correct result is a
        COMPUTED zero (negative Basisertrag -> no VP), not a config-gap skip."""
        import logging
        fund = _make_fund()
        with caplog.at_level(logging.INFO):
            results = _run_vp(fund, vorabpauschale_year=2021)
        assert len(results) == 0
        assert not any("No Basiszins configured" in r.message for r in caplog.records), \
            "2021 must be configured (negative rate), not treated as a config gap"

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
# Tests: a fund bought during the Vorabpauschale year
# ---------------------------------------------------------------------------

class TestAFundAcquiredDuringTheYear:
    """Bought mid-year, still held at 31 December. Three rules meet here.

    Replaces `test_no_soy_position_no_vp`, whose docstring read *"Fund not held
    at SoY -> no VP"*. That is not the law: § 18 Abs. 2 **reduces** the
    Vorabpauschale for units bought during the year, it does not remove it, and
    Rz. 18.4 counts the units held at the *close*. The old test also conflated
    two different facts — it set `soy_qty=0`, which the fixture helper turns
    into a missing *price* — so it pinned the skip path while claiming to pin a
    rule about quantity. It dates from `a1c7bf0`, before Rz. 18.4, before the
    Abs. 2 pro-rata, and before the 2026-08-07 audit closed Q5 and Q13.

    What is covered where, so no rule is assumed to be someone else's job:

    | Rule | Says | Engine | Guarded |
    |---|---|---|---|
    | Rz. 18.4 [GT-INVSTG-017] | multiplier is the units held at the close of 31 Dec | implements | here, and `test_vorabpauschale_price_and_units.py` |
    | § 18 Abs. 2 [GT-INVSTG-011] | 12 twelfths less one per full month before the month of acquisition | implements | the twelfths in `test_vorabpauschale_abs2.py`; **their effect on a declared figure only here** |
    | § 18 Abs. 1 S. 2 [GT-INVSTG-010] | Basisertrag from the Rücknahmepreis at the start of the year | cannot: no export carries it for a fund not held then | issue #65; the silence about it is #55 |

    The Abs. 2 row is why this class exists rather than one more case in the
    file above. Measured 2026-08-08: replacing the engine's
    `if twelfths != 12:` reduction with `if False:` left all 869 tests green.
    `test_vorabpauschale_abs2.py` exercises `FundUnitTranche` in isolation, so
    the engine could stop applying the result and nothing observed it.
    """

    # 100 units at a year-start price of 100: 100 * 0.0229 * 0.7 = 1.603 per unit,
    # under the Satz 3 cap of (110 - 100) = 10, so 160.30 for a full twelve twelfths.
    FULL_YEAR_VP = Decimal("160.30")

    @pytest.mark.parametrize("month,twelfths,expected", [
        (1, 12, Decimal("160.30")),   # no full month precedes January
        (7, 6, Decimal("80.15")),     # January to June are six full months
        (12, 1, Decimal("13.36")),    # a December purchase still attracts one twelfth
    ])
    def test_abs2_reduces_the_declared_figure(self, month, twelfths, expected):
        """The pro-rata reaches the figure, not just the helper that computes it."""
        fund = _make_fund()
        results = _run_vp(fund, acquisition_date=dt_date(2024, month, 15))

        assert len(results) == 1, "a mid-year purchase is entitled to a reduced VP, not none"
        assert results[0].gross_vorabpauschale_eur == expected
        assert expected == (self.FULL_YEAR_VP * twelfths / 12).quantize(Decimal("0.01"))

    def test_the_units_counted_are_those_held_at_the_close(self):
        """Rz. 18.4. Holding nothing when the year opened does not reduce the
        count; only Abs. 2's twelfths reduce, and they are a separate step."""
        fund = _make_fund(soy_qty=Decimal("0"))
        fund.prior_year_soy_mark_price = Decimal("100")   # the fund had a price; we did not hold it

        results = _run_vp(fund, acquisition_date=dt_date(2024, 7, 15))

        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur == Decimal("80.15")

    def test_without_a_year_start_price_it_is_dropped_at_the_price_check(self, caplog):
        """Pins **which** branch fires, not merely that nothing comes out.

        The engine has two ways to produce nothing here and only one of them is
        lawful. Asserting the count alone would pass if a regression started
        dropping the fund on its unit count instead — which is the reading
        `test_no_soy_position_no_vp` enshrined.

        The discrimination is the pair, not a log string: this fixture and the
        one in `test_the_units_counted_are_those_held_at_the_close` differ in
        the year-start price and nothing else, and that one produces a figure.
        So the price is the only thing that can account for the difference.
        Deliberately not asserted: the text of the message. Issue #55 replaces
        that warning with a recorded gap, which must not break this test.
        """
        import logging

        fund = _make_fund(soy_qty=Decimal("0"))          # -> no year-start price
        with caplog.at_level(logging.DEBUG):
            results = _run_vp(fund, acquisition_date=dt_date(2024, 7, 15))

        assert len(results) == 0
        assert "nothing held at the close" not in caplog.text, (
            "dropped for the wrong reason: 100 units were held at 31 December")

    @pytest.mark.xfail(strict=True, reason=(
        "issue #55 — the four per-fund skips do not reach the data-gap channel. "
        "strict so that landing #55 makes this XPASS and forces the marker out "
        "rather than leaving a stale xfail behind."))
    def test_a_dropped_fund_is_recorded_rather_than_only_logged(self):
        """A skipped fund contributes no deemed income and the report is silent.

        Asserts only that *something* is recorded: the gap code and severity are
        #55's to choose, and pinning them here would fix its design from a test.
        """
        collector = DataGapCollector()
        fund = _make_fund(soy_qty=Decimal("0"))

        _run_vp(fund, acquisition_date=dt_date(2024, 7, 15), collector=collector)

        assert len(collector) > 0


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

class TestZeile53VorabpauschaleDeduction:
    """Anlage KAP-INV Zeile 53 -- "Waehrend der Besitzzeit angesetzte Vorabpauschalen".

    Until 2026-08-03 the engine emitted the sum of the CURRENT year's gross Vorabpauschalen
    on a category named `..._Z55`. Both halves were wrong: Zeile 55 is "Gewinne aus der
    Veraeusserung von bestandsgeschuetzten Alt-Anteilen" (Anleitung zur Anlage KAP-INV 2024
    and 2025), and the deduction under 19 Abs. 1 S. 3-4 InvStG is the Vorabpauschale
    accumulated over the holding period of the units actually disposed of, so far as it was
    brought to tax -- not a current-year total.

    The engine cannot compute that (no per-lot Vorabpauschale history), so it emits nothing and
    reports a data gap. These tests hold that line: they fail if a figure reappears, and they
    fail if the gap stops being reported.
    """

    def _engine(self, *, rgls=None, vp_items=None, tax_year=2024, collector=None):
        resolver = MagicMock(spec=AssetResolver)
        resolver.get_asset_by_id.return_value = None
        return LossOffsettingEngine(
            realized_gains_losses=rgls or [],
            vorabpauschale_items=vp_items or [],
            current_year_financial_events=[],
            asset_resolver=resolver,
            tax_year=tax_year,
            data_gap_collector=collector,
        )

    def test_no_zeile_53_figure_is_emitted(self):
        """No amount is placed on Zeile 53, even when the year has Vorabpauschalen."""
        engine = self._engine(
            rgls=[_make_fund_disposal()],
            vp_items=[_make_vp_item(vorabpauschale_year=2023)],
        )
        result = engine.calculate_reporting_figures()
        assert (
            TaxReportingCategory.ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z53
            not in result.form_line_values
        )

    def test_gap_recorded_when_fund_units_were_disposed(self):
        """A disposal makes Zeile 53 relevant, so the un-computable deduction is reported."""
        collector = DataGapCollector()
        engine = self._engine(rgls=[_make_fund_disposal()], collector=collector)
        engine.calculate_reporting_figures()

        codes = [g.code for g in collector.gaps]
        assert "KAP_INV_Z53_VORABPAUSCHALE_DEDUCTION_NOT_COMPUTED" in codes
        gap = next(g for g in collector.gaps
                   if g.code == "KAP_INV_Z53_VORABPAUSCHALE_DEDUCTION_NOT_COMPUTED")
        # WARNING, not FAIL_FAST: omitting the deduction OVERSTATES the gain, so the figures
        # are conservative rather than income-understating.
        assert gap.severity is GapSeverity.WARNING
        assert "Zeile 53" in gap.detail

    def test_no_gap_when_no_fund_units_were_disposed(self):
        """Zeile 53 is legitimately empty without a fund disposal -- that is not a gap."""
        collector = DataGapCollector()
        engine = self._engine(
            rgls=[_make_fund_disposal(category=AssetCategory.STOCK)],
            vp_items=[_make_vp_item(vorabpauschale_year=2023)],
            collector=collector,
        )
        engine.calculate_reporting_figures()
        assert collector.gaps == []


# ---------------------------------------------------------------------------
# Tests: a Vorabpauschale is declared in the year AFTER the one it is computed for
# ---------------------------------------------------------------------------

class TestVorabpauschaleDeclarationYear:
    """18 Abs. 3 InvStG: the VP for calendar X flows on the first working day of X+1 and is
    declared in VZ X+1. The engine used to declare it in VZ X."""

    def _run(self, vp_year, tax_year):
        resolver = MagicMock(spec=AssetResolver)
        resolver.get_asset_by_id.return_value = None
        engine = LossOffsettingEngine(
            realized_gains_losses=[],
            vorabpauschale_items=[_make_vp_item(vorabpauschale_year=vp_year)],
            current_year_financial_events=[],
            asset_resolver=resolver,
            tax_year=tax_year,
        )
        return engine.calculate_reporting_figures()

    def test_prior_year_vp_is_declared_in_this_year(self):
        """The VP for calendar 2023 belongs on the VZ 2024 return."""
        result = self._run(vp_year=2023, tax_year=2024)
        assert result.conceptual_fund_income_net_taxable == Decimal("112.21")

    def test_this_years_vp_is_not_declared_yet(self):
        """The VP for calendar 2024 flows 02.01.2025 -- it must NOT appear in VZ 2024.

        This is the guard for the defect fixed on 2026-08-03: the engine declared the tax
        year's own Vorabpauschale, one year early.
        """
        result = self._run(vp_year=2024, tax_year=2024)
        assert result.conceptual_fund_income_net_taxable == Decimal("0.00")

    def test_declaration_year_is_one_past_the_vorabpauschale_year(self):
        assert _make_vp_item(vorabpauschale_year=2023).declaration_year == 2024


# ---------------------------------------------------------------------------
# Tests: the shipped Basiszins table covers exactly the years the law defines
# ---------------------------------------------------------------------------

class TestBasiszinsTableCoverage:
    """Every BMF-published rate must be configured so that no tax year inside
    the regime silently produces zero Vorabpauschale — and no year OUTSIDE the
    regime may carry a rate, which would invent deemed income.

    The values themselves are pinned against the knowledge store by
    `tests/test_tax_law_registry.py::TestBasiszinsReferenceConsistency`, which
    parses `reference/bmf-guidance/basiszins-vorabpauschale.md`. This class
    checks the SHAPE of the table, which that parse cannot: where it starts,
    that it has no holes, and that the year an engine run needs is present."""

    def test_regime_floor_is_2018(self):
        """§56 Abs. 1 S. 1 InvStG: the InvStG 2018 applies from 01.01.2018, so
        the first Vorabpauschale is the one for calendar 2018 and the first
        published Basiszins is the 2018 one. Nothing earlier belongs here — the
        1.10%/0.59% once listed for 2016/2017 are the §203 Abs. 2 BewG rate."""
        from src.tax_law import registry
        assert min(registry.BASISZINS_PCT) == 2018
        assert 2016 not in registry.BASISZINS_PCT
        assert 2017 not in registry.BASISZINS_PCT

    def test_every_year_from_2018_to_the_latest_is_present(self):
        from src.tax_law import registry
        years = sorted(registry.BASISZINS_PCT)
        assert years == list(range(2018, years[-1] + 1)), (
            "gap in the Basiszins table — that year's Vorabpauschale would be "
            "skipped; fill it from reference/bmf-guidance/basiszins-vorabpauschale.md")


# ---------------------------------------------------------------------------
# Tests: guards that mutation-probing found blind
# ---------------------------------------------------------------------------

class TestDistributionsComeFromTheVorabpauschaleYear:
    """`_collect_fund_distributions_for_year` filters by calendar year.

    Found blind by mutation on 2026-08-03: replacing the year filter with `if False`
    left the whole suite green, because every fixture distribution happened to be dated
    inside the year under test. The filter decides whether a distribution reduces the
    Basisertrag (18 Abs. 1 S. 1 InvStG), and for a VZ Y run the relevant distributions are
    Y-1's, not Y's -- so a filter that does nothing silently understates the deemed income.
    """

    def test_distribution_in_the_vorabpauschale_year_reduces_the_basisertrag(self):
        fund = _make_fund()
        dist = _make_distribution(fund.internal_asset_id, Decimal("50"), event_date="2024-06-15")
        results = _run_vp(fund, events=[dist], vorabpauschale_year=2024)
        # Basisertrag 160.30 - 50 = 110.30
        assert results[0].gross_vorabpauschale_eur == Decimal("110.30")

    def test_distribution_from_a_later_year_does_not_reduce_it(self):
        """A distribution paid in the VZ itself belongs to the NEXT Vorabpauschale."""
        fund = _make_fund()
        dist = _make_distribution(fund.internal_asset_id, Decimal("50"), event_date="2025-06-15")
        results = _run_vp(fund, events=[dist], vorabpauschale_year=2024)
        assert results[0].gross_vorabpauschale_eur == Decimal("160.30")
        assert results[0].distributions_during_year_eur == Decimal("0.00")

    def test_distribution_from_an_earlier_year_does_not_reduce_it(self):
        fund = _make_fund()
        dist = _make_distribution(fund.internal_asset_id, Decimal("50"), event_date="2023-06-15")
        results = _run_vp(fund, events=[dist], vorabpauschale_year=2024)
        assert results[0].gross_vorabpauschale_eur == Decimal("160.30")


class TestMissingPriorYearSnapshotIsFatal:
    """A held fund plus no prior-year snapshot must stop the run.

    Found blind by mutation on 2026-08-03: replacing the condition with `if False` left all
    492 tests green. The Vorabpauschale declared in VZ Y is the one for calendar Y-1
    (18 Abs. 3 InvStG), so without Y-1's position snapshots it cannot be computed. Silently
    emitting no Vorabpauschale would understate deemed income, which is the FAIL_FAST
    contract in src/processing/data_gaps.py.
    """

    def _run(self, *, prior_available, with_fund=True):
        from src.engine.calculation_engine import run_main_calculations
        resolver = MagicMock(spec=AssetResolver)
        resolver.assets_by_internal_id = (
            {(f := _make_fund()).internal_asset_id: f} if with_fund else {}
        )
        resolver.get_asset_by_id.return_value = None
        collector = DataGapCollector()
        run_main_calculations(
            financial_events=[],
            asset_resolver=resolver,
            currency_converter=_eur_converter(),
            exchange_rate_provider=MagicMock(),
            tax_year=2025,
            internal_calculation_precision=config.INTERNAL_CALCULATION_PRECISION,
            decimal_rounding_mode=config.DECIMAL_ROUNDING_MODE,
            data_gap_collector=collector,
            prior_year_positions_available=prior_available,
        )
        return collector

    def test_raises_when_a_fund_is_held_and_the_snapshot_is_absent(self):
        from src.processing.data_gaps import DataGapError
        with pytest.raises(DataGapError, match="VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING"):
            self._run(prior_available=False)

    def test_does_not_raise_when_the_snapshot_is_present(self):
        collector = self._run(prior_available=True)
        assert not [g for g in collector.gaps
                    if g.code == "VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING"]

    def test_does_not_raise_when_no_fund_is_held(self):
        """No fund, no deemed income -- an absent snapshot is then not a gap."""
        collector = self._run(prior_available=False, with_fund=False)
        assert not [g for g in collector.gaps
                    if g.code == "VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING"]

"""
Gap-coverage tests for Vorabpauschale (§18 InvStG).

This file is ADDITIVE — it does not modify any test in test_vorabpauschale.py.
It covers requirements the existing suite missed and now exercises the
partial-year (§18 Abs. 2) implementation.

Requirements (verbatim §18 InvStG, https://www.gesetze-im-internet.de/invstg_2018/__18.html):
  R1 (Abs. 1 S. 1): VP = max(0, Basisertrag − Ausschüttungen)
  R2 (Abs. 1 S. 2): Basisertrag = Rücknahmepreis(Jahresbeginn) × 0.70 × Basiszins
  R3 (Abs. 1 S. 3): Basisertrag capped at (letzter − erster Rücknahmepreis) + Ausschüttungen
  R4 (Abs. 2):      In the acquisition year, VP is reduced by 1/12 for each full
                    month preceding the month of acquisition.
  R5 (Abs. 3):      VP is deemed to flow on the first business day of the
                    FOLLOWING calendar year (taxed in year X+1).  -- still xfail.
"""
import builtins
import uuid
from decimal import Decimal, Context
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.config as config
from src.utils.account_utils import DEFAULT_ACCOUNT
from src.domain.events import TradeEvent
from src.domain.enums import FinancialEventType
from src.engine.calculation_engine import _calculate_vorabpauschale
from src.identification.fund_soy_nav_provider import FundSoyNavProvider
from src.processing.vp_nav_resolution import resolve_year_start_navs

from tests.test_vorabpauschale import (
    _make_fund,
    _make_distribution,
    _make_resolver_with_fund,
    _eur_converter,
    _run_vp,
)


# Basiszins 2024 = 2.29% -> Basisertrag factor 0.0229 * 0.7 = 0.01603
# Default fund: SoY=10000, EoY=11000 -> full-year Basisertrag = 160.30
FULL_YEAR_VP = Decimal("160.30")


def _lot(acq_date: str, qty: str):
    """Minimal stand-in for a FifoLot (the VP factor reads only these fields)."""
    return SimpleNamespace(acquisition_date=acq_date, quantity=Decimal(qty))


def _run_vp_with_ledger(fund, lots, events=None, tax_year=2024):
    """Run the VP calc with a stub FIFO ledger (for multi-tranche month factors)."""
    resolver = _make_resolver_with_fund(fund)
    ledger = SimpleNamespace(lots=lots)
    ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION, rounding=config.DECIMAL_ROUNDING_MODE)
    return _calculate_vorabpauschale(
        asset_resolver=resolver,
        current_year_events=events or [],
        currency_converter=_eur_converter(),
        tax_year=tax_year,
        ctx=ctx,
        fifo_ledgers={(DEFAULT_ACCOUNT, fund.internal_asset_id): ledger},
    )


# ---------------------------------------------------------------------------
# R3 cap AND distributions active simultaneously (code is correct; pins it).
# ---------------------------------------------------------------------------

class TestCapAndDistributionsCombined:

    def test_cap_binds_with_small_distribution(self):
        """Gain 50, dist 30, Basisertrag 160.30 -> VP 50."""
        fund = _make_fund(eoy_position_value=Decimal("10050"))
        dist = _make_distribution(fund.internal_asset_id, Decimal("30"))
        results = _run_vp(fund, events=[dist])
        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur == Decimal("50.00")

    def test_cap_binds_with_large_distribution(self):
        """Gain 20, dist 100, Basisertrag 160.30 -> VP 20."""
        fund = _make_fund(eoy_position_value=Decimal("10020"))
        dist = _make_distribution(fund.internal_asset_id, Decimal("100"))
        results = _run_vp(fund, events=[dist])
        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur == Decimal("20.00")

    def test_cap_not_binding_distribution_reduces_basisertrag(self):
        """Large gain, dist 60.30 -> VP = 160.30 − 60.30 = 100.00."""
        fund = _make_fund(eoy_position_value=Decimal("11000"))
        dist = _make_distribution(fund.internal_asset_id, Decimal("60.30"))
        results = _run_vp(fund, events=[dist])
        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur == Decimal("100.00")

    def test_value_loss_with_distribution_yields_zero_vp(self):
        """Fund lost value (EoY 9500 < SoY 10000) but paid a 200 distribution. The §18 cap is
        (EoY−SoY)+Ausschüttungen = −500+200 = −300; VP = max(0, min(Basisertrag, −300) − 200) = 0.
        Equivalently the engine's value-gain cap max(0, EoY−SoY) binds at 0. A distribution must
        not mask a value loss into a positive VP."""
        fund = _make_fund(eoy_position_value=Decimal("9500"))
        dist = _make_distribution(fund.internal_asset_id, Decimal("200"))
        results = _run_vp(fund, events=[dist])
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Abs. 4: a negative Basiszins (e.g. 2021/2022) makes the Basisertrag <= 0 -> VP 0.
# ---------------------------------------------------------------------------

class TestNegativeBasiszins:

    def test_negative_basiszins_yields_zero_vp(self, monkeypatch):
        from decimal import Decimal as D
        from src.tax_law import registry
        monkeypatch.setitem(registry.BASISZINS_PCT, 2024, D("-0.50"))
        fund = _make_fund()  # positive value gain, no distributions
        results = _run_vp(fund, tax_year=2024)
        # Basisertrag = 10000 * (-0.005) * 0.7 < 0 -> no Vorabpauschale.
        assert all(r.tax_year != 2024 for r in results)


# ---------------------------------------------------------------------------
# R4: partial-year acquisition (§18 Abs. 2 monthly reduction).
# Retained fraction for acquisition month M = (13 − M)/12.
# ---------------------------------------------------------------------------

class TestPartialYearAcquisitionReduction:

    @pytest.mark.parametrize("acq_month, retained_twelfths", [
        (1, 12),   # acquired January -> full VP
        (6, 7),    # acquired June -> 7/12
        (11, 2),   # acquired November -> 2/12
        (12, 1),   # acquired December -> 1/12
    ])
    def test_acquisition_month_reduces_vp(self, acq_month, retained_twelfths):
        """VP for a mid-year acquisition = full-year VP × (13 − M)/12."""
        fund = _make_fund(
            soy_qty=Decimal("0"),                  # not held at SoY
            eoy_position_value=Decimal("11000"),
            eoy_qty=Decimal("100"),
            description="Mid-year fund",
        )
        fund.vp_soy_nav_per_unit = Decimal("100")  # year-start NAV (externally sourced)
        fund.vp_acquisition_month = acq_month

        results = _run_vp(fund)
        assert len(results) == 1
        expected = (FULL_YEAR_VP * Decimal(retained_twelfths) / Decimal(12)).quantize(Decimal("0.01"))
        assert abs(results[0].gross_vorabpauschale_eur - expected) <= Decimal("0.01")
        assert results[0].partial_year_factor == (Decimal(retained_twelfths) / Decimal(12)).quantize(Decimal("0.0001"))


# ---------------------------------------------------------------------------
# A fund acquired mid-year and held at EoY must NOT be dropped (counterpart to
# test_vorabpauschale.py::test_no_soy_position_no_vp, which stays valid for a
# fund that was never acquired).
# ---------------------------------------------------------------------------

class TestMidYearAcquisitionNotDropped:

    def test_mid_year_acquisition_held_at_eoy_produces_vp(self):
        fund = _make_fund(
            soy_qty=Decimal("0"),
            eoy_position_value=Decimal("11000"),
            eoy_qty=Decimal("100"),
            description="Acquired mid-year, held at EoY",
        )
        fund.vp_soy_nav_per_unit = Decimal("100")
        fund.vp_acquisition_month = 6

        results = _run_vp(fund)
        assert len(results) == 1
        assert results[0].gross_vorabpauschale_eur > Decimal("0")


# ---------------------------------------------------------------------------
# Value-gain cap with intra-year quantity change: now correct (per-unit cap).
# 100 units held all year at 100/unit + 100 bought mid-year at 100/unit ->
# per-share gain is zero -> VP = 0.
# ---------------------------------------------------------------------------

class TestCapWithIntraYearQuantityChange:

    def test_zero_per_share_gain_yields_zero_vp(self):
        fund = _make_fund(
            soy_qty=Decimal("100"),
            soy_position_value=Decimal("10000"),   # 100 units @ 100
            eoy_qty=Decimal("200"),
            eoy_position_value=Decimal("20000"),   # 200 units @ 100 (price unchanged)
            description="Intra-year purchase, flat price",
        )
        results = _run_vp(fund)
        total_gross_vp = sum((r.gross_vorabpauschale_eur for r in results), Decimal("0"))
        assert total_gross_vp == Decimal("0")


# ---------------------------------------------------------------------------
# Full multi-tranche: per-lot acquisition-month factors from the FIFO ledger.
# ---------------------------------------------------------------------------

class TestMultiTranche:

    def test_two_current_year_lots_units_weighted(self):
        """200 units @ Jan (f=1) + 100 units @ Oct (f=3/12=0.25) -> F=0.75."""
        fund = _make_fund(
            soy_qty=Decimal("0"),
            eoy_qty=Decimal("300"),
            eoy_position_value=Decimal("33000"),   # 300 @ 110
            description="Two mid-year tranches",
        )
        fund.vp_soy_nav_per_unit = Decimal("100")  # year-start NAV per unit

        lots = [_lot("2024-01-15", "200"), _lot("2024-10-10", "100")]
        results = _run_vp_with_ledger(fund, lots)
        assert len(results) == 1
        # Basisertrag on 300 @ 100 = 30000 * 0.01603 = 480.90; F = (200*1 + 100*0.25)/300 = 0.75
        assert abs(results[0].gross_vorabpauschale_eur - Decimal("360.68")) <= Decimal("0.01")
        assert results[0].partial_year_factor == Decimal("0.7500")

    def test_mixed_prior_year_and_mid_year_lots(self):
        """200 units held since 2023 (f=1) + 100 units bought Jul 2024 (f=0.5) -> F=0.8333.

        NAV comes from the SoY position (soy_market_price) -- no user input needed.
        """
        fund = _make_fund(
            soy_qty=Decimal("200"),
            soy_position_value=Decimal("20000"),   # 200 @ 100 -> soy_market_price 100
            eoy_qty=Decimal("300"),
            eoy_position_value=Decimal("33000"),   # 300 @ 110
            description="Prior-year holding plus a mid-year tranche",
        )
        lots = [_lot("2023-05-01", "200"), _lot("2024-07-01", "100")]
        results = _run_vp_with_ledger(fund, lots)
        assert len(results) == 1
        # F = (200*1 + 100*0.5)/300 = 250/300; gross = 480.90 * 250/300 = 400.75
        assert abs(results[0].gross_vorabpauschale_eur - Decimal("400.75")) <= Decimal("0.01")
        # No user NAV needed: SoY position provided it.
        assert fund.vp_soy_nav_per_unit is None


# ---------------------------------------------------------------------------
# NAV resolution pre-pass: fail-fast and cache behaviour.
# ---------------------------------------------------------------------------

class TestNavResolution:

    def _buy(self, asset_id, date_str):
        return TradeEvent(
            asset_internal_id=asset_id,
            event_date=date_str,
            event_type=FinancialEventType.TRADE_BUY_LONG,
            quantity=Decimal("100"),
            price_foreign_currency=Decimal("100"),
        )

    def test_non_interactive_missing_nav_warns_not_fails(self, tmp_path):
        """Missing current-year NAV is warn-only: a gap is recorded, no exception."""
        fund = _make_fund(soy_qty=Decimal("0"), eoy_qty=Decimal("100"),
                          description="Needs NAV")
        resolver = _make_resolver_with_fund(fund)
        provider = FundSoyNavProvider(cache_file_path=str(tmp_path / "nav.json"))
        events = [self._buy(fund.internal_asset_id, "2024-06-15")]

        gaps = resolve_year_start_navs(resolver, events, 2024, interactive=False, provider=provider)
        assert any(g.description == "Needs NAV" and g.deemed_inflow_year == 2025 for g in gaps)
        assert fund.vp_soy_nav_per_unit is None

    def test_cached_nav_resolves_without_prompt(self, tmp_path, monkeypatch):
        fund = _make_fund(soy_qty=Decimal("0"), eoy_qty=Decimal("100"))
        resolver = _make_resolver_with_fund(fund)
        provider = FundSoyNavProvider(cache_file_path=str(tmp_path / "nav.json"))
        provider.nav_cache[provider.cache_key(fund, 2024)] = ["123.45", "EUR"]
        events = [self._buy(fund.internal_asset_id, "2024-06-15")]

        # If interactive prompting were attempted, this would raise.
        monkeypatch.setattr(builtins, "input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("prompted despite cache hit")))

        resolve_year_start_navs(resolver, events, 2024, interactive=True, provider=provider)
        assert fund.vp_soy_nav_per_unit == Decimal("123.45")
        assert fund.vp_acquisition_month == 6

    def test_held_at_soy_needs_no_nav(self, tmp_path):
        """A fund held at SoY is not flagged as needing a user-supplied NAV."""
        fund = _make_fund(soy_qty=Decimal("100"), eoy_qty=Decimal("100"))
        resolver = _make_resolver_with_fund(fund)
        provider = FundSoyNavProvider(cache_file_path=str(tmp_path / "nav.json"))
        # No exception, nothing attached.
        resolve_year_start_navs(resolver, [], 2024, interactive=False, provider=provider)
        assert fund.vp_soy_nav_per_unit is None


# ---------------------------------------------------------------------------
# R5: deemed inflow timing (§18 Abs. 3). The VP for calendar year Y is deemed to
# flow on the first business day of Y+1 and is declared in the Y+1 assessment.
# ---------------------------------------------------------------------------

class TestDeemedInflowTiming:

    def test_vp_deemed_inflow_year_is_following_year(self):
        """A VP computed for calendar year 2024 is deemed to flow in 2025."""
        fund = _make_fund(description="Full-year fund")
        results = _run_vp(fund, tax_year=2024)
        assert len(results) == 1
        assert results[0].tax_year == 2024
        assert results[0].deemed_inflow_year == 2025

    def test_run_computes_current_preview_and_prior_for_return(self):
        """A 2025 run yields the 2025 VP (preview, inflow 2026) and the 2024 VP
        (inflow 2025 -> belongs on the 2025 return)."""
        fund = _make_fund(
            soy_qty=Decimal("100"), soy_position_value=Decimal("10000"),  # SoY 2025 = EoY 2024
            eoy_position_value=Decimal("11000"), eoy_qty=Decimal("100"),
            description="Held across the year boundary",
        )
        fund.vp_prior_soy_nav_per_unit = Decimal("95")   # 1 Jan 2024 NAV
        fund.vp_prior_soy_nav_currency = "EUR"

        results = _run_vp(fund, tax_year=2025)
        by_inflow = {r.deemed_inflow_year: r for r in results}
        assert set(by_inflow) == {2025, 2026}
        assert by_inflow[2026].tax_year == 2025   # current-year VP, preview of 2026 return
        assert by_inflow[2025].tax_year == 2024   # prior-year VP, on the 2025 return


class TestPriorYearFeedsFormLines:
    """The KAP-INV VP form lines for assessment year X are fed by the X-1 VP."""

    def test_prior_year_vp_feeds_z9_13(self):
        """§18 Abs. 3: the VP on the X return's Z9-13 is the X-1 VP (deemed_inflow_year == X);
        the current-year VP (inflow X+1) is only a preview. The VP feeds the annual VP lines
        (Z9-13), not a separate deduction line."""
        from src.engine.loss_offsetting import LossOffsettingEngine
        from src.domain.enums import TaxReportingCategory
        from src.domain.results import VorabpauschaleData
        from src.domain.enums import InvestmentFundType
        import uuid

        # Two VP records: the 2025 VP (inflow 2026) and the 2024 VP (inflow 2025).
        def _vp(tax_year, inflow, gross):
            return VorabpauschaleData(
                asset_internal_id=uuid.uuid4(), tax_year=tax_year,
                fund_value_start_year_eur=Decimal("10000"), fund_value_end_year_eur=Decimal("11000"),
                distributions_during_year_eur=Decimal("0"), base_return_rate=Decimal("0.0229"),
                basiszins=Decimal("2.29"), calculated_base_return_eur=gross,
                gross_vorabpauschale_eur=gross, fund_type=InvestmentFundType.AKTIENFONDS,
                teilfreistellung_rate_applied=Decimal("0.30"),
                teilfreistellung_amount_eur=(gross * Decimal("0.30")).quantize(Decimal("0.01")),
                net_taxable_vorabpauschale_eur=(gross * Decimal("0.70")).quantize(Decimal("0.01")),
                tax_reporting_category_gross=TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO,
                deemed_inflow_year=inflow,
            )

        current = _vp(2025, 2026, Decimal("177.10"))
        prior = _vp(2024, 2025, Decimal("152.29"))

        resolver = MagicMock()
        resolver.get_asset_by_id.return_value = None
        engine = LossOffsettingEngine(
            realized_gains_losses=[], vorabpauschale_items=[current, prior],
            current_year_financial_events=[], asset_resolver=resolver, tax_year=2025,
        )
        result = engine.calculate_reporting_figures()
        # Only the prior-year (2024) VP flows into the 2025 return, via Z9 (Aktienfonds VP brutto).
        z9 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO, Decimal("0"))
        assert z9 == Decimal("152.29")
        # The VP deduction is not a separate loss-offsetting form line.
        z55 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z55, Decimal("0"))
        assert z55 == Decimal("0")


# ---------------------------------------------------------------------------
# Report surface: unresolved-NAV gaps must reach the console VP section.
# ---------------------------------------------------------------------------

class TestVpGapReportCallout:

    @staticmethod
    def _render(data_gaps, tax_year=2024):
        from src.identification.asset_resolver import AssetResolver
        from src.domain.results import LossOffsettingResult
        from src.reporting.console_reporter import generate_console_tax_report
        generate_console_tax_report(
            realized_gains_losses=[], vorabpauschale_items=[],
            all_financial_events=[], asset_resolver=AssetResolver(MagicMock()),
            tax_year=tax_year, eoy_mismatch_count=0,
            loss_offsetting_summary=LossOffsettingResult(),
            data_gaps=data_gaps,
        )

    def test_unresolved_nav_gap_rendered_in_vp_section(self, capsys):
        """An interactive run with a still-missing year-start NAV must show the
        understatement warning next to the Zeile 9-13 figures (finding F4)."""
        from src.processing.data_gaps import DataGap
        gap = DataGap(code="VP_NAV_MISSING", subject="Fonds Z (IE000TEST0000)",
                      detail="Jahresanfangs-NAV 2023 fehlt (betrifft Vorabpauschale, Zufluss 2024)")
        self._render([gap])
        out = capsys.readouterr().out
        assert "VORABPAUSCHALE UNVOLLSTÄNDIG" in out
        assert "Fonds Z (IE000TEST0000)" in out

    def test_gap_for_other_inflow_year_not_shown_in_vp_section(self, capsys):
        """The current year's VP section only flags gaps whose deemed inflow is
        THIS assessment year; next year's preview gap does not belong here."""
        from src.processing.data_gaps import DataGap
        gap = DataGap(code="VP_NAV_MISSING", subject="Fonds Z (IE000TEST0000)",
                      detail="Jahresanfangs-NAV 2024 fehlt (betrifft Vorabpauschale, Zufluss 2025)")
        self._render([gap])
        out = capsys.readouterr().out
        assert "VORABPAUSCHALE UNVOLLSTÄNDIG" not in out

"""
Tests for the §19 Abs. 1 Satz 3-4 InvStG Vorabpauschale deduction at fund disposal.

Legal framework (verbatim, https://www.gesetze-im-internet.de/invstg_2018/__19.html
and the official Anlage KAP-INV 2025 instructions, reference/Anltg_KAP_INV_25.md):

  §19 Abs. 1 S. 3: the disposal gain is reduced by the Vorabpauschalen **assessed during
                   the holding period** of the sold units.
  §19 Abs. 1 S. 4: the deduction is the **gross** VP (vor Teilfreistellung).
  Form instructions (Z53, p.4): the VP reduces the gain **only to the extent it was actually
                   subjected to taxation in the prior years (Z9-13)** — i.e. the *declared* VP.
  Form instructions (Z46-54, p.3): per fund, **per acquisition tranche (own column)**,
                   **FIFO** — "zuerst angeschafften Anteile gelten als zuerst veräußert".

Mechanic (per-lot FIFO, per-unit VP):
    per-unit VP for year Y = declared_VP[Y] / units_held_at_end_of_Y
    lot deduction          = units_sold × Σ_{Y = acq_year .. sale_year-1} per-unit VP[Y]
A full exit of the whole position therefore reduces to Σ_Y declared_VP[Y].

These tests assert the **requirements**, not the implementation. They drive:
  - src/processing/vp_disposal_deduction.py: year_end_quantities(), vp_deduction_for_lot()
  - src/identification/declared_vp_provider.py: DeclaredVpProvider
"""
import builtins
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.domain.events import TradeEvent
from src.domain.enums import FinancialEventType
from src.processing.vp_disposal_deduction import (
    year_end_quantities,
    vp_deduction_for_lot,
)
from src.identification.declared_vp_provider import DeclaredVpProvider
from src.domain.results import RealizedGainLoss, VorabpauschaleData
from src.domain.enums import AssetCategory, InvestmentFundType, RealizationType, TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine

from tests.test_vorabpauschale import _make_fund, _make_resolver_with_fund


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _buy(asset_id, date_str, qty):
    return TradeEvent(
        asset_internal_id=asset_id, event_date=date_str,
        event_type=FinancialEventType.TRADE_BUY_LONG,
        quantity=Decimal(qty), price_foreign_currency=Decimal("100"),
    )


def _sell(asset_id, date_str, qty_abs):
    # TradeEvent.quantity is signed: negative for a sell.
    return TradeEvent(
        asset_internal_id=asset_id, event_date=date_str,
        event_type=FinancialEventType.TRADE_SELL_LONG,
        quantity=-Decimal(qty_abs), price_foreign_currency=Decimal("100"),
    )


# ---------------------------------------------------------------------------
# vp_deduction_for_lot — the §19 per-lot rule
# ---------------------------------------------------------------------------

class TestVpDeductionForLot:

    def test_full_single_tranche_deducts_all_declared_vp(self):
        """Lot held all of 2022-2024, sold 2025: deduction = Σ declared VP (units cancel)."""
        ded = vp_deduction_for_lot(
            acquisition_year=2022, sale_year=2025, units_sold=Decimal("100"),
            declared_vp_by_year={2022: Decimal("50"), 2023: Decimal("60"), 2024: Decimal("70")},
            qty_eoy_by_year={2022: Decimal("100"), 2023: Decimal("100"), 2024: Decimal("100")},
        )
        assert ded == Decimal("180")

    def test_partial_exit_prorates_by_units_sold(self):
        """Selling 40 of 100 units deducts 40/100 of each year's VP."""
        ded = vp_deduction_for_lot(
            acquisition_year=2022, sale_year=2025, units_sold=Decimal("40"),
            declared_vp_by_year={2022: Decimal("50"), 2023: Decimal("60"), 2024: Decimal("70")},
            qty_eoy_by_year={2022: Decimal("100"), 2023: Decimal("100"), 2024: Decimal("100")},
        )
        # 40 * (50+60+70)/100 = 72
        assert ded == Decimal("72")

    def test_undeclared_year_is_not_deducted(self):
        """A year with no declared VP (not subjected to tax) does not reduce the gain (Z53 cond.)."""
        ded = vp_deduction_for_lot(
            acquisition_year=2022, sale_year=2025, units_sold=Decimal("100"),
            declared_vp_by_year={2022: Decimal("50"), 2024: Decimal("70")},  # 2023 missing
            qty_eoy_by_year={2022: Decimal("100"), 2023: Decimal("100"), 2024: Decimal("100")},
        )
        assert ded == Decimal("120")  # 50 + 70 only

    def test_year_before_acquisition_excluded(self):
        """VP from a year before the lot existed is not attributable to it."""
        ded = vp_deduction_for_lot(
            acquisition_year=2023, sale_year=2025, units_sold=Decimal("100"),
            declared_vp_by_year={2022: Decimal("50"), 2023: Decimal("60"), 2024: Decimal("70")},
            qty_eoy_by_year={2022: Decimal("100"), 2023: Decimal("100"), 2024: Decimal("100")},
        )
        assert ded == Decimal("130")  # 2023 + 2024 only; 2022 excluded

    def test_sale_year_vp_excluded(self):
        """No VP is assessed for the disposal year (units not held at 31.12): range is acq..sale-1."""
        ded = vp_deduction_for_lot(
            acquisition_year=2024, sale_year=2025, units_sold=Decimal("100"),
            declared_vp_by_year={2024: Decimal("70"), 2025: Decimal("99")},
            qty_eoy_by_year={2024: Decimal("100"), 2025: Decimal("100")},
        )
        assert ded == Decimal("70")  # 2025 excluded

    def test_zero_year_end_quantity_is_skipped(self):
        """A year-end quantity of 0 must not divide-by-zero; that year contributes nothing."""
        ded = vp_deduction_for_lot(
            acquisition_year=2023, sale_year=2025, units_sold=Decimal("100"),
            declared_vp_by_year={2023: Decimal("60"), 2024: Decimal("70")},
            qty_eoy_by_year={2023: Decimal("0"), 2024: Decimal("100")},
        )
        assert ded == Decimal("70")  # 2023 skipped (qty_eoy 0)

    def test_no_declared_vp_no_deduction(self):
        """No declared VP at all -> deduction 0 (existing fund-sale behaviour unchanged)."""
        ded = vp_deduction_for_lot(
            acquisition_year=2022, sale_year=2025, units_sold=Decimal("100"),
            declared_vp_by_year={}, qty_eoy_by_year={2022: Decimal("100")},
        )
        assert ded == Decimal("0")

    def test_multi_tranche_fifo_per_lot_sums_to_full_exit(self):
        """
        Two tranches (FIFO), full exit. The earlier lot accrues more VP-years; the
        per-lot sum must equal Σ declared VP across the holding years.
        Position: 100 units bought 2022, +50 bought 2023 -> 150 at EoY 2023/2024.
        """
        qty_eoy = {2022: Decimal("100"), 2023: Decimal("150"), 2024: Decimal("150")}
        declared = {2022: Decimal("30"), 2023: Decimal("45"), 2024: Decimal("45")}

        lot_a = vp_deduction_for_lot(
            acquisition_year=2022, sale_year=2025, units_sold=Decimal("100"),
            declared_vp_by_year=declared, qty_eoy_by_year=qty_eoy,
        )
        lot_b = vp_deduction_for_lot(
            acquisition_year=2023, sale_year=2025, units_sold=Decimal("50"),
            declared_vp_by_year=declared, qty_eoy_by_year=qty_eoy,
        )
        # lot_a: 100*(30/100 + 45/150 + 45/150) = 90 ; lot_b: 50*(45/150+45/150) = 30
        assert lot_a == Decimal("90")
        assert lot_b == Decimal("30")
        # Full exit of the whole 150-unit position == Σ declared VP across years.
        assert lot_a + lot_b == declared[2022] + declared[2023] + declared[2024]


# ---------------------------------------------------------------------------
# year_end_quantities — units held at each 31.12 (FIFO denominator)
# ---------------------------------------------------------------------------

class TestYearEndQuantities:

    def test_single_buy_carries_forward(self):
        aid = uuid.uuid4()
        events = [_buy(aid, "2022-05-09", "100")]
        q = year_end_quantities(events, aid, up_to_year=2024)
        assert q[2022] == Decimal("100")
        assert q[2023] == Decimal("100")  # carried forward (no trades)
        assert q[2024] == Decimal("100")

    def test_buys_and_sells_net_per_year_end(self):
        aid = uuid.uuid4()
        events = [
            _buy(aid, "2022-05-09", "100"),
            _buy(aid, "2023-03-01", "50"),
            _sell(aid, "2024-07-01", "40"),
        ]
        q = year_end_quantities(events, aid, up_to_year=2025)
        assert q[2022] == Decimal("100")
        assert q[2023] == Decimal("150")
        assert q[2024] == Decimal("110")
        assert q[2025] == Decimal("110")  # carried forward

    def test_only_target_asset_counted(self):
        aid, other = uuid.uuid4(), uuid.uuid4()
        events = [_buy(aid, "2022-01-10", "100"), _buy(other, "2022-01-10", "999")]
        q = year_end_quantities(events, aid, up_to_year=2022)
        assert q[2022] == Decimal("100")


# ---------------------------------------------------------------------------
# DeclaredVpProvider — interactive cache (mirrors FundSoyNavProvider)
# ---------------------------------------------------------------------------

class TestDeclaredVpProvider:

    def test_non_interactive_missing_returns_none(self, tmp_path):
        fund = _make_fund()
        provider = DeclaredVpProvider(cache_file_path=str(tmp_path / "declared_vp.json"))
        assert provider.get_or_prompt(fund, 2023, interactive=False) is None

    def test_cache_hit_avoids_prompt(self, tmp_path, monkeypatch):
        fund = _make_fund()
        path = str(tmp_path / "declared_vp.json")
        provider = DeclaredVpProvider(cache_file_path=path)
        # seed via a prompted entry, then ensure a second lookup never calls input()
        monkeypatch.setattr(builtins, "input", lambda *_: "123.45")
        first = provider.get_or_prompt(fund, 2024, interactive=True)
        assert first == Decimal("123.45")

        def _boom(*_):
            raise AssertionError("input() must not be called on a cache hit")
        monkeypatch.setattr(builtins, "input", _boom)
        provider2 = DeclaredVpProvider(cache_file_path=path)  # reloads persisted cache
        assert provider2.get_or_prompt(fund, 2024, interactive=True) == Decimal("123.45")

    def test_blank_input_treated_as_zero(self, tmp_path, monkeypatch):
        fund = _make_fund()
        provider = DeclaredVpProvider(cache_file_path=str(tmp_path / "declared_vp.json"))
        monkeypatch.setattr(builtins, "input", lambda *_: "")
        # blank = "I did not declare VP for that year" -> 0 (not deductible)
        assert provider.get_or_prompt(fund, 2023, interactive=True) == Decimal("0")

    def test_prompt_persists_to_cache(self, tmp_path, monkeypatch):
        fund = _make_fund()
        path = str(tmp_path / "declared_vp.json")
        provider = DeclaredVpProvider(cache_file_path=path)
        monkeypatch.setattr(builtins, "input", lambda *_: "12,34")  # German comma tolerated
        assert provider.get_or_prompt(fund, 2024, interactive=True) == Decimal("12.34")
        # persisted and reloadable without prompting
        reloaded = DeclaredVpProvider(cache_file_path=path)
        assert reloaded.get_cached(fund, 2024) == Decimal("12.34")

    def test_set_persists_and_overwrites_stale(self, tmp_path):
        """set() auto-writes a value (used to auto-enter the computed current holding-year VP),
        overwriting any stale cached value, and persists it."""
        fund = _make_fund()
        path = str(tmp_path / "declared_vp.json")
        p = DeclaredVpProvider(cache_file_path=path)
        p.set(fund, 2024, Decimal("0"))           # stale placeholder
        p.set(fund, 2024, Decimal("123.45"))      # computed VP overwrites it
        assert p.get_cached(fund, 2024) == Decimal("123.45")
        assert DeclaredVpProvider(cache_file_path=path).get_cached(fund, 2024) == Decimal("123.45")


# ---------------------------------------------------------------------------
# resolve_declared_vp: auto-compute current holding year (V-1), prompt only ≤ V-2
# ---------------------------------------------------------------------------

class TestDeclaredVpResolution:

    def _recording_provider(self):
        class RecordingProvider:
            def __init__(self):
                self.prompted = []
                self.set_calls = []
            def get_or_prompt(self, asset, year, interactive, context_lines=None):
                self.prompted.append(year)
                return Decimal("0")
            def set(self, asset, year, value):
                self.set_calls.append((year, value))
        return RecordingProvider()

    def test_v_minus_1_autocomputed_and_earlier_years_prompted(self):
        """Fund bought 2022, sold 2025 (V=2025): holding year 2024 (V-1) is auto-computed from
        the resolved prior-year NAV (not prompted); only 2022 and 2023 are prompted."""
        from src.processing.declared_vp_resolution import resolve_declared_vp
        from tests.test_vorabpauschale import _eur_converter

        fund = _make_fund(
            soy_qty=Decimal("100"), soy_position_value=Decimal("11000"),  # end-2024 NAV = 110
            eoy_qty=Decimal("0"), eoy_position_value=Decimal("0"),        # sold: not held end-2025
            currency="EUR", description="Sold Fund",
        )
        fund.vp_prior_soy_nav_per_unit = Decimal("100")   # 1-Jan-2024 NAV
        fund.vp_prior_soy_nav_currency = "EUR"
        resolver = _make_resolver_with_fund(fund)
        aid = fund.internal_asset_id
        events = [_buy(aid, "2022-03-01", "100"), _sell(aid, "2025-04-01", "100")]

        prov = self._recording_provider()
        resolve_declared_vp(resolver, events, tax_year=2025, interactive=True,
                            provider=prov, currency_converter=_eur_converter())

        # 2024 (V-1) is auto-computed, never prompted; only 2022 and 2023 are asked.
        assert prov.prompted == [2022, 2023]
        # Basisertrag 10000 * 0.0229 * 0.7 = 160.30 (full-year factor; cap 1000 non-binding).
        assert (2024, Decimal("160.30")) in prov.set_calls
        assert fund.vp_declared_by_year[2024] == Decimal("160.30")

    def test_not_disposed_fund_is_ignored(self):
        from src.processing.declared_vp_resolution import resolve_declared_vp
        from tests.test_vorabpauschale import _eur_converter
        fund = _make_fund(currency="EUR")
        resolver = _make_resolver_with_fund(fund)
        events = [_buy(fund.internal_asset_id, "2022-03-01", "100")]  # held, not sold
        prov = self._recording_provider()
        resolve_declared_vp(resolver, events, tax_year=2025, interactive=True,
                            provider=prov, currency_converter=_eur_converter())
        assert prov.prompted == [] and prov.set_calls == []


# ---------------------------------------------------------------------------
# Form-line effect: the §19 net gain feeds Z14-26 (brutto vor Teilfreistellung)
# ---------------------------------------------------------------------------

class TestDisposalGainOnForm:
    """The VP deduction is folded into the fund disposal gain: the value on Anlage KAP-INV
    Z14-26 is brutto (vor Teilfreistellung) but already reduced by the held-period VP, and
    the Teilfreistellung is applied to that reduced gain."""

    def _fund_rgl(self, gross_after_vp, vp_deduction):
        from unittest.mock import MagicMock  # local import to keep module top tidy
        return RealizedGainLoss(
            originating_event_id=uuid.uuid4(), asset_internal_id=uuid.uuid4(),
            asset_category_at_realization=AssetCategory.INVESTMENT_FUND,
            acquisition_date="2022-05-09", realization_date="2025-01-15",
            realization_type=RealizationType.LONG_POSITION_SALE,
            quantity_realized=Decimal("100"),
            unit_cost_basis_eur=Decimal("6"), unit_realization_value_eur=Decimal("10"),
            total_cost_basis_eur=Decimal("600"), total_realization_value_eur=Decimal("1000"),
            gross_gain_loss_eur=gross_after_vp,  # 400 gross − 180 VP = 220 (still pre-TF)
            tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS,
            fund_type_at_sale=InvestmentFundType.AKTIENFONDS,
            vp_deduction_eur=vp_deduction,
        )

    def test_teilfreistellung_applies_to_reduced_gain(self):
        rgl = self._fund_rgl(gross_after_vp=Decimal("220"), vp_deduction=Decimal("180"))
        assert rgl.vp_deduction_eur == Decimal("180")
        assert rgl.gross_gain_loss_eur == Decimal("220")  # brutto n. VP, vor Teilfreistellung
        # Aktienfonds Teilfreistellung 30% applied to the reduced gain.
        assert rgl.teilfreistellung_amount_eur == Decimal("66.00")
        assert rgl.net_gain_loss_after_teilfreistellung_eur == Decimal("154.00")

    def test_net_gain_feeds_kap_inv_z14(self):
        rgl = self._fund_rgl(gross_after_vp=Decimal("220"), vp_deduction=Decimal("180"))
        resolver = MagicMock()
        resolver.get_asset_by_id.return_value = None
        engine = LossOffsettingEngine(
            realized_gains_losses=[rgl], vorabpauschale_items=[],
            current_year_financial_events=[], asset_resolver=resolver, tax_year=2025,
        )
        result = engine.calculate_reporting_figures()
        z14 = result.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS, Decimal("0"))
        # Z14 carries the brutto-after-VP gain (the Aufstellung net §19 figure, vor TF).
        assert z14 == Decimal("220.00")

    def test_vp_can_turn_gain_into_loss(self):
        """§19 permits the VP deduction to exceed the raw gain -> a deductible loss (no clamp)."""
        rgl = self._fund_rgl(gross_after_vp=Decimal("-50"), vp_deduction=Decimal("450"))
        assert rgl.gross_gain_loss_eur == Decimal("-50")
        # TF on a loss reduces its magnitude; net loss = -50 + 15 = -35 for Aktienfonds (30%).
        assert rgl.net_gain_loss_after_teilfreistellung_eur == Decimal("-35.00")


# ---------------------------------------------------------------------------
# Engine seam: FifoLedger.consume_long_lots_for_sale applies the deduction
# ---------------------------------------------------------------------------

class TestFifoLedgerAppliesDeduction:
    """End-to-end at the disposal seam: a fund ledger carrying the VP-deduction context
    reduces the realized gain by the §19 held-period VP and records the amount."""

    def _fund_ledger(self):
        import src.config as config
        from src.engine.fifo_manager import FifoLedger, FifoLot
        ledger = FifoLedger(
            asset_internal_id=uuid.uuid4(),
            asset_category=AssetCategory.INVESTMENT_FUND,
            asset_multiplier_from_asset=Decimal("1"),
            currency_converter=MagicMock(), exchange_rate_provider=MagicMock(),
            internal_working_precision=config.INTERNAL_CALCULATION_PRECISION,
            decimal_rounding_mode=config.DECIMAL_ROUNDING_MODE,
            fund_type=InvestmentFundType.AKTIENFONDS,
        )
        ledger.lots.append(FifoLot(
            acquisition_date="2022-05-09", quantity=Decimal("100"),
            unit_cost_basis_eur=Decimal("6"), total_cost_basis_eur=Decimal("600"),
            source_transaction_id="BUY1",
        ))
        return ledger

    def _sell(self, asset_id, proceeds_eur, qty="100"):
        return TradeEvent(
            asset_internal_id=asset_id, event_date="2025-01-15",
            event_type=FinancialEventType.TRADE_SELL_LONG,
            quantity=-Decimal(qty), price_foreign_currency=Decimal("10"),
            net_proceeds_or_cost_basis_eur=Decimal(proceeds_eur),
        )

    def test_deduction_reduces_realized_gain(self):
        ledger = self._fund_ledger()
        ledger.vp_declared_by_year = {2022: Decimal("50"), 2023: Decimal("60"), 2024: Decimal("70")}
        ledger.vp_qty_eoy_by_year = {2022: Decimal("100"), 2023: Decimal("100"), 2024: Decimal("100")}

        rgls = ledger.consume_long_lots_for_sale(
            self._sell(ledger.asset_internal_id, "1000"), is_historical_simulation=False)

        assert len(rgls) == 1
        rgl = rgls[0]
        # raw gain 1000 - 600 = 400; held-period VP 50+60+70 = 180; gain net of VP = 220.
        assert rgl.vp_deduction_eur == Decimal("180")
        assert rgl.gross_gain_loss_eur == Decimal("220")

    def test_no_context_means_no_deduction(self):
        """Without a declared-VP context the gain is unchanged (existing behaviour)."""
        ledger = self._fund_ledger()  # vp_declared_by_year left empty
        rgls = ledger.consume_long_lots_for_sale(
            self._sell(ledger.asset_internal_id, "1000"), is_historical_simulation=False)
        assert rgls[0].vp_deduction_eur is None
        assert rgls[0].gross_gain_loss_eur == Decimal("400")

    def test_partial_disposal_prorates_deduction_through_the_seam(self):
        """A PARTIAL FIFO disposal (sell 40 of the 100-unit lot) deducts only the sold units'
        share of the held-period VP — exercising the deduction through the real disposal code,
        not just the pure helper."""
        ledger = self._fund_ledger()  # one lot: 100 units, cost 6/unit (600 total), acq 2022-05-09
        ledger.vp_declared_by_year = {2022: Decimal("50"), 2023: Decimal("60"), 2024: Decimal("70")}
        ledger.vp_qty_eoy_by_year = {2022: Decimal("100"), 2023: Decimal("100"), 2024: Decimal("100")}

        # Sell 40 units for 400 EUR (10/unit).
        rgls = ledger.consume_long_lots_for_sale(
            self._sell(ledger.asset_internal_id, "400", qty="40"), is_historical_simulation=False)

        assert len(rgls) == 1
        rgl = rgls[0]
        assert rgl.quantity_realized == Decimal("40")
        # deduction = 40 * (50+60+70)/100 = 72 ; raw gain 400 - 40*6=240 = 160 ; net = 88.
        assert rgl.vp_deduction_eur == Decimal("72")
        assert rgl.gross_gain_loss_eur == Decimal("88")
        # The 60 unsold units remain in the lot.
        assert sum(lot.quantity for lot in ledger.lots) == Decimal("60")


# ---------------------------------------------------------------------------
# Integration guard: §18 Abs. 3 + §19 — the VP is taxed exactly once (no double tax)
# ---------------------------------------------------------------------------

class TestDeemedInflowAndSaleNoDoubleTax:
    """The exact bug this whole feature fixed: when a fund is sold in V, its V-1 Vorabpauschale
    appears on Z9-13 (income, §18 Abs. 3) AND is deducted from the Z14-26 gain (§19 Abs. 1 S. 3).
    The two must net so the economic gain is taxed once: Z13 + Z26 == gross gain *before* VP.
    (Were Z26 left un-reduced, Z13 + Z26 would over-count the VP — the double taxation.)"""

    def test_v_minus_1_vp_taxed_once_across_z13_and_z26(self):
        gross_gain_before_vp = Decimal("500.00")
        vp_v1 = Decimal("123.45")  # 2024 holding-year VP, deemed inflow 2025
        # Sonstige Fonds (0% Teilfreistellung) for clean arithmetic, like the Singapore ETF.
        rgl = RealizedGainLoss(
            originating_event_id=uuid.uuid4(), asset_internal_id=uuid.uuid4(),
            asset_category_at_realization=AssetCategory.INVESTMENT_FUND,
            acquisition_date="2023-05-01", realization_date="2025-01-15",
            realization_type=RealizationType.LONG_POSITION_SALE,
            quantity_realized=Decimal("100"),
            unit_cost_basis_eur=Decimal("1"), unit_realization_value_eur=Decimal("1"),
            total_cost_basis_eur=Decimal("0"), total_realization_value_eur=Decimal("0"),
            gross_gain_loss_eur=gross_gain_before_vp - vp_v1,  # 376.55 (net of VP, pre-TF)
            tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS,
            fund_type_at_sale=InvestmentFundType.SONSTIGE_FONDS,
            vp_deduction_eur=vp_v1,
        )
        vp = VorabpauschaleData(
            asset_internal_id=uuid.uuid4(), tax_year=2024,
            fund_value_start_year_eur=Decimal("10000"), fund_value_end_year_eur=Decimal("11000"),
            distributions_during_year_eur=Decimal("0"), base_return_rate=Decimal("0.0229"),
            basiszins=Decimal("2.29"), calculated_base_return_eur=vp_v1,
            gross_vorabpauschale_eur=vp_v1, fund_type=InvestmentFundType.SONSTIGE_FONDS,
            teilfreistellung_rate_applied=Decimal("0"), teilfreistellung_amount_eur=Decimal("0"),
            net_taxable_vorabpauschale_eur=vp_v1,
            tax_reporting_category_gross=TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO,
            deemed_inflow_year=2025,
        )
        resolver = MagicMock()
        resolver.get_asset_by_id.return_value = None
        engine = LossOffsettingEngine(
            realized_gains_losses=[rgl], vorabpauschale_items=[vp],
            current_year_financial_events=[], asset_resolver=resolver, tax_year=2025,
        )
        result = engine.calculate_reporting_figures()
        z13 = result.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO, Decimal("0"))
        z26 = result.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS, Decimal("0"))
        assert z13 == vp_v1                      # VP income on Z13
        assert z26 == Decimal("376.55")          # gain reduced by the held-period VP
        # Taxed exactly once: declared income (Z13) + reduced gain (Z26) == full economic gain.
        assert z13 + z26 == gross_gain_before_vp

"""German KESt must not reach Anlage KAP Zeile 41, by either detection route.

legal_basis: reference/tax-forms/anlage-kap-zeilen.md [GT-FORM-007] — German
Kapitalertragsteuer on a German issuer's dividend is not an ausländische Steuer
and does not belong on Zeile 41. The 26.375% composite that identifies it is
[GT-CREDIT-025] in reference/tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md,
and [GT-CREDIT-022] is why the credit cannot simply be re-declared elsewhere.

The country-code route is pinned in test_withholding_tax_linker.py. This file
pins everything that route does not reach: the rate-composite fallback for export
vintages with no country code, the precedence between the two signals, the `XX`
placeholder, and the data gap that carries the excluded amount to the user.
"""
import uuid
from decimal import Decimal

import pytest

from src.classification.asset_classifier import AssetClassifier
from src.domain.enums import TaxReportingCategory
from src.domain.events import CashFlowEvent, WithholdingTaxEvent
from src.domain.enums import FinancialEventType
from src.engine.loss_offsetting import LossOffsettingEngine
from src.identification.asset_resolver import AssetResolver
from src.processing.data_gaps import DataGapCollector, GapSeverity


ZEILE_41 = TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID


@pytest.fixture
def resolver(tmp_path):
    return AssetResolver(asset_classifier=AssetClassifier(
        cache_file_path=str(tmp_path / "cls.json")))


@pytest.fixture
def asset(resolver):
    return resolver.get_or_create_asset(
        raw_isin="DE0007164600", raw_conid="CONSAP", raw_symbol="SAP",
        raw_currency="EUR", raw_ibkr_asset_class="STK",
        raw_description="SAP SE", raw_ibkr_sub_category="COMMON",
    )


def _dividend(asset, gross_eur):
    ev = CashFlowEvent(
        asset_internal_id=asset.internal_asset_id,
        event_date="2023-05-10",
        event_type=FinancialEventType.DIVIDEND_CASH,
        gross_amount_foreign_currency=Decimal(gross_eur),
        local_currency="EUR",
    )
    ev.gross_amount_eur = Decimal(gross_eur)
    return ev


def _wht(asset, tax_eur, country=None, linked_to=None):
    ev = WithholdingTaxEvent(
        asset_internal_id=asset.internal_asset_id,
        event_date="2023-05-10",
        gross_amount_foreign_currency=Decimal(tax_eur),
        local_currency="EUR",
        source_country_code=country,
    )
    ev.gross_amount_eur = Decimal(tax_eur)
    if linked_to is not None:
        ev.taxed_income_event_id = linked_to.event_id
    return ev


def _zeile_41(events, resolver, collector=None):
    engine = LossOffsettingEngine(
        realized_gains_losses=[], vorabpauschale_items=[],
        current_year_financial_events=events, asset_resolver=resolver,
        tax_year=2023, data_gap_collector=collector,
    )
    result = engine.calculate_reporting_figures()
    return result.form_line_values.get(ZEILE_41, Decimal("0.00"))


class TestRateCompositeFallback:
    """No country code — the 26.375% composite has to carry the detection.

    This is the path that covers older broker exports, where the country column
    is essentially never populated. Without it a country filter fixes only the
    most recent assessment years.
    """

    @pytest.mark.parametrize("gross,tax", [
        ("1204.00", "317.56"),   # exactly 26.375%
        ("100.00", "26.37"),     # one cent under the exact figure
        ("100.00", "26.38"),     # one cent over
        ("50.00", "13.18"),      # small amount, rounding dominates
    ])
    def test_composite_rows_are_excluded(self, resolver, asset, gross, tax):
        div = _dividend(asset, gross)
        assert _zeile_41([div, _wht(asset, tax, country=None, linked_to=div)], resolver) == Decimal("0.00")

    @pytest.mark.parametrize("gross,tax", [
        ("100.00", "15.00"),     # treaty rate
        ("100.00", "25.00"),     # KESt without SolZ, or a foreign 25% — not decidable, stays foreign
        ("100.00", "30.00"),
        ("100.00", "26.00"),     # below the band
        ("100.00", "27.00"),     # above the band
    ])
    def test_other_rates_stay_on_zeile_41(self, resolver, asset, gross, tax):
        """The detector narrows Zeile 41 and must never widen it: anything it
        cannot identify as German keeps the pre-existing treatment."""
        div = _dividend(asset, gross)
        assert _zeile_41([div, _wht(asset, tax, country=None, linked_to=div)], resolver) == Decimal(tax)

    def test_unlinked_withholding_stays_foreign(self, resolver, asset):
        """No linked income event means no rate to test. Defaulting to German
        would silently drop a foreign credit."""
        assert _zeile_41([_wht(asset, "26.375", country=None, linked_to=None)], resolver) == Decimal("26.38")

    def test_zero_gross_income_does_not_divide(self, resolver, asset):
        div = _dividend(asset, "0.00")
        assert _zeile_41([div, _wht(asset, "26.375", country=None, linked_to=div)], resolver) == Decimal("26.38")


class TestCountryCodePrecedence:
    """The issuer country decides when the broker supplies one."""

    def test_foreign_code_wins_over_a_german_looking_rate(self, resolver, asset):
        """A US row that happens to sit at 26.375% is foreign. The country code is
        authoritative; the composite is only a fallback for when it is absent."""
        div = _dividend(asset, "1204.00")
        assert _zeile_41([div, _wht(asset, "317.56", country="US", linked_to=div)], resolver) == Decimal("317.56")

    def test_de_wins_over_a_foreign_looking_rate(self, resolver, asset):
        div = _dividend(asset, "100.00")
        assert _zeile_41([div, _wht(asset, "15.00", country="DE", linked_to=div)], resolver) == Decimal("0.00")

    @pytest.mark.parametrize("code", ["de", " DE ", "De"])
    def test_country_code_is_normalised(self, resolver, asset, code):
        assert _zeile_41([_wht(asset, "26.375", country=code)], resolver) == Decimal("0.00")

    def test_xx_is_not_a_country_and_falls_through_to_the_rate(self, resolver, asset):
        """IBKR emits XX for unknown/multiple. Treating it as a foreign country
        would disable the fallback on exactly the rows that need it."""
        div = _dividend(asset, "1204.00")
        assert _zeile_41([div, _wht(asset, "317.56", country="XX", linked_to=div)], resolver) == Decimal("0.00")


class TestTheExcludedAmountReachesTheUser:
    """Excluding from Zeile 41 without telling anyone would silently drop a credit."""

    def test_gap_is_recorded_with_the_amount(self, resolver, asset):
        collector = DataGapCollector()
        div = _dividend(asset, "1204.00")
        _zeile_41([div, _wht(asset, "317.56", country="DE", linked_to=div)], resolver, collector)
        gaps = [g for g in collector.gaps if g.code == "ANLAGE_KAP_GERMAN_KEST_NOT_DECLARABLE"]
        assert len(gaps) == 1, "the excluded KESt must reach the report, not only the log"
        assert "317.56" in gaps[0].detail
        assert "Steuerbescheinigung" in gaps[0].detail
        assert gaps[0].severity is GapSeverity.WARNING

    def test_no_gap_when_all_withholding_is_foreign(self, resolver, asset):
        collector = DataGapCollector()
        div = _dividend(asset, "100.00")
        _zeile_41([div, _wht(asset, "15.00", country="US", linked_to=div)], resolver, collector)
        assert not [g for g in collector.gaps if g.code == "ANLAGE_KAP_GERMAN_KEST_NOT_DECLARABLE"]

    def test_several_rows_are_reported_together(self, resolver, asset):
        """One run identifies the whole problem, not one item per attempt."""
        collector = DataGapCollector()
        d1, d2 = _dividend(asset, "100.00"), _dividend(asset, "200.00")
        events = [d1, d2,
                  _wht(asset, "26.375", country="DE", linked_to=d1),
                  _wht(asset, "52.75", country="DE", linked_to=d2)]
        _zeile_41(events, resolver, collector)
        gap = [g for g in collector.gaps if g.code == "ANLAGE_KAP_GERMAN_KEST_NOT_DECLARABLE"][0]
        assert "2 withholding row(s)" in gap.detail
        assert "79.13" in gap.detail

    def test_zeile_41_still_sums_the_foreign_rows_alongside(self, resolver, asset):
        """Excluding German KESt must not disturb the foreign total next to it."""
        d1, d2 = _dividend(asset, "100.00"), _dividend(asset, "200.00")
        events = [d1, d2,
                  _wht(asset, "26.375", country="DE", linked_to=d1),
                  _wht(asset, "30.00", country="US", linked_to=d2)]
        assert _zeile_41(events, resolver) == Decimal("30.00")

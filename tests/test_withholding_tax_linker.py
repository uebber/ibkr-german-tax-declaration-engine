# tests/test_withholding_tax_linker.py
import pytest
import uuid
from decimal import Decimal
from datetime import date

from src.processing.withholding_tax_linker import WithholdingTaxLinker, WithholdingTaxLink, LinkingCriteriaMatch
from src.domain.events import WithholdingTaxEvent, CashFlowEvent, FinancialEventType


class TestWithholdingTaxLinker:
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.linker = WithholdingTaxLinker()
        self.test_asset_id = uuid.uuid4()
        self.cash_asset_id = uuid.uuid4()  # For interest events
        self.test_event_date = "2023-01-27"
        
    def create_dividend_event(self, amount=Decimal("206.00"), currency="CAD", transaction_id="1633926800"):
        """Create a test dividend event."""
        return CashFlowEvent(
            asset_internal_id=self.test_asset_id,
            event_date=self.test_event_date,
            event_type=FinancialEventType.DIVIDEND_CASH,
            gross_amount_foreign_currency=amount,
            local_currency=currency,
            ibkr_transaction_id=transaction_id,
            ibkr_activity_description="BNS(CA0000000006) CASH DIVIDEND"
        )
    
    def create_withholding_tax_event(self, amount=Decimal("30.90"), currency="CAD", transaction_id="1633926801"):
        """Create a test withholding tax event."""
        return WithholdingTaxEvent(
            asset_internal_id=self.test_asset_id,
            event_date=self.test_event_date,
            source_country_code="CA",
            gross_amount_foreign_currency=amount,
            local_currency=currency,
            ibkr_transaction_id=transaction_id,
            ibkr_activity_description="BNS(CA0000000006) CASH DIVIDEND - CA TAX"
        )
    
    def create_interest_event(self, amount=Decimal("0.69"), currency="EUR", description="EUR CREDIT INT FOR FEB-2023"):
        """Create a test interest event."""
        # Use shared cash asset for interest (cash balance)
        return CashFlowEvent(
            asset_internal_id=self.cash_asset_id,
            event_date="2023-03-03",
            event_type=FinancialEventType.INTEREST_RECEIVED,
            gross_amount_foreign_currency=amount,
            local_currency=currency,
            ibkr_activity_description=description,
            ibkr_transaction_id="9000316760"
        )
    
    def create_interest_withholding_tax_event(self, amount=Decimal("0.14"), currency="EUR", description="WITHHOLDING @ 20% ON CREDIT INT FOR FEB-2023"):
        """Create a test interest withholding tax event."""
        # Use shared cash asset for interest WHT (cash balance) 
        return WithholdingTaxEvent(
            asset_internal_id=self.cash_asset_id,
            event_date="2023-03-03",
            source_country_code="IE",
            gross_amount_foreign_currency=amount,
            local_currency=currency,
            ibkr_activity_description=description,
            ibkr_transaction_id="9999999"  # Non-sequential to test pattern matching
        )
    
    def test_exact_match_dividend_withholding_tax(self):
        """Test exact match linking for dividend and withholding tax with sequential transaction IDs."""
        dividend_event = self.create_dividend_event()
        wht_event = self.create_withholding_tax_event()
        
        events = [dividend_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 1
        assert len(unlinked) == 0
        
        link = links[0]
        assert link.withholding_tax_event_id == wht_event.event_id
        assert link.linked_income_event_id == dividend_event.event_id
        assert link.link_confidence_score == 100
        assert "exact_date" in link.match_criteria
        assert "exact_asset" in link.match_criteria
        assert "exact_currency" in link.match_criteria
        assert "sequential_transaction_id" in link.match_criteria
        
        # Check that the WHT event was updated
        assert wht_event.taxed_income_event_id == dividend_event.event_id
        assert wht_event.link_confidence_score == 100
        
        # Check effective tax rate calculation
        expected_rate = Decimal("30.90") / Decimal("206.00")
        assert abs(wht_event.effective_tax_rate - expected_rate) < Decimal("0.001")
    
    def test_strong_match_without_sequential_ids(self):
        """Test strong match linking when transaction IDs are not sequential."""
        dividend_event = self.create_dividend_event(transaction_id="1000000")
        wht_event = self.create_withholding_tax_event(transaction_id="2000000")  # Not sequential
        
        events = [dividend_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 1
        assert len(unlinked) == 0
        
        link = links[0]
        assert link.link_confidence_score == 80  # Strong match, not exact
        assert "exact_date" in link.match_criteria
        assert "exact_asset" in link.match_criteria
        assert "exact_currency" in link.match_criteria
        assert "valid_amount_relationship" in link.match_criteria
        assert "sequential_transaction_id" not in link.match_criteria
    
    def test_interest_pattern_match(self):
        """Test that interest events get linked properly (may be strong match due to same asset/date/currency)."""
        interest_event = self.create_interest_event()
        wht_event = self.create_interest_withholding_tax_event()
        
        events = [interest_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 1
        assert len(unlinked) == 0
        
        link = links[0]
        # Interest events with same asset/date/currency will get strong match (80) not pattern match (70)
        assert link.link_confidence_score == 80  # Strong match due to exact criteria
        assert "exact_date" in link.match_criteria
        assert "exact_asset" in link.match_criteria
        assert "exact_currency" in link.match_criteria
        assert "valid_amount_relationship" in link.match_criteria
    
    def test_interest_pattern_match_different_assets(self):
        """Test interest pattern matching when assets are different but description patterns match."""
        # Create interest event with different asset to force pattern matching
        interest_event = self.create_interest_event()
        wht_event = self.create_interest_withholding_tax_event()
        wht_event.asset_internal_id = uuid.uuid4()  # Different asset to avoid strong match
        
        events = [interest_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        # Interest pattern matching should work even with different assets (cash accounts)
        assert len(links) == 1
        assert len(unlinked) == 0
        
        link = links[0]
        assert link.link_confidence_score == 70  # Interest pattern match
        assert "interest_wht_pattern" in link.match_criteria
        assert "exact_date" in link.match_criteria
        assert "exact_currency" in link.match_criteria
    
    def test_no_match_different_assets(self):
        """Test that events with different assets are not linked."""
        dividend_event = self.create_dividend_event()
        wht_event = self.create_withholding_tax_event()
        wht_event.asset_internal_id = uuid.uuid4()  # Different asset
        
        events = [dividend_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 0
        assert len(unlinked) == 1
        assert unlinked[0] == wht_event
    
    def test_no_match_different_currencies(self):
        """Test that events with different currencies are not linked."""
        dividend_event = self.create_dividend_event(currency="USD")
        wht_event = self.create_withholding_tax_event(currency="EUR")
        
        events = [dividend_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 0
        assert len(unlinked) == 1
    
    def test_no_match_different_dates(self):
        """Test that events with different dates are not linked (unless close proximity)."""
        dividend_event = self.create_dividend_event()
        wht_event = self.create_withholding_tax_event()
        wht_event.event_date = "2023-02-15"  # Different date, more than 3 days
        
        events = [dividend_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 0
        assert len(unlinked) == 1
    
    def test_proximity_match_close_dates(self):
        """Test proximity matching for events with close dates."""
        dividend_event = self.create_dividend_event()
        wht_event = self.create_withholding_tax_event(transaction_id="9999999")  # Non-sequential
        wht_event.event_date = "2023-01-29"  # 2 days later, within proximity threshold
        
        events = [dividend_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 1
        assert len(unlinked) == 0
        
        link = links[0]
        assert link.link_confidence_score == 60  # Proximity match
        assert "exact_asset" in link.match_criteria
        assert "exact_currency" in link.match_criteria
        assert "close_dates" in link.match_criteria
        assert "reasonable_amount_relationship" in link.match_criteria
    
    def test_invalid_amount_relationship(self):
        """Test that events with invalid amount relationships are not linked."""
        dividend_event = self.create_dividend_event(amount=Decimal("1.00"))  # Very small dividend
        wht_event = self.create_withholding_tax_event(amount=Decimal("100.00"))  # Very large tax (>50%)
        
        events = [dividend_event, wht_event]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 0
        assert len(unlinked) == 1
    
    def test_two_dividends_each_wht_pairs_with_its_own(self):
        """Realistic multi-candidate case: TWO dividends, TWO WHT events — each
        WHT must link to ITS OWN dividend (sequential transaction ids decide).

        legal_basis: GT-FORM-006 / GT-CREDIT-004 — withholding events are summed
        into ANLAGE_KAP_FOREIGN_TAX_PAID. Note what that means for this test:
        `loss_offsetting.py` sums `WithholdingTaxEvent.gross_amount_eur` over
        events and never consults the links, so a wrong link cannot by itself
        move Zeile 41. What the attribution decides is which income event a
        credit is reported against, and the previous version of this test used
        one dividend and blessed BOTH WHT events linking to it — leaving the
        attribution rule untested rather than leaving a figure wrong."""
        dividend_a = self.create_dividend_event(amount=Decimal("206.00"), transaction_id="1633926800")
        dividend_b = self.create_dividend_event(amount=Decimal("100.00"), transaction_id="1633926900")
        wht_a = self.create_withholding_tax_event(amount=Decimal("30.90"), transaction_id="1633926801")
        wht_b = self.create_withholding_tax_event(amount=Decimal("15.00"), transaction_id="1633926901")

        events = [dividend_a, dividend_b, wht_a, wht_b]
        links, unlinked = self.linker.link_withholding_tax_events(events)

        assert len(links) == 2
        assert len(unlinked) == 0
        by_wht = {l.withholding_tax_event_id: l for l in links}
        assert by_wht[wht_a.event_id].linked_income_event_id == dividend_a.event_id
        assert by_wht[wht_b.event_id].linked_income_event_id == dividend_b.event_id
        # Both are exact matches via sequential ids
        assert by_wht[wht_a.event_id].link_confidence_score == 100
        assert by_wht[wht_b.event_id].link_confidence_score == 100
        # No double-link: two distinct income events are referenced
        assert len({l.linked_income_event_id for l in links}) == 2
    
    def test_two_wht_events_against_one_dividend(self):
        """Two withholding entries against a single dividend: the engine links
        BOTH to that dividend. This pins current behaviour so a change to it is
        visible.

        legal_basis: infrastructure. No declared figure turns on it — Zeile 41
        sums the WithholdingTaxEvents themselves and never reads the links
        (see test_withholding_events_sum_into_zeile_41), and the links are
        consumed only by the console, PDF and diagnostic reports.

        The previous version of this file asserted the same shape but framed it
        as picking a "best match"; the point here is narrower and honest — an
        income event may currently carry more than one link, nothing forbids it,
        and if that ever becomes one-to-one this test is what says so.
        """
        dividend = self.create_dividend_event(transaction_id="1633926800")
        wht_1 = self.create_withholding_tax_event(transaction_id="1633926801")
        wht_2 = self.create_withholding_tax_event(transaction_id="9999999")

        links, unlinked = self.linker.link_withholding_tax_events(
            [dividend, wht_1, wht_2])

        assert len(links) == 2, "both WHT events link; nothing enforces one-to-one"
        assert len(unlinked) == 0
        assert {l.linked_income_event_id for l in links} == {dividend.event_id}, \
            "both links point at the single dividend"

    def test_withholding_events_sum_into_zeile_41(self, tmp_path):
        """The withholding events themselves — not their links — are what
        Zeile 41 is built from.

        legal_basis: GT-FORM-006 / GT-CREDIT-004 — Zeile 41 aggregates
        *foreign* withholding tax into one figure. This is a declared figure and,
        before this test, nothing in the suite asserted it: replacing the
        accumulation in `loss_offsetting.py` with `pass` left the whole suite
        green, while `docs/legal-implementation-map.md` named this file as the
        guard for both claims.

        What this test does NOT certify, on two counts:

        - The engine sums every withholding event with no country filter, which
          the map records as the known defect GT-CREDIT-025, and GT-FORM-007
          states German KESt withheld through a foreign depot does not belong in
          Zeile 41 at all. The fixture here is a Canadian asset, so the expected
          value is unaffected either way and this test keeps passing once the
          filter is added.
        - GT-CREDIT-005 and GT-CREDIT-006 impose a per-Kapitalertrag and a
          per-VZ ceiling. The engine applies neither — the map records that the
          Finanzamt does — and nothing in the store says the taxpayer enters the
          uncapped figure. This fixture carries no Kapitalertrag at all, so the
          assertion cannot observe either ceiling in any direction.

        The value asserted here is therefore the aggregation rule and nothing
        beyond it.
        """
        from src.engine.loss_offsetting import LossOffsettingEngine
        from src.domain.enums import TaxReportingCategory
        from src.identification.asset_resolver import AssetResolver
        from src.classification.asset_classifier import AssetClassifier

        resolver = AssetResolver(asset_classifier=AssetClassifier(
            cache_file_path=str(tmp_path / "cls.json")))
        asset = resolver.get_or_create_asset(
            raw_isin="CA0000000006", raw_conid="CONBNS", raw_symbol="BNS",
            raw_currency="CAD", raw_ibkr_asset_class="STK",
            raw_description="BANK OF NOVA SCOTIA", raw_ibkr_sub_category="COMMON",
        )

        wht_a = self.create_withholding_tax_event(amount=Decimal("30.90"), transaction_id="1633926801")
        wht_a.asset_internal_id = asset.internal_asset_id
        wht_a.gross_amount_eur = Decimal("21.00")
        wht_b = self.create_withholding_tax_event(amount=Decimal("15.00"), transaction_id="1633926901")
        wht_b.asset_internal_id = asset.internal_asset_id
        wht_b.gross_amount_eur = Decimal("10.50")

        engine = LossOffsettingEngine(
            realized_gains_losses=[],
            vorabpauschale_items=[],
            current_year_financial_events=[wht_a, wht_b],
            asset_resolver=resolver,
            tax_year=2023,
        )
        form = engine.calculate_reporting_figures()

        assert form.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID, Decimal("0.00")
        ) == Decimal("31.50"), "Zeile 41 aggregates the withholding events' EUR amounts (GT-FORM-006)"

    def test_german_kest_is_excluded_from_zeile_41(self, tmp_path):
        """German Kapitalertragsteuer must not be declared as anrechenbare
        ausländische Steuer.

        legal_basis: GT-FORM-007 — "German Kapitalertragsteuer withheld on a
        German issuer's dividend is **not** an ausländische Steuer and does not
        belong in Zeile 41." It is credited through Zeile 7 with Zeilen 37/38/39.

        Written as xfail(strict=True) while GT-CREDIT-025 was an open defect, so
        that the day a filter landed it would XPASS and strict would force the
        marker's removal rather than leave a stale xfail behind. The filter
        landed; the marker is gone. The mechanism worked as intended.

        This asserts the **country-code** route only — it sets source_country_code
        explicitly. The rate-composite fallback, which is what covers export
        vintages carrying no country code, is pinned separately in
        test_german_kest_detection.py. Passing this test alone would not mean the
        defect is fixed.

        The credit is not re-declared anywhere: GT-FORM-007 routes it to Zeilen
        7/37/38/39, but those are transcribed from a Steuerbescheinigung and
        § 36 Abs. 2 Satz 2 bars the credit without one, so the engine reports the
        amount through the data-gap channel instead of computing a line the form
        defines as copied.
        """
        from src.engine.loss_offsetting import LossOffsettingEngine
        from src.domain.enums import TaxReportingCategory
        from src.identification.asset_resolver import AssetResolver
        from src.classification.asset_classifier import AssetClassifier

        resolver = AssetResolver(asset_classifier=AssetClassifier(
            cache_file_path=str(tmp_path / "cls.json")))
        german = resolver.get_or_create_asset(
            raw_isin="DE0007164600", raw_conid="CONSAP", raw_symbol="SAP",
            raw_currency="EUR", raw_ibkr_asset_class="STK",
            raw_description="SAP SE", raw_ibkr_sub_category="COMMON",
        )

        kest = self.create_withholding_tax_event(amount=Decimal("26.375"), currency="EUR")
        kest.asset_internal_id = german.internal_asset_id
        kest.source_country_code = "DE"
        kest.gross_amount_eur = Decimal("26.375")

        engine = LossOffsettingEngine(
            realized_gains_losses=[],
            vorabpauschale_items=[],
            current_year_financial_events=[kest],
            asset_resolver=resolver,
            tax_year=2023,
        )
        form = engine.calculate_reporting_figures()

        assert form.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID, Decimal("0.00")
        ) == Decimal("0.00"), "German KESt is not an ausländische Steuer (GT-FORM-007)"

    def test_is_sequential_transaction_id(self):
        """Test the sequential transaction ID logic."""
        wht_event = self.create_withholding_tax_event(transaction_id="1000002")
        income_event = self.create_dividend_event(transaction_id="1000001")
        
        assert self.linker._is_sequential_transaction_id(wht_event, income_event) == True
        
        # Test non-sequential
        wht_event.ibkr_transaction_id = "2000000"
        assert self.linker._is_sequential_transaction_id(wht_event, income_event) == False
        
        # Test too large gap
        wht_event.ibkr_transaction_id = "1000010"  # Gap of 9
        assert self.linker._is_sequential_transaction_id(wht_event, income_event) == False
    
    def test_calculate_effective_tax_rate(self):
        """Test effective tax rate calculation."""
        wht_event = self.create_withholding_tax_event(amount=Decimal("15.00"))
        income_event = self.create_dividend_event(amount=Decimal("100.00"))
        
        rate = self.linker._calculate_effective_tax_rate(wht_event, income_event)
        assert rate == Decimal("0.15")  # 15%
        
        # Test with zero income
        income_event.gross_amount_foreign_currency = Decimal("0.00")
        rate = self.linker._calculate_effective_tax_rate(wht_event, income_event)
        assert rate is None
    
    def test_extract_period_from_description(self):
        """Test period extraction from interest descriptions."""
        test_cases = [
            ("EUR CREDIT INT FOR FEB-2023", ("FEB", "2023")),
            ("WITHHOLDING @ 20% ON CREDIT INT FOR MAR-2024", ("MAR", "2024")),
            ("Some other description", None),
            ("", None)
        ]
        
        for description, expected in test_cases:
            result = self.linker._extract_period_from_description(description)
            assert result == expected
    
    def test_validate_interest_tax_rate(self):
        """Test interest tax rate validation (should be around 20%)."""
        wht_event = self.create_interest_withholding_tax_event(amount=Decimal("20.00"))
        interest_event = self.create_interest_event(amount=Decimal("100.00"))
        
        # 20% tax rate should be valid for interest
        assert self.linker._validate_interest_tax_rate(wht_event, interest_event) == True
        
        # 50% tax rate should be invalid for interest
        wht_event.gross_amount_foreign_currency = Decimal("50.00")
        assert self.linker._validate_interest_tax_rate(wht_event, interest_event) == False
        
        # 10% tax rate should be invalid for interest (too low)
        wht_event.gross_amount_foreign_currency = Decimal("10.00")
        assert self.linker._validate_interest_tax_rate(wht_event, interest_event) == False


if __name__ == "__main__":
    # Run basic smoke test
    test_instance = TestWithholdingTaxLinker()
    test_instance.setup_method()
    test_instance.test_exact_match_dividend_withholding_tax()
    print("Basic smoke test passed!")
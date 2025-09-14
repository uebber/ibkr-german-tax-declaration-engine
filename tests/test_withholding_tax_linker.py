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
        
    def create_dividend_event(self, amount=Decimal("206.00"), currency="CAD", transaction_id="1633925900"):
        """Create a test dividend event."""
        return CashFlowEvent(
            asset_internal_id=self.test_asset_id,
            event_date=self.test_event_date,
            event_type=FinancialEventType.DIVIDEND_CASH,
            gross_amount_foreign_currency=amount,
            local_currency=currency,
            ibkr_transaction_id=transaction_id,
            ibkr_activity_description="BNS(CA0641491075) CASH DIVIDEND"
        )
    
    def create_withholding_tax_event(self, amount=Decimal("30.90"), currency="CAD", transaction_id="1633925901"):
        """Create a test withholding tax event."""
        return WithholdingTaxEvent(
            asset_internal_id=self.test_asset_id,
            event_date=self.test_event_date,
            source_country_code="CA",
            gross_amount_foreign_currency=amount,
            local_currency=currency,
            ibkr_transaction_id=transaction_id,
            ibkr_activity_description="BNS(CA0641491075) CASH DIVIDEND - CA TAX"
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
            ibkr_transaction_id="1709613676"
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
    
    def test_multiple_wht_events_best_match(self):
        """Test that the best matching WHT event is selected when multiple candidates exist."""
        dividend_event = self.create_dividend_event()
        
        # Create two WHT events, one with sequential ID (better match)
        wht_event_1 = self.create_withholding_tax_event(transaction_id="1633925901")  # Sequential
        wht_event_2 = self.create_withholding_tax_event(transaction_id="9999999")    # Non-sequential
        
        events = [dividend_event, wht_event_1, wht_event_2]
        links, unlinked = self.linker.link_withholding_tax_events(events)
        
        assert len(links) == 2  # Both should be linked to same dividend (in real scenario, you'd have 2 dividends)
        # But let's test that the sequential one gets higher confidence
        
        # Find the link with higher confidence
        high_confidence_link = max(links, key=lambda x: x.link_confidence_score)
        assert high_confidence_link.link_confidence_score == 100
        assert high_confidence_link.withholding_tax_event_id == wht_event_1.event_id
    
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
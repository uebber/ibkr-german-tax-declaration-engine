# src/processing/withholding_tax_linker.py
import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Dict, Set, Tuple, Union

from src.domain.events import (
    FinancialEvent, WithholdingTaxEvent, CashFlowEvent, 
    FinancialEventType
)

logger = logging.getLogger(__name__)

@dataclass
class WithholdingTaxLink:
    """Represents a link between a withholding tax event and its underlying income event."""
    withholding_tax_event_id: uuid.UUID
    linked_income_event_id: uuid.UUID
    link_confidence_score: int  # 0-100
    match_criteria: List[str]  # List of criteria that matched
    effective_tax_rate: Optional[Decimal] = None
    linking_notes: Optional[str] = None

@dataclass
class LinkingCriteriaMatch:
    """Represents the strength of a match between WHT and income events."""
    candidate_event_id: uuid.UUID
    confidence_score: int
    match_criteria: List[str]
    effective_tax_rate: Optional[Decimal] = None
    notes: Optional[str] = None

class WithholdingTaxLinker:
    """
    Links withholding tax events to their underlying income-generating transactions.
    Implements comprehensive matching logic based on observed transaction patterns.
    """
    
    def __init__(self):
        self.wht_on_interest_pattern = re.compile(
            r"WITHHOLDING\s*(?:@\s*(\d{1,3}(?:\.\d+)?)%)?\s*ON\s*(?:CREDIT\s*)?INT(?:EREST)?.*",
            re.IGNORECASE
        )
        self.period_extraction_pattern = re.compile(
            r"(?:FOR\s+|OF\s+)?([A-Z]{3})-?(\d{4})",
            re.IGNORECASE
        )
        
    def link_withholding_tax_events(
        self, 
        all_events: List[FinancialEvent]
    ) -> Tuple[List[WithholdingTaxLink], List[WithholdingTaxEvent]]:
        """
        Main entry point for linking withholding tax events to income events.
        
        Returns:
            Tuple of (successful_links, unlinked_wht_events)
        """
        logger.info("Starting withholding tax linking process...")
        
        # Separate WHT events from potential income events
        wht_events = [e for e in all_events if isinstance(e, WithholdingTaxEvent)]
        income_events = [e for e in all_events if self._is_potential_income_event(e)]
        
        logger.info(f"Found {len(wht_events)} withholding tax events and {len(income_events)} potential income events")
        
        successful_links: List[WithholdingTaxLink] = []
        unlinked_wht_events: List[WithholdingTaxEvent] = []
        
        for wht_event in wht_events:
            best_match = self._find_best_match(wht_event, income_events)
            
            if best_match and best_match.confidence_score >= 50:  # Minimum confidence threshold
                link = WithholdingTaxLink(
                    withholding_tax_event_id=wht_event.event_id,
                    linked_income_event_id=best_match.candidate_event_id,
                    link_confidence_score=best_match.confidence_score,
                    match_criteria=best_match.match_criteria,
                    effective_tax_rate=best_match.effective_tax_rate,
                    linking_notes=best_match.notes
                )
                successful_links.append(link)
                
                # Update the WHT event with linking information
                wht_event.taxed_income_event_id = best_match.candidate_event_id
                wht_event.link_confidence_score = best_match.confidence_score
                wht_event.effective_tax_rate = best_match.effective_tax_rate
                
                logger.debug(f"Linked WHT event {wht_event.event_id} to income event {best_match.candidate_event_id} with confidence {best_match.confidence_score}")
            else:
                unlinked_wht_events.append(wht_event)
                logger.warning(f"Could not link WHT event {wht_event.event_id} (Date: {wht_event.event_date}, Amount: {wht_event.gross_amount_foreign_currency} {wht_event.local_currency})")
        
        logger.info(f"Linking complete: {len(successful_links)} successful links, {len(unlinked_wht_events)} unlinked WHT events")
        return successful_links, unlinked_wht_events
    
    def _is_potential_income_event(self, event: FinancialEvent) -> bool:
        """Check if an event could generate income subject to withholding tax."""
        if not isinstance(event, CashFlowEvent):
            return False
            
        income_event_types = {
            FinancialEventType.DIVIDEND_CASH,
            FinancialEventType.DISTRIBUTION_FUND,
            FinancialEventType.INTEREST_RECEIVED,
            FinancialEventType.PAYMENT_IN_LIEU_DIVIDEND,
            FinancialEventType.CAPITAL_REPAYMENT
        }
        
        return event.event_type in income_event_types
    
    def _find_best_match(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_events: List[FinancialEvent]
    ) -> Optional[LinkingCriteriaMatch]:
        """Find the best matching income event for a withholding tax event."""
        
        candidate_matches: List[LinkingCriteriaMatch] = []
        
        for income_event in income_events:
            # Try different matching strategies in order of confidence
            match = self._try_exact_match(wht_event, income_event)
            if not match:
                match = self._try_strong_match(wht_event, income_event)
            if not match:
                match = self._try_interest_pattern_match(wht_event, income_event)
            if not match:
                match = self._try_proximity_match(wht_event, income_event)
            
            if match:
                candidate_matches.append(match)
        
        # Return the match with highest confidence score
        if candidate_matches:
            return max(candidate_matches, key=lambda m: m.confidence_score)
        
        return None
    
    def _try_exact_match(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent
    ) -> Optional[LinkingCriteriaMatch]:
        """
        Exact match strategy: Same date, asset, currency, and sequential transaction IDs.
        Confidence: 100
        """
        if not isinstance(income_event, CashFlowEvent):
            return None
            
        criteria_met = []
        
        # Same date
        if wht_event.event_date == income_event.event_date:
            criteria_met.append("exact_date")
        else:
            return None
            
        # Same asset
        if wht_event.asset_internal_id == income_event.asset_internal_id:
            criteria_met.append("exact_asset")
        else:
            return None
            
        # Same currency
        if wht_event.local_currency == income_event.local_currency:
            criteria_met.append("exact_currency")
        else:
            return None
            
        # Sequential transaction IDs
        if self._is_sequential_transaction_id(wht_event, income_event):
            criteria_met.append("sequential_transaction_id")
            
            # Even for exact matches, validate amount relationship as a sanity check
            if not self._validate_amount_relationship(wht_event, income_event, tolerance=0.3):  # More lenient for exact matches
                return None
            
            # Calculate effective tax rate
            tax_rate = self._calculate_effective_tax_rate(wht_event, income_event)
            
            return LinkingCriteriaMatch(
                candidate_event_id=income_event.event_id,
                confidence_score=100,
                match_criteria=criteria_met,
                effective_tax_rate=tax_rate,
                notes="Perfect match - exact criteria with sequential transaction IDs"
            )
        
        return None
    
    def _try_strong_match(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent
    ) -> Optional[LinkingCriteriaMatch]:
        """
        Strong match strategy: Same date, asset, currency, with validated amount relationship.
        Confidence: 80
        """
        if not isinstance(income_event, CashFlowEvent):
            return None
            
        criteria_met = []
        
        # Same date
        if wht_event.event_date == income_event.event_date:
            criteria_met.append("exact_date")
        else:
            return None
            
        # Same asset
        if wht_event.asset_internal_id == income_event.asset_internal_id:
            criteria_met.append("exact_asset")
        else:
            return None
            
        # Same currency
        if wht_event.local_currency == income_event.local_currency:
            criteria_met.append("exact_currency")
        else:
            return None
            
        # Validate amount relationship
        if self._validate_amount_relationship(wht_event, income_event):
            criteria_met.append("valid_amount_relationship")
            
            tax_rate = self._calculate_effective_tax_rate(wht_event, income_event)
            
            return LinkingCriteriaMatch(
                candidate_event_id=income_event.event_id,
                confidence_score=80,
                match_criteria=criteria_met,
                effective_tax_rate=tax_rate,
                notes="Strong match - exact criteria with validated amount relationship"
            )
        else:
            # Amount relationship is invalid, don't link
            return None
        
        return None
    
    def _try_interest_pattern_match(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent
    ) -> Optional[LinkingCriteriaMatch]:
        """
        Interest pattern match: Special logic for interest withholding based on description patterns.
        Confidence: 70
        """
        if not isinstance(income_event, CashFlowEvent):
            return None
            
        if income_event.event_type != FinancialEventType.INTEREST_RECEIVED:
            return None
            
        criteria_met = []
        
        # Check if WHT description matches interest withholding pattern
        wht_desc = (wht_event.ibkr_activity_description or "").upper()
        if not self.wht_on_interest_pattern.match(wht_desc):
            return None
            
        criteria_met.append("interest_wht_pattern")
        
        # Same date
        if wht_event.event_date == income_event.event_date:
            criteria_met.append("exact_date")
        else:
            return None
            
        # Same currency
        if wht_event.local_currency == income_event.local_currency:
            criteria_met.append("exact_currency")
        else:
            return None
            
        # Extract period from descriptions
        wht_period = self._extract_period_from_description(wht_desc)
        income_desc = (income_event.ibkr_activity_description or "").upper()
        income_period = self._extract_period_from_description(income_desc)
        
        if wht_period and income_period and wht_period == income_period:
            criteria_met.append("description_period_match")
        
        # Validate interest tax rate (typically 20% for EU interest)
        if self._validate_interest_tax_rate(wht_event, income_event):
            criteria_met.append("valid_interest_tax_rate")
        
        if len(criteria_met) >= 3:  # At least pattern + date + currency
            tax_rate = self._calculate_effective_tax_rate(wht_event, income_event)
            
            return LinkingCriteriaMatch(
                candidate_event_id=income_event.event_id,
                confidence_score=70,
                match_criteria=criteria_met,
                effective_tax_rate=tax_rate,
                notes="Interest pattern match - based on description patterns and timing"
            )
        
        return None
    
    def _try_proximity_match(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent
    ) -> Optional[LinkingCriteriaMatch]:
        """
        Proximity match: Fallback strategy for same asset/currency with close dates.
        Confidence: 60
        """
        if not isinstance(income_event, CashFlowEvent):
            return None
            
        criteria_met = []
        
        # Same asset
        if wht_event.asset_internal_id == income_event.asset_internal_id:
            criteria_met.append("exact_asset")
        else:
            return None
            
        # Same currency
        if wht_event.local_currency == income_event.local_currency:
            criteria_met.append("exact_currency")
        else:
            return None
            
        # Close dates (within 3 days)
        if self._are_dates_close(wht_event.event_date, income_event.event_date, max_days=3):
            criteria_met.append("close_dates")
        else:
            return None
            
        # Reasonable amount relationship
        if self._validate_amount_relationship(wht_event, income_event, tolerance=0.5):
            criteria_met.append("reasonable_amount_relationship")
            
            tax_rate = self._calculate_effective_tax_rate(wht_event, income_event)
            
            return LinkingCriteriaMatch(
                candidate_event_id=income_event.event_id,
                confidence_score=60,
                match_criteria=criteria_met,
                effective_tax_rate=tax_rate,
                notes="Proximity match - same asset/currency with close timing"
            )
        
        return None
    
    def _is_sequential_transaction_id(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent
    ) -> bool:
        """Check if transaction IDs are sequential (WHT typically follows income)."""
        wht_tx_id = wht_event.ibkr_transaction_id
        income_tx_id = income_event.ibkr_transaction_id
        
        if not wht_tx_id or not income_tx_id:
            return False
            
        try:
            wht_id_num = int(wht_tx_id)
            income_id_num = int(income_tx_id)
            
            # WHT should be 1-5 IDs after income event
            return 1 <= (wht_id_num - income_id_num) <= 5
        except ValueError:
            return False
    
    def _validate_amount_relationship(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent,
        tolerance: float = 0.1
    ) -> bool:
        """Validate that WHT amount is a reasonable percentage of income amount."""
        if not income_event.gross_amount_foreign_currency or not wht_event.gross_amount_foreign_currency:
            return False
            
        if income_event.gross_amount_foreign_currency <= Decimal('0'):
            return False
            
        tax_rate = wht_event.gross_amount_foreign_currency / income_event.gross_amount_foreign_currency
        
        # Reasonable tax rates: 5% to 50%
        min_rate = Decimal('0.05') - Decimal(str(tolerance))
        max_rate = Decimal('0.50') + Decimal(str(tolerance))
        
        return min_rate <= tax_rate <= max_rate
    
    def _validate_interest_tax_rate(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent
    ) -> bool:
        """Validate tax rate for interest withholding (typically 20% in EU)."""
        if not income_event.gross_amount_foreign_currency or not wht_event.gross_amount_foreign_currency:
            return False
            
        if income_event.gross_amount_foreign_currency <= Decimal('0'):
            return False
            
        tax_rate = wht_event.gross_amount_foreign_currency / income_event.gross_amount_foreign_currency
        
        # Interest withholding is typically 20% (+/- 2%)
        return Decimal('0.18') <= tax_rate <= Decimal('0.22')
    
    def _calculate_effective_tax_rate(
        self, 
        wht_event: WithholdingTaxEvent, 
        income_event: FinancialEvent
    ) -> Optional[Decimal]:
        """Calculate the effective tax rate from WHT and income amounts."""
        if not income_event.gross_amount_foreign_currency or not wht_event.gross_amount_foreign_currency:
            return None
            
        if income_event.gross_amount_foreign_currency <= Decimal('0'):
            return None
            
        return wht_event.gross_amount_foreign_currency / income_event.gross_amount_foreign_currency
    
    def _extract_period_from_description(self, description: str) -> Optional[Tuple[str, str]]:
        """Extract month-year period from description (e.g., 'FEB-2023' -> ('FEB', '2023'))."""
        match = self.period_extraction_pattern.search(description)
        if match:
            return (match.group(1).upper(), match.group(2))
        return None
    
    def _are_dates_close(self, date1: str, date2: str, max_days: int = 3) -> bool:
        """Check if two ISO date strings are within max_days of each other."""
        try:
            from datetime import datetime
            d1 = datetime.fromisoformat(date1)
            d2 = datetime.fromisoformat(date2)
            return abs((d2 - d1).days) <= max_days
        except ValueError:
            return False
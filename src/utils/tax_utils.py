# src/utils/tax_utils.py
from decimal import Decimal
from typing import Optional
from src.domain.enums import InvestmentFundType

def get_teilfreistellung_rate_for_fund_type(fund_type: Optional[InvestmentFundType]) -> Decimal:
    """
    Returns the Teilfreistellung (partial exemption) rate for a given fund type.
    Rates are for private investors, shares acquired after 01.01.2018.
    Returns Decimal('0.00') if fund_type is None or not specifically handled with a non-zero rate.
    """
    if fund_type == InvestmentFundType.AKTIENFONDS:
        return Decimal('0.30')  # 30% for equity funds
    if fund_type == InvestmentFundType.MISCHFONDS:
        return Decimal('0.15')  # 15% for mixed funds
    if fund_type == InvestmentFundType.IMMOBILIENFONDS:
        return Decimal('0.60')  # 60% for real estate funds (domestic focus)
    if fund_type == InvestmentFundType.AUSLANDS_IMMOBILIENFONDS:
        return Decimal('0.80')  # 80% for real estate funds (foreign focus)
    
    # Covers InvestmentFundType.SONSTIGE_FONDS, InvestmentFundType.NONE, or Python None input
    return Decimal('0.00')
        
    # return None # Should ideally not be reached if fund_type is always a valid enum member

# src/utils/tax_utils.py
"""Compatibility shim: Teilfreistellung rates live in the
law-as-data registry (src/tax_law/registry.py, §20 InvStG citations there)."""
from decimal import Decimal
from typing import Optional

from src.domain.enums import InvestmentFundType
from src.tax_law.registry import teilfreistellung_rate


def get_teilfreistellung_rate_for_fund_type(fund_type: Optional[InvestmentFundType]) -> Decimal:
    """Teilfreistellung (partial exemption) rate for a fund type; private
    investors, units acquired after 01.01.2018. Delegates to the registry."""
    return teilfreistellung_rate(fund_type)

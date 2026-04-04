# src/reporting/form_rules.py
"""
Year-specific rules for German tax form (Anlage KAP) calculations.

Key change in 2025: The Verlustverrechnungsbeschränkung (loss offsetting
restriction) for Termingeschäfte (§20 Abs. 6 Satz 5 and 6 EStG) was abolished.
This means:
- Derivative losses no longer require separate declaration in Z24
- Derivative gains no longer require separate declaration in Z21
- Derivative losses are fully deductible (no 20k EUR annual cap)
- Z19 now subtracts derivative losses alongside other losses
- Z22 now includes derivative losses (combined with other non-stock losses)
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormYearRules:
    """Encapsulates year-specific differences in Anlage KAP form logic."""

    # Whether Termingeschäfte have separate form lines (Z21 for gains, Z24 for losses)
    separate_derivative_lines: bool

    # Whether the 20,000 EUR annual cap on derivative losses applies (conceptual)
    derivative_loss_cap_applies: bool

    # Whether the Z19 net calculation subtracts derivative losses
    z19_subtracts_derivative_losses: bool

    # Whether Z22 (Sonstige Verluste) includes derivative losses
    z22_includes_derivative_losses: bool


# Registry of year-specific rules.
# Years not listed fall back to the nearest earlier year.
_FORM_RULES_BY_YEAR = {
    2024: FormYearRules(
        separate_derivative_lines=True,
        derivative_loss_cap_applies=True,
        z19_subtracts_derivative_losses=False,
        z22_includes_derivative_losses=False,
    ),
    2025: FormYearRules(
        separate_derivative_lines=False,
        derivative_loss_cap_applies=False,
        z19_subtracts_derivative_losses=True,
        z22_includes_derivative_losses=True,
    ),
}


def get_form_rules(tax_year: int) -> FormYearRules:
    """Get form rules for a given tax year.

    Looks up exact year first. If not found, falls back to the highest
    year that is <= tax_year. If tax_year is before all known years,
    uses the earliest known year's rules.
    """
    if tax_year in _FORM_RULES_BY_YEAR:
        return _FORM_RULES_BY_YEAR[tax_year]

    available_years = sorted(_FORM_RULES_BY_YEAR.keys())
    fallback_year = None
    for year in available_years:
        if year <= tax_year:
            fallback_year = year

    if fallback_year is not None:
        logger.info(f"No form rules defined for tax year {tax_year}, falling back to {fallback_year} rules.")
        return _FORM_RULES_BY_YEAR[fallback_year]

    # tax_year is before all known years — use earliest
    earliest = available_years[0]
    logger.info(f"No form rules defined for tax year {tax_year}, falling back to earliest known year {earliest}.")
    return _FORM_RULES_BY_YEAR[earliest]

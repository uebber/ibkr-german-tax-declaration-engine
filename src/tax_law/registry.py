# src/tax_law/registry.py
"""
Law-as-data registry — the SINGLE home of year-parameterized German tax-law
values. Engine and tests read the SAME tables; every entry carries its
statutory citation; lookups outside an entry's validity are LOUD, never a
silent zero.

Layering, as it actually stands: the computation core emits year-agnostic
`TaxReportingCategory` totals, and the year-specific *branching* between form
structures happens only through `get_form_rules(tax_year)` defined here. That
is not the same as being the only Zeilen-aware layer — the category enum names
carry Zeilen semantics, and `console_reporter.py` / `pdf_generator.py` print
line numbers directly. Concentrating the branching here is the property to
preserve; single-point Zeilen knowledge is not yet true.

Sources of truth mirrored here (machine-readable side of `reference/`):
- Basiszins:        reference/bmf-guidance/basiszins-vorabpauschale.md (BStBl I)
- Teilfreistellung: reference/investment-tax-law/invstg-20-teilfreistellung.md
- Form structure:   reference/tax-law/estg-20-abs6-verlustverrechnung.md,
                    reference/tax-forms/anlage-kap-zeilen.md
`tests/test_tax_law_registry.py` pins registry <-> reference consistency.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.domain.enums import InvestmentFundType

logger = logging.getLogger(__name__)


# =============================================================================
# Basiszins (§18 Abs. 4 InvStG) — BMF-published, percent values
# =============================================================================
# Negative years (2021/2022) are deliberately PRESENT: a negative Basiszins is
# a computed zero Vorabpauschale, not a configuration gap.
# Citation: BMF Basiszins notices, BStBl I (per-year links in the reference doc).

# The series starts in 2018: the Vorabpauschale was introduced by the InvStG
# 2018, whose provisions "sind ab dem 1. Januar 2018 anzuwenden" (§56 Abs. 1
# Satz 1 InvStG). No §18 Abs. 4 InvStG Basiszins exists for 2016 or 2017 — the
# 1.10%/0.59% once listed for those years are the §203 Abs. 2 BewG Basiszins
# (a different statute); see the reference doc.
INVSTG_2018_FIRST_BASISZINS_YEAR = 2018

BASISZINS_PCT: dict[int, Decimal] = {
    2018: Decimal("0.87"),
    2019: Decimal("0.52"),
    2020: Decimal("0.07"),
    2021: Decimal("-0.45"),  # negative -> Basisertrag <= 0 -> no Vorabpauschale
    2022: Decimal("-0.05"),  # negative -> Basisertrag <= 0 -> no Vorabpauschale
    2023: Decimal("2.55"),
    2024: Decimal("2.29"),
    2025: Decimal("2.53"),
    2026: Decimal("3.20"),
}


def basiszins_pct(year: int) -> Optional[Decimal]:
    """BMF-published Basiszins for `year` in percent, or None if unavailable.

    Two ways to be absent, logged differently because they mean opposite things:

    - `year` predates the InvStG-2018 regime (§56 Abs. 1 S. 1 InvStG): there was
      no Vorabpauschale at all. INFO — nothing is being missed.
    - `year` is 2018 or later: a rate WAS published and the table lacks it.
      WARNING — skipping understates deemed income (§18 InvStG). Add the rate."""
    value = BASISZINS_PCT.get(year)
    if value is None:
        if year < INVSTG_2018_FIRST_BASISZINS_YEAR:
            logger.info(
                f"No Vorabpauschale for year {year}: the InvStG 2018 regime "
                f"applies from 1 January {INVSTG_2018_FIRST_BASISZINS_YEAR} "
                f"(§56 Abs. 1 Satz 1 InvStG), so no Basiszins was published."
            )
        else:
            logger.warning(
                f"No Basiszins in the tax-law registry for year {year} — SKIPPING "
                f"its Vorabpauschale computation. If funds were held through "
                f"{year} and the BMF-published Basiszins for that year was "
                f"positive, deemed income is being understated. Add the rate to "
                f"src/tax_law/registry.py (source: "
                f"reference/bmf-guidance/basiszins-vorabpauschale.md)."
            )
    return value


# =============================================================================
# Teilfreistellung (§20 InvStG) — private investors, units acquired >= 2018
# =============================================================================
# §20 Abs. 1 S. 1 (Aktienfonds 30%), Abs. 2 (Mischfonds 15%),
# Abs. 3 S. 1 Nr. 1 (Immobilienfonds 60%), Nr. 2 (Auslands-Immobilien 80%).
# Sonstige Fonds / unknown: no provision -> 0%.

TEILFREISTELLUNG_RATES: dict[InvestmentFundType, Decimal] = {
    InvestmentFundType.AKTIENFONDS: Decimal("0.30"),
    InvestmentFundType.MISCHFONDS: Decimal("0.15"),
    InvestmentFundType.IMMOBILIENFONDS: Decimal("0.60"),
    InvestmentFundType.AUSLANDS_IMMOBILIENFONDS: Decimal("0.80"),
}


def teilfreistellung_rate(fund_type: Optional[InvestmentFundType]) -> Decimal:
    """Teilfreistellung rate for a fund type (0 for Sonstige/None — no
    statutory provision, full amount taxable)."""
    if fund_type is None:
        return Decimal("0.00")
    return TEILFREISTELLUNG_RATES.get(fund_type, Decimal("0.00"))


# =============================================================================
# Anlage KAP form structure per assessment year (§20 Abs. 6 EStG)
# =============================================================================
# The €20k Termingeschäft loss cap (§20 Abs. 6 S. 5/6 a.F.) was abolished by
# JStG 2024 (BGBl. I 2024 Nr. 387). Its scope comes from the application rule:
# §52 Abs. 28 Satz 25 EStG n.F. (Termingeschäfte) and Satz 26 (Forderungs-
# ausfälle) each order that the a.F. sentence "ist auf alle offenen Fälle nicht
# mehr anzuwenden" — therefore derivative_loss_cap_applies is False for EVERY
# year: a return prepared today, including VZ 2021-2024, is not subject to it.
#
# Only the FORM STRUCTURE remains year-specific:
#   VZ <= 2024: derivative gains/losses declared separately on Z21/Z24; Z19
#               does not subtract derivative losses; Z22 excludes them.
#   VZ >= 2025: Z21/Z24 removed; derivative gains AND losses flow through Z19;
#               Z22 includes derivative losses with other non-stock losses.

@dataclass(frozen=True)
class FormYearRules:
    """Year-specific differences in the Anlage KAP form projection."""
    separate_derivative_lines: bool       # Z21/Z24 exist on the form
    derivative_loss_cap_applies: bool     # repealed retroactively: always False
    z19_subtracts_derivative_losses: bool
    z22_includes_derivative_losses: bool


_FORM_RULES_BY_YEAR: dict[int, FormYearRules] = {
    2024: FormYearRules(
        separate_derivative_lines=True,
        derivative_loss_cap_applies=False,  # JStG 2024 (§52 Abs. 28 S. 25)
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
    """Form rules for an assessment year. Exact year first; otherwise the
    nearest EARLIER configured year (form structures persist until changed);
    years before all configured ones use the earliest, so VZ 2021-2023 are
    served the 2024 entry.

    That fallback is an engine convention, not a verified mapping: the Zeilen
    are checked against the official Anleitung for 2024 and 2025 only. See
    reference/tax-law/estg-20-abs6-verlustverrechnung.md."""
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

    earliest = available_years[0]
    logger.info(f"No form rules defined for tax year {tax_year}, falling back to earliest known year {earliest}.")
    return _FORM_RULES_BY_YEAR[earliest]

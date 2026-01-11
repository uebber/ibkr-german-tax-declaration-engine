"""
Shared Schema Definitions for Test Specifications

This module contains dataclass definitions used across multiple test spec files.
These provide type-safe, IDE-friendly structures for complex test data.

PRD Reference: These schemas capture the domain model concepts from the PRD
for tax reporting (Anlage KAP, KAP-INV, SO) in a testable format.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional
from enum import Enum


# =============================================================================
# Enums for Tax Reporting
# =============================================================================

class TaxPot(Enum):
    """Tax pots for German capital gains taxation."""
    AKTIEN = "AKTIEN"           # Stocks (Anlage KAP Zeilen 20, 23)
    TERMINGESCHAEFTE = "TERM"   # Derivatives (Anlage KAP Zeilen 21, 24)
    SONSTIGE = "SONST"          # Other capital income (Anlage KAP Zeilen 19, 22)
    FONDS = "FUND"              # Investment funds (Anlage KAP-INV)
    PARAGRAPH_23 = "P23"        # Private sales (Anlage SO Zeile 54)


# =============================================================================
# Loss Offsetting Structures
# =============================================================================

@dataclass(frozen=True)
class GrossPotComponents:
    """
    Input: Gross aggregates for each category before any offsetting.
    Losses are positive Decimals representing absolute loss amounts.

    Keys align with PRD terminology:
    - akt_g/v: Aktien (stocks)
    - term_g/v: Termingeschäfte (derivatives)
    - sonst_g/v: Sonstige (other capital income, non-fund)
    - p23_g/v: §23 EStG private sales
    """
    akt_g: Decimal = Decimal("0")    # Gross gains from stocks
    akt_v: Decimal = Decimal("0")    # Gross losses from stocks (absolute)
    term_g: Decimal = Decimal("0")   # Gross gains from derivatives
    term_v: Decimal = Decimal("0")   # Gross losses from derivatives (absolute)
    sonst_g: Decimal = Decimal("0")  # Gross positive other capital income
    sonst_v: Decimal = Decimal("0")  # Gross other capital losses (absolute)
    p23_g: Decimal = Decimal("0")    # Gross §23 EStG gains
    p23_v: Decimal = Decimal("0")    # Gross §23 EStG losses (absolute)


@dataclass(frozen=True)
class ExpectedReportingFigures:
    """
    Expected output: Form line values and conceptual summaries.

    Form values map directly to Anlage KAP/SO line numbers.
    Conceptual values are for user information/internal logging.
    """
    # Anlage KAP form lines
    form_kap_z19_auslaendische_net: Decimal      # Foreign capital income after netting
    form_kap_z20_aktien_g: Decimal               # Gross stock gains
    form_kap_z21_derivate_g: Decimal             # Gross derivative gains
    form_kap_z22_sonstige_v: Decimal             # Gross other losses (absolute)
    form_kap_z23_aktien_v: Decimal               # Gross stock losses (absolute)
    form_kap_z24_derivate_v: Decimal             # Gross derivative losses (absolute, un-capped)

    # Anlage SO form line
    form_so_z54_p23_net_gv: Decimal              # Net §23 EStG G/L

    # Conceptual summaries (for user information)
    conceptual_net_other_income: Decimal         # sonst_g - sonst_v
    conceptual_net_stocks: Decimal               # akt_g - akt_v
    conceptual_net_derivatives_uncapped: Decimal # term_g - term_v (no cap)
    conceptual_net_derivatives_capped: Decimal   # term_g - term_v (€20k cap on net loss)
    conceptual_net_p23_estg: Decimal             # p23_g - p23_v
    conceptual_fund_income_net_taxable: Decimal  # Separate pot for fund income


@dataclass
class LossOffsettingTestCase:
    """
    A single test case for loss offsetting logic.

    The spec and test data are unified - this IS the test definition.
    """
    id: str
    description: str
    inputs: GrossPotComponents
    expected: ExpectedReportingFigures

    # Optional: Simulated fund income (not part of GrossPotComponents)
    fund_income_net_taxable: Decimal = Decimal("0")

    # Documentation
    notes: Optional[str] = None
    prd_references: List[str] = field(default_factory=list)


# =============================================================================
# Helpers
# =============================================================================

# Note: FIFO test structures (TradeSpec, PositionSpec, ExpectedRGLSpec, FifoTestSpec)
# are defined in __init__.py and are the canonical versions used by the test runner.
# The Loss Offsetting structures above are specific to Group 6 tests.

def D(value: str) -> Decimal:
    """Shorthand for Decimal creation from string."""
    return Decimal(value)

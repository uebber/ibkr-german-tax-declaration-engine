"""
Test Group 6: Tax Reporting Aggregation & Loss Offsetting Logic

Revision: 2025-05-18
PRD Coverage: §2.7 (Gross Reporting for Forms), §2.8 (Conceptual Net Summaries)

Objective:
1. Correct aggregation of gross gains/losses for Anlage KAP/SO
2. Correct calculation of conceptual net balances per tax pot
3. Fund income isolation from KAP Zeile 19

Key Principles:
- Form Line Reporting: Gross amounts, derivative losses un-capped
- Conceptual Summaries: Net balances, €20k derivative cap configurable
- Fund income: Separate pot, NOT in Z19 or "Other Capital Income"

This module defines test scenarios for tax reporting aggregation and loss offsetting logic.
Uses Python dataclasses as an executable specification format.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from .schema import GrossPotComponents, ExpectedReportingFigures, LossOffsettingTestCase, D


# =============================================================================
# Test Cases - All 28 scenarios from test_spec_fifo.md
# =============================================================================

LOSS_OFFSETTING_TESTS: List[LossOffsettingTestCase] = [

    # -------------------------------------------------------------------------
    # Baseline: All zeros
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_ALL_001",
        description="All pots zero",
        inputs=GrossPotComponents(),  # All defaults to 0
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # Stock-only scenarios (Aktien)
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_AKT_001",
        description="Stocks - gains only",
        inputs=GrossPotComponents(akt_g=D("1000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("1000.00"),
            form_kap_z20_aktien_g=D("1000.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("1000.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_AKT_002",
        description="Stocks - losses only",
        inputs=GrossPotComponents(akt_v=D("1000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("-1000.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("1000.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("-1000.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_AKT_003",
        description="Stocks - gains > losses",
        inputs=GrossPotComponents(akt_g=D("1000"), akt_v=D("200")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("800.00"),
            form_kap_z20_aktien_g=D("1000.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("200.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("800.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_AKT_004",
        description="Stocks - losses > gains",
        inputs=GrossPotComponents(akt_g=D("200"), akt_v=D("1000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("-800.00"),
            form_kap_z20_aktien_g=D("200.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("1000.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("-800.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_AKT_005",
        description="Stocks - gains = losses",
        inputs=GrossPotComponents(akt_g=D("1000"), akt_v=D("1000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("1000.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("1000.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # Derivative scenarios (Termingeschäfte) - €20k cap testing
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_TERM_001",
        description="Derivatives - gains only",
        inputs=GrossPotComponents(term_g=D("5000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("5000.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("5000.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("5000.00"),
            conceptual_net_derivatives_capped=D("5000.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_002",
        description="Derivatives - losses only (< 20k threshold)",
        notes="Net loss below €20k cap - capped and uncapped should be equal",
        inputs=GrossPotComponents(term_v=D("15000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),  # Derivative losses not subtracted from Z19
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("15000.00"),  # Always un-capped for form
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("-15000.00"),
            conceptual_net_derivatives_capped=D("-15000.00"),  # Below cap, same as uncapped
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_003",
        description="Derivatives - losses = 20k (at threshold)",
        notes="Net loss exactly at €20k cap boundary",
        inputs=GrossPotComponents(term_v=D("20000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("20000.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("-20000.00"),
            conceptual_net_derivatives_capped=D("-20000.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_004",
        description="Derivatives - losses > 20k (exceeds threshold)",
        notes="Net loss exceeds €20k cap - capped value should be limited to -20000",
        prd_references=["2.8"],
        inputs=GrossPotComponents(term_v=D("30000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("30000.00"),  # Form always shows full amount
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("-30000.00"),
            conceptual_net_derivatives_capped=D("-20000.00"),  # Capped!
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_005",
        description="Derivatives - gains > losses",
        inputs=GrossPotComponents(term_g=D("25000"), term_v=D("5000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("25000.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("25000.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("5000.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("20000.00"),
            conceptual_net_derivatives_capped=D("20000.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_006",
        description="Derivatives - losses > gains (net loss < 20k)",
        inputs=GrossPotComponents(term_g=D("5000"), term_v=D("15000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("5000.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("5000.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("15000.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("-10000.00"),
            conceptual_net_derivatives_capped=D("-10000.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_007",
        description="Derivatives - losses > gains (net loss > 20k)",
        notes="Gains partially offset losses, but net loss still exceeds cap",
        inputs=GrossPotComponents(term_g=D("5000"), term_v=D("30000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("5000.00"),  # Only gains in Z19
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("5000.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("30000.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("-25000.00"),  # 5000 - 30000
            conceptual_net_derivatives_capped=D("-20000.00"),    # Capped
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_008",
        description="Derivatives - gains > losses (loss batch > 20k)",
        inputs=GrossPotComponents(term_g=D("40000"), term_v=D("25000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("40000.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("40000.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("25000.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("15000.00"),
            conceptual_net_derivatives_capped=D("15000.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_TERM_009",
        description="Derivatives - gains = losses",
        inputs=GrossPotComponents(term_g=D("10000"), term_v=D("10000")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("10000.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("10000.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("10000.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # Other Capital Income scenarios (Sonstige)
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_SONST_001",
        description="Other - gains only",
        inputs=GrossPotComponents(sonst_g=D("700")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("700.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("700.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_SONST_002",
        description="Other - losses only",
        inputs=GrossPotComponents(sonst_v=D("700")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("-700.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("700.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("-700.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_SONST_003",
        description="Other - gains > losses",
        inputs=GrossPotComponents(sonst_g=D("700"), sonst_v=D("100")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("600.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("100.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("600.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_SONST_004",
        description="Other - losses > gains",
        inputs=GrossPotComponents(sonst_g=D("100"), sonst_v=D("700")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("-600.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("700.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("-600.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # §23 EStG scenarios (Private Sales)
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_P23_001",
        description="§23 - gains only",
        inputs=GrossPotComponents(p23_g=D("1200")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("1200.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("1200.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_P23_002",
        description="§23 - losses only",
        inputs=GrossPotComponents(p23_v=D("1200")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("-1200.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("-1200.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_P23_003",
        description="§23 - gains > losses",
        inputs=GrossPotComponents(p23_g=D("1200"), p23_v=D("300")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("900.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("900.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_P23_004",
        description="§23 - losses > gains",
        inputs=GrossPotComponents(p23_g=D("300"), p23_v=D("1200")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("-900.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("-900.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # Mixed scenarios
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_MIX_001",
        description="All pots active, Term net loss < 20k",
        inputs=GrossPotComponents(
            akt_g=D("2000"), akt_v=D("500"),
            term_g=D("3000"), term_v=D("4000"),
            sonst_g=D("1000"), sonst_v=D("1500"),
            p23_g=D("800"), p23_v=D("200"),
        ),
        expected=ExpectedReportingFigures(
            # Z19 = akt_g + term_g + sonst_g - akt_v - sonst_v = 2000 + 3000 + 1000 - 500 - 1500 = 4000
            form_kap_z19_auslaendische_net=D("4000.00"),
            form_kap_z20_aktien_g=D("2000.00"),
            form_kap_z21_derivate_g=D("3000.00"),
            form_kap_z22_sonstige_v=D("1500.00"),
            form_kap_z23_aktien_v=D("500.00"),
            form_kap_z24_derivate_v=D("4000.00"),
            form_so_z54_p23_net_gv=D("600.00"),  # 800 - 200
            conceptual_net_other_income=D("-500.00"),  # 1000 - 1500
            conceptual_net_stocks=D("1500.00"),  # 2000 - 500
            conceptual_net_derivatives_uncapped=D("-1000.00"),  # 3000 - 4000
            conceptual_net_derivatives_capped=D("-1000.00"),  # Below 20k cap
            conceptual_net_p23_estg=D("600.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_MIX_002",
        description="All pots active, Term net loss > 20k",
        inputs=GrossPotComponents(
            akt_g=D("500"), akt_v=D("2000"),
            term_g=D("1000"), term_v=D("30000"),
            sonst_g=D("1500"), sonst_v=D("500"),
            p23_g=D("200"), p23_v=D("800"),
        ),
        expected=ExpectedReportingFigures(
            # Z19 = 500 + 1000 + 1500 - 2000 - 500 = 500
            form_kap_z19_auslaendische_net=D("500.00"),
            form_kap_z20_aktien_g=D("500.00"),
            form_kap_z21_derivate_g=D("1000.00"),
            form_kap_z22_sonstige_v=D("500.00"),
            form_kap_z23_aktien_v=D("2000.00"),
            form_kap_z24_derivate_v=D("30000.00"),
            form_so_z54_p23_net_gv=D("-600.00"),
            conceptual_net_other_income=D("1000.00"),  # 1500 - 500
            conceptual_net_stocks=D("-1500.00"),  # 500 - 2000
            conceptual_net_derivatives_uncapped=D("-29000.00"),  # 1000 - 30000
            conceptual_net_derivatives_capped=D("-20000.00"),  # Capped!
            conceptual_net_p23_estg=D("-600.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_MIX_003",
        description="All pots generate gains",
        inputs=GrossPotComponents(
            akt_g=D("1000"),
            term_g=D("2000"),
            sonst_g=D("500"),
            p23_g=D("300"),
        ),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("3500.00"),
            form_kap_z20_aktien_g=D("1000.00"),
            form_kap_z21_derivate_g=D("2000.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("300.00"),
            conceptual_net_other_income=D("500.00"),
            conceptual_net_stocks=D("1000.00"),
            conceptual_net_derivatives_uncapped=D("2000.00"),
            conceptual_net_derivatives_capped=D("2000.00"),
            conceptual_net_p23_estg=D("300.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_MIX_004",
        description="All pots report losses",
        inputs=GrossPotComponents(
            akt_v=D("1000"),
            term_v=D("25000"),
            sonst_v=D("500"),
            p23_v=D("300"),
        ),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("-1500.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("500.00"),
            form_kap_z23_aktien_v=D("1000.00"),
            form_kap_z24_derivate_v=D("25000.00"),
            form_so_z54_p23_net_gv=D("-300.00"),
            conceptual_net_other_income=D("-500.00"),
            conceptual_net_stocks=D("-1000.00"),
            conceptual_net_derivatives_uncapped=D("-25000.00"),
            conceptual_net_derivatives_capped=D("-20000.00"),
            conceptual_net_p23_estg=D("-300.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # Sonstige filtering tests (historical vs current year)
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_SFILT_G_001",
        description="sonst_g: Historical positive events only - current year should be 0",
        notes="Historical positive events only (e.g., Div 100 TY-1, Int 50 TY-1). Current year sonst_g should be 0.",
        inputs=GrossPotComponents(sonst_g=D("0")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_SFILT_G_002",
        description="sonst_g: Mix of historical and current tax year - current year 275",
        notes="Mix of historical (Div 100 TY-1) and current tax year (Div 200 TY, Int 75 TY). Current year sonst_g should be 275.00.",
        inputs=GrossPotComponents(sonst_g=D("275.00")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("275.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("275.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_SFILT_V_001",
        description="sonst_v: Historical negative events only - current year should be 0",
        notes="Historical negative events only (e.g., Bond Loss 100 TY-1). Current year sonst_v should be 0.",
        inputs=GrossPotComponents(sonst_v=D("0")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_SFILT_V_002",
        description="sonst_v: Mix of historical and current tax year - current year 150",
        notes="Mix of historical (Bond Loss 100 TY-1) and current tax year (Bond Loss 150 TY). Current year sonst_v should be 150.00.",
        inputs=GrossPotComponents(sonst_v=D("150.00")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("-150.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("150.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("-150.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_SFILT_GV_001",
        description="sonst_g/v: Mixed historical and current tax year events",
        notes="Mixed historical (Div 50 TY-1, Loss 20 TY-1) and current tax year (Div 100 TY, Loss 30 TY) events. Current year sonst_g=100.00, sonst_v=30.00.",
        inputs=GrossPotComponents(sonst_g=D("100.00"), sonst_v=D("30.00")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("70.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("30.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("70.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("0.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # Fund income isolation tests
    # -------------------------------------------------------------------------

    LossOffsettingTestCase(
        id="LO_FUND_001",
        description="Fund Income Present (Net +200) - Test Z.19 exclusion",
        notes="Fund income should NOT appear in form_kap_z19 or conceptual_net_other_income",
        prd_references=["2.7", "2.8"],
        fund_income_net_taxable=D("200.00"),
        inputs=GrossPotComponents(akt_g=D("100"), sonst_g=D("50")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("150.00"),  # Only 100 + 50, NOT +200
            form_kap_z20_aktien_g=D("100.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("50.00"),  # Only sonst, NOT fund
            conceptual_net_stocks=D("100.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("200.00"),  # Separate pot
        ),
    ),

    LossOffsettingTestCase(
        id="LO_FUND_002",
        description="Fund Loss Present (Net -60) - Test Z.19 exclusion",
        notes="Fund losses should NOT reduce form_kap_z19",
        prd_references=["2.7", "2.8"],
        fund_income_net_taxable=D("-60.00"),
        inputs=GrossPotComponents(akt_g=D("100"), sonst_g=D("50")),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("150.00"),  # Still 100 + 50
            form_kap_z20_aktien_g=D("100.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("50.00"),
            conceptual_net_stocks=D("100.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("-60.00"),
        ),
    ),

    # -------------------------------------------------------------------------
    # Fund Type Teilfreistellung Rate Tests
    # -------------------------------------------------------------------------
    # These tests verify correct Teilfreistellung (partial exemption) rates:
    # - Aktienfonds: 30% (already tested in LO_FUND_001/002)
    # - Mischfonds: 15%
    # - Immobilienfonds: 60%
    # - Auslands-Immobilienfonds: 80%
    # - Sonstige Fonds: 0%

    LossOffsettingTestCase(
        id="LO_FUND_MISCH_001",
        description="Mischfonds with 15% Teilfreistellung",
        notes="Net 170 with 15% TF means Gross = 170 / 0.85 = 200. Taxable = 170.",
        prd_references=["2.7"],
        fund_income_net_taxable=D("170.00"),
        fund_type="MISCHFONDS",
        inputs=GrossPotComponents(),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("170.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_FUND_IMMO_001",
        description="Immobilienfonds with 60% Teilfreistellung",
        notes="Net 400 with 60% TF means Gross = 400 / 0.40 = 1000. Taxable = 400.",
        prd_references=["2.7"],
        fund_income_net_taxable=D("400.00"),
        fund_type="IMMOBILIENFONDS",
        inputs=GrossPotComponents(),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("400.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_FUND_AUSLAND_001",
        description="Auslands-Immobilienfonds with 80% Teilfreistellung",
        notes="Net 200 with 80% TF means Gross = 200 / 0.20 = 1000. Taxable = 200.",
        prd_references=["2.7"],
        fund_income_net_taxable=D("200.00"),
        fund_type="AUSLANDS_IMMOBILIENFONDS",
        inputs=GrossPotComponents(),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("200.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_FUND_SONST_001",
        description="Sonstige Fonds with 0% Teilfreistellung",
        notes="Net = Gross for 0% TF. Taxable = 500.",
        prd_references=["2.7"],
        fund_income_net_taxable=D("500.00"),
        fund_type="SONSTIGE_FONDS",
        inputs=GrossPotComponents(),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("500.00"),
        ),
    ),

    LossOffsettingTestCase(
        id="LO_FUND_MISCH_002",
        description="Mischfonds loss with 15% TF",
        notes="Net loss -85 with 15% TF means Gross = -85 / 0.85 = -100. Taxable loss = -85.",
        prd_references=["2.7"],
        fund_income_net_taxable=D("-85.00"),
        fund_type="MISCHFONDS",
        inputs=GrossPotComponents(),
        expected=ExpectedReportingFigures(
            form_kap_z19_auslaendische_net=D("0.00"),
            form_kap_z20_aktien_g=D("0.00"),
            form_kap_z21_derivate_g=D("0.00"),
            form_kap_z22_sonstige_v=D("0.00"),
            form_kap_z23_aktien_v=D("0.00"),
            form_kap_z24_derivate_v=D("0.00"),
            form_so_z54_p23_net_gv=D("0.00"),
            conceptual_net_other_income=D("0.00"),
            conceptual_net_stocks=D("0.00"),
            conceptual_net_derivatives_uncapped=D("0.00"),
            conceptual_net_derivatives_capped=D("0.00"),
            conceptual_net_p23_estg=D("0.00"),
            conceptual_fund_income_net_taxable=D("-85.00"),
        ),
    ),
]


# =============================================================================
# Test IDs for pytest parametrization
# =============================================================================

def get_loss_offsetting_test_ids() -> List[str]:
    """Return list of test IDs for pytest parametrization."""
    return [tc.id for tc in LOSS_OFFSETTING_TESTS]


def get_loss_offsetting_test_by_id(test_id: str) -> Optional[LossOffsettingTestCase]:
    """Lookup a test case by ID."""
    for tc in LOSS_OFFSETTING_TESTS:
        if tc.id == test_id:
            return tc
    return None

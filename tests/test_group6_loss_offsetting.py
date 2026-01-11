"""
Test Group 6: Tax Reporting Aggregation & Loss Offsetting Logic

This module executes tests from the group6_loss_offsetting spec against
the LossOffsettingEngine implementation.

Test Flow:
1. Load test cases from specs/group6_loss_offsetting.py
2. For each test case:
   a. Convert inputs to mock RGLs
   b. Run LossOffsettingEngine
   c. Compare results to expected values

PRD Coverage: §2.7 (Gross Reporting), §2.8 (Conceptual Net Summaries)
"""

import pytest
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional

# Application imports
from src.engine.loss_offsetting import LossOffsettingEngine, LossOffsettingResult
from src.domain.results import RealizedGainLoss
from src.domain.enums import AssetCategory, TaxReportingCategory, InvestmentFundType, RealizationType
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import Asset, InvestmentFund
from src.domain.events import FinancialEvent
import src.config as global_config

# Spec imports
from tests.specs.group6_loss_offsetting import (
    LOSS_OFFSETTING_TESTS,
    LossOffsettingTestCase,
)


# =============================================================================
# Test Infrastructure
# =============================================================================

class MockAssetResolver(AssetResolver):
    """
    A mock AssetResolver for testing that doesn't require file I/O.
    """
    def __init__(self):
        class DummyClassifier(AssetClassifier):
            def __init__(self):
                super().__init__(cache_file_path="dummy_cache.json")
            def preliminary_classify(self, *args, **kwargs) -> tuple[AssetCategory, InvestmentFundType | None]:
                return AssetCategory.UNKNOWN, None
            def save_classifications(self):
                pass

        super().__init__(asset_classifier=DummyClassifier())
        self.mock_assets_store: Dict[uuid.UUID, Asset] = {}

    def add_mock_asset(self, asset: Asset):
        self.mock_assets_store[asset.internal_asset_id] = asset

    def get_asset_by_id(self, internal_asset_id: uuid.UUID) -> Optional[Asset]:
        if internal_asset_id in self.mock_assets_store:
            return self.mock_assets_store[internal_asset_id]

        # Create a generic mock asset on-the-fly
        mock_asset = Asset(asset_category=AssetCategory.UNKNOWN, description="Generic Mock Asset")
        mock_asset.internal_asset_id = internal_asset_id
        self.mock_assets_store[internal_asset_id] = mock_asset
        return mock_asset


def create_mock_rgl(
    gross_amount: Decimal,
    asset_category: AssetCategory,
    is_taxable_p23: bool = False,
    fund_type: InvestmentFundType = InvestmentFundType.AKTIENFONDS,
    asset_id: Optional[uuid.UUID] = None,
    realization_date: str = f"{global_config.TAX_YEAR}-12-31",
) -> RealizedGainLoss:
    """
    Create a mock RealizedGainLoss for testing.

    Args:
        gross_amount: Positive for gain, negative for loss
        asset_category: The asset category
        is_taxable_p23: Whether this is a taxable §23 EStG sale
        fund_type: For fund assets, the fund type
        asset_id: Optional specific asset ID
        realization_date: Date of realization
    """
    internal_asset_id = asset_id or uuid.uuid4()

    # Derive cost basis and realization value from gross amount
    cost_basis = Decimal("0")
    realization_value = Decimal("0")
    if gross_amount >= Decimal("0"):
        realization_value = gross_amount
    else:
        cost_basis = -gross_amount

    rgl = RealizedGainLoss(
        originating_event_id=uuid.uuid4(),
        asset_internal_id=internal_asset_id,
        asset_category_at_realization=asset_category,
        acquisition_date=f"{global_config.TAX_YEAR}-01-01",
        realization_date=realization_date,
        realization_type=RealizationType.LONG_POSITION_SALE,
        quantity_realized=Decimal("1"),
        unit_cost_basis_eur=cost_basis,
        unit_realization_value_eur=realization_value,
        total_cost_basis_eur=cost_basis,
        total_realization_value_eur=realization_value,
        gross_gain_loss_eur=gross_amount,
    )

    if asset_category == AssetCategory.INVESTMENT_FUND:
        rgl.fund_type_at_sale = fund_type
        rgl.__post_init__()

    if asset_category == AssetCategory.PRIVATE_SALE_ASSET:
        rgl.is_taxable_under_section_23 = is_taxable_p23
        rgl.__post_init__()

    return rgl


def build_rgls_from_test_case(
    test_case: LossOffsettingTestCase,
    asset_resolver: MockAssetResolver,
) -> List[RealizedGainLoss]:
    """
    Build mock RGLs from a test case's input specification.
    """
    mock_rgls: List[RealizedGainLoss] = []
    inputs = test_case.inputs
    D = Decimal

    # Fund income handling (special case)
    if test_case.fund_income_net_taxable != D("0"):
        fund_asset_id = uuid.uuid4()
        tf_rate = D("0.30")  # Aktienfonds TF rate

        # Calculate gross from net: Net = Gross * (1 - TF_Rate)
        denominator = D("1") - tf_rate
        if denominator != D("0"):
            gross_fund_gl = test_case.fund_income_net_taxable / denominator
        else:
            gross_fund_gl = test_case.fund_income_net_taxable

        gross_fund_gl = gross_fund_gl.quantize(D("0.000001"), rounding=ROUND_HALF_UP)

        # Create the fund asset
        mock_fund_asset = InvestmentFund(
            internal_asset_id=fund_asset_id,
            description="Mock Aktienfonds for Test",
            currency="EUR",
            fund_type=InvestmentFundType.AKTIENFONDS,
        )
        asset_resolver.add_mock_asset(mock_fund_asset)

        fund_rgl = create_mock_rgl(
            gross_amount=gross_fund_gl,
            asset_category=AssetCategory.INVESTMENT_FUND,
            fund_type=InvestmentFundType.AKTIENFONDS,
            asset_id=fund_asset_id,
        )
        mock_rgls.append(fund_rgl)

    # Stock gains/losses
    if inputs.akt_g > D("0"):
        mock_rgls.append(create_mock_rgl(inputs.akt_g, AssetCategory.STOCK))
    if inputs.akt_v > D("0"):
        mock_rgls.append(create_mock_rgl(-inputs.akt_v, AssetCategory.STOCK))

    # Derivative gains/losses
    if inputs.term_g > D("0"):
        mock_rgls.append(create_mock_rgl(inputs.term_g, AssetCategory.OPTION))
    if inputs.term_v > D("0"):
        mock_rgls.append(create_mock_rgl(-inputs.term_v, AssetCategory.OPTION))

    # Other capital income gains/losses (using BOND category)
    if inputs.sonst_g > D("0"):
        mock_rgls.append(create_mock_rgl(inputs.sonst_g, AssetCategory.BOND))
    if inputs.sonst_v > D("0"):
        mock_rgls.append(create_mock_rgl(-inputs.sonst_v, AssetCategory.BOND))

    # §23 EStG gains/losses
    if inputs.p23_g > D("0"):
        mock_rgls.append(create_mock_rgl(inputs.p23_g, AssetCategory.PRIVATE_SALE_ASSET, is_taxable_p23=True))
    if inputs.p23_v > D("0"):
        mock_rgls.append(create_mock_rgl(-inputs.p23_v, AssetCategory.PRIVATE_SALE_ASSET, is_taxable_p23=True))

    return mock_rgls


# =============================================================================
# Form line mapping
# =============================================================================

FORM_LINE_TO_ENGINE_KEY = {
    "form_kap_z19_auslaendische_net": TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT,
    "form_kap_z20_aktien_g": TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN,
    "form_kap_z21_derivate_g": TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN,
    "form_kap_z22_sonstige_v": TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE,
    "form_kap_z23_aktien_v": TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST,
    "form_kap_z24_derivate_v": TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST,
    "form_so_z54_p23_net_gv": "ANLAGE_SO_Z54_NET_GV",  # String key
}

CONCEPTUAL_TO_ENGINE_FIELD = {
    "conceptual_net_other_income": "conceptual_net_other_income",
    "conceptual_net_stocks": "conceptual_net_stocks",
    "conceptual_net_derivatives_uncapped": "conceptual_net_derivatives_uncapped",
    "conceptual_net_derivatives_capped": "conceptual_net_derivatives_capped",
    "conceptual_net_p23_estg": "conceptual_net_p23_estg",
    "conceptual_fund_income_net_taxable": "conceptual_fund_income_net_taxable",
}


# =============================================================================
# Test Class
# =============================================================================

class TestLossOffsettingFromSpec:
    """
    Test loss offsetting logic using test cases from the spec.

    Each test case is loaded from specs/group6_loss_offsetting.py.
    The spec IS the test definition - no separate test data file needed.
    """

    @pytest.mark.parametrize(
        "test_case",
        LOSS_OFFSETTING_TESTS,
        ids=[tc.id for tc in LOSS_OFFSETTING_TESTS],
    )
    def test_loss_offsetting_scenario(self, test_case: LossOffsettingTestCase):
        """Execute a single loss offsetting test case."""

        # Setup
        asset_resolver = MockAssetResolver()
        mock_rgls = build_rgls_from_test_case(test_case, asset_resolver)
        mock_current_year_events: List[FinancialEvent] = []

        # Execute
        engine = LossOffsettingEngine(
            realized_gains_losses=mock_rgls,
            vorabpauschale_items=[],
            current_year_financial_events=mock_current_year_events,
            asset_resolver=asset_resolver,
            tax_year=global_config.TAX_YEAR,
            apply_conceptual_derivative_loss_capping=global_config.APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING,
        )
        result: LossOffsettingResult = engine.calculate_reporting_figures()

        # Verify form line values
        expected = test_case.expected
        for form_key, engine_key in FORM_LINE_TO_ENGINE_KEY.items():
            expected_value = getattr(expected, form_key)
            actual_value = result.form_line_values.get(engine_key, Decimal("0.00"))

            assert actual_value.compare(expected_value) == Decimal("0"), (
                f"{test_case.id}: Form line {form_key} mismatch. "
                f"Expected {expected_value}, got {actual_value}. "
                f"Inputs: {test_case.inputs}"
            )

        # Verify conceptual summaries
        for concept_key, engine_field in CONCEPTUAL_TO_ENGINE_FIELD.items():
            expected_value = getattr(expected, concept_key)
            actual_value = getattr(result, engine_field, Decimal("0.00"))

            assert actual_value.compare(expected_value) == Decimal("0"), (
                f"{test_case.id}: Conceptual {concept_key} mismatch. "
                f"Expected {expected_value}, got {actual_value}. "
                f"Inputs: {test_case.inputs}"
            )

        # Additional verification for fund tests
        if test_case.id in ["LO_FUND_001", "LO_FUND_002"]:
            # Verify fund income is NOT included in Z19
            non_fund_akt_g = test_case.inputs.akt_g
            non_fund_sonst_g = test_case.inputs.sonst_g

            expected_z19_without_fund = (non_fund_akt_g + non_fund_sonst_g).quantize(
                global_config.OUTPUT_PRECISION_AMOUNTS
            )
            actual_z19 = result.form_line_values.get(
                TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT,
                Decimal("0.00"),
            )

            assert actual_z19.compare(expected_z19_without_fund) == Decimal("0"), (
                f"{test_case.id}: Z19 should exclude fund income. "
                f"Expected {expected_z19_without_fund}, got {actual_z19}."
            )


# =============================================================================
# Additional Test Categories
# =============================================================================

class TestLossOffsettingDerivativeCap:
    """
    Focused tests on the €20k derivative loss cap behavior.

    These tests verify the specific boundary conditions around the cap.
    """

    def test_derivative_cap_exactly_at_boundary(self):
        """Test that exactly €20k net loss is not further capped."""
        test_case = next(tc for tc in LOSS_OFFSETTING_TESTS if tc.id == "LO_TERM_003")

        asset_resolver = MockAssetResolver()
        mock_rgls = build_rgls_from_test_case(test_case, asset_resolver)

        engine = LossOffsettingEngine(
            realized_gains_losses=mock_rgls,
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=asset_resolver,
            tax_year=global_config.TAX_YEAR,
            apply_conceptual_derivative_loss_capping=True,
        )
        result = engine.calculate_reporting_figures()

        # Both capped and uncapped should be -20000 at the boundary
        assert result.conceptual_net_derivatives_uncapped == Decimal("-20000.00")
        assert result.conceptual_net_derivatives_capped == Decimal("-20000.00")

    def test_derivative_cap_exceeded(self):
        """Test that losses exceeding €20k are capped in conceptual summary."""
        test_case = next(tc for tc in LOSS_OFFSETTING_TESTS if tc.id == "LO_TERM_004")

        asset_resolver = MockAssetResolver()
        mock_rgls = build_rgls_from_test_case(test_case, asset_resolver)

        engine = LossOffsettingEngine(
            realized_gains_losses=mock_rgls,
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=asset_resolver,
            tax_year=global_config.TAX_YEAR,
            apply_conceptual_derivative_loss_capping=True,
        )
        result = engine.calculate_reporting_figures()

        # Uncapped should show full loss
        assert result.conceptual_net_derivatives_uncapped == Decimal("-30000.00")
        # Capped should be limited to -20000
        assert result.conceptual_net_derivatives_capped == Decimal("-20000.00")
        # Form value should still show full loss (uncapped for forms)
        assert result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST] == Decimal("30000.00")


class TestLossOffsettingFundIsolation:
    """
    Tests verifying that fund income is properly isolated from Z19 and other pots.
    """

    def test_positive_fund_income_excluded_from_z19(self):
        """Verify positive fund income doesn't inflate Z19."""
        test_case = next(tc for tc in LOSS_OFFSETTING_TESTS if tc.id == "LO_FUND_001")

        asset_resolver = MockAssetResolver()
        mock_rgls = build_rgls_from_test_case(test_case, asset_resolver)

        engine = LossOffsettingEngine(
            realized_gains_losses=mock_rgls,
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=asset_resolver,
            tax_year=global_config.TAX_YEAR,
            apply_conceptual_derivative_loss_capping=True,
        )
        result = engine.calculate_reporting_figures()

        # Z19 should only include akt_g + sonst_g = 100 + 50 = 150
        z19 = result.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT,
            Decimal("0.00"),
        )
        assert z19 == Decimal("150.00")

        # Fund income should be in its own pot
        assert result.conceptual_fund_income_net_taxable == Decimal("200.00")

    def test_negative_fund_income_excluded_from_z19(self):
        """Verify negative fund income doesn't reduce Z19."""
        test_case = next(tc for tc in LOSS_OFFSETTING_TESTS if tc.id == "LO_FUND_002")

        asset_resolver = MockAssetResolver()
        mock_rgls = build_rgls_from_test_case(test_case, asset_resolver)

        engine = LossOffsettingEngine(
            realized_gains_losses=mock_rgls,
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=asset_resolver,
            tax_year=global_config.TAX_YEAR,
            apply_conceptual_derivative_loss_capping=True,
        )
        result = engine.calculate_reporting_figures()

        # Z19 should still be 100 + 50 = 150 (fund loss doesn't reduce it)
        z19 = result.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT,
            Decimal("0.00"),
        )
        assert z19 == Decimal("150.00")

        # Fund loss should be in its own pot
        assert result.conceptual_fund_income_net_taxable == Decimal("-60.00")

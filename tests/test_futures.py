"""
Test Group 11: Futures Support

Tests futures-specific functionality:
- Asset classification (FUT -> AssetCategory.FUTURE)
- Future domain class creation
- Loss offsetting routing (Termingeschäfte, Zeile 21/24)
- FIFO mechanics via YAML spec (group11_futures.yaml)

legal_basis: GT-ESTG20-007 — §20 Abs. 2 Satz 1 Nr. 3 EStG. Futures are
Termingeschäfte, taxed identically to options and CFDs; the form line they
land on is year-specific (GT-FORM-010, GT-FORM-011).
reference/tax-law/estg-20-kapitalvermoegen.md.
"""

import pytest
import uuid
from decimal import Decimal
from typing import Optional, Dict, List

from src.domain.assets import Asset, Future, Derivative
from src.domain.enums import AssetCategory, InvestmentFundType, TaxReportingCategory, RealizationType
from src.domain.results import RealizedGainLoss
from src.domain.events import FinancialEvent
from src.classification.asset_classifier import AssetClassifier
from src.identification.asset_resolver import AssetResolver
from src.engine.loss_offsetting import LossOffsettingEngine
import src.config as global_config


# =============================================================================
# Test Infrastructure
# =============================================================================

class MockAssetResolver(AssetResolver):
    """Minimal mock for loss offsetting tests."""
    def __init__(self):
        class DummyClassifier(AssetClassifier):
            def __init__(self):
                super().__init__(cache_file_path="dummy_cache.json")
            def save_classifications(self):
                pass
        super().__init__(asset_classifier=DummyClassifier())
        self.mock_assets_store: Dict[uuid.UUID, Asset] = {}

    def add_mock_asset(self, asset: Asset):
        self.mock_assets_store[asset.internal_asset_id] = asset

    def get_asset_by_id(self, internal_asset_id: uuid.UUID) -> Optional[Asset]:
        if internal_asset_id in self.mock_assets_store:
            return self.mock_assets_store[internal_asset_id]
        mock_asset = Asset(asset_category=AssetCategory.UNKNOWN, description="Generic Mock")
        mock_asset.internal_asset_id = internal_asset_id
        self.mock_assets_store[internal_asset_id] = mock_asset
        return mock_asset


def create_future_rgl(
    gross_amount: Decimal,
    realization_date: str = "2023-06-15",
) -> RealizedGainLoss:
    """Create a mock RGL for a futures trade."""
    cost_basis = Decimal("0")
    realization_value = Decimal("0")
    if gross_amount >= Decimal("0"):
        realization_value = gross_amount
    else:
        cost_basis = -gross_amount

    return RealizedGainLoss(
        originating_event_id=uuid.uuid4(),
        asset_internal_id=uuid.uuid4(),
        asset_category_at_realization=AssetCategory.FUTURE,
        acquisition_date="2023-01-15",
        realization_date=realization_date,
        realization_type=RealizationType.LONG_POSITION_SALE,
        quantity_realized=Decimal("1"),
        unit_cost_basis_eur=cost_basis,
        unit_realization_value_eur=realization_value,
        total_cost_basis_eur=cost_basis,
        total_realization_value_eur=realization_value,
        gross_gain_loss_eur=gross_amount,
    )


# =============================================================================
# Classification Tests
# =============================================================================

class TestFuturesClassification:
    """Verify that FUT asset class is correctly classified."""

    def test_preliminary_classify_fut(self):
        """FUT asset class should map to AssetCategory.FUTURE."""
        classifier = AssetClassifier(cache_file_path="dummy_cache.json")
        cat, fund_type = classifier.preliminary_classify(
            ibkr_asset_class="FUT",
            ibkr_sub_category=None,
            description="E-mini S&P 500 Dec 2023",
            symbol="ESZ3",
        )
        assert cat == AssetCategory.FUTURE
        assert fund_type == InvestmentFundType.NONE

    def test_preliminary_classify_fut_lowercase(self):
        """Classification should be case-insensitive."""
        classifier = AssetClassifier(cache_file_path="dummy_cache.json")
        cat, _ = classifier.preliminary_classify(
            ibkr_asset_class="fut",
            ibkr_sub_category=None,
            description="Euro Stoxx 50 Future",
            symbol="ESTX50",
        )
        assert cat == AssetCategory.FUTURE

    def test_is_not_potentially_special(self):
        """Futures should not require special classification attention."""
        classifier = AssetClassifier(cache_file_path="dummy_cache.json")
        future_asset = Future(
            description="E-mini S&P 500",
            ibkr_symbol="ESZ3",
            ibkr_asset_class_raw="FUT",
            multiplier=Decimal("50"),
        )
        assert not classifier._is_potentially_special(future_asset)

    def test_get_python_type_for_future(self):
        """FUTURE category should map to Future class."""
        classifier = AssetClassifier(cache_file_path="dummy_cache.json")
        assert classifier._get_python_type_for_category(AssetCategory.FUTURE) is Future


# =============================================================================
# Domain Model Tests
# =============================================================================

class TestFutureDomainClass:
    """Verify Future domain class behavior."""

    def test_future_is_derivative(self):
        """Future should be a subclass of Derivative."""
        future = Future(
            description="E-mini S&P 500",
            ibkr_symbol="ESZ3",
            multiplier=Decimal("50"),
        )
        assert isinstance(future, Derivative)
        assert isinstance(future, Asset)

    def test_future_category(self):
        """Future should have AssetCategory.FUTURE."""
        future = Future(description="Test Future")
        assert future.asset_category == AssetCategory.FUTURE

    def test_future_multiplier(self):
        """Future should store multiplier from Derivative base."""
        future = Future(
            description="E-mini S&P 500",
            multiplier=Decimal("50"),
        )
        assert future.multiplier == Decimal("50")

    def test_future_underlying_fields(self):
        """Future should support underlying asset linking."""
        underlying_id = uuid.uuid4()
        future = Future(
            description="E-mini",
            underlying_ibkr_conid="12345",
            underlying_ibkr_symbol="SPX",
            underlying_asset_internal_id=underlying_id,
            multiplier=Decimal("50"),
        )
        assert future.underlying_ibkr_conid == "12345"
        assert future.underlying_ibkr_symbol == "SPX"
        assert future.underlying_asset_internal_id == underlying_id


# =============================================================================
# Asset Resolver Tests
# =============================================================================

class TestFuturesAssetResolver:
    """Verify asset resolver creates and replaces Future objects."""

    def test_get_or_create_future(self):
        """Asset resolver should create a Future instance for FUT class."""
        classifier = AssetClassifier(cache_file_path="dummy_cache.json")
        resolver = AssetResolver(asset_classifier=classifier)

        asset = resolver.get_or_create_asset(
            raw_isin=None,
            raw_conid="987654",
            raw_symbol="ESZ3",
            raw_currency="USD",
            raw_ibkr_asset_class="FUT",
            raw_description="E-mini S&P 500 Dec 2023",
            raw_multiplier="50",
            raw_underlying_symbol="SPX",
        )

        assert isinstance(asset, Future)
        assert asset.asset_category == AssetCategory.FUTURE
        assert asset.multiplier == Decimal("50")
        assert asset.underlying_ibkr_symbol == "SPX"

    def test_replace_asset_to_future(self):
        """Replacing an unknown asset type to FUTURE should work."""
        classifier = AssetClassifier(cache_file_path="dummy_cache.json")
        resolver = AssetResolver(asset_classifier=classifier)

        # Create a generic asset first
        generic = Asset(
            asset_category=AssetCategory.UNKNOWN,
            description="Unknown derivative",
            ibkr_symbol="NQZ3",
            ibkr_conid="111222",
        )
        resolver.assets_by_internal_id[generic.internal_asset_id] = generic
        for alias in generic.aliases:
            resolver.alias_map[alias] = generic

        # Replace to FUTURE
        new_asset = resolver.replace_asset_type(
            internal_asset_id=generic.internal_asset_id,
            new_category=AssetCategory.FUTURE,
            new_fund_type=None,
            new_user_notes="Reclassified as future",
        )

        assert isinstance(new_asset, Future)
        assert new_asset.asset_category == AssetCategory.FUTURE
        assert new_asset.internal_asset_id == generic.internal_asset_id


# =============================================================================
# Loss Offsetting Tests
# =============================================================================

class TestFuturesLossOffsetting:
    """Verify futures gains/losses route to Termingeschäfte lines."""

    def _run_loss_offsetting(
        self, rgls: List[RealizedGainLoss], tax_year: int = 2023
    ) -> "LossOffsettingResult":
        resolver = MockAssetResolver()
        engine = LossOffsettingEngine(
            realized_gains_losses=rgls,
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=resolver,
            tax_year=tax_year,
            apply_conceptual_derivative_loss_capping=True,
        )
        return engine.calculate_reporting_figures()

    def test_future_gain_routes_to_termin_gewinn(self):
        """Future gains should appear in ANLAGE_KAP_TERMIN_GEWINN (Zeile 21)."""
        rgl = create_future_rgl(Decimal("500.00"))
        result = self._run_loss_offsetting([rgl])

        z21 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN, Decimal("0"))
        assert z21 == Decimal("500.00")

    def test_future_loss_routes_to_termin_verlust(self):
        """Future losses should appear in ANLAGE_KAP_TERMIN_VERLUST (Zeile 24)."""
        rgl = create_future_rgl(Decimal("-300.00"))
        result = self._run_loss_offsetting([rgl])

        z24 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST, Decimal("0"))
        assert z24 == Decimal("300.00")

    def test_future_gain_not_in_stock_lines(self):
        """Future gains must NOT appear in stock lines (Zeile 20/23)."""
        rgl = create_future_rgl(Decimal("500.00"))
        result = self._run_loss_offsetting([rgl])

        z20 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN, Decimal("0"))
        z23 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST, Decimal("0"))
        assert z20 == Decimal("0")
        assert z23 == Decimal("0")

    def test_future_included_in_derivative_conceptual_net(self):
        """Future P/L should be included in conceptual derivative net."""
        rgl_gain = create_future_rgl(Decimal("1000.00"))
        rgl_loss = create_future_rgl(Decimal("-400.00"))
        result = self._run_loss_offsetting([rgl_gain, rgl_loss])

        assert result.conceptual_net_derivatives_uncapped == Decimal("600.00")

    def test_futures_mixed_with_options_in_derivative_bucket(self):
        """Futures and options should aggregate in the same Termingeschäfte bucket."""
        from src.domain.results import RealizedGainLoss

        # Future gain
        fut_rgl = create_future_rgl(Decimal("800.00"))

        # Option gain (using OPTION category)
        opt_rgl = RealizedGainLoss(
            originating_event_id=uuid.uuid4(),
            asset_internal_id=uuid.uuid4(),
            asset_category_at_realization=AssetCategory.OPTION,
            acquisition_date="2023-01-01",
            realization_date="2023-06-15",
            realization_type=RealizationType.LONG_POSITION_SALE,
            quantity_realized=Decimal("1"),
            unit_cost_basis_eur=Decimal("0"),
            unit_realization_value_eur=Decimal("200"),
            total_cost_basis_eur=Decimal("0"),
            total_realization_value_eur=Decimal("200"),
            gross_gain_loss_eur=Decimal("200.00"),
        )

        result = self._run_loss_offsetting([fut_rgl, opt_rgl])

        z21 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN, Decimal("0"))
        assert z21 == Decimal("1000.00")  # 800 + 200

    def test_future_no_loss_cap_2024_retroactive_repeal(self):
        """VZ 2024: the €20k cap (§20 Abs. 6 S. 5 a.F.) was abolished
        RETROACTIVELY for all open cases (JStG 2024, §52 Abs. 28 EStG n.F.) —
        a 2024 return prepared today must NOT cap the conceptual net."""
        rgl = create_future_rgl(Decimal("-25000.00"))
        result = self._run_loss_offsetting([rgl], tax_year=2024)

        assert result.conceptual_net_derivatives_capped == Decimal("-25000.00")
        assert result.conceptual_net_derivatives_uncapped == Decimal("-25000.00")

    def test_future_no_loss_cap_2025(self):
        """In 2025, no derivative loss cap — full loss reported."""
        rgl = create_future_rgl(Decimal("-25000.00"))
        result = self._run_loss_offsetting([rgl], tax_year=2025)

        # No cap in 2025
        assert result.conceptual_net_derivatives_capped == Decimal("-25000.00")
        assert result.conceptual_net_derivatives_uncapped == Decimal("-25000.00")

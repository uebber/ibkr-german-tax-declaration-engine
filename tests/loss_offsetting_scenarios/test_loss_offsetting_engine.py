# tests/engine/test_loss_offsetting_engine.py
import pytest
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Any, Tuple

from src.engine.loss_offsetting import LossOffsettingEngine, LossOffsettingResult
from src.domain.results import RealizedGainLoss
from src.domain.enums import AssetCategory, TaxReportingCategory, InvestmentFundType, RealizationType
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier # For MockAssetResolver
from src.domain.assets import Asset, InvestmentFund # For MockAssetResolver type hint and event creation
from src.domain.events import FinancialEvent, CashFlowEvent # For current_year_financial_events
from src.domain.enums import FinancialEventType # For CashFlowEvent
import src.config as global_config # For TAX_YEAR

# Mock AssetResolver that does minimal work, as LossOffsettingEngine doesn't heavily use it
# for RGLs that already have asset_category_at_realization.
# It is used for current_year_financial_events.
class MockAssetResolver(AssetResolver):
    def __init__(self):
        class DummyClassifier(AssetClassifier): # type: ignore
            def __init__(self):
                super().__init__(cache_file_path="dummy_cache.json") # type: ignore
            def preliminary_classify(self, *args, **kwargs) -> tuple[AssetCategory, InvestmentFundType | None]: # type: ignore
                return AssetCategory.UNKNOWN, None
            def save_classifications(self): # Explicitly mock save if it's called and has side effects (like file IO)
                pass

        super().__init__(asset_classifier=DummyClassifier()) # type: ignore
        self.mock_assets_store: Dict[uuid.UUID, Asset] = {}


    def add_mock_asset(self, asset: Asset):
        self.mock_assets_store[asset.internal_asset_id] = asset

    def get_asset_by_id(self, internal_asset_id: uuid.UUID) -> Optional[Asset]:
        if internal_asset_id in self.mock_assets_store:
            return self.mock_assets_store[internal_asset_id]
        
        mock_asset = Asset(asset_category=AssetCategory.UNKNOWN, description="Generic Mock Asset for Event")
        mock_asset.internal_asset_id = internal_asset_id 
        self.mock_assets_store[internal_asset_id] = mock_asset
        return mock_asset


def create_mock_rgl_for_pot_testing(
    gross_amount: Decimal,
    asset_category: AssetCategory,
    is_taxable_p23: bool = False,
    fund_type_for_fund_rgl: InvestmentFundType = InvestmentFundType.AKTIENFONDS, # Default for fund RGLs
    asset_id: Optional[uuid.UUID] = None,
    tax_reporting_category_override: Optional[TaxReportingCategory] = None,
    realization_date: str = f"{global_config.TAX_YEAR}-12-31" # Ensure it's within the tax year
) -> RealizedGainLoss:
    internal_asset_id = asset_id or uuid.uuid4()
    
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
        gross_gain_loss_eur=gross_amount
    )

    if asset_category == AssetCategory.INVESTMENT_FUND:
        rgl.fund_type_at_sale = fund_type_for_fund_rgl
        if tax_reporting_category_override:
            rgl.tax_reporting_category = tax_reporting_category_override
        rgl.__post_init__() 

    if asset_category == AssetCategory.PRIVATE_SALE_ASSET:
        rgl.is_taxable_under_section_23 = is_taxable_p23
        rgl.__post_init__()

    return rgl


D = Decimal 

# Test data based on Test Group 6 in test_spec_fifo.md (Revision 2025-05-18)
# Input dict is `InputGrossPotComponents`
# Expected dict is `ExpectedReportingAndSummaries`
# For LO_FUND_* tests, `simulated_fund_income_net_taxable` is a special field for test setup.
LOSS_OFFSETTING_TEST_CASES: List[Tuple[str, Dict[str, Decimal], Dict[str, Decimal]]] = [
    (
        "LO_ALL_001",
        {'akt_g': D("0"), 'akt_v': D("0"), 'term_g': D("0"), 'term_v': D("0"), 'sonst_g': D("0"), 'sonst_v': D("0"), 'p23_g': D("0"), 'p23_v': D("0")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_AKT_001",
        {'akt_g': D("1000")},
        {'form_kap_z19_auslaendische_net': D("1000.00"), 'form_kap_z20_aktien_g': D("1000.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("1000.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_AKT_002",
        {'akt_v': D("1000")},
        {'form_kap_z19_auslaendische_net': D("-1000.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("1000.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("-1000.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_AKT_003",
        {'akt_g': D("1000"), 'akt_v': D("200")},
        {'form_kap_z19_auslaendische_net': D("800.00"), 'form_kap_z20_aktien_g': D("1000.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("200.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("800.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_AKT_004",
        {'akt_g': D("200"), 'akt_v': D("1000")},
        {'form_kap_z19_auslaendische_net': D("-800.00"), 'form_kap_z20_aktien_g': D("200.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("1000.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("-800.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_AKT_005",
        {'akt_g': D("1000"), 'akt_v': D("1000")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("1000.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("1000.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_001",
        {'term_g': D("5000")},
        {'form_kap_z19_auslaendische_net': D("5000.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("5000.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("5000.00"), 'conceptual_net_derivatives_capped': D("5000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_002",
        {'term_v': D("15000")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("15000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("-15000.00"), 'conceptual_net_derivatives_capped': D("-15000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_003",
        {'term_v': D("20000")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("20000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("-20000.00"), 'conceptual_net_derivatives_capped': D("-20000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_004",
        {'term_v': D("30000")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("30000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("-30000.00"), 'conceptual_net_derivatives_capped': D("-20000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_005",
        {'term_g': D("25000"), 'term_v': D("5000")},
        {'form_kap_z19_auslaendische_net': D("25000.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("25000.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("5000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("20000.00"), 'conceptual_net_derivatives_capped': D("20000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_006",
        {'term_g': D("5000"), 'term_v': D("15000")},
        {'form_kap_z19_auslaendische_net': D("5000.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("5000.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("15000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("-10000.00"), 'conceptual_net_derivatives_capped': D("-10000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_007",
        {'term_g': D("5000"), 'term_v': D("30000")},
        {'form_kap_z19_auslaendische_net': D("5000.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("5000.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("30000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("-25000.00"), 'conceptual_net_derivatives_capped': D("-20000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_008",
        {'term_g': D("40000"), 'term_v': D("25000")},
        {'form_kap_z19_auslaendische_net': D("40000.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("40000.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("25000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("15000.00"), 'conceptual_net_derivatives_capped': D("15000.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_TERM_009",
        {'term_g': D("10000"), 'term_v': D("10000")},
        {'form_kap_z19_auslaendische_net': D("10000.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("10000.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("10000.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SONST_001",
        {'sonst_g': D("700")},
        {'form_kap_z19_auslaendische_net': D("700.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("700.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SONST_002",
        {'sonst_v': D("700")},
        {'form_kap_z19_auslaendische_net': D("-700.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("700.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("-700.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SONST_003",
        {'sonst_g': D("700"), 'sonst_v': D("100")},
        {'form_kap_z19_auslaendische_net': D("600.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("100.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("600.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SONST_004",
        {'sonst_g': D("100"), 'sonst_v': D("700")},
        {'form_kap_z19_auslaendische_net': D("-600.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("700.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("-600.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_P23_001",
        {'p23_g': D("1200")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("1200.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("1200.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_P23_002",
        {'p23_v': D("1200")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("-1200.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("-1200.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_P23_003",
        {'p23_g': D("1200"), 'p23_v': D("300")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("900.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("900.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_P23_004",
        {'p23_g': D("300"), 'p23_v': D("1200")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("-900.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("-900.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_MIX_001",
        {'akt_g': D("2000"), 'akt_v': D("500"), 'term_g': D("3000"), 'term_v': D("4000"), 'sonst_g': D("1000"), 'sonst_v': D("1500"), 'p23_g': D("800"), 'p23_v': D("200")},
        {'form_kap_z19_auslaendische_net': D("4000.00"), 'form_kap_z20_aktien_g': D("2000.00"), 'form_kap_z21_derivate_g': D("3000.00"), 'form_kap_z22_sonstige_v': D("1500.00"), 'form_kap_z23_aktien_v': D("500.00"), 'form_kap_z24_derivate_v': D("4000.00"), 'form_so_z54_p23_net_gv': D("600.00"), 'conceptual_net_other_income': D("-500.00"), 'conceptual_net_stocks': D("1500.00"), 'conceptual_net_derivatives_uncapped': D("-1000.00"), 'conceptual_net_derivatives_capped': D("-1000.00"), 'conceptual_net_p23_estg': D("600.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_MIX_002",
        {'akt_g': D("500"), 'akt_v': D("2000"), 'term_g': D("1000"), 'term_v': D("30000"), 'sonst_g': D("1500"), 'sonst_v': D("500"), 'p23_g': D("200"), 'p23_v': D("800")},
        {'form_kap_z19_auslaendische_net': D("500.00"), 'form_kap_z20_aktien_g': D("500.00"), 'form_kap_z21_derivate_g': D("1000.00"), 'form_kap_z22_sonstige_v': D("500.00"), 'form_kap_z23_aktien_v': D("2000.00"), 'form_kap_z24_derivate_v': D("30000.00"), 'form_so_z54_p23_net_gv': D("-600.00"), 'conceptual_net_other_income': D("1000.00"), 'conceptual_net_stocks': D("-1500.00"), 'conceptual_net_derivatives_uncapped': D("-29000.00"), 'conceptual_net_derivatives_capped': D("-20000.00"), 'conceptual_net_p23_estg': D("-600.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_MIX_003",
        {'akt_g': D("1000"), 'term_g': D("2000"), 'sonst_g': D("500"), 'p23_g': D("300")},
        {'form_kap_z19_auslaendische_net': D("3500.00"), 'form_kap_z20_aktien_g': D("1000.00"), 'form_kap_z21_derivate_g': D("2000.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("300.00"), 'conceptual_net_other_income': D("500.00"), 'conceptual_net_stocks': D("1000.00"), 'conceptual_net_derivatives_uncapped': D("2000.00"), 'conceptual_net_derivatives_capped': D("2000.00"), 'conceptual_net_p23_estg': D("300.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_MIX_004",
        {'akt_v': D("1000"), 'term_v': D("25000"), 'sonst_v': D("500"), 'p23_v': D("300")},
        {'form_kap_z19_auslaendische_net': D("-1500.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("500.00"), 'form_kap_z23_aktien_v': D("1000.00"), 'form_kap_z24_derivate_v': D("25000.00"), 'form_so_z54_p23_net_gv': D("-300.00"), 'conceptual_net_other_income': D("-500.00"), 'conceptual_net_stocks': D("-1000.00"), 'conceptual_net_derivatives_uncapped': D("-25000.00"), 'conceptual_net_derivatives_capped': D("-20000.00"), 'conceptual_net_p23_estg': D("-300.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SFILT_G_001", 
        {'sonst_g': D("0")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SFILT_G_002", 
        {'sonst_g': D("275.00")},
        {'form_kap_z19_auslaendische_net': D("275.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("275.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SFILT_V_001", 
        {'sonst_v': D("0")},
        {'form_kap_z19_auslaendische_net': D("0.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("0.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SFILT_V_002", 
        {'sonst_v': D("150.00")},
        {'form_kap_z19_auslaendische_net': D("-150.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("150.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("-150.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_SFILT_GV_001", 
        {'sonst_g': D("100.00"), 'sonst_v': D("30.00")},
        {'form_kap_z19_auslaendische_net': D("70.00"), 'form_kap_z20_aktien_g': D("0.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("30.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("70.00"), 'conceptual_net_stocks': D("0.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("0.00")}
    ),
    (
        "LO_FUND_001",
        {'akt_g': D("100"), 'sonst_g': D("50"), 'simulated_fund_income_net_taxable': D("200.00")},
        {'form_kap_z19_auslaendische_net': D("150.00"), 'form_kap_z20_aktien_g': D("100.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("50.00"), 'conceptual_net_stocks': D("100.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("200.00")}
    ),
    (
        "LO_FUND_002",
        {'akt_g': D("100"), 'sonst_g': D("50"), 'simulated_fund_income_net_taxable': D("-60.00")},
        {'form_kap_z19_auslaendische_net': D("150.00"), 'form_kap_z20_aktien_g': D("100.00"), 'form_kap_z21_derivate_g': D("0.00"), 'form_kap_z22_sonstige_v': D("0.00"), 'form_kap_z23_aktien_v': D("0.00"), 'form_kap_z24_derivate_v': D("0.00"), 'form_so_z54_p23_net_gv': D("0.00"), 'conceptual_net_other_income': D("50.00"), 'conceptual_net_stocks': D("100.00"), 'conceptual_net_derivatives_uncapped': D("0.00"), 'conceptual_net_derivatives_capped': D("0.00"), 'conceptual_net_p23_estg': D("0.00"), 'conceptual_fund_income_net_taxable': D("-60.00")}
    )
]


EXPECTED_FORM_LINE_TO_ENGINE_KEY_MAP = {
    'form_kap_z19_auslaendische_net': TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT,
    'form_kap_z20_aktien_g': TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN,
    'form_kap_z21_derivate_g': TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN,
    'form_kap_z22_sonstige_v': TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE,
    'form_kap_z23_aktien_v': TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST,
    'form_kap_z24_derivate_v': TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST,
    'form_so_z54_p23_net_gv': "ANLAGE_SO_Z54_NET_GV", # String key as per LossOffsettingResult
}

EXPECTED_CONCEPTUAL_TO_ENGINE_FIELD_MAP = {
    'conceptual_net_other_income': 'conceptual_net_other_income',
    'conceptual_net_stocks': 'conceptual_net_stocks',
    'conceptual_net_derivatives_uncapped': 'conceptual_net_derivatives_uncapped',
    'conceptual_net_derivatives_capped': 'conceptual_net_derivatives_capped',
    'conceptual_net_p23_estg': 'conceptual_net_p23_estg',
    'conceptual_fund_income_net_taxable': 'conceptual_fund_income_net_taxable'
}


class TestLossOffsettingEngineScenarios:

    @pytest.mark.parametrize(
        "test_id, input_gross_pot_components, expected_reporting_and_summaries",
        LOSS_OFFSETTING_TEST_CASES,
        ids=[tc[0] for tc in LOSS_OFFSETTING_TEST_CASES]
    )
    def test_loss_offsetting_scenario(self, test_id: str, input_gross_pot_components: Dict[str, Decimal], expected_reporting_and_summaries: Dict[str, Decimal]):
        mock_rgls: List[RealizedGainLoss] = []
        mock_current_year_events: List[FinancialEvent] = [] 
        asset_resolver = MockAssetResolver()

        simulated_net_fund_income = input_gross_pot_components.get('simulated_fund_income_net_taxable')

        if simulated_net_fund_income is not None:
            fund_asset_id = uuid.uuid4()
            tf_rate = D("0.30") # Aktienfonds
            
            # Gross = Net / (1 - TF_rate) if Net > 0
            # Gross = Net / (1 + TF_rate_on_loss_abs) if Net < 0. TF amount makes loss smaller.
            # For Teilfreistellung, the rate applies to the absolute amount of gain/loss.
            # So if Net = Gross - |Gross| * TF_Rate => Net = Gross * (1 - TF_Rate) for G > 0
            # And if Net = Gross + |Gross| * TF_Rate => Net = Gross * (1 + TF_Rate) for G < 0 (where Gross is negative)
            # This means Net = Gross * (1 - sign(Gross) * TF_Rate)
            # Then Gross = Net / (1 - sign(Gross) * TF_Rate) if sign(Gross) could be known.
            # Simpler: if net > 0, gross > 0. if net < 0, gross < 0.
            # if simulated_net_fund_income >= D(0):
            #     gross_fund_gl = simulated_net_fund_income / (D("1") - tf_rate) if (D("1") - tf_rate) != D(0) else simulated_net_fund_income # Avoid div by zero if TF=100%
            # else: # simulated_net_fund_income < D(0)
            #     gross_fund_gl = simulated_net_fund_income / (D("1") - tf_rate) # Correct formula is: Net = Gross + Gross.abs() * TF_Rate => Net = Gross (1 - TF_Rate) for negative Gross.
            
            # Corrected calculation for gross_fund_gl based on net and TF rate:
            # Net_Gain = Gross_Gain * (1 - TF_Rate)  => Gross_Gain = Net_Gain / (1 - TF_Rate)
            # Net_Loss = Gross_Loss * (1 - TF_Rate) (where Gross_Loss is negative, TF_Rate reduces the magnitude of the loss)
            # Example: Gross_Loss = -100, TF = 30%. TF_Amount = 30. Net_Loss = -100 + 30 = -70.
            # So Net = Gross - Gross.copy_abs() * TF_Rate if Gross >=0
            #    Net = Gross + Gross.copy_abs() * TF_Rate if Gross < 0
            # This means: Net = Gross * (1 - TF_Rate) for Gains
            #             Net = Gross * (1 - TF_Rate) for Losses (where Gross is neg, (1-TF) is pos, result neg)
            # So, always: Gross = Net / (1 - TF_Rate), assuming (1-TF_Rate) != 0
            
            denominator = (D("1") - tf_rate)
            gross_fund_gl = simulated_net_fund_income / denominator if denominator != D(0) else simulated_net_fund_income

            gross_fund_gl = gross_fund_gl.quantize(D("0.000001"), rounding=ROUND_HALF_UP) 

            mock_fund_asset = InvestmentFund(
                internal_asset_id=fund_asset_id,
                description="Mock Aktienfonds for Test",
                currency="EUR",
                fund_type=InvestmentFundType.AKTIENFONDS
            )
            asset_resolver.add_mock_asset(mock_fund_asset)

            fund_rgl = create_mock_rgl_for_pot_testing(
                gross_amount=gross_fund_gl,
                asset_category=AssetCategory.INVESTMENT_FUND,
                fund_type_for_fund_rgl=InvestmentFundType.AKTIENFONDS,
                asset_id=fund_asset_id
            )
            
            expected_net_quantized = simulated_net_fund_income.quantize(global_config.OUTPUT_PRECISION_AMOUNTS)
            actual_net_from_rgl = fund_rgl.net_gain_loss_after_teilfreistellung_eur
            if actual_net_from_rgl is None: 
                raise ValueError("Fund RGL net_gain_loss_after_teilfreistellung_eur is None")
            
            assert abs(actual_net_from_rgl - expected_net_quantized) < D("0.01"), \
                f"{test_id}: Mismatch in generated fund RGL net income. Expected {expected_net_quantized}, got {actual_net_from_rgl} from gross {gross_fund_gl}."

            mock_rgls.append(fund_rgl)


        if input_gross_pot_components.get('akt_g', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(input_gross_pot_components['akt_g'], AssetCategory.STOCK))
        if input_gross_pot_components.get('akt_v', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(-input_gross_pot_components['akt_v'], AssetCategory.STOCK))

        if input_gross_pot_components.get('term_g', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(input_gross_pot_components['term_g'], AssetCategory.OPTION))
        if input_gross_pot_components.get('term_v', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(-input_gross_pot_components['term_v'], AssetCategory.OPTION))
        
        if input_gross_pot_components.get('sonst_g', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(input_gross_pot_components['sonst_g'], AssetCategory.BOND))
        if input_gross_pot_components.get('sonst_v', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(-input_gross_pot_components['sonst_v'], AssetCategory.BOND))
        
        if input_gross_pot_components.get('p23_g', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(input_gross_pot_components['p23_g'], AssetCategory.PRIVATE_SALE_ASSET, is_taxable_p23=True))
        if input_gross_pot_components.get('p23_v', D(0)) > D(0):
            mock_rgls.append(create_mock_rgl_for_pot_testing(-input_gross_pot_components['p23_v'], AssetCategory.PRIVATE_SALE_ASSET, is_taxable_p23=True))
        
        engine = LossOffsettingEngine(
            realized_gains_losses=mock_rgls,
            vorabpauschale_items=[], 
            current_year_financial_events=mock_current_year_events, 
            asset_resolver=asset_resolver,
            tax_year=global_config.TAX_YEAR,
            apply_conceptual_derivative_loss_capping=global_config.APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING
        )

        result: LossOffsettingResult = engine.calculate_reporting_figures()

        for expected_key_str, engine_key_or_cat in EXPECTED_FORM_LINE_TO_ENGINE_KEY_MAP.items():
            expected_value = expected_reporting_and_summaries.get(expected_key_str, D("0.00"))
            actual_value = result.form_line_values.get(engine_key_or_cat, D("0.00")) 
            
            assert actual_value.compare(expected_value) == D("0"), \
                (f"{test_id}: Mismatch for FORM LINE {expected_key_str} (Engine key: {engine_key_or_cat}). "
                 f"Expected {expected_value}, got {actual_value}. "
                 f"Relevant Input Pots: {input_gross_pot_components}. "
                 f"All form_line_values: { {str(k):v for k,v in result.form_line_values.items()} }")

        for expected_key_str, engine_field_name in EXPECTED_CONCEPTUAL_TO_ENGINE_FIELD_MAP.items():
            expected_value = expected_reporting_and_summaries.get(expected_key_str, D("0.00"))
            actual_value = getattr(result, engine_field_name, D("0.00")) 

            assert actual_value.compare(expected_value) == D("0"), \
                (f"{test_id}: Mismatch for CONCEPTUAL SUMMARY {expected_key_str} (Engine field: {engine_field_name}). "
                 f"Expected {expected_value}, got {actual_value}. "
                 f"Relevant Input Pots: {input_gross_pot_components}.")

        if test_id in ["LO_FUND_001", "LO_FUND_002"]:
            non_fund_akt_g = input_gross_pot_components.get('akt_g', D(0))
            non_fund_akt_v = input_gross_pot_components.get('akt_v', D(0))
            non_fund_term_g = input_gross_pot_components.get('term_g', D(0))
            non_fund_sonst_g = input_gross_pot_components.get('sonst_g', D(0))
            non_fund_sonst_v = input_gross_pot_components.get('sonst_v', D(0))

            expected_z19_without_fund_effect = (non_fund_akt_g + non_fund_term_g + non_fund_sonst_g - non_fund_akt_v - non_fund_sonst_v).quantize(global_config.OUTPUT_PRECISION_AMOUNTS)
            expected_conceptual_other_without_fund_effect = (non_fund_sonst_g - non_fund_sonst_v).quantize(global_config.OUTPUT_PRECISION_AMOUNTS)
            
            actual_z19 = result.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT, D("0.00"))
            actual_conceptual_other = result.conceptual_net_other_income

            assert actual_z19.compare(expected_z19_without_fund_effect) == D("0"), \
                (f"{test_id}: Anlage KAP Z.19 verification failed. Expected (without fund effect) {expected_z19_without_fund_effect}, got {actual_z19}. This indicates fund income might be incorrectly included.")
            
            assert actual_conceptual_other.compare(expected_conceptual_other_without_fund_effect) == D("0"), \
                (f"{test_id}: Conceptual Net Other Income verification failed. Expected (without fund effect) {expected_conceptual_other_without_fund_effect}, got {actual_conceptual_other}. This indicates fund income might be incorrectly included.")

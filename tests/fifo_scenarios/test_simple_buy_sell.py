# tests/fifo_scenarios/test_simple_buy_sell.py
import pytest
from decimal import Decimal

from tests.fifo_scenarios.test_case_base import FifoTestCaseBase
from tests.results.test_result_defs import ScenarioExpectedOutput, ExpectedRealizedGainLoss, ExpectedAssetEoyState
from tests.helpers.mock_providers import MockECBExchangeRateProvider
from src.domain.enums import AssetCategory, TaxReportingCategory, RealizationType

ACCOUNT_ID = "U_TEST_SIMPLE"
DEFAULT_TAX_YEAR = 2023
COMMISSION_EUR = Decimal("-1.00")
COMMISSION_USD = Decimal("-1.00")

class TestSimpleBuySell(FifoTestCaseBase):

    def test_buy_then_sell_all_eur(self, mock_config_paths):
        asset_a_symbol = "ASSET.A.EUR"
        asset_a_isin = "TESTISINAAAEUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_a_symbol, "Asset A EUR", asset_a_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-03-01", Decimal("10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "BUY", "T001", None, None, "CONA01EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_a_symbol, "Asset A EUR", asset_a_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-09-15", Decimal("-10"), Decimal("120.00"), COMMISSION_EUR, "EUR",
             "SELL", "T002", None, None, "CONA01EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_a_symbol, "Asset A EUR", asset_a_isin,
             Decimal("0"), Decimal("0"), Decimal("120.00"), Decimal("0"),
             None, "CONA01EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_L_001: Simple buy and sell all shares in EUR, no SOY.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_a_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-09-15",
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("1001.00"), # CHANGED from total_cost_basis_eur_realized
                    total_realization_value_eur=Decimal("1199.00"),
                    gross_gain_loss_eur=Decimal("198.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-03-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_a_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        mock_rate_provider = MockECBExchangeRateProvider()
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_buy_usd_sell_usd_mock_conversion(self, mock_config_paths):
        asset_b_symbol = "ASSET.B.USD"
        asset_b_isin = "TESTISINBBBUSD"
        usd_curr = "USD"

        trades_data = [
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_b_symbol, "Asset B USD", asset_b_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-02-01", Decimal("10"), Decimal("50.00"), COMMISSION_USD, usd_curr,
             "BUY", "T003", None, None, "CONB01USD", None, Decimal("1"), "O"],
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_b_symbol, "Asset B USD", asset_b_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-10-01", Decimal("-10"), Decimal("60.00"), COMMISSION_USD, usd_curr,
             "SELL", "T004", None, None, "CONB01USD", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_b_symbol, "Asset B USD", asset_b_isin,
             Decimal("0"), Decimal("0"), Decimal("60.00"), Decimal("0"), 
             None, "CONB01USD", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_L_001 (USD): Simple buy and sell all shares in USD with 1:2 mock conversion to EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_b_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-10-01",
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("1002.00"), # CHANGED
                    total_realization_value_eur=Decimal("1198.00"),
                    gross_gain_loss_eur=Decimal("196.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-02-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_b_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_buy_then_sell_partial_eur(self, mock_config_paths):
        asset_c_symbol = "ASSET.C.EUR"
        asset_c_isin = "TESTISINCCCCEUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_c_symbol, "Asset C EUR", asset_c_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-04-01", Decimal("10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "BUY", "T005", None, None, "CONC01EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_c_symbol, "Asset C EUR", asset_c_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-10-01", Decimal("-5"), Decimal("120.00"), COMMISSION_EUR, "EUR",
             "SELL", "T006", None, None, "CONC01EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_c_symbol, "Asset C EUR", asset_c_isin,
             Decimal("5"), Decimal("600"), Decimal("120.00"), Decimal("500.50"),
             None, "CONC01EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_L_002: Buy then sell partial in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_c_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-10-01",
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("500.50"), # CHANGED
                    total_realization_value_eur=Decimal("599.00"),
                    gross_gain_loss_eur=Decimal("98.50"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-04-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_c_isin}", eoy_quantity=Decimal("5"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_multiple_buys_single_sell_eur(self, mock_config_paths):
        asset_d_symbol = "ASSET.D.EUR"
        asset_d_isin = "TESTISINDDDDEUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_d_symbol, "Asset D EUR", asset_d_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-03-01", Decimal("10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "BUY", "T007", None, None, "COND01EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_d_symbol, "Asset D EUR", asset_d_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-04-01", Decimal("10"), Decimal("110.00"), COMMISSION_EUR, "EUR",
             "BUY", "T008", None, None, "COND01EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_d_symbol, "Asset D EUR", asset_d_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-09-01", Decimal("-10"), Decimal("120.00"), COMMISSION_EUR, "EUR",
             "SELL", "T009", None, None, "COND01EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
             [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_d_symbol, "Asset D EUR", asset_d_isin,
             Decimal("10"), Decimal("1200"), Decimal("120.00"), Decimal("1101.00"),
             None, "COND01EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_L_003: Multiple Buys, Single Sell (covering first lot) in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_d_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-09-01",
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("1001.00"), # CHANGED
                    total_realization_value_eur=Decimal("1199.00"),
                    gross_gain_loss_eur=Decimal("198.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-03-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_d_isin}", eoy_quantity=Decimal("10"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_multiple_buys_multiple_sells_eur(self, mock_config_paths):
        asset_symbol = "ASSET.X.EUR"
        asset_isin = "TESTISINXL004EUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-03-01", Decimal("10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "BUY", "T012", None, None, "CONX04EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-04-01", Decimal("10"), Decimal("110.00"), COMMISSION_EUR, "EUR",
             "BUY", "T013", None, None, "CONX04EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-09-01", Decimal("-5"), Decimal("120.00"), COMMISSION_EUR, "EUR",
             "SELL", "T014", None, None, "CONX04EUR", None, Decimal("1"), "C"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-10-01", Decimal("-10"), Decimal("125.00"), COMMISSION_EUR, "EUR",
             "SELL", "T015", None, None, "CONX04EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             Decimal("5"), Decimal("625.00"), Decimal("125.00"), Decimal("550.50"), 
             None, "CONX04EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_L_004: Long: Multiple Buys, Multiple Sells in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-09-01",
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("500.50"), # CHANGED
                    total_realization_value_eur=Decimal("599.00"),
                    gross_gain_loss_eur=Decimal("98.50"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-03-01", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-10-01",
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("500.50"), # CHANGED
                    total_realization_value_eur=Decimal("624.50"),
                    gross_gain_loss_eur=Decimal("124.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-03-01", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-10-01",
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("550.50"), # CHANGED
                    total_realization_value_eur=Decimal("624.50"),
                    gross_gain_loss_eur=Decimal("74.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-04-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("5"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_sell_short_then_buy_cover_all_eur(self, mock_config_paths):
        asset_e_symbol = "ASSET.E.EUR"
        asset_e_isin = "TESTISINEEEEEUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_e_symbol, "Asset E EUR", asset_e_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-05-01", Decimal("-10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "SELL", "T010", None, None, "CONE01EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_e_symbol, "Asset E EUR", asset_e_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-11-01", Decimal("10"), Decimal("80.00"), COMMISSION_EUR, "EUR",
             "BUY", "T011", None, None, "CONE01EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
             [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_e_symbol, "Asset E EUR", asset_e_isin,
             Decimal("0"), Decimal("0"), Decimal("80.00"), Decimal("0"),
             None, "CONE01EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_S_001: Basic Short: Sell Short then Buy Cover All in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_e_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-11-01",
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("801.00"), # CHANGED
                    total_realization_value_eur=Decimal("999.00"),
                    gross_gain_loss_eur=Decimal("198.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-05-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name, 
                    realization_type=RealizationType.SHORT_POSITION_COVER.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_e_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_sell_short_then_buy_cover_partial_eur(self, mock_config_paths):
        asset_symbol = "ASSET.X.EUR"
        asset_isin = "TESTISINXS002EUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-05-01", Decimal("-10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "SELL", "T016", None, None, "CONXS02EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-11-01", Decimal("5"), Decimal("80.00"), COMMISSION_EUR, "EUR",
             "BUY", "T017", None, None, "CONXS02EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             Decimal("-5"), Decimal("-400.00"), Decimal("80.00"), Decimal("-499.50"), 
             None, "CONXS02EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_S_002: Short: Sell Short then Buy Cover Partial in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-11-01", 
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("401.00"), # CHANGED
                    total_realization_value_eur=Decimal("499.50"),
                    gross_gain_loss_eur=Decimal("98.50"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-05-01", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("-5"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_multiple_ssos_single_cover_eur(self, mock_config_paths):
        asset_symbol = "ASSET.X.EUR"
        asset_isin = "TESTISINXS003EUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-05-01", Decimal("-10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "SELL", "T018", None, None, "CONXS03EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-06-01", Decimal("-10"), Decimal("90.00"), COMMISSION_EUR, "EUR",
             "SELL", "T019", None, None, "CONXS03EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-11-01", Decimal("10"), Decimal("80.00"), COMMISSION_EUR, "EUR",
             "BUY", "T020", None, None, "CONXS03EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             Decimal("-10"), Decimal("-800.00"), Decimal("80.00"), Decimal("-899.00"), 
             None, "CONXS03EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_S_003: Short: Multiple SSOs, Single Cover (covering first lot) in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-11-01", 
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("801.00"), # CHANGED
                    total_realization_value_eur=Decimal("999.00"),
                    gross_gain_loss_eur=Decimal("198.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-05-01", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("-10"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_multiple_ssos_multiple_covers_eur(self, mock_config_paths):
        asset_symbol = "ASSET.X.EUR"
        asset_isin = "TESTISINXS004EUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-05-01", Decimal("-10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "SELL", "T021", None, None, "CONXS04EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-06-01", Decimal("-10"), Decimal("90.00"), COMMISSION_EUR, "EUR",
             "SELL", "T022", None, None, "CONXS04EUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-11-01", Decimal("5"), Decimal("80.00"), COMMISSION_EUR, "EUR",
             "BUY", "T023", None, None, "CONXS04EUR", None, Decimal("1"), "C"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-12-01", Decimal("10"), Decimal("75.00"), COMMISSION_EUR, "EUR",
             "BUY", "T024", None, None, "CONXS04EUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset X EUR", asset_isin,
             Decimal("-5"), Decimal("-375.00"), Decimal("75.00"), Decimal("-449.50"), 
             None, "CONXS04EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_S_004: Short: Multiple SSOs, Multiple Covers in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-11-01",
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("401.00"), # CHANGED
                    total_realization_value_eur=Decimal("499.50"),
                    gross_gain_loss_eur=Decimal("98.50"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-05-01", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name,
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-12-01",
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("375.50"), # CHANGED
                    total_realization_value_eur=Decimal("499.50"),
                    gross_gain_loss_eur=Decimal("124.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-05-01", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name,
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-12-01",
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("375.50"), # CHANGED
                    total_realization_value_eur=Decimal("449.50"),
                    gross_gain_loss_eur=Decimal("74.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-06-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("-5"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_zero_quantity_trade_eur(self, mock_config_paths):
        asset_symbol = "ASSET.Z.EUR"
        asset_isin = "TESTISINXZ001EUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset Z EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-07-01", Decimal("0"), Decimal("100.00"), Decimal("0.00"), "EUR",
             "BUY", "T025Z", None, None, "CONXZ01EUR", None, Decimal("1"), "O"],
        ]
        positions_start_data = []
        positions_end_data = [ 
             [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset Z EUR", asset_isin,
             Decimal("0"), Decimal("0.00"), Decimal("100.00"), Decimal("0.00"),
             None, "CONXZ01EUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_Z_001: Zero Quantity Trade in EUR. Should result in no RGLs.",
            expected_rgls=[], 
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    def test_mixed_assets_long_and_short_eur(self, mock_config_paths):
        asset_x_symbol = "ASSET.X.EUR"
        asset_x_isin = "TESTISINXM01XEUR"
        asset_y_symbol = "ASSET.Y.EUR"
        asset_y_isin = "TESTISINXM01YEUR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_x_symbol, "Asset X EUR", asset_x_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-03-01", Decimal("10"), Decimal("50.00"), COMMISSION_EUR, "EUR",
             "BUY", "T025X", None, None, "CONXM01XEUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_x_symbol, "Asset X EUR", asset_x_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-09-01", Decimal("-10"), Decimal("60.00"), COMMISSION_EUR, "EUR",
             "SELL", "T026X", None, None, "CONXM01XEUR", None, Decimal("1"), "C"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_y_symbol, "Asset Y EUR", asset_y_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-04-01", Decimal("-5"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "SELL", "T027Y", None, None, "CONXM01YEUR", None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_y_symbol, "Asset Y EUR", asset_y_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-10-01", Decimal("5"), Decimal("90.00"), COMMISSION_EUR, "EUR",
             "BUY", "T028Y", None, None, "CONXM01YEUR", None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_x_symbol, "Asset X EUR", asset_x_isin,
             Decimal("0"), Decimal("0.00"), Decimal("60.00"), Decimal("0.00"),
             None, "CONXM01XEUR", None, Decimal("1")],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_y_symbol, "Asset Y EUR", asset_y_isin,
             Decimal("0"), Decimal("0.00"), Decimal("90.00"), Decimal("0.00"),
             None, "CONXM01YEUR", None, Decimal("1")]
        ]
        expected_outcome = ScenarioExpectedOutput(
            test_description="CFM_M_001: Mixed Assets (Long X, Short Y) in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss( 
                    asset_identifier=f"ISIN:{asset_x_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-09-01",
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("501.00"), # CHANGED
                    total_realization_value_eur=Decimal("599.00"), 
                    gross_gain_loss_eur=Decimal("98.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-03-01",
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
                ExpectedRealizedGainLoss( 
                    asset_identifier=f"ISIN:{asset_y_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-10-01", 
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("451.00"), # CHANGED
                    total_realization_value_eur=Decimal("499.00"), 
                    gross_gain_loss_eur=Decimal("48.00"),
                    acquisition_date=f"{DEFAULT_TAX_YEAR}-04-01", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name,
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_x_isin}", eoy_quantity=Decimal("0")),
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_y_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

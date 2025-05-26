# tests/fifo_scenarios/test_soy_eoy_scenarios.py
import pytest
from decimal import Decimal
from datetime import date

from tests.fifo_scenarios.test_case_base import FifoTestCaseBase
from tests.results.test_result_defs import ScenarioExpectedOutput, ExpectedRealizedGainLoss, ExpectedAssetEoyState
from tests.helpers.mock_providers import MockECBExchangeRateProvider
from src.domain.enums import AssetCategory, TaxReportingCategory, RealizationType # Ensured RealizationType is imported

# Assumed constants for readability
ACCOUNT_ID = "U_TEST_SOY_EOY" # Kept original, can be overridden or made more specific if needed per test
DEFAULT_TAX_YEAR = 2023
HISTORICAL_YEAR = DEFAULT_TAX_YEAR - 1
COMMISSION_EUR = Decimal("-1.00")
COMMISSION_USD = Decimal("-1.00")


class TestSoyEoyScenarios(FifoTestCaseBase):

    # Corresponds to SOY_R_001
    def test_soy_from_report_only_no_hist_sell_all_eur(self, mock_config_paths):
        asset_a_symbol = "ASSET.A.EUR" # For SOY_R_001
        asset_a_isin = "TESTISINSOYRAEUR"
        asset_a_conid = "CONA01SOYR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_a_symbol, "Asset A EUR", asset_a_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-07-15", Decimal("-10"), Decimal("120.00"), COMMISSION_EUR, "EUR",
             "SELL", "T_CURR_A001", None, None, asset_a_conid, None, Decimal("1"), "C"],
        ]

        positions_start_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_a_symbol, "Asset A EUR", asset_a_isin,
             Decimal("10"), Decimal("1200"), Decimal("120.00"), Decimal("1000.00"), # Qty, Val, MarkPx, CostBasisMoney
             None, asset_a_conid, None, Decimal("1")]
        ]
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_a_symbol, "Asset A EUR", asset_a_isin,
             Decimal("0"), Decimal("0"), Decimal("120.00"), Decimal("0.00"),
             None, asset_a_conid, None, Decimal("1")]
        ]
        
        # Cost basis from SOY Report: 1000 EUR
        # Proceeds: 10 * 120 - 1 = 1199 EUR
        # Gain: 1199 - 1000 = 199 EUR
        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_R_001: SOY Long from Report Only (No Hist.), Sell All in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_a_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-07-15",
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("1000.00"), # CHANGED
                    total_realization_value_eur=Decimal("1199.00"),
                    gross_gain_loss_eur=Decimal("199.00"),
                    acquisition_date=f"{HISTORICAL_YEAR}-12-31", # Fallback SOY cost implies prev year-end acq.
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(date(DEFAULT_TAX_YEAR, 7, 15) - date(HISTORICAL_YEAR, 12, 31)).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_a_isin}", eoy_quantity=Decimal("0"))
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

    # Corresponds to SOY_R_002
    def test_soy_short_from_report_only_no_hist_cover_all_eur(self, mock_config_paths):
        asset_symbol = "ASSET.R002.EUR"
        asset_isin = "TESTISINSOYR002EUR"
        asset_conid = "CONR002SOYR"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset R002 EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-08-10", Decimal("10"), Decimal("80.00"), COMMISSION_EUR, "EUR",
             "BUY", "T_CURR_R002", None, None, asset_conid, None, Decimal("1"), "C"], # Buy to Cover
        ]

        positions_start_data = [ # SOY_RPT(-10, 1000 EUR proceeds)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset R002 EUR", asset_isin,
             Decimal("-10"), Decimal("-800"), Decimal("80.00"), Decimal("1000.00"), # Qty, Val, MarkPx, ProceedsBasisMoney
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset R002 EUR", asset_isin,
             Decimal("0"), Decimal("0"), Decimal("80.00"), Decimal("0.00"),
             None, asset_conid, None, Decimal("1")]
        ]
        
        # Proceeds basis from SOY Report: 1000 EUR
        # Cost to Cover: 10 * 80 + abs(-1) = 801 EUR
        # Gain: 1000 - 801 = 199 EUR
        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_R_002: SOY Short from Report Only (No Hist.), Cover All in EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=f"{DEFAULT_TAX_YEAR}-08-10",
                    quantity_realized=Decimal("10"), # Absolute quantity
                    total_cost_basis_eur=Decimal("801.00"), # CHANGED: Cost to cover
                    total_realization_value_eur=Decimal("1000.00"), # Proceeds from initial short
                    gross_gain_loss_eur=Decimal("199.00"),
                    acquisition_date=f"{HISTORICAL_YEAR}-12-31", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name, 
                    holding_period_days=(date(DEFAULT_TAX_YEAR, 8, 10) - date(HISTORICAL_YEAR, 12, 31)).days
                )
            ],
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

    # Corresponds to SOY_H_001
    def test_soy_long_hist_trades_sufficient_cost_from_hist_usd(self, mock_config_paths):
        asset_b_symbol = "ASSET.B.USD" 
        asset_b_isin = "TESTISINSOYHBUSD"
        asset_b_conid = "CONB01SOYH"
        usd_curr = "USD"
        hist_trade_date_str = f"{HISTORICAL_YEAR}-03-01"
        hist_trade_date_obj = date(HISTORICAL_YEAR, 3, 1)
        sell_date_str = f"{DEFAULT_TAX_YEAR}-07-15"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 7, 15)


        trades_data = [
            # Historical Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_b_symbol, "Asset B USD", asset_b_isin,
             None, None, None, hist_trade_date_str, Decimal("15"), Decimal("90.00"), COMMISSION_USD, usd_curr,
             "BUY", "T_HIST_B001", None, None, asset_b_conid, None, Decimal("1"), "O"],
            # Intra-Year Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_b_symbol, "Asset B USD", asset_b_isin,
             None, None, None, sell_date_str, Decimal("-10"), Decimal("120.00"), COMMISSION_USD, usd_curr,
             "SELL", "T_CURR_B001", None, None, asset_b_conid, None, Decimal("1"), "C"],
        ]

        positions_start_data = [ # SOY_RPT(10, ignored_cost)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_b_symbol, "Asset B USD", asset_b_isin,
             Decimal("10"), Decimal("1200"), Decimal("120.00"), Decimal("950.00"), # Qty 10, CostBasisMoney is ignored here
             None, asset_b_conid, None, Decimal("1")]
        ]
        positions_end_data = [ # EOY Qty 0
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_b_symbol, "Asset B USD", asset_b_isin,
             Decimal("0"), Decimal("0"), Decimal("120.00"), Decimal("0.00"),
             None, asset_b_conid, None, Decimal("1")]
        ]
        
        hist_cost_per_share_usd = (Decimal("15") * Decimal("90.00") + COMMISSION_USD.copy_abs()) / Decimal("15") 
        cost_basis_usd = hist_cost_per_share_usd * Decimal("10") 
        proceeds_usd = (Decimal("10") * Decimal("120.00")) - COMMISSION_USD.copy_abs() 
        gain_usd = proceeds_usd - cost_basis_usd 
        
        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        rate = mock_rate_provider.one_foreign_unit_in_eur

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_H_001: SOY Long, Hist. sufficient, cost from Hist. trades. USD.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_b_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=(cost_basis_usd * rate), # CHANGED
                    total_realization_value_eur=(proceeds_usd * rate), 
                    gross_gain_loss_eur=(gain_usd * rate),
                    acquisition_date=hist_trade_date_str, 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,  
                    holding_period_days=(sell_date_obj - hist_trade_date_obj).days               
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_b_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=mock_rate_provider, 
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to SOY_H_002
    def test_soy_short_hist_trades_sufficient_proceeds_from_hist_usd(self, mock_config_paths):
        asset_symbol = "ASSET.H002.USD"
        asset_isin = "TESTISINSOYH002USD"
        asset_conid = "CONH002SOYH"
        usd_curr = "USD"
        hist_trade_date_str = f"{HISTORICAL_YEAR}-04-01"
        hist_trade_date_obj = date(HISTORICAL_YEAR, 4, 1)
        cover_date_str = f"{DEFAULT_TAX_YEAR}-06-20"
        cover_date_obj = date(DEFAULT_TAX_YEAR, 6, 20)

        trades_data = [
            # Historical Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset H002 USD", asset_isin,
             None, None, None, hist_trade_date_str, Decimal("-15"), Decimal("110.00"), COMMISSION_USD, usd_curr,
             "SELL", "T_HIST_H002", None, None, asset_conid, None, Decimal("1"), "O"], # Sell Short Open
            # Intra-Year Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset H002 USD", asset_isin,
             None, None, None, cover_date_str, Decimal("10"), Decimal("90.00"), COMMISSION_USD, usd_curr,
             "BUY", "T_CURR_H002", None, None, asset_conid, None, Decimal("1"), "C"], # Buy to Cover
        ]

        positions_start_data = [ # SOY_RPT(-10, ignored_proceeds)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset H002 USD", asset_isin,
             Decimal("-10"), Decimal("-900"), Decimal("90.00"), Decimal("1150.00"), # Qty -10, ProceedsBasisMoney ignored
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [ # EOY Qty 0
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset H002 USD", asset_isin,
             Decimal("0"), Decimal("0"), Decimal("90.00"), Decimal("0.00"),
             None, asset_conid, None, Decimal("1")]
        ]
        
        hist_proceeds_per_share_usd = (Decimal("15") * Decimal("110.00") - COMMISSION_USD.copy_abs()) / Decimal("15") 
        proceeds_basis_usd = hist_proceeds_per_share_usd * Decimal("10") 
        cost_to_cover_usd = (Decimal("10") * Decimal("90.00")) + COMMISSION_USD.copy_abs() 
        gain_usd = proceeds_basis_usd - cost_to_cover_usd 
        
        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        rate = mock_rate_provider.one_foreign_unit_in_eur

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_H_002: SOY Short, Hist. sufficient, proceeds from Hist. trades. USD.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=cover_date_str,
                    quantity_realized=Decimal("10"), # Absolute quantity
                    total_cost_basis_eur=(cost_to_cover_usd * rate), # CHANGED
                    total_realization_value_eur=(proceeds_basis_usd * rate), 
                    gross_gain_loss_eur=(gain_usd * rate),
                    acquisition_date=hist_trade_date_str, 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(cover_date_obj - hist_trade_date_obj).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=mock_rate_provider, 
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to SOY_F_001
    def test_soy_long_fallback_hist_insufficient_sell_all_usd(self, mock_config_paths):
        asset_d_symbol = "ASSET.D.USD" 
        asset_d_isin = "TESTISINSOYFDUSD"
        asset_d_conid = "COND01SOYF"
        usd_curr = "USD"
        sell_date_str = f"{DEFAULT_TAX_YEAR}-05-10"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 5, 10)

        trades_data = [
            # Historical Trade (insufficient)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_d_symbol, "Asset D USD", asset_d_isin,
             None, None, None, f"{HISTORICAL_YEAR}-08-01", Decimal("10"), Decimal("90.00"), COMMISSION_USD, usd_curr,
             "BUY", "T_HIST_D001", None, None, asset_d_conid, None, Decimal("1"), "O"],
            # Intra-Year Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_d_symbol, "Asset D USD", asset_d_isin,
             None, None, None, sell_date_str, Decimal("-20"), Decimal("120.00"), COMMISSION_USD, usd_curr,
             "SELL", "T_CURR_D001", None, None, asset_d_conid, None, Decimal("1"), "C"],
        ]

        positions_start_data = [ # SOY_RPT(20, 2000 USD cost_basis_money)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_d_symbol, "Asset D USD", asset_d_isin,
             Decimal("20"), Decimal("2400"), Decimal("120.00"), Decimal("2000.00"), 
             None, asset_d_conid, None, Decimal("1")]
        ]
        positions_end_data = [ # EOY Qty 0
             [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_d_symbol, "Asset D USD", asset_d_isin,
             Decimal("0"), Decimal("0"), Decimal("120.00"), Decimal("0.00"),
             None, asset_d_conid, None, Decimal("1")]
        ]
        
        cost_basis_usd_soy = Decimal("2000.00") 
        proceeds_usd_sale = (Decimal("20") * Decimal("120.00")) - COMMISSION_USD.copy_abs() 
        gain_usd = proceeds_usd_sale - cost_basis_usd_soy 

        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        rate = mock_rate_provider.one_foreign_unit_in_eur

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_F_001: SOY Long Fallback, Hist. Insufficient, cost from SOY Report. USD.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_d_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("20"),
                    total_cost_basis_eur=(cost_basis_usd_soy * rate), # CHANGED
                    total_realization_value_eur=(proceeds_usd_sale * rate), 
                    gross_gain_loss_eur=(gain_usd * rate), 
                    acquisition_date=f"{HISTORICAL_YEAR}-12-31", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - date(HISTORICAL_YEAR, 12, 31)).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_d_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to SOY_F_002
    def test_soy_short_fallback_hist_insufficient_cover_all_usd(self, mock_config_paths):
        asset_symbol = "ASSET.F002.USD"
        asset_isin = "TESTISINSOYF002USD"
        asset_conid = "CONF002SOYF"
        usd_curr = "USD"
        cover_date_str = f"{DEFAULT_TAX_YEAR}-07-25"
        cover_date_obj = date(DEFAULT_TAX_YEAR, 7, 25)

        trades_data = [
            # Historical Trade (insufficient)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset F002 USD", asset_isin,
             None, None, None, f"{HISTORICAL_YEAR}-09-15", Decimal("-10"), Decimal("110.00"), COMMISSION_USD, usd_curr,
             "SELL", "T_HIST_F002", None, None, asset_conid, None, Decimal("1"), "O"], # Sell Short Open
            # Intra-Year Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset F002 USD", asset_isin,
             None, None, None, cover_date_str, Decimal("20"), Decimal("90.00"), COMMISSION_USD, usd_curr,
             "BUY", "T_CURR_F002", None, None, asset_conid, None, Decimal("1"), "C"], # Buy to Cover
        ]

        positions_start_data = [ # SOY_RPT(-20, 2200 USD proceeds)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset F002 USD", asset_isin,
             Decimal("-20"), Decimal("-1800"), Decimal("90.00"), Decimal("2200.00"), 
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [ # EOY Qty 0
             [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset F002 USD", asset_isin,
             Decimal("0"), Decimal("0"), Decimal("90.00"), Decimal("0.00"),
             None, asset_conid, None, Decimal("1")]
        ]
        
        proceeds_basis_usd_soy = Decimal("2200.00") 
        cost_to_cover_usd = (Decimal("20") * Decimal("90.00")) + COMMISSION_USD.copy_abs() 
        gain_usd = proceeds_basis_usd_soy - cost_to_cover_usd 

        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        rate = mock_rate_provider.one_foreign_unit_in_eur

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_F_002: SOY Short Fallback, Hist. Insufficient, proceeds from SOY Report. USD.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=cover_date_str,
                    quantity_realized=Decimal("20"), # Absolute quantity
                    total_cost_basis_eur=(cost_to_cover_usd * rate), # CHANGED
                    total_realization_value_eur=(proceeds_basis_usd_soy * rate), 
                    gross_gain_loss_eur=(gain_usd * rate), 
                    acquisition_date=f"{HISTORICAL_YEAR}-12-31", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(cover_date_obj - date(HISTORICAL_YEAR, 12, 31)).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to SOY_F_003
    def test_soy_long_fallback_no_hist_trades_sell_all_usd(self, mock_config_paths):
        asset_symbol = "ASSET.F003.USD"
        asset_isin = "TESTISINSOYF003USD"
        asset_conid = "CONF003SOYF"
        usd_curr = "USD"
        sell_date_str = f"{DEFAULT_TAX_YEAR}-03-10"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 3, 10)

        trades_data = [
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset F003 USD", asset_isin,
             None, None, None, sell_date_str, Decimal("-10"), Decimal("120.00"), COMMISSION_USD, usd_curr,
             "SELL", "T_CURR_F003", None, None, asset_conid, None, Decimal("1"), "C"],
        ]

        positions_start_data = [ # SOY_RPT(10, 1000 USD)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset F003 USD", asset_isin,
             Decimal("10"), Decimal("1200"), Decimal("120.00"), Decimal("1000.00"), 
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [
             [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset F003 USD", asset_isin,
             Decimal("0"), Decimal("0"), Decimal("120.00"), Decimal("0.00"),
             None, asset_conid, None, Decimal("1")]
        ]
        
        cost_basis_usd_soy = Decimal("1000.00")
        proceeds_usd_sale = (Decimal("10") * Decimal("120.00")) - COMMISSION_USD.copy_abs() 
        gain_usd = proceeds_usd_sale - cost_basis_usd_soy 

        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        rate = mock_rate_provider.one_foreign_unit_in_eur

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_F_003: SOY Long Fallback, No Hist. Trades, Sell All. USD.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=(cost_basis_usd_soy * rate), # CHANGED
                    total_realization_value_eur=(proceeds_usd_sale * rate), 
                    gross_gain_loss_eur=(gain_usd * rate), 
                    acquisition_date=f"{HISTORICAL_YEAR}-12-31", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - date(HISTORICAL_YEAR, 12, 31)).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=0
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to SOY_N_001
    def test_asset_not_in_soy_report_intra_year_buy_sell_eur(self, mock_config_paths):
        asset_symbol = "ASSET.N001.EUR"
        asset_isin = "TESTISINSOYN001EUR"
        asset_conid = "CONN001SOYN"
        buy_date_str = f"{DEFAULT_TAX_YEAR}-02-15"
        buy_date_obj = date(DEFAULT_TAX_YEAR, 2, 15)
        sell_date_str = f"{DEFAULT_TAX_YEAR}-09-05"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 9, 5)

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset N001 EUR", asset_isin,
             None, None, None, buy_date_str, Decimal("10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "BUY", "T_CURR_N001_B", None, None, asset_conid, None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset N001 EUR", asset_isin,
             None, None, None, sell_date_str, Decimal("-10"), Decimal("120.00"), COMMISSION_EUR, "EUR",
             "SELL", "T_CURR_N001_S", None, None, asset_conid, None, Decimal("1"), "C"],
        ]

        positions_start_data = [] # Asset not in SOY report
        positions_end_data = [
             [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset N001 EUR", asset_isin,
             Decimal("0"), Decimal("0"), Decimal("120.00"), Decimal("0.00"),
             None, asset_conid, None, Decimal("1")]
        ]
        
        cost_basis_eur = (Decimal("10") * Decimal("100.00")) + COMMISSION_EUR.copy_abs() 
        proceeds_eur = (Decimal("10") * Decimal("120.00")) - COMMISSION_EUR.copy_abs() 
        gain_eur = proceeds_eur - cost_basis_eur 

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_N_001: Asset Not in SOY Report, Intra-Year Buy then Sell. EUR.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=cost_basis_eur, # CHANGED
                    total_realization_value_eur=proceeds_eur, 
                    gross_gain_loss_eur=gain_eur, 
                    acquisition_date=buy_date_str, 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - buy_date_obj).days
                )
            ],
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

    # Corresponds to SOY_V_001
    def test_soy_long_hist_insufficient_fallback_sell_partial_usd(self, mock_config_paths):
        asset_symbol = "ASSET.V001.USD"
        asset_isin = "TESTISINSOYV001USD"
        asset_conid = "CONV001SOYV"
        usd_curr = "USD"
        sell_date_str = f"{DEFAULT_TAX_YEAR}-10-10"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 10, 10)

        trades_data = [
            # Historical Trade (insufficient)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V001 USD", asset_isin,
             None, None, None, f"{HISTORICAL_YEAR}-07-01", Decimal("10"), Decimal("95.00"), COMMISSION_USD, usd_curr,
             "BUY", "T_HIST_V001", None, None, asset_conid, None, Decimal("1"), "O"],
            # Intra-Year Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V001 USD", asset_isin,
             None, None, None, sell_date_str, Decimal("-15"), Decimal("120.00"), COMMISSION_USD, usd_curr,
             "SELL", "T_CURR_V001", None, None, asset_conid, None, Decimal("1"), "C"],
        ]

        positions_start_data = [ # SOY_RPT(20, 2000 USD) -> 100 USD/sh from report
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V001 USD", asset_isin,
             Decimal("20"), Decimal("2400"), Decimal("120.00"), Decimal("2000.00"), 
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [
             [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V001 USD", asset_isin,
             Decimal("5"), Decimal("600"), Decimal("120.00"), Decimal("500.00"), # 5 * 100
             None, asset_conid, None, Decimal("1")]
        ]
        
        cost_per_share_usd_soy = Decimal("2000.00") / Decimal("20") 
        cost_basis_usd_sold = cost_per_share_usd_soy * Decimal("15") 
        proceeds_usd_sale = (Decimal("15") * Decimal("120.00")) - COMMISSION_USD.copy_abs() 
        gain_usd = proceeds_usd_sale - cost_basis_usd_sold 

        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        rate = mock_rate_provider.one_foreign_unit_in_eur

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_V_001: SOY Long Fallback (Hist Insufficient), Sell Partial. Cost from SOY Report. USD.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("15"),
                    total_cost_basis_eur=(cost_basis_usd_sold * rate), # CHANGED
                    total_realization_value_eur=(proceeds_usd_sale * rate), 
                    gross_gain_loss_eur=(gain_usd * rate), 
                    acquisition_date=f"{HISTORICAL_YEAR}-12-31", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - date(HISTORICAL_YEAR, 12, 31)).days
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
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to SOY_V_002
    def test_soy_short_hist_insufficient_fallback_cover_partial_usd(self, mock_config_paths):
        asset_symbol = "ASSET.V002.USD"
        asset_isin = "TESTISINSOYV002USD"
        asset_conid = "CONV002SOYV"
        usd_curr = "USD"
        cover_date_str = f"{DEFAULT_TAX_YEAR}-11-05"
        cover_date_obj = date(DEFAULT_TAX_YEAR, 11, 5)

        trades_data = [
            # Historical Trade (insufficient)
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V002 USD", asset_isin,
             None, None, None, f"{HISTORICAL_YEAR}-06-01", Decimal("-10"), Decimal("105.00"), COMMISSION_USD, usd_curr,
             "SELL", "T_HIST_V002", None, None, asset_conid, None, Decimal("1"), "O"], # Sell Short Open
            # Intra-Year Trade
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V002 USD", asset_isin,
             None, None, None, cover_date_str, Decimal("15"), Decimal("90.00"), COMMISSION_USD, usd_curr,
             "BUY", "T_CURR_V002", None, None, asset_conid, None, Decimal("1"), "C"], # Buy to Cover
        ]

        positions_start_data = [ # SOY_RPT(-20, 2200 USD proceeds) -> 110 USD/sh proceeds from report
            [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V002 USD", asset_isin,
             Decimal("-20"), Decimal("-1800"), Decimal("90.00"), Decimal("2200.00"), 
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [
             [ACCOUNT_ID, usd_curr, "STK", "COMMON", asset_symbol, "Asset V002 USD", asset_isin,
             Decimal("-5"), Decimal("-450"), Decimal("90.00"), Decimal("550.00"), # -5 * 110
             None, asset_conid, None, Decimal("1")]
        ]
        
        proceeds_per_share_usd_soy = Decimal("2200.00") / Decimal("20") 
        proceeds_basis_usd_covered = proceeds_per_share_usd_soy * Decimal("15") 
        cost_to_cover_usd = (Decimal("15") * Decimal("90.00")) + COMMISSION_USD.copy_abs() 
        gain_usd = proceeds_basis_usd_covered - cost_to_cover_usd 

        mock_rate_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        rate = mock_rate_provider.one_foreign_unit_in_eur

        expected_outcome = ScenarioExpectedOutput(
            test_description="SOY_V_002: SOY Short Fallback (Hist Insufficient), Cover Partial. Proceeds from SOY Report. USD.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=cover_date_str,
                    quantity_realized=Decimal("15"), # Absolute quantity
                    total_cost_basis_eur=(cost_to_cover_usd * rate), # CHANGED
                    total_realization_value_eur=(proceeds_basis_usd_covered * rate), 
                    gross_gain_loss_eur=(gain_usd * rate), 
                    acquisition_date=f"{HISTORICAL_YEAR}-12-31", 
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(cover_date_obj - date(HISTORICAL_YEAR, 12, 31)).days
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
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # --- EOY Tests from original file / spec ---
    # Corresponds to EOY_C_001 from spec (already present as test_consistent_eoy_buy_sell_partial_eur)
    def test_eoy_c_001_consistent_eoy_buy_sell_partial_eur(self, mock_config_paths):
        asset_e_symbol = "ASSET.E.EUR" # Renaming to match EOY_C_001 for clarity
        asset_e_isin = "TESTISINEOYCEUR" # Original was TESTISINEOYCEUR
        asset_e_conid = "CONE01EOYC" # Original was CONE01EOYC
        
        # Dates for holding period
        buy_date_str = f"{DEFAULT_TAX_YEAR}-02-10"
        buy_date_obj = date(DEFAULT_TAX_YEAR, 2, 10)
        sell_date_str = f"{DEFAULT_TAX_YEAR}-08-20"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 8, 20)

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_e_symbol, "Asset E EUR", asset_e_isin,
             None, None, None, buy_date_str, Decimal("20"), Decimal("10.00"), COMMISSION_EUR, "EUR",
             "BUY", "T_CURR_E001", None, None, asset_e_conid, None, Decimal("1"), "O"],
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_e_symbol, "Asset E EUR", asset_e_isin,
             None, None, None, sell_date_str, Decimal("-5"), Decimal("12.00"), COMMISSION_EUR, "EUR",
             "SELL", "T_CURR_E002", None, None, asset_e_conid, None, Decimal("1"), "C"],
        ]
        positions_start_data = []
        
        # EOY_RPT(15). Cost per share from buy: (20*10+1)/20 = 10.05. Remaining 15 shares cost basis: 15 * 10.05 = 150.75
        positions_end_data = [ 
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_e_symbol, "Asset E EUR", asset_e_isin,
             Decimal("15"), Decimal("180"), Decimal("12.00"), Decimal("150.75"), # 15 * 12 = 180 value
             None, asset_e_conid, None, Decimal("1")]
        ]
        
        cost_per_share_eur = (Decimal("20") * Decimal("10.00") + COMMISSION_EUR.copy_abs()) / Decimal("20") 
        cost_basis_eur = cost_per_share_eur * Decimal("5") 
        proceeds_eur = (Decimal("5") * Decimal("12.00")) - COMMISSION_EUR.copy_abs() 
        gain_eur = proceeds_eur - cost_basis_eur # 59 - 50.25 = 8.75

        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_C_001: Consistent EOY: SOY Empty -> Buy -> Sell Partial -> EOY matches.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_e_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=cost_basis_eur, # CHANGED (50.25)
                    total_realization_value_eur=proceeds_eur, # 59.00
                    gross_gain_loss_eur=gain_eur, # 8.75
                    acquisition_date=buy_date_str,
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - buy_date_obj).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_e_isin}", eoy_quantity=Decimal("15"))
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

    # Corresponds to EOY_M_001 from spec (already present as test_eoy_mismatch_calculated_greater_than_reported_eur)
    def test_eoy_m_001_mismatch_calc_gt_report_eur(self, mock_config_paths):
        asset_f_symbol = "ASSET.F.EUR" 
        asset_f_isin = "TESTISINEOYMFEUR" 
        asset_f_conid = "CONF01EOYM"

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_f_symbol, "Asset F EUR", asset_f_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-04-01", Decimal("20"), Decimal("10.00"), COMMISSION_EUR, "EUR",
             "BUY", "T_CURR_F001", None, None, asset_f_conid, None, Decimal("1"), "O"],
        ]
        positions_start_data = [] 
        positions_end_data = [ # EOY_RPT(10)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_f_symbol, "Asset F EUR", asset_f_isin,
             Decimal("10"), Decimal("100"), Decimal("10.00"), Decimal("100.50"), # Qty 10, cost for 10: (10*10)+0.5 = 100.5 for some reason
             None, asset_f_conid, None, Decimal("1")]
        ]

        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_M_001: Mismatch: Calculated EOY (20) > EOY Report Qty (10).",
            expected_rgls=[], # No sales
            expected_eoy_states=[ 
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_f_isin}", eoy_quantity=Decimal("10")) 
            ],
            expected_eoy_mismatch_error_count=1 
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to EOY_M_002 from spec (already present as test_eoy_mismatch_calculated_less_than_reported_eur)
    def test_eoy_m_002_mismatch_calc_lt_report_eur(self, mock_config_paths):
        asset_g_symbol = "ASSET.G.EUR" 
        asset_g_isin = "TESTISINEOYMGEUR"
        asset_g_conid = "CONG01EOYM"

        trades_data = [ # BL (5@10 EUR, c1)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_g_symbol, "Asset G EUR", asset_g_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-03-01", Decimal("5"), Decimal("10.00"), COMMISSION_EUR, "EUR",
             "BUY", "T_CURR_G001", None, None, asset_g_conid, None, Decimal("1"), "O"],
        ]
        positions_start_data = []
        positions_end_data = [ # EOY_RPT(10)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_g_symbol, "Asset G EUR", asset_g_isin,
             Decimal("10"), Decimal("100"), Decimal("10.00"), Decimal("100.50"), # Qty 10
             None, asset_g_conid, None, Decimal("1")]
        ]
        
        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_M_002: Mismatch: Calculated EOY (5) < EOY Report Qty (10).",
            expected_rgls=[], # No sales
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_g_isin}", eoy_quantity=Decimal("10"))
            ],
            expected_eoy_mismatch_error_count=1 
        )

        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to EOY_M_003 from spec (already present as test_eoy_mismatch_calculated_nonzero_asset_missing_in_eoy_report_eur)
    def test_eoy_m_003_mismatch_calc_nonzero_report_missing_eur(self, mock_config_paths):
        asset_h_symbol = "ASSET.H.EUR" 
        asset_h_isin = "TESTISINEOYMHEUR" 
        asset_h_conid = "CONH01EOYM"

        trades_data = [ # BL (10@10 EUR, c1)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_h_symbol, "Asset H EUR", asset_h_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-05-01", Decimal("10"), Decimal("10.00"), COMMISSION_EUR, "EUR",
             "BUY", "T_CURR_H001", None, None, asset_h_conid, None, Decimal("1"), "O"],
        ]
        positions_start_data = []
        positions_end_data = [] # Asset H missing, implies Qty 0

        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_M_003: Mismatch: Calculated EOY (10) != 0, Asset Missing in EOY Report (implies 0).",
            expected_rgls=[],
            expected_eoy_states=[ 
                 ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_h_isin}", eoy_quantity=Decimal("0"))
            ],
            expected_eoy_mismatch_error_count=1 
        )

        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # --- New EOY tests based on spec Group 3 ---

    # Corresponds to EOY_C_002
    def test_eoy_c_002_consistent_soy_present_sell_partial_eur(self, mock_config_paths):
        asset_symbol = "ASSET.EOYC002.EUR"
        asset_isin = "TESTISINEOYC002EUR"
        asset_conid = "CONEOYC002"
        
        sell_date_str = f"{DEFAULT_TAX_YEAR}-08-20"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 8, 20)
        soy_acq_date_str = f"{HISTORICAL_YEAR}-12-31"
        soy_acq_date_obj = date(HISTORICAL_YEAR, 12, 31)

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYC002 EUR", asset_isin,
             None, None, None, sell_date_str, Decimal("-5"), Decimal("12.00"), COMMISSION_EUR, "EUR",
             "SELL", "T_EOYC002_S", None, None, asset_conid, None, Decimal("1"), "C"],
        ]
        positions_start_data = [ # SOY_RPT(20, 200 EUR)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYC002 EUR", asset_isin,
             Decimal("20"), Decimal("240"), Decimal("12.00"), Decimal("200.00"), # Val, MarkPx for illustration
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [ # EOY_RPT(15)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYC002 EUR", asset_isin,
             Decimal("15"), Decimal("180"), Decimal("12.00"), Decimal("150.00"), # 15 * 10 (cost per share)
             None, asset_conid, None, Decimal("1")]
        ]
        
        # Cost from SOY: 200 EUR for 20 shares -> 10 EUR/share
        # Sell 5 shares: Cost = 5 * 10 = 50 EUR
        # Proceeds: (5 * 12) - 1 (commission) = 59 EUR
        # Gain: 59 - 50 = 9 EUR
        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_C_002: Consistent EOY: SOY Present -> Sell Partial -> EOY matches.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("5"),
                    total_cost_basis_eur=Decimal("50.00"), # CHANGED
                    total_realization_value_eur=Decimal("59.00"),
                    gross_gain_loss_eur=Decimal("9.00"),
                    acquisition_date=soy_acq_date_str,
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - soy_acq_date_obj).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("15"))
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

    # Corresponds to EOY_C_003
    def test_eoy_c_003_consistent_calc_zero_report_missing_eur(self, mock_config_paths):
        asset_symbol = "ASSET.EOYC003.EUR"
        asset_isin = "TESTISINEOYC003EUR"
        asset_conid = "CONEOYC003"

        sell_date_str = f"{DEFAULT_TAX_YEAR}-09-05"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 9, 5)
        soy_acq_date_str = f"{HISTORICAL_YEAR}-12-31"
        soy_acq_date_obj = date(HISTORICAL_YEAR, 12, 31)

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYC003 EUR", asset_isin,
             None, None, None, sell_date_str, Decimal("-10"), Decimal("12.00"), COMMISSION_EUR, "EUR",
             "SELL", "T_EOYC003_S", None, None, asset_conid, None, Decimal("1"), "C"],
        ]
        positions_start_data = [ # SOY_RPT(10, 100 EUR)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYC003 EUR", asset_isin,
             Decimal("10"), Decimal("120"), Decimal("12.00"), Decimal("100.00"),
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [] # Asset missing in EOY report

        # Cost from SOY: 100 EUR for 10 shares -> 10 EUR/share
        # Sell 10 shares: Cost = 10 * 10 = 100 EUR
        # Proceeds: (10 * 12) - 1 (commission) = 119 EUR
        # Gain: 119 - 100 = 19 EUR
        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_C_003: Consistent EOY: Calculated 0, Asset Missing in EOY Report.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("100.00"), # CHANGED
                    total_realization_value_eur=Decimal("119.00"),
                    gross_gain_loss_eur=Decimal("19.00"),
                    acquisition_date=soy_acq_date_str,
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - soy_acq_date_obj).days
                )
            ],
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

    # Corresponds to EOY_M_004
    def test_eoy_m_004_mismatch_calc_zero_report_nonzero_eur(self, mock_config_paths):
        asset_symbol = "ASSET.EOYM004.EUR"
        asset_isin = "TESTISINEOYM004EUR"
        asset_conid = "CONEOYM004"

        sell_date_str = f"{DEFAULT_TAX_YEAR}-10-15"
        sell_date_obj = date(DEFAULT_TAX_YEAR, 10, 15)
        soy_acq_date_str = f"{HISTORICAL_YEAR}-12-31"
        soy_acq_date_obj = date(HISTORICAL_YEAR, 12, 31)

        trades_data = [
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYM004 EUR", asset_isin,
             None, None, None, sell_date_str, Decimal("-10"), Decimal("12.00"), COMMISSION_EUR, "EUR",
             "SELL", "T_EOYM004_S", None, None, asset_conid, None, Decimal("1"), "C"],
        ]
        positions_start_data = [ # SOY_RPT(10, 100 EUR)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYM004 EUR", asset_isin,
             Decimal("10"), Decimal("120"), Decimal("12.00"), Decimal("100.00"),
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [ # EOY_RPT(5)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYM004 EUR", asset_isin,
             Decimal("5"), Decimal("60"), Decimal("12.00"), Decimal("50.00"), # Qty 5, cost for 5: 5*10
             None, asset_conid, None, Decimal("1")]
        ]
        
        # Gain calc same as EOY_C_003: +19 EUR
        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_M_004: Mismatch: Calculated EOY 0, Asset Present in EOY Report with Non-Zero Qty.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=sell_date_str,
                    quantity_realized=Decimal("10"),
                    total_cost_basis_eur=Decimal("100.00"), # CHANGED
                    total_realization_value_eur=Decimal("119.00"),
                    gross_gain_loss_eur=Decimal("19.00"),
                    acquisition_date=soy_acq_date_str,
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.LONG_POSITION_SALE.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(sell_date_obj - soy_acq_date_obj).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("5"))
            ],
            expected_eoy_mismatch_error_count=1
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

    # Corresponds to EOY_S_001
    def test_eoy_s_001_consistent_eoy_short_eur(self, mock_config_paths):
        asset_symbol = "ASSET.EOYS001.EUR"
        asset_isin = "TESTISINEOYS001EUR"
        asset_conid = "CONEOYS001"

        cover_date_str = f"{DEFAULT_TAX_YEAR}-07-10"
        cover_date_obj = date(DEFAULT_TAX_YEAR, 7, 10)
        soy_short_open_date_str = f"{HISTORICAL_YEAR}-12-31"
        soy_short_open_date_obj = date(HISTORICAL_YEAR, 12, 31)

        trades_data = [ # BSC (5@90 EUR)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYS001 EUR", asset_isin,
             None, None, None, cover_date_str, Decimal("5"), Decimal("90.00"), COMMISSION_EUR, "EUR",
             "BUY", "T_EOYS001_BSC", None, None, asset_conid, None, Decimal("1"), "C"],
        ]
        positions_start_data = [ # SOY_RPT(-10, 1000 EUR proceeds)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYS001 EUR", asset_isin,
             Decimal("-10"), Decimal("-900"), Decimal("90.00"), Decimal("1000.00"), # Val, MarkPx for illustration
             None, asset_conid, None, Decimal("1")]
        ]
        positions_end_data = [ # EOY_RPT(-5)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYS001 EUR", asset_isin,
             Decimal("-5"), Decimal("-450"), Decimal("90.00"), Decimal("500.00"), # -5 qty, remaining proceeds basis 5*100
             None, asset_conid, None, Decimal("1")]
        ]
        
        # Proceeds basis from SOY: 1000 EUR for 10 shares -> 100 EUR/share
        # Cover 5 shares: Proceeds basis = 5 * 100 = 500 EUR
        # Cost to cover: (5 * 90) + 1 (commission) = 451 EUR
        # Gain: 500 - 451 = 49 EUR
        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_S_001: Consistent EOY Short Position.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=cover_date_str,
                    quantity_realized=Decimal("5"), # Absolute quantity
                    total_cost_basis_eur=Decimal("451.00"), # CHANGED: Cost to cover
                    total_realization_value_eur=Decimal("500.00"), # Proceeds basis
                    gross_gain_loss_eur=Decimal("49.00"),
                    acquisition_date=soy_short_open_date_str, # Date of initial short
                    asset_category_at_realization=AssetCategory.STOCK.name,
                    realization_type=RealizationType.SHORT_POSITION_COVER.name, # CHANGED
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name,
                    holding_period_days=(cover_date_obj - soy_short_open_date_obj).days
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

    # Corresponds to EOY_SM_001
    def test_eoy_sm_001_mismatch_eoy_short_calc_gt_report_eur(self, mock_config_paths):
        asset_symbol = "ASSET.EOYSM001.EUR"
        asset_isin = "TESTISINEOYSM001EUR"
        asset_conid = "CONEOYSM001"

        trades_data = [ # SSO(10@100 EUR)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYSM001 EUR", asset_isin,
             None, None, None, f"{DEFAULT_TAX_YEAR}-03-15", Decimal("-10"), Decimal("100.00"), COMMISSION_EUR, "EUR",
             "SELL", "T_EOYSM001_SSO", None, None, asset_conid, None, Decimal("1"), "O"],
        ]
        positions_start_data = [] # SOY Empty
        positions_end_data = [ # EOY_RPT(-5)
            [ACCOUNT_ID, "EUR", "STK", "COMMON", asset_symbol, "Asset EOYSM001 EUR", asset_isin,
             Decimal("-5"), Decimal("-500"), Decimal("100.00"), Decimal("500.00"), # Qty -5. Proceeds basis for -5: (5*100)-0.5*comm = 499.5 (approx)
             None, asset_conid, None, Decimal("1")]
        ]
        
        # Calculated EOY: -10. Reported EOY: -5. Mismatch. No RGLs.
        expected_outcome = ScenarioExpectedOutput(
            test_description="EOY_SM_001: Mismatch EOY Short: Calc -10, Report -5.",
            expected_rgls=[],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("-5"))
            ],
            expected_eoy_mismatch_error_count=1
        )
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_processing_output, expected_outcome)

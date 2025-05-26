# tests/fifo_scenarios/test_multi_year_scenarios.py
import pytest
from decimal import Decimal
from datetime import date, timedelta

from tests.fifo_scenarios.test_case_base import FifoTestCaseBase
from tests.results.test_result_defs import ScenarioExpectedOutput, ExpectedRealizedGainLoss, ExpectedAssetEoyState
from tests.helpers.mock_providers import MockECBExchangeRateProvider
from src.domain.enums import AssetCategory, TaxReportingCategory, RealizationType

# Constants for tests
ACCOUNT_ID = "U_TEST_MULTIYEAR"
DEFAULT_TAX_YEAR = 2023
TY_MINUS_1 = DEFAULT_TAX_YEAR - 1
TY_MINUS_2 = DEFAULT_TAX_YEAR - 2
TY_MINUS_3 = DEFAULT_TAX_YEAR - 3

COMMISSION_USD = Decimal("-1.00") # Commission is a cost, so negative when received from broker data
ABS_COMMISSION_USD = COMMISSION_USD.copy_abs()
FX_RATE_USD_EUR = Decimal("2.0") # 1 USD = 2 EUR

USD_CURRENCY = "USD"
EUR_CURRENCY = "EUR"
ASSET_CATEGORY_STK = AssetCategory.STOCK.name
TRC_AKTIEN_GEWINN = TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name
# Updated RealizationType names
RT_SALE_LONG = RealizationType.LONG_POSITION_SALE.name
RT_COVER_SHORT = RealizationType.SHORT_POSITION_COVER.name


class TestMultiYearScenarios(FifoTestCaseBase):
    """
    Implements Test Group 4: Multi-Year Data Handling from test_spec_fifo.md.
    """

    # Corresponds to MYH_L_001
    def test_myh_l_001_deep_history_long_buys_sold_in_ty(self, mock_config_paths):
        asset_symbol = "ASSET.MYHL001.USD"
        asset_isin = "TESTISINMYHL001USD"
        asset_conid = "CONMYHL001"

        # Trade Dates
        date_buy_ty2_str = f"{TY_MINUS_2}-03-10"
        date_buy_ty1_str = f"{TY_MINUS_1}-06-15"
        date_sell_ty_str = f"{DEFAULT_TAX_YEAR}-02-20"

        date_buy_ty2_obj = date(TY_MINUS_2, 3, 10)
        date_buy_ty1_obj = date(TY_MINUS_1, 6, 15)
        date_sell_ty_obj = date(DEFAULT_TAX_YEAR, 2, 20)

        trades_data = [
            # TY-2: BL(10 @ 80 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHL001", asset_isin,
             None, None, None, date_buy_ty2_str, Decimal("10"), Decimal("80.00"), COMMISSION_USD, USD_CURRENCY,
             "BUY", "T_MYHL001_BUY_TY2", None, None, asset_conid, None, Decimal("1"), "O"],
            # TY-1: BL(10 @ 90 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHL001", asset_isin,
             None, None, None, date_buy_ty1_str, Decimal("10"), Decimal("90.00"), COMMISSION_USD, USD_CURRENCY,
             "BUY", "T_MYHL001_BUY_TY1", None, None, asset_conid, None, Decimal("1"), "O"],
            # TY: SL(15 @ 100 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHL001", asset_isin,
             None, None, None, date_sell_ty_str, Decimal("-15"), Decimal("100.00"), COMMISSION_USD, USD_CURRENCY,
             "SELL", "T_MYHL001_SELL_TY", None, None, asset_conid, None, Decimal("1"), "C"],
        ]

        # SOY_RPT(20, ignored)
        positions_start_data = [
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHL001", asset_isin,
             Decimal("20"), Decimal("2000.00"), Decimal("100.00"), Decimal("1702.00"), # Qty, Val, MarkPx, CostBasis (ignored)
             None, asset_conid, None, Decimal("1")]
        ]
        # EOY State: 5 shares remaining (cost basis from TY-1 buy)
        # Cost of remaining 5 shares: ( (10*90+1)/10 ) * 5 = 90.1 * 5 = 450.5 USD
        positions_end_data = [
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHL001", asset_isin,
             Decimal("5"), Decimal("500.00"), Decimal("100.00"), Decimal("450.50"), # Qty, Val, MarkPx, CostBasis
             None, asset_conid, None, Decimal("1")]
        ]

        # RGL 1 (from TY-2 lot)
        cost_lot1_usd_total = (Decimal("10") * Decimal("80.00")) + ABS_COMMISSION_USD  # 801 USD
        proceeds_total_trade_usd = (Decimal("15") * Decimal("100.00")) - ABS_COMMISSION_USD # 1499 USD
        
        qty_rgl1 = Decimal("10")
        proceeds_rgl1_usd = proceeds_total_trade_usd * qty_rgl1 / Decimal("15") # 1499 * 10/15
        cost_rgl1_usd = cost_lot1_usd_total # All of lot 1 sold
        gain_rgl1_usd = proceeds_rgl1_usd - cost_rgl1_usd

        # RGL 2 (from TY-1 lot)
        cost_lot2_usd_total = (Decimal("10") * Decimal("90.00")) + ABS_COMMISSION_USD # 901 USD
        qty_bought_lot2 = Decimal("10")
        
        qty_rgl2 = Decimal("5")
        proceeds_rgl2_usd = proceeds_total_trade_usd * qty_rgl2 / Decimal("15") # 1499 * 5/15
        cost_rgl2_usd = cost_lot2_usd_total * qty_rgl2 / qty_bought_lot2 # 901 * 5/10
        gain_rgl2_usd = proceeds_rgl2_usd - cost_rgl2_usd

        expected_outcome = ScenarioExpectedOutput(
            test_description="MYH_L_001: Deep History Long: Buys over TY-2, TY-1, Sold in TY.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=date_sell_ty_str,
                    quantity_realized=qty_rgl1,
                    total_cost_basis_eur=cost_rgl1_usd * FX_RATE_USD_EUR, 
                    total_realization_value_eur=proceeds_rgl1_usd * FX_RATE_USD_EUR, 
                    gross_gain_loss_eur=gain_rgl1_usd * FX_RATE_USD_EUR, # Expected: 396.67
                    acquisition_date=date_buy_ty2_str,
                    asset_category_at_realization=ASSET_CATEGORY_STK,
                    realization_type=RT_SALE_LONG,
                    tax_reporting_category=TRC_AKTIEN_GEWINN,
                    holding_period_days=(date_sell_ty_obj - date_buy_ty2_obj).days
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=date_sell_ty_str,
                    quantity_realized=qty_rgl2,
                    total_cost_basis_eur=cost_rgl2_usd * FX_RATE_USD_EUR, 
                    total_realization_value_eur=proceeds_rgl2_usd * FX_RATE_USD_EUR, 
                    gross_gain_loss_eur=gain_rgl2_usd * FX_RATE_USD_EUR, # Expected: 98.33
                    acquisition_date=date_buy_ty1_str,
                    asset_category_at_realization=ASSET_CATEGORY_STK,
                    realization_type=RT_SALE_LONG,
                    tax_reporting_category=TRC_AKTIEN_GEWINN,
                    holding_period_days=(date_sell_ty_obj - date_buy_ty1_obj).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("5"))
            ],
            expected_eoy_mismatch_error_count=0
        )

        actual_results = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(foreign_to_eur_init_value=FX_RATE_USD_EUR),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_results, expected_outcome)

    # Corresponds to MYH_S_001
    def test_myh_s_001_deep_history_short_ssos_covered_in_ty(self, mock_config_paths):
        asset_symbol = "ASSET.MYHS001.USD"
        asset_isin = "TESTISINMYHS001USD"
        asset_conid = "CONMYHS001"

        date_sso_ty2_str = f"{TY_MINUS_2}-04-05"
        date_sso_ty1_str = f"{TY_MINUS_1}-07-10"
        date_bsc_ty_str = f"{DEFAULT_TAX_YEAR}-03-25"

        date_sso_ty2_obj = date(TY_MINUS_2, 4, 5)
        date_sso_ty1_obj = date(TY_MINUS_1, 7, 10)
        date_bsc_ty_obj = date(DEFAULT_TAX_YEAR, 3, 25)
        
        trades_data = [
            # TY-2: SSO(10 @ 120 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHS001", asset_isin,
             None, None, None, date_sso_ty2_str, Decimal("-10"), Decimal("120.00"), COMMISSION_USD, USD_CURRENCY,
             "SELL", "T_MYHS001_SSO_TY2", None, None, asset_conid, None, Decimal("1"), "O"],
            # TY-1: SSO(10 @ 110 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHS001", asset_isin,
             None, None, None, date_sso_ty1_str, Decimal("-10"), Decimal("110.00"), COMMISSION_USD, USD_CURRENCY,
             "SELL", "T_MYHS001_SSO_TY1", None, None, asset_conid, None, Decimal("1"), "O"],
            # TY: BSC(15 @ 100 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHS001", asset_isin,
             None, None, None, date_bsc_ty_str, Decimal("15"), Decimal("100.00"), COMMISSION_USD, USD_CURRENCY,
             "BUY", "T_MYHS001_BSC_TY", None, None, asset_conid, None, Decimal("1"), "C"],
        ]

        # SOY_RPT(-20, ignored)
        positions_start_data = [
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHS001", asset_isin,
             Decimal("-20"), Decimal("-2000.00"), Decimal("100.00"), Decimal("2298.00"), # Qty, Val, MarkPx, ProceedsBasis (ignored)
             None, asset_conid, None, Decimal("1")]
        ]
        # EOY State: -5 shares remaining (proceeds basis from TY-1 SSO)
        # Proceeds of remaining 5 shares: ( (10*110-1)/10 ) * 5 = 109.9 * 5 = 549.5 USD
        positions_end_data = [
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHS001", asset_isin,
             Decimal("-5"), Decimal("-500.00"), Decimal("100.00"), Decimal("549.50"), # Qty, Val, MarkPx, ProceedsBasis
             None, asset_conid, None, Decimal("1")]
        ]

        # RGL 1 (covering TY-2 lot)
        proceeds_lot1_usd_total = (Decimal("10") * Decimal("120.00")) - ABS_COMMISSION_USD # 1199 USD
        cost_total_cover_trade_usd = (Decimal("15") * Decimal("100.00")) + ABS_COMMISSION_USD # 1501 USD
        
        qty_rgl1 = Decimal("10")
        cost_rgl1_usd = cost_total_cover_trade_usd * qty_rgl1 / Decimal("15") # 1501 * 10/15
        proceeds_rgl1_usd = proceeds_lot1_usd_total # All of lot 1 covered
        gain_rgl1_usd = proceeds_rgl1_usd - cost_rgl1_usd # For shorts, Gain = Proceeds - Cost

        # RGL 2 (covering TY-1 lot)
        proceeds_lot2_usd_total = (Decimal("10") * Decimal("110.00")) - ABS_COMMISSION_USD # 1099 USD
        qty_opened_lot2 = Decimal("10")
        
        qty_rgl2 = Decimal("5")
        cost_rgl2_usd = cost_total_cover_trade_usd * qty_rgl2 / Decimal("15") # 1501 * 5/15
        proceeds_rgl2_usd = proceeds_lot2_usd_total * qty_rgl2 / qty_opened_lot2 # 1099 * 5/10
        gain_rgl2_usd = proceeds_rgl2_usd - cost_rgl2_usd

        expected_outcome = ScenarioExpectedOutput(
            test_description="MYH_S_001: Deep History Short: SSOs over TY-2, TY-1, Covered in TY.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=date_bsc_ty_str,
                    quantity_realized=qty_rgl1, # Absolute quantity
                    total_cost_basis_eur=cost_rgl1_usd * FX_RATE_USD_EUR, # Cost to cover
                    total_realization_value_eur=proceeds_rgl1_usd * FX_RATE_USD_EUR, # Proceeds from original short
                    gross_gain_loss_eur=gain_rgl1_usd * FX_RATE_USD_EUR, # Expected: 396.67
                    acquisition_date=date_sso_ty2_str, # Date of original short sale
                    asset_category_at_realization=ASSET_CATEGORY_STK,
                    realization_type=RT_COVER_SHORT,
                    tax_reporting_category=TRC_AKTIEN_GEWINN,
                    holding_period_days=(date_bsc_ty_obj - date_sso_ty2_obj).days
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=date_bsc_ty_str,
                    quantity_realized=qty_rgl2,
                    total_cost_basis_eur=cost_rgl2_usd * FX_RATE_USD_EUR, 
                    total_realization_value_eur=proceeds_rgl2_usd * FX_RATE_USD_EUR, 
                    gross_gain_loss_eur=gain_rgl2_usd * FX_RATE_USD_EUR, # Expected: 98.33
                    acquisition_date=date_sso_ty1_str,
                    asset_category_at_realization=ASSET_CATEGORY_STK,
                    realization_type=RT_COVER_SHORT,
                    tax_reporting_category=TRC_AKTIEN_GEWINN,
                    holding_period_days=(date_bsc_ty_obj - date_sso_ty1_obj).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("-5"))
            ],
            expected_eoy_mismatch_error_count=0
        )

        actual_results = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(foreign_to_eur_init_value=FX_RATE_USD_EUR),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_results, expected_outcome)

    # Corresponds to MYH_P_001
    def test_myh_p_001_deep_history_partial_sales_across_years(self, mock_config_paths):
        asset_symbol = "ASSET.MYHP001.USD"
        asset_isin = "TESTISINMYHP001USD"
        asset_conid = "CONMYHP001"

        date_buy_ty3_str = f"{TY_MINUS_3}-02-10"
        date_sell_ty2_str = f"{TY_MINUS_2}-05-15" # Sells from TY-3 buy
        date_buy_ty1_str = f"{TY_MINUS_1}-08-20"
        date_sell_ty_str = f"{DEFAULT_TAX_YEAR}-04-25" # Sells from TY-3 (rem) and TY-1 lots

        date_buy_ty3_obj = date(TY_MINUS_3, 2, 10)
        # date_sell_ty2_obj = date(TY_MINUS_2, 5, 15) # Not needed for RGL in TY
        date_buy_ty1_obj = date(TY_MINUS_1, 8, 20)
        date_sell_ty_obj = date(DEFAULT_TAX_YEAR, 4, 25)

        trades_data = [
            # TY-3: BL(20 @ 70 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHP001", asset_isin,
             None, None, None, date_buy_ty3_str, Decimal("20"), Decimal("70.00"), COMMISSION_USD, USD_CURRENCY,
             "BUY", "T_MYHP001_BUY_TY3", None, None, asset_conid, None, Decimal("1"), "O"],
            # TY-2: SL(5 @ 80 USD), Comm -1 (from TY-3 lot)
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHP001", asset_isin,
             None, None, None, date_sell_ty2_str, Decimal("-5"), Decimal("80.00"), COMMISSION_USD, USD_CURRENCY,
             "SELL", "T_MYHP001_SELL_TY2", None, None, asset_conid, None, Decimal("1"), "C"],
            # TY-1: BL(10 @ 90 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHP001", asset_isin,
             None, None, None, date_buy_ty1_str, Decimal("10"), Decimal("90.00"), COMMISSION_USD, USD_CURRENCY,
             "BUY", "T_MYHP001_BUY_TY1", None, None, asset_conid, None, Decimal("1"), "O"],
            # TY: SL(20 @ 100 USD), Comm -1
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHP001", asset_isin,
             None, None, None, date_sell_ty_str, Decimal("-20"), Decimal("100.00"), COMMISSION_USD, USD_CURRENCY,
             "SELL", "T_MYHP001_SELL_TY", None, None, asset_conid, None, Decimal("1"), "C"],
        ]

        # SOY for TY: Qty 25 (15 from TY-3 buy, 10 from TY-1 buy)
        # Cost TY-3 buy: 20*70+1=1401. 5 sold in TY-2. Remaining 15 cost: 1401 * 15/20 = 1050.75
        # Cost TY-1 buy: 10*90+1=901
        # Total SOY CostBasisMoney for calculation: 1050.75 + 901 = 1951.75
        positions_start_data = [
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHP001", asset_isin,
             Decimal("25"), Decimal("2500.00"), Decimal("100.00"), Decimal("1951.75"), # Qty, Val, MarkPx, CostBasis(ignored)
             None, asset_conid, None, Decimal("1")]
        ]
        # EOY State: 5 shares remaining (from TY-1 buy)
        # Cost of remaining 5 from TY-1 lot: ((10*90+1)/10) * 5 = 90.1 * 5 = 450.5
        positions_end_data = [
            [ACCOUNT_ID, USD_CURRENCY, "STK", "COMMON", asset_symbol, "Desc MYHP001", asset_isin,
             Decimal("5"), Decimal("500.00"), Decimal("100.00"), Decimal("450.50"), # Qty, Val, MarkPx, CostBasis
             None, asset_conid, None, Decimal("1")]
        ]

        # Lot A (TY-3): BL(20@70), cost (20*70)+1 = 1401. Qty_bought_A = 20.
        #   TY-2 Sale: SL(5@80).
        #   Remaining Lot A for TY: 15 shares. Cost_rem_A_usd = 1401 * 15/20 = 1050.75
        cost_rem_A_usd = Decimal("1050.75")
        # Lot B (TY-1): BL(10@90), cost (10*90)+1 = 901. 
        Qty_bought_B = Decimal("10")
        cost_lotB_usd_total = (Decimal("10") * Decimal("90.00")) + ABS_COMMISSION_USD # 901

        # TY Sale: SL(20@100), Comm -1.
        proceeds_total_TY_sale_USD = (Decimal("20") * Decimal("100.00")) - ABS_COMMISSION_USD # 1999.
        
        # RGL 1 (from remaining Lot A - original acq TY-3)
        qty_rgl1 = Decimal("15") # All remaining from Lot A
        cost_rgl1_usd = cost_rem_A_usd 
        proceeds_rgl1_usd = proceeds_total_TY_sale_USD * qty_rgl1 / Decimal("20") # 1999 * 15/20
        gain_rgl1_usd = proceeds_rgl1_usd - cost_rgl1_usd

        # RGL 2 (from Lot B - original acq TY-1)
        qty_rgl2 = Decimal("5") # 20 total sold - 15 from Lot A = 5 from Lot B
        cost_rgl2_usd = cost_lotB_usd_total * qty_rgl2 / Qty_bought_B # 901 * 5/10
        proceeds_rgl2_usd = proceeds_total_TY_sale_USD * qty_rgl2 / Decimal("20") # 1999 * 5/20
        gain_rgl2_usd = proceeds_rgl2_usd - cost_rgl2_usd
        
        expected_outcome = ScenarioExpectedOutput(
            test_description="MYH_P_001: Deep History with Partial Sales Across Years.",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=date_sell_ty_str,
                    quantity_realized=qty_rgl1,
                    total_cost_basis_eur=cost_rgl1_usd * FX_RATE_USD_EUR, 
                    total_realization_value_eur=proceeds_rgl1_usd * FX_RATE_USD_EUR, 
                    gross_gain_loss_eur=gain_rgl1_usd * FX_RATE_USD_EUR, # Expected: 897.00
                    acquisition_date=date_buy_ty3_str,
                    asset_category_at_realization=ASSET_CATEGORY_STK,
                    realization_type=RT_SALE_LONG,
                    tax_reporting_category=TRC_AKTIEN_GEWINN,
                    holding_period_days=(date_sell_ty_obj - date_buy_ty3_obj).days
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{asset_isin}",
                    realization_date=date_sell_ty_str,
                    quantity_realized=qty_rgl2,
                    total_cost_basis_eur=cost_rgl2_usd * FX_RATE_USD_EUR, 
                    total_realization_value_eur=proceeds_rgl2_usd * FX_RATE_USD_EUR, 
                    gross_gain_loss_eur=gain_rgl2_usd * FX_RATE_USD_EUR, # Expected: 98.50
                    acquisition_date=date_buy_ty1_str,
                    asset_category_at_realization=ASSET_CATEGORY_STK,
                    realization_type=RT_SALE_LONG,
                    tax_reporting_category=TRC_AKTIEN_GEWINN,
                    holding_period_days=(date_sell_ty_obj - date_buy_ty1_obj).days
                )
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{asset_isin}", eoy_quantity=Decimal("5"))
            ],
            expected_eoy_mismatch_error_count=0
        )

        actual_results = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            custom_rate_provider=MockECBExchangeRateProvider(foreign_to_eur_init_value=FX_RATE_USD_EUR),
            tax_year=DEFAULT_TAX_YEAR
        )
        self.assert_results(actual_results, expected_outcome)

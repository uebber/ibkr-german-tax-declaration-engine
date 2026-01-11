# tests/test_dividend_handling.py
import pytest
from decimal import Decimal

from tests.support.base import FifoTestCaseBase
from tests.support.expected import ScenarioExpectedOutput, ExpectedRealizedGainLoss, ExpectedAssetEoyState
from tests.support.mock_providers import MockECBExchangeRateProvider
from src.domain.enums import AssetCategory, TaxReportingCategory, RealizationType, FinancialEventType
from src.engine.loss_offsetting import LossOffsettingEngine

ACCOUNT_ID = "U1234567"
DEFAULT_TAX_YEAR = 2024

class TestDividendHandling(FifoTestCaseBase):
    """
    Comprehensive dividend handling test suite covering different dividend scenarios:
    
    1. Tax-free dividend rights: Cost basis adjustment without taxable income
    2. Taxable stock dividends: New FIFO lot creation with tax impact
    """

    def _assert_dividend_income_events(self, processing_output, expected_count, expected_amount=None, tax_year="2024"):
        """
        Helper method to validate dividend income events consistently across tests.
        
        Args:
            processing_output: The processing output to check
            expected_count: Expected number of dividend income events with positive amounts
            expected_amount: Expected total dividend amount (optional)
            tax_year: Tax year to filter events (default: "2024")
        """
        dividend_income_events = [
            event for event in processing_output.processed_income_events
            if hasattr(event, 'event_type') and (
                event.event_type == FinancialEventType.DIVIDEND_CASH or
                event.event_type == FinancialEventType.CORP_STOCK_DIVIDEND
            ) and event.event_date.startswith(tax_year) and 
            hasattr(event, 'gross_amount_eur') and event.gross_amount_eur > 0
        ]
        
        assert len(dividend_income_events) == expected_count, \
            f"Expected {expected_count} dividend income events with positive amounts, but found {len(dividend_income_events)}: " \
            f"{[(e.event_type, e.event_date, e.gross_amount_eur) for e in dividend_income_events]}"
        
        if expected_amount is not None:
            total_dividend_amount = sum(e.gross_amount_eur for e in dividend_income_events)
            assert total_dividend_amount == expected_amount, \
                f"Expected total dividend amount {expected_amount}, but got {total_dividend_amount}"
    
    def _assert_tax_impact(self, processing_output, expected_kap_other_income=None, 
                          expected_kap_foreign_income=None, expected_conceptual_other_income=None):
        """
        Helper method to validate tax impact consistently across tests.
        
        Args:
            processing_output: The processing output to check
            expected_kap_other_income: Expected value for ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
            expected_kap_foreign_income: Expected value for ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT
            expected_conceptual_other_income: Expected value for conceptual_net_other_income
        """
        import src.config as config
        loss_engine = LossOffsettingEngine(
            realized_gains_losses=processing_output.realized_gains_losses,
            vorabpauschale_items=processing_output.vorabpauschale_items,
            current_year_financial_events=processing_output.processed_income_events,
            asset_resolver=processing_output.asset_resolver,
            tax_year=DEFAULT_TAX_YEAR,
            apply_conceptual_derivative_loss_capping=config.APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING
        )
        tax_results = loss_engine.calculate_reporting_figures()
        
        if expected_kap_other_income is not None:
            kap_other_income = tax_results.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE, Decimal("0"))
            assert kap_other_income == expected_kap_other_income, \
                f"Expected kap_other_income {expected_kap_other_income}, but got {kap_other_income}"
        
        if expected_kap_foreign_income is not None:
            kap_foreign_income = tax_results.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT, Decimal("0"))
            assert kap_foreign_income == expected_kap_foreign_income, \
                f"Expected kap_foreign_income {expected_kap_foreign_income}, but got {kap_foreign_income}"
        
        if expected_conceptual_other_income is not None:
            assert tax_results.conceptual_net_other_income == expected_conceptual_other_income, \
                f"Expected conceptual_net_other_income {expected_conceptual_other_income}, but got {tax_results.conceptual_net_other_income}"

    def test_dividend_rights_fifo_adjustment_via_sale_gains(self, mock_config_paths):
        """
        Test Case: Dividend rights handling - verify FIFO adjustment via realized gains from stock sale.
        
        This test verifies:
        1. Tax-free dividend ("Exempt From Withholding") adjusts first FIFO lot cost basis
        2. FIFO adjustment is confirmed by checking realized gains from subsequent stock sale
        3. No impact on kap_other_income_positive in tax year 2024 from the tax-free dividend
        
        Scenario:
        - 2023-05-17: Buy 100 LEG shares at €55 each = €5500 total cost
        - 2023-06-21: Buy 50 LEG shares at €80 each = €4000 total cost  
        - 2024-05-24: Dividend rights issued (100 rights, 1 for 1)
        - 2024-06-26: Rights expire, €245 tax-free dividend paid
        - 2024-07-15: Sell all 150 shares at €85 each = €12750 total proceeds
        
        Expected FIFO calculation:
        - First lot after dividend adjustment: 100 shares, cost €5500 - €245 = €5255 (€52.55 per share)
        - Second lot unchanged: 50 shares, cost €4000 (€80 per share)
        - Total adjusted cost: €5255 + €4000 = €9255
        - Realized gain: €12750 - €9255 = €3495
        """
        leg_symbol = "LEGd"
        leg_isin = "DE000LEG1110"
        leg_divir_symbol = "LEG.DIVIR"
        leg_divir_isin = "DE000LEG1268"
        currency = "EUR"

        # Trades data - LEG stock purchases and sale
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN, 
        #          Strike, Expiry, Put/Call, TradeDate, Quantity, TradePrice, IBCommission, IBCommissionCurrency, 
        #          Buy/Sell, TransactionID, Notes/Codes, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier, Open/CloseIndicator
        trades_data = [
            # First purchase: 100 shares at €55 on 2023-05-17
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin, 
             "", "", "", "20230517", "100", "55", "0", currency, "BUY", "1873530058", "A", "", "121764205", "", "1", "O"],
            
            # Second purchase: 50 shares at €80 on 2023-06-21
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             "", "", "", "20230621", "50", "80", "0", currency, "BUY", "2830028658", "P", "", "121764205", "", "1", "O"],
            
            # Sale: 150 shares at €85 on 2024-07-15 (after dividend to see FIFO adjustment impact)
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             "", "", "", "20240715", "-150", "85", "0", currency, "SELL", "2830028659", "", "", "121764205", "", "1", "C"]
        ]

        # Corporate actions data - dividend rights issuance and expiry
        # Headers: ClientAccountID, Symbol, Description, ISIN, Report Date, Code, Type, ActionID, 
        #          Conid, UnderlyingConid, UnderlyingSymbol, CurrencyPrimary, Amount, Proceeds, Value, Quantity
        corporate_actions_data = [
            # Dividend rights issued (DI) - 100 rights issued 1 for 1
            [ACCOUNT_ID, leg_divir_symbol, 
             f"LEG({leg_isin}) DIVIDEND RIGHTS ISSUE  1 FOR 1 ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})",
             leg_divir_isin, "20240524", "", "DI", "137293437", "705911909", "", "", currency, "0", "0", "0", "100"],
            
            # Dividend rights expire (ED) - 100 rights expire
            [ACCOUNT_ID, leg_divir_symbol,
             f"{leg_divir_symbol}({leg_divir_isin}) EXPIRE DIVIDEND RIGHT ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})",
             leg_divir_isin, "20240626", "", "ED", "139982491", "705911909", "", "", currency, "0", "0", "0", "-100"]
        ]

        # Cash transaction - tax-free dividend payment
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, 
        #          SettleDate, Amount, Type, Conid, UnderlyingConid, ISIN, IssuerCountryCode, TransactionID
        cash_transactions_data = [
            # Tax-free dividend payment on rights expiry - this should reduce cost basis of LEG shares
            # Using real-world description that contains BOTH "EXPIRE DIVIDEND RIGHT" and "Exempt From Withholding"
            [ACCOUNT_ID, currency, "STK", "RIGHT", leg_divir_symbol,  # Use DIVIR symbol as in real data
             f"LEG.DIVIR({leg_divir_isin}) EXPIRE DIVIDEND RIGHT (Exempt From Withholding)",
             "20240626", "245", "Dividends", "705911909", "", leg_divir_isin, "XX", "2841481203"]  # Use DIVIR data
        ]

        # Start positions - LEG shares after trades but before dividend event
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN, 
        #          Quantity, PositionValue, MarkPrice, CostBasisMoney, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
        positions_start_data = [
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             Decimal("150"), Decimal("9500"), Decimal("63.333"), Decimal("9500"),
             "", "121764205", "", Decimal("1")]
        ]

        # End positions - no shares remaining after sale
        positions_end_data = []

        # Expected realized gain calculation:
        # Original cost basis: 100 * €55 + 50 * €80 = €5500 + €4000 = €9500
        # Dividend adjustment: €9500 - €245 = €9255 (first lot reduced by €245)
        # Sale proceeds: 150 * €85 = €12750
        # Expected realized gain: €12750 - €9255 = €3495
        expected_outcome = ScenarioExpectedOutput(
            test_description="LEG Dividend Rights: Verify FIFO adjustment via sale realized gains",
            expected_rgls=[
                # First FIFO lot: 100 shares with dividend-adjusted cost basis
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-07-15",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("5255.00"),  # €5500 - €245 dividend adjustment
                    total_realization_value_eur=Decimal("8500.00"),
                    gross_gain_loss_eur=Decimal("3245.00")
                ),
                # Second FIFO lot: 50 shares with unchanged cost basis
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-07-15",
                    quantity_realized=Decimal("50"),
                    total_cost_basis_eur=Decimal("4000.00"),  # Unchanged
                    total_realization_value_eur=Decimal("4250.00"),
                    gross_gain_loss_eur=Decimal("250.00")
                )
            ],
            expected_eoy_states=[
                # No shares remaining after sale
            ],
            expected_eoy_mismatch_error_count=0
        )

        # Use standard mock rate provider
        mock_rate_provider = MockECBExchangeRateProvider()
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            cash_transactions_data=cash_transactions_data,
            corporate_actions_data=corporate_actions_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        
        # Assert basic FIFO and EOY results
        self.assert_results(actual_processing_output, expected_outcome)
        
        # Verify no dividend income events for tax-free dividend
        self._assert_dividend_income_events(actual_processing_output, expected_count=0)
        
        # Verify tax impact is zero for tax-free dividend
        self._assert_tax_impact(actual_processing_output, 
                               expected_kap_other_income=Decimal("0.00"),
                               expected_conceptual_other_income=Decimal("0.00"))

    def test_dividend_rights_first_fifo_lot_to_zero_second_reduced(self, mock_config_paths):
        """
        Test Case 2: Dividend rights handling where first FIFO lot goes to zero and second lot is also reduced.
        
        This test verifies:
        1. First FIFO lot cost basis reduced to zero by dividend payment
        2. Second FIFO lot cost basis also partially reduced by remaining dividend amount
        3. FIFO adjustment confirmed via realized gains calculation from stock sale
        4. No impact on kap_other_income_positive from tax-free dividend ("Exempt From Withholding")
        5. Expected impact to Anlage KAP other income: €0 (tax-free dividend only adjusts cost basis)
        
        Scenario (based on provided test case data):
        - 2023-05-17: Buy 100 LEG shares at €1 each = €100 total cost (first lot)
        - 2023-06-21: Buy 50 LEG shares at €55 each = €2750 total cost (second lot)  
        - 2024-05-24: Dividend rights issued (100 rights, 1 for 1)
        - 2024-06-26: Rights expire, €245 tax-free dividend paid
        - 2024-11-21: Sell all 150 shares at €85 each = €12750 total proceeds
        
        Expected FIFO calculation:
        - First lot: €100 cost - €100 from dividend = €0 (completely eliminated)
        - Second lot: €2750 cost - €145 remaining dividend = €2605
        - Total adjusted cost: €0 + €2605 = €2605
        - Realized gain: €12750 - €2605 = €10145
        
        Expected tax impact:
        - Anlage KAP other income (kap_other_income_positive): €0 (tax-free dividend)
        - Conceptual other income: €0 (tax-free dividend only reduces cost basis)
        """
        leg_symbol = "LEGd"
        leg_isin = "DE000LEG1110"
        leg_divir_symbol = "LEG.DIVIR"
        leg_divir_isin = "DE000LEG1268"
        currency = "EUR"

        # Trades data - LEG stock purchases and sale
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN, 
        #          Strike, Expiry, Put/Call, TradeDate, Quantity, TradePrice, IBCommission, IBCommissionCurrency, 
        #          Buy/Sell, TransactionID, Notes/Codes, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier, Open/CloseIndicator
        trades_data = [
            # First purchase: 100 shares at €1 on 2023-05-17
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin, 
             "", "", "", "20230517", "100", "1", "0", currency, "BUY", "1873530058", "A", "", "121764205", "", "1", "O"],
            
            # Second purchase: 50 shares at €55 on 2023-06-21
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             "", "", "", "20230621", "50", "55", "0", currency, "BUY", "2830028658", "P", "", "121764205", "", "1", "O"],
            
            # Sale: 150 shares at €85 on 2024-01-21 (from test case data)
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             "", "", "", "20241121", "-150", "85", "0", currency, "SELL", "2830028658", "", "", "121764205", "", "1", "C"]
        ]

        # Corporate actions data - dividend rights issuance and expiry
        # Headers: ClientAccountID, Symbol, Description, ISIN, Report Date, Code, Type, ActionID, 
        #          Conid, UnderlyingConid, UnderlyingSymbol, CurrencyPrimary, Amount, Proceeds, Value, Quantity
        corporate_actions_data = [
            # Dividend rights issued (DI) - 100 rights issued 1 for 1
            [ACCOUNT_ID, leg_divir_symbol, 
             f"LEG({leg_isin}) DIVIDEND RIGHTS ISSUE  1 FOR 1 ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})",
             leg_divir_isin, "20240524", "", "DI", "137293437", "705911909", "", "", currency, "0", "0", "0", "100"],
            
            # Dividend rights expire (ED) - 100 rights expire
            [ACCOUNT_ID, leg_divir_symbol,
             f"{leg_divir_symbol}({leg_divir_isin}) EXPIRE DIVIDEND RIGHT ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})",
             leg_divir_isin, "20240626", "", "ED", "139982491", "705911909", "", "", currency, "0", "0", "0", "-100"]
        ]

        # Cash transaction - tax-free dividend payment
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, 
        #          SettleDate, Amount, Type, Conid, UnderlyingConid, ISIN, IssuerCountryCode, TransactionID
        cash_transactions_data = [
            # Tax-free dividend payment of €245 (from test case data)
            [ACCOUNT_ID, currency, "STK", "RIGHT", leg_divir_symbol,
             f"LEG.DIVIR({leg_divir_isin}) EXPIRE DIVIDEND RIGHT (Exempt From Withholding)",
             "20240626", "245", "Dividends", "705911909", "", leg_divir_isin, "XX", "2841481203"]
        ]

        # Start positions - LEG shares after trades but before dividend event
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN, 
        #          Quantity, PositionValue, MarkPrice, CostBasisMoney, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
        positions_start_data = [
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             Decimal("150"), Decimal("9500"), Decimal("63.333"), Decimal("2850"),  # Total cost: €100 + €2750 = €2850
             "", "121764205", "", Decimal("1")]
        ]

        positions_end_data = []

        # Expected calculation:
        # Original cost: €100 (first lot) + €2750 (second lot) = €2850
        # Dividend reduces first lot by €100 (to zero), then second lot by €145
        # Adjusted costs: €0 (first lot) + €2605 (second lot) = €2605 total
        expected_outcome = ScenarioExpectedOutput(
            test_description="LEG Dividend Rights: First lot to zero, second lot reduced by €245 dividend",
            expected_rgls=[
                # First FIFO lot: 100 shares with cost basis reduced to zero
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-11-21",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("0.00"),  # €100 - €100 = €0
                    total_realization_value_eur=Decimal("8500.00"),
                    gross_gain_loss_eur=Decimal("8500.00")
                ),
                # Second FIFO lot: 50 shares with cost basis reduced by €145
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-11-21",
                    quantity_realized=Decimal("50"),
                    total_cost_basis_eur=Decimal("2605.00"),  # €2750 - €145 = €2605
                    total_realization_value_eur=Decimal("4250.00"),
                    gross_gain_loss_eur=Decimal("1645.00")
                )
            ],
            expected_eoy_states=[],
            expected_eoy_mismatch_error_count=0
        )

        mock_rate_provider = MockECBExchangeRateProvider()
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            cash_transactions_data=cash_transactions_data,
            corporate_actions_data=corporate_actions_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        
        self.assert_results(actual_processing_output, expected_outcome)
        
        # Verify no dividend income events for tax-free dividend
        self._assert_dividend_income_events(actual_processing_output, expected_count=0)
        
        # Verify tax impact is zero for tax-free dividend
        self._assert_tax_impact(actual_processing_output, 
                               expected_kap_other_income=Decimal("0.00"),
                               expected_conceptual_other_income=Decimal("0.00"))

    def test_d05_stock_dividend_fifo_lot_creation_and_tax_impact(self, mock_config_paths):
        """
        Test Case: D05-style stock dividend creates FIFO lot with dividend value and is treated as taxable income.
        
        Based on PRD Section 2.4: For taxable stock dividends, FMV of new shares is dividend income 
        and new shares form a new FIFO lot with FMV as cost basis.
        
        This test verifies:
        1. FIFO lot creation with correct cost basis (EUR 349 for 10 shares on 2024-04-30)
        2. EOY quantity is correct (110 shares total)
        3. Stock dividend income appears in processed_income_events
        4. Tax impact: dividend income contributes to kap_other_income_positive
        
        Corporate Actions Data based on D05 example but using EUR values:
        1. 2024-04-22: D05.REC receivable entry (EUR 340.7 value, 10 shares)
        2. 2024-04-30: D05 actual dividend (EUR 349 value, 10 shares) - dividend issue date
        3. 2024-04-30: D05.REC removal (-10 shares, 0 value)
        """
        d05_symbol = "D05"
        d05_isin = "SG1L01001701"
        d05_rec_symbol = "D05.REC"
        d05_rec_isin = "SG1L1701REC0"
        currency = "EUR"  # Using EUR to avoid currency conversion complexity

        # No trades data - this test focuses on stock dividend corporate action
        trades_data = []
        
        # Corporate actions data using EUR values
        # Headers: ClientAccountID, Symbol, Description, ISIN, Report Date, Code, Type, ActionID, 
        #          Conid, UnderlyingConid, UnderlyingSymbol, CurrencyPrimary, Amount, Proceeds, Value, Quantity
        corporate_actions_data = [
            # D05.REC receivable entry
            [ACCOUNT_ID, d05_rec_symbol, f"{d05_rec_symbol}({d05_isin}) STOCK DIVIDEND 1 FOR 10 ({d05_rec_symbol}, D05.RECEIVABLE, {d05_rec_isin})",
             d05_rec_isin, "2024-04-22", "", "SD", "135043471", "698426866", "", "", currency, "0", "0", "340.7", "10"],
            
            # D05 actual stock dividend (should create income event + FIFO lot)
            [ACCOUNT_ID, d05_symbol, f"{d05_symbol}({d05_isin}) STOCK DIVIDEND 1 FOR 10 ({d05_symbol}, DBS GROUP HOLDINGS LTD, {d05_isin})",
             d05_isin, "2024-04-30", "", "SD", "135043471", "15785538", "", "", currency, "0", "0", "349", "10"],
            
            # D05.REC removal
            [ACCOUNT_ID, d05_rec_symbol, f"{d05_rec_symbol}({d05_isin}) STOCK DIVIDEND 1 FOR 10 ({d05_rec_symbol}, D05.RECEIVABLE, {d05_rec_isin})",
             d05_rec_isin, "2024-04-30", "", "SD", "135043471", "698426866", "", "", currency, "0", "0", "0", "-10"]
        ]
        
        # Start with some D05 shares (prerequisite for receiving stock dividend)
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN, 
        #          Quantity, PositionValue, MarkPrice, CostBasisMoney, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
        positions_start_data = [
            [ACCOUNT_ID, currency, "STK", "COMMON", d05_symbol, "DBS GROUP HOLDINGS LTD", d05_isin,
             Decimal("100"), Decimal("3490"), Decimal("34.90"), Decimal("3490"),
             "", "15785538", "", Decimal("1")]
        ]
        
        # End position should include the 10 new shares from stock dividend
        positions_end_data = [
            [ACCOUNT_ID, currency, "STK", "COMMON", d05_symbol, "DBS GROUP HOLDINGS LTD", d05_isin,
             Decimal("110"), Decimal("3839"), Decimal("34.90"), Decimal("3839"),
             "", "15785538", "", Decimal("1")]
        ]

        expected_outcome = ScenarioExpectedOutput(
            test_description="D05 Stock Dividend: FIFO lot creation with dividend value and tax treatment",
            expected_rgls=[],  # No realized gains/losses from stock dividend itself
            expected_eoy_states=[
                # Should have 110 shares total (100 original + 10 from stock dividend)
                ExpectedAssetEoyState(asset_identifier=f"ISIN:{d05_isin}", eoy_quantity=Decimal("110"))
            ],
            expected_eoy_mismatch_error_count=0
        )

        # Use standard mock rate provider (no conversion needed since using EUR)
        mock_rate_provider = MockECBExchangeRateProvider()
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            corporate_actions_data=corporate_actions_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        
        # Assert basic FIFO and EOY results
        self.assert_results(actual_processing_output, expected_outcome)
        
        # Verify stock dividend income is recorded with expected amount
        self._assert_dividend_income_events(actual_processing_output, 
                                           expected_count=1, 
                                           expected_amount=Decimal("349"))
        
        # Verify tax impact includes the stock dividend
        self._assert_tax_impact(actual_processing_output,
                               expected_kap_foreign_income=Decimal("349.00"),
                               expected_conceptual_other_income=Decimal("349.00"))

    def test_dividend_rights_both_fifo_lots_to_zero_with_tax_impact(self, mock_config_paths):
        """
        Test Case 3: Dividend rights handling where both FIFO lots go to zero with additional tax impact.
        
        This test verifies:
        1. First and second FIFO lots cost basis correctly adjusted (verified via dividend impact on realized gains of stock sale)
        2. Both FIFO lots reduced to zero by dividend payment
        3. Additional impact on kap_other_income_positive from the tax-free dividend in tax year 2024
        4. "Exempt From Withholding" dividend treatment creates additional taxable income beyond cost basis adjustment
        
        Scenario (based on user specifications):
        - 2023-05-17: Buy 100 LEG shares at €1 each = €100 total cost (first lot)
        - 2023-06-21: Buy 50 LEG shares at €1 each = €50 total cost (second lot)  
        - 2024-05-24: Dividend rights issued (100 rights, 1 for 1)
        - 2024-06-26: Rights expire, €245 tax-free dividend paid
        - 2024-11-21: Sell all 150 shares at €85 each = €12750 total proceeds
        
        Expected FIFO calculation:
        - First lot: €100 cost - €100 from dividend = €0 (completely eliminated)
        - Second lot: €50 cost - €50 from dividend = €0 (completely eliminated)
        - Remaining dividend amount after cost basis reduction: €245 - €100 - €50 = €95
        - Total adjusted cost: €0 + €0 = €0
        - Realized gain: €12750 - €0 = €12750
        
        Expected tax impact:
        - Anlage KAP other income (kap_other_income_positive): €95 (remaining dividend after cost basis adjustment)
        - Conceptual other income: €95 (taxable portion of dividend)
        """
        leg_symbol = "LEGd"
        leg_isin = "DE000LEG1110"
        leg_divir_symbol = "LEG.DIVIR"
        leg_divir_isin = "DE000LEG1268"
        currency = "EUR"

        # Trades data - using test framework column order
        # Framework headers: "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol", "Description", "ISIN", "Strike", "Expiry", "Put/Call", "TradeDate", "Quantity", "TradePrice", "IBCommission", "IBCommissionCurrency", "Buy/Sell", "TransactionID", "Notes/Codes", "UnderlyingSymbol", "Conid", "UnderlyingConid", "Multiplier", "Open/CloseIndicator"
        trades_data = [
            # First purchase: 100 shares at €1 on 2023-05-17
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin, "", "", "", "20230517", "100", "1", "0", currency, "BUY", "1873530058", "A", "", "121764205", "", "1", "O"],
            
            # Second purchase: 50 shares at €1 on 2023-06-21  
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin, "", "", "", "20230621", "50", "1", "0", currency, "BUY", "2830028658", "P", "", "121764205", "", "1", "O"],
            
            # Sale: 150 shares at €85 on 2024-11-21
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin, "", "", "", "20241121", "-150", "85", "0", currency, "SELL", "2830028658", "", "", "121764205", "", "1", "C"]
        ]

        # Corporate actions data - using test framework column order  
        # Framework headers: "ClientAccountID", "Symbol", "Description", "ISIN", "Report Date", "Code", "Type", "ActionID", "Conid", "UnderlyingConid", "UnderlyingSymbol", "CurrencyPrimary", "Amount", "Proceeds", "Value", "Quantity"
        corporate_actions_data = [
            # Dividend rights issued (DI) - 100 rights issued 1 for 1
            [ACCOUNT_ID, leg_divir_symbol, f"LEG({leg_isin}) DIVIDEND RIGHTS ISSUE  1 FOR 1 ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})", leg_divir_isin, "20240524", "", "DI", "137293437", "705911909", "", "", currency, "0", "0", "0", "100"],
            
            # Dividend rights expire (ED) - 100 rights expire  
            [ACCOUNT_ID, leg_divir_symbol, f"{leg_divir_symbol}({leg_divir_isin}) EXPIRE DIVIDEND RIGHT ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})", leg_divir_isin, "20240626", "", "ED", "139982491", "705911909", "", "", currency, "0", "0", "0", "-100"]
        ]

        # Cash transaction - using test framework column order
        # Framework headers: "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol", "Description", "SettleDate", "Amount", "Type", "Conid", "UnderlyingConid", "ISIN", "IssuerCountryCode", "TransactionID"
        cash_transactions_data = [
            # Tax-free dividend payment of €245 (exactly as specified by user)
            [ACCOUNT_ID, currency, "STK", "RIGHT", leg_divir_symbol,
             f"{leg_divir_symbol}({leg_divir_isin}) EXPIRE DIVIDEND RIGHT (Exempt From Withholding)",
             "20240626", "245", "Dividends", "705911909", "", leg_divir_isin, "XX", "2841481203"]
        ]

        # Start positions - LEG shares after trades but before dividend event
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN, 
        #          Quantity, PositionValue, MarkPrice, CostBasisMoney, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
        positions_start_data = [
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             Decimal("150"), Decimal("9500"), Decimal("63.333"), Decimal("150"),  # Total cost: €100 + €50 = €150
             "", "121764205", "", Decimal("1")]
        ]

        positions_end_data = []

        # Expected calculation:
        # Original cost: €100 (first lot) + €50 (second lot) = €150
        # Dividend reduces first lot by €100 (to zero), second lot by €50 (to zero)
        # Remaining dividend: €245 - €150 = €95 (becomes taxable income)
        # Adjusted costs: €0 (first lot) + €0 (second lot) = €0 total
        expected_outcome = ScenarioExpectedOutput(
            test_description="LEG Dividend Rights: Both lots to zero, additional tax impact from remaining dividend",
            expected_rgls=[
                # First FIFO lot: 100 shares with cost basis reduced to zero
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-11-21",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("0.00"),  # €100 - €100 = €0
                    total_realization_value_eur=Decimal("8500.00"),
                    gross_gain_loss_eur=Decimal("8500.00")
                ),
                # Second FIFO lot: 50 shares with cost basis reduced to zero
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-11-21",
                    quantity_realized=Decimal("50"),
                    total_cost_basis_eur=Decimal("0.00"),  # €50 - €50 = €0
                    total_realization_value_eur=Decimal("4250.00"),
                    gross_gain_loss_eur=Decimal("4250.00")
                )
            ],
            expected_eoy_states=[],
            expected_eoy_mismatch_error_count=0
        )

        mock_rate_provider = MockECBExchangeRateProvider()
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            cash_transactions_data=cash_transactions_data,
            corporate_actions_data=corporate_actions_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        
        self.assert_results(actual_processing_output, expected_outcome)
        
        # Verify dividend income event for remaining amount after cost basis adjustment
        # Expected: €95 dividend income (€245 total - €150 cost basis adjustment)
        self._assert_dividend_income_events(actual_processing_output, 
                                           expected_count=1, 
                                           expected_amount=Decimal("95"))
        
        # Verify tax impact includes the remaining dividend amount as taxable income
        self._assert_tax_impact(actual_processing_output,
                               expected_kap_other_income=Decimal("95.00"),
                               expected_conceptual_other_income=Decimal("95.00"))

    def test_dividend_rights_payment_in_lieu_fifo_adjustment_via_sale_gains(self, mock_config_paths):
        """
        Test Case: Dividend rights handling using "Payment In Lieu Of Dividends" transaction type.

        This test mirrors test_dividend_rights_fifo_adjustment_via_sale_gains but uses the actual
        transaction structure found in real data files:
        - Transaction Type: "Payment In Lieu Of Dividends" (instead of "Dividends")
        - Description: "PAYMENT IN LIEU OF DIVIDEND" (instead of "EXPIRE DIVIDEND RIGHT")

        This test verifies:
        1. Tax-free dividend ("Exempt From Withholding") adjusts first FIFO lot cost basis
        2. FIFO adjustment is confirmed by checking realized gains from subsequent stock sale
        3. No impact on kap_other_income_positive in tax year 2024 from the tax-free dividend

        Scenario:
        - 2023-05-17: Buy 100 LEG shares at €55 each = €5500 total cost
        - 2023-06-21: Buy 50 LEG shares at €80 each = €4000 total cost
        - 2024-05-24: Dividend rights issued (100 rights, 1 for 1)
        - 2024-06-26: Rights expire, €245 tax-free dividend paid (Payment In Lieu type)
        - 2024-07-15: Sell all 150 shares at €85 each = €12750 total proceeds

        Expected FIFO calculation:
        - First lot after dividend adjustment: 100 shares, cost €5500 - €245 = €5255 (€52.55 per share)
        - Second lot unchanged: 50 shares, cost €4000 (€80 per share)
        - Total adjusted cost: €5255 + €4000 = €9255
        - Realized gain: €12750 - €9255 = €3495
        """
        leg_symbol = "LEGd"
        leg_isin = "DE000LEG1110"
        leg_divir_symbol = "LEG.DIVIR"
        leg_divir_isin = "DE000LEG1268"
        currency = "EUR"

        # Trades data - LEG stock purchases and sale
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN,
        #          Strike, Expiry, Put/Call, TradeDate, Quantity, TradePrice, IBCommission, IBCommissionCurrency,
        #          Buy/Sell, TransactionID, Notes/Codes, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier, Open/CloseIndicator
        trades_data = [
            # First purchase: 100 shares at €55 on 2023-05-17
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             "", "", "", "20230517", "100", "55", "0", currency, "BUY", "1873530058", "A", "", "121764205", "", "1", "O"],

            # Second purchase: 50 shares at €80 on 2023-06-21
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             "", "", "", "20230621", "50", "80", "0", currency, "BUY", "2830028658", "P", "", "121764205", "", "1", "O"],

            # Sale: 150 shares at €85 on 2024-07-15 (after dividend to see FIFO adjustment impact)
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             "", "", "", "20240715", "-150", "85", "0", currency, "SELL", "2830028659", "", "", "121764205", "", "1", "C"]
        ]

        # Corporate actions data - dividend rights issuance and expiry
        # Headers: ClientAccountID, Symbol, Description, ISIN, Report Date, Code, Type, ActionID,
        #          Conid, UnderlyingConid, UnderlyingSymbol, CurrencyPrimary, Amount, Proceeds, Value, Quantity
        corporate_actions_data = [
            # Dividend rights issued (DI) - 100 rights issued 1 for 1
            [ACCOUNT_ID, leg_divir_symbol,
             f"LEG({leg_isin}) DIVIDEND RIGHTS ISSUE  1 FOR 1 ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})",
             leg_divir_isin, "20240524", "", "DI", "137293437", "705911909", "", "", currency, "0", "0", "0", "100"],

            # Dividend rights expire (ED) - 100 rights expire
            [ACCOUNT_ID, leg_divir_symbol,
             f"{leg_divir_symbol}({leg_divir_isin}) EXPIRE DIVIDEND RIGHT ({leg_divir_symbol}, LEG IMMOBILIEN SE - DIVIDEND RIGHTS, {leg_divir_isin})",
             leg_divir_isin, "20240626", "", "ED", "139982491", "705911909", "", "", currency, "0", "0", "0", "-100"]
        ]

        # Cash transaction - using "Payment In Lieu Of Dividends" transaction type as found in real data
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description,
        #          SettleDate, Amount, Type, Conid, UnderlyingConid, ISIN, IssuerCountryCode, TransactionID
        cash_transactions_data = [
            # Tax-free dividend payment using "Payment In Lieu Of Dividends" type and "PAYMENT IN LIEU OF DIVIDEND" description
            [ACCOUNT_ID, currency, "STK", "RIGHT", leg_divir_symbol,  # Use DIVIR symbol as in real data
             f"LEG.DIVIR({leg_divir_isin}) PAYMENT IN LIEU OF DIVIDEND (Exempt From Withholding)",
             "20240626", "245", "Payment In Lieu Of Dividends", "705911909", "", leg_divir_isin, "XX", "2841481481"]  # Use real transaction ID from data
        ]

        # Start positions - LEG shares after trades but before dividend event
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN,
        #          Quantity, PositionValue, MarkPrice, CostBasisMoney, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
        positions_start_data = [
            [ACCOUNT_ID, currency, "STK", "COMMON", leg_symbol, "LEG IMMOBILIEN SE", leg_isin,
             Decimal("150"), Decimal("9500"), Decimal("63.333"), Decimal("9500"),
             "", "121764205", "", Decimal("1")]
        ]

        # End positions - no shares remaining after sale
        positions_end_data = []

        # Expected realized gain calculation:
        # Original cost basis: 100 * €55 + 50 * €80 = €5500 + €4000 = €9500
        # Dividend adjustment: €9500 - €245 = €9255 (first lot reduced by €245)
        # Sale proceeds: 150 * €85 = €12750
        # Expected realized gain: €12750 - €9255 = €3495
        expected_outcome = ScenarioExpectedOutput(
            test_description="LEG Dividend Rights (Payment In Lieu): Verify FIFO adjustment via sale realized gains",
            expected_rgls=[
                # First FIFO lot: 100 shares with dividend-adjusted cost basis
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-07-15",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("5255.00"),  # €5500 - €245 dividend adjustment
                    total_realization_value_eur=Decimal("8500.00"),
                    gross_gain_loss_eur=Decimal("3245.00")
                ),
                # Second FIFO lot: 50 shares with unchanged cost basis
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{leg_isin}",
                    realization_date="2024-07-15",
                    quantity_realized=Decimal("50"),
                    total_cost_basis_eur=Decimal("4000.00"),  # Unchanged
                    total_realization_value_eur=Decimal("4250.00"),
                    gross_gain_loss_eur=Decimal("250.00")
                )
            ],
            expected_eoy_states=[
                # No shares remaining after sale
            ],
            expected_eoy_mismatch_error_count=0
        )

        # Use standard mock rate provider
        mock_rate_provider = MockECBExchangeRateProvider()

        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            cash_transactions_data=cash_transactions_data,
            corporate_actions_data=corporate_actions_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )

        # Assert basic FIFO and EOY results
        self.assert_results(actual_processing_output, expected_outcome)

        # Verify no dividend income events for tax-free dividend
        self._assert_dividend_income_events(actual_processing_output, expected_count=0)

        # Verify tax impact is zero for tax-free dividend
        self._assert_tax_impact(actual_processing_output,
                               expected_kap_other_income=Decimal("0.00"),
                               expected_conceptual_other_income=Decimal("0.00"))

    def test_dividend_rights_both_fifo_lots_to_zero_with_tax_impact_abc(self, mock_config_paths):
        """
        Test Case 3 (ABC variant): Dividend rights handling where both FIFO lots go to zero with additional tax impact.
        
        This test verifies:
        1. First and second FIFO lots cost basis correctly adjusted (verified via dividend impact on realized gains of stock sale)
        2. Both FIFO lots reduced to zero by dividend payment
        3. Additional impact on kap_other_income_positive from the tax-free dividend in tax year 2024
        4. "Exempt From Withholding" dividend treatment creates additional taxable income beyond cost basis adjustment
        
        Scenario (based on user specifications):
        - 2023-05-17: Buy 100 ABC shares at €1 each = €100 total cost (first lot)
        - 2023-06-21: Buy 50 ABC shares at €1 each = €50 total cost (second lot)  
        - 2024-05-24: Dividend rights issued (100 rights, 1 for 1)
        - 2024-06-26: Rights expire, €245 tax-free dividend paid
        - 2024-11-21: Sell all 150 shares at €85 each = €12750 total proceeds
        
        Expected FIFO calculation:
        - First lot: €100 cost - €100 from dividend = €0 (completely eliminated)
        - Second lot: €50 cost - €50 from dividend = €0 (completely eliminated)
        - Remaining dividend amount after cost basis reduction: €245 - €100 - €50 = €95
        - Total adjusted cost: €0 + €0 = €0
        - Realized gain: €12750 - €0 = €12750
        
        Expected tax impact:
        - Anlage KAP other income (kap_other_income_positive): €95 (remaining dividend after cost basis adjustment)
        - Conceptual other income: €95 (taxable portion of dividend)
        """
        abc_symbol = "ABCd"
        abc_isin = "US0123456789"
        abc_divir_symbol = "ABC.DIVIR"
        abc_divir_isin = "US0123456890"
        currency = "EUR"

        # Trades data - using test framework column order
        # Framework headers: "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol", "Description", "ISIN", "Strike", "Expiry", "Put/Call", "TradeDate", "Quantity", "TradePrice", "IBCommission", "IBCommissionCurrency", "Buy/Sell", "TransactionID", "Notes/Codes", "UnderlyingSymbol", "Conid", "UnderlyingConid", "Multiplier", "Open/CloseIndicator"
        trades_data = [
            # First purchase: 100 shares at €1 on 2023-05-17
            [ACCOUNT_ID, currency, "STK", "COMMON", abc_symbol, "ABC CORPORATION", abc_isin, "", "", "", "20230517", "100", "1", "0", currency, "BUY", "1873530058", "A", "", "121764205", "", "1", "O"],
            
            # Second purchase: 50 shares at €1 on 2023-06-21  
            [ACCOUNT_ID, currency, "STK", "COMMON", abc_symbol, "ABC CORPORATION", abc_isin, "", "", "", "20230621", "50", "1", "0", currency, "BUY", "2830028658", "P", "", "121764205", "", "1", "O"],
            
            # Sale: 150 shares at €85 on 2024-11-21
            [ACCOUNT_ID, currency, "STK", "COMMON", abc_symbol, "ABC CORPORATION", abc_isin, "", "", "", "20241121", "-150", "85", "0", currency, "SELL", "2830028658", "", "", "121764205", "", "1", "C"]
        ]

        # Corporate actions data - using test framework column order  
        # Framework headers: "ClientAccountID", "Symbol", "Description", "ISIN", "Report Date", "Code", "Type", "ActionID", "Conid", "UnderlyingConid", "UnderlyingSymbol", "CurrencyPrimary", "Amount", "Proceeds", "Value", "Quantity"
        corporate_actions_data = [
            # Dividend rights issued (DI) - 100 rights issued 1 for 1
            [ACCOUNT_ID, abc_divir_symbol, f"ABC({abc_isin}) DIVIDEND RIGHTS ISSUE  1 FOR 1 ({abc_divir_symbol}, ABC CORPORATION - DIVIDEND RIGHTS, {abc_divir_isin})", abc_divir_isin, "20240524", "", "DI", "137293437", "705911909", "", "", currency, "0", "0", "0", "100"],
            
            # Dividend rights expire (ED) - 100 rights expire  
            [ACCOUNT_ID, abc_divir_symbol, f"{abc_divir_symbol}({abc_divir_isin}) EXPIRE DIVIDEND RIGHT ({abc_divir_symbol}, ABC CORPORATION - DIVIDEND RIGHTS, {abc_divir_isin})", abc_divir_isin, "20240626", "", "ED", "139982491", "705911909", "", "", currency, "0", "0", "0", "-100"]
        ]

        # Cash transaction - using test framework column order
        # Framework headers: "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol", "Description", "SettleDate", "Amount", "Type", "Conid", "UnderlyingConid", "ISIN", "IssuerCountryCode", "TransactionID"
        cash_transactions_data = [
            # Tax-free dividend payment of €245 (exactly as specified by user)
            [ACCOUNT_ID, currency, "STK", "RIGHT", abc_divir_symbol,
             f"{abc_divir_symbol}({abc_divir_isin}) EXPIRE DIVIDEND RIGHT (Exempt From Withholding)",
             "20240626", "245", "Dividends", "705911909", "", abc_divir_isin, "XX", "2841481203"]
        ]

        # Start positions - ABC shares after trades but before dividend event
        # Headers: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol, Description, ISIN, 
        #          Quantity, PositionValue, MarkPrice, CostBasisMoney, UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
        positions_start_data = [
            [ACCOUNT_ID, currency, "STK", "COMMON", abc_symbol, "ABC CORPORATION", abc_isin,
             Decimal("150"), Decimal("9500"), Decimal("63.333"), Decimal("150"),  # Total cost: €100 + €50 = €150
             "", "121764205", "", Decimal("1")]
        ]

        positions_end_data = []

        # Expected calculation:
        # Original cost: €100 (first lot) + €50 (second lot) = €150
        # Dividend reduces first lot by €100 (to zero), second lot by €50 (to zero)
        # Remaining dividend: €245 - €150 = €95 (becomes taxable income)
        # Adjusted costs: €0 (first lot) + €0 (second lot) = €0 total
        expected_outcome = ScenarioExpectedOutput(
            test_description="ABC Dividend Rights: Both lots to zero, additional tax impact from remaining dividend",
            expected_rgls=[
                # First FIFO lot: 100 shares with cost basis reduced to zero
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{abc_isin}",
                    realization_date="2024-11-21",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("0.00"),  # €100 - €100 = €0
                    total_realization_value_eur=Decimal("8500.00"),
                    gross_gain_loss_eur=Decimal("8500.00")
                ),
                # Second FIFO lot: 50 shares with cost basis reduced to zero
                ExpectedRealizedGainLoss(
                    asset_identifier=f"ISIN:{abc_isin}",
                    realization_date="2024-11-21",
                    quantity_realized=Decimal("50"),
                    total_cost_basis_eur=Decimal("0.00"),  # €50 - €50 = €0
                    total_realization_value_eur=Decimal("4250.00"),
                    gross_gain_loss_eur=Decimal("4250.00")
                )
            ],
            expected_eoy_states=[],
            expected_eoy_mismatch_error_count=0
        )

        mock_rate_provider = MockECBExchangeRateProvider()
        
        actual_processing_output = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start_data,
            positions_end_data=positions_end_data,
            cash_transactions_data=cash_transactions_data,
            corporate_actions_data=corporate_actions_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=DEFAULT_TAX_YEAR
        )
        
        self.assert_results(actual_processing_output, expected_outcome)
        
        # Verify dividend income event for remaining amount after cost basis adjustment
        # Expected: €95 dividend income (€245 total - €150 cost basis adjustment)
        self._assert_dividend_income_events(actual_processing_output, 
                                           expected_count=1, 
                                           expected_amount=Decimal("95"))
        
        # Verify tax impact includes the remaining dividend amount as taxable income
        self._assert_tax_impact(actual_processing_output, 
                               expected_kap_other_income=Decimal("95.00"),
                               expected_conceptual_other_income=Decimal("95.00"))
"""
Bond Maturity (BM Corporate Action) Tests

Legal basis: §20 Abs. 2 Satz 1 Nr. 7 EStG — gains/losses from redemption of
Kapitalforderungen (capital claims). Bond maturity is economically a disposal at
par value. Gain/loss = maturity proceeds - FIFO cost basis.

Form lines:
  - Gain  → ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE  (Zeile 19 component)
  - Loss  → ANLAGE_KAP_SONSTIGE_VERLUSTE          (Zeile 22)

IBKR reports bond maturity as a CA record with Type="BM".
There is no corresponding trade record for the maturity event itself.
"""

from datetime import date
from decimal import Decimal

from src.domain.enums import RealizationType, TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.expected import (
    ScenarioExpectedOutput,
    ExpectedRealizedGainLoss,
    ExpectedAssetEoyState,
)


ACCOUNT = "U_BOND_TEST"


def _bond_buy_row(symbol, isin, date, quantity, price, commission="0", tx_id="TX_BUY",
                  currency="EUR"):
    """Return a trades CSV row for a BOND BUY."""
    return [
        ACCOUNT, currency, "BOND", "Govt",
        symbol, f"{symbol} Bond", isin,
        "", "", "",        # Strike, Expiry, Put/Call
        date,
        str(quantity), str(price), str(commission), currency,
        "BUY", tx_id, "", "", f"CON_{symbol}", "", "1", "O",
    ]


def _bm_ca_row(symbol, isin, date, quantity, proceeds_per_bond, action_id="BM_001",
               currency="EUR"):
    """
    Return a corporate_actions CSV row for a bond maturity (Type=BM).

    quantity      — number of bonds disposed (positive integer; sign is applied internally)
    proceeds_per_bond — face value per bond at maturity in `currency` (e.g. Decimal("1.00"))

    Column order: ClientAccountID, Symbol, Description, ISIN, Report Date, Code,
                  Type, ActionID, Conid, UnderlyingConid, UnderlyingSymbol,
                  CurrencyPrimary, Amount, Proceeds, Value, Quantity
    """
    total_proceeds = Decimal(str(quantity)) * Decimal(str(proceeds_per_bond))
    return [
        ACCOUNT,
        symbol,
        f"({isin}) BOND MATURITY FOR {currency} {proceeds_per_bond} PER BOND ({symbol})",
        isin,
        date,
        "",          # Code
        "BM",        # Type
        action_id,
        f"CON_{symbol}",
        "", "",      # UnderlyingConid, UnderlyingSymbol
        currency,
        str(-total_proceeds),   # Amount (negative = cash value of bonds removed)
        str(total_proceeds),    # Proceeds (cash received)
        "0",                    # Value
        str(-quantity),         # Quantity (negative = bonds removed from position)
    ]


def _bond_soy_row(symbol, isin, quantity, cost_basis, currency="EUR"):
    """
    Return a start-of-year positions CSV row for a bond held across years.

    Required so the SOY-precedence rule keeps the historically-replayed lots
    (an asset absent from the SOY file is reset to quantity 0 and its lots dropped).

    Column order: ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol,
                  Description, ISIN, Quantity, PositionValue, MarkPrice, CostBasisMoney,
                  UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
    """
    return [
        ACCOUNT, currency, "BOND", "Govt",
        symbol, f"{symbol} Bond", isin,
        str(quantity), "0", "100", str(cost_basis),
        "", f"CON_{symbol}", "", "1",
    ]


class TestBondMaturity(FifoTestCaseBase):

    # -------------------------------------------------------------------------
    # Scenario 1: Gain on maturity
    # Bond bought below par in prior year, matures at par in tax year.
    # §20 Abs. 2 Nr. 7 EStG: gain feeds ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE.
    # -------------------------------------------------------------------------
    def test_gain_on_maturity(self, mock_config_paths):
        """
        BUY 1000 bonds @ 98.00 (% of par) in 2022, BM 1000 bonds @ par (1.00) in 2023.
        Bond prices are quoted as a percentage of nominal; gross = qty * price / 100.
        Cost = 1000 * 98.00 / 100 = EUR 980.00, proceeds = 1000 * 1.00 = EUR 1000.00.
        Gain = EUR 20.00
        """
        tax_year = 2023
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        trades_data = [
            _bond_buy_row("TBOND1", "DE000TEST0001", "2022-06-01",
                          quantity=1000, price="98.00", commission="0",
                          tx_id="TX_BUY_1"),
        ]
        corp_actions_data = [
            _bm_ca_row("TBOND1", "DE000TEST0001", "2023-03-15",
                       quantity=1000, proceeds_per_bond="1.00",
                       action_id="BM_GAIN_001"),
        ]
        positions_start = [
            _bond_soy_row("TBOND1", "DE000TEST0001", quantity=1000, cost_basis="980"),
        ]

        # cost = 1000 * 0.98 + 0 commission = 980.00
        # proceeds = 1000 * 1.00 = 1000.00
        # gain = 20.00
        expected = ScenarioExpectedOutput(
            test_description="Bond maturity gain: bought below par",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="TBOND1",
                    realization_date="2023-03-15",
                    quantity_realized=Decimal("1000"),
                    total_cost_basis_eur=Decimal("980.00"),
                    total_realization_value_eur=Decimal("1000.00"),
                    gross_gain_loss_eur=Decimal("20.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="TBOND1", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

        # Verify form line: gain feeds Zeile 19 (Sonstige Kapitalerträge)
        engine = LossOffsettingEngine(
            realized_gains_losses=results.realized_gains_losses,
            vorabpauschale_items=results.vorabpauschale_items,
            current_year_financial_events=results.processed_income_events,
            asset_resolver=results.asset_resolver,
            tax_year=tax_year,
        )
        form = engine.calculate_reporting_figures()
        assert form.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE, Decimal("0.00")
        ) == Decimal("20.00"), "Bond maturity gain must feed ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE"
        assert form.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE, Decimal("0.00")
        ) == Decimal("0.00"), "No loss expected"

    # -------------------------------------------------------------------------
    # Scenario 2: Loss on maturity
    # Bond bought above par, matures at par → loss feeds Zeile 22.
    # -------------------------------------------------------------------------
    def test_loss_on_maturity(self, mock_config_paths):
        """
        BUY 1000 bonds @ 102.00 (% of par) in 2022, BM @ par (1.00) in 2023.
        Cost = 1000 * 102.00 / 100 = EUR 1020.00, proceeds = EUR 1000.00.
        Loss = -EUR 20.00
        """
        tax_year = 2023
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        trades_data = [
            _bond_buy_row("TBOND2", "DE000TEST0002", "2022-09-01",
                          quantity=1000, price="102.00", commission="0",
                          tx_id="TX_BUY_2"),
        ]
        corp_actions_data = [
            _bm_ca_row("TBOND2", "DE000TEST0002", "2023-06-15",
                       quantity=1000, proceeds_per_bond="1.00",
                       action_id="BM_LOSS_001"),
        ]
        positions_start = [
            _bond_soy_row("TBOND2", "DE000TEST0002", quantity=1000, cost_basis="1020"),
        ]

        # cost = 1020.00, proceeds = 1000.00, loss = -20.00
        expected = ScenarioExpectedOutput(
            test_description="Bond maturity loss: bought above par",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="TBOND2",
                    realization_date="2023-06-15",
                    quantity_realized=Decimal("1000"),
                    total_cost_basis_eur=Decimal("1020.00"),
                    total_realization_value_eur=Decimal("1000.00"),
                    gross_gain_loss_eur=Decimal("-20.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="TBOND2", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

        # Verify form line: loss feeds Zeile 22 (Sonstige Verluste)
        engine = LossOffsettingEngine(
            realized_gains_losses=results.realized_gains_losses,
            vorabpauschale_items=results.vorabpauschale_items,
            current_year_financial_events=results.processed_income_events,
            asset_resolver=results.asset_resolver,
            tax_year=tax_year,
        )
        form = engine.calculate_reporting_figures()
        assert form.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE, Decimal("0.00")
        ) == Decimal("20.00"), "Bond maturity loss must feed ANLAGE_KAP_SONSTIGE_VERLUSTE"
        assert form.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE, Decimal("0.00")
        ) == Decimal("0.00"), "No gain expected"

    # -------------------------------------------------------------------------
    # Scenario 3: Multi-lot FIFO
    # Two buy lots in different years; BM drains oldest lot first.
    # -------------------------------------------------------------------------
    def test_fifo_two_lots(self, mock_config_paths):
        """
        Maturity consumes the entire position across multiple lots, each producing
        its own RGL with its own cost basis.

        Lot 1: BUY 500 bonds @ 96.00 (%) on 2022-01-10  → cost EUR 480.00
        Lot 2: BUY 500 bonds @ 98.00 (%) on 2022-07-01  → cost EUR 490.00
        BM: 1000 bonds @ par (1.00) on 2023-03-01
          Total cost = EUR 970.00, proceeds = EUR 1000.00, combined gain = EUR 30.00
        """
        tax_year = 2023
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        trades_data = [
            _bond_buy_row("TBOND3", "DE000TEST0003", "2022-01-10",
                          quantity=500, price="96.00", commission="0",
                          tx_id="TX_BUY_3A"),
            _bond_buy_row("TBOND3", "DE000TEST0003", "2022-07-01",
                          quantity=500, price="98.00", commission="0",
                          tx_id="TX_BUY_3B"),
        ]
        corp_actions_data = [
            _bm_ca_row("TBOND3", "DE000TEST0003", "2023-03-01",
                       quantity=1000, proceeds_per_bond="1.00",
                       action_id="BM_FIFO_001"),
        ]
        positions_start = [
            _bond_soy_row("TBOND3", "DE000TEST0003", quantity=1000, cost_basis="970"),
        ]

        # FIFO: lot1 (500 @ 0.96 = 480) + lot2 (500 @ 0.98 = 490) = 970 total cost
        # proceeds = 1000 * 1.00 = 1000.00
        # gain = 30.00
        expected = ScenarioExpectedOutput(
            test_description="Bond maturity FIFO: two lots, oldest first",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="TBOND3",
                    realization_date="2023-03-01",
                    quantity_realized=Decimal("500"),
                    total_cost_basis_eur=Decimal("480.00"),
                    total_realization_value_eur=Decimal("500.00"),
                    gross_gain_loss_eur=Decimal("20.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
                ExpectedRealizedGainLoss(
                    asset_identifier="TBOND3",
                    realization_date="2023-03-01",
                    quantity_realized=Decimal("500"),
                    total_cost_basis_eur=Decimal("490.00"),
                    total_realization_value_eur=Decimal("500.00"),
                    gross_gain_loss_eur=Decimal("10.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="TBOND3", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

        # Combined gain of EUR 30.00 must feed ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
        engine = LossOffsettingEngine(
            realized_gains_losses=results.realized_gains_losses,
            vorabpauschale_items=results.vorabpauschale_items,
            current_year_financial_events=results.processed_income_events,
            asset_resolver=results.asset_resolver,
            tax_year=tax_year,
        )
        form = engine.calculate_reporting_figures()
        assert form.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE, Decimal("0.00")
        ) == Decimal("30.00"), "Combined FIFO gain must feed ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE"

    # -------------------------------------------------------------------------
    # Scenario 4: Foreign-currency (USD) bond
    # Gain is computed in EUR using ECB rates at purchase vs. maturity date.
    # This exercises the synthetic trade's FX path (_process_trade_currency_impact).
    # -------------------------------------------------------------------------
    def test_foreign_currency_bond_maturity(self, mock_config_paths):
        """
        USD bond. BUY 1000 @ 98.00 (% of par) on 2022-06-01 (1 USD = 1.00 EUR),
        BM 1000 @ par (1.00) on 2023-03-15 (1 USD = 1.10 EUR).

        Cost basis  = 1000 * 98.00 / 100 * 1.00 = EUR 980.00
        Proceeds    = 1000 * 1.00 * 1.10        = EUR 1100.00
        Bond gain   = EUR 120.00   (includes the EUR effect of the rising USD,
                                     per §20 Abs. 4 — gain computed in EUR)
        """
        tax_year = 2023
        # 1 USD = 1.00 EUR until 2023-01-01, then 1 USD = 1.10 EUR
        mock_provider = MockECBExchangeRateProvider(
            currency_schedules={
                "USD": [
                    (date(2022, 1, 1), Decimal("1.00")),
                    (date(2023, 1, 1), Decimal("1.10")),
                ],
            },
            foreign_to_eur_init_value=Decimal("1.0"),
        )

        trades_data = [
            _bond_buy_row("UBOND1", "US000TEST0001", "2022-06-01",
                          quantity=1000, price="98.00", commission="0",
                          tx_id="TX_BUY_USD", currency="USD"),
        ]
        corp_actions_data = [
            _bm_ca_row("UBOND1", "US000TEST0001", "2023-03-15",
                       quantity=1000, proceeds_per_bond="1.00",
                       action_id="BM_USD_001", currency="USD"),
        ]
        positions_start = [
            _bond_soy_row("UBOND1", "US000TEST0001", quantity=1000,
                          cost_basis="980", currency="USD"),
        ]

        expected = ScenarioExpectedOutput(
            test_description="USD bond maturity: gain computed in EUR across two rates",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="UBOND1",
                    realization_date="2023-03-15",
                    quantity_realized=Decimal("1000"),
                    total_cost_basis_eur=Decimal("980.00"),
                    total_realization_value_eur=Decimal("1100.00"),
                    gross_gain_loss_eur=Decimal("120.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="UBOND1", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        # The bond RGL is asserted by identifier; a CASH_BALANCE (USD) lot is also
        # created from the maturity proceeds, so filter to the bond before matching.
        bond_rgls = [
            rgl for rgl in results.realized_gains_losses
            if results.asset_resolver.get_asset_by_id(rgl.asset_internal_id).ibkr_isin
            == "US000TEST0001"
        ]
        assert len(bond_rgls) == 1, "Exactly one bond maturity RGL expected"
        assert bond_rgls[0].gross_gain_loss_eur.quantize(Decimal("0.01")) == Decimal("120.00")
        assert bond_rgls[0].total_cost_basis_eur.quantize(Decimal("0.01")) == Decimal("980.00")
        assert bond_rgls[0].total_realization_value_eur.quantize(Decimal("0.01")) == Decimal("1100.00")

    # -------------------------------------------------------------------------
    # Scenario 5: Prior-year maturity (historical replay)
    # Bond bought 2022, matured 2023, processing tax year 2024.
    # The maturity must drain the FIFO lots during historical replay so the bond
    # does NOT appear as a phantom holding and produces NO current-year RGL.
    # This verifies that the synthetic TradeEvent is replayed historically
    # (calculation_engine.py treats TradeEvent as a first-class historical event).
    # -------------------------------------------------------------------------
    def test_prior_year_maturity_historical_replay(self, mock_config_paths):
        """
        2022: BUY 1000 @ 98.00 (% of par)
        2023: BM 1000 @ par (1.00)   (gain belongs to 2023, not 2024)
        Process tax year 2024 → no RGLs, bond not held, no EOY mismatch.
        """
        tax_year = 2024
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        trades_data = [
            _bond_buy_row("HBOND1", "DE000TEST0009", "2022-06-01",
                          quantity=1000, price="98.00", commission="0",
                          tx_id="TX_BUY_HIST"),
        ]
        corp_actions_data = [
            _bm_ca_row("HBOND1", "DE000TEST0009", "2023-03-15",
                       quantity=1000, proceeds_per_bond="1.00",
                       action_id="BM_HIST_001"),
        ]

        expected = ScenarioExpectedOutput(
            test_description="Prior-year bond maturity drained in historical replay",
            expected_rgls=[],  # 2023 maturity does not appear in 2024
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="HBOND1", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=[],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

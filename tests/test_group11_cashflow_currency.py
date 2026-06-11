"""
Group 11: Implicit FX from Cash Flows (Phase 5c)

Tests that cash flow events (dividends, interest, withholding tax, fees)
in foreign currency correctly create/consume currency FIFO lots and
generate FX gains/losses.

Tax Law Basis:
- BMF Circular May 2022, Para. 131: IBKR FX reserves are interest-bearing
- FX gains/losses from cash flows → §20 EStG → Anlage KAP Zeile 19

Test Organization:
- CFX_CF_DIV_*  : Dividend income creating currency lots
- CFX_CF_INT_*  : Interest income creating currency lots
- CFX_CF_WHT_*  : Withholding tax consuming currency lots
- CFX_CF_FEE_*  : Fee payments consuming currency lots
- CFX_CF_MIX_*  : Mixed cash flows with FX gain/loss realization
"""

import logging
import pytest
from decimal import Decimal
from typing import List, Any, Optional

logger = logging.getLogger(__name__)

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from src.domain.enums import AssetCategory, RealizationType, TaxReportingCategory


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TAX_YEAR = 2023
ACCOUNT_ID = "U_CF_TEST"


# =============================================================================
# Mock Rate Provider
# =============================================================================

class CashflowTestRateProvider(MockECBExchangeRateProvider):
    """Mock rate provider with per-date, per-currency rate map."""

    def __init__(self, rate_map: dict):
        super().__init__(foreign_to_eur_init_value=Decimal("0.909090909"))  # 1/1.10
        self._rate_map = rate_map

    def get_rate(self, date_of_conversion, currency_code: str) -> Optional[Decimal]:
        from datetime import date as date_type

        currency_upper = currency_code.upper()
        if currency_upper == "EUR":
            return Decimal("1.0")

        if isinstance(date_of_conversion, date_type):
            date_str = date_of_conversion.strftime("%Y-%m-%d")
        else:
            date_str = str(date_of_conversion)

        key = (date_str, currency_upper)
        if key in self._rate_map:
            return self._rate_map[key]

        return super().get_rate(date_of_conversion, currency_code)


# =============================================================================
# CSV Row Builders
# =============================================================================

def _cash_balance_row(currency: str, soy: Decimal, eoy: Decimal) -> List[Any]:
    """Create a cash balance CSV row."""
    return [ACCOUNT_ID, currency, "20230101", "20231231", soy, eoy]


def _cash_transaction_row(
    currency: str,
    amount: Decimal,
    tx_type: str,
    date: str,
    symbol: str = "",
    description: str = "",
    isin: str = "",
    asset_class: str = "",
    sub_category: str = "",
    country_code: str = "",
    conid: str = "",
    underlying_conid: str = "",
    tx_id: str = "",
) -> List[Any]:
    """Create a cash transaction CSV row."""
    return [
        ACCOUNT_ID,      # ClientAccountID
        currency,        # CurrencyPrimary
        asset_class,     # AssetClass
        sub_category,    # SubCategory
        symbol,          # Symbol
        description,     # Description
        date,            # SettleDate
        amount,          # Amount
        tx_type,         # Type
        conid,           # Conid
        underlying_conid,  # UnderlyingConid
        isin,            # ISIN
        country_code,    # IssuerCountryCode
        tx_id,           # TransactionID
    ]


def _fx_trade_row(
    currency: str,
    eur_amount: Decimal,
    trade_type: str,  # BUY or SELL
    ecb_rate: Decimal,
    date: str,
    tx_id: str,
) -> List[Any]:
    """Create an FX trade CSV row (buy/sell foreign currency)."""
    symbol = f"EUR.{currency}"
    quantity = -eur_amount if trade_type == "BUY" else eur_amount
    buy_sell = "SELL" if trade_type == "BUY" else "BUY"

    return [
        ACCOUNT_ID, "EUR", "CASH", "", symbol, f"FX {symbol}", "",
        None, None, None,
        date, quantity, ecb_rate, Decimal("0"), "EUR",
        buy_sell, tx_id, None, None, None, None, Decimal("1"), "O",
    ]


def _currency_position_row(currency: str, balance: Decimal, cost_basis: Decimal) -> List[Any]:
    """Create a currency position CSV row (for SOY/EOY)."""
    mark_price = cost_basis / abs(balance) if balance != Decimal("0") else Decimal("1")
    return [
        ACCOUNT_ID, currency, "CASH", "", currency,
        f"Cash Balance {currency}", "",
        balance, abs(balance) * mark_price, mark_price, cost_basis,
        None, None, None, Decimal("1"),
    ]


# =============================================================================
# Test Classes
# =============================================================================

class TestCashflowCurrencyLotCreation(FifoTestCaseBase):
    """
    Tests that income cash flows (dividends, interest) in foreign currency
    create new FIFO lots in the currency ledger.
    """

    def test_dividend_creates_usd_lot(self, mock_config_paths):
        """
        CFX_CF_DIV_001: USD dividend creates a currency FIFO lot.

        Scenario:
        - SOY: 0 USD
        - 2023-06-15: Receive 200 USD dividend (ECB rate 1.25 → 160 EUR)
        - 2023-09-01: Sell 200 USD via explicit FX at rate 1.60 (→ 125 EUR)

        Expected:
        - Dividend creates lot: 200 USD @ 0.80 EUR/USD (160/200)
        - FX sale realizes: proceeds 125 EUR - cost 160 EUR = -35 EUR loss
        """
        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.25"),
            ("2023-09-01", "USD"): Decimal("1.60"),
            ("2022-12-31", "USD"): Decimal("1.10"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("0"), Decimal("0"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("200"), tx_type="Dividends",
                date="2023-06-15", symbol="AAPL", description="AAPL CASH DIVIDEND USD 2.00",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="DIV_001",
            ),
        ]

        trades = [
            _fx_trade_row("USD", Decimal("125"), "SELL", Decimal("1.60"), "2023-09-01", "FX_001"),
        ]

        actual = self._run_pipeline(
            trades_data=trades,
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        # Filter to CASH_BALANCE RGLs only
        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        assert len(currency_rgls) == 1, f"Expected 1 currency RGL, got {len(currency_rgls)}: {currency_rgls}"
        rgl = currency_rgls[0]

        from src import config as app_config
        assert rgl.quantity_realized == Decimal("200")
        assert rgl.total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("160.00")
        assert rgl.total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("125.00")
        assert rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("-35.00")
        assert rgl.realization_type == RealizationType.FX_CONVERSION_SALE

    def test_interest_creates_currency_lot(self, mock_config_paths):
        """
        CFX_CF_INT_001: Broker interest in CHF creates a currency FIFO lot.

        Scenario:
        - SOY: 0 CHF
        - 2023-03-15: Receive 10 CHF interest (ECB rate 1.00 → 10 EUR)
        - 2023-07-01: Sell 10 CHF via explicit FX at rate 0.50 (→ 20 EUR)

        Expected:
        - Interest creates lot: 10 CHF @ 1.00 EUR/CHF
        - FX sale realizes: proceeds 20 EUR - cost 10 EUR = 10 EUR gain
        """
        rate_map = {
            ("2023-03-15", "CHF"): Decimal("1.00"),
            ("2023-07-01", "CHF"): Decimal("0.50"),
            ("2022-12-31", "CHF"): Decimal("1.00"),
        }

        cash_balance = [_cash_balance_row("CHF", Decimal("0"), Decimal("0"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="CHF", amount=Decimal("10"), tx_type="Broker Interest Received",
                date="2023-03-15", description="CREDIT INTEREST FOR MAR-2023",
                tx_id="INT_001",
            ),
        ]

        trades = [
            _fx_trade_row("CHF", Decimal("20"), "SELL", Decimal("0.50"), "2023-07-01", "FX_001"),
        ]

        actual = self._run_pipeline(
            trades_data=trades,
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        assert len(currency_rgls) == 1, f"Expected 1 currency RGL, got {len(currency_rgls)}: {currency_rgls}"
        rgl = currency_rgls[0]

        from src import config as app_config
        assert rgl.quantity_realized == Decimal("10")
        assert rgl.total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("10.00")
        assert rgl.total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("20.00")
        assert rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("10.00")

    def test_dividend_without_subsequent_sale_no_rgl(self, mock_config_paths):
        """
        CFX_CF_DIV_002: Dividend creates a lot but no sale → no FX RGL.

        Scenario:
        - SOY: 0 USD
        - 2023-06-15: Receive 500 USD dividend
        - No FX trade in the year

        Expected: No currency RGLs (lot just sits in ledger)
        """
        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.25"),
            ("2022-12-31", "USD"): Decimal("1.10"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("0"), Decimal("500"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("500"), tx_type="Dividends",
                date="2023-06-15", symbol="MSFT", description="MSFT CASH DIVIDEND",
                isin="US5949181045", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="DIV_002",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        assert len(currency_rgls) == 0, f"Expected 0 currency RGLs, got {len(currency_rgls)}: {currency_rgls}"


class TestCashflowCurrencyConsumption(FifoTestCaseBase):
    """
    Tests that expense cash flows (WHT, fees) in foreign currency
    consume from currency FIFO ledger and realize FX gains/losses.
    """

    def test_wht_consumes_from_existing_lot(self, mock_config_paths):
        """
        CFX_CF_WHT_001: WHT in USD consumes from existing currency lot.

        Scenario:
        - SOY: 1000 USD (cost basis 800 EUR, rate was 1.25)
        - 2023-06-15: WHT -30 USD (ECB rate 1.50 → 20 EUR)

        Expected:
        - WHT consumes 30 USD from SOY lot
        - Cost basis of consumed lot: 30 * (800/1000) = 24 EUR
        - Proceeds (EUR value at WHT date): 30/1.50 = 20 EUR
        - FX loss: 20 - 24 = -4 EUR
        """
        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.50"),
            ("2022-12-31", "USD"): Decimal("1.25"),
            ("2023-01-01", "USD"): Decimal("1.25"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("1000"), Decimal("970"))]
        positions_soy = [_currency_position_row("USD", Decimal("1000"), Decimal("800"))]
        positions_eoy = [_currency_position_row("USD", Decimal("970"), Decimal("776"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("-30"), tx_type="Withholding Tax",
                date="2023-06-15", symbol="AAPL",
                description="AAPL CASH DIVIDEND USD 2.00 - US TAX",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="WHT_001",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            positions_start_data=positions_soy,
            positions_end_data=positions_eoy,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        assert len(currency_rgls) == 1, f"Expected 1 currency RGL, got {len(currency_rgls)}: {currency_rgls}"
        rgl = currency_rgls[0]

        from src import config as app_config
        assert rgl.quantity_realized == Decimal("30")
        assert rgl.realization_type == RealizationType.FX_IMPLICIT_CASHFLOW_EXPENSE
        assert rgl.total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("24.00")
        assert rgl.total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("20.00")
        assert rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("-4.00")

    def test_wht_opens_short_when_no_balance(self, mock_config_paths):
        """
        CFX_CF_WHT_002: WHT with no existing balance opens short position.

        Scenario:
        - SOY: 0 USD
        - 2023-06-15: WHT -50 USD (ECB rate 1.25 → 40 EUR)

        Expected:
        - No RGL (short position opened, not covered)
        - Short lot created for 50 USD
        """
        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.25"),
            ("2022-12-31", "USD"): Decimal("1.10"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("0"), Decimal("-50"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("-50"), tx_type="Withholding Tax",
                date="2023-06-15", symbol="AAPL",
                description="AAPL CASH DIVIDEND - US TAX",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="WHT_002",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        # No RGL because short was opened, not covered
        assert len(currency_rgls) == 0, f"Expected 0 currency RGLs, got {len(currency_rgls)}: {currency_rgls}"


class TestCashflowMixedScenarios(FifoTestCaseBase):
    """
    Tests combining income and expense cash flows to verify FIFO ordering
    and correct gain/loss calculations.
    """

    def test_dividend_then_wht_fifo_ordering(self, mock_config_paths):
        """
        CFX_CF_MIX_001: Dividend creates lot, then WHT consumes from it.

        Scenario:
        - SOY: 0 USD
        - 2023-06-15: Receive 200 USD dividend (ECB rate 1.25 → 160 EUR)
        - 2023-06-15: WHT -30 USD (ECB rate 1.25 → 24 EUR)

        Expected:
        - Dividend creates lot: 200 USD @ 0.80 EUR/USD
        - WHT consumes 30 USD from that lot
        - Same rate on same day → cost basis = proceeds → FX gain/loss = 0
        - Remaining lot: 170 USD
        """
        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.25"),
            ("2022-12-31", "USD"): Decimal("1.10"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("0"), Decimal("170"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("200"), tx_type="Dividends",
                date="2023-06-15", symbol="AAPL", description="AAPL CASH DIVIDEND",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="DIV_MIX_001",
            ),
            _cash_transaction_row(
                currency="USD", amount=Decimal("-30"), tx_type="Withholding Tax",
                date="2023-06-15", symbol="AAPL", description="AAPL - US TAX",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="WHT_MIX_001",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        # WHT on same day as dividend → same rate → the disposal still happens,
        # with exactly zero FX gain/loss. Pin ONE outcome: the RGL must exist
        # (the WHT consumed 30 USD from the dividend lot — a disposal under the
        # BMF FX rules) and its gain must be exactly 0.00. (The previous
        # accept-0-or-1 soft assertion could not catch a dropped-RGL regression.)
        from src import config as app_config
        assert len(currency_rgls) == 1, \
            f"Expected exactly 1 currency RGL (zero-gain disposal), got {len(currency_rgls)}: {currency_rgls}"
        rgl = currency_rgls[0]
        assert rgl.quantity_realized == Decimal("30")
        assert rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("0.00")
        assert rgl.realization_type == RealizationType.FX_IMPLICIT_CASHFLOW_EXPENSE

    def test_soy_lot_then_wht_with_fx_gain(self, mock_config_paths):
        """
        CFX_CF_MIX_002: SOY lot consumed by WHT with FX gain.

        Scenario:
        - SOY: 1000 USD (cost basis 500 EUR → 0.50 EUR/USD, rate was 2.00)
        - 2023-06-15: WHT -100 USD (ECB rate 1.25 → 80 EUR)

        Expected:
        - WHT consumes 100 USD from SOY lot
        - Cost basis: 100 * 0.50 = 50 EUR
        - Proceeds: 100/1.25 = 80 EUR
        - FX gain: 80 - 50 = 30 EUR (USD appreciated since acquisition)
        """
        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.25"),
            ("2022-12-31", "USD"): Decimal("2.00"),
            ("2023-01-01", "USD"): Decimal("2.00"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("1000"), Decimal("900"))]
        positions_soy = [_currency_position_row("USD", Decimal("1000"), Decimal("500"))]
        positions_eoy = [_currency_position_row("USD", Decimal("900"), Decimal("450"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("-100"), tx_type="Withholding Tax",
                date="2023-06-15", symbol="AAPL",
                description="AAPL CASH DIVIDEND - US TAX",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="WHT_MIX_002",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            positions_start_data=positions_soy,
            positions_end_data=positions_eoy,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        assert len(currency_rgls) == 1, f"Expected 1 currency RGL, got {len(currency_rgls)}: {currency_rgls}"
        rgl = currency_rgls[0]

        from src import config as app_config
        assert rgl.quantity_realized == Decimal("100")
        assert rgl.realization_type == RealizationType.FX_IMPLICIT_CASHFLOW_EXPENSE
        assert rgl.total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("50.00")
        assert rgl.total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("80.00")
        assert rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("30.00")
        assert rgl.tax_reporting_category == TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE

    def test_dividend_covers_short_position(self, mock_config_paths):
        """
        CFX_CF_MIX_003: Dividend income covers an existing short currency position.

        Scenario:
        - SOY: -500 USD short (short proceeds 400 EUR → 0.80 EUR/USD, rate was 1.25)
        - 2023-06-15: Receive 500 USD dividend (ECB rate 1.00 → 500 EUR)

        Expected:
        - Dividend covers 500 USD short position
        - Original proceeds: 500 * 0.80 = 400 EUR
        - Cover cost: 500 * 1.00 = 500 EUR
        - FX loss on short cover: 400 - 500 = -100 EUR (USD appreciated, bad for short)
        """
        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.00"),
            ("2022-12-31", "USD"): Decimal("1.25"),
            ("2023-01-01", "USD"): Decimal("1.25"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("-500"), Decimal("0"))]
        positions_soy = [_currency_position_row("USD", Decimal("-500"), Decimal("400"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("500"), tx_type="Dividends",
                date="2023-06-15", symbol="AAPL", description="AAPL CASH DIVIDEND",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="DIV_MIX_003",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            positions_start_data=positions_soy,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        assert len(currency_rgls) == 1, f"Expected 1 currency RGL, got {len(currency_rgls)}: {currency_rgls}"
        rgl = currency_rgls[0]

        from src import config as app_config
        assert rgl.quantity_realized == Decimal("500")
        assert rgl.realization_type == RealizationType.FX_IMPLICIT_CASHFLOW_INCOME
        assert rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("-100.00")
        assert rgl.tax_reporting_category == TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE

    def test_explicit_fx_then_wht_fifo_lot_ordering(self, mock_config_paths):
        """
        CFX_CF_MIX_004: Explicit FX buy creates lot, WHT consumes from it.

        Scenario:
        - SOY: 0 USD
        - 2023-03-01: Buy 1000 USD via FX at rate 1.25 (cost: 800 EUR)
        - 2023-06-15: WHT -100 USD (ECB rate 1.00 → 100 EUR)

        Expected:
        - FX buy creates lot: 1000 USD @ 0.80 EUR/USD
        - WHT consumes 100 USD from lot
        - Cost basis: 100 * 0.80 = 80 EUR
        - Proceeds: 100 / 1.00 = 100 EUR
        - FX gain: 100 - 80 = 20 EUR
        """
        rate_map = {
            ("2023-03-01", "USD"): Decimal("1.25"),
            ("2023-06-15", "USD"): Decimal("1.00"),
            ("2022-12-31", "USD"): Decimal("1.10"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("0"), Decimal("900"))]

        trades = [
            _fx_trade_row("USD", Decimal("800"), "BUY", Decimal("1.25"), "2023-03-01", "FX_001"),
        ]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("-100"), tx_type="Withholding Tax",
                date="2023-06-15", symbol="AAPL",
                description="AAPL CASH DIVIDEND - US TAX",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="WHT_MIX_004",
            ),
        ]

        actual = self._run_pipeline(
            trades_data=trades,
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        # Should have 1 RGL from WHT consuming the lot
        assert len(currency_rgls) == 1, f"Expected 1 currency RGL, got {len(currency_rgls)}: {currency_rgls}"
        rgl = currency_rgls[0]

        from src import config as app_config
        assert rgl.quantity_realized == Decimal("100")
        assert rgl.realization_type == RealizationType.FX_IMPLICIT_CASHFLOW_EXPENSE
        assert rgl.total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("80.00")
        assert rgl.total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("100.00")
        assert rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("20.00")


class TestCashflowAggregates(FifoTestCaseBase):
    """
    Integration test: verify FX gains/losses from cash flows
    flow correctly to Anlage KAP tax form lines.
    """

    def test_cashflow_fx_gains_in_kap_aggregates(self, mock_config_paths):
        """
        CFX_CF_AGG_001: Cash flow FX gains aggregate into kap_other_income.

        Scenario:
        - SOY: 1000 USD (cost basis 500 EUR)
        - 2023-06-15: WHT -200 USD (rate 1.25 → 160 EUR)
        - Cost basis consumed: 200 * 0.50 = 100 EUR
        - FX gain: 160 - 100 = 60 EUR

        Verify: kap_other_income = 60.00
        """
        from src.engine.loss_offsetting import LossOffsettingEngine

        rate_map = {
            ("2023-06-15", "USD"): Decimal("1.25"),
            ("2022-12-31", "USD"): Decimal("2.00"),
            ("2023-01-01", "USD"): Decimal("2.00"),
        }

        cash_balance = [_cash_balance_row("USD", Decimal("1000"), Decimal("800"))]
        positions_soy = [_currency_position_row("USD", Decimal("1000"), Decimal("500"))]
        positions_eoy = [_currency_position_row("USD", Decimal("800"), Decimal("400"))]

        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("-200"), tx_type="Withholding Tax",
                date="2023-06-15", symbol="AAPL",
                description="AAPL CASH DIVIDEND - US TAX",
                isin="US0378331005", asset_class="STK", sub_category="COMMON",
                country_code="US", tx_id="WHT_AGG_001",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            positions_start_data=positions_soy,
            positions_end_data=positions_eoy,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        loss_engine = LossOffsettingEngine(
            realized_gains_losses=currency_rgls,
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=actual.asset_resolver,
            tax_year=DEFAULT_TAX_YEAR,
        )
        figures = loss_engine.calculate_reporting_figures()

        from src import config as app_config
        actual_income = figures.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE, Decimal("0")
        )
        assert actual_income.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == Decimal("60.00"), \
            f"kap_other_income: Expected 60.00, Got {actual_income}"


class TestCashflowEurSkipped(FifoTestCaseBase):
    """
    Tests that EUR-denominated cash flows are correctly skipped
    (no currency impact for base currency events).
    """

    def test_eur_dividend_no_fx_impact(self, mock_config_paths):
        """
        CFX_CF_EUR_001: EUR dividend has no currency impact.
        """
        rate_map = {("2022-12-31", "USD"): Decimal("1.10")}

        cash_transactions = [
            _cash_transaction_row(
                currency="EUR", amount=Decimal("500"), tx_type="Dividends",
                date="2023-06-15", symbol="SAP", description="SAP CASH DIVIDEND",
                isin="DE0007164600", asset_class="STK", sub_category="COMMON",
                country_code="DE", tx_id="DIV_EUR_001",
            ),
        ]

        actual = self._run_pipeline(
            cash_transactions_data=cash_transactions,
            custom_rate_provider=CashflowTestRateProvider(rate_map),
            tax_year=DEFAULT_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        assert len(currency_rgls) == 0, f"EUR dividend should not create currency RGLs: {currency_rgls}"

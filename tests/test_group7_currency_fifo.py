"""
Currency FIFO Test Runner for Group 7

Loads YAML-based currency FIFO test specifications and executes them through
the full processing pipeline. Tests cover:
- Explicit FX trades (EUR ↔ Foreign currency)
- Implicit FX from security trades (Phase 5a)
- Long and short currency positions
- Cross-currency trades (USD→GBP where neither is EUR)
- SOY position handling and EOY reconciliation

Test Organization:
- TestCurrencyFifoRGLs: Unit-level RGL verification (cost basis, proceeds, gain/loss)
- TestCurrencyFifoAggregates: Integration-level tax form aggregate verification

legal_basis: GT-FX-001 — currency gains on an interest-bearing balance are
§20 Abs. 2 Satz 1 Nr. 7 EStG income; reference/bmf-guidance/fremdwaehrung-konten.md.
Related: GT-FX-006 (short currency positions) and GT-FX-007 (currency embedded
in a securities trade), both choices under uncertainty — see
reference/research/open-legal-questions.md and docs/legal-implementation-map.md.

The controlling text is the BMF-Schreiben vom 14.05.2025, retrieved and read in
full on 2026-08-03 and reproduced verbatim in the store. Cite that date with the
Randziffer: the 14.05.2025 text is a Neufassung of BMF 19.05.2022, and whether
the older text numbered it identically is not established.

Which expectations in this file that actually grounds: the § 20 classification of
a currency balance and the FIFO lot order are verified Tier 2 (Rz. 131, GT-FX-008).
The short-position specs (CFX_S_*, CFX_IS_*) are NOT — Rz. 131 addresses Guthaben
throughout and says nothing about a negative balance, so they rest on GT-FX-006,
a choice under uncertainty (Q8). The embedded currency leg of a securities trade
is GT-FX-007, recorded as reasoned rather than sourced (Q9).
"""

import pytest
from decimal import Decimal
from typing import List, Tuple, Any, Optional


from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.expected import (
    ScenarioExpectedOutput,
    ExpectedRealizedGainLoss,
    ExpectedAssetEoyState,
)

from tests.fixtures import (
    load_yaml_spec,
    parse_currency_fifo_tests,
    CurrencyFifoTestSpec,
    get_group7_currency_fifo_tests,
    FxTradeSpec,
    SecurityTradeForFxSpec,
    CurrencyPositionSpec,
)

from src.domain.assets import person_snapshot
from src.domain.enums import RealizationType, TaxReportingCategory


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TAX_YEAR = 2023
DEFAULT_FX_RATE = Decimal("1.0")  # Default mock rate when not specified


# =============================================================================
# Spec Loading
# =============================================================================

def load_all_currency_fifo_specs() -> List[Tuple[str, CurrencyFifoTestSpec]]:
    """
    Load all currency FIFO test specs from group 7.

    Returns list of (group_name, spec) tuples for pytest parameterization.
    """
    try:
        specs = get_group7_currency_fifo_tests()
        return [("group7", spec) for spec in specs]
    except Exception as e:
        print(f"Warning: Could not load group7 specs: {e}")
        return []


ALL_CURRENCY_FIFO_SPECS = load_all_currency_fifo_specs()


def _has_rgl_expectations(spec: CurrencyFifoTestSpec) -> bool:
    """True if this spec should run in the RGL test class."""
    return bool(spec.expected_rgls) or spec.has_explicit_rgl_expectations


def _has_aggregate_expectations(spec: CurrencyFifoTestSpec) -> bool:
    """True if this spec defines non-zero aggregate expectations."""
    return (spec.expected_aggregates.kap_other_income != Decimal("0") or
            spec.expected_aggregates.kap_other_losses != Decimal("0"))


RGL_SPECS = [s for s in ALL_CURRENCY_FIFO_SPECS if _has_rgl_expectations(s[1])]
AGGREGATE_SPECS = [s for s in ALL_CURRENCY_FIFO_SPECS if _has_aggregate_expectations(s[1])]


def spec_id(item: Tuple[str, CurrencyFifoTestSpec]) -> str:
    """Generate test ID in format 'group7::CFX_L_001'."""
    group_name, spec = item
    return f"{group_name}::{spec.id}"


# =============================================================================
# Helper Functions - FX Trade CSV Generation
# =============================================================================

def create_fx_trade_csv_row(
    account_id: str,
    foreign_currency: str,
    trade_type: str,  # BUY (EUR→Foreign) or SELL (Foreign→EUR)
    foreign_amount: Decimal,
    eur_amount: Decimal,
    ecb_rate: Optional[Decimal],
    trade_date: str,
    transaction_id: str,
    trade_time: Optional[str] = None,
) -> List[Any]:
    """
    Create a CSV row for an FX trade.

    IBKR FX Pair format:
    - Symbol: e.g., "EUR.USD"
    - AssetClass: "CASH"
    - Quantity: Amount of first currency (EUR)
      - Positive = buy EUR (sell foreign)
      - Negative = sell EUR (buy foreign)
    - TradePrice: Exchange rate (foreign per EUR)
    """
    # Negative amounts are a SPEC-AUTHORING error, not a real IBKR data shape:
    # IBKR FX-pair rows encode direction in the SIGN of the EUR-leg quantity,
    # amounts in specs are absolute. Fail loudly instead of silently dropping
    # the row (a silent skip made CFX_ERR_002 test nothing since it was written (bdd9688, 2026-03-08)).
    if foreign_amount is not None and foreign_amount < Decimal("0"):
        raise ValueError(f"FX trade {transaction_id}: negative foreign_amount {foreign_amount} in spec")
    if eur_amount is not None and eur_amount < Decimal("0"):
        raise ValueError(f"FX trade {transaction_id}: negative eur_amount {eur_amount} in spec")

    symbol = f"EUR.{foreign_currency}"

    # Determine quantity direction
    if trade_type == "BUY":
        # BUY foreign = sell EUR = negative EUR quantity
        quantity = -eur_amount
    else:  # SELL
        # SELL foreign = buy EUR = positive EUR quantity
        quantity = eur_amount

    # Format trade date/time
    trade_datetime = trade_date
    if trade_time:
        trade_datetime = f"{trade_date} {trade_time}"

    # Buy/Sell indicator
    buy_sell = "SELL" if trade_type == "BUY" else "BUY"

    # Open/Close indicator - FX trades don't use this the same way
    open_close = "O"  # Default to Open

    return [
        account_id,          # ClientAccountID
        "EUR",               # CurrencyPrimary (base currency for FX)
        "CASH",              # AssetClass
        "",                  # SubCategory
        symbol,              # Symbol (e.g., EUR.USD)
        f"FX {symbol}",      # Description
        "",                  # ISIN (none for FX)
        None, None, None,    # Strike, Expiry, Put/Call
        trade_datetime,      # TradeDate
        quantity,            # Quantity (EUR amount, signed)
        ecb_rate if ecb_rate is not None else Decimal("0"),  # TradePrice (0 = missing rate, parser will skip)
        Decimal("0"),        # IBCommission (assume no commission for FX)
        "EUR",               # IBCommissionCurrency
        buy_sell,            # Buy/Sell
        transaction_id,      # TransactionID
        None, None,          # Notes/Codes, UnderlyingSymbol
        None,                # Conid (none for FX)
        None,                # UnderlyingConid
        Decimal("1"),        # Multiplier
        open_close,          # Open/CloseIndicator
    ]


def create_cross_currency_fx_trade_csv_row(
    account_id: str,
    from_currency: str,
    to_currency: str,
    from_amount: Decimal,
    to_amount: Decimal,
    trade_date: str,
    transaction_id: str,
    trade_time: Optional[str] = None,
) -> List[Any]:
    """
    Create a CSV row for a cross-currency FX trade (e.g., USD→GBP).

    IBKR format: Symbol is "FROM.TO" (e.g., "USD.GBP")
    Negative quantity = selling first currency (FROM)
    TradePrice = TO/FROM rate
    """
    symbol = f"{from_currency}.{to_currency}"
    # Selling from_currency (negative quantity)
    quantity = -from_amount
    # Rate = to_amount / from_amount (units of TO per FROM)
    rate = to_amount / from_amount

    trade_datetime = trade_date
    if trade_time:
        trade_datetime = f"{trade_date} {trade_time}"

    return [
        account_id,          # ClientAccountID
        from_currency,       # CurrencyPrimary
        "CASH",              # AssetClass
        "",                  # SubCategory
        symbol,              # Symbol (e.g., USD.GBP)
        f"FX {symbol}",      # Description
        "",                  # ISIN
        None, None, None,    # Strike, Expiry, Put/Call
        trade_datetime,      # TradeDate
        quantity,            # Quantity (from_amount, negative = selling)
        rate,                # TradePrice (to/from rate)
        Decimal("0"),        # IBCommission
        from_currency,       # IBCommissionCurrency
        "SELL",              # Buy/Sell (selling from_currency)
        transaction_id,      # TransactionID
        None, None,          # Notes/Codes, UnderlyingSymbol
        None,                # Conid
        None,                # UnderlyingConid
        Decimal("1"),        # Multiplier
        "O",                 # Open/CloseIndicator
    ]


def create_security_trade_csv_row(
    account_id: str,
    security_trade: SecurityTradeForFxSpec,
    transaction_id: str,
) -> List[Any]:
    """
    Create a CSV row for a security trade that causes implicit FX.
    """
    # Map trade type to Buy/Sell and Open/Close
    trade_type_map = {
        "BUY_LONG": ("BUY", "O"),
        "SELL_LONG": ("SELL", "C"),
        "SELL_SHORT_OPEN": ("SELL", "O"),
        "BUY_SHORT_COVER": ("BUY", "C"),
    }
    buy_sell, open_close = trade_type_map.get(security_trade.type, ("BUY", "O"))

    # Calculate quantity (signed)
    quantity = security_trade.quantity if buy_sell == "BUY" else -security_trade.quantity

    # Format trade date/time
    trade_datetime = security_trade.date
    if security_trade.time:
        trade_datetime = f"{security_trade.date} {security_trade.time}"

    return [
        account_id,                      # ClientAccountID
        security_trade.local_currency,   # CurrencyPrimary
        "STK",                           # AssetClass
        "COMMON",                        # SubCategory
        security_trade.asset_symbol,     # Symbol
        f"{security_trade.asset_symbol} Common Stock",  # Description
        security_trade.asset_isin,       # ISIN
        None, None, None,                # Strike, Expiry, Put/Call
        trade_datetime,                  # TradeDate
        quantity,                        # Quantity
        security_trade.price_foreign,    # TradePrice
        Decimal("0"),                    # IBCommission (zero to isolate currency FIFO logic from commission FX)
        security_trade.local_currency,   # IBCommissionCurrency
        buy_sell,                        # Buy/Sell
        transaction_id,                  # TransactionID
        None, None,                      # Notes/Codes, UnderlyingSymbol
        f"CON{security_trade.asset_isin[:8]}",  # Conid
        None,                            # UnderlyingConid
        Decimal("1"),                    # Multiplier
        open_close,                      # Open/CloseIndicator
    ]


def create_currency_position_csv_row(
    account_id: str,
    position: CurrencyPositionSpec,
    is_soy: bool = True,
) -> List[Any]:
    """
    Create a CSV row for a currency (CashBalance) position.
    """
    # For CashBalance assets, the symbol equals the currency
    symbol = position.currency

    # Mark price and value
    mark_price = Decimal("1")  # FX mark price
    # For short positions, use short_proceeds_eur as cost_basis (IBKR convention)
    effective_cost_basis = position.cost_basis_eur
    if position.balance < Decimal("0") and position.short_proceeds_eur:
        effective_cost_basis = position.short_proceeds_eur

    if effective_cost_basis and position.balance != Decimal("0"):
        # Derive unit cost from total cost basis
        mark_price = effective_cost_basis / abs(position.balance)

    position_value = abs(position.balance) * mark_price
    cost_basis = effective_cost_basis or Decimal("0")

    return [
        account_id,              # ClientAccountID
        position.currency,       # CurrencyPrimary
        "CASH",                  # AssetClass
        "",                      # SubCategory
        symbol,                  # Symbol (= currency code)
        f"Cash Balance {position.currency}",  # Description
        "",                      # ISIN
        position.balance,        # Quantity
        position_value,          # PositionValue
        mark_price,              # MarkPrice
        cost_basis,              # CostBasisMoney
        None,                    # UnderlyingSymbol
        None,                    # Conid
        None,                    # UnderlyingConid
        Decimal("1"),            # Multiplier
    ]


# =============================================================================
# Spec to Pipeline Conversion
# =============================================================================

def spec_to_trades_data(
    spec: CurrencyFifoTestSpec,
    account_id: str,
    tax_year: int,
) -> List[List[Any]]:
    """
    Convert currency FIFO spec to pipeline trades input format.
    """
    trades_data = []

    # Get default currency from spec (for FX trades without explicit foreign_currency)
    default_currency = "USD"  # Default
    if spec.currency_positions_soy:
        default_currency = spec.currency_positions_soy[0].currency

    # Add FX trades
    for i, fx_trade in enumerate(spec.fx_trades):
        if fx_trade.type == "CROSS_CURRENCY":
            # Cross-currency: neither side is EUR (e.g., USD→GBP)
            trades_data.append(create_cross_currency_fx_trade_csv_row(
                account_id=account_id,
                from_currency=fx_trade.foreign_currency or default_currency,
                to_currency=fx_trade.to_currency or "GBP",
                from_amount=fx_trade.foreign_amount,
                to_amount=fx_trade.eur_amount,  # eur_amount holds to_amount for cross-currency
                trade_date=fx_trade.date,
                transaction_id=f"FX_T_{i:04d}",
                trade_time=fx_trade.time,
            ))
        else:
            # Standard EUR↔Foreign trade
            foreign_currency = fx_trade.foreign_currency or default_currency
            csv_row = create_fx_trade_csv_row(
                account_id=account_id,
                foreign_currency=foreign_currency,
                trade_type=fx_trade.type,
                foreign_amount=fx_trade.foreign_amount,
                eur_amount=fx_trade.eur_amount,
                ecb_rate=fx_trade.ecb_rate,
                trade_date=fx_trade.date,
                transaction_id=f"FX_T_{i:04d}",
                trade_time=fx_trade.time,
            )
            trades_data.append(csv_row)

    # Add security trades (for implicit FX)
    for i, sec_trade in enumerate(spec.security_trades):
        trades_data.append(create_security_trade_csv_row(
            account_id=account_id,
            security_trade=sec_trade,
            transaction_id=f"SEC_T_{i:04d}",
        ))

    return trades_data


def spec_to_cash_balance_data(
    spec: CurrencyFifoTestSpec,
    account_id: str,
    tax_year: int,
) -> List[List[Any]]:
    """
    Convert currency positions to cash balance CSV format for FIFO initialization.

    Cash balance CSV format: ClientAccountID, CurrencyPrimary, FromDate, ToDate,
                            StartingCash, EndingCash
    """
    cash_balance_data = []

    # Build a map from currency to (soy_balance, eoy_balance)
    currency_balances = {}

    for position in spec.currency_positions_soy:
        currency_balances[position.currency] = {
            "soy": position.balance,
            "eoy": Decimal("0"),
        }

    for eoy_state in spec.expected_eoy_states:
        if eoy_state.currency not in currency_balances:
            currency_balances[eoy_state.currency] = {"soy": Decimal("0"), "eoy": Decimal("0")}
        currency_balances[eoy_state.currency]["eoy"] = eoy_state.quantity

    # Create CSV rows
    from_date = f"{tax_year}0101"  # YYYYMMDD format
    to_date = f"{tax_year}1231"

    for currency, balances in currency_balances.items():
        cash_balance_data.append([
            account_id,          # ClientAccountID
            currency,            # CurrencyPrimary
            from_date,           # FromDate
            to_date,             # ToDate
            balances["soy"],     # StartingCash
            balances["eoy"],     # EndingCash
        ])

    return cash_balance_data


def spec_to_positions_soy_data(
    spec: CurrencyFifoTestSpec,
    account_id: str,
) -> List[List[Any]]:
    """
    Convert SOY positions from spec to pipeline positions input format.

    This includes:
    1. Currency positions from currency_positions_soy (with cost basis for FIFO)
    2. Security positions for trades that close existing positions
    """
    positions_data = []

    # Add currency SOY positions with cost basis for FIFO initialization
    for currency_pos in spec.currency_positions_soy:
        positions_data.append(create_currency_position_csv_row(
            account_id=account_id,
            position=currency_pos,
            is_soy=True,
        ))

    # Add security positions for implicit FX tests
    for sec_trade in spec.security_trades:
        # Create SOY position for securities that will be sold
        if sec_trade.type in ("SELL_LONG", "BUY_SHORT_COVER"):
            positions_data.append([
                account_id,                      # ClientAccountID
                sec_trade.local_currency,        # CurrencyPrimary
                "STK",                           # AssetClass
                "COMMON",                        # SubCategory
                sec_trade.asset_symbol,          # Symbol
                f"{sec_trade.asset_symbol} Stock",  # Description
                sec_trade.asset_isin,            # ISIN
                sec_trade.quantity,              # Quantity (SOY position)
                Decimal("0"),                    # PositionValue
                sec_trade.price_foreign,         # MarkPrice
                Decimal("0"),                    # CostBasisMoney
                None,                            # UnderlyingSymbol
                f"CON{sec_trade.asset_isin[:8]}",  # Conid
                None,                            # UnderlyingConid
                Decimal("1"),                    # Multiplier
            ])

    return positions_data


def spec_to_positions_eoy_data(
    spec: CurrencyFifoTestSpec,
    account_id: str,
) -> List[List[Any]]:
    """
    Generate EOY positions based on expected EOY states in the spec.

    This includes:
    1. Currency positions from expected_eoy_states
    2. Security positions created by BUY_LONG or SELL_SHORT_OPEN trades
    """
    positions_data = []

    # Add currency EOY positions
    for eoy_state in spec.expected_eoy_states:
        if eoy_state.quantity != Decimal("0"):
            # Create a CurrencyPositionSpec for the EOY state
            eoy_pos = CurrencyPositionSpec(
                currency=eoy_state.currency,
                balance=eoy_state.quantity,
            )
            positions_data.append(create_currency_position_csv_row(
                account_id=account_id,
                position=eoy_pos,
                is_soy=False,
            ))

    # Add security EOY positions for trades that create positions
    # BUY_LONG creates a long position, SELL_SHORT_OPEN creates a short position
    for sec_trade in spec.security_trades:
        if sec_trade.type == "BUY_LONG":
            # Long position created - positive quantity at EOY
            positions_data.append([
                account_id,                      # ClientAccountID
                sec_trade.local_currency,        # CurrencyPrimary
                "STK",                           # AssetClass
                "COMMON",                        # SubCategory
                sec_trade.asset_symbol,          # Symbol
                f"{sec_trade.asset_symbol} Common Stock",  # Description
                sec_trade.asset_isin,            # ISIN
                sec_trade.quantity,              # Quantity (positive for long)
                Decimal("0"),                    # PositionValue
                sec_trade.price_foreign,         # MarkPrice
                Decimal("0"),                    # CostBasisMoney
                None,                            # UnderlyingSymbol
                f"CON{sec_trade.asset_isin[:8]}",  # Conid
                None,                            # UnderlyingConid
                Decimal("1"),                    # Multiplier
            ])
        elif sec_trade.type == "SELL_SHORT_OPEN":
            # Short position created - negative quantity at EOY
            positions_data.append([
                account_id,                      # ClientAccountID
                sec_trade.local_currency,        # CurrencyPrimary
                "STK",                           # AssetClass
                "COMMON",                        # SubCategory
                sec_trade.asset_symbol,          # Symbol
                f"{sec_trade.asset_symbol} Common Stock",  # Description
                sec_trade.asset_isin,            # ISIN
                -sec_trade.quantity,             # Quantity (negative for short)
                Decimal("0"),                    # PositionValue
                sec_trade.price_foreign,         # MarkPrice
                Decimal("0"),                    # CostBasisMoney
                None,                            # UnderlyingSymbol
                f"CON{sec_trade.asset_isin[:8]}",  # Conid
                None,                            # UnderlyingConid
                Decimal("1"),                    # Multiplier
            ])
        # SELL_LONG and BUY_SHORT_COVER close positions (EOY qty = 0, no record needed)

    return positions_data


def spec_to_expected_outcome(
    spec: CurrencyFifoTestSpec,
) -> ScenarioExpectedOutput:
    """
    Convert spec expectations to ScenarioExpectedOutput for RGL verification.
    """
    expected_rgls = []

    for rgl in spec.expected_rgls:
        # Map realization type
        realization_type = rgl.realization_type

        # Determine tax category
        tax_category = rgl.tax_category
        if not tax_category:
            if rgl.gain_loss_eur and rgl.gain_loss_eur >= Decimal("0"):
                tax_category = TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE.name
            else:
                tax_category = TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE.name

        # Build kwargs for ExpectedRealizedGainLoss
        # Note: acquisition_date is not included because the positions CSV format
        # doesn't support acquisition dates, and the system uses fallback dates.
        # When historical trade simulation is implemented, this can be added back.
        rgl_kwargs = {
            "tax_reporting_category": tax_category,
            "realization_type": realization_type,
        }

        expected_rgls.append(
            ExpectedRealizedGainLoss(
                asset_identifier=f"CASH_BALANCE:{rgl.currency}",
                realization_date=rgl.realization_date or "",
                quantity_realized=rgl.quantity,
                total_cost_basis_eur=rgl.total_cost_basis_eur or Decimal("0"),
                total_realization_value_eur=rgl.total_proceeds_eur or Decimal("0"),
                gross_gain_loss_eur=rgl.gain_loss_eur or Decimal("0"),
                **rgl_kwargs,
            )
        )

    # Build EOY states
    expected_eoy_states = []
    for eoy_state in spec.expected_eoy_states:
        expected_eoy_states.append(
            ExpectedAssetEoyState(
                asset_identifier=f"SYMBOL:{eoy_state.currency}",
                eoy_quantity=eoy_state.quantity,
            )
        )

    return ScenarioExpectedOutput(
        test_description=f"{spec.id}: {spec.description}",
        expected_rgls=expected_rgls,
        expected_eoy_states=expected_eoy_states,
        expected_eoy_mismatch_error_count=spec.expected_errors,
    )


# =============================================================================
# Mock Rate Provider for Currency Tests
# =============================================================================

class CurrencyTestRateProvider(MockECBExchangeRateProvider):
    """
    Mock rate provider that returns rates from the test spec.

    For currency FIFO tests, we need the provider to return the ECB rate
    that was active on each trade date.

    ECB rates are in format: 1 EUR = X Foreign (e.g., 1 EUR = 1.10 USD)
    The get_rate() method returns this same value.
    """

    def __init__(self, spec: CurrencyFifoTestSpec):
        # Use a default rate as fallback (1 EUR = 1.10 Foreign)
        super().__init__(foreign_to_eur_init_value=Decimal("0.909090909"))  # 1/1.10
        self.spec = spec
        self._build_rate_map()

    def _build_rate_map(self):
        """Build a map of date+currency to ECB rate from spec trades."""
        self.rate_map: dict = {}

        for fx_trade in self.spec.fx_trades:
            # Skip trades with missing rates (ecb_rate=None)
            if fx_trade.ecb_rate is None:
                continue
            # Get the currency from the trade or fall back to first SOY currency
            currency = fx_trade.foreign_currency
            if not currency and self.spec.currency_positions_soy:
                currency = self.spec.currency_positions_soy[0].currency
            if currency:
                key = (fx_trade.date, currency.upper())
                self.rate_map[key] = fx_trade.ecb_rate
            # For cross-currency trades, also register the target currency rate
            if fx_trade.to_currency and fx_trade.ecb_rate_to:
                key = (fx_trade.date, fx_trade.to_currency.upper())
                self.rate_map[key] = fx_trade.ecb_rate_to

        for sec_trade in self.spec.security_trades:
            key = (sec_trade.date, sec_trade.local_currency.upper())
            self.rate_map[key] = sec_trade.ecb_rate

        # Register fallback rates from SOY positions (used for SOY lot initialization)
        for soy_pos in self.spec.currency_positions_soy:
            if soy_pos.fallback_ecb_rate and soy_pos.currency.upper() != "EUR":
                # Register for Jan 1 of tax year (SOY initialization date)
                key = (f"{DEFAULT_TAX_YEAR - 1}-12-31", soy_pos.currency.upper())
                self.rate_map[key] = soy_pos.fallback_ecb_rate
                # Also register for Jan 1 in case pipeline uses that date
                key = (f"{DEFAULT_TAX_YEAR}-01-01", soy_pos.currency.upper())
                self.rate_map[key] = soy_pos.fallback_ecb_rate

    def get_rate(self, date_of_conversion, currency_code: str) -> Optional[Decimal]:
        """
        Get the exchange rate for converting currency_code to EUR.

        Returns the rate as "foreign currency units per 1 EUR" (ECB format).
        Example: If 1 EUR = 1.10 USD, this returns Decimal("1.10").
        """
        from datetime import date as date_type

        currency_upper = currency_code.upper()

        if currency_upper == "EUR":
            return Decimal("1.0")

        # Convert date_of_conversion to string format used in rate_map
        if isinstance(date_of_conversion, date_type):
            date_str = date_of_conversion.strftime("%Y-%m-%d")
        else:
            date_str = str(date_of_conversion)

        # Look up in rate map
        key = (date_str, currency_upper)
        if key in self.rate_map:
            return self.rate_map[key]

        # Fall back to parent's method
        return super().get_rate(date_of_conversion, currency_code)


# =============================================================================
# Test Classes
# =============================================================================

class TestCurrencyFifoRGLs(FifoTestCaseBase):
    """
    Unit-level RGL verification for currency FIFO tests.

    Tests that the currency conversion processor generates correct RGLs:
    - Cost basis from FIFO lot matching
    - Proceeds from conversion rates
    - Gain/loss calculations
    - Acquisition and realization dates
    """

    def assert_currency_rgls(self,
                              actual_results,
                              expected_test_outcome: ScenarioExpectedOutput):
        """
        Compare currency-only RGLs (CASH_BALANCE assets) against expected.

        This filters out stock/option/other RGLs from the comparison since
        currency FIFO tests only specify expected currency RGLs in the YAML.

        For currency tests, we use a relaxed matching that:
        - Always compares: date, quantity, gain/loss
        - Optionally compares: cost/proceeds (only if non-zero in expected)
        """
        from src.domain.enums import AssetCategory
        from src import config as app_config

        # Check EOY mismatch errors
        assert actual_results.eoy_mismatch_error_count == expected_test_outcome.expected_eoy_mismatch_error_count, \
            (f"EOY mismatch error count: Expected {expected_test_outcome.expected_eoy_mismatch_error_count}, "
             f"Got {actual_results.eoy_mismatch_error_count}")

        # Filter actual RGLs to only include CASH_BALANCE assets
        currency_rgls = [
            rgl for rgl in actual_results.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        # Check count
        assert len(currency_rgls) == len(expected_test_outcome.expected_rgls), \
            (f"Number of currency RGLs: Expected {len(expected_test_outcome.expected_rgls)}, "
             f"Got {len(currency_rgls)}. "
             f"Currency RGLs: {currency_rgls}")

        def matches_currency_rgl(expected, actual, resolver) -> bool:
            """Match currency RGL with relaxed comparison for optional fields."""
            # Check asset identifier (CASH_BALANCE:XXX)
            asset = resolver.get_asset_by_id(actual.asset_internal_id)
            if not asset:
                return False

            # Check for CASH_BALANCE:XXX alias match
            if not any(alias == expected.asset_identifier for alias in asset.aliases):
                return False

            # Always compare: date, quantity, gain/loss
            if str(actual.realization_date) != expected.realization_date:
                return False

            # Allow small tolerance for quantity (0.01 for rounding differences)
            qty_diff = abs(actual.quantity_realized - expected.quantity_realized)
            if qty_diff > Decimal("0.01"):
                print(f"  Qty mismatch: expected {expected.quantity_realized}, got {actual.quantity_realized} (diff: {qty_diff})")
                return False

            actual_gain = actual.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
            # Allow small tolerance (0.01 EUR) for rounding differences
            gain_diff = abs(actual_gain - expected.gross_gain_loss_eur)
            if gain_diff > Decimal("0.01"):
                print(f"  Gain mismatch: expected {expected.gross_gain_loss_eur}, got {actual_gain} (diff: {gain_diff})")
                return False

            # Optionally compare: cost/proceeds (only if specified, i.e., non-zero in expected)
            if expected.total_cost_basis_eur != Decimal("0"):
                actual_cost = actual.total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
                if actual_cost.compare(expected.total_cost_basis_eur) != Decimal("0"):
                    print(f"  Cost mismatch: expected {expected.total_cost_basis_eur}, got {actual_cost}")
                    return False

            if expected.total_realization_value_eur != Decimal("0"):
                actual_proceeds = actual.total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
                if actual_proceeds.compare(expected.total_realization_value_eur) != Decimal("0"):
                    print(f"  Proceeds mismatch: expected {expected.total_realization_value_eur}, got {actual_proceeds}")
                    return False

            return True

        # Match each expected RGL to an actual one
        matched_indices = [False] * len(currency_rgls)
        for expected_rgl in expected_test_outcome.expected_rgls:
            found_match = False
            for i, actual_rgl in enumerate(currency_rgls):
                if matched_indices[i]:
                    continue
                if matches_currency_rgl(expected_rgl, actual_rgl, actual_results.asset_resolver):
                    matched_indices[i] = True
                    found_match = True
                    break

            assert found_match, \
                f"No matching actual RGL found for expected RGL: {expected_rgl}. \n" \
                f"Currency RGLs were: {currency_rgls}"

        # Check for unmatched actual RGLs
        unmatched = [currency_rgls[i] for i, m in enumerate(matched_indices) if not m]
        if unmatched:
            pytest.fail(f"Found {len(unmatched)} unmatched currency RGL(s): {unmatched}")

    def assert_currency_eoy_states(self,
                                    actual_results,
                                    expected_test_outcome: ScenarioExpectedOutput):
        """
        Verify EOY ledger state for currency (CashBalance) assets.

        Checks that after processing, the remaining currency quantity matches
        expectations. This ensures FIFO lot consumption is correct and the
        carry-forward basis for next year will be accurate.
        """
        from src.domain.enums import AssetCategory

        all_actual_assets = list(actual_results.asset_resolver.assets_by_internal_id.values())
        # Filter to CashBalance assets only
        currency_assets = [
            a for a in all_actual_assets
            if a.asset_category == AssetCategory.CASH_BALANCE
        ]

        for expected_eoy_state in expected_test_outcome.expected_eoy_states:
            found_match = False
            for actual_asset in currency_assets:
                if expected_eoy_state.matches(actual_asset, actual_results.eoy_positions):
                    found_match = True
                    break

            assert found_match, \
                (f"EOY state check failed for '{expected_eoy_state.asset_identifier}': "
                 f"expected quantity {expected_eoy_state.eoy_quantity}. "
                 f"Currency assets: {[(a.ibkr_symbol, person_snapshot(actual_results.eoy_positions, a.internal_asset_id)) for a in currency_assets]}")

    @pytest.mark.parametrize(
        "group_spec",
        RGL_SPECS,
        ids=spec_id,
    )
    def test_currency_fifo_rgls(self, group_spec: Tuple[str, CurrencyFifoTestSpec], mock_config_paths):
        """Execute a currency FIFO test case from Group 7."""
        group_name, spec = group_spec

        # Skip tests marked with skip flag
        if spec.skip:
            pytest.skip(spec.skip_reason or "Test marked as skip")

        account_id = f"U_{group_name.upper()}_TEST"
        tax_year = DEFAULT_TAX_YEAR

        # Convert spec to pipeline inputs
        trades_data = spec_to_trades_data(spec, account_id, tax_year)
        positions_start = spec_to_positions_soy_data(spec, account_id)
        positions_end = spec_to_positions_eoy_data(spec, account_id)
        cash_balance_data = spec_to_cash_balance_data(spec, account_id, tax_year)

        # Build expected outcome
        expected = spec_to_expected_outcome(spec)

        # Use mock rate provider with spec-defined rates
        mock_rate_provider = CurrencyTestRateProvider(spec)

        # Tests that expect a pipeline error (e.g., DataIntegrityError for corrupt data)
        if spec.expect_pipeline_error:
            # "data integrity" only pins THAT the pipeline refused. A spec that
            # names the condition it is about pins WHY, via expect_pipeline_error_match.
            expected_match = spec.expect_pipeline_error_match or "data integrity"
            with pytest.raises(pytest.fail.Exception, match=expected_match):
                self._run_pipeline(
                    trades_data=trades_data,
                    positions_start_data=positions_start,
                    positions_end_data=positions_end,
                    cash_balance_data=cash_balance_data,
                    custom_rate_provider=mock_rate_provider,
                    tax_year=tax_year,
                )
            return

        actual = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start,
            positions_end_data=positions_end,
            cash_balance_data=cash_balance_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=tax_year,
        )

        # Use currency-specific assertion that filters out stock/option RGLs
        self.assert_currency_rgls(actual, expected)

        # Verify EOY ledger state (WP-4)
        if expected.expected_eoy_states:
            self.assert_currency_eoy_states(actual, expected)


class TestCurrencyFifoAggregates(FifoTestCaseBase):
    """
    Integration-level tax form aggregate verification.

    Tests that currency RGLs are correctly aggregated into tax form lines:
    - kap_other_income (Anlage KAP Zeile 19 positive)
    - kap_other_losses (Anlage KAP Zeile 19 negative, absolute value)

    Uses LossOffsettingEngine to verify the full pipeline from RGL generation
    through to tax form line aggregation.
    """

    @pytest.mark.parametrize(
        "group_spec",
        AGGREGATE_SPECS,
        ids=spec_id,
    )
    def test_currency_fifo_aggregates(self, group_spec: Tuple[str, CurrencyFifoTestSpec], mock_config_paths):
        """Verify tax form aggregates for currency FIFO tests."""
        from src.engine.loss_offsetting import LossOffsettingEngine
        from src.domain.enums import TaxReportingCategory, AssetCategory

        group_name, spec = group_spec

        # Skip tests marked with skip flag
        if spec.skip:
            pytest.skip(spec.skip_reason or "Test marked as skip")

        account_id = f"U_{group_name.upper()}_TEST"
        tax_year = DEFAULT_TAX_YEAR

        # Convert spec to pipeline inputs
        trades_data = spec_to_trades_data(spec, account_id, tax_year)
        positions_start = spec_to_positions_soy_data(spec, account_id)
        positions_end = spec_to_positions_eoy_data(spec, account_id)
        cash_balance_data = spec_to_cash_balance_data(spec, account_id, tax_year)

        # Use mock rate provider with spec-defined rates
        mock_rate_provider = CurrencyTestRateProvider(spec)

        actual = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start,
            positions_end_data=positions_end,
            cash_balance_data=cash_balance_data,
            custom_rate_provider=mock_rate_provider,
            tax_year=tax_year,
        )

        # Filter to only CASH_BALANCE RGLs for FX aggregate verification
        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]

        # Run LossOffsettingEngine on currency RGLs only
        loss_engine = LossOffsettingEngine(
            realized_gains_losses=currency_rgls,
            vorabpauschale_items=[],
            current_year_financial_events=[],
            asset_resolver=actual.asset_resolver,
            tax_year=tax_year,
        )
        figures = loss_engine.calculate_reporting_figures()

        # Verify aggregate values
        actual_income = figures.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE, Decimal("0")
        )
        actual_losses = figures.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE, Decimal("0")
        )

        from src import config as app_config
        assert actual_income.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == \
            spec.expected_aggregates.kap_other_income, \
            (f"kap_other_income: Expected {spec.expected_aggregates.kap_other_income}, "
             f"Got {actual_income.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)}")

        assert actual_losses.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) == \
            spec.expected_aggregates.kap_other_losses, \
            (f"kap_other_losses: Expected {spec.expected_aggregates.kap_other_losses}, "
             f"Got {actual_losses.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)}")


# =============================================================================
# Spec Loading Verification
# =============================================================================

class TestSpecRowBuilderRejectsNegativeAmounts:
    """The row builder raises on a negative spec amount instead of dropping the row.

    legal_basis: infrastructure. No declared figure depends on this test — but the
    behaviour it pins is why other tests in this file can be trusted. The builder
    used to log and return None, so a spec authored with a negative amount produced
    no CSV row at all and its expectations were satisfied by the engine never
    running. CFX_ERR_002 sat in that state and asserted nothing.

    Real IBKR FX-pair rows encode direction in the sign of the EUR-leg quantity, so
    an amount in a spec is absolute by definition and a negative one is an authoring
    error, not an input shape to model.
    """

    def test_negative_foreign_amount_raises(self):
        with pytest.raises(ValueError, match="negative foreign_amount"):
            create_fx_trade_csv_row(
                account_id="U_TEST", foreign_currency="USD", trade_type="SELL_FOREIGN",
                foreign_amount=Decimal("-500.00"), eur_amount=Decimal("450.00"),
                ecb_rate=Decimal("1.11"), trade_date="2023-06-01", transaction_id="FX_NEG_1",
            )

    def test_negative_eur_amount_raises(self):
        with pytest.raises(ValueError, match="negative eur_amount"):
            create_fx_trade_csv_row(
                account_id="U_TEST", foreign_currency="USD", trade_type="SELL_FOREIGN",
                foreign_amount=Decimal("500.00"), eur_amount=Decimal("-450.00"),
                ecb_rate=Decimal("1.11"), trade_date="2023-06-01", transaction_id="FX_NEG_2",
            )


class TestCurrencyFifoSpecsLoaded:
    """Verify that currency FIFO specs are loaded correctly."""

    def test_specs_loaded(self):
        """Verify specs are loaded."""
        assert len(ALL_CURRENCY_FIFO_SPECS) > 0, "No currency FIFO specs loaded"

    def test_explicit_fx_specs_exist(self):
        """Verify explicit FX trade specs exist."""
        explicit_specs = [s for g, s in ALL_CURRENCY_FIFO_SPECS if s.id.startswith("CFX_L_") or s.id.startswith("CFX_S_")]
        assert len(explicit_specs) >= 5, f"Expected at least 5 explicit FX specs, got {len(explicit_specs)}"

    def test_soy_specs_exist(self):
        """Verify SOY handling specs exist."""
        soy_specs = [s for g, s in ALL_CURRENCY_FIFO_SPECS if "SOY" in s.id]
        assert len(soy_specs) >= 2, f"Expected at least 2 SOY specs, got {len(soy_specs)}"

    def test_ids_follow_naming_convention(self):
        """Verify spec IDs follow CFX_ naming convention."""
        for group, spec in ALL_CURRENCY_FIFO_SPECS:
            assert spec.id.startswith("CFX_"), f"Spec {spec.id} should start with CFX_"

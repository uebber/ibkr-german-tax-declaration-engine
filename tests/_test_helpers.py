"""
Shared Test Helpers for FIFO Test Groups 1-5

This module contains shared configuration, helper functions, and utilities
used across all FIFO test groups.

Extracted from the original combined test file to enable separate test files
per group while avoiding code duplication.
"""

from decimal import Decimal
from typing import List, Optional
from datetime import date

# Test infrastructure imports
from tests.fifo_scenarios.test_case_base import FifoTestCaseBase
from tests.results.test_result_defs import (
    ScenarioExpectedOutput,
    ExpectedRealizedGainLoss,
    ExpectedAssetEoyState,
)
from tests.helpers.mock_providers import MockECBExchangeRateProvider
from src.domain.enums import AssetCategory, TaxReportingCategory, RealizationType

# Spec imports
from tests.specs import (
    load_yaml_spec,
    parse_fifo_tests,
    FifoTestSpec,
    TradeSpec,
    ExpectedRGLSpec,
)


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_TAX_YEAR = 2023
HISTORICAL_YEAR = DEFAULT_TAX_YEAR - 1
COMMISSION = Decimal("1.00")  # Commission per trade (absolute value)
COMMISSION_EUR = Decimal("-1.00")
COMMISSION_USD = Decimal("-1.00")
DEFAULT_FX_RATE = Decimal("2.0")  # 1 USD = 2 EUR

# Trade type mappings
TRADE_TYPE_MAP = {
    "BL": ("BUY", "O"),    # Buy Long Open
    "SL": ("SELL", "C"),   # Sell Long Close
    "SSO": ("SELL", "O"),  # Sell Short Open
    "BSC": ("BUY", "C"),   # Buy Short Cover
}

REALIZATION_TYPE_MAP = {
    "SOLD_LONG": RealizationType.LONG_POSITION_SALE.name,
    "COV_SHORT": RealizationType.SHORT_POSITION_COVER.name,
}


# =============================================================================
# Currency and FX Helpers
# =============================================================================

def get_spec_currency(spec: FifoTestSpec) -> str:
    """
    Derive currency from spec's SOY position or first trade.

    Priority:
    1. SOY position currency
    2. First intra-year trade currency
    3. First historical trade currency
    4. Default to EUR
    """
    if spec.positions_soy and spec.positions_soy.currency:
        return spec.positions_soy.currency
    if spec.intra_year_trades:
        return spec.intra_year_trades[0].currency
    if spec.historical_trades:
        return spec.historical_trades[0].currency
    return "EUR"


def get_fx_rate_for_currency(currency: str) -> Decimal:
    """Get FX rate based on currency. Non-EUR currencies use DEFAULT_FX_RATE."""
    return DEFAULT_FX_RATE if currency != "EUR" else Decimal("1")


def get_eoy_file_quantity(spec: FifoTestSpec) -> Decimal:
    """
    Get the EOY quantity to use when creating the EOY position file.

    This is the broker-reported quantity that the engine will read for reconciliation.

    Priority:
    1. positions_eoy_report.quantity (explicit broker report - semantic INPUT)
    2. expected_eoy_quantity (fallback for backward compatibility)

    This separation ensures:
    - positions_eoy_report represents what the broker says (input)
    - expected_eoy_quantity represents what asset.eoy_quantity should be (output)
    - For most tests they're equal, but the semantic distinction is clear
    """
    if spec.positions_eoy_report is not None:
        return spec.positions_eoy_report.quantity
    return spec.expected_eoy_quantity


# =============================================================================
# Expected Value Computation Helpers
# =============================================================================

def compute_cost_basis_from_trades(
    trades: List[TradeSpec],
    quantity_sold: Decimal,
    is_short: bool = False,
) -> Decimal:
    """
    Compute cost basis from historical/intra-year trades using FIFO.

    For long positions: cost = (qty * price) + commission
    For short positions: this calculates proceeds from short sale
    """
    remaining_qty = quantity_sold
    total_cost = Decimal("0")

    for trade in trades:
        if is_short:
            # For short positions, we look for SSO trades
            if trade.type != "SSO":
                continue
        else:
            # For long positions, we look for BL trades
            if trade.type != "BL":
                continue

        qty_from_this_lot = min(trade.qty, remaining_qty)
        if qty_from_this_lot <= 0:
            continue

        # Cost per share including commission allocation
        cost_per_share = trade.price + (COMMISSION / trade.qty)
        total_cost += qty_from_this_lot * cost_per_share

        remaining_qty -= qty_from_this_lot
        if remaining_qty <= 0:
            break

    return total_cost


def compute_proceeds_from_trades(
    trades: List[TradeSpec],
    quantity_sold: Decimal,
    is_short: bool = False,
) -> Decimal:
    """
    Compute proceeds from sale/cover trades.

    For long positions: proceeds from SL trades
    For short positions: proceeds from original SSO trades (stored as cost basis)
    """
    remaining_qty = quantity_sold
    total_proceeds = Decimal("0")

    for trade in trades:
        if is_short:
            # For short covers, proceeds come from original short sale (SSO)
            if trade.type != "SSO":
                continue
            qty_from_this_lot = min(trade.qty, remaining_qty)
            if qty_from_this_lot <= 0:
                continue
            # Proceeds per share minus commission allocation
            proceeds_per_share = trade.price - (COMMISSION / trade.qty)
            total_proceeds += qty_from_this_lot * proceeds_per_share
        else:
            # For long sales, proceeds from SL trades
            if trade.type != "SL":
                continue
            qty_from_this_lot = min(trade.qty, remaining_qty)
            if qty_from_this_lot <= 0:
                continue
            # Single sale proceeds: (qty * price) - commission
            total_proceeds = trade.qty * trade.price - COMMISSION

        remaining_qty -= qty_from_this_lot
        if remaining_qty <= 0:
            break

    return total_proceeds


def compute_expected_financials(
    spec: FifoTestSpec,
    rgl_spec: ExpectedRGLSpec,
    fx_rate: Decimal,
) -> tuple:
    """
    Compute expected cost basis, proceeds, and gain/loss in EUR.

    Returns: (cost_basis_eur, proceeds_eur, gain_loss_eur)

    Strategy:
    1. If all three values are provided in spec, use them as-is
    2. If gain_loss_eur is provided but cost/proceeds are not, compute cost
       from inputs and derive proceeds from: proceeds = cost + gain
    3. If nothing is provided, compute all from inputs (may not be accurate
       for multi-RGL scenarios, but provides a fallback)
    """
    is_short = rgl_spec.realization_type == "COV_SHORT"
    qty = rgl_spec.quantity or Decimal("0")

    # Case 1: All values are provided in spec - use them directly
    if (rgl_spec.total_cost_basis_eur is not None and
        rgl_spec.total_proceeds_eur is not None and
        rgl_spec.gain_loss_eur is not None):
        return (
            rgl_spec.total_cost_basis_eur,
            rgl_spec.total_proceeds_eur,
            rgl_spec.gain_loss_eur,
        )

    # Case 2: gain_loss_eur provided but cost/proceeds are not
    # This is common for multi-RGL scenarios where FIFO splits trades
    if rgl_spec.gain_loss_eur is not None:
        gain_loss_eur = rgl_spec.gain_loss_eur

        # Compute cost from inputs
        cost_foreign = _compute_cost_for_rgl(spec, rgl_spec, qty, is_short)
        cost_basis_eur = cost_foreign * fx_rate

        # Override with spec value if provided
        if rgl_spec.total_cost_basis_eur is not None:
            cost_basis_eur = rgl_spec.total_cost_basis_eur

        # Derive proceeds from cost + gain to ensure consistency
        if rgl_spec.total_proceeds_eur is not None:
            proceeds_eur = rgl_spec.total_proceeds_eur
        else:
            proceeds_eur = cost_basis_eur + gain_loss_eur

        return (cost_basis_eur, proceeds_eur, gain_loss_eur)

    # Case 3: Nothing provided - compute everything from inputs
    # This may not be accurate for multi-RGL scenarios
    cost_foreign = _compute_cost_for_rgl(spec, rgl_spec, qty, is_short)
    proceeds_foreign = _compute_proceeds_for_rgl(spec, rgl_spec, qty, is_short)

    cost_basis_eur = cost_foreign * fx_rate
    proceeds_eur = proceeds_foreign * fx_rate
    gain_loss_eur = proceeds_eur - cost_basis_eur

    return (cost_basis_eur, proceeds_eur, gain_loss_eur)


def _compute_cost_for_rgl(
    spec: FifoTestSpec,
    rgl_spec: ExpectedRGLSpec,
    qty: Decimal,
    is_short: bool,
) -> Decimal:
    """Compute cost basis in foreign currency for a single RGL."""
    if is_short:
        # For shorts, "cost" is the cover trade(s)
        for trade in spec.intra_year_trades:
            if trade.type == "BSC":
                # Pro-rate if RGL qty differs from trade qty
                return qty * trade.price + COMMISSION * (qty / trade.qty)
        return Decimal("0")

    # For longs, cost comes from buy trades or SOY fallback
    # Check if we have sufficient historical trades
    has_sufficient_historical = False
    if spec.historical_trades:
        hist_qty = sum(t.qty for t in spec.historical_trades if t.type == "BL")
        soy_qty = abs(spec.positions_soy.quantity) if spec.positions_soy else Decimal("0")
        has_sufficient_historical = hist_qty >= soy_qty and soy_qty > 0

    if has_sufficient_historical:
        return compute_cost_basis_from_trades(spec.historical_trades or [], qty, is_short=False)
    elif spec.positions_soy:
        per_share = spec.positions_soy.cost_basis / abs(spec.positions_soy.quantity)
        return qty * per_share
    else:
        return compute_cost_basis_from_trades(spec.intra_year_trades, qty, is_short=False)


def _compute_proceeds_for_rgl(
    spec: FifoTestSpec,
    rgl_spec: ExpectedRGLSpec,
    qty: Decimal,
    is_short: bool,
) -> Decimal:
    """Compute proceeds in foreign currency for a single RGL."""
    if is_short:
        # For shorts, proceeds come from original short sale (historical or SOY)
        if spec.historical_trades:
            hist_qty = sum(t.qty for t in spec.historical_trades if t.type == "SSO")
            soy_qty = abs(spec.positions_soy.quantity) if spec.positions_soy else Decimal("0")
            if hist_qty >= soy_qty and soy_qty > 0:
                return compute_proceeds_from_trades(spec.historical_trades or [], qty, is_short=True)
        if spec.positions_soy:
            per_share = spec.positions_soy.cost_basis / abs(spec.positions_soy.quantity)
            return qty * per_share
        return Decimal("0")

    # For longs, proceeds come from sale trade(s)
    for trade in spec.intra_year_trades:
        if trade.type == "SL":
            # Pro-rate if RGL qty differs from trade qty
            return qty * trade.price - COMMISSION * (qty / trade.qty)
    return Decimal("0")


# =============================================================================
# Spec Conversion Helpers
# =============================================================================

def load_group_specs(group_filename: str) -> List[FifoTestSpec]:
    """Load and parse specs from a YAML file."""
    try:
        spec_data = load_yaml_spec(group_filename)
        return parse_fifo_tests(spec_data)
    except FileNotFoundError:
        return []


def spec_to_trades_data(
    spec: FifoTestSpec,
    account_id: str,
    tax_year: int,
    include_historical: bool = True,
) -> List[List]:
    """
    Convert spec trades to pipeline input format.

    Note: If time is provided, it's appended to the date for same-day ordering.
    """
    trades_data = []
    commission = Decimal("-1.00")

    # Add historical trades if present
    if include_historical and spec.historical_trades:
        for i, trade in enumerate(spec.historical_trades):
            direction, open_close = TRADE_TYPE_MAP[trade.type]
            qty = trade.qty if direction == "BUY" else -trade.qty

            # Include time for same-day ordering if provided
            trade_datetime = trade.date
            if trade.time:
                trade_datetime = f"{trade.date} {trade.time}"

            trades_data.append([
                account_id,
                trade.currency,
                "STK",
                "COMMON",
                trade.asset or spec.asset_symbol,
                f"{spec.asset_symbol} Desc",
                spec.asset_isin,
                None, None, None,
                trade_datetime,
                qty,
                trade.price,
                commission,
                trade.currency,
                direction,
                f"T_HIST_{i:04d}",
                None, None,
                f"CON{spec.asset_isin[:6]}",
                None,
                Decimal("1"),
                open_close,
            ])

    # Add intra-year trades
    for i, trade in enumerate(spec.intra_year_trades):
        direction, open_close = TRADE_TYPE_MAP[trade.type]
        qty = trade.qty if direction == "BUY" else -trade.qty

        # Include time for same-day ordering if provided
        trade_date = trade.date or f"{tax_year}-01-01"
        if trade.time:
            trade_datetime = f"{trade_date} {trade.time}"
        else:
            trade_datetime = trade_date

        trades_data.append([
            account_id,
            trade.currency,
            "STK",
            "COMMON",
            trade.asset or spec.asset_symbol,
            f"{spec.asset_symbol} Desc",
            spec.asset_isin,
            None, None, None,
            trade_datetime,
            qty,
            trade.price,
            commission,
            trade.currency,
            direction,
            f"T_CURR_{i:04d}",
            None, None,
            f"CON{spec.asset_isin[:6]}",
            None,
            Decimal("1"),
            open_close,
        ])

    return trades_data


def spec_to_positions_data(
    spec: FifoTestSpec,
    account_id: str,
    is_soy: bool = True,
) -> List[List]:
    """
    Convert spec position to pipeline input format.
    """
    pos = spec.positions_soy if is_soy else None

    if not pos:
        return []

    return [[
        account_id,
        pos.currency,
        "STK",
        "COMMON",
        spec.asset_symbol,
        f"{spec.asset_symbol} Desc",
        spec.asset_isin,
        pos.quantity,
        pos.quantity * Decimal("100"),  # Approximate value
        Decimal("100"),  # Mark price
        pos.cost_basis or Decimal("0"),
        None,
        f"CON{spec.asset_isin[:6]}",
        None,
        Decimal("1"),
    ]]


def spec_to_expected_outcome(
    spec: FifoTestSpec,
    fx_rate: Optional[Decimal] = None,
) -> ScenarioExpectedOutput:
    """
    Convert spec expectations to ScenarioExpectedOutput.

    If fx_rate is provided, uses compute_expected_financials to calculate
    cost/proceeds/gain values when not explicitly provided in the spec.
    """
    expected_rgls = []

    # Derive FX rate from spec if not provided
    if fx_rate is None:
        currency = get_spec_currency(spec)
        fx_rate = get_fx_rate_for_currency(currency)

    for rgl in spec.expected_rgls:
        # Compute financial values (uses spec values if provided, computes otherwise)
        cost_basis_eur, proceeds_eur, gain_loss_eur = compute_expected_financials(
            spec, rgl, fx_rate
        )

        # Determine tax category from gain/loss sign
        realization_type = rgl.realization_type

        if "LONG" in realization_type or realization_type == "SOLD_LONG":
            if gain_loss_eur >= 0:
                tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name
            else:
                tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST.name
        else:
            if gain_loss_eur >= 0:
                tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN.name
            else:
                tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST.name

        expected_rgls.append(
            ExpectedRealizedGainLoss(
                asset_identifier=f"ISIN:{spec.asset_isin}",
                realization_date=rgl.realization_date or "",
                quantity_realized=rgl.quantity or Decimal("0"),
                total_cost_basis_eur=cost_basis_eur,
                total_realization_value_eur=proceeds_eur,
                gross_gain_loss_eur=gain_loss_eur,
                acquisition_date=rgl.acquisition_date or "",
                asset_category_at_realization=AssetCategory.STOCK.name,
                tax_reporting_category=rgl.tax_category or tax_cat,
                realization_type=REALIZATION_TYPE_MAP.get(
                    rgl.realization_type, rgl.realization_type
                ),
            )
        )

    return ScenarioExpectedOutput(
        test_description=f"{spec.id}: {spec.description}",
        expected_rgls=expected_rgls,
        expected_eoy_states=[
            ExpectedAssetEoyState(
                asset_identifier=f"ISIN:{spec.asset_isin}",
                eoy_quantity=spec.expected_eoy_quantity,
            )
        ],
        expected_eoy_mismatch_error_count=spec.expected_errors,
    )

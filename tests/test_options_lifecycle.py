"""
Options Lifecycle Test Runner for Group 8

Loads YAML-based option test specifications and executes them through
the full processing pipeline. Tests cover:
- Long call/put exercise
- Short put/call assignment
- Worthless expiration (long and short)
- Option closing trades (buy-to-close, sell-to-close)
- Multi-lot FIFO for options

Groups:
- Group 8A (OPT_CALL_EX_*): Long Call Exercise
- Group 8B (OPT_PUT_ASGN_*): Short Put Assignment
- Group 8C (OPT_CCALL_ASGN_*): Short Call Assignment (Covered Call)
- Group 8D (OPT_PUT_EX_*): Long Put Exercise (Protective Put)
- Group 8E (OPT_EXP_*): Worthless Expiration
- Group 8F (OPT_CLOSE_*): Option Closing Trades
- Group 8G (OPT_EDGE_*): Edge Cases

PRD Coverage: Options Lifecycle, Termingeschäfte
"""

import pytest
from decimal import Decimal
from typing import List, Tuple, Any

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.expected import (
    ScenarioExpectedOutput,
    ExpectedRealizedGainLoss,
    ExpectedAssetEoyState,
)
from tests.support.option_helpers import (
    create_option_trade_data,
    create_stock_trade_data,
    format_expiry_for_symbol,
    create_option_symbol_ibkr,
    create_option_description_ibkr,
    generate_option_conid,
    DEFAULT_MULTIPLIER,
    OPTION_TRADE_TYPE_MAP,
)

from tests.fixtures import (
    load_yaml_spec,
    parse_option_tests,
    OptionTestSpec,
    get_group8_options_tests,
)

from src.domain.enums import RealizationType, TaxReportingCategory


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TAX_YEAR = 2023
DEFAULT_FX_RATE = Decimal("1.0")  # 1:1 for EUR tests


# =============================================================================
# Spec Loading
# =============================================================================

def load_all_option_specs() -> List[Tuple[str, OptionTestSpec]]:
    """
    Load all option test specs from group 8.

    Returns list of (group_name, spec) tuples for pytest parameterization.
    """
    specs = get_group8_options_tests()
    return [("group8", spec) for spec in specs]


ALL_OPTION_SPECS = load_all_option_specs()


def spec_id(item: Tuple[str, OptionTestSpec]) -> str:
    """Generate test ID in format 'group8::OPT_CALL_EX_001'."""
    group_name, spec = item
    return f"{group_name}::{spec.id}"


# =============================================================================
# Helper Functions
# =============================================================================

def spec_to_trades_data(
    spec: OptionTestSpec,
    account_id: str,
    tax_year: int,
) -> Tuple[List[List[Any]], str]:
    """
    Convert option spec to pipeline trades input format.

    Generates both option trades and stock trades (if present).

    Returns:
        Tuple of (trades_data, option_conid) for use in expected outcome generation.
    """
    trades_data = []

    # Generate option symbol, description, and conid in IBKR format
    option_symbol = create_option_symbol_ibkr(
        spec.underlying.symbol,
        spec.option.expiry,
        spec.option.type,
        spec.option.strike,
    )
    option_desc = create_option_description_ibkr(
        spec.underlying.symbol,
        spec.option.expiry,
        spec.option.type,
        spec.option.strike,
    )
    # Generate deterministic numeric conid
    option_conid = generate_option_conid(
        spec.underlying.conid,
        spec.option.expiry,
        spec.option.type,
        spec.option.strike,
    )

    # Add option trades
    for i, trade in enumerate(spec.option_trades):
        trades_data.append(create_option_trade_data(
            account_id=account_id,
            currency=trade.currency,
            symbol=option_symbol,
            description=option_desc,
            underlying_symbol=spec.underlying.symbol,
            underlying_conid=spec.underlying.conid,
            option_conid=option_conid,
            strike=spec.option.strike,
            expiry_date=spec.option.expiry,
            option_type=spec.option.type,
            trade_date=trade.date,
            trade_type=trade.type,
            quantity=trade.qty,
            price=trade.price,
            multiplier=spec.option.multiplier,
            transaction_id=f"OPT_T_{i:04d}",
            notes_codes=trade.notes_codes,
        ))

    # Add stock trades if present
    if spec.stock_trades:
        stock_desc = f"{spec.underlying.symbol} COMMON STOCK"
        for i, trade in enumerate(spec.stock_trades):
            trades_data.append(create_stock_trade_data(
                account_id=account_id,
                currency=trade.currency,
                symbol=spec.underlying.symbol,
                description=stock_desc,
                isin=spec.underlying.isin,
                conid=spec.underlying.conid,
                trade_date=trade.date,
                trade_type=trade.type,
                quantity=trade.qty,
                price=trade.price,
                transaction_id=f"STK_T_{i:04d}",
                notes_codes=trade.notes_codes,
            ))

    return trades_data, option_conid


def spec_to_positions_soy_data(
    spec: OptionTestSpec,
    account_id: str,
) -> List[List[Any]]:
    """
    Convert SOY position from spec to pipeline positions input format.
    """
    if not spec.positions_soy:
        return []

    pos = spec.positions_soy
    return [[
        account_id,
        pos.currency,
        "STK",
        "COMMON",
        spec.underlying.symbol,
        f"{spec.underlying.symbol} COMMON STOCK",
        spec.underlying.isin,
        pos.quantity,
        pos.quantity * Decimal("50"),  # Approximate value
        Decimal("50"),  # Mark price
        pos.cost_basis or Decimal("0"),
        None,
        spec.underlying.conid,
        None,
        Decimal("1"),
    ]]


def spec_to_positions_eoy_data(
    spec: OptionTestSpec,
    account_id: str,
    option_conid: str,
) -> List[List[Any]]:
    """
    Generate EOY positions based on expected EOY quantities in the spec.
    """
    positions = []

    # Option EOY position
    if spec.option_eoy_quantity != Decimal("0"):
        option_symbol = create_option_symbol_ibkr(
            spec.underlying.symbol,
            spec.option.expiry,
            spec.option.type,
            spec.option.strike,
        )
        option_desc = create_option_description_ibkr(
            spec.underlying.symbol,
            spec.option.expiry,
            spec.option.type,
            spec.option.strike,
        )
        positions.append([
            account_id,
            "EUR",  # Default currency
            "OPT",
            spec.option.type,
            option_symbol,
            option_desc,
            "",  # No ISIN for options
            spec.option_eoy_quantity,
            spec.option_eoy_quantity * Decimal("100"),  # Approximate value
            Decimal("1"),  # Mark price
            Decimal("0"),  # Cost basis (approximate)
            spec.underlying.symbol,  # UnderlyingSymbol
            option_conid,
            spec.underlying.conid,
            spec.option.multiplier,
        ])

    # Stock EOY position
    if spec.stock_eoy_quantity != Decimal("0"):
        positions.append([
            account_id,
            "EUR",
            "STK",
            "COMMON",
            spec.underlying.symbol,
            f"{spec.underlying.symbol} COMMON STOCK",
            spec.underlying.isin,
            spec.stock_eoy_quantity,
            spec.stock_eoy_quantity * Decimal("50"),  # Approximate value
            Decimal("50"),  # Mark price
            Decimal("0"),  # Cost basis
            None,
            spec.underlying.conid,
            None,
            Decimal("1"),
        ])

    return positions


def spec_to_expected_outcome(
    spec: OptionTestSpec,
    option_conid: str,
) -> ScenarioExpectedOutput:
    """
    Convert spec expectations to ScenarioExpectedOutput.

    Args:
        spec: The option test specification
        option_conid: The numeric option conid generated for this test
    """
    expected_rgls = []

    # Determine realization date from trades
    # For options, it's typically the last trade date (expiry, exercise, or close)
    # For stocks, it's the stock sale date
    option_realization_date = ""
    stock_realization_date = ""
    if spec.option_trades:
        # Last option trade date is typically the realization date
        option_realization_date = spec.option_trades[-1].date
    if spec.stock_trades:
        # Last stock trade date is typically the stock realization date
        for trade in spec.stock_trades:
            if trade.type == "SL":  # Sell Long - this is the realization
                stock_realization_date = trade.date
                break

    for i, rgl in enumerate(spec.expected_rgls):
        # Map realization type string to enum name
        realization_type = rgl.realization_type

        # Build additional fields dict
        additional_fields = {}
        if rgl.tax_category:
            additional_fields["tax_reporting_category"] = rgl.tax_category
        if rgl.is_stillhalter_income is not None:
            additional_fields["is_stillhalter_income"] = rgl.is_stillhalter_income
        additional_fields["realization_type"] = realization_type

        # Determine asset identifier and realization date based on RGL type
        if rgl.asset:
            # Stock RGL - use ISIN and stock realization date
            asset_identifier = f"ISIN:{spec.underlying.isin}"
            realization_date = rgl.realization_date or stock_realization_date
        else:
            # Option RGL - use the numeric conid and option realization date
            asset_identifier = f"CONID:{option_conid}"
            realization_date = rgl.realization_date or option_realization_date

        expected_rgls.append(
            ExpectedRealizedGainLoss(
                asset_identifier=asset_identifier,
                realization_date=realization_date,
                quantity_realized=rgl.quantity or Decimal("0"),
                total_cost_basis_eur=rgl.total_cost_basis_eur or Decimal("0"),
                total_realization_value_eur=rgl.total_proceeds_eur or Decimal("0"),
                gross_gain_loss_eur=rgl.gain_loss_eur or Decimal("0"),
                **additional_fields,
            )
        )

    # Build EOY states - we need to check both option and stock EOY
    expected_eoy_states = []

    # Stock EOY state
    if spec.stock_eoy_quantity != Decimal("0") or spec.positions_soy:
        expected_eoy_states.append(
            ExpectedAssetEoyState(
                asset_identifier=f"ISIN:{spec.underlying.isin}",
                eoy_quantity=spec.stock_eoy_quantity,
            )
        )

    # Option EOY state - use the numeric conid
    expected_eoy_states.append(
        ExpectedAssetEoyState(
            asset_identifier=f"CONID:{option_conid}",
            eoy_quantity=spec.option_eoy_quantity,
        )
    )

    return ScenarioExpectedOutput(
        test_description=f"{spec.id}: {spec.description}",
        expected_rgls=expected_rgls,
        expected_eoy_states=expected_eoy_states,
        expected_eoy_mismatch_error_count=spec.expected_errors,
    )


# =============================================================================
# Test Classes
# =============================================================================

class TestOptionsLifecycle(FifoTestCaseBase):
    """
    Options lifecycle test runner for Group 8.

    Tests option exercise, assignment, expiration, and closing trades.
    """

    @pytest.mark.parametrize(
        "group_spec",
        ALL_OPTION_SPECS,
        ids=spec_id,
    )
    def test_options(self, group_spec: Tuple[str, OptionTestSpec], mock_config_paths):
        """Execute an options test case from Group 8."""
        group_name, spec = group_spec

        if not spec:
            pytest.skip("No spec provided")

        account_id = f"U_{group_name.upper()}_TEST"
        tax_year = DEFAULT_TAX_YEAR

        # Convert spec to pipeline inputs - returns trades data and option conid
        trades_data, option_conid = spec_to_trades_data(spec, account_id, tax_year)
        positions_start = spec_to_positions_soy_data(spec, account_id)

        # Build EOY positions from expected EOY quantities
        positions_end = spec_to_positions_eoy_data(spec, account_id, option_conid)

        # Build expected outcome using the same option_conid that was used for trades
        expected = spec_to_expected_outcome(spec, option_conid)

        # Use 1:1 FX rate for EUR-denominated tests
        mock_rate_provider = MockECBExchangeRateProvider(
            foreign_to_eur_init_value=DEFAULT_FX_RATE
        )

        actual = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start,
            positions_end_data=positions_end,
            custom_rate_provider=mock_rate_provider,
            tax_year=tax_year,
        )

        self.assert_results(actual, expected)


# =============================================================================
# Spec Loading Verification
# =============================================================================

class TestOptionsSpecsLoaded:
    """Verify that option specs are loaded correctly."""

    def test_option_specs_count(self):
        """Verify total number of option specs."""
        assert len(ALL_OPTION_SPECS) >= 12, f"Expected at least 12 option specs, got {len(ALL_OPTION_SPECS)}"

    def test_expiration_specs_exist(self):
        """Verify expiration specs exist."""
        expiration_specs = [s for g, s in ALL_OPTION_SPECS if "EXP" in s.id]
        assert len(expiration_specs) >= 4, f"Expected at least 4 expiration specs, got {len(expiration_specs)}"

    def test_close_specs_exist(self):
        """Verify closing trade specs exist."""
        close_specs = [s for g, s in ALL_OPTION_SPECS if "CLOSE" in s.id]
        assert len(close_specs) >= 4, f"Expected at least 4 closing trade specs, got {len(close_specs)}"

    def test_ids_follow_naming_convention(self):
        """Verify spec IDs follow OPT_ naming convention."""
        for group, spec in ALL_OPTION_SPECS:
            assert spec.id.startswith("OPT_"), f"Spec {spec.id} should start with OPT_"

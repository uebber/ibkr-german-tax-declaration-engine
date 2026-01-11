"""
Test Support Module

This module consolidates all test infrastructure:
- Base test classes
- Expected result definitions
- Mock providers
- CSV creators
- Helper functions
"""

# Base test class
from tests.support.base import FifoTestCaseBase

# Expected result definitions
from tests.support.expected import (
    ExpectedRealizedGainLoss,
    ExpectedAssetEoyState,
    ScenarioExpectedOutput,
)

# Mock providers
from tests.support.mock_providers import (
    MockECBExchangeRateProvider,
    create_constant_rate_provider,
    create_variable_rate_provider,
    create_multi_currency_provider,
)

# CSV creators
from tests.support.csv_creators import (
    create_trades_csv_string,
    create_positions_csv_string,
    create_cash_transactions_csv_string,
    create_corporate_actions_csv_string,
)

# Helper functions
from tests.support.helpers import (
    DEFAULT_TAX_YEAR,
    HISTORICAL_YEAR,
    COMMISSION,
    COMMISSION_EUR,
    COMMISSION_USD,
    DEFAULT_FX_RATE,
    TRADE_TYPE_MAP,
    REALIZATION_TYPE_MAP,
    get_spec_currency,
    get_fx_rate_for_currency,
    get_eoy_file_quantity,
    spec_to_trades_data,
    spec_to_positions_data,
    spec_to_expected_outcome,
    load_group_specs,
    _get_asset_class_and_desc_for_category,
)

__all__ = [
    # Base
    "FifoTestCaseBase",
    # Expected
    "ExpectedRealizedGainLoss",
    "ExpectedAssetEoyState",
    "ScenarioExpectedOutput",
    # Mock providers
    "MockECBExchangeRateProvider",
    "create_constant_rate_provider",
    "create_variable_rate_provider",
    "create_multi_currency_provider",
    # CSV creators
    "create_trades_csv_string",
    "create_positions_csv_string",
    "create_cash_transactions_csv_string",
    "create_corporate_actions_csv_string",
    # Helpers
    "DEFAULT_TAX_YEAR",
    "HISTORICAL_YEAR",
    "COMMISSION",
    "COMMISSION_EUR",
    "COMMISSION_USD",
    "DEFAULT_FX_RATE",
    "TRADE_TYPE_MAP",
    "REALIZATION_TYPE_MAP",
    "get_spec_currency",
    "get_fx_rate_for_currency",
    "get_eoy_file_quantity",
    "spec_to_trades_data",
    "spec_to_positions_data",
    "spec_to_expected_outcome",
    "load_group_specs",
    "_get_asset_class_and_desc_for_category",
]

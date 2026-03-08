"""
Group 10: Options with Variable FX Rates

Verifies that option lifecycle calculations produce correct EUR values
when options are traded in foreign currency (USD) with different ECB rates
on different trade dates.

Group 8 uses EUR for all option trades, so it never tests the FX interaction.
This group closes that gap by testing:
- Long/short option closing trades in USD with variable rates
- Call exercise with premium and stock at different FX rates

Tax Law Basis:
- Termingeschaefte (§20 Abs. 2 Nr. 3 EStG): Option gains/losses
- §20 Abs. 4 EStG: FIFO cost basis at acquisition-date EUR value
- Stillhaltergeschaefte: Premium income for short options
"""

import pytest
import yaml
from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.fixtures import (
    load_yaml_spec,
    parse_option_tests,
    OptionTestSpec,
)

# Reuse option test infrastructure from Group 8
from tests.test_options_lifecycle import (
    spec_to_trades_data,
    spec_to_positions_soy_data,
    spec_to_positions_eoy_data,
    spec_to_expected_outcome,
)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TAX_YEAR = 2023


# =============================================================================
# Rate Schedule Extraction
# =============================================================================

def _load_fx_rate_schedules() -> Dict[str, Dict[str, List[Tuple[date, Decimal]]]]:
    """
    Load fx_rates from the raw YAML for each test spec.

    Returns a dict: test_id -> currency -> [(date, foreign_to_eur), ...]
    """
    raw = load_yaml_spec("group10_options_variable_fx.yaml")
    schedules = {}

    for test_dict in raw.get("tests", []):
        test_id = test_dict["id"]
        fx_rates = test_dict.get("inputs", {}).get("fx_rates", {})

        if not fx_rates:
            continue

        currency_schedules = {}
        for currency, date_rate_map in fx_rates.items():
            schedule = []
            for date_str, rate_str in date_rate_map.items():
                parts = str(date_str).split("-")
                d = date(int(parts[0]), int(parts[1]), int(parts[2]))
                schedule.append((d, Decimal(str(rate_str))))
            schedule.sort(key=lambda x: x[0])
            currency_schedules[currency] = schedule

        schedules[test_id] = currency_schedules

    return schedules


# =============================================================================
# Spec Loading
# =============================================================================

def _load_option_fx_specs() -> List[Tuple[str, OptionTestSpec]]:
    """Load Group 10 specs using the option parser."""
    spec_data = load_yaml_spec("group10_options_variable_fx.yaml")
    specs = parse_option_tests(spec_data)
    return [("group10", spec) for spec in specs]


ALL_OPTFX_SPECS = _load_option_fx_specs()
FX_RATE_SCHEDULES = _load_fx_rate_schedules()


def spec_id(item: Tuple[str, OptionTestSpec]) -> str:
    group_name, spec = item
    return f"{group_name}::{spec.id}"


# =============================================================================
# Test Runner
# =============================================================================

class TestOptionsVariableFx(FifoTestCaseBase):
    """
    Variable FX rate tests for options.

    Uses date-specific ECB rates via MockECBExchangeRateProvider's
    currency_schedules. All expected EUR values are explicitly provided
    in the YAML specs.
    """

    @pytest.mark.parametrize(
        "group_spec",
        ALL_OPTFX_SPECS,
        ids=spec_id,
    )
    def test_option_variable_fx(self, group_spec: Tuple[str, OptionTestSpec], mock_config_paths):
        group_name, spec = group_spec
        account_id = "U_GROUP10_OPTFX_TEST"
        tax_year = DEFAULT_TAX_YEAR

        # Build variable-rate provider from YAML fx_rates
        currency_schedules = FX_RATE_SCHEDULES.get(spec.id, {})
        assert currency_schedules, (
            f"Test {spec.id} has no fx_rates defined in YAML. "
            "Variable FX tests require explicit rate schedules."
        )

        mock_rate_provider = MockECBExchangeRateProvider(
            currency_schedules=currency_schedules,
        )

        # Convert spec to pipeline inputs (reuses Group 8 helpers)
        trades_data, option_conid = spec_to_trades_data(spec, account_id, tax_year)
        positions_start = spec_to_positions_soy_data(spec, account_id)
        positions_end = spec_to_positions_eoy_data(spec, account_id, option_conid)

        # Build expected outcome
        expected = spec_to_expected_outcome(spec, option_conid)

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

class TestOptionsFxSpecsLoaded:
    """Verify that Group 10 specs are loaded correctly."""

    def test_spec_count(self):
        assert len(ALL_OPTFX_SPECS) == 4, f"Expected 4 OPTFX specs, got {len(ALL_OPTFX_SPECS)}"

    def test_all_ids_start_with_optfx(self):
        for group, spec in ALL_OPTFX_SPECS:
            assert spec.id.startswith("OPTFX_"), f"Spec {spec.id} should start with OPTFX_"

    def test_all_have_fx_rate_schedules(self):
        for group, spec in ALL_OPTFX_SPECS:
            assert spec.id in FX_RATE_SCHEDULES, (
                f"Spec {spec.id} missing from FX_RATE_SCHEDULES"
            )

    def test_all_use_usd(self):
        """All OPTFX specs should use USD for option trades."""
        for group, spec in ALL_OPTFX_SPECS:
            for trade in spec.option_trades:
                assert trade.currency == "USD", (
                    f"{spec.id}: option trade uses {trade.currency}, expected USD"
                )

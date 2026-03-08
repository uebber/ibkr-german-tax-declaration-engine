"""
Group 9: Variable FX Rate Verification

Verifies that security gain/loss calculations produce correct EUR values
when ECB rates differ between acquisition and sale dates.

Groups 1-5 use a constant FX rate (2.0) for ALL dates, so they never test
the interaction between trade-date-specific ECB rates and FIFO cost basis
calculations. This group closes that gap.

Tax Law Basis:
- §20 Abs. 4 EStG: FIFO cost basis must use acquisition-date EUR value
- The enrichment layer converts each trade at its trade-date ECB rate
- Cost basis carries the acquisition-date EUR value through FIFO lots
- Proceeds use the sale-date EUR value
- The gain/loss therefore includes both foreign price movement AND FX movement
"""

import pytest
import yaml
from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.fixtures import load_yaml_spec, parse_fifo_tests, FifoTestSpec

from tests.support.helpers import (
    DEFAULT_TAX_YEAR,
    get_eoy_file_quantity,
    spec_to_trades_data,
    spec_to_positions_data,
    spec_to_expected_outcome,
    _get_asset_class_and_desc_for_category,
)


# =============================================================================
# Rate Schedule Extraction
# =============================================================================

def _load_fx_rate_schedules() -> Dict[str, Dict[str, List[Tuple[date, Decimal]]]]:
    """
    Load fx_rates from the raw YAML for each test spec.

    Returns a dict: test_id -> currency -> [(date, foreign_to_eur), ...]
    """
    raw = load_yaml_spec("group9_variable_fx_rates.yaml")
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

def _load_variable_fx_specs() -> List[Tuple[str, FifoTestSpec]]:
    """Load Group 9 specs using the standard FIFO parser."""
    spec_data = load_yaml_spec("group9_variable_fx_rates.yaml")
    specs = parse_fifo_tests(spec_data)
    return [("group9", spec) for spec in specs]


ALL_VFX_SPECS = _load_variable_fx_specs()
FX_RATE_SCHEDULES = _load_fx_rate_schedules()


def spec_id(item: Tuple[str, FifoTestSpec]) -> str:
    group_name, spec = item
    return f"{group_name}::{spec.id}"


# =============================================================================
# Test Runner
# =============================================================================

class TestVariableFxRates(FifoTestCaseBase):
    """
    Variable FX rate tests for security trades.

    Unlike Groups 1-5 which use a constant FX rate, these tests use
    date-specific rates via MockECBExchangeRateProvider's currency_schedules.
    All expected EUR values are explicitly provided in the YAML specs.
    """

    @pytest.mark.parametrize(
        "group_spec",
        ALL_VFX_SPECS,
        ids=spec_id,
    )
    def test_variable_fx(self, group_spec: Tuple[str, FifoTestSpec], mock_config_paths):
        group_name, spec = group_spec
        account_id = "U_GROUP9_VFX_TEST"
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

        # Convert spec to pipeline inputs (reuses existing helpers)
        trades_data = spec_to_trades_data(spec, account_id, tax_year)
        positions_start = spec_to_positions_data(spec, account_id, is_soy=True)

        # EOY positions
        eoy_file_qty = get_eoy_file_quantity(spec)
        asset_class_code, asset_desc = _get_asset_class_and_desc_for_category(spec)
        currency = "USD"
        if spec.positions_soy and spec.positions_soy.currency:
            currency = spec.positions_soy.currency
        elif spec.intra_year_trades:
            currency = spec.intra_year_trades[0].currency

        if eoy_file_qty != Decimal("0"):
            positions_end = [[
                account_id, currency, asset_class_code, "COMMON",
                spec.asset_symbol, asset_desc, spec.asset_isin,
                eoy_file_qty, Decimal("0"), Decimal("100"),
                Decimal("0"), None, f"CON{spec.asset_isin[:6]}", None, Decimal("1")
            ]]
        else:
            positions_end = []

        # Build expected outcome - all EUR values are explicit in YAML,
        # so compute_expected_financials uses Case 1 (all provided)
        expected = spec_to_expected_outcome(spec)

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

class TestVariableFxSpecsLoaded:
    """Verify that Group 9 specs are loaded correctly."""

    def test_spec_count(self):
        assert len(ALL_VFX_SPECS) == 6, f"Expected 6 VFX specs, got {len(ALL_VFX_SPECS)}"

    def test_all_ids_start_with_vfx(self):
        for group, spec in ALL_VFX_SPECS:
            assert spec.id.startswith("VFX_"), f"Spec {spec.id} should start with VFX_"

    def test_all_have_fx_rate_schedules(self):
        for group, spec in ALL_VFX_SPECS:
            assert spec.id in FX_RATE_SCHEDULES, (
                f"Spec {spec.id} missing from FX_RATE_SCHEDULES"
            )

    def test_all_have_explicit_eur_values(self):
        """All VFX specs must provide explicit EUR values (not computed from constant rate)."""
        for group, spec in ALL_VFX_SPECS:
            for rgl in spec.expected_rgls:
                assert rgl.total_cost_basis_eur is not None, (
                    f"{spec.id}: total_cost_basis_eur must be explicit"
                )
                assert rgl.total_proceeds_eur is not None, (
                    f"{spec.id}: total_proceeds_eur must be explicit"
                )
                assert rgl.gain_loss_eur is not None, (
                    f"{spec.id}: gain_loss_eur must be explicit"
                )

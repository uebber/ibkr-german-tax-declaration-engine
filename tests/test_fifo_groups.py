"""
Unified FIFO Test Runner for Groups 1-5

Loads all YAML-based FIFO test specifications and executes them through
a single parameterized test. The YAML specs encode all semantic differences
(SOY positions, EOY reconciliation, historical trades) - the helpers handle
the variations automatically.

Groups:
- Group 1 (CFM_*): Core FIFO Mechanics - basic lot matching
- Group 2 (SOY_*): SOY Handling - cost basis from SOY reports/historical trades
- Group 3 (EOY_*): EOY Validation - reconciliation with broker reports
- Group 4 (MYH_*): Multi-Year - trades spanning multiple years
- Group 5 (CTX_*): Complex Sequences - reversals, day trading patterns

PRD Coverage: §2.4 (FIFO), §2.5 (SOY), §2.6 (EOY)
"""

import pytest
from decimal import Decimal
from typing import List, Tuple

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.fixtures import FifoTestSpec

from tests.support.helpers import (
    DEFAULT_TAX_YEAR,
    load_group_specs,
    get_spec_currency,
    get_fx_rate_for_currency,
    get_eoy_file_quantity,
    spec_to_trades_data,
    spec_to_positions_data,
    spec_to_expected_outcome,
    _get_asset_class_and_desc_for_category,
)


# =============================================================================
# Spec Loading
# =============================================================================

def load_all_fifo_specs() -> List[Tuple[str, FifoTestSpec]]:
    """
    Load all FIFO test specs from groups 1-5.

    Returns list of (group_name, spec) tuples for pytest parameterization.
    """
    groups = [
        ("group1", "group1_core_fifo.yaml"),
        ("group2", "group2_soy_handling.yaml"),
        ("group3", "group3_eoy_validation.yaml"),
        ("group4", "group4_multi_year.yaml"),
        ("group5", "group5_complex_sequences.yaml"),
    ]

    all_specs = []
    for group_name, filename in groups:
        specs = load_group_specs(filename)
        for spec in specs:
            all_specs.append((group_name, spec))

    return all_specs


ALL_FIFO_SPECS = load_all_fifo_specs()


def spec_id(item: Tuple[str, FifoTestSpec]) -> str:
    """Generate test ID in format 'group1::CFM_L_001'."""
    group_name, spec = item
    return f"{group_name}::{spec.id}"


# =============================================================================
# Unified Test Runner
# =============================================================================

class TestFifoGroups(FifoTestCaseBase):
    """
    Unified FIFO test runner for Groups 1-5.

    All semantic differences between groups are encoded in the YAML specs:
    - Group 1: No positions_soy (fresh year)
    - Group 2: positions_soy present (cost basis derivation)
    - Group 3: positions_eoy_report present (EOY reconciliation)
    - Group 4: historical_trades spanning years
    - Group 5: Complex trade sequences

    The helper functions handle these variations automatically based on
    which fields are present in the spec.
    """

    @pytest.mark.parametrize(
        "group_spec",
        ALL_FIFO_SPECS,
        ids=spec_id,
    )
    def test_fifo(self, group_spec: Tuple[str, FifoTestSpec], mock_config_paths):
        """Execute a FIFO test case from any group."""
        group_name, spec = group_spec

        if not spec:
            pytest.skip("No spec provided")

        account_id = f"U_{group_name.upper()}_TEST"
        tax_year = DEFAULT_TAX_YEAR

        # Derive currency and FX rate from spec
        currency = get_spec_currency(spec)
        fx_rate = get_fx_rate_for_currency(currency)

        # Convert spec to pipeline inputs
        # - spec_to_trades_data handles historical_trades if present
        # - spec_to_positions_data returns [] if no positions_soy
        trades_data = spec_to_trades_data(spec, account_id, tax_year)
        positions_start = spec_to_positions_data(spec, account_id, is_soy=True)

        # EOY positions from spec
        # - get_eoy_file_quantity uses positions_eoy_report if present, else expected_eoy_quantity
        # - Empty list if quantity is 0 (handles sold-all and mismatch scenarios)
        eoy_file_qty = get_eoy_file_quantity(spec)
        asset_class_code, asset_desc = _get_asset_class_and_desc_for_category(spec)
        if eoy_file_qty != Decimal("0"):
            positions_end = [[
                account_id, currency, asset_class_code, "COMMON",
                spec.asset_symbol, asset_desc, spec.asset_isin,
                eoy_file_qty, Decimal("0"), Decimal("100"),
                Decimal("0"), None, f"CON{spec.asset_isin[:6]}", None, Decimal("1")
            ]]
        else:
            positions_end = []

        expected = spec_to_expected_outcome(spec, fx_rate)

        mock_rate_provider = MockECBExchangeRateProvider(
            foreign_to_eur_init_value=fx_rate
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

class TestFifoSpecsLoaded:
    """Verify that all FIFO specs are loaded correctly."""

    def test_total_spec_count(self):
        """Verify total number of specs across all groups."""
        assert len(ALL_FIFO_SPECS) == 42, f"Expected 42 total specs, got {len(ALL_FIFO_SPECS)}"

    def test_group1_count(self):
        """Verify Group 1 has 10 specs."""
        group1 = [s for g, s in ALL_FIFO_SPECS if g == "group1"]
        assert len(group1) == 10, f"Group 1 should have 10 specs, got {len(group1)}"

    def test_group2_count(self):
        """Verify Group 2 has 10 specs."""
        group2 = [s for g, s in ALL_FIFO_SPECS if g == "group2"]
        assert len(group2) == 10, f"Group 2 should have 10 specs, got {len(group2)}"

    def test_group3_count(self):
        """Verify Group 3 has 9 specs."""
        group3 = [s for g, s in ALL_FIFO_SPECS if g == "group3"]
        assert len(group3) == 9, f"Group 3 should have 9 specs, got {len(group3)}"

    def test_group4_count(self):
        """Verify Group 4 has 3 specs."""
        group4 = [s for g, s in ALL_FIFO_SPECS if g == "group4"]
        assert len(group4) == 3, f"Group 4 should have 3 specs, got {len(group4)}"

    def test_group5_count(self):
        """Verify Group 5 has 10 specs."""
        group5 = [s for g, s in ALL_FIFO_SPECS if g == "group5"]
        assert len(group5) == 10, f"Group 5 should have 10 specs, got {len(group5)}"

    def test_group1_ids_start_with_cfm(self):
        """Verify Group 1 spec IDs follow naming convention."""
        for group, spec in ALL_FIFO_SPECS:
            if group == "group1":
                assert spec.id.startswith("CFM_"), f"Spec {spec.id} should start with CFM_"

    def test_group2_ids_start_with_soy(self):
        """Verify Group 2 spec IDs follow naming convention."""
        for group, spec in ALL_FIFO_SPECS:
            if group == "group2":
                assert spec.id.startswith("SOY_"), f"Spec {spec.id} should start with SOY_"

    def test_group3_ids_start_with_eoy(self):
        """Verify Group 3 spec IDs follow naming convention."""
        for group, spec in ALL_FIFO_SPECS:
            if group == "group3":
                assert spec.id.startswith("EOY_"), f"Spec {spec.id} should start with EOY_"

    def test_group4_ids_start_with_myh(self):
        """Verify Group 4 spec IDs follow naming convention."""
        for group, spec in ALL_FIFO_SPECS:
            if group == "group4":
                assert spec.id.startswith("MYH_"), f"Spec {spec.id} should start with MYH_"

    def test_group5_ids_start_with_ctx(self):
        """Verify Group 5 spec IDs follow naming convention."""
        for group, spec in ALL_FIFO_SPECS:
            if group == "group5":
                assert spec.id.startswith("CTX_"), f"Spec {spec.id} should start with CTX_"

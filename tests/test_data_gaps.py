"""
AR6 (rework2): the data-gap channel — one path for "input could not fully
support the computation", with an explicit severity policy.

legal_basis: infrastructure for findings F4/F6 — silent fallbacks must never
understate income (FAIL_FAST) and evidentiary mismatches must reach the
report, not only a log file (WARNING).
"""
import logging
from decimal import Decimal

import pytest

from src.processing.data_gaps import DataGapCollector, DataGapError, GapSeverity
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider


class TestCollectorPolicy:
    def test_warning_gap_is_recorded_and_logged(self, caplog):
        c = DataGapCollector()
        with caplog.at_level(logging.WARNING):
            c.record("EOY_QTY_MISMATCH", "ASSET X", "calc 20 vs reported 10")
        assert len(c) == 1
        assert c.gaps[0].severity is GapSeverity.WARNING
        assert any("EOY_QTY_MISMATCH" in r.message for r in caplog.records)

    def test_fail_fast_gap_raises(self):
        """FAIL_FAST = continuing would risk understating income — the run
        must stop, never emit a plausible-looking incomplete declaration."""
        c = DataGapCollector()
        with pytest.raises(DataGapError, match="VP_NAV_MISSING"):
            c.record("VP_NAV_MISSING", "Fund Y", "no year-start NAV",
                     severity=GapSeverity.FAIL_FAST)
        assert len(c) == 1  # recorded before raising (visible post-mortem)



class TestVpNavGapPolicy:
    """B4 plugs §18 InvStG NAV gaps into the channel via the pipeline boundary
    (src/pipeline_runner._record_vp_nav_gaps) — the F4 resolution: a missing
    year-start NAV understates deemed income, so non-interactive runs abort."""

    @staticmethod
    def _gap():
        from src.domain.results import VorabpauschaleGap
        return VorabpauschaleGap(
            asset_internal_id=None, description="Fonds Z (IE000TEST0000)",
            target_year=2024, deemed_inflow_year=2025,
            reason="Jahresanfangs-NAV 2024 fehlt",
        )

    def test_non_interactive_missing_nav_is_fail_fast(self):
        from src.pipeline_runner import _record_vp_nav_gaps
        c = DataGapCollector()
        with pytest.raises(DataGapError, match="VP_NAV_MISSING"):
            _record_vp_nav_gaps(c, [self._gap()], interactive=False)
        assert c.gaps[0].severity is GapSeverity.FAIL_FAST

    def test_interactive_missing_nav_is_warning_with_inflow_year(self):
        from src.pipeline_runner import _record_vp_nav_gaps
        c = DataGapCollector()
        _record_vp_nav_gaps(c, [self._gap()], interactive=True)
        assert len(c) == 1
        gap = c.gaps[0]
        assert gap.severity is GapSeverity.WARNING
        assert gap.code == "VP_NAV_MISSING"
        # the report's VP section filters by deemed-inflow year from the detail
        assert "Zufluss 2025" in gap.detail


class TestEoyMismatchFlowsIntoChannel(FifoTestCaseBase):
    def test_eoy_quantity_mismatch_recorded_as_gap(self, mock_config_paths):
        """Buy 20, EOY report says 10: the existing mismatch error count is
        unchanged AND the divergence appears in the data-gap channel."""
        trades = [["U_GAP_TEST", "EUR", "STK", "COMMON", "GAPX", "GAP X", "US000000GAP1",
                   "", "", "", "20230401", "20", "10", "0", "EUR", "BUY", "T1", "", "",
                   "CONGAP", "", "1", "O"]]
        positions_end = [["U_GAP_TEST", "EUR", "STK", "COMMON", "GAPX", "GAP X",
                          "US000000GAP1", Decimal("10"), Decimal("100"), Decimal("10"),
                          Decimal("100"), "", "CONGAP", "", Decimal("1")]]
        out = self._run_pipeline(
            trades_data=trades, positions_end_data=positions_end,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.0")),
            tax_year=2023,
        )
        assert out.eoy_mismatch_error_count == 1  # unchanged behavior
        assert any(g.code == "EOY_QTY_MISMATCH" for g in out.data_gaps)

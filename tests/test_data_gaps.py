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


class TestEoyMismatchFlowsIntoChannel(FifoTestCaseBase):
    def test_eoy_quantity_mismatch_aborts_the_run(self, mock_config_paths):
        """Buy 20, EOY report says 10: the divergence flows through the data-gap
        channel and the run ABORTS.

        Changed from the original assertion (`eoy_mismatch_error_count == 1`,
        "unchanged behavior") on the maintainer's decision: given a full year of
        input the reconciliation must succeed, so a residual means a disposal was
        missed, duplicated or mismatched and every figure from that ledger is
        unsafe. PRD 2.4 requires the quantities to be identical and the
        discrepancy to be a critical error; the engine no longer continues past
        one. See tests/docs/spec_fifo.md, Group 3.
        """
        trades = [["U_GAP_TEST", "EUR", "STK", "COMMON", "GAPX", "GAP X", "US000000GAP1",
                   "", "", "", "20230401", "20", "10", "0", "EUR", "BUY", "T1", "", "",
                   "CONGAP", "", "1", "O"]]
        positions_end = [["U_GAP_TEST", "EUR", "STK", "COMMON", "GAPX", "GAP X",
                          "US000000GAP1", Decimal("10"), Decimal("100"), Decimal("10"),
                          Decimal("100"), "", "CONGAP", "", Decimal("1")]]
        with pytest.raises(DataGapError) as excinfo:
            self._run_pipeline(
                trades_data=trades, positions_end_data=positions_end,
                custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.0")),
                tax_year=2023,
            )
        message = str(excinfo.value)
        assert "EOY_RECONCILIATION_FAILED" in message
        assert "GAP X" in message, message

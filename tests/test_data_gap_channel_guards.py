"""
The halves of the data-gap channel its own tests cannot see.

The channel has two ends: recording a gap in the engine, and putting it in
front of the user. `tests/test_data_gaps.py` covers the collector's policy and
one of the two recording sites. Probing the rest by mutation, with the whole
474-test suite running:

    mutation                                              failures
    drop the record at the "quantity differs" branch      1  (covered)
    drop the record at the "asset absent from EoY" branch  0  <- blind
    delete the report section that renders the gaps        0  <- blind

The second recording branch is the sharper of the two — the engine holds a
position the broker does not report at all — and the report section is the
entire point of the channel: a gap that reaches only the log is the condition
this module exists to end. Both are pinned here.

legal_basis: infrastructure. No figure depends on these assertions; what
depends on them is whether the taxpayer is told that a figure may be wrong.
An EoY quantity mismatch is the signature of an unprocessed disposal (see
src/processing/data_gaps.py), so losing it silently understates income.
"""
import contextlib
import io
import logging
from decimal import Decimal

import pytest

from src.domain.exceptions import ProcessingError
from src.domain.results import LossOffsettingResult
from src.processing.data_gaps import (
    DataGap, DataGapCollector, DataGapError, GapSeverity,
)
from src.reporting.console_reporter import generate_console_tax_report
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider


class _StubResolver:
    assets_by_internal_id: dict = {}

    def get_asset_by_id(self, internal_id):
        return None


def _report_lines(data_gaps, eoy_mismatch_count=0) -> list:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        generate_console_tax_report(
            [], [], [], _StubResolver(), 2025, eoy_mismatch_count,
            LossOffsettingResult(), data_gaps=data_gaps,
        )
    return [line.strip() for line in buffer.getvalue().splitlines()]


class TestGapsReachTheReport:
    """Blind spot: the whole rendering block can be deleted, suite still green."""

    def test_every_recorded_gap_is_printed_with_code_subject_and_detail(self):
        gaps = [
            DataGap(code="EOY_QTY_MISMATCH", subject="ACME INC",
                    detail="Berechnete EoY-Stückzahl 20 weicht ab."),
            DataGap(code="VP_NAV_MISSING", subject="SOME FUND",
                    detail="Kein Jahresanfangs-NAV."),
        ]
        lines = _report_lines(gaps, eoy_mismatch_count=1)

        assert any("DATENLÜCKEN / HINWEISE" in line for line in lines), \
            "the gap section is missing from the report"
        for gap in gaps:
            assert any(gap.code in line and gap.subject in line and gap.detail in line
                       for line in lines), f"gap {gap.code} never reached the report"

    def test_clean_run_prints_no_gap_section(self):
        """A run without gaps must be byte-unchanged — this is what makes the
        channel safe to add to an engine whose output is compared for parity."""
        for empty in (None, []):
            lines = _report_lines(empty)
            assert not any("DATENLÜCKEN" in line for line in lines)

    def test_eoy_warning_points_at_the_section_that_carries_the_detail(self):
        """The pre-existing warning said "Siehe Log für Details" — wrong once
        the details are in the report, right when no gaps were collected."""
        with_gaps = _report_lines(
            [DataGap(code="EOY_QTY_MISMATCH", subject="ACME INC", detail="x")],
            eoy_mismatch_count=1,
        )
        warning = [line for line in with_gaps if "Mengenvalidierung festgestellt" in line]
        assert warning and "DATENLÜCKEN" in warning[0], warning

        without = _report_lines(None, eoy_mismatch_count=1)
        warning = [line for line in without if "Mengenvalidierung festgestellt" in line]
        assert warning and "Siehe Log für Details" in warning[0], warning


class TestBothEoyBranchesRecord(FifoTestCaseBase):
    """Blind spot: the second EoY branch's record() can be removed unnoticed."""

    def test_asset_absent_from_eoy_report_is_recorded(self, mock_config_paths):
        """Bought 20 and never sold, but the EoY positions export does not list
        the asset at all — reported quantity is not "different", it is absent.
        The engine treats that as a mismatch against an implied zero; that is
        the branch the suite could not see."""
        trades = [["U_GAP_TEST", "EUR", "STK", "COMMON", "GAPY", "GAP Y", "US000000GAP2",
                   "", "", "", "20230401", "20", "10", "0", "EUR", "BUY", "T1", "", "",
                   "CONGAPY", "", "1", "O"]]
        out = self._run_pipeline(
            trades_data=trades, positions_end_data=[],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.0")),
            tax_year=2023,
        )
        assert out.eoy_mismatch_error_count == 1
        recorded = [g for g in out.data_gaps if g.code == "EOY_QTY_MISMATCH"]
        assert len(recorded) == 1, out.data_gaps
        assert "GAP Y" in recorded[0].subject
        assert "20" in recorded[0].detail


class TestFailFastIsNotSwallowed:
    """FAIL_FAST is the channel's whole claim, and nothing raises it yet — the
    first site arrives with the Vorabpauschale NAV resolution. Pin the path it
    will travel, so a broad `except` cannot quietly turn an aborted run into a
    filed declaration."""

    def test_data_gap_error_is_a_processing_error(self):
        """CLAUDE.md's taxonomy: the engine raises ProcessingError. A handler
        written against it must not miss a fail-fast gap."""
        with pytest.raises(ProcessingError):
            DataGapCollector().record("X", "Y", "Z", severity=GapSeverity.FAIL_FAST)

    def test_pipeline_does_not_swallow_a_fail_fast_gap(self, monkeypatch, caplog):
        """run_core_processing_pipeline wraps the engine in `except Exception`.
        It re-raises today; if that ever becomes a log-and-continue, every
        FAIL_FAST gap silently degrades to a WARNING with no report entry."""
        import src.pipeline_runner as pipeline_runner

        def _boom(**kwargs):
            kwargs["data_gap_collector"].record(
                "VP_NAV_MISSING", "Fund Z", "no year-start NAV",
                severity=GapSeverity.FAIL_FAST,
            )

        monkeypatch.setattr(pipeline_runner, "run_main_calculations", _boom)
        with caplog.at_level(logging.CRITICAL):
            with pytest.raises(DataGapError, match="VP_NAV_MISSING"):
                pipeline_runner.run_core_processing_pipeline(
                    trades_file_path="", cash_transactions_file_path="",
                    positions_start_file_path="", positions_end_file_path="",
                    corporate_actions_file_path="",
                    interactive_classification_mode=False,
                    tax_year_to_process=2023,
                )
        assert any("VP_NAV_MISSING" in r.message for r in caplog.records)

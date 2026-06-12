"""
C8 — Einlagenrückgewähr (§20 Abs. 1 Nr. 1 S. 3 EStG): the engine's pinned legal
position, asserted results-oriented (synthetic CSVs in -> declared figures out).

legal_basis:
  - §20 Abs. 1 Nr. 1 S. 3 EStG, §27 KStG: a distribution from the steuerliches
    Einlagekonto is NOT income; it reduces the Anschaffungskosten of the shares
    (reference/bmf-guidance/abgeltungsteuer-einzelfragen.md, section
    "Einlagenrückgewähr").
  - PINNED POSITION (legal-position register EINLAGENRUECKGEWAEHR_EXCESS; the
    excess case for <1% Privatvermögen holdings is an OPEN legal question — no
    BFH ruling, no BMF sentence): reduction is FIFO-SEQUENTIAL across lots;
    only the residual exceeding ALL lots' combined basis is taxed immediately,
    as sonstige Kapitalerträge (Z19 pot), in the DISTRIBUTION year. The h.M.
    alternative (negative Anschaffungskosten, deferral into the Z20 pot at
    disposal) is documented in the register and disclosed on every report.

Where the candidate readings diverge — and what each test pins:
  T1  cross-year basis carry: the reduction must survive into later tax years'
      SoY reconstruction (else the sale gain is UNDERSTATED by the repayment).
  T2  partial exit: FIFO-sequential allocation (lot 1 zeroed first), NOT
      per-share allocation (which would leave lot 1 with basis and declare a
      smaller gain on the first partial sale).
  T3  excess over all lots: the residual is income NOW, in the Z19 pot — not
      deferred, not Aktiengewinn.
  T4  cross-year excess timing: the excess belongs to the DISTRIBUTION year's
      assessment; it must not reappear as income in the sale year, and the
      sale realises against the fully-zeroed basis.

All data is SYNTHETIC. Full exits in the distribution year are already covered
by the pre-existing dividend-rights spillover tests; these are the scenarios
where the readings actually diverge.
"""
import os
from decimal import Decimal

import pytest

from src.pipeline_runner import run_core_processing_pipeline
from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from src.parsers.column_validator import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_TRANSACTIONS_COLUMNS,
)
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.test_e2e_declaration import _trade, _pos, _write

TAX_YEAR = 2025


def _repayment(isin, date, amount, txid):
    """An Einlagenrückgewähr row: 'Dividends' type, description marks it exempt."""
    return [
        "U10000001", "EUR", "STK", "COMMON", isin[8:],
        f"{isin[8:]} CORP RETURN OF CAPITAL - EXEMPT FROM WITHHOLDING",
        date, Decimal(amount), "Dividends", "CON" + isin[8:], None, isin, "US", txid,
    ]


class _RepaymentScenarioBase(FifoTestCaseBase):
    def _run(self, trades, cash_rows, pos_soy, pos_eoy):
        p = self.config_paths
        _write(p["trades"], TRADES_COLUMNS, trades)
        _write(p["cash"], CASH_TRANSACTIONS_COLUMNS, cash_rows)
        _write(p["pos_start"], POSITIONS_COLUMNS, pos_soy)
        _write(p["pos_end"], POSITIONS_COLUMNS, pos_eoy)
        from tests.support.csv_creators import (
            create_corporate_actions_csv_string, create_cash_balance_csv_string,
        )
        with open(p["corp_actions"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_corporate_actions_csv_string([]))
        with open(p["cash_balance"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_cash_balance_csv_string([]))
        out = run_core_processing_pipeline(
            trades_file_path=p["trades"],
            cash_transactions_file_path=p["cash"],
            positions_start_file_path=p["pos_start"],
            positions_end_file_path=p["pos_end"],
            corporate_actions_file_path=p["corp_actions"],
            interactive_classification_mode=False,
            tax_year_to_process=TAX_YEAR,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            cash_balance_file_path=p["cash_balance"],
        )
        flv = LossOffsettingEngine(
            realized_gains_losses=out.realized_gains_losses,
            vorabpauschale_items=out.vorabpauschale_items,
            current_year_financial_events=out.processed_income_events,
            asset_resolver=out.asset_resolver,
            tax_year=TAX_YEAR,
        ).calculate_reporting_figures().form_line_values
        return out, flv


class TestCrossYearBasisCarry(_RepaymentScenarioBase):
    def test_prior_year_repayment_reduces_basis_of_current_year_sale(self):
        """Buy 100 @ 5 (2023, basis 500); Einlagenrückgewähr 300 (2024);
        sell 100 @ 10 (2025). Basis at sale = 500 − 300 = 200 -> gain 800.
        An engine that loses the reduction in SoY reconstruction declares 500
        — UNDERSTATING income by the repayment amount."""
        isin = "US000000EEE1"
        out, flv = self._run(
            trades=[
                _trade(isin, "2023-03-01", "100", "5", "BUY", "O", "T1"),
                _trade(isin, "2025-03-01", "-100", "10", "SELL", "C", "T2"),
            ],
            cash_rows=[_repayment(isin, "2024-06-03", "300", "CT1")],
            # Broker's SoY snapshot reports the post-repayment cost (200) — but
            # the reconstruction-sufficient path must carry the reduction
            # itself, not depend on the snapshot.
            pos_soy=[_pos(isin, "100", "10", cost="200")],
            pos_eoy=[],
        )
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("800.00")
        # The 2024 repayment itself is NOT income of 2025.
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("800.00")


class TestFifoSequentialAllocation(_RepaymentScenarioBase):
    def test_partial_exit_after_spillover_uses_zeroed_first_lot(self):
        """Lots 100 @ 5 and 100 @ 8 (2023); Einlagenrückgewähr 700 (2025-05):
        FIFO-sequential -> lot 1: 500 -> 0, spill 200 -> lot 2: 800 -> 600.
        Sell 100 @ 10 (2025-07): consumes lot 1 (basis 0) -> gain 1000.
        The per-share alternative (700/200 = 3,50 per share) would leave lot 1
        at 150 and declare only 850 — pinning 1000 pins the allocation rule."""
        isin = "US000000GGG1"
        out, flv = self._run(
            trades=[
                _trade(isin, "2023-03-01", "100", "5", "BUY", "O", "T1"),
                _trade(isin, "2023-09-01", "100", "8", "BUY", "O", "T2"),
                _trade(isin, "2025-07-01", "-100", "10", "SELL", "C", "T3"),
            ],
            cash_rows=[_repayment(isin, "2025-05-02", "700", "CT1")],
            pos_soy=[_pos(isin, "200", "9", cost="1300")],
            pos_eoy=[_pos(isin, "100", "10", cost="600")],
        )
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("1000.00")
        # No excess (700 < 1300): the repayment itself must not be income.
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("1000.00")


class TestExcessOverAllLots(_RepaymentScenarioBase):
    def test_excess_is_immediate_income_in_the_sonstige_pot(self):
        """Lot 100 @ 2 (2023, basis 200); Einlagenrückgewähr 300 (2025):
        basis -> 0, residual 100 is taxed NOW as sonstige Kapitalerträge
        (Z19 pot) — not deferred (negative-AK reading) and not Aktiengewinn.
        The shares stay held (no sale this year)."""
        isin = "US000000HHH1"
        out, flv = self._run(
            trades=[_trade(isin, "2023-03-01", "100", "2", "BUY", "O", "T1")],
            cash_rows=[_repayment(isin, "2025-06-02", "300", "CT1")],
            pos_soy=[_pos(isin, "100", "3", cost="200")],
            pos_eoy=[_pos(isin, "100", "3", cost="0")],
        )
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("100.00")
        assert flv.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN, Decimal("0")) == Decimal("0.00")


class TestCrossYearExcessTiming(_RepaymentScenarioBase):
    def test_prior_year_excess_is_not_re_taxed_in_the_sale_year(self):
        """Lot 100 @ 2 (2023); Einlagenrückgewähr 300 (2024) — basis -> 0 and
        the 100 excess was VZ-2024 income (not this return's). Sell 100 @ 10
        (2025): gain = 1000 − 0 = 1000 on Z20; Z19 must contain ONLY that gain
        (no resurrected repayment income)."""
        isin = "US000000III1"
        out, flv = self._run(
            trades=[
                _trade(isin, "2023-03-01", "100", "2", "BUY", "O", "T1"),
                _trade(isin, "2025-03-01", "-100", "10", "SELL", "C", "T2"),
            ],
            cash_rows=[_repayment(isin, "2024-06-03", "300", "CT1")],
            pos_soy=[_pos(isin, "100", "3", cost="0")],
            pos_eoy=[],
        )
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("1000.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("1000.00")

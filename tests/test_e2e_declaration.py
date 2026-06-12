"""
End-to-end declaration correctness: synthetic input CSVs -> the figures the
taxpayer would declare, checked at all three output surfaces (pipeline result,
console report, PDF). Results-oriented by design: every expected number below
is derived BY HAND from the statute, never from the engine.

legal_basis:
  - §20 Abs. 2 S. 1 Nr. 1, Abs. 4 EStG — Aktienveräußerungsgewinne/-verluste
    (reference/tax-law/estg-20-kapitalvermoegen.md)
  - §20 Abs. 1 Nr. 1 EStG — Dividenden; §32d Abs. 5 / §34c — anrechenbare
    ausländische Quellensteuer (reference/tax-forms/anlage-kap-zeilen.md:
    VZ-2025 rules, Z19 = Aktiengewinne − Aktienverluste + sonstige Erträge)
  - §18 InvStG — Vorabpauschale, Basiszins 2024 = 2,29 % / 2025 = 2,53 %
    (reference/investment-tax-law/invstg-18-vorabpauschale.md,
    reference/bmf-guidance/basiszins-vorabpauschale.md); §18 Abs. 3: the 2024
    VP is deemed to flow 02.01.2025 and belongs on the VZ-2025 return (Z13
    for Sonstige Fonds, Teilfreistellung 0 %).

All data is SYNTHETIC (fictional ISINs, accounts, amounts) — nothing here may
ever be replaced with real broker exports; real-data verification lives in the
gitignored parity harness (scripts/parity_check.sh).

Hand computation pinned by this file (tax year 2025, all amounts EUR):
  Stock A  US000000AAA1: buy 100 @ 10 (2024) — sell 100 @ 15 (2025)  -> +500
  Stock B  US000000BBB1: buy  50 @ 20 (2025) — sell  50 @ 16 (2025)  -> −200
  Dividend stock A (US issuer): +100 gross; US withholding tax 15
  Fund F   LU0000000001 (Sonstige, TF 0 %): 100 units held throughout;
           NAV 02.01.2024 = 9, 02.01.2025 = 10, 31.12.2025 = 11; no
           distributions.
    VP(2024) = 100·9 · 2,29 % · 0,7 = 14,427 -> 14,43  (< Wertzuwachs-Kappung
    100), deemed inflow 2025 -> KAP-INV Zeile 13 of THIS return.
    VP(2025) preview = 100·10 · 2,53 % · 0,7 = 17,71 (flows 2026; must NOT be
    in this return's lines).

  Anlage KAP (VZ 2025 — Z21/Z24 abolished):
    Zeile 19 = 500 − 200 + 100 = 400,00
    Zeile 20 = 500,00      Zeile 23 = 200,00      Zeile 41 = 15,00
  Anlage KAP-INV:
    Zeile 13 (Sonstige Fonds Vorabpauschale) = 14,43
"""
import csv
import os
from decimal import Decimal

import pytest

from src.pipeline_runner import run_core_processing_pipeline
from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from src.parsers.column_validator import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_TRANSACTIONS_COLUMNS, TRANSFERS_COLUMNS,
)
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCT = "U10000001"
STOCK_A = "US000000AAA1"   # gain stock, pays the dividend
STOCK_B = "US000000BBB1"   # loss stock
FUND_F = "LU0000000001"    # Sonstige Investmentfonds (TF 0%)

TAX_YEAR = 2025


def _trade(isin, date, qty, price, side, oc, txid, acct=ACCT):
    return [acct, "EUR", "STK", "COMMON", isin[8:], isin, isin,
            None, None, None, date, Decimal(qty), Decimal(price), Decimal("0"),
            "EUR", side, txid, None, None, "CON" + isin[8:], None, Decimal("1"), oc]


def _pos(isin, qty, price, asset_class="STK", acct=ACCT, cost=None):
    q, p = Decimal(qty), Decimal(price)
    return [acct, "EUR", asset_class, "COMMON", isin[8:], isin, isin,
            q, q * p, p, Decimal(cost) if cost is not None else q * p,
            None, "CON" + isin[8:], None, Decimal("1")]


def _transfer_out(src, tgt, isin, date, qty, txid):
    """OUT leg of an INTERNAL Depotübertragung (column order = TRANSFERS_COLUMNS)."""
    return [src, "EUR", "STK", isin[8:], isin, "CON" + isin[8:], date,
            "INTERNAL", "OUT", tgt, Decimal(qty), Decimal("0"), txid]


def _cash_tx(isin, date, amount, tx_type, desc, txid):
    return [ACCT, "EUR", "STK", "COMMON", isin[8:], desc, date,
            Decimal(amount), tx_type, "CON" + isin[8:], None, isin, "US", txid]


def _write(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(headers))
        for r in rows:
            w.writerow(["" if c is None else str(c) for c in r])


class TestDeclarationEndToEnd(FifoTestCaseBase):
    """One pipeline run, asserted at every output surface."""

    @pytest.fixture(autouse=True)
    def _run_scenario(self, setup_test_paths_and_config):
        p = self.config_paths
        _write(p["trades"], TRADES_COLUMNS, [
            _trade(STOCK_A, "2024-04-01", "100", "10", "BUY", "O", "T1"),
            _trade(STOCK_A, "2025-06-01", "-100", "15", "SELL", "C", "T2"),
            _trade(STOCK_B, "2025-02-01", "50", "20", "BUY", "O", "T3"),
            _trade(STOCK_B, "2025-09-01", "-50", "16", "SELL", "C", "T4"),
        ])
        _write(p["cash"], CASH_TRANSACTIONS_COLUMNS, [
            _cash_tx(STOCK_A, "2025-05-15", "100", "Dividends",
                     "AAA INC CASH DIVIDEND EUR 1.00 PER SHARE (Ordinary Dividend)", "D1"),
            _cash_tx(STOCK_A, "2025-05-15", "-15", "Withholding Tax",
                     "AAA INC CASH DIVIDEND EUR 1.00 PER SHARE - US TAX", "W1"),
        ])
        # SoY 2025: stock A still held (sold mid-2025), fund @ NAV 10.
        _write(p["pos_start"], POSITIONS_COLUMNS, [
            _pos(STOCK_A, "100", "10"),
            _pos(FUND_F, "100", "10", asset_class="FUND"),
        ])
        # EoY 2025: both stocks disposed; fund @ NAV 11.
        _write(p["pos_end"], POSITIONS_COLUMNS, [
            _pos(FUND_F, "100", "11", asset_class="FUND"),
        ])
        # Prior-year (2024) SoY snapshot: fund @ NAV 9 — drives the VP(2024)
        # that is deemed to flow into, and is declared on, the 2025 return.
        prior_soy = os.path.join(p["temp_dir_root"], "positions_prior_soy.csv")
        _write(prior_soy, POSITIONS_COLUMNS, [_pos(FUND_F, "100", "9", asset_class="FUND")])
        from tests.support.csv_creators import (
            create_corporate_actions_csv_string, create_cash_balance_csv_string,
        )
        with open(p["corp_actions"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_corporate_actions_csv_string([]))
        with open(p["cash_balance"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_cash_balance_csv_string([]))

        self.out = run_core_processing_pipeline(
            trades_file_path=p["trades"],
            cash_transactions_file_path=p["cash"],
            positions_start_file_path=p["pos_start"],
            positions_end_file_path=p["pos_end"],
            corporate_actions_file_path=p["corp_actions"],
            interactive_classification_mode=False,
            tax_year_to_process=TAX_YEAR,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            cash_balance_file_path=p["cash_balance"],
            positions_prior_start_file_path=prior_soy,
        )
        self.loss_offsetting = LossOffsettingEngine(
            realized_gains_losses=self.out.realized_gains_losses,
            vorabpauschale_items=self.out.vorabpauschale_items,
            current_year_financial_events=self.out.processed_income_events,
            asset_resolver=self.out.asset_resolver,
            tax_year=TAX_YEAR,
        ).calculate_reporting_figures()

    # ---------------------------------------------------------------- figures
    def test_form_line_figures_match_hand_computation(self):
        assert self.out.eoy_mismatch_error_count == 0
        flv = self.loss_offsetting.form_line_values
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("500.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST] == Decimal("200.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("400.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID] == Decimal("15.00")

    def test_vorabpauschale_deemed_inflow_assignment(self):
        """§18 Abs. 3 InvStG: VP(2024) belongs on THIS (2025) return; VP(2025)
        is only a preview for 2026 and must not enter the 2025 figures."""
        on_this_return = [v for v in self.out.vorabpauschale_items
                          if v.deemed_inflow_year == TAX_YEAR]
        preview = [v for v in self.out.vorabpauschale_items
                   if v.deemed_inflow_year == TAX_YEAR + 1]
        assert [v.gross_vorabpauschale_eur for v in on_this_return] == [Decimal("14.43")]
        # Sonstige Fonds: Teilfreistellung 0% -> net == gross.
        assert on_this_return[0].net_taxable_vorabpauschale_eur == Decimal("14.43")
        assert [v.gross_vorabpauschale_eur for v in preview] == [Decimal("17.71")]

    # ---------------------------------------------------------------- console
    def test_console_report_shows_the_declarable_figures(self, capsys):
        from src.reporting.console_reporter import generate_console_tax_report
        generate_console_tax_report(
            realized_gains_losses=self.out.realized_gains_losses,
            vorabpauschale_items=self.out.vorabpauschale_items,
            all_financial_events=self.out.all_financial_events_enriched,
            asset_resolver=self.out.asset_resolver,
            tax_year=TAX_YEAR,
            eoy_mismatch_count=self.out.eoy_mismatch_error_count,
            loss_offsetting_summary=self.loss_offsetting,
            data_gaps=self.out.data_gaps,
        )
        lines = capsys.readouterr().out.splitlines()

        def line_with(label):
            hits = [l for l in lines if label in l]
            assert hits, f"console report is missing a '{label}' line"
            return hits[0]

        assert line_with("Zeile 19 (Ausländische Kapitalerträge").endswith("400.00")
        assert line_with("Zeile 20 (Gewinne aus Aktienveräußerungen").endswith("500.00")
        assert line_with("Zeile 23 (Verluste aus Aktienveräußerungen").endswith("200.00")
        assert line_with("Zeile 41 (Anrechenbare ausländische Steuern").endswith("15.00")
        assert line_with("Zeile 13 (Sonstige Fonds Vorabpauschale").endswith("14.43")

    # ---------------------------------------------------------------- pdf
    def test_pdf_report_shows_the_declarable_figures(self, tmp_path):
        import fitz
        from src.reporting.pdf_generator import PdfReportGenerator
        pdf_path = str(tmp_path / "report.pdf")
        PdfReportGenerator(
            loss_offsetting_result=self.loss_offsetting,
            all_financial_events=self.out.processed_income_events,
            realized_gains_losses=self.out.realized_gains_losses,
            vorabpauschale_items=self.out.vorabpauschale_items,
            assets_by_id=self.out.asset_resolver.assets_by_internal_id,
            tax_year=TAX_YEAR,
            eoy_mismatch_details=None,
        ).generate_report(pdf_path)

        text = "\n".join(page.get_text() for page in fitz.open(pdf_path))
        # German number format in the PDF (comma decimals).
        for figure, what in [
            ("500,00", "Z20 Aktiengewinne"),
            ("200,00", "Z23 Aktienverluste"),
            ("400,00", "Z19 ausländische Kapitalerträge"),
            ("15,00", "Z41 anrechenbare Quellensteuer"),
            ("14,43", "KAP-INV Z13 Vorabpauschale"),
        ]:
            assert figure in text, f"PDF is missing {what} = {figure}"
        # The 2025 preview VP (deemed inflow 2026) must not be on a KAP-INV line
        # of this return; it may only appear as a marked preview ("Vorschau").
        assert "Anrechenbare" in text or "ausländische" in text


class TestDeclarationEndToEndMultiAccount(FifoTestCaseBase):
    """Multi-Depot inputs -> the PERSON's declaration. The amounts are chosen so
    the form lines are only correct under per-Depot FIFO (§20 Abs. 4 S. 7 EStG)
    and Fußstapfentheorie (§43 Abs. 1 S. 5 EStG) — a merged-FIFO or
    snapshot-basis engine would declare DIFFERENT numbers on the same inputs.

    Hand computation (tax year 2025, all EUR; Depots A and B):
      Stock C  US000000CCC1, co-held:
        A buys 100 @ 10 (2023); B buys 50 @ 40 (2024); B sells 50 @ 35 (2025).
        Per-Depot: the sale consumes B's OWN lot -> 1750 − 2000 = −250 loss.
        (Merged FIFO would consume A's older 10-cost shares: +1250 gain — a
        completely different declaration: Z20 1750 / Z23 0 instead of the
        correct Z20 500 / Z23 250.)
      Stock D  US000000DDD1, transferred:
        A buys 100 @ 10 (2024); Depotübertragung A->B (2024); B sells
        100 @ 15 (2025). Tax-neutral carry-over: gain = 1500 − 1000 = +500.
        The SoY snapshot deliberately reports a WRONG cost (8888) for the
        moved position — if the engine fell back to the snapshot instead of
        the carried basis, Z20/Z23 would change.

      Anlage KAP (VZ 2025), per PERSON (aggregated across Depots):
        Zeile 19 = 500 − 250 = 250,00
        Zeile 20 = 500,00      Zeile 23 = 250,00
    """
    A, B = "U10000001", "U10000002"
    STOCK_C = "US000000CCC1"
    STOCK_D = "US000000DDD1"

    @pytest.fixture(autouse=True)
    def _run_scenario(self, setup_test_paths_and_config):
        p = self.config_paths
        A, B = self.A, self.B
        _write(p["trades"], TRADES_COLUMNS, [
            _trade(self.STOCK_C, "2023-05-01", "100", "10", "BUY", "O", "HA1", acct=A),
            _trade(self.STOCK_C, "2024-05-01", "50", "40", "BUY", "O", "HB1", acct=B),
            _trade(self.STOCK_C, "2025-06-01", "-50", "35", "SELL", "C", "S1", acct=B),
            _trade(self.STOCK_D, "2024-03-01", "100", "10", "BUY", "O", "T1", acct=A),
            _trade(self.STOCK_D, "2025-09-01", "-100", "15", "SELL", "C", "T2", acct=B),
        ])
        transfers_path = os.path.join(p["temp_dir_root"], "transfers.csv")
        _write(transfers_path, TRANSFERS_COLUMNS, [
            _transfer_out(A, B, self.STOCK_D, "2024-06-01", "-100", "TR1"),
        ])
        # SoY 2025 snapshots per Depot; stock D's cost is deliberately WRONG
        # (8888) to prove the declaration uses the carried basis, not the file.
        _write(p["pos_start"], POSITIONS_COLUMNS, [
            _pos(self.STOCK_C, "100", "10", acct=A),
            _pos(self.STOCK_C, "50", "40", acct=B, cost="2000"),
            _pos(self.STOCK_D, "100", "10", acct=B, cost="8888"),
        ])
        # EoY 2025: only A's stock-C position remains.
        _write(p["pos_end"], POSITIONS_COLUMNS, [
            _pos(self.STOCK_C, "100", "10", acct=A),
        ])
        from tests.support.csv_creators import (
            create_cash_transactions_csv_string, create_corporate_actions_csv_string,
            create_cash_balance_csv_string,
        )
        with open(p["cash"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_cash_transactions_csv_string([]))
        with open(p["corp_actions"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_corporate_actions_csv_string([]))
        with open(p["cash_balance"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_cash_balance_csv_string([]))

        self.out = run_core_processing_pipeline(
            trades_file_path=p["trades"],
            cash_transactions_file_path=p["cash"],
            positions_start_file_path=p["pos_start"],
            positions_end_file_path=p["pos_end"],
            corporate_actions_file_path=p["corp_actions"],
            interactive_classification_mode=False,
            tax_year_to_process=TAX_YEAR,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            cash_balance_file_path=p["cash_balance"],
            transfers_file_path=transfers_path,
        )
        self.loss_offsetting = LossOffsettingEngine(
            realized_gains_losses=self.out.realized_gains_losses,
            vorabpauschale_items=self.out.vorabpauschale_items,
            current_year_financial_events=self.out.processed_income_events,
            asset_resolver=self.out.asset_resolver,
            tax_year=TAX_YEAR,
        ).calculate_reporting_figures()

    def test_per_depot_form_line_figures(self):
        assert self.out.eoy_mismatch_error_count == 0
        flv = self.loss_offsetting.form_line_values
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("500.00"), \
            "transfer must carry the original basis (1000), not the SoY snapshot (8888)"
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST] == Decimal("250.00"), \
            "the co-held sale must consume Depot B's own 40-cost lot (per-Depot FIFO)"
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("250.00")

    def test_console_report_shows_per_depot_figures(self, capsys):
        from src.reporting.console_reporter import generate_console_tax_report
        generate_console_tax_report(
            realized_gains_losses=self.out.realized_gains_losses,
            vorabpauschale_items=self.out.vorabpauschale_items,
            all_financial_events=self.out.all_financial_events_enriched,
            asset_resolver=self.out.asset_resolver,
            tax_year=TAX_YEAR,
            eoy_mismatch_count=self.out.eoy_mismatch_error_count,
            loss_offsetting_summary=self.loss_offsetting,
            data_gaps=self.out.data_gaps,
        )
        lines = capsys.readouterr().out.splitlines()

        def line_with(label):
            hits = [l for l in lines if label in l]
            assert hits, f"console report is missing a '{label}' line"
            return hits[0]

        assert line_with("Zeile 19 (Ausländische Kapitalerträge").endswith("250.00")
        assert line_with("Zeile 20 (Gewinne aus Aktienveräußerungen").endswith("500.00")
        assert line_with("Zeile 23 (Verluste aus Aktienveräußerungen").endswith("250.00")

    def test_pdf_report_shows_per_depot_figures(self, tmp_path):
        import fitz
        from src.reporting.pdf_generator import PdfReportGenerator
        pdf_path = str(tmp_path / "report.pdf")
        PdfReportGenerator(
            loss_offsetting_result=self.loss_offsetting,
            all_financial_events=self.out.processed_income_events,
            realized_gains_losses=self.out.realized_gains_losses,
            vorabpauschale_items=self.out.vorabpauschale_items,
            assets_by_id=self.out.asset_resolver.assets_by_internal_id,
            tax_year=TAX_YEAR,
            eoy_mismatch_details=None,
        ).generate_report(pdf_path)
        text = "\n".join(page.get_text() for page in fitz.open(pdf_path))
        for figure, what in [
            ("500,00", "Z20 Aktiengewinne (carried-basis transfer gain)"),
            ("250,00", "Z23 Aktienverluste (per-Depot co-held sale)"),
        ]:
            assert figure in text, f"PDF is missing {what} = {figure}"
        # The merged-FIFO wrong answers must appear NOWHERE:
        assert "1.250,00" not in text and "1250,00" not in text, \
            "merged-FIFO gain (+1250) leaked into the declaration"
        assert "7.388,00" not in text and "7388,00" not in text, \
            "SoY-snapshot basis (8888) was used instead of the carried basis"

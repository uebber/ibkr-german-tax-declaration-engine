"""
C2/C3 — cash merger (Barabfindung) and forward split, results-oriented:
synthetic Corporate_Actions + Trades CSVs in -> declared figures out.

legal_basis:
  - C2 cash merger: §20 Abs. 2 S. 1 Nr. 1, Abs. 4 EStG — shares taken out
    against cash are a Veräußerung; gain = cash proceeds − acquisition cost,
    in the AKTIEN pot (reference/tax-forms/anlage-kap-zeilen.md: "Cash merger
    proceeds (stock)" under Z20/Z23; engine RealizationType
    CASH_MERGER_PROCEEDS).
  - C3 forward split: §20 Abs. 4a EStG / general Gewinnermittlung — a split
    is NOT a taxable event; the lots' quantity multiplies, the TOTAL
    acquisition cost is unchanged, and the LATER sale realises the same gain
    as without the split (reference/tax-law/estg-20-kapitalvermoegen.md,
    Abs. 4a; the split processor was imported with main and never tested —
    legal-review coverage gap #C3).

All data synthetic; hand-computed figures in each docstring.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.test_e2e_declaration import _trade, _pos

ACCT = "U10000001"
TAX_YEAR = 2025


class _CorpActionBase(FifoTestCaseBase):
    def _run(self, trades, corp_actions, pos_soy, pos_eoy):
        out = self._run_pipeline(
            trades_data=trades,
            corporate_actions_data=corp_actions,
            positions_start_data=pos_soy,
            positions_end_data=pos_eoy,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        flv = LossOffsettingEngine(
            realized_gains_losses=out.realized_gains_losses,
            vorabpauschale_items=out.vorabpauschale_items,
            current_year_financial_events=out.processed_income_events,
            asset_resolver=out.asset_resolver,
            tax_year=TAX_YEAR,
        ).calculate_reporting_figures().form_line_values
        return out, flv


class TestCashMerger(_CorpActionBase):
    def test_cash_merger_gain_is_a_stock_gain(self):
        """100 MMM bought @ 10 (2024, basis 1000); 2025 cash merger pays
        EUR 14 per share -> proceeds 1400, gain 400. The disposal is a
        Veräußerung of shares: Zeile 20 = 400,00 (Aktien pot, NOT sonstige)."""
        isin = "DE000000MMM1"
        trades = [_trade(isin, "2024-04-01", "100", "10", "BUY", "O", "T1")]
        corp_actions = [
            [ACCT, "MMM1", f"MMM1({isin}) MERGED(Acquisition) FOR EUR 14 PER SHARE",
             isin, "2025-07-15", "TC", "TC", "900000001",
             "CON" + isin[8:], "", "", "EUR", "0", "1400", "-1000", "-100"],
        ]
        pos_soy = [_pos(isin, "100", "10")]
        out, flv = self._run(trades, corp_actions, pos_soy, [])

        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("400.00"), \
            "cash merger proceeds − basis must land in the Aktien pot (Z20)"
        assert flv.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST, Decimal("0")) == Decimal("0.00")

    def test_cash_merger_below_basis_is_a_stock_loss(self):
        """100 NNN bought @ 10 (2024, basis 1000); cash merger pays EUR 7
        per share -> proceeds 700, loss 300 -> Zeile 23 = 300,00 (the Aktien
        loss pot, ring-fenced under §20 Abs. 6 S. 4)."""
        isin = "DE000000NNN1"
        trades = [_trade(isin, "2024-04-01", "100", "10", "BUY", "O", "T1")]
        corp_actions = [
            [ACCT, "NNN1", f"NNN1({isin}) MERGED(Acquisition) FOR EUR 7 PER SHARE",
             isin, "2025-07-15", "TC", "TC", "900000002",
             "CON" + isin[8:], "", "", "EUR", "0", "700", "-1000", "-100"],
        ]
        pos_soy = [_pos(isin, "100", "10")]
        out, flv = self._run(trades, corp_actions, pos_soy, [])

        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST] == Decimal("300.00")
        assert flv.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN, Decimal("0")) == Decimal("0.00")

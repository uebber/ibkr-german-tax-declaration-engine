"""
C4 — CFD lifecycle, results-oriented: synthetic Trades CSVs in -> declared
VZ-2025 figures out, hand-computed.

legal_basis: §20 Abs. 2 S. 1 Nr. 3 EStG — CFDs are Termingeschäfte
(reference/tax-law/estg-20-kapitalvermoegen.md, Satz 1 Nr. 3: engine mapping
includes CFD gains/losses; reference/tax-forms/anlage-kap-zeilen.md: VZ 2025
derivative gains flow into Zeile 19, losses into Zeile 22 — the §20 Abs. 6
S. 5 loss cap is retroactively repealed, JStG 2024). CFD results must NEVER
touch the Aktien pot (Z20/Z23): a CFD on a stock is not a share disposal.

The legal review found the CFD path completely untested. All data synthetic.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCT = "U10000001"
TAX_YEAR = 2025


def _cfd_trade(symbol, conid, date, qty, price, side, oc, txid):
    """One Trades row for a CFD (AssetClass CFD, no ISIN)."""
    return [ACCT, "EUR", "CFD", "", symbol, f"{symbol} CFD", "",
            None, None, None, date, Decimal(qty), Decimal(price), Decimal("0"),
            "EUR", side, txid, None, None, conid, None, Decimal("1"), oc]


class _CfdBase(FifoTestCaseBase):
    def _run(self, trades):
        out = self._run_pipeline(
            trades_data=trades,
            positions_start_data=[],
            positions_end_data=[],
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


class TestCfdLifecycle(_CfdBase):
    def test_long_cfd_gain_is_a_derivative_gain(self):
        """Open 10 long CFD @ 100, close @ 130 -> gain 300,00. VZ 2025:
        flows into Zeile 19 (derivative gain) — NOT Zeile 20 (no share was
        disposed)."""
        trades = [
            _cfd_trade("ABCCFD", "CONCFD1", "2025-03-01", "10", "100", "BUY", "O", "C1"),
            _cfd_trade("ABCCFD", "CONCFD1", "2025-08-01", "-10", "130", "SELL", "C", "C2"),
        ]
        out, flv = self._run(trades)
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("300.00")
        assert flv.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN, Decimal("0")) == Decimal("0.00"), \
            "a CFD result must never enter the Aktien pot"

    def test_short_cfd_loss_is_a_derivative_loss(self):
        """Sell 10 CFD short @ 100 (proceeds 1000), cover @ 140 (cost 1400)
        -> loss 400,00. VZ 2025: Zeile 22 = 400,00 (gross derivative loss;
        cap repealed), Zeile 19 nets to −400,00; Aktien pots untouched."""
        trades = [
            _cfd_trade("XYZCFD", "CONCFD2", "2025-02-01", "-10", "100", "SELL", "O", "C1"),
            _cfd_trade("XYZCFD", "CONCFD2", "2025-09-01", "10", "140", "BUY", "C", "C2"),
        ]
        out, flv = self._run(trades)
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE] == Decimal("400.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("-400.00")
        assert flv.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST, Decimal("0")) == Decimal("0.00"), \
            "a CFD loss must never enter the ring-fenced Aktien loss pot"

    def test_cross_year_cfd_position(self):
        """Open 10 long CFD @ 100 in 2024 (historical), close @ 90 in 2025
        -> loss 100,00 on Zeile 22; the historical open must reconstruct the
        position (SoY snapshot lists the open CFD)."""
        trades = [
            _cfd_trade("HSTCFD", "CONCFD3", "2024-11-01", "10", "100", "BUY", "O", "C1"),
            _cfd_trade("HSTCFD", "CONCFD3", "2025-04-01", "-10", "90", "SELL", "C", "C2"),
        ]
        # SoY 2025 snapshot carries the open CFD position.
        pos_soy = [[ACCT, "EUR", "CFD", "", "HSTCFD", "HSTCFD CFD", "",
                    Decimal("10"), Decimal("1000"), Decimal("100"), Decimal("1000"),
                    None, "CONCFD3", None, Decimal("1")]]
        out = self._run_pipeline(
            trades_data=trades,
            positions_start_data=pos_soy,
            positions_end_data=[],
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
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE] == Decimal("100.00")

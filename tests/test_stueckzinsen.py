"""
C7 — Stückzinsen (accrued interest), results-oriented.

legal_basis: §20 Abs. 1 Nr. 7 EStG / BMF Einzelfragen zur Abgeltungsteuer
(reference/bmf-guidance/abgeltungsteuer-einzelfragen.md, Zinsen):
- Stückzinsen PAID at a bond purchase are negative Einnahmen aus
  Kapitalvermögen in the payment year (not part of the bond's acquisition
  cost) — VZ 2025: they appear among the Zeile-22 losses and reduce the
  Zeile-19 net (reference/tax-forms/anlage-kap-zeilen.md: "Stückzinsen
  (paid = negative income at acquisition)").
- Stückzinsen RECEIVED on a bond sale are interest income (Zeile 19).

Scenario (hand-computed): buy 10 bonds @ 100 paying 80 Stückzinsen; sell at
the same price receiving 50 Stückzinsen -> bond G/L exactly 0; Zeile 19 =
50 − 80 = −30,00 net; Zeile 22 = 80,00 gross. The legal review found no
test exercising either Stückzinsen direction. All data synthetic.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCT = "U10000001"
TAX_YEAR = 2025
BOND_ISIN = "DE000000BND1"


def _bond_trade(date, qty, price, side, oc, txid):
    return [ACCT, "EUR", "BOND", "", "BND1", BOND_ISIN, BOND_ISIN,
            None, None, None, date, Decimal(qty), Decimal(price), Decimal("0"),
            "EUR", side, txid, None, None, "CONBND1", None, Decimal("1"), oc]


def _accrued(date, amount, txid):
    return [ACCT, "EUR", "BOND", "", "BND1",
            f"BND1({BOND_ISIN}) BOND ACCRUED INT", date,
            Decimal(amount), "Bond Interest", "CONBND1", None, BOND_ISIN, "DE", txid]


class TestStueckzinsen(FifoTestCaseBase):
    def test_paid_is_negative_income_received_is_interest(self):
        trades = [
            _bond_trade("2025-04-01", "10", "100", "BUY", "O", "B1"),
            _bond_trade("2025-09-01", "-10", "100", "SELL", "C", "B2"),
        ]
        cash_tx = [
            _accrued("2025-04-01", "-80", "SZ1"),   # paid at purchase
            _accrued("2025-09-01", "50", "SZ2"),    # received at sale
        ]
        out = self._run_pipeline(
            trades_data=trades,
            positions_start_data=[],
            positions_end_data=[],
            cash_transactions_data=cash_tx,
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
        # Bond bought and sold at the same price: G/L 0 by construction —
        # the Stückzinsen must NOT be folded into the bond's basis/proceeds.
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("-30.00"), \
            "Z19 net = received 50 − paid 80; Stückzinsen are income items, not basis"
        assert flv[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE] == Decimal("80.00"), \
            "paid Stückzinsen are negative Einnahmen — gross on the Zeile-22 side"

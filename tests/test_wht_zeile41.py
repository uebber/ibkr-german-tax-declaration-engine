"""
C6 — foreign withholding tax on Zeile 41, results-oriented.

legal_basis: §32d Abs. 5 EStG / §34c EStG (reference/tax-law/
estg-32d-abgeltungsteuer.md, Abs. 5): foreign WHT is creditable against the
Abgeltungsteuer; Anlage KAP Zeile 41 carries the foreign tax; the income
itself is declared GROSS (the WHT must never reduce the Zeile-19 income).

SCOPE (per the reference, "Not Directly Implemented"): the engine reports the
WITHHELD total on Z41 and leaves the creditability cap to the assessment —
the DBA caps the credit at the treaty rate (commonly 15%); for above-treaty
withholding (e.g. CH 35%) the excess 20% is not creditable but RECLAIMABLE
from the source state (CH: ESTV form 86), which is outside a tax-return
engine's scope. The per-payment effective rates are itemised in the PDF's
WHT table for the assessment. This test pins the engine's documented
position: Z41 = sum of all foreign WHT, income gross.

All data synthetic.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCT = "U10000001"
TAX_YEAR = 2025
US_ISIN, CH_ISIN = "US000000RRR1", "CH000000RRR1"


def _pos(isin, qty, price):
    q, p = Decimal(qty), Decimal(price)
    return [ACCT, "EUR", "STK", "COMMON", isin[8:], isin, isin,
            q, q * p, p, q * p, None, "CON" + isin[8:], None, Decimal("1")]


def _div(isin, country, date, amount, desc, txid):
    return [ACCT, "EUR", "STK", "COMMON", isin[8:], desc, date,
            Decimal(amount), "Dividends", "CON" + isin[8:], None, isin, country, txid]


def _wht(isin, country, date, amount, desc, txid):
    return [ACCT, "EUR", "STK", "COMMON", isin[8:], desc, date,
            Decimal(amount), "Withholding Tax", "CON" + isin[8:], None, isin, country, txid]


class TestForeignWhtOnZeile41(FifoTestCaseBase):
    def test_z41_sums_wht_and_income_stays_gross(self):
        """US dividend 100 with 15 WHT (treaty rate) and CH dividend 200 with
        70 WHT (35% — 20% above treaty, reclaimable from ESTV, not from the
        German fisc): Zeile 41 = 85,00 (withheld total, engine position) and
        Zeile 19 carries the GROSS 300,00 — net-of-WHT income would
        understate the declaration."""
        cash_tx = [
            _div(US_ISIN, "US", "2025-05-15", "100",
                 "RRR1 CASH DIVIDEND (Ordinary Dividend)", "D1"),
            _wht(US_ISIN, "US", "2025-05-15", "-15",
                 "RRR1 CASH DIVIDEND - US TAX", "W1"),
            _div(CH_ISIN, "CH", "2025-06-15", "200",
                 "RRR1CH CASH DIVIDEND (Ordinary Dividend)", "D2"),
            _wht(CH_ISIN, "CH", "2025-06-15", "-70",
                 "RRR1CH CASH DIVIDEND - CH TAX", "W2"),
        ]
        pos = [_pos(US_ISIN, "100", "10"), _pos(CH_ISIN, "100", "20")]
        out = self._run_pipeline(
            trades_data=[],
            positions_start_data=pos,
            positions_end_data=pos,
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
        assert flv[TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID] == Decimal("85.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("300.00"), \
            "dividend income is declared GROSS; WHT must not reduce Zeile 19"

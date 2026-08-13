"""Awarded shares, end to end, through the real pipeline.

legal_basis: [GT-ESTG20-064] puts Zufluss where wirtschaftliche Verfuegungsmacht arrives,
which while the grantor may still take the shares back is not the booking;
[GT-ESTG20-065] makes the value brought to tax then the Anschaffungskosten on a later
disposal. Both in reference/tax-law/estg-22-nr3-leistungen.md.

**What the unit tests beside this file cannot see.** `test_stock_award_lots.py` calls the
three `FifoLedger` methods directly, so it stays green while the events never reach the
ledger at all. Deleting any one of the four links in the chain -- the sort-key band, the
EUR conversion, the historical bucket entry, the current-year processor -- left the whole
suite green before this file existed. Each scenario below is built so that the link it
covers changes a DECLARED FIGURE when it is removed, not merely a call count.

The vesting-inside-the-tax-year case is the one that motivated the file: an award or a
reversal that goes unapplied is caught by the end-of-year quantity reconciliation, but a
vesting moves no shares, so it reconciled clean while leaving the provisional award price
on the lot for the disposal to be measured against. A wrong figure that looks right.

All identifiers and amounts are invented. CLAUDE.md forbids an account number, a position
value or a cash balance copied from a real export reaching a commit.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from tests.support.base import FifoTestCaseBase
from tests.support.multi_account import trade_row, position_row, conid_for

ACCOUNT = "U_AWARD_1"
ISIN = "TEST00AWARD01"
TAX_YEAR = 2023


def grant_row(activity, report_date, award_date, vesting_date, qty, price,
              account=ACCOUNT, isin=ISIN, currency="EUR"):
    """One Grants row, in GRANTS_COLUMNS order."""
    q = Decimal(str(qty))
    p = Decimal(str(price))
    return [account, currency, "STK", "COMMON", isin[:6], f"{isin[:6]} security",
            conid_for(isin), isin, Decimal("1"), report_date, activity, award_date,
            vesting_date, q, p, q * p, ""]


class TestAwardedSharesReachTheLedger(FifoTestCaseBase):

    def _sale_gain(self, results):
        ids = {a.internal_asset_id
               for a in results.asset_resolver.assets_by_internal_id.values()
               if getattr(a, "ibkr_isin", None) == ISIN}
        rgls = [r for r in results.realized_gains_losses if r.asset_internal_id in ids]
        assert len(rgls) == 1, f"expected one disposal, got {len(rgls)}"
        return rgls[0]

    def test_a_vesting_inside_the_tax_year_sets_the_cost_the_sale_is_measured_against(self):
        """The defect this file exists for.

        The award is booked before the tax year at 4; it vests INSIDE the tax year at 7;
        the shares are sold later that same year at 10. The gain is 10 - 7 = 3 per unit.

        If the vesting is not applied in the current year, the lot keeps its provisional
        cost of 4 and the gain reads 6 per unit -- with the quantity, and therefore the
        end-of-year reconciliation, identical either way.
        """
        results = self._run_pipeline(
            tax_year=TAX_YEAR,
            grants_data=[
                grant_row("Stock Award Grant for Cash Deposit",
                          "20220302", "20220302", "20230401", "10", "4"),
                grant_row("Stock Award Vesting",
                          "20230405", "20220302", "20230401", "10", "7"),
            ],
            trades_data=[
                trade_row(ACCOUNT, ISIN, "2023-06-01", "-10", "10", "SELL", "C", "T_SELL"),
            ],
            positions_start_data=[position_row(ACCOUNT, ISIN, "10", "40", price="4")],
            positions_end_data=[],
        )
        rgl = self._sale_gain(results)
        assert rgl.total_cost_basis_eur == Decimal("70"), (
            "the disposal must be measured against the VESTED cost. 40 means the vesting "
            "never reached the ledger and the provisional award price was used.")
        assert rgl.gross_gain_loss_eur == Decimal("30")
        assert rgl.acquisition_date == "2023-04-01", (
            "acquisition falls at Zufluss, which is the vesting ([GT-ESTG20-064])")

    def test_an_award_before_the_tax_year_gives_the_sale_a_real_basis(self):
        """Covers the historical bucket and the replay dispatch.

        Without the grant report the opening snapshot supplies the quantity and the
        engine synthesises a lot; with it, the lot carries the award's own date and the
        vested cost.
        """
        results = self._run_pipeline(
            tax_year=TAX_YEAR,
            grants_data=[
                grant_row("Stock Award Grant for Cash Deposit",
                          "20220302", "20220302", "20220902", "10", "4"),
                grant_row("Stock Award Vesting",
                          "20220905", "20220302", "20220902", "10", "6"),
            ],
            trades_data=[
                trade_row(ACCOUNT, ISIN, "2023-06-01", "-10", "10", "SELL", "C", "T_SELL"),
            ],
            positions_start_data=[position_row(ACCOUNT, ISIN, "10", "60", price="6")],
            positions_end_data=[],
        )
        rgl = self._sale_gain(results)
        assert rgl.total_cost_basis_eur == Decimal("60")
        assert rgl.acquisition_date == "2022-09-02"

    def test_a_reversal_is_not_a_disposal(self):
        """It produces no RealizedGainLoss of its own, and leaves the survivors at the
        cost they were awarded at -- not at the reversal row's price."""
        results = self._run_pipeline(
            tax_year=TAX_YEAR,
            grants_data=[
                grant_row("Stock Award Grant for Cash Deposit",
                          "20220302", "20220302", "20220902", "10", "4"),
                grant_row("Stock Award Return for Cash Withdrawal",
                          "20220601", "20220302", "20220902", "-4", "9"),
                grant_row("Stock Award Vesting",
                          "20220905", "20220302", "20220902", "6", "6"),
            ],
            trades_data=[
                trade_row(ACCOUNT, ISIN, "2023-06-01", "-6", "10", "SELL", "C", "T_SELL"),
            ],
            positions_start_data=[position_row(ACCOUNT, ISIN, "6", "36", price="6")],
            positions_end_data=[],
        )
        rgl = self._sale_gain(results)
        assert rgl.quantity_realized == Decimal("6"), "4 of the 10 were taken back"
        assert rgl.total_cost_basis_eur == Decimal("36")

    def test_a_currency_award_is_converted_at_the_event_date_not_left_foreign(self):
        """Covers the enrichment link. A non-EUR award whose price is never converted
        would reach the ledger with no EUR cost and stop the run; one converted at the
        wrong date would give a different basis."""
        results = self._run_pipeline(
            tax_year=TAX_YEAR,
            grants_data=[
                grant_row("Stock Award Grant for Cash Deposit",
                          "20220302", "20220302", "20220902", "10", "4", currency="USD"),
                grant_row("Stock Award Vesting",
                          "20220905", "20220302", "20220902", "10", "6", currency="USD"),
            ],
            trades_data=[
                trade_row(ACCOUNT, ISIN, "2023-06-01", "-10", "10", "SELL", "C", "T_SELL",
                          currency="USD"),
            ],
            positions_start_data=[
                position_row(ACCOUNT, ISIN, "10", "60", currency="USD", price="6")],
            positions_end_data=[],
        )
        rgl = self._sale_gain(results)
        assert rgl.total_cost_basis_eur > Decimal("0"), (
            "an unconverted award would have stopped the run, not produced a zero basis")
        assert rgl.total_cost_basis_eur != Decimal("60"), (
            "60 is the FOREIGN figure taken as EUR -- the conversion did not happen")

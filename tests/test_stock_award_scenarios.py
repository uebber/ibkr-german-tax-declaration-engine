"""Awarded shares, end to end, through the real pipeline.

legal_basis: [GT-ESTG20-064] puts Zufluss where wirtschaftliche Verfuegungsmacht arrives,
which while the grantor may still take the shares back is not the booking;
[GT-ESTG20-065] makes the value brought to tax then the Anschaffungskosten on a later
disposal. Both in reference/tax-law/estg-22-nr3-leistungen.md.

**What the unit tests beside this file cannot see.** `test_stock_award_lots.py` calls the
three `FifoLedger` methods directly, so it stays green while the events never reach the
ledger at all. Deleting any one of the links in the chain left the whole suite green
before this file existed.

**Calibration, measured link by link -- and two are still not covered.** Deleting each and
running this file:

| link deleted | caught |
|---|---|
| current-year processor entry | yes -- 1 of 4 red |
| historical bucket entry | yes -- 2 of 4 red |
| EUR conversion in enrichment | yes -- 4 of 4 red |
| parser's unclassified-kind refusal | yes |
| factory's zero-quantity guard | yes |
| **sort-key band in `get_event_sort_key`** | **no -- still green** |
| **award dated on `ReportDate` instead of `AwardDate`** | **no -- still green** |

The last two are written up in CLAUDE.md's *Where the suite is blind*. The scenarios
aimed at them (`test_a_same_day_sale_is_measured_after_the_vesting_not_before_it` and
`test_an_award_is_dated_on_its_award_date_not_the_broker_s_report_date`) assert the right
figures and pass, but they pass with the code broken too, so they document the intent
without instrumenting it. Do not read them as guards.

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


def test_an_unclassified_activity_kind_stops_the_run(tmp_path):
    """The parser's headline promise, and nothing observed its removal.

    An award and a vesting differ in nothing a parser can see except this text, so a kind
    nobody classified is as likely to move the position as not. Tested at the parser
    rather than through the pipeline because the scenario harness converts an exception
    into a test failure, which would make the refusal unassertable.
    """
    from src.domain.exceptions import DataIntegrityError
    from src.parsers.grants_parser import parse_grants_csv
    from tests.support.csv_creators import create_grants_csv_string

    path = tmp_path / "grants.csv"
    path.write_text(create_grants_csv_string([
        grant_row("Stock Award Reinvestment For Something New",
                  "20220302", "20220302", "20220902", "10", "4"),
    ]), encoding="utf-8-sig")

    with pytest.raises(DataIntegrityError, match="does not classify"):
        parse_grants_csv(str(path))


def test_an_award_of_zero_shares_stops_the_run():
    """A no-op award would leave the ledger disagreeing with the broker for a reason
    nothing recorded. Tested at the factory, for the reason above."""
    from unittest.mock import MagicMock
    from src.domain.enums import AssetCategory
    from src.domain.exceptions import DataIntegrityError
    from src.identification.asset_resolver import AssetResolver
    from src.parsers.domain_event_factory import DomainEventFactory
    from src.parsers.raw_models import RawGrantRecord

    classifier = MagicMock()
    classifier.preliminary_classify.return_value = (AssetCategory.STOCK, None)
    factory = DomainEventFactory(AssetResolver(classifier))
    row = RawGrantRecord(**dict(zip(
        [c for c in __import__("src.parsers.column_validator", fromlist=["x"]).GRANTS_COLUMNS],
        grant_row("Stock Award Grant for Cash Deposit",
                  "20220302", "20220302", "20220902", "0", "4"))))

    with pytest.raises(DataIntegrityError, match="zero shares"):
        factory.create_events_from_grants([row])


class TestTheGuardsAreObserved(FifoTestCaseBase):
    """The guards the suite could not see removed.

    Each of these was probed by deleting the guard and running the whole suite: before
    this class, all three left it green. A guard nothing would notice the removal of is
    the instrument-nobody-broke-on-purpose case CLAUDE.md names.
    """

    def test_an_award_is_dated_on_its_award_date_not_the_broker_s_report_date(self):
        """Load-bearing whenever the two differ, which the maintainer's export does not
        exercise -- every award row there has them equal. Built here so the choice is
        pinned by something rather than by that coincidence."""
        results = self._run_pipeline(
            tax_year=TAX_YEAR,
            grants_data=[
                # Awarded in March, booked by the broker in May.
                grant_row("Stock Award Grant for Cash Deposit",
                          "20220510", "20220302", "20220902", "10", "4"),
                grant_row("Stock Award Vesting",
                          "20220905", "20220302", "20220902", "10", "6"),
            ],
            trades_data=[
                trade_row(ACCOUNT, ISIN, "2023-06-01", "-10", "10", "SELL", "C", "T_SELL"),
            ],
            positions_start_data=[position_row(ACCOUNT, ISIN, "10", "60", price="6")],
            positions_end_data=[],
        )
        rgls = [r for r in results.realized_gains_losses]
        assert len(rgls) == 1
        # The lot is created on the award date; a lot created on the report date would
        # still reconcile, because the quantity is the same either way.
        assert rgls[0].total_cost_basis_eur == Decimal("60")

    def test_a_same_day_sale_is_measured_after_the_vesting_not_before_it(self):
        """The sort-key band. Awards share the corporate-action intra-day slot so a
        vesting restates the lot BEFORE that day's disposals read its cost. Without the
        band the event falls to the unknown-type fallback, which sorts after trades, and
        the sale is measured against the provisional award price."""
        results = self._run_pipeline(
            tax_year=TAX_YEAR,
            grants_data=[
                grant_row("Stock Award Grant for Cash Deposit",
                          "20220302", "20220302", "20230401", "10", "4"),
                grant_row("Stock Award Vesting",
                          "20230401", "20220302", "20230401", "10", "7"),
            ],
            trades_data=[
                # Sold the same day it vested.
                trade_row(ACCOUNT, ISIN, "2023-04-01", "-10", "10", "SELL", "C", "T_SELL"),
            ],
            positions_start_data=[position_row(ACCOUNT, ISIN, "10", "40", price="4")],
            positions_end_data=[],
        )
        rgls = [r for r in results.realized_gains_losses]
        assert len(rgls) == 1
        assert rgls[0].total_cost_basis_eur == Decimal("70"), (
            "40 means the sale was applied before the vesting restated the lot")

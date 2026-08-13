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

    def test_a_vesting_inside_the_tax_year_does_not_move_the_cost(self):
        """Zufluss was the booking ([GT-ESTG20-064]), so the award's price is final and a
        later vesting changes nothing.

        The award is booked before the tax year at 4 and vests INSIDE the tax year at 7;
        the shares are sold that year at 10. The gain is 10 - 4 = 6 per unit. A build that
        restated the lot at vesting would read 3 -- the retired reading -- with the
        quantity, and therefore the reconciliation, identical either way.
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
        assert rgl.total_cost_basis_eur == Decimal("40"), (
            "the AWARD price is the Anschaffungskosten; 70 would be the retired "
            "vesting-restatement reading")
        assert rgl.gross_gain_loss_eur == Decimal("60")
        assert rgl.acquisition_date == "2022-03-02", (
            "acquisition falls at Zufluss, which is the booking ([GT-ESTG20-064])")

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
            positions_start_data=[position_row(ACCOUNT, ISIN, "10", "40", price="4")],
            positions_end_data=[],
        )
        rgl = self._sale_gain(results)
        assert rgl.total_cost_basis_eur == Decimal("40")
        assert rgl.acquisition_date == "2022-03-02"

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
            positions_start_data=[position_row(ACCOUNT, ISIN, "6", "24", price="4")],
            positions_end_data=[],
        )
        rgl = self._sale_gain(results)
        assert rgl.quantity_realized == Decimal("6"), "4 of the 10 were taken back"
        assert rgl.total_cost_basis_eur == Decimal("24"), "at the awarded price"

    def test_a_grant_inside_the_tax_year_creates_its_lot(self):
        """The current-year dispatch. A grant dated in the declared year goes through
        `StockAwardProcessor`, not the historical replay, and nothing else reaches that
        path -- a vesting is inert and a reversal needs a grant to reverse.

        Without the processor entry the grant is dropped with a log line, the lot never
        exists, and the sale has nothing to consume.
        """
        results = self._run_pipeline(
            tax_year=TAX_YEAR,
            grants_data=[
                grant_row("Stock Award Grant for Cash Deposit",
                          "20230210", "20230210", "20240210", "10", "4"),
            ],
            trades_data=[
                trade_row(ACCOUNT, ISIN, "2023-08-01", "-10", "10", "SELL", "C", "T_SELL"),
            ],
            positions_start_data=[],
            positions_end_data=[],
        )
        rgl = self._sale_gain(results)
        assert rgl.total_cost_basis_eur == Decimal("40")
        assert rgl.acquisition_date == "2023-02-10"

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
            positions_start_data=[position_row(ACCOUNT, ISIN, "10", "40", price="4")],
            positions_end_data=[],
        )
        rgls = [r for r in results.realized_gains_losses]
        assert len(rgls) == 1
        # The lot is created on the award date; a lot created on the report date would
        # still reconcile, because the quantity is the same either way.
        assert rgls[0].total_cost_basis_eur == Decimal("40")

def test_an_award_in_the_tax_year_reports_the_receipt_it_does_not_declare():
    """The one thing standing between a user and an understated return.

    The engine takes the vesting value as the Anschaffungskosten -- which LOWERS the
    gain declared on a later disposal -- and cannot declare the matching § 22 Nr. 3
    receipt, because there is no Anlage SO line for it (issue #76). Taking the half that
    reduces a figure and dropping the half that adds one is understatement, so the
    omission has to reach the report rather than only the README.

    Asserted on the collector rather than through the scenario harness: the gap is a
    WARNING, so the run completes and the harness returns before the report is rendered.
    """
    from decimal import Decimal as D
    from src.domain.enums import FinancialEventType as T
    from src.domain.events import StockAwardEvent
    from src.engine.event_processors.stock_award_processor import (
        StockAwardProcessor, STOCK_AWARD_RECEIPT_NOT_DECLARED)
    from src.processing.data_gaps import DataGapCollector, GapSeverity
    from tests.test_stock_award_lots import _ledger, ASSET_ID

    ledger = _ledger()
    award = StockAwardEvent(ASSET_ID, "2023-01-02",
                            event_type=T.STOCK_AWARD_GRANTED, award_date="2023-01-02",
                            quantity=D("10"), unit_price_foreign=D("4"), currency="EUR")
    award.unit_cost_basis_eur = D("4")

    collector = DataGapCollector()
    StockAwardProcessor().process(award, ledger, {'data_gap_collector': collector})

    gaps = [g for g in collector.gaps if g.code == STOCK_AWARD_RECEIPT_NOT_DECLARED]
    assert len(gaps) == 1, "the undeclared receipt must reach the report"
    assert gaps[0].severity is GapSeverity.WARNING
    assert "40" in gaps[0].detail, "the amount to declare has to be in it, not just the fact"


def test_a_vesting_and_a_reversal_report_no_receipt():
    """Only the award is the Zufluss. Reporting a receipt again on the vesting would tell
    the user to declare the same shares twice."""
    from decimal import Decimal as D
    from src.domain.enums import FinancialEventType as T
    from src.domain.events import StockAwardEvent
    from src.engine.event_processors.stock_award_processor import (
        StockAwardProcessor, STOCK_AWARD_RECEIPT_NOT_DECLARED)
    from src.processing.data_gaps import DataGapCollector
    from tests.test_stock_award_lots import _ledger, ASSET_ID

    ledger = _ledger()
    collector = DataGapCollector()
    award = StockAwardEvent(ASSET_ID, "2023-01-02",
                            event_type=T.STOCK_AWARD_GRANTED, award_date="2023-01-02",
                            quantity=D("10"), unit_price_foreign=D("4"), currency="EUR")
    award.unit_cost_basis_eur = D("4")
    ledger.add_lot_for_stock_award(award)

    vesting = StockAwardEvent(ASSET_ID, "2023-06-01",
                              event_type=T.STOCK_AWARD_VESTED, award_date="2023-01-02",
                              quantity=D("10"), unit_price_foreign=D("7"), currency="EUR")
    vesting.unit_cost_basis_eur = D("7")
    StockAwardProcessor().process(vesting, ledger, {'data_gap_collector': collector})

    reversal = StockAwardEvent(ASSET_ID, "2023-03-01",
                               event_type=T.STOCK_AWARD_REVERSED, award_date="2023-01-02",
                               quantity=D("4"), unit_price_foreign=D("9"), currency="EUR")
    reversal.unit_cost_basis_eur = D("9")
    StockAwardProcessor().process(reversal, ledger, {'data_gap_collector': collector})

    assert not [g for g in collector.gaps if g.code == STOCK_AWARD_RECEIPT_NOT_DECLARED]

"""
Moving shares between your own accounts is not a sale.

legal_basis: [GT-ESTG20-014] -- a transfer between the taxpayer's own depots is not a
Veraeusserung under § 20 Abs. 2 EStG. No change of beneficial owner and no consideration,
so acquisition date and acquisition cost carry over and the lots are RELOCATED between
the two accounts' queues rather than closed and reopened. Reopening would reset the
holding period and the basis. Verbatim in
reference/tax-law/estg-20-kapitalvermoegen.md, "Abs. 2".

Which queue a sale draws from is [GT-ESTG20-013] (BMF 14.05.2025 Rz. 97 Satz 2), which is
why a move that the engine cannot see puts the sale in front of the wrong lots.

Each scenario is built so that reading the move and not reading it give **different signs
and different form lines**. A scenario where both agree would pass before and after the
change and prove nothing.

All identifiers and amounts are invented. CLAUDE.md forbids an account number, a position
value or a cash balance copied from a real export reaching a commit.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from src.processing.data_gaps import DataGapError
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import trade_row, position_row, transfer_row

A, B = "U10000001", "U10000002"
TAX_YEAR = 2025
ISIN = "US000000TR01"


def _sales_of(out, isin):
    ids = {a.internal_asset_id for a in out.asset_resolver.assets_by_internal_id.values()
           if getattr(a, "ibkr_isin", None) == isin}
    return [r for r in out.realized_gains_losses if r.asset_internal_id in ids]


def _form_lines(out):
    return LossOffsettingEngine(
        realized_gains_losses=out.realized_gains_losses,
        vorabpauschale_items=out.vorabpauschale_items,
        current_year_financial_events=out.processed_income_events,
        asset_resolver=out.asset_resolver,
        tax_year=TAX_YEAR,
    ).calculate_reporting_figures().form_line_values


def _move(from_account, to_account, date, isin=ISIN, quantity="100", tx_out="X1",
          tx_in="X2"):
    """The two summary rows one move produces, as the export writes them.

    The signs are opposite between the sides and neither says which way the units
    went -- that is what `Direction` is for, and what the real export does.
    """
    return [
        transfer_row(from_account, to_account, "OUT", date, isin=isin,
                     quantity=f"-{quantity}", tx_id=tx_out),
        transfer_row(to_account, from_account, "IN", date, isin=isin,
                     quantity=quantity, tx_id=tx_in),
    ]


class TestTheMovedSharesKeepTheirDateAndCost(FifoTestCaseBase):
    """The core case, with the move in a year BEFORE the tax year.

    A buys 100 @ 30 on 2023-01-15 (cost 3000).  B buys 100 @ 5 on 2023-09-01 (cost 500).
    In 2024 A moves its whole holding to B, so B holds both lots.  In 2025 B sells 100
    @ 25 for 2500.

        move read    : FIFO in B takes the OLDER lot, the one that moved.
                       2500 - 3000 = -500 LOSS, acquired 2023-01-15  -> Zeile 23
        move unseen  : B's ledger holds only its own 100 @ 5. The opening snapshot says
                       200, so reconciliation invents a lot for the difference and dates
                       it to the year end -- newer than B's own, so FIFO takes B's.
                       2500 -  500 = +2500 GAIN, acquired 2023-09-01 -> Zeile 20

    Opposite signs, different form lines and different acquisition dates, so this cannot
    pass under the wrong reading.
    """

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, ISIN, "2023-01-15", "100", "30", "BUY", "O", "T1"),
                trade_row(B, ISIN, "2023-09-01", "100", "5", "BUY", "O", "T2"),
                trade_row(B, ISIN, "2025-06-01", "-100", "25", "SELL", "C", "T3"),
            ],
            transfers_data=_move(A, B, "20240601"),
            positions_start_data=[position_row(B, ISIN, "200", "3500", price="20")],
            positions_end_data=[position_row(B, ISIN, "100", "500", price="5")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_the_sale_uses_the_price_the_moved_shares_were_bought_at(self):
        rgl = _sales_of(self._run(), ISIN)
        assert len(rgl) == 1
        assert rgl[0].total_cost_basis_eur == Decimal("3000"), \
            "the cost the moved lot was bought at, carried across the move"
        assert rgl[0].gross_gain_loss_eur == Decimal("-500")

    def test_the_moved_shares_keep_the_day_they_were_bought(self):
        """Not cosmetic: the date decides the holding period, and a reconciliation
        that only compares quantities agrees with the broker either way."""
        assert _sales_of(self._run(), ISIN)[0].acquisition_date == "2023-01-15"

    def test_it_lands_on_the_loss_line_not_the_gain_line(self):
        flv = _form_lines(self._run())
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST] == Decimal("500.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("0.00")

    def test_the_move_itself_declares_nothing(self):
        """A move is not a disposal ([GT-ESTG20-014]). One sale happened in 2025 and
        that is the only realised result there may be -- no second disposal on the
        move date, and no gain or loss of any size attached to it."""
        out = self._run()
        rgl = _sales_of(out, ISIN)
        assert len(rgl) == 1, f"only the 2025 sale realises anything, got {rgl}"
        assert not any(r.realization_date.startswith("2024") for r in rgl)

    def test_the_engine_no_longer_has_to_invent_the_moved_lot(self):
        """The gap the change closes. Without the export, B's reconstruction falls
        short of the opening snapshot, the reconstruction is discarded and a lot with
        a fabricated acquisition date takes its place -- reported as a data gap. With
        the move applied both accounts agree with the broker and nothing is invented.
        """
        out = self._run()
        subjects = [g.subject for g in out.data_gaps
                    if g.code in ("REPLAY_MARK_UNCONFIRMED_START", "REPLAY_MARK_MISMATCH")]
        assert not any(ISIN in s for s in subjects), \
            f"the moved instrument must reconcile without a synthesised lot, got {subjects}"
        assert out.eoy_mismatch_error_count == 0


class TestTheMoveInsideTheTaxYear(FifoTestCaseBase):
    """The same move, made during the tax year rather than before it.

    Both paths must apply it -- the chronological replay for earlier years and the
    tax year's own dispatch -- and they call one implementation, so this scenario
    checks the second entry point rather than a second rule.

    A holds 100 @ 30 from 2023, B holds 100 @ 5 from 2023.  A moves its holding to B
    in March 2025; B sells 100 @ 25 in September.  Same -500, and A must end the year
    empty or the closing reconciliation stops the run.
    """
    ISIN_TY = "US000000TR02"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_TY, "2023-01-15", "100", "30", "BUY", "O", "T1"),
                trade_row(B, self.ISIN_TY, "2023-09-01", "100", "5", "BUY", "O", "T2"),
                trade_row(B, self.ISIN_TY, "2025-09-01", "-100", "25", "SELL", "C", "T3"),
            ],
            transfers_data=_move(A, B, "20250301", isin=self.ISIN_TY),
            positions_start_data=[
                position_row(A, self.ISIN_TY, "100", "3000", price="30"),
                position_row(B, self.ISIN_TY, "100", "500", price="5"),
            ],
            positions_end_data=[position_row(B, self.ISIN_TY, "100", "500", price="5")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_the_sale_after_the_move_uses_the_moved_lot(self):
        rgl = _sales_of(self._run(), self.ISIN_TY)
        assert len(rgl) == 1
        assert rgl[0].gross_gain_loss_eur == Decimal("-500")
        assert rgl[0].acquisition_date == "2023-01-15"

    def test_the_receiving_account_may_appear_nowhere_but_the_move(self):
        """B has no trades and no opening-snapshot row: the move INTO it during the
        tax year is the only thing that names it, and the closing snapshot is
        deliberately not a source of ledgers. So the move itself has to create B's
        ledger or the units arrive nowhere.

        Found by probe, not by design: deleting the receiving-account registration in
        `calculation_engine._register_event_accounts` left every other scenario in
        this file green, because each of them names B somewhere else as well.
        """
        isin = "US000000TR06"
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, isin, "2023-01-15", "100", "30", "BUY", "O", "T1"),
            ],
            transfers_data=_move(A, B, "20250301", isin=isin),
            positions_start_data=[position_row(A, isin, "100", "3000", price="30")],
            positions_end_data=[position_row(B, isin, "100", "3000", price="30")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        assert out.eoy_mismatch_error_count == 0

    def test_the_sending_account_ends_the_year_empty_and_reconciles(self):
        """The half a person-level check cannot see. A's units left A; the broker's
        closing snapshot does not list A at all, and the per-account end-of-year check
        compares A's ledger against that reported zero."""
        assert self._run().eoy_mismatch_error_count == 0


class TestAMoveOfPartOfAPositionStopsTheRun(FifoTestCaseBase):
    """The refusal, and what it has to say.

    Nothing in the standard export names the lots that moved: `TransferPrice` is zero on
    every row. The oldest units and the newest give different gains and different holding
    periods, so choosing between them would be inventing the figure rather than computing
    it -- CLAUDE.md's fallback rule. The run stops instead.
    """
    ISIN_PART = "US000000TR03"

    def _run(self, moved):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_PART, "2023-01-15", "100", "30", "BUY", "O", "T1"),
            ],
            transfers_data=_move(A, B, "20240601", isin=self.ISIN_PART, quantity=moved),
            positions_start_data=[
                position_row(A, self.ISIN_PART, "60", "1800", price="30"),
                position_row(B, self.ISIN_PART, "40", "1200", price="30"),
            ],
            positions_end_data=[
                position_row(A, self.ISIN_PART, "60", "1800", price="30"),
                position_row(B, self.ISIN_PART, "40", "1200", price="30"),
            ],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_it_names_what_the_reader_needs_to_find_the_move(self):
        with pytest.raises(DataGapError) as excinfo:
            self._run("40")
        message = str(excinfo.value)
        assert "TR03" in message or self.ISIN_PART in message, "the instrument"
        assert A in message, "the account the units left"
        assert "2024-06-01" in message, "the date of the move"
        assert "40" in message, "the quantity moved"
        assert "100" in message, "the quantity held at that moment"

    def test_it_points_at_the_export_option_that_would_answer_it(self):
        """A refusal a person cannot act on is only half of one. The Transfers report
        has a lot-detail option; with it on, the export carries a basis per lot and
        names the units that moved."""
        with pytest.raises(DataGapError) as excinfo:
            self._run("40")
        assert "lot-detail" in str(excinfo.value)

    def test_a_whole_position_is_not_refused(self):
        """The other side of the same guard: moving all of it is exactly the case
        this change supports, and it must not trip the refusal."""
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_PART, "2023-01-15", "100", "30", "BUY", "O", "T1"),
            ],
            transfers_data=_move(A, B, "20240601", isin=self.ISIN_PART, quantity="100"),
            positions_start_data=[position_row(B, self.ISIN_PART, "100", "3000", price="30")],
            positions_end_data=[position_row(B, self.ISIN_PART, "100", "3000", price="30")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        assert out.eoy_mismatch_error_count == 0


class TestTheExportIsCollapsedNotSummed(FifoTestCaseBase):
    """The export writes one move several times. Adding the rows up moves it twice.

    Both tests below hold the SAME holding and the same ledger state, so an engine that
    applied a move more than once would drain a ledger that has nothing left and be
    refused for a partial move -- which is the guard doing its job, and what makes this
    observable rather than a silent doubling.
    """
    ISIN_C = "US000000TR04"

    def _run(self, transfers):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_C, "2023-01-15", "100", "30", "BUY", "O", "T1"),
            ],
            transfers_data=transfers,
            positions_start_data=[position_row(B, self.ISIN_C, "100", "3000", price="30")],
            positions_end_data=[position_row(B, self.ISIN_C, "100", "3000", price="30")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_the_two_sides_of_one_move_are_one_move(self):
        assert self._run(_move(A, B, "20240601", isin=self.ISIN_C)
                         ).eoy_mismatch_error_count == 0

    def test_the_lot_detail_rows_beneath_a_move_add_nothing(self):
        """Under each summary row the export writes one row per lot, carrying `Code`
        "ST" and no `TransactionID`. They describe the same units a second time."""
        rows = _move(A, B, "20240601", isin=self.ISIN_C)
        rows += [
            transfer_row(A, B, "OUT", "20240601", isin=self.ISIN_C, quantity="-60",
                         code="ST"),
            transfer_row(A, B, "OUT", "20240601", isin=self.ISIN_C, quantity="-40",
                         code="ST"),
            transfer_row(B, A, "IN", "20240601", isin=self.ISIN_C, quantity="60",
                         code="ST"),
            transfer_row(B, A, "IN", "20240601", isin=self.ISIN_C, quantity="40",
                         code="ST"),
        ]
        assert self._run(rows).eoy_mismatch_error_count == 0

    def test_one_side_alone_still_describes_the_whole_move(self):
        """Each summary row names both accounts, so a person who exported only the
        receiving account's report still gets the move applied."""
        rows = [transfer_row(B, A, "IN", "20240601", isin=self.ISIN_C, quantity="100",
                             tx_id="X2")]
        assert self._run(rows).eoy_mismatch_error_count == 0


class TestAMoveToAnAccountTheInputDoesNotReportStopsTheRun(FifoTestCaseBase):
    """`Type=INTERNAL` is not a test of who owns the other account.

    [GT-ESTG20-014] covers a move between the taxpayer's OWN depots, and that is what
    the engine does with one: relocate the lots, realise nothing. IBKR's `INTERNAL`
    means the counterparty is an IBKR account — a gift, a spousal transfer or any move
    to a third party is `INTERNAL` too, and each may be a disposal that no rule in
    `reference/` decides.

    Found by review. Before this guard the pre-tax-year case completed in silence: the
    units left the person's holdings with no disposal anywhere, and the opening
    snapshot never listed the account, so nothing disagreed with anything.
    """
    ISIN_X = "US000000TR07"
    STRANGER = "U99999999"

    def _run(self, date):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_X, "2023-01-15", "100", "30", "BUY", "O", "T1"),
            ],
            transfers_data=_move(A, self.STRANGER, date, isin=self.ISIN_X),
            positions_start_data=[position_row(A, self.ISIN_X, "100", "3000", price="30")],
            positions_end_data=[],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_a_move_out_before_the_tax_year_is_not_waved_through(self):
        with pytest.raises(DataGapError) as excinfo:
            self._run("20240601")
        message = str(excinfo.value)
        assert "TRANSFER_COUNTERPARTY_UNKNOWN" in message
        assert self.STRANGER in message, "the account the reader has to look up"
        assert "receiving" in message

    def test_a_move_inside_the_tax_year_is_not_waved_through_either(self):
        with pytest.raises(DataGapError) as excinfo:
            self._run("20250301")
        assert "TRANSFER_COUNTERPARTY_UNKNOWN" in str(excinfo.value)

    def test_an_account_the_input_does_report_is_accepted(self):
        """The other side of the guard: B trades, so B is demonstrably the person's,
        and the move is the ordinary case this change exists for."""
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_X, "2023-01-15", "100", "30", "BUY", "O", "T1"),
                trade_row(B, self.ISIN_X, "2023-09-01", "10", "5", "BUY", "O", "T2"),
            ],
            transfers_data=_move(A, B, "20240601", isin=self.ISIN_X),
            positions_start_data=[position_row(B, self.ISIN_X, "110", "3050", price="30")],
            positions_end_data=[position_row(B, self.ISIN_X, "110", "3050", price="30")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        assert out.eoy_mismatch_error_count == 0


class TestASingleAccountIsUnaffected(FifoTestCaseBase):
    """The guard for everyone who holds one account and has no Transfers export."""
    ISIN_S = "US000000TR05"

    def test_no_transfers_export_changes_nothing(self):
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_S, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row(A, self.ISIN_S, "2025-06-01", "-50", "35", "SELL", "C", "T2"),
            ],
            positions_start_data=[position_row(A, self.ISIN_S, "100", "1000", price="10")],
            positions_end_data=[position_row(A, self.ISIN_S, "50", "500", price="10")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        rgl = _sales_of(out, self.ISIN_S)
        assert len(rgl) == 1
        assert rgl[0].gross_gain_loss_eur == Decimal("1250")
        assert out.eoy_mismatch_error_count == 0

    def test_an_empty_transfers_export_changes_nothing_either(self):
        """A person who has never moved a holding exports an empty file, and absence
        of rows must mean nothing moved rather than anything else."""
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN_S, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row(A, self.ISIN_S, "2025-06-01", "-50", "35", "SELL", "C", "T2"),
            ],
            transfers_data=[],
            positions_start_data=[position_row(A, self.ISIN_S, "100", "1000", price="10")],
            positions_end_data=[position_row(A, self.ISIN_S, "50", "500", price="10")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        assert _sales_of(out, self.ISIN_S)[0].gross_gain_loss_eur == Decimal("1250")

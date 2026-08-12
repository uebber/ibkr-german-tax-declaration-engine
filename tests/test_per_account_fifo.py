"""
Selling from one account consumes THAT account's shares.

legal_basis: BMF-Schreiben vom 14.05.2025 Rz. 97 Satz 2 — *"Die Anwendung der
Fifo-Methode im Sinne des § 20 Absatz 4 Satz 7 EStG ist auf das einzelne Depot
bezogen anzuwenden."* [GT-ESTG20-013]. Whether that boundary reaches a foreign
broker's sub-accounts is open question Q2; Reading A (each sub-account is its own
Depot) was chosen by the taxpayer on 2026-08-11 and is recorded in
docs/legal-implementation-map.md, not here.

What is declared remains the person's total across their accounts —
[GT-ESTG20-061] — so every scenario below also checks that the per-account
records still add up to the figure the return carries.

Each scenario is built so the two readings give **different signs or different
form lines**. A scenario where pooled and per-account agree proves nothing: it
would pass before and after the change.

All identifiers and amounts are invented. CLAUDE.md forbids an account number, a
position value or a cash balance copied from a real export reaching a commit.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.processing.data_gaps import DataGapError
from src.engine.loss_offsetting import LossOffsettingEngine
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import trade_row, position_row

A, B = "U10000001", "U10000002"
TAX_YEAR = 2025


def _sales_of(out, isin):
    """RealizedGainLoss carries only the asset's internal id."""
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


class TestTheSaleConsumesItsOwnAccount(FifoTestCaseBase):
    """The core case: one instrument, both accounts, sold from the newer one.

    A buys 100 @ 10 in 2023.  B buys 50 @ 40 in 2024.  B sells 50 @ 35 in 2025.

        per Depot : 1750 - 2000 = -250  LOSS   -> Zeile 23
        pooled    : 1750 -  500 = +1250 GAIN   -> Zeile 20

    Opposite signs and different form lines, so this cannot pass under the wrong
    reading.
    """
    ISIN = "US000000CH01"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row(B, self.ISIN, "2024-05-01", "50", "40", "BUY", "O", "T2"),
                trade_row(B, self.ISIN, "2025-06-01", "-50", "35", "SELL", "C", "T3"),
            ],
            positions_start_data=[
                position_row(A, self.ISIN, "100", "1000", price="10"),
                position_row(B, self.ISIN, "50", "2000", price="40"),
            ],
            positions_end_data=[position_row(A, self.ISIN, "100", "1000", price="10")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_the_cost_basis_is_the_selling_accounts_own_lot(self):
        rgl = _sales_of(self._run(), self.ISIN)
        assert len(rgl) == 1
        assert rgl[0].total_cost_basis_eur == Decimal("2000"), \
            "B's own 40-cost lot, not A's older 10-cost lot"
        assert rgl[0].gross_gain_loss_eur == Decimal("-250")

    def test_the_acquisition_date_follows_the_lot_consumed(self):
        """Not cosmetic: the date decides the holding period, and a wrong one is
        invisible to a reconciliation that only checks quantity."""
        assert _sales_of(self._run(), self.ISIN)[0].acquisition_date == "2024-05-01"

    def test_it_lands_on_the_loss_line_not_the_gain_line(self):
        flv = _form_lines(self._run())
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST] == Decimal("250.00")
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("0.00")

    def test_the_person_still_declares_the_total_of_both_accounts(self):
        """[GT-ESTG20-061]. Splitting the ledgers must not lose the aggregate the
        return actually carries."""
        out = self._run()
        assert out.eoy_mismatch_error_count == 0


class TestAdversarial(FifoTestCaseBase):
    """Cases chosen to break a naive per-account implementation.

    Each is something a real IBKR account produces, and each has an answer the
    law fixes — none of them asks the engine to guess.
    """

    def test_an_account_that_only_appears_in_the_snapshot_still_gets_a_ledger(self):
        """A holds shares bought before the import window: no trade rows at all,
        only a snapshot line. A naive implementation builds ledgers from events
        and never creates one for A, so A's holding silently vanishes and the
        person's total is understated.

        B's sale is unaffected and must still consume B's own lot.
        """
        isin = "US000000SN01"
        out = self._run_pipeline(
            trades_data=[
                trade_row(B, isin, "2024-05-01", "50", "40", "BUY", "O", "T1"),
                trade_row(B, isin, "2025-06-01", "-50", "35", "SELL", "C", "T2"),
            ],
            positions_start_data=[
                position_row(A, isin, "100", "1000", price="10"),   # no trades, ever
                position_row(B, isin, "50", "2000", price="40"),
            ],
            positions_end_data=[position_row(A, isin, "100", "1000", price="10")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        assert out.eoy_mismatch_error_count == 0, \
            "A's snapshot-only holding must survive; the person still holds 100 units"
        rgl = _sales_of(out, isin)
        assert rgl[0].total_cost_basis_eur == Decimal("2000")

    def test_the_historical_replay_gives_each_account_only_its_own_past(self):
        """The lots are built by the pre-tax-year replay, and it has to be split
        by account too. Both accounts hold the SAME quantity, which is the point:
        with unequal quantities the opening reconciliation trims each ledger back
        to its reported figure and — taking the newest lots — repairs the wrong
        ones by accident, so the defect hides.

        A: 100 @ 10 in 2023.  B: 100 @ 40 in 2024.  A sells 50 @ 35 in 2025.

            per Depot : 1750 -  500 = +1250 GAIN, acquired 2023-05-01
            pooled    : 1750 - 2000 =  -250 LOSS, acquired 2024-05-01

        The pooled figure comes from B's lot, which A never held. Sign, form line
        and acquisition date all differ, and the holding period with them.
        """
        isin = "US000000HR01"
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, isin, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row(B, isin, "2024-05-01", "100", "40", "BUY", "O", "T2"),
                trade_row(A, isin, "2025-06-01", "-50", "35", "SELL", "C", "T3"),
            ],
            positions_start_data=[
                position_row(A, isin, "100", "1000", price="10"),
                position_row(B, isin, "100", "4000", price="40"),
            ],
            positions_end_data=[
                position_row(A, isin, "50", "500", price="10"),
                position_row(B, isin, "100", "4000", price="40"),
            ],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        rgl = _sales_of(out, isin)
        assert len(rgl) == 1
        assert rgl[0].total_cost_basis_eur == Decimal("500"), \
            "A's own 2023 lot, not the 2024 lot the replay would have handed it"
        assert rgl[0].gross_gain_loss_eur == Decimal("1250")
        assert rgl[0].acquisition_date == "2023-05-01"

    def test_an_accounts_unconfirmed_history_is_reported_and_not_dropped_in_silence(self):
        """The historical events are a source of ledgers in their own right.

        A bought 100 in 2023 and the opening snapshot does not list A at all, so
        the input is missing whatever disposed of them. Building A's ledger is
        what makes that disagreement visible: the reconstruction meets a reported
        zero, is discarded, and the run says so.

        Drop the historical events as a source of accounts and A has no ledger,
        so there is nothing to disagree with anything — the reconstruction is
        never built and the gap is never recorded. No figure moves either way,
        which is exactly why this needs its own test: the one thing lost is the
        report that the input was incomplete.
        """
        isin = "US000000UH01"
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, isin, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row(B, isin, "2024-05-01", "50", "40", "BUY", "O", "T2"),
            ],
            positions_start_data=[position_row(B, isin, "50", "2000", price="40")],
            positions_end_data=[position_row(B, isin, "50", "2000", price="40")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        subjects = [g.subject for g in out.data_gaps
                    if g.code == "REPLAY_MARK_UNCONFIRMED_START"]
        assert any(isin in s for s in subjects), \
            f"A's unconfirmed 100 units must be reported, got {subjects}"

    def test_a_position_opened_and_closed_inside_the_year_needs_no_snapshot_row(self):
        """B buys and sells within the tax year, so B has no opening snapshot line
        for it. An implementation that seeds ledgers only from snapshots has no
        ledger to sell from and either crashes or reports nothing.

        Bought 100 @ 20, sold 100 @ 26 -> +600 gain, all in B.
        """
        isin = "US000000IY01"
        out = self._run_pipeline(
            trades_data=[
                trade_row(B, isin, "2025-03-01", "100", "20", "BUY", "O", "T1"),
                trade_row(B, isin, "2025-09-01", "-100", "26", "SELL", "C", "T2"),
            ],
            positions_start_data=[],
            positions_end_data=[],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        rgl = _sales_of(out, isin)
        assert len(rgl) == 1
        assert rgl[0].gross_gain_loss_eur == Decimal("600")

    def test_both_accounts_sell_the_same_instrument_on_the_same_day(self):
        """Same instrument, same date, one sale from each account. Each must take
        its own lot. Pooled FIFO would serve both sales from A's cheaper lot and
        report two gains instead of a gain and a loss.

        A: 100 @ 10 (2023), sells 50 @ 35 -> +1250 gain
        B:  50 @ 40 (2024), sells 50 @ 35 ->  -250 loss
        """
        isin = "US000000SD01"
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, isin, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row(B, isin, "2024-05-01", "50", "40", "BUY", "O", "T2"),
                trade_row(A, isin, "2025-06-01", "-50", "35", "SELL", "C", "T3"),
                trade_row(B, isin, "2025-06-01", "-50", "35", "SELL", "C", "T4"),
            ],
            positions_start_data=[
                position_row(A, isin, "100", "1000", price="10"),
                position_row(B, isin, "50", "2000", price="40"),
            ],
            positions_end_data=[position_row(A, isin, "50", "500", price="10")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        results = sorted(r.gross_gain_loss_eur for r in _sales_of(out, isin))
        assert results == [Decimal("-250"), Decimal("1250")], \
            "one gain and one loss, not two gains from the same cheap lot"

    def test_the_year_end_check_catches_errors_that_cancel_across_accounts(self):
        """The reason the check runs per account.

        The snapshot says A holds 90 and B holds 110; the trades say 100 each.
        The person's total matches at 200, so a person-level check passes and the
        misplacement is invisible. Per account, both fail.

        This is the blind spot CLAUDE.md names: a start-of-year snapshot both
        seeds the ledger and is the baseline it is checked against.
        """
        isin = "US000000CX01"
        with pytest.raises(DataGapError, match="EOY_RECONCILIATION_FAILED"):
            self._run_pipeline(
                trades_data=[
                    trade_row(A, isin, "2025-03-01", "100", "10", "BUY", "O", "T1"),
                    trade_row(B, isin, "2025-03-01", "100", "10", "BUY", "O", "T2"),
                ],
                positions_start_data=[],
                positions_end_data=[
                    position_row(A, isin, "90", "900", price="10"),
                    position_row(B, isin, "110", "1100", price="10"),
                ],
                custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
                tax_year=TAX_YEAR,
            )

    def test_a_move_the_input_does_not_record_still_stops_the_run(self):
        """A holds 100 units at the start of the year and B holds none. At the end
        of the year the broker reports the position in B. Nothing was bought or
        sold: it was moved between the person's own accounts, which is not a
        disposal ([GT-ESTG20-014]) -- and here the Transfers export is not supplied,
        so nothing tells the engine that it happened.

        Pooled, this was invisible AND harmless: the lots never left the pool. Per
        Depot it is invisible and not harmless, so the run must stop. The person's
        total is unchanged at 100, which is exactly why a person-level check would
        let it through.

        **What changed when the export became readable.** Supply the rows and this
        same scenario completes, with the lots relocated carrying their date and
        cost -- `test_internal_transfers.py` is where that is asserted. This one
        keeps the other half: a move the input does not record must not be guessed
        at from the snapshots, whatever the reason it is missing.
        """
        isin = "US000000TR01"
        with pytest.raises(DataGapError, match="EOY_RECONCILIATION_FAILED"):
            self._run_pipeline(
                trades_data=[
                    trade_row(A, isin, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                ],
                positions_start_data=[position_row(A, isin, "100", "1000", price="10")],
                positions_end_data=[position_row(B, isin, "100", "1000", price="10")],
                custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
                tax_year=TAX_YEAR,
            )

    def test_a_single_account_is_unchanged(self):
        """The guard that protects everyone who holds one account: one account
        named on every row means one ledger, and the figures are what they were.

        It does NOT exercise the absent-`ClientAccountID` path — every row here
        names an account. The scenario below does that one.

        100 @ 10 bought 2023, 50 sold @ 35 in 2025 -> +1250 gain.
        """
        isin = "US000000SA01"
        out = self._run_pipeline(
            trades_data=[
                trade_row(A, isin, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row(A, isin, "2025-06-01", "-50", "35", "SELL", "C", "T2"),
            ],
            positions_start_data=[position_row(A, isin, "100", "1000", price="10")],
            positions_end_data=[position_row(A, isin, "50", "500", price="10")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        rgl = _sales_of(out, isin)
        assert len(rgl) == 1
        assert rgl[0].gross_gain_loss_eur == Decimal("1250")
        assert out.eoy_mismatch_error_count == 0

    def test_an_export_carrying_no_account_at_all_behaves_as_it_always_did(self):
        """Older exports, and any row where the column is blank.

        `account_key()` collapses an absent account to one DEFAULT ledger, which
        is what makes this change invisible to everyone whose input predates the
        column. Nothing else in the suite exercises that path, so a conversion
        that started keying on a raw `account_id` — `None` and `""` landing in
        different ledgers — would go unnoticed here.

        Same scenario as the one above, with the account column empty: the same
        +1250 gain, and a ledger that reconciles.
        """
        isin = "US000000NA01"
        out = self._run_pipeline(
            trades_data=[
                trade_row("", isin, "2023-05-01", "100", "10", "BUY", "O", "T1"),
                trade_row("", isin, "2025-06-01", "-50", "35", "SELL", "C", "T2"),
            ],
            positions_start_data=[position_row("", isin, "100", "1000", price="10")],
            positions_end_data=[position_row("", isin, "50", "500", price="10")],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        rgl = _sales_of(out, isin)
        assert len(rgl) == 1
        assert rgl[0].gross_gain_loss_eur == Decimal("1250")
        assert rgl[0].acquisition_date == "2023-05-01"
        assert out.eoy_mismatch_error_count == 0


class TestTheLimitationsAreStated(FifoTestCaseBase):
    """Multi-account support is incomplete, and a run that uses it says so.

    The warning is raised on the presence of a second account, not on the
    presence of a defect: a transfer in an earlier year re-dates lots this year
    still holds, and nothing in the input marks that it happened. A person who
    has moved nothing between accounts is told so in the text.

    The securities clause went with the change that reads the Transfers export and
    relocates lots between accounts ([GT-ESTG20-014]). The currency clause is what
    is left, and it takes this class with it when it goes.
    """
    ISIN = "US000000LM01"

    def _run(self, accounts, transfers_data=None, transfers_missing_years=""):
        return self._run_pipeline(
            trades_data=[trade_row(a, self.ISIN, "2025-03-01", "10", "20", "BUY", "O", f"T{i}")
                         for i, a in enumerate(accounts)],
            transfers_data=transfers_data,
            transfers_missing_years=transfers_missing_years,
            positions_start_data=[],
            positions_end_data=[position_row(a, self.ISIN, "10", "200", price="20")
                                for a in accounts],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def _gap(self, out):
        return next((g for g in out.data_gaps
                     if g.code == "MULTI_ACCOUNT_LIMITATIONS"), None)

    def test_two_accounts_are_told_what_is_not_covered(self):
        gap = self._gap(self._run([A, B], transfers_data=[]))
        assert gap is not None, "a multi-account run must state its limitations"
        assert "Fremdwährungsbestände werden je Person geführt" in gap.detail

    def test_the_closed_limitation_is_not_still_warned_about(self):
        """A warning left standing after its limitation is closed is the same defect
        as a comment asserting something false: the reader trusts it and works around
        a problem that is gone. With the export supplied, the moves ARE read."""
        gap = self._gap(self._run([A, B], transfers_data=[]))
        assert "KEIN TRANSFERS-BERICHT" not in gap.detail
        assert "NICHT BELASTBAR" not in gap.detail, \
            "the securities figures no longer rest on what this warning covered"

    def test_a_run_with_no_transfers_export_is_told_the_moves_are_invisible(self):
        """The other half, and the one that matters more. Supplying no Transfers
        export does not mean nothing moved — it means the engine cannot know. The
        text must not tell that reader the moves were read and their figures are
        unaffected, because that is the run where a move would be invisible and the
        acquisition dates behind it invented.

        Found by review: the wording was unconditional, so the reader who most
        needed the caveat was told the opposite of the truth.
        """
        gap = self._gap(self._run([A, B]))
        assert "KEIN TRANSFERS-BERICHT" in gap.detail
        assert "NICHT BELASTBAR" in gap.detail, \
            "the severity is only WARNING, so the text has to carry the weight"
        assert "eingelesen; die Bestände" not in gap.detail, \
            "it must not claim the moves were applied"

    def test_a_transfers_export_with_a_year_missing_stops_the_run(self):
        """A hole is not an absence. An export covering some years and not others means
        the query exists and a year of it is simply missing — and a move in that year is
        invisible, silently, in that year and every year after it. Exporting the year is
        cheap; the acquisition date it protects is not recoverable afterwards.

        Found by review as a wording defect, then decided by the taxpayer on 2026-08-12
        to be a refusal rather than a caveat.
        """
        with pytest.raises(DataGapError) as excinfo:
            self._run([A, B], transfers_data=[], transfers_missing_years="2025")
        message = str(excinfo.value)
        assert "TRANSFERS_WINDOW_INCOMPLETE" in message
        assert "2025" in message, "the year to export is the reader's next action"

    def test_no_transfers_export_at_all_is_a_warning_and_not_a_refusal(self):
        """The other side of that decision, and the reason it is not simply "refuse".
        Everyone who holds one account, and everyone who has never moved anything, has
        no Transfers export — stopping them would be stopping them for nothing."""
        gap = self._gap(self._run([A, B]))
        assert gap is not None and "KEIN TRANSFERS-BERICHT" in gap.detail

    def test_an_absent_export_stays_a_warning_even_if_years_are_reported_missing(self):
        """The scoping condition, pinned rather than left to another module's
        behaviour. `data_preparation` reports no missing years when there is no export
        at all, so in production the two never arrive together — but the refusal is
        scoped on "the export exists AND a year of it is missing", and a change over
        there must not silently turn an absence into a refusal.

        Found by probe: dropping the `transfers_file_supplied` condition left the
        suite green.
        """
        gap = self._gap(self._run([A, B], transfers_missing_years="2025"))
        assert gap is not None, "an absent export is a warning, not a refusal"
        assert "KEIN TRANSFERS-BERICHT" in gap.detail

    def test_a_single_account_is_never_refused_over_a_missing_year(self):
        """A move between the taxpayer's own accounts needs two of them, so with one
        account there is no per-Depot placement a missing year could get wrong.
        Refusing there would stop a run for nothing.

        Found by probe: dropping the two-account condition left the suite green.
        """
        out = self._run([A], transfers_data=[], transfers_missing_years="2025")
        assert self._gap(out) is None, "one account gets no multi-account warning either"

    def test_one_account_is_told_nothing(self):
        """The warning must not reach the people it does not apply to — a report
        that cries wolf on every run is a report nobody reads."""
        assert self._gap(self._run([A])) is None


class TestTheWarningReachesTheReader:
    """The report end of the channel, probed separately from the engine end.

    Deleting the banner leaves every other test in this file green: the engine
    records the gap either way. `CLAUDE.md` names this shape — "the ends of a new
    channel … probe the ends, not the middle" — so both ends have a test.
    """

    def _lines(self, gaps):
        import contextlib, io
        from src.domain.results import LossOffsettingResult
        from src.reporting.console_reporter import generate_console_tax_report

        class _Resolver:
            assets_by_internal_id: dict = {}
            def get_asset_by_id(self, internal_id): return None

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            generate_console_tax_report([], [], [], _Resolver(), TAX_YEAR, 0,
                                        LossOffsettingResult(), data_gaps=gaps)
        return buffer.getvalue().splitlines()

    def _gap(self, detail="…"):
        from src.processing.data_gaps import DataGap, GapSeverity
        return DataGap(code="MULTI_ACCOUNT_LIMITATIONS", subject="2 Konten im Export",
                       detail=detail, severity=GapSeverity.WARNING)

    def test_it_is_printed_before_the_figures(self):
        """A reader who stops at the number they came for must have passed it."""
        lines = self._lines([self._gap()])
        banner = next(i for i, l in enumerate(lines) if "Mehrkonten-Unterstützung" in l)
        first_figure = next(i for i, l in enumerate(lines) if "Zeile 20" in l)
        assert banner < first_figure

    def test_the_banner_does_not_contradict_the_gap_it_points_at(self):
        """The banner is a pointer to the full wording, so the two must agree about
        the one thing that decides how bad the run is. It reads the answer off the
        gap's own detail rather than making its own claim.

        It keys on "NICHT BELASTBAR", which the engine writes in the cautious variant
        and only there. Keying on one variant's own wording was a defect while there
        were two cautious variants: the second printed the reassuring banner over a
        full wording that said the opposite. There is one cautious variant again now —
        a partly exported window stops the run instead — and the marker is what keeps
        the banner right if a third is ever added.
        """
        lines = "\n".join(self._lines([
            self._gap("… ES WURDE KEIN TRANSFERS-BERICHT … NICHT BELASTBAR …")]))
        assert "NICHT BELASTBAR" in lines
        assert "nicht betroffen" not in lines
        read = "\n".join(self._lines([self._gap("… Überträge werden eingelesen …")]))
        assert "NICHT BELASTBAR" not in read
        assert "nicht betroffen" in read

    def test_a_clean_run_prints_no_banner(self):
        assert not any("Mehrkonten-Unterstützung" in l for l in self._lines([]))

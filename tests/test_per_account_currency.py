"""
Your foreign currency sits in an account, not in a pot.

legal_basis: BMF-Schreiben vom 14.05.2025 Rz. 131 second paragraph — an Umbuchung
of a Fremdwaehrungskapitalforderung *"auf ein anderes verzinsliches Konto bei
demselben oder einem anderen Kreditinstitut"* is *"eine Veraeusserung der
urspruenglichen Kapitalforderung und zugleich eine Anschaffung einer neuen"*
([GT-FX-009]). A balance cannot be sold to itself, so two accounts holding one
currency hold two Kapitalforderungen and a disposal from one consumes what was
paid into that one. What the Umbuchung is worth is [GT-FX-010], and the reading
applied is recorded in docs/legal-implementation-map.md, not here.

Cite Rz. 131 for currency and never Rz. 97: Rz. 97 draws the Depot boundary for
§ 20 Abs. 4 Satz 7, which by its own wording reaches only Wertpapiere in
Sammelverwahrung ([GT-FX-008]).

Each scenario is built so that the pooled reading and the per-account reading give
**different signs or different totals**. A scenario where the two agree proves
nothing: it would pass before and after the change.

All identifiers and amounts are invented. CLAUDE.md forbids an account number or a
cash balance copied from a real export reaching a commit.
"""
from decimal import Decimal

import pytest

from src.domain.enums import RealizationType, TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from src.processing.data_gaps import DataGapError
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import (
    cash_balance_row, fx_trade_row, position_row, trade_row, transfer_row)

A, B = "U10000001", "U10000002"
TAX_YEAR = 2025


class _Rates(MockECBExchangeRateProvider):
    """A rate per date, so a gain can be built from the currency alone.

    `MockECBExchangeRateProvider` answers one rate for every day, which cannot
    express a currency movement — and a currency movement is the whole subject here.

    Scenarios are written in **EUR per unit of foreign currency**, because that is
    how a cost basis reads. ECB quotes the reciprocal (foreign per EUR), so the
    inversion happens here rather than in every scenario.
    """

    def __init__(self, eur_per_unit_by_date, default=Decimal("1.00")):
        super().__init__(default)
        self._by_date = {d: Decimal("1") / Decimal(str(r))
                         for d, r in eur_per_unit_by_date.items()}

    def get_rate(self, rate_date, currency):
        if currency and currency.upper() == "EUR":
            return Decimal("1")
        return self._by_date.get(rate_date.isoformat(), super().get_rate(rate_date, currency))


def _fx_rgls(out):
    """Realisations on a cash balance, whichever path produced them."""
    cash_ids = {a.internal_asset_id
                for a in out.asset_resolver.assets_by_internal_id.values()
                if getattr(a, "currency", None) and getattr(a, "ibkr_isin", None) is None
                and a.__class__.__name__ == "CashBalance"}
    return [r for r in out.realized_gains_losses if r.asset_internal_id in cash_ids]


def _fx_total(out):
    return sum((r.gross_gain_loss_eur for r in _fx_rgls(out)), Decimal(0))


def _gaps(out, code):
    return [g for g in out.data_gaps if g.code == code]


class TestTheDisposalConsumesItsOwnAccountsBalance(FifoTestCaseBase):
    """The core case: one currency, both accounts, spent from the newer one.

    A opens the year holding 1000 USD acquired long ago at 0.50 EUR/USD.
    B opens the year holding 1000 USD acquired at 1.20 EUR/USD.
    B then buys a EUR-priced share... no: B spends 1000 USD buying a USD share on
    2025-06-01, when the rate is 1.00.

        per account : 1000 x 1.00 - 1000 x 1.20 = -200  LOSS  -> Zeile 22
        pooled      : 1000 x 1.00 - 1000 x 0.50 = +500  GAIN  -> Zeile 19

    Opposite signs and different form lines, so this cannot pass under the pooled
    reading. The cost bases are supplied through the opening Positions snapshot,
    which is the only place an export states a cost basis for a balance.
    """
    ISIN = "US000000FX01"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(B, self.ISIN, "2025-06-01", "10", "100", "BUY", "O", "T1",
                          currency="USD"),
            ],
            positions_start_data=[
                _usd_position(A, "1000", "500"),
                _usd_position(B, "1000", "1200"),
            ],
            positions_end_data=[
                position_row(B, self.ISIN, "10", "1000", currency="USD", price="100"),
                _usd_position(A, "1000", "500"),
            ],
            cash_balance_data=[
                cash_balance_row(A, "USD", "1000", "1000", year=TAX_YEAR),
                cash_balance_row(B, "USD", "1000", "0", year=TAX_YEAR),
            ],
            custom_rate_provider=_Rates({"2025-06-01": "1.00"}),
            tax_year=TAX_YEAR,
        )

    def test_the_cost_basis_is_the_spending_accounts_own_balance(self):
        out = self._run()
        spends = [r for r in _fx_rgls(out)
                  if r.realization_type == RealizationType.FX_IMPLICIT_SECURITY_PURCHASE]
        assert len(spends) == 1, _fx_rgls(out)
        assert spends[0].total_cost_basis_eur == Decimal("1200"), \
            "B's own 1.20 balance, not A's older 0.50 one"
        assert spends[0].gross_gain_loss_eur == Decimal("-200")

    def test_it_lands_on_the_loss_line_and_not_the_income_line(self):
        figures = LossOffsettingEngine(
            realized_gains_losses=self._run().realized_gains_losses,
            vorabpauschale_items=[], current_year_financial_events=[],
            asset_resolver=self._run().asset_resolver, tax_year=TAX_YEAR,
        ).calculate_reporting_figures().form_line_values
        assert figures.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE,
                           Decimal(0)) >= Decimal("200")


class TestTheHistoricalReplayGivesEachAccountOnlyItsOwnPast(FifoTestCaseBase):
    """The years before the tax year are replayed per account too.

    **Both accounts end the historical window holding the same amount and different
    cost.** That is what makes this observable, and it is not decoration: the opening
    reconciliation pins each ledger to the reported balance, so a ledger that replayed
    both accounts' history is trimmed back to the right *quantity* and keeps the wrong
    *lots*. Unequal amounts would be repaired by that trim, by accident, and the test
    would pass with the filter deleted — which is exactly what happened to the
    securities half of this before it was written this way.

    A sells a USD share in 2024 receiving 1000 USD at 0.50 EUR/USD.
    B sells a USD share in 2024 receiving 1000 USD at 1.20 EUR/USD.
    In 2025, at 1.00, each spends its own 1000 USD.

        per account : A +500, B -200
        pooled past : both accounts hold both lots, and one of them is wrong

    Found by probe: deleting the per-account filter on the historical currency stream
    left the whole suite green.
    """
    A_ISIN, B_ISIN = "US000000FX05", "US000000FX06"
    BUY_ISIN = "US000000FX07"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                # The historical window: each account acquires its USD by selling a
                # share of its own, at its own rate.
                trade_row(A, self.A_ISIN, "2024-03-01", "-10", "100", "SELL", "C", "H1",
                          currency="USD"),
                trade_row(B, self.B_ISIN, "2024-03-02", "-10", "100", "SELL", "C", "H2",
                          currency="USD"),
                # The tax year: each spends its own balance. **B spends first**, which
                # is what makes the two readings disagree: pooled FIFO consumes the
                # oldest lot in the person's pile, so B's spend would take A's 0.50 lot
                # and A's would be left with B's 1.20 one -- the two figures swapped.
                # With A spending first the pooled order happens to agree, and the test
                # passed on the base branch.
                trade_row(B, self.BUY_ISIN, "2025-06-01", "10", "100", "BUY", "O", "T1",
                          currency="USD"),
                trade_row(A, self.BUY_ISIN, "2025-06-02", "10", "100", "BUY", "O", "T2",
                          currency="USD"),
            ],
            positions_start_data=[],
            positions_end_data=[
                position_row(A, self.BUY_ISIN, "10", "1000", currency="USD", price="100"),
                position_row(B, self.BUY_ISIN, "10", "1000", currency="USD", price="100"),
            ],
            cash_balance_data=[
                cash_balance_row(A, "USD", "1000", "0", year=TAX_YEAR),
                cash_balance_row(B, "USD", "1000", "0", year=TAX_YEAR),
            ],
            custom_rate_provider=_Rates({
                "2024-03-01": "0.50", "2024-03-02": "1.20",
                "2025-06-01": "1.00", "2025-06-02": "1.00",
            }),
            tax_year=TAX_YEAR,
        )

    def test_each_account_spends_the_balance_its_own_past_built(self):
        by_date = {r.realization_date: r for r in _fx_rgls(self._run())
                   if r.realization_type == RealizationType.FX_IMPLICIT_SECURITY_PURCHASE}
        assert set(by_date) == {"2025-06-01", "2025-06-02"}, by_date
        assert by_date["2025-06-01"].gross_gain_loss_eur == Decimal("-200"), \
            "B spends first and takes B's own 1.20 acquisition, not A's older 0.50 one"
        assert by_date["2025-06-02"].gross_gain_loss_eur == Decimal("500"), \
            "A's own 0.50 acquisition"


class TestAnAccountWithNoOpeningBalance(FifoTestCaseBase):
    """A currency spent from an account that opens holding none of it.

    Pooled, the person has plenty and the spend is measured against the other
    account's lots. Per account, this account is overdrawn and opens a short
    position ([GT-FX-006]) — which is a different figure, and it is the honest one:
    nothing in A's balance paid for what B spent.
    """
    ISIN = "US000000FX02"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(B, self.ISIN, "2025-06-01", "10", "100", "BUY", "O", "T1",
                          currency="USD"),
            ],
            positions_start_data=[_usd_position(A, "5000", "2500")],
            positions_end_data=[
                position_row(B, self.ISIN, "10", "1000", currency="USD", price="100"),
                _usd_position(A, "5000", "2500"),
            ],
            cash_balance_data=[
                cash_balance_row(A, "USD", "5000", "5000", year=TAX_YEAR),
                cash_balance_row(B, "USD", "0", "-1000", year=TAX_YEAR),
            ],
            custom_rate_provider=_Rates({"2025-06-01": "1.00"}),
            tax_year=TAX_YEAR,
        )

    def test_nothing_is_taken_from_the_other_accounts_balance(self):
        out = self._run()
        assert not any(
            r.total_cost_basis_eur == Decimal("500")
            for r in _fx_rgls(out)), \
            "A's 0.50 lots must not pay for a spend made from B"

    def test_nothing_is_realised_at_all(self):
        """Pooled, the spend consumes A's cheap lots and declares a gain. Per account
        it opens a short in B and declares nothing until that short is covered — a
        different figure on the return, not a different internal representation.

        Asserting on the absence of a gap would prove nothing here: both readings
        reconcile, because the pooled ledger's total also matches the reported total.
        """
        assert _fx_rgls(self._run()) == [], \
            "no lot of A's paid for a spend made from B, so nothing is realised yet"


class TestTheEndOfYearCheckRunsPerAccount(FifoTestCaseBase):
    """Too high in one account and too low in the other cancels out per person.

    A is reported holding 1000 USD it never acquired; B is reported holding 1000
    less than its ledger says. The person's total agrees with the broker exactly,
    so a person-level check passes — and every disposal in both accounts has been
    measured against the wrong balance.
    """

    def _run(self):
        return self._run_pipeline(
            trades_data=[],
            positions_start_data=[],
            positions_end_data=[],
            cash_balance_data=[
                cash_balance_row(A, "USD", "0", "1000", year=TAX_YEAR),
                cash_balance_row(B, "USD", "2000", "1000", year=TAX_YEAR),
            ],
            custom_rate_provider=_Rates({}),
            tax_year=TAX_YEAR,
        )

    def test_both_sides_of_a_cancelling_pair_are_reported(self):
        gaps = _gaps(self._run(), "CURRENCY_EOY_MISMATCH")
        assert len(gaps) == 2, \
            "a person-level check sees 2000 reported against 2000 held and passes"
        assert {g.subject for g in gaps} == {f"USD (Konto {A})", f"USD (Konto {B})"}


class TestALedgerWithNoReportedBalanceIsRecorded(FifoTestCaseBase):
    """A currency ledger the cash report does not cover is reconciled against nothing.

    A holds 1000 USD and moves all of it to B, which then simply holds it. B does
    nothing else with dollars, and B's Cash_Balance row is zero on both ends, so it is
    dropped as dust — B's USD has no reported end-of-year position at all. B's ledger
    says 1000; there is nothing to check it against.

    Absent is not empty: the §20 Abs. 2 Satz 1 Nr. 7 gains computed from that ledger are
    unconfirmed, so the run records `CURRENCY_EOY_UNRECONCILED` for B rather than
    skipping the account in silence. A, which moved everything out and reports zero,
    reconciles cleanly and gets no such gap.

    Red-first: with the skip (`if reported_eoy is None: continue`) B's 1000 vanishes
    without a gap.
    """

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(B, "US000000FX12", "2025-01-05", "10", "10", "BUY", "O", "E1"),
            ],
            positions_start_data=[_usd_position(A, "1000", "500")],
            positions_end_data=[
                position_row(B, "US000000FX12", "10", "100", price="10"),
            ],
            cash_balance_data=[cash_balance_row(A, "USD", "1000", "0", year=TAX_YEAR)],
            transfers_data=[
                transfer_row(A, B, "OUT", "20250601", asset_class="CASH",
                             currency="USD", quantity="0", cash_transfer="-1000",
                             tx_id="X1", multiplier=""),
                transfer_row(B, A, "IN", "20250601", asset_class="CASH",
                             currency="USD", quantity="0", cash_transfer="1000",
                             tx_id="X1", multiplier=""),
            ],
            custom_rate_provider=_Rates({"2025-06-01": "1.00"}),
            tax_year=TAX_YEAR,
        )

    def test_the_unreconciled_ledger_is_recorded_not_skipped(self):
        gaps = _gaps(self._run(), "CURRENCY_EOY_UNRECONCILED")
        assert len(gaps) == 1, \
            "B holds 1000 USD from the move with no reported balance to check it against"
        assert gaps[0].subject == f"USD (Konto {B})"


class TestASingleAccountRunIsUnchanged(FifoTestCaseBase):
    """The account is named only when there is one to name."""

    def test_a_run_with_no_account_column_reports_the_currency_alone(self):
        out = self._run_pipeline(
            trades_data=[],
            positions_start_data=[],
            positions_end_data=[],
            cash_balance_data=[cash_balance_row("", "USD", "0", "1000", year=TAX_YEAR)],
            custom_rate_provider=_Rates({}),
            tax_year=TAX_YEAR,
        )
        gaps = _gaps(out, "CURRENCY_EOY_MISMATCH")
        assert len(gaps) == 1
        assert gaps[0].subject == "USD", "no account id, nothing to name"


class TestMovingMoneyBetweenYourAccounts(FifoTestCaseBase):
    """A move is a disposal of one Kapitalforderung and an acquisition of another.

    A opens holding 1000 USD acquired at 0.50 EUR/USD. On 2025-06-01, when the rate
    is 1.00, all 1000 move to B. On 2025-09-01, when the rate is 1.10, B spends them.

        realised at the move  : 1000 x 1.00 - 1000 x 0.50 = +500
        realised at the spend : 1000 x 1.10 - 1000 x 1.00 = +100
        total                                               +600

    Under the reading that a move relocates the balance, nothing is realised in June
    and the September spend realises 600 in one go. The totals agree — which is why
    the test asserts the *split*, not the sum: that is the whole difference between
    the two readings, and in a year where the balance were not spent it would be the
    difference between 500 and nothing.
    """
    ISIN = "US000000FX03"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(B, self.ISIN, "2025-09-01", "10", "100", "BUY", "O", "T1",
                          currency="USD"),
            ],
            positions_start_data=[_usd_position(A, "1000", "500")],
            positions_end_data=[
                position_row(B, self.ISIN, "10", "1100", currency="USD", price="110"),
            ],
            cash_balance_data=[
                cash_balance_row(A, "USD", "1000", "0", year=TAX_YEAR),
                cash_balance_row(B, "USD", "0", "0", year=TAX_YEAR),
            ],
            transfers_data=[
                transfer_row(A, B, "OUT", "20250601", asset_class="CASH",
                             currency="USD", quantity="0", cash_transfer="-1000",
                             tx_id="X1", multiplier=""),
                transfer_row(B, A, "IN", "20250601", asset_class="CASH",
                             currency="USD", quantity="0", cash_transfer="1000",
                             tx_id="X1", multiplier=""),
            ],
            custom_rate_provider=_Rates({"2025-06-01": "1.00", "2025-09-01": "1.10"}),
            tax_year=TAX_YEAR,
        )

    def test_the_move_itself_realises_the_gain_accrued_up_to_that_day(self):
        realised = [r for r in _fx_rgls(self._run())
                    if r.realization_date == "2025-06-01"]
        assert len(realised) == 1, "the Umbuchung is a Veraeusserung ([GT-FX-009])"
        assert realised[0].gross_gain_loss_eur == Decimal("500")

    def test_the_receiving_account_acquires_at_the_moves_own_rate(self):
        """[GT-FX-010]: the new Kapitalforderung's Anschaffungskosten are the gemeiner
        Wert of what was received, converted on the day of the move."""
        spend = [r for r in _fx_rgls(self._run())
                 if r.realization_date == "2025-09-01"]
        assert len(spend) == 1
        assert spend[0].total_cost_basis_eur == Decimal("1000"), \
            "1000 at the June rate, not the 500 the units originally cost"
        assert spend[0].gross_gain_loss_eur == Decimal("100")

    def test_the_receiving_account_needs_no_other_currency_activity(self):
        """The balance can arrive in an account that has never held that currency.

        Every other source of a currency ledger is something the receiving account did
        itself — its own events, or a row in the cash report. An account that only ever
        *received* has none of those, and without a ledger the move has nowhere to put
        the balance. B here holds a euro-priced share, so it is an account the input
        reports, and has no dollar activity of any kind.

        Found by probe: with B spending the balance in the same year, B's own spend
        registers the ledger and deleting the receiving-side registration left the suite
        green.
        """
        out = self._run_pipeline(
            trades_data=[
                trade_row(B, "US000000FX12", "2025-01-05", "10", "10", "BUY", "O", "E1"),
            ],
            positions_start_data=[_usd_position(A, "1000", "500")],
            positions_end_data=[
                position_row(B, "US000000FX12", "10", "100", price="10"),
            ],
            cash_balance_data=[cash_balance_row(A, "USD", "1000", "0", year=TAX_YEAR)],
            transfers_data=[
                transfer_row(A, B, "OUT", "20250601", asset_class="CASH", currency="USD",
                             quantity="0", cash_transfer="-1000", tx_id="R1",
                             multiplier=""),
                transfer_row(B, A, "IN", "20250601", asset_class="CASH", currency="USD",
                             quantity="0", cash_transfer="1000", tx_id="R1",
                             multiplier=""),
            ],
            custom_rate_provider=_Rates({"2025-06-01": "1.00"}),
            tax_year=TAX_YEAR,
        )
        realised = [r for r in _fx_rgls(out) if r.realization_date == "2025-06-01"]
        assert len(realised) == 1, "the move still has to be applied, and both halves"
        assert realised[0].gross_gain_loss_eur == Decimal("500")

    def test_the_two_sides_of_one_move_are_not_applied_twice(self):
        """The export writes each move once per side. Both describe the same move."""
        assert len([r for r in _fx_rgls(self._run())
                    if r.realization_date == "2025-06-01"]) == 1


class TestACashMoveKeepsItsBrokerChronology(FifoTestCaseBase):
    """A cash Umbuchung is ordered by the broker's own chronology among the day's
    currency events, not forced ahead of them.

    On 2025-06-01, in the broker's order, B:
      1. buys USD 100 for EUR 50            (tx 100) -> a lot at 0.50 EUR/USD
      2. receives USD 100 by Umbuchung, valued EUR 80 at that day's rate (tx 200)
      3. buys a share for USD 100           (tx 300), consuming USD 100

    FIFO consumes the earlier, cheaper lot: the USD spent on the share is valued at
    0.80 and the consumed lot cost 0.50, realising +30, and the 0.80 lot from the move
    remains. The sending account A held its 100 USD at 0.80 and disposes at 0.80, so
    the move realises 0 on A. Total FX = 30.

    Forcing the move ahead of the whole day (the corporate-action band it used to take)
    consumed the 0.80 move-lot on the share purchase and realised 0 -- the F1 defect.
    """

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                fx_trade_row(B, "USD", "BUY", "100", "50", "2", "2025-06-01", "100"),
                trade_row(B, "US000000RV89", "2025-06-01", "1", "100", "BUY", "O",
                          "300", currency="USD"),
            ],
            positions_start_data=[_usd_position(A, "100", "80")],
            positions_end_data=[
                position_row(B, "US000000RV89", "1", "100", currency="USD"),
            ],
            cash_balance_data=[
                cash_balance_row(A, "USD", "100", "0"),
                cash_balance_row(B, "USD", "0", "100"),
            ],
            transfers_data=[
                transfer_row(A, B, "OUT", "20250601", asset_class="CASH",
                             currency="USD", cash_transfer="-100", tx_id="200"),
                transfer_row(B, A, "IN", "20250601", asset_class="CASH",
                             currency="USD", cash_transfer="100", tx_id="200"),
            ],
            custom_rate_provider=_Rates({"2025-06-01": "0.80"}), tax_year=TAX_YEAR)

    def test_the_earlier_cheaper_lot_is_consumed_before_the_moves_lot(self):
        out = self._run()
        assert not _gaps(out, "CURRENCY_EOY_MISMATCH")
        assert not _gaps(out, "CURRENCY_EOY_UNRECONCILED")
        assert _fx_total(out) == Decimal("30"), \
            "the 0.50 lot is consumed, not the 0.80 lot the move delivered"


class TestAMoveInAnEarlierYear(FifoTestCaseBase):
    """The replay half, which is the half a real export usually exercises.

    A move dated before the tax year is not declared by this return — the year it
    belonged to declared it — but it decides what each account then holds and what it
    cost, and every later disposal is measured against that.

    A acquires two 500-USD lots in 2023, at 0.50 and at 0.80. In 2024, at 1.00, **500**
    move to B — a part of the balance, which is ordinary for cash and refused for
    securities, because FIFO says which units went. In 2025 B spends its 500 at 1.25 and
    A spends its remaining 500 at 1.60.

        move applied : B's lot cost 500 (the move's own day) → B gains 125
                       A's oldest lot went, so A's 0.80 lot is left    → A gains 400
        move ignored : B has nothing to spend and A still holds the 0.50 lot first
                       → B realises nothing and A gains 550

    The rates are exact reciprocals, so every figure above is exact rather than rounded:
    the provider inverts EUR-per-unit into the ECB's unit-per-EUR quote.

    **No cash-balance rows, on purpose.** With them, the opening reconciliation repairs
    every one of these mutations by accident: it trims a ledger that kept too much and
    rebuilds one that has too little, both from the reported figure, so the four ends
    below stayed invisible through two attempts at this test. That is CLAUDE.md's
    "anything a start-of-year snapshot can rebuild", met head-on. Here each account's
    ledger is what its own history made it, and the move is the only thing that puts a
    balance in B at all.

    Probing found these four ends invisible before this test existed, each deletable
    with the whole suite green: `_currencies_of_event` returning nothing for this event,
    the sending consume, the receiving create, and the receiving account's ledger
    registration.
    """
    A_SELL_1, A_SELL_2 = "US000000FX08", "US000000FX09"
    A_BUY, B_BUY = "US000000FX10", "US000000FX11"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, self.A_SELL_1, "2023-06-01", "-5", "100", "SELL", "C",
                          "H1", currency="USD"),
                trade_row(A, self.A_SELL_2, "2023-07-01", "-5", "100", "SELL", "C",
                          "H2", currency="USD"),
                trade_row(B, self.B_BUY, "2025-06-01", "5", "100", "BUY", "O", "T1",
                          currency="USD"),
                trade_row(A, self.A_BUY, "2025-07-01", "5", "100", "BUY", "O", "T2",
                          currency="USD"),
            ],
            positions_start_data=[],
            positions_end_data=[
                position_row(B, self.B_BUY, "5", "550", currency="USD", price="110"),
                position_row(A, self.A_BUY, "5", "600", currency="USD", price="120"),
            ],
            transfers_data=[
                transfer_row(A, B, "OUT", "20240301", asset_class="CASH", currency="USD",
                             quantity="0", cash_transfer="-500", tx_id="H3",
                             multiplier=""),
                transfer_row(B, A, "IN", "20240301", asset_class="CASH", currency="USD",
                             quantity="0", cash_transfer="500", tx_id="H3",
                             multiplier=""),
            ],
            custom_rate_provider=_Rates({
                "2023-06-01": "0.50", "2023-07-01": "0.80",
                "2024-03-01": "1.00",
                "2025-06-01": "1.25", "2025-07-01": "1.60",
            }),
            tax_year=TAX_YEAR,
        )

    def test_the_receiving_account_spends_what_the_move_gave_it(self):
        spends = {r.realization_date: r for r in _fx_rgls(self._run())
                  if r.realization_type == RealizationType.FX_IMPLICIT_SECURITY_PURCHASE}
        assert "2025-06-01" in spends, "the move is the only thing that puts USD in B"
        assert spends["2025-06-01"].total_cost_basis_eur == Decimal("500"), \
            "priced at the day of the move, not at what the units originally cost A"
        assert spends["2025-06-01"].gross_gain_loss_eur == Decimal("125")

    def test_the_sending_account_gave_up_its_oldest_units(self):
        """FIFO decides which half went ([GT-FX-008]), so what A has left is the 0.60
        lot. A sending side that did not consume would leave the 0.50 lot in front and
        A's own later spend would be measured against it."""
        spends = {r.realization_date: r for r in _fx_rgls(self._run())
                  if r.realization_type == RealizationType.FX_IMPLICIT_SECURITY_PURCHASE}
        assert "2025-07-01" in spends
        assert spends["2025-07-01"].total_cost_basis_eur == Decimal("400"), \
            "A's remaining 0.80 lot, not the 0.50 one the move took"
        assert spends["2025-07-01"].gross_gain_loss_eur == Decimal("400")

    def test_the_move_itself_declares_nothing_in_this_year(self):
        """It belonged to an earlier return. The replay rebuilds lot state and produces
        no realised gain — the same rule every other historical event follows."""
        assert not [r for r in _fx_rgls(self._run())
                    if r.realization_date and r.realization_date < f"{TAX_YEAR}-01-01"]


class TestAnEarlierMoveReconcilesAtYearEnd(FifoTestCaseBase):
    """The completed-run half the contributor's real export cannot reach: it aborts at an
    unrelated securities grant before the currency reconciliation, so this stands in for it
    as a self-contained synthetic run.

    A move from before the tax year builds each account's balance, and the year-end currency
    reconciliation ties the ledger out against the broker's reported cash balance with no gap
    — the whole point of routing the historical move through the same account-local
    coordinator the tax-year path uses. A buys 1000 USD in 2023; in 2024, before this
    return's year, 400 move to B; nobody spends in 2025. At the close of 2025 A holds 600 and
    B holds 400, both of which exist only because the historical move was replayed onto the
    two ledgers, and both of which the broker reports, so the run completes and every currency
    ledger reconciles.

    SoY balances are given as zero on purpose: a non-zero SoY snapshot makes
    `_reconcile_currency_soy` rebuild the ledger from the reported figure and mask the move
    (CLAUDE.md's "anything a start-of-year snapshot can rebuild"). With SoY zero the year-end
    check compares the historically-built ledger itself — break the receiving side and B
    reconciles 0 against a reported 400, a CURRENCY_EOY_MISMATCH.
    """

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                fx_trade_row(A, "USD", "BUY", "1000", "500", "2.0", "2023-06-01", "H1"),
            ],
            positions_start_data=[],
            positions_end_data=[],
            cash_balance_data=[
                cash_balance_row(A, "USD", "0", "600", year=TAX_YEAR),
                cash_balance_row(B, "USD", "0", "400", year=TAX_YEAR),
            ],
            transfers_data=[
                transfer_row(A, B, "OUT", "20240301", asset_class="CASH", currency="USD",
                             quantity="0", cash_transfer="-400", tx_id="H2",
                             multiplier=""),
                transfer_row(B, A, "IN", "20240301", asset_class="CASH", currency="USD",
                             quantity="0", cash_transfer="400", tx_id="H2",
                             multiplier=""),
            ],
            custom_rate_provider=_Rates({"2023-06-01": "0.50", "2024-03-01": "1.0"}),
            tax_year=TAX_YEAR,
        )

    def test_both_accounts_reconcile_with_no_gap(self):
        out = self._run()
        assert not _gaps(out, "CURRENCY_EOY_MISMATCH"), \
            "the move built 600 in A and 400 in B, each matching its reported balance"
        assert not _gaps(out, "CURRENCY_EOY_UNRECONCILED"), \
            "both balances are reported, so neither is unreconciled"

    def test_the_earlier_move_declares_nothing_this_year(self):
        assert _fx_total(self._run()) == Decimal("0"), \
            "the move belonged to an earlier return; nothing is spent in this one"


class TestWhatACashMoveDoesNotDo(FifoTestCaseBase):
    ISIN = "US000000FX04"

    def _run(self, transfers, cash=None, **kw):
        return self._run_pipeline(
            trades_data=[],
            positions_start_data=[],
            positions_end_data=[],
            cash_balance_data=cash if cash is not None else [
                cash_balance_row(A, "USD", "0", "0", year=TAX_YEAR),
                cash_balance_row(B, "USD", "0", "0", year=TAX_YEAR),
            ],
            transfers_data=transfers,
            custom_rate_provider=_Rates({"2025-06-01": "1.00"}),
            tax_year=TAX_YEAR,
            **kw,
        )

    def test_a_move_of_euros_realises_nothing(self):
        """§ 20 Abs. 2 Satz 1 Nr. 7 reaches a *Fremdwaehrungs*guthaben, and the
        declaration is written in euros. Read, and deliberately without effect."""
        out = self._run([
            transfer_row(A, B, "OUT", "20250601", asset_class="CASH", currency="EUR",
                         quantity="0", cash_transfer="-1000", tx_id="X1",
                         multiplier=""),
            transfer_row(B, A, "IN", "20250601", asset_class="CASH", currency="EUR",
                         quantity="0", cash_transfer="1000", tx_id="X1",
                         multiplier=""),
        ])
        assert _fx_rgls(out) == []

    def test_a_move_to_an_account_the_input_never_reports_stops_the_run(self):
        """[GT-FX-009] reaches an Umbuchung between the taxpayer's OWN accounts. A
        payment to somebody else is a disposal for consideration or a gift, and
        realising the currency gain as if it stayed in the family would be a figure
        the claim does not carry. IBKR's `INTERNAL` says the far side is an IBKR
        account, not that it is yours."""
        with pytest.raises(DataGapError, match="TRANSFER_COUNTERPARTY_UNKNOWN"):
            self._run([
                transfer_row(A, "U90000009", "OUT", "20250601", asset_class="CASH",
                             currency="USD", quantity="0", cash_transfer="-1000",
                             tx_id="X1", multiplier=""),
            ], cash=[cash_balance_row(A, "USD", "1000", "0", year=TAX_YEAR)])

    def test_a_move_whose_day_has_no_rate_stops_the_historical_replay(self):
        """The historical cash-move path refuses a move it cannot value, rather than
        skipping it. A move swallowed would leave the sending account holding a balance it
        no longer has and the receiving one short of what it received -- and the opening
        reconciliation then repairs the QUANTITY against the cash report and synthesises the
        lots, so the run finishes with acquisition dates nobody measured. That is the blind
        spot `CLAUDE.md` names, and it is why this path raises rather than skips.
        """
        import uuid as _uuid
        from decimal import Context
        from types import SimpleNamespace
        from src.domain.enums import AssetCategory
        from src.domain.events import InternalCashTransferEvent
        from src.domain.exceptions import ProcessingError
        from src.engine.calculation_engine import apply_historical_cash_transfer
        from src.utils.account_utils import account_key
        from tests.test_stock_merger_fifo import _make_ledger

        asset_id = _uuid.uuid4()
        source = _make_ledger(asset_id, AssetCategory.CASH_BALANCE)
        target = _make_ledger(asset_id, AssetCategory.CASH_BALANCE)
        event = InternalCashTransferEvent(
            _uuid.uuid4(), "2023-06-19", to_account_id=B, quantity=Decimal("1000"),
            account_id=A, local_currency="USD",
            gross_amount_foreign_currency=Decimal("1000"))
        # What enrichment leaves behind when the day has no rate after its fallback.
        event.gross_amount_eur = None
        resolver = SimpleNamespace(
            get_cash_balance_asset=lambda _: SimpleNamespace(internal_asset_id=asset_id))

        with pytest.raises(ProcessingError, match="no exchange rate"):
            apply_historical_cash_transfer(
                event, {(account_key(A), asset_id): source,
                        (account_key(B), asset_id): target},
                resolver, Context(prec=28))
        assert not source.lots and not source.short_lots
        assert not target.lots and not target.short_lots

    def test_a_cash_row_with_no_amount_stops_the_run(self):
        """`CashTransfer` is the only column carrying it — `Quantity`,
        `PositionAmount` and `TransferPrice` are all zero on a cash row. Reading a
        move of nothing as a move would leave the balance where it was while the
        broker reported it elsewhere."""
        with pytest.raises(pytest.fail.Exception, match="CashTransfer"):
            self._run([
                transfer_row(A, B, "OUT", "20250601", asset_class="CASH",
                             currency="USD", quantity="0", cash_transfer="0",
                             tx_id="X1", multiplier=""),
            ])


def _usd_position(account, quantity, cost_basis_eur):
    """One Positions row for a USD cash balance.

    A CASH row in a Positions export is where a cost basis for a balance comes
    from; the cash report states quantities only. Some exports carry such rows and
    some do not, which is why the reconciliation falls back to the ECB rate of the
    reconciliation date when there is none.
    """
    from tests.support.multi_account import POSITIONS_COLUMNS  # noqa: F401 - shape check
    q = Decimal(str(quantity))
    unit = Decimal(str(cost_basis_eur)) / q if q else Decimal("1")
    return [account, "USD", "CASH", "", "USD", "Cash Balance USD", "", q,
            q * unit, unit, Decimal(str(cost_basis_eur)), None, None, None,
            Decimal("1")]


class TestASuppliedBalanceIsComparedNotCalledAbsent(FifoTestCaseBase):
    """A cash-balance row below the parser's threshold is still a value the broker
    reported. The end-of-year reconciliation compares the ledger against it instead of
    recording CURRENCY_EOY_UNRECONCILED as though nothing was reported (F4). The opening
    is still not seeded from a sub-threshold row, so no figure moves."""

    def test_a_reported_zero_is_a_comparison_value_not_an_absent_report(self):
        out = self._run_pipeline(
            trades_data=[fx_trade_row(A, "USD", "BUY", "100", "80", "1.25",
                                      "2025-06-01", "100")],
            positions_start_data=[], positions_end_data=[],
            cash_balance_data=[cash_balance_row(A, "USD", "0", "0")],
            custom_rate_provider=_Rates({"2025-06-01": "0.80"}), tax_year=TAX_YEAR)
        assert not _gaps(out, "CURRENCY_EOY_UNRECONCILED"), \
            "a supplied zero is not an absent report"
        assert len(_gaps(out, "CURRENCY_EOY_MISMATCH")) == 1, \
            "ledger of 100 against a reported 0 is a mismatch, and it is compared"


class TestCurrencyDiagnosticsAreOrderedStably(FifoTestCaseBase):
    """The per-account currency diagnostics are ordered by (currency, account) -- stable
    identifiers -- not by the asset's uuid4 internal id, which is redrawn every run and
    reordered the warnings, PDF included, between two runs of the same tree (F4)."""

    def test_the_diagnostics_come_out_in_a_stable_currency_order(self):
        currencies = ["USD", "GBP", "CHF", "JPY", "AUD"]
        out = self._run_pipeline(
            trades_data=[fx_trade_row(A, c, "BUY", "100", "80", "1.25", "2025-06-01",
                                      f"T{i}") for i, c in enumerate(currencies)],
            positions_start_data=[], positions_end_data=[],
            cash_balance_data=[cash_balance_row(A, c, "0", "0") for c in currencies],
            custom_rate_provider=_Rates({"2025-06-01": "0.80"}), tax_year=TAX_YEAR)
        subjects = [g.subject for g in _gaps(out, "CURRENCY_EOY_MISMATCH")]
        assert len(subjects) == len(currencies)
        assert subjects == sorted(subjects), \
            "diagnostics must be ordered by stable currency/account ids, not asset uuid"


class TestACashMoveIsAtomic:
    """The two sides of a cash Umbuchung fall on two ledgers. Both are prepared on isolated
    copies and committed only once both succeed, so a failure on the receiving side never
    leaves the sending balance already disposed of. Before the fix the sending disposal was
    committed before the receiving acquisition was even attempted."""

    def test_a_receiving_side_failure_leaves_the_sender_untouched(self, monkeypatch):
        from types import SimpleNamespace
        from uuid import uuid4
        from src.domain.enums import AssetCategory
        from src.domain.events import InternalCashTransferEvent
        from src.domain.exceptions import ProcessingError
        from src.engine.event_processors.currency_conversion_processor import (
            CurrencyConversionProcessor)
        from src.engine.event_processors.transfer_processor import (
            InternalCashTransferProcessor)
        from tests.test_stock_merger_fifo import _make_ledger, _make_long_lot

        asset_id = uuid4()
        source = _make_ledger(asset_id, AssetCategory.CASH_BALANCE)
        target = _make_ledger(asset_id, AssetCategory.CASH_BALANCE)
        lot = _make_long_lot("2023-01-01", "100", "0.50", "OPEN")
        source.lots = [lot]
        currency = CurrencyConversionProcessor(source.currency_converter, 28, "ROUND_HALF_UP")
        monkeypatch.setattr(currency, "create_long_lot_for_cashflow_income",
                            lambda *a, **k: (_ for _ in ()).throw(
                                ProcessingError("receiving-side validation failed")))
        event = InternalCashTransferEvent(
            asset_id, "2025-06-01", account_id="A", to_account_id="B",
            quantity=Decimal("100"), local_currency="USD", gross_amount_eur=Decimal("80"))
        resolver = SimpleNamespace(
            get_cash_balance_asset=lambda _: SimpleNamespace(internal_asset_id=asset_id))
        with pytest.raises(ProcessingError, match="receiving-side"):
            InternalCashTransferProcessor().process(event, source, {
                "asset_resolver": resolver,
                "currency_fifo_ledgers": {("A", asset_id): source, ("B", asset_id): target},
                "currency_processor": currency})
        assert source.lots == [lot] and source.lots[0].quantity == Decimal("100")
        assert not target.lots


class TestAHistoricalCashMoveIsAtomic:
    """A cash Umbuchung replayed from before the tax year falls on two ledgers, exactly like
    the tax-year move, and goes through the same prepare-both-then-commit boundary. A failure
    on the receiving side never leaves the sending balance already disposed of. Before the
    fix the historical replay registered the two sides as separate per-account stream
    callbacks, so the sending disposal was committed before the receiving acquisition was
    attempted -- partial mutation on an aborted run."""

    def test_a_receiving_side_failure_leaves_the_sender_untouched(self, monkeypatch):
        from types import SimpleNamespace
        from decimal import Context
        from uuid import uuid4
        from src.domain.enums import AssetCategory
        from src.domain.events import InternalCashTransferEvent
        from src.domain.exceptions import ProcessingError
        from src.engine import calculation_engine as engine
        from src.utils.account_utils import account_key
        from tests.test_stock_merger_fifo import _make_ledger, _make_long_lot

        asset_id = uuid4()
        source = _make_ledger(asset_id, AssetCategory.CASH_BALANCE)
        target = _make_ledger(asset_id, AssetCategory.CASH_BALANCE)
        lot = _make_long_lot("2023-01-01", "100", "0.50", "OPEN")
        source.lots = [lot]
        # The receiving side (a historical lot creation) refuses. It runs after the sending
        # side has already been computed -- on an isolated copy, which is the whole point.
        monkeypatch.setattr(engine, "_create_lot_historical",
                            lambda *a, **k: (_ for _ in ()).throw(
                                ProcessingError("receiving-side validation failed")))
        event = InternalCashTransferEvent(
            asset_id, "2024-06-01", account_id="A", to_account_id="B",
            quantity=Decimal("100"), local_currency="USD", gross_amount_eur=Decimal("80"))
        resolver = SimpleNamespace(
            get_cash_balance_asset=lambda _: SimpleNamespace(internal_asset_id=asset_id))
        with pytest.raises(ProcessingError, match="receiving-side"):
            engine.apply_historical_cash_transfer(
                event, {(account_key("A"), asset_id): source,
                        (account_key("B"), asset_id): target},
                resolver, Context(prec=28))
        assert source.lots == [lot] and source.lots[0].quantity == Decimal("100")
        assert not target.lots and not target.short_lots


class TestACashMoveWithoutItsLedgerFailsFast(FifoTestCaseBase):
    """The cash-transfer dispatch resolves both account ledgers inside the processor and
    fails fast if one is missing, so the move is dispatched even when the loop found no ledger
    for the sending account. Otherwise its CASH_BALANCE category dodges the non-cash "requires
    a FIFO ledger" raise and the move is silently dropped -- a disposal lost with no warning.
    Unreachable while registration builds every named account's ledger; this pins the
    fail-fast against a registration/lookup drift.
    """

    def test_a_missing_sending_ledger_raises_instead_of_dropping(self, monkeypatch):
        from src.engine import calculation_engine as engine
        from src.utils.account_utils import account_key

        original = engine._ensure_currency_ledger_exists

        def skip_the_senders_usd_ledger(currency_code, ledger_account, *rest):
            # Simulate a registration/lookup drift: the sending account's USD ledger is
            # never built, so the current-year dispatch finds no ledger for the move.
            if currency_code == "USD" and account_key(ledger_account) == account_key(A):
                return
            return original(currency_code, ledger_account, *rest)

        monkeypatch.setattr(engine, "_ensure_currency_ledger_exists",
                            skip_the_senders_usd_ledger)

        # `_run_pipeline` converts a pipeline `ProcessingError` into `pytest.fail`, so the
        # raise surfaces here as `pytest.fail.Exception` carrying the original message.
        with pytest.raises(pytest.fail.Exception, match="no currency ledger"):
            self._run_pipeline(
                trades_data=[],
                positions_start_data=[],
                positions_end_data=[],
                cash_balance_data=[cash_balance_row(A, "USD", "0", "0", year=TAX_YEAR),
                                   cash_balance_row(B, "USD", "0", "100", year=TAX_YEAR)],
                transfers_data=[
                    transfer_row(A, B, "OUT", f"{TAX_YEAR}0601", asset_class="CASH",
                                 currency="USD", quantity="0", cash_transfer="-100",
                                 tx_id="M1", multiplier=""),
                    transfer_row(B, A, "IN", f"{TAX_YEAR}0601", asset_class="CASH",
                                 currency="USD", quantity="0", cash_transfer="100",
                                 tx_id="M1", multiplier=""),
                ],
                custom_rate_provider=_Rates({f"{TAX_YEAR}-06-01": "1.0"}),
                tax_year=TAX_YEAR,
            )


class TestASingleSidedMoveInTheYearRealisesTheDisposal(FifoTestCaseBase):
    """The shape the contributor's real export carries, pinned as a figure. A non-EUR
    Umbuchung between the taxpayer's own accounts is reported by the sending OUT row alone --
    no matching IN -- dated inside the tax year. It is a current-year § 20 Abs. 2 disposal of
    the sending account's Kapitalforderung: the move is built from the one observed side and
    realises the gain accrued up to that day. On the contributor's full run this figure is
    reached but never emitted, because an unrelated securities reconciliation aborts first; it
    is pinned here directly so the § 20 delta is measured, not left to that abort.

    A opens the year holding 100 USD at 0.80 EUR/USD. On 2025-06-01, at 1.00, all 100 move to
    B. The disposal realises 100 x (1.00 - 0.80) = +20 EUR.
    """

    def _run(self):
        return self._run_pipeline(
            trades_data=[],
            positions_start_data=[_usd_position(A, "100", "80")],
            positions_end_data=[],
            cash_balance_data=[cash_balance_row(A, "USD", "100", "0", year=TAX_YEAR),
                               cash_balance_row(B, "USD", "0", "100", year=TAX_YEAR)],
            transfers_data=[
                # Single-sided, exactly as the real export reports it: the sending OUT row
                # with no matching IN. The receiving leg is synthesised.
                transfer_row(A, B, "OUT", f"{TAX_YEAR}0601", asset_class="CASH",
                             currency="USD", quantity="0", cash_transfer="-100",
                             tx_id="T1", multiplier=""),
            ],
            custom_rate_provider=_Rates({f"{TAX_YEAR}-06-01": "1.00"}),
            tax_year=TAX_YEAR,
        )

    def test_the_single_sided_move_realises_the_year_disposal(self):
        assert _fx_total(self._run()) == Decimal("20"), \
            "100 USD disposed at 1.00 against an 0.80 basis is a +20 EUR gain"

    def test_both_accounts_reconcile(self):
        out = self._run()
        assert not _gaps(out, "CURRENCY_EOY_MISMATCH")
        assert not _gaps(out, "CURRENCY_EOY_UNRECONCILED")

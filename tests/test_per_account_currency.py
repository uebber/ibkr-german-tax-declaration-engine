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
    cash_balance_row, position_row, trade_row, transfer_row)

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
        """Both paths refuse, and the historical one had to be made to.

        Every other branch of the historical currency replay is wrapped in a catch-all
        that logs at DEBUG and carries on (issue #49). A move swallowed there leaves the
        sending account holding a balance it no longer has and the receiving one short
        of what it received -- and the opening reconciliation then repairs the QUANTITY
        against the cash report and synthesises the lots, so the run finishes with
        acquisition dates nobody measured. That is the blind spot `CLAUDE.md` names, and
        it is why this branch raises rather than skips.
        """
        import uuid as _uuid
        from decimal import Context
        from src.domain.enums import AssetCategory
        from src.domain.events import InternalCashTransferEvent
        from src.domain.exceptions import ProcessingError
        from src.engine.calculation_engine import _apply_historical_currency_event
        from src.engine.fifo_manager import FifoLedger

        ledger = FifoLedger(
            asset_internal_id=_uuid.uuid4(), asset_category=AssetCategory.CASH_BALANCE,
            asset_multiplier_from_asset=None, currency_converter=None,
            exchange_rate_provider=None, internal_working_precision=28,
            decimal_rounding_mode="ROUND_HALF_EVEN")
        event = InternalCashTransferEvent(
            _uuid.uuid4(), "2023-06-19", to_account_id=B, quantity=Decimal("1000"),
            account_id=A, local_currency="USD",
            gross_amount_foreign_currency=Decimal("1000"))
        # What enrichment leaves behind when the day has no rate after its fallback.
        event.gross_amount_eur = None

        with pytest.raises(ProcessingError, match="no exchange rate"):
            _apply_historical_currency_event(
                event, ledger, "USD", None, Context(prec=28), ledger_account=A)
        assert not ledger.lots and not ledger.short_lots

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

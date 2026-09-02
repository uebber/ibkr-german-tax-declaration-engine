"""
What the person holds is every account's row, not the last one read.

legal_basis: [GT-ESTG20-061]. The taxable subject is the person -- § 2 Abs. 1
Satz 1 Nr. 5 with § 25 Abs. 1 EStG -- so the holding a return declares is the
total across that person's accounts. Verbatim sources in
reference/tax-law/estg-20-kapitalvermoegen.md, section "Whose holding".

Ticking several accounts in one Flex Query emits them into one file, so one
instrument or one currency legitimately arrives on several rows. The engine
assigned each row to the asset in turn, so the surviving record was whichever
row the file happened to end with: one account's holding, presented as the
whole.

Every scenario below is built so the two readings differ in *outcome*, not only
in a stored number -- a holding that fails reconciliation, a gain that lands on
a different figure. A scenario where the sum and the last row agree proves
nothing. The two securities scenarios put the account that matters at opposite
ends of the file, so neither can be passed by reading the first row instead.

All identifiers and amounts are invented. CLAUDE.md forbids an account number,
a position value or a cash balance copied from a real export reaching a commit.
"""
from datetime import date
from decimal import Decimal
import uuid

import pytest
from unittest.mock import MagicMock

from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import (
    PositionSnapshot, person_mark, person_snapshot, snapshots_for_asset)
from src.domain.assets import Stock
from src.domain.enums import RealizationType
from src.domain.exceptions import DataIntegrityError
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from src.parsers.positions_parser import parse_positions_csv
from src.reporting.diagnostic_reports import print_asset_positions_diagnostic
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import (
    POSITIONS_COLUMNS, cash_balance_row, fx_trade_row, position_row, trade_row, write_csv)

A, B = "U10000001", "U10000002"
TAX_YEAR = 2023


class TestTheOpeningSnapshotIsEveryAccountsRow(FifoTestCaseBase):
    """A opens the year with 100 units and B with 50; B sells its 50.

    The person opened with 150 and closes with 100, which is what the closing
    snapshot reports. Reading the opening snapshot as B's row alone opens the
    year with 50, sells all of them, and calculates a closing holding of zero
    against a reported 100 -- a securities reconciliation failure, which is
    fatal (PRD 2.4), so the run produces no figures at all.

    The closing snapshot has one row because IBKR omits an account holding
    nothing.
    """
    ISIN = "US000000PS01"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(B, self.ISIN, "2023-06-01", "-50", "12", "SELL", "C", "T1"),
            ],
            positions_start_data=[
                position_row(A, self.ISIN, "100", "1000", price="10"),
                position_row(B, self.ISIN, "50", "500", price="10"),
            ],
            positions_end_data=[
                position_row(A, self.ISIN, "100", "1000", price="10"),
            ],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_the_year_opens_with_both_accounts_units(self):
        assert self._run().eoy_mismatch_error_count == 0

    def test_the_sale_is_declared(self):
        """The reconciliation failure is not a cosmetic one: it aborts before
        any figure is emitted, so the sale that really happened goes
        undeclared."""
        rgls = self._run().realized_gains_losses
        assert len(rgls) == 1
        assert rgls[0].quantity_realized == Decimal("50")


class TestTheClosingSnapshotIsEveryAccountsRow(FifoTestCaseBase):
    """Both accounts hold the instrument at both ends and A buys 30 more.

    The person closes with 180 across two rows. Reading the closing snapshot as
    B's row alone reports 50 against a calculated 180. Here it is the *closing*
    read that decides, and the account that moved is the one the file does not
    end with.
    """
    ISIN = "US000000PS02"

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                trade_row(A, self.ISIN, "2023-06-01", "30", "10", "BUY", "O", "T1"),
            ],
            positions_start_data=[
                position_row(A, self.ISIN, "100", "1000", price="10"),
                position_row(B, self.ISIN, "50", "500", price="10"),
            ],
            positions_end_data=[
                position_row(A, self.ISIN, "130", "1300", price="10"),
                position_row(B, self.ISIN, "50", "500", price="10"),
            ],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )

    def test_the_year_closes_with_both_accounts_units(self):
        assert self._run().eoy_mismatch_error_count == 0


class TestACurrencyHeldInTwoAccounts(FifoTestCaseBase):
    """A opens with 1000 USD and B with 500; 1000 more are bought in March at a
    different rate, and 1400 are sold in September.

    A USD is worth 0.50 EUR on the last day of the preceding year and 1.00 EUR
    from March on, so the opening lot costs 0.50 EUR per USD and the March lot
    1.00. Which lot the September sale eats therefore decides the gain:

        the person's 1500 opening : 1400 x 0.50            = 700 basis -> 700 gain
        B's 500 alone             : 500 x 0.50 + 900 x 1.00 = 1150     -> 250 gain

    Different figures on Anlage KAP, from the same export.
    """
    RATES = MockECBExchangeRateProvider(rate_schedule=[
        (date(2022, 1, 1), Decimal("0.50")),   # 1 USD = 0.50 EUR
        (date(2023, 3, 1), Decimal("1.00")),   # 1 USD = 1.00 EUR
    ])

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                fx_trade_row(A, "USD", "BUY", "1000", "1000", "1.00", "2023-03-01", "FX1"),
                fx_trade_row(A, "USD", "SELL", "1400", "1400", "1.00", "2023-09-01", "FX2"),
            ],
            cash_balance_data=[
                cash_balance_row(A, "USD", "1000", "600", year=TAX_YEAR),
                cash_balance_row(B, "USD", "500", "500", year=TAX_YEAR),
            ],
            custom_rate_provider=self.RATES,
            tax_year=TAX_YEAR,
        )

    @staticmethod
    def _fx_sales(out):
        return [r for r in out.realized_gains_losses
                if r.realization_type == RealizationType.FX_CONVERSION_SALE]

    def test_the_gain_is_measured_against_the_persons_own_opening_balance(self):
        rgls = self._fx_sales(self._run())
        assert sum(r.gross_gain_loss_eur for r in rgls) == Decimal("700")

    def test_the_whole_sale_comes_out_of_the_opening_balance(self):
        """1400 of the person's 1500 opening units, so the March lot is
        untouched and there is one realisation, not two."""
        rgls = self._fx_sales(self._run())
        assert len(rgls) == 1
        assert rgls[0].quantity_realized == Decimal("1400")

    def test_the_closing_balance_is_both_accounts_and_reconciles(self):
        """1500 opened + 1000 bought - 1400 sold = 1100, which is 600 in A and
        500 in B. Reading one row reports 500 against a calculated 100, and the
        divergence reaches the report as a gap."""
        gaps = [g for g in self._run().data_gaps if g.code == "CURRENCY_EOY_MISMATCH"]
        assert gaps == []


class TestACheckpointMarksBasisCarriesIntoALaterSale(FifoTestCaseBase):
    """A mid-window checkpoint mark's cost basis reaches a sale four years later.

    The mark is where the ledger's cost basis is set for units acquired before the
    import window: the reconstruction is compared against the reported mark and, where
    they disagree, the mark's figures are what the ledger carries forward. This checks
    that carry end to end -- from a 2021 mark to a 2024 disposal.

    Per Depot ([GT-ESTG20-013]) the mark, the carried lots and the sale are all one
    account's: the disposal consumes the lots of the account it was made from, at the
    basis that account's own mark set. (The two-account storage of a mark -- one row per
    account, `person_mark` the derived view -- is pinned at the seam in
    TestTheCheckpointMarkRegistry; here what matters is that an account's own mark basis
    is what its later sale costs.)

        A's 2021 mark : 100 units at 1400 -> 3500 - 1400 = 2100 gain
    """
    ISIN = "US000000PS03"
    RATES = MockECBExchangeRateProvider(Decimal("1.00"))

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                # No opening trade: the 100 units are carried from the 2021 mark, which is
                # exactly the basis-setting path under test.
                trade_row(A, self.ISIN, "2024-03-12", "-100", "35", "SELL", "C", "T1"),
            ],
            positions_mark_data={
                2021: [position_row(A, self.ISIN, "100", "1400", price="14")],
            },
            positions_start_data=[position_row(A, self.ISIN, "100", "1400", price="14")],
            positions_end_data=[],  # A sold all 100; IBKR omits a zero holding
            custom_rate_provider=self.RATES,
            tax_year=2024,
        )

    def test_a_marks_basis_is_what_the_later_sale_costs(self):
        rgls = [r for r in self._run().realized_gains_losses
                if r.quantity_realized == Decimal("100")]
        assert len(rgls) == 1
        assert rgls[0].total_cost_basis_eur == Decimal("1400")
        assert rgls[0].gross_gain_loss_eur == Decimal("2100")


class TestTheCheckpointMarkRegistry:
    """A mark is stored per account, and `person_mark` is the derived view.

    Asserted at the seam: this pins the storage shape directly -- each account's
    row survives and `person_mark` sums them -- independently of the engine, which
    now reconciles each account's ledger against its own mark row
    (`mark_positions[year][(account, asset)]`).
    """
    ISIN = "US000000PS06"

    def _marks(self, tmp_path, rows):
        classifier = AssetClassifier(cache_file_path=str(tmp_path / "classification.json"))
        orchestrator = ParsingOrchestrator(
            asset_resolver=AssetResolver(asset_classifier=classifier),
            asset_classifier=classifier, interactive_classification=False)
        path = tmp_path / "mark.csv"
        write_csv(str(path), POSITIONS_COLUMNS, rows)
        orchestrator.raw_positions_marks = {2021: parse_positions_csv(str(path))}
        orchestrator.process_positions()
        return orchestrator.mark_positions[2021]

    def test_each_account_keeps_its_own_row(self, tmp_path):
        marks = self._marks(tmp_path, [
            position_row(A, self.ISIN, "60", "600", price="10"),
            position_row(B, self.ISIN, "40", "800", price="20"),
        ])
        asset_id = next(aid for (_a, aid) in marks)

        assert marks[(A, asset_id)].quantity == Decimal("60")
        assert marks[(A, asset_id)].cost_basis_amount == Decimal("600")
        assert marks[(B, asset_id)].quantity == Decimal("40")
        assert marks[(B, asset_id)].cost_basis_amount == Decimal("800")

    def test_the_person_s_mark_adds_the_quantity_and_the_basis_together(self, tmp_path):
        """Both columns or neither.

        A quantity added up over the rows and a cost basis taken from one of them
        imply a per-unit cost that belongs to no holding anybody had -- and that
        is the figure a disagreeing reconstruction is replaced by.
        """
        marks = self._marks(tmp_path, [
            position_row(A, self.ISIN, "60", "600", price="10"),
            position_row(B, self.ISIN, "40", "800", price="20"),
        ])
        asset_id = next(aid for (_a, aid) in marks)

        person = person_mark(marks, asset_id)
        assert person.quantity == Decimal("100")
        assert person.cost_basis_amount == Decimal("1400")
        assert person.cost_basis_currency == "EUR"

    def test_two_rows_for_one_account_are_one_holding(self, tmp_path):
        """A repeat of the same (account, asset) accumulates rather than replacing.

        Two rows for one instrument in one account are two parts of one holding,
        and the last of them is not the holding.
        """
        marks = self._marks(tmp_path, [
            position_row(A, self.ISIN, "60", "600", price="10"),
            position_row(A, self.ISIN, "40", "800", price="20"),
        ])
        asset_id = next(aid for (_a, aid) in marks)

        assert list(marks) == [(A, asset_id)]
        assert marks[(A, asset_id)].quantity == Decimal("100")
        assert marks[(A, asset_id)].cost_basis_amount == Decimal("1400")

    def test_a_wholly_blank_cost_basis_stays_blank(self, tmp_path):
        """`None` is "the broker left the column blank", not zero.

        A basis of zero declares the whole proceeds as gain. Kept at `None`, the
        mark reaches the guard that refuses a holding reported with no basis.
        """
        marks = self._marks(tmp_path, [
            position_row(A, self.ISIN, "60", None, price="10"),
            position_row(B, self.ISIN, "40", None, price="20"),
        ])
        asset_id = next(aid for (_a, aid) in marks)

        assert person_mark(marks, asset_id).cost_basis_amount is None

    def test_an_unreported_asset_has_no_person_level_mark(self, tmp_path):
        marks = self._marks(tmp_path, [position_row(A, self.ISIN, "60", "600", price="10")])
        assert person_mark(marks, uuid.uuid4()) is None

    def test_two_currencies_for_one_instrument_are_refused(self, tmp_path):
        """Same verdict as for the opening and closing snapshots, same reason.

        `person_mark` adds the cost bases across accounts, so two currencies
        would be added together and the reconstruction graded against a figure
        in neither.
        """
        with pytest.raises(DataIntegrityError) as excinfo:
            self._marks(tmp_path, [
                position_row(A, self.ISIN, "60", "600", price="10", currency="USD"),
                position_row(B, self.ISIN, "40", "800", price="20", currency="CAD"),
            ])
        assert "USD" in str(excinfo.value) and "CAD" in str(excinfo.value)

    def test_two_currencies_within_one_account_are_refused(self, tmp_path):
        """The same, where the two rows are one account's.

        Caught while accumulating rather than by the pass over the finished
        registry, because here the disagreeing row can still be named.
        """
        with pytest.raises(DataIntegrityError) as excinfo:
            self._marks(tmp_path, [
                position_row(A, self.ISIN, "60", "600", price="10", currency="USD"),
                position_row(A, self.ISIN, "40", "800", price="20", currency="CAD"),
            ])
        assert "USD" in str(excinfo.value) and "CAD" in str(excinfo.value)


class TestTwoCurrenciesForOneInstrumentAreRefused:
    """Amounts in two currencies cannot be added, so the run stops.

    A currency belongs to the instrument, not to the account holding it, so this
    does not happen -- but the total it would otherwise produce is a number in no
    currency at all, and no consumer downstream could tell it from a real one.

    Driven at the parser seam rather than through the pipeline: the refusal is a
    parsing verdict, and the pipeline harness turns every non-gap exception into
    a harness failure.
    """
    ISIN = "US000000PS04"

    def test_the_run_stops_naming_both_currencies(self, tmp_path):
        classifier = AssetClassifier(cache_file_path=str(tmp_path / "classification.json"))
        orchestrator = ParsingOrchestrator(
            asset_resolver=AssetResolver(asset_classifier=classifier),
            asset_classifier=classifier, interactive_classification=False)

        path = tmp_path / "positions.csv"
        write_csv(str(path), POSITIONS_COLUMNS, [
            position_row(A, self.ISIN, "100", "1000", price="10", currency="USD"),
            position_row(B, self.ISIN, "50", "500", price="10", currency="CAD"),
        ])
        orchestrator.raw_positions_start = parse_positions_csv(str(path))

        with pytest.raises(DataIntegrityError) as excinfo:
            orchestrator.process_positions()
        assert "USD" in str(excinfo.value) and "CAD" in str(excinfo.value)


class TestTheRegistryItself:
    """Two properties of the per-(account, asset) records that no scenario reaches.

    Both were found by mutation while probing the change that introduced them: the
    engine's own output is identical with either broken, so a scenario test cannot see
    them and the contract has to be asserted directly.
    """

    ISIN = "US000000PS05"

    @staticmethod
    def _orchestrator(tmp_path):
        classifier = AssetClassifier(cache_file_path=str(tmp_path / "classification.json"))
        return ParsingOrchestrator(
            asset_resolver=AssetResolver(asset_classifier=classifier),
            asset_classifier=classifier, interactive_classification=False)

    def _read(self, tmp_path, rows):
        orchestrator = self._orchestrator(tmp_path)
        path = tmp_path / "positions.csv"
        write_csv(str(path), POSITIONS_COLUMNS, rows)
        orchestrator.raw_positions_start = parse_positions_csv(str(path))
        orchestrator.process_positions()
        return orchestrator

    def test_two_rows_for_one_account_are_one_holding(self, tmp_path):
        """A repeat of the same (account, asset) accumulates rather than overwriting.

        The checkpoint marks have always read a repeated row this way -- two rows for one
        instrument in one account are two parts of one holding, and the last of them is
        not the holding. The opening and closing snapshots kept the last row until the
        per-account records replaced them.

        No export in `data_import/` repeats an (account, instrument) pair, so nothing
        downstream can observe this and no scenario can be built that does.
        """
        orchestrator = self._read(tmp_path, [
            position_row(A, self.ISIN, "100", "1000", price="10"),
            position_row(A, self.ISIN, "50", "500", price="10"),
        ])
        [(_account, snapshot)] = list(orchestrator.soy_positions.items())
        assert snapshot.quantity == Decimal("150")
        assert snapshot.cost_basis_amount == Decimal("1500")
        assert snapshot.position_value == Decimal("1500")   # 100 x 10 + 50 x 10

    def test_the_preceding_years_snapshots_are_kept_per_account_too(self, tmp_path):
        """The Vorabpauschale's own three snapshots are recorded the same way.

        Two of them have a live consumer whose answer depends on the person's total:
        the closing count, tested `> 0` in `fund_prices.py` and
        `vorabpauschale_declarations.py` to decide whether a fund was held at all, and
        the opening count, which is a **magnitude** in the § 18 Abs. 2 path --
        `undated_units > held_before_the_year` decides whether a Vorabpauschale is
        computed or refused for units the reconstruction could not date. Reading one
        account's row understates the threshold and refuses a figure that is due.

        Asserted at the seam because the figure consequence needs an undated tranche in
        two accounts, and the `> 0` one needs a closing row of zero -- which is 0 of 88
        rows in the exports this engine is run against.
        """
        orchestrator = self._orchestrator(tmp_path)
        path = tmp_path / "prior.csv"
        write_csv(str(path), POSITIONS_COLUMNS, [
            position_row(A, self.ISIN, "100", "1000", price="10"),
            position_row(B, self.ISIN, "40", "400", price="10"),
        ])
        rows = parse_positions_csv(str(path))
        orchestrator.raw_positions_prior_start = rows
        orchestrator.raw_positions_prior_end = rows
        orchestrator.raw_positions_prior_opening = rows
        orchestrator.process_positions()

        [asset] = list(orchestrator.asset_resolver.assets_by_internal_id.values())
        asset_id = asset.internal_asset_id
        for registry in (orchestrator.prior_soy_positions,
                         orchestrator.prior_eoy_positions,
                         orchestrator.prior_opening_positions):
            assert registry[(A, asset_id)].quantity == Decimal("100")
            assert registry[(B, asset_id)].quantity == Decimal("40")
            assert person_snapshot(registry, asset_id).quantity == Decimal("140")
            assert person_snapshot(registry, asset_id).position_value == Decimal("1400")

    def test_two_currencies_for_one_instrument_are_refused_in_the_prior_year_too(
            self, tmp_path):
        """The preceding year's registries take the same verdict as the tax year's.

        `person_snapshot` adds their position values across accounts, and the
        Vorabpauschale reads the price they are quoted in.
        """
        orchestrator = self._orchestrator(tmp_path)
        path = tmp_path / "prior.csv"
        write_csv(str(path), POSITIONS_COLUMNS, [
            position_row(A, self.ISIN, "100", "1000", price="10", currency="USD"),
            position_row(B, self.ISIN, "40", "400", price="10", currency="CAD"),
        ])
        orchestrator.raw_positions_prior_end = parse_positions_csv(str(path))

        with pytest.raises(DataIntegrityError) as excinfo:
            orchestrator.process_positions()
        assert "USD" in str(excinfo.value) and "CAD" in str(excinfo.value)

    def test_a_repeat_row_within_one_account_keeps_the_stichtag(self, tmp_path):
        """The day a price was set is a property of the file, not of the row.

        Two rows for one instrument in one account are accumulated into one
        record, and the Stichtag has to survive that -- Rz. 18.6 converts the
        Vorabpauschale price at the ECB rate of its own day ([GT-INVSTG-018]),
        and a record that lost it is converted at a day derived from the year.
        """
        orchestrator = self._orchestrator(tmp_path)
        path = tmp_path / "prior.csv"
        write_csv(str(path), POSITIONS_COLUMNS, [
            position_row(A, self.ISIN, "60", "600", price="10"),
            position_row(A, self.ISIN, "40", "400", price="10"),
        ])
        orchestrator.raw_positions_prior_start = parse_positions_csv(str(path))
        orchestrator.process_positions(tax_year=2024)   # Vorabpauschale year 2023

        [(_key, snap)] = list(orchestrator.prior_soy_positions.items())
        assert snap.quantity == Decimal("100")
        assert snap.mark_price_date == date(2023, 1, 3)

    def test_two_listings_of_one_instrument_leave_no_per_unit_price(self, tmp_path):
        """One ISIN on two exchanges, one account, one currency.

        The broker reports two contracts; the resolver keys on ISIN, so they are one
        instrument. The units and the value add -- one ISIN is one holding for FIFO --
        but the two market prices do not, and neither is the other's. Keeping whichever
        row came last would put an arbitrary venue's price on the record, and nothing
        downstream would notice: the end-of-year check compares quantities.

        The one figure a snapshot price reaches is the Vorabpauschale, and § 18 Abs. 1
        wants a Ruecknahmepreis -- one number the fund sets, which no average of two
        venues produces. So an ambiguous price is recorded as no price, and the run
        goes and fetches one or stops naming the fund.
        """
        orchestrator = self._read(tmp_path, [
            position_row(A, self.ISIN, "100", "1000", price="10.00",
                         symbol="DUAL", conid="111"),
            position_row(A, self.ISIN, "50", "520", price="10.40",
                         symbol="DUALd", conid="222"),
        ])
        [(_key, snap)] = list(orchestrator.soy_positions.items())

        assert snap.quantity == Decimal("150")
        assert snap.position_value == Decimal("1520")
        assert snap.mark_price is None, (
            "two market prices for one instrument are not a per-unit price for the "
            "holding, and 10.40 is only the row that came last"
        )

    def test_rows_agreeing_on_a_price_keep_it(self, tmp_path):
        """The other half of the same rule, so the drop cannot be a blanket one."""
        orchestrator = self._read(tmp_path, [
            position_row(A, self.ISIN, "100", "1000", price="10.00",
                         symbol="DUAL", conid="111"),
            position_row(A, self.ISIN, "50", "500", price="10.00",
                         symbol="DUALd", conid="222"),
        ])
        [(_key, snap)] = list(orchestrator.soy_positions.items())

        assert snap.quantity == Decimal("150")
        assert snap.mark_price == Decimal("10.00")

    def test_a_price_dropped_once_stays_dropped(self, tmp_path):
        """A third row agreeing with the first does not restore what two disagreed on.

        The record cannot distinguish "no price yet" from "the rows disagreed", so the
        rule has to be one-way: once dropped, dropped. Otherwise the price a later row
        happens to carry becomes the holding's, which is the last-row reading again.
        """
        orchestrator = self._read(tmp_path, [
            position_row(A, self.ISIN, "100", "1000", price="10.00",
                         symbol="DUAL", conid="111"),
            position_row(A, self.ISIN, "50", "520", price="10.40",
                         symbol="DUALd", conid="222"),
            position_row(A, self.ISIN, "20", "200", price="10.00",
                         symbol="DUALp", conid="333"),
        ])
        [(_key, snap)] = list(orchestrator.soy_positions.items())

        assert snap.quantity == Decimal("170")
        assert snap.mark_price is None

    def test_a_blank_row_within_one_account_keeps_the_reported_price(self, tmp_path):
        """Same rule as across accounts: a blank says nothing, so it takes nothing away."""
        orchestrator = self._read(tmp_path, [
            position_row(A, self.ISIN, "100", "1000", price="10.00",
                         symbol="DUAL", conid="111"),
            position_row(A, self.ISIN, "50", "500", price=None, value="500",
                         symbol="DUALd", conid="222"),
        ])
        [(_key, snap)] = list(orchestrator.soy_positions.items())

        assert snap.quantity == Decimal("150")
        assert snap.mark_price == Decimal("10.00")

    def test_the_same_instrument_priced_differently_in_two_accounts(self, tmp_path):
        """Across accounts the rule is the same, and `person_snapshot` applies it."""
        orchestrator = self._read(tmp_path, [
            position_row(A, self.ISIN, "100", "1000", price="10.00"),
            position_row(B, self.ISIN, "50", "520", price="10.40"),
        ])
        asset_id = next(aid for (_a, aid) in orchestrator.soy_positions)
        person = person_snapshot(orchestrator.soy_positions, asset_id)

        assert person.quantity == Decimal("150")
        assert person.mark_price is None

    def test_a_blank_price_is_an_omission_and_not_a_disagreement(self, tmp_path):
        """A row that reports no price says nothing about the price.

        Dropping the one the other row does report would send a fund to the
        substituted price -- a day too early -- over a blank the broker simply left.
        """
        orchestrator = self._read(tmp_path, [
            position_row(A, self.ISIN, "100", "1000", price="10.00"),
            position_row(B, self.ISIN, "50", "500", price=None, value="500"),
        ])
        asset_id = next(aid for (_a, aid) in orchestrator.soy_positions)

        assert person_snapshot(orchestrator.soy_positions, asset_id).mark_price \
            == Decimal("10.00")

    def test_the_accounts_come_back_in_a_fixed_order(self, tmp_path):
        """`snapshots_for_asset` sorts by account rather than returning the order the
        rows arrived in.

        `person_snapshot` sums the amounts, which no order changes, but it takes the
        first non-empty currency and mark price -- and every other consumer of the view
        inherits whatever order it is given. Insertion order is the order the export
        happened to list the accounts in, which is input a figure must not depend on.

        Asserted here because it is invisible everywhere else: reversing the sort, or
        removing it, leaves the whole suite green and every declared figure unchanged.
        """
        orchestrator = self._read(tmp_path, [
            position_row("U30000003", self.ISIN, "10", "100", price="10"),
            position_row("U10000001", self.ISIN, "20", "200", price="10"),
            position_row("U20000002", self.ISIN, "30", "300", price="10"),
        ])
        asset_id = next(aid for (_a, aid) in orchestrator.soy_positions)
        accounts = [account for account, _snap
                    in snapshots_for_asset(orchestrator.soy_positions, asset_id)]
        assert accounts == ["U10000001", "U20000002", "U30000003"]



class TestTheAssetPositionsDiagnostic:
    """The `--group-by-type` position listing, which no other test reaches.

    It moved from reading fields on `Asset` to reading the per-(account, asset)
    registries, and the claim attached to that move is that it prints exactly what it
    printed before. Nothing measured it: three separate mutations of the formatting --
    every opening reported as N/A, the closing value printed where the price goes, the
    registries handed in empty -- left the whole suite green, and a real-data run cannot
    settle it either because the run aborts before the report.

    So the rendered line is asserted here, in full.
    """

    ISIN = "US000000PS07"

    def _asset(self):
        return Stock(description="Probe Co", currency="EUR",
                     ibkr_isin=self.ISIN, ibkr_symbol="PRB")

    def _render(self, asset, soy, eoy, capsys):
        classifier = AssetClassifier(cache_file_path="/dev/null")
        resolver = AssetResolver(asset_classifier=classifier)
        resolver.assets_by_internal_id[asset.internal_asset_id] = asset
        print_asset_positions_diagnostic(resolver, soy, eoy)
        return [line for line in capsys.readouterr().out.splitlines()
                if "Probe Co" in line]

    def test_the_line_is_the_person_s_holding_in_the_format_it_has_always_had(self, capsys):
        """Both accounts on both sides, so every column the line prints is the person's:
        the quantities and the values add, and the mark price -- a property of the
        instrument, common to every account -- is taken."""
        asset = self._asset()
        key = ("U10000001", asset.internal_asset_id)
        other = ("U20000002", asset.internal_asset_id)
        [line] = self._render(
            asset,
            {key: PositionSnapshot(Decimal("100"), Decimal("1000"), "EUR",
                                   Decimal("1200"), Decimal("12"), "EUR"),
             other: PositionSnapshot(Decimal("50"), Decimal("500"), "EUR",
                                     Decimal("600"), Decimal("12"), "EUR")},
            {key: PositionSnapshot(Decimal("120"), None, "EUR",
                                   Decimal("1560"), Decimal("13"), "EUR"),
             other: PositionSnapshot(Decimal("50"), None, "EUR",
                                     Decimal("650"), Decimal("13"), "EUR")},
            capsys)
        assert line == (
            "  Probe Co                                           | "
            "Cat: STOCK                | "
            "SOY: Qty: 150.00000000, Cost: 1500.00 EUR               | "
            "EOY: Qty: 170.00000000, MarkPrice: 13.000000 EUR, Value: 2210.00")

    def test_an_unreported_snapshot_prints_N_A_and_a_reported_one_does_not(self, capsys):
        """The distinction the format has always drawn, and the one an empty registry
        would erase in both directions."""
        asset = self._asset()
        [line] = self._render(
            asset, {}, {("U10000001", asset.internal_asset_id):
                        PositionSnapshot(Decimal("0"), None, "EUR", Decimal("0"),
                                         Decimal("13"), "EUR")}, capsys)
        assert "SOY: N/A" in line
        assert "EOY: Qty: 0E-8," in line   # Decimal keeps the exponent; unchanged by the move

    def test_main_hands_the_diagnostic_the_registries_and_not_empty_ones(self):
        """The end of the channel, which the suite cannot otherwise reach.

        `--group-by-type` is a CLI path no test drives, so replacing the two arguments
        at the call site with empty dicts leaves every test green and every position
        prints N/A. Asserted on the source, which is what
        `test_vorabpauschale_price_and_units.py` already does for the same class of
        wiring.
        """
        import inspect

        from src.main import main_application

        source = inspect.getsource(main_application)
        assert "print_asset_positions_diagnostic(asset_resolver," in source
        assert "processing_results.soy_positions" in source
        assert "processing_results.eoy_positions" in source


class TestTheAbs2ThresholdIsThePersonsHolding:
    """Units the reconstruction could not date, weighed against what was held.

    § 18 Abs. 2 asks whether a tranche was acquired *during* the Vorabpauschale
    year. Where the replay could not place a lot in time, the engine answers from
    the report instead: units the broker already showed at the close of the year
    before were demonstrably acquired before this year began, so no reduction
    applies to them. Above that count the question is unanswerable and the fund
    is refused rather than computed from an invented date.

    That count is the person's, summed over their accounts ([GT-ESTG20-061]).
    Read from one account's row it is too small, and a Vorabpauschale that is
    due is refused -- deemed income missing from KAP-INV Zeilen 9-13.
    """
    ISIN = "IE00PERSVP01"

    def _run(self, opening_rows):
        from src.engine.calculation_engine import (
            FundUnitTranche, _calculate_vorabpauschale)
        from decimal import Context
        from src.domain.enums import InvestmentFundType
        from src.domain.assets import InvestmentFund
        from tests.support.prior_year_snapshots import snapshot_row
        import src.config as config

        fund = InvestmentFund(fund_type=InvestmentFundType.AKTIENFONDS,
                              description="Two Account Fund", currency="EUR",
                              ibkr_isin=self.ISIN, ibkr_symbol="TAF")
        resolver = MagicMock()
        resolver.assets_by_internal_id = {fund.internal_asset_id: fund}
        resolver.get_asset_by_id.return_value = fund

        prior_opening = {}
        for account, quantity in opening_rows:
            prior_opening.update(snapshot_row(
                fund.internal_asset_id, quantity=Decimal(quantity), account=account))

        converter = MagicMock()
        converter.convert_to_eur.side_effect = lambda amount, currency, dt: amount
        ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION,
                      rounding=config.DECIMAL_ROUNDING_MODE)
        # One lot the replay could not date, for the whole holding.
        lots = {fund.internal_asset_id: [FundUnitTranche(
            quantity=Decimal("100"), acquisition_date=date(2023, 12, 31),
            acquisition_date_is_known=False)]}

        return _calculate_vorabpauschale(
            asset_resolver=resolver,
            distributions_by_asset={},
            currency_converter=converter,
            vorabpauschale_year=2024,
            opening_lots_by_asset=lots,
            prior_soy_positions=snapshot_row(
                fund.internal_asset_id, mark_price=Decimal("100"),
                mark_price_currency="EUR", mark_price_date=date(2024, 1, 2)),
            prior_eoy_positions=snapshot_row(
                fund.internal_asset_id, quantity=Decimal("100"),
                mark_price=Decimal("110"), mark_price_currency="EUR",
                mark_price_date=date(2024, 12, 30)),
            prior_opening_positions=prior_opening,
            ctx=ctx,
            data_gap_collector=None,
        )

    def test_the_units_of_both_accounts_answer_for_the_undated_lot(self):
        results = self._run([(A, "60"), (B, "40")])
        assert len(results) == 1, (
            "100 undated units were all held at the close of the year before, "
            "across two accounts, so 18 Abs. 2 does not reduce them")
        assert results[0].gross_vorabpauschale_eur == Decimal("160.30")

    def test_one_accounts_row_is_not_enough_and_the_fund_is_refused(self):
        """The other reading, stated so the difference is visible."""
        results = self._run([(A, "60")])
        assert results == []


class TestTheEndsOfThePriorYearChannel:
    """The three preceding-year registries have to reach the code that reads them.

    Every other test in this file and in the Vorabpauschale suites hands them to
    the engine directly, so all of them survive deleting a call site -- the blind
    spot CLAUDE.md names for a newly added channel, and the one PR-A's own review
    already found once, in `main.py`.
    """

    def test_the_pipeline_hands_the_engine_all_three(self):
        import inspect

        from src.pipeline_runner import run_core_processing_pipeline

        source = inspect.getsource(run_core_processing_pipeline)
        for name in ("prior_soy_positions=orchestrator.prior_soy_positions",
                     "prior_eoy_positions=orchestrator.prior_eoy_positions",
                     "prior_opening_positions=orchestrator.prior_opening_positions"):
            assert name in source, (
                f"{name} never reaches run_main_calculations; the Vorabpauschale would "
                "read an empty registry and drop every fund without a word")

    def test_the_pipeline_hands_the_price_resolver_the_registries(self):
        import inspect

        from src.pipeline_runner import run_core_processing_pipeline

        source = inspect.getsource(run_core_processing_pipeline)
        assert "prior_soy_positions=orchestrator.prior_soy_positions" in source
        assert "prior_eoy_positions=orchestrator.prior_eoy_positions" in source

    def test_main_hands_the_declaration_commit_the_closing_registry(self):
        """`--commit-vorabpauschale-declaration` is a CLI path no test drives.

        Which funds get an entry is the person's holding at the close of the
        Vorabpauschale year; handed an empty registry, every fund that owed
        nothing would be left off the record, and a later run could not tell
        "declared nothing" from "never declared".
        """
        import inspect

        from src.main import _commit_vorabpauschale_declaration

        source = inspect.getsource(_commit_vorabpauschale_declaration)
        assert "prior_eoy_positions=processing_results.prior_eoy_positions" in source

        from src.pipeline_runner import run_core_processing_pipeline

        pipeline = inspect.getsource(run_core_processing_pipeline)
        assert "prior_eoy_positions=orchestrator.prior_eoy_positions,\n    )" in pipeline, (
            "the closing registry must reach ProcessingOutput, or the commit above "
            "is handed an empty one"
        )


class TestAFundHeldInTwoAccounts(FifoTestCaseBase):
    """The preceding year's snapshot is read the same way, and it decides a form line.

    The Vorabpauschale declared in VZ Y is the one computed for calendar Y-1
    (§ 18 Abs. 3 InvStG), and § 18 Abs. 1 multiplies a per-unit Basisertrag by the units
    held at the close of that year. Those unit counts come from the preceding year's
    snapshots, which arrive one row per account exactly as the tax year's do -- so the
    same last-row-wins reading understated the units and, with them, KAP-INV Zeilen 9-13.

    The unit counts are the only thing that differs between the two readings here: the
    prices are per unit and identical on both rows, so the figure moves in proportion.

    Latent on the export this engine is run against -- no instrument appears under two
    accounts in any position file -- which is why it needs a scenario at all.
    """
    ISIN = "IE00TEST9001"
    CONID = "CON9001"
    VP_TAX_YEAR = 2024   # declares the Vorabpauschale computed for calendar 2023

    def _position_row(self, account, quantity, mark_price, position_value, cost="10000"):
        return [account, "EUR", "STK", "", "TFND", "TFND ETF INDEX",
                self.ISIN, quantity, position_value, mark_price, cost,
                "", self.CONID, "", "1"]

    def _buy(self, account, date, quantity, price, tx):
        return [account, "EUR", "STK", "", "TFND", "TFND ETF INDEX",
                self.ISIN, "", "", "", date, quantity, price, "0", "EUR",
                "BUY", tx, "", "", self.CONID, "", "1", "O"]

    def _run(self):
        return self._run_pipeline(
            trades_data=[
                self._buy(A, "2022-03-15", "100", "90", "TXA"),
                self._buy(B, "2022-03-15", "40", "90", "TXB"),
            ],
            # Calendar 2023, which the VZ 2024 return declares: 100 units in A and 40 in B.
            positions_prior_start_data=[
                self._position_row(A, "100", "100", "10000"),
                self._position_row(B, "40", "100", "4000"),
            ],
            positions_prior_end_data=[
                self._position_row(A, "100", "110", "11000"),
                self._position_row(B, "40", "110", "4400"),
            ],
            positions_start_data=[
                self._position_row(A, "100", "110", "11000"),
                self._position_row(B, "40", "110", "4400"),
            ],
            positions_end_data=[
                self._position_row(A, "100", "110", "11000"),
                self._position_row(B, "40", "110", "4400"),
            ],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=self.VP_TAX_YEAR,
        )

    def test_the_vorabpauschale_counts_the_units_of_both_accounts(self):
        """140 units at 100.00 open the year, not the 40 of whichever row the file ends
        with. Basiszins 2023 is 2.55 %, so the per-unit Basisertrag is
        100.00 x 0.0255 x 0.7 = 1.785, under the Satz 3 cap of 10.00 (110.00 - 100.00),
        and 140 units give 249.90. Reading one account's row gives 71.40."""
        items = self._run().vorabpauschale_items
        assert len(items) == 1
        item = items[0]
        assert item.fund_value_start_year_eur == Decimal("14000.00")
        assert item.gross_vorabpauschale_eur == Decimal("249.90")

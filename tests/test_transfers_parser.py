"""
Reading the Transfers export, and collapsing it into one event per move.

legal_basis: the moves this file records are not disposals -- [GT-ESTG20-014], a transfer
between the taxpayer's own depots has no change of beneficial owner and no
consideration, so acquisition date and cost carry over. What the engine then DOES with a
move is tested in `test_internal_transfers.py`; this file covers getting the rows in and
turning them into moves.

The export's shape is described in `src/parsers/raw_models.py::RawTransferRecord` and was
measured against the real export before either was written; the counts are in
`VALIDATION_REPORT.md`, not here. Every identifier and amount below is invented.
"""
from decimal import Decimal

import pytest

from src.domain.exceptions import DataIntegrityError
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.parsers.domain_event_factory import DomainEventFactory
from src.parsers.transfers_parser import parse_transfers_csv
from tests.support.multi_account import write_csv, transfer_row, TRANSFERS_COLUMNS

A, B = "U10000001", "U10000002"
ISIN = "US000000TR01"


def _write(tmp_path, rows, columns=TRANSFERS_COLUMNS):
    p = tmp_path / "transfers.csv"
    write_csv(str(p), columns, rows)
    return str(p)


def _factory(tmp_path):
    classifier = AssetClassifier(cache_file_path=str(tmp_path / "classifications.json"))
    return DomainEventFactory(asset_resolver=AssetResolver(asset_classifier=classifier))


def _moves(tmp_path, rows):
    return _factory(tmp_path).create_events_from_transfers(
        parse_transfers_csv(_write(tmp_path, rows)))


class TestReadingTheFile:

    def test_both_sides_of_a_move_survive_parsing(self, tmp_path):
        """The parser keeps every row. Deciding that two rows are one move is the
        factory's job, and a parser that collapsed them would hide the rows a later
        question might need."""
        recs = parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            transfer_row(B, A, "IN", "20230601", isin=ISIN, quantity="100", tx_id="X2"),
        ]))
        assert len(recs) == 2
        assert [r.client_account_id for r in recs] == [A, B]
        assert [r.transfer_account for r in recs] == [B, A]
        assert [r.direction for r in recs] == ["OUT", "IN"]
        assert [r.transaction_id for r in recs] == ["X1", "X2"]

    def test_the_direction_and_the_sign_are_read_separately(self, tmp_path):
        """The sign of `Quantity` does not track `Direction` in the real export, so
        the two must arrive as two separate facts. A parser that normalised the sign
        against the direction would destroy the evidence that they disagree."""
        recs = parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="100", tx_id="X1"),
            transfer_row(B, A, "IN", "20230601", isin=ISIN, quantity="-100", tx_id="X2"),
        ]))
        assert recs[0].direction == "OUT" and recs[0].quantity == Decimal("100")
        assert recs[1].direction == "IN" and recs[1].quantity == Decimal("-100")

    def test_a_lot_detail_row_is_marked_by_its_level_of_detail(self, tmp_path):
        """`LevelOfDetail` discriminates a lot-detail row from a summary, replacing the
        old Code/TransactionID heuristic. A LOT row carries the acquisition day
        (`OpenDateTime`) and its basis, and no transaction id."""
        recs = parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-60",
                         level_of_detail="LOT", open_date_time="20230115",
                         cost_basis="1800", code="ST"),
        ]))
        assert recs[0].level_of_detail == "LOT"
        assert not (recs[0].transaction_id or "").strip()
        assert recs[0].quantity == Decimal("-60")
        assert recs[0].open_date_time == "20230115"

    def test_a_cash_row_carries_no_instrument(self, tmp_path):
        """A CASH row has no ISIN and no Conid, and its `Multiplier` is blank. Blank
        must not raise -- it is the ordinary shape of these rows."""
        recs = parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", asset_class="CASH", currency="USD",
                         quantity="0", cash_transfer="-500", tx_id="X1", multiplier=""),
        ]))
        assert recs[0].asset_class == "CASH"
        assert not recs[0].isin
        assert recs[0].multiplier is None
        assert recs[0].currency_primary == "USD"

    def test_the_move_date_is_read(self, tmp_path):
        """The move is applied in chronological order, so the date has to survive."""
        recs = parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230615", isin=ISIN, quantity="-100", tx_id="X1"),
        ]))
        assert recs[0].date == "20230615"

    def test_an_empty_file_parses_to_nothing(self, tmp_path):
        """A person who has never moved a holding between their accounts exports an
        empty file. That is ordinary input, not an error."""
        assert parse_transfers_csv(_write(tmp_path, [])) == []

    def test_a_missing_column_is_rejected(self, tmp_path):
        """The export growing or losing a column must be loud. Nothing read this file
        until now, so no shape of it has been established that a silent tolerance
        could rest on."""
        with pytest.raises(ValueError):
            parse_transfers_csv(_write(tmp_path, [], columns=TRANSFERS_COLUMNS[:-1]))

    def test_a_blank_quantity_is_rejected(self, tmp_path):
        """Not defaulted to zero, which is what the other raw models do with an
        unparseable amount. Zero here is a move of nothing, so the holding would stay
        where it was while the broker reported it elsewhere."""
        with pytest.raises(ValueError):
            parse_transfers_csv(_write(tmp_path, [
                transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="", tx_id="X1"),
            ]))

    def test_a_repeated_header_never_becomes_data(self, tmp_path):
        """Appending a second account's export leaves that export's header row in the
        middle of the file. Both `_copy_file` and `_concatenate_csvs` strip it, so it
        never reaches the parser -- checked here because the parser is what would have
        to catch it if either ever stopped."""
        from src.data_preparation import _concatenate_csvs
        paths = []
        for year, rows in ((2022, []), (2023, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            transfer_row(B, A, "IN", "20230601", isin=ISIN, quantity="100", tx_id="X2"),
        ])):
            p = tmp_path / f"Transfers-{year}.csv"
            write_csv(str(p), TRANSFERS_COLUMNS, rows)
            paths.append(p)
        out = tmp_path / "concatenated.csv"
        _concatenate_csvs(paths, out)
        assert out.read_text(encoding="utf-8-sig").count("ClientAccountID") == 1
        recs = parse_transfers_csv(str(out))
        assert len(recs) == 2 and all(r.symbol != "Symbol" for r in recs)


class TestCollapsingRowsIntoMoves:
    """One move per move, however many rows the export spent on it."""

    def test_the_two_sides_collapse_into_one(self, tmp_path):
        moves = _moves(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            transfer_row(B, A, "IN", "20230601", isin=ISIN, quantity="100", tx_id="X2"),
        ])
        assert len(moves) == 1
        assert moves[0].account_id == A and moves[0].to_account_id == B
        assert moves[0].quantity == Decimal("100")
        assert moves[0].event_date == "2023-06-01"

    def test_either_side_alone_gives_the_same_move(self, tmp_path):
        """Each summary row names both accounts, so neither side is privileged."""
        out_only = _moves(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1")])
        in_only = _moves(tmp_path, [
            transfer_row(B, A, "IN", "20230601", isin=ISIN, quantity="100", tx_id="X2")])
        assert len(out_only) == len(in_only) == 1
        for moves in (out_only, in_only):
            assert (moves[0].account_id, moves[0].to_account_id) == (A, B)
            assert moves[0].quantity == Decimal("100")

    def test_the_lot_rows_become_the_moves_breakdown(self, tmp_path):
        """The lot rows beneath a summary are READ, not dropped: they say which
        acquisition days moved. The summary's total is one move; the lot rows are its
        per-day breakdown, and the run does not sum them into a second move.

        (Rewritten from `test_the_lot_detail_rows_are_dropped`, which asserted the old
        whole-position design dropped them. Reading them is what makes a partial move --
        of some acquisition days but not all -- supportable.)"""
        moves = _moves(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-60",
                         level_of_detail="LOT", open_date_time="20230115"),
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-40",
                         level_of_detail="LOT", open_date_time="20230220"),
        ])
        assert len(moves) == 1
        assert moves[0].quantity == Decimal("100")
        assert [(lot.acquisition_date, lot.quantity) for lot in moves[0].moved_lots] == [
            ("2023-01-15", Decimal("60")), ("2023-02-20", Decimal("40"))]

    def test_the_quantity_is_the_absolute_one(self, tmp_path):
        """Whichever side is negative, the move is of that many units. Which of the
        moved units are long and which short is read from the ledger, not from here."""
        moves = _moves(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-40", tx_id="X1"),
        ])
        assert moves[0].quantity == Decimal("40")

    def test_two_moves_of_one_instrument_on_different_days_stay_two(self, tmp_path):
        moves = _moves(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            transfer_row(A, B, "OUT", "20230715", isin=ISIN, quantity="-100", tx_id="X3"),
        ])
        assert len(moves) == 2
        assert sorted(m.event_date for m in moves) == ["2023-06-01", "2023-07-15"]

    def test_a_cash_row_produces_no_move(self, tmp_path):
        """Currency is held as one balance per person, so a move between two of that
        person's accounts changes nothing in it. Reading these rows is what
        per-account currency would need, and the engine does not do that yet."""
        assert _moves(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", asset_class="CASH", currency="USD",
                         quantity="0", cash_transfer="-500", tx_id="X1", multiplier=""),
            transfer_row(B, A, "IN", "20230601", asset_class="CASH", currency="USD",
                         quantity="0", cash_transfer="500", tx_id="X2", multiplier=""),
        ]) == []

    def test_the_event_carries_no_transaction_id(self, tmp_path):
        """The two sides carry different ids, so neither names the move -- and the id
        would additionally decide the intra-day order, because `get_event_sort_key`
        puts it ahead of the intra-day band."""
        moves = _moves(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            transfer_row(B, A, "IN", "20230601", isin=ISIN, quantity="100", tx_id="X2"),
        ])
        assert moves[0].ibkr_transaction_id is None


class TestWhatItRefusesToRead:
    """Each of these would otherwise become a move the law here does not cover."""

    def test_a_transfer_that_is_not_internal_stops_the_run(self, tmp_path):
        """[GT-ESTG20-014] settles the own-depot case and nothing else. A move to a
        third party or to another institution may well be a disposal, and no rule in
        `reference/` decides which -- so it is not relocated as if it stayed."""
        with pytest.raises(DataIntegrityError, match="INTERNAL"):
            _moves(tmp_path, [
                transfer_row(A, "EXTERNAL", "OUT", "20230601", isin=ISIN,
                             quantity="-100", tx_id="X1", transfer_type="ACATS"),
            ])

    def test_a_row_with_no_direction_stops_the_run(self, tmp_path):
        """The sign of `Quantity` does not carry the direction, so there is nothing
        else to read it from and guessing would send the units the wrong way."""
        with pytest.raises(DataIntegrityError, match="Direction"):
            _moves(tmp_path, [
                transfer_row(A, B, "", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            ])

    def test_a_row_naming_only_one_account_stops_the_run(self, tmp_path):
        with pytest.raises(DataIntegrityError, match="only one account"):
            _moves(tmp_path, [
                transfer_row(A, "", "OUT", "20230601", isin=ISIN, quantity="-100",
                             tx_id="X1"),
            ])

    def test_a_row_with_an_unreadable_date_stops_the_run(self, tmp_path):
        with pytest.raises(DataIntegrityError, match="Date"):
            _moves(tmp_path, [
                transfer_row(A, B, "OUT", "not-a-date", isin=ISIN, quantity="-100",
                             tx_id="X1"),
            ])

    def test_a_move_of_zero_units_stops_the_run(self, tmp_path):
        with pytest.raises(DataIntegrityError, match="move of nothing"):
            _moves(tmp_path, [
                transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="0",
                             tx_id="X1"),
            ])

    def test_every_bad_row_is_reported_together(self, tmp_path):
        """One run names the whole problem rather than the first row of it."""
        with pytest.raises(DataIntegrityError) as excinfo:
            _moves(tmp_path, [
                transfer_row(A, B, "", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
                transfer_row(A, B, "OUT", "20230602", isin=ISIN, quantity="0", tx_id="X2"),
            ])
        assert "2 transfer record(s)" in str(excinfo.value)


class TestAPartlyExportedWindowIsCountedAsSuch:
    """The other end of the channel that tells the reader whether the moves were read.

    `data_preparation` is where the years are known, and the engine's warning is where
    the reader is. Probed at both ends because a claim of completeness resting on a file
    path is exactly as wrong for a window with a hole as for a window with nothing in it
    — and the second is the case a review caught after the first was fixed.
    """

    def _prepare(self, tmp_path, monkeypatch, transfer_years, tax_year=2025):
        import src.data_preparation as dp

        imports = tmp_path / "data_import"
        imports.mkdir()
        monkeypatch.setattr(dp, "IMPORT_DIR", imports)
        monkeypatch.setattr(dp, "WORKING_DIR", tmp_path / "data")

        for prefix in ("Trades", "Cash_Transactions", "Corporate_Actions"):
            for year in (2023, 2024, 2025):
                write_csv(str(imports / f"{prefix}-{year}.csv"),
                          _columns_for(prefix), [])
        for year in (2024, 2025):
            for suffix in ("-EoY.csv", "-SoY.csv"):
                write_csv(str(imports / f"Positions-{year}{suffix}"),
                          _columns_for("Positions"), [])
        for year in transfer_years:
            write_csv(str(imports / f"Transfers-{year}.csv"), TRANSFERS_COLUMNS, [
                transfer_row(A, B, "OUT", f"{year}0601", isin=ISIN, quantity="-100",
                             tx_id=f"X{year}"),
            ])
        return dp.prepare_data_for_tax_year(tax_year)

    def test_a_complete_window_reports_nothing_missing(self, tmp_path, monkeypatch):
        result = self._prepare(tmp_path, monkeypatch, (2023, 2024, 2025))
        assert result["transfers"]
        assert result["transfers_missing_years"] == ""

    def test_a_window_that_stops_before_the_tax_year_names_the_gap(self, tmp_path, monkeypatch):
        """The shape a real import has when the newest year has not been exported. The
        path is still returned — the years that exist are worth reading — but nothing
        downstream may call the export complete."""
        result = self._prepare(tmp_path, monkeypatch, (2023, 2024))
        assert result["transfers"], "the years that do exist are still read"
        assert result["transfers_missing_years"] == "2025"

    def test_a_hole_in_the_middle_is_named_too(self, tmp_path, monkeypatch):
        result = self._prepare(tmp_path, monkeypatch, (2023, 2025))
        assert result["transfers_missing_years"] == "2024"

    def test_no_transfers_at_all_is_not_a_gap_but_an_absence(self, tmp_path, monkeypatch):
        """Reported through the empty path, not through a list of every year. A person
        who has never exported the report is a different case from one whose export
        stops early, and the warning distinguishes them."""
        result = self._prepare(tmp_path, monkeypatch, ())
        assert result["transfers"] == ""
        assert result["transfers_missing_years"] == ""


def _columns_for(prefix):
    from src.parsers import column_validator as cv
    return {"Trades": cv.TRADES_COLUMNS,
            "Cash_Transactions": cv.CASH_TRANSACTIONS_COLUMNS,
            "Corporate_Actions": cv.CORPORATE_ACTIONS_COLUMNS,
            "Positions": cv.POSITIONS_COLUMNS}[prefix]


class TestTheMoveTakesItsIntraDaySlot:
    """A move must land before that day's trades, so a sale of what just arrived has
    something to consume. Pinned rather than left to the sort key's shape."""

    def test_a_move_sorts_before_a_same_day_trade(self, tmp_path):
        from decimal import Decimal as D
        from src.domain.enums import FinancialEventType
        from src.domain.events import TradeEvent
        from src.utils.sorting_utils import get_event_sort_key

        factory = _factory(tmp_path)
        moves = factory.create_events_from_transfers(parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
        ])))
        resolver = factory.asset_resolver
        asset_id = moves[0].asset_internal_id
        sale = TradeEvent(asset_id, "2023-06-01", quantity=D("-100"),
                          price_foreign_currency=D("25"),
                          event_type=FinancialEventType.TRADE_SELL_LONG,
                          account_id=B, ibkr_transaction_id="A0000000",
                          local_currency="EUR")

        assert get_event_sort_key(moves[0], resolver) < get_event_sort_key(sale, resolver)

    def test_the_band_not_the_transaction_id_puts_a_move_before_trades(self, tmp_path):
        """The move sorts before that day's trades BY THE RULE, not by the accident of an
        empty transaction id. Give the move a transaction id that would drag it behind the
        sale under an id-first key; the lot-delivering precedence still puts it first.

        This is what makes the ordering explicit. Red two ways: without the
        InternalTransferEvent branch in `get_event_sort_key` (the move falls to the
        unknown band, outside the lot-delivering partition, and the large id then sorts it
        after the sale), and under the old `(transaction_id, intra_day_order, ...)` key
        (the id would decide directly). The factory never sets a transaction id on a move;
        this builds one that carries a large one to exercise the rule."""
        from decimal import Decimal as D
        from src.domain.enums import FinancialEventType
        from src.domain.events import TradeEvent, InternalTransferEvent
        from src.utils.sorting_utils import get_event_sort_key

        factory = _factory(tmp_path)
        moves = factory.create_events_from_transfers(parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
        ])))
        resolver = factory.asset_resolver
        asset_id = moves[0].asset_internal_id
        move_with_id = InternalTransferEvent(
            asset_id, "2023-06-01", to_account_id=B, quantity=D("100"),
            account_id=A, ibkr_transaction_id="9999999999")  # would sort after the sale
        sale = TradeEvent(asset_id, "2023-06-01", quantity=D("-100"),
                          price_foreign_currency=D("25"),
                          event_type=FinancialEventType.TRADE_SELL_LONG,
                          account_id=B, ibkr_transaction_id="1322551221",
                          local_currency="EUR")
        assert get_event_sort_key(move_with_id, resolver) < get_event_sort_key(sale, resolver)

    def test_two_moves_on_one_day_sort_without_blowing_up(self, tmp_path):
        """Two moves on one date carry no transaction id and share an intra-day band,
        so every element before the branch's own is equal and the comparison reaches
        them. An element that does not compare -- an `AssetCategory`, which is a plain
        Enum -- takes the whole run down with a TypeError at that point, before a
        single figure is computed.

        Found by a real-data run and not by the suite, which until this test had no
        scenario with two moves on one day.
        """
        from src.utils.sorting_utils import get_event_sort_key

        factory = _factory(tmp_path)
        moves = factory.create_events_from_transfers(parse_transfers_csv(_write(tmp_path, [
            transfer_row(A, B, "OUT", "20230601", isin=ISIN, quantity="-100", tx_id="X1"),
            transfer_row(A, B, "OUT", "20230601", isin="US000000TR09", quantity="-50",
                         tx_id="X3"),
        ])))
        assert len(moves) == 2
        keys = sorted(get_event_sort_key(m, factory.asset_resolver) for m in moves)
        assert keys[0] != keys[1], "two distinct moves must not collide on one key"

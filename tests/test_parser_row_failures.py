"""A row an export contains and a parser cannot read stops the run.

legal_basis: harness/integrity only — this pins no legal rule and no expected
figure depends on it. It pins CLAUDE.md's fail-fast rule at the parsing boundary:
"Do not swallow errors, default a missing value, or skip a row to keep a run
alive when the value is required for a correct figure."

Why these tests exist: all six parsers printed a row's `ValidationError` to
stdout and carried on with the rows that survived. Nothing compared a file's
row count against the parsed record count, so the loss was unobservable — the
orchestrator logs "Loaded N raw ... records", and N *is* the survivor count. The
same handlers swallowed two more things: `validate_csv_columns`' `ValueError`,
so a header drifting out of step with the Flex Query returned zero records and
raised nothing, and `FileNotFoundError`, returning an empty list for a file that
was not there.

The per-parser cases below are parametrized rather than written once because the
defect was six copies of one block: a fix applied to five of them would pass a
single-parser test.
"""
import csv
import io
from typing import Any, List, Sequence

import pytest

from src.domain.exceptions import DataIntegrityError
from src.parsers.cash_balance_parser import parse_cash_balance_csv
from src.parsers.cash_transactions_parser import parse_cash_transactions_csv
from src.parsers.column_validator import (
    CASH_BALANCE_COLUMNS,
    CASH_TRANSACTIONS_COLUMNS,
    CORPORATE_ACTIONS_COLUMNS,
    OPTIONS_EAE_COLUMNS,
    POSITIONS_COLUMNS,
    TRADES_COLUMNS,
)
from src.parsers.corporate_actions_parser import parse_corporate_actions_csv
from src.parsers.options_eae_parser import parse_options_eae_csv
from src.parsers.positions_parser import parse_positions_csv
from src.parsers.trades_parser import parse_trades_csv

ACCOUNT = "U10000001"


def _write(path, headers: Sequence[str], rows: List[dict]) -> str:
    """Write dict rows under the canonical header, BOM-prefixed and all-quoted."""
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(list(headers))
    for row in rows:
        w.writerow([row.get(h, "") for h in headers])
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(buf.getvalue())
    return str(path)


def _trade(tx_id="T1", **over):
    row = {"ClientAccountID": ACCOUNT, "CurrencyPrimary": "EUR", "AssetClass": "STK",
           "SubCategory": "COMMON", "Symbol": "AAA", "Description": "AAA security",
           "ISIN": "DE000000TEST", "TradeDate": "20250301", "Quantity": "10",
           "TradePrice": "12", "IBCommission": "0", "IBCommissionCurrency": "EUR",
           "Buy/Sell": "BUY", "TransactionID": tx_id, "Conid": "C1", "Multiplier": "1",
           "Open/CloseIndicator": "O"}
    row.update(over)
    return row


def _cash_txn(tx_id="X1", **over):
    row = {"ClientAccountID": ACCOUNT, "CurrencyPrimary": "EUR", "AssetClass": "STK",
           "Symbol": "AAA", "Description": "AAA dividend", "SettleDate": "20250301",
           "Amount": "3", "Type": "Dividends", "Conid": "C1", "ISIN": "DE000000TEST",
           "TransactionID": tx_id}
    row.update(over)
    return row


def _position(**over):
    row = {"ClientAccountID": ACCOUNT, "CurrencyPrimary": "EUR", "AssetClass": "STK",
           "SubCategory": "COMMON", "Symbol": "AAA", "Description": "AAA security",
           "ISIN": "DE000000TEST", "Quantity": "10", "PositionValue": "120",
           "MarkPrice": "12", "CostBasisMoney": "100", "Conid": "C1", "Multiplier": "1"}
    row.update(over)
    return row


def _corp_action(action_id="A1", **over):
    row = {"ClientAccountID": ACCOUNT, "Symbol": "AAA", "Description": "AAA split",
           "ISIN": "DE000000TEST", "Report Date": "20250301", "Code": "FS", "Type": "FS",
           "ActionID": action_id, "Conid": "C1", "CurrencyPrimary": "EUR",
           "Amount": "0", "Proceeds": "0", "Value": "0", "Quantity": "10"}
    row.update(over)
    return row


def _cash_balance(**over):
    row = {"ClientAccountID": ACCOUNT, "CurrencyPrimary": "EUR", "FromDate": "20250101",
           "ToDate": "20251231", "StartingCash": "5", "EndingCash": "7"}
    row.update(over)
    return row


def _options_eae(**over):
    row = {"ClientAccountID": ACCOUNT, "CurrencyPrimary": "EUR", "FXRateToBase": "1",
           "AssetClass": "OPT", "Symbol": "AAA 20250718 100 C",
           "Description": "AAA option", "Conid": "C1", "Multiplier": "100",
           "Strike": "100", "Expiry": "20250718", "Put/Call": "C", "Date": "20250718",
           "Transaction Type": "Assignment", "Quantity": "1", "Trade Price": "0",
           "Proceeds": "0", "Comm/Tax": "0", "Basis": "0", "RealizedPnl": "0"}
    row.update(over)
    return row


# (label, parser, columns, good-row builder, the column blanked to break a row)
PARSERS = [
    ("trades", parse_trades_csv, TRADES_COLUMNS, _trade, "Quantity"),
    ("cash_transactions", parse_cash_transactions_csv, CASH_TRANSACTIONS_COLUMNS,
     _cash_txn, "Amount"),
    ("positions", parse_positions_csv, POSITIONS_COLUMNS, _position, "Quantity"),
    ("corporate_actions", parse_corporate_actions_csv, CORPORATE_ACTIONS_COLUMNS,
     _corp_action, "Report Date"),
    # FromDate / Date rather than a Decimal column, for reasons particular to each
    # model and neither of them a defect: `RawCashBalanceRecord` reads a blank balance
    # as zero on purpose -- an empty cell in a cash report is zero cash, pinned by
    # `test_the_cash_balance_record_keeps_its_own_zero_default` -- and every required
    # column on `RawOptionsEAERecord` is a plain `str`, where a blank is a valid value.
    ("cash_balance", parse_cash_balance_csv, CASH_BALANCE_COLUMNS, _cash_balance,
     "FromDate"),
    ("options_eae", parse_options_eae_csv, OPTIONS_EAE_COLUMNS, _options_eae, "Date"),
]
IDS = [p[0] for p in PARSERS]


@pytest.mark.parametrize("label,parse,columns,good,break_column", PARSERS, ids=IDS)
def test_a_good_file_parses(tmp_path, label, parse, columns, good, break_column):
    path = _write(tmp_path / f"{label}.csv", columns, [good(), good()])
    assert len(parse(path)) == 2


@pytest.mark.parametrize("label,parse,columns,good,break_column", PARSERS, ids=IDS)
def test_one_unparseable_row_stops_the_run(tmp_path, label, parse, columns, good,
                                           break_column):
    """Before: printed to stdout, dropped, and the remaining rows declared."""
    path = _write(tmp_path / f"{label}.csv", columns,
                  [good(), good(**{break_column: ""}), good()])
    with pytest.raises(DataIntegrityError) as exc:
        parse(path)
    message = str(exc.value)
    assert message.startswith("1 row(s)")
    assert "line 3" in message           # the file line, header counted
    assert break_column in message       # which column, not just which row


@pytest.mark.parametrize("label,parse,columns,good,break_column", PARSERS, ids=IDS)
def test_every_bad_row_is_named_not_only_the_first(tmp_path, label, parse, columns,
                                                   good, break_column):
    """CLAUDE.md: check every case first and report them together."""
    path = _write(tmp_path / f"{label}.csv", columns,
                  [good(**{break_column: ""}), good(), good(**{break_column: ""})])
    with pytest.raises(DataIntegrityError) as exc:
        parse(path)
    message = str(exc.value)
    assert message.startswith("2 row(s)")
    assert "line 2" in message and "line 4" in message


@pytest.mark.parametrize("label,parse,columns,good,break_column", PARSERS, ids=IDS)
def test_a_header_out_of_step_with_the_flex_query_raises(tmp_path, label, parse,
                                                         columns, good, break_column):
    """Before: `validate_csv_columns` raised, the file-level `except Exception`
    caught it one frame later, and the parser returned an empty list."""
    renamed = tuple(("Renamed" if c == break_column else c) for c in columns)
    path = _write(tmp_path / f"{label}.csv", renamed, [good()])
    with pytest.raises(ValueError, match="column mismatch"):
        parse(path)


@pytest.mark.parametrize("label,parse,columns,good,break_column", PARSERS, ids=IDS)
def test_a_missing_file_raises_rather_than_reading_as_empty(tmp_path, label, parse,
                                                            columns, good, break_column):
    """Before: printed and returned []. `data_preparation.py` already raises for a
    missing required file, so this was a second, weaker layer that could only
    disagree with the first."""
    with pytest.raises(FileNotFoundError):
        parse(str(tmp_path / "absent.csv"))


def test_a_row_with_more_fields_than_the_header_is_reported_as_such(tmp_path):
    """csv.DictReader files the surplus under the None key, which reaches a model
    as a TypeError about keyword names — a message that says nothing about the CSV."""
    path = tmp_path / "trades.csv"
    good = _write(path, TRADES_COLUMNS, [_trade()])
    with open(path, "a", encoding="utf-8-sig", newline="") as fh:
        fh.write(",".join(['"x"'] * (len(TRADES_COLUMNS) + 3)) + "\n")
    with pytest.raises(DataIntegrityError, match="more fields than the header"):
        parse_trades_csv(good)


def test_the_failure_names_the_row_so_it_can_be_found_in_the_export(tmp_path):
    """A line number locates the row in the concatenated working copy; the
    TransactionID locates it in the export the user actually has."""
    path = _write(tmp_path / "trades.csv", TRADES_COLUMNS,
                  [_trade(tx_id="T1"), _trade(tx_id="T77", Quantity="")])
    with pytest.raises(DataIntegrityError) as exc:
        parse_trades_csv(path)
    assert "TransactionID=T77" in str(exc.value)


def test_a_programming_error_is_not_reported_as_a_bad_row(tmp_path, monkeypatch):
    """The old handler's second arm was a bare `except Exception` around the model
    constructor, so a defect in this repository was printed as though the broker
    had exported a bad row. Only ValidationError is caught now."""
    import src.parsers.csv_reader as reader

    class Exploding:
        def __init__(self, **kwargs):
            raise KeyboardInterrupt("stand-in for a defect, not a bad row")

    monkeypatch.setattr(reader, "validate_csv_columns", lambda *a, **k: None)
    path = _write(tmp_path / "trades.csv", TRADES_COLUMNS, [_trade()])
    with pytest.raises(KeyboardInterrupt):
        reader.parse_records(path, Exploding, TRADES_COLUMNS, "Trades")

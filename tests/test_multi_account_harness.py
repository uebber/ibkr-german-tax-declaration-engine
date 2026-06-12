"""
Self-test for the multi-account harness builders (rework2-plan AR0).

legal_basis: harness only — enables §20 Abs. 4 S. 7 (FIFO je Depot) scenarios.
Pins that rows built with an explicit account survive the REAL parsers
(BOM-prefixed, all-quoted CSV) with the account intact — the property the
old single-account YAML harness could not provide.
"""
from decimal import Decimal

from src.parsers.trades_parser import parse_trades_csv
from src.parsers.positions_parser import parse_positions_csv
from src.parsers.cash_balance_parser import parse_cash_balance_csv

from tests.support.multi_account import (
    write_csv, trade_row, position_row, cash_balance_row,
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_BALANCE_COLUMNS,
)

A, B = "U10000001", "U10000002"


def test_trade_rows_carry_their_accounts_through_the_parser(tmp_path):
    p = tmp_path / "trades.csv"
    write_csv(str(p), TRADES_COLUMNS, [
        trade_row(A, "US000000ABC1", "20250301", "10", "5", "BUY", "O", "T1"),
        trade_row(B, "US000000ABC1", "20250302", "-4", "6", "SELL", "C", "T2"),
    ])
    assert p.read_bytes()[:3] == b"\xef\xbb\xbf"  # BOM-prefixed like real exports
    recs = parse_trades_csv(str(p))
    assert [r.client_account_id for r in recs] == [A, B]
    assert recs[1].quantity == Decimal("-4")


def test_position_rows_per_account(tmp_path):
    p = tmp_path / "pos.csv"
    write_csv(str(p), POSITIONS_COLUMNS, [
        position_row(A, "US000000ABC1", "100", "600"),
        position_row(B, "US000000ABC1", "50", "300"),
    ])
    recs = parse_positions_csv(str(p))
    assert len(recs) == 2
    assert recs[0].position == Decimal("100") and recs[1].position == Decimal("50")
    # Strengthened with the aggregation fix (B2), which corrected the
    # RawPositionRecord alias (was "AccountId", dropping the account):
    assert {r.client_account_id for r in recs} == {A, B}


def test_cash_balance_rows_per_account(tmp_path):
    p = tmp_path / "cash_bal.csv"
    write_csv(str(p), CASH_BALANCE_COLUMNS, [
        cash_balance_row(A, "USD", "1000", "900"),
        cash_balance_row(B, "USD", "-121.24", "0"),
    ])
    recs = parse_cash_balance_csv(str(p))
    assert [(r.client_account_id, r.starting_cash) for r in recs] == [
        (A, Decimal("1000")), (B, Decimal("-121.24")),
    ]


def test_trade_events_carry_their_account_through_the_factory(tmp_path):
    """per-Depot prerequisite: FinancialEvent.account_id must survive the real
    parser -> factory path, or the (account, asset) ledger routing that follows
    (§20 Abs. 4 S. 7 EStG, FIFO je Depot) has nothing to key on."""
    import os
    from src.parsers.domain_event_factory import DomainEventFactory
    from src.identification.asset_resolver import AssetResolver
    from src.classification.asset_classifier import AssetClassifier
    from src.domain.events import TradeEvent

    p = tmp_path / "trades.csv"
    write_csv(str(p), TRADES_COLUMNS, [
        trade_row(A, "US000000ABC1", "20250301", "10", "5", "BUY", "O", "T1"),
        trade_row(B, "US000000ABC1", "20250302", "-4", "6", "SELL", "C", "T2"),
    ])
    raw = parse_trades_csv(str(p))
    resolver = AssetResolver(asset_classifier=AssetClassifier(
        cache_file_path=str(tmp_path / "cls.json")))
    events, _cand, _stock = DomainEventFactory(resolver).create_events_from_trades(raw)
    trades = [e for e in events if isinstance(e, TradeEvent)]
    assert [e.account_id for e in trades] == [A, B]

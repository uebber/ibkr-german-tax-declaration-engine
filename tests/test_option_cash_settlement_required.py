"""The OptionEAE file is required exactly when a cash settlement happened.

legal_basis: harness/integrity only — this pins no legal rule. It pins that the
engine refuses to produce a figure for a cash-settled option whose settlement
proceeds are absent from the input, which is CLAUDE.md's fail-fast rule, not a
provision. The gain those proceeds carry is taxed under §20 Abs. 2 S. 1 Nr. 3
EStG; the reference is `reference/tax-law/estg-20-kapitalvermoegen.md` and no
expected value here depends on it.

Why these tests exist: `OptionExerciseProcessor` and `OptionAssignmentProcessor`
step aside for an option with no underlying link, on the stated ground that
`OptionCashSettlementProcessor` handles it. Nothing checked that a settlement
event existed. With the OptionEAE file absent the lot stayed open and the run
died at end-of-year reconciliation on a position mismatch — a diagnosis that
sends the reader looking for a missing trade — and if the settlement fell in a
prior year, `reconcile_with_mark` discarded the phantom lot in silence.

The predicate under test is derivable from the Trades export alone, which is
what makes the check possible: an index option's underlying is not an
instrument the account can hold, so it never resolves a link, while a
physically settled option's underlying arrives with the delivery leg.
"""
import csv
import io
from typing import Any, List, Optional, Sequence

import pytest

from src.classification.asset_classifier import AssetClassifier
from src.domain.exceptions import DataIntegrityError
from src.identification.asset_resolver import AssetResolver
from src.parsers.column_validator import OPTIONS_EAE_COLUMNS, TRADES_COLUMNS
from src.parsers.domain_event_factory import DomainEventFactory
from src.parsers.parsing_orchestrator import ParsingOrchestrator

ACCOUNT = "U10000001"


def _write_csv(path, headers: Sequence[str], rows: List[List[Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(list(headers))
    for r in rows:
        w.writerow(["" if c is None else str(c) for c in r])
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(buf.getvalue())
    return str(path)


def _option_trade(symbol: str, conid: str, date: str, qty: str, price: str,
                  side: str, open_close: str, tx_id: str, notes: str,
                  underlying_conid: Optional[str], underlying_symbol: str) -> List[Any]:
    """One Trades row for an option (TRADES_COLUMNS order).

    `underlying_conid=None` with an underlying symbol nothing else in the data
    carries is what an index option looks like: no link resolves.
    """
    return [ACCOUNT, "EUR", "OPT", "OPT", symbol, f"{symbol} option", None,
            "5000", "20250718", "C", date, qty, price, "0", "EUR", side,
            tx_id, notes, underlying_symbol, conid, underlying_conid, "100",
            open_close]


def _stock_trade(symbol: str, conid: str, date: str, qty: str, price: str,
                 side: str, open_close: str, tx_id: str) -> List[Any]:
    return [ACCOUNT, "EUR", "STK", "COMMON", symbol, f"{symbol} security",
            "DE000000TEST", None, None, None, date, qty, price, "0", "EUR",
            side, tx_id, "", None, conid, None, "1", open_close]


def _cash_settlement_rows(symbol: str, conid: str, date: str, qty: str,
                          proceeds: str) -> List[List[Any]]:
    """The Assignment row and its companion Cash Settlement, as IBKR pairs them."""
    base = [ACCOUNT, "EUR", "1", "OPT", symbol, f"{symbol} option", conid, None,
            None, "IDX", "100", "5000", "20250718"]
    return [
        base + ["C", date, "Assignment", qty, "0", "0", "0", "0", "0"],
        base + ["C", date, "Cash Settlement", "0", "0", proceeds, "0", "0", "0"],
    ]


def _run_up_to_the_check(tmp_path, trade_rows, eae_rows=None):
    """Load, resolve assets, link underlyings, create events — the real path.

    Stops short of the engine: the check under test sits at the end of event
    creation, so nothing downstream is needed to observe it.
    """
    trades = _write_csv(tmp_path / "trades.csv", TRADES_COLUMNS, trade_rows)
    eae = (_write_csv(tmp_path / "options_eae.csv", OPTIONS_EAE_COLUMNS, eae_rows)
           if eae_rows is not None else None)

    classifier = AssetClassifier()
    resolver = AssetResolver(asset_classifier=classifier)
    orch = ParsingOrchestrator(asset_resolver=resolver,
                               asset_classifier=classifier,
                               interactive_classification=False)
    orch.load_all_raw_data(trades_file=trades, options_eae_file=eae)
    orch.discover_assets_from_transactions()
    resolver.link_derivatives()
    orch.create_domain_events_and_prepare_for_linking(
        DomainEventFactory(asset_resolver=resolver))
    return orch


def test_cash_settled_assignment_without_the_file_stops_the_run(tmp_path):
    with pytest.raises(DataIntegrityError) as exc:
        _run_up_to_the_check(tmp_path, [
            _option_trade("OESX 20250718 5000 C", "C1", "20250601", "-1", "40",
                          "SELL", "O", "T1", "", None, "ESTX50"),
            _option_trade("OESX 20250718 5000 C", "C1", "20250718", "1", "0",
                          "BUY", "C", "T2", "A", None, "ESTX50"),
        ])
    message = str(exc.value)
    assert "OESX 20250718 5000 C" in message
    assert "OPTION_ASSIGNMENT" in message
    assert "2025-07-18" in message
    # The remedy is named, not just the symptom.
    assert "Options_EAE-YYYY.csv" in message


def test_every_unpaired_contract_is_named_not_only_the_first(tmp_path):
    """Collect, do not stop at the first — CLAUDE.md's report-them-together rule."""
    with pytest.raises(DataIntegrityError) as exc:
        _run_up_to_the_check(tmp_path, [
            _option_trade("OESX 20250718 5000 C", "C1", "20250601", "-1", "40",
                          "SELL", "O", "T1", "", None, "ESTX50"),
            _option_trade("OESX 20250718 5000 C", "C1", "20250718", "1", "0",
                          "BUY", "C", "T2", "A", None, "ESTX50"),
            _option_trade("SPX 20251219 5200 C", "C2", "20250602", "-1", "50",
                          "SELL", "O", "T3", "", None, "SPX"),
            _option_trade("SPX 20251219 5200 C", "C2", "20251219", "1", "0",
                          "BUY", "C", "T4", "A", None, "SPX"),
        ])
    message = str(exc.value)
    assert "OESX 20250718 5000 C" in message
    assert "SPX 20251219 5200 C" in message
    assert message.startswith("2 cash-settled option")


def test_the_file_present_but_missing_this_settlement_also_stops_the_run(tmp_path):
    """File presence is not the requirement; the row for this contract is."""
    with pytest.raises(DataIntegrityError) as exc:
        _run_up_to_the_check(
            tmp_path,
            [
                _option_trade("OESX 20250718 5000 C", "C1", "20250601", "-1", "40",
                              "SELL", "O", "T1", "", None, "ESTX50"),
                _option_trade("OESX 20250718 5000 C", "C1", "20250718", "1", "0",
                              "BUY", "C", "T2", "A", None, "ESTX50"),
            ],
            # A settlement for a different contract entirely.
            eae_rows=_cash_settlement_rows("SPX 20251219 5200 C", "C2",
                                           "20251219", "1", "1200"),
        )
    assert "An OptionEAE file was read" in str(exc.value)
    assert "OESX 20250718 5000 C" in str(exc.value)


def test_a_settlement_for_the_right_contract_on_the_wrong_day_does_not_count(tmp_path):
    """The pairing key is (contract, date), not contract alone.

    A contract can be partially assigned across days, and each assignment has
    its own settlement row. Matching on the contract would let one row cover
    them all — including the ones whose proceeds never arrived.
    """
    with pytest.raises(DataIntegrityError) as exc:
        _run_up_to_the_check(
            tmp_path,
            [
                _option_trade("OESX 20250718 5000 C", "C1", "20250601", "-2", "40",
                              "SELL", "O", "T1", "", None, "ESTX50"),
                _option_trade("OESX 20250718 5000 C", "C1", "20250717", "1", "0",
                              "BUY", "C", "T2", "A", None, "ESTX50"),
                _option_trade("OESX 20250718 5000 C", "C1", "20250718", "1", "0",
                              "BUY", "C", "T3", "A", None, "ESTX50"),
            ],
            eae_rows=_cash_settlement_rows("OESX 20250718 5000 C", "C1",
                                           "20250718", "1", "1200"),
        )
    message = str(exc.value)
    assert message.startswith("1 cash-settled option")  # the 07-17 leg, not the 07-18 one
    assert "2025-07-17" in message


def test_a_zero_proceeds_settlement_row_counts_as_absent(tmp_path):
    """The parser skips a zero-proceeds row, so nothing consumes the lot.

    That skip predates this check and was silent; it must not read as coverage.
    """
    with pytest.raises(DataIntegrityError):
        _run_up_to_the_check(
            tmp_path,
            [
                _option_trade("OESX 20250718 5000 C", "C1", "20250601", "-1", "40",
                              "SELL", "O", "T1", "", None, "ESTX50"),
                _option_trade("OESX 20250718 5000 C", "C1", "20250718", "1", "0",
                              "BUY", "C", "T2", "A", None, "ESTX50"),
            ],
            eae_rows=_cash_settlement_rows("OESX 20250718 5000 C", "C1",
                                           "20250718", "1", "0"),
        )


def test_the_paired_settlement_passes(tmp_path):
    orch = _run_up_to_the_check(
        tmp_path,
        [
            _option_trade("OESX 20250718 5000 C", "C1", "20250601", "-1", "40",
                          "SELL", "O", "T1", "", None, "ESTX50"),
            _option_trade("OESX 20250718 5000 C", "C1", "20250718", "1", "0",
                          "BUY", "C", "T2", "A", None, "ESTX50"),
        ],
        eae_rows=_cash_settlement_rows("OESX 20250718 5000 C", "C1",
                                       "20250718", "1", "1200"),
    )
    settlements = [e for e in orch.domain_financial_events
                   if type(e).__name__ == "OptionCashSettlementEvent"]
    assert len(settlements) == 1


def test_a_physically_settled_assignment_needs_no_file(tmp_path):
    """The majority case: the underlying arrives with the delivery leg, the link
    resolves, and the normal processors consume the lot. 30 of the 44 A/EX rows
    in the 2021-2025 import are this shape (measured 2026-08-08)."""
    orch = _run_up_to_the_check(tmp_path, [
        _option_trade("TEST 20250718 100 C", "C9", "20250601", "-1", "4",
                      "SELL", "O", "T1", "", "S1", "TEST"),
        _option_trade("TEST 20250718 100 C", "C9", "20250718", "1", "0",
                      "BUY", "C", "T2", "A", "S1", "TEST"),
        _stock_trade("TEST", "S1", "20250718", "-100", "110", "SELL", "C", "T3"),
    ])
    assert orch.domain_financial_events  # no raise; events were produced


def test_an_option_that_never_settled_needs_no_file(tmp_path):
    """An open index-option position carries no requirement — nothing settled."""
    orch = _run_up_to_the_check(tmp_path, [
        _option_trade("OESX 20250718 5000 C", "C1", "20250601", "-1", "40",
                      "SELL", "O", "T1", "", None, "ESTX50"),
    ])
    assert orch.domain_financial_events

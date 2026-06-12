"""
account_id propagation + BOM-input robustness (per-Depot prerequisites).

Per-Depot FIFO only works if every event carries the custody account it belongs to. Early in this
work the option-lifecycle events were missing `account_id`, which split the option ledger across a
real account and the DEFAULT account and broke option processing — a green suite didn't catch it.
These pin that account_id reaches each event type, and that the account column survives a UTF-8 BOM
(the real 2025 export is BOM-prefixed; a naive reader silently drops the first column).

No existing tests or shared helpers are modified.
"""
from decimal import Decimal

from src.parsers.trades_parser import parse_trades_csv
from src.parsers.domain_event_factory import DomainEventFactory
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.domain.events import TradeEvent, OptionLifecycleEvent, CurrencyConversionEvent
from tests.support.option_helpers import create_option_trade_data, create_stock_trade_data
from tests.support.csv_creators import create_trades_csv_string

ACCT = "U10000002"


def _resolver(tmp_path):
    return AssetResolver(asset_classifier=AssetClassifier(cache_file_path=str(tmp_path / "cls.json")))


def _forex_row(acct, symbol, date, qty, rate, txid):
    """A CASH forex-pair trade row (column order = TRADES_COLUMNS) -> CurrencyConversionEvent."""
    base = symbol.split(".")[0]
    return [acct, base, "CASH", "", symbol, f"{symbol} forex", "",
            None, None, None, date, Decimal(qty), Decimal(rate), Decimal("0"), base,
            "BUY" if Decimal(qty) > 0 else "SELL", txid, None, None, "FXCON1", None, Decimal("1"), ""]


class TestAccountIdPropagation:

    def test_trade_option_lifecycle_and_conversion_carry_account_id(self, tmp_path):
        rows = [
            create_stock_trade_data(ACCT, "EUR", "ABC", "ABC Inc", "US000000ABC1", "CONABC",
                                    "2025-03-01", "BL", Decimal("10"), Decimal("5"),
                                    transaction_id="STK1"),
            # option expiring worthless (Notes/Codes 'Ep') -> OptionLifecycleEvent (the bug we hit)
            create_option_trade_data(ACCT, "EUR", "ABCOPT", "ABC option", "ABC", "CONABC",
                                     "OPTCON1", Decimal("50"), "2025-01-20", "C",
                                     "2025-01-20", "SL", Decimal("1"), Decimal("0"),
                                     transaction_id="OPTEXP1", notes_codes="Ep"),
            _forex_row(ACCT, "EUR.USD", "2025-04-01", "1000", "1.1", "FX1"),
        ]
        path = tmp_path / "trades.csv"
        path.write_text(create_trades_csv_string(rows), encoding="utf-8-sig")
        raw = parse_trades_csv(str(path))
        events, _candidates, _stock = DomainEventFactory(_resolver(tmp_path)).create_events_from_trades(raw)

        trade_events = [e for e in events if isinstance(e, TradeEvent)]
        option_events = [e for e in events if isinstance(e, OptionLifecycleEvent)]
        conv_events = [e for e in events if isinstance(e, CurrencyConversionEvent)]

        assert trade_events and all(e.account_id == ACCT for e in trade_events)
        assert option_events and all(e.account_id == ACCT for e in option_events), \
            "OptionLifecycleEvent must carry account_id (else the option ledger splits)"
        assert conv_events and all(e.account_id == ACCT for e in conv_events)


class TestBomInputRobustness:

    def test_client_account_id_read_from_utf8_bom_file(self, tmp_path):
        rows = [create_stock_trade_data(ACCT, "EUR", "ABC", "ABC Inc", "US000000ABC1", "CONABC",
                                        "2025-03-01", "BL", Decimal("10"), Decimal("5"),
                                        transaction_id="STK1")]
        path = tmp_path / "trades_bom.csv"
        # utf-8-sig prepends a BOM; the parser must still read the first column (ClientAccountID).
        path.write_text(create_trades_csv_string(rows), encoding="utf-8-sig")
        assert path.read_bytes()[:3] == b"\xef\xbb\xbf", "fixture must actually contain a BOM"
        raw = parse_trades_csv(str(path))
        assert raw and raw[0].client_account_id == ACCT

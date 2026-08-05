# tests/test_replay_stream.py
"""
Guards for the unified historical replayer's ordering contract
(`src/engine/replay.py`, introduced with the AR5 refactor).

Why this needs its own test. The refactor replaced three separate machines --
per-asset batch simulation, a dedicated merger pass and a per-currency replay
loop -- with ONE stream whose only guarantee is the order it replays items in:
`Phase.LEDGER_EVENTS` chronologically, then `Phase.MERGERS`, then
`Phase.RECONCILE`, with the insertion sequence as the final tie-breaker. That
ordering IS the behaviour; everything else in `replay.py` is a list and a sort.

It shipped without a test, and the suite could not see it. Probed by mutating
`ReplayStream.run()` and running all 466 tests:

    mutation                                            failures
    ---------------------------------------------------------------
    drop the sort entirely (insertion order)                   0
    drop chronology, keep phase + insertion order              0
    drop the seq tie-breaker                                   0
    reverse every historical CURRENCY event                    0
    reverse every historical SECURITY event                    1
    run MERGERS before LEDGER_EVENTS                           1
    run RECONCILE before MERGERS                               1

The first three are green because insertion order happens to reproduce the old
three-pass order, so they are weak mutations. The fourth is not: the entire
historical currency replay -- which fixes the EUR cost basis of every foreign
currency lot, and therefore every FX gain declared under § 20 Abs. 2 Nr. 3 /
Abs. 4 EStG -- can be replayed backwards with the whole suite still green. And
the single failure for the two phase mutations is
`tests/test_historical_merger_replay_guard.py`, added while reviewing the
LedgerKey seam; without it the phase contract would be unobservable too.

The ordering also stops being merely internal later in the train: the
internal-transfer handler registers at `Phase.LEDGER_EVENTS` and relies on the
chronological interleave with trades to reconstruct a bought-transferred-sold
history lot-exactly.

`TestReplayStreamOrdering` pins the contract directly.
`TestHistoricalCurrencyReplayOrder` pins its consequence for a declared figure,
which is the part the suite was blind to.
"""
from decimal import Decimal
from typing import Any, List, Optional

from src.domain.enums import AssetCategory
from src.engine.replay import Phase, ReplayStream
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider


class TestReplayStreamOrdering:
    """The three properties `ReplayStream.run()` promises, one test each."""

    @staticmethod
    def _recorder(log: List[str], name: str):
        return lambda: log.append(name)

    def test_phases_run_in_ascending_order_regardless_of_insertion(self):
        """RECONCILE after MERGERS after LEDGER_EVENTS, even inserted backwards."""
        log: List[str] = []
        stream = ReplayStream()
        stream.add(Phase.RECONCILE, (0,), self._recorder(log, "reconcile"))
        stream.add(Phase.MERGERS, ("2020-01-01",), self._recorder(log, "merger"))
        stream.add(Phase.LEDGER_EVENTS, ("2021-01-01",), self._recorder(log, "event"))

        stream.run()

        assert log == ["event", "merger", "reconcile"]

    def test_items_within_a_phase_run_in_sort_key_order(self):
        """Chronology, not insertion order, decides within a phase."""
        log: List[str] = []
        stream = ReplayStream()
        for key in ("2023-09-01", "2023-03-01", "2023-06-01"):
            stream.add(Phase.LEDGER_EVENTS, (key,), self._recorder(log, key))

        stream.run()

        assert log == ["2023-03-01", "2023-06-01", "2023-09-01"]

    def test_equal_sort_keys_keep_insertion_order(self):
        """
        Colliding keys are the common case, not the corner case: on the real
        2025 data 7,614 of 8,949 stream items share a (phase, sort_key) with at
        least one other item -- every trade is streamed twice (once for its
        security ledger, once for its currency ledger) under the same event
        sort key, and all reconcile items carry the constant key `(0,)`.

        This pins the property, not the mechanism. `run()` delivers it twice
        over: explicitly via the `seq` field, and implicitly because `sorted()`
        is stable and `_items` is already in insertion order -- so dropping
        `seq` from the key today changes nothing. The property is what callers
        depend on; keep it pinned however it is implemented.
        """
        log: List[str] = []
        stream = ReplayStream()
        for name in ("security-leg", "currency-leg"):
            stream.add(Phase.LEDGER_EVENTS, ("2023-03-01",), self._recorder(log, name))
        for name in ("reconcile-a", "reconcile-b", "reconcile-c"):
            stream.add(Phase.RECONCILE, (0,), self._recorder(log, name))

        stream.run()

        assert log == [
            "security-leg", "currency-leg",
            "reconcile-a", "reconcile-b", "reconcile-c",
        ]

    def test_len_counts_added_items(self):
        stream = ReplayStream()
        assert len(stream) == 0
        stream.add(Phase.LEDGER_EVENTS, ("2023-01-01",), lambda: None)
        stream.add(Phase.RECONCILE, (0,), lambda: None)
        assert len(stream) == 2


# =============================================================================
# Engine-level: the historical CURRENCY replay must be chronological
# =============================================================================

_ACCOUNT = "U_REPLAY_ORDER"
_TAX_YEAR = 2023


class _DatedRateProvider(MockECBExchangeRateProvider):
    """Per-date, per-currency rates; falls back to the mock's default."""

    def __init__(self, rate_map: dict):
        super().__init__(foreign_to_eur_init_value=Decimal("1.0"))
        self._rate_map = rate_map

    def get_rate(self, date_of_conversion, currency_code: str) -> Optional[Decimal]:
        from datetime import date as date_type

        currency_upper = currency_code.upper()
        if currency_upper == "EUR":
            return Decimal("1.0")
        if isinstance(date_of_conversion, date_type):
            date_str = date_of_conversion.strftime("%Y-%m-%d")
        else:
            date_str = str(date_of_conversion)
        if (date_str, currency_upper) in self._rate_map:
            return self._rate_map[(date_str, currency_upper)]
        return super().get_rate(date_of_conversion, currency_code)


def _cash_transaction_row(currency: str, amount: Decimal, tx_type: str, settle_date: str,
                          tx_id: str, symbol: str = "", description: str = "",
                          isin: str = "", asset_class: str = "", sub_category: str = "",
                          country_code: str = "") -> List[Any]:
    return [
        _ACCOUNT, currency, asset_class, sub_category, symbol, description,
        settle_date, amount, tx_type, "", "", isin, country_code, tx_id,
    ]


def _fx_sell_row(currency: str, eur_amount: Decimal, ecb_rate: Decimal,
                 trade_date: str, tx_id: str) -> List[Any]:
    """Sell `currency` for EUR (IBKR books this as a BUY of the EUR.CCY pair)."""
    return [
        _ACCOUNT, "EUR", "CASH", "", f"EUR.{currency}", f"FX EUR.{currency}", "",
        None, None, None,
        trade_date, eur_amount, ecb_rate, Decimal("0"), "EUR",
        "BUY", tx_id, None, None, None, None, Decimal("1"), "O",
    ]


class TestHistoricalCurrencyReplayOrder(FifoTestCaseBase):
    """
    The historical currency events are fed to the engine in DELIBERATELY
    non-chronological order, and the FX loss declared for the tax year is the
    discriminator between replaying them chronologically and replaying them in
    input order.

    2022 history for USD, given to the parser in the order Sep, Jun, Mar:

        2022-03-01  dividend  +100 USD   rate 1.00  ->  100.00 EUR  (1.00 EUR/USD)
        2022-06-01  fee       -100 USD
        2022-09-01  dividend  +100 USD   rate 2.00  ->   50.00 EUR  (0.50 EUR/USD)

    Chronologically the June fee consumes the March lot, so the 100 USD carried
    into 2023 is the September lot at 0.50 EUR/USD -- cost basis 50.00 EUR.
    Replayed in input order the fee consumes the September lot instead and the
    surviving lot is March's, at 1.00 EUR/USD -- cost basis 100.00 EUR.

    Selling the 100 USD in 2023 at 4.00 USD/EUR yields 25.00 EUR, so the
    declared FX result is -25.00 EUR chronologically and -75.00 EUR if the
    order is disturbed. Nothing else in the scenario changes.

    What this can and cannot see. `ParsingOrchestrator.get_all_financial_events`
    already sorts the whole event list by `get_event_sort_key` before the engine
    is called, so the CSV row order above is normalised away and the stream's
    own sort is a second, independent guarantee rather than the one that
    establishes chronology. This test therefore observes a *disturbed* replay
    order (the stream re-ordering the events it was handed), not "input order
    survives to the ledger" -- which today it cannot, and which the assertion
    would silently stop covering if the upstream sort were ever removed.

    The 2022-12-31 rate is deliberately unlike every other rate in the map so
    that a fallback lot, if one were ever minted, would be visible in the cost
    basis. It is reached only by `_reconcile_currency_soy`, which returns early
    here because the reconstructed 100 USD equals the reported SoY 100 USD.
    Phase ordering itself is pinned by `TestReplayStreamOrdering` above, not by
    this scenario: running RECONCILE first only adds an unconsumed 100 USD
    fallback lot dated 2022-12-31, which sorts *after* the September lot and so
    leaves this disposal's cost basis untouched. That is Pass 3's SoY masking
    again -- a reconciliation that can paper over a broken replay with a
    plausible number.
    """

    def test_historical_currency_events_replay_chronologically(self, mock_config_paths):
        rate_map = {
            ("2022-03-01", "USD"): Decimal("1.00"),
            ("2022-06-01", "USD"): Decimal("1.00"),
            ("2022-09-01", "USD"): Decimal("2.00"),
            # Only reachable through the SoY fallback lot; see the class docstring.
            ("2022-12-31", "USD"): Decimal("5.00"),
            ("2023-05-02", "USD"): Decimal("4.00"),
        }

        # Rows deliberately out of chronological order: Sep, Jun, Mar.
        cash_transactions = [
            _cash_transaction_row(
                currency="USD", amount=Decimal("100"), tx_type="Dividends",
                settle_date="2022-09-01", tx_id="DIV_SEP", symbol="AAPL",
                description="AAPL CASH DIVIDEND USD", isin="US0378331005",
                asset_class="STK", sub_category="COMMON", country_code="US",
            ),
            _cash_transaction_row(
                currency="USD", amount=Decimal("-100"), tx_type="Other Fees",
                settle_date="2022-06-01", tx_id="FEE_JUN",
                description="USD ACCOUNT FEE",
            ),
            _cash_transaction_row(
                currency="USD", amount=Decimal("100"), tx_type="Dividends",
                settle_date="2022-03-01", tx_id="DIV_MAR", symbol="AAPL",
                description="AAPL CASH DIVIDEND USD", isin="US0378331005",
                asset_class="STK", sub_category="COMMON", country_code="US",
            ),
        ]

        # 100 USD carried into 2023, sold on 2023-05-02 at 4.00 USD/EUR.
        trades = [_fx_sell_row("USD", Decimal("25"), Decimal("4.00"), "2023-05-02", "FX_SELL")]

        cash_balance = [[_ACCOUNT, "USD", "20230101", "20231231", Decimal("100"), Decimal("0")]]

        actual = self._run_pipeline(
            trades_data=trades,
            cash_transactions_data=cash_transactions,
            cash_balance_data=cash_balance,
            custom_rate_provider=_DatedRateProvider(rate_map),
            tax_year=_TAX_YEAR,
        )

        currency_rgls = [
            rgl for rgl in actual.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.CASH_BALANCE
        ]
        assert len(currency_rgls) == 1, f"Expected exactly 1 currency RGL, got {currency_rgls}"
        rgl = currency_rgls[0]

        from src import config as app_config
        q = app_config.OUTPUT_PRECISION_AMOUNTS
        assert rgl.quantity_realized == Decimal("100")
        # 50.00 chronologically; 100.00 if the stream replays in input order.
        assert rgl.total_cost_basis_eur.quantize(q) == Decimal("50.00")
        assert rgl.total_realization_value_eur.quantize(q) == Decimal("25.00")
        assert rgl.gross_gain_loss_eur.quantize(q) == Decimal("-25.00")

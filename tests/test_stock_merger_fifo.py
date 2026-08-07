"""
Stock Merger FIFO Lot Transfer Tests

Tests for the stock-for-stock merger feature:
- Parser: receive-row filtering (Step 1)
- FifoLedger: drain/receive methods (Step 3)
- MergerStockProcessor: lot transfer with prepare-then-commit (Step 4)
- Historical replay: three-pass SOY initialization (Step 5)
- Integration: end-to-end merger + subsequent sell
"""

import pytest
import uuid
from decimal import Decimal, getcontext
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from typing import List, Optional

from src.domain.events import (
    CorpActionMergerStock, TradeEvent, CorpActionSplitForward,
    FinancialEvent,
)
from src.domain.enums import FinancialEventType, AssetCategory, RealizationType
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger, FifoLot, ShortFifoLot
from src.engine.event_processors.corporate_action_processor import MergerStockProcessor
from src.utils.account_utils import DEFAULT_ACCOUNT
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.expected import (
    ScenarioExpectedOutput,
    ExpectedRealizedGainLoss,
    ExpectedAssetEoyState,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_ledger(asset_id: uuid.UUID,
                 category: AssetCategory = AssetCategory.STOCK) -> FifoLedger:
    """Create a FifoLedger with mock dependencies for unit testing."""
    mock_converter = MagicMock(spec=CurrencyConverter)
    mock_provider = MagicMock(spec=ECBExchangeRateProvider)
    return FifoLedger(
        asset_internal_id=asset_id,
        asset_category=category,
        asset_multiplier_from_asset=None,
        currency_converter=mock_converter,
        exchange_rate_provider=mock_provider,
        internal_working_precision=28,
        decimal_rounding_mode="ROUND_HALF_UP",
    )


def _make_long_lot(acq_date: str, qty: str, unit_cost: str, tx_id: str) -> FifoLot:
    """Create a FifoLot for testing."""
    q = Decimal(qty)
    u = Decimal(unit_cost)
    return FifoLot(
        acquisition_date=acq_date,
        quantity=q,
        unit_cost_basis_eur=u,
        total_cost_basis_eur=q * u,
        source_transaction_id=tx_id,
    )


def _make_short_lot(open_date: str, qty: str, unit_proceeds: str, tx_id: str) -> ShortFifoLot:
    """Create a ShortFifoLot for testing."""
    q = Decimal(qty)
    u = Decimal(unit_proceeds)
    return ShortFifoLot(
        opening_date=open_date,
        quantity_shorted=q,
        unit_sale_proceeds_eur=u,
        total_sale_proceeds_eur=q * u,
        source_transaction_id=tx_id,
    )


def _make_merger_event(source_id: uuid.UUID, target_id: uuid.UUID,
                       ratio: str = "1", event_date: str = "2022-08-22") -> CorpActionMergerStock:
    """Create a CorpActionMergerStock event for testing."""
    return CorpActionMergerStock(
        asset_internal_id=source_id,
        event_date=event_date,
        new_asset_internal_id=target_id,
        new_shares_received_per_old=Decimal(ratio),
    )


class TestMergerIntraDayOrdering:
    """
    Pin the one intra-day rule the chronological merger replay depends on.

    Since issue #56 a merger is an ordinary `Phase.LEDGER_EVENTS` item placed at
    its own date (§20 Abs. 4a Satz 6 EStG, GT-ESTG20-018: the measure takes
    effect at the Einbuchung into the depot). For that to be worth anything, the
    merger has to be applied BEFORE the same day's trades -- otherwise a
    disposal of the delivered shares still oversells.

    **That ordering currently holds by accident.** `sorting_utils.py` puts the
    transaction id ahead of `intra_day_order` in the secondary key, so
    `_INTRA_DAY_SORT_ORDER_CORP_ACTION` decides nothing between events with
    different ids. A corporate action sorts first only because
    `Corporate_Actions-*.csv` carries no `TransactionID` column, so
    `ibkr_transaction_id` is None and the key element is `""`, which precedes
    every real id. If IBKR ever supplies that column the order flips and the
    integration tests break with no explanation. This test is the explanation.
    """

    @staticmethod
    def _resolver():
        asset = MagicMock()
        asset.ibkr_symbol = "BETA"
        asset.asset_category = AssetCategory.STOCK
        resolver = MagicMock()
        resolver.get_asset_by_id.return_value = asset
        return resolver

    def test_merger_sorts_before_same_day_trades(self):
        from src.utils.sorting_utils import get_event_sort_key

        resolver = self._resolver()
        source_id, target_id = uuid.uuid4(), uuid.uuid4()

        merger = _make_merger_event(source_id, target_id, event_date="2022-06-15")
        sale = TradeEvent(
            asset_internal_id=target_id,
            event_date="2022-06-15",
            quantity=Decimal("-40"),
            price_foreign_currency=Decimal("52.00"),
            event_type=FinancialEventType.TRADE_SELL_LONG,
            ibkr_transaction_id="1322551221",
        )

        assert get_event_sort_key(merger, resolver) < get_event_sort_key(sale, resolver)

    def test_a_transaction_id_on_the_merger_would_break_it(self):
        """
        The failure mode above, made visible: give the merger an id and the
        ordering is decided by a lexicographic string comparison instead. Not a
        wish for different behaviour -- a record of what the guarantee rests on,
        so that whoever adds the column knows what they have to fix.
        """
        from src.utils.sorting_utils import get_event_sort_key

        resolver = self._resolver()
        source_id, target_id = uuid.uuid4(), uuid.uuid4()

        merger = _make_merger_event(source_id, target_id, event_date="2022-06-15")
        merger.ibkr_transaction_id = "9999999999"  # would sort after the sale
        sale = TradeEvent(
            asset_internal_id=target_id,
            event_date="2022-06-15",
            quantity=Decimal("-40"),
            price_foreign_currency=Decimal("52.00"),
            event_type=FinancialEventType.TRADE_SELL_LONG,
            ibkr_transaction_id="1322551221",
        )

        assert get_event_sort_key(merger, resolver) > get_event_sort_key(sale, resolver)


# =============================================================================
# Group 1: FifoLedger drain/receive methods
# =============================================================================

class TestFifoLedgerDrainReceive:
    """Unit tests for drain_all_long_lots, drain_all_short_lots, receive_all_lots_from_merger."""

    def test_drain_all_long_lots_removes_and_returns(self):
        source_id = uuid.uuid4()
        ledger = _make_ledger(source_id)
        lot1 = _make_long_lot("2022-01-15", "50", "100.00", "TX1")
        lot2 = _make_long_lot("2022-03-20", "80", "110.00", "TX2")
        ledger.lots.extend([lot1, lot2])

        drained = ledger.drain_all_long_lots()

        assert len(drained) == 2
        assert len(ledger.lots) == 0
        assert drained[0].quantity == Decimal("50")
        assert drained[1].quantity == Decimal("80")

    def test_drain_all_short_lots_removes_and_returns(self):
        source_id = uuid.uuid4()
        ledger = _make_ledger(source_id)
        lot = _make_short_lot("2022-02-10", "30", "200.00", "TX_SHORT1")
        ledger.short_lots.append(lot)

        drained = ledger.drain_all_short_lots()

        assert len(drained) == 1
        assert len(ledger.short_lots) == 0
        assert drained[0].quantity_shorted == Decimal("30")

    def test_drain_empty_ledger_returns_empty(self):
        ledger = _make_ledger(uuid.uuid4())
        assert ledger.drain_all_long_lots() == []
        assert ledger.drain_all_short_lots() == []

    def test_receive_long_lots_1_to_1_ratio(self):
        """1:1 ratio preserves quantity, unit cost, total cost, and acquisition date."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        target_ledger = _make_ledger(target_id)

        lot1 = _make_long_lot("2021-06-01", "100", "50.00", "TX_A")
        lot2 = _make_long_lot("2022-01-15", "30", "60.00", "TX_B")
        merger = _make_merger_event(source_id, target_id, ratio="1")

        target_ledger.receive_all_lots_from_merger([lot1, lot2], [], Decimal("1"), merger)

        assert len(target_ledger.lots) == 2
        assert target_ledger.lots[0].quantity == Decimal("100")
        assert target_ledger.lots[0].unit_cost_basis_eur == Decimal("50.00")
        assert target_ledger.lots[0].total_cost_basis_eur == Decimal("5000.00")
        assert target_ledger.lots[0].acquisition_date == "2021-06-01"
        assert target_ledger.lots[1].quantity == Decimal("30")

    def test_receive_long_lots_2_to_1_ratio(self):
        """2:1 ratio doubles qty, halves unit cost, preserves total cost."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        target_ledger = _make_ledger(target_id)

        lot = _make_long_lot("2021-03-01", "50", "200.00", "TX_C")
        merger = _make_merger_event(source_id, target_id, ratio="2")

        target_ledger.receive_all_lots_from_merger([lot], [], Decimal("2"), merger)

        assert len(target_ledger.lots) == 1
        assert target_ledger.lots[0].quantity == Decimal("100")
        assert target_ledger.lots[0].total_cost_basis_eur == Decimal("10000.00")
        # unit cost = 10000 / 100 = 100
        assert target_ledger.lots[0].unit_cost_basis_eur == Decimal("100")
        assert target_ledger.lots[0].acquisition_date == "2021-03-01"

    def test_receive_short_lots_1_to_1(self):
        """Short lots transferred with preserved opening date and proceeds."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        target_ledger = _make_ledger(target_id)

        short_lot = _make_short_lot("2022-05-10", "40", "150.00", "TX_S1")
        merger = _make_merger_event(source_id, target_id, ratio="1")

        target_ledger.receive_all_lots_from_merger([], [short_lot], Decimal("1"), merger)

        assert len(target_ledger.short_lots) == 1
        assert target_ledger.short_lots[0].quantity_shorted == Decimal("40")
        assert target_ledger.short_lots[0].unit_sale_proceeds_eur == Decimal("150.00")
        assert target_ledger.short_lots[0].total_sale_proceeds_eur == Decimal("6000.00")
        assert target_ledger.short_lots[0].opening_date == "2022-05-10"

    def test_receive_mixed_long_and_short(self):
        """Both long and short lots transferred correctly."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        target_ledger = _make_ledger(target_id)

        long_lot = _make_long_lot("2021-01-01", "100", "50.00", "TX_L")
        short_lot = _make_short_lot("2022-01-01", "20", "80.00", "TX_S")
        merger = _make_merger_event(source_id, target_id, ratio="1")

        target_ledger.receive_all_lots_from_merger([long_lot], [short_lot], Decimal("1"), merger)

        assert len(target_ledger.lots) == 1
        assert len(target_ledger.short_lots) == 1
        assert target_ledger.lots[0].quantity == Decimal("100")
        assert target_ledger.short_lots[0].quantity_shorted == Decimal("20")

    def test_cost_basis_conservation(self):
        """Total cost basis across source lots must equal total on target lots."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        target_ledger = _make_ledger(target_id)

        lots = [
            _make_long_lot("2021-01-01", "50", "100.00", "TX1"),
            _make_long_lot("2021-06-01", "30", "120.00", "TX2"),
        ]
        original_total = sum(l.total_cost_basis_eur for l in lots)
        merger = _make_merger_event(source_id, target_id, ratio="1")

        target_ledger.receive_all_lots_from_merger(lots, [], Decimal("1"), merger)

        transferred_total = sum(l.total_cost_basis_eur for l in target_ledger.lots)
        assert transferred_total == original_total

    def test_cost_basis_conservation_non_unity_ratio(self):
        """Cost basis conserved even with non-1:1 ratio."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        target_ledger = _make_ledger(target_id)

        lot = _make_long_lot("2021-01-01", "60", "100.00", "TX1")
        original_total = lot.total_cost_basis_eur  # 6000
        merger = _make_merger_event(source_id, target_id, ratio="3")

        target_ledger.receive_all_lots_from_merger([lot], [], Decimal("3"), merger)

        assert target_ledger.lots[0].total_cost_basis_eur == original_total
        assert target_ledger.lots[0].quantity == Decimal("180")

    def test_appends_to_existing_target_lots(self):
        """Merger lots are added to target's existing lots, not replacing them."""
        target_id = uuid.uuid4()
        target_ledger = _make_ledger(target_id)
        existing_lot = _make_long_lot("2020-01-01", "10", "50.00", "TX_EXIST")
        target_ledger.lots.append(existing_lot)

        source_id = uuid.uuid4()
        lot = _make_long_lot("2021-06-01", "20", "100.00", "TX_MERGE")
        merger = _make_merger_event(source_id, target_id, ratio="1")

        target_ledger.receive_all_lots_from_merger([lot], [], Decimal("1"), merger)

        assert len(target_ledger.lots) == 2


# =============================================================================
# Group 2: MergerStockProcessor
# =============================================================================

class TestMergerStockProcessor:
    """Unit tests for MergerStockProcessor.process()."""

    def test_long_lots_transferred(self):
        """Source long lots are drained and appear on target ledger."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        source_ledger = _make_ledger(source_id)
        target_ledger = _make_ledger(target_id)

        source_ledger.lots.append(_make_long_lot("2022-01-01", "130", "167.56", "TX1"))

        merger = _make_merger_event(source_id, target_id)
        fifo_ledgers = {(DEFAULT_ACCOUNT, source_id): source_ledger,
                        (DEFAULT_ACCOUNT, target_id): target_ledger}
        context = {'fifo_ledgers': fifo_ledgers}

        processor = MergerStockProcessor()
        rgls = processor.process(merger, source_ledger, context)

        assert rgls == []  # Tax-neutral
        assert len(source_ledger.lots) == 0
        assert len(source_ledger.short_lots) == 0
        assert len(target_ledger.lots) == 1
        assert target_ledger.lots[0].quantity == Decimal("130")
        assert target_ledger.lots[0].acquisition_date == "2022-01-01"

    def test_short_lots_transferred(self):
        """Source short lots are transferred to target."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        source_ledger = _make_ledger(source_id)
        target_ledger = _make_ledger(target_id)

        source_ledger.short_lots.append(_make_short_lot("2022-04-01", "50", "200.00", "TX_S"))

        merger = _make_merger_event(source_id, target_id)
        context = {'fifo_ledgers': {(DEFAULT_ACCOUNT, source_id): source_ledger,
                                    (DEFAULT_ACCOUNT, target_id): target_ledger}}

        processor = MergerStockProcessor()
        rgls = processor.process(merger, source_ledger, context)

        assert rgls == []
        assert len(source_ledger.short_lots) == 0
        assert len(target_ledger.short_lots) == 1

    def test_empty_source_ledger_returns_empty(self):
        """Empty source ledger produces warning, no crash."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        source_ledger = _make_ledger(source_id)
        target_ledger = _make_ledger(target_id)

        merger = _make_merger_event(source_id, target_id)
        context = {'fifo_ledgers': {(DEFAULT_ACCOUNT, source_id): source_ledger,
                                    (DEFAULT_ACCOUNT, target_id): target_ledger}}

        processor = MergerStockProcessor()
        rgls = processor.process(merger, source_ledger, context)
        assert rgls == []

    def test_missing_target_ledger_returns_empty(self):
        """Missing target ledger produces error log, no crash."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        source_ledger = _make_ledger(source_id)
        source_ledger.lots.append(_make_long_lot("2022-01-01", "100", "50.00", "TX1"))

        merger = _make_merger_event(source_id, target_id)
        context = {'fifo_ledgers': {(DEFAULT_ACCOUNT, source_id): source_ledger}}  # No target ledger

        processor = MergerStockProcessor()
        rgls = processor.process(merger, source_ledger, context)
        assert rgls == []
        # Source lots should NOT be drained since target is missing
        assert len(source_ledger.lots) == 1

    def test_rollback_on_failure(self):
        """If receive fails, source lots are restored."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        source_ledger = _make_ledger(source_id)
        target_ledger = _make_ledger(target_id)

        lot = _make_long_lot("2022-01-01", "100", "50.00", "TX1")
        source_ledger.lots.append(lot)

        merger = _make_merger_event(source_id, target_id)
        context = {'fifo_ledgers': {(DEFAULT_ACCOUNT, source_id): source_ledger,
                                    (DEFAULT_ACCOUNT, target_id): target_ledger}}

        # Patch receive to raise an exception
        with patch.object(target_ledger, 'receive_all_lots_from_merger', side_effect=ValueError("Test error")):
            processor = MergerStockProcessor()
            with pytest.raises(ValueError, match="Test error"):
                processor.process(merger, source_ledger, context)

        # Source lots should be restored
        assert len(source_ledger.lots) == 1
        assert source_ledger.lots[0].quantity == Decimal("100")
        # Target should be untouched
        assert len(target_ledger.lots) == 0

    def test_post_conditions_source_empty(self):
        """After successful merger, source has 0 long and 0 short lots."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        source_ledger = _make_ledger(source_id)
        target_ledger = _make_ledger(target_id)

        source_ledger.lots.append(_make_long_lot("2022-01-01", "100", "50.00", "TX1"))
        source_ledger.short_lots.append(_make_short_lot("2022-02-01", "20", "60.00", "TX_S"))

        merger = _make_merger_event(source_id, target_id)
        context = {'fifo_ledgers': {(DEFAULT_ACCOUNT, source_id): source_ledger,
                                    (DEFAULT_ACCOUNT, target_id): target_ledger}}

        processor = MergerStockProcessor()
        processor.process(merger, source_ledger, context)

        assert len(source_ledger.lots) == 0
        assert len(source_ledger.short_lots) == 0

    def test_multiple_lots_different_dates_and_costs(self):
        """Multiple lots with different dates/costs are all transferred."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        source_ledger = _make_ledger(source_id)
        target_ledger = _make_ledger(target_id)

        source_ledger.lots.extend([
            _make_long_lot("2021-01-15", "50", "100.00", "TX1"),
            _make_long_lot("2021-06-20", "80", "110.00", "TX2"),
        ])

        merger = _make_merger_event(source_id, target_id)
        context = {'fifo_ledgers': {(DEFAULT_ACCOUNT, source_id): source_ledger,
                                    (DEFAULT_ACCOUNT, target_id): target_ledger}}

        processor = MergerStockProcessor()
        processor.process(merger, source_ledger, context)

        assert len(target_ledger.lots) == 2
        # Should preserve original acquisition dates
        dates = {l.acquisition_date for l in target_ledger.lots}
        assert dates == {"2021-01-15", "2021-06-20"}


# =============================================================================
# Group 3: Integration tests (end-to-end via pipeline)
# =============================================================================

# Corporate Actions CSV columns: ClientAccountID, Symbol, Description, ISIN,
# Report Date, Code, Type, ActionID, Conid, UnderlyingConid, UnderlyingSymbol,
# CurrencyPrimary, Amount, Proceeds, Value, Quantity

class TestMergerIntegration(FifoTestCaseBase):
    """Integration tests: full pipeline with stock mergers."""

    def test_current_year_merger_and_sell(self, mock_config_paths):
        """
        Current-year merger followed by immediate sell.
        BUY 130 GZUR -> Merger GZUR->SGBS 1:1 -> SELL 130 SGBS
        """
        tax_year = 2023
        account = "U_MERGER_TEST"
        fx_rate = Decimal("1.0")  # EUR assets
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=fx_rate)

        # Trades: BUY 130 GZUR on 2023-03-01, SELL 130 SGBS on 2023-08-22
        trades_data = [
            # BUY 130 GZUR @ 167.56 EUR
            [account, "EUR", "STK", "", "GZUR", "GZUR Stock", "DE0000000015",
             "", "", "", "2023-03-01", "130", "167.56", "-2.00", "EUR",
             "BUY", "TX_BUY_GZUR", "", "", "CON_GZUR", "", "1", "O"],
            # SELL 130 SGBS @ 168.00 EUR (after merger)
            [account, "EUR", "STK", "", "SGBS", "SGBS Stock", "JE0000000014",
             "", "", "", "2023-08-22", "-130", "168.00", "-2.00", "EUR",
             "SELL", "TX_SELL_SGBS", "", "", "CON_SGBS", "", "1", "C"],
        ]

        # Corporate action: GZUR merged into SGBS on 2023-08-22
        # Dispose row (qty=-130)
        corp_actions_data = [
            [account, "GZUR", "GZUR(DE0000000015) MERGED(Acquisition) WITH SGBS 1 FOR 1",
             "DE0000000015", "2023-08-22", "TC", "TC", "900034051",
             "CON_GZUR", "", "", "EUR", "0", "0", "-21782.80", "-130"],
        ]

        # No EOY positions (both consumed)
        positions_end = [
            # empty
        ]

        # BUY cost: 130 * 167.56 + 2.00 commission = 21782.80 + 2.00 = 21784.80
        # SELL proceeds: 130 * 168.00 - 2.00 commission = 21840.00 - 2.00 = 21838.00
        # Gain = 21838.00 - 21784.80 = 53.20
        expected = ScenarioExpectedOutput(
            test_description="Current-year merger GZUR->SGBS then sell SGBS",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="SGBS",
                    realization_date="2023-08-22",
                    quantity_realized=Decimal("130"),
                    total_cost_basis_eur=Decimal("21784.80"),
                    total_realization_value_eur=Decimal("21838.00"),
                    gross_gain_loss_eur=Decimal("53.20"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="GZUR", eoy_quantity=Decimal("0")),
                ExpectedAssetEoyState(asset_identifier="SGBS", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_end_data=positions_end,
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

    def test_historical_merger_sell_in_current_year(self, mock_config_paths):
        """
        Merger in prior year, sell in current year.
        2022: BUY 130 GZUR, Merger GZUR->SGBS 1:1
        2023: SELL 130 SGBS -> uses GZUR's acquisition date and cost basis
        """
        tax_year = 2023
        account = "U_HIST_MERGER"
        fx_rate = Decimal("1.0")
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=fx_rate)

        # Historical trades (BUY in 2022) + current year SELL
        trades_data = [
            # Historical BUY 130 GZUR @ 167.56 EUR in 2022
            [account, "EUR", "STK", "", "GZUR", "GZUR Stock", "DE0000000015",
             "", "", "", "2022-03-01", "130", "167.56", "-2.00", "EUR",
             "BUY", "TX_BUY_GZUR", "", "", "CON_GZUR", "", "1", "O"],
            # Current-year SELL 130 SGBS @ 168.00 EUR
            [account, "EUR", "STK", "", "SGBS", "SGBS Stock", "JE0000000014",
             "", "", "", "2023-08-22", "-130", "168.00", "-2.00", "EUR",
             "SELL", "TX_SELL_SGBS", "", "", "CON_SGBS", "", "1", "C"],
        ]

        # Historical corporate action (2022) - dispose row only
        corp_actions_data = [
            [account, "GZUR", "GZUR(DE0000000015) MERGED(Acquisition) WITH SGBS 1 FOR 1",
             "DE0000000015", "2022-08-22", "TC", "TC", "900034051",
             "CON_GZUR", "", "", "EUR", "0", "0", "-21782.80", "-130"],
        ]

        # SOY positions: SGBS has 130 shares at start of 2023
        positions_start = [
            [account, "EUR", "STK", "", "SGBS", "SGBS Stock", "JE0000000014",
             "130", "21800.00", "167.69", "21784.80", "", "CON_SGBS", "", "1"],
        ]

        # No EOY positions (sold)
        positions_end = []

        expected = ScenarioExpectedOutput(
            test_description="Historical merger, sell in current year uses original cost basis",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="SGBS",
                    realization_date="2023-08-22",
                    quantity_realized=Decimal("130"),
                    total_cost_basis_eur=Decimal("21784.80"),
                    total_realization_value_eur=Decimal("21838.00"),
                    gross_gain_loss_eur=Decimal("53.20"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="SGBS", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=positions_end,
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

    def test_chained_mergers_historical(self, mock_config_paths):
        # Input: the intermediate merger asset BBB exists only in corporate
        # actions (AssetClass UNKNOWN) and needs the user's classification.
        self.seed_classification("CONID:CON_B", "STOCK")
        """
        Chained mergers in prior years:
        2021: BUY 50 AAA
        2021: Merger AAA->BBB 1:1
        2022: Merger BBB->CCC 2:1
        2023: SELL 100 CCC -> uses AAA's original acquisition date
        """
        tax_year = 2023
        account = "U_CHAIN_MERGER"
        fx_rate = Decimal("1.0")
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=fx_rate)

        trades_data = [
            # BUY 50 AAA @ 100.00 in 2021
            [account, "EUR", "STK", "", "AAA", "AAA Stock", "",
             "", "", "", "2021-06-01", "50", "100.00", "-1.00", "EUR",
             "BUY", "TX_BUY_A", "", "", "CON_A", "", "1", "O"],
            # SELL 100 CCC @ 55.00 in 2023
            [account, "EUR", "STK", "", "CCC", "CCC Stock", "",
             "", "", "", "2023-09-15", "-100", "55.00", "-1.00", "EUR",
             "SELL", "TX_SELL_C", "", "", "CON_C", "", "1", "C"],
        ]

        corp_actions_data = [
            # Merger AAA->BBB in 2021 (1:1 ratio)
            [account, "AAA", "AAA() MERGED(Acquisition) WITH BBB 1 FOR 1",
             "", "2021-09-01", "TC", "TC", "CA_A_TO_B",
             "CON_A", "", "", "EUR", "0", "0", "-5000.00", "-50"],
            # Merger BBB->CCC in 2022 (2:1 ratio)
            [account, "BBB", "BBB() MERGED(Acquisition) WITH CCC 2 FOR 1",
             "", "2022-06-01", "TC", "TC", "CA_B_TO_C",
             "CON_B", "", "", "EUR", "0", "0", "-5000.00", "-50"],
        ]

        # SOY: 100 shares of CCC at start of 2023
        positions_start = [
            [account, "EUR", "STK", "", "CCC", "CCC Stock", "",
             "100", "5500.00", "55.00", "5001.00", "", "CON_C", "", "1"],
        ]

        positions_end = []

        # Cost basis: BUY 50 A @ 100.00 + 1.00 commission = 5001.00
        # After A->B (1:1): 50 lots of B, total cost 5001.00
        # After B->C (2:1): 100 lots of C, total cost 5001.00
        # SELL 100 C @ 55.00 - 1.00 commission = 5499.00
        # Gain = 5499.00 - 5001.00 = 498.00
        expected = ScenarioExpectedOutput(
            test_description="Chained mergers AAA->BBB->CCC, sell CCC",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="CCC",
                    realization_date="2023-09-15",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("5001.00"),
                    total_realization_value_eur=Decimal("5499.00"),
                    gross_gain_loss_eur=Decimal("498.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="CCC", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=positions_end,
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

    def test_receive_row_filtered_by_parser(self, mock_config_paths):
        """
        Both dispose (qty=-130) and receive (qty=+130) CSV rows are present.
        Only one CorpActionMergerStock event should be created (from dispose row).
        """
        tax_year = 2023
        account = "U_PARSER_TEST"
        fx_rate = Decimal("1.0")
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=fx_rate)

        trades_data = [
            # BUY 130 GZUR
            [account, "EUR", "STK", "", "GZUR", "GZUR Stock", "DE0000000015",
             "", "", "", "2023-03-01", "130", "167.56", "-2.00", "EUR",
             "BUY", "TX_BUY_GZUR", "", "", "CON_GZUR", "", "1", "O"],
            # SELL 130 SGBS
            [account, "EUR", "STK", "", "SGBS", "SGBS Stock", "JE0000000014",
             "", "", "", "2023-08-22", "-130", "168.00", "-2.00", "EUR",
             "SELL", "TX_SELL_SGBS", "", "", "CON_SGBS", "", "1", "C"],
        ]

        # BOTH dispose and receive rows present (like real IBKR data)
        corp_actions_data = [
            # Dispose row (qty=-130)
            [account, "GZUR", "GZUR(DE0000000015) MERGED(Acquisition) WITH SGBS 1 FOR 1",
             "DE0000000015", "2023-08-22", "TC", "TC", "900034051",
             "CON_GZUR", "", "", "EUR", "0", "0", "-21782.80", "-130"],
            # Receive row (qty=+130) - should be skipped
            [account, "SGBS", "GZUR(DE0000000015) MERGED(Acquisition) WITH SGBS 1 FOR 1",
             "JE0000000014", "2023-08-22", "TC", "TC", "900034051",
             "CON_SGBS", "", "", "EUR", "0", "0", "21837.40", "130"],
        ]

        positions_end = []

        expected = ScenarioExpectedOutput(
            test_description="Parser filters receive row, only one merger event created",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="SGBS",
                    realization_date="2023-08-22",
                    quantity_realized=Decimal("130"),
                    total_cost_basis_eur=Decimal("21784.80"),
                    total_realization_value_eur=Decimal("21838.00"),
                    gross_gain_loss_eur=Decimal("53.20"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="GZUR", eoy_quantity=Decimal("0")),
                ExpectedAssetEoyState(asset_identifier="SGBS", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_end_data=positions_end,
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

    def test_merger_no_sell_eoy_correct(self, mock_config_paths):
        """
        Merger without subsequent sell — target should have correct EOY qty.
        """
        tax_year = 2023
        account = "U_NO_SELL"
        fx_rate = Decimal("1.0")
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=fx_rate)

        trades_data = [
            # BUY 100 XAAA
            [account, "EUR", "STK", "", "XAAA", "XAAA Stock", "",
             "", "", "", "2023-02-01", "100", "50.00", "-1.00", "EUR",
             "BUY", "TX_BUY_A", "", "", "CON_A", "", "1", "O"],
        ]

        corp_actions_data = [
            [account, "XAAA", "XAAA() MERGED(Acquisition) WITH XBBB 1 FOR 1",
             "", "2023-06-15", "TC", "TC", "CA_MERGE",
             "CON_A", "", "", "EUR", "0", "0", "-5000.00", "-100"],
        ]

        # EOY: XBBB has 100 shares
        positions_end = [
            [account, "EUR", "STK", "", "XBBB", "XBBB Stock", "",
             "100", "5200.00", "52.00", "5001.00", "", "CON_B", "", "1"],
        ]

        expected = ScenarioExpectedOutput(
            test_description="Merger without sell, EOY quantity correct",
            expected_rgls=[],  # No sell, no RGL
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="XAAA", eoy_quantity=Decimal("0")),
                ExpectedAssetEoyState(asset_identifier="XBBB", eoy_quantity=Decimal("100")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_end_data=positions_end,
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

    def test_merged_in_shares_sold_inside_the_historical_window(self, mock_config_paths):
        """
        The merger delivers shares that are disposed of *within* the historical
        window, and more of the target is bought later in that window.

        2022-03-01  BUY  40 ACME
        2022-06-15  merger ACME -> BETA 1:1        <- delivers 40 BETA
        2022-06-15  SELL 40 BETA                   <- same day, consumes them
        2023-04-10  BUY  25 BETA                   <- still held at SoY 2024
        2024-05-20  SELL 25 BETA

        Abs. 4a Satz 6 (GT-ESTG20-018) fixes the moment a Kapitalmassnahme takes
        effect at the Einbuchung into the depot, so the 40 BETA exist from
        2022-06-15 and that day's sale consumes them. The 25 units left at SoY
        2024 are then the 2023-04-10 purchase, and GT-ESTG20-015 requires the
        2024 disposal to be measured against it.

        **This test is deliberately blind to quantity, cost basis, proceeds and
        gain.** The SoY snapshot below reports a cost basis equal to the real
        2023-04-10 purchase cost, because that is what the broker reports, so a
        synthesised fallback lot reproduces all four figures exactly. Only the
        acquisition date separates a real reconstruction from a fabricated one
        -- the same discriminator, and the same reason, as
        `test_historical_merger_replay_guard.py`.
        """
        tax_year = 2024
        account = "U_MERGE_SELL_IN_WINDOW"
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        trades_data = [
            # 2022-03-01 BUY 40 ACME @ 50.00, commission 1.00 -> basis 2001.00
            [account, "EUR", "STK", "", "ACME", "ACME Stock", "DE0000000021",
             "", "", "", "2022-03-01", "40", "50.00", "-1.00", "EUR",
             "BUY", "TX_BUY_ACME", "", "", "CON_ACME", "", "1", "O"],
            # 2022-06-15 SELL 40 BETA -- same day as the merger that delivers them
            [account, "EUR", "STK", "", "BETA", "BETA Stock", "DE0000000022",
             "", "", "", "2022-06-15", "-40", "52.00", "-1.00", "EUR",
             "SELL", "TX_SELL_BETA_2022", "", "", "CON_BETA", "", "1", "C"],
            # 2023-04-10 BUY 25 BETA @ 60.00, commission 1.00 -> basis 1501.00
            [account, "EUR", "STK", "", "BETA", "BETA Stock", "DE0000000022",
             "", "", "", "2023-04-10", "25", "60.00", "-1.00", "EUR",
             "BUY", "TX_BUY_BETA_2023", "", "", "CON_BETA", "", "1", "O"],
            # 2024-05-20 SELL 25 BETA @ 64.00, commission 1.00 -> proceeds 1599.00
            [account, "EUR", "STK", "", "BETA", "BETA Stock", "DE0000000022",
             "", "", "", "2024-05-20", "-25", "64.00", "-1.00", "EUR",
             "SELL", "TX_SELL_BETA_2024", "", "", "CON_BETA", "", "1", "C"],
        ]

        corp_actions_data = [
            [account, "ACME", "ACME(DE0000000021) MERGED(Acquisition) WITH BETA 1 FOR 1",
             "DE0000000021", "2022-06-15", "TC", "TC", "900000021",
             "CON_ACME", "", "", "EUR", "0", "0", "-2001.00", "-40"],
        ]

        # SoY 2024: the 25 BETA bought on 2023-04-10, at their real cost.
        positions_start = [
            [account, "EUR", "STK", "", "BETA", "BETA Stock", "DE0000000022",
             "25", "1550.00", "62.00", "1501.00", "", "CON_BETA", "", "1"],
        ]

        expected = ScenarioExpectedOutput(
            test_description="Merged-in shares disposed of inside the historical window",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="BETA",
                    realization_date="2024-05-20",
                    quantity_realized=Decimal("25"),
                    total_cost_basis_eur=Decimal("1501.00"),
                    total_realization_value_eur=Decimal("1599.00"),
                    gross_gain_loss_eur=Decimal("98.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                    # The discriminator. A fallback lot would say 2023-12-31.
                    acquisition_date="2023-04-10",
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="BETA", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)

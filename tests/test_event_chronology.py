"""GT-ESTG20-011/013: consume the lots that exist at each transaction, in order."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domain.enums import AssetCategory, FinancialEventType
from src.domain.events import TradeEvent, OptionExerciseEvent, OptionAssignmentEvent
from src.utils.sorting_utils import get_event_sort_key


@pytest.mark.parametrize('lifecycle', [OptionExerciseEvent, OptionAssignmentEvent])
def test_opening_precedes_same_day_option_consumption(lifecycle):
    asset_id = uuid4()
    resolver = SimpleNamespace(get_asset_by_id=lambda _: SimpleNamespace(
        asset_category=AssetCategory.OPTION))
    opening = TradeEvent(asset_id, '2025-03-01', quantity=Decimal('1'),
        price_foreign_currency=Decimal('10'),
        event_type=FinancialEventType.TRADE_BUY_LONG,
        ibkr_transaction_id='100')
    closing = lifecycle(asset_id, '2025-03-01', quantity_contracts=Decimal('1'),
                        ibkr_transaction_id='200')
    assert sorted([closing, opening], key=lambda e: get_event_sort_key(e, resolver)) == [opening, closing]


def test_interleaved_option_openings_and_exercises_keep_broker_order():
    asset_id = uuid4()
    resolver = SimpleNamespace(get_asset_by_id=lambda _: SimpleNamespace(
        asset_category=AssetCategory.OPTION))
    events = []
    for tx in range(1, 5):
        if tx % 2:
            event = TradeEvent(asset_id, '2025-03-01', quantity=Decimal('1'),
                price_foreign_currency=Decimal(str(tx)),
                event_type=FinancialEventType.TRADE_BUY_LONG,
                ibkr_transaction_id=str(tx))
        else:
            event = OptionExerciseEvent(asset_id, '2025-03-01',
                quantity_contracts=Decimal('1'), ibkr_transaction_id=str(tx))
        events.append(event)
    assert sorted(reversed(events), key=lambda e: get_event_sort_key(e, resolver)) == events

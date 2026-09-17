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


def test_linked_stock_leg_waits_for_exercise_without_moving_opening():
    from src.domain.events import OptionDeliveryLink
    from src.processing.event_ordering import order_financial_events
    option_id, stock_id = uuid4(), uuid4()
    resolver = SimpleNamespace(get_asset_by_id=lambda asset_id: SimpleNamespace(
        asset_category=AssetCategory.OPTION if asset_id == option_id else AssetCategory.STOCK))
    opening = TradeEvent(option_id, '2025-03-01', quantity=Decimal('1'),
        price_foreign_currency=Decimal('2'), event_type=FinancialEventType.TRADE_BUY_LONG,
        account_id='A', ibkr_transaction_id='100')
    exercise = OptionExerciseEvent(option_id, '2025-03-01', quantity_contracts=Decimal('1'),
                                   account_id='A', ibkr_transaction_id='200')
    delivery = TradeEvent(stock_id, '2025-03-01', quantity=Decimal('100'),
        price_foreign_currency=Decimal('50'), event_type=FinancialEventType.TRADE_BUY_LONG,
        account_id='A', ibkr_transaction_id='150',
        option_delivery_links=[OptionDeliveryLink(exercise.event_id, Decimal('100'))])
    ordered = order_financial_events([delivery, exercise, opening], resolver)
    assert ordered == [opening, exercise, delivery]
    assert order_financial_events(reversed(ordered), resolver) == ordered
    assert sorted(ordered, key=lambda e: get_event_sort_key(e, resolver)) == ordered


def test_reciprocal_transfer_observations_must_agree_on_chronology():
    from src.domain.events import InternalTransferEvent
    from src.domain.exceptions import DataIntegrityError
    from src.processing.event_ordering import order_financial_events
    asset_id = uuid4()
    resolver = SimpleNamespace(get_asset_by_id=lambda _: SimpleNamespace(asset_category=AssetCategory.STOCK))
    outward = InternalTransferEvent(asset_id, '2025-03-01', quantity=Decimal('100'),
        account_id='A', to_account_id='B', source_transaction_ids=(('A', '100'), ('B', '300')))
    backward = InternalTransferEvent(asset_id, '2025-03-01', quantity=Decimal('100'),
        account_id='B', to_account_id='A', source_transaction_ids=(('B', '200'), ('A', '400')))
    with pytest.raises(DataIntegrityError, match='Conflicting same-day'):
        order_financial_events([outward, backward], resolver)


def test_sequenced_reciprocal_transfers_do_not_form_a_false_cycle():
    from src.domain.events import InternalTransferEvent
    from src.processing.event_ordering import order_financial_events
    asset_id = uuid4()
    resolver = SimpleNamespace(get_asset_by_id=lambda _: SimpleNamespace(asset_category=AssetCategory.STOCK))
    outward = InternalTransferEvent(asset_id, '2025-03-01', quantity=Decimal('100'),
        account_id='B', to_account_id='A', source_transaction_ids=(('B', '100'), ('A', '110')))
    backward = InternalTransferEvent(asset_id, '2025-03-01', quantity=Decimal('100'),
        account_id='A', to_account_id='B', source_transaction_ids=(('A', '200'), ('B', '210')))
    assert order_financial_events([backward, outward], resolver) == [outward, backward]

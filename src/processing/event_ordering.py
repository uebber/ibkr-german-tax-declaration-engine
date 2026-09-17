"""Stable same-day scheduling of explicit option and transfer dependencies.

Unrelated events retain the accepted order. Import establishes option links and
transfer-side observations; scheduling never changes account ledger contents.
"""
from collections import defaultdict
from heapq import heappop, heappush

from src.domain.events import InternalTransferEvent, OptionLifecycleEvent, OptionCashSettlementEvent, TradeEvent
from src.domain.enums import FinancialEventType as Kind
from src.domain.exceptions import DataIntegrityError
from src.utils.account_utils import account_key
from src.utils.sorting_utils import get_event_sort_key


def _transfer_tx(event, account):
    observations = dict(event.source_transaction_ids)
    value = observations.get(account)
    if value is None and len(observations) == 1:
        value = next(iter(observations.values()))
    return int(value) if value and value.isdecimal() else None


def order_financial_events(events, resolver):
    events = list(events)
    for event in events:
        event.resolved_day_position = None
    days = defaultdict(list)
    for event in sorted(events, key=lambda e: get_event_sort_key(e, resolver)):
        days[event.event_date].append(event)
    result = []
    for day, items in sorted(days.items()):
        by_id = {event.event_id: i for i, event in enumerate(items)}
        outgoing = [set() for _ in items]
        incoming = [0 for _ in items]

        def before(a, b):
            if a != b and b not in outgoing[a]:
                outgoing[a].add(b)
                incoming[b] += 1

        # Preserve option FIFO order and the original currency-affecting sequence.
        # Lifecycle events themselves have no additional cash flow; their stock
        # deliveries and option opening trades retain their own cash positions.
        last_cash = None
        last_ledger = {}
        transfers = []
        for i, event in enumerate(items):
            if isinstance(event, InternalTransferEvent):
                transfers.append(i)
                continue
            key = (account_key(event.account_id), event.asset_internal_id)
            if key in last_ledger:
                before(last_ledger[key], i)
            last_ledger[key] = i
            if not isinstance(event, OptionLifecycleEvent) or isinstance(event, OptionCashSettlementEvent):
                if last_cash is not None:
                    before(last_cash, i)
                last_cash = i
            for link in getattr(event, 'option_delivery_links', ()):
                if link.option_event_id not in by_id:
                    raise DataIntegrityError(f'Option delivery on {day} has no same-day exercise')
                before(by_id[link.option_event_id], i)

        for i in transfers:
            move = items[i]
            for j, event in enumerate(items):
                if i == j or event.asset_internal_id != move.asset_internal_id:
                    continue
                if isinstance(event, InternalTransferEvent):
                    shared = {move.account_id, move.to_account_id} & {event.account_id, event.to_account_id}
                    observations = [(_transfer_tx(move, a), _transfer_tx(event, a)) for a in shared]
                    observed = False
                    for left, right in observations:
                        if left is not None and right is not None and left != right:
                            before(i, j) if left < right else before(j, i)
                            observed = True
                    if observed:
                        continue
                    left_days = {lot.acquisition_date for lot in move.moved_lots}
                    right_days = {lot.acquisition_date for lot in event.moved_lots}
                    if (move.to_account_id == event.account_id
                            and (not left_days or not right_days or left_days & right_days)):
                        before(i, j)
                elif isinstance(event, TradeEvent):
                    account = account_key(event.account_id)
                    if account not in (move.account_id, move.to_account_id):
                        continue
                    transfer_tx = _transfer_tx(move, account)
                    tx = event.ibkr_transaction_id
                    if transfer_tx is not None and tx and tx.isdecimal() and int(tx) != transfer_tx:
                        before(i, j) if transfer_tx < int(tx) else before(j, i)
                        continue
                    # Without a broker sequence retain the documented delivery
                    # dependency: acquire in sender, transfer, consume in receiver.
                    opens = event.event_type in (Kind.TRADE_BUY_LONG, Kind.TRADE_SELL_SHORT_OPEN)
                    consumes = event.event_type in (Kind.TRADE_SELL_LONG, Kind.TRADE_BUY_SHORT_COVER)
                    if account == move.account_id and opens:
                        before(j, i)
                    if account == move.to_account_id and consumes:
                        before(i, j)

        ready = []
        for i, count in enumerate(incoming):
            if count == 0:
                heappush(ready, i)
        ordered = []
        while ready:
            i = heappop(ready)
            ordered.append(items[i])
            for j in outgoing[i]:
                incoming[j] -= 1
                if incoming[j] == 0:
                    heappush(ready, j)
        if len(ordered) != len(items):
            raise DataIntegrityError(f'Conflicting same-day transaction dependencies on {day}')
        for position, event in enumerate(ordered):
            event.resolved_day_position = position
        result.extend(ordered)
    return result

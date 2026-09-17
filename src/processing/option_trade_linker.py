"""Account-local physical option deliveries (GT-ESTG20-013).

Match economic identity before allocating quantities. Same-contract partial
executions are allocated in the broker order within each leg. Different option
contracts that cannot be distinguished by the stock export are an ambiguity,
never a dictionary overwrite. Linking does not choose the tax treatment.
"""
from collections import defaultdict
from decimal import Decimal
import logging

from src.domain.assets import Option, Stock
from src.domain.events import OptionExerciseEvent, OptionAssignmentEvent, OptionDeliveryLink
from src.domain.exceptions import DataIntegrityError
from src.utils.account_utils import account_key

logger = logging.getLogger(__name__)


def _action(event):
    codes = {c.strip().upper() for c in (event.ibkr_notes_codes or '').split(';')}
    if 'EX' in codes:
        return 'EX'
    if 'A' in codes:
        return 'A'
    return None


def _order(event):
    return event.ibkr_transaction_id or '', event.creation_sequence


def perform_option_trade_linking(asset_resolver, candidate_option_lifecycle_events,
                                candidate_stock_trades_for_linking):
    options, stocks = defaultdict(list), defaultdict(list)
    errors = []
    for event in candidate_option_lifecycle_events:
        if not isinstance(event, (OptionExerciseEvent, OptionAssignmentEvent)):
            continue
        asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
        # Cash-settled options have a separate OptionEAE pairing and no stock leg.
        if not isinstance(asset, Option) or asset.underlying_asset_internal_id is None:
            continue
        # PM-005 repairs the existing Stock premium channel. Fund/other underlying
        # treatment is a separate pre-existing gap, not a new import rejection.
        underlying = asset_resolver.get_asset_by_id(asset.underlying_asset_internal_id)
        if not isinstance(underlying, Stock):
            continue
        if asset.strike_price is None or asset.multiplier is None or asset.multiplier <= 0:
            errors.append(f'Option {event.ibkr_transaction_id}: missing strike/multiplier')
            continue
        exercised = isinstance(event, OptionExerciseEvent)
        buys_stock = (asset.option_type == 'C') == exercised
        key = (account_key(event.account_id), event.event_date,
               asset.underlying_asset_internal_id, 'EX' if exercised else 'A',
               buys_stock, asset.strike_price, event.local_currency)
        options[key].append((event, event.quantity_contracts * asset.multiplier))

    for trade in candidate_stock_trades_for_linking:
        asset = asset_resolver.get_asset_by_id(trade.asset_internal_id)
        action = _action(trade)
        if not isinstance(asset, Stock) or action is None:
            continue
        key = (account_key(trade.account_id), trade.event_date, trade.asset_internal_id,
               action, trade.quantity > 0, trade.price_foreign_currency, trade.local_currency)
        stocks[key].append(trade)

    prepared = []
    for key in options.keys() | stocks.keys():
        source = sorted(options.get(key, []), key=lambda item: _order(item[0]))
        target = sorted(stocks.get(key, []), key=_order)
        label = f'account {key[0]}, {key[1]}, {key[3]}'
        source_total = sum((qty for _, qty in source), Decimal('0'))
        target_total = sum((e.quantity.copy_abs() for e in target), Decimal('0'))
        if not source:
            # Preserve the existing stock-only history path. Repairing matching
            # must not newly reject earlier acquisitions supplied without their
            # option history (e.g. dividend-rights scenarios). No premium is
            # invented and no delivered stock value is changed on this path.
            logger.warning('%s: stock delivery has no supplied option event; '
                           'retaining the existing unadjusted stock-history treatment', label)
            continue
        if not target or source_total != target_total:
            errors.append(f'{label}: unmatched option/stock delivery quantities; '
                          f'options={source_total}, stock={target_total}')
            continue
        if len({event.asset_internal_id for event, _ in source}) != 1:
            errors.append(f'{label}: ambiguous contracts share the same delivery terms')
            continue
        index, remaining = 0, source[0][1]
        for trade in target:
            wanted = trade.quantity.copy_abs()
            links = []
            while wanted:
                event, _ = source[index]
                take = min(wanted, remaining)
                links.append(OptionDeliveryLink(event.event_id, take))
                wanted -= take
                remaining -= take
                if remaining == 0 and index + 1 < len(source):
                    index += 1
                    remaining = source[index][1]
            prepared.append((trade, links))
    if errors:
        raise DataIntegrityError('Option delivery linking failed:\n  ' + '\n  '.join(sorted(errors)))
    for trade, links in prepared:
        trade.option_delivery_links = links

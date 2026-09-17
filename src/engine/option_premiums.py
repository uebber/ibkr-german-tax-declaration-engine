"""Single-use, account-owned premium allocations for linked stock deliveries.

GT-ESTG20-013: another account cannot consume this account's option premium.
The existing exercise/assignment treatment is applied by the trade processor;
this boundary preserves identity, quantity and amount through partial legs.
"""
from dataclasses import dataclass
from decimal import Decimal, getcontext

from src.domain.exceptions import ProcessingError
from src.utils.account_utils import account_key


@dataclass
class PendingPremium:
    amount: Decimal
    quantity: Decimal
    underlying_id: object
    option_type: str
    date: str


class OptionPremiumBook:
    def __init__(self, context=None):
        self._pending = {}
        self._recorded = set()
        self._consumed_deliveries = set()
        self.ctx = (context or getcontext()).copy()

    def record(self, event, asset, amount):
        key = (account_key(event.account_id), event.event_id)
        if key in self._recorded:
            raise ProcessingError('Option premium was recorded twice')
        self._recorded.add(key)
        self._pending[key] = PendingPremium(amount,
            self.ctx.multiply(event.quantity_contracts, asset.multiplier), asset.underlying_asset_internal_id,
            asset.option_type, event.event_date)

    def consume(self, trade):
        """Validate all allocations before consuming any; final slice gets the remainder."""
        if trade.event_id in self._consumed_deliveries:
            raise ProcessingError('Option delivery allocation was already consumed')
        requested = {}
        for link in trade.option_delivery_links:
            if link.quantity <= 0:
                raise ProcessingError('Option delivery quantity must be positive')
            requested[link.option_event_id] = requested.get(link.option_event_id, Decimal('0')) + link.quantity
        if sum(requested.values(), Decimal('0')) != trade.quantity.copy_abs():
            raise ProcessingError('Option delivery allocation does not match the stock quantity')
        prepared = []
        for option_id, quantity in requested.items():
            key = (account_key(trade.account_id), option_id)
            premium = self._pending.get(key)
            if premium is None:
                raise ProcessingError('Missing account-owned option premium; wrong order or repeated delivery')
            if (premium.underlying_id != trade.asset_internal_id or premium.date != trade.event_date
                    or quantity > premium.quantity):
                raise ProcessingError('Option delivery does not match its premium allocation')
            amount = (premium.amount if quantity == premium.quantity else
                      self.ctx.divide(self.ctx.multiply(premium.amount, quantity), premium.quantity))
            prepared.append((key, premium, quantity, amount))
        result = []
        for key, premium, quantity, amount in prepared:
            result.append((amount, premium.option_type))
            premium.amount = self.ctx.subtract(premium.amount, amount)
            premium.quantity = self.ctx.subtract(premium.quantity, quantity)
            if premium.quantity == 0:
                del self._pending[key]
        self._consumed_deliveries.add(trade.event_id)
        return result

    def require_empty(self):
        if self._pending:
            raise ProcessingError('Unconsumed option premium allocations remain after stock deliveries')

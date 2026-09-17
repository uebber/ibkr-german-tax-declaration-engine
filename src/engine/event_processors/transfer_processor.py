"""Coordinate account-local delivery and receipt (GT-ESTG20-014).

Both replay paths use this coordinator. Each ledger prepares only its own state.
All validation and sorting finish before either prepared state is committed.
"""
from src.domain.events import InternalTransferEvent
from src.domain.exceptions import ProcessingError
from src.utils.account_utils import account_key
from .base_processor import EventProcessor


def apply_internal_transfer(event, fifo_ledgers, asset_resolver, data_gap_collector=None):
    source_key = (account_key(event.account_id), event.asset_internal_id)
    target_key = (account_key(event.to_account_id), event.asset_internal_id)
    if source_key == target_key:
        raise ProcessingError('A transfer must name two different accounts')
    source = fifo_ledgers.get(source_key)
    target = fifo_ledgers.get(target_key)
    if source is None or target is None:
        raise ProcessingError('Internal transfer has no sending or receiving ledger')
    asset = asset_resolver.get_asset_by_id(event.asset_internal_id) if asset_resolver else None
    name = asset.get_classification_key() if asset else str(event.asset_internal_id)
    delivery, source_state = source.prepare_transfer_delivery(event, name, data_gap_collector)
    target_state = target.prepare_transfer_receipt(delivery)
    source.commit_transfer_state(source_state)
    target.commit_transfer_state(target_state)


class InternalTransferProcessor(EventProcessor):
    def process(self, event, ledger, context):
        if not isinstance(event, InternalTransferEvent):
            raise ProcessingError('InternalTransferProcessor requires an internal transfer')
        # The processor submits a move to the coordinator; it receives no peer ledger.
        context['transfer_coordinator'](event)
        return []

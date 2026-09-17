"""Independent PR88 review probes. All accounts and figures are synthetic.

GT-ESTG20-011/013/014/022: transfers preserve actual lots, their costs and
provenance; a move cannot manufacture history or silently select another lot.
"""
from decimal import Decimal
import pytest

from src.domain.exceptions import DataIntegrityError
from src.processing.data_gaps import DataGapError
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import position_row, trade_row, transfer_row
from tests.test_transfers_parser import _moves

ISIN = 'US000000TR01'

class TestIncomingHistory(FifoTestCaseBase):
    @pytest.mark.parametrize('short', [False, True])
    def test_current_year_transfer_cannot_bypass_history_guard(self, short):
        qty = '-100' if short else '100'
        with pytest.raises(DataGapError, match='SECURITIES_ACQUISITION_HISTORY_UNKNOWN'):
            out = self._run_pipeline(
                trades_data=[trade_row('B', ISIN, '2025-06-01', '100' if short else '-100',
                    '20', 'BUY' if short else 'SELL', 'C', 'SALE')],
                positions_start_data=[position_row('A', ISIN, qty, '-1013' if short else '1013')],
                positions_end_data=[],
                transfers_data=[transfer_row('A', 'B', 'OUT', '20250301', isin=ISIN,
                    quantity=qty, tx_id='MOVE')],
                custom_rate_provider=MockECBExchangeRateProvider(Decimal('1')),
                tax_year=2025)
            assert out.eoy_mismatch_error_count == 0
            assert len(out.realized_gains_losses) == 1
            assert out.realized_gains_losses[0].acquisition_date == '2024-12-31'

class TestRelayChronology(FifoTestCaseBase):
    def test_same_day_relay_uses_delivery_dependencies(self):
        out = self._run_pipeline(
            trades_data=[trade_row('B', ISIN, '2023-01-15', '100', '10.13', 'BUY', 'O', 'BUY')],
            positions_start_data=[position_row('B', ISIN, '100', '1013'),
                                  position_row('A', ISIN, '0', '0')],
            positions_end_data=[position_row('C', ISIN, '100', '1013')],
            transfers_data=[
                transfer_row('B', 'A', 'OUT', '20250301', isin=ISIN, quantity='100', tx_id='100'),
                transfer_row('A', 'C', 'OUT', '20250301', isin=ISIN, quantity='100', tx_id='200')],
            custom_rate_provider=MockECBExchangeRateProvider(Decimal('1')),
            tax_year=2025)
        assert out.eoy_mismatch_error_count == 0

def side(client, other, direction, day, tx):
    return [transfer_row(client, other, direction, '20240601', isin=ISIN,
                        quantity='100', tx_id=tx),
            transfer_row(client, other, direction, '20240601', isin=ISIN,
                        quantity='100', level_of_detail='LOT', open_date_time=day)]

def test_two_distinct_equal_sized_moves_are_not_dropped(tmp_path):
    rows = side('A', 'B', 'OUT', '20230115', '100') + side('A', 'B', 'OUT', '20230215', '200')
    moves = _moves(tmp_path, rows)
    assert len(moves) == 2
    assert {m.moved_lots[0].acquisition_date for m in moves} == {'2023-01-15', '2023-02-15'}

@pytest.mark.parametrize('reverse', [False, True])
def test_disagreeing_sides_do_not_silently_choose_a_lot(tmp_path, reverse):
    groups = [side('A', 'B', 'OUT', '20230115', '100'),
              side('B', 'A', 'IN', '20230215', '200')]
    if reverse:
        groups.reverse()
    with pytest.raises(DataIntegrityError):
        _moves(tmp_path, sum(groups, []))

def test_agreeing_sides_collapse_once(tmp_path):
    moves = _moves(tmp_path, side('A', 'B', 'OUT', '20230115', '100')
                   + side('B', 'A', 'IN', '20230115', '200'))
    assert len(moves) == 1
    assert moves[0].moved_lots[0].acquisition_date == '2023-01-15'


def test_receiving_failure_cannot_remove_source_lots():
    from uuid import uuid4
    from src.domain.events import InternalTransferEvent
    from src.domain.exceptions import ProcessingError
    from src.engine.event_processors.transfer_processor import apply_internal_transfer
    from tests.test_stock_merger_fifo import _make_ledger, _make_long_lot, _make_short_lot
    asset_id = uuid4()
    source, target = _make_ledger(asset_id), _make_ledger(asset_id)
    lot = _make_long_lot('2023-01-15', '100', '10', 'OPEN')
    source.lots = [lot]
    target.short_lots = [_make_short_lot('2024-01-15', '50', '20', 'SHORT')]
    event = InternalTransferEvent(asset_id, '2025-03-01', account_id='A',
                                  to_account_id='B', quantity=Decimal('100'))
    with pytest.raises(ProcessingError, match='combine long and short'):
        apply_internal_transfer(event, {('A', asset_id): source, ('B', asset_id): target}, None)
    assert source.lots == [lot] and source.lots[0] is lot
    assert not target.lots
    assert target.short_lots[0].quantity_shorted == Decimal('50')


def test_duplicate_day_details_cannot_duplicate_lot_objects():
    from uuid import uuid4
    from src.domain.events import InternalTransferEvent, TransferLot
    from src.engine.event_processors.transfer_processor import apply_internal_transfer
    from tests.test_stock_merger_fifo import _make_ledger, _make_long_lot
    asset_id = uuid4()
    source, target = _make_ledger(asset_id), _make_ledger(asset_id)
    lot = _make_long_lot('2023-01-15', '100', '10', 'OPEN')
    source.lots = [lot]
    event = InternalTransferEvent(asset_id, '2025-03-01', account_id='A',
        to_account_id='B', quantity=Decimal('200'),
        moved_lots=[TransferLot('2023-01-15', Decimal('100'))] * 2)
    with pytest.raises(DataGapError):
        apply_internal_transfer(event, {('A', asset_id): source, ('B', asset_id): target}, None)
    assert source.lots[0] is lot and not target.lots


def test_transfer_preserves_identity_provenance_and_accrual():
    from uuid import uuid4
    from src.domain.events import InternalTransferEvent
    from src.engine.event_processors.transfer_processor import apply_internal_transfer
    from tests.test_stock_merger_fifo import _make_ledger, _make_long_lot
    asset_id = uuid4()
    source, target = _make_ledger(asset_id), _make_ledger(asset_id)
    lot = _make_long_lot('2023-01-15', '100', '10', 'OPEN')
    lot.acquisition_date_is_known = False
    lot.vorabpauschale_gross_eur = Decimal('12')
    source.lots = [lot]
    event = InternalTransferEvent(asset_id, '2025-03-01', account_id='A',
                                  to_account_id='B', quantity=Decimal('100'))
    apply_internal_transfer(event, {('A', asset_id): source, ('B', asset_id): target}, None)
    assert not source.lots and target.lots[0] is lot
    assert not target.lots[0].acquisition_date_is_known
    assert target.lots[0].vorabpauschale_gross_eur == Decimal('12')


def test_paired_transfer_retains_both_source_observations(tmp_path):
    moves = _moves(tmp_path, side('A', 'B', 'OUT', '20230115', '100')
                   + side('B', 'A', 'IN', '20230115', '200'))
    assert set(moves[0].source_transaction_ids) == {('A', '100'), ('B', '200')}

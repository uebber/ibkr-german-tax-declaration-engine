"""PR87: incomplete lot history and unclassified fee refunds must not emit figures.

GT-ESTG20-011/013/014/022 require the actual lot's costs and acquisition history.
GT-ESTG20-010/048 distinguish reimbursements from a return of invested capital.
All inputs are synthetic.
"""
from decimal import Decimal
import pytest

from src.domain.exceptions import DataIntegrityError
from src.pipeline_runner import run_core_processing_pipeline
from src.processing.data_gaps import DataGapError
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_TRANSACTIONS_COLUMNS, CORPORATE_ACTIONS_COLUMNS,
    trade_row, position_row, cash_transaction_row, write_csv,
)


def run_case(tmp_path, *, trades=(), opening=(), closing=(), cash=(), marks=None):
    kwargs = {}
    for name, columns, rows in (
        ('trades', TRADES_COLUMNS, trades), ('positions_start', POSITIONS_COLUMNS, opening),
        ('positions_end', POSITIONS_COLUMNS, closing),
        ('cash_transactions', CASH_TRANSACTIONS_COLUMNS, cash),
        ('corporate_actions', CORPORATE_ACTIONS_COLUMNS, ()),
    ):
        path = tmp_path / (name + '.csv')
        write_csv(str(path), columns, list(rows))
        kwargs[name + '_file_path'] = str(path)
    mark_paths = {}
    for year, rows in (marks or {}).items():
        path = tmp_path / f'mark-{year}.csv'
        write_csv(str(path), POSITIONS_COLUMNS, rows)
        mark_paths[year] = str(path)
    return run_core_processing_pipeline(**kwargs, positions_mark_file_paths=mark_paths,
        tax_year_to_process=2025, interactive_classification_mode=False,
        custom_rate_provider=MockECBExchangeRateProvider(Decimal('1')))


@pytest.mark.parametrize('short', [False, True])
@pytest.mark.parametrize('checkpoint', [False, True])
def test_untraced_receiving_account_refuses_disposal(tmp_path, short, checkpoint):
    isin = 'US000000FIX1'
    opening = [position_row('B', isin, '-100' if short else '100', '-1000' if short else '1000')]
    trades = [
        trade_row('A', isin, '2023-05-01', '-100' if short else '100', '10',
                  'SELL' if short else 'BUY', 'O', 'OPEN'),
        trade_row('B', isin, '2025-06-01', '100' if short else '-100', '20',
                  'BUY' if short else 'SELL', 'C', 'CLOSE'),
    ]
    with pytest.raises(DataGapError, match='SECURITIES_ACQUISITION_HISTORY_UNKNOWN'):
        run_case(tmp_path, trades=trades, opening=opening,
                 marks={2023: opening} if checkpoint else None)


def test_all_affected_accounts_are_named_before_processing(tmp_path):
    opening = [position_row(a, isin, '100', '1000')
               for a, isin in [('B', 'US000000FIX1'), ('C', 'US111111FIX2')]]
    trades = [trade_row(a, isin, '2025-06-01', '-100', '20', 'SELL', 'C', a)
              for a, isin in [('B', 'US000000FIX1'), ('C', 'US111111FIX2')]]
    with pytest.raises(DataGapError) as error:
        run_case(tmp_path, trades=trades, opening=opening)
    assert 'US000000FIX1' in str(error.value)
    assert 'US111111FIX2' in str(error.value)


def test_known_account_history_still_produces_a_disposal(tmp_path):
    isin = 'US000000FIX1'
    out = run_case(tmp_path, trades=[
        trade_row('B', isin, '2023-05-01', '100', '10', 'BUY', 'O', 'OPEN'),
        trade_row('B', isin, '2025-06-01', '-100', '20', 'SELL', 'C', 'CLOSE')],
        opening=[position_row('B', isin, '100', '1000')])
    assert out.realized_gains_losses[0].acquisition_date == '2023-05-01'


@pytest.mark.parametrize('account', ['', 'A'])
@pytest.mark.parametrize('kind', ['Deposits/Withdrawals', 'Commission Adjustments'])
def test_unattributed_positive_commission_is_not_a_capital_repayment(tmp_path, account, kind):
    with pytest.raises(DataIntegrityError, match='COMMISSION_REFUND_UNCLASSIFIED'):
        run_case(tmp_path, cash=[cash_transaction_row(account, 'USD', '10', kind,
            '2025-06-01', description='ADJUSTMENT: COMMISSION', tx_id='REFUND')])


def test_unclassified_refunds_are_collected(tmp_path):
    with pytest.raises(DataIntegrityError) as error:
        run_case(tmp_path, cash=[cash_transaction_row('A', 'EUR', '10', 'Deposits/Withdrawals',
            '2025-06-01', description='ADJUSTMENT: COMMISSION', tx_id=tx) for tx in ['REFUND1', 'REFUND2']])
    assert 'REFUND1' in str(error.value) and 'REFUND2' in str(error.value)


@pytest.mark.parametrize('short', [False, True])
def test_merger_cannot_turn_unknown_history_into_known_history(short):
    from uuid import uuid4
    from tests.test_stock_merger_fifo import _make_ledger, _make_long_lot, _make_short_lot, _make_merger_event
    source, target = uuid4(), uuid4()
    ledger = _make_ledger(target)
    make_lot = _make_short_lot if short else _make_long_lot
    lot = make_lot('2024-12-31', '10', '20', 'UNCONFIRMED')
    lot.acquisition_date_is_known = False
    ledger.receive_all_lots_from_merger([] if short else [lot], [lot] if short else [],
        Decimal('2'), _make_merger_event(source, target))
    received = (ledger.short_lots if short else ledger.lots)[0]
    assert not getattr(received, 'acquisition_date_is_known', True)
    assert ledger.has_unresolved_acquisition_history()

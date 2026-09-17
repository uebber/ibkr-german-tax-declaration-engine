"""PR87: preserve lot provenance and the direction of commission corrections.

GT-ESTG20-011/013/014/022 require the actual lot's costs and acquisition history.
GT-ESTG20-010/048 distinguish reimbursements from a return of invested capital.
All inputs are synthetic.
"""
from decimal import Decimal
import pytest

from src.domain.events import FeeEvent
from src.pipeline_runner import run_core_processing_pipeline
from src.processing.data_gaps import DataGapError
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_TRANSACTIONS_COLUMNS, CORPORATE_ACTIONS_COLUMNS,
    CASH_BALANCE_COLUMNS, cash_balance_row, trade_row, position_row, cash_transaction_row, write_csv,
)


def run_case(tmp_path, *, trades=(), opening=(), closing=(), cash=(), marks=None, balances=()):
    kwargs = {}
    for name, columns, rows in (
        ('trades', TRADES_COLUMNS, trades), ('positions_start', POSITIONS_COLUMNS, opening),
        ('positions_end', POSITIONS_COLUMNS, closing),
        ('cash_transactions', CASH_TRANSACTIONS_COLUMNS, cash),
        ('corporate_actions', CORPORATE_ACTIONS_COLUMNS, ()),
        ('cash_balance', CASH_BALANCE_COLUMNS, balances),
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
@pytest.mark.parametrize('opening_balance', ['100', '-100'])
def test_commission_refund_credits_cash_once(tmp_path, account, kind, opening_balance):
    out = run_case(tmp_path, cash=[cash_transaction_row(account, 'USD', '10', kind,
        '2025-06-01', description='ADJUSTMENT: COMMISSION', tx_id='REFUND')],
        balances=[cash_balance_row(account, 'USD', opening_balance, Decimal(opening_balance) + 10)])
    assert not any(g.code == 'CURRENCY_EOY_MISMATCH' for g in out.data_gaps)
    refunds = [e for e in out.processed_income_events if e.ibkr_transaction_id == 'REFUND']
    assert len(refunds) == 1 and isinstance(refunds[0], FeeEvent)
    assert refunds[0].is_refund
    assert refunds[0].gross_amount_foreign_currency == Decimal('10')
    assert all(r.gross_gain_loss_eur == 0 for r in out.realized_gains_losses)


def test_each_commission_refund_is_preserved(tmp_path):
    out = run_case(tmp_path, cash=[cash_transaction_row('A', 'EUR', '10', 'Deposits/Withdrawals',
        '2025-06-01', description='ADJUSTMENT: COMMISSION', tx_id=tx) for tx in ['REFUND1', 'REFUND2']])
    refunds = [e for e in out.processed_income_events if isinstance(e, FeeEvent)]
    assert {e.ibkr_transaction_id for e in refunds} == {'REFUND1', 'REFUND2'}
    assert all(e.is_refund for e in refunds)


@pytest.mark.parametrize('kind', ['Deposits/Withdrawals', 'Commission Adjustments'])
def test_additional_commission_remains_a_cash_charge(tmp_path, kind):
    out = run_case(tmp_path, cash=[cash_transaction_row('A', 'USD', '-10', kind,
        '2025-06-01', description='ADJUSTMENT: COMMISSION', tx_id='CHARGE')],
        balances=[cash_balance_row('A', 'USD', '100', '90')])
    assert not any(g.code == 'CURRENCY_EOY_MISMATCH' for g in out.data_gaps)
    fees = [e for e in out.processed_income_events if isinstance(e, FeeEvent)]
    assert len(fees) == 1 and not fees[0].is_refund


def test_historical_refund_creates_currency_instead_of_consuming_it():
    from uuid import uuid4
    from decimal import Context
    from src.domain.enums import AssetCategory
    from src.engine.calculation_engine import _apply_historical_currency_event
    from tests.test_stock_merger_fifo import _make_ledger
    ledger = _make_ledger(uuid4(), AssetCategory.CASH_BALANCE)
    refund = FeeEvent(ledger.asset_internal_id, '2024-06-01',
        gross_amount_foreign_currency=Decimal('10'), gross_amount_eur=Decimal('20'),
        local_currency='USD', ibkr_transaction_id='REFUND')
    refund.is_refund = True
    assert _apply_historical_currency_event(refund, ledger, 'USD', ledger.currency_converter, Context(prec=28)) == 1
    assert not ledger.short_lots
    assert sum(lot.quantity for lot in ledger.lots) == Decimal('10')
    assert sum(lot.total_cost_basis_eur for lot in ledger.lots) == Decimal('20')


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

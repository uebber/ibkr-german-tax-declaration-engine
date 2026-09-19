"""PM-005: GT-ESTG20-013 account ownership and exact single-use delivery links.

These tests compare ownership and conservation. They do not choose a new tax
treatment for option premiums. Every identifier and amount is synthetic.
"""
from decimal import Decimal

import pytest

from src.domain.exceptions import DataIntegrityError
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.option_helpers import create_option_trade_data, create_stock_trade_data
from tests.support.multi_account import (TRADES_COLUMNS, POSITIONS_COLUMNS,
    CASH_TRANSACTIONS_COLUMNS, CORPORATE_ACTIONS_COLUMNS, position_row, write_csv)
from src.pipeline_runner import run_core_processing_pipeline


def option(account, tx, *, when='2025-06-20', opening=False, premium='2',
           contracts='1', kind='C', assigned=False, strike='50', conid='880002', expiry='2025-06-20'):
    return create_option_trade_data(
        account_id=account, currency='EUR', symbol=f'{kind} REVIEW {expiry.replace("-", "")} {strike} M',
        description=f'REVIEW {expiry} {strike} {kind}', underlying_symbol='REVIEW',
        underlying_conid='880001', option_conid=conid, strike=Decimal(strike),
        expiry_date=expiry, option_type=kind, trade_date=when,
        trade_type=('SSO' if assigned else 'BL') if opening else ('BSC' if assigned else 'SL'),
        quantity=Decimal(contracts), price=Decimal(premium) if opening else Decimal('0'),
        commission=Decimal('0'), transaction_id=tx,
        notes_codes='' if opening else ('A' if assigned else 'Ex'))


def stock(account, tx, *, when='2025-06-20', qty='100', price='50', kind='C', assigned=False, sale=False):
    buy = (kind == 'C') != assigned
    if sale:
        buy = not buy
    return create_stock_trade_data(
        account_id=account, currency='EUR', symbol='REVIEW', description='REVIEW STOCK',
        isin='US000000RV88', conid='880001', trade_date=when,
        trade_type=('BSC' if buy else 'SL') if sale else ('BL' if buy else 'SSO'),
        quantity=Decimal(qty), price=Decimal(price),
        commission=Decimal('0'), transaction_id=tx,
        notes_codes='' if sale else ('A' if assigned else 'Ex'))


class TestOptionDeliveryIntegrity(FifoTestCaseBase):
    def run_rows(self, rows):
        holdings = {}
        for values in rows:
            row = dict(zip(TRADES_COLUMNS, values))
            if row['AssetClass'] == 'STK':
                account = row['ClientAccountID']
                holdings[account] = holdings.get(account, Decimal('0')) + Decimal(str(row['Quantity']))
        kwargs = {}
        for name, key, columns, data in (
            ('trades', 'trades', TRADES_COLUMNS, rows),
            ('positions_start', 'pos_start', POSITIONS_COLUMNS, []),
            ('positions_end', 'pos_end', POSITIONS_COLUMNS,
             [position_row(a, 'US000000RV88', q, q * 50) for a, q in holdings.items()]),
            ('cash_transactions', 'cash', CASH_TRANSACTIONS_COLUMNS, []),
            ('corporate_actions', 'corp_actions', CORPORATE_ACTIONS_COLUMNS, []),
        ):
            path = self.config_paths[key]
            write_csv(path, columns, data)
            kwargs[name + '_file_path'] = path
        return run_core_processing_pipeline(**kwargs, tax_year_to_process=2025,
            interactive_classification_mode=False,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal('1')))

    @pytest.mark.parametrize('kind,assigned', [('C', False), ('P', False), ('C', True), ('P', True)])
    @pytest.mark.parametrize('reverse', [False, True])
    def test_identical_exercises_in_two_accounts_keep_separate_links(self, kind, assigned, reverse):
        rows = []
        for account, premium in [('A', '2'), ('B', '7')]:
            rows.extend([option(account, '10'+account, when='2025-01-02', opening=True,
                                premium=premium, kind=kind, assigned=assigned),
                         option(account, '20'+account, kind=kind, assigned=assigned),
                         # Opposite stock-leg order must not swap account premiums.
                         stock(account, '30'+('B' if account == 'A' else 'A'), kind=kind, assigned=assigned),
                         stock(account, '40'+account, kind=kind, assigned=assigned, sale=True,
                               when='2025-07-01', price='70')])
        if reverse:
            rows.reverse()
        out = self.run_rows(rows)
        # Holdings are intentionally left open; inspect the parsed delivery links.
        deliveries = [e for e in out.all_financial_events_enriched if getattr(e, 'option_delivery_links', ())]
        assert len(deliveries) == 2
        by_id = {e.event_id: e for e in out.all_financial_events_enriched}
        for delivery in deliveries:
            assert len(delivery.option_delivery_links) == 1
            linked = by_id[delivery.option_delivery_links[0].option_event_id]
            assert linked.account_id == delivery.account_id
        def figures(result):
            return [(r.realization_type.name, r.quantity_realized, r.gross_gain_loss_eur)
                    for r in result.realized_gains_losses]
        separate = []
        for account in ('A', 'B'):
            separate.extend(figures(self.run_rows([r for r in rows if r[0] == account])))
        assert sorted(figures(out)) == sorted(separate)

    def test_one_exercise_can_deliver_several_stock_rows(self):
        out = self.run_rows([
            option('A', '100', when='2025-01-02', opening=True, contracts='2'),
            option('A', '200', contracts='2'), stock('A', '300', qty='50'),
            stock('A', '400', qty='150')])
        deliveries = [e for e in out.all_financial_events_enriched if getattr(e, 'option_delivery_links', ())]
        assert len(deliveries) == 2
        assert sum(e.net_proceeds_or_cost_basis_eur for e in deliveries) == Decimal('10400')

    def test_several_exercises_can_deliver_one_stock_row(self):
        out = self.run_rows([
            option('A', '100', when='2025-01-02', opening=True, contracts='2'),
            option('A', '200'), option('A', '201'), stock('A', '300', qty='200')])
        deliveries = [e for e in out.all_financial_events_enriched if getattr(e, 'option_delivery_links', ())]
        assert len(deliveries) == 1
        assert len(deliveries[0].option_delivery_links) == 2
        assert deliveries[0].net_proceeds_or_cost_basis_eur == Decimal('10400')

    def test_distinct_strikes_disambiguate_same_day_exercises(self):
        out = self.run_rows([
            option('A', '100', when='2025-01-02', opening=True),
            option('A', '101', when='2025-01-02', opening=True, strike='60', conid='880003'),
            option('A', '200'), option('A', '201', strike='60', conid='880003'),
            stock('A', '300', price='60'), stock('A', '301')])
        deliveries = [e for e in out.all_financial_events_enriched if getattr(e, 'option_delivery_links', ())]
        by_id = {e.event_id: e for e in out.all_financial_events_enriched}
        assert len(deliveries) == 2
        for delivery in deliveries:
            opt = by_id[delivery.option_delivery_links[0].option_event_id]
            asset = out.asset_resolver.get_asset_by_id(opt.asset_internal_id)
            assert asset.strike_price == delivery.price_foreign_currency

    def test_indistinguishable_contracts_are_collected_as_ambiguous(self):
        with pytest.raises(DataIntegrityError, match='ambiguous'):
            self.run_rows([
                option('A', '100', when='2025-01-02', opening=True),
                option('A', '101', when='2025-01-02', opening=True, conid='880003', expiry='2025-07-20'),
                option('A', '200'), option('A', '201', conid='880003', expiry='2025-07-20'),
                stock('A', '300'), stock('A', '301')])

    @pytest.mark.parametrize('reverse', [False, True])
    def test_interleaved_same_day_exercises_keep_each_premium(self, reverse):
        rows = [option('A', '100', opening=True, premium='2.0317'), option('A', '200'),
                stock('A', '300'), option('A', '400', opening=True, premium='7.0729'),
                option('A', '500'), stock('A', '600')]
        if reverse:
            rows.reverse()
        out = self.run_rows(rows)
        deliveries = sorted((e for e in out.all_financial_events_enriched
                             if getattr(e, 'option_delivery_links', ())), key=lambda e: e.ibkr_transaction_id)
        assert [e.net_proceeds_or_cost_basis_eur for e in deliveries] == [Decimal('5203.17'), Decimal('5707.29')]


def test_premium_cannot_be_taken_by_another_account_or_twice():
    from types import SimpleNamespace
    from uuid import uuid4
    from src.domain.events import OptionDeliveryLink
    from src.domain.exceptions import ProcessingError
    from src.engine.option_premiums import OptionPremiumBook
    event_id, underlying_id = uuid4(), uuid4()
    book = OptionPremiumBook()
    book.record(SimpleNamespace(account_id='A', event_id=event_id, quantity_contracts=Decimal('1'), event_date='2025-06-20'),
        SimpleNamespace(multiplier=Decimal('100'), underlying_asset_internal_id=underlying_id, option_type='C'), Decimal('7'))
    trade = SimpleNamespace(event_id=uuid4(), account_id='B', asset_internal_id=underlying_id, event_date='2025-06-20',
        quantity=Decimal('100'), option_delivery_links=[OptionDeliveryLink(event_id, Decimal('100'))])
    with pytest.raises(ProcessingError):
        book.consume(trade)
    trade.account_id = 'A'
    assert book.consume(trade) == [(Decimal('7'), 'C')]
    with pytest.raises(ProcessingError, match='already consumed'):
        book.consume(trade)
    book.require_empty()


def test_partial_premiums_conserve_the_exact_remainder():
    from types import SimpleNamespace
    from uuid import uuid4
    from src.domain.events import OptionDeliveryLink
    from src.engine.option_premiums import OptionPremiumBook
    event_id, underlying_id = uuid4(), uuid4()
    book = OptionPremiumBook()
    book.record(SimpleNamespace(account_id='A', event_id=event_id, quantity_contracts=Decimal('3'), event_date='2025-06-20'),
        SimpleNamespace(multiplier=Decimal('1'), underlying_asset_internal_id=underlying_id, option_type='C'), Decimal('1'))
    allocated = []
    for _ in range(3):
        trade = SimpleNamespace(event_id=uuid4(), account_id='A', asset_internal_id=underlying_id, event_date='2025-06-20',
            quantity=Decimal('1'), option_delivery_links=[OptionDeliveryLink(event_id, Decimal('1'))])
        allocated.append(book.consume(trade)[0][0])
    assert sum(allocated) == Decimal('1')
    book.require_empty()


def test_a_partial_delivery_cannot_consume_its_allocation_twice():
    from types import SimpleNamespace
    from uuid import uuid4
    from src.domain.events import OptionDeliveryLink
    from src.domain.exceptions import ProcessingError
    from src.engine.option_premiums import OptionPremiumBook
    event_id, underlying_id = uuid4(), uuid4()
    book = OptionPremiumBook()
    book.record(SimpleNamespace(account_id='A', event_id=event_id, quantity_contracts=Decimal('1'), event_date='2025-06-20'),
        SimpleNamespace(multiplier=Decimal('100'), underlying_asset_internal_id=underlying_id, option_type='C'), Decimal('7'))
    trade = SimpleNamespace(event_id=uuid4(), account_id='A', asset_internal_id=underlying_id,
        event_date='2025-06-20', quantity=Decimal('50'),
        option_delivery_links=[OptionDeliveryLink(event_id, Decimal('50'))])
    assert book.consume(trade) == [(Decimal('3.5'), 'C')]
    with pytest.raises(ProcessingError):
        book.consume(trade)

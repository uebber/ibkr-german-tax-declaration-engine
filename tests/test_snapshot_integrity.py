"""Snapshot integrity regressions from the independent PR86 review.

Ground truth: GT-ESTG20-011/012, GT-INVSTG-010/011/055; user requires
incomplete acquisition data to stop instead of silently entering a figure.
"""
from datetime import date
from decimal import Context, Decimal
from itertools import permutations
from unittest.mock import MagicMock

import pytest
import src.config as config
from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import InvestmentFund, PositionSnapshot, person_snapshot
from src.domain.enums import InvestmentFundType
from src.domain.exceptions import DataIntegrityError, ProcessingError
from src.engine.calculation_engine import FundUnitTranche, _calculate_vorabpauschale
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from src.parsers.positions_parser import parse_positions_csv
from src.pipeline_runner import run_core_processing_pipeline
from src.processing.data_gaps import DataGapCollector, DataGapError
from src.processing.fund_prices import FundPrice, FundPriceStore, resolve_year_start_prices
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.multi_account import (POSITIONS_COLUMNS, TRADES_COLUMNS,
    CASH_TRANSACTIONS_COLUMNS, CORPORATE_ACTIONS_COLUMNS, position_row, trade_row, write_csv)
from tests.support.prior_year_snapshots import snapshot_row

A, B = 'REVIEW-A', 'REVIEW-B'
ISIN = 'IE00REVIEW086'

def pipeline(tmp_path, monkeypatch, *, trades, opening, closing, tax_year,
             prior_start=None, prior_end=None, prior_opening=None, fund=False, marks=None):
    monkeypatch.setattr(config, 'FUND_PRICE_AUTO_FETCH', False)
    if fund:
        import json
        from pathlib import Path
        p = Path(config.CLASSIFICATION_CACHE_FILE_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'ISIN:' + ISIN: ['INVESTMENT_FUND', 'AKTIENFONDS', 'synthetic review']}))
    paths = {}
    for name, columns, rows in [
        ('trades', TRADES_COLUMNS, trades),
        ('positions_start', POSITIONS_COLUMNS, opening),
        ('positions_end', POSITIONS_COLUMNS, closing),
        ('cash_transactions', CASH_TRANSACTIONS_COLUMNS, []),
        ('corporate_actions', CORPORATE_ACTIONS_COLUMNS, []),
        ('positions_prior_start', POSITIONS_COLUMNS, prior_start),
        ('positions_prior_end', POSITIONS_COLUMNS, prior_end),
        ('positions_prior_opening', POSITIONS_COLUMNS, prior_opening),
    ]:
        if rows is not None:
            path = tmp_path / (name + '.csv')
            write_csv(str(path), columns, rows)
            paths[name + '_file_path'] = str(path)
    mark_paths = {}
    for year, rows in (marks or {}).items():
        path = tmp_path / f'mark-{year}.csv'
        write_csv(str(path), POSITIONS_COLUMNS, rows)
        mark_paths[year] = str(path)
    return run_core_processing_pipeline(**paths, interactive_classification_mode=False,
        tax_year_to_process=tax_year,
        positions_mark_file_paths=mark_paths,
        custom_rate_provider=MockECBExchangeRateProvider(Decimal('1')))

@pytest.mark.parametrize('second_account', [A, B])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('checkpoint', [False, True])
def test_partial_cost_basis_must_not_become_complete(
        tmp_path, monkeypatch, second_account, reverse, checkpoint):
    # GT-ESTG20-011 requires actual acquisition costs, not just the known subset.
    sales = ([trade_row(A, ISIN, '2023-06-01', '-200', '15', 'SELL', 'C', 'SALE')]
             if second_account == A else
             [trade_row(A, ISIN, '2023-06-01', '-100', '15', 'SELL', 'C', 'SALE-A'),
              trade_row(B, ISIN, '2023-06-01', '-100', '15', 'SELL', 'C', 'SALE-B')])
    rows = [position_row(A, ISIN, '100', '1000', price='10'),
            position_row(second_account, ISIN, '100', None, price='10')]
    if reverse:
        rows.reverse()
    with pytest.raises((ProcessingError, DataIntegrityError, DataGapError), match='cost basis|basis'):
        pipeline(tmp_path, monkeypatch,
            trades=sales,
            opening=rows if not checkpoint else [position_row(A, ISIN, '200', '2000', price='10')],
            marks={2021: rows} if checkpoint else None,
            closing=[], tax_year=2023)

def test_explicit_zero_cost_is_a_known_cost(tmp_path, monkeypatch):
    out = pipeline(tmp_path, monkeypatch,
        trades=[trade_row(A, ISIN, '2023-06-01', '-200', '15', 'SELL', 'C', 'SALE')],
        opening=[position_row(A, ISIN, '100', '0', price='10'),
                 position_row(A, ISIN, '100', '1000', price='10')],
        closing=[], tax_year=2023)
    assert sum(r.total_cost_basis_eur for r in out.realized_gains_losses) == Decimal('1000')

def test_all_incomplete_opening_holdings_are_named(tmp_path, monkeypatch):
    other = 'US00MISSING86'
    with pytest.raises(ProcessingError) as error:
        pipeline(tmp_path, monkeypatch, trades=[], closing=[], tax_year=2023,
            opening=[position_row(A, ISIN, '100', None, symbol='FUND1'),
                     position_row(B, other, '100', None, symbol='FUND2')])
    assert ISIN in str(error.value) and other in str(error.value)

@pytest.mark.parametrize('third_account', [A, B])
@pytest.mark.parametrize('order', list(permutations(range(3))))
@pytest.mark.parametrize('at_start', [False, True])
def test_a_price_conflict_cannot_be_erased_by_another_account(tmp_path, third_account, order, at_start):
    # All three rows carry prices: no missing-input assumption is involved.
    classifier = AssetClassifier(cache_file_path=str(tmp_path / 'classifications.json'))
    resolver = AssetResolver(classifier)
    orchestrator = ParsingOrchestrator(resolver, classifier, False)
    path = tmp_path / 'closing.csv'
    rows = [
        position_row(A, ISIN, '100', '10000', price='101', conid='C1', symbol='REVIEW'),
        position_row(A, ISIN, '100', '10000', price='110', conid='C2', symbol='REVIEW2'),
        position_row(third_account, ISIN, '100', '10000', price='101', conid='C1', symbol='REVIEW'),
    ]
    write_csv(str(path), POSITIONS_COLUMNS, [rows[i] for i in order])
    parsed = parse_positions_csv(str(path))
    if at_start:
        orchestrator.raw_positions_prior_start = parsed
    else:
        orchestrator.raw_positions_prior_end = parsed
    orchestrator.process_positions(tax_year=2025)
    asset_id = next(iter(resolver.assets_by_internal_id))
    fund = InvestmentFund(internal_asset_id=asset_id, currency='EUR', ibkr_isin=ISIN,
        description='Synthetic review fund', fund_type=InvestmentFundType.AKTIENFONDS)
    resolver.assets_by_internal_id[asset_id] = fund
    converter = MagicMock()
    converter.convert_to_eur.side_effect = lambda amount, currency, when: amount
    collector = DataGapCollector()
    with pytest.raises(DataGapError, match='VORABPAUSCHALE_PRICE_UNUSABLE'):
        _calculate_vorabpauschale(
            asset_resolver=resolver, distributions_by_asset={}, currency_converter=converter,
            vorabpauschale_year=2024,
            opening_lots_by_asset={asset_id: [FundUnitTranche(Decimal('300'), date(2022, 1, 1))]},
            prior_soy_positions=(orchestrator.prior_soy_positions if at_start else
                snapshot_row(asset_id, quantity=Decimal('300'),
                             mark_price=Decimal('100'), mark_price_currency='EUR')),
            prior_eoy_positions=(snapshot_row(asset_id, quantity=Decimal('300'),
                mark_price=Decimal('110'), mark_price_currency='EUR') if at_start
                else orchestrator.prior_eoy_positions),
            prior_opening_positions={}, ctx=Context(prec=28), data_gap_collector=collector)

def test_start_price_conflict_needs_an_independent_resolution(tmp_path):
    fund = InvestmentFund(currency='EUR', ibkr_isin=ISIN,
        fund_type=InvestmentFundType.AKTIENFONDS)
    asset_id = fund.internal_asset_id
    classifier = AssetClassifier(cache_file_path=str(tmp_path / 'classes.json'))
    resolver = AssetResolver(classifier)
    resolver.assets_by_internal_id[asset_id] = fund
    orchestrator = ParsingOrchestrator(resolver, classifier, False)
    orchestrator.prior_soy_positions = {
        (A, asset_id): PositionSnapshot(Decimal('100'), mark_price_conflicted=True)}
    orchestrator.prior_eoy_positions = snapshot_row(asset_id, quantity=Decimal('100'), account=A)
    orchestrator.prior_opening_positions = snapshot_row(asset_id, quantity=Decimal('100'),
        mark_price=Decimal('90'), mark_price_currency='EUR', account=A)
    orchestrator._resolve_vorabpauschale_start_price(2024)
    assert person_snapshot(orchestrator.prior_soy_positions, asset_id).mark_price is None
    store = FundPriceStore(str(tmp_path / 'prices.json'))
    with pytest.raises(DataGapError):
        resolve_year_start_prices([fund], orchestrator.prior_soy_positions,
            orchestrator.prior_eoy_positions, 2024, store, False,
            data_gap_collector=DataGapCollector(), auto_fetch=False)
    price = FundPrice(Decimal('105'), 'USD', date(2024, 1, 2), 'Synthetic issuer NAV')
    store.put(fund.get_classification_key(), 2024, price)
    resolve_year_start_prices([fund], orchestrator.prior_soy_positions,
        orchestrator.prior_eoy_positions, 2024, store, False,
        data_gap_collector=DataGapCollector(), auto_fetch=False)
    settled = person_snapshot(orchestrator.prior_soy_positions, asset_id)
    assert (settled.mark_price, settled.mark_price_currency, settled.mark_price_date) == (
        price.price, price.currency, price.date_set)
    assert settled.quantity == Decimal('100') and not settled.mark_price_conflicted

def test_old_units_sold_cannot_prove_replacement_units_were_held_all_year(tmp_path, monkeypatch):
    # GT-INVSTG-011 concerns the surviving acquisition, not the old position's size.
    # The 2024 acquisition is missing; a 2023 position cannot establish its month.
    with pytest.raises(DataGapError, match='VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN'):
        pipeline(tmp_path, monkeypatch, fund=True,
            trades=[trade_row(A, ISIN, '2022-06-01', '100', '100', 'BUY', 'O', 'OLD-BUY'),
                    trade_row(A, ISIN, '2024-06-01', '-100', '110', 'SELL', 'C', 'OLD-SALE')],
            opening=[position_row(A, ISIN, '100', '10000', price='110')],
            closing=[position_row(A, ISIN, '100', '10000', price='110')],
            prior_start=[position_row(A, ISIN, '100', '10000', price='100')],
            prior_end=[position_row(A, ISIN, '100', '10000', price='110')],
            prior_opening=[position_row(A, ISIN, '100', '10000', price='100')], tax_year=2025)

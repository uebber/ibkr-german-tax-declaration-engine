"""
Aggregate views over (account, asset)-keyed ledger registries.

legal_basis: FIFO je Depot -- BMF-Schreiben vom 14.05.2025,
GZ IV C 1 - S 2252/00075/016/070, Rz. 97 Satz 2 (Tier 2). § 20 Abs. 4 Satz 7
EStG supplies the FIFO fiction but not the Depot boundary; see
reference/tax-law/estg-20-kapitalvermoegen.md. Per-person figures are derived
views across accounts.
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from src.engine.fifo_manager import FifoLedger, FifoLot
from src.engine.ledger_views import ledgers_for_asset, aggregate_lots
from src.domain.enums import AssetCategory
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider


def _ledger(asset_id):
    return FifoLedger(
        asset_internal_id=asset_id, asset_category=AssetCategory.STOCK,
        asset_multiplier_from_asset=None,
        currency_converter=MagicMock(spec=CurrencyConverter),
        exchange_rate_provider=MagicMock(spec=ECBExchangeRateProvider),
        internal_working_precision=28, decimal_rounding_mode="ROUND_HALF_UP",
    )


def _lot(date, qty, cost):
    q = Decimal(qty)
    return FifoLot(acquisition_date=date, quantity=q,
                   unit_cost_basis_eur=Decimal(cost),
                   total_cost_basis_eur=q * Decimal(cost),
                   source_transaction_id="T")


def test_aggregate_across_accounts_sorted_by_date():
    aid, other = uuid.uuid4(), uuid.uuid4()
    la, lb, lo = _ledger(aid), _ledger(aid), _ledger(other)
    la.lots.append(_lot("2024-05-01", "100", "10"))
    lb.lots.append(_lot("2023-01-01", "50", "20"))
    lo.lots.append(_lot("2022-01-01", "1", "1"))
    ledgers = {("U1", aid): la, ("U2", aid): lb, ("U1", other): lo}

    assert set(map(id, ledgers_for_asset(ledgers, aid))) == {id(la), id(lb)}
    lots = aggregate_lots(ledgers, aid)
    assert [l.acquisition_date for l in lots] == ["2023-01-01", "2024-05-01"]
    assert sum(l.quantity for l in lots) == Decimal("150")

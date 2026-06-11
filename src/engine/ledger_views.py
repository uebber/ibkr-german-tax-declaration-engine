# src/engine/ledger_views.py
"""
Ledger views over the (account_key, asset_id)-keyed registries (rework2 AR4).

Per-Depot is the statutory FIFO unit (§20 Abs. 4 S. 7 EStG) — disposals
consume the OWN account's ledger. Per-PERSON figures (Vorabpauschale, EOY
validation, return totals) are DERIVED views across all of a person's
accounts and must go through these helpers, never iterate the raw dicts.
While the seam holds everything under DEFAULT_ACCOUNT the views are trivial;
after the per-Depot flip they are the only correct way to aggregate.
"""
from typing import Dict, List, Tuple
import uuid

from src.engine.fifo_manager import FifoLedger, FifoLot


def ledgers_for_asset(ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger],
                      asset_id: uuid.UUID) -> List[FifoLedger]:
    """All accounts' ledgers for one asset (per-person view)."""
    return [ledger for (_acct, aid), ledger in ledgers.items() if aid == asset_id]


def aggregate_lots(ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger],
                   asset_id: uuid.UUID) -> List[FifoLot]:
    """All long lots of one asset across all accounts, sorted by acquisition
    date (the per-person holdings, e.g. for §18 InvStG multi-tranche VP)."""
    lots: List[FifoLot] = []
    for ledger in ledgers_for_asset(ledgers, asset_id):
        lots.extend(ledger.lots)
    return sorted(lots, key=lambda l: l.acquisition_date)

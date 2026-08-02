# src/engine/ledger_views.py
"""
Ledger views over the (account_key, asset_id)-keyed registries.

FIFO is applied per single Depot -- but that is *not* what § 20 Abs. 4 Satz 7
EStG says. Satz 7 supplies the FIFO fiction for vertretbare Wertpapiere in
Sammelverwahrung im Sinne des § 5 DepotG; its only occurrence of "Depot" is
inside the word "Depotgesetzes". The Depot boundary is Tier 2: BMF-Schreiben
vom 14.05.2025, GZ IV C 1 - S 2252/00075/016/070, Rz. 97 Satz 2 -- *"Die
Anwendung der Fifo-Methode im Sinne des § 20 Absatz 4 Satz 7 EStG ist auf das
einzelne Depot bezogen anzuwenden."* (identical wording in BMF 18.01.2016).
See reference/tax-law/estg-20-kapitalvermoegen.md, which also records the open
question this engine sits on: § 5 DepotG is a German statute and Rz. 97-99 are
written for a German depotfuehrende Stelle, so whether the "einzelnes Depot"
boundary transposes to a foreign broker's sub-accounts is reasoned, not sourced.

Disposals therefore consume the OWN account's ledger. Per-PERSON figures
(Vorabpauschale, EOY validation, return totals) are DERIVED views across all of
a person's accounts and must go through these helpers, never iterate the raw
dicts. While the seam holds everything under DEFAULT_ACCOUNT the views are
trivial; after the per-Depot flip they are the only correct way to aggregate.
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

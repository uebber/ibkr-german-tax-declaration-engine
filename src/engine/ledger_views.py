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

Disposals therefore consume the OWN account's ledger, and since the per-Depot
flip a person's accounts each have one. Per-PERSON figures (Vorabpauschale,
return totals) are DERIVED views across all of them and must go through these
helpers, never iterate the raw dicts.

The EOY validation is the exception, and deliberately so: it runs per account,
because a reconstruction too high in one account and too low in another agrees
with the broker on the person's total while every disposal in both has been
matched against the wrong lots.
"""
from datetime import datetime
from typing import Dict, List, Tuple
import uuid

from src.engine.fifo_manager import FifoLedger, FifoLot
from src.utils.type_utils import parse_ibkr_date


def ledgers_for_asset(ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger],
                      asset_id: uuid.UUID) -> List[FifoLedger]:
    """All accounts' ledgers for one asset (per-person view)."""
    return [ledger for (_acct, aid), ledger in ledgers.items() if aid == asset_id]


def aggregate_lots(ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger],
                   asset_id: uuid.UUID) -> List[FifoLot]:
    """All long lots of one asset across all accounts, in acquisition order
    (the per-person holdings, e.g. for § 18 InvStG multi-tranche VP).

    The sort key is deliberately the same one `FifoLedger` keeps its own `lots`
    in -- parsed date, then `source_transaction_id`. Two reasons it may not be
    shortened to the raw `acquisition_date` string:

    * `acquisition_date` is IBKR-sourced and only documented as YYYY-MM-DD.
      `parse_ibkr_date` also accepts YYYYMMDD, MM/DD/YYYY and DD.MM.YYYY, and
      those do not sort lexicographically against each other or against ISO
      ("2024-12-31" < "20240501" as strings). Every other lot sort in the
      engine parses first; this one must not be the exception that silently
      depends on the invariant.
    * Without the `source_transaction_id` tie-break, same-date lots from
      different accounts fall back to `sorted`'s stability, i.e. to the
      iteration order of the ledger registry, i.e. to the order the ledgers
      happened to be constructed in. That is run-dependent input, not content
      -- the same conflation of "unique" with "deterministic" recorded against
      PRD 5.8 event ordering. This is the input to the Vorabpauschale tranche
      calculation, so lot order picks the figure.
    """
    lots: List[FifoLot] = []
    for ledger in ledgers_for_asset(ledgers, asset_id):
        lots.extend(ledger.lots)
    return sorted(lots, key=lambda l: (parse_ibkr_date(l.acquisition_date) or datetime.min.date(),
                                       l.source_transaction_id))

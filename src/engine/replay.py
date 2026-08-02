# src/engine/replay.py
"""
Unified chronological replayer (rework2-plan AR5).

ONE ordered stream of work items reconstructs all pre-tax-year ledger state —
securities AND currencies — replacing the previous three separate machines
(per-asset batch simulation, a dedicated merger pass, a per-currency replay
loop). The current tax year is processed by the SAME dispatch mechanism over
a live event list (see calculation_engine).

## Ordering contract (the law of the stream)

Items are processed in ascending (phase, sort_key, seq) order:

1. ``Phase.LEDGER_EVENTS`` — every currency- or security-ledger-affecting
   event, globally chronological (``get_event_sort_key``: date, type
   priority, transaction id). Handlers touch exactly ONE ledger, so events of
   different assets/currencies commute; relative order WITHIN a ledger is
   what matters and is preserved via ``seq``.
2. ``Phase.MERGERS`` — historical stock-for-stock mergers, chronological.
   These are tax-neutral under §20 Abs. 4a Satz 1-2 EStG: the new shares step
   into the tax position of the old ones, so the lots move ACROSS asset
   ledgers with their acquisition date and cost basis intact
   (reference/tax-law/estg-20-kapitalvermoegen.md, "Abs. 4a"). They are
   deliberately ordered after all plain ledger events of the historical
   window (the established Pass-2 semantics every merger scenario encodes).
   Future cross-ledger events join the stream with their own documented
   priority instead of growing new passes.
3. ``Phase.RECONCILE`` — start-of-year reconciliation against the reported
   snapshots, after all lot state exists: securities ledgers against SoY
   positions, currency ledgers against SoY cash balances.

``seq`` is an insertion sequence number used as the final tie-breaker: items
whose (phase, sort_key) collide keep the order in which the stream was built.
That collision is the common case, not a corner case — every trade is streamed
twice under the SAME event sort key, once for its security ledger and once for
its currency ledger, and all RECONCILE items share the constant key ``(0,)``.

What ``seq`` does NOT do is make replay deterministic across runs. ``sort_key``
comes from ``get_event_sort_key``, whose tail element is ``event.event_id``, a
``uuid.uuid4()`` regenerated on every run (PRD 5.8 calls that "deterministic";
it is unique-within-a-run, which is a different property). So the order of
DISTINCT same-day events sharing a transaction id is redrawn each run, and no
tie-breaker downstream can recover it — ``seq`` only stabilises items whose
keys are already identical. Ordering within a single ledger is what decides a
figure, and that is unaffected today; it stops being safe once same-day
disposals compete for lots across per-Depot ledgers. The repair belongs in the
PRD and in ``get_event_sort_key``, not here.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, List, Tuple


class Phase(IntEnum):
    LEDGER_EVENTS = 0
    MERGERS = 1
    RECONCILE = 2


@dataclass(frozen=True)
class StreamItem:
    phase: Phase
    sort_key: Tuple
    seq: int
    apply: Callable[[], None]
    label: str = ""  # for diagnostics


class ReplayStream:
    """Collects StreamItems and replays them under the ordering contract."""

    def __init__(self) -> None:
        self._items: List[StreamItem] = []
        self._seq = 0

    def add(self, phase: Phase, sort_key: Tuple, apply: Callable[[], None],
            label: str = "") -> None:
        self._items.append(StreamItem(phase, sort_key, self._seq, apply, label))
        self._seq += 1

    def __len__(self) -> int:
        return len(self._items)

    def run(self) -> None:
        for item in sorted(self._items,
                           key=lambda i: (i.phase, i.sort_key, i.seq)):
            item.apply()

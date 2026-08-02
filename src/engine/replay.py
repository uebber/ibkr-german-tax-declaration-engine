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
2. ``Phase.MERGERS`` — historical stock-for-stock mergers (§20 Abs. 4a
   EStG), chronological. Mergers transfer lots ACROSS asset ledgers and are
   deliberately ordered after all plain ledger events of the historical
   window (the established Pass-2 semantics every merger scenario encodes).
   Future cross-ledger events (internal transfers, §43 Abs. 1 S. 5) join the
   stream with their own documented priority instead of growing new passes.
3. ``Phase.RECONCILE`` — start-of-year reconciliation against the reported
   snapshots, after all lot state exists: securities ledgers against SoY
   positions, currency ledgers against SoY cash balances.

``seq`` is an insertion sequence number used as the FINAL tie-breaker: items
whose (phase, sort_key) collide keep the order in which the stream was built
(per-ledger event order), making replay fully deterministic.
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

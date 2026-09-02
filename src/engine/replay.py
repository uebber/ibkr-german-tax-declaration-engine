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
   priority, transaction id). Most handlers touch exactly ONE ledger, so
   events of different assets/currencies commute; relative order WITHIN a
   ledger is what matters and is preserved via ``seq``.

   Historical stock-for-stock mergers are ordinary members of this phase,
   placed at their own date. They are tax-neutral under §20 Abs. 4a Satz 1-2
   EStG — the new shares step into the tax position of the old ones, so the
   lots move ACROSS asset ledgers with their acquisition date and cost basis
   intact — and Satz 6 fixes the moment the measure takes effect at the
   *Einbuchung in das Depot* (GT-ESTG20-015, GT-ESTG20-018;
   reference/tax-law/estg-20-kapitalvermoegen.md, "Abs. 4a").

   A merger is the one handler that touches TWO ledgers, so unlike everything
   else in this phase its correctness depends on the global interleaving and
   not merely on per-ledger order. What that costs is one intra-day rule:

       On its date, the merger is applied BEFORE that day's trades.

   Until 2026-08 mergers instead ran in a phase of their own, after every
   ledger event in the whole window. A disposal of merged-in shares occurring
   inside the historical window therefore hit a ledger that did not yet hold
   them: the sale overshot, the merger then delivered lots nothing could
   consume, and the reconstruction exceeded the reported SoY by exactly the
   transferred quantity. Reconcile discarded the whole reconstruction and
   synthesised a lot — right quantity, right cost basis, fabricated
   acquisition date. See issue #56 and
   ``test_merged_in_shares_sold_inside_the_historical_window``.

   **That rule is explicit, not accidental.** ``sorting_utils.py`` partitions
   the same-day secondary key by precedence: lot-DELIVERING kinds (corporate
   actions and mergers, internal transfers, option lifecycle events) sort ahead
   of that day's disposals regardless of transaction id, and only within a part
   does IBKR's txid chronology decide. So a merger sorts before that day's
   trades by the rule -- it would still do so if IBKR ever gave the corporate
   action export a ``TransactionID`` column. Pinned by
   ``test_merger_sorts_before_same_day_trades`` and
   ``test_a_transaction_id_on_the_merger_does_not_break_it``.
2. ``Phase.RECONCILE`` — start-of-year reconciliation against the reported
   snapshots, after all lot state exists: securities ledgers against SoY
   positions, currency ledgers against SoY cash balances.

``seq`` is an insertion sequence number used as the final tie-breaker: items
whose (phase, sort_key) collide keep the order in which the stream was built.
That collision is the common case, not a corner case — every trade is streamed
twice under the SAME event sort key, once for its security ledger and once for
its currency ledger, and all RECONCILE items share the constant key ``(0,)``.

What ``seq`` does NOT do is make replay deterministic across runs, and until
August 2026 nothing did. ``sort_key`` comes from ``get_event_sort_key``, whose
tail element was ``event.event_id``, a ``uuid.uuid4()`` regenerated on every
run (PRD 5.8 called that "deterministic"; it is unique-within-a-run, which is a
different property). The order of DISTINCT same-day events sharing a
transaction id was therefore redrawn each run, and no tie-breaker downstream
could recover it — ``seq`` only stabilises items whose keys are already
identical. That tail element is now ``event.creation_sequence``, fixed at
construction, so equal ``sort_key`` means the same two items on every run and
``seq`` decides between them as designed. Issue #71 has the measurement: 14
OptionEAE cash settlements reordering freely between two captures of one tree.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, List, Tuple


class Phase(IntEnum):
    LEDGER_EVENTS = 0
    RECONCILE = 1


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

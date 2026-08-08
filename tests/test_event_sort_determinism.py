"""The event sort order must be reproducible across runs, not merely total (issue #71).

`get_event_sort_key` ended every branch with `event.event_id` until August 2026. That is a
`uuid.uuid4()` regenerated on each run, so two events tying on every earlier element were
ordered at random, differently each run -- while PRD 5.8 and the function's own docstring
called the result deterministic. The tail element is now `event.creation_sequence`, fixed
at construction.

The tie is not hypothetical. It is reached whenever `ibkr_transaction_id` is absent, which
on real input means every OptionEAE cash settlement: that file carries no `TransactionID`
column at all. VZ 2025 produced 14 of them, and two captures of the same tree ordered them
differently.

**Why these tests and not an end-to-end one.** The nondeterminism is across *processes*, and
no test in this suite compares two runs -- which is why the suite never observed the defect
and why the parity captures had to. What is testable in-process is the property that makes
the cross-run order fixed: that the sort key contains nothing regenerated per run, and that
tying events therefore fall in construction order. The first of those is the discriminator;
it fails deterministically against the old tie-break rather than probabilistically.
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.enums import AssetCategory, FinancialEventType
from src.domain.events import (
    CashFlowEvent,
    CorpActionSplitForward,
    OptionCashSettlementEvent,
    TradeEvent,
)
from src.utils.sorting_utils import get_event_sort_key


def _resolver(category=AssetCategory.OPTION, symbol="ESTX50"):
    asset = MagicMock()
    asset.ibkr_symbol = symbol
    asset.asset_category = category
    asset.internal_asset_id = uuid.uuid4()
    resolver = MagicMock()
    resolver.get_asset_by_id.return_value = asset
    return resolver


def _settlement(asset_id=None, event_date="2025-12-19", proceeds="1234.56"):
    """An OptionEAE cash settlement: the real event that reaches the tie.

    No `ibkr_transaction_id`, because `Options_EAE-*.csv` has no such column.
    """
    return OptionCashSettlementEvent(
        asset_internal_id=asset_id or uuid.uuid4(),
        event_date=event_date,
        quantity_contracts=Decimal("3"),
        cash_settlement_proceeds=Decimal(proceeds),
        local_currency="USD",
    )


def _flatten(sort_key):
    date_part, secondary = sort_key
    return (date_part,) + tuple(secondary)


class TestSortKeyCarriesNoPerRunIdentifier:
    """The discriminator. Deterministically red against the `event_id` tie-break."""

    def test_option_lifecycle_branch(self):
        key = get_event_sort_key(_settlement(), _resolver())
        assert not any(isinstance(e, uuid.UUID) for e in _flatten(key)), (
            f"sort key carries a per-run identifier: {_flatten(key)}"
        )

    def test_trade_branch(self):
        event = TradeEvent(
            asset_internal_id=uuid.uuid4(),
            event_date="2025-03-04",
            quantity=Decimal("-40"),
            price_foreign_currency=Decimal("52.00"),
            event_type=FinancialEventType.TRADE_SELL_LONG,
            ibkr_transaction_id="1322551221",
        )
        key = get_event_sort_key(event, _resolver(AssetCategory.STOCK))
        assert not any(isinstance(e, uuid.UUID) for e in _flatten(key))

    def test_cash_like_branch(self):
        event = CashFlowEvent(
            asset_internal_id=uuid.uuid4(),
            event_date="2025-03-04",
            event_type=FinancialEventType.DIVIDEND_CASH,
            gross_amount_foreign_currency=Decimal("31.50"),
            local_currency="USD",
        )
        key = get_event_sort_key(event, _resolver(AssetCategory.STOCK))
        assert not any(isinstance(e, uuid.UUID) for e in _flatten(key))

    def test_corporate_action_branch(self):
        event = CorpActionSplitForward(
            asset_internal_id=uuid.uuid4(),
            event_date="2025-03-04",
            ca_action_id_ibkr="123456789",
            new_shares_per_old_share=Decimal("2"),
        )
        key = get_event_sort_key(event, _resolver(AssetCategory.STOCK))
        assert not any(isinstance(e, uuid.UUID) for e in _flatten(key))


class TestTyingEventsKeepConstructionOrder:
    def test_the_tie_is_actually_reached(self):
        """Pins the premise of the test below.

        If a future change gave these events distinguishing earlier elements, the
        construction-order assertion would pass without testing anything. This asserts the
        two keys are equal up to the final element, so that failure mode is visible.
        """
        resolver = _resolver()
        first, second = _settlement(), _settlement()

        key_a, key_b = _flatten(get_event_sort_key(first, resolver)), _flatten(
            get_event_sort_key(second, resolver)
        )
        assert key_a[:-1] == key_b[:-1], (
            "two OptionEAE cash settlements on one date no longer tie; this test's premise "
            f"is stale: {key_a} vs {key_b}"
        )
        assert key_a[-1] != key_b[-1], "the tie-break does not distinguish two distinct events"

    def test_settlements_sort_in_construction_order(self):
        """Sorting a reversed list of tying events restores construction order.

        Against the `event_id` tie-break this is a coin flip per adjacent pair, so with 20
        events it fails with probability 1 - 1/20! -- deterministic in practice, but the
        discriminator that fails *by construction* is `TestSortKeyCarriesNoPerRunIdentifier`.
        """
        resolver = _resolver()
        events = [_settlement() for _ in range(20)]
        expected = [e.creation_sequence for e in events]

        ordered = sorted(reversed(events), key=lambda e: get_event_sort_key(e, resolver))

        assert [e.creation_sequence for e in ordered] == expected

    def test_the_order_does_not_depend_on_the_input_order(self):
        """A total order, not a stable sort over equal keys.

        Note this one does **not** discriminate against the `event_id` tie-break -- within a
        single process those ids are fixed, so it passed against the broken tree too. What it
        guards is a different future mistake: a tie-break that leaves two events genuinely
        equal, where the order would then be whatever order the list arrived in.
        """
        resolver = _resolver()
        events = [_settlement() for _ in range(20)]

        first = [id(e) for e in sorted(events, key=lambda e: get_event_sort_key(e, resolver))]
        second = [
            id(e) for e in sorted(reversed(events), key=lambda e: get_event_sort_key(e, resolver))
        ]

        assert first == second


class TestCreationSequence:
    def test_is_assigned_without_being_asked_for(self):
        """Every event gets one at __init__.

        This is why a construction counter was chosen over a source row index: the events
        the engine synthesises after parsing have no source row, and an ordinal that has to
        be passed in is an ordinal that can be forgotten at one call site.
        """
        before = _settlement().creation_sequence
        after = _settlement().creation_sequence
        assert after > before

    def test_is_strictly_increasing(self):
        sequences = [_settlement().creation_sequence for _ in range(5)]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == 5

# src/utils/sorting_utils.py
import logging
from datetime import date
from decimal import Decimal
from typing import Tuple, Any 

from src.domain.events import (
    FinancialEvent, TradeEvent, CashFlowEvent, WithholdingTaxEvent, CorporateActionEvent,
    OptionLifecycleEvent, CurrencyConversionEvent, FeeEvent, InternalTransferEvent,
    InternalCashTransferEvent
)
from src.identification.asset_resolver import AssetResolver
from src.domain.assets import Asset
from src.domain.enums import AssetCategory 
from src.utils.type_utils import parse_ibkr_date

logger = logging.getLogger(__name__)

# Define sort order for event categories for TIE-BREAKING ON THE SAME DAY ONLY.
# Lower value sorts earlier. This order is chosen based on typical dependencies
# or logical processing flow for events happening on the *exact same day*.
# This does NOT override the primary date sort.
_INTRA_DAY_SORT_ORDER_CORP_ACTION = 0  # Corporate actions (e.g., splits) first
_INTRA_DAY_SORT_ORDER_OPTION_LIFECYCLE = 1 # Option Ex, As, Ep before resulting trades
_INTRA_DAY_SORT_ORDER_TRADE = 2          # Trades / Currency Conversions
_INTRA_DAY_SORT_ORDER_CASH = 3           # Dividends, Interest, WHT, Fees
_INTRA_DAY_SORT_ORDER_UNKNOWN = 99       # Fallback

def get_event_sort_key(event: FinancialEvent, asset_resolver: AssetResolver) -> Tuple[date, Tuple[Any, ...]]:
    """
    Generates a deterministic sort key tuple for FinancialEvent as per PRD 5.8.
    Primary key: event_date.
    Secondary key: Tuple starting with an intra-day sort order, then PRD-specified fields,
                   ending with event.creation_sequence for ultimate tie-breaking.

    The tail element is `creation_sequence`, not `event_id`. `event_id` is a `uuid4`
    redrawn on every run, so using it made the order of two events that tie on every
    earlier element random run to run — the opposite of what this docstring and PRD 5.8
    both claimed. See `FinancialEvent.creation_sequence` and issue #71.

    The tie is reached whenever `ibkr_transaction_id` is absent, since every branch below
    substitutes `""` for it.
    """
    parsed_date = parse_ibkr_date(event.event_date)
    if not parsed_date:
        raise ValueError(f"Event {event.event_id} ({type(event).__name__}) has unparseable date '{event.event_date}'. Cannot generate sort key.")

    asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
    if not asset:
        raise ValueError(f"Event {event.event_id} ({type(event).__name__}) on {parsed_date} references unknown asset {event.asset_internal_id}. Cannot generate sort key.")

    intra_day_order: int
    specific_secondary_elements: Tuple[Any, ...]

    # Determine intra-day sort order and the specific PRD-defined tuple part
    if isinstance(event, CorporateActionEvent):
        intra_day_order = _INTRA_DAY_SORT_ORDER_CORP_ACTION
        # PRD: (asset.ibkr_symbol, event.ca_action_id_ibkr, event.description, event.creation_sequence)
        if not asset.ibkr_symbol:
            logger.warning(f"Asset {asset.internal_asset_id} for CA Event {event.event_id} on {parsed_date} lacks ibkr_symbol. Using placeholder.")
        specific_secondary_elements = (
            asset.ibkr_symbol or "", 
            event.ca_action_id_ibkr or "", 
            event.ibkr_activity_description or "", # PRD's event.description (FinancialEvent.ibkr_activity_description)
            event.creation_sequence
        )
    elif isinstance(event, (InternalTransferEvent, InternalCashTransferEvent)):
        # Same intra-day slot as a corporate action, and for the same reason a merger
        # takes it (see engine/replay.py): the units must be in the RECEIVING account
        # before that day's disposals, or a sale of what just arrived hits an empty
        # ledger. The price is the other end of the day -- a sale out of the SENDING
        # account booked on the move date is applied after the move, so the ledger then
        # holds less than the move claims; that case is loud, not silent, because the
        # closing reconciliation compares the sending account against the broker.
        #
        # A CASH move shares the band and the argument -- the balance has to be in the
        # receiving account before that day's spending -- but not the loudness: a
        # currency ledger that runs short opens a short position rather than refusing
        # ([GT-FX-006]), so the sending side simply sells what it has and shorts the rest.
        # Nothing in the export orders a move against a trade on the same day, so this is
        # a choice between two unsourced orders, and it is the one that keeps the
        # receiving side able to spend what it just received.
        #
        # This band puts the move in the lot-DELIVERING partition below, which sorts
        # ahead of that day's trades BY THE RULE, not by the accident of an empty
        # transaction id -- the move would sort first even if it carried one. See the
        # precedence comment at the end of this function.
        intra_day_order = _INTRA_DAY_SORT_ORDER_CORP_ACTION
        # Four elements, all strings but the last, because that is the shape the
        # corporate-action branch above produces and this event shares its band. Two
        # items in one band whose element types differ at some position raise TypeError
        # the moment everything before that position ties -- so `asset.asset_category`
        # (a plain Enum, which does not compare) must be its `.name`, or two moves on
        # one day take the whole run down. Pinned by
        # `test_two_moves_on_one_day_sort_without_blowing_up`.
        specific_secondary_elements = (
            asset.asset_category.name,
            event.account_id or "",
            event.to_account_id,
            event.creation_sequence,
        )
    elif isinstance(event, OptionLifecycleEvent): # Option Lifecycles before regular trades
        intra_day_order = _INTRA_DAY_SORT_ORDER_OPTION_LIFECYCLE
        # PRD: (event.ibkr_transaction_id, asset.asset_category, event.creation_sequence)
        if not event.ibkr_transaction_id:
             logger.warning(f"OptionLifecycle Event {event.event_id} on {parsed_date} lacks ibkr_transaction_id. Using placeholder.")
        specific_secondary_elements = (
            event.ibkr_transaction_id or "", 
            asset.asset_category, 
            event.creation_sequence
        )
    elif isinstance(event, (TradeEvent, CurrencyConversionEvent)): # Trade and Currency Conversion share structure
        intra_day_order = _INTRA_DAY_SORT_ORDER_TRADE
        # PRD: (event.ibkr_transaction_id, asset.asset_category, event.creation_sequence)
        if not event.ibkr_transaction_id:
             logger.warning(f"Trade/CurrencyConversion Event {event.event_id} on {parsed_date} lacks ibkr_transaction_id. Using placeholder.")
        specific_secondary_elements = (
            event.ibkr_transaction_id or "", 
            asset.asset_category, 
            event.creation_sequence
        )
    elif isinstance(event, (CashFlowEvent, WithholdingTaxEvent, FeeEvent)):
        intra_day_order = _INTRA_DAY_SORT_ORDER_CASH
        # PRD: (event.ibkr_transaction_id, asset.asset_category, event.gross_amount_foreign_currency, event.creation_sequence)
        if not event.ibkr_transaction_id:
            logger.warning(f"Cash-like Event {event.event_id} on {parsed_date} lacks ibkr_transaction_id. Using placeholder.")
        gross_amount_for_sort = event.gross_amount_foreign_currency if event.gross_amount_foreign_currency is not None else Decimal('0')
        specific_secondary_elements = (
            event.ibkr_transaction_id or "", 
            asset.asset_category,
            gross_amount_for_sort,
            event.creation_sequence
        )
    else:
        logger.error(f"Event {event.event_id} of unrecognized type {type(event).__name__} encountered. Using fallback sort order.")
        intra_day_order = _INTRA_DAY_SORT_ORDER_UNKNOWN
        specific_secondary_elements = ( # Minimal structure for unknown
            event.ibkr_transaction_id or "", 
            asset.asset_category, 
            event.creation_sequence
        )
    
    # Within a day, transaction id is IBKR's own chronology (ids are assigned
    # sequentially), and it is the ground truth: currency FIFO is computed over this same
    # stream, so consuming the currency lots in the true order is what makes the currency
    # gain right.
    transaction_id_for_sort = event.ibkr_transaction_id or ""

    # There is ONE legitimate override of that chronology: an event that DELIVERS lots
    # must precede a same-day disposal of the lots it delivers, because a sale cannot
    # consume what has not yet arrived. §20 Abs. 4a Satz 6 fixes a merger at the
    # Einbuchung; an internal transfer-in must exist before a same-day sale out of the
    # receiving account; an option exercise/assignment creates the position the resulting
    # trade settles. So the day is partitioned: lot-DELIVERING kinds (corporate actions
    # and mergers, internal transfers -- which share the corp-action band -- and option
    # lifecycle events) sort ahead of everything else; WITHIN each part the true txid
    # chronology is kept, so trades, dividends, interest and FX -- which touch the
    # currency ledger and have no delivery dependency between them -- keep their real
    # order and the currency figure stays correct.
    #
    # This is the explicit domain rule, not the accident it replaced: the old key put the
    # transaction id ahead of the band, so a delivering event landed before a trade only
    # when its id happened to be smaller (e.g. corporate actions, whose export carries no
    # id, sorted to ""). An event that delivers lots AND carries an id -- an internal
    # transfer given one, an option lifecycle event -- would otherwise sort by the
    # broker's string rather than by the rule. See engine/replay.py on the merger, which
    # this fixes too.
    _LOT_DELIVERING_BANDS = (
        _INTRA_DAY_SORT_ORDER_CORP_ACTION,      # corporate actions, mergers, internal transfers
        _INTRA_DAY_SORT_ORDER_OPTION_LIFECYCLE,  # option exercise/assignment/expiry
    )
    precedence = 0 if intra_day_order in _LOT_DELIVERING_BANDS else 1

    # The final secondary key tuple: (precedence, transaction_id, intra_day_order, then
    # PRD elements). The PRD elements ALREADY end with event.creation_sequence.
    secondary_key_tuple = (precedence, transaction_id_for_sort, intra_day_order) + specific_secondary_elements

    return (parsed_date, secondary_key_tuple)

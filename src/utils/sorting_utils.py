# src/utils/sorting_utils.py
import logging
from datetime import date
from decimal import Decimal
from typing import Tuple, Any 

from src.domain.events import (
    FinancialEvent, TradeEvent, CashFlowEvent, WithholdingTaxEvent, CorporateActionEvent,
    OptionLifecycleEvent, CurrencyConversionEvent, FeeEvent, InternalTransferEvent,
    InternalCashTransferEvent, StockAwardEvent
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
    elif isinstance(event, StockAwardEvent):
        # Same intra-day slot as a corporate action, for the same reason a transfer takes
        # it: the shares must be in the ledger before that day's disposals, or a sale on
        # the award date hits a lot that does not exist yet. A vesting shares the band
        # because it must restate the lot before any sale that day reads its cost basis
        # -- selling first would measure the gain against the provisional award price.
        #
        # The band decides this only because the event carries no `ibkr_transaction_id`:
        # the export's SerialNumber is blank on every row, so there is none to carry, and
        # the shared tail below would otherwise put it ahead of the band.
        intra_day_order = _INTRA_DAY_SORT_ORDER_CORP_ACTION
        # Four elements, all strings but the last, matching the shape of the two branches
        # that share this band. Two items in one band whose element types differ at some
        # position raise TypeError the moment everything before it ties -- the defect
        # recorded on the transfer branch below.
        specific_secondary_elements = (
            asset.ibkr_symbol or "",
            event.award_date or "",
            event.ibkr_activity_description or "",
            event.creation_sequence,
        )
    elif isinstance(event, (InternalTransferEvent, InternalCashTransferEvent)):
        # Same intra-day slot as a corporate action, and for the same reason a merger
        # takes it (see engine/replay.py): the units must be in the RECEIVING account
        # before that day's disposals, or a sale of what just arrived hits an empty
        # ledger. The price is the other end of the day -- a sale out of the SENDING
        # account booked on the move date is applied after the move, so the ledger then
        # holds less than the move claims. That case is loud, not silent: the move takes
        # the whole position or the run stops (`apply_internal_transfer`).
        #
        # A CASH move shares the band and the argument -- the balance has to be in the
        # receiving account before that day's spending -- but not the loudness: a
        # currency ledger that runs short opens a short position rather than refusing
        # ([GT-FX-006]), so the sending side simply sells what it has and shorts the
        # rest. Nothing in the export orders a move against a trade on the same day, so
        # this is a choice between two unsourced orders, and it is the one that keeps
        # the receiving side able to spend what it just received.
        #
        # The band decides this only because the event carries no `ibkr_transaction_id`;
        # the shared tail below puts that ahead of the band. See InternalTransferEvent.
        intra_day_order = _INTRA_DAY_SORT_ORDER_CORP_ACTION
        # Four elements, all strings but the last, because that is the shape the
        # corporate-action branch above produces and this event shares its band. Two
        # items in one band whose element types differ at some position raise TypeError
        # the moment everything before that position ties -- which is exactly what
        # `asset.asset_category` did here: `AssetCategory` is a plain Enum and does not
        # compare, so two moves on the same day (neither carrying a transaction id) took
        # the whole run down. Caught by a real-data run, not by the suite;
        # `test_two_moves_on_one_day_sort_without_blowing_up` is what catches it now.
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
    
    # For events on the same date, prioritize transaction ID over event type
    # This ensures chronological order is preserved (IBKR assigns transaction IDs sequentially)
    transaction_id_for_sort = event.ibkr_transaction_id or ""

    # The final secondary key tuple: (transaction_id, intra_day_order_integer, then PRD elements)
    # The PRD elements ALREADY end with event.creation_sequence.
    secondary_key_tuple = (transaction_id_for_sort, intra_day_order) + specific_secondary_elements

    return (parsed_date, secondary_key_tuple)

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

    if event.resolved_day_position is not None:
        return parsed_date, (event.resolved_day_position, event.creation_sequence)

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
    elif isinstance(event, InternalTransferEvent):
        # A SECURITIES move takes the corporate-action slot, and for the same reason a
        # merger does (see engine/replay.py): the units must be in the RECEIVING account
        # before that day's disposals, or a sale of what just arrived hits an empty
        # ledger. The price is the other end of the day -- a sale out of the SENDING
        # account booked on the move date is applied after the move, so the ledger then
        # holds less than the move claims; that case is loud, not silent, because the
        # closing reconciliation compares the sending account against the broker.
        #
        # It carries no transaction id (neither side's names the combined move), so the
        # lot-DELIVERING partition below is what puts it ahead of the day's trades BY THE
        # RULE, not by the accident of an empty id -- it would sort first even with one.
        #
        # A CASH Umbuchung is deliberately NOT here. It is a valued disposal whose FIFO
        # gain depends on consuming the currency lots in the broker's true order; forcing
        # it ahead of an earlier same-day currency purchase consumed the wrong lot and
        # realised the wrong gain. It sits in the TRADE band, ordered by its own broker id.
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
    elif isinstance(event, InternalCashTransferEvent):
        # A cash Umbuchung is ordered by the broker's own chronology among the day's
        # currency events -- the same TRADE band as a currency conversion. It is a valued
        # disposal of one currency balance and an acquisition of another, and the currency
        # FIFO gain is right only if the lots are consumed in the broker's true order. So
        # the move must sit where its transaction id places it: after an earlier same-day
        # currency purchase, before a later spend. The corporate-action band it used to
        # take forced it ahead of the whole day and consumed the wrong lot.
        #
        # The bare `asset.asset_category` Enum, exactly as this band's other members emit it
        # (`TradeEvent`, `CurrencyConversionEvent`). It MUST match them: with a no-id move
        # the earlier elements tie and the comparison reaches this one, and a member is a
        # currency conversion of the SAME category, so Enum-vs-Enum resolves by equality and
        # never needs `<`. Using `.name` here (a str) would compare str-vs-Enum against those
        # same-category siblings and raise TypeError. (The securities branch above uses
        # `.name` for the opposite reason: ITS band-mates are strings.) Two no-id trade-band
        # events of DIFFERENT categories is a separate, pre-existing limit of this band.
        intra_day_order = _INTRA_DAY_SORT_ORDER_TRADE
        if not event.ibkr_transaction_id:
            logger.warning(f"Internal cash transfer {event.event_id} on {parsed_date} lacks "
                           f"ibkr_transaction_id; its intra-day order falls to the front of "
                           f"the trade band.")
        specific_secondary_elements = (
            event.ibkr_transaction_id or "",
            asset.asset_category,
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

    # Corporate deliveries retain their established before-trades position. Options
    # must retain transaction order: exercise/assignment CONSUMES option lots, including
    # those opened earlier on the same day (GT-ESTG20-011/013). A dependency on a linked
    # stock leg does not permit moving the exercise ahead of its own purchase.
    _LOT_DELIVERING_BANDS = (
        _INTRA_DAY_SORT_ORDER_CORP_ACTION,      # corporate actions, mergers, internal transfers
    )
    precedence = 0 if intra_day_order in _LOT_DELIVERING_BANDS else 1

    # The final secondary key tuple: (precedence, transaction_id, intra_day_order, then
    # PRD elements). The PRD elements ALREADY end with event.creation_sequence.
    secondary_key_tuple = (precedence, transaction_id_for_sort, intra_day_order) + specific_secondary_elements

    return (parsed_date, secondary_key_tuple)

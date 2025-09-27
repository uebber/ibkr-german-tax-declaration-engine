# src/utils/sorting_utils.py
import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Tuple, Any 

from src.domain.events import (
    FinancialEvent, TradeEvent, CashFlowEvent, WithholdingTaxEvent, CorporateActionEvent,
    OptionLifecycleEvent, CurrencyConversionEvent, FeeEvent
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
                   ending with event.event_id for ultimate tie-breaking.
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
        # PRD: (asset.ibkr_symbol, event.ca_action_id_ibkr, event.description, event.event_id)
        if not asset.ibkr_symbol:
            logger.warning(f"Asset {asset.internal_asset_id} for CA Event {event.event_id} on {parsed_date} lacks ibkr_symbol. Using placeholder.")
        specific_secondary_elements = (
            asset.ibkr_symbol or "", 
            event.ca_action_id_ibkr or "", 
            event.ibkr_activity_description or "", # PRD's event.description (FinancialEvent.ibkr_activity_description)
            event.event_id
        )
    elif isinstance(event, OptionLifecycleEvent): # Option Lifecycles before regular trades
        intra_day_order = _INTRA_DAY_SORT_ORDER_OPTION_LIFECYCLE
        # PRD: (event.ibkr_transaction_id, asset.asset_category, event.event_id)
        if not event.ibkr_transaction_id:
             logger.warning(f"OptionLifecycle Event {event.event_id} on {parsed_date} lacks ibkr_transaction_id. Using placeholder.")
        specific_secondary_elements = (
            event.ibkr_transaction_id or "", 
            asset.asset_category, 
            event.event_id
        )
    elif isinstance(event, (TradeEvent, CurrencyConversionEvent)): # Trade and Currency Conversion share structure
        intra_day_order = _INTRA_DAY_SORT_ORDER_TRADE
        # PRD: (event.ibkr_transaction_id, asset.asset_category, event.event_id)
        if not event.ibkr_transaction_id:
             logger.warning(f"Trade/CurrencyConversion Event {event.event_id} on {parsed_date} lacks ibkr_transaction_id. Using placeholder.")
        specific_secondary_elements = (
            event.ibkr_transaction_id or "", 
            asset.asset_category, 
            event.event_id
        )
    elif isinstance(event, (CashFlowEvent, WithholdingTaxEvent, FeeEvent)):
        intra_day_order = _INTRA_DAY_SORT_ORDER_CASH
        # PRD: (event.ibkr_transaction_id, asset.asset_category, event.gross_amount_foreign_currency, event.event_id)
        if not event.ibkr_transaction_id:
            logger.warning(f"Cash-like Event {event.event_id} on {parsed_date} lacks ibkr_transaction_id. Using placeholder.")
        gross_amount_for_sort = event.gross_amount_foreign_currency if event.gross_amount_foreign_currency is not None else Decimal('0')
        specific_secondary_elements = (
            event.ibkr_transaction_id or "", 
            asset.asset_category,
            gross_amount_for_sort,
            event.event_id
        )
    else:
        logger.error(f"Event {event.event_id} of unrecognized type {type(event).__name__} encountered. Using fallback sort order.")
        intra_day_order = _INTRA_DAY_SORT_ORDER_UNKNOWN
        specific_secondary_elements = ( # Minimal structure for unknown
            event.ibkr_transaction_id or "", 
            asset.asset_category, 
            event.event_id
        )
    
    # For events on the same date, prioritize transaction ID over event type
    # This ensures chronological order is preserved (IBKR assigns transaction IDs sequentially)
    transaction_id_for_sort = event.ibkr_transaction_id or ""

    # The final secondary key tuple: (transaction_id, intra_day_order_integer, then PRD elements)
    # The PRD elements ALREADY end with event.event_id.
    secondary_key_tuple = (transaction_id_for_sort, intra_day_order) + specific_secondary_elements

    return (parsed_date, secondary_key_tuple)

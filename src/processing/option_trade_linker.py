# src/processing/option_trade_linker.py
import logging
from typing import List, Dict, Tuple
from decimal import Decimal # Import Decimal

from src.domain.events import TradeEvent, OptionLifecycleEvent, OptionExerciseEvent, OptionAssignmentEvent
from src.domain.assets import Stock, Option
from src.identification.asset_resolver import AssetResolver

logger = logging.getLogger(__name__)

class OptionTradeLinker:
    def __init__(self, asset_resolver: AssetResolver):
        self.asset_resolver = asset_resolver

    def _build_option_event_lookup(self,
                                   option_lifecycle_events: List[OptionLifecycleEvent]
                                   ) -> Dict[Tuple[str, str, str], OptionLifecycleEvent]:
        """
        Builds a lookup map for option lifecycle events (Exercise/Assignment).
        Key: (event_date_str, underlying_conid_str, abs_expected_stock_qty_str)
        Value: OptionLifecycleEvent
        """
        lookup: Dict[Tuple[str, str, str], OptionLifecycleEvent] = {}
        for opt_event in option_lifecycle_events:
            if not isinstance(opt_event, (OptionExerciseEvent, OptionAssignmentEvent)):
                continue

            option_asset = self.asset_resolver.get_asset_by_id(opt_event.asset_internal_id)
            if not isinstance(option_asset, Option) or not option_asset.underlying_ibkr_conid:
                logger.warning(f"OptionLifecycleEvent {opt_event.event_id} (Type: {opt_event.event_type.name}) "
                               f"is missing valid Option asset or underlying_ibkr_conid. Cannot build lookup key.")
                continue

            multiplier = option_asset.multiplier if option_asset.multiplier is not None else Decimal("100")
            if multiplier == Decimal(0): multiplier = Decimal("100") # Safety

            expected_stock_qty_abs = (opt_event.quantity_contracts * multiplier).copy_abs()
            link_key = (
                opt_event.event_date, # Event date is already string YYYY-MM-DD
                option_asset.underlying_ibkr_conid,
                expected_stock_qty_abs.to_eng_string()
            )

            if link_key in lookup:
                existing_event = lookup[link_key]
                logger.warning(
                    f"Duplicate key {link_key} for option lifecycle event lookup. "
                    f"Existing event: {existing_event.event_id} ({existing_event.event_type.name}), "
                    f"New event: {opt_event.event_id} ({opt_event.event_type.name}). Overwriting with new event. "
                    "This might indicate multiple option events leading to the same underlying stock movement on the same day."
                )
            lookup[link_key] = opt_event
        logger.debug(f"Built option event lookup map with {len(lookup)} entries.")
        return lookup

    def link_trades(self,
                    stock_trades_to_link: List[TradeEvent],
                    option_event_lookup: Dict[Tuple[str, str, str], OptionLifecycleEvent]
                    ):
        """
        Attempts to link stock trades to option lifecycle events.
        Modifies stock_trades_to_link in place by setting related_option_event_id.
        """
        linked_count = 0
        if not stock_trades_to_link:
            logger.debug("No stock trades provided for linking.")
            return
        if not option_event_lookup:
            logger.debug("Option event lookup map is empty. No linking possible.")
            return

        for stock_trade in stock_trades_to_link:
            stock_asset = self.asset_resolver.get_asset_by_id(stock_trade.asset_internal_id)
            if not isinstance(stock_asset, Stock) or not stock_asset.ibkr_conid:
                logger.warning(f"Stock trade {stock_trade.ibkr_transaction_id} (Event ID: {stock_trade.event_id}) "
                               f"is missing valid Stock asset or ibkr_conid. Cannot attempt linking.")
                continue

            stock_qty_abs_str = stock_trade.quantity.copy_abs().to_eng_string()
            # For stock trades, the "key" needs to use the stock's own conid for the conid part of the tuple
            link_key_for_stock_trade = (
                stock_trade.event_date,
                stock_asset.ibkr_conid, # Use the stock's conid
                stock_qty_abs_str
            )

            matched_option_event = option_event_lookup.get(link_key_for_stock_trade)

            if matched_option_event:
                stock_trade.related_option_event_id = matched_option_event.event_id
                linked_count += 1
                logger.info(
                    f"Successfully linked stock trade {stock_trade.ibkr_transaction_id} (Asset: {stock_asset.get_classification_key()}) "
                    f"to option event {matched_option_event.event_id} (Type: {matched_option_event.event_type.name}) "
                    f"via key: {link_key_for_stock_trade}"
                )
            else:
                logger.warning(
                    f"Stock trade {stock_trade.ibkr_transaction_id} (Asset: {stock_asset.get_classification_key()}, Event Date: {stock_trade.event_date}, ConID: {stock_asset.ibkr_conid}, Qty: {stock_trade.quantity}) "
                    f"has E/A Notes/Codes ('{stock_trade.ibkr_notes_codes}') but no matching OptionLifecycleEvent found. "
                    f"Lookup key: {link_key_for_stock_trade}. "
                    f"Available option event keys for date {stock_trade.event_date}: "
                    f"{ {k for k in option_event_lookup if k[0] == stock_trade.event_date} }"
                )
        logger.info(f"Option trade linking completed. {linked_count} stock trades linked to option events.")

def perform_option_trade_linking(
    asset_resolver: AssetResolver,
    candidate_option_lifecycle_events: List[OptionLifecycleEvent],
    candidate_stock_trades_for_linking: List[TradeEvent]
):
    """
    Orchestrates the linking of stock trades to option lifecycle events.
    """
    if not candidate_stock_trades_for_linking:
        logger.info("No stock trades eligible for option linking. Skipping linking step.")
        return
    if not candidate_option_lifecycle_events:
        logger.info("No candidate option lifecycle events for linking. Skipping linking step.")
        return

    linker = OptionTradeLinker(asset_resolver)
    option_event_lookup = linker._build_option_event_lookup(candidate_option_lifecycle_events)

    if not option_event_lookup:
        logger.info("Option event lookup map is empty after building. No linking possible for stock trades.")
        return

    linker.link_trades(candidate_stock_trades_for_linking, option_event_lookup)

# src/engine/event_processors/trade_processor.py
import logging
from typing import List, Dict, Any, Optional, Tuple
import uuid
from decimal import Decimal

from src.domain.events import TradeEvent
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger
from src.domain.enums import FinancialEventType, AssetCategory
from src.identification.asset_resolver import AssetResolver # Added
from src.domain.assets import Option, Asset # Added Option and Asset
from .base_processor import EventProcessor

logger = logging.getLogger(__name__)

class TradeProcessor(EventProcessor):
    """Processes standard trade events (buy long, sell long, open short, cover short),
       including adjustments for stock trades resulting from option exercise/assignment."""

    def process(self, event: TradeEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        """Handles trade events by adding lots or consuming lots and generating RGL.
           If the trade is a stock trade linked to an option event, adjusts cost/proceeds."""
        realized_gains_losses: List[RealizedGainLoss] = []

        if not isinstance(event, TradeEvent):
             logger.error(f"TradeProcessor received non-TradeEvent: {type(event).__name__} (ID: {event.event_id}). Skipping.")
             return []

        if not ledger:
             # Option assets might not have a ledger if they are only ever bought to exercise or sold to assign
             # and never traded independently. Processors for OptionExercise/Assignment handle ledger consumption.
             # For stock trades resulting from these, the stock ledger is relevant.
             # If this trade event is for an option asset itself (e.g., buying/selling an option contract),
             # and it's not an exercise/assignment, then a ledger *should* exist.
             asset_resolver_check: Optional[AssetResolver] = context.get('asset_resolver')
             is_option_asset = False
             if asset_resolver_check:
                 asset_obj_check = asset_resolver_check.get_asset_by_id(event.asset_internal_id)
                 if isinstance(asset_obj_check, Option):
                     is_option_asset = True
            
             if not is_option_asset: # Only error if it's not an option trade without a ledger
                 logger.error(f"TradeProcessor received event {event.event_id} ({event.event_type.name}) for non-option asset {event.asset_internal_id} but no ledger exists. Skipping.")
                 return []
             else: # It's an option asset, but not an exercise/assignment/expiration.
                  # This means it's a regular trade of an option.
                  # The FifoLedger for this Option asset should have been created.
                  # If it's None here, it's an issue.
                  logger.error(f"TradeProcessor received trade for Option asset {event.asset_internal_id} (Event {event.event_id}, Type {event.event_type.name}), but no ledger was found. This is unexpected for option trades. Skipping.")
                  return []


        asset_resolver: Optional[AssetResolver] = context.get('asset_resolver')
        asset_symbol = "UNKNOWN_ASSET_SYMBOL"
        stock_asset_obj: Optional[Asset] = None 

        if asset_resolver is None:
            logger.critical("Missing 'asset_resolver' in context for TradeProcessor. Cannot proceed safely.")
            raise ValueError("Missing 'asset_resolver' in context for TradeProcessor.")
        
        # This event is for an asset, get its details
        event_asset_obj = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if event_asset_obj:
            asset_symbol = event_asset_obj.ibkr_symbol or event_asset_obj.description or f"NO_SYMBOL_ID_{event_asset_obj.internal_asset_id}"
        else: # Should not happen if asset discovery worked
            asset_symbol = f"UNKNOWN_ASSET_ID_{event.asset_internal_id}"


        # Adjustment logic for STOCKS linked to option events
        if event_asset_obj and event_asset_obj.asset_category == AssetCategory.STOCK and event.related_option_event_id:
            stock_asset_obj = event_asset_obj # To avoid confusion with option_asset_obj
            logger.info(f"Stock trade event {event.event_id} ({event.event_type.name}) for asset {asset_symbol} (ID: {event.asset_internal_id}) is linked to option event {event.related_option_event_id}. Attempting adjustment.")

            pending_adjustments: Optional[Dict[uuid.UUID, Tuple[Decimal, uuid.UUID, str]]] = context.get('pending_option_adjustments')

            if pending_adjustments is None:
                logger.critical(f"Missing 'pending_option_adjustments' in context for TradeProcessor. Cannot adjust stock trade {event.event_id}.")
                raise ValueError("Missing 'pending_option_adjustments' in context for stock trade adjustment.")

            adjustment_data = pending_adjustments.get(event.related_option_event_id)

            if adjustment_data is None:
                logger.critical(f"Stock trade {event.event_id} linked to option event {event.related_option_event_id}, but no pending adjustment data found for that option event ID. Adjustment failed. "
                                f"[Stock Trade CSV Context: Date={event.event_date}, Symbol={asset_symbol}, Qty={event.quantity}, Price={event.price_foreign_currency}, TxID={event.ibkr_transaction_id or 'N/A'}, Desc='{event.ibkr_activity_description or 'N/A'}']")
                raise ValueError(f"Missing pending adjustment data for option event {event.related_option_event_id}.")

            total_premium_eur, option_asset_id_from_adj, option_type_str = adjustment_data
            option_asset_from_adj = asset_resolver.get_asset_by_id(option_asset_id_from_adj)
            option_asset_symbol_for_log = "UNKNOWN_OPTION_SYMBOL"
            if option_asset_from_adj:
                option_asset_symbol_for_log = option_asset_from_adj.ibkr_symbol or option_asset_from_adj.description or f"NO_SYMBOL_ID_{option_asset_id_from_adj}"

            if not isinstance(option_asset_from_adj, Option):
                 logger.critical(f"Adjustment data for option event {event.related_option_event_id} (Option Symbol: {option_asset_symbol_for_log}, Option Asset ID: {option_asset_id_from_adj}) "
                                 f"references asset {option_asset_id_from_adj}, which is not an Option type ({type(option_asset_from_adj).__name__}). Cannot verify adjustment for stock trade {event.event_id} (Stock Symbol: {asset_symbol}).")
                 raise TypeError(f"Asset {option_asset_id_from_adj} linked to adjustment is not an Option.")

            if option_asset_from_adj.underlying_asset_internal_id != event.asset_internal_id:
                option_underlying_resolved_asset = asset_resolver.get_asset_by_id(option_asset_from_adj.underlying_asset_internal_id) if option_asset_from_adj.underlying_asset_internal_id else None
                option_underlying_symbol_for_log = option_underlying_resolved_asset.ibkr_symbol if option_underlying_resolved_asset else "UNKNOWN_UNDERLYING_SYMBOL"
                
                logger.critical(f"Link Integrity Check FAILED: Stock trade {event.event_id} (Symbol: {asset_symbol}, AssetID: {event.asset_internal_id}) "
                                f"linked to option event {event.related_option_event_id} (Option Symbol: {option_asset_symbol_for_log}, Option AssetID: {option_asset_id_from_adj}, OptionType: {option_type_str}) "
                                f"points to underlying asset ID {option_asset_from_adj.underlying_asset_internal_id} (Underlying Symbol: {option_underlying_symbol_for_log}). Aborting.")
                raise ValueError("Mismatch between stock trade asset and linked option's underlying asset.")

            adjustment_amount = Decimal(0)
            option_action_description = "Unknown Option Action resulting in stock trade"
            trade_action_description = "Stock trade value" # Generic, will be refined

            original_net_value_eur = event.net_proceeds_or_cost_basis_eur
            if original_net_value_eur is None:
                logger.critical(f"Cannot adjust stock trade {event.event_id}: Original net_proceeds_or_cost_basis_eur is None. "
                                f"[Stock Trade CSV Context: Date={event.event_date}, Symbol={asset_symbol}, Qty={event.quantity}, TxID={event.ibkr_transaction_id or 'N/A'}, Desc='{event.ibkr_activity_description or 'N/A'}]")
                raise ValueError(f"Missing original net value for stock trade {event.event_id} requiring adjustment.")

            # Determine Adjustment Logic based on PRD Section 2.4
            # total_premium_eur is always positive: cost if long option exercised, proceeds if short option assigned.
            if event.event_type in [FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER]:
                trade_action_description = "Stock Buy Cost" if event.event_type == FinancialEventType.TRADE_BUY_LONG else "Stock Cover Cost"
                if option_type_str == 'C': # Stock purchase due to Long Call Exercise
                    adjustment_amount = +total_premium_eur # Cost increases by premium paid for call
                    option_action_description = "Long Call Exercise Premium"
                elif option_type_str == 'P': # Stock purchase due to Short Put Assignment
                    adjustment_amount = -total_premium_eur # Cost decreases by premium received for put
                    option_action_description = "Short Put Assignment Premium"
                else:
                    logger.error(f"Invalid option type '{option_type_str}' for {trade_action_description} adjustment of {asset_symbol}. Stock Event ID: {event.event_id}, Option Event ID: {event.related_option_event_id}")
            
            elif event.event_type in [FinancialEventType.TRADE_SELL_LONG, FinancialEventType.TRADE_SELL_SHORT_OPEN]:
                trade_action_description = "Stock Sell Proceeds" if event.event_type == FinancialEventType.TRADE_SELL_LONG else "Stock Short Sale Proceeds"
                if option_type_str == 'C': # Stock sale due to Short Call Assignment
                    adjustment_amount = +total_premium_eur # Proceeds increase by premium received for call
                    option_action_description = "Short Call Assignment Premium"
                elif option_type_str == 'P': # Stock sale due to Long Put Exercise
                    adjustment_amount = -total_premium_eur # Proceeds decrease by premium paid for put
                    option_action_description = "Long Put Exercise Premium"
                else:
                    logger.error(f"Invalid option type '{option_type_str}' for {trade_action_description} adjustment of {asset_symbol}. Stock Event ID: {event.event_id}, Option Event ID: {event.related_option_event_id}")
            
            else: # Should not be reached if linking is correct and event types are constrained
                logger.warning(
                    f"Stock trade linked to option event {event.related_option_event_id} has an unexpected event type "
                    f"{event.event_type.name} for economic adjustment. Cannot apply adjustment for stock event {event.event_id}."
                )

            # Apply adjustment if conditions were met (valid option type and valid stock trade type)
            if option_type_str in ['C', 'P'] and event.event_type in [
                FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER,
                FinancialEventType.TRADE_SELL_LONG, FinancialEventType.TRADE_SELL_SHORT_OPEN
            ]:
                logger.info(f"  Adjusting {trade_action_description} for {asset_symbol}: {adjustment_amount:+.2f} EUR ({option_action_description} from Option {option_asset_symbol_for_log})")
                
                adjusted_value_eur = original_net_value_eur + adjustment_amount
                logger.info(f"  Original net value for {asset_symbol}: {original_net_value_eur:.4f} EUR. Adjusted value: {adjusted_value_eur:.4f} EUR.")
                event.net_proceeds_or_cost_basis_eur = adjusted_value_eur
                
                if event.related_option_event_id in pending_adjustments:
                    del pending_adjustments[event.related_option_event_id]
                    logger.debug(f"  Removed pending adjustment for option event {event.related_option_event_id}.")
                else: # Should ideally not happen if linking and processing order is correct
                    logger.warning(f"Attempted to remove pending adjustment for option event {event.related_option_event_id}, but it was not found. Stock event: {event.event_id}.")
        
        # Log if a stock trade looks like it should be linked but isn't
        elif event_asset_obj and event_asset_obj.asset_category == AssetCategory.STOCK and \
             event.related_option_event_id is None and \
             event.ibkr_notes_codes and \
             any(code in (event.ibkr_notes_codes or "").upper() for code in ['A', ';A', 'EX', ';EX']): # Ensure Notes/Codes is checked safely
             logger.error(
                 f"Stock trade {event.event_id} (Symbol: {asset_symbol}) appears to be from an option Exercise/Assignment "
                 f"(Notes/Codes: '{event.ibkr_notes_codes}') but is NOT LINKED (related_option_event_id is None). "
                 f"Economic adjustment will be SKIPPED. This indicates a potential issue in the option/stock trade linking logic."
                 f"[Stock Trade CSV Context: Date={event.event_date}, Qty={event.quantity or 'N/A'}, Price={event.price_foreign_currency or 'N/A'} {event.local_currency or ''}, TxID={event.ibkr_transaction_id or 'N/A'}]"
             )

        # Proceed with FIFO ledger operations using the (potentially adjusted) event
        try:
            if event.event_type == FinancialEventType.TRADE_BUY_LONG:
                ledger.add_long_lot(event)
            elif event.event_type == FinancialEventType.TRADE_SELL_LONG:
                new_rgls = ledger.consume_long_lots_for_sale(event)
                realized_gains_losses.extend(new_rgls)
            elif event.event_type == FinancialEventType.TRADE_SELL_SHORT_OPEN:
                ledger.add_short_lot(event)
            elif event.event_type == FinancialEventType.TRADE_BUY_SHORT_COVER:
                new_rgls = ledger.consume_short_lots_for_cover(event)
                realized_gains_losses.extend(new_rgls)
            else:
                # This handles trades of options themselves (not exercises/assignments which are OptionLifecycleEvents)
                # If an Option asset ledger is passed, it implies a trade of the option contract.
                if ledger.asset_category == AssetCategory.OPTION:
                     logger.warning(f"TradeProcessor received a trade event of type {event.event_type.name} for an Option asset {ledger.asset_internal_id}. This trade type is not standard for opening/closing option positions via FIFO. Logic may be incomplete.")
                     # For now, assume any BUY for option is opening long, any SELL is closing long/opening short
                     # This is a simplification; OptionLifecycleEvents are primary for exercises/assignments.
                     # This path would be for outright buying/selling option contracts.
                     if event.quantity > 0 : # Buying an option
                         ledger.add_long_lot(event)
                     elif event.quantity < 0: # Selling an option
                         # If there are long lots, it's a sell to close. Otherwise, sell to open short.
                         # This simplistic handling might need refinement if complex option trading strategies are common.
                         # For now, let's assume simple buy to open, sell to close/open.
                         if ledger.get_current_position_quantity() > 0 : # Existing long position
                              new_rgls = ledger.consume_long_lots_for_sale(event)
                              realized_gains_losses.extend(new_rgls)
                         else: # No long position, or already short; this is opening/adding to short.
                              ledger.add_short_lot(event)
                else:
                    logger.warning(f"TradeProcessor received unexpected event type: {event.event_type.name} for asset category {ledger.asset_category.name} (Event ID: {event.event_id}). Ignoring.")

        except ValueError as e:
            logger.critical(
                f"Error processing trade {event.event_id} ({event.event_type.name}) in ledger for asset {ledger.asset_internal_id} (Symbol: {asset_symbol}): {e}. "
                f"[Trade Event Context: Date={event.event_date}, Qty={event.quantity}, Price={event.price_foreign_currency}, TxID={event.ibkr_transaction_id or 'N/A'}, Desc='{event.ibkr_activity_description or 'N/A'}']",
                exc_info=True
            )
            raise e
        except TypeError as e: # Catch potential errors if ledger methods are called unexpectedly
            logger.critical(
                f"Type error during ledger operation for trade {event.event_id} ({event.event_type.name}), asset {ledger.asset_internal_id} (Symbol: {asset_symbol}): {e}. "
                f"This might indicate an issue with event type or ledger state.",
                exc_info=True
            )
            raise e


        return realized_gains_losses

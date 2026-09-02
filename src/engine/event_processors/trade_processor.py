# src/engine/event_processors/trade_processor.py
import logging
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
import uuid
from decimal import Decimal

from src.utils.account_utils import account_key
from src.domain.events import TradeEvent
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger
from src.domain.enums import FinancialEventType, AssetCategory
from src.domain.exceptions import ProcessingError
from src.identification.asset_resolver import AssetResolver # Added
from src.domain.assets import Option, Asset, CashBalance # Added Option, Asset, and CashBalance
from .base_processor import EventProcessor

if TYPE_CHECKING:
    from .currency_conversion_processor import CurrencyConversionProcessor

logger = logging.getLogger(__name__)

class TradeProcessor(EventProcessor):
    """Processes standard trade events (buy long, sell long, open short, cover short),
       including adjustments for stock trades resulting from option exercise/assignment."""

    def process(self, event: TradeEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        """Handles trade events by adding lots or consuming lots and generating RGL.
           If the trade is a stock trade linked to an option event, adjusts cost/proceeds."""
        realized_gains_losses: List[RealizedGainLoss] = []

        if not isinstance(event, TradeEvent):
             raise ProcessingError(f"TradeProcessor received non-TradeEvent: {type(event).__name__} (ID: {event.event_id}).")

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
            
             if not is_option_asset:
                 raise ProcessingError(f"TradeProcessor: event {event.event_id} ({event.event_type.name}) for non-option asset {event.asset_internal_id} has no FIFO ledger.")
             else:
                  raise ProcessingError(f"TradeProcessor: Option trade {event.event_id} ({event.event_type.name}) for asset {event.asset_internal_id} has no FIFO ledger.")


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
        # Note: Exclude "IA" codes which are Internalized + Automatically Allocated (not option assignments)
        elif event_asset_obj and event_asset_obj.asset_category == AssetCategory.STOCK and \
             event.related_option_event_id is None and \
             event.ibkr_notes_codes and \
             'IA' not in (event.ibkr_notes_codes or "").upper() and \
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
                    raise ProcessingError(f"TradeProcessor: unexpected event type {event.event_type.name} for asset category {ledger.asset_category.name} (Event ID: {event.event_id}).")

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

        # Phase 5a: Process implicit currency consumption/acquisition from security trades
        currency_rgls = self._process_trade_currency_impact(event, context)
        realized_gains_losses.extend(currency_rgls)

        return realized_gains_losses

    def _process_trade_currency_impact(
        self,
        event: TradeEvent,
        context: Dict[str, Any]
    ) -> List[RealizedGainLoss]:
        """
        Handle implicit currency consumption (BUY) or acquisition (SELL) from security trades.

        When buying a security in foreign currency:
          - You consume currency from your cash balance
          - This triggers FX gain/loss on the consumed currency

        When selling a security in foreign currency:
          - You receive currency into your cash balance
          - This creates a new currency lot (no immediate FX gain/loss)
          - Exception: If short currency lots exist, receiving currency covers them (realizes FX gain/loss)

        The EUR value used MUST match gross_amount_eur from enrichment for consistency.

        Cross-currency trades (Phase 5b):
          When the asset's denomination currency differs from the settlement currency
          (e.g., buy GBP stock with USD), we process based on the SETTLEMENT currency
          because that's what you actually pay/receive. The EUR bridge valuation
          comes from gross_amount_eur (ECB rate conversion during enrichment).

        Returns:
            List of RealizedGainLoss records for any FX gains/losses
        """
        results: List[RealizedGainLoss] = []

        # Skip EUR-denominated trades - no currency impact
        trade_currency = event.local_currency
        if not trade_currency or trade_currency.upper() == "EUR":
            return results

        # Get currency infrastructure from context
        asset_resolver: Optional[AssetResolver] = context.get('asset_resolver')
        currency_fifo_ledgers: Optional[Dict[uuid.UUID, FifoLedger]] = context.get('currency_fifo_ledgers')
        currency_processor = context.get('currency_processor')

        if not asset_resolver or not currency_processor:
            logger.debug(f"Trade {event.event_id}: Currency processing infrastructure not available, skipping implicit FX")
            return results

        if currency_fifo_ledgers is None:
            logger.debug(f"Trade {event.event_id}: No currency FIFO ledgers available, skipping implicit FX")
            return results

        # Get the currency's CashBalance asset and ledger
        currency_asset = asset_resolver.get_cash_balance_asset(trade_currency.upper())
        if not currency_asset:
            logger.debug(f"Trade {event.event_id}: No CashBalance asset for {trade_currency}, skipping implicit FX")
            return results

        # The account that made the trade: the currency leaves or arrives in that account's
        # balance, and each account's balance is its own Kapitalforderung ([GT-FX-009]).
        currency_ledger = currency_fifo_ledgers.get(
            (account_key(event.account_id), currency_asset.internal_asset_id))
        if not currency_ledger:
            logger.debug(f"Trade {event.event_id}: No currency ledger for {trade_currency}, skipping implicit FX")
            return results

        # Use gross_amount_foreign_currency which already includes the multiplier
        # (e.g., for options: qty * price * 100)
        foreign_amount = event.gross_amount_foreign_currency
        eur_amount = event.gross_amount_eur

        if foreign_amount is None or foreign_amount <= Decimal("0"):
            logger.debug(f"Trade {event.event_id}: Missing or zero gross_amount_foreign_currency, skipping implicit FX")
            return results

        if eur_amount is None or eur_amount <= Decimal("0"):
            logger.warning(f"Trade {event.event_id}: Missing or zero gross_amount_eur ({eur_amount}), skipping implicit FX")
            return results

        # Phase 5b: Cross-currency trade detection
        # Check if asset denomination currency differs from settlement currency
        traded_asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if traded_asset and traded_asset.currency:
            asset_currency = traded_asset.currency.upper()
            settlement_currency = trade_currency.upper()

            if asset_currency != "EUR" and settlement_currency != "EUR" and asset_currency != settlement_currency:
                # Cross-currency trade: asset is denominated in one foreign currency,
                # but settlement is in a different foreign currency.
                # Example: Buying a GBP stock with USD settlement
                # We process based on SETTLEMENT currency (what you actually pay/receive).
                # The EUR bridge valuation is already in gross_amount_eur from enrichment.
                logger.info(
                    f"Trade {event.event_id}: Cross-currency trade detected "
                    f"(asset: {asset_currency}, settlement: {settlement_currency}). "
                    f"Processing FX impact on {settlement_currency} (settlement currency)."
                )

        # Calculate EUR per unit of foreign currency
        eur_per_unit = eur_amount / foreign_amount

        # Determine direction based on trade type
        if event.event_type in [FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER]:
            # BUYING security → CONSUMING foreign currency
            results = self._consume_currency_for_purchase(
                event, currency_ledger, currency_asset,
                foreign_amount, eur_per_unit, currency_processor
            )
        elif event.event_type in [FinancialEventType.TRADE_SELL_LONG, FinancialEventType.TRADE_SELL_SHORT_OPEN]:
            # SELLING security → RECEIVING foreign currency (may cover shorts)
            results = self._acquire_currency_from_sale(
                event, currency_ledger, currency_asset,
                foreign_amount, eur_per_unit, currency_processor
            )

        # Process commission as currency consumption
        commission_rgls = self._process_commission_currency_impact(event, context)
        results.extend(commission_rgls)

        return results

    def _consume_currency_for_purchase(
        self,
        event: TradeEvent,
        currency_ledger: FifoLedger,
        currency_asset: CashBalance,
        foreign_amount: Decimal,
        eur_per_unit: Decimal,
        processor: 'CurrencyConversionProcessor'
    ) -> List[RealizedGainLoss]:
        """
        Consume currency from FIFO ledger when buying a security.

        This is equivalent to selling currency (from_currency=USD, to_currency=EUR)
        but triggered implicitly by a stock purchase.
        """
        results: List[RealizedGainLoss] = []
        quantity_to_consume = foreign_amount

        # Check available long quantity
        available_long_qty = sum(lot.quantity for lot in currency_ledger.lots)

        if available_long_qty > Decimal("0"):
            qty_to_consume_from_longs = min(quantity_to_consume, available_long_qty)

            # Realize FX gain/loss on consumed lots
            long_results = processor.realize_long_lots_for_security_trade(
                currency_ledger,
                currency_asset.internal_asset_id,
                event.event_date,
                event.event_id,
                event.ibkr_transaction_id,
                qty_to_consume_from_longs,
                eur_per_unit
            )
            results.extend(long_results)

            if long_results:
                total_fx_gl = sum(rgl.gross_gain_loss_eur for rgl in long_results)
                logger.info(
                    f"Trade {event.event_id}: Implicit FX from consuming {qty_to_consume_from_longs:.2f} {currency_asset.currency} "
                    f"for security purchase. FX gain/loss: {total_fx_gl:.2f} EUR"
                )

            quantity_to_consume -= qty_to_consume_from_longs

        # If consuming more than available, open short currency position
        if quantity_to_consume > Decimal("1e-10"):
            logger.info(
                f"Trade {event.event_id}: Opening implicit SHORT {currency_asset.currency} position: "
                f"{quantity_to_consume:.2f} (security purchase exceeds currency balance)"
            )
            processor.open_short_position_for_security_trade(
                currency_ledger,
                event.event_date,
                event.ibkr_transaction_id,
                quantity_to_consume,
                eur_per_unit
            )

        return results

    def _process_commission_currency_impact(
        self,
        event: TradeEvent,
        context: Dict[str, Any]
    ) -> List[RealizedGainLoss]:
        """
        Consume trade commission from the currency FIFO ledger.

        Commissions paid in foreign currency reduce the cash balance and
        must be tracked as currency consumption for FX gain/loss purposes.
        """
        results: List[RealizedGainLoss] = []

        commission_amount = event.commission_foreign_currency
        if commission_amount is None or commission_amount == Decimal("0"):
            return results

        commission_currency = (event.commission_currency or "").upper()
        if not commission_currency or commission_currency == "EUR":
            return results

        commission_eur = event.commission_eur
        if commission_eur is None:
            return results

        comm_abs = commission_amount.copy_abs()
        comm_eur_abs = commission_eur.copy_abs()

        if comm_abs <= Decimal("0") or comm_eur_abs <= Decimal("0"):
            return results

        asset_resolver: Optional[AssetResolver] = context.get('asset_resolver')
        currency_fifo_ledgers: Optional[Dict] = context.get('currency_fifo_ledgers')
        currency_processor = context.get('currency_processor')

        if not asset_resolver or not currency_processor or currency_fifo_ledgers is None:
            return results

        currency_asset = asset_resolver.get_cash_balance_asset(commission_currency)
        if not currency_asset:
            return results

        # The account that made the trade: the currency leaves or arrives in that account's
        # balance, and each account's balance is its own Kapitalforderung ([GT-FX-009]).
        currency_ledger = currency_fifo_ledgers.get(
            (account_key(event.account_id), currency_asset.internal_asset_id))
        if not currency_ledger:
            return results

        eur_per_unit = comm_eur_abs / comm_abs

        # Positive commission = rebate (cash inflow), negative = normal fee (cash outflow)
        is_rebate = commission_amount > Decimal("0")

        if is_rebate:
            # Commission rebate: acquire currency (same as receiving proceeds)
            currency_processor.create_long_lot_for_security_trade(
                currency_ledger, event.event_date, event.ibkr_transaction_id,
                comm_abs, eur_per_unit
            )
            logger.debug(
                f"Trade {event.event_id}: Commission rebate created {comm_abs:.2f} "
                f"{commission_currency} lot @ {eur_per_unit:.6f} EUR per unit"
            )
        else:
            # Normal commission fee: consume currency (cash outflow)
            available_long_qty = sum(lot.quantity for lot in currency_ledger.lots)

            if available_long_qty > Decimal("0"):
                qty_to_consume = min(comm_abs, available_long_qty)
                long_results = currency_processor.realize_long_lots_for_cashflow_expense(
                    currency_ledger, currency_asset.internal_asset_id,
                    event.event_date, event.event_id, event.ibkr_transaction_id,
                    qty_to_consume, eur_per_unit
                )
                results.extend(long_results)

                if long_results:
                    total_fx_gl = sum(rgl.gross_gain_loss_eur for rgl in long_results)
                    logger.info(
                        f"Trade {event.event_id}: Commission FX from consuming {qty_to_consume:.2f} "
                        f"{commission_currency}. FX gain/loss: {total_fx_gl:.2f} EUR"
                    )

                comm_abs -= qty_to_consume

            # If insufficient balance, open short
            if comm_abs > Decimal("1e-10"):
                currency_processor.open_short_position_for_cashflow_expense(
                    currency_ledger, event.event_date, event.ibkr_transaction_id,
                    comm_abs, eur_per_unit
                )

        return results

    def _acquire_currency_from_sale(
        self,
        event: TradeEvent,
        currency_ledger: FifoLedger,
        currency_asset: CashBalance,
        foreign_amount: Decimal,
        eur_per_unit: Decimal,
        processor: 'CurrencyConversionProcessor'
    ) -> List[RealizedGainLoss]:
        """
        Acquire currency into FIFO ledger when selling a security.

        This creates a new currency lot. No immediate FX gain/loss -
        the gain/loss is realized when this currency is later spent or converted.
        Exception: If short currency lots exist, receiving currency covers them.
        """
        results: List[RealizedGainLoss] = []
        quantity_to_acquire = foreign_amount

        # Check if there are short lots to cover first
        available_short_qty = sum(lot.quantity_shorted for lot in currency_ledger.short_lots)

        if available_short_qty > Decimal("0"):
            qty_to_cover = min(quantity_to_acquire, available_short_qty)

            # Cover short positions (this DOES realize gain/loss)
            short_cover_results = processor.cover_short_lots_for_security_trade(
                currency_ledger,
                currency_asset.internal_asset_id,
                event.event_date,
                event.event_id,
                event.ibkr_transaction_id,
                qty_to_cover,
                eur_per_unit
            )
            results.extend(short_cover_results)

            if short_cover_results:
                total_fx_gl = sum(rgl.gross_gain_loss_eur for rgl in short_cover_results)
                logger.info(
                    f"Trade {event.event_id}: Implicit FX from covering {qty_to_cover:.2f} {currency_asset.currency} "
                    f"short position with security sale proceeds. FX gain/loss: {total_fx_gl:.2f} EUR"
                )

            quantity_to_acquire -= qty_to_cover

        # Create new long lot for remaining quantity
        if quantity_to_acquire > Decimal("1e-10"):
            processor.create_long_lot_for_security_trade(
                currency_ledger,
                event.event_date,
                event.ibkr_transaction_id,
                quantity_to_acquire,
                eur_per_unit
            )
            logger.debug(
                f"Trade {event.event_id}: Created {currency_asset.currency} lot from security sale: "
                f"{quantity_to_acquire:.2f} @ {eur_per_unit:.6f} EUR per unit"
            )

        return results

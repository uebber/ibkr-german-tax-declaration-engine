# src/engine/event_processors/corporate_action_processor.py
import logging
from typing import List, Dict, Any 

from src.domain.events import (
    CorpActionSplitForward, CorpActionMergerCash, CorpActionStockDividend, CorpActionMergerStock,
    CorporateActionEvent, FinancialEvent, CorpActionExpireDividendRights
)
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger
from .base_processor import EventProcessor
from src.domain.enums import FinancialEventType # Added for checking event type

logger = logging.getLogger(__name__)

def _format_asset_info(asset_obj) -> str:
    """Helper to format asset information for logging."""
    if not asset_obj:
        return "Unknown Asset"
    desc = asset_obj.description or asset_obj.get_classification_key()
    symbol = asset_obj.ibkr_symbol or "N/A"
    return f"'{desc}' (Symbol: {symbol})"

class SplitProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not ledger:
            logger.error(f"SplitProcessor received event {event.event_id} but no ledger provided. Cannot process.")
            return []
        if not isinstance(event, CorpActionSplitForward):
            logger.error(f"SplitProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
            return []
        # Check using renamed FinancialEventType from enums.py
        if event.event_type != FinancialEventType.CORP_SPLIT_FORWARD:
            logger.error(f"SplitProcessor received event with type {event.event_type} but expected CORP_SPLIT_FORWARD. ID: {event.event_id}")
            return []
        try:
            logger.info(f"Processing {event.event_type.name} for asset {ledger.asset_internal_id} on {event.event_date} (ID: {event.event_id}). Ratio: {event.new_shares_per_old_share}")
            ledger.adjust_lots_for_split(event)
        except Exception as e:
            logger.error(f"Error processing Split event {event.event_id} in ledger for asset {ledger.asset_internal_id}: {e}", exc_info=True)
        return []

class MergerCashProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not ledger:
            logger.error(f"MergerCashProcessor received event {event.event_id} but no ledger provided. Cannot process.")
            return []
        if not isinstance(event, CorpActionMergerCash):
            logger.error(f"MergerCashProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
            return []
        if event.event_type != FinancialEventType.CORP_MERGER_CASH:
            logger.error(f"MergerCashProcessor received event with type {event.event_type} but expected CORP_MERGER_CASH. ID: {event.event_id}")
            return []
        try:
            logger.info(f"Processing {event.event_type.name} for asset {ledger.asset_internal_id} on {event.event_date} (ID: {event.event_id}). Cash/Share: {event.cash_per_share_eur} EUR")
            if event.cash_per_share_eur is None:
                 logger.error(f"Cash Merger event {event.event_id} is missing cash_per_share_eur. Cannot process.")
                 return []
            realized_gains_losses = ledger.consume_all_lots_for_cash_merger(event)
            logger.info(f"Cash Merger generated {len(realized_gains_losses)} RealizedGainLoss records.")
            return realized_gains_losses
        except ValueError as e:
             logger.critical(f"Critical error processing Cash Merger {event.event_id} in ledger for asset {ledger.asset_internal_id}: {e}", exc_info=True)
             raise e
        except Exception as e:
            logger.error(f"Unexpected error processing Cash Merger event {event.event_id} for asset {ledger.asset_internal_id}: {e}", exc_info=True)
            return []


class StockDividendProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not ledger:
            logger.error(f"StockDividendProcessor received event {event.event_id} but no ledger provided. Cannot process.")
            return []
        if not isinstance(event, CorpActionStockDividend):
             logger.error(f"StockDividendProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
             return []
        if event.event_type != FinancialEventType.CORP_STOCK_DIVIDEND:
            logger.error(f"StockDividendProcessor received event with type {event.event_type} but expected CORP_STOCK_DIVIDEND. ID: {event.event_id}")
            return []
        try:
             logger.info(f"Processing {event.event_type.name} for asset {ledger.asset_internal_id} on {event.event_date} (ID: {event.event_id}). New Shares: {event.quantity_new_shares_received} (German tax: zero cost basis)")
             # FMV no longer required - German tax treatment uses zero cost basis
             ledger.add_lot_for_stock_dividend(event)
        except ValueError as e:
             logger.critical(f"Critical error processing Stock Dividend {event.event_id} in ledger for asset {ledger.asset_internal_id}: {e}", exc_info=True)
             raise e
        except Exception as e:
            logger.error(f"Error processing Stock Dividend event {event.event_id} in ledger for asset {ledger.asset_internal_id}: {e}", exc_info=True)
        return []

class MergerStockProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not ledger:
             logger.error(f"MergerStockProcessor received event {event.event_id} but no source ledger provided. Cannot process.")
             return []
        if not isinstance(event, CorpActionMergerStock):
             logger.error(f"MergerStockProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
             return []
        if event.event_type != FinancialEventType.CORP_MERGER_STOCK:
            logger.error(f"MergerStockProcessor received event with type {event.event_type} but expected CORP_MERGER_STOCK. ID: {event.event_id}")
            return []

        logger.warning(f"Processing {event.event_type.name} for asset {ledger.asset_internal_id} on {event.event_date} (ID: {event.event_id}) - FIFO Lot Adjustment LOGIC NOT IMPLEMENTED YET as per PRD.")
        return []

class ExpireDividendRightsProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, CorpActionExpireDividendRights):
            logger.error(f"ExpireDividendRightsProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
            return []
        
        # These events are used only for post-processing DI/ED consolidation, no FIFO ledger processing needed
        return []

class GenericCorporateActionProcessor(EventProcessor):
     def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, CorporateActionEvent):
            logger.error(f"GenericCorporateActionProcessor received non-CorporateActionEvent type: {type(event).__name__} (ID: {event.event_id}).")
            return []
        
        # Get asset information for better logging
        asset_resolver = context.get('asset_resolver')
        asset_obj = asset_resolver.get_asset_by_id(event.asset_internal_id) if asset_resolver else None
        
        ledger_id_str = f"ledger for asset {ledger.asset_internal_id}" if ledger else "no ledger provided"
        logger.warning(f"No specific processor found for Corporate Action type {event.event_type.name} for asset {_format_asset_info(asset_obj)} (IBKR Action ID: {getattr(event, 'ca_action_id_ibkr', 'N/A')}, Event ID: {event.event_id}) with {ledger_id_str}. No ledger modifications performed.")
        return []

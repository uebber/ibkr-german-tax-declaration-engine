# src/engine/event_processors/corporate_action_processor.py
import logging
import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional

from src.utils.account_utils import account_key, DEFAULT_ACCOUNT
from src.domain.events import (
    CorpActionSplitForward, CorpActionMergerCash, CorpActionStockDividend, CorpActionMergerStock,
    CorporateActionEvent, FinancialEvent, CorpActionExpireDividendRights
)
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger
from .base_processor import EventProcessor
from src.domain.enums import FinancialEventType

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

            # Create currency lot for cash proceeds received in foreign currency
            currency_rgls = self._process_currency_impact(event, context)
            realized_gains_losses.extend(currency_rgls)

            return realized_gains_losses
        except ValueError as e:
             logger.critical(f"Critical error processing Cash Merger {event.event_id} in ledger for asset {ledger.asset_internal_id}: {e}", exc_info=True)
             raise e
        except Exception as e:
            logger.error(f"Unexpected error processing Cash Merger event {event.event_id} for asset {ledger.asset_internal_id}: {e}", exc_info=True)
            return []

    def _process_currency_impact(
        self, event: CorpActionMergerCash, context: Dict[str, Any]
    ) -> List[RealizedGainLoss]:
        """
        Create currency FIFO lot for cash merger proceeds received in foreign currency.
        Follows the same pattern as TradeProcessor._acquire_currency_from_sale.
        """
        results: List[RealizedGainLoss] = []

        proceeds_currency = (event.local_currency or "").upper()
        if not proceeds_currency or proceeds_currency == "EUR":
            return results

        foreign_amount = event.gross_amount_foreign_currency
        eur_amount = event.gross_amount_eur
        if not foreign_amount or not eur_amount or foreign_amount <= Decimal("0") or eur_amount <= Decimal("0"):
            return results

        asset_resolver = context.get('asset_resolver')
        currency_fifo_ledgers: Optional[Dict[uuid.UUID, FifoLedger]] = context.get('currency_fifo_ledgers')
        currency_processor = context.get('currency_processor')

        if not asset_resolver or not currency_processor or currency_fifo_ledgers is None:
            return results

        currency_asset = asset_resolver.get_cash_balance_asset(proceeds_currency)
        if not currency_asset:
            return results

        currency_ledger = currency_fifo_ledgers.get((DEFAULT_ACCOUNT, currency_asset.internal_asset_id))
        if not currency_ledger:
            return results

        eur_per_unit = eur_amount / foreign_amount

        # Cover short positions first, then create long lot (same as security sale)
        available_short_qty = sum(lot.quantity_shorted for lot in currency_ledger.short_lots)

        if available_short_qty > Decimal("0"):
            qty_to_cover = min(foreign_amount, available_short_qty)
            short_cover_results = currency_processor.cover_short_lots_for_security_trade(
                currency_ledger, currency_asset.internal_asset_id,
                event.event_date, event.event_id, event.ibkr_transaction_id,
                qty_to_cover, eur_per_unit
            )
            results.extend(short_cover_results)
            if short_cover_results:
                total_fx_gl = sum(rgl.gross_gain_loss_eur for rgl in short_cover_results)
                logger.info(
                    f"Cash Merger {event.event_id}: Implicit FX from covering {qty_to_cover:.2f} "
                    f"{proceeds_currency} short position. FX gain/loss: {total_fx_gl:.2f} EUR"
                )
            foreign_amount = foreign_amount - qty_to_cover

        if foreign_amount > Decimal("1e-10"):
            currency_processor.create_long_lot_for_security_trade(
                currency_ledger, event.event_date, event.ibkr_transaction_id,
                foreign_amount, eur_per_unit
            )
            logger.info(
                f"Cash Merger {event.event_id}: Created {proceeds_currency} lot from merger proceeds: "
                f"{foreign_amount:.2f} @ {eur_per_unit:.6f} EUR per unit"
            )

        return results


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

        # 1. Get target ledger. The registry is keyed by (account_key, asset_id).
        fifo_ledgers = context.get('fifo_ledgers', {})
        target_ledger = fifo_ledgers.get((DEFAULT_ACCOUNT, event.new_asset_internal_id))
        if target_ledger is None:
            logger.error(f"No FIFO ledger for target asset {event.new_asset_internal_id}. "
                         f"Cannot transfer lots for merger event {event.event_id}.")
            return []

        # 2. Drain source lots (both long and short)
        source_long_lots = ledger.drain_all_long_lots()
        source_short_lots = ledger.drain_all_short_lots()
        if not source_long_lots and not source_short_lots:
            logger.warning(f"Source ledger for {ledger.asset_internal_id} has no lots to transfer "
                           f"for merger event {event.event_id}.")
            return []

        # 3. Atomic prepare-then-commit transfer to target
        try:
            target_ledger.receive_all_lots_from_merger(
                source_long_lots, source_short_lots,
                event.new_shares_received_per_old, event
            )
        except Exception as e:
            # ROLLBACK: restore drained lots to source ledger.
            # Target ledger is untouched (prepare-then-commit guarantees this).
            from src.utils.type_utils import parse_ibkr_date
            from datetime import datetime
            ledger.lots.extend(source_long_lots)
            ledger.lots.sort(key=lambda lot: (
                parse_ibkr_date(lot.acquisition_date) or datetime.min.date(),
                lot.source_transaction_id
            ))
            ledger.short_lots.extend(source_short_lots)
            ledger.short_lots.sort(key=lambda lot: (
                parse_ibkr_date(lot.opening_date) or datetime.min.date(),
                lot.source_transaction_id
            ))
            logger.error(f"Failed to transfer lots from {ledger.asset_internal_id} "
                         f"to {target_ledger.asset_internal_id}. Rolled back. Error: {e}")
            raise

        # 4. Post-condition assertions
        assert len(ledger.lots) == 0, \
            f"Source ledger {ledger.asset_internal_id} must have no long lots after merger"
        assert len(ledger.short_lots) == 0, \
            f"Source ledger {ledger.asset_internal_id} must have no short lots after merger"

        logger.info(f"Transferred {len(source_long_lots)} long + {len(source_short_lots)} "
                     f"short lots from {ledger.asset_internal_id} to "
                     f"{target_ledger.asset_internal_id} "
                     f"(ratio: {event.new_shares_received_per_old})")

        return []  # Stock-for-stock merger is tax-neutral, no RGL

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

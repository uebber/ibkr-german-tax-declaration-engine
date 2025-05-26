# src/engine/event_processors/option_processor.py
import logging
from typing import List, Dict, Any, Tuple, Optional 
import uuid 
from decimal import Decimal, Context

from src.domain.events import (
    OptionExerciseEvent, OptionAssignmentEvent, OptionExpirationWorthlessEvent,
    FinancialEvent
)
from src.domain.assets import Option, Asset 
from src.domain.enums import AssetCategory, FinancialEventType, TaxReportingCategory, RealizationType
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger, ConsumedLotDetail
from src.identification.asset_resolver import AssetResolver 
from .base_processor import EventProcessor
import src.config as global_config # For precisions if needed
from src.utils.type_utils import parse_ibkr_date # For holding period calculation

logger = logging.getLogger(__name__)

class OptionExerciseProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, OptionExerciseEvent):
            logger.error(f"OptionExerciseProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
            return []
        
        if not ledger: 
            logger.error(f"OptionExerciseProcessor received event {event.event_id} but no ledger provided. Cannot process.")
            return []

        asset_resolver: Optional[AssetResolver] = context.get('asset_resolver')
        pending_adjustments: Optional[Dict[uuid.UUID, Tuple[Decimal, uuid.UUID, str]]] = context.get('pending_option_adjustments')

        if asset_resolver is None or pending_adjustments is None:
            logger.critical(f"Missing asset_resolver or pending_option_adjustments in context for OptionExerciseProcessor. Event ID: {event.event_id}")
            raise ValueError("Missing required context for option exercise processing.")

        option_asset = asset_resolver.get_asset_by_id(event.asset_internal_id)

        if not isinstance(option_asset, Option):
            logger.error(f"Event {event.event_id} (Exercise) references asset {event.asset_internal_id} which is not an Option type ({type(option_asset).__name__}). Skipping adjustment storage.")
            return [] 

        if option_asset.underlying_asset_internal_id is None:
            logger.critical(f"Option asset {option_asset.get_classification_key()} (ID: {option_asset.internal_asset_id}) "
                            f"is missing underlying link. Cannot process exercise event {event.event_id}.")
            raise ValueError(f"Option asset {option_asset.internal_asset_id} missing underlying link for exercise.")

        if option_asset.option_type not in ['C', 'P']:
            logger.error(f"Option asset {option_asset.internal_asset_id} has invalid option_type '{option_asset.option_type}' for exercise event {event.event_id}.")
            return [] 

        try:
            logger.info(f"Processing {event.event_type.name} for option {ledger.asset_internal_id} on {event.event_date} (ID: {event.event_id}). Qty Contracts: {event.quantity_contracts}")
            
            consumed_lot_details: List[ConsumedLotDetail] = ledger.consume_long_option_get_cost(event.quantity_contracts)
            
            total_premium_paid_eur = ledger.ctx.create_decimal(0)
            for detail in consumed_lot_details:
                cost_for_detail = ledger.ctx.multiply(detail.consumed_quantity, detail.value_per_unit_eur)
                total_premium_paid_eur = ledger.ctx.add(total_premium_paid_eur, cost_for_detail)
            
            logger.debug(f"  Total premium paid (cost) for exercised option {option_asset.get_classification_key()}: {total_premium_paid_eur} EUR from {len(consumed_lot_details)} consumed lot details.")

            pending_adjustments[event.event_id] = (total_premium_paid_eur, event.asset_internal_id, option_asset.option_type)
            logger.info(f"  Stored pending adjustment for stock trade linked to exercise event {event.event_id}. "
                        f"Total Premium Paid (Cost): {total_premium_paid_eur} EUR, Option Type: {option_asset.option_type}")

        except ValueError as e:
            logger.critical(f"Error consuming long option lots for exercise event {event.event_id}: {e}", exc_info=True)
            raise e 

        return [] 

class OptionAssignmentProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, OptionAssignmentEvent):
            logger.error(f"OptionAssignmentProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
            return []
            
        if not ledger: 
            logger.error(f"OptionAssignmentProcessor received event {event.event_id} but no ledger provided. Cannot process.")
            return []

        asset_resolver: Optional[AssetResolver] = context.get('asset_resolver')
        pending_adjustments: Optional[Dict[uuid.UUID, Tuple[Decimal, uuid.UUID, str]]] = context.get('pending_option_adjustments')

        if asset_resolver is None or pending_adjustments is None:
            logger.critical(f"Missing asset_resolver or pending_option_adjustments in context for OptionAssignmentProcessor. Event ID: {event.event_id}")
            raise ValueError("Missing required context for option assignment processing.")

        option_asset = asset_resolver.get_asset_by_id(event.asset_internal_id)

        if not isinstance(option_asset, Option):
            logger.error(f"Event {event.event_id} (Assignment) references asset {event.asset_internal_id} which is not an Option type ({type(option_asset).__name__}). Skipping adjustment storage.")
            return []

        if option_asset.underlying_asset_internal_id is None:
            logger.critical(f"Option asset {option_asset.get_classification_key()} (ID: {option_asset.internal_asset_id}) "
                            f"is missing underlying link. Cannot process assignment event {event.event_id}.")
            raise ValueError(f"Option asset {option_asset.internal_asset_id} missing underlying link for assignment.")

        if option_asset.option_type not in ['C', 'P']:
             logger.error(f"Option asset {option_asset.internal_asset_id} has invalid option_type '{option_asset.option_type}' for assignment event {event.event_id}.")
             return []

        try:
            logger.info(f"Processing {event.event_type.name} for option {ledger.asset_internal_id} on {event.event_date} (ID: {event.event_id}). Qty Contracts: {event.quantity_contracts}")
            
            consumed_lot_details: List[ConsumedLotDetail] = ledger.consume_short_option_get_proceeds(event.quantity_contracts)

            total_premium_received_eur = ledger.ctx.create_decimal(0)
            for detail in consumed_lot_details:
                proceeds_for_detail = ledger.ctx.multiply(detail.consumed_quantity, detail.value_per_unit_eur)
                total_premium_received_eur = ledger.ctx.add(total_premium_received_eur, proceeds_for_detail)

            logger.debug(f"  Total premium received (proceeds) for assigned option {option_asset.get_classification_key()}: {total_premium_received_eur} EUR from {len(consumed_lot_details)} consumed lot details.")

            pending_adjustments[event.event_id] = (total_premium_received_eur, event.asset_internal_id, option_asset.option_type)
            logger.info(f"  Stored pending adjustment for stock trade linked to assignment event {event.event_id}. "
                        f"Total Premium Received (Proceeds): {total_premium_received_eur} EUR, Option Type: {option_asset.option_type}")

        except ValueError as e:
            logger.critical(f"Error consuming short option lots for assignment event {event.event_id}: {e}", exc_info=True)
            raise e 

        return [] 

class OptionExpirationWorthlessProcessor(EventProcessor):
    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, OptionExpirationWorthlessEvent):
            logger.error(f"OptionExpirationWorthlessProcessor received incorrect event type: {type(event).__name__} (ID: {event.event_id}).")
            return []
        
        if not ledger:
            logger.error(f"OptionExpirationWorthlessProcessor received event {event.event_id} but no ledger provided. Cannot process.")
            return []

        logger.info(f"Processing {event.event_type.name} for option {ledger.asset_internal_id} on {event.event_date} (ID: {event.event_id}). Quantity Contracts Expiring: {event.quantity_contracts}")
        
        realized_gains_losses: List[RealizedGainLoss] = []
        
        available_long_qty = sum(lot.quantity for lot in ledger.lots)
        available_short_qty = sum(lot.quantity_shorted for lot in ledger.short_lots)

        consumed_lot_details: List[ConsumedLotDetail] = []
        current_realization_type: Optional[RealizationType] = None

        if available_long_qty >= event.quantity_contracts:
            try:
                consumed_lot_details = ledger.consume_long_option_get_cost(event.quantity_contracts)
                current_realization_type = RealizationType.OPTION_EXPIRED_LONG # Renamed
                logger.info(f"  Option {ledger.asset_internal_id} expiration treated as LONG position expiring worthless.")
            except ValueError as e: 
                logger.warning(f"  Attempted to consume long option for worthless expiration failed: {e}. Trying short if applicable.")
        
        if not current_realization_type and available_short_qty >= event.quantity_contracts:
            try:
                consumed_lot_details = ledger.consume_short_option_get_proceeds(event.quantity_contracts)
                current_realization_type = RealizationType.OPTION_EXPIRED_SHORT # Renamed
                logger.info(f"  Option {ledger.asset_internal_id} expiration treated as SHORT position expiring worthless.")
            except ValueError as e:
                logger.warning(f"  Attempted to consume short option for worthless expiration failed: {e}.")
        
        if not current_realization_type:
            logger.error(f"  Could not determine if option {ledger.asset_internal_id} expiration (Event ID: {event.event_id}) was long or short, or insufficient lots. "
                         f"Available Long Qty: {available_long_qty}, Available Short Qty: {available_short_qty}, Expiring Qty: {event.quantity_contracts}. No RGL created.")
            return []

        for detail in consumed_lot_details:
            acq_date_obj = parse_ibkr_date(detail.original_lot_date)
            real_date_obj = parse_ibkr_date(event.event_date)
            holding_period_days: Optional[int] = None
            if acq_date_obj and real_date_obj and real_date_obj >= acq_date_obj:
                holding_period_days = (real_date_obj - acq_date_obj).days
            
            quantity_realized_for_rgl = detail.consumed_quantity 
            
            cost_basis_eur_per_unit_rgl: Decimal
            realization_value_eur_per_unit_rgl: Decimal
            
            if current_realization_type == RealizationType.OPTION_EXPIRED_LONG: # Renamed
                cost_basis_eur_per_unit_rgl = detail.value_per_unit_eur 
                realization_value_eur_per_unit_rgl = ledger.ctx.create_decimal(0)
            elif current_realization_type == RealizationType.OPTION_EXPIRED_SHORT: # Renamed
                cost_basis_eur_per_unit_rgl = ledger.ctx.create_decimal(0)
                realization_value_eur_per_unit_rgl = detail.value_per_unit_eur 
            else: 
                logger.error(f"Unexpected realization type {current_realization_type} in worthless expiration logic.")
                continue

            total_cost_basis_eur_rgl = ledger.ctx.multiply(quantity_realized_for_rgl, cost_basis_eur_per_unit_rgl)
            total_realization_value_eur_rgl = ledger.ctx.multiply(quantity_realized_for_rgl, realization_value_eur_per_unit_rgl)
            gross_gain_loss_eur = ledger.ctx.subtract(total_realization_value_eur_rgl, total_cost_basis_eur_rgl)
            
            tax_cat: TaxReportingCategory
            is_stillhalter_income_flag: bool = False # Renamed from is_option_premium_gain

            if gross_gain_loss_eur >= Decimal(0):
                tax_cat = TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN
                if current_realization_type == RealizationType.OPTION_EXPIRED_SHORT: # Renamed
                    is_stillhalter_income_flag = True # Renamed
            else:
                tax_cat = TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST
            
            rgl = RealizedGainLoss(
                originating_event_id=event.event_id,
                asset_internal_id=ledger.asset_internal_id,
                asset_category_at_realization=AssetCategory.OPTION, 
                acquisition_date=detail.original_lot_date,
                realization_date=event.event_date,
                realization_type=current_realization_type,
                quantity_realized=quantity_realized_for_rgl,
                unit_cost_basis_eur=cost_basis_eur_per_unit_rgl, # Renamed kwarg
                unit_realization_value_eur=realization_value_eur_per_unit_rgl, # Renamed kwarg
                total_cost_basis_eur=total_cost_basis_eur_rgl, # Renamed kwarg
                total_realization_value_eur=total_realization_value_eur_rgl,
                gross_gain_loss_eur=gross_gain_loss_eur,
                holding_period_days=holding_period_days,
                is_taxable_under_section_23=True, # Renamed kwarg (Options are Termingeschäfte, not §23)
                tax_reporting_category=tax_cat,
                is_stillhalter_income=is_stillhalter_income_flag # Renamed kwarg
            )
            realized_gains_losses.append(rgl)
            logger.debug(f"  Generated RGL for worthless option expiration: Asset {ledger.asset_internal_id}, Realiz.Type {current_realization_type.name}, Qty {quantity_realized_for_rgl}, G/L {gross_gain_loss_eur:.2f} EUR, Acq. Date {detail.original_lot_date}")

        return realized_gains_losses

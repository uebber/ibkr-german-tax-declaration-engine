# src/engine/event_processors/option_processor.py
import logging
from typing import List, Dict, Any, Tuple, Optional 
import uuid 
from decimal import Decimal, Context

from src.utils.account_utils import account_key, DEFAULT_ACCOUNT
from src.domain.events import (
    OptionExerciseEvent, OptionAssignmentEvent, OptionExpirationWorthlessEvent,
    OptionCashSettlementEvent, FinancialEvent
)
from src.domain.assets import Option, Asset 
from src.domain.enums import AssetCategory, FinancialEventType, TaxReportingCategory, RealizationType
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger, ConsumedLotDetail
from src.domain.exceptions import ProcessingError
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
            raise ProcessingError(f"OptionExerciseProcessor: event {event.event_id} references asset {event.asset_internal_id} which is {type(option_asset).__name__}, not Option.")

        if option_asset.underlying_asset_internal_id is None:
            logger.info(f"Option asset {option_asset.get_classification_key()} (ID: {option_asset.internal_asset_id}) "
                        f"has no underlying link — likely a cash-settled index option. "
                        f"Skipping exercise event {event.event_id} (handled by OptionCashSettlementProcessor).")
            return []

        if option_asset.option_type not in ['C', 'P']:
            raise ProcessingError(f"OptionExerciseProcessor: option asset {option_asset.internal_asset_id} has invalid option_type '{option_asset.option_type}' for exercise event {event.event_id}.")

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
            raise ProcessingError(f"OptionAssignmentProcessor: event {event.event_id} references asset {event.asset_internal_id} which is {type(option_asset).__name__}, not Option.")

        if option_asset.underlying_asset_internal_id is None:
            logger.info(f"Option asset {option_asset.get_classification_key()} (ID: {option_asset.internal_asset_id}) "
                        f"has no underlying link — likely a cash-settled index option. "
                        f"Skipping assignment event {event.event_id} (handled by OptionCashSettlementProcessor).")
            return []

        if option_asset.option_type not in ['C', 'P']:
             raise ProcessingError(f"OptionAssignmentProcessor: option asset {option_asset.internal_asset_id} has invalid option_type '{option_asset.option_type}' for assignment event {event.event_id}.")

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


class OptionCashSettlementProcessor(EventProcessor):
    """Processes cash-settled index option exercises/assignments (SPX, ESTX50, etc.).

    For cash-settled options, there is no stock delivery. Instead:
    1. The option position is closed (FIFO lots consumed for cost basis)
    2. The cash settlement proceeds represent the realization value
    3. Gain/Loss = Cash Settlement Proceeds - Option Premium Cost Basis

    The cash_settlement_proceeds sign convention:
    - Positive = money received (long option exercised ITM)
    - Negative = money paid out (short option assigned ITM)
    """

    def process(self, event: FinancialEvent, ledger: FifoLedger, context: Dict[str, Any]) -> List[RealizedGainLoss]:
        if not isinstance(event, OptionCashSettlementEvent):
            logger.error(f"OptionCashSettlementProcessor received incorrect event type: "
                        f"{type(event).__name__} (ID: {event.event_id}).")
            return []

        if not ledger:
            logger.error(f"OptionCashSettlementProcessor received event {event.event_id} "
                        f"but no ledger provided. Cannot process.")
            return []

        asset_resolver: Optional[AssetResolver] = context.get('asset_resolver')
        if asset_resolver is None:
            logger.critical(f"Missing asset_resolver in context for OptionCashSettlementProcessor. "
                          f"Event ID: {event.event_id}")
            raise ValueError("Missing required context for cash settlement processing.")

        option_asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if not isinstance(option_asset, Option):
            logger.error(f"Event {event.event_id} (Cash Settlement) references asset "
                        f"{event.asset_internal_id} which is not an Option type. Skipping.")
            return []

        logger.info(f"Processing OPTION_CASH_SETTLEMENT for {option_asset.get_classification_key()} "
                    f"on {event.event_date} (ID: {event.event_id}). "
                    f"Proceeds: {event.cash_settlement_proceeds} {event.local_currency}, "
                    f"Qty Contracts: {event.quantity_contracts}")

        realized_gains_losses: List[RealizedGainLoss] = []

        # Determine if this is a long or short position settlement
        # Positive proceeds = long option exercised (received money)
        # Negative proceeds = short option assigned (paid money)
        proceeds = event.cash_settlement_proceeds
        is_long_settlement = proceeds > Decimal("0")

        # Get the EUR value of proceeds from enrichment
        proceeds_eur = event.gross_amount_eur
        if proceeds_eur is None or proceeds_eur == Decimal("0"):
            # Fallback: if gross_amount_eur not set, we can't compute proper EUR values
            logger.warning(f"Cash settlement {event.event_id}: gross_amount_eur is {proceeds_eur}. "
                          f"EUR conversion may be missing.")
            # Still proceed — the value will be recorded as 0 EUR if not enriched

        # Commission in EUR (from enrichment or as-is if EUR)
        commission_eur = event.commission_eur or Decimal("0")
        commission_abs_eur = commission_eur.copy_abs()

        try:
            consumed_lot_details: List[ConsumedLotDetail]
            current_realization_type: RealizationType

            available_long_qty = sum(lot.quantity for lot in ledger.lots)
            available_short_qty = sum(lot.quantity_shorted for lot in ledger.short_lots)

            if is_long_settlement and available_long_qty > Decimal("0"):
                # Long option exercised → consume long lots
                qty_to_consume = min(event.quantity_contracts, available_long_qty)
                consumed_lot_details = ledger.consume_long_option_get_cost(qty_to_consume)
                current_realization_type = RealizationType.OPTION_CASH_SETTLED_LONG
            elif not is_long_settlement and available_short_qty > Decimal("0"):
                # Short option assigned → consume short lots
                qty_to_consume = min(event.quantity_contracts, available_short_qty)
                consumed_lot_details = ledger.consume_short_option_get_proceeds(qty_to_consume)
                current_realization_type = RealizationType.OPTION_CASH_SETTLED_SHORT
            elif available_long_qty > Decimal("0"):
                # Fallback: try long lots even if proceeds are negative
                qty_to_consume = min(event.quantity_contracts, available_long_qty)
                consumed_lot_details = ledger.consume_long_option_get_cost(qty_to_consume)
                current_realization_type = RealizationType.OPTION_CASH_SETTLED_LONG
                logger.warning(f"Cash settlement {event.event_id}: Negative proceeds but consuming "
                             f"long lots (possible mismatch).")
            elif available_short_qty > Decimal("0"):
                # Fallback: try short lots even if proceeds are positive
                qty_to_consume = min(event.quantity_contracts, available_short_qty)
                consumed_lot_details = ledger.consume_short_option_get_proceeds(qty_to_consume)
                current_realization_type = RealizationType.OPTION_CASH_SETTLED_SHORT
                logger.warning(f"Cash settlement {event.event_id}: Positive proceeds but consuming "
                             f"short lots (possible mismatch).")
            else:
                logger.error(f"Cash settlement {event.event_id}: No option lots available to consume. "
                           f"Long: {available_long_qty}, Short: {available_short_qty}")
                return []

        except ValueError as e:
            logger.critical(f"Error consuming option lots for cash settlement {event.event_id}: {e}",
                          exc_info=True)
            raise e

        # Compute total premium (cost basis for longs, proceeds for shorts)
        total_premium_eur = ledger.ctx.create_decimal(0)
        for detail in consumed_lot_details:
            premium_for_detail = ledger.ctx.multiply(detail.consumed_quantity, detail.value_per_unit_eur)
            total_premium_eur = ledger.ctx.add(total_premium_eur, premium_for_detail)

        # Calculate gain/loss for each consumed lot detail
        settlement_eur = proceeds_eur if proceeds_eur is not None else Decimal("0")

        for detail in consumed_lot_details:
            acq_date_obj = parse_ibkr_date(detail.original_lot_date)
            real_date_obj = parse_ibkr_date(event.event_date)
            holding_period_days: Optional[int] = None
            if acq_date_obj and real_date_obj and real_date_obj >= acq_date_obj:
                holding_period_days = (real_date_obj - acq_date_obj).days

            quantity_realized = detail.consumed_quantity
            premium_per_unit_eur = detail.value_per_unit_eur

            if current_realization_type == RealizationType.OPTION_CASH_SETTLED_LONG:
                # Long option: cost basis = premium paid, realization = settlement received
                cost_basis_per_unit = premium_per_unit_eur
                # Distribute settlement proportionally across consumed lots
                if total_premium_eur != Decimal("0"):
                    lot_fraction = ledger.ctx.divide(
                        ledger.ctx.multiply(detail.consumed_quantity, detail.value_per_unit_eur),
                        total_premium_eur
                    )
                else:
                    lot_fraction = ledger.ctx.divide(detail.consumed_quantity,
                                                     sum(d.consumed_quantity for d in consumed_lot_details))
                realization_value_total = ledger.ctx.multiply(settlement_eur, lot_fraction)
                commission_portion = ledger.ctx.multiply(commission_abs_eur, lot_fraction)

                total_cost = ledger.ctx.multiply(quantity_realized, cost_basis_per_unit)
                total_realization = realization_value_total
                realization_per_unit = ledger.ctx.divide(total_realization, quantity_realized) if quantity_realized != Decimal("0") else Decimal("0")

                # Subtract commission from realization (reduces gain or increases loss)
                gross_gl = ledger.ctx.subtract(total_realization, ledger.ctx.add(total_cost, commission_portion))

                rgl = RealizedGainLoss(
                    originating_event_id=event.event_id,
                    asset_internal_id=ledger.asset_internal_id,
                    asset_category_at_realization=AssetCategory.OPTION,
                    acquisition_date=detail.original_lot_date,
                    realization_date=event.event_date,
                    realization_type=current_realization_type,
                    quantity_realized=quantity_realized,
                    unit_cost_basis_eur=cost_basis_per_unit,
                    unit_realization_value_eur=realization_per_unit,
                    total_cost_basis_eur=total_cost,
                    total_realization_value_eur=total_realization,
                    gross_gain_loss_eur=gross_gl,
                    holding_period_days=holding_period_days,
                    tax_reporting_category=(TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN
                                            if gross_gl >= Decimal("0")
                                            else TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST),
                    is_stillhalter_income=False,
                )
                realized_gains_losses.append(rgl)
                logger.debug(f"  Generated RGL for cash settlement: Asset {ledger.asset_internal_id}, "
                            f"Type {current_realization_type.name}, Qty {quantity_realized}, "
                            f"G/L {gross_gl:.2f} EUR")

            else:
                # Short option (Stillhalter), STRICT SPLIT (BFH VIII R 55/13):
                # the premium received is Nr. 11 income and the Barausgleich a
                # SEPARATE Termingeschäft loss under Abs. 2 S. 1 Nr. 3a — they
                # are two tax events and must not be netted into one figure
                # (the gross Zeile-22 loss declaration is the FULL settlement).
                if total_premium_eur != Decimal("0"):
                    lot_fraction = ledger.ctx.divide(
                        ledger.ctx.multiply(detail.consumed_quantity, detail.value_per_unit_eur),
                        total_premium_eur
                    )
                else:
                    lot_fraction = ledger.ctx.divide(detail.consumed_quantity,
                                                     sum(d.consumed_quantity for d in consumed_lot_details))

                settlement_portion = ledger.ctx.multiply(settlement_eur, lot_fraction).copy_abs()
                commission_portion = ledger.ctx.multiply(commission_abs_eur, lot_fraction)
                premium_total = ledger.ctx.multiply(quantity_realized, premium_per_unit_eur)

                # Leg 1 — Stillhalterprämie (§20 Abs. 1 Nr. 11): income in full.
                premium_rgl = RealizedGainLoss(
                    originating_event_id=event.event_id,
                    asset_internal_id=ledger.asset_internal_id,
                    asset_category_at_realization=AssetCategory.OPTION,
                    acquisition_date=detail.original_lot_date,
                    realization_date=event.event_date,
                    realization_type=current_realization_type,
                    quantity_realized=quantity_realized,
                    unit_cost_basis_eur=Decimal("0"),
                    unit_realization_value_eur=premium_per_unit_eur,
                    total_cost_basis_eur=Decimal("0"),
                    total_realization_value_eur=premium_total,
                    gross_gain_loss_eur=premium_total,
                    holding_period_days=holding_period_days,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN,
                    is_stillhalter_income=True,
                )
                realized_gains_losses.append(premium_rgl)

                # Leg 2 — Barausgleich (§20 Abs. 2 S. 1 Nr. 3a): loss in full
                # (settlement paid + commission), separate from the premium.
                settlement_loss = ledger.ctx.add(settlement_portion, commission_portion)
                if settlement_loss > Decimal("0"):
                    settlement_rgl = RealizedGainLoss(
                        originating_event_id=event.event_id,
                        asset_internal_id=ledger.asset_internal_id,
                        asset_category_at_realization=AssetCategory.OPTION,
                        acquisition_date=detail.original_lot_date,
                        realization_date=event.event_date,
                        realization_type=current_realization_type,
                        quantity_realized=quantity_realized,
                        unit_cost_basis_eur=ledger.ctx.divide(settlement_loss, quantity_realized) if quantity_realized != Decimal("0") else Decimal("0"),
                        unit_realization_value_eur=Decimal("0"),
                        total_cost_basis_eur=settlement_loss,
                        total_realization_value_eur=Decimal("0"),
                        gross_gain_loss_eur=ledger.ctx.minus(settlement_loss),
                        holding_period_days=holding_period_days,
                        tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST,
                        is_stillhalter_income=False,
                    )
                    realized_gains_losses.append(settlement_rgl)
                logger.debug(f"  Generated SPLIT RGLs for Stillhalter cash settlement: "
                            f"premium +{premium_total:.2f} EUR (Nr. 11), "
                            f"Barausgleich -{settlement_loss:.2f} EUR (Nr. 3a)")

        # Process currency impact for cash settlement proceeds
        currency_rgls = self._process_currency_impact(event, context)
        realized_gains_losses.extend(currency_rgls)

        return realized_gains_losses

    def _process_currency_impact(
        self, event: OptionCashSettlementEvent, context: Dict[str, Any]
    ) -> List[RealizedGainLoss]:
        """Handle implicit currency acquisition/consumption from cash settlement."""
        results: List[RealizedGainLoss] = []

        currency = (event.local_currency or "").upper()
        if not currency or currency == "EUR":
            return results

        proceeds_abs = event.cash_settlement_proceeds.copy_abs()
        eur_amount = event.gross_amount_eur
        if not proceeds_abs or not eur_amount or proceeds_abs <= Decimal("0") or eur_amount <= Decimal("0"):
            return results

        asset_resolver = context.get('asset_resolver')
        currency_fifo_ledgers = context.get('currency_fifo_ledgers')
        currency_processor = context.get('currency_processor')

        if not asset_resolver or not currency_processor or currency_fifo_ledgers is None:
            return results

        currency_asset = asset_resolver.get_cash_balance_asset(currency)
        if not currency_asset:
            return results

        currency_ledger = currency_fifo_ledgers.get((account_key(event.account_id), currency_asset.internal_asset_id))
        if not currency_ledger:
            return results

        eur_per_unit = eur_amount / proceeds_abs

        if event.cash_settlement_proceeds > Decimal("0"):
            # Received money → acquire currency (cover shorts first, then create lot)
            available_short_qty = sum(lot.quantity_shorted for lot in currency_ledger.short_lots)
            if available_short_qty > Decimal("0"):
                qty_to_cover = min(proceeds_abs, available_short_qty)
                short_cover_results = currency_processor.cover_short_lots_for_security_trade(
                    currency_ledger, currency_asset.internal_asset_id,
                    event.event_date, event.event_id, event.ibkr_transaction_id,
                    qty_to_cover, eur_per_unit
                )
                results.extend(short_cover_results)
                proceeds_abs -= qty_to_cover

            if proceeds_abs > Decimal("1e-10"):
                currency_processor.create_long_lot_for_security_trade(
                    currency_ledger, event.event_date, event.ibkr_transaction_id,
                    proceeds_abs, eur_per_unit
                )
        else:
            # Paid money → consume currency
            available_long_qty = sum(lot.quantity for lot in currency_ledger.lots)
            if available_long_qty > Decimal("0"):
                qty_to_consume = min(proceeds_abs, available_long_qty)
                long_results = currency_processor.realize_long_lots_for_security_trade(
                    currency_ledger, currency_asset.internal_asset_id,
                    event.event_date, event.event_id, event.ibkr_transaction_id,
                    qty_to_consume, eur_per_unit
                )
                results.extend(long_results)
                proceeds_abs -= qty_to_consume

            if proceeds_abs > Decimal("1e-10"):
                currency_processor.open_short_position_for_security_trade(
                    currency_ledger, event.event_date, event.ibkr_transaction_id,
                    proceeds_abs, eur_per_unit
                )

        return results

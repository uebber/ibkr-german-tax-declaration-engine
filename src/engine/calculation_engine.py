# src/engine/calculation_engine.py
import logging
from typing import List, Tuple, Dict, DefaultDict, Optional, Any
import uuid
from decimal import Decimal, getcontext, Context
from collections import defaultdict
from datetime import datetime, date

from src.domain.events import (
    FinancialEvent, TradeEvent, CorpActionSplitForward, CorpActionMergerCash,
    CorpActionStockDividend, CorpActionMergerStock, CorporateActionEvent,
    OptionExerciseEvent, OptionAssignmentEvent, OptionExpirationWorthlessEvent,
    OptionLifecycleEvent, CashFlowEvent, FeeEvent, WithholdingTaxEvent, CurrencyConversionEvent
)
from src.domain.assets import Asset, Stock, Bond, AssetCategory, Option, InvestmentFund
from src.identification.asset_resolver import AssetResolver
from src.domain.results import RealizedGainLoss, VorabpauschaleData
from src.domain.enums import FinancialEventType, InvestmentFundType 
from src.utils.sorting_utils import get_event_sort_key
from src.utils.type_utils import parse_ibkr_date

from .fifo_manager import FifoLedger
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider
import src.config as config

# Import the event processors
from .event_processors.base_processor import EventProcessor
from .event_processors.trade_processor import TradeProcessor
from .event_processors.corporate_action_processor import (
    SplitProcessor, MergerCashProcessor, StockDividendProcessor, MergerStockProcessor,
    GenericCorporateActionProcessor
)
from .event_processors.option_processor import (
    OptionExerciseProcessor, OptionAssignmentProcessor, OptionExpirationWorthlessProcessor
)


logger = logging.getLogger(__name__)

def _format_asset_info(asset_obj) -> str:
    """Helper to format asset information for logging."""
    if not asset_obj:
        return "Unknown Asset"
    desc = asset_obj.description or asset_obj.get_classification_key()
    symbol = asset_obj.ibkr_symbol or "N/A"
    return f"'{desc}' (Symbol: {symbol})"

def run_main_calculations(
    financial_events: List[FinancialEvent],
    asset_resolver: AssetResolver,
    currency_converter: CurrencyConverter,
    exchange_rate_provider: ECBExchangeRateProvider,
    tax_year: int,
    internal_calculation_precision: int, # Renamed from internal_working_precision
    decimal_rounding_mode: str
) -> Tuple[List[RealizedGainLoss], List[VorabpauschaleData], List[FinancialEvent], int]: 
    """
    Runs the main calculation logic:
    1. Separates historical and current year events.
    2. Initializes FIFO ledgers based on SOY positions and historical trades.
    3. Processes current year events chronologically using dedicated processors.
    4. Performs EOY quantity validation (logs errors but does not halt).
    5. Calculates Vorabpauschale (currently placeholder).
    6. Returns calculated results (Realized G/L, Vorabpauschale), processed events, and EOY mismatch count.
    """
    logger.info(f"Starting main calculation engine for tax year {tax_year} with {len(financial_events)} events.")
    ctx = Context(prec=internal_calculation_precision, rounding=decimal_rounding_mode) # Renamed internal_working_precision

    realized_gains_losses: List[RealizedGainLoss] = []
    vorabpauschale_data_items: List[VorabpauschaleData] = []

    historical_events_by_asset: DefaultDict[uuid.UUID, List[FinancialEvent]] = defaultdict(list)
    current_year_events: List[FinancialEvent] = []

    pending_option_adjustments: Dict[uuid.UUID, Tuple[Decimal, uuid.UUID, str]] = {}

    tax_year_start_date_str = f"{tax_year}-01-01"
    tax_year_end_date_str = f"{tax_year}-12-31"
    tax_year_start_date_obj = parse_ibkr_date(tax_year_start_date_str)
    tax_year_end_date_obj = parse_ibkr_date(tax_year_end_date_str)
    
    if not tax_year_start_date_obj:
        logger.error(f"Could not parse tax year start date: {tax_year_start_date_str}. Aborting calculations.")
        return [], [], financial_events, 0 
    if not tax_year_end_date_obj:
        logger.error(f"Could not parse tax year end date: {tax_year_end_date_str}. Aborting calculations.")
        return [], [], financial_events, 0 

    logger.info("Separating historical and current year events...")
    filtered_events_count = 0
    for event in financial_events:
        try:
            event_sort_key = get_event_sort_key(event, asset_resolver)
            event_date_obj = event_sort_key[0] 
        except ValueError as e:
            logger.error(f"Event {event.event_id} has invalid date or identifier ({e}). Cannot process.")
            continue 

        if event_date_obj < tax_year_start_date_obj:
            if isinstance(event, (TradeEvent, CorpActionSplitForward, CorpActionStockDividend)): 
                historical_events_by_asset[event.asset_internal_id].append(event)
        elif event_date_obj <= tax_year_end_date_obj:
            current_year_events.append(event)
        else:
            filtered_events_count += 1
            logger.debug(f"Filtered out event {event.event_id} with date {event_date_obj} (after tax year {tax_year})")
    
    if filtered_events_count > 0:
        logger.info(f"Filtered out {filtered_events_count} events occurring after tax year {tax_year}")

    logger.info(f"Separated events: {sum(len(v) for v in historical_events_by_asset.values())} relevant historical events for SOY FIFO reconstruction, "
                f"{len(current_year_events)} current tax year events.")

    fifo_ledgers: Dict[uuid.UUID, FifoLedger] = {}

    logger.info("Initializing FIFO ledgers from Start-of-Year positions and historical data...")
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if asset_obj.asset_category != AssetCategory.CASH_BALANCE:
            asset_multiplier_val: Optional[Decimal] = None
            asset_fund_type: Optional[InvestmentFundType] = None

            if isinstance(asset_obj, Option):
                asset_multiplier_val = asset_obj.multiplier
            elif isinstance(asset_obj, InvestmentFund):
                asset_fund_type = asset_obj.fund_type
            
            ledger = FifoLedger(
                asset_internal_id=asset_id, asset_category=asset_obj.asset_category,
                asset_multiplier_from_asset=asset_multiplier_val,
                currency_converter=currency_converter, exchange_rate_provider=exchange_rate_provider,
                internal_working_precision=internal_calculation_precision, # Pass renamed variable
                decimal_rounding_mode=decimal_rounding_mode,
                fund_type=asset_fund_type 
            )
            
            asset_historical_events_for_soy_init = []
            if asset_id in historical_events_by_asset:
                try:
                    sort_key_func = lambda e: get_event_sort_key(e, asset_resolver)
                    asset_historical_events_for_soy_init = sorted(
                        historical_events_by_asset[asset_id], key=sort_key_func
                    )
                except ValueError as e:
                    logger.critical(f"Fatal error sorting historical events for asset {asset_obj.get_classification_key()} (ID: {asset_id}): {e}. Cannot guarantee deterministic order for FIFO init. Aborting.")
                    raise e

            try:
                ledger.initialize_lots_from_soy(
                    asset=asset_obj,
                    all_historical_events_for_asset=asset_historical_events_for_soy_init, 
                    tax_year=tax_year
                )
            except ValueError as e:
                logger.critical(f"Fatal error initializing FIFO lots from SOY for asset {asset_obj.get_classification_key()} (ID: {asset_id}): {e}. Aborting.")
                raise e 

            fifo_ledgers[asset_id] = ledger

    logger.info(f"Initialized {len(fifo_ledgers)} FIFO ledgers.")

    logger.info("Initializing event processors...")
    trade_processor = TradeProcessor()
    split_processor = SplitProcessor()
    merger_cash_processor = MergerCashProcessor()
    stock_dividend_processor = StockDividendProcessor()
    merger_stock_processor = MergerStockProcessor()
    generic_ca_processor = GenericCorporateActionProcessor()
    option_exercise_processor = OptionExerciseProcessor()
    option_assignment_processor = OptionAssignmentProcessor()
    option_expiration_processor = OptionExpirationWorthlessProcessor()

    event_processor_map: Dict[FinancialEventType, EventProcessor] = {
        FinancialEventType.TRADE_BUY_LONG: trade_processor,
        FinancialEventType.TRADE_SELL_LONG: trade_processor,
        FinancialEventType.TRADE_SELL_SHORT_OPEN: trade_processor,
        FinancialEventType.TRADE_BUY_SHORT_COVER: trade_processor,
        FinancialEventType.CORP_SPLIT_FORWARD: split_processor, # Renamed
        FinancialEventType.CORP_MERGER_CASH: merger_cash_processor, # Renamed
        FinancialEventType.CORP_STOCK_DIVIDEND: stock_dividend_processor, # Renamed
        FinancialEventType.CORP_MERGER_STOCK: merger_stock_processor, # Renamed
        FinancialEventType.OPTION_EXERCISE: option_exercise_processor,
        FinancialEventType.OPTION_ASSIGNMENT: option_assignment_processor,
        FinancialEventType.OPTION_EXPIRATION_WORTHLESS: option_expiration_processor,
    }

    logger.info(f"Processing {len(current_year_events)} current tax year events using dispatch table...")
    for event_idx, event in enumerate(current_year_events):
        asset_object = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if not asset_object:
            logger.error(f"Event {event.event_id} ({event.event_type.name}) references unknown asset {event.asset_internal_id}. Skipping processing.")
            continue

        ledger = fifo_ledgers.get(asset_object.internal_asset_id)
        processor = event_processor_map.get(event.event_type)

        if not processor and isinstance(event, CorporateActionEvent):
            logger.warning(f"Event {event.event_id} is CorporateActionEvent type {event.event_type.name} for asset {_format_asset_info(asset_object)} but not in specific map. Using GenericCorporateActionProcessor.")
            processor = generic_ca_processor
        elif processor and isinstance(event, CorporateActionEvent) and not isinstance(event, (CorpActionSplitForward, CorpActionMergerCash, CorpActionStockDividend, CorpActionMergerStock)):
            logger.warning(f"Event {event.event_id} is generic CorporateActionEvent with type {event.event_type.name} for asset {_format_asset_info(asset_object)} but specific processor expects subclass. Using GenericCorporateActionProcessor.")
            processor = generic_ca_processor

        if processor and (ledger or event.event_type in [FinancialEventType.OPTION_EXERCISE, FinancialEventType.OPTION_ASSIGNMENT, FinancialEventType.OPTION_EXPIRATION_WORTHLESS]):
            if not ledger and asset_object.asset_category == AssetCategory.OPTION:
                logger.warning(f"Option event {event.event_id} ({event.event_type.name}) occurred, but no FIFO ledger exists. Processor will handle.")
            elif not ledger and asset_object.asset_category != AssetCategory.CASH_BALANCE:
                logger.warning(f"Non-option/non-cash event {event.event_id} ({event.event_type.name}) requires ledger, but none found for asset {asset_object.get_classification_key()}. Skipping processor.")
                continue

            try:
                context: Dict[str, Any] = {
                    'asset_resolver': asset_resolver,
                    'pending_option_adjustments': pending_option_adjustments,
                    'currency_converter': currency_converter 
                }
                logger.debug(f"Dispatching event {event.event_id} ({event.event_type.name}) to {type(processor).__name__}")

                current_ledger = ledger if ledger else None
                new_rgls = processor.process(event, current_ledger, context)

                if new_rgls:
                    realized_gains_losses.extend(new_rgls)
                    logger.debug(f"  Processor generated {len(new_rgls)} RGL records.")

            except ValueError as e:
                logger.critical(f"Fatal error processing event {event.event_id} ({event.event_type.name}) for asset {asset_object.get_classification_key()} via {type(processor).__name__}: {e}. Aborting.")
                raise e
            except TypeError as e:
                logger.error(f"Type error processing event {event.event_id} ({event.event_type.name}) with {type(processor).__name__}: {e}. Skipping.", exc_info=True)
                continue
            except NotImplementedError:
                logger.warning(f"Processor {type(processor).__name__} indicated logic for event type {event.event_type.name} (ID: {event.event_id}) is not yet implemented.")
                continue

        elif not ledger and asset_object.asset_category != AssetCategory.CASH_BALANCE:
            logger.warning(f"Event {event.event_id} ({event.event_type.name}) for non-cash asset {asset_object.get_classification_key()} occurred, but no FIFO ledger exists. Skipping processing for this event.")

        # Handle capital repayments directly
        elif event.event_type == FinancialEventType.CAPITAL_REPAYMENT and ledger:
            try:
                repayment_amount_eur = event.gross_amount_eur or Decimal('0')
                logger.info(f"Processing capital repayment for {asset_object.get_classification_key()}: {repayment_amount_eur} EUR")
                excess = ledger.reduce_cost_basis_for_capital_repayment(repayment_amount_eur)
                if excess > Decimal('0'):
                    logger.info(f"Capital repayment excess {excess} EUR becomes taxable dividend income")
                    # Store excess for later aggregation - we'll handle this in loss offsetting
                    if not hasattr(event, '_excess_taxable_amount_eur'):
                        event._excess_taxable_amount_eur = excess
            except Exception as e:
                logger.error(f"Error processing capital repayment {event.event_id}: {e}", exc_info=True)

        elif not processor:
            if event.event_type not in [
                FinancialEventType.DIVIDEND_CASH, FinancialEventType.CAPITAL_REPAYMENT, FinancialEventType.DISTRIBUTION_FUND,
                FinancialEventType.INTEREST_RECEIVED, FinancialEventType.INTEREST_PAID_STUECKZINSEN,
                FinancialEventType.PAYMENT_IN_LIEU_DIVIDEND, FinancialEventType.WITHHOLDING_TAX,
                FinancialEventType.FEE_TRANSACTION, FinancialEventType.CURRENCY_CONVERSION
            ]:
                logger.warning(f"No processor mapped and no ledger interaction expected for event type: {event.event_type.name} (ID: {event.event_id}).")
            else:
                logger.debug(f"Event type {event.event_type.name} (ID: {event.event_id}) does not require FIFO ledger processing. Skipping processor dispatch.")


    logger.info("Finished processing current year events.")
    logger.info(f"Pending option adjustments stored: {len(pending_option_adjustments)}")

    logger.info("Performing End-of-Year (EOY) quantity validation...")
    eoy_mismatch_errors = 0 
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if asset_obj.asset_category == AssetCategory.CASH_BALANCE:
            continue

        ledger = fifo_ledgers.get(asset_id)
        calculated_eoy_qty: Decimal

        if ledger:
            calculated_eoy_qty = ledger.get_current_position_quantity()
        else:
            calculated_eoy_qty = Decimal(0)
            if asset_obj.soy_quantity is not None and asset_obj.soy_quantity != Decimal(0): # Renamed
                logger.warning(f"EOY Validation: Asset {asset_obj.get_classification_key()} had SOY qty {asset_obj.soy_quantity} but no ledger found at EOY. Calculated EOY assumed 0.") # Renamed

        reported_eoy_qty = asset_obj.eoy_quantity
        try:
            tolerance_exponent = -(ctx.prec // 2)
            comparison_tolerance = Decimal('1e' + str(tolerance_exponent))
        except Exception:
            logger.warning(f"Could not calculate dynamic tolerance from precision {ctx.prec}. Using fixed tolerance 1e-8.")
            comparison_tolerance = Decimal('1e-8')

        if reported_eoy_qty is not None:
            if abs(calculated_eoy_qty - reported_eoy_qty) > comparison_tolerance:
                logger.error(
                    f"CRITICAL EOY MISMATCH for {asset_obj.description or asset_obj.get_classification_key()} (ID: {asset_id}): "
                    f"Calculated EOY Qty: {calculated_eoy_qty}, Reported EOY Qty (from file): {reported_eoy_qty}. "
                    f"Difference: {calculated_eoy_qty - reported_eoy_qty}"
                )
                eoy_mismatch_errors += 1
        elif abs(calculated_eoy_qty) > comparison_tolerance: 
            logger.error( 
                f"EOY MISMATCH for {asset_obj.description or asset_obj.get_classification_key()} (ID: {asset_id}): "
                f"Calculated EOY Qty: {calculated_eoy_qty}, but asset NOT found in EOY positions report (implying reported EOY Qty is 0)."
            )
            eoy_mismatch_errors += 1 

    if eoy_mismatch_errors > 0:
        logger.error(f"EOY Quantity Validation FAILED with {eoy_mismatch_errors} critical mismatches. Processing will continue, but results may be inaccurate.")
    else:
        logger.info("EOY Quantity Validation passed or no critical mismatches found against reported EOY positions.")

    logger.info("Vorabpauschale calculation skipped (result is €0 for tax year 2023).")

    processed_income_events_for_output: List[FinancialEvent] = list(current_year_events)

    logger.info(f"Calculation engine finished. Produced {len(realized_gains_losses)} RealizedGainLoss records.")
    logger.info(f"Calculation engine produced {len(vorabpauschale_data_items)} VorabpauschaleData records (expected 0 for 2023).")

    return realized_gains_losses, vorabpauschale_data_items, processed_income_events_for_output, eoy_mismatch_errors

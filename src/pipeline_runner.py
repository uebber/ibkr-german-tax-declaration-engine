# src/pipeline_runner.py
import logging
from decimal import Decimal, getcontext
from typing import Any, Optional, Tuple, List, Dict # Python 3.8 compatibility for List, Dict

# Configuration
import src.config as config

# Domain objects and Enums (assuming they are accessible)
from src.domain.assets import Asset # For type hinting if needed
from src.domain.events import FinancialEvent
from src.domain.results import RealizedGainLoss, VorabpauschaleData

# Core components
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from src.classification.asset_classifier import AssetClassifier
from src.processing.enrichment import enrich_financial_events
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider, ExchangeRateProvider # Added base for custom provider
from src.engine.calculation_engine import run_main_calculations
from src.identification.asset_resolver import AssetResolver

logger = logging.getLogger(__name__)

class ProcessingOutput:
    """
    Encapsulates the results of the core processing pipeline.
    """
    def __init__(self,
                 realized_gains_losses: List[RealizedGainLoss],
                 vorabpauschale_items: List[VorabpauschaleData],
                 processed_income_events: List[FinancialEvent], # Assuming this is the third item from run_main_calculations
                 all_financial_events_enriched: List[FinancialEvent],
                 asset_resolver: AssetResolver,
                 eoy_mismatch_error_count: int):
        self.realized_gains_losses = realized_gains_losses
        self.vorabpauschale_items = vorabpauschale_items
        self.processed_income_events = processed_income_events
        self.all_financial_events_enriched = all_financial_events_enriched
        self.asset_resolver = asset_resolver
        self.eoy_mismatch_error_count = eoy_mismatch_error_count
        # For EOY state checks in tests, final assets can be fetched from asset_resolver
        self.final_assets_by_id: Dict[Any, Asset] = asset_resolver.assets_by_internal_id


def run_core_processing_pipeline(
    trades_file_path: str,
    cash_transactions_file_path: str,
    positions_start_file_path: str,
    positions_end_file_path: str,
    corporate_actions_file_path: str,
    interactive_classification_mode: bool,
    tax_year_to_process: int = config.TAX_YEAR, # Allow override for testing
    custom_rate_provider: Optional[ExchangeRateProvider] = None # For testing ECB mock
) -> ProcessingOutput:
    """
    Runs the core data processing pipeline: parsing, enrichment, and calculations.
    Returns a ProcessingOutput object containing all relevant results.
    """
    logger.info("Initializing system components for pipeline...")
    asset_classifier = AssetClassifier(
        cache_file_path=config.CLASSIFICATION_CACHE_FILE_PATH, # Renamed from CLASSIFICATION_CACHE_FILE
    )
    asset_resolver = AssetResolver(asset_classifier=asset_classifier)
    orchestrator = ParsingOrchestrator(
        asset_resolver=asset_resolver,
        asset_classifier=asset_classifier,
        interactive_classification=interactive_classification_mode
    )

    logger.info("Starting parsing pipeline...")
    try:
        all_financial_events_raw = orchestrator.run_parsing_pipeline(
            trades_file=trades_file_path,
            cash_transactions_file=cash_transactions_file_path,
            positions_start_file=positions_start_file_path,
            positions_end_file=positions_end_file_path,
            corporate_actions_file=corporate_actions_file_path,
            tax_year=tax_year_to_process
        )
    except ValueError as e:
        logger.critical(f"Parsing pipeline failed: {e}. Check input data and configuration.")
        # Re-raise or handle as per application's error strategy for pipeline failures
        raise  # Or sys.exit(1) if this function is allowed to terminate
    except Exception as e:
        logger.critical(f"Parsing pipeline failed with unexpected error: {e}", exc_info=True)
        raise

    logger.info(f"Parsing pipeline completed. Discovered {len(asset_resolver.assets_by_internal_id)} unique assets.")
    logger.info(f"Generated {len(all_financial_events_raw)} raw financial event objects.")

    if custom_rate_provider:
        rate_provider = custom_rate_provider
        logger.info("Using custom exchange rate provider.")
    else:
        rate_provider = ECBExchangeRateProvider(
            cache_file_path=config.ECB_RATES_CACHE_FILE_PATH, # Renamed from ECB_RATES_CACHE_FILE
            max_fallback_days_override=config.MAX_FALLBACK_DAYS_EXCHANGE_RATES,
            currency_code_mapping_override=config.CURRENCY_CODE_MAPPING_ECB
        )
        try:
            logger.info("ECB exchange rates provider initialized.")
        except Exception as e:
            logger.error(f"Failed to load ECB exchange rates: {e}. Currency conversions might fail.")
            # Decide on error strategy: raise, or continue with potential failures later?
            # For now, logging error and continuing.

    currency_converter = CurrencyConverter(rate_provider=rate_provider)

    logger.info("Enriching financial events (e.g., EUR conversion)...")
    financial_events_enriched = enrich_financial_events(
        financial_events=all_financial_events_raw,
        currency_converter=currency_converter,
        internal_calculation_precision=config.INTERNAL_CALCULATION_PRECISION, # Renamed parameter
        decimal_rounding_mode=config.DECIMAL_ROUNDING_MODE
    )
    logger.info(f"Enrichment completed. {len(financial_events_enriched)} events processed.")

    logger.info(f"Running calculation engine for tax year {tax_year_to_process}...")
    eoy_mismatch_error_count_calc = 0
    try:
        # Ensure run_main_calculations uses the passed tax_year_to_process
        realized_gains_losses, vorabpauschale_items, processed_income_events, eoy_mismatch_error_count_calc = run_main_calculations(
            financial_events=financial_events_enriched,
            asset_resolver=orchestrator.asset_resolver, # Use the resolver from the orchestrator
            currency_converter=currency_converter,
            exchange_rate_provider=rate_provider,
            tax_year=tax_year_to_process,
            internal_calculation_precision=config.INTERNAL_CALCULATION_PRECISION, # Renamed parameter
            decimal_rounding_mode=config.DECIMAL_ROUNDING_MODE
        )
    except Exception as e:
        logger.critical(f"Calculation engine failed with unexpected error: {e}", exc_info=True)
        raise # Re-raise for higher level handling or test assertion

    logger.info("Calculation engine run completed.")
    if eoy_mismatch_error_count_calc > 0:
         logger.warning(f"Calculation engine reported {eoy_mismatch_error_count_calc} EOY quantity mismatch errors.")


    return ProcessingOutput(
        realized_gains_losses=realized_gains_losses,
        vorabpauschale_items=vorabpauschale_items,
        processed_income_events=processed_income_events,
        all_financial_events_enriched=financial_events_enriched,
        asset_resolver=orchestrator.asset_resolver,
        eoy_mismatch_error_count=eoy_mismatch_error_count_calc
    )

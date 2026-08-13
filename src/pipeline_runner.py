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
from src.processing.data_gaps import DataGap, DataGapCollector
from src.processing.fund_prices import (
    FundPriceStore, make_price_prompt, resolve_year_start_prices)
from src.processing.vorabpauschale_declarations import (
    VorabpauschaleDeclarationStore, make_declaration_prompt)
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
                 eoy_mismatch_error_count: int,
                 data_gaps: Optional[List["DataGap"]] = None,
                 declaration_store: Optional["VorabpauschaleDeclarationStore"] = None):
        self.realized_gains_losses = realized_gains_losses
        self.vorabpauschale_items = vorabpauschale_items
        self.processed_income_events = processed_income_events
        self.all_financial_events_enriched = all_financial_events_enriched
        self.asset_resolver = asset_resolver
        self.eoy_mismatch_error_count = eoy_mismatch_error_count
        # Data-gap channel: every "input could not fully support the
        # computation" condition, for the report's gap section.
        self.data_gaps: List["DataGap"] = data_gaps or []
        # The record of what was declared as Vorabpauschale, carried out so that the
        # commit step at filing writes to the same store the run read from.
        self.declaration_store = declaration_store
        # For EOY state checks in tests, final assets can be fetched from asset_resolver
        self.final_assets_by_id: Dict[Any, Asset] = asset_resolver.assets_by_internal_id


def run_core_processing_pipeline(
    trades_file_path: str,
    cash_transactions_file_path: str,
    positions_start_file_path: str,
    positions_end_file_path: str,
    corporate_actions_file_path: str,
    interactive_classification_mode: bool,
    # REQUIRED — no global default: a run's tax year must be explicit at the
    # boundary (src/main.py via CLI/config). A silent module-global default made
    # behavior depend on ambient, monkeypatchable state. See src/run_context.py.
    tax_year_to_process: int,
    custom_rate_provider: Optional[ExchangeRateProvider] = None, # For testing ECB mock
    cash_balance_file_path: Optional[str] = None,  # For currency FIFO processing
    options_eae_file_path: Optional[str] = None,  # For cash-settled option processing
    # Moves of a holding between the taxpayer's own accounts. Optional: a person who has
    # never exported the report has no rows.
    transfers_file_path: Optional[str] = None,
    grants_file_path: Optional[str] = None,
    # Years of the replayed window the Transfers export does not cover, comma-joined.
    # Only the multi-account warning reads it, and only to refuse to call a partly
    # exported window complete. "" means either complete or absent, which the path above
    # already distinguishes.
    transfers_missing_years: str = "",
    # Preceding calendar year's position snapshots. Required for the Vorabpauschale, which for
    # a VZ Y declaration is the one computed for calendar Y-1 (18 Abs. 3 InvStG). Optional at
    # this boundary: the engine decides what a missing snapshot means once it knows whether any
    # fund is held. See reference/investment-tax-law/invstg-18-vorabpauschale.md.
    positions_prior_start_file_path: Optional[str] = None,
    positions_prior_end_file_path: Optional[str] = None,
    positions_prior_opening_file_path: Optional[str] = None,
    # Checkpoint marks for the historical replay: {year: Positions-{year}-EoY.csv}. Each is a
    # point where the reconstruction is compared against the broker and, on disagreement,
    # replaced by it. Absent (or empty) means the replay runs as one uninterrupted interval,
    # which is what it did before checkpointing.
    positions_mark_file_paths: Optional[Dict[int, str]] = None
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
            positions_prior_start_file=positions_prior_start_file_path,
            positions_prior_end_file=positions_prior_end_file_path,
            positions_prior_opening_file=positions_prior_opening_file_path,
            corporate_actions_file=corporate_actions_file_path,
            cash_balance_file=cash_balance_file_path,
            options_eae_file=options_eae_file_path,
            transfers_file=transfers_file_path,
            grants_file=grants_file_path,
            positions_mark_files=positions_mark_file_paths,
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
            currency_code_mapping_override=config.CURRENCY_CODE_MAPPING_ECB,
            pegged_currency_rates=config.PEGGED_CURRENCY_RATES
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
        data_gap_collector = DataGapCollector()
        for key, description in orchestrator.vorabpauschale_price_substitutions:
            data_gap_collector.record(
                code="VORABPAUSCHALE_PRICE_WRONG_DAY",
                subject=f"{key} ({description})" if description else key,
                detail=(
                    "Der Ruecknahmepreis zu Beginn des Kalenderjahres fehlt im Positions-"
                    "Snapshot, obwohl der Fonds zu Jahresbeginn gehalten wurde. Fuer die "
                    "Vorabpauschale wurde ersatzweise der letzte vor Jahresbeginn "
                    "festgesetzte Preis verwendet -- einen Boersentag zu frueh statt ein "
                    "Jahr zu spaet; der Basisertrag stammt damit vom falschen Tag und ist "
                    "bei gestiegenem Kurs zu niedrig."
                ),
            )

        # A fund bought during the Vorabpauschale year is absent from that year's
        # start-of-year snapshot, so no price reached it above. That is ordinary and
        # the figure is still due (18 Abs. 1 Satz 2 with Abs. 2), so the price is
        # asked for and remembered rather than skipped or invented. Runs here, after
        # classification has settled which assets are funds and before the engine,
        # which then sees a price like any other. See src/processing/fund_prices.py.
        resolve_year_start_prices(
            assets=list(orchestrator.asset_resolver.assets_by_internal_id.values()),
            vorabpauschale_year=tax_year_to_process - 1,
            store=FundPriceStore(),
            # The resolved run setting, not config.IS_INTERACTIVE_CLASSIFICATION:
            # --no-interactive overrides the config, and reading the global here
            # meant a --no-interactive run still tried to prompt and died on EOF.
            interactive=interactive_classification_mode,
            data_gap_collector=data_gap_collector,
            # The events go in so the prompt can show what the account paid per
            # unit beside the price being asked for; the issuer lookup fills in
            # the default. Both are aids to a person answering, and neither
            # answers for them -- see src/processing/fund_price_sources.py.
            ask=make_price_prompt(financial_events_enriched),
            auto_fetch=getattr(config, "FUND_PRICE_AUTO_FETCH", True),
        )

        # What was DECLARED as Vorabpauschale on earlier returns. Read on every run and
        # written on none: the Zeile 53 deduction (19 Abs. 1 Satz 3 InvStG) may rest only
        # on declared amounts, and a run before filing is not a declaration. Committing
        # is `src/main.py --commit-vorabpauschale-declaration`.
        # See src/processing/vorabpauschale_declarations.py.
        declaration_store = VorabpauschaleDeclarationStore()

        realized_gains_losses, vorabpauschale_items, processed_income_events, eoy_mismatch_error_count_calc = run_main_calculations(
            financial_events=financial_events_enriched,
            asset_resolver=orchestrator.asset_resolver, # Use the resolver from the orchestrator
            currency_converter=currency_converter,
            exchange_rate_provider=rate_provider,
            tax_year=tax_year_to_process,
            internal_calculation_precision=config.INTERNAL_CALCULATION_PRECISION, # Renamed parameter
            decimal_rounding_mode=config.DECIMAL_ROUNDING_MODE,
            data_gap_collector=data_gap_collector,
            mark_positions=orchestrator.mark_positions,
            soy_positions=orchestrator.soy_positions,
            eoy_positions=orchestrator.eoy_positions,
            cash_balances=orchestrator.cash_balances,
            prior_year_positions_available=bool(
                positions_prior_start_file_path and positions_prior_end_file_path
            ),
            transfers_file_supplied=orchestrator.transfers_file_supplied,
            transfers_missing_years=transfers_missing_years,
            declaration_store=declaration_store,
            # Earlier holding-period years are ASKED about, never assumed. A
            # --no-interactive run passes None: nobody can be asked, so nothing is
            # taken for granted and the year is reported unanswered. See
            # src/processing/vorabpauschale_declarations.py.
            ask_for_declared_vorabpauschale=(
                make_declaration_prompt() if interactive_classification_mode else None),
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
        eoy_mismatch_error_count=eoy_mismatch_error_count_calc,
        data_gaps=data_gap_collector.gaps,
        declaration_store=declaration_store,
    )

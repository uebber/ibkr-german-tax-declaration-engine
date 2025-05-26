# src/main.py
import logging
import sys
from decimal import getcontext
import os # For path operations if needed for PDF output

# Configuration and CLI
import src.config as config
from src.cli import parse_arguments

# Core pipeline runner
from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput

# Loss Offsetting Engine
from src.engine.loss_offsetting import LossOffsettingEngine

# Reporting
from src.reporting.console_reporter import generate_console_tax_report, generate_stock_trade_report_for_symbol
from src.reporting.diagnostic_reports import (
    print_grouped_event_details,
    print_asset_positions_diagnostic,
    print_assets_by_category_diagnostic,
    print_object_counts_diagnostic,
    print_realized_gains_losses_diagnostic,
    print_vorabpauschale_diagnostic
)
from src.reporting.pdf_generator import PdfReportGenerator # Added PDF Generator

# Configure logging (can be moved to a dedicated setup function if complex)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def setup_decimal_context():
    """Sets the global decimal precision and rounding mode."""
    getcontext().prec = config.INTERNAL_CALCULATION_PRECISION # Renamed from INTERNAL_WORKING_PRECISION
    valid_rounding_modes = ["ROUND_CEILING", "ROUND_DOWN", "ROUND_FLOOR", "ROUND_HALF_DOWN",
                            "ROUND_HALF_EVEN", "ROUND_HALF_UP", "ROUND_UP", "ROUND_05UP"]
    rounding_mode_to_set = config.DECIMAL_ROUNDING_MODE
    if rounding_mode_to_set not in valid_rounding_modes:
        logger.warning(f"Invalid DECIMAL_ROUNDING_MODE '{rounding_mode_to_set}' in config. Using ROUND_HALF_UP as fallback.")
        rounding_mode_to_set = "ROUND_HALF_UP"
    
    getcontext().rounding = rounding_mode_to_set
    logger.info(f"Global decimal precision set to {getcontext().prec}, rounding mode to {getcontext().rounding}.")


def main_application():
    """
    Main application entry point.
    Parses arguments, runs processing, and generates reports.
    """
    args = parse_arguments()
    setup_decimal_context()

    logger.info("Starting IBKR German Tax Declaration Engine...")

    try:
        processing_results: ProcessingOutput = run_core_processing_pipeline(
            trades_file_path=args.trades,
            cash_transactions_file_path=args.cash,
            positions_start_file_path=args.pos_start,
            positions_end_file_path=args.pos_end,
            corporate_actions_file_path=args.corp_actions,
            interactive_classification_mode=args.interactive,
            tax_year_to_process=config.TAX_YEAR 
        )
    except Exception as e:
        logger.critical(f"Core processing pipeline failed: {e}. Exiting.", exc_info=True)
        sys.exit(1)

    loss_offsetting_summary = None
    if args.report_tax_declaration or args.pdf_output_file: # Calculate if any report needing it is active
        logger.info("Calculating final tax figures with loss offsetting...")
        try:
            loss_engine = LossOffsettingEngine(
                realized_gains_losses=processing_results.realized_gains_losses,
                vorabpauschale_items=processing_results.vorabpauschale_items,
                # THE FIX IS HERE: Use processed_income_events instead of all_financial_events_enriched
                current_year_financial_events=processing_results.processed_income_events,
                asset_resolver=processing_results.asset_resolver,
                tax_year=config.TAX_YEAR,
                apply_conceptual_derivative_loss_capping=config.APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING
            )
            loss_offsetting_summary = loss_engine.calculate_reporting_figures()
            logger.info("Loss offsetting calculation completed.")
        except Exception as e:
            logger.error(f"Loss offsetting calculation failed: {e}. Tax reports might be incomplete or inaccurate.", exc_info=True)
            
    asset_resolver = processing_results.asset_resolver
    tax_year = config.TAX_YEAR 

    if args.group_by_type:
        print_assets_by_category_diagnostic(asset_resolver)
        print_asset_positions_diagnostic(asset_resolver)
        # For diagnostic output, it might still be useful to see all events
        print_grouped_event_details(processing_results.all_financial_events_enriched, asset_resolver)
        print_realized_gains_losses_diagnostic(processing_results.realized_gains_losses, asset_resolver)
        print_vorabpauschale_diagnostic(processing_results.vorabpauschale_items)

    if args.count_objects:
        print_object_counts_diagnostic(
            asset_resolver=asset_resolver,
            all_events=processing_results.all_financial_events_enriched, # Display count of all
            rgl_items=processing_results.realized_gains_losses,
            vp_items=processing_results.vorabpauschale_items
        )

    if args.report_tax_declaration:
        if loss_offsetting_summary:
            generate_console_tax_report(
                realized_gains_losses=processing_results.realized_gains_losses,
                vorabpauschale_items=processing_results.vorabpauschale_items,
                # The console reporter uses this list and filters it itself for its detailed views
                all_financial_events=processing_results.all_financial_events_enriched, 
                asset_resolver=asset_resolver,
                tax_year=tax_year,
                eoy_mismatch_count=processing_results.eoy_mismatch_error_count,
                loss_offsetting_summary=loss_offsetting_summary
            )
        else:
            logger.error("Console tax declaration report cannot be generated because loss offsetting calculation failed or was skipped.")

    if args.pdf_output_file: 
        if loss_offsetting_summary:
            logger.info(f"Generating PDF report to {args.pdf_output_file}...")
            eoy_mismatch_details_for_pdf = [] 
            if processing_results.eoy_mismatch_error_count > 0 and not eoy_mismatch_details_for_pdf:
                 logger.warning(f"EOY mismatch count is {processing_results.eoy_mismatch_error_count}, but detailed mismatch data is not available for the PDF report. The PDF section will be limited.")

            pdf_generator = PdfReportGenerator(
                loss_offsetting_result=loss_offsetting_summary,
                # The PDF report should also use correctly filtered events for income sections
                all_financial_events=processing_results.processed_income_events, 
                realized_gains_losses=processing_results.realized_gains_losses,
                vorabpauschale_items=processing_results.vorabpauschale_items,
                assets_by_id=asset_resolver.assets_by_internal_id,
                tax_year=tax_year,
                eoy_mismatch_details=eoy_mismatch_details_for_pdf,
                report_version="v3.2.3" # Updated to match PRD version reflecting this fix
            )
            pdf_generator.generate_report(args.pdf_output_file)
        else:
            logger.error(f"PDF report '{args.pdf_output_file}' cannot be generated because loss offsetting calculation failed or was skipped.")


    if args.report_stock_trades_details:
        generate_stock_trade_report_for_symbol(
            stock_symbol_arg=args.report_stock_trades_details,
            # This report filters events itself, so passing all enriched is fine
            all_financial_events=processing_results.all_financial_events_enriched, 
            rgl_items=processing_results.realized_gains_losses,
            asset_resolver=asset_resolver,
            tax_year=tax_year
        )

    logger.info("Processing finished.")
    if processing_results.eoy_mismatch_error_count > 0:
        logger.warning(f"There were {processing_results.eoy_mismatch_error_count} EOY quantity mismatch errors. Review logs and output carefully.")

if __name__ == "__main__":
    main_application()

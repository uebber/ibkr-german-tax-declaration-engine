# src/cli.py
import argparse
import src.config as config # For default paths and settings

def parse_arguments():
    """Parses command line arguments for the application."""
    parser = argparse.ArgumentParser(description="IBKR German Tax Declaration Engine")
    
    # File paths
    parser.add_argument("--trades", default=config.TRADES_FILE_PATH, help="Path to trades CSV file.")
    parser.add_argument("--cash", default=config.CASH_TRANSACTIONS_FILE_PATH, help="Path to cash transactions CSV file.")
    parser.add_argument("--pos_start", default=config.POSITIONS_START_FILE_PATH, help="Path to start of year positions CSV file.")
    parser.add_argument("--pos_end", default=config.POSITIONS_END_FILE_PATH, help="Path to end of year positions CSV file.")
    parser.add_argument("--corp_actions", default=config.CORPORATE_ACTIONS_FILE_PATH, help="Path to corporate actions CSV file.")
    
    # Operational modes
    parser.add_argument("--interactive", action="store_true", default=None, help="Enable interactive asset classification. Overrides config if set.")
    parser.add_argument("--no-interactive", dest="interactive", action="store_false", help="Disable interactive asset classification. Overrides config if set.")
    
    # Reporting options
    parser.add_argument("--group-by-type", action="store_true", help="Print detailed events and asset information grouped by asset type/category.")
    parser.add_argument("--count-objects", action="store_true", help="Print counts of different object types after processing.")
    parser.add_argument("--debug-asset-summary", action="store_true", help="Print debug summary of each asset with classification and gross P/L.")
    parser.add_argument("--report-tax-declaration", action="store_true", help="Generate and print a console tax declaration summary. Also generates a PDF report.")
    parser.add_argument("--report-stock-trades-details", type=str, metavar="SYMBOL", help="Generate a detailed report of all trades for a given stock symbol in the tax year.")
    parser.add_argument("--pdf-output-file", type=str, default=None, help="Filename for the PDF report. Defaults to tax_report_<tax_year>.pdf if --report-tax-declaration is used.")

    args = parser.parse_args()

    # Handle the tri-state for args.interactive:
    # If neither --interactive nor --no-interactive is specified, args.interactive will be None.
    # In this case, we should use the value from config.py.
    if args.interactive is None:
        args.interactive = config.IS_INTERACTIVE_CLASSIFICATION # Updated config variable name
    
    if args.report_tax_declaration and args.pdf_output_file is None:
        args.pdf_output_file = f"tax_report_{config.TAX_YEAR}.pdf"
        
    return args

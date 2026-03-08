# src/cli.py
import argparse
import src.config as config # For default settings

def parse_arguments():
    """Parses command line arguments for the application."""
    parser = argparse.ArgumentParser(description="IBKR German Tax Declaration Engine")

    # Tax year selection
    parser.add_argument("--tax-year", type=int, default=config.TAX_YEAR, help=f"Tax year to process (default: {config.TAX_YEAR} from config.py).")

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

    # Download options
    download_group = parser.add_argument_group("IBKR Flex Download", "Download CSV data directly from IBKR Flex Web Service")
    download_group.add_argument("--download", action="store_true", help="Download current tax year data from IBKR before processing.")
    download_group.add_argument("--download-only", action="store_true", help="Download data from IBKR and exit (no processing).")
    download_group.add_argument("--force-download", action="store_true", help="Re-download even if cached files exist.")

    args = parser.parse_args()

    # Handle the tri-state for args.interactive:
    # If neither --interactive nor --no-interactive is specified, args.interactive will be None.
    # In this case, we should use the value from config.py.
    if args.interactive is None:
        args.interactive = config.IS_INTERACTIVE_CLASSIFICATION

    if args.report_tax_declaration and args.pdf_output_file is None:
        args.pdf_output_file = f"tax_report_{args.tax_year}.pdf"

    return args

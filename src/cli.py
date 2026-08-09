# src/cli.py
import argparse

# NOTE: this module deliberately does NOT import src.config. Parsing is purely
# syntactic; every run-defining value is left as None when the user did not
# supply it, and is resolved against the user config exactly once, in
# RunContext.from_config() (see src/run_context.py). Binding a config value as
# an argparse default here would put a second config read upstream of that
# boundary and make the tri-state unobservable.

def parse_arguments():
    """Parses command line arguments for the application.

    Run-defining options (--tax-year, --interactive/--no-interactive) default to
    None meaning "not specified"; the boundary resolves them from config.
    """
    parser = argparse.ArgumentParser(description="IBKR German Tax Declaration Engine")

    # Tax year selection
    parser.add_argument("--tax-year", type=int, default=None, help="Tax year to process (default: TAX_YEAR from config.py).")

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

    # Filing
    # The Zeile 53 deduction (19 Abs. 1 Satz 3 InvStG) may rest only on Vorabpauschalen
    # that were actually declared, so what was declared has to be recorded — and a run
    # before filing is not a declaration. Hence an explicit flag rather than an
    # automatic write: it says "this return has been filed with these figures".
    parser.add_argument(
        "--commit-vorabpauschale-declaration", action="store_true",
        help=("Record this run's Anlage KAP-INV Zeilen 9-13 figures as declared, for the "
              "preceding calendar year. Run it AFTER filing: the record is write-once and "
              "buys the Zeile 53 deduction when the units are eventually sold."))

    # Download options
    download_group = parser.add_argument_group("IBKR Flex Download", "Download CSV data directly from IBKR Flex Web Service")
    download_group.add_argument("--download", action="store_true", help="Download current tax year data from IBKR before processing.")
    download_group.add_argument("--download-only", action="store_true", help="Download data from IBKR and exit (no processing).")
    download_group.add_argument("--force-download", action="store_true", help="Re-download even if cached files exist.")

    # args.tax_year and args.interactive stay None when unspecified; resolving
    # them is the boundary's job. args.pdf_output_file likewise: its default
    # name embeds the tax year, which is only known after resolution, so it is
    # derived in src/main.py.
    return parser.parse_args()

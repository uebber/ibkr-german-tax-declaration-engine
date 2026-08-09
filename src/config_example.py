# src/config.py
# Copy this file to src/config.py and update with your values.

from decimal import Decimal

# Tax year being processed
TAX_YEAR = 2024

# Input/output directories
IMPORT_DIR = "data_import"  # Read-only source CSVs (never modified by the application)
WORKING_DIR = "data"        # Working copies prepared by data_preparation module

# Cache file for user classifications
CLASSIFICATION_CACHE_FILE_PATH = "cache/user_classifications.json"

# Cache file for ECB exchange rates
ECB_RATES_CACHE_FILE_PATH = "cache/ecb_exchange_rates.json"

# Cache file for year-start Ruecknahmepreise supplied by hand. A fund bought
# during the year is absent from that year's start-of-year positions snapshot,
# but 18 Abs. 1 Satz 2 InvStG still measures the Basisertrag from its price at
# the start of the calendar year. No IBKR export carries that price, so the
# interactive run asks for it and remembers the answer here. Like the
# classification cache, nothing recomputes this file.
FUND_PRICE_CACHE_FILE_PATH = "cache/user_fund_prices.json"

# Record of the Vorabpauschale DECLARED on earlier returns, per fund and calendar
# year. 19 Abs. 1 Satz 3 InvStG deducts the Vorabpauschalen angesetzt during the
# holding period when units are sold, and for units without inlaendischer
# Steuerabzug the Anleitung admits only what was actually declared -- so the
# deduction rests on this file, and nothing can recompute it. Written only from
# what the taxpayer states: the interactive prompt for earlier years, and
# `--commit-vorabpauschale-declaration` for the year the current return declares.
VORABPAUSCHALE_DECLARATION_STORE_PATH = "cache/vorabpauschale_declarations.json"

# Whether the run looks the year-start Ruecknahmepreis up in the published NAV
# history (iShares, SPDR, VanEck, Swiss Fund Data). 18 Abs. 1 Satz 2 InvStG asks
# for the Ruecknahmepreis and Satz 4 admits the position report's market price
# only where none was set, so the lookup runs for every fund held across the year
# end -- not only for one the report cannot price. Set False to keep the run
# offline: funds the report prices then use that price, recorded as the substitute
# it is, and a fund the report does not price stops the run.
# A price once obtained is cached, so only the first run per year is slow.
FUND_PRICE_AUTO_FETCH = True

# Taxpayer Information
TAXPAYER_NAME = "Your Name"  # Update with your name
ACCOUNT_ID = "U1234567"      # Update with your IBKR account ID

# Interactive mode for asset classification
IS_INTERACTIVE_CLASSIFICATION = True

# Numerical Precision
INTERNAL_CALCULATION_PRECISION = 28
DECIMAL_ROUNDING_MODE = "ROUND_HALF_UP"

# Output/Reporting Precisions
OUTPUT_PRECISION_AMOUNTS: Decimal = Decimal("0.01")
OUTPUT_PRECISION_PER_SHARE: Decimal = Decimal("0.000001")
PRECISION_QUANTITY: Decimal = Decimal("0.00000001")

# Fallback days for ECB exchange rates
MAX_FALLBACK_DAYS_EXCHANGE_RATES = 7
# Currency code mapping for ECB
CURRENCY_CODE_MAPPING_ECB: dict[str, str] = {"CNH": "CNY"}

# IBKR Flex Web Service
FLEX_TOKEN_ENV_VAR = "IBKR_FLEX_TOKEN"
FLEX_TOKEN_FILE = "~/.ibkr_flex_token"

# Pegged currency rates: currencies not published by ECB that are pegged to an ECB currency.
# Format: {currency_code: (base_currency_code, peg_factor)}
# The rate is derived as: pegged_currency/EUR = base_currency/EUR * peg_factor
# Example: SAR is pegged to USD at 3.75 SAR = 1 USD
PEGGED_CURRENCY_RATES: dict[str, tuple[str, str]] = {
    "SAR": ("USD", "3.75"),
}

# Flex Query IDs — set these after creating queries in IBKR portal
FLEX_QUERY_IDS: dict[str, int | None] = {
    "trades": None,
    "cash_transactions": None,
    "positions": None,
    "corporate_actions": None,
    "cash_balance": None,
    # Needed once, and only once, a cash-settled index option (SPX, ESTX50, ...) is
    # assigned or exercised: that settlement's proceeds are the whole realised gain and
    # appear in no other export. A run that needs it and does not have it stops and names
    # the contracts -- see ParsingOrchestrator._require_option_cash_settlements.
    "options_eae": None,
}

# Cache directory for downloaded Flex Query CSVs
FLEX_CACHE_DIR = "data/flex_cache"

# Naming prefix for the Flex Queries belonging to this engine, used by the
# Client Portal downloader (src/web_portal/) to find them by name instead of by
# the numeric IDs above. Set this if you gave your queries a common prefix —
# e.g. "MyTax", matching "MyTax Trades", "MyTax_Cash_Transactions" and so on;
# separators and case do not matter. Resolving by name survives recreating a
# query, which changes its ID. Leave as None to use FLEX_QUERY_IDS.
FLEX_QUERY_NAME_PREFIX: str | None = None

# Basiszins (§18 InvStG): lives in the law-as-data registry —
# src/tax_law/registry.py (source: reference/bmf-guidance/
# basiszins-vorabpauschale.md). Not user configuration.

# Configuration for Loss Offsetting Engine
# Determines if the conceptual summary for net derivative losses should apply the 20k EUR cap.
# Form reporting of derivative losses (Anlage KAP Zeile 24) is always gross and un-capped.
APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING: bool = True

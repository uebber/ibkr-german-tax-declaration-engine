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

# Cache file for user-supplied start-of-year fund NAVs (Vorabpauschale, mid-year acquisitions)
FUND_SOY_NAV_CACHE_FILE_PATH = "cache/fund_soy_nav.json"

# Cache file for user-declared Vorabpauschale per fund per year (§19 Abs. 1 S. 3 deduction at sale)

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
    "options_eae": None,         # Optional: for cash-settled index options (e.g. SPX, ESTX50)
}

# Cache directory for downloaded Flex Query CSVs
FLEX_CACHE_DIR = "data/flex_cache"

# Basiszins (§18 InvStG): lives in the law-as-data registry —
# src/tax_law/registry.py (source: reference/bmf-guidance/
# basiszins-vorabpauschale.md). Not user configuration.

# Configuration for Loss Offsetting Engine
# Determines if the conceptual summary for net derivative losses should apply the 20k EUR cap.
# Form reporting of derivative losses (Anlage KAP Zeile 24) is always gross and un-capped.
APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING: bool = True

# src/config.py

from decimal import Decimal # Added for Decimal type hint

# File paths for IBKR Flex Query reports
TRADES_FILE_PATH = "data/trades.csv"
CASH_TRANSACTIONS_FILE_PATH = "data/cash_transactions.csv"
POSITIONS_START_FILE_PATH = "data/positions_start_of_year.csv"
POSITIONS_END_FILE_PATH = "data/positions_end_of_year.csv"
CORPORATE_ACTIONS_FILE_PATH = "data/corporate_actions.csv" # e.g. corpact*.csv

# Cache file for user classifications
CLASSIFICATION_CACHE_FILE_PATH = "cache/user_classifications.json" # Renamed from CLASSIFICATION_CACHE_FILE

# Cache file for ECB exchange rates
ECB_RATES_CACHE_FILE_PATH = "cache/ecb_exchange_rates.json" # Renamed from ECB_RATES_CACHE_FILE

# Tax year being processed
TAX_YEAR = 2024

# Taxpayer Information (NEW)
TAXPAYER_NAME = "Warren Buffet"  # Placeholder - Please update
ACCOUNT_ID = "U1234567"          # Placeholder - Please update

# Interactive mode for asset classification
IS_INTERACTIVE_CLASSIFICATION = True # Set to False for non-interactive runs using cache/defaults # Renamed from INTERACTIVE_CLASSIFICATION

# Numerical Precision (Added as per PRD Section 2.0)
INTERNAL_CALCULATION_PRECISION = 28  # Recommended minimum # Renamed from INTERNAL_WORKING_PRECISION
DECIMAL_ROUNDING_MODE = "ROUND_HALF_UP" # Python's decimal module uses strings like 'ROUND_HALF_UP', 'ROUND_HALF_EVEN'

# Output/Reporting Precisions (Primarily for final display/reporting, not intermediate calculations)
# Referenced in enrichment.py and potentially reporting layer.
OUTPUT_PRECISION_AMOUNTS: Decimal = Decimal("0.01") # Renamed from PRECISION_TOTAL_AMOUNTS
OUTPUT_PRECISION_PER_SHARE: Decimal = Decimal("0.000001") # Renamed from PRECISION_PER_SHARE_AMOUNTS
PRECISION_QUANTITY: Decimal = Decimal("0.00000001") # Example for quantities, used in FifoLot

# Fallback days for ECB exchange rates (Example, used by ECBExchangeRateProvider if not overridden)
MAX_FALLBACK_DAYS_EXCHANGE_RATES = 7
# Currency code mapping for ECB (Example)
CURRENCY_CODE_MAPPING_ECB: dict[str, str] = {"CNH": "CNY"}

# Configuration for Loss Offsetting Engine (NEW)
# Determines if the conceptual summary for net derivative losses should apply the 20k EUR cap.
# Form reporting of derivative losses (Anlage KAP Zeile 24) is always gross and un-capped.
APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING: bool = True

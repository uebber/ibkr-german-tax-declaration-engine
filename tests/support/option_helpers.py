# tests/support/option_helpers.py
"""
Option-specific test helpers for Group 8 Options Lifecycle tests.

Provides:
- Option trade CSV creation functions following real IBKR data formats
- Option lifecycle event handling
- Helper constants for common option scenarios

IBKR Format Reference (from real data):
- Symbol: "P LEG  20230120 63 M" - Type + Underlying (padded) + YYYYMMDD + Strike + M
- Description: "LEG 20JAN23 63 P" - Human readable format
- Conid: Numeric IBKR contract ID like "604172754"
- UnderlyingConid: Numeric like "121764205"
"""

from decimal import Decimal
from typing import List, Optional, Any
from datetime import date
import hashlib

# Constants for option testing
DEFAULT_MULTIPLIER = Decimal("100")
DEFAULT_COMMISSION = Decimal("-1.00")

# Trade type mappings for options
OPTION_TRADE_TYPE_MAP = {
    "BL": ("BUY", "O"),    # Buy Long Open - buy to open long option position
    "SL": ("SELL", "C"),   # Sell Long Close - sell to close long option position
    "SSO": ("SELL", "O"),  # Sell Short Open - sell to open short option position
    "BSC": ("BUY", "C"),   # Buy Short Cover - buy to close short option position
}

# Month abbreviations for IBKR description format
MONTH_ABBREV = {
    "01": "JAN", "02": "FEB", "03": "MAR", "04": "APR",
    "05": "MAY", "06": "JUN", "07": "JUL", "08": "AUG",
    "09": "SEP", "10": "OCT", "11": "NOV", "12": "DEC",
}


def create_option_symbol_ibkr(
    underlying: str,
    expiry_date: str,  # YYYY-MM-DD format
    option_type: str,  # 'C' or 'P'
    strike: Decimal,
) -> str:
    """
    Create an IBKR-style option symbol.

    Real IBKR format: "P LEG  20230120 63 M"
    - Type (P/C)
    - Underlying (padded to min 4 chars)
    - Two spaces
    - YYYYMMDD
    - Strike (as integer if whole number)
    - M (monthly)
    """
    parts = expiry_date.split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid expiry_date format: {expiry_date}")

    date_str = f"{parts[0]}{parts[1]}{parts[2]}"
    # Format strike - remove trailing zeros after decimal
    strike_str = str(int(strike)) if strike == int(strike) else str(strike)
    underlying_padded = underlying.ljust(4)

    return f"{option_type} {underlying_padded} {date_str} {strike_str} M"


def create_option_description_ibkr(
    underlying: str,
    expiry_date: str,  # YYYY-MM-DD format
    option_type: str,  # 'C' or 'P'
    strike: Decimal,
) -> str:
    """
    Create an IBKR-style option description.

    Real IBKR format: "LEG 20JAN23 63 P"
    - Underlying
    - DDMMMYY (day + month abbrev + 2-digit year)
    - Strike
    - Type (P/C)
    """
    parts = expiry_date.split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid expiry_date format: {expiry_date}")

    day = parts[2]
    month = MONTH_ABBREV.get(parts[1], parts[1])
    year = parts[0][2:]  # Last 2 digits
    strike_str = str(int(strike)) if strike == int(strike) else str(strike)

    return f"{underlying} {day}{month}{year} {strike_str} {option_type}"


def generate_option_conid(
    underlying_conid: str,
    expiry_date: str,
    option_type: str,
    strike: Decimal,
) -> str:
    """
    Generate a deterministic numeric conid for test options.

    Uses a hash-based approach to generate a realistic-looking 9-digit numeric conid.
    This ensures the same option always gets the same conid, which is important for
    matching in tests.
    """
    key = f"{underlying_conid}_{expiry_date}_{option_type}_{strike}"
    hash_bytes = hashlib.md5(key.encode()).hexdigest()
    # Take first 9 hex digits and convert to decimal, keeping it under 1 billion
    numeric_hash = int(hash_bytes[:8], 16) % 900000000 + 100000000
    return str(numeric_hash)


def format_expiry_for_symbol(expiry_date: str) -> str:
    """Convert YYYY-MM-DD to YYMMDD for symbol."""
    parts = expiry_date.split("-")
    if len(parts) != 3:
        return expiry_date  # Return as-is if not proper format
    return f"{parts[0][2:]}{parts[1]}{parts[2]}"


def create_option_trade_data(
    account_id: str,
    currency: str,
    symbol: str,
    description: str,
    underlying_symbol: str,
    underlying_conid: str,
    option_conid: str,
    strike: Decimal,
    expiry_date: str,  # YYYY-MM-DD
    option_type: str,  # 'C' or 'P'
    trade_date: str,
    trade_type: str,  # 'BL', 'SL', 'SSO', 'BSC'
    quantity: Decimal,  # Number of contracts (positive)
    price: Decimal,  # Price per share (not per contract)
    multiplier: Decimal = DEFAULT_MULTIPLIER,
    commission: Decimal = DEFAULT_COMMISSION,
    transaction_id: Optional[str] = None,
    notes_codes: str = "",
) -> List[Any]:
    """
    Create a single option trade row for CSV input.

    Returns a list matching TRADES_FILE_HEADERS format.
    """
    direction, open_close = OPTION_TRADE_TYPE_MAP[trade_type]

    # Adjust quantity sign: negative for sells
    qty = quantity if direction == "BUY" else -quantity

    return [
        account_id,          # ClientAccountID
        currency,            # CurrencyPrimary
        "OPT",               # AssetClass
        option_type,         # SubCategory (P or C)
        symbol,              # Symbol
        description,         # Description
        "",                  # ISIN (options don't have ISIN)
        strike,              # Strike
        expiry_date,         # Expiry
        option_type,         # Put/Call
        trade_date,          # TradeDate
        qty,                 # Quantity
        price,               # TradePrice
        commission,          # IBCommission
        currency,            # IBCommissionCurrency
        direction,           # Buy/Sell
        transaction_id or f"OPT_T_{trade_date}_{qty}",  # TransactionID
        notes_codes,         # Notes/Codes
        underlying_symbol,   # UnderlyingSymbol
        option_conid,        # Conid
        underlying_conid,    # UnderlyingConid
        multiplier,          # Multiplier
        open_close,          # Open/CloseIndicator
    ]


def create_stock_trade_data(
    account_id: str,
    currency: str,
    symbol: str,
    description: str,
    isin: str,
    conid: str,
    trade_date: str,
    trade_type: str,  # 'BL', 'SL', 'SSO', 'BSC'
    quantity: Decimal,  # Number of shares (positive)
    price: Decimal,
    commission: Decimal = DEFAULT_COMMISSION,
    transaction_id: Optional[str] = None,
    notes_codes: str = "",
) -> List[Any]:
    """
    Create a single stock trade row for CSV input.
    Useful for creating linked stock trades from option exercise/assignment.

    Returns a list matching TRADES_FILE_HEADERS format.
    """
    direction, open_close = OPTION_TRADE_TYPE_MAP[trade_type]

    # Adjust quantity sign: negative for sells
    qty = quantity if direction == "BUY" else -quantity

    return [
        account_id,          # ClientAccountID
        currency,            # CurrencyPrimary
        "STK",               # AssetClass
        "COMMON",            # SubCategory
        symbol,              # Symbol
        description,         # Description
        isin,                # ISIN
        None,                # Strike
        None,                # Expiry
        None,                # Put/Call
        trade_date,          # TradeDate
        qty,                 # Quantity
        price,               # TradePrice
        commission,          # IBCommission
        currency,            # IBCommissionCurrency
        direction,           # Buy/Sell
        transaction_id or f"STK_T_{trade_date}_{qty}",  # TransactionID
        notes_codes,         # Notes/Codes
        "",                  # UnderlyingSymbol (none for stocks)
        conid,               # Conid
        "",                  # UnderlyingConid (none for stocks)
        Decimal("1"),        # Multiplier (1 for stocks)
        open_close,          # Open/CloseIndicator
    ]


def build_option_test_scenario(
    underlying_symbol: str,
    underlying_isin: str,
    underlying_conid: str,
    strike: Decimal,
    expiry: str,
    option_type: str,
    option_trades: List[dict],
    stock_trades: List[dict] = None,
    account_id: str = "U_TEST",
    currency: str = "USD",
) -> tuple:
    """
    Build complete trade data for an option test scenario.

    Args:
        underlying_symbol: e.g., "AAPL"
        underlying_isin: e.g., "US0378331005"
        underlying_conid: e.g., "265598"
        strike: Option strike price
        expiry: Expiry date in YYYY-MM-DD format
        option_type: 'C' for call, 'P' for put
        option_trades: List of dicts with keys: type, qty, price, date, notes_codes (optional)
        stock_trades: List of dicts with keys: type, qty, price, date, notes_codes (optional)
        account_id: Account ID
        currency: Currency code

    Returns:
        Tuple of (trades_data, option_symbol, option_conid)
    """
    # Generate option symbol and conid
    expiry_short = format_expiry_for_symbol(expiry)
    option_symbol = create_option_symbol(underlying_symbol, expiry_short, option_type, strike)
    option_conid = f"OPT_{underlying_conid}_{expiry_short}_{option_type}{strike}"
    option_desc = f"{underlying_symbol} {expiry[2:4]}{expiry[5:7]}{expiry[8:10]} {strike} {option_type}"

    trades_data = []

    # Add option trades
    for i, trade in enumerate(option_trades):
        trades_data.append(create_option_trade_data(
            account_id=account_id,
            currency=currency,
            symbol=option_symbol,
            description=option_desc,
            underlying_symbol=underlying_symbol,
            underlying_conid=underlying_conid,
            option_conid=option_conid,
            strike=strike,
            expiry_date=expiry,
            option_type=option_type,
            trade_date=trade["date"],
            trade_type=trade["type"],
            quantity=Decimal(str(trade["qty"])),
            price=Decimal(str(trade["price"])),
            transaction_id=f"OPT_T_{i:04d}",
            notes_codes=trade.get("notes_codes", ""),
        ))

    # Add stock trades if provided
    stock_trades = stock_trades or []
    stock_desc = f"{underlying_symbol} COMMON STOCK"
    for i, trade in enumerate(stock_trades):
        trades_data.append(create_stock_trade_data(
            account_id=account_id,
            currency=currency,
            symbol=underlying_symbol,
            description=stock_desc,
            isin=underlying_isin,
            conid=underlying_conid,
            trade_date=trade["date"],
            trade_type=trade["type"],
            quantity=Decimal(str(trade["qty"])),
            price=Decimal(str(trade["price"])),
            transaction_id=f"STK_T_{i:04d}",
            notes_codes=trade.get("notes_codes", ""),
        ))

    return trades_data, option_symbol, option_conid

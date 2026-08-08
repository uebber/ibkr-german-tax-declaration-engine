# src/utils/type_utils.py
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Union
from datetime import datetime, date

def safe_decimal(value: Any, default: Optional[Decimal] = None, raise_error: bool = False) -> Optional[Decimal]:
    """
    Safely converts a value to a Decimal.
    Handles None, empty strings, strings with commas (as thousands or decimal).
    If default is provided, returns default on conversion error.
    If raise_error is True, re-raises InvalidOperation instead of returning default.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)): # float conversion is direct, can lead to precision issues if not careful
        return Decimal(str(value))

    s_value = str(value).strip()
    if not s_value:
        return default

    try:
        # Handle European style (comma as decimal separator) if no period is present
        # And US style (comma as thousands separator) if a period is also present
        if '.' in s_value and ',' in s_value: # e.g., "1,234.56" or "1.234,56"
            s_value = s_value.replace(',', '') # First remove potential thousands separator
        elif ',' in s_value and '.' not in s_value: # e.g., "12,34"
             s_value = s_value.replace(',', '.')
        # If only '.' is present, it's fine. If only ',' is present, it was converted above.
        return Decimal(s_value)
    except InvalidOperation as e:
        if raise_error:
            raise e
        # print(f"Warning: Could not parse decimal from '{value}', using default {default}. Error: {e}")
        return default

def parse_ibkr_date(date_str: Optional[str], default: Optional[date] = None) -> Optional[date]:
    """
    Parses various date formats IBKR might use (YYYY-MM-DD, YYYYMMDD, MM/DD/YYYY, etc.)
    Returns a datetime.date object or None.
    """
    if not date_str or not str(date_str).strip():
        return default

    s_date_str = str(date_str).strip()
    
    formats_to_try = [
        "%Y-%m-%d",         # 2023-12-31
        "%Y%m%d",           # 20231231
        "%m/%d/%Y",         # 12/31/2023
        "%d.%m.%Y",         # 31.12.2023
        "%Y-%m-%d %H:%M:%S", # If datetime is provided, take date part
        "%Y%m%d %H:%M:%S",
    ]

    # Attempt with dateutil.parser for flexibility first
    try:
        # dateutil.parser.parse can be too lenient, but good for common variations
        dt_obj = datetime.strptime(s_date_str.split(' ')[0], formats_to_try[0]) # Try most common first
        return dt_obj.date()
    except ValueError:
        pass # Try other formats

    for fmt in formats_to_try[1:]:
        try:
            dt_obj = datetime.strptime(s_date_str.split(' ')[0], fmt) # Take only date part if time exists
            return dt_obj.date()
        except ValueError:
            continue
    
    # Fallback to dateutil.parser if specific formats fail (can be slower)
    try:
        from dateutil import parser as dateutil_parser
        dt_obj = dateutil_parser.parse(s_date_str)
        return dt_obj.date()
    except (ValueError, TypeError, ImportError):
        # print(f"Warning: Could not parse date from '{s_date_str}' using multiple formats.")
        return default

# There is deliberately no `parse_ibkr_datetime`. It was removed in August 2026 with its
# last two call sites (issue #64): both were reading `TradeTime` and a cash transaction's
# `DateTime`, neither of which any Flex Query in this repo requests. Its one distinguishing
# behaviour was a `dateutil` fallback on the *whole* string rather than on the date part,
# which is more lenient than anything a date column here should get. `parse_ibkr_date`
# already splits a time component off, so a value that does arrive with one still resolves;
# see `DomainEventFactory._trade_contract_date`.

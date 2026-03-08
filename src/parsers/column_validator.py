# src/parsers/column_validator.py
"""
Canonical CSV column definitions for all IBKR Flex Query input files.

These tuples define the exact columns each CSV file must contain.
Parsers validate incoming CSV headers against these definitions before processing.
Test CSV creators import these to stay in sync.
"""
import logging
from typing import List, Sequence

logger = logging.getLogger(__name__)

TRADES_COLUMNS = (
    "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol",
    "Description", "ISIN", "Strike", "Expiry", "Put/Call", "TradeDate", "Quantity",
    "TradePrice", "IBCommission", "IBCommissionCurrency", "Buy/Sell",
    "TransactionID", "Notes/Codes", "UnderlyingSymbol", "Conid", "UnderlyingConid",
    "Multiplier", "Open/CloseIndicator",
)

CASH_TRANSACTIONS_COLUMNS = (
    "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol",
    "Description", "SettleDate", "Amount", "Type", "Conid", "UnderlyingConid",
    "ISIN", "IssuerCountryCode", "TransactionID",
)

POSITIONS_COLUMNS = (
    "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol",
    "Description", "ISIN", "Quantity", "PositionValue", "MarkPrice",
    "CostBasisMoney", "UnderlyingSymbol", "Conid", "UnderlyingConid", "Multiplier",
)

CORPORATE_ACTIONS_COLUMNS = (
    "ClientAccountID", "Symbol", "Description", "ISIN", "Report Date", "Code",
    "Type", "ActionID", "Conid", "UnderlyingConid", "UnderlyingSymbol",
    "CurrencyPrimary", "Amount", "Proceeds", "Value", "Quantity",
)

CASH_BALANCE_COLUMNS = (
    "ClientAccountID", "CurrencyPrimary", "FromDate", "ToDate",
    "StartingCash", "EndingCash",
)


def validate_csv_columns(
    actual_headers: Sequence[str],
    expected_columns: Sequence[str],
    file_description: str,
) -> None:
    """Validate that CSV headers match expected columns exactly.

    Raises ValueError if there are missing or unexpected columns.
    """
    expected_set = set(expected_columns)
    actual_set = set(actual_headers)
    missing = expected_set - actual_set
    extra = actual_set - expected_set

    if missing or extra:
        parts = [f"CSV column mismatch in {file_description}:"]
        if missing:
            parts.append(f"  Missing columns: {sorted(missing)}")
        if extra:
            parts.append(f"  Unexpected columns: {sorted(extra)}")
        parts.append(f"  Expected columns: {sorted(expected_columns)}")
        raise ValueError("\n".join(parts))

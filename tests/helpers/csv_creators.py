# tests/helpers/csv_creators.py
import io
import csv
from decimal import Decimal
from typing import List, Dict, Any, Union

def create_csv_string(headers: List[str], data_rows: List[List[Union[str, Decimal, int, float, None]]]) -> str:
    """
    Generates a CSV formatted string from headers and data rows.
    Handles Decimal types by converting them to strings.
    None values are converted to empty strings.
    Floats are also converted to strings.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in data_rows:
        processed_row = []
        for item in row:
            if isinstance(item, Decimal):
                processed_row.append(str(item))
            elif item is None:
                processed_row.append("")
            elif isinstance(item, float): # Ensure floats are also stringified
                processed_row.append(str(item))
            else:
                processed_row.append(str(item))
        writer.writerow(processed_row)
    return output.getvalue()

# --- Trades CSV ---
TRADES_FILE_HEADERS = [
    "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol",
    "Description", "ISIN", "Strike", "Expiry", "Put/Call", "TradeDate", "Quantity",
    "TradePrice", "IBCommission", "IBCommissionCurrency", "Buy/Sell",
    "TransactionID", "Notes/Codes", "UnderlyingSymbol", "Conid", "UnderlyingConid",
    "Multiplier", "Open/CloseIndicator"
]

def create_trades_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(TRADES_FILE_HEADERS, data_rows)

# --- Positions CSV (Start/End of Year) ---
POSITIONS_FILE_HEADERS = [
    "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol",
    "Description", "ISIN", "Quantity", "PositionValue", "MarkPrice",
    "CostBasisMoney", "UnderlyingSymbol", "Conid", "UnderlyingConid", "Multiplier"
]

def create_positions_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(POSITIONS_FILE_HEADERS, data_rows)

# --- Cash Transactions CSV ---
CASH_TRANSACTIONS_HEADERS = [
    "ClientAccountID", "CurrencyPrimary", "AssetClass", "SubCategory", "Symbol",
    "Description", "SettleDate", "Amount", "Type", "Conid", "UnderlyingConid",
    "ISIN", "IssuerCountryCode"
]
def create_cash_transactions_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(CASH_TRANSACTIONS_HEADERS, data_rows)


# --- Corporate Actions CSV ---
CORPORATE_ACTIONS_HEADERS = [
    "ClientAccountID", "Symbol", "Description", "ISIN", "Report Date", "Code",
    "Type", "ActionID", "Conid", "UnderlyingConid", "UnderlyingSymbol",
    "CurrencyPrimary", "Amount", "Proceeds", "Value", "Quantity"
]
def create_corporate_actions_csv_string(data_rows: List[List[Any]]) -> str:
    return create_csv_string(CORPORATE_ACTIONS_HEADERS, data_rows)

# src/parsers/raw_models.py
from typing import Optional, Any
from decimal import Decimal
from pydantic import BaseModel, Field, validator

from src.utils.type_utils import safe_decimal, parse_ibkr_date, parse_ibkr_datetime

class RawBaseRecord(BaseModel):
    # Common validator for all decimal fields that might appear in subclasses
    @validator('*', pre=True, allow_reuse=True)
    def parse_all_decimals(cls, v: Any, field: Any) -> Any:
        # Check if the field is supposed to be Decimal based on annotations
        # This is a bit general; specific validators per field are more robust
        # but this can catch common cases if fields are named consistently for decimal parsing.
        # For now, relying on specific validators in each model or direct safe_decimal calls.
        if hasattr(field, 'type_') and field.type_ == Decimal : # Check annotation more safely
             return safe_decimal(v, default=Decimal("0.0")) # Default to 0 if unparsable
        return v


class RawTradeRecord(RawBaseRecord):
    # Fields are named to match typical IBKR Flex Query CSV headers for trades
    # Using Field(alias=...) if CSV headers have spaces or special characters
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    account_alias: Optional[str] = Field(None, alias="AccountAlias")
    model: Optional[str] = Field(None, alias="Model")
    currency_primary: str = Field(alias="CurrencyPrimary") # Renamed from Currency to CurrencyPrimary per PRD
    asset_class: str = Field(alias="AssetClass")
    sub_category: Optional[str] = Field(None, alias="SubCategory")
    symbol: str = Field(alias="Symbol")
    description: str = Field(alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    security_id: Optional[str] = Field(None, alias="SecurityID") # Often ISIN
    security_id_type: Optional[str] = Field(None, alias="SecurityIDType") # e.g. "ISIN"
    cusip: Optional[str] = Field(None, alias="Cusip")
    isin: Optional[str] = Field(None, alias="ISIN") # Explicit ISIN field
    listing_exchange: Optional[str] = Field(None, alias="ListingExchange")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    underlying_security_id: Optional[str] = Field(None, alias="UnderlyingSecurityID")
    underlying_listing_exchange: Optional[str] = Field(None, alias="UnderlyingListingExchange")
    issuer: Optional[str] = Field(None, alias="Issuer")
    multiplier: Optional[Decimal] = Field(None, alias="Multiplier")
    strike: Optional[Decimal] = Field(None, alias="Strike")
    expiry: Optional[str] = Field(None, alias="Expiry") # Kept as str, parsed by AssetResolver/Orchestrator
    put_call: Optional[str] = Field(None, alias="Put/Call") # 'P' or 'C'
    trade_id: Optional[str] = Field(None, alias="TradeID")
    report_date: Optional[str] = Field(None, alias="ReportDate") # Kept as str - Ensure this is optional if not always present
    trade_date: str = Field(alias="TradeDate") # Kept as str
    trade_time: Optional[str] = Field(None, alias="TradeTime") # Kept as str
    settle_date_target: Optional[str] = Field(None, alias="SettleDateTarget") # Kept as str
    transaction_type: Optional[str] = Field(None, alias="TransactionType")
    exchange: Optional[str] = Field(None, alias="Exchange")
    quantity: Decimal = Field(alias="Quantity") # Can be positive (buy) or negative (sell)
    trade_price: Decimal = Field(alias="TradePrice")
    trade_money: Optional[Decimal] = Field(None, alias="TradeMoney") # quantity * trade_price * multiplier
    proceeds: Optional[Decimal] = Field(None, alias="Proceeds")
    taxes: Optional[Decimal] = Field(None, alias="Taxes")
    ib_commission: Optional[Decimal] = Field(None, alias="IBCommission")
    ib_commission_currency: Optional[str] = Field(None, alias="IBCommissionCurrency")
    net_cash: Optional[Decimal] = Field(None, alias="NetCash")
    close_price: Optional[Decimal] = Field(None, alias="ClosePrice")
    open_close_indicator: Optional[str] = Field(None, alias="Open/CloseIndicator") # O, C, A, Ex, Ep etc.
    notes_codes: Optional[str] = Field(None, alias="Notes/Codes") # Contains O, C, A, Ex, Ep, P, D etc.
    cost_basis: Optional[Decimal] = Field(None, alias="CostBasis")
    fifo_pnl_realized: Optional[Decimal] = Field(None, alias="FifoPnlRealized")
    mtm_pnl: Optional[Decimal] = Field(None, alias="MtmPnl")
    orig_trade_price: Optional[Decimal] = Field(None, alias="OrigTradePrice")
    orig_trade_date: Optional[str] = Field(None, alias="OrigTradeDate") # Kept as str
    orig_trade_id: Optional[str] = Field(None, alias="OrigTradeID")
    order_type: Optional[str] = Field(None, alias="OrderType")
    transaction_id: Optional[str] = Field(None, alias="TransactionID") # Often used for linking
    buy_sell: Optional[str] = Field(None, alias="Buy/Sell") # BUY, SELL - important for TradeEvent type

    # Validators for specific fields
    @validator('multiplier', 'strike', 'quantity', 'trade_price', 'trade_money', 'proceeds', 'taxes',
               'ib_commission', 'net_cash', 'close_price', 'cost_basis', 'fifo_pnl_realized',
               'mtm_pnl', 'orig_trade_price', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('trade_date', 'report_date', 'settle_date_target', 'expiry', 'orig_trade_date', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore' # Ignore extra columns not defined in the model

class RawCashTransactionRecord(RawBaseRecord):
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    account_alias: Optional[str] = Field(None, alias="AccountAlias")
    model: Optional[str] = Field(None, alias="Model")
    currency_primary: str = Field(alias="CurrencyPrimary") # Renamed from Currency to CurrencyPrimary per PRD
    fx_rate_to_base: Optional[Decimal] = Field(None, alias="FXRateToBase")
    asset_class: Optional[str] = Field(None, alias="AssetClass") # STK, BOND, OPT, FUT, FUND, CASH
    sub_category: Optional[str] = Field(None, alias="SubCategory")
    symbol: Optional[str] = Field(None, alias="Symbol")
    description: str = Field(alias="Description") # Very important for type determination
    conid: Optional[str] = Field(None, alias="Conid")
    security_id: Optional[str] = Field(None, alias="SecurityID")
    security_id_type: Optional[str] = Field(None, alias="SecurityIDType")
    cusip: Optional[str] = Field(None, alias="Cusip")
    isin: Optional[str] = Field(None, alias="ISIN")
    listing_exchange: Optional[str] = Field(None, alias="ListingExchange")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    issuer: Optional[str] = Field(None, alias="Issuer")
    report_date: Optional[str] = Field(None, alias="ReportDate") # MODIFIED TO OPTIONAL
    date_time: Optional[str] = Field(None, alias="DateTime")     # MODIFIED TO OPTIONAL
    settle_date: str = Field(alias="SettleDate") # Kept as str, as it's present in the sample CSV
    type: str = Field(alias="Type") # E.g. "Dividends", "Withholding Tax", "Broker Interest Received"
    amount: Decimal = Field(alias="Amount") # Cash amount
    proceeds: Optional[Decimal] = Field(None, alias="Proceeds") # Usually for sales, may not be relevant here
    transaction_id: Optional[str] = Field(None, alias="TransactionID")
    # Fields that might appear in some Cash Transaction reports
    level_of_detail: Optional[str] = Field(None, alias="LevelOfDetail")
    code: Optional[str] = Field(None, alias="Code") # e.g. 'Po' for Payment in Lieu, 'Re' for Return of Capital
    issuer_country_code: Optional[str] = Field(None, alias="IssuerCountryCode") # Added as it's in sample CSV

    @validator('fx_rate_to_base', 'amount', 'proceeds', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('report_date', 'date_time', 'settle_date', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore'

class RawPositionRecord(RawBaseRecord): # For Start and End of Year positions
    account_id: Optional[str] = Field(None, alias="AccountId")
    acct_alias: Optional[str] = Field(None, alias="AcctAlias")
    model: Optional[str] = Field(None, alias="Model")
    currency_primary: str = Field(alias="CurrencyPrimary") # Renamed for consistency
    asset_class: str = Field(alias="AssetClass")
    symbol: str = Field(alias="Symbol")
    description: str = Field(alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    security_id: Optional[str] = Field(None, alias="SecurityID")
    security_id_type: Optional[str] = Field(None, alias="SecurityIDType")
    cusip: Optional[str] = Field(None, alias="Cusip")
    isin: Optional[str] = Field(None, alias="ISIN")
    listing_exchange: Optional[str] = Field(None, alias="ListingExchange")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    underlying_security_id: Optional[str] = Field(None, alias="UnderlyingSecurityID")
    underlying_listing_exchange: Optional[str] = Field(None, alias="UnderlyingListingExchange")
    issuer_country_code: Optional[str] = Field(None, alias="IssuerCountryCode")
    multiplier: Optional[Decimal] = Field(None, alias="Multiplier")
    strike: Optional[Decimal] = Field(None, alias="Strike")
    expiry: Optional[str] = Field(None, alias="Expiry") # Kept as str
    put_call: Optional[str] = Field(None, alias="Put/Call")
    report_date: Optional[str] = Field(None, alias="ReportDate") # MODIFIED TO OPTIONAL (if not in actual CSV)
    position: Decimal = Field(alias="Quantity") # <--- MODIFIED ALIAS HERE
    mark_price: Optional[Decimal] = Field(None, alias="MarkPrice")
    position_value: Optional[Decimal] = Field(None, alias="PositionValue") # In CurrencyPrimary
    cost_basis_price: Optional[Decimal] = Field(None, alias="CostBasisPrice")
    cost_basis_money: Optional[Decimal] = Field(None, alias="CostBasisMoney") # Total cost basis in CurrencyPrimary
    percent_of_nav: Optional[Decimal] = Field(None, alias="PercentOfNAV")
    fifo_pnl_unrealized: Optional[Decimal] = Field(None, alias="FifoPnlUnrealized")
    level_of_detail: Optional[str] = Field(None, alias="LevelOfDetail") # e.g. LOT

    @validator('multiplier', 'strike', 'position', 'mark_price', 'position_value',
               'cost_basis_price', 'cost_basis_money', 'percent_of_nav', 'fifo_pnl_unrealized', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('report_date', 'expiry', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore'


class RawCorporateActionRecord(RawBaseRecord): # From corpact*.csv
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    account_alias: Optional[str] = Field(None, alias="AccountAlias")
    model: Optional[str] = Field(None, alias="Model")
    currency_primary: Optional[str] = Field(None, alias="CurrencyPrimary") # Made optional as might not be in all CA files
    fx_rate_to_base: Optional[Decimal] = Field(None, alias="FXRateToBase")
    asset_class: Optional[str] = Field(None, alias="AssetClass") # Made optional
    symbol: str = Field(alias="Symbol")
    description: str = Field(alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    security_id: Optional[str] = Field(None, alias="SecurityID")
    security_id_type: Optional[str] = Field(None, alias="SecurityIDType")
    cusip: Optional[str] = Field(None, alias="Cusip")
    isin: Optional[str] = Field(None, alias="ISIN")
    listing_exchange: Optional[str] = Field(None, alias="ListingExchange")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    issuer: Optional[str] = Field(None, alias="Issuer")
    report_date: str = Field(alias="Report Date") # Corrected alias "Report Date"
    action_id_ibkr: Optional[str] = Field(None, alias="ActionID")
    action_description: Optional[str] = Field(None, alias="ActionDescription")
    code: Optional[str] = Field(None, alias="Code")
    type_ca: str = Field(None, alias="Type")
    quantity: Optional[Decimal] = Field(None, alias="Quantity")
    proceeds: Optional[Decimal] = Field(None, alias="Proceeds")
    value: Optional[Decimal] = Field(None, alias="Value")
    transaction_id: Optional[str] = Field(None, alias="TransactionID")
    pay_date: Optional[str] = Field(None, alias="PayDate")
    ex_date: Optional[str] = Field(None, alias="ExDate")
    record_date: Optional[str] = Field(None, alias="RecordDate")


    @validator('fx_rate_to_base', 'quantity', 'proceeds', 'value', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('report_date', 'pay_date', 'ex_date', 'record_date', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()
        
    class Config:
        extra = 'ignore'

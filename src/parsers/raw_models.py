# src/parsers/raw_models.py
"""Raw records: one field per column the Flex Query actually requests, and no others.

**A field here is a claim that the column arrives.** Each model declares exactly the
aliases in its `*_COLUMNS` tuple in `column_validator.py` -- no more -- and
`tests/test_raw_model_fields.py` fails if that stops being true.

The rule is not tidiness. A declared-but-never-populated field is indistinguishable from
a supported input at every call site, so the next person wires a fallback to it and the
fallback is dead in a way nothing fails on. That is not hypothetical: `SettleDateTarget`
was declared here, populated by nothing, and listed *first* in the date priority chain,
so the legally decisive date of every trade was the settlement date by rule and the trade
date only by the accident of the column being absent. Adding the column to the query would
have moved every lot's date silently. Removed August 2026; see
`DomainEventFactory._trade_contract_date` and [GT-ESTG20-039/040].

The same sweep removed 72 further such fields across four models (issue #64), among them
two thirds of the corporate-action date chain, `TradeTime`, `TradeMoney`/`Proceeds` on
trades, `Code` on cash transactions, and the `SecurityID`/`SecurityIDType` pair whose
absence made `raw_isin=... if security_id_type == "ISIN" else ...` reduce to `isin` at
six call sites.

Adding a field therefore means adding the column to the Flex Query *and* to the
`*_COLUMNS` tuple. Leaving it declared-but-unrequested is the one state to avoid.

Note the mirror case, which is *not* corrected here because changing it could move a
figure: `Positions` exports `ClientAccountID` and `SubCategory`, and `Corporate_Actions`
exports `Amount`, none of which have a field below, so `extra = 'ignore'` discards them.
"""
from typing import Optional, Any
from decimal import Decimal
from pydantic import BaseModel, Field, validator

from src.utils.type_utils import safe_decimal

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
    """One row of the Trades export. Mirrors `TRADES_COLUMNS` exactly."""
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    currency_primary: str = Field(alias="CurrencyPrimary") # Renamed from Currency to CurrencyPrimary per PRD
    asset_class: str = Field(alias="AssetClass")
    sub_category: Optional[str] = Field(None, alias="SubCategory")
    symbol: str = Field(alias="Symbol")
    description: str = Field(alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    isin: Optional[str] = Field(None, alias="ISIN")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    multiplier: Optional[Decimal] = Field(None, alias="Multiplier")
    strike: Optional[Decimal] = Field(None, alias="Strike")
    expiry: Optional[str] = Field(None, alias="Expiry") # Kept as str, parsed by AssetResolver/Orchestrator
    put_call: Optional[str] = Field(None, alias="Put/Call") # 'P' or 'C'
    # The contract date, and the only date of a trade this engine recognises. There is
    # deliberately no settlement, report or time field: none is requested in the Flex Query,
    # none is in TRADES_COLUMNS, and all were removed in August 2026 because a
    # declared-but-unpopulated date field is how the settlement date became the engine's
    # default in the first place. See DomainEventFactory._trade_contract_date and the module
    # docstring above, [GT-ESTG20-039/040].
    trade_date: str = Field(alias="TradeDate") # Kept as str
    quantity: Decimal = Field(alias="Quantity") # Can be positive (buy) or negative (sell)
    trade_price: Decimal = Field(alias="TradePrice")
    ib_commission: Optional[Decimal] = Field(None, alias="IBCommission")
    ib_commission_currency: Optional[str] = Field(None, alias="IBCommissionCurrency")
    open_close_indicator: Optional[str] = Field(None, alias="Open/CloseIndicator") # O, C, A, Ex, Ep etc.
    notes_codes: Optional[str] = Field(None, alias="Notes/Codes") # Contains O, C, A, Ex, Ep, P, D etc.
    transaction_id: Optional[str] = Field(None, alias="TransactionID") # Used for linking
    buy_sell: Optional[str] = Field(None, alias="Buy/Sell") # BUY, SELL - important for TradeEvent type

    # No TradeMoney/Proceeds either: neither is exported, so the gross amount is always
    # derived from Quantity x TradePrice x Multiplier. See create_events_from_trades.

    # Validators for specific fields
    @validator('multiplier', 'strike', 'quantity', 'trade_price', 'ib_commission', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('trade_date', 'expiry', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore' # Ignore extra columns not defined in the model

class RawCashTransactionRecord(RawBaseRecord):
    """One row of the Cash Transactions export. Mirrors `CASH_TRANSACTIONS_COLUMNS` exactly."""
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    currency_primary: str = Field(alias="CurrencyPrimary") # Renamed from Currency to CurrencyPrimary per PRD
    asset_class: Optional[str] = Field(None, alias="AssetClass") # STK, BOND, OPT, FUT, FUND, CASH
    sub_category: Optional[str] = Field(None, alias="SubCategory")
    symbol: Optional[str] = Field(None, alias="Symbol")
    description: str = Field(alias="Description") # Very important for type determination
    conid: Optional[str] = Field(None, alias="Conid")
    isin: Optional[str] = Field(None, alias="ISIN")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    issuer_country_code: Optional[str] = Field(None, alias="IssuerCountryCode")
    # The Zufluss, and the only date of a cash transaction this engine has. `DateTime` and
    # `ReportDate` were declared here and passed to _zufluss_date as second and third
    # priority until August 2026; neither is exported, so both were dead. See that helper.
    settle_date: str = Field(alias="SettleDate") # Kept as str
    type: str = Field(alias="Type") # E.g. "Dividends", "Withholding Tax", "Broker Interest Received"
    amount: Decimal = Field(alias="Amount") # Cash amount
    transaction_id: Optional[str] = Field(None, alias="TransactionID")

    # No `Code` field: it is not exported, so the 'DI' / 'IN' / 'PO' shortcuts that once
    # read it were dead. `Type` and `Description` carry the same distinction and are what
    # create_events_from_cash_transactions classifies on -- all 26 "Payment In Lieu Of
    # Dividends" rows in the 2021-2025 history are typed, not coded.

    @validator('amount', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('settle_date', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore'

class RawPositionRecord(RawBaseRecord): # For Start and End of Year positions
    """One row of a Positions snapshot. Mirrors `POSITIONS_COLUMNS`, less the two
    columns noted in the module docstring that this model does not map at all.

    Carries no option contract terms. `Strike`, `Expiry` and `Put/Call` were declared here
    and read by `process_positions` until August 2026, but the Positions query does not
    export them, so an option whose first sighting was a snapshot got
    `Option(option_type=None, strike_price=None, expiry_date=None)` either way. Measured
    over 2021-2025: of the 17 distinct OPT conids in the snapshots, 0 are absent from
    Trades or Options_EAE, both of which do export the terms -- so the snapshot has never
    been an option's only source. Restoring the capability means adding the three columns
    to the Flex Query and to POSITIONS_COLUMNS together, not re-declaring them here.
    """
    currency_primary: str = Field(alias="CurrencyPrimary") # Renamed for consistency
    asset_class: str = Field(alias="AssetClass")
    symbol: str = Field(alias="Symbol")
    description: str = Field(alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    isin: Optional[str] = Field(None, alias="ISIN")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    multiplier: Optional[Decimal] = Field(None, alias="Multiplier")
    position: Decimal = Field(alias="Quantity")
    mark_price: Optional[Decimal] = Field(None, alias="MarkPrice")
    position_value: Optional[Decimal] = Field(None, alias="PositionValue") # In CurrencyPrimary
    cost_basis_money: Optional[Decimal] = Field(None, alias="CostBasisMoney") # Total cost basis in CurrencyPrimary

    @validator('multiplier', 'position', 'mark_price', 'position_value',
               'cost_basis_money', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    class Config:
        extra = 'ignore'


class RawCorporateActionRecord(RawBaseRecord): # From corpact*.csv
    """One row of the Corporate Actions export. Mirrors `CORPORATE_ACTIONS_COLUMNS`, less
    `Amount`, which this model does not map -- see the module docstring.

    `Report Date` is the only date. `PayDate` and `ExDate` were declared here and took
    first and third place in the `_zufluss_date` chain until August 2026, with the report
    date wedged between them as the sole reachable entry; neither is exported. Had the
    query later started carrying `PayDate`, every corporate action would have moved from
    its report date to its pay date -- changing which assessment year an event lands in,
    by nobody's decision. That is the settlement-date defect exactly.
    """
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    currency_primary: Optional[str] = Field(None, alias="CurrencyPrimary") # Made optional as might not be in all CA files
    symbol: str = Field(alias="Symbol")
    description: str = Field(alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    isin: Optional[str] = Field(None, alias="ISIN")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    report_date: str = Field(alias="Report Date") # Corrected alias "Report Date"
    action_id_ibkr: Optional[str] = Field(None, alias="ActionID")
    code: Optional[str] = Field(None, alias="Code")
    type_ca: str = Field(None, alias="Type")
    quantity: Optional[Decimal] = Field(None, alias="Quantity")
    proceeds: Optional[Decimal] = Field(None, alias="Proceeds")
    value: Optional[Decimal] = Field(None, alias="Value")

    @validator('quantity', 'proceeds', 'value', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('report_date', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore'


class RawOptionsEAERecord(RawBaseRecord):
    """Raw record from IBKR OptionEAE Flex Query (Option Exercises, Assignments, Expirations)."""
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    currency_primary: str = Field(alias="CurrencyPrimary")
    fx_rate_to_base: Optional[Decimal] = Field(None, alias="FXRateToBase")
    asset_class: Optional[str] = Field(None, alias="AssetClass")
    symbol: str = Field(alias="Symbol")
    description: str = Field(alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    isin: Optional[str] = Field(None, alias="ISIN")
    underlying_conid: Optional[str] = Field(None, alias="UnderlyingConid")
    underlying_symbol: Optional[str] = Field(None, alias="UnderlyingSymbol")
    multiplier: Optional[Decimal] = Field(None, alias="Multiplier")
    strike: Optional[Decimal] = Field(None, alias="Strike")
    expiry: Optional[str] = Field(None, alias="Expiry")
    put_call: Optional[str] = Field(None, alias="Put/Call")
    date: str = Field(alias="Date")
    transaction_type: str = Field(alias="Transaction Type")
    quantity: Optional[Decimal] = Field(None, alias="Quantity")
    trade_price: Optional[Decimal] = Field(None, alias="Trade Price")
    proceeds: Optional[Decimal] = Field(None, alias="Proceeds")
    comm_tax: Optional[Decimal] = Field(None, alias="Comm/Tax")
    basis: Optional[Decimal] = Field(None, alias="Basis")
    realized_pnl: Optional[Decimal] = Field(None, alias="RealizedPnl")

    @validator('fx_rate_to_base', 'multiplier', 'strike', 'quantity', 'trade_price',
               'proceeds', 'comm_tax', 'basis', 'realized_pnl', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

    @validator('date', 'expiry', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore'


class RawCashBalanceRecord(RawBaseRecord):
    """Raw record for currency cash balances from IBKR Cash Report."""
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    currency_primary: str = Field(alias="CurrencyPrimary")
    from_date: str = Field(alias="FromDate")   # YYYYMMDD format
    to_date: str = Field(alias="ToDate")       # YYYYMMDD format
    starting_cash: Decimal = Field(alias="StartingCash")
    ending_cash: Decimal = Field(alias="EndingCash")

    @validator('starting_cash', 'ending_cash', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Optional[Decimal]:
        return safe_decimal(v, default=Decimal("0.0"))

    @validator('from_date', 'to_date', pre=True)
    def validate_date_strings(cls, v: Any) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return str(v).strip()

    class Config:
        extra = 'ignore'

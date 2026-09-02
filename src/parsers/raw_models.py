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
figure: `Positions` exports `SubCategory` and `Corporate_Actions` exports `Amount`,
neither of which has a field below, so `extra = 'ignore'` discards them.
"""
from typing import Optional, Any
from decimal import Decimal
from pydantic import BaseModel, Field, validator

from src.utils.type_utils import safe_decimal

class RawBaseRecord(BaseModel):
    """Shared base. Deliberately carries no validators -- see below.

    It used to define `parse_all_decimals`, a `@validator('*', pre=True)` that coerced every
    `Decimal`-typed field with `safe_decimal(v, default=Decimal("0.0"))`. Because pydantic
    runs a subclass's pre-validators *before* an inherited one, it did not shadow the
    per-field validators' input, as issue #47 supposed -- it overwrote their **output**. Each
    model's `parse_decimal_fields` distinguishes blank from zero and returns `None` for a
    blank optional field; this then turned that `None` straight back into `Decimal("0.0")`,
    so the distinction could never be observed and the per-field rule read as though it
    guarded something it did not.

    Removed August 2026. Every `Decimal` field on every model below has its own validator,
    and `tests/test_raw_model_decimals.py` fails if one is ever added without one -- which is
    what makes deleting this safe rather than merely tidy. Do not reintroduce a wildcard
    validator here: one that runs after the specific rules silently discards them, and the
    ordering that decides which wins is not visible at either site.
    """


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
    """One row of a Positions snapshot. Mirrors `POSITIONS_COLUMNS`, less the one
    column noted in the module docstring that this model does not map at all.

    Carries no option contract terms. `Strike`, `Expiry` and `Put/Call` were declared here
    and read by `process_positions` until August 2026, but the Positions query does not
    export them, so an option whose first sighting was a snapshot got
    `Option(option_type=None, strike_price=None, expiry_date=None)` either way. Measured
    over 2021-2025: of the 17 distinct OPT conids in the snapshots, 0 are absent from
    Trades or Options_EAE, both of which do export the terms -- so the snapshot has never
    been an option's only source. Restoring the capability means adding the three columns
    to the Flex Query and to POSITIONS_COLUMNS together, not re-declaring them here.
    """
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
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

class RawTransferRecord(RawBaseRecord):
    """One row of the Transfers export -- a move of a holding or a cash balance.

    The export writes a move as SEVERAL rows, and a consumer that sums them moves the
    holding more than once. `LevelOfDetail` discriminates them:

    * a **TRANSFER** row -- the summary, one per side of the move: `Direction` "OUT" on
      the sending account and "IN" on the receiving one. Each names both accounts -- its
      own in `ClientAccountID` and the other in `TransferAccount` -- so either side alone
      describes the whole move. It carries a `TransactionID`.
    * a **LOT** row per acquisition day beneath a summary, carrying `Code` "ST", no
      `TransactionID`, and the day and basis of that lot in `OpenDateTime` and
      `CostBasis`. Measured: one row per acquisition day, not per trade.

    `DomainEventFactory.create_events_from_transfers` reads `LevelOfDetail`, collapses the
    summary rows into one move per side pair, and attaches the `LOT` rows as the per-day
    breakdown of which lots moved. The older shape of this export lacked `LevelOfDetail`,
    `CostBasis` and `OpenDateTime`; those three are now REQUIRED input -- an export without
    them stops the run rather than being read on a heuristic (`Code`/`TransactionID`) that
    the real field replaces.

    **`Direction` carries the direction and the sign of `Quantity` does not.** The two
    sides of one move carry opposite signs, and which side is negative varies by
    instrument, so the sign identifies neither the direction nor a short position on the
    summary row. The engine reads `abs(quantity)` for the move total and takes the
    direction from `Direction`. On a LOT row the sign DOES mark long-versus-short
    (measured: 6 of 13 real lot rows are shorts opened by SELL), but the sending ledger
    remains authoritative and the sign is a cross-check.

    **`TransferPrice` and `CostBasis` are parsed but not consumed.** They ARE a cost basis
    -- the previous shape of this model asserted they were "not a cost basis", which was
    wrong -- but in the broker's convention: IBKR nets an option-assignment premium into
    the basis of assigned shares, which German law rejects ([GT-ESTG20-004], BMF
    14.05.2025 Rz. 26). Taking them would understate the basis and tax the premium twice.
    The German-correct basis is the sending ledger's own reconstruction, which the
    handover relocates, so these two values are never read to value anything. They are
    parsed here only because they complete the required lot-detail export shape (an export
    lacking them is read on a heuristic instead, which is the state this file exists to
    prevent). What the `LOT` rows ARE used for -- the acquisition day, the quantity and the
    long/short sign -- is on `TransferLot`, and those are matched and cross-checked against
    the sending ledger.
    """
    client_account_id: Optional[str] = Field(None, alias="ClientAccountID")
    currency_primary: str = Field(alias="CurrencyPrimary")
    asset_class: str = Field(alias="AssetClass")
    symbol: Optional[str] = Field(None, alias="Symbol")
    description: Optional[str] = Field(None, alias="Description")
    conid: Optional[str] = Field(None, alias="Conid")
    isin: Optional[str] = Field(None, alias="ISIN")
    multiplier: Optional[Decimal] = Field(None, alias="Multiplier")
    date: str = Field(alias="Date")
    transfer_type: Optional[str] = Field(None, alias="Type")
    direction: Optional[str] = Field(None, alias="Direction")
    transfer_account: Optional[str] = Field(None, alias="TransferAccount")
    quantity: Decimal = Field(alias="Quantity")
    transfer_price: Optional[Decimal] = Field(None, alias="TransferPrice")
    transaction_id: Optional[str] = Field(None, alias="TransactionID")
    cost_basis: Optional[Decimal] = Field(None, alias="CostBasis")
    open_date_time: Optional[str] = Field(None, alias="OpenDateTime")
    level_of_detail: Optional[str] = Field(None, alias="LevelOfDetail")
    # The amount moved, on a cash row. `Quantity`, `PositionAmount` and `TransferPrice`
    # are all zero on such a row -- a cash move has no units -- so this is the only column
    # that carries it, and without it a currency move could not be measured at all. Blank
    # on a securities row, where the units are in `Quantity`.
    cash_transfer: Optional[Decimal] = Field(None, alias="CashTransfer")

    @validator('multiplier', 'quantity', 'transfer_price', 'cost_basis', 'cash_transfer', pre=True)
    def parse_decimal_fields(cls, v: Any) -> Any:
        """Blank becomes absent; anything else is handed to pydantic to parse or reject.

        Deliberately NOT the other models' pattern of defaulting an unparseable non-blank
        value to `Decimal("0.0")`. A quantity of zero here is a move of nothing, so that
        default would leave the holding where it was while the broker had moved it -- and
        the reconciliation that follows compares quantities, which would then agree with
        the snapshot for the wrong reason.

        Blank must not raise: `Multiplier` is blank on a cash row, `CostBasis` and
        `TransferPrice` blank on some summary rows. `Quantity` is required, so a blank one
        still raises.
        """
        if v is None or str(v).strip() == "":
            return None
        return v

    class Config:
        extra = 'ignore'

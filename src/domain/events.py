# src/domain/events.py
from dataclasses import dataclass, field, KW_ONLY
from decimal import Decimal
import uuid
from typing import Optional

from .enums import FinancialEventType
# Removed AssetCategory, InvestmentFundType, TaxReportingCategory imports as they are not directly used in event fields
# Asset information will be linked via asset_internal_id, and classification is on the Asset object itself.

@dataclass
class FinancialEvent:
    # Positional, non-default arguments
    asset_internal_id: uuid.UUID # Links to the Asset this event pertains to
    event_date: str # YYYY-MM-DD string representing the primary date of the event (e.g., trade date, payment date, settlement date)

    # Keyword-only arguments, can have defaults
    _: KW_ONLY
    event_type: FinancialEventType # The type of financial event
    event_id: uuid.UUID = field(default_factory=uuid.uuid4) # Unique ID for this event instance

    # Monetary amounts related to the event
    # These are typically in the original currency of the transaction/event
    gross_amount_foreign_currency: Optional[Decimal] = None # e.g., dividend amount, interest amount before tax
    local_currency: Optional[str] = None # The currency of gross_amount_foreign_currency

    # Corresponding amounts in EUR after conversion (populated by enrichment step)
    gross_amount_eur: Optional[Decimal] = None

    # IBKR specific identifiers for tracing back to reports
    ibkr_transaction_id: Optional[str] = None # From Trades, Cash Transactions etc.
    ibkr_activity_description: Optional[str] = None # From Cash Transactions "Description" or Trades "Description"
    ibkr_notes_codes: Optional[str] = None # From Trades "Notes/Codes" column

    def __post_init__(self):
        if not isinstance(self.event_type, FinancialEventType):
            raise TypeError(f"FinancialEvent.event_type must be a FinancialEventType enum member, got {type(self.event_type)}")
        if not self.event_date:
            raise ValueError("FinancialEvent.event_date cannot be empty.")
        # Basic date format validation (optional, could be stricter)
        # Example: if not (len(self.event_date) == 10 and self.event_date[4] == '-' and self.event_date[7] == '-'):
        # raise ValueError(f"event_date format error: {self.event_date}")


@dataclass
class TradeEvent(FinancialEvent):
    # Trade-specific details (positional after FinancialEvent's positional args)
    quantity: Decimal # Number of shares/contracts. Positive for buy, negative for sell.
    price_foreign_currency: Decimal # Price per unit in local_currency

    # Keyword-only arguments for TradeEvent
    _: KW_ONLY
    commission_foreign_currency: Optional[Decimal] = Decimal('0.0')
    commission_currency: Optional[str] = None # Currency of the commission
    commission_eur: Optional[Decimal] = None # Commission in EUR (populated by enrichment)

    # Net proceeds (for sales) or cost basis (for buys) in EUR, including commission
    # This can be calculated during processing.
    net_proceeds_or_cost_basis_eur: Optional[Decimal] = None

    # If this trade results from an option event (exercise/assignment)
    related_option_event_id: Optional[uuid.UUID] = None

    # event_type will be one of:
    # TRADE_BUY_LONG, TRADE_SELL_LONG, TRADE_SELL_SHORT_OPEN, TRADE_BUY_SHORT_COVER
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 quantity: Decimal, price_foreign_currency: Decimal, # Made core trade details part of the main signature
                 event_type: FinancialEventType, # Ensure event_type is passed correctly
                 commission_foreign_currency: Optional[Decimal] = Decimal('0.0'),
                 commission_currency: Optional[str] = None,
                 commission_eur: Optional[Decimal] = None,
                 net_proceeds_or_cost_basis_eur: Optional[Decimal] = None,
                 related_option_event_id: Optional[uuid.UUID] = None,
                 **kwargs_for_parent_kw_only): # Catches event_id, gross_amount_foreign_currency etc.
        super().__init__(asset_internal_id, event_date, event_type=event_type, **kwargs_for_parent_kw_only)
        self.quantity = quantity
        self.price_foreign_currency = price_foreign_currency
        self.commission_foreign_currency = commission_foreign_currency
        self.commission_currency = commission_currency
        self.commission_eur = commission_eur
        self.net_proceeds_or_cost_basis_eur = net_proceeds_or_cost_basis_eur
        self.related_option_event_id = related_option_event_id

    def __post_init__(self):
        super().__post_init__()
        # If commission is non-zero and its currency is not specified,
        # assume it's the same as the trade's local_currency.
        # This is crucial for the enrichment step to pick up the correct currency for conversion.
        if self.commission_foreign_currency is not None and self.commission_foreign_currency != Decimal('0.0'):
            if self.commission_currency is None and self.local_currency is not None:
                self.commission_currency = self.local_currency
            elif self.commission_currency is None and self.local_currency is None:
                # This scenario would be problematic for conversion.
                # Consider raising a warning or error if critical.
                # print(f"Warning: TradeEvent {self.event_id} has non-zero commission but no commission_currency and no local_currency.")
                pass
        elif self.commission_foreign_currency == Decimal('0.0') and self.commission_currency is None:
            # If commission is zero, its currency doesn't strictly matter for conversion,
            # but can be set to local_currency for consistency if local_currency exists.
             if self.local_currency is not None:
                self.commission_currency = self.local_currency


@dataclass
class CashFlowEvent(FinancialEvent): # For dividends, distributions, interest
    _: KW_ONLY
    source_country_code: Optional[str] = None # ISO country code, if applicable (e.g., for WHT context)
    # event_type will be one of:
    # DIVIDEND_CASH, DISTRIBUTION_FUND, INTEREST_RECEIVED, PAYMENT_IN_LIEU_DIVIDEND
    # gross_amount_foreign_currency in FinancialEvent holds the income amount.
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 event_type: FinancialEventType, # Ensure event_type is passed correctly
                 source_country_code: Optional[str] = None,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date, event_type=event_type, **kwargs_for_parent_kw_only)
        self.source_country_code = source_country_code

    def __post_init__(self):
        super().__post_init__()

@dataclass
class WithholdingTaxEvent(FinancialEvent):
    _: KW_ONLY
    taxed_income_event_id: Optional[uuid.UUID] = None # ID of the CashFlowEvent this tax relates to (optional)
    source_country_code: Optional[str] = None # ISO country code of the taxing authority
    # event_type is FinancialEventType.WITHHOLDING_TAX
    # gross_amount_foreign_currency in FinancialEvent holds the tax amount (should be positive).
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 taxed_income_event_id: Optional[uuid.UUID] = None,
                 source_country_code: Optional[str] = None,
                 **kwargs_for_parent_kw_only): # Catches event_id etc.
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.WITHHOLDING_TAX,
                         **kwargs_for_parent_kw_only)
        self.taxed_income_event_id = taxed_income_event_id
        self.source_country_code = source_country_code

    def __post_init__(self):
        super().__post_init__()


@dataclass
class CorporateActionEvent(FinancialEvent):
    _: KW_ONLY
    ca_action_id_ibkr: Optional[str] = None # IBKR's ActionID for this corporate action
    # event_type will be one of CORP_*
    # Specific details will be in subclasses.
    # gross_amount_foreign_currency might be used for cash components of CAs.
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 event_type: FinancialEventType, # Ensure event_type is passed
                 ca_action_id_ibkr: Optional[str] = None,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date, event_type=event_type, **kwargs_for_parent_kw_only)
        self.ca_action_id_ibkr = ca_action_id_ibkr

    def __post_init__(self):
        super().__post_init__()

@dataclass
class CorpActionSplitForward(CorporateActionEvent):
    _: KW_ONLY
    new_shares_per_old_share: Decimal # e.g., 2 for a 2-for-1 split

    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 new_shares_per_old_share: Decimal,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.CORP_SPLIT_FORWARD, # Renamed
                         **kwargs_for_parent_kw_only)
        self.new_shares_per_old_share = new_shares_per_old_share

    def __post_init__(self):
        super().__post_init__()


@dataclass
class CorpActionMergerCash(CorporateActionEvent): # Acquisition for cash
    _: KW_ONLY
    cash_per_share_foreign_currency: Decimal # Cash amount received per share disposed
    cash_per_share_eur: Optional[Decimal] = None # Cash amount per share in EUR (populated by enrichment)
    quantity_disposed: Decimal # Added: Store the quantity disposed directly (always positive)

    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 cash_per_share_foreign_currency: Decimal,
                 quantity_disposed: Decimal, # Added
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.CORP_MERGER_CASH, # Renamed
                         **kwargs_for_parent_kw_only)
        self.cash_per_share_foreign_currency = cash_per_share_foreign_currency
        self.quantity_disposed = quantity_disposed.copy_abs() # Ensure positive

    def __post_init__(self):
        super().__post_init__()


@dataclass
class CorpActionMergerStock(CorporateActionEvent): # Stock-for-stock merger
    _: KW_ONLY
    new_asset_internal_id: uuid.UUID # Asset ID of the new shares received
    new_shares_received_per_old: Decimal # Ratio: new shares received per one old share

    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 new_asset_internal_id: uuid.UUID,
                 new_shares_received_per_old: Decimal,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.CORP_MERGER_STOCK, # Renamed
                         **kwargs_for_parent_kw_only)
        self.new_asset_internal_id = new_asset_internal_id
        self.new_shares_received_per_old = new_shares_received_per_old

    def __post_init__(self):
        super().__post_init__()


@dataclass
class CorpActionStockDividend(CorporateActionEvent):
    _: KW_ONLY
    # Store the actual number of new shares received, easier to get from CSV usually
    quantity_new_shares_received: Decimal
    # Ratio is less critical if we have absolute quantity and FMV, keep as optional reference
    new_shares_per_existing_share: Optional[Decimal] = None # Renamed from quantity_new_shares_received_per_old
    fmv_per_new_share_foreign_currency: Optional[Decimal] = None # Fair Market Value of each new share received, if taxable as income
    fmv_per_new_share_eur: Optional[Decimal] = None # FMV per new share in EUR (populated by enrichment)


    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 quantity_new_shares_received: Decimal, # Added this direct quantity
                 new_shares_per_existing_share: Optional[Decimal] = None, # Renamed and made optional
                 fmv_per_new_share_foreign_currency: Optional[Decimal] = None,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.CORP_STOCK_DIVIDEND, # Renamed
                         **kwargs_for_parent_kw_only)
        self.quantity_new_shares_received = quantity_new_shares_received
        self.new_shares_per_existing_share = new_shares_per_existing_share
        self.fmv_per_new_share_foreign_currency = fmv_per_new_share_foreign_currency

    def __post_init__(self):
        super().__post_init__()


@dataclass
class CorpActionExpireDividendRights(CorporateActionEvent):
    """Event for ED (Expire Dividend Rights) corporate actions.
    
    This event is used only for post-processing to identify and modify
    matching DI events and cash dividend events. It carries no tax implications itself.
    """
    _: KW_ONLY
    
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.CORP_EXPIRE_DIVIDEND_RIGHTS,
                         **kwargs_for_parent_kw_only)
    
    def __post_init__(self):
        super().__post_init__()


@dataclass
class OptionLifecycleEvent(FinancialEvent):
    _: KW_ONLY
    quantity_contracts: Decimal # Number of option contracts involved

    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 event_type: FinancialEventType, # Ensure event_type is passed by subclasses
                 quantity_contracts: Decimal,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date, event_type=event_type, **kwargs_for_parent_kw_only)
        self.quantity_contracts = quantity_contracts

    def __post_init__(self):
        super().__post_init__()


@dataclass
class OptionExerciseEvent(OptionLifecycleEvent):
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 quantity_contracts: Decimal,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date, quantity_contracts=quantity_contracts,
                         event_type=FinancialEventType.OPTION_EXERCISE,
                         **kwargs_for_parent_kw_only)
    def __post_init__(self): super().__post_init__()


@dataclass
class OptionAssignmentEvent(OptionLifecycleEvent):
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 quantity_contracts: Decimal,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date, quantity_contracts=quantity_contracts,
                         event_type=FinancialEventType.OPTION_ASSIGNMENT,
                         **kwargs_for_parent_kw_only)
    def __post_init__(self): super().__post_init__()


@dataclass
class OptionExpirationWorthlessEvent(OptionLifecycleEvent):
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 quantity_contracts: Decimal,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date, quantity_contracts=quantity_contracts,
                         event_type=FinancialEventType.OPTION_EXPIRATION_WORTHLESS,
                         **kwargs_for_parent_kw_only)
    def __post_init__(self): super().__post_init__()


@dataclass
class CurrencyConversionEvent(FinancialEvent):
    _: KW_ONLY
    from_currency: str
    from_amount: Decimal
    to_currency: str
    to_amount: Decimal
    exchange_rate: Decimal # As reported by IBKR for this specific conversion

    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *, # asset_internal_id might be a dummy/general one for pure FX
                 from_currency: str, from_amount: Decimal,
                 to_currency: str, to_amount: Decimal, exchange_rate: Decimal,
                 **kwargs_for_parent_kw_only):
        # For CurrencyConversionEvent, 'gross_amount_foreign_currency' and 'local_currency'
        # in the parent FinancialEvent are set to the 'to_amount' and 'to_currency' respectively
        # by default if not provided through kwargs_for_parent_kw_only.
        # This makes the 'to' side the primary representation for FinancialEvent fields.
        # The 'from' side is specific to CurrencyConversionEvent.
        # The event_type is CURRENCY_CONVERSION.
        # asset_internal_id here could represent the target currency cash balance asset.
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.CURRENCY_CONVERSION,
                         **kwargs_for_parent_kw_only)
        self.from_currency = from_currency
        self.from_amount = from_amount
        self.to_currency = to_currency
        self.to_amount = to_amount
        self.exchange_rate = exchange_rate

        # Default parent's gross amount and currency to the 'to' side of the conversion
        # if they weren't explicitly passed in kwargs_for_parent_kw_only
        if self.gross_amount_foreign_currency is None:
            self.gross_amount_foreign_currency = to_amount
        if self.local_currency is None:
            self.local_currency = to_currency
        # gross_amount_eur will be populated by the enrichment step based on to_amount and to_currency (if to_currency is not EUR).

    def __post_init__(self):
        super().__post_init__()


@dataclass
class FeeEvent(FinancialEvent):
    # For miscellaneous fees (e.g., account fees, market data fees)
    # event_type is FinancialEventType.FEE_TRANSACTION
    # gross_amount_foreign_currency in FinancialEvent holds the fee amount (typically negative or handled as positive cost)
    # local_currency in FinancialEvent holds the currency of the fee
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, # Removed the problematic bare '*'
                 **kwargs_for_parent_kw_only): # asset_internal_id could be general cash account
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.FEE_TRANSACTION,
                         **kwargs_for_parent_kw_only)

    def __post_init__(self):
        super().__post_init__()

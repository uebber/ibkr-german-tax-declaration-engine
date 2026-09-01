# src/domain/events.py
import itertools
from dataclasses import dataclass, field, KW_ONLY
from decimal import Decimal
import uuid
from typing import Optional

from .enums import FinancialEventType
# Removed AssetCategory, InvestmentFundType, TaxReportingCategory imports as they are not directly used in event fields
# Asset information will be linked via asset_internal_id, and classification is on the Asset object itself.

# Hands out `FinancialEvent.creation_sequence`. See the field for why this exists and
# why `event_id` cannot do its job.
_creation_sequence_counter = itertools.count()


def _next_creation_sequence() -> int:
    return next(_creation_sequence_counter)

@dataclass
class FinancialEvent:
    # Positional, non-default arguments
    asset_internal_id: uuid.UUID # Links to the Asset this event pertains to
    # YYYY-MM-DD. The date the law attaches to this event, which differs by event kind and is
    # never a matter of which field the broker happened to populate:
    #   trade      -> the contract date, the obligatorisches Rechtsgeschaeft. BMF 14.05.2025
    #                 Rn. 317 for Erwerb and Rn. 85 for Veraeusserung/Einloesung; it fixes the
    #                 FX rate, the gain, the assessment year and the Section 23 Jahresfrist.
    #                 Built by DomainEventFactory._trade_contract_date, which accepts no
    #                 settlement or report date. [GT-ESTG20-039], [GT-ESTG20-040]
    #   cash flow  -> the Zufluss: settlement for a cash transaction, pay date for a corporate
    #                 action. Built by DomainEventFactory._zufluss_date.
    # A settlement date is never the date of a trade here, and the Trades import carries no
    # settlement column at all.
    event_date: str

    # Keyword-only arguments, can have defaults
    _: KW_ONLY
    event_type: FinancialEventType # The type of financial event
    event_id: uuid.UUID = field(default_factory=uuid.uuid4) # Unique ID for this event instance

    # The final tie-break of `get_event_sort_key`, and the only element of it that is
    # guaranteed to differ between two distinct events.
    #
    # `event_id` used to hold that position. It is unique *within* a run and redrawn on the
    # next one, so two events tying on every earlier element were ordered at random,
    # differently each run — while the PRD and the sort key's own docstring called the
    # result deterministic. Measured on VZ 2025 (issue #71): 14 OptionEAE cash settlements,
    # the one input carrying no `TransactionID`, reordered freely between two captures of
    # the same tree. No figure moved there, but only because those 14 fell on distinct
    # option ledgers and all but two were EUR — properties of that year's data, not of this
    # code.
    #
    # A construction counter rather than a source row index because it cannot be missed:
    # every event gets one at __init__, including the ones the engine synthesises after
    # parsing (`calculation_engine._create_excess_dividend_event`, the sub-events
    # `fifo_manager.split_position_flip_event` builds at dispatch), which have no source
    # row to index. Construction order follows the order rows are read out of the
    # concatenated input, so the tie-break also tracks the order IBKR reported — but
    # determinism is the property being bought here, and it holds whatever the
    # construction order happens to be.
    creation_sequence: int = field(default_factory=_next_creation_sequence)

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

    # The custody account (Depot) this event was booked in — IBKR's ClientAccountID.
    # A disposal consumes the lots of the account it was made from: FIFO is applied
    # per single Depot (BMF 14.05.2025 Rz. 97 Satz 2, [GT-ESTG20-013]). Normalised to
    # a ledger key by `account_key()`, which collapses an absent id to one DEFAULT
    # account, so an export without the column behaves exactly as before.
    account_id: Optional[str] = None # From ClientAccountID

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

    # True if this trade is a position flip (IBKR C;O or O;C indicator),
    # meaning part closes existing position and part opens opposite direction.
    # Split into two sub-events at FIFO dispatch time when ledger state is known.
    is_position_flip: bool = False

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
                 is_position_flip: bool = False,
                 **kwargs_for_parent_kw_only): # Catches event_id, gross_amount_foreign_currency etc.
        super().__init__(asset_internal_id, event_date, event_type=event_type, **kwargs_for_parent_kw_only)
        self.quantity = quantity
        self.price_foreign_currency = price_foreign_currency
        self.commission_foreign_currency = commission_foreign_currency
        self.commission_currency = commission_currency
        self.commission_eur = commission_eur
        self.net_proceeds_or_cost_basis_eur = net_proceeds_or_cost_basis_eur
        self.related_option_event_id = related_option_event_id
        self.is_position_flip = is_position_flip

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
    # DIVIDEND_CASH, DISTRIBUTION_FUND, INTEREST_RECEIVED
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
    link_confidence_score: Optional[int] = None # Confidence score (0-100) of the linking to income event
    effective_tax_rate: Optional[Decimal] = None # Calculated effective tax rate (WHT amount / income amount)
    # event_type is FinancialEventType.WITHHOLDING_TAX
    # gross_amount_foreign_currency in FinancialEvent holds the tax amount (should be positive).
    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 taxed_income_event_id: Optional[uuid.UUID] = None,
                 source_country_code: Optional[str] = None,
                 link_confidence_score: Optional[int] = None,
                 effective_tax_rate: Optional[Decimal] = None,
                 **kwargs_for_parent_kw_only): # Catches event_id etc.
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.WITHHOLDING_TAX,
                         **kwargs_for_parent_kw_only)
        self.taxed_income_event_id = taxed_income_event_id
        self.source_country_code = source_country_code
        self.link_confidence_score = link_confidence_score
        self.effective_tax_rate = effective_tax_rate

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
class OptionCashSettlementEvent(OptionLifecycleEvent):
    """Cash settlement for index options (SPX, ESTX50).

    The cash_settlement_proceeds is the total intrinsic value exchanged:
    - Positive = money received (long option exercised ITM)
    - Negative = money paid out (short option assigned ITM)

    The related_option_event_id links to the companion Assignment/Exercise event
    that closed the option position.
    """
    _: KW_ONLY
    cash_settlement_proceeds: Decimal  # In local_currency, signed
    commission_foreign_currency: Decimal = Decimal('0')
    commission_eur: Optional[Decimal] = None
    related_option_event_id: Optional[uuid.UUID] = None

    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 quantity_contracts: Decimal,
                 cash_settlement_proceeds: Decimal,
                 commission_foreign_currency: Decimal = Decimal('0'),
                 commission_eur: Optional[Decimal] = None,
                 related_option_event_id: Optional[uuid.UUID] = None,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date, quantity_contracts=quantity_contracts,
                         event_type=FinancialEventType.OPTION_CASH_SETTLEMENT,
                         **kwargs_for_parent_kw_only)
        self.cash_settlement_proceeds = cash_settlement_proceeds
        self.commission_foreign_currency = commission_foreign_currency
        self.commission_eur = commission_eur
        self.related_option_event_id = related_option_event_id
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


@dataclass
class TransferLot:
    """One acquisition-day's worth of a moved holding, read from a Transfers `LOT` row.

    The export writes one `LOT` row per acquisition day beneath each move's summary row
    (measured: one row per day, not per trade -- three same-day trades collapse to one
    row). Carries the day (`OpenDateTime`), the units moved that day, and the per-lot sign.
    The handover uses all three: the day and quantity are matched against the sending
    ledger to find the lots that moved, and the sign is cross-checked against the ledger's
    own long-versus-short. The `LOT` row's `CostBasis` is NOT carried here -- it is in
    IBKR's convention (an option-assignment premium netted into the basis, contrary to
    [GT-ESTG20-004]) and the German basis is the ledger's own reconstruction, so it is
    parsed on `RawTransferRecord` to complete the required export shape and not consumed.
    See `src/parsers/raw_models.py::RawTransferRecord`.
    """
    acquisition_date: str  # YYYY-MM-DD, the export's OpenDateTime for this lot
    quantity: Decimal      # units moved on that day, always positive
    # The export's per-lot sign: negative on a short position, positive on a long one
    # (measured -- 6 of 13 real lot rows are shorts opened by SELL). The sending ledger is
    # authoritative for long-versus-short; this is the cross-check the export now permits.
    is_short: bool = False


@dataclass
class InternalTransferEvent(FinancialEvent):
    """A holding moved from one of the taxpayer's own accounts to another.

    **Not a disposal** -- no change of beneficial owner and no consideration, so
    acquisition date and acquisition cost carry over and the lots RELOCATE between the
    two accounts' ledgers rather than being closed and reopened ([GT-ESTG20-014];
    reference/tax-law/estg-20-kapitalvermoegen.md, "Abs. 2"). It therefore realises
    nothing: no proceeds, no cost, no amount of any kind, which is why this event carries
    none.

    `account_id` (from `FinancialEvent`) is the SENDING account and `to_account_id` the
    receiving one -- the same convention as every other event, where `account_id` is the
    account whose ledger the event acts on first.

    `quantity` is the total number of units moved, always positive. `moved_lots` breaks
    that total down by acquisition day, from the export's `LOT` rows: the handover
    relocates the sending ledger's lots for each of those days. The export's sign carries
    neither the direction nor long-versus-short of the total (see `RawTransferRecord`);
    the per-lot sign in `moved_lots` does state long-versus-short, and it is cross-checked
    against the sending ledger, which is authoritative.

    **`ibkr_transaction_id` is deliberately left unset.** The export records each move
    once per side and the two sides carry different ids, so neither names the move. It
    would also decide more than identity: `get_event_sort_key` places
    `ibkr_transaction_id` ahead of the intra-day band, so an id here would let a broker's
    string decide whether the move lands before or after the same day's trades. That
    order is fixed deliberately by the band branch in `sorting_utils.py` instead.
    """
    _: KW_ONLY
    to_account_id: str
    quantity: Decimal
    moved_lots: list = field(default_factory=list)

    def __init__(self, asset_internal_id: uuid.UUID, event_date: str, *,
                 to_account_id: str, quantity: Decimal,
                 moved_lots: Optional[list] = None,
                 **kwargs_for_parent_kw_only):
        super().__init__(asset_internal_id, event_date,
                         event_type=FinancialEventType.INTERNAL_TRANSFER,
                         **kwargs_for_parent_kw_only)
        self.to_account_id = to_account_id
        self.quantity = quantity
        self.moved_lots = moved_lots if moved_lots is not None else []
        # Checked here and not in `__post_init__`: the parent's generated `__init__`
        # calls `__post_init__` before the three lines above have run, so none of the
        # fields exist yet at that point.
        if quantity is None or quantity <= Decimal(0):
            raise ValueError(
                f"InternalTransferEvent quantity must be positive, got {quantity}. "
                f"The export's sign does not carry the direction; callers pass the "
                f"absolute quantity and the direction separately."
            )
        if not to_account_id or not str(to_account_id).strip():
            raise ValueError(
                "InternalTransferEvent requires a receiving account. Without it the "
                "units have nowhere to go and would be lost rather than relocated."
            )

    def __post_init__(self):
        super().__post_init__()

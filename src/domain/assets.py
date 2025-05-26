# src/domain/assets.py
from dataclasses import dataclass, field, KW_ONLY
from decimal import Decimal
import uuid
from typing import Set, Optional

from .enums import AssetCategory, InvestmentFundType

@dataclass # Base class defines eq and hash
class Asset:
    _: KW_ONLY
    asset_category: AssetCategory
    internal_asset_id: uuid.UUID = field(default_factory=uuid.uuid4)
    aliases: Set[str] = field(default_factory=set) # All known string identifiers (ISIN:xxx, CONID:xxx, SYMBOL:xxx, CASH_BALANCE:xxx)
    description: Optional[str] = None
    currency: Optional[str] = None # Primary currency of the asset (e.g., USD for AAPL stock, EUR for a EUR cash balance)
    user_notes: Optional[str] = None

    # IBKR specific identifiers, stored for reference and aiding identification
    ibkr_conid: Optional[str] = None
    ibkr_symbol: Optional[str] = None # The symbol as reported by IBKR
    ibkr_isin: Optional[str] = None
    ibkr_asset_class_raw: Optional[str] = None # e.g., "STK", "OPT", "FUND", "CASH"
    ibkr_sub_category_raw: Optional[str] = None # e.g. "COMMON", "ETF"

    # Start of Year (SOY) position data (from IBKR positions_start_file)
    soy_quantity: Optional[Decimal] = None # Renamed from initial_quantity_soy
    soy_cost_basis_amount: Optional[Decimal] = None # Renamed from initial_cost_basis_money_soy
    soy_cost_basis_currency: Optional[str] = None # Renamed from initial_cost_basis_currency_soy

    # End of Year (EOY) position data (from IBKR positions_end_file, for Vorabpauschale, reconciliation)
    eoy_quantity: Optional[Decimal] = None
    eoy_mark_price_currency: Optional[str] = None # Currency of the EOY mark price
    eoy_market_price: Optional[Decimal] = None # Renamed from eoy_mark_price
    eoy_position_value: Optional[Decimal] = None # EOY position value in eoy_mark_price_currency


    def __post_init__(self):
        if not isinstance(self.asset_category, AssetCategory):
             raise TypeError(f"Asset.asset_category must be an AssetCategory enum member, got {type(self.asset_category)}")

    def add_alias(self, alias_string: str):
        if alias_string:
            self.aliases.add(alias_string)

    def get_classification_key(self) -> str:
        """
        Generates a stable key for caching user-defined classifications.
        Priority: ISIN > Conid > Specific Cash Balance Key > Symbol.
        Raises ValueError if no stable key can be determined.
        """
        if self.ibkr_isin:
            return f"ISIN:{self.ibkr_isin}"
        if self.ibkr_conid:
            return f"CONID:{self.ibkr_conid}"

        # Special handling for CashBalance assets for a stable key
        if self.asset_category == AssetCategory.CASH_BALANCE and self.currency:
            return f"CASH_BALANCE:{self.currency}"

        if self.ibkr_symbol:
            # Using ibkr_asset_class_raw to help differentiate symbols that might be shared (e.g. 'EUR' symbol)
            # but represent different asset types (e.g. cash vs a stock with symbol 'EUR')
            # However, for classification, a simpler symbol key might be better if asset class is already handled.
            # The PRD suggests resolver creates specific aliases like "CASH_BALANCE:EUR", which will be primary.
            # If it's not a cash balance, then SYMBOL: is the way.
             # Add asset class to help differentiate symbols that might be shared across classes (e.g., 'CAD' symbol vs 'CAD' currency)
            # Exclude for CASH as CASH_BALANCE:CURRENCY is handled above.
             if self.asset_category != AssetCategory.CASH_BALANCE and self.ibkr_asset_class_raw:
                 return f"SYMBOL:{self.ibkr_symbol}_{self.ibkr_asset_class_raw}"
             else: # Fallback for non-cash without asset class? Should be rare.
                 return f"SYMBOL:{self.ibkr_symbol}"

        # Fallback removed - raise error if no stable key found
        raise ValueError(
            f"Cannot generate stable classification key for asset "
            f"(ID: {self.internal_asset_id}, Desc: '{self.description}', Cat: {self.asset_category.name}). "
            f"Missing ISIN, ConID, Symbol, and not a Cash Balance."
        )


    def __hash__(self):
        return hash(self.internal_asset_id)

    def __eq__(self, other):
        if not isinstance(other, Asset):
            return NotImplemented
        return self.internal_asset_id == other.internal_asset_id


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset
class Stock(Asset):
    # Specific attributes for stocks, if any, beyond base Asset
    def __init__(self, **kwargs): # Ensure asset_category is correctly passed if not fixed by __init__
        super().__init__(asset_category=kwargs.pop('asset_category', AssetCategory.STOCK), **kwargs)

    def __post_init__(self):
        super().__post_init__()
        if self.asset_category != AssetCategory.STOCK:
            self.asset_category = AssetCategory.STOCK


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset
class Bond(Asset):
    # Specific attributes for bonds
    def __init__(self, **kwargs):
        super().__init__(asset_category=kwargs.pop('asset_category', AssetCategory.BOND), **kwargs)

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.BOND


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset
class InvestmentFund(Asset):
    _: KW_ONLY
    fund_type: Optional[InvestmentFundType] = InvestmentFundType.NONE # Default to NONE

    def __init__(self, *, fund_type: Optional[InvestmentFundType] = InvestmentFundType.NONE, **kwargs):
        super().__init__(asset_category=kwargs.pop('asset_category', AssetCategory.INVESTMENT_FUND), **kwargs)
        self.fund_type = fund_type if fund_type is not None else InvestmentFundType.NONE

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.INVESTMENT_FUND
        if self.fund_type is not None and not isinstance(self.fund_type, InvestmentFundType):
            raise TypeError(f"InvestmentFund.fund_type must be an InvestmentFundType enum member or None, got {type(self.fund_type)}")
        if self.fund_type is None: # Ensure it's always set to NONE if not provided or explicitly None
            self.fund_type = InvestmentFundType.NONE


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset
class Derivative(Asset): # Abstract base for Option, Cfd
    _: KW_ONLY
    underlying_asset_internal_id: Optional[uuid.UUID] = None
    # IBKR identifiers for the underlying, useful for resolving underlying_asset_internal_id
    underlying_ibkr_conid: Optional[str] = None
    underlying_ibkr_symbol: Optional[str] = None
    multiplier: Decimal = Decimal('1.0')
    # asset_category will be set by subclasses (Option, Cfd)

    def __post_init__(self):
        super().__post_init__()


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset (via Derivative)
class Option(Derivative):
    _: KW_ONLY
    option_type: Optional[str] = None  # 'P' for Put, 'C' for Call
    strike_price: Optional[Decimal] = None
    expiry_date: Optional[str] = None # YYYY-MM-DD string

    def __init__(self, *,
                 option_type: Optional[str] = None,
                 strike_price: Optional[Decimal] = None,
                 expiry_date: Optional[str] = None,
                 **kwargs_for_parents):
        # Ensure asset_category is passed to Derivative, which passes to Asset
        super().__init__(asset_category=kwargs_for_parents.pop('asset_category', AssetCategory.OPTION), **kwargs_for_parents)
        self.option_type = option_type
        self.strike_price = strike_price
        self.expiry_date = expiry_date

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.OPTION
        if self.option_type not in [None, 'P', 'C']:
            raise ValueError(f"Option.option_type must be 'P', 'C', or None, got {self.option_type}")


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset (via Derivative)
class Cfd(Derivative):
    # Specific attributes for CFDs, if any
    def __init__(self, **kwargs_for_parents):
        super().__init__(asset_category=kwargs_for_parents.pop('asset_category', AssetCategory.CFD), **kwargs_for_parents)

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.CFD


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset
class PrivateSaleAsset(Asset): # Renamed from Section23EstgAsset
    # Specific attributes for §23 EStG assets
    def __init__(self, **kwargs):
        super().__init__(asset_category=kwargs.pop('asset_category', AssetCategory.PRIVATE_SALE_ASSET), **kwargs)

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.PRIVATE_SALE_ASSET


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset
class CashBalance(Asset):
    # Currency is a key identifier for CashBalance, set in Asset.currency
    def __init__(self, *, currency: str, **kwargs): # currency is mandatory
        if not currency:
             raise ValueError("CashBalance instantiation requires a currency.")
        # The asset_category is fixed here, and currency is passed to the parent Asset.
        super().__init__(asset_category=kwargs.pop('asset_category', AssetCategory.CASH_BALANCE), currency=currency, **kwargs)
        # Ensure the primary alias reflects this is a cash balance
        self.add_alias(f"CASH_BALANCE:{currency.upper()}")

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.CASH_BALANCE
        if self.currency is None: # Should be caught by __init__
            raise ValueError("CashBalance must have a currency.")
        # Ensure symbol is typically the currency code for cash balances if not set otherwise
        if self.ibkr_symbol is None and self.currency:
            self.ibkr_symbol = self.currency
        if self.description is None and self.currency:
            self.description = f"Cash Balance {self.currency}"

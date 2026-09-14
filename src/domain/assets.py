# src/domain/assets.py
from dataclasses import dataclass, field, KW_ONLY
from datetime import date
from decimal import Decimal
import uuid
from typing import Dict, List, Optional, Set, Tuple, TypeVar

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

    # No snapshot of a holding is here, and none may be added.
    #
    # Every snapshot the engine reads is recorded per `(account, asset)` in the
    # `ParsingOrchestrator` registries -- the tax year's opening and closing
    # positions (`soy_positions` / `eoy_positions`), the checkpoint marks
    # (`mark_positions`), and the preceding calendar year's three Vorabpauschale
    # snapshots (`prior_soy_positions`, `prior_eoy_positions`,
    # `prior_opening_positions`). The person's figure is `person_snapshot()` over
    # those, derived where it is needed and never stored.
    #
    # A Flex Query covering several accounts emits one row per account. Reading
    # those rows onto one field per instrument is how one account's holding came
    # to be declared as the person's ([GT-ESTG20-061]); keyed by account they
    # cannot overwrite each other. FIFO is applied per Depot (BMF 14.05.2025
    # Rz. 97 Satz 2, [GT-ESTG20-013]) while the person declares the total across
    # their accounts, and both readings are wanted -- storing either one on the
    # Asset means bridging to the other.
    #
    # The registries are keyed by `internal_asset_id`, which a reclassification
    # preserves, so a snapshot cannot be lost by an asset being rebuilt as a
    # different Python type.


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
class SonstigeKapitalforderung(Asset):
    """A sonstige Kapitalforderung under 20 Abs. 2 Satz 1 Nr. 7 that is not a bond.

    Unbacked gold and commodity ETCs ([GT-ESTG23-011], BMF 14.05.2025 Rz. 57),
    Zertifikate ([GT-ESTG20-038], Rz. 9 excludes them from the Termingeschaefte), and
    unallocated spot precious metal at the broker (Q11, Reading C). Disposals go to
    Anlage KAP Zeile 19/22, the same lines as a bond, but this is deliberately not
    ``Bond``: none of the bond-specific handling (percentage-of-nominal trade prices,
    Stueckzinsen, BM maturity) applies to these instruments.

    Which instrument is routed here is a per-instrument determination that cannot be read
    off an IBKR asset class ([GT-ESTG23-011]); it comes from classification only.
    """
    def __init__(self, **kwargs):
        super().__init__(asset_category=kwargs.pop('asset_category', AssetCategory.SONSTIGE_KAPITALFORDERUNG), **kwargs)

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.SONSTIGE_KAPITALFORDERUNG


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


@dataclass(eq=False) # Inherit __eq__ and __hash__ from Asset (via Derivative)
class Future(Derivative):
    # Futures contracts — Termingeschäfte like options/CFDs for German tax purposes
    def __init__(self, **kwargs_for_parents):
        super().__init__(asset_category=kwargs_for_parents.pop('asset_category', AssetCategory.FUTURE), **kwargs_for_parents)

    def __post_init__(self):
        super().__post_init__()
        self.asset_category = AssetCategory.FUTURE


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


@dataclass(frozen=True)
class PositionSnapshot:
    """One account's holding of one asset, as the broker reported it in a snapshot.

    The tax year's opening and closing snapshots, recorded per `(account, asset)`
    because that is what they are: a Flex Query covering several accounts emits one
    row per account, and reading them as one row per instrument is how one account's
    holding came to be declared as the person's ([GT-ESTG20-061]).

    Every field but the last is exactly one column of the Positions export. Amounts and
    quantities belong to the account; `mark_price` is per unit and so is a property of the
    instrument, which is why `person_snapshot` sums the first and takes the second.

    `mark_price_date` is the day the price was set. The export carries no such column, so
    it is the naming convention the file was selected by, and only the preceding year's
    snapshots record it -- Rz. 18.6 converts a Vorabpauschale price at the ECB rate of its
    own Stichtag ([GT-INVSTG-018]), and nothing else here needs the day at all.
    """
    quantity: Optional[Decimal]
    cost_basis_amount: Optional[Decimal] = None
    cost_basis_currency: Optional[str] = None
    position_value: Optional[Decimal] = None
    mark_price: Optional[Decimal] = None
    mark_price_currency: Optional[str] = None
    mark_price_date: Optional[date] = None


# {(account_key, asset_id): PositionSnapshot} -- the shape every snapshot registry takes:
# the tax year's opening and closing positions, and the preceding year's three
# Vorabpauschale snapshots.
SnapshotsByAccount = Dict[Tuple[str, uuid.UUID], PositionSnapshot]

_RecordT = TypeVar("_RecordT")


def snapshots_for_asset(snapshots: Dict[Tuple[str, uuid.UUID], _RecordT],
                        asset_id: uuid.UUID) -> List[Tuple[str, _RecordT]]:
    """Every account's record of one asset, in account order.

    Sorted rather than left in insertion order: insertion order is the order the rows
    happened to arrive in the export, which is input a figure must not depend on.

    Used for both registry shapes -- `PositionSnapshot` and `MarkPosition` -- because
    the account key is all it reads.
    """
    return sorted(((account, snap) for (account, aid), snap in snapshots.items()
                   if aid == asset_id), key=lambda pair: pair[0])


def person_snapshot(snapshots: "SnapshotsByAccount",
                    asset_id: uuid.UUID) -> Optional[PositionSnapshot]:
    """One asset's holding across all of a person's accounts, or None if unreported.

    The person is the unit of assessment ([GT-ESTG20-061]), so quantities and amounts
    are summed. `None` in a column is "the broker left it blank" and is skipped, so an
    asset whose every row is blank keeps `None` there and reaches the guard that
    refuses a holding reported with no cost basis. What that cannot distinguish is one
    account blank and another filled; see `_sum_snapshot_column` in
    `src/parsers/parsing_orchestrator.py`, where the same assumption is written out.

    A currency belongs to the instrument, not to the account holding it, so the rows
    agree and the first non-empty one is taken. `parsing_orchestrator` refuses two
    currencies for one asset at read time, which is where a disagreement can still be
    named against the row that carried it.

    `mark_price` is per unit and so belongs to the instrument too, but the rows can
    genuinely disagree about it -- one ISIN listed on two exchanges carries two market
    prices. It is therefore the value they agree on, or `None` where they do not, which
    is what `_one_snapshot_price` in `parsing_orchestrator` does within one account and
    for the same reason. A row reporting no price adds nothing: a blank is the broker
    omitting a figure, not a second venue disagreeing about it.
    """
    rows = [snap for _account, snap in snapshots_for_asset(snapshots, asset_id)]
    if not rows:
        return None

    def total(pick):
        values = [v for v in (pick(r) for r in rows) if v is not None]
        return sum(values[1:], values[0]) if values else None

    def first(pick):
        return next((v for v in (pick(r) for r in rows) if v is not None), None)

    def agreed(pick):
        values = [v for v in (pick(r) for r in rows) if v is not None]
        if not values:
            return None
        return values[0] if all(v == values[0] for v in values) else None

    return PositionSnapshot(
        quantity=total(lambda r: r.quantity),
        cost_basis_amount=total(lambda r: r.cost_basis_amount),
        cost_basis_currency=first(lambda r: r.cost_basis_currency),
        position_value=total(lambda r: r.position_value),
        mark_price=agreed(lambda r: r.mark_price),
        mark_price_currency=first(lambda r: r.mark_price_currency),
        mark_price_date=first(lambda r: r.mark_price_date),
    )


@dataclass(frozen=True)
class MarkPosition:
    """One asset's holding as the broker reported it at a checkpoint mark.

    A *mark* is the close of a calendar year inside the historical replay
    window, taken from `Positions-{Y}-EoY.csv`. The replay stops at each mark
    and compares; where it disagrees with the broker the reconstruction is
    replaced by this. Distinct from the tax year's own opening snapshot, which
    is one `PositionSnapshot` per (account, asset) -- itself read from
    `Positions-{tax_year-1}-EoY.csv`, not from any SoY file. Keeping the two
    apart is what stops a mid-window snapshot feeding the tax year's cost basis.

    Only what reconciliation needs: quantity and the reported cost basis. A
    mark supplies no acquisition date, which is why a lot built from one is
    flagged `acquisition_date_is_known=False`.

    Recorded per `(account, asset)` like every other snapshot, and for the same
    reason: one instrument held in two accounts is reported on two rows at each
    mark ([GT-ESTG20-061]).
    """
    quantity: Decimal
    cost_basis_amount: Optional[Decimal]
    cost_basis_currency: Optional[str]


# {(account_key, asset_id): MarkPosition} -- one calendar year's checkpoint mark.
MarksByAccount = Dict[Tuple[str, uuid.UUID], MarkPosition]


def person_mark(marks: "MarksByAccount",
                asset_id: uuid.UUID) -> Optional[MarkPosition]:
    """One asset's holding at a mark across all of a person's accounts, or None.

    The counterpart of `person_snapshot` for the checkpoint marks, and it sums for
    the same reason: the person is the unit of assessment ([GT-ESTG20-061]).

    Quantity and cost basis are summed together or not at all. A quantity added up
    across the rows and a cost basis taken from one of them imply a per-unit cost
    that belongs to no holding anybody had -- and that is the figure a reconstruction
    disagreeing with the broker is replaced by. A blank cost basis is skipped rather
    than read as zero, so an asset whose every row is blank keeps `None` and reaches
    the guard that refuses a holding reported with no cost basis.
    """
    rows = [mark for _account, mark in snapshots_for_asset(marks, asset_id)]
    if not rows:
        return None
    amounts = [r.cost_basis_amount for r in rows if r.cost_basis_amount is not None]
    currency = next((r.cost_basis_currency for r in rows
                     if r.cost_basis_currency is not None), None)
    return MarkPosition(
        quantity=sum((r.quantity for r in rows[1:]), rows[0].quantity),
        cost_basis_amount=sum(amounts[1:], amounts[0]) if amounts else None,
        cost_basis_currency=currency,
    )

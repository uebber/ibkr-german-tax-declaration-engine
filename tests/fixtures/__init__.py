"""
Test Fixtures Module

This module provides structured test specifications in two formats:

1. YAML-based specs (group1_core_fifo.yaml, etc.)
   - Best for: Input/output scenarios with clear parameter variations
   - Human-readable, parseable, git-diff friendly
   - Use load_yaml_spec() to parse

2. Python dataclass specs (loss_offsetting_data.py, etc.)
   - Best for: Complex data structures with type safety
   - IDE support, refactoring-friendly
   - Import directly and use with pytest.mark.parametrize

Both formats support:
- Capturing intent and PRD references
- Grouping related test cases
- Documenting variations and corner cases
- Transparent threshold testing
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from decimal import Decimal
import yaml


FIXTURES_DIR = Path(__file__).parent


@dataclass
class TradeSpec:
    """Parsed trade from YAML spec."""
    type: str
    qty: Decimal
    price: Decimal
    date: str
    asset: Optional[str] = None
    currency: str = "EUR"
    time: Optional[str] = None


@dataclass
class PositionSpec:
    """Parsed position from YAML spec (SOY/EOY)."""
    quantity: Decimal
    cost_basis: Optional[Decimal] = None
    currency: str = "EUR"


@dataclass
class ExpectedRGLSpec:
    """Parsed expected RGL from YAML spec."""
    realization_type: str
    quantity: Optional[Decimal] = None
    acquisition_date: Optional[str] = None
    realization_date: Optional[str] = None
    total_cost_basis_eur: Optional[Decimal] = None
    total_proceeds_eur: Optional[Decimal] = None
    gain_loss_eur: Optional[Decimal] = None
    tax_category: Optional[str] = None
    asset: Optional[str] = None
    is_stillhalter_income: Optional[bool] = None


# =============================================================================
# Option-specific dataclasses
# =============================================================================

@dataclass
class OptionTradeSpec:
    """Parsed option trade from YAML spec."""
    type: str  # BL, SL, SSO, BSC
    qty: Decimal  # Number of contracts
    price: Decimal  # Price per share
    date: str
    currency: str = "EUR"
    notes_codes: str = ""


@dataclass
class StockTradeSpec:
    """Parsed stock trade from YAML spec (for linked trades)."""
    type: str  # BL, SL, SSO, BSC
    qty: Decimal  # Number of shares
    price: Decimal
    date: str
    currency: str = "EUR"
    notes_codes: str = ""


@dataclass
class OptionSpec:
    """Option contract specification."""
    type: str  # C or P
    strike: Decimal
    expiry: str
    multiplier: Decimal = Decimal("100")


@dataclass
class UnderlyingSpec:
    """Underlying asset specification."""
    symbol: str
    isin: str
    conid: str


@dataclass
class OptionTestSpec:
    """A single option test case parsed from YAML."""
    id: str
    description: str
    underlying: UnderlyingSpec
    option: OptionSpec
    option_trades: List[OptionTradeSpec]
    expected_rgls: List[ExpectedRGLSpec]
    option_eoy_quantity: Decimal
    stock_eoy_quantity: Decimal
    expected_errors: int
    notes: Optional[str] = None
    stock_trades: Optional[List[StockTradeSpec]] = None
    positions_soy: Optional[PositionSpec] = None  # For underlying stock


@dataclass
class FifoTestSpec:
    """A single FIFO test case parsed from YAML."""
    id: str
    description: str
    asset_symbol: str
    asset_isin: str
    asset_category: str
    intra_year_trades: List[TradeSpec]
    expected_rgls: List[ExpectedRGLSpec]
    expected_eoy_quantity: Decimal
    expected_errors: int
    variations: List[Dict[str, Any]]
    notes: Optional[str] = None
    positions_soy: Optional[PositionSpec] = None
    historical_trades: Optional[List[TradeSpec]] = None
    # EOY reconciliation fields (Option B implementation)
    positions_eoy_report: Optional[PositionSpec] = None  # Broker-reported EOY position (input)
    expected_calculated_eoy: Optional[Decimal] = None    # Expected engine calculation (documentation)


def _decimal_constructor(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> Decimal:
    """YAML constructor for Decimal values."""
    value = loader.construct_scalar(node)
    return Decimal(str(value))


def _parse_trade(trade_dict: Dict) -> TradeSpec:
    """Parse a trade dictionary into TradeSpec."""
    return TradeSpec(
        type=trade_dict["type"],
        qty=Decimal(str(trade_dict["qty"])),
        price=Decimal(str(trade_dict["price"])),
        date=trade_dict.get("date", ""),
        asset=trade_dict.get("asset"),
        currency=trade_dict.get("currency", "EUR"),
        time=trade_dict.get("time"),
    )


def _parse_position(pos_dict: Optional[Dict]) -> Optional[PositionSpec]:
    """Parse a position dictionary into PositionSpec."""
    if not pos_dict:
        return None
    return PositionSpec(
        quantity=Decimal(str(pos_dict["quantity"])),
        cost_basis=Decimal(str(pos_dict["cost_basis"])) if "cost_basis" in pos_dict else None,
        currency=pos_dict.get("currency", "EUR"),
    )


def _parse_expected_rgl(rgl_dict: Dict) -> ExpectedRGLSpec:
    """Parse an expected RGL dictionary into ExpectedRGLSpec."""
    return ExpectedRGLSpec(
        realization_type=rgl_dict["realization_type"],
        quantity=Decimal(str(rgl_dict["quantity"])) if "quantity" in rgl_dict else None,
        acquisition_date=rgl_dict.get("acquisition_date"),
        realization_date=rgl_dict.get("realization_date"),
        total_cost_basis_eur=Decimal(str(rgl_dict["total_cost_basis_eur"])) if "total_cost_basis_eur" in rgl_dict else None,
        total_proceeds_eur=Decimal(str(rgl_dict["total_proceeds_eur"])) if "total_proceeds_eur" in rgl_dict else None,
        gain_loss_eur=Decimal(str(rgl_dict["gain_loss_eur"])) if "gain_loss_eur" in rgl_dict else None,
        tax_category=rgl_dict.get("tax_category"),
        asset=rgl_dict.get("asset"),
    )


def load_yaml_spec(filename: str) -> Dict[str, Any]:
    """
    Load a YAML test specification file.

    Args:
        filename: Name of the YAML file in the fixtures directory

    Returns:
        Parsed YAML content as a dictionary
    """
    filepath = FIXTURES_DIR / filename

    # Register Decimal constructor for numeric values
    yaml.add_constructor("!decimal", _decimal_constructor, Loader=yaml.SafeLoader)

    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_fifo_tests(spec_data: Dict[str, Any]) -> List[FifoTestSpec]:
    """
    Parse FIFO test specifications from loaded YAML.

    Args:
        spec_data: Loaded YAML dictionary

    Returns:
        List of FifoTestSpec objects
    """
    tests = []
    metadata = spec_data.get("metadata", {})

    for test_dict in spec_data.get("tests", []):
        inputs = test_dict.get("inputs", {})
        expected = test_dict.get("expected", {})

        # Handle single asset or multiple assets
        asset = inputs.get("asset", {})
        if not asset and "assets" in inputs:
            asset = inputs["assets"][0]  # Use first asset for single-asset compat

        # Parse trades
        trades = []
        for trade in inputs.get("intra_year_trades", []):
            trades.append(_parse_trade(trade))

        # Parse historical trades
        hist_trades = None
        if inputs.get("historical_trades"):
            hist_trades = [_parse_trade(t) for t in inputs["historical_trades"]]

        # Parse expected RGLs
        rgls = []
        for rgl in expected.get("rgls", []):
            rgls.append(_parse_expected_rgl(rgl))

        # Handle EOY state
        eoy_state = expected.get("eoy_state", expected.get("eoy_states", [{}])[0] if "eoy_states" in expected else {})
        eoy_qty = eoy_state.get("quantity", 0)

        # Parse SOY position
        soy_pos = _parse_position(inputs.get("positions_soy"))

        # Parse EOY report position (broker-reported, used as input for reconciliation)
        eoy_report_pos = _parse_position(inputs.get("positions_eoy_report"))

        # Parse expected calculated EOY (optional, for documentation of mismatch tests)
        expected_calc_eoy = expected.get("calculated_eoy_quantity")
        expected_calc_eoy_decimal = Decimal(str(expected_calc_eoy)) if expected_calc_eoy is not None else None

        tests.append(FifoTestSpec(
            id=test_dict["id"],
            description=test_dict["description"],
            asset_symbol=asset.get("symbol", ""),
            asset_isin=asset.get("isin", ""),
            asset_category=asset.get("category", "STOCK"),
            intra_year_trades=trades,
            expected_rgls=rgls,
            expected_eoy_quantity=Decimal(str(eoy_qty)),
            expected_errors=expected.get("errors", 0),
            variations=test_dict.get("variations", []),
            notes=test_dict.get("notes"),
            positions_soy=soy_pos,
            historical_trades=hist_trades,
            positions_eoy_report=eoy_report_pos,
            expected_calculated_eoy=expected_calc_eoy_decimal,
        ))

    return tests


def get_group1_core_fifo_tests() -> List[FifoTestSpec]:
    """Load and parse Group 1: Core FIFO Mechanics test specifications."""
    spec_data = load_yaml_spec("group1_core_fifo.yaml")
    return parse_fifo_tests(spec_data)


def get_group2_soy_handling_tests() -> List[FifoTestSpec]:
    """Load and parse Group 2: SOY Handling test specifications."""
    spec_data = load_yaml_spec("group2_soy_handling.yaml")
    return parse_fifo_tests(spec_data)


def get_group3_eoy_validation_tests() -> List[FifoTestSpec]:
    """Load and parse Group 3: EOY Validation test specifications."""
    spec_data = load_yaml_spec("group3_eoy_validation.yaml")
    return parse_fifo_tests(spec_data)


def get_group4_multi_year_tests() -> List[FifoTestSpec]:
    """Load and parse Group 4: Multi-Year test specifications."""
    spec_data = load_yaml_spec("group4_multi_year.yaml")
    return parse_fifo_tests(spec_data)


def get_group5_complex_sequences_tests() -> List[FifoTestSpec]:
    """Load and parse Group 5: Complex Sequences test specifications."""
    spec_data = load_yaml_spec("group5_complex_sequences.yaml")
    return parse_fifo_tests(spec_data)


# =============================================================================
# Option test parsing functions
# =============================================================================

def _parse_option_trade(trade_dict: Dict) -> OptionTradeSpec:
    """Parse an option trade dictionary into OptionTradeSpec."""
    return OptionTradeSpec(
        type=trade_dict["type"],
        qty=Decimal(str(trade_dict["qty"])),
        price=Decimal(str(trade_dict["price"])),
        date=trade_dict.get("date", ""),
        currency=trade_dict.get("currency", "EUR"),
        notes_codes=trade_dict.get("notes_codes", ""),
    )


def _parse_stock_trade(trade_dict: Dict) -> StockTradeSpec:
    """Parse a stock trade dictionary into StockTradeSpec."""
    return StockTradeSpec(
        type=trade_dict["type"],
        qty=Decimal(str(trade_dict["qty"])),
        price=Decimal(str(trade_dict["price"])),
        date=trade_dict.get("date", ""),
        currency=trade_dict.get("currency", "EUR"),
        notes_codes=trade_dict.get("notes_codes", ""),
    )


def _parse_option_spec(option_dict: Dict) -> OptionSpec:
    """Parse an option specification dictionary."""
    return OptionSpec(
        type=option_dict["type"],
        strike=Decimal(str(option_dict["strike"])),
        expiry=option_dict["expiry"],
        multiplier=Decimal(str(option_dict.get("multiplier", "100"))),
    )


def _parse_underlying_spec(underlying_dict: Dict) -> UnderlyingSpec:
    """Parse an underlying asset specification dictionary."""
    return UnderlyingSpec(
        symbol=underlying_dict["symbol"],
        isin=underlying_dict["isin"],
        conid=str(underlying_dict["conid"]),
    )


def _parse_option_expected_rgl(rgl_dict: Dict) -> ExpectedRGLSpec:
    """Parse an expected RGL dictionary for options."""
    return ExpectedRGLSpec(
        realization_type=rgl_dict["realization_type"],
        quantity=Decimal(str(rgl_dict["quantity"])) if "quantity" in rgl_dict else None,
        acquisition_date=rgl_dict.get("acquisition_date"),
        realization_date=rgl_dict.get("realization_date"),
        total_cost_basis_eur=Decimal(str(rgl_dict["total_cost_basis_eur"])) if "total_cost_basis_eur" in rgl_dict else None,
        total_proceeds_eur=Decimal(str(rgl_dict["total_proceeds_eur"])) if "total_proceeds_eur" in rgl_dict else None,
        gain_loss_eur=Decimal(str(rgl_dict["gain_loss_eur"])) if "gain_loss_eur" in rgl_dict else None,
        tax_category=rgl_dict.get("tax_category"),
        asset=rgl_dict.get("asset"),
        is_stillhalter_income=rgl_dict.get("is_stillhalter_income"),
    )


def parse_option_tests(spec_data: Dict[str, Any]) -> List[OptionTestSpec]:
    """
    Parse option test specifications from loaded YAML.

    Args:
        spec_data: Loaded YAML dictionary

    Returns:
        List of OptionTestSpec objects
    """
    tests = []

    for test_dict in spec_data.get("tests", []):
        inputs = test_dict.get("inputs", {})
        expected = test_dict.get("expected", {})

        # Parse underlying and option specs
        underlying = _parse_underlying_spec(inputs.get("underlying", {}))
        option = _parse_option_spec(inputs.get("option", {}))

        # Parse option trades
        option_trades = []
        for trade in inputs.get("option_trades", []):
            option_trades.append(_parse_option_trade(trade))

        # Parse stock trades (for exercise/assignment)
        stock_trades = None
        if inputs.get("stock_trades"):
            stock_trades = [_parse_stock_trade(t) for t in inputs["stock_trades"]]

        # Parse SOY position (for underlying stock)
        soy_pos = _parse_position(inputs.get("positions_soy"))

        # Parse expected RGLs
        rgls = []
        for rgl in expected.get("rgls", []):
            rgls.append(_parse_option_expected_rgl(rgl))

        # Get EOY quantities
        option_eoy_qty = expected.get("option_eoy_quantity", 0)
        stock_eoy_qty = expected.get("stock_eoy_quantity", 0)

        tests.append(OptionTestSpec(
            id=test_dict["id"],
            description=test_dict["description"],
            underlying=underlying,
            option=option,
            option_trades=option_trades,
            expected_rgls=rgls,
            option_eoy_quantity=Decimal(str(option_eoy_qty)),
            stock_eoy_quantity=Decimal(str(stock_eoy_qty)),
            expected_errors=expected.get("errors", 0),
            notes=test_dict.get("notes"),
            stock_trades=stock_trades,
            positions_soy=soy_pos,
        ))

    return tests


def get_group8_options_tests() -> List[OptionTestSpec]:
    """Load and parse Group 8: Options Lifecycle test specifications."""
    spec_data = load_yaml_spec("group8_options.yaml")
    return parse_option_tests(spec_data)


# =============================================================================
# Currency FIFO dataclasses (Group 7)
# =============================================================================

@dataclass
class FxTradeSpec:
    """
    Parsed explicit FX trade from YAML spec.

    Represents a currency conversion: EUR ↔ Foreign currency.
    """
    type: str  # BUY (EUR→Foreign), SELL (Foreign→EUR), or CROSS_CURRENCY
    date: str
    foreign_amount: Decimal
    eur_amount: Decimal
    ecb_rate: Optional[Decimal]  # Foreign currency per EUR (for from_currency in cross-currency); None = missing rate
    time: Optional[str] = None
    foreign_currency: Optional[str] = None  # The non-EUR currency (USD, GBP, etc.)
    # Cross-currency fields
    to_currency: Optional[str] = None  # Target currency for cross-currency trades
    ecb_rate_to: Optional[Decimal] = None  # ECB rate for target currency


@dataclass
class SecurityTradeForFxSpec:
    """
    Parsed security trade that causes implicit FX movement.

    When buying/selling securities in foreign currency, the currency
    balance changes implicitly, potentially triggering FX gains/losses.
    """
    type: str  # BUY_LONG, SELL_LONG, etc.
    date: str
    asset_symbol: str
    asset_isin: str
    quantity: Decimal
    price_foreign: Decimal  # Price per share in local_currency
    local_currency: str  # Currency the trade settles in (e.g., USD)
    ecb_rate: Decimal  # local_currency per EUR
    time: Optional[str] = None


@dataclass
class CurrencyPositionSpec:
    """
    Currency position specification (SOY or EOY).

    Supports both long positions (positive balance) and
    short positions (negative balance).
    """
    currency: str
    balance: Decimal
    cost_basis_eur: Optional[Decimal] = None  # For long positions
    acquisition_date: Optional[str] = None  # For long positions
    short_proceeds_eur: Optional[Decimal] = None  # For short positions
    short_opening_date: Optional[str] = None  # For short positions
    fallback_ecb_rate: Optional[Decimal] = None  # When no historical data


@dataclass
class ExpectedCurrencyRGLSpec:
    """
    Expected currency RGL from YAML spec.

    Similar to ExpectedRGLSpec but with currency-specific fields.
    """
    realization_type: str  # FX_CONVERSION_SALE, FX_CONVERSION_SHORT_COVER, FX_IMPLICIT_*
    currency: str
    quantity: Decimal
    acquisition_date: Optional[str] = None
    realization_date: Optional[str] = None
    total_cost_basis_eur: Optional[Decimal] = None
    total_proceeds_eur: Optional[Decimal] = None
    gain_loss_eur: Optional[Decimal] = None
    tax_category: Optional[str] = None


@dataclass
class ExpectedCurrencyEoyState:
    """Expected EOY state for a currency position."""
    currency: str
    quantity: Decimal
    # Lot details are optional - for documentation/debugging
    lots: Optional[List[Dict[str, Any]]] = None
    short_lots: Optional[List[Dict[str, Any]]] = None


@dataclass
class ExpectedAggregates:
    """
    Expected tax form aggregates.

    Kept separate from RGLs for clean separation between
    unit testing (RGLs) and integration testing (aggregates).
    """
    kap_other_income: Decimal = Decimal("0")
    kap_other_losses: Decimal = Decimal("0")


@dataclass
class CurrencyFifoTestSpec:
    """
    A single currency FIFO test case parsed from YAML.

    Supports:
    - Explicit FX trades (EUR ↔ Foreign)
    - Implicit FX from security trades
    - Long and short currency positions
    - Cross-currency trades
    - Multi-currency portfolios
    """
    id: str
    description: str
    # Currency positions (supports multi-currency)
    currency_positions_soy: List[CurrencyPositionSpec]
    # Trade inputs
    fx_trades: List[FxTradeSpec]
    security_trades: List[SecurityTradeForFxSpec]
    # Expected outputs
    expected_rgls: List[ExpectedCurrencyRGLSpec]
    expected_eoy_states: List[ExpectedCurrencyEoyState]
    expected_aggregates: ExpectedAggregates
    expected_errors: int
    expected_warnings: int
    # Documentation
    notes: Optional[str] = None
    # Whether rgls were explicitly specified in YAML (even if empty list)
    has_explicit_rgl_expectations: bool = True
    # Whether the pipeline is expected to raise an error (e.g., DataIntegrityError)
    expect_pipeline_error: bool = False
    # Skip flag for tests that test unimplemented features
    skip: bool = False
    skip_reason: Optional[str] = None


# =============================================================================
# Currency FIFO parsing functions
# =============================================================================

def _parse_fx_trade(trade_dict: Dict) -> FxTradeSpec:
    """Parse an FX trade dictionary into FxTradeSpec.

    Supports two formats:
    1. New simplified format:
       type: BUY/SELL, foreign_amount, eur_amount, ecb_rate

    2. Legacy format:
       type: BUY_FOREIGN/SELL_FOREIGN, from_currency, from_amount, to_currency, to_amount, ecb_rate
       For cross-currency: ecb_rate_from, ecb_rate_to instead of ecb_rate
    """
    trade_type = trade_dict["type"]
    date = trade_dict["date"]
    time = trade_dict.get("time")

    # Handle ECB rate - support both single rate and separate from/to rates
    if "ecb_rate" in trade_dict and trade_dict["ecb_rate"] is not None:
        ecb_rate = Decimal(str(trade_dict["ecb_rate"]))
    elif "ecb_rate_from" in trade_dict and trade_dict["ecb_rate_from"] is not None:
        # Cross-currency trade - use the "from" rate as the primary rate
        ecb_rate = Decimal(str(trade_dict["ecb_rate_from"]))
    elif "ecb_rate" in trade_dict and trade_dict["ecb_rate"] is None:
        ecb_rate = None  # Explicitly null - test missing rate scenario
    else:
        ecb_rate = Decimal("1.0")  # Default fallback when not specified

    # Check if using new simplified format
    if "foreign_amount" in trade_dict:
        # New format should also have foreign_currency
        foreign_currency = trade_dict.get("foreign_currency", trade_dict.get("currency"))
        return FxTradeSpec(
            type=trade_type,
            date=date,
            foreign_amount=Decimal(str(trade_dict["foreign_amount"])),
            eur_amount=Decimal(str(trade_dict["eur_amount"])),
            ecb_rate=ecb_rate,
            time=time,
            foreign_currency=foreign_currency,
        )

    # Legacy format with from_currency/to_currency
    from_currency = trade_dict.get("from_currency", "")
    to_currency = trade_dict.get("to_currency", "")
    from_amount = Decimal(str(trade_dict.get("from_amount", "0")))
    to_amount = Decimal(str(trade_dict.get("to_amount", "0")))

    # Determine which is EUR and which is foreign
    if from_currency == "EUR":
        # Selling EUR to buy foreign (BUY foreign)
        eur_amount = from_amount
        foreign_amount = to_amount
        normalized_type = "BUY"
        foreign_currency = to_currency
    elif to_currency == "EUR":
        # Selling foreign to buy EUR (SELL foreign)
        foreign_amount = from_amount
        eur_amount = to_amount
        normalized_type = "SELL"
        foreign_currency = from_currency
    else:
        # Cross-currency trade (neither is EUR)
        foreign_amount = from_amount
        eur_amount = to_amount
        normalized_type = "CROSS_CURRENCY"
        foreign_currency = from_currency
        to_currency_val = to_currency
        ecb_rate_to_val = Decimal(str(trade_dict["ecb_rate_to"])) if "ecb_rate_to" in trade_dict else None

        return FxTradeSpec(
            type=normalized_type,
            date=date,
            foreign_amount=foreign_amount,
            eur_amount=eur_amount,
            ecb_rate=ecb_rate,
            time=time,
            foreign_currency=foreign_currency,
            to_currency=to_currency_val,
            ecb_rate_to=ecb_rate_to_val,
        )

    return FxTradeSpec(
        type=normalized_type,
        date=date,
        foreign_amount=foreign_amount,
        eur_amount=eur_amount,
        ecb_rate=ecb_rate,
        time=time,
        foreign_currency=foreign_currency,
    )


def _parse_security_trade_for_fx(trade_dict: Dict) -> SecurityTradeForFxSpec:
    """Parse a security trade dictionary for FX purposes."""
    return SecurityTradeForFxSpec(
        type=trade_dict["type"],
        date=trade_dict["date"],
        asset_symbol=trade_dict["asset_symbol"],
        asset_isin=trade_dict["asset_isin"],
        quantity=Decimal(str(trade_dict["quantity"])),
        price_foreign=Decimal(str(trade_dict["price_foreign"])),
        local_currency=trade_dict["local_currency"],
        ecb_rate=Decimal(str(trade_dict["ecb_rate"])),
        time=trade_dict.get("time"),
    )


def _parse_currency_position(pos_dict: Dict) -> CurrencyPositionSpec:
    """Parse a currency position dictionary using 'balance' key format."""
    return CurrencyPositionSpec(
        currency=pos_dict["currency"],
        balance=Decimal(str(pos_dict["balance"])),
        cost_basis_eur=Decimal(str(pos_dict["cost_basis_eur"])) if pos_dict.get("cost_basis_eur") else None,
        acquisition_date=pos_dict.get("acquisition_date"),
        short_proceeds_eur=Decimal(str(pos_dict["short_proceeds_eur"])) if pos_dict.get("short_proceeds_eur") else None,
        short_opening_date=pos_dict.get("short_opening_date"),
        fallback_ecb_rate=Decimal(str(pos_dict["fallback_ecb_rate"])) if pos_dict.get("fallback_ecb_rate") else None,
    )


def _parse_soy_currency_position(pos_dict: Dict) -> CurrencyPositionSpec:
    """Parse a SOY currency position dictionary using 'soy_balance' key format.

    This is for the 'currencies:' YAML format which uses soy_* prefixed keys
    to explicitly denote Start-of-Year validation points.
    """
    return CurrencyPositionSpec(
        currency=pos_dict["currency"],
        balance=Decimal(str(pos_dict.get("soy_balance", "0"))),
        cost_basis_eur=Decimal(str(pos_dict["soy_cost_basis_eur"])) if pos_dict.get("soy_cost_basis_eur") else None,
        acquisition_date=pos_dict.get("soy_acquisition_date"),
        short_proceeds_eur=Decimal(str(pos_dict["soy_short_proceeds_eur"])) if pos_dict.get("soy_short_proceeds_eur") else None,
        short_opening_date=pos_dict.get("soy_short_opening_date"),
        fallback_ecb_rate=Decimal(str(pos_dict["soy_fallback_ecb_rate"])) if pos_dict.get("soy_fallback_ecb_rate") else None,
    )


def _parse_currency_rgl(rgl_dict: Dict) -> ExpectedCurrencyRGLSpec:
    """Parse an expected currency RGL dictionary."""
    return ExpectedCurrencyRGLSpec(
        realization_type=rgl_dict["realization_type"],
        currency=rgl_dict["currency"],
        quantity=Decimal(str(rgl_dict["quantity"])),
        acquisition_date=rgl_dict.get("acquisition_date"),
        realization_date=rgl_dict.get("realization_date"),
        total_cost_basis_eur=Decimal(str(rgl_dict["total_cost_basis_eur"])) if rgl_dict.get("total_cost_basis_eur") else None,
        total_proceeds_eur=Decimal(str(rgl_dict["total_proceeds_eur"])) if rgl_dict.get("total_proceeds_eur") else None,
        gain_loss_eur=Decimal(str(rgl_dict["gain_loss_eur"])) if rgl_dict.get("gain_loss_eur") else None,
        tax_category=rgl_dict.get("tax_category"),
    )


def _parse_currency_eoy_state(state_dict: Dict) -> ExpectedCurrencyEoyState:
    """Parse expected EOY state for a currency."""
    return ExpectedCurrencyEoyState(
        currency=state_dict["currency"],
        quantity=Decimal(str(state_dict["quantity"])),
        lots=state_dict.get("lots"),
        short_lots=state_dict.get("short_lots"),
    )


def _parse_aggregates(agg_dict: Optional[Dict]) -> ExpectedAggregates:
    """Parse expected aggregates dictionary."""
    if not agg_dict:
        return ExpectedAggregates()
    return ExpectedAggregates(
        kap_other_income=Decimal(str(agg_dict.get("kap_other_income", "0"))),
        kap_other_losses=Decimal(str(agg_dict.get("kap_other_losses", "0"))),
    )


def parse_currency_fifo_tests(spec_data: Dict[str, Any]) -> List[CurrencyFifoTestSpec]:
    """
    Parse currency FIFO test specifications from loaded YAML.

    Args:
        spec_data: Loaded YAML dictionary

    Returns:
        List of CurrencyFifoTestSpec objects
    """
    tests = []

    for test_dict in spec_data.get("tests", []):
        inputs = test_dict.get("inputs", {})
        expected = test_dict.get("expected", {})

        # Parse currency positions (SOY)
        soy_positions = []
        # Support both single currency and multi-currency formats
        if "currency_positions" in inputs:
            for pos in inputs["currency_positions"]:
                soy_positions.append(_parse_currency_position(pos))
        elif "currencies" in inputs:
            # Multi-currency SOY format using 'currencies:' key with soy_* prefixed fields
            for pos in inputs["currencies"]:
                soy_positions.append(_parse_soy_currency_position(pos))
        elif "currency" in inputs:
            # Legacy single-currency format
            soy_positions.append(CurrencyPositionSpec(
                currency=inputs["currency"],
                balance=Decimal(str(inputs.get("soy_balance", "0"))),
                cost_basis_eur=Decimal(str(inputs["soy_cost_basis_eur"])) if inputs.get("soy_cost_basis_eur") else None,
                acquisition_date=inputs.get("soy_acquisition_date"),
                short_proceeds_eur=Decimal(str(inputs["soy_short_proceeds_eur"])) if inputs.get("soy_short_proceeds_eur") else None,
                short_opening_date=inputs.get("soy_short_opening_date"),
                fallback_ecb_rate=Decimal(str(inputs["soy_fallback_ecb_rate"])) if inputs.get("soy_fallback_ecb_rate") else None,
            ))

        # Parse FX trades
        fx_trades = []
        for trade in inputs.get("fx_trades", []):
            fx_trades.append(_parse_fx_trade(trade))

        # Parse security trades
        security_trades = []
        for trade in inputs.get("security_trades", []):
            security_trades.append(_parse_security_trade_for_fx(trade))

        # Parse expected RGLs (support both 'rgls' and 'currency_rgls' keys)
        rgls = []
        has_explicit_rgl_expectations = "rgls" in expected or "currency_rgls" in expected
        rgl_list = expected.get("rgls", expected.get("currency_rgls", []))
        for rgl in rgl_list:
            rgls.append(_parse_currency_rgl(rgl))

        # Parse expected EOY states
        eoy_states = []
        if "eoy_states" in expected:
            for state in expected["eoy_states"]:
                eoy_states.append(_parse_currency_eoy_state(state))
        elif "eoy_state" in expected:
            # Single currency EOY state
            eoy_state = expected["eoy_state"]
            # Derive currency from SOY positions or first RGL
            currency = soy_positions[0].currency if soy_positions else (rgls[0].currency if rgls else "USD")
            eoy_states.append(ExpectedCurrencyEoyState(
                currency=currency,
                quantity=Decimal(str(eoy_state.get("quantity", "0"))),
                lots=eoy_state.get("lots"),
                short_lots=eoy_state.get("short_lots"),
            ))
        elif inputs.get("eoy_balance_expected") is not None:
            # Legacy format
            currency = soy_positions[0].currency if soy_positions else "USD"
            eoy_states.append(ExpectedCurrencyEoyState(
                currency=currency,
                quantity=Decimal(str(inputs["eoy_balance_expected"])),
            ))

        # Parse aggregates
        aggregates = _parse_aggregates(expected.get("aggregates"))
        # Also support legacy format
        if "kap_other_income_positive" in expected:
            aggregates = ExpectedAggregates(
                kap_other_income=Decimal(str(expected.get("kap_other_income_positive", "0"))),
                kap_other_losses=Decimal(str(expected.get("kap_other_losses_abs", "0"))),
            )

        tests.append(CurrencyFifoTestSpec(
            id=test_dict["id"],
            description=test_dict["description"],
            currency_positions_soy=soy_positions,
            fx_trades=fx_trades,
            security_trades=security_trades,
            expected_rgls=rgls,
            expected_eoy_states=eoy_states,
            expected_aggregates=aggregates,
            expected_errors=expected.get("errors", 0),
            expected_warnings=expected.get("warnings", 0),
            has_explicit_rgl_expectations=has_explicit_rgl_expectations,
            notes=test_dict.get("notes"),
            expect_pipeline_error=test_dict.get("expect_pipeline_error", False),
            skip=test_dict.get("skip", False),
            skip_reason=test_dict.get("skip_reason"),
        ))

    return tests


def get_group7_currency_fifo_tests() -> List[CurrencyFifoTestSpec]:
    """Load and parse Group 7: Currency FIFO test specifications."""
    spec_data = load_yaml_spec("group7_currency_fifo.yaml")
    return parse_currency_fifo_tests(spec_data)

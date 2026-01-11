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

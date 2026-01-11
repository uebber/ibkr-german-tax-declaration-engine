# tests/support/expected.py
from typing import List, Dict, Optional, Any
from decimal import Decimal
from uuid import UUID

# Domain specific enums and classes for type hints and comparisons
from src.domain.results import RealizedGainLoss
from src.domain.assets import Asset # For type hint of actual_asset
from src.domain.enums import AssetCategory, TaxReportingCategory, InvestmentFundType, RealizationType
from src.identification.asset_resolver import AssetResolver # For type hint
# Import config to access OUTPUT_PRECISION_AMOUNTS
from src import config as app_config

class ExpectedRealizedGainLoss:
    """
    Represents the expected outcome for a single RealizedGainLoss record.
    Uses asset_identifier (e.g., ISIN or Symbol) for easier identification in tests.
    The actual RGL object will use asset_internal_id. Tests will need to map this.
    """
    asset_identifier: str
    realization_date: str
    quantity_realized: Decimal
    total_cost_basis_eur: Decimal # CHANGED from total_cost_basis_eur_realized
    total_realization_value_eur: Decimal
    gross_gain_loss_eur: Decimal
    
    additional_fields: Dict[str, Any]

    def __init__(self,
                 asset_identifier: str,
                 realization_date: str,
                 quantity_realized: Decimal,
                 total_cost_basis_eur: Decimal, # CHANGED: Parameter name updated
                 total_realization_value_eur: Decimal,
                 gross_gain_loss_eur: Decimal,
                 **kwargs: Any):
        self.asset_identifier = asset_identifier
        self.realization_date = realization_date
        self.quantity_realized = quantity_realized
        
        self.total_cost_basis_eur = total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) # CHANGED: Instance variable name updated
        self.total_realization_value_eur = total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
        self.gross_gain_loss_eur = gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
        
        self.additional_fields = {}
        for key, value in kwargs.items():
            if isinstance(value, Decimal):
                self.additional_fields[key] = value.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
            else:
                self.additional_fields[key] = value

    def __repr__(self) -> str:
        return (f"ExpectedRGL(identifier={self.asset_identifier}, date={self.realization_date}, "
                f"qty={self.quantity_realized}, cost_eur={self.total_cost_basis_eur}, " # CHANGED: Instance variable in repr updated
                f"proceeds_eur={self.total_realization_value_eur}, gain_eur={self.gross_gain_loss_eur}, " 
                f"add_fields_count={len(self.additional_fields)})")

    def matches(self, actual_rgl: RealizedGainLoss, asset_resolver: AssetResolver) -> bool:
        asset = asset_resolver.get_asset_by_id(actual_rgl.asset_internal_id)
        if not asset:
            print(f"Asset ID {actual_rgl.asset_internal_id} not found in resolver for RGL.")
            return False

        identifier_type, identifier_value = self.asset_identifier.split(":", 1) if ":" in self.asset_identifier else ("SYMBOL", self.asset_identifier)
        
        asset_matched = False
        if identifier_type == "ISIN" and asset.ibkr_isin == identifier_value:
            asset_matched = True
        elif identifier_type == "CONID" and asset.ibkr_conid == identifier_value:
            asset_matched = True
        elif identifier_type == "SYMBOL":
            if asset.ibkr_symbol == identifier_value: asset_matched = True
            elif any(alias == f"SYMBOL:{identifier_value}" for alias in asset.aliases): asset_matched = True

        if not asset_matched and str(actual_rgl.asset_internal_id) == self.asset_identifier:
            asset_matched = True
        
        if not asset_matched:
            print(f"Asset identifier mismatch: expected '{self.asset_identifier}', "
                  f"actual asset (ID: {asset.internal_asset_id}) has ISIN '{asset.ibkr_isin}', "
                  f"ConID '{asset.ibkr_conid}', Symbol '{asset.ibkr_symbol}', Aliases '{asset.aliases}'.")
            return False

        date_match = str(actual_rgl.realization_date) == self.realization_date
        qty_match = actual_rgl.quantity_realized.compare(self.quantity_realized) == Decimal("0")
        
        actual_cost_quantized = actual_rgl.total_cost_basis_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
        actual_proceeds_quantized = actual_rgl.total_realization_value_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
        actual_gain_quantized = actual_rgl.gross_gain_loss_eur.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)

        # Comparison now correctly uses self.total_cost_basis_eur which holds the expected value
        cost_match = actual_cost_quantized.compare(self.total_cost_basis_eur) == Decimal("0")
        proceeds_match = actual_proceeds_quantized.compare(self.total_realization_value_eur) == Decimal("0")
        gain_match = actual_gain_quantized.compare(self.gross_gain_loss_eur) == Decimal("0")

        if not all([date_match, qty_match, cost_match, proceeds_match, gain_match]):
            print(f"Core RGL field mismatch for asset '{self.asset_identifier}' on {self.realization_date}:")
            if not date_match: print(f"  Date: expected {self.realization_date}, got {actual_rgl.realization_date}")
            if not qty_match: print(f"  Qty: expected {self.quantity_realized}, got {actual_rgl.quantity_realized}")
            if not cost_match: print(f"  Cost: expected {self.total_cost_basis_eur}, got {actual_cost_quantized} (orig: {actual_rgl.total_cost_basis_eur})")
            if not proceeds_match: print(f"  Proceeds: expected {self.total_realization_value_eur}, got {actual_proceeds_quantized} (orig: {actual_rgl.total_realization_value_eur})")
            if not gain_match: print(f"  Gain: expected {self.gross_gain_loss_eur}, got {actual_gain_quantized} (orig: {actual_rgl.gross_gain_loss_eur})")
            return False

        for field_name, expected_value in self.additional_fields.items():
            actual_value = getattr(actual_rgl, field_name, None)
            
            if isinstance(expected_value, Decimal):
                actual_decimal_quantized = actual_value.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) if isinstance(actual_value, Decimal) else None
                if not isinstance(actual_decimal_quantized, Decimal) or actual_decimal_quantized.compare(expected_value) != Decimal("0"):
                    print(f"  RGL Decimal field '{field_name}' mismatch: expected {expected_value}, got {actual_decimal_quantized} (orig: {actual_value})")
                    return False
            elif isinstance(expected_value, str) and hasattr(actual_value, 'name'): 
                 if expected_value != actual_value.name:
                    print(f"  RGL Enum field '{field_name}' mismatch: expected '{expected_value}', got '{actual_value.name}'")
                    return False
            elif isinstance(expected_value, bool) and isinstance(actual_value, bool):
                if expected_value != actual_value:
                    print(f"  RGL Bool field '{field_name}' mismatch: expected {expected_value}, got {actual_value}")
                    return False
            elif expected_value is None and actual_value is None:
                continue
            elif actual_value != expected_value:
                print(f"  RGL Field '{field_name}' mismatch: expected '{expected_value}' (type {type(expected_value)}), got '{actual_value}' (type {type(actual_value)})")
                return False
        return True

class ExpectedAssetEoyState:
    """Represents the expected end-of-year state for a specific asset."""
    asset_identifier: str
    eoy_quantity: Decimal
    additional_fields: Dict[str, Any]

    def __init__(self,
                 asset_identifier: str,
                 eoy_quantity: Decimal,
                 **kwargs: Any):
        self.asset_identifier = asset_identifier
        self.eoy_quantity = eoy_quantity
        
        self.additional_fields = {}
        for key, value in kwargs.items():
            if isinstance(value, Decimal):
                self.additional_fields[key] = value.quantize(app_config.OUTPUT_PRECISION_AMOUNTS)
            else:
                self.additional_fields[key] = value

    def __repr__(self) -> str:
        return f"ExpectedEoyState(identifier={self.asset_identifier}, qty={self.eoy_quantity})"

    def matches(self, actual_asset: Asset) -> bool:
        identifier_type, identifier_value = self.asset_identifier.split(":", 1) if ":" in self.asset_identifier else ("SYMBOL", self.asset_identifier)
        asset_matched = False
        if identifier_type == "ISIN" and actual_asset.ibkr_isin == identifier_value:
            asset_matched = True
        elif identifier_type == "CONID" and actual_asset.ibkr_conid == identifier_value:
            asset_matched = True
        elif identifier_type == "SYMBOL":
            if actual_asset.ibkr_symbol == identifier_value: asset_matched = True
            elif any(alias == f"SYMBOL:{identifier_value}" for alias in actual_asset.aliases): asset_matched = True
        
        if not asset_matched and str(actual_asset.internal_asset_id) == self.asset_identifier:
            asset_matched = True

        if not asset_matched:
            print(f"EOY Asset identifier mismatch: expected '{self.asset_identifier}', "
                  f"actual asset (ID: {actual_asset.internal_asset_id}) has ISIN '{actual_asset.ibkr_isin}', "
                  f"ConID '{actual_asset.ibkr_conid}', Symbol '{actual_asset.ibkr_symbol}'.")
            return False

        actual_eoy_qty = actual_asset.eoy_quantity if actual_asset.eoy_quantity is not None else Decimal("0")
        qty_match = actual_eoy_qty.compare(self.eoy_quantity) == Decimal("0")

        if not qty_match:
            print(f"EOY Qty Mismatch for '{self.asset_identifier}': expected {self.eoy_quantity}, got {actual_asset.eoy_quantity}")
            return False

        for field_name, expected_value in self.additional_fields.items():
            actual_value = getattr(actual_asset, field_name, None)
            if isinstance(expected_value, Decimal):
                actual_decimal_quantized = actual_value.quantize(app_config.OUTPUT_PRECISION_AMOUNTS) if isinstance(actual_value, Decimal) else None
                if not isinstance(actual_decimal_quantized, Decimal) or actual_decimal_quantized.compare(expected_value) != Decimal("0"):
                    print(f"  EOY Decimal field '{field_name}' mismatch: expected {expected_value}, got {actual_decimal_quantized} (orig: {actual_value})")
                    return False
            elif isinstance(expected_value, str) and hasattr(actual_value, 'name'): 
                 if expected_value != actual_value.name:
                    print(f"  EOY Enum field '{field_name}' mismatch: expected '{expected_value}', got '{actual_value.name}'")
                    return False
            elif actual_value != expected_value:
                print(f"  EOY Field '{field_name}' mismatch: expected '{expected_value}', got '{actual_value}'")
                return False
        return True

class ScenarioExpectedOutput:
    """Encapsulates all expected outcomes for a FIFO-focused test case."""
    test_description: str
    expected_rgls: List[ExpectedRealizedGainLoss]
    expected_eoy_states: List[ExpectedAssetEoyState]
    expected_eoy_mismatch_error_count: int

    def __init__(self,
                 test_description: str,
                 expected_rgls: Optional[List[ExpectedRealizedGainLoss]] = None,
                 expected_eoy_states: Optional[List[ExpectedAssetEoyState]] = None,
                 expected_eoy_mismatch_error_count: int = 0):
        self.test_description = test_description
        self.expected_rgls = expected_rgls if expected_rgls is not None else []
        self.expected_eoy_states = expected_eoy_states if expected_eoy_states is not None else []
        self.expected_eoy_mismatch_error_count = expected_eoy_mismatch_error_count

    def __repr__(self) -> str:
        return (f"ScenarioExpectedOutput(desc='{self.test_description}', " 
                f"rgl_count={len(self.expected_rgls)}, "
                f"eoy_state_count={len(self.expected_eoy_states)}, "
                f"expected_errors={self.expected_eoy_mismatch_error_count})")

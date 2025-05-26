# src/domain/results.py
from dataclasses import dataclass, field, KW_ONLY
from decimal import Decimal
import uuid
from typing import Optional, Dict 
from collections import defaultdict

import logging 

from .enums import AssetCategory, TaxReportingCategory, InvestmentFundType, RealizationType
from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type
from src import config as global_config

logger = logging.getLogger(__name__)


@dataclass
class LossOffsettingResult:
    form_line_values: Dict[TaxReportingCategory | str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    conceptual_net_stocks: Decimal = Decimal('0')
    conceptual_net_other_income: Decimal = Decimal('0') 
    conceptual_net_derivatives_uncapped: Decimal = Decimal('0')
    conceptual_net_derivatives_capped: Decimal = Decimal('0')
    conceptual_net_p23_estg: Decimal = Decimal('0')
    conceptual_fund_income_net_taxable: Decimal = Decimal('0') 


@dataclass
class RealizedGainLoss:
    originating_event_id: uuid.UUID 
    asset_internal_id: uuid.UUID
    asset_category_at_realization: AssetCategory 
    acquisition_date: str 
    realization_date: str 
    
    realization_type: RealizationType 
    quantity_realized: Decimal 
    
    unit_cost_basis_eur: Decimal 
    unit_realization_value_eur: Decimal 
    
    total_cost_basis_eur: Decimal 
    total_realization_value_eur: Decimal 
    
    gross_gain_loss_eur: Decimal

    _: KW_ONLY
    holding_period_days: Optional[int] = None
    is_within_speculation_period: bool = False 
    is_taxable_under_section_23: bool = False # Changed default to False

    tax_reporting_category: Optional[TaxReportingCategory] = None 

    fund_type_at_sale: Optional[InvestmentFundType] = None 
    teilfreistellung_rate_applied: Optional[Decimal] = None 
    teilfreistellung_amount_eur: Optional[Decimal] = None 
    net_gain_loss_after_teilfreistellung_eur: Optional[Decimal] = None 

    is_stillhalter_income: bool = False 

    def __post_init__(self):
        if not isinstance(self.asset_category_at_realization, AssetCategory):
            raise TypeError(f"RealizedGainLoss.asset_category_at_realization must be an AssetCategory, got {type(self.asset_category_at_realization)}")
        if not isinstance(self.realization_type, RealizationType):
            raise TypeError(f"RealizedGainLoss.realization_type must be a RealizationType, got {type(self.realization_type)}")
        if self.tax_reporting_category is not None and not isinstance(self.tax_reporting_category, TaxReportingCategory):
            raise TypeError(f"RealizedGainLoss.tax_reporting_category must be a TaxReportingCategory, got {type(self.tax_reporting_category)}")
        if self.fund_type_at_sale is not None and not isinstance(self.fund_type_at_sale, InvestmentFundType):
            raise TypeError(f"RealizedGainLoss.fund_type_at_sale must be an InvestmentFundType, got {type(self.fund_type_at_sale)}")
        if not isinstance(self.quantity_realized, Decimal) or self.quantity_realized < Decimal(0):
            raise ValueError(f"RealizedGainLoss.quantity_realized must be a non-negative Decimal, got {self.quantity_realized}")

        # Handle §23 specifics
        if self.asset_category_at_realization == AssetCategory.PRIVATE_SALE_ASSET: 
            self.is_within_speculation_period = True 
            # is_taxable_under_section_23 is assumed to be correctly set by the constructor based on input.

        # Handle Investment Fund specifics (Teilfreistellung)
        if self.asset_category_at_realization == AssetCategory.INVESTMENT_FUND:
            # Always re-derive the rate based on the current fund_type_at_sale for idempotency.
            self.teilfreistellung_rate_applied = get_teilfreistellung_rate_for_fund_type(self.fund_type_at_sale)
            
            # Calculate Teilfreistellung amount
            if self.gross_gain_loss_eur is not None and self.teilfreistellung_rate_applied is not None:
                self.teilfreistellung_amount_eur = (self.gross_gain_loss_eur.copy_abs() * self.teilfreistellung_rate_applied).quantize(
                    global_config.OUTPUT_PRECISION_AMOUNTS,
                    rounding=global_config.DECIMAL_ROUNDING_MODE
                )
            else:
                self.teilfreistellung_amount_eur = Decimal('0.00')
            
            # Calculate net gain/loss after Teilfreistellung
            if self.gross_gain_loss_eur is not None: # self.teilfreistellung_amount_eur is now guaranteed to be set
                if self.gross_gain_loss_eur >= Decimal('0'):
                    self.net_gain_loss_after_teilfreistellung_eur = self.gross_gain_loss_eur - self.teilfreistellung_amount_eur
                else: 
                    self.net_gain_loss_after_teilfreistellung_eur = self.gross_gain_loss_eur + self.teilfreistellung_amount_eur
            else: # gross_gain_loss_eur is None
                 self.net_gain_loss_after_teilfreistellung_eur = None
        
        # Fallback for non-funds or if net hasn't been set yet (e.g., gross_gain_loss_eur was None for a fund)
        elif self.asset_category_at_realization != AssetCategory.INVESTMENT_FUND:
            if self.gross_gain_loss_eur is not None:
                # For non-funds, net is gross if TF not applicable
                self.net_gain_loss_after_teilfreistellung_eur = self.gross_gain_loss_eur
            else:
                self.net_gain_loss_after_teilfreistellung_eur = None
        
        # If it's an INVESTMENT_FUND and gross_gain_loss_eur was None, 
        # net_gain_loss_after_teilfreistellung_eur will correctly remain None from its default or the fund block's else.


@dataclass
class VorabpauschaleData: 
    asset_internal_id: uuid.UUID
    tax_year: int
    
    fund_value_start_year_eur: Decimal
    fund_value_end_year_eur: Decimal
    distributions_during_year_eur: Decimal
    base_return_rate: Decimal 
    basiszins: Decimal 
    
    calculated_base_return_eur: Decimal 
    
    gross_vorabpauschale_eur: Decimal
    
    fund_type: InvestmentFundType
    teilfreistellung_rate_applied: Decimal
    teilfreistellung_amount_eur: Decimal 
    
    net_taxable_vorabpauschale_eur: Decimal 

    tax_reporting_category_gross: Optional[TaxReportingCategory] = None

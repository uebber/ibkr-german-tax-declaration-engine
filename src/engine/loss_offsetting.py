# src/engine/loss_offsetting.py
import logging
from decimal import Decimal, Context
from collections import defaultdict
from typing import List, Dict, Optional

from src.domain.results import RealizedGainLoss, VorabpauschaleData, LossOffsettingResult
from src.domain.events import FinancialEvent, CashFlowEvent
from src.domain.enums import AssetCategory, FinancialEventType, InvestmentFundType, TaxReportingCategory
from src.domain.assets import Asset, InvestmentFund
from src.identification.asset_resolver import AssetResolver
from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type
import src.config as global_config

logger = logging.getLogger(__name__)

class LossOffsettingEngine:
    def __init__(self,
                 realized_gains_losses: List[RealizedGainLoss],
                 vorabpauschale_items: List[VorabpauschaleData],
                 current_year_financial_events: List[FinancialEvent],
                 asset_resolver: AssetResolver,
                 tax_year: int,
                 apply_conceptual_derivative_loss_capping: bool = global_config.APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING):
        self.realized_gains_losses = realized_gains_losses
        self.vorabpauschale_items = vorabpauschale_items
        self.current_year_financial_events = current_year_financial_events
        self.asset_resolver = asset_resolver
        self.tax_year = tax_year
        self.apply_conceptual_derivative_loss_capping = apply_conceptual_derivative_loss_capping

        self.ctx = Context(prec=global_config.INTERNAL_CALCULATION_PRECISION, rounding=global_config.DECIMAL_ROUNDING_MODE) # Renamed INTERNAL_WORKING_PRECISION
        self.TWO_PLACES = global_config.OUTPUT_PRECISION_AMOUNTS # Renamed from PRECISION_TOTAL_AMOUNTS

    def _calculate_net_fund_distribution(self, event: CashFlowEvent, asset: InvestmentFund) -> Decimal:
        if not isinstance(event, CashFlowEvent) or event.event_type != FinancialEventType.DISTRIBUTION_FUND:
            return self.ctx.create_decimal(Decimal('0'))
        if not isinstance(asset, InvestmentFund):
            logger.error(f"Asset {asset.internal_asset_id} for fund distribution event {event.event_id} is not of type InvestmentFund.")
            return event.gross_amount_eur if event.gross_amount_eur is not None else self.ctx.create_decimal(Decimal('0'))

        gross_dist_eur = event.gross_amount_eur
        if gross_dist_eur is None:
            return self.ctx.create_decimal(Decimal('0'))

        tf_rate = get_teilfreistellung_rate_for_fund_type(asset.fund_type)

        tf_amount = Decimal('0')
        if gross_dist_eur > Decimal('0'):
             tf_amount = self.ctx.multiply(gross_dist_eur, tf_rate)

        net_dist_eur = self.ctx.subtract(gross_dist_eur, tf_amount)

        return net_dist_eur.quantize(self.TWO_PLACES, context=self.ctx)


    def calculate_reporting_figures(self) -> LossOffsettingResult:
        result = LossOffsettingResult()

        stock_gains_gross = self.ctx.create_decimal(Decimal('0'))
        stock_losses_abs = self.ctx.create_decimal(Decimal('0'))
        derivative_gains_gross = self.ctx.create_decimal(Decimal('0'))
        derivative_losses_abs = self.ctx.create_decimal(Decimal('0'))
        kap_other_income_positive = self.ctx.create_decimal(Decimal('0'))
        kap_other_losses_abs = self.ctx.create_decimal(Decimal('0'))

        fund_income_net_taxable = self.ctx.create_decimal(Decimal('0'))

        p23_net_total = self.ctx.create_decimal(Decimal('0'))

        for rgl in self.realized_gains_losses:
            gross_gl_eur = rgl.gross_gain_loss_eur if rgl.gross_gain_loss_eur is not None else self.ctx.create_decimal(Decimal('0'))

            cat = rgl.asset_category_at_realization
            if cat == AssetCategory.STOCK:
                if gross_gl_eur > Decimal('0'):
                    stock_gains_gross = self.ctx.add(stock_gains_gross, gross_gl_eur)
                else:
                    stock_losses_abs = self.ctx.add(stock_losses_abs, gross_gl_eur.copy_abs())
            elif cat in [AssetCategory.OPTION, AssetCategory.CFD]:
                if gross_gl_eur > Decimal('0'):
                    derivative_gains_gross = self.ctx.add(derivative_gains_gross, gross_gl_eur)
                else:
                    derivative_losses_abs = self.ctx.add(derivative_losses_abs, gross_gl_eur.copy_abs())
            elif cat == AssetCategory.BOND:
                if gross_gl_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, gross_gl_eur)
                else:
                    kap_other_losses_abs = self.ctx.add(kap_other_losses_abs, gross_gl_eur.copy_abs())
            elif cat == AssetCategory.INVESTMENT_FUND:
                net_gl_eur_after_tf = rgl.net_gain_loss_after_teilfreistellung_eur
                if net_gl_eur_after_tf is None:
                     logger.warning(f"RGL {rgl.originating_event_id} for fund {rgl.asset_internal_id} has no net_gain_loss_after_teilfreistellung_eur. Using gross_gain_loss_eur.")
                     net_gl_eur_after_tf = gross_gl_eur

                fund_income_net_taxable = self.ctx.add(fund_income_net_taxable, net_gl_eur_after_tf)

            elif cat == AssetCategory.PRIVATE_SALE_ASSET:
                if rgl.is_taxable_under_section_23:
                    p23_net_total = self.ctx.add(p23_net_total, gross_gl_eur)

        stueckzinsen_paid_sum = self.ctx.create_decimal(Decimal('0')) # Only used for logging/future explicit handling

        for event in self.current_year_financial_events:
            asset_resolved = self.asset_resolver.get_asset_by_id(event.asset_internal_id)
            if not asset_resolved:
                logger.warning(f"Could not resolve asset ID {event.asset_internal_id} for financial event {event.event_id}. Skipping for LossOffsettingEngine income aggregation.")
                continue

            event_gross_eur = event.gross_amount_eur if event.gross_amount_eur is not None else self.ctx.create_decimal(Decimal('0'))

            if event.event_type == FinancialEventType.DIVIDEND_CASH and isinstance(asset_resolved, Asset) and asset_resolved.asset_category == AssetCategory.STOCK:
                if event_gross_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)
            elif event.event_type == FinancialEventType.INTEREST_RECEIVED:
                 if event_gross_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)           
            elif event.event_type == FinancialEventType.INTEREST_PAID_STUECKZINSEN:
                 stueckzinsen_paid_sum = self.ctx.add(stueckzinsen_paid_sum, event_gross_eur.copy_abs())
                 # According to PRD Section 2.6, paid Stückzinsen reduce "Other Capital Income".
                 # If they are reliably parsed as negative amounts, this would be:
                 # kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)
                 # Or if always positive cost:
                 if event_gross_eur.copy_abs() > Decimal('0'): # ensure non-zero before adding to losses
                    kap_other_losses_abs = self.ctx.add(kap_other_losses_abs, event_gross_eur.copy_abs())

            elif event.event_type == FinancialEventType.DISTRIBUTION_FUND and isinstance(asset_resolved, InvestmentFund):
                net_dist_eur = self._calculate_net_fund_distribution(event, asset_resolved)
                fund_income_net_taxable = self.ctx.add(fund_income_net_taxable, net_dist_eur)
            elif event.event_type == FinancialEventType.CORP_STOCK_DIVIDEND:
                 if isinstance(asset_resolved, Asset) and asset_resolved.asset_category == AssetCategory.STOCK and event_gross_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)

        for vp_item in self.vorabpauschale_items:
            if vp_item.tax_year == self.tax_year:
                net_vp_eur = vp_item.net_taxable_vorabpauschale_eur
                if net_vp_eur is None:
                    logger.warning(f"Vorabpauschale item for asset {vp_item.asset_internal_id} has no net_taxable_vorabpauschale_eur. Assuming 0.")
                    net_vp_eur = self.ctx.create_decimal(Decimal('0'))

                fund_income_net_taxable = self.ctx.add(fund_income_net_taxable, net_vp_eur)

        result.conceptual_fund_income_net_taxable = fund_income_net_taxable.quantize(self.TWO_PLACES, context=self.ctx)

        # Anlage KAP Line Calculations (as per PRD Sec 2.7)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] = stock_gains_gross.quantize(self.TWO_PLACES, context=self.ctx)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST] = stock_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN] = derivative_gains_gross.quantize(self.TWO_PLACES, context=self.ctx)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST] = derivative_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE] = kap_other_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)

        # Zeile 19 Calculation
        zeile_19_amount = self.ctx.add(stock_gains_gross, derivative_gains_gross)
        zeile_19_amount = self.ctx.add(zeile_19_amount, kap_other_income_positive)
        zeile_19_amount = self.ctx.subtract(zeile_19_amount, stock_losses_abs)
        # Note: derivative_losses_abs are NOT subtracted here for Z19 per PRD.
        zeile_19_amount = self.ctx.subtract(zeile_19_amount, kap_other_losses_abs)
            
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] = zeile_19_amount.quantize(self.TWO_PLACES, context=self.ctx)


        # Anlage SO
        result.form_line_values["ANLAGE_SO_Z54_NET_GV"] = p23_net_total.quantize(self.TWO_PLACES, context=self.ctx)

        # Anlage KAP-INV (Gross Figures)
        kap_inv_gross_dist_collector = defaultdict(lambda: self.ctx.create_decimal(Decimal('0')))
        kap_inv_gross_gl_collector = defaultdict(lambda: self.ctx.create_decimal(Decimal('0')))
        kap_inv_gross_vop_collector = defaultdict(lambda: self.ctx.create_decimal(Decimal('0'))) # Should be 0 for 2023

        for event in self.current_year_financial_events:
            if isinstance(event, CashFlowEvent) and event.event_type == FinancialEventType.DISTRIBUTION_FUND:
                asset = self.asset_resolver.get_asset_by_id(event.asset_internal_id)
                if isinstance(asset, InvestmentFund) and event.gross_amount_eur is not None:
                    from src.reporting.reporting_utils import get_kap_inv_category_for_reporting
                    reporting_cat = get_kap_inv_category_for_reporting(asset.fund_type, is_distribution=True, is_gain=False) # For distributions
                    if reporting_cat:
                        kap_inv_gross_dist_collector[reporting_cat] = self.ctx.add(kap_inv_gross_dist_collector[reporting_cat], event.gross_amount_eur)

        for key, val in kap_inv_gross_dist_collector.items():
            result.form_line_values[key] = val.quantize(self.TWO_PLACES, context=self.ctx)

        for rgl in self.realized_gains_losses:
            if rgl.asset_category_at_realization == AssetCategory.INVESTMENT_FUND and rgl.gross_gain_loss_eur is not None:
                from src.reporting.reporting_utils import get_kap_inv_category_for_reporting
                reporting_cat = get_kap_inv_category_for_reporting(rgl.fund_type_at_sale, is_distribution=False, is_gain=True)
                if reporting_cat:
                     if rgl.tax_reporting_category:
                         kap_inv_gross_gl_collector[rgl.tax_reporting_category] = self.ctx.add(kap_inv_gross_gl_collector[rgl.tax_reporting_category], rgl.gross_gain_loss_eur)
                     else:
                         logger.warning(f"RGL for fund {rgl.asset_internal_id} missing tax_reporting_category. Using derived category {reporting_cat}.")
                         kap_inv_gross_gl_collector[reporting_cat] = self.ctx.add(kap_inv_gross_gl_collector[reporting_cat], rgl.gross_gain_loss_eur)


        for key, val in kap_inv_gross_gl_collector.items():
            result.form_line_values[key] = val.quantize(self.TWO_PLACES, context=self.ctx)

        for vp_item in self.vorabpauschale_items: # Will be 0 for 2023
             if vp_item.tax_year == self.tax_year and vp_item.gross_vorabpauschale_eur != Decimal(0):
                if vp_item.tax_reporting_category_gross:
                     kap_inv_gross_vop_collector[vp_item.tax_reporting_category_gross] = self.ctx.add(kap_inv_gross_vop_collector[vp_item.tax_reporting_category_gross], vp_item.gross_vorabpauschale_eur)

        for key, val in kap_inv_gross_vop_collector.items():
            result.form_line_values[key] = val.quantize(self.TWO_PLACES, context=self.ctx)

        # Conceptual Net Balances (as per PRD Sec 2.8)
        result.conceptual_net_stocks = (self.ctx.subtract(stock_gains_gross, stock_losses_abs)).quantize(self.TWO_PLACES, context=self.ctx)
        result.conceptual_net_other_income = (self.ctx.subtract(kap_other_income_positive, kap_other_losses_abs)).quantize(self.TWO_PLACES, context=self.ctx)
        result.conceptual_net_p23_estg = p23_net_total.quantize(self.TWO_PLACES, context=self.ctx)

        net_derivatives_uncapped = self.ctx.subtract(derivative_gains_gross, derivative_losses_abs)
        result.conceptual_net_derivatives_uncapped = net_derivatives_uncapped.quantize(self.TWO_PLACES, context=self.ctx)

        if self.apply_conceptual_derivative_loss_capping and net_derivatives_uncapped < Decimal('0'):
            capped_net_derivative_loss = max(net_derivatives_uncapped, self.ctx.create_decimal(Decimal('-20000')))
            result.conceptual_net_derivatives_capped = capped_net_derivative_loss.quantize(self.TWO_PLACES, context=self.ctx)
        else:
            result.conceptual_net_derivatives_capped = net_derivatives_uncapped.quantize(self.TWO_PLACES, context=self.ctx)

        return result

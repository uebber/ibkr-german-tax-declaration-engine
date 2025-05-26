# src/reporting/reporting_utils.py
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Any
from datetime import date

from src.domain.enums import InvestmentFundType, TaxReportingCategory 
import src.config as config # For precision settings


logger = logging.getLogger(__name__)

def _q(val: Optional[Decimal | int | float | str]) -> Decimal:
    """Quantize Decimal value for total amounts, handling None, int, float, str."""
    if val is None:
        return Decimal('0.00')
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except Exception:
            logger.error(f"Could not convert value '{val}' of type {type(val)} to Decimal in _q. Returning 0.00.")
            return Decimal('0.00')

    return val.quantize(config.OUTPUT_PRECISION_AMOUNTS, rounding=ROUND_HALF_UP) # Renamed from PRECISION_TOTAL_AMOUNTS

def _q_price(val: Optional[Decimal | int | float | str]) -> Decimal:
    """Quantize Decimal value for per-share prices."""
    if val is None:
        # Return a zero value quantized to the correct precision
        return Decimal('0').quantize(config.OUTPUT_PRECISION_PER_SHARE, rounding=ROUND_HALF_UP) # Renamed from PRECISION_PER_SHARE_AMOUNTS
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except Exception:
            logger.error(f"Could not convert value '{val}' of type {type(val)} to Decimal in _q_price. Returning zero.")
            return Decimal('0').quantize(config.OUTPUT_PRECISION_PER_SHARE, rounding=ROUND_HALF_UP) # Renamed from PRECISION_PER_SHARE_AMOUNTS
    return val.quantize(config.OUTPUT_PRECISION_PER_SHARE, rounding=ROUND_HALF_UP) # Renamed from PRECISION_PER_SHARE_AMOUNTS

def _q_qty(val: Optional[Decimal | int | float | str]) -> Decimal:
    """Quantize Decimal value for quantities."""
    if val is None:
        return Decimal('0').quantize(config.PRECISION_QUANTITY, rounding=ROUND_HALF_UP)
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except Exception:
            logger.error(f"Could not convert value '{val}' of type {type(val)} to Decimal in _q_qty. Returning zero.")
            return Decimal('0').quantize(config.PRECISION_QUANTITY, rounding=ROUND_HALF_UP)
    return val.quantize(config.PRECISION_QUANTITY, rounding=ROUND_HALF_UP)

def format_date_german(dt: Optional[date | str]) -> str:
    """Formats a date object or YYYY-MM-DD string to DD.MM.YYYY string."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        try:
            dt = date.fromisoformat(dt)
        except ValueError:
            return dt # Return original string if parsing fails
    if isinstance(dt, date):
        return dt.strftime("%d.%m.%Y")
    return str(dt)


# Helper to create a standard paragraph for ReportLab
def create_paragraph(text: str, style_name: str, styles):
    from reportlab.platypus import Paragraph
    return Paragraph(text, styles[style_name])

# Helper to create a basic table for ReportLab
def create_table(data: List[List[Any]], col_widths: Optional[List[float]] = None, style_commands: Optional[List[Any]] = None):
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    table = Table(data, colWidths=col_widths)
    
    # Default style
    ts = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), # Header row background
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), # Header font
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),    # Body font
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]
    if style_commands:
        ts.extend(style_commands)
    
    table.setStyle(TableStyle(ts))
    return table

# This function was in the PRD, moving it here for consistency
def get_kap_inv_category_for_reporting(
    fund_type: Optional[InvestmentFundType],
    is_distribution: bool,
    is_gain: bool # Note: For G/L, this should be true, sign of amount indicates gain or loss
) -> Optional[TaxReportingCategory]:
    """
    Helper to map fund type and event type to KAP-INV TaxReportingCategory for reporting.
    """
    if fund_type == InvestmentFundType.AKTIENFONDS:
        if is_distribution: return TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_AUSSCHUETTUNG_GROSS
        if is_gain: return TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS
    elif fund_type == InvestmentFundType.MISCHFONDS:
        if is_distribution: return TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_AUSSCHUETTUNG_GROSS
        if is_gain: return TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS
    elif fund_type == InvestmentFundType.IMMOBILIENFONDS:
        if is_distribution: return TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS
        if is_gain: return TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS
    elif fund_type == InvestmentFundType.AUSLANDS_IMMOBILIENFONDS:
        if is_distribution: return TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS
        if is_gain: return TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS
    elif fund_type == InvestmentFundType.SONSTIGE_FONDS or fund_type == InvestmentFundType.NONE: # Grouping NONE with Sonstige for reporting
        if is_distribution: return TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_AUSSCHUETTUNG_GROSS
        if is_gain: return TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS
    return None

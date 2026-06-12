# src/processing/vp_nav_resolution.py
"""
Pre-pass that resolves the start-of-year NAVs needed for the §18 InvStG
Vorabpauschale, for two calendar years:

  * Current year X — the VP that flows next year (preview of the X+1 return).
    Funds acquired during X and held at year-end need a user-supplied 1 Jan X NAV
    (absent from IBKR data). Attached as vp_soy_nav_per_unit.

  * Prior year X-1 — the VP that flows this year and belongs on the X return.
    Funds held at end of X-1 need their 1 Jan X-1 NAV: from the prior-year SoY
    positions export (Positions-{X-1}-SoY.csv) when held on 1 Jan X-1, otherwise
    interactive input for funds acquired during X-1. Attached as vp_prior_soy_nav_per_unit.

All resolution is warn-only: anything that cannot be resolved is recorded as a
VorabpauschaleGap (surfaced as an explicit report callout), never aborting the run.
"""
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from src.domain.assets import InvestmentFund
from src.domain.events import FinancialEvent, TradeEvent
from src.domain.enums import FinancialEventType
from src.domain.results import VorabpauschaleGap
from src.identification.asset_resolver import AssetResolver
from src.identification.fund_soy_nav_provider import FundSoyNavProvider
from src.utils.type_utils import parse_ibkr_date

logger = logging.getLogger(__name__)

# Map of ISIN -> (nav_per_unit, currency) from a prior-year SoY positions export.
PriorSoyPositions = Dict[str, Tuple[Decimal, str]]


def _first_buy_month_in_year(asset_id, events: List[FinancialEvent], year: int) -> Optional[int]:
    months = []
    for ev in events:
        if (
            isinstance(ev, TradeEvent)
            and ev.asset_internal_id == asset_id
            and ev.event_type == FinancialEventType.TRADE_BUY_LONG
        ):
            d = parse_ibkr_date(ev.event_date)
            if d is not None and d.year == year:
                months.append(d.month)
    return min(months) if months else None


def resolve_year_start_navs(
    asset_resolver: AssetResolver,
    events: List[FinancialEvent],
    tax_year: int,
    interactive: bool,
    provider: FundSoyNavProvider,
    prior_year_soy_positions: Optional[PriorSoyPositions] = None,
) -> List[VorabpauschaleGap]:
    """Attach current- and prior-year start NAVs to funds; return any gaps (warn-only)."""
    gaps: List[VorabpauschaleGap] = []
    prior_year = tax_year - 1
    prior_file_available = prior_year_soy_positions is not None
    prior_map: PriorSoyPositions = prior_year_soy_positions or {}
    prior_file_missing_funds = 0

    for asset in asset_resolver.assets_by_internal_id.values():
        if not isinstance(asset, InvestmentFund):
            continue

        # --- Current year X: funds acquired during X, held at year-end ---
        if (
            asset.eoy_quantity is not None and asset.eoy_quantity > Decimal("0")
            and (asset.soy_quantity is None or asset.soy_quantity <= Decimal("0"))
        ):
            first_buy_month = _first_buy_month_in_year(asset.internal_asset_id, events, tax_year)
            if first_buy_month is not None:
                context = [f"Acquired during {tax_year}; held at year-end: {asset.eoy_quantity} units."]
                if asset.eoy_market_price is not None:
                    context.append(f"Year-end price/unit (ref): {asset.eoy_market_price} {asset.currency or ''}".rstrip())
                nav = provider.get_or_prompt(asset, tax_year, interactive, context_lines=context)
                if nav is not None:
                    asset.vp_soy_nav_per_unit = nav
                    asset.vp_soy_nav_currency = asset.vp_soy_nav_currency or asset.currency
                    asset.vp_acquisition_month = first_buy_month
                else:
                    gaps.append(VorabpauschaleGap(
                        asset_internal_id=asset.internal_asset_id,
                        description=asset.description or asset.get_classification_key(),
                        target_year=tax_year, deemed_inflow_year=tax_year + 1,
                        reason=f"SoY-NAV zum 01.01.{tax_year} fehlt (unterjährig {tax_year} erworben) — interaktiv eingeben",
                    ))

        # --- Prior year X-1: funds held at end of X-1 (= this run's SoY) ---
        if asset.soy_quantity is not None and asset.soy_quantity > Decimal("0"):
            isin = asset.ibkr_isin
            if isin and isin in prior_map:
                nav, ccy = prior_map[isin]
                asset.vp_prior_soy_nav_per_unit = nav
                asset.vp_prior_soy_nav_currency = ccy
                asset.vp_prior_acquisition_month = None  # held on 1 Jan X-1 -> full factor
                continue

            first_buy_month = _first_buy_month_in_year(asset.internal_asset_id, events, prior_year)
            if first_buy_month is not None:
                # Acquired during X-1 -> not in the prior SoY export; needs manual NAV.
                context = [f"Erworben {prior_year}; zum Jahresende {prior_year} gehalten: {asset.soy_quantity} Anteile."]
                nav = provider.get_or_prompt(asset, prior_year, interactive, context_lines=context)
                if nav is not None:
                    asset.vp_prior_soy_nav_per_unit = nav
                    asset.vp_prior_soy_nav_currency = asset.vp_prior_soy_nav_currency or asset.currency
                    asset.vp_prior_acquisition_month = first_buy_month
                else:
                    gaps.append(VorabpauschaleGap(
                        asset_internal_id=asset.internal_asset_id,
                        description=asset.description or asset.get_classification_key(),
                        target_year=prior_year, deemed_inflow_year=tax_year,
                        reason=f"SoY-NAV zum 01.01.{prior_year} fehlt (unterjährig {prior_year} erworben) — interaktiv eingeben",
                    ))
            elif not prior_file_available:
                prior_file_missing_funds += 1
            else:
                # Held at end of X-1, in the run's SoY, but absent from the prior SoY export
                # and no X-1 purchase — cannot place its 1 Jan X-1 NAV.
                gaps.append(VorabpauschaleGap(
                    asset_internal_id=asset.internal_asset_id,
                    description=asset.description or asset.get_classification_key(),
                    target_year=prior_year, deemed_inflow_year=tax_year,
                    reason=f"SoY-NAV zum 01.01.{prior_year} nicht im Export Positions-{prior_year}-SoY.csv gefunden",
                ))

    if prior_file_missing_funds > 0:
        gaps.append(VorabpauschaleGap(
            asset_internal_id=None,
            description=f"{prior_file_missing_funds} Bestandsfonds aus {prior_year}",
            target_year=prior_year, deemed_inflow_year=tax_year,
            reason=f"Positions-{prior_year}-SoY.csv (IBKR-Export) fehlt — Vorjahres-Vorabpauschale nicht berechenbar",
        ))

    for gap in gaps:
        logger.warning("Vorabpauschale gap: %s — %s", gap.description, gap.reason)
    return gaps

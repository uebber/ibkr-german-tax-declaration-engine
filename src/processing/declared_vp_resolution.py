# src/processing/declared_vp_resolution.py
"""
Pre-pass that resolves the Vorabpauschale a user *declared* in prior years for funds
**disposed during the tax year**, so the §19 Abs. 1 S. 3-4 InvStG deduction can reduce
the disposal gain (Anlage KAP-INV: gain on Z14-26 net of the held-period VP).

For every investment fund sold in the tax year, we prompt (once, cached) for the gross
Vorabpauschale declared in each prior holding year (earliest acquisition year .. tax_year-1)
and attach it as asset.vp_declared_by_year. The form (Z53) only allows the deduction for VP
that was actually subjected to taxation, so a year the user did not declare (blank -> 0) is
simply not deducted.

Warn-only: anything unresolved (non-interactive run, no cache) is recorded as a
VorabpauschaleGap and surfaced as a report callout; the run never aborts. With no declared
VP resolved, the disposal gain is left unreduced (conservative — may overstate the gain).
"""
import logging
import uuid
from decimal import Decimal, Context
from typing import Dict, List, Optional

import src.config as config
from src.domain.assets import InvestmentFund
from src.domain.events import FinancialEvent, TradeEvent
from src.domain.enums import FinancialEventType
from src.domain.results import VorabpauschaleGap, VorabpauschaleData
from src.identification.asset_resolver import AssetResolver
from src.identification.declared_vp_provider import DeclaredVpProvider

logger = logging.getLogger(__name__)


def _buy_years(asset_id, events: List[FinancialEvent]) -> List[int]:
    return [
        int(ev.event_date[:4])
        for ev in events
        if isinstance(ev, TradeEvent)
        and ev.asset_internal_id == asset_id
        and ev.event_type == FinancialEventType.TRADE_BUY_LONG
    ]


def _is_disposed_in_year(asset_id, events: List[FinancialEvent], year: int) -> bool:
    return any(
        isinstance(ev, TradeEvent)
        and ev.asset_internal_id == asset_id
        and ev.event_type == FinancialEventType.TRADE_SELL_LONG
        and int(ev.event_date[:4]) == year
        for ev in events
    )


def resolve_declared_vp(
    asset_resolver: AssetResolver,
    events: List[FinancialEvent],
    tax_year: int,
    interactive: bool,
    provider: DeclaredVpProvider,
    currency_converter,
) -> List[VorabpauschaleGap]:
    """Attach `vp_declared_by_year` to every fund disposed in `tax_year`; return gaps.

    The most recent holding year (V-1) is the one the engine itself computes and places on
    Anlage KAP-INV Z9-13 of this return; here we compute the same figure (via the §18 prior-
    year path) and **auto-enter it** into the deduction map and the cache — it is never
    prompted. Only the earlier holding years (≤ V-2), which were declared on prior returns and
    cannot be recomputed (no historical NAVs), are prompted.
    """
    gaps: List[VorabpauschaleGap] = []
    prior_year = tax_year - 1  # most recent holding year (V-1); auto-computed

    # Compute the prior-year (V-1) Vorabpauschale for all funds — the same figure the engine
    # places on Z13 — so disposed funds can deduct it without prompting. Uses the prior-year
    # NAVs already resolved by the NAV pre-pass (vp_nav_resolution), no FIFO ledger needed.
    prior_vp_gross: Dict[uuid.UUID, Decimal] = {}
    from src.tax_law.registry import basiszins_pct
    if basiszins_pct(prior_year) is not None:
        from src.engine.calculation_engine import _vp_for_calendar_year  # lazy: avoid import cycle
        ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION, rounding=config.DECIMAL_ROUNDING_MODE)
        prior_records: List[VorabpauschaleData] = []
        _vp_for_calendar_year(
            asset_resolver, events, currency_converter, prior_year, tax_year, ctx, None, prior_records
        )
        prior_vp_gross = {r.asset_internal_id: r.gross_vorabpauschale_eur for r in prior_records}

    for asset in asset_resolver.assets_by_internal_id.values():
        if not isinstance(asset, InvestmentFund):
            continue
        if not _is_disposed_in_year(asset.internal_asset_id, events, tax_year):
            continue

        # Earliest holding year: earliest acquisition year (or, for pre-window holdings, the
        # most recent holding year only).
        buys = _buy_years(asset.internal_asset_id, events)
        if buys:
            earliest = min(buys)
        elif asset.soy_quantity is not None and asset.soy_quantity > Decimal("0"):
            earliest = prior_year
        else:
            continue  # bought and fully sold within the tax year -> no prior-year VP

        declared: Dict[int, Decimal] = {}

        # --- Holding year V-1: auto-computed, auto-entered into cache, never prompted ---
        computed_v1 = prior_vp_gross.get(asset.internal_asset_id)
        if computed_v1 is not None and computed_v1 > Decimal("0"):
            declared[prior_year] = computed_v1
            provider.set(asset, prior_year, computed_v1)
            if interactive:
                print(
                    f"  [auto] Haltejahr {prior_year}: Vorabpauschale = {computed_v1} EUR "
                    f"(berechnet; steht in Zeile 9-13 dieser Erklärung {tax_year} und wird vom "
                    f"Veräußerungsgewinn abgezogen). Keine Eingabe nötig."
                )

        # --- Holding years ≤ V-2: declared on prior returns, prompted (or cache-hit) ---
        missing_years: List[int] = []
        for year in range(earliest, prior_year):  # excludes V-1
            context = [f"(Fonds wurde {tax_year} veräußert.)"]
            value = provider.get_or_prompt(asset, year, interactive, context_lines=context)
            if value is not None:
                if value > Decimal("0"):
                    declared[year] = value
            else:
                missing_years.append(year)

        if declared:
            asset.vp_declared_by_year = declared

        if missing_years:
            gaps.append(VorabpauschaleGap(
                asset_internal_id=asset.internal_asset_id,
                description=asset.description or asset.get_classification_key(),
                target_year=tax_year, deemed_inflow_year=tax_year,
                reason=(
                    f"Erklärte Vorabpauschale für Haltejahr(e) {', '.join(map(str, missing_years))} "
                    f"fehlt — Veräußerungsgewinn evtl. nicht voll um §19-VP gemindert (interaktiv eingeben)"
                ),
            ))

    for gap in gaps:
        logger.warning("Declared-VP gap: %s — %s", gap.description, gap.reason)
    return gaps

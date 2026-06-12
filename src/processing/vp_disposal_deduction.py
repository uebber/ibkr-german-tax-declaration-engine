# src/processing/vp_disposal_deduction.py
"""
§19 Abs. 1 Satz 3-4 InvStG — Vorabpauschale deduction at fund disposal.

When investment-fund units are sold, the disposal gain is reduced by the gross
Vorabpauschalen **assessed during the holding period of the sold units** (§19 Abs. 1
S. 3), at their full pre-Teilfreistellung amount (S. 4), and only to the extent the VP
was actually subjected to taxation in the prior years (Z9-13 — the *declared* VP).

The official Anlage KAP-INV worksheet (Z46-54) is per fund, per acquisition tranche,
**FIFO**. Each sold unit carries, for every year-end it was held, a share of that year's
VP equal to `declared_VP[Y] / units_held_at_end_of_Y`. Hence, per lot:

    deduction = units_sold × Σ_{Y = acquisition_year .. sale_year-1} declared_VP[Y] / qty_eoy[Y]

A full exit of the whole position reduces to `Σ_Y declared_VP[Y]`.

This module holds the two pure helpers; the engine wires them at the disposal seam.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Iterable
import uuid

from src.domain.events import FinancialEvent, TradeEvent


def year_end_quantities(
    events: Iterable[FinancialEvent],
    asset_internal_id: uuid.UUID,
    up_to_year: int,
) -> Dict[int, Decimal]:
    """Net units of a fund held at 31 December of each year, from the earliest trade
    year through `up_to_year` (inclusive). Carries the running balance forward across
    years without trades, so a year held but untraded still has a denominator.

    `TradeEvent.quantity` is signed (positive buy, negative sell), so the running sum
    is the net position. Returns {} if the asset has no trades.
    """
    deltas: Dict[int, Decimal] = defaultdict(lambda: Decimal(0))
    min_year = None
    for ev in events:
        if not isinstance(ev, TradeEvent):
            continue
        if ev.asset_internal_id != asset_internal_id:
            continue
        year = int(ev.event_date[:4])
        deltas[year] += ev.quantity
        min_year = year if min_year is None else min(min_year, year)

    result: Dict[int, Decimal] = {}
    if min_year is None:
        return result
    running = Decimal(0)
    for year in range(min_year, up_to_year + 1):
        running += deltas.get(year, Decimal(0))
        result[year] = running
    return result


def vp_deduction_for_lot(
    *,
    acquisition_year: int,
    sale_year: int,
    units_sold: Decimal,
    declared_vp_by_year: Dict[int, Decimal],
    qty_eoy_by_year: Dict[int, Decimal],
) -> Decimal:
    """Gross Vorabpauschale (§19 Abs. 1 S. 3-4) attributable to `units_sold` of a lot
    acquired in `acquisition_year` and disposed in `sale_year`.

    Sums, over each year-end the lot was held (`acquisition_year .. sale_year-1`), the
    units' share of that year's declared VP. A year contributes only when it has both a
    positive declared VP (i.e. it was subjected to taxation) and a positive year-end
    quantity (the denominator); otherwise it is skipped (no divide-by-zero).
    """
    total = Decimal(0)
    for year in range(acquisition_year, sale_year):
        declared = declared_vp_by_year.get(year)
        qty_eoy = qty_eoy_by_year.get(year)
        if declared and qty_eoy and declared > Decimal(0) and qty_eoy > Decimal(0):
            total += units_sold * declared / qty_eoy
    return total

# src/engine/vorabpauschale_attribution.py
"""
Spreading one fund-year's declared Vorabpauschale over the tranches that bore it.

Zeile 53 follows *the units disposed of* ([GT-INVSTG-030], Satz 3: *"waehrend der
Besitzzeit"*), so the deduction has to reach the lot. What the taxpayer can supply
-- and what a tax return records -- is the annual figure per fund. This module is
the bridge: it takes the declared fund-year total and distributes it across the
lots held at the close of that calendar year.

**The key is the engine's own § 18 Abs. 2 split, and the prices cancel out of it.**
Every factor in the per-unit Vorabpauschale is common to all tranches of a fund --
the Ruecknahmepreis at each end of the year, the Basiszins, the Satz 3 cap, the
per-unit distribution. The only thing that varies from tranche to tranche is the
unit count and the twelfths Abs. 2 leaves it ([GT-INVSTG-011]). So the weight of a
tranche is `quantity x retained twelfths` and nothing else, which is why this can
distribute a *declared* total for a year whose prices the run never loaded.

That is a derivation from inputs the run has, not a stand-in for one it lacks: the
declared total remains the cap, and no arithmetic here can produce more of it than
was declared.

**Where a tranche cannot be weighed, nothing is attributed.** A lot the historical
replay could not reconstruct carries an invented acquisition date
(`acquisition_date_is_known=False`), and Abs. 2 turns on the month of acquisition.
The other tranches cannot be normalised without it either -- their shares are
fractions of a total whose denominator includes it -- so the whole fund-year is
refused and the caller reports it. Attributing "as much as can be seen" would put
a figure nobody can check on a tax return.
"""
import logging
from datetime import date, datetime
from decimal import Context, Decimal
from typing import List, Optional, Sequence, Tuple

from src.domain.exceptions import ProcessingError
from src.utils.type_utils import parse_ibkr_date
import src.config as global_config

logger = logging.getLogger(__name__)


def abs2_retained_twelfths(acquisition_date: date, calendar_year: int) -> int:
    """Twelfths of the Vorabpauschale units acquired on this day keep, per § 18 Abs. 2.

    *"Im Jahr des Erwerbs der Investmentanteile vermindert sich die Vorabpauschale
    um ein Zwoelftel fuer jeden vollen Monat, der dem Monat des Erwerbs
    vorangeht."* ([GT-INVSTG-011]) Units acquired before the calendar year are not
    in their year of acquisition and keep all twelve; units acquired in it keep
    twelve less one for each full month that preceded the month of acquisition, so
    a January purchase keeps twelve and a December purchase keeps one.

    Units acquired *after* the year cannot be part of a holding counted at its
    close, so that case is a programming error rather than a tax one.
    """
    if acquisition_date.year < calendar_year:
        return 12
    if acquisition_date.year > calendar_year:
        raise ProcessingError(
            f"Vorabpauschale {calendar_year}: a lot acquired {acquisition_date} "
            "cannot be part of the holding at the close of that year. The snapshot "
            "was taken at the wrong point in the pipeline.")
    return 12 - (acquisition_date.month - 1)


def _tranche_weight(lot, calendar_year: int) -> Decimal:
    """`quantity x retained twelfths` for one lot; raises where Abs. 2 cannot apply."""
    if not getattr(lot, "acquisition_date_is_known", True):
        raise ProcessingError(
            f"the acquisition date of {lot.quantity} unit(s) "
            f"(lot {lot.source_transaction_id}) was invented by reconciliation, so "
            f"§ 18 Abs. 2 cannot weigh them against the other tranches")
    acquired = parse_ibkr_date(lot.acquisition_date)
    if acquired is None:
        raise ProcessingError(
            f"lot {lot.source_transaction_id} carries an unreadable acquisition "
            f"date {lot.acquisition_date!r}")
    return lot.quantity * Decimal(abs2_retained_twelfths(acquired, calendar_year))


def weigh_tranches(lots: Sequence, calendar_year: int) -> Tuple[List[Tuple[object, Decimal]], Decimal]:
    """The § 18 Abs. 2 weight of every tranche held at the close of `calendar_year`.

    Split out from the distribution because the two happen at different moments.
    The weights can only be taken while the ledger still describes that year's
    close; the amount to spread over them may not be known until later -- for an
    earlier year it comes from a record, or from asking, and asking is worth
    batching into one block rather than interleaving with the replay.

    Every tranche is weighed before anything is returned, so a fund-year whose
    weights cannot be established yields nothing at all rather than a partial set:
    the shares are fractions of a total, and a total missing a term is wrong
    everywhere, not just in the term it lacks.
    """
    ordered = sorted(
        lots,
        key=lambda l: (parse_ibkr_date(l.acquisition_date) or datetime.min.date(),
                       l.source_transaction_id))
    weights = [(lot, _tranche_weight(lot, calendar_year)) for lot in ordered]
    return weights, sum((w for _, w in weights), Decimal(0))


def apply_weighted_share(
    lot_weights: Sequence,
    total_weight: Decimal,
    declared_gross_eur: Decimal,
    ctx: Optional[Context] = None,
) -> Decimal:
    """Add each weighed tranche's share of `declared_gross_eur` to its accumulation.

    `total_weight` is the whole fund-year's weight, which is **not** necessarily
    the sum of `lot_weights`: tranches disposed of between that year's close and
    now took their share with them, and it went to whatever return declared that
    disposal. Passing the surviving subset with the original total is how those
    shares stay gone instead of being redistributed over the survivors.

    Where the subset IS the whole set, the last tranche takes the rounding
    remainder so the shares sum to the declared total exactly. A cent lost per
    fund-year is a cent off a deduction, i.e. off the taxpayer.
    """
    if ctx is None:
        ctx = Context(prec=global_config.INTERNAL_CALCULATION_PRECISION,
                      rounding=global_config.DECIMAL_ROUNDING_MODE)
    if not lot_weights or total_weight <= Decimal(0):
        return Decimal(0)

    complete = sum((w for _, w in lot_weights), Decimal(0)) == total_weight
    two_places = global_config.OUTPUT_PRECISION_AMOUNTS
    distributed = Decimal(0)
    for index, (lot, weight) in enumerate(lot_weights):
        if complete and index == len(lot_weights) - 1:
            share = ctx.subtract(declared_gross_eur, distributed)
        else:
            share = ctx.divide(ctx.multiply(declared_gross_eur, weight),
                               total_weight).quantize(two_places, context=ctx)
        lot.vorabpauschale_gross_eur = ctx.add(lot.vorabpauschale_gross_eur, share)
        distributed = ctx.add(distributed, share)
        logger.debug(
            "Vorabpauschale %s: lot %s (%s units acquired %s) takes EUR %s of the "
            "declared EUR %s.", total_weight, lot.source_transaction_id,
            lot.quantity, lot.acquisition_date, share, declared_gross_eur)
    return distributed


def distribute_declared_vorabpauschale(
    lots: Sequence,
    *,
    calendar_year: int,
    declared_gross_eur: Decimal,
    ctx: Optional[Context] = None,
) -> Decimal:
    """Add each lot's share of `declared_gross_eur` to its accumulated total.

    `lots` are the long lots of ONE fund as they stood at the close of
    `calendar_year`, across every account -- the per-person holding, because the
    declaration is per person and per fund. Returns the amount distributed.

    The last tranche takes the rounding remainder, so the shares sum to the
    declared total exactly. A cent lost per fund-year would be lost from a
    deduction, i.e. from the taxpayer.

    Raises `ProcessingError` without touching a single lot where any tranche
    cannot be weighed; the caller records that fund-year as unattributable.
    """
    # Weighed in full before anything is written, so a refusal leaves the lots
    # exactly as they were.
    weights, total_weight = weigh_tranches(lots, calendar_year)
    return apply_weighted_share(weights, total_weight, declared_gross_eur, ctx)

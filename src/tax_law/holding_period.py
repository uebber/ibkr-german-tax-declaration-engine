# src/tax_law/holding_period.py
"""
The §23 Abs. 1 Satz 1 Nr. 2 Satz 1 EStG one-year speculation period (Jahresfrist)
as a DOMAIN RULE, implemented exactly once.

Computed per §108 Abs. 1 AO i.V.m. §§187 Abs. 1, 188 Abs. 2 BGB: the acquisition
day itself is not counted, and the period ends with the expiry of the ANNIVERSARY
DAY of the acquisition in the following year. A disposal ON the anniversary day is
still within the period (taxable); the first exempt day is the day after. If the
anniversary day does not exist (acquisition on 29 February), the period ends with
the last day of February (§188 Abs. 3 BGB) — relativedelta clamps accordingly.

NOT equivalent to counting calendar days: across a leap day the anniversary lies
366 days after acquisition yet is still within the period, so a ``days <= 365``
shortcut wrongly exempts anniversary-day sales whenever the holding spans
29 February.

Deliberately NOT implemented here: whether §108 Abs. 3 AO extends the period when
the anniversary falls on a Saturday, Sunday or public holiday. That question is
unresolved at Tier 1/2 and it moves declared figures; this rule implements the
no-extension reading.

Statutory text, the derivation, the worked boundary cases, the §108 Abs. 3 AO
question and the two further rules the engine does not implement (Nr. 2 Satz 4,
Nr. 3): reference/tax-law/estg-23-private-veraeusserung.md.
"""
from datetime import date

from dateutil.relativedelta import relativedelta

from src.domain.exceptions import ProcessingError


def is_within_section23_speculation_period(acquisition_date: date,
                                           realization_date: date) -> bool:
    """True if a disposal on `realization_date` falls within the one-year
    speculation period of an asset acquired on `acquisition_date`.

    Raises ProcessingError if the disposal precedes the acquisition. §23 measures
    *"der Zeitraum zwischen Anschaffung und Veraeusserung"*, which is undefined in
    that direction; answering it silently would decide a tax figure from a state the
    engine cannot legitimately be in. (A disposal genuinely preceding the acquisition
    is a short position, which falls under §23 Abs. 1 Satz 1 Nr. 3 — a separate rule
    with no holding period at all. It reaches this function only via the short-cover
    path, which passes the opening date as the acquisition, so the arguments arrive
    in chronological order there too.)
    """
    if realization_date < acquisition_date:
        raise ProcessingError(
            f"§23 Jahresfrist is undefined for a disposal on {realization_date} that "
            f"precedes the acquisition on {acquisition_date}."
        )
    return realization_date <= acquisition_date + relativedelta(years=1)

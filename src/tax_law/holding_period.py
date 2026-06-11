# src/tax_law/holding_period.py
"""
Jahresfrist arithmetic (rework2-plan AR3) — §23 Abs. 1 Nr. 2 EStG one-year
speculation period as a DOMAIN RULE, implemented exactly once.

Computed per §108 AO i.V.m. §§187 Abs. 1, 188 Abs. 2 BGB: the period ends
with the expiry of the ANNIVERSARY DAY of the acquisition in the following
year. A disposal ON the anniversary day is still within the period (taxable);
the first exempt day is the day after. If the anniversary day does not exist
(acquisition on 29 February), the period ends with the last day of February
(§188 Abs. 3 BGB) — relativedelta clamps accordingly.

NOT equivalent to counting calendar days: across a leap day the anniversary
lies 366 days after acquisition yet is still within the period, so a
``days <= 365`` shortcut wrongly exempts anniversary-day sales whenever the
holding spans 29 February (legal-review finding F3).

reference/tax-law/estg-23-private-veraeusserung.md documents the rule.
"""
from datetime import date

from dateutil.relativedelta import relativedelta


def is_within_section23_speculation_period(acquisition_date: date,
                                           realization_date: date) -> bool:
    """True if a disposal on `realization_date` falls within the one-year
    speculation period of an asset acquired on `acquisition_date`."""
    return realization_date <= acquisition_date + relativedelta(years=1)

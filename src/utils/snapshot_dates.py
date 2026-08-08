"""
Which day a Positions snapshot describes.

`Positions-{Y}-SoY.csv` and `Positions-{Y}-EoY.csv` carry no date column, so the
day each one describes is a convention: the first and the last trading day of
`Y`. That convention is stated in `src/data_preparation.py` and it is what the
portal downloader asks IBKR for, so it is the same rule at both ends of the
pipeline -- which is the reason it lives here rather than in either of them.

**Two consumers, one rule.** The downloader uses it to request a report; the
Vorabpauschale uses it to know the Stichtag at which a price was set, because
Rz. 18.6 converts each input at the ECB rate of its own Stichtag
([GT-INVSTG-018]) and a Stichtag is a day a price was set, never a fixed
calendar date. Stating the rule twice is how the engine came to convert a
first-trading-day price at a hardcoded 2 January -- a Saturday in 2021 and a
Sunday in 2022, days on which the ECB published no rate at all.

**This is a calendar rule, not an exchange calendar.** It knows weekends and
New Year and nothing else; a fund that struck no price on the day this returns
is not detectable here. Issue #59 replaces the convention with a report date
the export itself carries, at which point these become a fallback rather than
the answer. Until then they are a derivation from the filename the file was
already selected by, not a new assumption.
"""
from datetime import date, timedelta

__all__ = [
    "weekday_on_or_before",
    "first_business_day_of_year",
    "last_business_day_of_year",
    "positions_snapshot_dates",
]


def weekday_on_or_before(day: date) -> date:
    """
    `day` itself if it is a weekday, else the Friday before it.

    The portal's date picker accepts weekdays and refuses weekends — it does
    not know or care about market holidays. 1 January 2025 was a Wednesday and
    was accepted; the recorded run for it returned a report. So the constraint
    to respect is Monday-to-Friday, not "a day the exchange was open".
    """
    while day.weekday() >= 5:      # 5 = Saturday, 6 = Sunday
        day -= timedelta(days=1)
    return day


def last_business_day_of_year(year: int) -> date:
    """31 December, or the Friday before it when it falls on a weekend."""
    return weekday_on_or_before(date(year, 12, 31))


def first_business_day_of_year(year: int) -> date:
    """
    The first trading day of a calendar year: the start-of-year snapshot date.

    1 January is closed on every exchange IBKR serves whatever weekday it falls
    on — 1 January 2021 was a Friday — and when it falls on a Sunday the
    exchanges observe it on Monday 2 January. Corroborated: the 2021 cash report
    carries FromDate 20210104, and this returns 4 January 2021.
    """
    new_year = date(year, 1, 1)
    closed = {new_year}
    if new_year.weekday() == 6:          # Sunday -> observed on the Monday
        closed.add(date(year, 1, 2))

    day = new_year
    while day.weekday() >= 5 or day in closed:
        day += timedelta(days=1)
    return day


def positions_snapshot_dates(year: int) -> tuple[date, date]:
    """
    The dates to request for a year's start-of-year and end-of-year snapshots.

    Returns:
        (start_of_year_date, end_of_year_date)
    """
    return first_business_day_of_year(year), last_business_day_of_year(year)

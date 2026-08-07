"""§ 18 Abs. 2 InvStG — the reduction for units acquired during the year.

legal_basis: [GT-INVSTG-011] § 18 Abs. 2 InvStG, *"Im Jahr des Erwerbs der
Investmentanteile vermindert sich die Vorabpauschale um ein Zwoelftel fuer jeden
vollen Monat, der dem Monat des Erwerbs vorangeht."*, and [GT-INVSTG-017]
Rz. 18.4, which fixes the unit count at the close of 31 December. Both in
reference/investment-tax-law/invstg-18-vorabpauschale.md.

Applying the reduction per acquisition tranche is what Rz. 18.11 does: its
worked example reduces the *per-Anteil* Vorabpauschale, before any unit count
has entered. Settled 2026-08-07 and recorded against GT-INVSTG-011 in
docs/legal-implementation-map.md; it is no longer a choice under uncertainty.

The failure these guard is a quiet one in both directions. Before this, units
acquired during the year produced *nothing* — an understatement invisible on the
form, because an absent figure is the one nobody notices. Getting the factor
wrong instead produces a figure that is eleven twelfths too small and looks
entirely plausible.
"""
from datetime import date
from decimal import Decimal

import pytest

from src.engine.calculation_engine import FundUnitTranche


def _tranche(quantity, acquired, known=True):
    return FundUnitTranche(quantity=Decimal(quantity), acquisition_date=acquired,
                           acquisition_date_is_known=known)


class TestTheTwelfthsATrancheKeeps:
    """One twelfth is dropped for each *full* month before the month of
    acquisition, so the month of acquisition itself is never dropped."""

    @pytest.mark.parametrize("month,expected", [
        (1, 12),   # no full month precedes January
        (2, 11),
        (6, 7),    # January to May are five full months
        (11, 2),
        (12, 1),   # the reference states this one explicitly
    ])
    def test_acquired_during_the_year(self, month, expected):
        tranche = _tranche("100", date(2024, month, 15))

        assert tranche.abs2_retained_twelfths(2024) == expected

    def test_acquired_before_the_year_keeps_all_twelve(self):
        """Not "im Jahr des Erwerbs", so Abs. 2 does not reach it at all."""
        assert _tranche("100", date(2019, 7, 1)).abs2_retained_twelfths(2024) == 12

    def test_the_day_within_the_month_does_not_matter(self):
        first = _tranche("100", date(2024, 6, 1)).abs2_retained_twelfths(2024)
        last = _tranche("100", date(2024, 6, 30)).abs2_retained_twelfths(2024)

        assert first == last == 7

    def test_acquired_after_the_year_is_a_programming_error(self):
        """
        Such a tranche cannot be part of a holding counted at the close of the
        year. Reaching here means the lots were snapshotted at the wrong point
        in the pipeline, which would silently mis-scale every figure rather
        than fail.
        """
        from src.domain.exceptions import ProcessingError

        with pytest.raises(ProcessingError, match="wrong point"):
            _tranche("100", date(2025, 3, 1)).abs2_retained_twelfths(2024)

    def test_an_invented_acquisition_date_is_never_reduced_on(self):
        """
        The caller drops the fund before reaching here. If that guard is ever
        removed, this raises rather than turning a placeholder date into an
        eleven-twelfths cut of deemed income.
        """
        from src.domain.exceptions import ProcessingError

        undated = _tranche("100", date(2023, 12, 31), known=False)

        with pytest.raises(ProcessingError, match="invented"):
            undated.abs2_retained_twelfths(2024)

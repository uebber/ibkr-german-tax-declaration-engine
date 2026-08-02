"""
Console summary: the Termingeschäfte block.

legal_basis: §20 Abs. 6 S. 5 a.F. EStG (€20k cap) was repealed by JStG 2024;
§52 Abs. 28 Satz 25 EStG orders it "auf alle offenen Fälle nicht mehr
anzuwenden" — so the block must never claim a first year of repeal, and it must
not tie the Zeile-24 cross-check to the cap, which no longer applies anywhere.
Source: reference/tax-law/estg-20-abs6-verlustverrechnung.md.
"""
import contextlib
import io
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.domain.results import LossOffsettingResult
from src.reporting.console_reporter import generate_console_tax_report


class _StubResolver:
    assets_by_internal_id: dict = {}

    def get_asset_by_id(self, internal_id):
        return None


def _summary_lines(tax_year: int, uncapped="-25000.00", z24="25000.00") -> list[str]:
    result = LossOffsettingResult()
    result.conceptual_net_derivatives_uncapped = Decimal(uncapped)
    result.conceptual_net_derivatives_capped = Decimal(uncapped)
    result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST] = Decimal(z24)

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        generate_console_tax_report([], [], [], _StubResolver(), tax_year, 0, result)
    return [line.strip() for line in buffer.getvalue().splitlines()]


@pytest.mark.parametrize("tax_year", [2021, 2022, 2023, 2024, 2025])
def test_no_capped_saldo_is_ever_printed(tax_year):
    """No assessment year applies the cap, so the 'ggf. Verlustbegrenzung'
    wording must not appear for any of them."""
    lines = _summary_lines(tax_year)
    assert not any("ggf. Verlustbegrenzung" in line for line in lines)
    assert any("ohne Verlustbegrenzung): -25000.00" in line for line in lines)


@pytest.mark.parametrize("tax_year", [2021, 2024, 2025])
def test_repeal_note_states_all_open_cases_not_a_start_year(tax_year):
    """The note must not read "ab {Jahr} aufgehoben": the repeal is not dated
    from the assessment year being processed, it applies to all open cases."""
    lines = _summary_lines(tax_year)
    note = [line for line in lines if "Verlustverrechnungsbeschränkung" in line]
    assert note, "the repeal note is missing"
    joined = " ".join(note)
    assert f"ab {tax_year}" not in joined
    assert "JStG 2024" in joined


@pytest.mark.parametrize("tax_year", [2021, 2022, 2023, 2024])
def test_zeile_24_cross_check_survives_for_years_whose_form_has_it(tax_year):
    """Z24 exists on the VZ<=2024 form and is still populated, so the console
    cross-check must be keyed to the form structure, not to the repealed cap."""
    lines = _summary_lines(tax_year)
    assert any("Zeile 24 deklarierte Verluste" in line and "25000.00" in line
               for line in lines)


def test_no_zeile_24_cross_check_for_2025():
    """VZ 2025 has no Zeile 24 — printing a cross-check against it would be
    reporting a line that is not on the form."""
    lines = _summary_lines(2025)
    assert not any("Zeile 24 deklarierte Verluste" in line for line in lines)

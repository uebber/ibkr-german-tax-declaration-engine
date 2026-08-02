"""
The PDF must not certify an End-of-Year reconciliation it never performed.

`main.py` hands `PdfReportGenerator` a hardcoded empty `eoy_mismatch_details`,
and `_add_eoy_reconciliation` printed "Alle berechneten Endbestände stimmen mit
den gemeldeten Endbeständen überein." whenever that list was empty. Since it is
always empty, every PDF ever produced carried the all-clear — including runs
where the engine had just logged the opposite and the console had just warned
about it. Pre-existing; surfaced while reviewing the data-gap channel, which
builds exactly the per-asset detail the section was missing.

legal_basis: infrastructure. No declared figure changes. What changes is
whether the report tells the taxpayer that a figure may be wrong: an EoY
quantity mismatch is the signature of a disposal the engine did not process,
so the calculated gains are then short by that disposal's realised gain.
"""
from decimal import Decimal

import pytest
from reportlab.platypus import Paragraph

from src.domain.results import LossOffsettingResult
from src.processing.data_gaps import DataGap
from src.reporting.pdf_generator import PdfReportGenerator

ALL_CLEAR = "Alle berechneten Endbestände stimmen"


def _eoy_section_text(eoy_mismatch_count=0, data_gaps=None) -> str:
    generator = PdfReportGenerator(
        loss_offsetting_result=LossOffsettingResult(),
        all_financial_events=[],
        realized_gains_losses=[],
        vorabpauschale_items=[],
        assets_by_id={},
        tax_year=2025,
        eoy_mismatch_details=None,
        eoy_mismatch_count=eoy_mismatch_count,
        data_gaps=data_gaps,
    )
    generator._add_eoy_reconciliation()
    return "\n".join(p.text for p in generator.story if isinstance(p, Paragraph))


def test_clean_run_still_reports_the_all_clear():
    text = _eoy_section_text(eoy_mismatch_count=0)
    assert ALL_CLEAR in text


def test_mismatch_count_suppresses_the_all_clear():
    """The defect in one assertion: a run with mismatches must not tell the
    reader every end balance agrees with the broker."""
    text = _eoy_section_text(eoy_mismatch_count=2)
    assert ALL_CLEAR not in text
    assert "ACHTUNG" in text
    assert "2" in text


def test_recorded_gaps_supply_the_per_asset_detail():
    gaps = [
        DataGap(code="EOY_QTY_MISMATCH", subject="ACME INC",
                detail="Berechnete EoY-Stückzahl 320 weicht von der gemeldeten (0) ab."),
        DataGap(code="VP_NAV_MISSING", subject="SOME FUND", detail="irrelevant hier"),
    ]
    text = _eoy_section_text(eoy_mismatch_count=1, data_gaps=gaps)
    assert "ACME INC" in text and "320" in text
    assert "SOME FUND" not in text, "only EoY gaps belong in the EoY section"


def test_mismatch_without_detail_says_so_rather_than_staying_silent():
    text = _eoy_section_text(eoy_mismatch_count=1, data_gaps=[])
    assert ALL_CLEAR not in text
    assert "Log-Ausgabe" in text


def test_structured_details_still_render_the_table():
    """The pre-existing table path is untouched — it is simply unreachable from
    production today, because the engine returns a count and not rows."""
    generator = PdfReportGenerator(
        loss_offsetting_result=LossOffsettingResult(),
        all_financial_events=[],
        realized_gains_losses=[],
        vorabpauschale_items=[],
        assets_by_id={},
        tax_year=2025,
        eoy_mismatch_details=[{
            "asset_description": "ACME INC", "asset_identifier": "US0000000001",
            "calculated_eoy_quantity": Decimal("320"),
            "reported_eoy_quantity": Decimal("0"),
            "difference": Decimal("320"),
        }],
        eoy_mismatch_count=1,
    )
    generator._add_eoy_reconciliation()
    texts = [p.text for p in generator.story if isinstance(p, Paragraph)]
    assert ALL_CLEAR not in " ".join(texts)
    assert any(not isinstance(item, Paragraph) for item in generator.story), \
        "the mismatch table is missing"

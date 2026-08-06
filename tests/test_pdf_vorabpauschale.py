"""The PDF must show the Vorabpauschale it declares, for the year it declares.

legal_basis: GT-INVSTG-012 and GT-INVSTG-014 — the VZ Y return carries the
Vorabpauschale computed for calendar Y-1, because 18 Abs. 3 InvStG deems it to
flow on the first working day of Y. See
reference/investment-tax-law/invstg-18-vorabpauschale.md and
docs/legal-implementation-map.md.

`9f5a92e` renamed `VorabpauschaleData.tax_year` to `vorabpauschale_year` and
derived `declaration_year` from it, precisely because the old name invited the
year confusion. The console reporter and `loss_offsetting` were both moved onto
`declaration_year`; the PDF's detail section was not, and still read the field
that no longer exists. Nothing caught it because no test rendered the section
with a Vorabpauschale record in it, and on this repository's own data no run
produced one — every fund there is retyped at classification, and retyping lost
the prior-year snapshot, so the list was always empty.

The rename is not the whole requirement. Selecting on `vorabpauschale_year ==
tax_year` would raise nothing and show nothing: the records the engine builds
are for `tax_year - 1`. The section has to select the same records the figure on
Zeilen 9-13 is built from, which is what `declaration_year` means.
"""
import uuid
from decimal import Decimal

from reportlab.platypus import Paragraph

from src.domain.assets import InvestmentFund
from src.domain.enums import InvestmentFundType, TaxReportingCategory
from src.domain.results import LossOffsettingResult, VorabpauschaleData
from src.reporting.pdf_generator import PdfReportGenerator
from tests.support.base import FifoTestCaseBase


TAX_YEAR = 2025
FUND_ID = uuid.uuid4()
SONSTIGE_LINE = (
    TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO,
    "Zeile 13",
    "Sonstige Fonds Vorabpauschale",
    Decimal("160.30"),
)


def _vp_item(vorabpauschale_year: int, gross: Decimal) -> VorabpauschaleData:
    return VorabpauschaleData(
        asset_internal_id=FUND_ID,
        vorabpauschale_year=vorabpauschale_year,
        fund_value_start_year_eur=Decimal("10000"),
        fund_value_end_year_eur=Decimal("11000"),
        distributions_during_year_eur=Decimal("0"),
        base_return_rate=Decimal("0.0229"),
        basiszins=Decimal("2.29"),
        calculated_base_return_eur=gross,
        gross_vorabpauschale_eur=gross,
        fund_type=InvestmentFundType.SONSTIGE_FONDS,
        teilfreistellung_rate_applied=Decimal("0"),
        teilfreistellung_amount_eur=Decimal("0"),
        net_taxable_vorabpauschale_eur=gross,
        tax_reporting_category_gross=SONSTIGE_LINE[0],
    )


def _generator(vorabpauschale_items):
    fund = InvestmentFund(
        internal_asset_id=FUND_ID,
        fund_type=InvestmentFundType.SONSTIGE_FONDS,
        description="XYZ1 BOND INDEX",
        currency="EUR",
        ibkr_isin="LU0000000001",
        ibkr_symbol="XYZ1",
    )
    return PdfReportGenerator(
        loss_offsetting_result=LossOffsettingResult(),
        all_financial_events=[],
        realized_gains_losses=[],
        vorabpauschale_items=vorabpauschale_items,
        assets_by_id={FUND_ID: fund},
        tax_year=TAX_YEAR,
        eoy_mismatch_details=None,
        eoy_mismatch_count=0,
    )


def _flatten(flowable, parts):
    """Collect the rendered text of a flowable. Tables are wrapped in
    `KeepTogether`, so the walk has to recurse rather than look at the top
    level only — the itemised figures live in the table, not the headings."""
    if isinstance(flowable, Paragraph):
        parts.append(flowable.text)
    elif hasattr(flowable, "_cellvalues"):  # Table
        for row in flowable._cellvalues:
            for cell in row:
                _flatten(cell, parts) if hasattr(cell, "text") else parts.append(str(cell))
    for attr in ("_content", "_flowables"):
        for child in getattr(flowable, attr, None) or []:
            _flatten(child, parts)


def _detail_text(vorabpauschale_items) -> str:
    generator = _generator(vorabpauschale_items)
    generator._add_vorabpauschale_details([SONSTIGE_LINE])
    parts = []
    for flowable in generator.story:
        _flatten(flowable, parts)
    return "\n".join(parts)


def test_the_declared_vorabpauschale_is_itemised():
    """The VZ 2025 PDF itemises the Vorabpauschale computed for calendar 2024."""
    text = _detail_text([_vp_item(vorabpauschale_year=2024, gross=Decimal("160.30"))])

    assert "LU0000000001" in text, "the fund owing the Vorabpauschale is not listed"
    assert "160,30" in text or "160.30" in text, "its gross figure is not shown"


def test_a_vorabpauschale_for_a_later_year_is_not_itemised_here():
    """The Vorabpauschale computed for calendar 2025 flows on the first working
    day of 2026 (18 Abs. 3 InvStG) and belongs on the VZ 2026 return, not this
    one. Selecting on the computation year instead of the declaration year would
    put it here — and would drop the 2024 figure that belongs here."""
    text = _detail_text([_vp_item(vorabpauschale_year=TAX_YEAR, gross=Decimal("999.99"))])

    assert "999,99" not in text and "999.99" not in text, (
        "a Vorabpauschale deemed to flow in the following assessment year was "
        "itemised on this return"
    )


def test_the_methodology_note_names_the_year_the_figure_was_computed_for():
    """"Vorabpauschale für 2025" on a VZ 2025 report is wrong: the figure is the
    one for calendar 2024."""
    generator = _generator([_vp_item(vorabpauschale_year=2024, gross=Decimal("160.30"))])
    generator._add_data_sources_notes()
    text = "\n".join(p.text for p in generator.story if isinstance(p, Paragraph))

    notes = [line for line in text.splitlines() if "Vorabpauschale" in line]
    assert notes, "the methodology note no longer mentions the Vorabpauschale"
    vorabpauschale_note = notes[0]
    assert "Vorabpauschale für 2024" in vorabpauschale_note, (
        f"the note attributes the figure to the wrong year: {vorabpauschale_note!r}"
    )
    # The note makes a second claim, and it is the one 18 Abs. 3 fixes: the
    # Vorabpauschale for calendar 2024 is deemed to flow on the first working day
    # of 2025. Both halves are printed for the taxpayer, so both are asserted.
    assert "ersten Werktag 2025" in vorabpauschale_note, (
        f"the note names the wrong Zuflussjahr: {vorabpauschale_note!r}"
    )


class TestVorabpauschaleFromARealRunReachesThePdf(FifoTestCaseBase):
    """The crash on the whole path, not just at the section.

    The tests above hand the section a `VorabpauschaleData` directly. This one
    earns the record: an instrument whose description says "ETF" is classified
    `INVESTMENT_FUND` by the preliminary heuristic and is therefore *created* as
    one. `needs_type_replacement` is set only where the Python type differs, so
    it is never retyped, never passes through the field copy, and keeps its
    prior-year snapshot — which is why it produces a Vorabpauschale on the base
    branch, where a fund that *is* retyped produces none.

    That makes this the realistic case for the AttributeError rather than a
    constructed one: the record exists, Zeile 13 carries a total, and rendering
    the KAP-INV section is what a `--report-tax-declaration` run does next.
    """

    ISIN = "LU0000000002"
    CONID = "900002"

    def _position_row(self, quantity, mark_price, position_value):
        return ["U1234567", "EUR", "STK", "", "XYZ2", "XYZ2 ETF INDEX",
                self.ISIN, quantity, position_value, mark_price, "10000",
                "", self.CONID, "", "1"]

    def _acquisition_row(self, trade_date, quantity, price):
        """The purchase behind the holding. Without it the reconstruction is
        empty, the ledger falls back to a lot with an invented acquisition date,
        and 18 Abs. 2 refuses to compute — so no record would reach the PDF and
        this test would pass for the wrong reason."""
        return ["U1234567", "EUR", "STK", "", "XYZ2", "XYZ2 ETF INDEX",
                self.ISIN, "", "", "", trade_date, quantity, price, "0", "EUR",
                "BUY", f"TX{trade_date.replace('-', '')}", "", "", self.CONID,
                "", "1", "O"]

    def test_a_fund_created_as_a_fund_renders_instead_of_crashing(self):
        results = self._run_pipeline(
            trades_data=[self._acquisition_row("2023-03-15", "100", "90")],
            tax_year=TAX_YEAR,
            positions_prior_start_data=[self._position_row("100", "100", "10000")],
            positions_prior_end_data=[self._position_row("100", "110", "11000")],
            positions_start_data=[self._position_row("100", "110", "11000")],
            positions_end_data=[self._position_row("100", "110", "11000")],
        )

        assert len(results.vorabpauschale_items) == 1, (
            "an instrument described as an ETF is created as a fund and keeps its "
            "prior-year snapshot, so it must produce a Vorabpauschale record"
        )
        record = results.vorabpauschale_items[0]

        loss_offsetting_result = LossOffsettingResult()
        loss_offsetting_result.form_line_values[SONSTIGE_LINE[0]] = \
            record.gross_vorabpauschale_eur

        generator = PdfReportGenerator(
            loss_offsetting_result=loss_offsetting_result,
            all_financial_events=[],
            realized_gains_losses=[],
            vorabpauschale_items=results.vorabpauschale_items,
            assets_by_id=results.asset_resolver.assets_by_internal_id,
            tax_year=TAX_YEAR,
            eoy_mismatch_details=None,
            eoy_mismatch_count=0,
        )
        # The line total must be non-zero to reach the itemisation at all --
        # _add_vorabpauschale_details returns early on a zero line, before the
        # filter that raises. A probe with empty totals passes and proves nothing.
        assert loss_offsetting_result.form_line_values[SONSTIGE_LINE[0]] > Decimal("0")

        generator._add_kap_inv_summary_detailed()

        parts = []
        for flowable in generator.story:
            _flatten(flowable, parts)
        assert self.ISIN in "\n".join(parts), (
            "the fund owing the Vorabpauschale is not itemised in the report"
        )

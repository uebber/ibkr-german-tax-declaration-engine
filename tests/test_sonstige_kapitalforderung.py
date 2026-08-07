"""
Sonstige Kapitalforderungen under § 20 Abs. 2 Satz 1 Nr. 7 that are NOT bonds.

legal_basis: GT-ESTG23-011 and GT-ESTG20-038.

  - BMF 14.05.2025 Rz. 57 [GT-ESTG23-011]: a commodity Inhaberschuldverschreibung is a
    Sachleistungsanspruch — and therefore a § 23 asset — only where the issuer must invest
    the capital almost entirely in the commodity AND the holder's claim is exclusively to
    delivery of the deposited commodity or to the proceeds of its sale. Where it is not
    backed that way, the disposal is § 20 Abs. 2 Satz 1 Nr. 7 income. The store's own
    conclusion is that this "cannot be read off an asset class label".
  - BMF 14.05.2025 Rz. 9 [GT-ESTG20-038]: "Zertifikate und Optionsscheine gehören nicht zu
    den Termingeschäften". So a Zertifikat, and an unallocated spot metal position treated
    like one (open question Q11, Reading C), is not on the Termingeschäft lines either.

Form lines, identical to a bond's — see reference/tax-forms/anlage-kap-zeilen.md:
  - Gain → ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE (Zeile 19 component)
  - Loss → ANLAGE_KAP_SONSTIGE_VERLUSTE         (Zeile 22)

**Why a separate AssetCategory rather than reusing BOND**, which lands on the same lines:
the two are unrelated instruments and BOND carries bond-only handling. The decisive one is
`domain_event_factory`'s percentage-of-nominal rule — a bond's trade price is a percentage
of par and its gross is divided by 100. Applied to an ETC or a spot metal position, that
understates proceeds and cost by two orders of magnitude. `test_price_is_not_read_as_a_percentage_of_nominal`
is the test that separates the two categories rather than merely counting them.
"""

import contextlib
import io
import uuid
from decimal import Decimal

import pytest
from reportlab.platypus import Paragraph

from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import Bond, SonstigeKapitalforderung
from src.domain.enums import (
    AssetCategory,
    InvestmentFundType,
    RealizationType,
    TaxReportingCategory,
)
from src.engine.loss_offsetting import LossOffsettingEngine

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.expected import (
    ScenarioExpectedOutput,
    ExpectedRealizedGainLoss,
    ExpectedAssetEoyState,
)


ACCOUNT = "U_SK_TEST"

# An unallocated spot metal position arrives from IBKR exactly like this: AssetClass
# "CMDTY", a symbol, and no ISIN. With no ISIN the classification key falls back to the
# Conid (src/domain/assets.py get_classification_key).
SYMBOL = "XAGUSD"
CONID = "CON_XAGUSD"
CACHE_KEY = f"CONID:{CONID}"


def _cmdty_trade_row(date, quantity, price, direction, tx_id,
                     commission="0", currency="EUR", open_close="O"):
    """A trades CSV row for a CMDTY instrument. No ISIN, as the broker reports none."""
    return [
        ACCOUNT, currency, "CMDTY", "",
        SYMBOL, f"{SYMBOL} Spot Silver", "",
        "", "", "",        # Strike, Expiry, Put/Call
        date,
        str(quantity), str(price), str(commission), currency,
        direction, tx_id, "", "", CONID, "", "1", open_close,
    ]


def _cmdty_soy_row(quantity, cost_basis, currency="EUR"):
    """
    Start-of-year positions row, so the historically replayed lots survive: an asset
    absent from the SOY snapshot is reset to quantity 0 and its lots dropped.
    """
    return [
        ACCOUNT, currency, "CMDTY", "",
        SYMBOL, f"{SYMBOL} Spot Silver", "",
        str(quantity), "0", "100", str(cost_basis),
        "", CONID, "", "1",
    ]


def _form_lines(results, tax_year):
    engine = LossOffsettingEngine(
        realized_gains_losses=results.realized_gains_losses,
        vorabpauschale_items=results.vorabpauschale_items,
        current_year_financial_events=results.processed_income_events,
        asset_resolver=results.asset_resolver,
        tax_year=tax_year,
    )
    return engine.calculate_reporting_figures().form_line_values


class TestSonstigeKapitalforderungIsClassifiable:
    """The category has to be reachable, and reachable only the one honest way."""

    def test_a_dialog_option_routes_to_the_category(self):
        classifier = AssetClassifier(cache_file_path="/tmp/does-not-exist/never-written.json")
        matching = [
            opt for opt in classifier._dialog_options
            if opt[1] == AssetCategory.SONSTIGE_KAPITALFORDERUNG
        ]
        assert len(matching) == 1, (
            "Exactly one classification dialog option must lead to "
            "SONSTIGE_KAPITALFORDERUNG; without it the category is unreachable and a "
            "CMDTY instrument still aborts the run as UNKNOWN."
        )
        display_name, _, fund_type = matching[0]
        assert fund_type == InvestmentFundType.NONE
        # The option has to be choosable by someone who has just decided the instrument is
        # NOT a §23 asset, which is the decision Rz. 57 actually poses.
        assert "Nr. 7" in display_name

    def test_the_category_builds_its_own_asset_type(self):
        classifier = AssetClassifier(cache_file_path="/tmp/does-not-exist/never-written.json")
        assert classifier._get_python_type_for_category(
            AssetCategory.SONSTIGE_KAPITALFORDERUNG
        ) is SonstigeKapitalforderung

    @pytest.mark.parametrize(
        "asset_class,sub_category,description,symbol",
        [
            ("CMDTY", "", "XAGUSD Spot Silver", "XAGUSD"),
            ("STK", "", "SOME ISSUER GOLD ETC", "GLDETC"),
            ("STK", "COMMON", "SOME ISSUER TURBO ZERTIFIKAT", "ZERT1"),
        ],
    )
    def test_it_is_never_a_preliminary_classification(
        self, asset_class, sub_category, description, symbol
    ):
        """
        [GT-ESTG23-011]: the deciding facts are physical backing and an exclusive delivery
        or proceeds claim, both of which live in the Emissionsbedingungen. The store states
        the classification "cannot be read off an asset class label", so no heuristic may
        put an instrument in this category — it has to be asked. This test fails the moment
        someone adds one.
        """
        classifier = AssetClassifier(cache_file_path="/tmp/does-not-exist/never-written.json")
        category, _ = classifier.preliminary_classify(
            asset_class, sub_category, description, symbol
        )
        assert category != AssetCategory.SONSTIGE_KAPITALFORDERUNG


class TestSonstigeKapitalforderungReporting(FifoTestCaseBase):

    def test_gain_feeds_zeile_19(self, mock_config_paths):
        """
        BUY 100 units @ 20.00 in 2022, SELL 100 @ 23.00 in 2023.
        Cost = 2000.00, proceeds = 2300.00, gain = 300.00 → Zeile 19, not Zeile 22,
        and not the Termingeschäft lines (Rz. 9 excludes them).
        """
        tax_year = 2023
        self.seed_classification(CACHE_KEY, AssetCategory.SONSTIGE_KAPITALFORDERUNG.name,
                                 note="unbacked, no delivery claim (Rz. 57)")
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        results = self._run_pipeline(
            trades_data=[
                _cmdty_trade_row("2022-06-01", 100, "20.00", "BUY", "TX_SK_BUY_1"),
                _cmdty_trade_row("2023-05-02", -100, "23.00", "SELL", "TX_SK_SELL_1",
                                 open_close="C"),
            ],
            positions_start_data=[_cmdty_soy_row(quantity=100, cost_basis="2000")],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, ScenarioExpectedOutput(
            test_description="Sonstige Kapitalforderung disposed at a gain",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=SYMBOL,
                    realization_date="2023-05-02",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("2000.00"),
                    total_realization_value_eur=Decimal("2300.00"),
                    gross_gain_loss_eur=Decimal("300.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                    asset_category_at_realization=AssetCategory.SONSTIGE_KAPITALFORDERUNG.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=SYMBOL, eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        ))

        form = _form_lines(results, tax_year)
        assert form.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE,
                        Decimal("0.00")) == Decimal("300.00")
        assert form.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE,
                        Decimal("0.00")) == Decimal("0.00")
        # Rz. 9: not a Termingeschäft. Up to VZ 2024 those are separate lines, so an
        # instrument wrongly routed there would show here.
        assert form.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN,
                        Decimal("0.00")) == Decimal("0.00")
        # Rz. 57: no physical backing, so not Anlage SO either.
        assert form.get("ANLAGE_SO_Z54_NET_GV", Decimal("0.00")) == Decimal("0.00")

    def test_loss_feeds_zeile_22(self, mock_config_paths):
        """BUY 100 @ 20.00 in 2022, SELL 100 @ 18.50 in 2023 → loss of 150.00 on Zeile 22."""
        tax_year = 2023
        self.seed_classification(CACHE_KEY, AssetCategory.SONSTIGE_KAPITALFORDERUNG.name,
                                 note="unbacked, no delivery claim (Rz. 57)")
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        results = self._run_pipeline(
            trades_data=[
                _cmdty_trade_row("2022-06-01", 100, "20.00", "BUY", "TX_SK_BUY_2"),
                _cmdty_trade_row("2023-05-02", -100, "18.50", "SELL", "TX_SK_SELL_2",
                                 open_close="C"),
            ],
            positions_start_data=[_cmdty_soy_row(quantity=100, cost_basis="2000")],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, ScenarioExpectedOutput(
            test_description="Sonstige Kapitalforderung disposed at a loss",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier=SYMBOL,
                    realization_date="2023-05-02",
                    quantity_realized=Decimal("100"),
                    total_cost_basis_eur=Decimal("2000.00"),
                    total_realization_value_eur=Decimal("1850.00"),
                    gross_gain_loss_eur=Decimal("-150.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                    asset_category_at_realization=AssetCategory.SONSTIGE_KAPITALFORDERUNG.name,
                    tax_reporting_category=TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE.name,
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier=SYMBOL, eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        ))

        form = _form_lines(results, tax_year)
        assert form.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE,
                        Decimal("0.00")) == Decimal("150.00")
        assert form.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE,
                        Decimal("0.00")) == Decimal("0.00")
        # Not a derivative loss: no ring-fencing and no pre-2025 cap.
        assert form.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST,
                        Decimal("0.00")) == Decimal("0.00")

    def test_price_is_not_read_as_a_percentage_of_nominal(self, mock_config_paths):
        """
        The reason the category exists rather than reusing BOND.

        `domain_event_factory` divides a bond's computed gross by 100, because a bond price
        is quoted as a percentage of par. A spot metal price is not. Classified BOND, the
        same trades would produce a cost of 20.00 and proceeds of 23.00 — a gain of 3.00
        instead of 300.00, a figure that is wrong by two orders of magnitude and entirely
        plausible on the form.

        The gross is computed from quantity and price here, not taken from TradeMoney, so
        the percentage rule is the only thing that can move it: the trade rows carry no
        proceeds column value.
        """
        tax_year = 2023
        self.seed_classification(CACHE_KEY, AssetCategory.SONSTIGE_KAPITALFORDERUNG.name)
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        results = self._run_pipeline(
            trades_data=[
                _cmdty_trade_row("2022-06-01", 100, "20.00", "BUY", "TX_SK_BUY_3"),
                _cmdty_trade_row("2023-05-02", -100, "23.00", "SELL", "TX_SK_SELL_3",
                                 open_close="C"),
            ],
            positions_start_data=[_cmdty_soy_row(quantity=100, cost_basis="2000")],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        asset = results.asset_resolver.get_asset_by_id(
            results.realized_gains_losses[0].asset_internal_id
        )
        assert isinstance(asset, SonstigeKapitalforderung)
        assert not isinstance(asset, Bond), (
            "A sonstige Kapitalforderung must not be modelled as a Bond: the bond-only "
            "handling (percentage-of-nominal prices, Stückzinsen, BM maturity) does not "
            "apply to it."
        )

        rgl = results.realized_gains_losses[0]
        assert rgl.total_cost_basis_eur == Decimal("2000.00"), (
            "Cost basis was divided by 100 — the bond percentage-of-nominal rule reached "
            "an instrument that is not a bond."
        )
        assert rgl.total_realization_value_eur == Decimal("2300.00")

    def test_it_shares_zeile_19_with_bonds_without_becoming_one(self, mock_config_paths):
        """
        Both categories add to the same Zeile 19 total — that is the point of the routing —
        while staying separately identifiable in the RGL stream, which is what the console
        and PDF breakdowns key off. A re-key that collapsed one into the other would keep
        the total right and lose the distinction, so both halves are asserted.
        """
        tax_year = 2023
        bond_symbol, bond_isin = "TBONDSK", "DE000TESTSK01"
        self.seed_classification(CACHE_KEY, AssetCategory.SONSTIGE_KAPITALFORDERUNG.name)
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        bond_buy = [
            ACCOUNT, "EUR", "BOND", "Govt",
            bond_symbol, f"{bond_symbol} Bond", bond_isin,
            "", "", "",
            "2022-06-01",
            "1000", "98.00", "0", "EUR",
            "BUY", "TX_SK_BOND_BUY", "", "", f"CON_{bond_symbol}", "", "1", "O",
        ]
        bond_sell = [
            ACCOUNT, "EUR", "BOND", "Govt",
            bond_symbol, f"{bond_symbol} Bond", bond_isin,
            "", "", "",
            "2023-05-02",
            "-1000", "99.00", "0", "EUR",
            "SELL", "TX_SK_BOND_SELL", "", "", f"CON_{bond_symbol}", "", "1", "C",
        ]
        bond_soy = [
            ACCOUNT, "EUR", "BOND", "Govt",
            bond_symbol, f"{bond_symbol} Bond", bond_isin,
            "1000", "0", "100", "980",
            "", f"CON_{bond_symbol}", "", "1",
        ]

        results = self._run_pipeline(
            trades_data=[
                _cmdty_trade_row("2022-06-01", 100, "20.00", "BUY", "TX_SK_BUY_4"),
                _cmdty_trade_row("2023-05-02", -100, "23.00", "SELL", "TX_SK_SELL_4",
                                 open_close="C"),
                bond_buy,
                bond_sell,
            ],
            positions_start_data=[
                _cmdty_soy_row(quantity=100, cost_basis="2000"),
                bond_soy,
            ],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        by_category = {}
        for rgl in results.realized_gains_losses:
            by_category.setdefault(rgl.asset_category_at_realization, Decimal("0"))
            by_category[rgl.asset_category_at_realization] += rgl.gross_gain_loss_eur

        # Bond: (1000 * 99.00 / 100) - (1000 * 98.00 / 100) = 990.00 - 980.00 = 10.00
        assert by_category[AssetCategory.BOND] == Decimal("10.00")
        assert by_category[AssetCategory.SONSTIGE_KAPITALFORDERUNG] == Decimal("300.00")

        form = _form_lines(results, tax_year)
        assert form.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE,
                        Decimal("0.00")) == Decimal("310.00")


# =============================================================================
# The ends of the channel.
#
# CLAUDE.md, "Where the suite is blind": when a new channel is added, its
# recording sites and its report-rendering block can each be deleted with the
# suite green. Probe the ends, not the middle. The engine half above is covered
# — deleting the loss-offsetting route reddens 3 tests and the FIFO dispatch 2 —
# but before these tests, deleting the console label block, the console
# component line, or the whole PDF section left all 796 tests passing.
# =============================================================================


class _SingleAssetResolver:
    """Minimal resolver: the reporters only ask it to name an asset."""

    def __init__(self, asset):
        self._asset = asset
        self.assets_by_internal_id = {asset.internal_asset_id: asset}

    def get_asset_by_id(self, internal_id):
        return self._asset if internal_id == self._asset.internal_asset_id else None


def _rgl(asset_id, category, gross):
    from src.domain.results import RealizedGainLoss

    return RealizedGainLoss(
        originating_event_id=uuid.uuid4(),
        asset_internal_id=asset_id,
        asset_category_at_realization=category,
        acquisition_date="2022-06-01",
        realization_date="2023-05-02",
        realization_type=RealizationType.LONG_POSITION_SALE,
        quantity_realized=Decimal("100"),
        unit_cost_basis_eur=Decimal("20.00"),
        unit_realization_value_eur=Decimal("20.00") + gross / Decimal("100"),
        total_cost_basis_eur=Decimal("2000.00"),
        total_realization_value_eur=Decimal("2000.00") + gross,
        gross_gain_loss_eur=gross,
    )


def _spot_metal_asset():
    return SonstigeKapitalforderung(
        description="XAGUSD Spot Silver",
        currency="EUR",
        ibkr_symbol=SYMBOL,
        ibkr_conid=CONID,
    )


def _console_text(rgls, asset) -> str:
    from src.domain.results import LossOffsettingResult
    from src.reporting.console_reporter import generate_console_tax_report

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        generate_console_tax_report(
            rgls, [], [], _SingleAssetResolver(asset), 2023, 0, LossOffsettingResult()
        )
    return buffer.getvalue()


def _flatten(flowable, parts):
    if isinstance(flowable, Paragraph):
        parts.append(flowable.text)
    elif hasattr(flowable, "_cellvalues"):  # Table
        for row in flowable._cellvalues:
            for cell in row:
                _flatten(cell, parts) if hasattr(cell, "text") else parts.append(str(cell))
    for attr in ("_content", "_flowables"):
        for child in getattr(flowable, attr, None) or []:
            _flatten(child, parts)


def _pdf_kap_text(rgls, asset) -> str:
    from src.domain.results import LossOffsettingResult
    from src.reporting.pdf_generator import PdfReportGenerator

    generator = PdfReportGenerator(
        loss_offsetting_result=LossOffsettingResult(),
        all_financial_events=[],
        realized_gains_losses=rgls,
        vorabpauschale_items=[],
        assets_by_id={asset.internal_asset_id: asset},
        tax_year=2023,
        eoy_mismatch_details=None,
        eoy_mismatch_count=0,
    )
    generator._add_kap_details()
    parts = []
    for flowable in generator.story:
        _flatten(flowable, parts)
    return "\n".join(parts)


class TestTheDisposalReachesTheReports:
    """A figure that reaches Zeile 19 but appears in no breakdown is unauditable."""

    def test_the_console_names_the_category_apart_from_bonds(self):
        asset = _spot_metal_asset()
        text = _console_text(
            [_rgl(asset.internal_asset_id, AssetCategory.SONSTIGE_KAPITALFORDERUNG,
                  Decimal("300.00"))],
            asset,
        )
        assert "sonstiger Kapitalforderungen" in text, (
            "the per-asset breakdown has no section for the category, so the "
            "disposal is invisible on the console"
        )
        assert SYMBOL in text or "Spot Silver" in text
        assert "Anleihenveräußerungen" not in text, (
            "a spot metal position was reported under the bond heading"
        )

    def test_the_console_lists_the_gain_among_the_zeile_19_components(self):
        asset = _spot_metal_asset()
        text = _console_text(
            [_rgl(asset.internal_asset_id, AssetCategory.SONSTIGE_KAPITALFORDERUNG,
                  Decimal("300.00"))],
            asset,
        )
        component = [
            line for line in text.splitlines()
            if "Gewinne aus sonstigen Kapitalforderungen" in line
        ]
        assert component, (
            "the Zeile 19 component breakdown omits the category, so its "
            "components no longer add up to the declared figure"
        )
        assert "300.00" in component[0]
        total = [line for line in text.splitlines()
                 if "Summe dieser positiven Komponenten" in line]
        assert total and "300.00" in total[0]

    def test_the_console_component_line_is_absent_when_nothing_lands_there(self):
        """A constant-zero line for a category almost no account holds is noise,
        and its absence is what keeps the report byte-identical for everyone
        else. The total still has to be printed."""
        asset = _spot_metal_asset()
        text = _console_text([_rgl(asset.internal_asset_id, AssetCategory.BOND,
                                   Decimal("10.00"))], asset)
        assert "Gewinne aus sonstigen Kapitalforderungen" not in text
        assert "Summe dieser positiven Komponenten" in text

    def test_the_pdf_itemises_the_disposal_in_its_own_section(self):
        asset = _spot_metal_asset()
        text = _pdf_kap_text(
            [_rgl(asset.internal_asset_id, AssetCategory.SONSTIGE_KAPITALFORDERUNG,
                  Decimal("300.00"))],
            asset,
        )
        assert "sonstigen Kapitalforderungen" in text, (
            "the PDF has no section for the category"
        )
        assert "300,00" in text or "300.00" in text, "its gross figure is not shown"
        assert "Keine Anleihenveräußerungen in diesem Steuerjahr." in text, (
            "the bond section must still report itself empty — the disposal "
            "belongs in its own section, not folded into that one"
        )

    def test_the_pdf_section_is_absent_when_nothing_lands_there(self):
        asset = _spot_metal_asset()
        text = _pdf_kap_text([_rgl(asset.internal_asset_id, AssetCategory.BOND,
                                   Decimal("10.00"))], asset)
        assert "sonstigen Kapitalforderungen" not in text

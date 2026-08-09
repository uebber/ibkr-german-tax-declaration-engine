"""Anlage KAP-INV Zeile 53 -- the § 19 Abs. 1 Satz 3 Vorabpauschale deduction.

legal_basis: GT-INVSTG-030 (Abs. 1 Saetze 3-4 verbatim: the gain is reduced by the
Vorabpauschalen *angesetzt* during the holding period, gross of Teilfreistellung),
GT-INVSTG-033 and GT-FORM-033 (the line is 53, not 55), GT-INVSTG-034 (units that
never bore inlaendischer Steuerabzug are deductible only so far as they were
brought to tax, and that must be demonstrated), GT-INVSTG-011 (§ 18 Abs. 2, the
twelfths that weight a tranche). See
reference/investment-tax-law/invstg-19-veraeusserungsgewinne.md and
docs/legal-implementation-map.md.

Three properties are pinned here, because each is a way the figure goes wrong
silently:

* the deduction **follows the lot**, so a partial disposal takes the tranches FIFO
  consumed and nothing else;
* what is deducted is what was **declared**, never what the engine recomputes today
  -- for a year of the holding period with no declaration record it deducts nothing
  and says so;
* the Teilfreistellung is applied to the gain **after** the deduction (Satz 4).
"""
import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.domain.enums import (
    AssetCategory, InvestmentFundType, RealizationType, TaxReportingCategory,
)
from src.domain.events import TradeEvent
from src.domain.exceptions import ProcessingError
from src.domain.results import RealizedGainLoss
from src.engine.fifo_manager import FifoLedger, FifoLot
from src.engine.loss_offsetting import LossOffsettingEngine
from src.engine.vorabpauschale_attribution import (
    abs2_retained_twelfths, distribute_declared_vorabpauschale,
)
from src.identification.asset_resolver import AssetResolver
from src.processing.data_gaps import DataGapCollector, GapSeverity
from src.processing.vorabpauschale_declarations import (
    DeclarationStatus, DeclaredVorabpauschale, VorabpauschaleDeclarationStore,
    prompt_for_declared_vorabpauschale,
)
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider
import src.config as config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lot(acquisition_date: str, quantity: str, unit_cost: str = "10",
         tx: str = "T1", known: bool = True, vp: str = "0") -> FifoLot:
    q = Decimal(quantity)
    return FifoLot(
        acquisition_date=acquisition_date, quantity=q,
        unit_cost_basis_eur=Decimal(unit_cost),
        total_cost_basis_eur=q * Decimal(unit_cost),
        source_transaction_id=tx,
        acquisition_date_is_known=known,
        vorabpauschale_gross_eur=Decimal(vp),
    )


def _fund_ledger(asset_id=None) -> FifoLedger:
    return FifoLedger(
        asset_internal_id=asset_id or uuid.uuid4(),
        asset_category=AssetCategory.INVESTMENT_FUND,
        asset_multiplier_from_asset=None,
        currency_converter=MagicMock(spec=CurrencyConverter),
        exchange_rate_provider=MagicMock(spec=ECBExchangeRateProvider),
        internal_working_precision=28, decimal_rounding_mode="ROUND_HALF_UP",
        fund_type=InvestmentFundType.AKTIENFONDS,
    )


def _sale(asset_id, quantity: str, proceeds_eur: str,
          event_date: str = "2025-06-02") -> TradeEvent:
    return TradeEvent(
        asset_internal_id=asset_id,
        event_date=event_date,
        event_type=__import__("src.domain.enums", fromlist=["x"]).FinancialEventType.TRADE_SELL_LONG,
        quantity=-Decimal(quantity),
        price_foreign_currency=Decimal("1"),
        local_currency="EUR",
        ibkr_transaction_id="SALE1",
        gross_amount_foreign_currency=Decimal(proceeds_eur),
        net_proceeds_or_cost_basis_eur=Decimal(proceeds_eur),
    )


def _fund_rgl(*, gross: str, deduction=None, quantity="1",
              category=AssetCategory.INVESTMENT_FUND) -> RealizedGainLoss:
    rgl = RealizedGainLoss(
        originating_event_id=uuid.uuid4(),
        asset_internal_id=uuid.uuid4(),
        asset_category_at_realization=category,
        acquisition_date="2023-02-01",
        realization_date="2025-06-02",
        realization_type=RealizationType.LONG_POSITION_SALE,
        quantity_realized=Decimal(quantity),
        unit_cost_basis_eur=Decimal("100"),
        unit_realization_value_eur=Decimal("150"),
        total_cost_basis_eur=Decimal("100"),
        total_realization_value_eur=Decimal("150"),
        gross_gain_loss_eur=Decimal(gross),
        fund_type_at_sale=(InvestmentFundType.AKTIENFONDS
                           if category == AssetCategory.INVESTMENT_FUND else None),
        vorabpauschale_deduction_eur=(Decimal(deduction) if deduction is not None else None),
        tax_reporting_category=(TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS
                                if category == AssetCategory.INVESTMENT_FUND else None),
    )
    return rgl


# ---------------------------------------------------------------------------
# § 18 Abs. 2: the twelfths that weight a tranche
# ---------------------------------------------------------------------------

class TestAbs2Twelfths:
    """GT-INVSTG-011. The same rule the Vorabpauschale itself applies, reused as
    the distribution key, so the two can never drift apart."""

    def test_units_held_since_before_the_year_keep_twelve(self):
        assert abs2_retained_twelfths(date(2022, 5, 3), 2024) == 12

    def test_january_keeps_twelve_and_december_keeps_one(self):
        assert abs2_retained_twelfths(date(2024, 1, 31), 2024) == 12
        assert abs2_retained_twelfths(date(2024, 12, 1), 2024) == 1

    def test_a_lot_acquired_after_the_year_is_a_programming_error(self):
        with pytest.raises(ProcessingError):
            abs2_retained_twelfths(date(2025, 1, 2), 2024)


# ---------------------------------------------------------------------------
# Distribution of one declared fund-year total across the tranches
# ---------------------------------------------------------------------------

class TestDistributeDeclaredVorabpauschale:
    """The declared annual total is the cap; the engine's own § 18 Abs. 2 split
    is only the key that spreads it over the tranches (issue #63)."""

    def test_two_full_year_tranches_split_by_quantity(self):
        lots = [_lot("2021-03-01", "30", tx="A"), _lot("2022-07-01", "70", tx="B")]
        distributed = distribute_declared_vorabpauschale(
            lots, calendar_year=2024, declared_gross_eur=Decimal("100.00"))
        assert distributed == Decimal("100.00")
        assert lots[0].vorabpauschale_gross_eur == Decimal("30.00")
        assert lots[1].vorabpauschale_gross_eur == Decimal("70.00")

    def test_a_tranche_bought_in_july_carries_half_the_weight_of_an_equal_one(self):
        """Abs. 2: a July acquisition keeps 6/12, so per unit it takes half as much."""
        lots = [_lot("2023-01-01", "100", tx="A"), _lot("2024-07-15", "100", tx="B")]
        distribute_declared_vorabpauschale(
            lots, calendar_year=2024, declared_gross_eur=Decimal("90.00"))
        assert lots[0].vorabpauschale_gross_eur == Decimal("60.00")
        assert lots[1].vorabpauschale_gross_eur == Decimal("30.00")

    def test_the_declared_total_is_distributed_exactly(self):
        """Three equal tranches and a total that does not divide by three: the
        rounding remainder stays inside the fund-year, it is never dropped."""
        lots = [_lot("2020-01-01", "1", tx=f"T{i}") for i in range(3)]
        distributed = distribute_declared_vorabpauschale(
            lots, calendar_year=2024, declared_gross_eur=Decimal("10.00"))
        assert distributed == Decimal("10.00")
        assert sum(l.vorabpauschale_gross_eur for l in lots) == Decimal("10.00")

    def test_years_accumulate_on_the_lot(self):
        lots = [_lot("2021-01-01", "10")]
        distribute_declared_vorabpauschale(lots, calendar_year=2023,
                                           declared_gross_eur=Decimal("5.00"))
        distribute_declared_vorabpauschale(lots, calendar_year=2024,
                                           declared_gross_eur=Decimal("7.00"))
        assert lots[0].vorabpauschale_gross_eur == Decimal("12.00")

    def test_an_invented_acquisition_date_refuses_the_whole_fund_year(self):
        """A lot the replay could not reconstruct carries a placeholder date. Abs. 2
        cannot be applied to it, and the weights of the other tranches cannot be
        normalised without it -- so nothing is attributed and the caller reports it."""
        lots = [_lot("2021-01-01", "10", tx="A"),
                _lot("2023-12-31", "5", tx="B", known=False)]
        with pytest.raises(ProcessingError):
            distribute_declared_vorabpauschale(
                lots, calendar_year=2024, declared_gross_eur=Decimal("10.00"))
        assert all(l.vorabpauschale_gross_eur == Decimal("0") for l in lots)

    def test_no_units_attributes_nothing(self):
        assert distribute_declared_vorabpauschale(
            [], calendar_year=2024, declared_gross_eur=Decimal("10.00")) == Decimal("0")


# ---------------------------------------------------------------------------
# The store of what was declared
# ---------------------------------------------------------------------------

class TestVorabpauschaleDeclarationStore:
    """Third instance of the pattern the classification cache and the fund price
    store already follow: a persisted answer to something nothing can recompute.
    Unlike those two it is **write-once and never auto-written** -- a run before
    filing is not a declaration."""

    def test_round_trip(self, tmp_path):
        path = tmp_path / "declarations.json"
        store = VorabpauschaleDeclarationStore(str(path))
        store.commit("IE00TEST1234", 2023, DeclaredVorabpauschale(
            gross_eur=Decimal("160.30"), declared_on=date(2025, 5, 1),
            source="VZ 2024 Anlage KAP-INV Zeile 9"))
        store.save()

        reloaded = VorabpauschaleDeclarationStore(str(path))
        entry = reloaded.get("IE00TEST1234", 2023)
        assert entry.gross_eur == Decimal("160.30")
        assert entry.declared_on == date(2025, 5, 1)
        assert reloaded.committed_years() == {2023}

    def test_a_second_commit_of_the_same_figure_is_a_no_op(self, tmp_path):
        store = VorabpauschaleDeclarationStore(str(tmp_path / "d.json"))
        entry = DeclaredVorabpauschale(gross_eur=Decimal("10.00"),
                                       declared_on=date(2025, 5, 1), source="x")
        store.commit("K", 2023, entry)
        store.commit("K", 2023, entry)
        assert len(store) == 1

    def test_a_commit_that_would_overwrite_a_different_figure_raises(self, tmp_path):
        """What was declared is what was declared. An amendment is a deliberate
        edit of the file, not a side effect of re-running the engine."""
        store = VorabpauschaleDeclarationStore(str(tmp_path / "d.json"))
        store.commit("K", 2023, DeclaredVorabpauschale(
            gross_eur=Decimal("10.00"), declared_on=date(2025, 5, 1), source="x"))
        with pytest.raises(ProcessingError, match="already"):
            store.commit("K", 2023, DeclaredVorabpauschale(
                gross_eur=Decimal("11.00"), declared_on=date(2026, 5, 1), source="y"))

    def test_an_unreadable_store_raises_rather_than_starting_empty(self, tmp_path):
        path = tmp_path / "d.json"
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(ProcessingError):
            VorabpauschaleDeclarationStore(str(path))

    def test_a_malformed_entry_raises(self, tmp_path):
        path = tmp_path / "d.json"
        path.write_text(json.dumps({"K|2023": {"gross_eur": "10.00"}}), encoding="utf-8")
        with pytest.raises(ProcessingError):
            VorabpauschaleDeclarationStore(str(path))

    def test_a_committed_year_with_no_entry_for_a_fund_is_still_a_committed_year(self, tmp_path):
        """The distinction the gap report turns on: 'this fund declared nothing in
        2023' is a fact about the declaration, 'the 2023 declaration was never
        recorded' is a missing record."""
        store = VorabpauschaleDeclarationStore(str(tmp_path / "d.json"))
        store.commit("OTHER", 2023, DeclaredVorabpauschale(
            gross_eur=Decimal("0.00"), declared_on=date(2025, 5, 1), source="x"))
        assert store.get("K", 2023) is None
        assert 2023 in store.committed_years()

    def test_the_default_path_is_the_configured_one(self):
        store = VorabpauschaleDeclarationStore()
        assert store.cache_file_path == config.VORABPAUSCHALE_DECLARATION_STORE_PATH


class TestNothingDeclaredIsNotADeclaredZero:
    """The state that carries the whole back-filling story: returns filed before
    this engine existed declared nothing, and that has to be recordable, visible
    and — once the return is corrected — replaceable."""

    def _not_declared(self):
        return DeclaredVorabpauschale(
            gross_eur=Decimal("0.00"), declared_on=date(2026, 8, 9),
            source="Angabe: nichts erklaert",
            status=DeclarationStatus.NOT_DECLARED)

    def test_a_not_declared_record_is_not_deductible(self):
        assert not self._not_declared().is_deductible

    def test_a_declared_zero_is_deductible_and_deducts_zero(self):
        """A fund that owed nothing that year is a complete answer, not a gap."""
        entry = DeclaredVorabpauschale(gross_eur=Decimal("0.00"),
                                       declared_on=date(2025, 5, 1), source="x")
        assert entry.is_deductible

    def test_a_not_declared_record_cannot_carry_an_amount(self):
        with pytest.raises(ProcessingError):
            DeclaredVorabpauschale(
                gross_eur=Decimal("10.00"), declared_on=date(2026, 8, 9),
                source="x", status=DeclarationStatus.NOT_DECLARED)

    def test_a_correction_may_supersede_it(self, tmp_path):
        store = VorabpauschaleDeclarationStore(str(tmp_path / "d.json"))
        store.commit("K", 2023, self._not_declared())
        store.commit("K", 2023, DeclaredVorabpauschale(
            gross_eur=Decimal("120.00"), declared_on=date(2026, 9, 1),
            source="berichtigte Erklaerung"))
        assert store.get("K", 2023).gross_eur == Decimal("120.00")
        assert store.get("K", 2023).is_deductible

    def test_a_declaration_may_not_be_downgraded_to_not_declared(self):
        """The prompt runs on every year the store has no answer for; it must not
        be able to talk a real declaration out of the record."""
        store = VorabpauschaleDeclarationStore.__new__(VorabpauschaleDeclarationStore)
        store.cache_file_path = "unused"
        store._entries = {}
        store.commit("K", 2023, DeclaredVorabpauschale(
            gross_eur=Decimal("120.00"), declared_on=date(2025, 5, 1), source="x"))
        with pytest.raises(ProcessingError):
            store.commit("K", 2023, self._not_declared())

    def test_the_status_survives_the_file(self, tmp_path):
        path = tmp_path / "d.json"
        store = VorabpauschaleDeclarationStore(str(path))
        store.commit("K", 2023, self._not_declared())
        store.save()
        assert VorabpauschaleDeclarationStore(str(path)).get("K", 2023).status \
            is DeclarationStatus.NOT_DECLARED

    def test_an_entry_written_before_the_status_existed_reads_as_declared(self, tmp_path):
        """The only writer of those entries was the commit at filing, so DECLARED
        is what they meant -- not a default standing in for a missing value."""
        path = tmp_path / "d.json"
        path.write_text(json.dumps({"K|2023": {
            "gross_eur": "120.00", "declared_on": "2025-05-01", "source": "x"}}),
            encoding="utf-8")
        assert VorabpauschaleDeclarationStore(str(path)).get("K", 2023).is_deductible


class TestThePromptForAnEarlierYear:
    """What the taxpayer is actually asked, and what each answer means."""

    def _asset(self):
        asset = MagicMock()
        asset.get_classification_key.return_value = "ISIN:IE00TEST1234"
        asset.description = "Test Fund"
        return asset

    def _ask(self, monkeypatch, answers):
        supplied = list(answers)
        monkeypatch.setattr("builtins.input", lambda _prompt="": supplied.pop(0))
        return prompt_for_declared_vorabpauschale(self._asset(), 2023)

    def test_an_amount_with_a_source_is_recorded_as_declared(self, monkeypatch):
        entry = self._ask(monkeypatch, ["120,30", "Anlage KAP-INV 2024 Zeile 9"])
        assert entry.gross_eur == Decimal("120.30")   # comma accepted
        assert entry.is_deductible
        assert entry.source == "Anlage KAP-INV 2024 Zeile 9"

    def test_n_records_that_nothing_was_declared(self, monkeypatch):
        entry = self._ask(monkeypatch, ["n"])
        assert entry.status is DeclarationStatus.NOT_DECLARED
        assert entry.gross_eur == Decimal("0.00")

    def test_an_empty_answer_records_nothing_at_all(self, monkeypatch):
        assert self._ask(monkeypatch, [""]) is None

    def test_an_amount_without_a_source_is_refused(self, monkeypatch):
        """The Anleitung asks the taxpayer to *darlegen* that the Vorabpauschalen
        were declared. A figure nobody can trace does not meet that."""
        assert self._ask(monkeypatch, ["120.30", ""]) is None

    def test_a_non_number_is_refused_rather_than_guessed(self, monkeypatch):
        assert self._ask(monkeypatch, ["ungefähr 120"]) is None

    def test_the_engines_own_figure_is_never_offered_as_a_default(self, monkeypatch):
        """It would answer a different question -- what the year's Vorabpauschale
        should have been, not what was brought to tax -- and a default is the kind
        of thing that gets accepted with Enter."""
        printed = []
        monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))
        monkeypatch.setattr("builtins.input", lambda _prompt="": "")
        prompt_for_declared_vorabpauschale(self._asset(), 2023)
        text = "\n".join(printed)
        assert "--tax-year 2024" in text      # where to get it instead
        assert "Zeile 53" in text


# ---------------------------------------------------------------------------
# The deduction follows the lot through FIFO consumption
# ---------------------------------------------------------------------------

class TestTheDeductionFollowsTheLot:

    def test_a_partial_sale_takes_a_pro_rata_slice_and_the_lot_keeps_the_rest(self):
        ledger = _fund_ledger()
        ledger.lots.append(_lot("2023-02-01", "100", unit_cost="10", vp="40"))
        rgls = ledger.consume_long_lots_for_sale(
            _sale(ledger.asset_internal_id, "25", "300"))
        assert len(rgls) == 1
        assert rgls[0].vorabpauschale_deduction_eur == Decimal("10")
        assert ledger.lots[0].vorabpauschale_gross_eur == Decimal("30")

    def test_fifo_order_decides_which_tranches_deduction_is_taken(self):
        """Two tranches with different accumulations; a sale of the older one's
        size must take the older one's Vorabpauschale, not an average."""
        ledger = _fund_ledger()
        ledger.lots.append(_lot("2023-02-01", "10", tx="OLD", vp="80"))
        ledger.lots.append(_lot("2024-02-01", "10", tx="NEW", vp="20"))
        rgls = ledger.consume_long_lots_for_sale(
            _sale(ledger.asset_internal_id, "10", "150"))
        assert [r.vorabpauschale_deduction_eur for r in rgls] == [Decimal("80")]
        assert ledger.lots[0].vorabpauschale_gross_eur == Decimal("20")

    def test_a_lot_with_no_vorabpauschale_yields_a_zero_deduction(self):
        ledger = _fund_ledger()
        ledger.lots.append(_lot("2025-02-01", "10"))
        rgls = ledger.consume_long_lots_for_sale(
            _sale(ledger.asset_internal_id, "10", "150"))
        assert rgls[0].vorabpauschale_deduction_eur == Decimal("0")

    def test_a_non_fund_disposal_carries_no_deduction_at_all(self):
        ledger = _fund_ledger()
        ledger.asset_category = AssetCategory.STOCK
        ledger.lots.append(_lot("2023-02-01", "10", vp="0"))
        rgls = ledger.consume_long_lots_for_sale(
            _sale(ledger.asset_internal_id, "10", "150"))
        assert rgls[0].vorabpauschale_deduction_eur is None


class TestAMergerCarriesTheAccumulation:
    """Found blind by mutation on 2026-08-09: dropping the carry left all 1100
    tests green.

    `receive_all_lots_from_merger` rebuilds the lots it takes over rather than
    moving them, which is why the acquisition date and cost basis are copied
    across explicitly -- the new units step into the tax position of the old ones.
    The Vorabpauschalen those units already bore belong to the same position: they
    were angesetzt during this holding period, and § 19 Abs. 1 Satz 3 deducts them
    when it ends. A rebuild that forgets them loses the deduction with nothing in
    the output to say so.
    """

    def test_the_new_lots_keep_the_vorabpauschale_of_the_old_ones(self):
        source, target = _fund_ledger(), _fund_ledger()
        source.lots.append(_lot("2023-02-01", "100", vp="120.00"))
        merger = MagicMock()
        merger.event_id = uuid.uuid4()

        target.receive_all_lots_from_merger(
            source.drain_all_long_lots(), source.drain_all_short_lots(),
            Decimal("1"), merger)

        assert len(target.lots) == 1
        assert target.lots[0].vorabpauschale_gross_eur == Decimal("120.00")

    def test_it_survives_an_exchange_ratio(self):
        """The ratio restates the unit count; it does not change which units are
        held, so the accumulated total travels whole -- exactly like
        `total_cost_basis_eur`, which the merger also carries across unchanged."""
        source, target = _fund_ledger(), _fund_ledger()
        source.lots.append(_lot("2023-02-01", "100", vp="120.00"))
        merger = MagicMock()
        merger.event_id = uuid.uuid4()

        target.receive_all_lots_from_merger(
            source.drain_all_long_lots(), [], Decimal("2"), merger)

        assert target.lots[0].quantity == Decimal("200")
        assert target.lots[0].vorabpauschale_gross_eur == Decimal("120.00")


# ---------------------------------------------------------------------------
# Satz 4: the deduction is gross, and the Teilfreistellung comes after it
# ---------------------------------------------------------------------------

class TestSatz4GrossDeductionThenTeilfreistellung:

    def test_teilfreistellung_is_applied_to_the_gain_after_the_deduction(self):
        """Satz 4: the Vorabpauschalen count in full, *ungeachtet* a possible
        Teilfreistellung. Applying the 30% to the gain before the deduction would
        deduct only 70% of it."""
        rgl = _fund_rgl(gross="100", deduction="40")
        assert rgl.gain_after_vorabpauschale_eur == Decimal("60")
        assert rgl.teilfreistellung_amount_eur == Decimal("18.00")
        assert rgl.net_gain_loss_after_teilfreistellung_eur == Decimal("42.00")

    def test_the_deduction_can_turn_a_gain_into_a_loss(self):
        """A deduction larger than the gain enlarges the loss -- it is not capped
        at zero. That is the case the deduction is worth claiming in with no gain
        in sight (issue #63)."""
        rgl = _fund_rgl(gross="30", deduction="50")
        assert rgl.gain_after_vorabpauschale_eur == Decimal("-20")
        assert rgl.net_gain_loss_after_teilfreistellung_eur == Decimal("-14.00")

    def test_no_deduction_leaves_every_figure_exactly_as_before(self):
        rgl = _fund_rgl(gross="100")
        assert rgl.gain_after_vorabpauschale_eur == Decimal("100")
        assert rgl.teilfreistellung_amount_eur == Decimal("30.00")
        assert rgl.net_gain_loss_after_teilfreistellung_eur == Decimal("70.00")

    def test_a_deduction_on_a_non_fund_disposal_is_rejected(self):
        """§ 19 reaches Investmentanteile only. A deduction anywhere else is a
        wiring defect, and a silent one would understate income."""
        with pytest.raises(ValueError):
            _fund_rgl(gross="100", deduction="10", category=AssetCategory.STOCK)


# ---------------------------------------------------------------------------
# Where the figure lands on the form
# ---------------------------------------------------------------------------

class TestZeile53OnTheForm:
    """Z54 = Erloes - Anschaffungskosten - Veraeusserungskosten - Z53, and Z54 is
    what is transferred to Z14/17/20/23/26 (GT-FORM-032, GT-FORM-033). So the gain
    lines are net of the deduction and Zeile 53 carries it as its own figure."""

    def _run(self, rgls, collector=None):
        resolver = MagicMock(spec=AssetResolver)
        resolver.get_asset_by_id.return_value = None
        engine = LossOffsettingEngine(
            realized_gains_losses=rgls, vorabpauschale_items=[],
            current_year_financial_events=[], asset_resolver=resolver,
            tax_year=2025, data_gap_collector=collector,
        )
        return engine.calculate_reporting_figures()

    def test_zeile_53_carries_the_sum_of_the_deductions(self):
        result = self._run([_fund_rgl(gross="100", deduction="40"),
                            _fund_rgl(gross="200", deduction="15")])
        assert (result.form_line_values[
            TaxReportingCategory.ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z53]
            == Decimal("55.00"))

    def test_the_gain_line_is_already_net_of_the_deduction(self):
        result = self._run([_fund_rgl(gross="100", deduction="40")])
        assert (result.form_line_values[
            TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS]
            == Decimal("60.00"))

    def test_the_conceptual_net_fund_income_uses_the_reduced_gain(self):
        result = self._run([_fund_rgl(gross="100", deduction="40")])
        assert result.conceptual_fund_income_net_taxable == Decimal("42.00")

    def test_no_deduction_and_no_disposal_leaves_zeile_53_at_zero(self):
        result = self._run([])
        assert (result.form_line_values.get(
            TaxReportingCategory.ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z53,
            Decimal(0)) == Decimal("0"))

    def test_a_disposal_alone_no_longer_records_the_not_computed_gap(self):
        """The gap that said the engine 'does not track per-lot Vorabpauschale
        history' is retired by #63. What replaces it is recorded where the
        attribution happens, naming the fund and the year -- not here."""
        collector = DataGapCollector()
        self._run([_fund_rgl(gross="100", deduction="40")], collector=collector)
        assert [g.code for g in collector.gaps] == []

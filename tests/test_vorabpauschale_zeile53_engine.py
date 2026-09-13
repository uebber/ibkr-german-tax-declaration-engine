"""Zeile 53 end to end: replay -> per-year attribution -> disposal -> form line.

legal_basis: GT-INVSTG-030 (§ 19 Abs. 1 Saetze 3-4), GT-INVSTG-034 (deductible only
so far as declared, and that must be demonstrated), GT-INVSTG-011 (§ 18 Abs. 2),
GT-FORM-031 / GT-FORM-033 (Zeilen 9-13 and Zeile 53). See
reference/investment-tax-law/invstg-19-veraeusserungsgewinne.md.

The unit tests in `test_vorabpauschale_zeile53.py` pin each piece. This file pins
the chain, because every seam between the pieces is a place a figure can vanish
without a test noticing: a year end that is not a checkpoint mark, a declaration
record that is never consulted, a lot rebuilt by reconciliation and losing its
accumulation.

The scenario is one Aktienfonds, 100 units bought 2023-02-01, 40 sold 2025-06-02,
run as VZ 2025:

    calendar 2023   declared 120.00, from the store (VZ 2024 return)
    calendar 2024   160.30, this run's own Zeilen 9-13 figure
    ------------------------------------------------------------------
    per lot         280.30 accumulated on 100 units
    40 units sold   112.12 on Zeile 53
"""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.domain.assets import InvestmentFund, MarkPosition, PositionSnapshot
from tests.support.prior_year_snapshots import snapshot_row
from src.utils.account_utils import DEFAULT_ACCOUNT
from src.domain.enums import (
    AssetCategory, FinancialEventType, InvestmentFundType, TaxReportingCategory,
)
from src.domain.events import TradeEvent
from src.engine.calculation_engine import run_main_calculations
from src.engine.loss_offsetting import LossOffsettingEngine
from src.identification.asset_resolver import AssetResolver
from src.processing.data_gaps import DataGapCollector
from src.processing.vorabpauschale_declarations import (
    DeclarationStatus, DeclaredVorabpauschale, VorabpauschaleDeclarationStore,
    commit_declared_vorabpauschale,
)
import src.config as config


TAX_YEAR = 2025
ISIN = "IE00TEST1234"
# What `Asset.get_classification_key()` returns for it, and therefore how the
# declaration store is keyed.
KEY = f"ISIN:{ISIN}"


def _eur_converter():
    converter = MagicMock()
    converter.convert_to_eur.side_effect = (
        lambda amount, currency, dt: amount if currency == "EUR" else None)
    return converter


def _fund(*, eoy_qty=Decimal("60"), soy_qty=Decimal("100")) -> InvestmentFund:
    """One Aktienfonds, priced for the calendar 2024 Vorabpauschale.

    Prices are invented round numbers: 100.00 at the start of 2024 and 110.00 at
    its close. Basiszins 2024 is 2.29%, so the per-unit Basisertrag is
    100 * 0.0229 * 0.7 = 1.603, under the Satz 3 cap of 10.00, and 100 units give
    a gross Vorabpauschale of 160.30.
    """
    fund = InvestmentFund(
        fund_type=InvestmentFundType.AKTIENFONDS,
        description="Test Aktienfonds", currency="EUR",
        ibkr_isin=ISIN, ibkr_symbol="TFUND",
    )
    # The opening snapshot for VZ 2025 = the close of 2024. These are not fields of
    # Asset: the engine reads them from the per-(account, asset) registries, which
    # `_snapshots` builds. They ride on the fund here so one helper hands the scenario
    # back whole.
    fund.reported_opening = PositionSnapshot(
        quantity=soy_qty, cost_basis_amount=Decimal("1000"), cost_basis_currency="EUR")
    fund.reported_closing = PositionSnapshot(quantity=eoy_qty)
    # Calendar 2024's own snapshots, which the Vorabpauschale for 2024 reads. Kept
    # per (account, asset) like the two above, and on the fund for the same reason.
    fund.prior_opening = snapshot_row(fund.internal_asset_id, quantity=Decimal("100"))
    fund.prior_soy = snapshot_row(
        fund.internal_asset_id, quantity=Decimal("100"), mark_price=Decimal("100.00"),
        mark_price_currency="EUR", mark_price_date=date(2024, 1, 2))
    fund.prior_eoy = snapshot_row(
        fund.internal_asset_id, quantity=Decimal("100"), mark_price=Decimal("110.00"),
        mark_price_currency="EUR", mark_price_date=date(2024, 12, 30))
    return fund


def _snapshots(fund):
    """The opening and closing registries the engine reads for this scenario.

    One unattributed account: these scenarios are about the Vorabpauschale, which is
    attributed per person, and none of them turns on which Depot the units sit in.
    """
    key = (DEFAULT_ACCOUNT, fund.internal_asset_id)
    return {key: fund.reported_opening}, {key: fund.reported_closing}


def _resolver(fund) -> AssetResolver:
    resolver = MagicMock(spec=AssetResolver)
    resolver.assets_by_internal_id = {fund.internal_asset_id: fund}
    resolver.get_asset_by_id.side_effect = (
        lambda aid: fund if aid == fund.internal_asset_id else None)
    resolver.get_cash_balance_asset.return_value = None
    return resolver


def _buy(fund, quantity="100", date_str="2023-02-01") -> TradeEvent:
    return TradeEvent(
        fund.internal_asset_id, date_str,
        event_type=FinancialEventType.TRADE_BUY_LONG,
        quantity=Decimal(quantity), price_foreign_currency=Decimal("10"),
        local_currency="EUR", ibkr_transaction_id="BUY1",
        gross_amount_foreign_currency=Decimal("1000"),
        net_proceeds_or_cost_basis_eur=Decimal("1000"),
    )


def _sell(fund, quantity="40", date_str="2025-06-02", proceeds="600") -> TradeEvent:
    return TradeEvent(
        fund.internal_asset_id, date_str,
        event_type=FinancialEventType.TRADE_SELL_LONG,
        quantity=-Decimal(quantity), price_foreign_currency=Decimal("15"),
        local_currency="EUR", ibkr_transaction_id="SELL1",
        gross_amount_foreign_currency=Decimal(proceeds),
        net_proceeds_or_cost_basis_eur=Decimal(proceeds),
    )


def _store(tmp_path, entries=()) -> VorabpauschaleDeclarationStore:
    store = VorabpauschaleDeclarationStore(str(tmp_path / "declarations.json"))
    for year, gross in entries:
        store.commit(KEY, year, DeclaredVorabpauschale(
            gross_eur=Decimal(gross), declared_on=date(year + 2, 5, 1),
            source=f"VZ {year + 1} Anlage KAP-INV Zeile 9"))
    return store


def _run(store, *, fund=None, events=None, collector=None, ask=None):
    fund = fund or _fund()
    collector = collector if collector is not None else DataGapCollector()
    soy_positions, eoy_positions = _snapshots(fund)
    rgls, vp_items, _income, _mismatches = run_main_calculations(
        financial_events=events if events is not None else [_buy(fund), _sell(fund)],
        asset_resolver=_resolver(fund),
        currency_converter=_eur_converter(),
        exchange_rate_provider=MagicMock(),
        tax_year=TAX_YEAR,
        internal_calculation_precision=config.INTERNAL_CALCULATION_PRECISION,
        decimal_rounding_mode=config.DECIMAL_ROUNDING_MODE,
        data_gap_collector=collector,
        prior_year_positions_available=True,
        mark_positions={2023: {(DEFAULT_ACCOUNT, fund.internal_asset_id): MarkPosition(
            quantity=Decimal("100"), cost_basis_amount=Decimal("1000"),
            cost_basis_currency="EUR")}},
        soy_positions=soy_positions,
        eoy_positions=eoy_positions,
        prior_soy_positions=fund.prior_soy,
        prior_eoy_positions=fund.prior_eoy,
        prior_opening_positions=fund.prior_opening,
        declaration_store=store,
        ask_for_declared_vorabpauschale=ask,
    )
    return fund, rgls, vp_items, collector


def _codes(collector):
    return [g.code for g in collector.gaps]


class TestTheDeductionReachesTheFormLine:

    def test_both_holding_period_years_reach_the_disposed_units(self, tmp_path):
        fund, rgls, vp_items, collector = _run(_store(tmp_path, [(2023, "120.00")]))

        # This run's own Zeilen 9-13 figure for calendar 2024.
        assert [i.gross_vorabpauschale_eur for i in vp_items] == [Decimal("160.30")]

        fund_rgls = [r for r in rgls
                     if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND]
        assert len(fund_rgls) == 1
        # (120.00 + 160.30) * 40/100
        assert fund_rgls[0].vorabpauschale_deduction_eur == Decimal("112.12")
        assert "KAP_INV_Z53_VORABPAUSCHALE_NOT_DECLARED" not in _codes(collector)

    def test_the_figure_lands_on_zeile_53_and_reduces_zeile_14(self, tmp_path):
        fund, rgls, vp_items, _c = _run(_store(tmp_path, [(2023, "120.00")]))
        engine = LossOffsettingEngine(
            realized_gains_losses=rgls, vorabpauschale_items=vp_items,
            current_year_financial_events=[], asset_resolver=_resolver(fund),
            tax_year=TAX_YEAR,
        )
        result = engine.calculate_reporting_figures()

        assert (result.form_line_values[
            TaxReportingCategory.ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z53]
            == Decimal("112.12"))
        # Sale 600.00 - cost 400.00 = 200.00 gross, less the 112.12 deduction.
        assert (result.form_line_values[
            TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS]
            == Decimal("87.88"))

    def test_units_bought_inside_the_tax_year_carry_no_deduction(self, tmp_path):
        """Nothing was held at any year end, so § 18 never reached these units."""
        fund = _fund(eoy_qty=Decimal("160"), soy_qty=Decimal("100"))
        _f, rgls, _v, _c = _run(
            _store(tmp_path, [(2023, "120.00")]), fund=fund,
            events=[_buy(fund), _buy(fund, "100", "2025-03-01"),
                    _sell(fund, "40", "2025-06-02")])
        # FIFO consumes the 2023 lot first, so this disposal still carries its
        # accumulation; what the assertion pins is that the 2025 purchase added
        # none of its own.
        assert sum((r.vorabpauschale_deduction_eur or Decimal(0)) for r in rgls
                   if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND
                   ) == Decimal("112.12")


class TestAYearWithNoDeclarationRecord:
    """GT-INVSTG-034: a Vorabpauschale never declared is not deferred, it is lost.
    The engine deducts nothing for that year and names it, rather than
    substituting its own recomputation -- which is the invented input CLAUDE.md
    refuses everywhere else."""

    def test_an_unanswered_year_is_dropped_and_reported_as_unanswered(self, tmp_path):
        """--no-interactive cannot ask, so it must not assume. Distinct from the
        taxpayer answering "nothing was declared", which is a different fact and a
        different remedy."""
        fund, rgls, _v, collector = _run(_store(tmp_path))  # nothing recorded, nobody asked

        fund_rgl = next(r for r in rgls
                        if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND)
        # Only calendar 2024 survives: 160.30 * 40/100.
        assert fund_rgl.vorabpauschale_deduction_eur == Decimal("64.12")

        gap = next(g for g in collector.gaps
                   if g.code == "KAP_INV_Z53_VORABPAUSCHALE_DECLARATION_UNKNOWN")
        assert "2023" in gap.detail
        assert ISIN in gap.subject or ISIN in gap.detail
        assert "interaktiv" in gap.detail

    def test_no_gap_is_raised_for_a_year_whose_basiszins_was_negative(self, tmp_path):
        """2021 and 2022 have a negative Basiszins, so § 18 Abs. 1 Satz 2 yields no
        Vorabpauschale for any fund and there is nothing anyone could have
        declared. Demanding a record for those years would be noise."""
        fund = _fund()
        _f, _r, _v, collector = _run(
            _store(tmp_path, [(2023, "120.00")]), fund=fund,
            events=[_buy(fund, "100", "2021-03-01"), _sell(fund)])
        missing = [g.detail for g in collector.gaps
                   if g.code == "KAP_INV_Z53_VORABPAUSCHALE_NOT_DECLARED"]
        assert not any("2021" in d or "2022" in d for d in missing)

    def test_nothing_is_reported_when_no_fund_units_were_disposed_of(self, tmp_path):
        """Zeile 53 is then legitimately empty: an undeclared year costs nothing
        until units are sold."""
        fund = _fund(eoy_qty=Decimal("100"))
        _f, _r, _v, collector = _run(_store(tmp_path), fund=fund, events=[_buy(fund)])
        assert "KAP_INV_Z53_VORABPAUSCHALE_NOT_DECLARED" not in _codes(collector)


class TestAskingAboutEarlierYears:
    """The point of the whole store, once you notice who uses this engine: the
    returns for 2023 and 2024 were filed before it could compute a Vorabpauschale,
    so nothing was declared for those years, and the taxpayer only finds out that
    it costs them a deduction if something asks."""

    def _recorder(self, answer=None):
        asked = []

        def ask(asset, calendar_year):
            asked.append((asset.get_classification_key(), calendar_year))
            return answer

        ask.asked = asked
        return ask

    def test_an_earlier_year_with_nothing_on_record_is_asked_about(self, tmp_path):
        ask = self._recorder()
        _f, _r, _v, _c = _run(_store(tmp_path), ask=ask)
        assert ask.asked == [(KEY, 2023)]

    def test_the_year_this_return_declares_is_never_asked_about(self, tmp_path):
        """Calendar 2024 is on the form being produced. Asking whether it will be
        declared would be asking the taxpayer to confirm the page in front of them."""
        ask = self._recorder()
        _f, _r, _v, _c = _run(_store(tmp_path), ask=ask)
        assert 2024 not in [year for _key, year in ask.asked]

    def test_a_fund_sold_before_the_tax_year_is_not_asked_about(self, tmp_path):
        """It cannot reach this return's Zeile 53 — no disposal this year can
        consume lots it no longer has, and its year belonged to an earlier return.

        Measured on VZ 2025 before this guard existed: all three questions the run
        put were about funds whose opening position was zero. Asking someone to
        look up a filed return for nothing is how the prompts that matter get
        dismissed."""
        fund = _fund(eoy_qty=Decimal("0"), soy_qty=Decimal("0"))  # gone before 2025 opened
        ask = self._recorder()
        _f, _r, _v, _c = _run(
            _store(tmp_path), fund=fund, ask=ask,
            events=[_buy(fund), _sell(fund, "100", "2024-06-02")])
        assert ask.asked == []

    def test_a_year_already_on_record_is_not_asked_about_again(self, tmp_path):
        ask = self._recorder()
        _f, _r, _v, _c = _run(_store(tmp_path, [(2023, "120.00")]), ask=ask)
        assert ask.asked == []

    def test_an_answered_amount_is_deducted_and_remembered(self, tmp_path):
        store = _store(tmp_path)
        answer = DeclaredVorabpauschale(
            gross_eur=Decimal("120.00"), declared_on=date(2025, 5, 14),
            source="Anlage KAP-INV 2024 Zeile 9, eingereicht 2025-05-14")
        _f, rgls, _v, _c = _run(store, ask=self._recorder(answer))

        fund_rgl = next(r for r in rgls
                        if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND)
        assert fund_rgl.vorabpauschale_deduction_eur == Decimal("112.12")
        # Remembered, so the next run does not ask again.
        assert store.get(KEY, 2023).gross_eur == Decimal("120.00")

    def test_nothing_declared_deducts_nothing_and_says_how_to_recover_it(self, tmp_path):
        """The answer this exists for. Not a zero — a lost deduction, with the
        route back to it named: find the amount by re-running that year, correct
        the declaration, then record it."""
        store = _store(tmp_path)
        answer = DeclaredVorabpauschale(
            gross_eur=Decimal("0.00"), declared_on=date(2026, 8, 9),
            source="Angabe des Steuerpflichtigen: nichts erklaert",
            status=DeclarationStatus.NOT_DECLARED)
        collector = DataGapCollector()
        _f, rgls, _v, _c = _run(store, ask=self._recorder(answer), collector=collector)

        fund_rgl = next(r for r in rgls
                        if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND)
        # Calendar 2024 only: 160.30 * 40/100. 2023 contributes nothing.
        assert fund_rgl.vorabpauschale_deduction_eur == Decimal("64.12")

        gap = next(g for g in collector.gaps
                   if g.code == "KAP_INV_Z53_VORABPAUSCHALE_NOT_DECLARED")
        assert "2023" in gap.detail
        assert "--tax-year" in gap.detail          # where to get the amount
        assert "berichtigt" in gap.detail          # what to do with it
        # And the answer is remembered as an answer, not as a declared zero.
        assert store.get(KEY, 2023).status is DeclarationStatus.NOT_DECLARED

    def test_a_deferred_answer_records_nothing_and_is_asked_again(self, tmp_path):
        store = _store(tmp_path)
        collector = DataGapCollector()
        _f, _r, _v, _c = _run(store, ask=self._recorder(None), collector=collector)
        assert len(store) == 0
        assert "KAP_INV_Z53_VORABPAUSCHALE_DECLARATION_UNKNOWN" in _codes(collector)

    def test_a_correction_supersedes_the_not_declared_record(self, tmp_path):
        """What happens after the taxpayer corrects the earlier return: the record
        has to be able to say so, or the deduction stays lost for good."""
        store = _store(tmp_path)
        store.commit(KEY, 2023, DeclaredVorabpauschale(
            gross_eur=Decimal("0.00"), declared_on=date(2026, 8, 9),
            source="nichts erklaert", status=DeclarationStatus.NOT_DECLARED))
        store.commit(KEY, 2023, DeclaredVorabpauschale(
            gross_eur=Decimal("120.00"), declared_on=date(2026, 9, 1),
            source="berichtigte Anlage KAP-INV 2024 Zeile 9"))

        _f, rgls, _v, _c = _run(store)
        fund_rgl = next(r for r in rgls
                        if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND)
        assert fund_rgl.vorabpauschale_deduction_eur == Decimal("112.12")


class TestDivergenceFromWhatWasDeclared:
    """The engine matures. A year it has since changed its mind about must surface
    while the return is still amendable -- and the deduction stays capped at what
    was actually declared."""

    def test_a_declared_figure_that_no_longer_matches_is_reported(self, tmp_path):
        store = _store(tmp_path, [(2023, "120.00"), (2024, "150.00")])
        fund, rgls, _v, collector = _run(store)

        gap = next(g for g in collector.gaps
                   if g.code == "VORABPAUSCHALE_DECLARATION_DIVERGES")
        assert "150.00" in gap.detail and "160.30" in gap.detail

    def test_the_deduction_uses_the_declared_figure_not_the_new_one(self, tmp_path):
        store = _store(tmp_path, [(2023, "120.00"), (2024, "150.00")])
        _f, rgls, _v, _c = _run(store)
        fund_rgl = next(r for r in rgls
                        if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND)
        # (120.00 + 150.00) * 40/100
        assert fund_rgl.vorabpauschale_deduction_eur == Decimal("108.00")

    def test_an_agreeing_declaration_is_silent(self, tmp_path):
        store = _store(tmp_path, [(2023, "120.00"), (2024, "160.30")])
        _f, _r, _v, collector = _run(store)
        assert "VORABPAUSCHALE_DECLARATION_DIVERGES" not in _codes(collector)


class TestAYearEndWithNoSnapshot:
    """Distributing a fund-year total over the tranches needs the holding as it
    stood at that year's close. Without `Positions-{Y}-EoY.csv` there is no such
    holding, so the year cannot be attributed to lots at all -- a different
    failure from an undeclared year, and named differently."""

    def test_a_missing_mark_year_is_reported_and_deducts_nothing(self, tmp_path):
        fund = _fund()
        collector = DataGapCollector()
        store = _store(tmp_path, [(2023, "120.00")])
        rgls, _vp, _inc, _mm = run_main_calculations(
            financial_events=[_buy(fund), _sell(fund)],
            asset_resolver=_resolver(fund),
            currency_converter=_eur_converter(),
            exchange_rate_provider=MagicMock(),
            tax_year=TAX_YEAR,
            internal_calculation_precision=config.INTERNAL_CALCULATION_PRECISION,
            decimal_rounding_mode=config.DECIMAL_ROUNDING_MODE,
            data_gap_collector=collector,
            prior_year_positions_available=True,
            mark_positions={},          # no 2023 mark
            soy_positions=_snapshots(fund)[0],
            eoy_positions=_snapshots(fund)[1],
            prior_soy_positions=fund.prior_soy,
            prior_eoy_positions=fund.prior_eoy,
            prior_opening_positions=fund.prior_opening,
            declaration_store=store,
        )
        fund_rgl = next(r for r in rgls
                        if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND)
        assert fund_rgl.vorabpauschale_deduction_eur == Decimal("64.12")
        gap = next(g for g in collector.gaps
                   if g.code == "KAP_INV_Z53_VORABPAUSCHALE_NOT_ATTRIBUTABLE")
        assert "2023" in gap.detail


class TestUnitsDroppedAtACheckpointMark:
    """Found blind by mutation on 2026-08-09: making the resize at a mark carry the
    whole lot's accumulation onto the survivors left all 1079 tests green.

    A reconstruction that exceeds the broker's figure means a disposal the input does
    not contain. FIFO consumed oldest-first, so the survivors are resized out of the
    newest lot — and the units that went carried their share of the Vorabpauschale
    with them, deducted (or forfeited) in whatever year that disposal happened. Left
    whole, the accumulation would be deducted a second time here.
    """

    def test_the_dropped_units_take_their_share_of_the_accumulation(self, tmp_path):
        # 100 units bought in 2023 and confirmed by the 2023 mark; the 2024 opening
        # snapshot reports only 60, so 40 left in a disposal the input does not have.
        # The 2024 price falls, so the Satz 3 cap leaves 2024 with no Vorabpauschale
        # and the only accumulation on the lot is 2023's declared 120.00.
        fund = _fund(eoy_qty=Decimal("0"), soy_qty=Decimal("60"))
        fund.prior_eoy = snapshot_row(
            fund.internal_asset_id, quantity=Decimal("60"), mark_price=Decimal("95.00"),
            mark_price_currency="EUR", mark_price_date=date(2024, 12, 30))
        _f, rgls, _vp, _c = _run(
            _store(tmp_path, [(2023, "120.00")]), fund=fund,
            events=[_buy(fund, "100", "2023-02-01"), _sell(fund, "60", "2025-06-02")])

        fund_rgls = [r for r in rgls
                     if r.asset_category_at_realization == AssetCategory.INVESTMENT_FUND]
        # 120.00 * 60/100, not the whole 120.00.
        assert sum((r.vorabpauschale_deduction_eur for r in fund_rgls),
                   Decimal(0)) == Decimal("72.00")


class TestUnitsWhoseHoldingPeriodIsUnknown:
    """A lot the replay could not reconstruct carries a date reconciliation
    invented. Its holding period is unknown, so no year of it can be weighed --
    and a silent zero on Zeile 53 would look exactly like a fund that owed
    nothing."""

    def test_an_invented_acquisition_date_is_reported_against_zeile_53(self, tmp_path):
        # The reported holding at the 2023 mark exceeds anything the trades can
        # build, so reconciliation discards the reconstruction and synthesises an
        # undated lot. The 2024 price falls, so the Satz 3 cap leaves no
        # Vorabpauschale for 2024 and the run reaches the disposal.
        fund = _fund(eoy_qty=Decimal("60"), soy_qty=Decimal("100"))
        fund.prior_eoy = snapshot_row(
            fund.internal_asset_id, quantity=Decimal("100"), mark_price=Decimal("95.00"),
            mark_price_currency="EUR", mark_price_date=date(2024, 12, 30))
        collector = DataGapCollector()
        _f, _rgls, _vp, _c = _run(
            _store(tmp_path, [(2023, "120.00")]), fund=fund, collector=collector,
            events=[_buy(fund, "10", "2023-02-01"), _sell(fund, "40", "2025-06-02")])

        gap = next(g for g in collector.gaps
                   if g.code == "KAP_INV_Z53_VORABPAUSCHALE_NOT_ATTRIBUTABLE")
        assert "Ersatz-Anschaffungsdatum" in gap.detail


class TestThePipelineDecidesWhoCanBeAsked:
    """The end of the channel, which a green suite cannot see: the engine's
    ask-or-assume behaviour is decided one layer up, by whether the pipeline hands
    it a prompt at all."""

    def _captured_kwargs(self, monkeypatch, *, interactive):
        import src.pipeline_runner as pipeline_runner
        seen = {}

        def _capture(**kwargs):
            seen.update(kwargs)
            return [], [], [], 0

        monkeypatch.setattr(pipeline_runner, "run_main_calculations", _capture)
        pipeline_runner.run_core_processing_pipeline(
            trades_file_path="", cash_transactions_file_path="",
            positions_start_file_path="", positions_end_file_path="",
            corporate_actions_file_path="",
            interactive_classification_mode=interactive,
            tax_year_to_process=TAX_YEAR,
        )
        return seen

    def test_an_interactive_run_can_ask(self, monkeypatch):
        seen = self._captured_kwargs(monkeypatch, interactive=True)
        assert callable(seen["ask_for_declared_vorabpauschale"])

    def test_a_non_interactive_run_cannot_ask_and_therefore_must_not_assume(self, monkeypatch):
        """None is not a degraded prompt, it is the instruction not to guess: the
        engine reports every unanswered year instead of filling it in."""
        seen = self._captured_kwargs(monkeypatch, interactive=False)
        assert seen["ask_for_declared_vorabpauschale"] is None

    def test_the_declaration_store_reaches_the_engine_either_way(self, monkeypatch):
        for interactive in (True, False):
            seen = self._captured_kwargs(monkeypatch, interactive=interactive)
            assert seen["declaration_store"] is not None


class TestCommittingTheDeclaration:
    """Write-once, at filing. A run before filing is not a declaration, so nothing
    on the ordinary path may write here."""

    def test_an_ordinary_run_writes_nothing(self, tmp_path):
        path = tmp_path / "declarations.json"
        store = VorabpauschaleDeclarationStore(str(path))
        _run(store)
        assert not path.exists()
        assert len(store) == 0

    def test_the_commit_records_this_years_figure_for_the_preceding_calendar_year(self, tmp_path):
        store = _store(tmp_path)
        fund, _rgls, vp_items, _c = _run(store)
        commit_declared_vorabpauschale(
            store=store, asset_resolver=_resolver(fund),
            prior_eoy_positions=fund.prior_eoy,
            vorabpauschale_items=vp_items, vorabpauschale_year=TAX_YEAR - 1,
            declared_on=date(2026, 5, 1), source=f"VZ {TAX_YEAR} Anlage KAP-INV")

        entry = store.get(fund.get_classification_key(), 2024)
        assert entry.gross_eur == Decimal("160.30")
        assert entry.declared_on == date(2026, 5, 1)

    def test_units_in_either_account_count_as_held(self, tmp_path):
        """Which funds get an entry is the person's holding at the close.

        Rz. 18.4's count is the person's ([GT-ESTG20-061]). Read from one
        account's row, a fund the taxpayer still holds in the other would be
        left off the record -- and a later run could not tell "declared nothing"
        from "never declared", which is what the zero entry exists to prevent.
        """
        fund = _fund()
        # The account the export lists last holds nothing of this fund.
        fund.prior_eoy = dict(snapshot_row(
            fund.internal_asset_id, quantity=Decimal("100"), account="U1111111"))
        fund.prior_eoy.update(snapshot_row(
            fund.internal_asset_id, quantity=Decimal("0"), account="U2222222"))
        store = _store(tmp_path)

        written = commit_declared_vorabpauschale(
            store=store, asset_resolver=_resolver(fund),
            prior_eoy_positions=fund.prior_eoy,
            vorabpauschale_items=[], vorabpauschale_year=2024,
            declared_on=date(2026, 5, 1), source="VZ 2025")

        assert len(written) == 1
        assert store.get(KEY, 2024).gross_eur == Decimal("0.00")

    def test_a_fund_held_with_no_vorabpauschale_is_recorded_as_a_zero(self, tmp_path):
        """Otherwise a later run cannot tell 'declared nothing' from 'never
        declared', and would raise a gap over a fund that owed nothing."""
        fund = _fund()
        store = _store(tmp_path)
        commit_declared_vorabpauschale(
            store=store, asset_resolver=_resolver(fund),
            prior_eoy_positions=fund.prior_eoy,
            vorabpauschale_items=[], vorabpauschale_year=2024,
            declared_on=date(2026, 5, 1), source="VZ 2025")
        assert store.get(fund.get_classification_key(), 2024).gross_eur == Decimal("0.00")
        assert 2024 in store.committed_years()

"""
The Basisertrag's price and its unit count, and where each comes from.

legal_basis: § 18 Abs. 1 Satz 2 InvStG takes the Ruecknahmepreis *zu Beginn des
Kalenderjahres*, which is the first price set in the calendar year — settled by
Rz. 18.3 of the BMF-Schreiben of 21.05.2019, whose worked example uses one
figure as both the Satz 2 base and the Satz 3 cap's lower bound, and Satz 3
defines that bound as *"dem ersten ... im Kalenderjahr festgesetzten
Ruecknahmepreis"*. [GT-INVSTG-010]. Rz. 18.4 then multiplies by a unit count.

These tests are about **bookkeeping**: reading the stored position reports into
a correct history. The parsing layer settles one thing here — the per-unit price
the Vorabpauschale year opens at. For calendar X that is the first price set in
X, from X's own start-of-year report.

Where a fund was sold on X's first trading day it has no price in that
snapshot, and the last price set before the year began stands in — one trading
day early rather than a year late. Every such substitution is recorded, because
the resulting Basisertrag is from the wrong day.

The unit count is deliberately *not* settled here. Rz. 18.4 takes the holding at
the close of 31 December, which only the ledger knows, and § 18 Abs. 2 reduces
it by the month each tranche was acquired — see the engine's own tests.
"""
from decimal import Decimal

from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import InvestmentFund
from src.domain.enums import InvestmentFundType
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator


def _orchestrator(tmp_cache) -> ParsingOrchestrator:
    classifier = AssetClassifier(cache_file_path=str(tmp_cache))
    resolver = AssetResolver(asset_classifier=classifier)
    return ParsingOrchestrator(asset_resolver=resolver, asset_classifier=classifier,
                               interactive_classification=False)


def _fund(orch, *, opening_qty, opening_price, soy_price,
          soy_value=None, description="Test Fund") -> InvestmentFund:
    """opening_* is the close of X-1; soy_price is X's first trading day."""
    fund = InvestmentFund(fund_type=InvestmentFundType.AKTIENFONDS,
                          description=description, currency="EUR",
                          ibkr_isin="IE00TEST0001", ibkr_symbol="TF")
    fund.prior_year_opening_quantity = opening_qty
    fund.prior_year_opening_mark_price = opening_price
    fund.prior_year_opening_mark_price_currency = "EUR"
    fund.prior_year_soy_mark_price = soy_price
    fund.prior_year_soy_mark_price_currency = "EUR"
    fund.prior_year_soy_position_value = soy_value
    orch.asset_resolver.assets_by_internal_id[fund.internal_asset_id] = fund
    return fund


def test_the_start_price_is_the_one_from_the_years_own_snapshot(tmp_path):
    """Present already: the resolver leaves it alone and records nothing."""
    orch = _orchestrator(tmp_path / "c.json")
    fund = _fund(orch, opening_qty=Decimal("100"), opening_price=Decimal("9"),
                 soy_price=Decimal("10"))

    orch._resolve_vorabpauschale_start_price()

    assert fund.prior_year_soy_mark_price == Decimal("10")
    assert orch.vorabpauschale_price_substitutions == []


class TestMissingFirstTradingDayPrice:
    def test_sold_on_the_first_day_falls_back_to_the_last_price_before_the_year(self, tmp_path):
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("100"), opening_price=Decimal("9"),
                     soy_price=None)

        orch._resolve_vorabpauschale_start_price()

        assert fund.prior_year_soy_mark_price == Decimal("9")
        assert len(orch.vorabpauschale_price_substitutions) == 1

    def test_a_fund_not_held_when_the_year_opened_is_left_alone(self, tmp_path):
        """
        A price from before the year cannot describe units that did not exist
        then. Nothing is substituted, and the fund keeps whatever its own
        snapshot gave it.
        """
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("0"), opening_price=Decimal("9"),
                     soy_price=None)

        orch._resolve_vorabpauschale_start_price()

        assert fund.prior_year_soy_mark_price is None
        assert orch.vorabpauschale_price_substitutions == []

    def test_nothing_is_invented_when_no_price_exists_at_all(self, tmp_path):
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("100"), opening_price=None,
                     soy_price=None)

        orch._resolve_vorabpauschale_start_price()

        assert fund.prior_year_soy_mark_price is None
        assert orch.vorabpauschale_price_substitutions == []


def test_the_resolver_is_reached_by_the_parsing_pipeline(tmp_path):
    """
    Probes the end of the channel, not the middle: every test above calls the
    resolver directly and so survives deleting its call site, which is the
    blind spot CLAUDE.md describes for a newly added channel.
    """
    from src.parsers.raw_models import RawPositionRecord

    def record(qty, price, value):
        return RawPositionRecord(
            CurrencyPrimary="EUR", AssetClass="STK", Symbol="TF",
            Description="Test Fund", ISIN="IE00TEST0001", Conid="1",
            Quantity=qty, MarkPrice=price, PositionValue=value, CostBasisMoney=value)

    orch = _orchestrator(tmp_path / "c.json")
    # Held at the close of X-1 at 9, and absent from X's own start-of-year
    # snapshot — sold on the first trading day. The fallback must fire.
    orch.raw_positions_prior_opening = [record("100", "9", "900")]
    orch.raw_positions_prior_start = []
    orch.raw_positions_prior_end = [record("150", "12", "1800")]

    orch.process_positions()

    assert len(orch.vorabpauschale_price_substitutions) == 1
    resolved = [a for a in orch.asset_resolver.assets_by_internal_id.values()
                if a.prior_year_soy_mark_price is not None]
    assert len(resolved) == 1
    assert resolved[0].prior_year_soy_mark_price == Decimal("9")


def test_the_opening_snapshot_file_actually_reaches_the_orchestrator(tmp_path):
    """
    One link further out than the test above, which sets
    `raw_positions_prior_opening` by hand and therefore passes while the file
    is never read at all. That is exactly what happened: `run_parsing_pipeline`
    accepted `positions_prior_opening_file` and did not forward it to
    `load_all_raw_data`, so `prior_year_opening_*` was empty in every real run
    and the fallback above could never fire outside a test.
    """
    import inspect

    from src.parsers.parsing_orchestrator import ParsingOrchestrator

    source = inspect.getsource(ParsingOrchestrator.run_parsing_pipeline)
    assert "positions_prior_opening_file=positions_prior_opening_file" in source, (
        "run_parsing_pipeline accepts the opening-positions file but does not "
        "pass it on; prior_year_opening_* will be empty in every real run"
    )

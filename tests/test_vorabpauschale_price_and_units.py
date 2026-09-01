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
from datetime import date
from decimal import Decimal

from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import InvestmentFund, person_snapshot
from src.domain.enums import InvestmentFundType
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from tests.support.prior_year_snapshots import snapshot_row


def _orchestrator(tmp_cache) -> ParsingOrchestrator:
    classifier = AssetClassifier(cache_file_path=str(tmp_cache))
    resolver = AssetResolver(asset_classifier=classifier)
    return ParsingOrchestrator(asset_resolver=resolver, asset_classifier=classifier,
                               interactive_classification=False)


def _fund(orch, *, opening_qty, opening_price, soy_price,
          soy_value=None, description="Test Fund") -> InvestmentFund:
    """opening_* is the close of X-1; soy_price is X's first trading day.

    Both snapshots go into the orchestrator's own registries, under one account,
    which is where the resolver reads them from.
    """
    fund = InvestmentFund(fund_type=InvestmentFundType.AKTIENFONDS,
                          description=description, currency="EUR",
                          ibkr_isin="IE00TEST0001", ibkr_symbol="TF")
    orch.prior_opening_positions.update(snapshot_row(
        fund.internal_asset_id, quantity=opening_qty, mark_price=opening_price,
        mark_price_currency="EUR" if opening_price is not None else None))
    if soy_price is not None or soy_value is not None:
        orch.prior_soy_positions.update(snapshot_row(
            fund.internal_asset_id, position_value=soy_value, mark_price=soy_price,
            mark_price_currency="EUR" if soy_price is not None else None))
    orch.asset_resolver.assets_by_internal_id[fund.internal_asset_id] = fund
    return fund


def _start_price(orch, fund):
    """The year-start price the resolver left on record, or None."""
    settled = person_snapshot(orch.prior_soy_positions, fund.internal_asset_id)
    return settled.mark_price if settled is not None else None


def test_the_start_price_is_the_one_from_the_years_own_snapshot(tmp_path):
    """Present already: the resolver leaves it alone and records nothing."""
    orch = _orchestrator(tmp_path / "c.json")
    fund = _fund(orch, opening_qty=Decimal("100"), opening_price=Decimal("9"),
                 soy_price=Decimal("10"))

    orch._resolve_vorabpauschale_start_price()

    assert _start_price(orch, fund) == Decimal("10")
    assert orch.vorabpauschale_price_substitutions == []


class TestMissingFirstTradingDayPrice:
    def test_sold_on_the_first_day_falls_back_to_the_last_price_before_the_year(self, tmp_path):
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("100"), opening_price=Decimal("9"),
                     soy_price=None)

        orch._resolve_vorabpauschale_start_price()

        assert _start_price(orch, fund) == Decimal("9")
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

        assert _start_price(orch, fund) is None
        assert orch.vorabpauschale_price_substitutions == []

    def test_nothing_is_invented_when_no_price_exists_at_all(self, tmp_path):
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("100"), opening_price=None,
                     soy_price=None)

        orch._resolve_vorabpauschale_start_price()

        assert _start_price(orch, fund) is None
        assert orch.vorabpauschale_price_substitutions == []


class TestTheFundIsHeldInTwoAccounts:
    """The price is a property of the fund; the holding belongs to an account.

    Both facts are in the same registry, one row per account, so the resolver has
    to read the price across the rows and write its answer back to all of them.
    """

    def _two_accounts(self, orch, *, price_on_second):
        fund = InvestmentFund(fund_type=InvestmentFundType.AKTIENFONDS,
                              description="Test Fund", currency="EUR",
                              ibkr_isin="IE00TEST0001", ibkr_symbol="TF")
        orch.asset_resolver.assets_by_internal_id[fund.internal_asset_id] = fund
        for account in ("U1111111", "U2222222"):
            orch.prior_opening_positions.update(snapshot_row(
                fund.internal_asset_id, quantity=Decimal("50"),
                mark_price=Decimal("9"), mark_price_currency="EUR", account=account))
        # The first account's row carries the year-start price; the second's does not.
        orch.prior_soy_positions.update(snapshot_row(
            fund.internal_asset_id, quantity=Decimal("50"),
            mark_price=Decimal("10") if price_on_second else None,
            mark_price_currency="EUR" if price_on_second else None,
            account="U1111111"))
        orch.prior_soy_positions.update(snapshot_row(
            fund.internal_asset_id, quantity=Decimal("50"), account="U2222222"))
        return fund

    def test_one_account_reporting_the_price_settles_it_for_the_fund(self, tmp_path):
        """A Ruecknahmepreis one account's row carries is the fund's price.

        Substituting on the strength of the other account's blank would report a
        substitution that did not happen and take the price from a day too early.
        """
        orch = _orchestrator(tmp_path / "c.json")
        fund = self._two_accounts(orch, price_on_second=True)

        orch._resolve_vorabpauschale_start_price(2023)

        assert _start_price(orch, fund) == Decimal("10")
        assert orch.vorabpauschale_price_substitutions == []

    def test_a_substituted_price_reaches_every_account_that_holds_the_fund(self, tmp_path):
        """The price is per unit, so it belongs on every account's row.

        A per-unit price is the same value whichever account's row a per-account
        ledger reads, so it must be written to every row -- a fund held in one
        account of two would otherwise leave the other's row without it.
        """
        orch = _orchestrator(tmp_path / "c.json")
        fund = self._two_accounts(orch, price_on_second=False)

        orch._resolve_vorabpauschale_start_price(2023)

        rows = [snap for (_a, aid), snap in orch.prior_soy_positions.items()
                if aid == fund.internal_asset_id]
        assert len(rows) == 2
        assert all(r.mark_price == Decimal("9") for r in rows)
        assert all(r.mark_price_date == date(2022, 12, 30) for r in rows)
        assert len(orch.vorabpauschale_price_substitutions) == 1, (
            "one substitution for the fund, not one per account holding it")


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
    resolved = [snap for snap in orch.prior_soy_positions.values()
                if snap.mark_price is not None]
    assert len(resolved) == 1
    assert resolved[0].mark_price == Decimal("9")


def test_the_opening_snapshot_file_actually_reaches_the_orchestrator(tmp_path):
    """
    One link further out than the test above, which sets
    `raw_positions_prior_opening` by hand and therefore passes while the file
    is never read at all. That is exactly what happened: `run_parsing_pipeline`
    accepted `positions_prior_opening_file` and did not forward it to
    `load_all_raw_data`, so `prior_opening_positions` was empty in every real run
    and the fallback above could never fire outside a test.
    """
    import inspect

    from src.parsers.parsing_orchestrator import ParsingOrchestrator

    source = inspect.getsource(ParsingOrchestrator.run_parsing_pipeline)
    assert "positions_prior_opening_file=positions_prior_opening_file" in source, (
        "run_parsing_pipeline accepts the opening-positions file but does not "
        "pass it on; prior_opening_positions will be empty in every real run"
    )

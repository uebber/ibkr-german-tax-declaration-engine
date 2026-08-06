"""
The Basisertrag's price and its unit count, and where each comes from.

legal_basis: § 18 Abs. 1 Satz 2 InvStG takes the Ruecknahmepreis *zu Beginn des
Kalenderjahres* — which day that is, is open question Q12, resolved to the first
price set in the year. Rz. 18.4 of the BMF-Schreiben of 21.05.2019 then
multiplies by a unit count.

For the Vorabpauschale of calendar X this engine takes the price from X's first
trading day and the unit count from the close of X-1, so that both describe the
position as it stood when the year opened. That unit count is a **deliberate
departure** from Rz. 18.4, which counts the units held at the close of X; it is
recorded against GT-INVSTG-017 in docs/legal-implementation-map.md. The two
coincide for a holding that did not change during the year.

Where a fund was sold on X's first trading day it has no price in that
snapshot, and the last price set before the year began stands in — one trading
day early rather than a year late.
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


def test_the_base_is_the_first_trading_day_price_times_the_opening_units(tmp_path):
    """Price from the year's first trading day, count from the close before it."""
    orch = _orchestrator(tmp_path / "c.json")
    fund = _fund(orch, opening_qty=Decimal("100"), opening_price=Decimal("9"),
                 soy_price=Decimal("10"))

    orch._compose_vorabpauschale_base_value()

    assert fund.prior_year_soy_position_value == Decimal("1000")


def test_units_bought_during_the_year_do_not_enlarge_the_base(tmp_path):
    """
    The count is the opening one. Rz. 18.4 would use the close of the year and
    give a larger figure for a holding that grew — the recorded departure.
    """
    orch = _orchestrator(tmp_path / "c.json")
    fund = _fund(orch, opening_qty=Decimal("100"), opening_price=Decimal("9"),
                 soy_price=Decimal("10"))
    fund.prior_year_eoy_quantity = Decimal("150")

    orch._compose_vorabpauschale_base_value()

    assert fund.prior_year_soy_position_value == Decimal("1000")


class TestMissingFirstTradingDayPrice:
    def test_sold_on_the_first_day_falls_back_to_the_last_price_before_the_year(self, tmp_path):
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("100"), opening_price=Decimal("9"),
                     soy_price=None)

        orch._compose_vorabpauschale_base_value()

        assert fund.prior_year_soy_position_value == Decimal("900")
        assert len(orch.vorabpauschale_price_substitutions) == 1

    def test_a_fund_not_held_when_the_year_opened_is_left_alone(self, tmp_path):
        """
        Abs. 2's pro-rata case (GT-INVSTG-011, GT-INVSTG-035), unimplemented.
        Inventing a full-year Basisertrag would be a plausible wrong number.
        """
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("0"), opening_price=None,
                     soy_price=Decimal("10"))

        orch._compose_vorabpauschale_base_value()

        assert fund.prior_year_soy_position_value is None
        assert orch.vorabpauschale_price_substitutions == []

    def test_nothing_is_invented_when_no_price_exists_at_all(self, tmp_path):
        orch = _orchestrator(tmp_path / "c.json")
        fund = _fund(orch, opening_qty=Decimal("100"), opening_price=None,
                     soy_price=None)

        orch._compose_vorabpauschale_base_value()

        assert fund.prior_year_soy_position_value is None
        assert orch.vorabpauschale_price_substitutions == []


def test_the_composition_is_reached_by_the_parsing_pipeline(tmp_path):
    """
    Probes the end of the channel, not the middle: every test above calls the
    composition directly and so survives deleting its call site, which is the
    blind spot CLAUDE.md describes for a newly added channel.
    """
    from src.parsers.raw_models import RawPositionRecord

    def record(qty, price, value):
        return RawPositionRecord(
            CurrencyPrimary="EUR", AssetClass="STK", Symbol="TF",
            Description="Test Fund", ISIN="IE00TEST0001", Conid="1",
            Quantity=qty, MarkPrice=price, PositionValue=value, CostBasisMoney=value)

    orch = _orchestrator(tmp_path / "c.json")
    # Close of X-1: 100 units at 9. First trading day of X: price 10.
    orch.raw_positions_prior_opening = [record("100", "9", "900")]
    # 120 units in this snapshot, so its own value (1200) differs from the composed
    # one — otherwise deleting the call site would go unnoticed.
    orch.raw_positions_prior_start = [record("120", "10", "1200")]
    orch.raw_positions_prior_end = [record("150", "12", "1800")]

    orch.process_positions()

    funds = [a for a in orch.asset_resolver.assets_by_internal_id.values()
             if a.prior_year_soy_position_value is not None]
    assert len(funds) == 1
    # 10 x 100 opening units — not 10 x 150, and not the snapshot's own 1000.
    assert funds[0].prior_year_soy_position_value == Decimal("1000")

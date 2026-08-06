"""
The Basisertrag's price and its unit count come from different days.

legal_basis: § 18 Abs. 1 Satz 2 InvStG takes the Ruecknahmepreis *zu Beginn des
Kalenderjahres*; Rz. 18.4 of the BMF-Schreiben of 21.05.2019 multiplies it by
the units held *at the close of 31 December* of that year. Two moments, one
product. See reference/investment-tax-law/invstg-18-vorabpauschale.md
[GT-INVSTG-010], [GT-INVSTG-017] and open question Q12.

The engine consumes a single value for this, so the two figures are composed
where the snapshots are read. Before that, the value was the start-of-year
snapshot's own — price *and* units from the start of the year — which is right
only for a holding that never changed. On real 2024 data the correction moved
Anlage KAP-INV Zeile 13 from 393.27 to 491.59.
"""
import uuid
from decimal import Decimal

import pytest

from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import InvestmentFund
from src.domain.enums import InvestmentFundType
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator


def _orchestrator(tmp_cache) -> ParsingOrchestrator:
    classifier = AssetClassifier(cache_file_path=str(tmp_cache))
    resolver = AssetResolver(asset_classifier=classifier)
    return ParsingOrchestrator(
        asset_resolver=resolver,
        asset_classifier=classifier,
        interactive_classification=False,
    )


def _fund(orch, *, soy_qty, soy_price, eoy_qty, eoy_price,
          soy_value=None, description="Test Fund") -> InvestmentFund:
    fund = InvestmentFund(fund_type=InvestmentFundType.AKTIENFONDS,
                          description=description, currency="EUR",
                          ibkr_isin="IE00TEST0001", ibkr_symbol="TF")
    fund.prior_year_soy_quantity = soy_qty
    fund.prior_year_soy_position_value = (
        soy_value if soy_value is not None
        else (None if soy_price is None or soy_qty is None else soy_price * soy_qty))
    fund.prior_year_soy_mark_price = soy_price
    fund.prior_year_soy_mark_price_currency = "EUR"
    fund.prior_year_eoy_quantity = eoy_qty
    fund.prior_year_eoy_mark_price = eoy_price
    fund.prior_year_eoy_mark_price_currency = "EUR"
    orch.asset_resolver.assets_by_internal_id[fund.internal_asset_id] = fund
    return fund


def test_the_base_is_the_start_price_times_the_year_end_units(tmp_path):
    """
    100 units at the start, 150 at 31 December, start price 10. The Basisertrag
    base is 10 x 150, not the start snapshot's own 10 x 100.
    """
    orch = _orchestrator(tmp_path / "cache.json")
    fund = _fund(orch, soy_qty=Decimal("100"), soy_price=Decimal("10"),
                 eoy_qty=Decimal("150"), eoy_price=Decimal("12"))

    orch._compose_vorabpauschale_base_value()

    assert fund.prior_year_soy_position_value == Decimal("1500")


def test_an_unchanged_holding_is_left_where_it_was(tmp_path):
    """The common case: composing must not perturb it."""
    orch = _orchestrator(tmp_path / "cache.json")
    fund = _fund(orch, soy_qty=Decimal("100"), soy_price=Decimal("10"),
                 eoy_qty=Decimal("100"), eoy_price=Decimal("11"))

    orch._compose_vorabpauschale_base_value()

    assert fund.prior_year_soy_position_value == Decimal("1000")


def test_units_sold_down_during_the_year_reduce_the_base(tmp_path):
    orch = _orchestrator(tmp_path / "cache.json")
    fund = _fund(orch, soy_qty=Decimal("100"), soy_price=Decimal("10"),
                 eoy_qty=Decimal("40"), eoy_price=Decimal("12"))

    orch._compose_vorabpauschale_base_value()

    assert fund.prior_year_soy_position_value == Decimal("400")


class TestMissingStartOfYearPrice:
    def test_a_fund_held_at_year_start_falls_back_to_the_year_end_price(self, tmp_path):
        """
        Held at the start of the year but absent from that snapshot — an export
        gap. A figure is produced from the wrong day rather than none at all,
        and the substitution is recorded so it reaches the report.
        """
        orch = _orchestrator(tmp_path / "cache.json")
        fund = _fund(orch, soy_qty=Decimal("100"), soy_price=None,
                     eoy_qty=Decimal("100"), eoy_price=Decimal("12"),
                     soy_value=None)

        orch._compose_vorabpauschale_base_value()

        assert fund.prior_year_soy_position_value == Decimal("1200")
        assert len(orch.vorabpauschale_price_substitutions) == 1

    def test_a_fund_acquired_during_the_year_is_left_alone(self, tmp_path):
        """
        Not a gap and not a substitution: units bought during the year are
        Abs. 2's pro-rata case with Rz. 18.7's first price actually set, neither
        of which is implemented (GT-INVSTG-011, GT-INVSTG-035). Using the
        year-end price would invent a full-year Basisertrag at the highest price
        available — a figure that looks right and is too high.
        """
        orch = _orchestrator(tmp_path / "cache.json")
        fund = _fund(orch, soy_qty=Decimal("0"), soy_price=None,
                     eoy_qty=Decimal("100"), eoy_price=Decimal("12"),
                     soy_value=None)

        orch._compose_vorabpauschale_base_value()

        assert fund.prior_year_soy_position_value is None
        assert orch.vorabpauschale_price_substitutions == []

    def test_nothing_is_invented_when_neither_price_exists(self, tmp_path):
        orch = _orchestrator(tmp_path / "cache.json")
        fund = _fund(orch, soy_qty=Decimal("100"), soy_price=None,
                     eoy_qty=Decimal("100"), eoy_price=None, soy_value=None)

        orch._compose_vorabpauschale_base_value()

        assert fund.prior_year_soy_position_value is None
        assert orch.vorabpauschale_price_substitutions == []


def test_a_fund_gone_by_year_end_is_not_composed(tmp_path):
    """No units at 31 December: Rz. 18.4's multiplier is zero, and Q5's chosen
    reading gives no Vorabpauschale at all."""
    orch = _orchestrator(tmp_path / "cache.json")
    fund = _fund(orch, soy_qty=Decimal("100"), soy_price=Decimal("10"),
                 eoy_qty=Decimal("0"), eoy_price=Decimal("12"),
                 soy_value=Decimal("1000"))

    orch._compose_vorabpauschale_base_value()

    assert fund.prior_year_soy_position_value == Decimal("1000")


def test_the_composition_is_reached_by_the_parsing_pipeline(tmp_path):
    """
    Probes the end of the channel, not the middle. The tests above call the
    composition directly, so every one of them still passes if the call site in
    process_positions() is deleted — which is exactly the blind spot CLAUDE.md
    describes for a newly added channel. This drives the real entry point.
    """
    from src.parsers.raw_models import RawPositionRecord

    def record(qty, price, value):
        return RawPositionRecord(
            CurrencyPrimary="EUR", AssetClass="STK", Symbol="TF",
            Description="Test Fund", ISIN="IE00TEST0001", Conid="1",
            Quantity=qty, MarkPrice=price, PositionValue=value,
            CostBasisMoney=value,
        )

    orch = _orchestrator(tmp_path / "cache.json")
    # Start of the prior year: 100 units at 10. End of it: 150 units at 12.
    orch.raw_positions_prior_start = [record("100", "10", "1000")]
    orch.raw_positions_prior_end = [record("150", "12", "1800")]

    orch.process_positions()

    funds = [a for a in orch.asset_resolver.assets_by_internal_id.values()
             if a.prior_year_soy_position_value is not None]
    assert len(funds) == 1
    # 10 x 150, not the start snapshot's own 1000.
    assert funds[0].prior_year_soy_position_value == Decimal("1500")

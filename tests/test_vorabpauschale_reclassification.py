# tests/test_vorabpauschale_reclassification.py
"""The Vorabpauschale must not depend on how the instrument arrived.

legal_basis: GT-INVSTG-010 (Basisertrag and its cap), GT-INVSTG-012 and
GT-INVSTG-014 (the VZ Y return carries the figure computed for calendar Y-1,
from that year's snapshots). See
reference/investment-tax-law/invstg-18-vorabpauschale.md and
docs/legal-implementation-map.md.

The requirement is about the figure, not the plumbing: a fund held through the
Vorabpauschale year owes deemed income under 18 Abs. 1, and nothing in 18 InvStG
conditions that on which asset class the broker's export happened to name.

Whether the engine ever sees it, though, has depended on exactly that. A
positions row is resolved without its `SubCategory`, so the only fund signal
left is the description: an instrument described as an ETF is created as an
`InvestmentFund` outright, and every other fund is created as a `Stock` and
retyped later, when the user's classification is applied — which is after the
prior-year snapshot has been read onto it. Only the second kind passes through
the field copy, and only the second kind lost the snapshot. On this repository's
own data that is every fund, because none of their descriptions say "ETF".

A fund that loses it reaches 18's computation with no year-start price and drops
out of the declaration silently. Zeile 13 is then empty and nothing anywhere
says a figure is missing, which is the failure mode CLAUDE.md's fail-fast rule
exists to prevent: an absent figure is the one nobody notices.
"""
import json
import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.domain.assets import InvestmentFund, person_snapshot
from src.domain.enums import AssetCategory, InvestmentFundType
from src.domain.exceptions import DataIntegrityError
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from tests.support.base import FifoTestCaseBase
from tests.support.prior_year_snapshots import snapshot_row


def _stock_resolver_with_prior_year_snapshot():
    """A resolver holding one asset that arrived as a Stock, plus the preceding
    year's snapshot of it, exactly as `process_positions()` leaves the two."""
    classifier = MagicMock()
    classifier.preliminary_classify.return_value = (AssetCategory.STOCK, None)
    resolver = AssetResolver(asset_classifier=classifier)
    asset = resolver.get_or_create_asset(
        raw_isin="LU0000000001", raw_conid="900001", raw_symbol="XYZ1",
        raw_currency="SGD", raw_ibkr_asset_class="STK",
        raw_description="XYZ1 BOND INDEX", description_source_type="position",
    )
    prior_soy = snapshot_row(
        asset.internal_asset_id, quantity=Decimal("100"),
        position_value=Decimal("7300"), mark_price=Decimal("73.00"),
        mark_price_currency="SGD")
    return resolver, asset, prior_soy


def test_prior_year_snapshot_survives_a_classification_retype():
    """Applying the user's classification must not discard the year-start price.

    `replace_asset_type` builds a new object of the classified type. It used to
    carry the prior-year snapshot across by copying a hand-maintained list of
    fields, and a field left off that list was dropped silently. There is no
    list now: the snapshot is a registry row keyed by `internal_asset_id`, so
    what has to hold is that the rebuild keeps the id. It does, and the whole
    class of loss goes with it.
    """
    resolver, asset, prior_soy = _stock_resolver_with_prior_year_snapshot()
    before = person_snapshot(prior_soy, asset.internal_asset_id)

    reclassified = resolver.replace_asset_type(
        asset.internal_asset_id,
        AssetCategory.INVESTMENT_FUND,
        InvestmentFundType.SONSTIGE_FONDS,
        "classified by the user as a fund",
    )

    assert isinstance(reclassified, InvestmentFund)
    assert reclassified.internal_asset_id == asset.internal_asset_id, (
        "the retyped asset must keep its id, or every snapshot registry keyed by "
        "it -- the opening and closing positions, the checkpoint marks, and the "
        "three the Vorabpauschale reads -- stops resolving for this instrument"
    )
    assert person_snapshot(prior_soy, reclassified.internal_asset_id) == before


def test_a_fund_merged_into_another_asset_is_followed_to_it():
    """Retyping is not the only way the snapshot can be lost.

    When two rows turn out to identify the same instrument, the resolver merges
    them: it repoints the loser's aliases at the winner, deletes the loser, and
    copies no field values. A fund whose prior-year snapshot was read before that
    merge reaches 18's computation with nothing, exactly as a dropped copy-list
    field would — so the guard has to follow the alias to the surviving asset
    rather than give up when the id it recorded is gone.
    """
    orchestrator = ParsingOrchestrator(
        asset_resolver=AssetResolver(asset_classifier=MagicMock()),
        asset_classifier=MagicMock(),
    )
    resolver = orchestrator.asset_resolver

    losing_fund = InvestmentFund(fund_type=InvestmentFundType.SONSTIGE_FONDS,
                                 description="XYZ1", currency="EUR", ibkr_conid="900001")
    losing_fund.aliases.add("CONID:900001")
    resolver.assets_by_internal_id[losing_fund.internal_asset_id] = losing_fund
    resolver.alias_map["CONID:900001"] = losing_fund
    orchestrator.prior_soy_positions.update(snapshot_row(
        losing_fund.internal_asset_id, quantity=Decimal("100"),
        position_value=Decimal("7300")))
    orchestrator._record_prior_year_snapshot_asset(losing_fund)

    # The merge, as `get_or_create_asset` performs it: aliases move, the losing
    # asset is deleted, and the registry row stays filed under its id.
    surviving_fund = InvestmentFund(fund_type=InvestmentFundType.SONSTIGE_FONDS,
                                    description="XYZ1", currency="EUR",
                                    ibkr_isin="LU0000000001")
    surviving_fund.aliases.update({"ISIN:LU0000000001", "CONID:900001"})
    resolver.assets_by_internal_id[surviving_fund.internal_asset_id] = surviving_fund
    resolver.alias_map["CONID:900001"] = surviving_fund
    del resolver.assets_by_internal_id[losing_fund.internal_asset_id]

    with pytest.raises(DataIntegrityError) as excinfo:
        orchestrator._verify_prior_year_snapshot_survived_classification()

    message = str(excinfo.value)
    assert surviving_fund.get_classification_key() in message
    assert "merge" in message, (
        "the message must name the merge as the cause, which is now the only "
        "way a prior-year snapshot can stop reaching the asset that owns it"
    )


def _break_the_retype(monkeypatch):
    """Make `replace_asset_type` give the rebuilt asset a fresh internal id.

    The snapshot registries are keyed by that id, and `replace_asset_type`
    re-uses it deliberately -- the line saying so calls itself crucial. Breaking
    it is the whole class of loss the keying rests on not happening: the rows
    stay filed under an id nothing looks up again, the fund reaches 18 Abs. 1
    with no year-start Ruecknahmepreis, and its deemed income leaves the
    declaration with nothing recorded anywhere.
    """
    import uuid as _uuid

    original = AssetResolver.replace_asset_type

    def _with_a_fresh_id(self_resolver, internal_asset_id, *args, **kwargs):
        rebuilt = original(self_resolver, internal_asset_id, *args, **kwargs)
        rebuilt.internal_asset_id = _uuid.uuid4()
        self_resolver.assets_by_internal_id.pop(internal_asset_id, None)
        self_resolver.assets_by_internal_id[rebuilt.internal_asset_id] = rebuilt
        return rebuilt

    monkeypatch.setattr(AssetResolver, "replace_asset_type", _with_a_fresh_id)


class TestVorabpauschaleAcrossClassification(FifoTestCaseBase):
    """The declared figure, end to end, for a fund the broker exports as STK."""

    ISIN = "LU0000000001"
    CONID = "900001"

    def _seed_classification(self, category="INVESTMENT_FUND", fund_type="SONSTIGE_FONDS"):
        """The user classified this instrument in an earlier run."""
        cache_path = self.config_paths["classification_cache"]
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({f"ISIN:{self.ISIN}": [category, fund_type, "user"]}, f)

    def _acquisition_row(self, trade_date, quantity, price):
        """The purchase that put the units on the books.

        Without it the historical reconstruction has nothing, disagrees with the
        opening snapshot, and the ledger falls back to a lot whose acquisition
        date the engine invents — which § 18 Abs. 2 refuses to compute from. The
        trade is not incidental scaffolding: a real holding has one.
        """
        # ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol,
        # Description, ISIN, Strike, Expiry, Put/Call, TradeDate, Quantity,
        # TradePrice, IBCommission, IBCommissionCurrency, Buy/Sell,
        # TransactionID, Notes/Codes, UnderlyingSymbol, Conid, UnderlyingConid,
        # Multiplier, Open/CloseIndicator
        return ["U1234567", "EUR", "STK", "", "XYZ1", "XYZ1 BOND INDEX",
                self.ISIN, "", "", "", trade_date, quantity, price, "0", "EUR",
                "BUY", f"TX{trade_date.replace('-', '')}", "", "", self.CONID,
                "", "1", "O"]

    def _position_row(self, quantity, mark_price, position_value):
        # ClientAccountID, CurrencyPrimary, AssetClass, SubCategory, Symbol,
        # Description, ISIN, Quantity, PositionValue, MarkPrice, CostBasisMoney,
        # UnderlyingSymbol, Conid, UnderlyingConid, Multiplier
        return ["U1234567", "EUR", "STK", "", "XYZ1", "XYZ1 BOND INDEX",
                self.ISIN, quantity, position_value, mark_price, "10000",
                "", self.CONID, "", "1"]

    def test_a_fund_exported_as_stk_still_gets_its_vorabpauschale(self):
        """A fund held through calendar 2024 owes a Vorabpauschale on the VZ 2025
        return (18 Abs. 3 InvStG), whatever asset class the positions row names.

        Basisertrag = 10000 EUR * 2.29 % * 0.7 = 160.30 EUR (Basiszins for 2024,
        reference/bmf-guidance/basiszins-vorabpauschale.md). No distributions;
        the value gain of 1000 EUR does not bind the Satz 3 cap. So the gross
        Vorabpauschale is 160.30 EUR, on Zeilen 9-13 of the VZ 2025 return.
        """
        self._seed_classification()

        results = self._run_pipeline(
            tax_year=2025,
            # Acquired well before the Vorabpauschale year, so 18 Abs. 2 does
            # not reduce it and the expected figure below is the full one.
            trades_data=[self._acquisition_row("2023-03-15", "100", "90")],
            positions_prior_start_data=[self._position_row("100", "100", "10000")],
            positions_prior_end_data=[self._position_row("100", "110", "11000")],
            positions_start_data=[self._position_row("100", "110", "11000")],
            positions_end_data=[self._position_row("100", "110", "11000")],
        )

        funds = [a for a in results.asset_resolver.assets_by_internal_id.values()
                 if isinstance(a, InvestmentFund)]
        assert len(funds) == 1, "the classified instrument should be an InvestmentFund"

        assert len(results.vorabpauschale_items) == 1, (
            "a fund held through the whole Vorabpauschale year produced no "
            "Vorabpauschale record, so Zeile 13 would be silently empty"
        )
        vp = results.vorabpauschale_items[0]
        assert vp.vorabpauschale_year == 2024
        assert vp.gross_vorabpauschale_eur == Decimal("160.30")

    def test_losing_the_snapshot_at_classification_is_fatal(self, monkeypatch):
        """Calibration: with the snapshot dropped again, the run must stop.

        This reproduces the defect deliberately and holds that the guard sees
        it. Without the guard the run completes and declares nothing, which is
        exactly what it did before.

        The raise surfaces as `pytest.fail.Exception`: `_run_pipeline` converts
        every exception but `DataGapError` into a test failure, and
        `test_group7_currency_fifo.py` already asserts a `DataIntegrityError`
        through that wrapper. This follows that convention.
        """
        self._seed_classification()

        _break_the_retype(monkeypatch)

        with pytest.raises(pytest.fail.Exception) as excinfo:
            self._run_pipeline(
                tax_year=2025,
                positions_prior_start_data=[self._position_row("100", "100", "10000")],
                positions_prior_end_data=[self._position_row("100", "110", "11000")],
                positions_start_data=[self._position_row("100", "110", "11000")],
                positions_end_data=[self._position_row("100", "110", "11000")],
            )

        message = str(excinfo.value)
        assert self.ISIN in message, "the guard must name the affected instrument"
        assert "no longer owns the instrument" in message, (
            "the guard must say how the snapshot stopped reaching the fund"
        )
        assert "Zeilen 9-13" in message, (
            "the guard must say which declared figure would have gone missing"
        )

    def test_a_bond_losing_the_snapshot_does_not_stop_the_run(self, monkeypatch):
        """The guard is scoped to what 18 InvStG can reach.

        The prior-year snapshot is read for every instrument in the file, not
        only for funds. A bond cannot carry a Vorabpauschale, so a bond losing
        those values costs no declared figure — and stopping the run would block
        a declaration that is not at risk.

        The instrument must be classified as something that *changes* its Python
        type, or it is never retyped and the breakage below never happens: the
        positions row is `AssetClass=STK`, whose preliminary classification is
        already `Stock`, so leaving it a share would exercise nothing and pass
        whatever the guard does.
        """
        self._seed_classification("BOND", "NONE")

        _break_the_retype(monkeypatch)

        results = self._run_pipeline(
            tax_year=2025,
            # Acquired well before the Vorabpauschale year, so 18 Abs. 2 does
            # not reduce it and the expected figure below is the full one.
            trades_data=[self._acquisition_row("2023-03-15", "100", "90")],
            positions_prior_start_data=[self._position_row("100", "100", "10000")],
            positions_prior_end_data=[self._position_row("100", "110", "11000")],
            positions_start_data=[self._position_row("100", "110", "11000")],
            positions_end_data=[self._position_row("100", "110", "11000")],
        )

        assert results.vorabpauschale_items == [], (
            "a share owes no Vorabpauschale, so none should have been computed"
        )

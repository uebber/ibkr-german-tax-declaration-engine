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

from src.domain.assets import InvestmentFund
from src.domain.enums import AssetCategory, InvestmentFundType
from src.domain.exceptions import DataIntegrityError
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from tests.support.base import FifoTestCaseBase


# The five snapshot fields 18 Abs. 1 reads for the Vorabpauschale year: the
# year-start Ruecknahmepreis (Satz 2) and the last price set in the year (the
# Satz 3 cap), each with the currency it is quoted in, plus the quantity that
# establishes the fund was held at the year's start.
PRIOR_YEAR_SNAPSHOT_FIELDS = (
    "prior_year_soy_quantity",
    "prior_year_soy_position_value",
    "prior_year_soy_mark_price_currency",
    "prior_year_eoy_position_value",
    "prior_year_eoy_mark_price_currency",
)


def _stock_resolver_with_prior_year_snapshot():
    """A resolver holding one asset that arrived as a Stock and carries the
    prior-year snapshot, exactly as `process_positions()` leaves it."""
    classifier = MagicMock()
    classifier.preliminary_classify.return_value = (AssetCategory.STOCK, None)
    resolver = AssetResolver(asset_classifier=classifier)
    asset = resolver.get_or_create_asset(
        raw_isin="LU0000000001", raw_conid="900001", raw_symbol="XYZ1",
        raw_currency="SGD", raw_ibkr_asset_class="STK",
        raw_description="XYZ1 BOND INDEX", description_source_type="position",
    )
    asset.prior_year_soy_quantity = Decimal("100")
    asset.prior_year_soy_position_value = Decimal("14891")
    asset.prior_year_soy_mark_price_currency = "SGD"
    asset.prior_year_eoy_position_value = Decimal("15197")
    asset.prior_year_eoy_mark_price_currency = "SGD"
    return resolver, asset


def test_prior_year_snapshot_survives_a_classification_retype():
    """Applying the user's classification must not discard the year-start price.

    `replace_asset_type` builds a new object of the classified type and copies
    the old one's fields across. Every field 18 Abs. 1 reads has to be among
    them, or the Vorabpauschale is computed from nothing.
    """
    resolver, asset = _stock_resolver_with_prior_year_snapshot()
    before = {f: getattr(asset, f) for f in PRIOR_YEAR_SNAPSHOT_FIELDS}

    reclassified = resolver.replace_asset_type(
        asset.internal_asset_id,
        AssetCategory.INVESTMENT_FUND,
        InvestmentFundType.SONSTIGE_FONDS,
        "classified by the user as a fund",
    )

    assert isinstance(reclassified, InvestmentFund)
    after = {f: getattr(reclassified, f) for f in PRIOR_YEAR_SNAPSHOT_FIELDS}
    assert after == before, (
        "the prior-year snapshot 18 Abs. 1 reads was lost when the asset was "
        f"retyped: {[f for f in PRIOR_YEAR_SNAPSHOT_FIELDS if after[f] != before[f]]}"
    )


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
    losing_fund.prior_year_soy_quantity = Decimal("100")
    losing_fund.prior_year_soy_position_value = Decimal("14891")
    resolver.assets_by_internal_id[losing_fund.internal_asset_id] = losing_fund
    resolver.alias_map["CONID:900001"] = losing_fund
    orchestrator._record_prior_year_snapshot_fields(
        losing_fund, ("prior_year_soy_quantity", "prior_year_soy_position_value"))

    # The merge, as `get_or_create_asset` performs it: aliases move, values do not.
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
    assert "prior_year_soy_position_value" in message
    assert "merge" in message, (
        "the message must offer the merge as a cause, not only the copy list"
    )


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

        This reproduces the defect deliberately — the field-copy list loses the
        prior-year snapshot — and holds that the guard sees it. Without the
        guard the run completes and declares nothing, which is exactly what it
        did before.

        The raise surfaces as `pytest.fail.Exception`: `_run_pipeline` converts
        every exception but `DataGapError` into a test failure, and
        `test_group7_currency_fifo.py` already asserts a `DataIntegrityError`
        through that wrapper. This follows that convention.
        """
        self._seed_classification()

        original = AssetResolver._extract_common_asset_fields

        def _dropping_the_prior_year_snapshot(self_resolver, asset):
            common = original(self_resolver, asset)
            for field in PRIOR_YEAR_SNAPSHOT_FIELDS:
                common.pop(field, None)
            return common

        monkeypatch.setattr(
            AssetResolver, "_extract_common_asset_fields",
            _dropping_the_prior_year_snapshot,
        )

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
        assert "prior_year_soy_position_value" in message, (
            "the guard must name which snapshot field was lost"
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

        original = AssetResolver._extract_common_asset_fields

        def _dropping_the_prior_year_snapshot(self_resolver, asset):
            common = original(self_resolver, asset)
            for field in PRIOR_YEAR_SNAPSHOT_FIELDS:
                common.pop(field, None)
            return common

        monkeypatch.setattr(
            AssetResolver, "_extract_common_asset_fields",
            _dropping_the_prior_year_snapshot,
        )

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

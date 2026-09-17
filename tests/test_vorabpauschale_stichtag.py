"""
The day each Vorabpauschale price is converted to EUR at.

legal_basis: Rz. 18.6 of the BMF-Schreiben of 21.05.2019 requires a
foreign-currency Investmentanteil to be converted at the ECB reference rate
*"am jeweiligen Stichtag (Jahresanfang, Ausschuettungstermin, Jahresende)"* --
the rate of the input's **own** Stichtag [GT-INVSTG-018]. The inputs are the
first Ruecknahmepreis set in the calendar year (§ 18 Abs. 1 Satz 2) and the
last one set in it (the Satz 3 cap) [GT-INVSTG-010].

**A Stichtag is a day the price was set, never a fixed calendar date.** The
engine converted the Jahresanfang price at a hardcoded 2 January and the
Jahresende price at a hardcoded 31 December. Measured against the repository's
own first/last-business-day convention, 2 January is the year's first trading
day in only two of 2021-2025, and in 2021 and 2022 it is a Saturday and a
Sunday -- not a day the ECB published a rate at all. 31 December falls on a
weekend in 2022 and 2023.

Rz. 18.14 shows the administration anchoring the year on its *erster
Boersentag* rather than on a calendar date, which is the same reading.

Which day each snapshot describes is the convention stated in
`src/data_preparation.py`: `Positions-{X}-SoY.csv` is X's first trading day,
`Positions-{X}-EoY.csv` the close of X. Issue #59 turns that convention into a
checked fact; until it lands the day is derived from the same filename the
price was already selected by, so nothing new is assumed here.
"""
from datetime import date
from decimal import Context, Decimal
from unittest.mock import MagicMock

import pytest

import src.config as config
from dataclasses import dataclass

from src.domain.assets import (
    InvestmentFund, SnapshotsByAccount, person_snapshot)
from tests.support.prior_year_snapshots import snapshot_row
from src.domain.enums import InvestmentFundType
from src.engine.calculation_engine import FundUnitTranche, _calculate_vorabpauschale
from src.identification.asset_resolver import AssetResolver


@dataclass
class _FundFixture:
    """A fixture fund with the preceding year's two price snapshots of it."""
    asset: InvestmentFund
    prior_soy: SnapshotsByAccount
    prior_eoy: SnapshotsByAccount

    @property
    def internal_asset_id(self):
        return self.asset.internal_asset_id


def _fund(currency="USD", soy_price=Decimal("100"), eoy_price=Decimal("110"),
          soy_price_date=None):
    fund = InvestmentFund(
        fund_type=InvestmentFundType.AKTIENFONDS, description="Stichtag Fund",
        currency=currency, ibkr_isin="IE00STICH001", ibkr_symbol="STCH",
    )
    return _FundFixture(
        asset=fund,
        prior_soy=snapshot_row(fund.internal_asset_id, mark_price=soy_price,
                               mark_price_currency=currency,
                               mark_price_date=soy_price_date),
        prior_eoy=snapshot_row(fund.internal_asset_id, quantity=Decimal("100"),
                               mark_price=eoy_price, mark_price_currency=currency),
    )


def _conversion_dates(fund, vorabpauschale_year):
    """Run the computation and return the dates it converted each price at.

    Returns (soy_date, eoy_date) as the converter was actually called with,
    which is the only thing these tests are about.
    """
    resolver = MagicMock(spec=AssetResolver)
    resolver.assets_by_internal_id = {fund.internal_asset_id: fund.asset}
    resolver.get_asset_by_id.return_value = fund.asset

    converter = MagicMock()
    converter.convert_to_eur.side_effect = lambda amount, currency, dt: amount

    ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION,
                  rounding=config.DECIMAL_ROUNDING_MODE)
    lots = {fund.internal_asset_id: [FundUnitTranche(
        quantity=Decimal("100"),
        acquisition_date=date(vorabpauschale_year - 3, 5, 20))]}

    _calculate_vorabpauschale(
        asset_resolver=resolver,
        distributions_by_asset={},
        currency_converter=converter,
        vorabpauschale_year=vorabpauschale_year,
        opening_lots_by_asset=lots,
        prior_soy_positions=fund.prior_soy,
        prior_eoy_positions=fund.prior_eoy,
        prior_opening_positions={},
        ctx=ctx,
    )

    calls = converter.convert_to_eur.call_args_list
    assert len(calls) >= 2, f"expected a SoY and an EoY conversion, got {calls}"
    return calls[0].args[2], calls[1].args[2]


class TestJahresanfangStichtag:
    """Satz 2's price is set on the year's first trading day, whichever day that is."""

    @pytest.mark.parametrize("year,expected", [
        (2021, date(2021, 1, 4)),   # 1 Jan Fri closed, 2-3 Jan weekend
        (2022, date(2022, 1, 3)),   # 1 Jan Sat
        (2023, date(2023, 1, 3)),   # 1 Jan Sun -> observed Mon 2 Jan
        (2024, date(2024, 1, 2)),   # 1 Jan Mon closed
        (2025, date(2025, 1, 2)),   # 1 Jan Wed closed
    ])
    def test_converted_at_the_first_trading_day(self, year, expected):
        soy_date, _ = _conversion_dates(_fund(), year)
        assert soy_date == expected

    def test_never_converted_at_a_weekend(self):
        """2021-01-02 was a Saturday and 2022-01-02 a Sunday.

        The ECB publishes no reference rate on either, so the hardcoded date
        did not merely name the wrong day -- it named a day with no rate, and
        the converter's fallback silently supplied one from elsewhere.
        """
        for year in (2021, 2022):
            soy_date, _ = _conversion_dates(_fund(), year)
            assert soy_date.weekday() < 5, f"{year}: {soy_date} is a weekend"


class TestJahresendeStichtag:
    """The Satz 3 cap's upper bound is the last price set in the year.

    Not flagged in GT-INVSTG-018 or issue #60, both of which name only the
    Jahresanfang date; found by measurement while fixing it.
    """

    @pytest.mark.parametrize("year,expected", [
        (2021, date(2021, 12, 31)),  # Friday
        (2022, date(2022, 12, 30)),  # 31 Dec Sat
        (2023, date(2023, 12, 29)),  # 31 Dec Sun
        (2024, date(2024, 12, 31)),  # Tuesday
    ])
    def test_converted_at_the_last_business_day(self, year, expected):
        _, eoy_date = _conversion_dates(_fund(), year)
        assert eoy_date == expected


class TestSubstitutedPriceCarriesItsOwnDate:
    """The substitution path takes a price from the *preceding* year.

    `_resolve_vorabpauschale_start_price()` substitutes the last price set
    before the year began where a fund held at the open has none in the
    year's own snapshot. Converting that price at a date inside the
    Vorabpauschale year puts the price and the rate in different years, which
    is the second of the two causes issue #60 names.
    """

    def test_a_substituted_price_converts_at_the_day_it_was_set(self):
        soy_date, _ = _conversion_dates(
            _fund(soy_price_date=date(2022, 12, 30)), 2023)
        assert soy_date == date(2022, 12, 30)

    def test_an_unsubstituted_price_still_uses_the_years_own_first_day(self):
        soy_date, _ = _conversion_dates(_fund(), 2023)
        assert soy_date == date(2023, 1, 3)


class TestTheEndsOfTheChannel:
    """The engine reads a date the parsing layer has to have written.

    Every test above hands the engine a fund object directly, so all of them
    survive the parsing layer never setting the field at all — the blind spot
    CLAUDE.md names for a new channel. These probe the two ends: the parser
    writes it, and a retype does not drop it.
    """

    def test_the_parser_records_the_day_each_snapshot_describes(self, tmp_path):
        from src.classification.asset_classifier import AssetClassifier
        from src.parsers.parsing_orchestrator import ParsingOrchestrator
        from src.parsers.raw_models import RawPositionRecord

        def record(qty, price, value):
            return RawPositionRecord(
                CurrencyPrimary="USD", AssetClass="STK", Symbol="TF",
                Description="Test Fund", ISIN="IE00TEST0001", Conid="1",
                Quantity=qty, MarkPrice=price, PositionValue=value,
                CostBasisMoney=value)

        classifier = AssetClassifier(cache_file_path=str(tmp_path / "c.json"))
        orch = ParsingOrchestrator(
            asset_resolver=AssetResolver(asset_classifier=classifier),
            asset_classifier=classifier, interactive_classification=False)
        orch.raw_positions_prior_start = [record("100", "10", "1000")]
        orch.raw_positions_prior_end = [record("100", "11", "1100")]

        orch.process_positions(tax_year=2024)      # Vorabpauschale year 2023

        asset = next(iter(orch.asset_resolver.assets_by_internal_id.values()))
        asset_id = asset.internal_asset_id
        assert person_snapshot(orch.prior_soy_positions, asset_id).mark_price_date \
            == date(2023, 1, 3)
        assert person_snapshot(orch.prior_eoy_positions, asset_id).mark_price_date \
            == date(2023, 12, 29)

    def test_a_substituted_price_is_dated_in_the_preceding_year(self, tmp_path):
        from src.classification.asset_classifier import AssetClassifier
        from src.parsers.parsing_orchestrator import ParsingOrchestrator
        from src.parsers.raw_models import RawPositionRecord

        def record(qty, price, value):
            return RawPositionRecord(
                CurrencyPrimary="USD", AssetClass="STK", Symbol="TF",
                Description="Test Fund", ISIN="IE00TEST0001", Conid="1",
                Quantity=qty, MarkPrice=price, PositionValue=value,
                CostBasisMoney=value)

        classifier = AssetClassifier(cache_file_path=str(tmp_path / "c.json"))
        orch = ParsingOrchestrator(
            asset_resolver=AssetResolver(asset_classifier=classifier),
            asset_classifier=classifier, interactive_classification=False)
        # Held at the close of 2022, gone from the 2023 start-of-year snapshot.
        orch.raw_positions_prior_opening = [record("100", "9", "900")]
        orch.raw_positions_prior_start = []
        orch.raw_positions_prior_end = [record("150", "12", "1800")]

        orch.process_positions(tax_year=2024)      # Vorabpauschale year 2023

        substituted = next(snap for snap in orch.prior_soy_positions.values()
                           if snap.mark_price is not None)
        assert substituted.mark_price == Decimal("9")
        assert substituted.mark_price_date == date(2022, 12, 30), (
            "the substituted price is the last one set in 2022, so its Stichtag "
            "is in 2022 — not the first trading day of 2023")

    def test_the_stichtag_survives_a_classification_retype(self):
        """A positions row arrives as a Stock and becomes a fund only once the
        user's classification is applied.

        `replace_asset_type` builds a new object of the classified type. It used
        to carry the snapshot across by copying a hand-listed set of fields, and
        a date left off that list was silently replaced by the year-derived
        convention -- wrong by a year on the substitution path. There is no list
        now: the snapshot is a registry row keyed by `internal_asset_id`, and
        the rebuild keeps that id, so the Stichtag reaches the retyped fund
        whatever fields the new object declares."""
        from unittest.mock import MagicMock as MM

        from src.domain.enums import AssetCategory

        classifier = MM()
        classifier.preliminary_classify.return_value = (AssetCategory.STOCK, None)
        resolver = AssetResolver(asset_classifier=classifier)
        asset = resolver.get_or_create_asset(
            raw_isin="LU0000000002", raw_conid="900002", raw_symbol="XYZ2",
            raw_currency="SGD", raw_ibkr_asset_class="STK",
            raw_description="XYZ2 BOND INDEX", description_source_type="position",
        )
        prior_soy = snapshot_row(asset.internal_asset_id, mark_price=Decimal("9"),
                                 mark_price_currency="SGD",
                                 mark_price_date=date(2022, 12, 30))
        prior_eoy = snapshot_row(asset.internal_asset_id, quantity=Decimal("100"),
                                 mark_price=Decimal("12"), mark_price_currency="SGD",
                                 mark_price_date=date(2023, 12, 29))

        retyped = resolver.replace_asset_type(
            asset.internal_asset_id, AssetCategory.INVESTMENT_FUND,
            InvestmentFundType.SONSTIGE_FONDS, "classified by the user as a fund")

        assert retyped.internal_asset_id == asset.internal_asset_id
        assert person_snapshot(prior_soy, retyped.internal_asset_id).mark_price_date \
            == date(2022, 12, 30)
        assert person_snapshot(prior_eoy, retyped.internal_asset_id).mark_price_date \
            == date(2023, 12, 29)


def test_a_price_settled_elsewhere_is_converted_in_its_own_currency():
    """Rz. 18.6 converts at the rate for the currency the price is quoted in.

    The year-start Ruecknahmepreis need not come from the export: an issuer's
    published NAV is preferred to it, and may be quoted in another currency than
    the fund itself. Falling back to the fund's currency would convert a USD NAV
    at a EUR rate -- which is no conversion at all -- and the Basisertrag would
    be the foreign figure taken as euros.
    """
    fund = _fund(currency="EUR", soy_price=Decimal("100"), eoy_price=Decimal("110"))
    # As `resolve_year_start_prices` leaves it, having taken the issuer's NAV.
    fund.prior_soy = snapshot_row(fund.internal_asset_id, mark_price=Decimal("100"),
                                  mark_price_currency="USD",
                                  mark_price_date=date(2023, 1, 3))

    resolver = MagicMock(spec=AssetResolver)
    resolver.assets_by_internal_id = {fund.internal_asset_id: fund.asset}
    resolver.get_asset_by_id.return_value = fund.asset
    converter = MagicMock()
    converter.convert_to_eur.side_effect = lambda amount, currency, dt: amount
    ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION,
                  rounding=config.DECIMAL_ROUNDING_MODE)
    lots = {fund.internal_asset_id: [FundUnitTranche(
        quantity=Decimal("100"), acquisition_date=date(2020, 5, 20))]}

    _calculate_vorabpauschale(
        asset_resolver=resolver, distributions_by_asset={},
        currency_converter=converter, vorabpauschale_year=2023,
        opening_lots_by_asset=lots, prior_soy_positions=fund.prior_soy,
        prior_eoy_positions=fund.prior_eoy, prior_opening_positions={}, ctx=ctx)

    soy_call = converter.convert_to_eur.call_args_list[0]
    assert soy_call.args[1] == "USD", (
        "the year-start price is converted in the currency it is quoted in, not "
        "the one the fund is quoted in")


def test_a_euro_fund_is_untouched_by_any_of_this():
    """Stated because the parity result has to say so rather than imply it:
    Rz. 18.6 reaches only *"in fremden Waehrungen notierende"* Anteile, so a
    EUR-denominated fund's figure cannot move whichever day is chosen."""
    resolver = MagicMock(spec=AssetResolver)
    fund = _fund(currency="EUR")
    resolver.assets_by_internal_id = {fund.internal_asset_id: fund.asset}
    resolver.get_asset_by_id.return_value = fund.asset

    converter = MagicMock()
    converter.convert_to_eur.side_effect = (
        lambda amount, currency, dt: amount if currency == "EUR" else None)
    ctx = Context(prec=config.INTERNAL_CALCULATION_PRECISION,
                  rounding=config.DECIMAL_ROUNDING_MODE)
    lots = {fund.internal_asset_id: [FundUnitTranche(
        quantity=Decimal("100"), acquisition_date=date(2020, 5, 20))]}

    results = _calculate_vorabpauschale(
        asset_resolver=resolver, distributions_by_asset={},
        currency_converter=converter, vorabpauschale_year=2023,
        opening_lots_by_asset=lots, prior_soy_positions=fund.prior_soy,
        prior_eoy_positions=fund.prior_eoy, prior_opening_positions={}, ctx=ctx,
    )

    assert len(results) == 1
    # 100 * 0.0255 * 0.7 = 1.785 per unit, capped by (110-100)+0 = 10, x100 units
    assert results[0].gross_vorabpauschale_eur == Decimal("178.50")

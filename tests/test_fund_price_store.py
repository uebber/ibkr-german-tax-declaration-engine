"""
The year-start Ruecknahmepreis, for every fund that owes a Vorabpauschale.

legal_basis: § 18 Abs. 1 Satz 2 InvStG builds the Basisertrag from *"dem
Ruecknahmepreis des Investmentanteils zu Beginn des Kalenderjahres"*
[GT-INVSTG-010]. Satz 4 admits a Boersen- oder Marktpreis **only where no
Ruecknahmepreis was set**. Abs. 2 then reduces the figure by one twelfth per
full month before the month of acquisition [GT-INVSTG-011], and Rz. 18.4
multiplies by the units held at the close of 31 December [GT-INVSTG-017].

**The price is a property of the fund, not of the holding**, so it is sought for
every fund held across the year end -- whether or not the start-of-year position
report happens to carry a row for it. Until 2026-08-08 the engine took the
report's mark wherever it had one and only went looking when it did not, which
put Satz 4's substitute ahead of the primary measure for every fund held on
1 January.

The order is: a price stored from an earlier run, then the provider's published
NAV, then the taxpayer -- offered the report's price as the default -- then the
report's price where nobody can be asked, then a stopped run. What must never
happen is the engine inventing one.
"""
import json
import os
from datetime import date
from decimal import Decimal

import pytest

from src.domain.assets import InvestmentFund, SnapshotsByAccount, person_snapshot
from src.domain.enums import InvestmentFundType
from src.processing.data_gaps import DataGapCollector, DataGapError, GapSeverity
from src.processing.fund_prices import (
    ISSUER_NAV_CODE,
    MARKET_FALLBACK_CODE,
    FundPrice,
    FundPriceStore,
    resolve_year_start_prices,
)
from tests.support.base import FifoTestCaseBase
from tests.support.prior_year_snapshots import snapshot_row


# The preceding year's snapshots the funds below are reported in, per
# (account, asset) exactly as the engine holds them. Module-level because
# `_fund` writes the rows and `_resolve` reads them, while a test names only the
# fund; cleared between tests by the autouse fixture beneath.
_PRIOR_SOY: SnapshotsByAccount = {}
_PRIOR_EOY: SnapshotsByAccount = {}


@pytest.fixture(autouse=True)
def _empty_prior_year_registries():
    _PRIOR_SOY.clear()
    _PRIOR_EOY.clear()
    yield


def _fund(*, eoy_qty=Decimal("100"), soy_price=None, soy_currency="EUR",
          soy_day=date(2023, 1, 2), isin="IE00TESTPRC1", description="A Fund"):
    fund = InvestmentFund(
        fund_type=InvestmentFundType.AKTIENFONDS, description=description,
        currency="EUR", ibkr_isin=isin, ibkr_symbol="MYF")
    _PRIOR_EOY.update(snapshot_row(fund.internal_asset_id, quantity=eoy_qty))
    _PRIOR_SOY.update(snapshot_row(
        fund.internal_asset_id,
        mark_price=soy_price,
        mark_price_currency=soy_currency if soy_price is not None else None,
        mark_price_date=soy_day if soy_price is not None else None,
    ))
    return fund


def _year_start_price(fund):
    """The year-start Ruecknahmepreis the run settled on, as the engine will read it."""
    return person_snapshot(_PRIOR_SOY, fund.internal_asset_id)


def _price(price="31.1026", currency="USD", day=date(2023, 1, 3), source="issuer NAV file"):
    return FundPrice(price=Decimal(price), currency=currency, date_set=day, source=source)


def _nav(price="31.1026", currency="USD", day=date(2023, 1, 3)):
    from src.processing.fund_price_sources import FetchedPrice
    return FetchedPrice(price=Decimal(price), currency=currency, date_set=day,
                        provider="iShares", url="https://example.invalid/nav",
                        fund_name="A Fund")


def _resolve(funds, *, store, interactive=False, collector=None, year=2023,
             fetch=None, ask=None, auto_fetch=True):
    return resolve_year_start_prices(
        assets=funds, prior_soy_positions=_PRIOR_SOY, prior_eoy_positions=_PRIOR_EOY,
        vorabpauschale_year=year, store=store, interactive=interactive,
        data_gap_collector=collector if collector is not None else DataGapCollector(),
        ask=ask, fetch=fetch, auto_fetch=auto_fetch)


class TestTheStore:
    def test_round_trips_through_the_file(self, tmp_path):
        path = tmp_path / "prices.json"
        store = FundPriceStore(cache_file_path=str(path))
        store.put("ISIN:IE00TESTPRC1", 2023, _price())
        store.save()

        assert FundPriceStore(cache_file_path=str(path)).get(
            "ISIN:IE00TESTPRC1", 2023) == _price()

    def test_the_price_survives_as_a_decimal_built_from_a_string(self, tmp_path):
        """Never Decimal(float): the stored text is the value."""
        path = tmp_path / "p.json"
        store = FundPriceStore(cache_file_path=str(path))
        store.put("ISIN:X", 2023, _price(price="31.1026"))
        store.save()

        got = FundPriceStore(cache_file_path=str(path)).get("ISIN:X", 2023)
        assert got.price == Decimal("31.1026") and str(got.price) == "31.1026"

    def test_the_year_is_part_of_the_key(self, tmp_path):
        store = FundPriceStore(cache_file_path=str(tmp_path / "p.json"))
        store.put("ISIN:X", 2023, _price(price="10"))
        store.put("ISIN:X", 2024, _price(price="20"))

        assert store.get("ISIN:X", 2023).price == Decimal("10")
        assert store.get("ISIN:X", 2024).price == Decimal("20")
        assert store.get("ISIN:X", 2025) is None

    def test_a_corrupt_file_is_not_silently_treated_as_empty(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text("{not json")
        with pytest.raises(Exception):
            FundPriceStore(cache_file_path=str(path))


class TestTheOrderOfSources:
    def test_the_providers_nav_beats_the_position_report(self, tmp_path):
        """The change of 2026-08-08, and the point of the whole pass.

        The report's mark is a Boersen- oder Marktpreis; Satz 4 admits one only
        where no Ruecknahmepreis was set, and for a fund that redeems at NAV one
        is set. Preferring the report because it was already in the export put
        the substitute ahead of the primary measure.
        """
        fund = _fund(soy_price=Decimal("100"))

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: _nav(price="101.5"))

        assert _year_start_price(fund).mark_price == Decimal("101.5")

    def test_the_nav_brings_its_own_day_and_currency(self, tmp_path):
        """Rz. 18.6 converts at the rate of the day the price was set
        [GT-INVSTG-018]; the report's day belongs to the report's price."""
        fund = _fund(soy_price=Decimal("100"), soy_currency="EUR", soy_day=date(2023, 1, 2))

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: _nav(currency="USD", day=date(2023, 1, 3)))

        assert _year_start_price(fund).mark_price_currency == "USD"
        assert _year_start_price(fund).mark_price_date == date(2023, 1, 3)

    def test_the_reports_own_price_keeps_its_day_and_its_currency(self, tmp_path):
        """The report's price is a figure the run may use, so it has to carry
        the two things Rz. 18.6 converts it by: the day it was set and the
        currency it is quoted in. The NAV path above pins the same two for a
        price obtained elsewhere; this pins them for the export's own.
        """
        fund = _fund(soy_price=Decimal("100"), soy_currency="SGD",
                     soy_day=date(2023, 1, 3))

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: None)

        settled = _year_start_price(fund)
        assert settled.mark_price == Decimal("100")
        assert settled.mark_price_currency == "SGD"
        assert settled.mark_price_date == date(2023, 1, 3)

    def test_units_in_either_account_are_units_held(self, tmp_path):
        """Whether a fund owes a Vorabpauschale at all is the person's holding.

        Rz. 18.4 multiplies by the units held at the close of 31 December, and
        those are the person's ([GT-ESTG20-061]). Reading one account's row
        would leave a fund the taxpayer still holds unpriced, and its deemed
        income would leave the declaration with nothing recorded.
        """
        fund = InvestmentFund(
            fund_type=InvestmentFundType.AKTIENFONDS, description="A Fund",
            currency="EUR", ibkr_isin="IE00TESTPRC1", ibkr_symbol="MYF")
        # The account the export happens to list last holds nothing.
        _PRIOR_EOY.update(snapshot_row(fund.internal_asset_id, quantity=Decimal("100"),
                                       account="U1111111"))
        _PRIOR_EOY.update(snapshot_row(fund.internal_asset_id, quantity=Decimal("0"),
                                       account="U2222222"))
        _PRIOR_SOY.update(snapshot_row(fund.internal_asset_id, account="U1111111"))
        _PRIOR_SOY.update(snapshot_row(fund.internal_asset_id, account="U2222222"))

        priced = _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                          fetch=lambda a, y: _nav(price="31.1026"))

        assert priced == 1, "a fund held in one of two accounts still owes a figure"
        assert _year_start_price(fund).mark_price == Decimal("31.1026")

    def test_the_settled_price_reaches_every_account_holding_the_fund(self, tmp_path):
        """The price is per unit, so it belongs on every account's row.

        A per-unit price is the same value whichever account's row a per-account
        ledger reads, so it must be written to every row -- a fund held in one
        account of two would otherwise leave the other's row without it.
        """
        fund = InvestmentFund(
            fund_type=InvestmentFundType.AKTIENFONDS, description="A Fund",
            currency="EUR", ibkr_isin="IE00TESTPRC1", ibkr_symbol="MYF")
        for account in ("U1111111", "U2222222"):
            _PRIOR_EOY.update(snapshot_row(fund.internal_asset_id,
                                           quantity=Decimal("50"), account=account))
            _PRIOR_SOY.update(snapshot_row(fund.internal_asset_id,
                                           quantity=Decimal("50"), account=account))

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: _nav(price="31.1026"))

        rows = [snap for (_a, aid), snap in _PRIOR_SOY.items()
                if aid == fund.internal_asset_id]
        assert len(rows) == 2
        assert all(r.mark_price == Decimal("31.1026") for r in rows)

    def test_a_fund_the_opening_report_omits_is_recorded_under_the_accounts_that_held_it(
            self, tmp_path):
        """A fund bought during the Vorabpauschale year is in no start-of-year
        row, so the settled price has nowhere obvious to go. It goes under the
        accounts the closing report names, which are accounts the export states
        -- rather than under an invented one.
        """
        fund = InvestmentFund(
            fund_type=InvestmentFundType.AKTIENFONDS, description="A Fund",
            currency="EUR", ibkr_isin="IE00TESTPRC1", ibkr_symbol="MYF")
        _PRIOR_EOY.update(snapshot_row(fund.internal_asset_id, quantity=Decimal("100"),
                                       account="U1111111"))

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: _nav(price="31.1026"))

        assert list(_PRIOR_SOY) == [("U1111111", fund.internal_asset_id)]
        assert _year_start_price(fund).mark_price == Decimal("31.1026")

    def test_a_fund_absent_from_the_report_is_priced_the_same_way(self, tmp_path):
        fund = _fund(soy_price=None)

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: _nav(price="31.1026"))

        assert _year_start_price(fund).mark_price == Decimal("31.1026")

    def test_a_stored_price_is_used_without_asking_the_provider(self, tmp_path):
        """A past year's first NAV does not change, so a run that already has
        one does not go back to the network for it."""
        store = FundPriceStore(cache_file_path=str(tmp_path / "p.json"))
        store.put("ISIN:IE00TESTPRC1", 2023, _price(price="99"))
        calls = []

        _resolve([_fund()], store=store, fetch=lambda a, y: calls.append(a) or _nav())

        assert calls == []

    def test_a_fetched_nav_is_stored_so_the_next_run_is_offline(self, tmp_path):
        path = tmp_path / "p.json"
        store = FundPriceStore(cache_file_path=str(path))

        _resolve([_fund()], store=store, fetch=lambda a, y: _nav(price="31.1026"))

        again = FundPriceStore(cache_file_path=str(path)).get("ISIN:IE00TESTPRC1", 2023)
        assert again is not None and again.price == Decimal("31.1026")

    def test_the_reports_own_price_is_not_stored(self, tmp_path):
        """It is in the export and is re-read every run. Storing it would freeze
        a substitute in place and hide a provider that came back."""
        path = tmp_path / "p.json"
        store = FundPriceStore(cache_file_path=str(path))

        _resolve([_fund(soy_price=Decimal("100"))], store=store, fetch=lambda a, y: None)

        assert FundPriceStore(cache_file_path=str(path)).get(
            "ISIN:IE00TESTPRC1", 2023) is None

    def test_the_provenance_of_a_fetched_price_reaches_the_report(self, tmp_path):
        collector = DataGapCollector()

        _resolve([_fund()], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 collector=collector, fetch=lambda a, y: _nav())

        gap = collector.gaps[-1]
        assert gap.code == ISSUER_NAV_CODE and gap.severity is GapSeverity.WARNING
        assert "example.invalid/nav" in gap.detail


class TestWhenNoRuecknahmepreisCanBeHad:
    def test_a_non_interactive_run_falls_back_to_the_report_and_says_so(self, tmp_path):
        """The report's price is a figure the run may use — Satz 4 admits it
        where no Ruecknahmepreis was set. What would be wrong is using it
        silently, when one probably was set and merely could not be reached."""
        collector = DataGapCollector()
        fund = _fund(soy_price=Decimal("100"))

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 collector=collector, fetch=lambda a, y: None)

        assert _year_start_price(fund).mark_price == Decimal("100")
        gap = collector.gaps[-1]
        assert gap.code == MARKET_FALLBACK_CODE and gap.severity is GapSeverity.WARNING

    def test_the_taxpayer_is_offered_the_reports_price_as_the_default(self, tmp_path):
        seen = {}

        def ask(asset, year, snapshot):
            seen["snapshot"] = snapshot
            return _price(price="102")

        _resolve([_fund(soy_price=Decimal("100"))], interactive=True, ask=ask,
                 store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: None)

        assert seen["snapshot"].price == Decimal("100")

    def test_accepting_that_default_is_recorded_as_the_substitute_it_is(self, tmp_path):
        """Answering with the report's own figure is not a Ruecknahmepreis, and
        the report must not claim it is."""
        collector = DataGapCollector()

        _resolve([_fund(soy_price=Decimal("100"))], interactive=True,
                 ask=lambda a, y, snap: snap,
                 store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 collector=collector, fetch=lambda a, y: None)

        assert collector.gaps[-1].code == MARKET_FALLBACK_CODE

    def test_an_accepted_default_is_not_stored_as_though_it_were_a_nav(self, tmp_path):
        """Storing it would freeze Satz 4's substitute in place and hide a
        provider that came back next year."""
        path = tmp_path / "p.json"
        store = FundPriceStore(cache_file_path=str(path))

        _resolve([_fund(soy_price=Decimal("100"))], interactive=True,
                 ask=lambda a, y, snap: snap, store=store, fetch=lambda a, y: None)

        assert FundPriceStore(cache_file_path=str(path)).get(
            "ISIN:IE00TESTPRC1", 2023) is None

    def test_a_price_the_taxpayer_researched_is_not_a_market_fallback(self, tmp_path):
        """Read off the source, not the value. A Ruecknahmepreis someone looked
        up may happen to equal the report's mark, and it is still not the
        substitute — so it is labelled and stored as what it is."""
        path = tmp_path / "p.json"
        collector = DataGapCollector()
        typed = FundPrice(price=Decimal("100"), currency="EUR",
                          date_set=date(2023, 1, 3), source="iShares NAV-Historie")

        _resolve([_fund(soy_price=Decimal("100"))], interactive=True,
                 ask=lambda a, y, snap: typed,
                 store=FundPriceStore(cache_file_path=str(path)),
                 collector=collector, fetch=lambda a, y: None)

        assert collector.gaps[-1].code == ISSUER_NAV_CODE
        assert FundPriceStore(cache_file_path=str(path)).get(
            "ISIN:IE00TESTPRC1", 2023) is not None

    def test_a_fund_with_no_report_row_and_no_answer_stops_the_run(self, tmp_path):
        """One run identifies the whole problem, naming every fund."""
        collector = DataGapCollector()
        funds = [_fund(soy_price=None, isin="IE00AAA", description="Fund A"),
                 _fund(soy_price=None, isin="IE00BBB", description="Fund B")]

        with pytest.raises(DataGapError) as excinfo:
            _resolve(funds, store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                     collector=collector, fetch=lambda a, y: None)

        assert "Fund A" in str(excinfo.value) and "Fund B" in str(excinfo.value)
        assert collector.gaps[-1].severity is GapSeverity.FAIL_FAST

    def test_declining_to_answer_is_not_treated_as_an_answer(self, tmp_path):
        with pytest.raises(DataGapError):
            _resolve([_fund(soy_price=None)], interactive=True,
                     ask=lambda a, y, snap: None,
                     store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                     fetch=lambda a, y: None)


class TestWhoIsProcessed:
    def test_a_fund_not_held_at_the_close_is_never_priced(self, tmp_path):
        """Rz. 18.4 multiplies by the units held at the close of 31 December."""
        calls = []
        _resolve([_fund(eoy_qty=Decimal("0"), soy_price=Decimal("100"))],
                 store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: calls.append(a) or _nav())
        assert calls == []

    def test_nothing_happens_when_the_basiszins_cannot_produce_a_figure(self, tmp_path):
        """Calendar 2022's Basiszins is negative, so no price can move a figure
        and no fund is worth a network round trip or a question."""
        calls = []
        _resolve([_fund()], year=2022,
                 store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=lambda a, y: calls.append(a) or _nav())
        assert calls == []

    def test_auto_fetch_off_keeps_the_run_offline(self, tmp_path):
        """`FUND_PRICE_AUTO_FETCH = False` is the switch a user has; with a
        report price present the run still completes."""
        fund = _fund(soy_price=Decimal("100"))

        _resolve([fund], store=FundPriceStore(cache_file_path=str(tmp_path / "p.json")),
                 fetch=None, auto_fetch=False)

        assert _year_start_price(fund).mark_price == Decimal("100")


class TestThePurchasePriceAnchor:
    """What the account paid per unit, shown beside the price being asked for.

    Derived entirely from trades already imported, so it invents nothing. It
    cannot tell a right Ruecknahmepreis from a slightly wrong one, and is not
    meant to: it catches the factor-of-a-hundred typo and the fetch that landed
    on the wrong share class.
    """

    def _buy(self, asset, day, quantity, price, currency="EUR"):
        from src.domain.enums import FinancialEventType
        from src.domain.events import TradeEvent
        return TradeEvent(
            asset.internal_asset_id, day,
            quantity=Decimal(quantity), price_foreign_currency=Decimal(price),
            event_type=FinancialEventType.TRADE_BUY_LONG, local_currency=currency)

    def test_it_weights_by_volume_rather_than_averaging_the_prices(self):
        from src.processing.fund_prices import acquisition_anchor
        fund = _fund()
        events = [self._buy(fund, "2023-03-01", "100", "10"),
                  self._buy(fund, "2023-09-01", "300", "20")]

        anchor = acquisition_anchor(fund, events, 2023)

        # (100*10 + 300*20) / 400 = 17.50, not the flat mean of 15.
        assert anchor.price_per_unit == Decimal("17.5")
        assert anchor.acquisitions == 2
        assert anchor.first_date == date(2023, 3, 1)

    def test_only_purchases_inside_the_vorabpauschale_year_count(self):
        from src.processing.fund_prices import acquisition_anchor
        fund = _fund()
        events = [self._buy(fund, "2022-06-01", "100", "5"),
                  self._buy(fund, "2023-06-01", "100", "10")]

        assert acquisition_anchor(fund, events, 2023).price_per_unit == Decimal("10")

    def test_another_funds_trades_are_not_counted(self):
        from src.processing.fund_prices import acquisition_anchor
        fund, other = _fund(), _fund(isin="IE00OTHER")
        events = [self._buy(other, "2023-06-01", "100", "999")]

        assert acquisition_anchor(fund, events, 2023) is None

    def test_a_mixed_currency_holding_yields_nothing(self):
        """Two currencies have no single price per unit, and showing one under
        the other's label would mislead the very check this exists for."""
        from src.processing.fund_prices import acquisition_anchor
        fund = _fund()
        events = [self._buy(fund, "2023-03-01", "100", "10", currency="EUR"),
                  self._buy(fund, "2023-09-01", "100", "20", currency="USD")]

        assert acquisition_anchor(fund, events, 2023) is None


class TestThePromptDefaults:
    """Reached only when no Ruecknahmepreis could be had.

    The provider is asked first and for every fund, so a person is consulted
    only where that failed. What they are offered is the position report's
    price, which is Satz 4's substitute — so accepting it is a real keystroke
    and the caller records it as the substitute it is.
    """

    def _snapshot(self, price="100", currency="EUR", day=date(2023, 1, 2)):
        return FundPrice(price=Decimal(price), currency=currency, date_set=day,
                         source="Positionsbericht zum Jahresanfang "
                                "(Boersen- bzw. Marktpreis)")

    def _answer(self, monkeypatch, replies):
        from src.processing import fund_prices
        pending = list(replies)
        monkeypatch.setattr("builtins.input", lambda *a, **k: pending.pop(0))
        return fund_prices

    def test_pressing_enter_accepts_the_reports_figure_whole(self, monkeypatch):
        fund_prices = self._answer(monkeypatch, ["", "", "", ""])

        got = fund_prices.prompt_for_fund_price(_fund(), 2023, self._snapshot())

        assert got.price == Decimal("100")
        assert got.currency == "EUR"
        assert got.date_set == date(2023, 1, 2)
        assert got.source.startswith("Positionsbericht")

    def test_the_reports_day_is_the_default_not_a_calendar_one(self, monkeypatch):
        """Rz. 18.6 converts at the day the price was set ([GT-INVSTG-018]), and
        the report's price belongs to the report's day."""
        fund_prices = self._answer(monkeypatch, ["", "", "", ""])

        got = fund_prices.prompt_for_fund_price(
            _fund(), 2023, self._snapshot(day=date(2023, 1, 3)))

        assert got.date_set == date(2023, 1, 3)

    def test_a_typed_price_overrides_the_offered_one(self, monkeypatch):
        fund_prices = self._answer(
            monkeypatch, ["80,25", "USD", "2023-01-03", "iShares NAV-Historie"])

        got = fund_prices.prompt_for_fund_price(_fund(), 2023, self._snapshot())

        assert got.price == Decimal("80.25")      # comma accepted as a decimal point
        assert got.currency == "USD"
        assert got.source == "iShares NAV-Historie"

    def test_with_no_report_row_an_empty_answer_is_a_refusal(self, monkeypatch):
        """Nothing to default to, and an empty price is the fail-fast case
        rather than a zero."""
        fund_prices = self._answer(monkeypatch, [""])

        assert fund_prices.prompt_for_fund_price(_fund(), 2023, None) is None

    def test_with_no_report_row_no_day_is_proposed(self, monkeypatch):
        """A fund launched during the year has its first price on its own first
        day, not the year's (Rz. 18.7, [GT-INVSTG-035]). Proposing a calendar
        date would get it accepted with Enter, and the wrong Stichtag converts
        at the wrong rate ([GT-INVSTG-018]). So: no default, and an empty answer
        is a refusal rather than a guess."""
        # A source is supplied, so a missing day is the only thing that can
        # refuse this — an earlier version of this test passed because the
        # empty source refused it first, and survived the mutation.
        fund_prices = self._answer(
            monkeypatch, ["20.14", "USD", "", "VanEck NAV-Historie"])

        assert fund_prices.prompt_for_fund_price(_fund(), 2023, None) is None

    def test_with_no_report_row_a_typed_day_is_taken(self, monkeypatch):
        fund_prices = self._answer(
            monkeypatch, ["20.14", "USD", "2023-04-18", "VanEck NAV-Historie"])

        got = fund_prices.prompt_for_fund_price(_fund(), 2023, None)

        assert got.date_set == date(2023, 4, 18) and got.price == Decimal("20.14")

    def test_a_price_dated_outside_the_year_is_refused(self, monkeypatch):
        """A price from another year is another year's figure, against another
        Basiszins ([GT-INVSTG-014])."""
        fund_prices = self._answer(monkeypatch, ["", "", "", ""])

        got = fund_prices.prompt_for_fund_price(
            _fund(), 2023, self._snapshot(day=date(2022, 12, 30)))

        assert got is None

    def test_the_prompt_takes_three_positional_arguments(self, monkeypatch):
        """`make_price_prompt` builds the `ask` the resolver calls, and the
        resolver passes the snapshot as the third argument."""
        fund_prices = self._answer(monkeypatch, ["", "", "", ""])

        ask = fund_prices.make_price_prompt([])
        got = ask(_fund(), 2023, self._snapshot(price="55"))

        assert got.price == Decimal("55")


class TestTheEndsOfTheChannel(FifoTestCaseBase):
    """The pipeline has to actually call the resolver.

    Every test above calls `resolve_year_start_prices` directly, so all
    of them survive deleting its call site in `src/pipeline_runner.py` — which
    is the blind spot CLAUDE.md names for a newly added channel, and which was
    measured to be real here: with the call site replaced by `pass`, the whole
    suite stayed green at 885. These run the real pipeline.
    """

    ISIN = "LU0000000009"
    CONID = "900009"

    def _seed_classification(self):
        cache_path = self.config_paths["classification_cache"]
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({f"ISIN:{self.ISIN}": ["INVESTMENT_FUND", "AKTIENFONDS", "user"]}, f)

    def _acquisition_row(self, trade_date, quantity, price):
        return ["U1234567", "EUR", "STK", "", "MYF", "MID YEAR FUND",
                self.ISIN, "", "", "", trade_date, quantity, price, "0", "EUR",
                "BUY", f"TX{trade_date.replace('-', '')}", "", "", self.CONID,
                "", "1", "O"]

    def _position_row(self, quantity, mark_price, position_value):
        return ["U1234567", "EUR", "STK", "", "MYF", "MID YEAR FUND",
                self.ISIN, quantity, position_value, mark_price, "9000",
                "", self.CONID, "", "1"]

    def _run_mid_year_purchase(self):
        """Bought 2024-07-15 and held at the close: absent from the 2024
        start-of-year snapshot, present in the end-of-year one."""
        return self._run_pipeline(
            tax_year=2025,                                    # Vorabpauschale year 2024
            trades_data=[self._acquisition_row("2024-07-15", "100", "90")],
            positions_prior_start_data=[],                    # not held on 1 January 2024
            positions_prior_end_data=[self._position_row("100", "110", "11000")],
            # Held throughout the tax year itself: bought in 2024, still there.
            positions_start_data=[self._position_row("100", "110", "11000")],
            positions_end_data=[self._position_row("100", "110", "11000")],
        )

    def test_a_non_interactive_run_stops_naming_the_fund(self):
        """Proves the resolver is reached: without the call site the run would
        produce an empty Zeile 13 and no gap at all."""
        self._seed_classification()

        with pytest.raises(DataGapError) as excinfo:
            self._run_mid_year_purchase()

        assert "VORABPAUSCHALE_YEAR_START_PRICE_UNKNOWN" in str(excinfo.value)
        assert self.ISIN in str(excinfo.value)

    def test_a_stored_price_produces_the_abs_2_reduced_figure(self):
        """The whole point, end to end. Bought in July, so six twelfths.

        Basisertrag je Anteil = 100 EUR * 2.29 % * 0.7 = 1.603, under the Satz 3
        cap of (110 - 100) = 10. Times 100 units = 160.30 for a full year;
        § 18 Abs. 2 keeps 6/12 for a July purchase = 80.15.
        """
        self._seed_classification()
        store = FundPriceStore()
        store.put(f"ISIN:{self.ISIN}", 2024,
                  FundPrice(price=Decimal("100"), currency="EUR",
                            date_set=date(2024, 1, 2), source="issuer NAV history"))
        store.save()

        results = self._run_mid_year_purchase()

        assert len(results.vorabpauschale_items) == 1, (
            "a fund bought in July and held at 31 December owes a reduced "
            "Vorabpauschale, not none")
        assert results.vorabpauschale_items[0].gross_vorabpauschale_eur == Decimal("80.15")

    def _run_held_across_new_year(self, **kwargs):
        """Held on 1 January 2024 and at its close: priced by the snapshot, so
        the ordinary pass never touches it and only strict mode can."""
        return self._run_pipeline(
            tax_year=2025,                                    # Vorabpauschale year 2024
            trades_data=[self._acquisition_row("2023-05-10", "100", "80")],
            positions_prior_start_data=[self._position_row("100", "100", "10000")],
            positions_prior_end_data=[self._position_row("100", "110", "11000")],
            positions_start_data=[self._position_row("100", "110", "11000")],
            positions_end_data=[self._position_row("100", "110", "11000")],
            **kwargs)



    def test_the_pipeline_reaches_the_provider_lookup(self, monkeypatch):
        """Proves the fetch is wired, not just the resolver.

        `conftest` disables the lookup and puts a tripwire on it for every test,
        so this one turns it back on and substitutes a stub. Without that the
        whole fetch path could be deleted with the suite green — the blind spot
        CLAUDE.md names for the ends of a new channel.
        """
        self._seed_classification()
        import src.config as app_config
        from src.processing import fund_price_sources
        from src.processing.fund_price_sources import FetchedPrice
        monkeypatch.setattr(app_config, "FUND_PRICE_AUTO_FETCH", True, raising=False)
        seen = []
        monkeypatch.setattr(
            fund_price_sources, "fetch_year_start_price",
            lambda asset, year: seen.append((asset.ibkr_isin, year)) or FetchedPrice(
                price=Decimal("100.4567"), currency="EUR", date_set=date(2024, 1, 2),
                provider="iShares", url="https://example.invalid/nav", fund_name="F"))

        results = self._run_mid_year_purchase()

        assert seen == [(self.ISIN, 2024)], "the provider was not consulted"
        gap = next(g for g in results.data_gaps if g.code == ISSUER_NAV_CODE)
        assert "100.4567" in gap.detail
        assert results.vorabpauschale_items

    def test_the_supplied_price_reaches_the_report(self):
        self._seed_classification()
        store = FundPriceStore()
        store.put(f"ISIN:{self.ISIN}", 2024,
                  FundPrice(price=Decimal("100"), currency="EUR",
                            date_set=date(2024, 1, 2), source="issuer NAV history"))
        store.save()

        results = self._run_mid_year_purchase()

        codes = [g.code for g in results.data_gaps]
        assert ISSUER_NAV_CODE in codes

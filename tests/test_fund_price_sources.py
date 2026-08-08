"""
The issuer NAV lookup that pre-fills the year-start Ruecknahmepreis prompt.

legal_basis: § 18 Abs. 1 Satz 2 InvStG measures the Basisertrag from the
Ruecknahmepreis at the start of the calendar year [GT-INVSTG-010]; Satz 3 fixes
that figure as *"dem ersten ... im Kalenderjahr festgesetzten Ruecknahmepreis"*
and [GT-INVSTG-014] records that the Satz 2 base is the same one; Rz. 18.6
converts it at the ECB rate of the day it was set [GT-INVSTG-018]. Price, day
and currency all therefore have to be right, and a figure that is plausible but
belongs to another fund, another share class or another year is worse than no
figure at all -- which is why most of what follows tests refusals.

**Nothing here touches the network.** Every test drives a fake fetcher holding
the shapes the five providers were observed to serve on 2026-08-08: iShares as
SpreadsheetML (German and US variants, the US one with the invalid XML it really
emits), SSGA as OOXML keyed by a ticker its own product workbook publishes, and
Swiss Fund Data as semicolon CSV. A test that reached the real sites would fail
the day any of them changed, which is the event this module is built to survive.
"""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal
from xml.sax.saxutils import escape

import pytest

from src.domain.assets import InvestmentFund
from src.domain.enums import InvestmentFundType
from src.processing import fund_price_sources as fps
from src.processing.fund_price_sources import (
    FundPriceFetchError,
    ISharesSource,
    SsgaSource,
    SwissFundDataSource,
    _first_price_set_in_year,
    _parse_day_first_date,
    _parse_issuer_date,
    fetch_year_start_price,
)


# --------------------------------------------------------------------------
# Fakes and builders
# --------------------------------------------------------------------------

class FakeFetcher:
    """Serves canned bytes; anything unmapped fails as an unreachable URL would."""

    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        if url not in self.responses:
            raise FundPriceFetchError(f"no canned response for {url}")
        body = self.responses[url]
        if isinstance(body, Exception):
            raise body
        return body if isinstance(body, bytes) else body.encode("utf-8")


def ssml(sheets):
    """SpreadsheetML, the format the iShares fund workbook really is."""
    out = ['<?xml version="1.0"?>'
           '<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">']
    for name, rows in sheets.items():
        out.append(f'<ss:Worksheet ss:Name="{name}"><ss:Table>')
        for row in rows:
            out.append("<ss:Row>" + "".join(
                f"<ss:Cell><ss:Data>{escape(str(v))}</ss:Data></ss:Cell>" for v in row)
                + "</ss:Row>")
        out.append("</ss:Table></ss:Worksheet>")
    out.append("</ss:Workbook>")
    return "".join(out)


def xlsx(rows):
    """OOXML with only the one part the parser reads, cells at declared columns."""
    sheet = ['<worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main"><sheetData>']
    for r, row in enumerate(rows, start=1):
        cells = "".join(
            f'<c r="{chr(ord("A") + i)}{r}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
            for i, v in enumerate(row) if v != "")
        sheet.append(f'<row r="{r}">{cells}</row>')
    sheet.append("</sheetData></worksheet>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", "".join(sheet))
    return buf.getvalue()


# ---- iShares fixtures -----------------------------------------------------

EMEA_ISIN, EMEA_PID = "IE000RHYOR04", "327355"
US_ISIN, US_PID = "US46434G8556", "239654"

EMEA_SEARCH = fps._ISHARES_EMEA_SEARCH.format(isin=EMEA_ISIN)
US_SEARCH = fps._ISHARES_EMEA_SEARCH.format(isin=US_ISIN)
EMEA_HEADER = fps._ISHARES_HEADER.format(pid=EMEA_PID, site="emea-ishares-v2", locale="de_DE")
EMEA_DOC = fps._ISHARES_DOCUMENT.format(pid=EMEA_PID, site="emea-ishares-v2", locale="de_DE")
US_HEADER = fps._ISHARES_HEADER.format(pid=US_PID, site="us-ishares", locale="en_US")
US_DOC = fps._ISHARES_DOCUMENT.format(pid=US_PID, site="us-ishares", locale="en_US")

DE_HISTORY = ssml({"Positionen": [["Ticker", "Name"]], "Historisch": [
    ["per", "Währung", "NAV", "Umlaufende Anteile"],
    ["05.Jan.2023", "EUR", "4.99999", "900000"],
    ["03.Jan.2023", "EUR", "4.99468", "900000"],     # first of 2023
    ["30.Dez.2022", "EUR", "4.98000", "900000"],     # nearer, wrong year
]})
US_HISTORY = ssml({"Historical": [
    ["As Of", "NAV per Share", "Ex-Dividends"],
    ["Jan 03, 2025", "28.970147", "0.00"],
    ["Jan 02, 2025", "29.13401", "0.00"],            # first of 2025
    ["Dec 31, 2024", "27.978144", "0.00"],
]})


def ishares_search(n=1, pid=EMEA_PID):
    return json.dumps({"totalResults": n,
                       "results": [{"fundName": "A Fund", "portfolioId": pid}
                                   for _ in range(n)]})


def ishares_header(ccy="EUR", name="A Fund"):
    return json.dumps({"currencyCode": ccy, "fundName": name})


def us_screener(isin=US_ISIN, pid=US_PID):
    return json.dumps({"data": {"tableData": {
        "columns": [{"name": "isin"}, {"name": "portfolioId"}],
        "data": [[isin, int(pid)]]}}})


def emea_fetcher(**over):
    r = {EMEA_SEARCH: ishares_search(), EMEA_HEADER: ishares_header(), EMEA_DOC: DE_HISTORY}
    r.update(over)
    return FakeFetcher(r)


def us_fetcher(**over):
    r = {US_SEARCH: ishares_search(n=0), fps._ISHARES_US_SCREENER: us_screener(),
         US_HEADER: ishares_header(ccy="USD", name="iShares MSCI Global Gold Miners ETF"),
         US_DOC: US_HISTORY}
    r.update(over)
    return FakeFetcher(r)


# ---- SSGA fixtures --------------------------------------------------------

SSGA_EMEA_ISIN, SSGA_US_ISIN = "IE00B9CQXS71", "US78463V1070"
SSGA_EMEA_NAVHIST = fps._SSGA_NAVHIST_EMEA.format(slug="zprg-gy")
SSGA_US_NAVHIST = fps._SSGA_NAVHIST_US.format(slug="gld")
SSGA_US_PAGE = "https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld"

SSGA_PRODUCTS_EMEA = xlsx([
    ["disclaimer row"],
    ["NAV as of Date", "Fund Name", "ISIN", "Deutsche Börse"],
    ["Aug 06 2026", "SPDR S&P Global Dividend Aristocrats", SSGA_EMEA_ISIN, "ZPRG GY"],
])
SSGA_PRODUCTS_US = xlsx([
    ["disclaimer row"],
    ["As of** ", "Ticker", "Name", "ISIN"],
    ["Aug 06 2026", "GLD®", "SPDR® Gold Shares", SSGA_US_ISIN],
])
SSGA_FUNDFINDER = json.dumps({"data": {"funds": {"etfs": {"datas": [
    {"fundTicker": "GLD®", "fundUri": "/us/en/intermediary/etfs/spdr-gold-shares-gld"}]}}}})


def ssga_navhist_emea(isin=SSGA_EMEA_ISIN, ccy="USD"):
    return xlsx([
        ["Fund Name:", "SPDR S&P Global Dividend Aristocrats"],
        ["ISIN:", isin],
        ["NAV Currency:", ccy],
        [],
        ["Date", "NAV", "Shares Outstanding"],
        ["05-Jan-2023", "31.1022", "1"],
        ["03-Jan-2023", "31.1026", "1"],             # first of 2023
        ["30-Dec-2022", "30.9641", "1"],
    ])


def ssga_navhist_us(carried_forward=True):
    rows = [
        ["Fund Name:", "SPDR® Gold Shares"],
        ["Ticker Symbol:", "GLD®"],
        ["Date", "NAV", "Shares Outstanding"],
        ["03-Jan-2025", "244.309162", "1"],
        ["02-Jan-2025", "244.265671", "1"],          # the price actually set
    ]
    if carried_forward:
        rows.append(["01-Jan-2025", "240.997613", "1"])   # republished close
    rows.append(["31-Dec-2024", "240.997613", "1"])
    return xlsx(rows)


def ssga_fetcher(**over):
    r = {fps._SSGA_PRODUCTS_EMEA: SSGA_PRODUCTS_EMEA,
         fps._SSGA_PRODUCTS_US: SSGA_PRODUCTS_US,
         fps._SSGA_FUNDFINDER_US: SSGA_FUNDFINDER,
         SSGA_EMEA_NAVHIST: ssga_navhist_emea(),
         SSGA_US_NAVHIST: ssga_navhist_us(),
         SSGA_US_PAGE: '<tr><th class="label">Base Currency</th><td class="data">USD</td></tr>'}
    r.update(over)
    return FakeFetcher(r)


# ---- Swiss Fund Data fixtures ---------------------------------------------

SFD_ISIN, SFD_ID = "IE00BKWQ0F09", "47932"
SFD_SEARCH = fps._SFD_SEARCH.format(isin=SFD_ISIN)
SFD_DOWNLOAD = fps._SFD_DOWNLOAD.format(fid=SFD_ID)


def sfd_csv(isin=SFD_ISIN, ccy="EUR"):
    return "\n".join([
        "sep=;",
        f"State Street SPDR MSCI Europe Energy - {isin} ({ccy})",
        "Date;CCY Chart Price;Chart Price;Net Asset Value;Issue Price;Redemption Price",
        f"2023-01-05;{ccy};178.246;178.246;;",
        f"2023-01-03;{ccy};182.997;182.997;;",       # first of 2023
        f"2022-12-30;{ccy};179.849;179.849;;",
    ])


def sfd_fetcher(**over):
    r = {SFD_SEARCH: f'<a href="/sfdpub/en/funds/show/{SFD_ID}">fund</a>',
         SFD_DOWNLOAD: sfd_csv()}
    r.update(over)
    return FakeFetcher(r)


def _fund(isin, symbol="XXX", description="A Fund"):
    return InvestmentFund(fund_type=InvestmentFundType.AKTIENFONDS,
                          description=description, currency="EUR",
                          ibkr_isin=isin, ibkr_symbol=symbol)


# --------------------------------------------------------------------------


class TestDateParsing:
    @pytest.mark.parametrize("text, expected", [
        ("03.Jan.2023", date(2023, 1, 3)),
        ("31.Juli2026", date(2026, 7, 31)),          # no separator before the year
        ("29.Sept.2009", date(2009, 9, 29)),         # four-letter abbreviation
        ("01.März2023", date(2023, 3, 1)),           # umlaut, no trailing dot
        ("03-Jan-2023", date(2023, 1, 3)),           # SSGA
        ("Jan 02, 2025", date(2025, 1, 2)),          # iShares US
        ("2023-01-03", date(2023, 1, 3)),            # Swiss Fund Data
    ])
    def test_every_form_the_five_providers_emit(self, text, expected):
        assert _parse_issuer_date(text) == expected

    @pytest.mark.parametrize("text", ["", "not a date", "31.Feb.2023"])
    def test_anything_else_is_refused_rather_than_guessed(self, text):
        assert _parse_issuer_date(text) is None

    def test_vanecks_slashed_form_is_read_day_first_and_only_on_request(self):
        """`07/08/2026` is 7 August. `dd/mm` and `mm/dd` are indistinguishable in
        any single row, so the day-first reader is a separate function no other
        provider is parsed with -- reading one as the other moves a price by
        months without any row looking wrong."""
        assert _parse_day_first_date("07/08/2026") == date(2026, 8, 7)
        assert _parse_day_first_date("31/07/2026") == date(2026, 7, 31)
        assert _parse_issuer_date("07/08/2026") is None


class TestTheXmlRepair:
    """It has to fix the invalid document without corrupting the valid one."""

    def _one_cell(self, inner):
        return fps._parse_spreadsheetml(
            ('<?xml version="1.0"?>'
             '<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
             '<ss:Worksheet ss:Name="S"><ss:Table><ss:Row><ss:Cell>'
             f"<ss:Data>{inner}</ss:Data>"
             "</ss:Cell></ss:Row></ss:Table></ss:Worksheet></ss:Workbook>").encode())["S"][0][0]

    def test_an_already_encoded_entity_is_not_double_escaped(self):
        """A fund name written correctly as `S&amp;P` must read back as `S&P`,
        not as `S&amp;P` -- the repair targets bare ampersands only."""
        assert self._one_cell("S&amp;P 500") == "S&P 500"

    def test_a_bare_ampersand_is_repaired(self):
        assert self._one_cell("Smith & Co") == "Smith & Co"

    @pytest.mark.parametrize("entity", ["&lt;", "&gt;", "&quot;", "&#39;", "&#x41;"])
    def test_the_other_entity_forms_survive(self, entity):
        assert "&amp;" not in self._one_cell(f"a{entity}b")


class TestFirstPriceSetInYear:
    """Satz 3's *"ersten im Kalenderjahr festgesetzten"* price [GT-INVSTG-014]."""

    def test_it_takes_the_first_row_of_the_year(self):
        series = [(date(2022, 12, 30), Decimal("9")), (date(2023, 1, 3), Decimal("10")),
                  (date(2023, 1, 4), Decimal("11"))]
        assert _first_price_set_in_year(series, 2023) == (date(2023, 1, 3), Decimal("10"), False)

    def test_a_republished_close_is_not_a_price_set_in_the_year(self):
        """SSGA US and VanEck both carry a 1 January row equal to 31 December's.
        Taking it would rest the Basisertrag on a price set in the previous
        year -- measured 1.1% high on one fund and 1.4% low on another."""
        series = [(date(2024, 12, 31), Decimal("240.997613")),
                  (date(2025, 1, 1), Decimal("240.997613")),   # carried forward
                  (date(2025, 1, 2), Decimal("244.265671"))]
        assert _first_price_set_in_year(series, 2025) == (
            date(2025, 1, 2), Decimal("244.265671"), True)

    def test_two_consecutive_republished_rows_are_both_skipped(self):
        """Where 1 and 2 January are both closed the file carries two republished
        rows. Stopping after one returns the second -- the previous year's price,
        which is the whole thing this rejects. Found by mutation: skipping only
        the first row passed every test written before this one."""
        series = [(date(2024, 12, 31), Decimal("9")),
                  (date(2025, 1, 1), Decimal("9")),
                  (date(2025, 1, 2), Decimal("9")),
                  (date(2025, 1, 3), Decimal("11"))]
        assert _first_price_set_in_year(series, 2025) == (date(2025, 1, 3), Decimal("11"), True)

    def test_a_flat_day_after_a_real_price_is_not_dropped(self):
        """Only the leading run is republished; a genuine flat day later in the
        year is a price and must stand."""
        series = [(date(2022, 12, 30), Decimal("9")),
                  (date(2023, 1, 3), Decimal("10")), (date(2023, 1, 4), Decimal("10"))]
        assert _first_price_set_in_year(series, 2023) == (date(2023, 1, 3), Decimal("10"), False)

    def test_a_fund_launched_mid_year_keeps_its_first_published_price(self):
        """Rz. 18.7 [GT-INVSTG-035]: with no price set before the year there is
        nothing to compare against, so nothing may be skipped."""
        series = [(date(2023, 4, 18), Decimal("20")), (date(2023, 4, 19), Decimal("21"))]
        assert _first_price_set_in_year(series, 2023) == (date(2023, 4, 18), Decimal("20"), False)

    def test_a_year_the_fund_never_priced_yields_nothing(self):
        """Not the nearest date: another year's figure is computed against
        another Basiszins [GT-INVSTG-014]."""
        series = [(date(2022, 12, 30), Decimal("9")), (date(2024, 1, 2), Decimal("11"))]
        assert _first_price_set_in_year(series, 2023) is None

    def test_a_year_holding_only_a_republished_row_yields_nothing(self):
        series = [(date(2022, 12, 30), Decimal("9")), (date(2023, 1, 1), Decimal("9"))]
        assert _first_price_set_in_year(series, 2023) is None


class TestIShares:
    def test_the_emea_route_reads_price_date_and_currency(self):
        got = ISharesSource(emea_fetcher()).fetch(EMEA_ISIN, "ERNX", 2023)
        assert (got.price, got.currency, got.date_set) == (
            Decimal("4.99468"), "EUR", date(2023, 1, 3))

    def test_the_us_route_is_reached_when_the_emea_search_is_empty(self):
        """A US ISIN returns zero hits from the EMEA search, so the screener --
        532 funds, each carrying its ISIN -- supplies the portfolio id."""
        got = ISharesSource(us_fetcher()).fetch(US_ISIN, "RING", 2025)
        assert (got.price, got.currency, got.date_set) == (
            Decimal("29.13401"), "USD", date(2025, 1, 2))

    def test_invalid_xml_from_the_us_estate_is_repaired_not_refused(self):
        """The US workbook carries a raw `&` in a hyperlink attribute, which
        stops a conformant parser on line 47 of 67,000. It sits in a banner
        above the tables, so the repair has to happen before any parsing."""
        broken = US_HISTORY.replace(
            '<ss:Worksheet ss:Name="Historical">',
            '<ss:Worksheet ss:Name="Banner"><ss:Table><ss:Row>'
            '<ss:Cell ss:HRef="https://www.ishares.com/us/products/etf-investments'
            '#!type=ishares&style=All&view=quarterlyPerfNav"><ss:Data>x</ss:Data>'
            '</ss:Cell></ss:Row></ss:Table></ss:Worksheet>'
            '<ss:Worksheet ss:Name="Historical">', 1)
        with pytest.raises(Exception):
            __import__("xml.etree.ElementTree", fromlist=["x"]).fromstring(broken)

        got = ISharesSource(us_fetcher(**{US_DOC: broken})).fetch(US_ISIN, "RING", 2025)
        assert got.price == Decimal("29.13401")

    def test_an_ambiguous_search_is_not_resolved_by_picking_one(self):
        """Two hits means the ISIN did not identify a single share class, and
        the distributing twin's price is the wrong price."""
        with pytest.raises(FundPriceFetchError, match="2 funds"):
            ISharesSource(emea_fetcher(**{EMEA_SEARCH: ishares_search(n=2)})).fetch(
                EMEA_ISIN, "X", 2023)

    def test_a_fund_with_no_stated_currency_is_refused(self):
        """Rz. 18.6 converts at the Stichtag rate [GT-INVSTG-018]; defaulting the
        currency would value a dollar fund at par."""
        with pytest.raises(FundPriceFetchError, match="no currency"):
            ISharesSource(emea_fetcher(**{EMEA_HEADER: ishares_header(ccy="")})).fetch(
                EMEA_ISIN, "X", 2023)

    def test_an_isin_neither_estate_publishes_is_refused(self):
        f = FakeFetcher({fps._ISHARES_EMEA_SEARCH.format(isin="IE00NOTOURS1"):
                         ishares_search(n=0),
                         fps._ISHARES_US_SCREENER: us_screener()})
        with pytest.raises(FundPriceFetchError, match="no fund with ISIN"):
            ISharesSource(f).fetch("IE00NOTOURS1", "X", 2023)

    def test_a_year_with_no_price_is_refused(self):
        with pytest.raises(FundPriceFetchError, match="no 2021 NAV"):
            ISharesSource(emea_fetcher()).fetch(EMEA_ISIN, "ERNX", 2021)


class TestSsga:
    def test_the_slug_comes_from_the_published_xetra_ticker(self):
        """The whole point of the map. IBKR reports `GLDV`, the SIX listing;
        SSGA names the file for the Xetra ticker `ZPRG`. Deriving the slug from
        the broker symbol asked for `gldv-gy` and got a 404 while the fund's
        file sat at `zprg-gy`."""
        f = ssga_fetcher()
        got = SsgaSource(f).fetch(SSGA_EMEA_ISIN, "GLDV", 2023)
        assert got.price == Decimal("31.1026") and got.currency == "USD"
        assert SSGA_EMEA_NAVHIST in f.requested
        assert not any("gldv-gy" in u for u in f.requested)

    def test_an_emea_file_naming_another_fund_is_refused(self):
        """The ISIN in the document is what makes the map safe to trust."""
        with pytest.raises(FundPriceFetchError, match="not IE00B9CQXS71"):
            SsgaSource(ssga_fetcher(
                **{SSGA_EMEA_NAVHIST: ssga_navhist_emea(isin="IE00SOMEONEELSE")})).fetch(
                SSGA_EMEA_ISIN, "GLDV", 2023)

    def test_the_us_route_takes_its_currency_from_the_fund_page(self):
        """The US history file states no currency and the `$` its product
        workbook prints is ambiguous across USD, CAD, AUD, HKD and SGD."""
        got = SsgaSource(ssga_fetcher()).fetch(SSGA_US_ISIN, "GLD", 2025)
        assert (got.price, got.currency, got.date_set) == (
            Decimal("244.265671"), "USD", date(2025, 1, 2))
        assert got.skipped_carried_forward is True

    def test_a_us_page_without_a_base_currency_is_refused(self):
        with pytest.raises(FundPriceFetchError, match="no base currency"):
            SsgaSource(ssga_fetcher(**{SSGA_US_PAGE: "<html>no such field</html>"})).fetch(
                SSGA_US_ISIN, "GLD", 2025)

    def test_an_isin_in_neither_product_workbook_is_refused(self):
        with pytest.raises(FundPriceFetchError, match="no fund with ISIN"):
            SsgaSource(ssga_fetcher()).fetch("IE00NOTSPDR1", "ZZZZ", 2023)


VANECK_ISIN, VANECK_SLUG = "IE00BDFBTQ78", "mining-etf"
VANECK_SEARCH = fps._VANECK_SEARCH.format(isin=VANECK_ISIN)
VANECK_PAGE = fps._VANECK_PERFORMANCE.format(slug=VANECK_SLUG)
VANECK_BLOCK = fps._VANECK_BLOCK.format(block="193521", page="233154", ticker="UCTGDIG")
VANECK_DL_PATH = "/de/en/investments/mining-etf/downloads/fundhistoprices/"
VANECK_DL = fps._VANECK + VANECK_DL_PATH


def vaneck_page(isin=VANECK_ISIN):
    return (f"<html><body><span>ISIN {isin}</span>"
            '<ve-fundticker class="d-none">UCTGDIG</ve-fundticker>'
            '<ve-histopricesblock class="" id="" data-section="" data-blockid="193521"'
            ' data-pageid="233154" data-template=""></ve-histopricesblock></body></html>')


def vaneck_block(ccy="USD", download=VANECK_DL_PATH):
    return json.dumps({"data": {"Ticker": "UCTGDIG", "Title": "NAVs",
                                "CurrencyName": ccy, "CurrencySymbol": "$",
                                "DownloadUrl": download}})


VANECK_HISTORY = xlsx([
    ["VanEck S&P Global Mining UCITS ETF - GDIG"],
    ["Date", "NAV", "Change", "% Change"],
    ["03/01/2024", "31.387", "-0.73", "-2.28"],
    ["02/01/2024", "32.117", "-0.35", "-1.09"],      # the price actually set
    ["01/01/2024", "32.470", "0.00", "0.00"],        # republished close
    ["29/12/2023", "32.470", "-0.21", "-0.64"],
])


def vaneck_fetcher(**over):
    r = {VANECK_SEARCH: f'<a href="/de/en/investments/{VANECK_SLUG}/">Mining ETF</a>',
         VANECK_PAGE: vaneck_page(), VANECK_BLOCK: vaneck_block(),
         VANECK_DL: VANECK_HISTORY}
    r.update(over)
    return FakeFetcher(r)


class TestVanEck:
    def test_the_page_is_found_by_searching_for_the_isin(self):
        """VanEck publishes no product list, so the site search is the only
        route from an ISIN to a fund page."""
        got = fps.VanEckSource(vaneck_fetcher()).fetch(VANECK_ISIN, "GDIG", 2024)
        assert (got.price, got.currency, got.date_set) == (
            Decimal("32.117"), "USD", date(2024, 1, 2))
        assert got.skipped_carried_forward is True

    def test_the_dates_are_read_day_first(self):
        """`03/01/2024` is 3 January. Read month-first it would be 1 March and
        the year's opening price would be silently two months late."""
        got = fps.VanEckSource(vaneck_fetcher()).fetch(VANECK_ISIN, "GDIG", 2024)
        assert got.date_set == date(2024, 1, 2)

    def test_an_ambiguous_search_is_refused(self):
        with pytest.raises(FundPriceFetchError, match="2 funds"):
            fps.VanEckSource(vaneck_fetcher(**{
                VANECK_SEARCH: '<a href="/de/en/investments/mining-etf/">a</a>'
                               '<a href="/de/en/investments/gold-etf/">b</a>'})).fetch(
                VANECK_ISIN, "GDIG", 2024)

    def test_a_page_that_does_not_name_the_isin_is_refused(self):
        with pytest.raises(FundPriceFetchError, match="does not name"):
            fps.VanEckSource(vaneck_fetcher(
                **{VANECK_PAGE: vaneck_page(isin="IE00SOMEONEELSE")})).fetch(
                VANECK_ISIN, "GDIG", 2024)

    def test_a_missing_currency_is_refused_rather_than_read_off_the_glyph(self):
        """Neither the workbook nor the page states an ISO code -- the page
        prints `$65.33` and the workbook has no currency column at all. The
        block API is the only machine-readable statement of it, and `$` is
        ambiguous across USD, CAD, AUD, HKD and SGD."""
        with pytest.raises(FundPriceFetchError, match="no currency"):
            fps.VanEckSource(vaneck_fetcher(**{VANECK_BLOCK: vaneck_block(ccy="")})).fetch(
                VANECK_ISIN, "GDIG", 2024)

    def test_a_missing_download_url_is_refused_rather_than_guessed(self):
        """The download path comes from the API, not from a convention this
        module invents."""
        with pytest.raises(FundPriceFetchError, match="no price history"):
            fps.VanEckSource(vaneck_fetcher(
                **{VANECK_BLOCK: vaneck_block(download="")})).fetch(
                VANECK_ISIN, "GDIG", 2024)


class TestSwissFundData:
    def test_it_reads_price_date_and_currency(self):
        got = SwissFundDataSource(sfd_fetcher()).fetch(SFD_ISIN, "STN", 2023)
        assert (got.price, got.currency, got.date_set) == (
            Decimal("182.997"), "EUR", date(2023, 1, 3))

    def test_a_file_headed_with_another_isin_is_refused(self):
        with pytest.raises(FundPriceFetchError, match="does not name"):
            SwissFundDataSource(sfd_fetcher(
                **{SFD_DOWNLOAD: sfd_csv(isin="IE00SOMEONEELSE")})).fetch(
                SFD_ISIN, "STN", 2023)

    def test_an_ambiguous_search_is_refused(self):
        with pytest.raises(FundPriceFetchError, match="2 funds"):
            SwissFundDataSource(sfd_fetcher(**{
                SFD_SEARCH: '<a href="/sfdpub/en/funds/show/1">a</a>'
                            '<a href="/sfdpub/en/funds/show/2">b</a>'})).fetch(
                SFD_ISIN, "STN", 2023)


class TestOrderingAndFailure:
    def test_an_issuer_is_preferred_over_the_aggregator(self):
        """Swiss Fund Data rounds to three decimals where the issuers publish
        four to six, and Rz. 18.4 wants four or more [GT-INVSTG-017]."""
        responses = dict(ssga_fetcher().responses)
        responses[fps._SFD_SEARCH.format(isin=SSGA_EMEA_ISIN)] = (
            f'<a href="/sfdpub/en/funds/show/5380">x</a>')
        responses[fps._SFD_DOWNLOAD.format(fid="5380")] = sfd_csv(isin=SSGA_EMEA_ISIN)
        got = fetch_year_start_price(_fund(SSGA_EMEA_ISIN, "GLDV"), 2023,
                                     fetcher=FakeFetcher(responses))
        assert got.provider == "SPDR" and got.price == Decimal("31.1026")

    def test_the_aggregator_catches_a_fund_no_issuer_reader_has(self):
        got = fetch_year_start_price(_fund(SFD_ISIN, "STN"), 2023, fetcher=sfd_fetcher())
        assert got.provider == "Swiss Fund Data"

    def test_an_unreachable_provider_returns_none_rather_than_raising(self):
        """An exception here would turn an issuer's outage into a failed tax
        run, which is a worse trade than one manual lookup."""
        assert fetch_year_start_price(_fund("IE00B4L5Y983"), 2023,
                                      fetcher=FakeFetcher()) is None

    def test_a_rebuilt_site_serving_html_returns_none(self):
        assert fetch_year_start_price(
            _fund(EMEA_ISIN), 2023,
            fetcher=emea_fetcher(**{EMEA_DOC: "<!doctype html><html>new site</html>"})
        ) is None

    def test_a_fund_without_an_isin_is_never_matched_on_its_name(self):
        f = FakeFetcher()
        assert fetch_year_start_price(
            _fund("", description="iShares Core MSCI World"), 2023, fetcher=f) is None
        assert f.requested == [], "no ISIN means nothing should be fetched"


class TestProvenance:
    def test_the_source_string_names_the_file_the_day_and_the_retrieval(self):
        """A figure on a tax return has to be traceable to something outside
        this program, and to the day it was read -- these files are overwritten
        and cannot be re-read as they stood."""
        got = ISharesSource(emea_fetcher()).fetch(EMEA_ISIN, "ERNX", 2023)
        source = got.as_source(date(2026, 8, 8))
        assert "iShares" in source and "2023-01-03" in source
        assert "abgerufen 2026-08-08" in source and EMEA_DOC in source

    def test_a_skipped_republished_row_is_stated_in_the_provenance(self):
        """The taxpayer confirms the figure, so the one judgement the fetch made
        on their behalf has to be visible."""
        got = SsgaSource(ssga_fetcher()).fetch(SSGA_US_ISIN, "GLD", 2025)
        assert "fortgeschriebene" in got.as_source(date(2026, 8, 8))

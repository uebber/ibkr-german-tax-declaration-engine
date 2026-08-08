# src/processing/fund_price_sources.py
"""
Issuer NAV history, fetched by ISIN, to propose a year-start price.

`src/processing/fund_prices.py` asks the taxpayer for the Ruecknahmepreis of a
fund bought mid-year, because no broker export carries it. This module looks the
same figure up at the issuer so the question arrives with an answer already in
it. **The taxpayer still confirms it.** A fetched figure is a default on a
prompt, never a value the engine adopts on its own.

That boundary is the whole design, and it is why this file changes no legal
position. § 18 Abs. 1 Satz 2 InvStG measures the Basisertrag from the
*Ruecknahmepreis* and Satz 4 lets a Boersen- oder Marktpreis stand in **only
where no Ruecknahmepreis was set** ([GT-INVSTG-010]). What these providers
publish is a *NAV*, and nothing in `reference/` settles whether an ETF's
published NAV is its Ruecknahmepreis. So the engine does not assert it: it shows
the figure, names the file it came from, and a person decides.

## The four steps, and where providers differ

Every provider reduces to the same shape, measured 2026-08-08:

    ISIN --(1)--> document key --(2)--> history document --(3)--> (date, price)
                                                         --(4)--> first price SET in the year

**(1) Identity.** Two classes, and the distinction decides whether a provider
generalises. *ISIN-queryable* providers answer a lookup directly: iShares EMEA
has a product search, Swiss Fund Data has one, and iShares US publishes a
screener carrying every ISIN. *Map-backed* providers key their files on a
ticker, and the map has to be downloaded: SSGA publishes one product workbook
per region.

**Never derive the key from the IBKR symbol.** IBKR reports the ticker of the
venue the trade happened on; SSGA keys EMEA files on the *Xetra* ticker. SPDR
Global Dividend Aristocrats is `GLDV` on SIX and `ZPRG` on Xetra, so a symbol
guess asks for `gldv-gy` and gets a 404 while the fund's file sits at `zprg-gy`.
That was measured, not imagined: it is the defect this module was rewritten to
remove, and it would recur for any holder of any SPDR bought outside Xetra.

**(3) Verification.** A document proves which fund it belongs to with varying
strength -- an ISIN inside it (SSGA EMEA, Swiss Fund Data), an ISIN on the page
it came from (iShares), or only a name and ticker (SSGA US). A *guessed* key is
therefore only ever acceptable where the document states an ISIN. Everywhere
else the key comes from a published map, and the name is checked instead.

**(4) A carried-forward row is not a price.** Some files republish the previous
close on days no price was set. SSGA US and VanEck both carry a 1 January row
identical to 31 December; iShares, SSGA EMEA and Swiss Fund Data omit
non-trading days entirely. Taking the first row of the calendar year would then
take a price *festgesetzt* in the previous year -- measured at 1.1% high for one
fund and 1.4% low for another, so not even a consistent direction. Satz 3
defines the figure as *"dem ersten ... im Kalenderjahr festgesetzten
Ruecknahmepreis"* and [GT-INVSTG-014] records that the Satz 2 base is the same
figure, so a republished value does not qualify. `_first_price_set_in_year`
skips it.

## How this fails

Every failure path returns `None` and none of them raises. The prompt then asks
exactly as it did before, and the FAIL_FAST in `fund_prices.py` still stops any
run that ends without a price. A provider rebuilding its site costs the taxpayer
a lookup; it cannot produce a wrong figure.
"""
import csv
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from src.domain.assets import Asset

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 45
_USER_AGENT = (
    "Mozilla/5.0 (compatible; ibkr-german-tax-declaration-engine/1.0; "
    "+https://github.com/) Python-requests"
)


class FundPriceFetchError(Exception):
    """A price could not be obtained. Never escapes `fetch_year_start_price`."""


@dataclass(frozen=True)
class FetchedPrice:
    """One published NAV, with everything needed to check it by hand."""
    price: Decimal
    currency: str
    date_set: date
    provider: str
    url: str
    fund_name: str
    skipped_carried_forward: bool = False

    def as_source(self, retrieved_on: date) -> str:
        note = (" (der 1.-Januar-Wert war der fortgeschriebene Vorjahreskurs "
                "und wurde uebergangen)" if self.skipped_carried_forward else "")
        return (f"{self.provider} NAV-Historie ({self.fund_name}), "
                f"Kurs vom {self.date_set.isoformat()}, "
                f"abgerufen {retrieved_on.isoformat()}: {self.url}{note}")


class HttpFetcher(Protocol):
    """The one seam every network call goes through, so tests need no network."""

    def get(self, url: str) -> bytes:
        ...


# Consent cookies some providers require before they serve content, set on the
# session up front so they are declared in one visible place rather than buried
# in whichever source happens to need them.
#
# `sfdpub-disclaimer` records which audience the visitor belongs to. It is set
# to `private` and not to `qualified`: the qualified-investor route is an
# attestation about the reader, and a German private taxpayer is not a Swiss
# qualified investor. Without it Swiss Fund Data serves the disclaimer page in
# place of every result.
#
# VanEck bounces a client with no consent cookie between `/row/disabled-cookies/`
# and `/corp/en/disabled-cookies` until it gives up, so every page 302s forever.
_CONSENT_COOKIES = {
    "www.swissfunddata.ch": {"sfdpub-disclaimer": "private"},
    "www.vaneck.com": {"cookie_consent": "true"},
}


class RequestsHttpFetcher:
    """The production fetcher.

    Uses one `Session` for the whole run: several providers gate their content
    behind a cookie set during a redirect, and a cookie-less client is bounced
    between two redirect targets until it gives up rather than being served.
    """

    def __init__(self):
        self._session = None

    def get(self, url: str) -> bytes:
        import requests
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({"User-Agent": _USER_AGENT})
            for domain, cookies in _CONSENT_COOKIES.items():
                for name, value in cookies.items():
                    self._session.cookies.set(name, value, domain=domain)
        try:
            response = self._session.get(url, timeout=_TIMEOUT_SECONDS)
        except Exception as e:
            raise FundPriceFetchError(f"{url} could not be reached: {e}") from e
        if response.status_code != 200:
            raise FundPriceFetchError(f"{url} returned HTTP {response.status_code}")
        return response.content


# --------------------------------------------------------------------------
# Dates, prices, series
# --------------------------------------------------------------------------

_GERMAN_MONTHS = {
    "jan": 1, "feb": 2, "mrz": 3, "marz": 3, "maerz": 3, "apr": 4, "mai": 5,
    "jun": 6, "juni": 6, "jul": 7, "juli": 7, "aug": 8, "sep": 9, "sept": 9,
    "okt": 10, "nov": 11, "dez": 12,
}
_ENGLISH_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# `03.Jan.2023`, `31.Juli2026`, `03-Jan-2023`
_DAY_MONTH_YEAR = re.compile(r"^\s*(\d{1,2})[.\-\s]*([^\W\d_]+)\.?[.\-\s]*(\d{4})\s*$")
# `Aug 07, 2026` -- iShares US
_MONTH_DAY_YEAR = re.compile(r"^\s*([^\W\d_]+)\s+(\d{1,2}),\s*(\d{4})\s*$")
# `2023-01-03` -- Swiss Fund Data
_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
# `07/08/2026` -- VanEck, day first (see `_parse_day_first_date`)
_SLASHED = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


def _month_number(name: str) -> Optional[int]:
    key = (name.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u"))
    return _GERMAN_MONTHS.get(key) or _ENGLISH_MONTHS.get(key[:3])


def _build(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_issuer_date(text: str) -> Optional[date]:
    """Every dated form the providers emit, except VanEck's ambiguous one.

    Deliberately not `strptime("%b")`: that reads the process locale, so the
    same file would parse on one machine and not on another.
    """
    text = text or ""
    m = _ISO.match(text)
    if m:
        return _build(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DAY_MONTH_YEAR.match(text)
    if m:
        month = _month_number(m.group(2))
        return _build(int(m.group(3)), month, int(m.group(1))) if month else None
    m = _MONTH_DAY_YEAR.match(text)
    if m:
        month = _month_number(m.group(1))
        return _build(int(m.group(3)), month, int(m.group(2))) if month else None
    return None


def _parse_day_first_date(text: str) -> Optional[date]:
    """`07/08/2026` as 7 August, the reading VanEck's own files force.

    Kept separate from `_parse_issuer_date` because `dd/mm` and `mm/dd` are
    indistinguishable in any single row, and reading one as the other silently
    moves a price by months. Two things fix the reading for VanEck and neither
    is an assumption: rows such as `31/07/2026` cannot be a month, and the file
    the server names `GDIG_asof_07_08_26.xlsx` has `07/08/2026` as its newest
    row on 8 August. `_SsgaSource` and the others never use this parser.
    """
    m = _SLASHED.match(text or "")
    if not m:
        return None
    return _build(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def _parse_price(text: str) -> Optional[Decimal]:
    """A positive Decimal built from the file's own text, or None."""
    try:
        value = Decimal((text or "").strip())
    except (InvalidOperation, ValueError):
        return None
    return value if value > 0 else None


def _first_price_set_in_year(
    series: Iterable[Tuple[date, Decimal]], year: int,
) -> Optional[Tuple[date, Decimal, bool]]:
    """The first day of `year` on which the provider published a new official value.

    That is the rule, and it is not the same as the first row dated in the year:
    a value republished unchanged over a closed day is not a new publication.

    Returns `(day, price, skipped_a_carried_forward_row)`, or None where the
    fund published nothing new in the year at all -- never a price from a
    neighbouring year, which is a different year's figure against a different
    Basiszins ([GT-INVSTG-014]).

    A leading row is treated as carried forward while its price still equals the
    last price set *before* the year. That is what SSGA US and VanEck do on
    1 January, and it needs no trading calendar for any market.

    **The skip repeats.** Where 1 and 2 January are both closed the file carries
    two republished rows, and stopping after one would return the second -- the
    previous year's price, which is exactly what this function exists to reject.
    Found by mutation: a version that skipped only the first row passed every
    test written for it, because no fixture had two.

    Where the fund set no price before the year at all -- Rz. 18.7's fund
    launched mid-year [GT-INVSTG-035] -- there is nothing to compare against and
    nothing is skipped, so its first published price stands.

    **The residual risk is a real price that happens to equal the previous
    close**, which would move the base to the next day. It is left rather than
    guarded because the prompt shows the date it chose and a person confirms it.
    """
    ordered = sorted(series)
    previous: Optional[Decimal] = None
    skipped = False
    for day, price in ordered:
        if day.year == year:
            if previous is not None and price == previous:
                skipped = True          # republished close; keep looking
                continue
            return day, price, skipped
        previous = price
    return None


# --------------------------------------------------------------------------
# Workbook readers
# --------------------------------------------------------------------------

_SS = "{urn:schemas-microsoft-com:office:spreadsheet}"
_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


_BARE_AMPERSAND = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);)")


def _parse_spreadsheetml(payload: bytes) -> Dict[str, List[List[str]]]:
    """The iShares fund workbook, which is XML rather than a binary .xls.

    The US estate emits invalid XML: a hyperlink attribute carries a raw `&`
    (`...#!type=ishares&style=All&view=...`), which stops a conformant parser on
    line 47 of a 67,000-line document. Bare ampersands are escaped first, and
    only those that do not already begin an entity, so a correctly encoded
    `&amp;` in a fund name is left alone. The German estate needs no repair;
    this is the same malformation third-party iShares scrapers patch around.
    """
    text = _BARE_AMPERSAND.sub("&amp;", payload.decode("utf-8-sig", errors="replace"))
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise FundPriceFetchError(f"the workbook is not parseable XML: {e}") from e

    sheets: Dict[str, List[List[str]]] = {}
    for worksheet in root.iter(f"{_SS}Worksheet"):
        rows = []
        for row in worksheet.iter(f"{_SS}Row"):
            cells: List[str] = []
            for cell in row.findall(f"{_SS}Cell"):
                # ss:Index means "this cell is column N". Reading cells
                # positionally would slide every later value one column left,
                # and a NAV read out of the units-outstanding column is a
                # plausible number that is wrong.
                index = cell.get(f"{_SS}Index")
                if index is not None:
                    try:
                        cells.extend([""] * (int(index) - 1 - len(cells)))
                    except ValueError:
                        pass
                cells.append("".join(cell.itertext()).strip())
            rows.append(cells)
        sheets[worksheet.get(f"{_SS}Name") or ""] = rows
    return sheets


def _parse_xlsx(payload: bytes) -> List[List[str]]:
    """The first worksheet of an .xlsx, cells placed at their declared column."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as e:
        raise FundPriceFetchError(f"the workbook is not a readable .xlsx: {e}") from e

    shared: List[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        shared = ["".join(n.text or "" for n in item.iter(f"{_X}t"))
                  for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]

    sheet_names = [n for n in archive.namelist()
                   if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    if not sheet_names:
        raise FundPriceFetchError("the workbook has no worksheets")

    def text(cell: ET.Element) -> str:
        if cell.get("t") == "inlineStr":
            return "".join(n.text or "" for n in cell.iter(f"{_X}t")).strip()
        value = cell.find(f"{_X}v")
        if value is None or value.text is None:
            return ""
        if cell.get("t") == "s":
            i = int(value.text)
            return shared[i] if 0 <= i < len(shared) else ""
        return value.text.strip()

    def column_of(reference: Optional[str]) -> Optional[int]:
        letters = "".join(c for c in (reference or "") if c.isalpha()).upper()
        if not letters:
            return None
        index = 0
        for char in letters:
            index = index * 26 + (ord(char) - ord("A") + 1)
        return index - 1

    root = ET.fromstring(archive.read(sorted(sheet_names)[0]))
    rows: List[List[str]] = []
    for row in root.iter(f"{_X}row"):
        cells: List[str] = []
        for cell in row.findall(f"{_X}c"):
            at = column_of(cell.get("r"))
            if at is None:
                at = len(cells)
            if at >= len(cells):
                cells.extend([""] * (at - len(cells) + 1))
            cells[at] = text(cell)
        rows.append(cells)
    return rows


def _labelled_preamble(rows: Sequence[Sequence[str]], limit: int = 12) -> Dict[str, str]:
    """`{'isin': 'IE00...', 'nav currency': 'USD'}` from a `Label:` / value block."""
    out: Dict[str, str] = {}
    for row in rows[:limit]:
        if len(row) >= 2 and row[0].strip().endswith(":"):
            out[row[0].strip().rstrip(":").lower()] = row[1].strip()
    return out


# --------------------------------------------------------------------------
# iShares  --  ISIN-queryable in both regions, one API for the document
# --------------------------------------------------------------------------

_ISHARES_EMEA_SEARCH = (
    "https://www.ishares.com/varnish-api/core-search/search/products"
    "?site=ishares-uk&locale=en-gb&userType=individual&rows=5&start=0&query={isin}"
)
_ISHARES_US_SCREENER = (
    "https://www.ishares.com/us/product-screener/product-screener-v3.jsn"
    "?dcrPath=/templatedata/config/product-screener-v3/data/en/us-ishares/"
    "ishares-product-screener-backend-config&siteEntryPassthrough=true"
)
_BLACKROCK_API = "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api"
_ISHARES_DOCUMENT = (
    _BLACKROCK_API + "/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES"
    "&component=fundDownload&userType=individual"
    "&portfolioId={pid}&targetSite={site}&locale={locale}"
)
_ISHARES_HEADER = (
    _BLACKROCK_API + "/v2/get-product-data?appType=PRODUCT_PAGE&appSubType=ISHARES"
    "&component=fundHeader&userType=individual"
    "&portfolioId={pid}&targetSite={site}&locale={locale}"
)


class ISharesSource:
    """Portfolio id from a lookup, then one API call for the workbook.

    Replaces an earlier route that scraped a `.ajax` component id out of the
    German product page. That page is being decommissioned -- the UK and US
    estates already serve a rebuilt front end where the `.ajax` path returns
    HTML with an `application/vnd.ms-excel` content type, which is the shape of
    failure most likely to be mistaken for success.
    """

    name = "iShares"
    _EMEA = ("emea-ishares-v2", "de_DE")
    _US = ("us-ishares", "en_US")

    def __init__(self, fetcher: HttpFetcher):
        self._fetcher = fetcher
        self._us_by_isin: Optional[Dict[str, str]] = None

    def _load_us_screener(self) -> Dict[str, str]:
        if self._us_by_isin is None:
            payload = json.loads(self._fetcher.get(_ISHARES_US_SCREENER)
                                 .decode("utf-8", errors="replace"))
            table = payload["data"]["tableData"]
            names = [c["name"] for c in table["columns"]]
            isin_at, pid_at = names.index("isin"), names.index("portfolioId")
            self._us_by_isin = {r[isin_at]: str(r[pid_at])
                                for r in table["data"] if r[isin_at]}
        return self._us_by_isin

    def _resolve(self, isin: str) -> Tuple[str, Tuple[str, str]]:
        """(portfolioId, (targetSite, locale)). EMEA search first, then the US list."""
        try:
            found = json.loads(self._fetcher.get(_ISHARES_EMEA_SEARCH.format(isin=isin))
                               .decode("utf-8", errors="replace"))
            results = found.get("results") or []
        except (FundPriceFetchError, ValueError):
            results = []
        if len(results) == 1:
            pid = str(results[0].get("portfolioId") or "").strip()
            if pid.isdigit():
                return pid, self._EMEA
        if len(results) > 1:
            # The ISIN did not identify a single share class. Picking from an
            # ambiguous list is how the distributing twin's price gets used.
            raise FundPriceFetchError(
                f"the iShares search returned {len(results)} funds for {isin}, not one")
        pid = self._load_us_screener().get(isin)
        if pid:
            return pid, self._US
        raise FundPriceFetchError(f"iShares publishes no fund with ISIN {isin}")

    def fetch(self, isin: str, symbol: Optional[str], year: int) -> FetchedPrice:
        pid, (site, locale) = self._resolve(isin)

        header = json.loads(
            self._fetcher.get(_ISHARES_HEADER.format(pid=pid, site=site, locale=locale))
            .decode("utf-8", errors="replace"))
        currency = (header.get("currencyCode") or "").strip().upper()
        fund_name = header.get("fundName") or f"iShares portfolio {pid}"
        if not currency:
            # Needed to convert at the Stichtag rate (Rz. 18.6); defaulting it
            # would value a dollar fund at par.
            raise FundPriceFetchError(f"iShares states no currency for {isin}")

        url = _ISHARES_DOCUMENT.format(pid=pid, site=site, locale=locale)
        sheets = _parse_spreadsheetml(self._fetcher.get(url))
        for rows in sheets.values():
            if len(rows) < 2:
                continue
            header_row = [c.strip().lower() for c in rows[0]]
            # Located by column heading, not sheet name: the sheet is
            # "Historisch" on the German estate and "Historical" on the US one,
            # and the heading is the part that says what the numbers are.
            price_at = next((i for i, c in enumerate(header_row)
                             if c in ("nav", "nav per share")), None)
            if price_at is None:
                continue
            series = []
            for row in rows[1:]:
                if len(row) <= price_at:
                    continue
                day = _parse_issuer_date(row[0])
                price = _parse_price(row[price_at])
                if day is not None and price is not None:
                    series.append((day, price))
            found = _first_price_set_in_year(series, year)
            if found is None:
                continue
            day, price, skipped = found
            return FetchedPrice(price=price, currency=currency, date_set=day,
                                provider=self.name, url=url, fund_name=fund_name,
                                skipped_carried_forward=skipped)
        raise FundPriceFetchError(f"the iShares workbook for {isin} has no {year} NAV")


# --------------------------------------------------------------------------
# SSGA / SPDR  --  map-backed, one product workbook per region
# --------------------------------------------------------------------------

_SSGA_LIBRARY = "https://www.ssga.com/library-content/products/fund-data/etfs"
_SSGA_PRODUCTS_EMEA = _SSGA_LIBRARY + "/emea/spdr-product-data-emea-en.xlsx"
_SSGA_PRODUCTS_US = _SSGA_LIBRARY + "/us/spdr-product-data-us-en.xlsx"
_SSGA_NAVHIST_EMEA = _SSGA_LIBRARY + "/emea/navhist-emea-en-{slug}.xlsx"
_SSGA_NAVHIST_US = _SSGA_LIBRARY + "/us/navhist-us-en-{slug}.xlsx"
_SSGA_FUNDFINDER_US = (
    "https://www.ssga.com/bin/v1/ssmp/fund/fundfinder"
    "?country=us&language=en&role=intermediary&product=etfs&ui=fund-finder"
)


class SsgaSource:
    """SPDR, keyed by the ticker its own product workbook publishes.

    The EMEA workbook carries a `Deutsche Boerse` column whose value is the
    Xetra ticker plus a country suffix -- `"ZPRG GY"` -- and the history file is
    named for exactly that, lowercased and hyphenated. The US workbook carries
    the plain ticker. Both are downloaded once per run.
    """

    name = "SPDR"

    def __init__(self, fetcher: HttpFetcher):
        self._fetcher = fetcher
        self._emea: Optional[Dict[str, Tuple[str, str]]] = None
        self._us: Optional[Dict[str, Tuple[str, str]]] = None
        self._us_uris: Optional[Dict[str, str]] = None

    # -- identity ---------------------------------------------------------

    def _load_emea(self) -> Dict[str, Tuple[str, str]]:
        if self._emea is None:
            rows = _parse_xlsx(self._fetcher.get(_SSGA_PRODUCTS_EMEA))
            head = next((i for i, r in enumerate(rows) if "ISIN" in r), None)
            if head is None:
                raise FundPriceFetchError("the SSGA EMEA product workbook has no ISIN column")
            names = rows[head]
            isin_at = names.index("ISIN")
            name_at = names.index("Fund Name") if "Fund Name" in names else None
            xetra_at = names.index("Deutsche Börse") if "Deutsche Börse" in names else None
            if xetra_at is None:
                raise FundPriceFetchError("the SSGA EMEA workbook has no Deutsche Börse column")
            table: Dict[str, Tuple[str, str]] = {}
            for row in rows[head + 1:]:
                if len(row) <= max(isin_at, xetra_at):
                    continue
                isin, listing = row[isin_at].strip(), row[xetra_at].strip()
                if not isin or not listing:
                    continue
                # "ZPRG GY" -> "zprg-gy"
                parts = listing.split()
                if len(parts) != 2:
                    continue
                fund_name = row[name_at].strip() if name_at is not None and len(row) > name_at else isin
                table[isin.upper()] = (f"{parts[0].lower()}-{parts[1].lower()}", fund_name)
            self._emea = table
        return self._emea

    def _load_us(self) -> Dict[str, Tuple[str, str]]:
        if self._us is None:
            rows = _parse_xlsx(self._fetcher.get(_SSGA_PRODUCTS_US))
            head = next((i for i, r in enumerate(rows) if "ISIN" in r), None)
            if head is None:
                raise FundPriceFetchError("the SSGA US product workbook has no ISIN column")
            names = rows[head]
            isin_at, tick_at = names.index("ISIN"), names.index("Ticker")
            name_at = names.index("Name") if "Name" in names else None
            table: Dict[str, Tuple[str, str]] = {}
            for row in rows[head + 1:]:
                if len(row) <= max(isin_at, tick_at):
                    continue
                isin = row[isin_at].strip().upper()
                ticker = row[tick_at].replace("®", "").strip().lower()
                if isin and ticker:
                    fund_name = (row[name_at].strip()
                                 if name_at is not None and len(row) > name_at else isin)
                    table[isin] = (ticker, fund_name)
            self._us = table
        return self._us

    def _us_fund_page(self, ticker: str) -> Optional[str]:
        if self._us_uris is None:
            payload = json.loads(self._fetcher.get(_SSGA_FUNDFINDER_US)
                                 .decode("utf-8", errors="replace"))
            self._us_uris = {
                d["fundTicker"].replace("®", "").strip().upper(): d["fundUri"]
                for d in payload["data"]["funds"]["etfs"]["datas"] if d.get("fundUri")}
        return self._us_uris.get(ticker.upper())

    # -- documents --------------------------------------------------------

    def fetch(self, isin: str, symbol: Optional[str], year: int) -> FetchedPrice:
        key = isin.upper()
        emea = self._load_emea()
        if key in emea:
            slug, fund_name = emea[key]
            return self._read(_SSGA_NAVHIST_EMEA.format(slug=slug), isin, fund_name, year,
                              expect_isin=True, currency=None)
        us = self._load_us()
        if key in us:
            ticker, fund_name = us[key]
            uri = self._us_fund_page(ticker)
            if not uri:
                raise FundPriceFetchError(f"no SSGA US fund page for {ticker}")
            page = self._fetcher.get("https://www.ssga.com" + uri).decode("utf-8", "replace")
            match = (re.search(r"Base Currency\s*</t[hd]>\s*<td[^>]*>([A-Z]{3})</td>", page)
                     or re.search(r"Base Currency\s*</div>\s*<div[^>]*>([A-Z]{3})</div>", page))
            if not match:
                # The US history file states no currency and the `$` its product
                # workbook prints is not one -- it is ambiguous across USD, CAD,
                # AUD, HKD and SGD.
                raise FundPriceFetchError(f"the SSGA page for {ticker} states no base currency")
            return self._read(_SSGA_NAVHIST_US.format(slug=ticker), isin, fund_name, year,
                              expect_isin=False, currency=match.group(1))
        raise FundPriceFetchError(f"SSGA publishes no fund with ISIN {isin}")

    def _read(self, url: str, isin: str, fund_name: str, year: int,
              *, expect_isin: bool, currency: Optional[str]) -> FetchedPrice:
        rows = _parse_xlsx(self._fetcher.get(url))
        preamble = _labelled_preamble(rows)

        if expect_isin:
            stated = preamble.get("isin", "")
            if stated.upper() != isin.upper():
                raise FundPriceFetchError(
                    f"{url} is the file for {stated or 'an unnamed fund'}, not {isin}")
            currency = (preamble.get("nav currency") or "").upper()
            if not currency:
                raise FundPriceFetchError(f"{url} does not state its NAV currency")

        head = next((i for i, r in enumerate(rows)
                     if len(r) >= 2 and r[0].strip().lower() == "date"
                     and r[1].strip().lower() == "nav"), None)
        if head is None:
            raise FundPriceFetchError(f"{url} has no Date/NAV table")

        series = []
        for row in rows[head + 1:]:
            if len(row) < 2:
                continue
            day, price = _parse_issuer_date(row[0]), _parse_price(row[1])
            if day is not None and price is not None:
                series.append((day, price))
        found = _first_price_set_in_year(series, year)
        if found is None:
            raise FundPriceFetchError(f"{url} carries no NAV dated in {year}")
        day, price, skipped = found
        return FetchedPrice(price=price, currency=currency, date_set=day,
                            provider=self.name, url=url, fund_name=fund_name,
                            skipped_carried_forward=skipped)


# --------------------------------------------------------------------------
# Swiss Fund Data  --  ISIN-queryable, many providers, the backstop
# --------------------------------------------------------------------------

_SFD_SEARCH = "https://www.swissfunddata.ch/sfdpub/en/funds/overview?text={isin}"
_SFD_DOWNLOAD = "https://www.swissfunddata.ch/sfdpub/de/funds/excelData/{fid}"
_SFD_ID = re.compile(r"/sfdpub/en/funds/show/(\d+)")


class SwissFundDataSource:
    """Every provider registered for distribution in Switzerland, keyed by ISIN.

    Ordered last, because its prices are rounded to three decimals where the
    issuers publish four to six -- measured on one fund and day, SSGA 31.1026
    against 31.103 here -- and Rz. 18.4 wants the Basisertrag carried at four or
    more ([GT-INVSTG-017]). It is the only route to a provider this module has
    no reader for, which is what it is here to be.

    The disclaimer cookie is sent directly rather than obtained by posting an
    acceptance: the value records which audience the visitor belongs to, and a
    private taxpayer is not a Swiss qualified investor.
    """

    name = "Swiss Fund Data"
    _COOKIE_URL_SUFFIX = ""      # the cookie travels on the session, see below

    def __init__(self, fetcher: HttpFetcher):
        self._fetcher = fetcher

    def fetch(self, isin: str, symbol: Optional[str], year: int) -> FetchedPrice:
        page = self._fetcher.get(_SFD_SEARCH.format(isin=isin)).decode("utf-8", "replace")
        ids = list(dict.fromkeys(_SFD_ID.findall(page)))
        if len(ids) != 1:
            raise FundPriceFetchError(
                f"Swiss Fund Data returned {len(ids)} funds for {isin}, not one")

        url = _SFD_DOWNLOAD.format(fid=ids[0])
        text = self._fetcher.get(url).decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(text.splitlines(), delimiter=";"))
        if len(rows) < 4:
            raise FundPriceFetchError(f"{url} carries no price history")

        # Line 2 is "<fund name> - <ISIN> (<currency>)": the identity check.
        title = rows[1][0] if rows[1] else ""
        if isin.upper() not in title.upper():
            raise FundPriceFetchError(f"{url} is headed {title!r}, which does not name {isin}")
        fund_name = title.split(" - ")[0].strip() or isin

        header = rows[2]
        try:
            price_at = header.index("Net Asset Value")
            ccy_at = header.index("CCY Chart Price")
        except ValueError:
            raise FundPriceFetchError(f"{url} has no Net Asset Value column")

        series, currency = [], ""
        for row in rows[3:]:
            if len(row) <= max(price_at, ccy_at):
                continue
            day, price = _parse_issuer_date(row[0]), _parse_price(row[price_at])
            if day is not None and price is not None:
                series.append((day, price))
                if day.year == year and not currency:
                    currency = (row[ccy_at] or "").strip().upper()
        found = _first_price_set_in_year(series, year)
        if found is None:
            raise FundPriceFetchError(f"{url} carries no NAV dated in {year}")
        day, price, skipped = found
        if not currency:
            raise FundPriceFetchError(f"{url} states no currency for {year}")
        return FetchedPrice(price=price, currency=currency, date_set=day,
                            provider=self.name, url=url, fund_name=fund_name,
                            skipped_carried_forward=skipped)


# --------------------------------------------------------------------------
# VanEck  --  site search for the page, then the page's own block API
# --------------------------------------------------------------------------

_VANECK = "https://www.vaneck.com"
_VANECK_SEARCH = _VANECK + "/de/en/search/?searchtext={isin}"
_VANECK_PERFORMANCE = _VANECK + "/de/en/investments/{slug}/performance/"
_VANECK_BLOCK = (_VANECK + "/Main/HistoPricesBlock/GetContent/"
                 "?blockid={block}&pageid={page}&ticker={ticker}")
_VANECK_FUND_PATH = re.compile(r"/de/en/investments/([a-z0-9-]+)/")
_VANECK_TICKER = re.compile(r"<ve-fundticker[^>]*>(.*?)</ve-fundticker>", re.S)
_VANECK_BLOCK_EL = re.compile(r"<ve-histopricesblock\b[^>]*>")
_VANECK_BLOCKID = re.compile(r'data-blockid="(\d+)"')
_VANECK_PAGEID = re.compile(r'data-pageid="(\d+)"')


class VanEckSource:
    """The only provider here whose page has to be found by searching for it.

    VanEck publishes no product list this could be keyed from -- the fund
    listing page is a shell, and none of the 65 script chunks carries a listing
    endpoint. What it does have is a site search that accepts an ISIN, and a
    result page linking exactly one fund. From there the page's own block API
    supplies both the currency and the download URL, so neither is constructed
    by convention.

    Neither the workbook nor the fund page states an ISO currency anywhere --
    the page prints `$65.33` and the workbook has four columns and no currency
    at all. `CurrencyName` from the block API is the only machine-readable
    statement of it, which is why this source goes through the API rather than
    straight to the download it already knows how to name.
    """

    name = "VanEck"

    def __init__(self, fetcher: HttpFetcher):
        self._fetcher = fetcher

    def fetch(self, isin: str, symbol: Optional[str], year: int) -> FetchedPrice:
        results = self._fetcher.get(_VANECK_SEARCH.format(isin=isin)).decode("utf-8", "replace")
        slugs = list(dict.fromkeys(_VANECK_FUND_PATH.findall(results)))
        if len(slugs) != 1:
            raise FundPriceFetchError(
                f"the VanEck search returned {len(slugs)} funds for {isin}, not one")

        page_url = _VANECK_PERFORMANCE.format(slug=slugs[0])
        page = self._fetcher.get(page_url).decode("utf-8", "replace")
        if isin.upper() not in page.upper():
            # The search matched, but this is the page the figures come from.
            raise FundPriceFetchError(f"the VanEck page {slugs[0]} does not name {isin}")

        ticker_match = _VANECK_TICKER.search(page)
        block_match = _VANECK_BLOCK_EL.search(page)
        if not ticker_match or not block_match:
            raise FundPriceFetchError(f"the VanEck page {slugs[0]} carries no price block")
        block_el = block_match.group(0)
        block_id = _VANECK_BLOCKID.search(block_el)
        page_id = _VANECK_PAGEID.search(block_el)
        if not block_id or not page_id:
            raise FundPriceFetchError(f"the VanEck price block on {slugs[0]} is unidentified")

        block = json.loads(self._fetcher.get(_VANECK_BLOCK.format(
            block=block_id.group(1), page=page_id.group(1),
            ticker=ticker_match.group(1).strip())).decode("utf-8", "replace")).get("data") or {}
        currency = (block.get("CurrencyName") or "").strip().upper()
        download = (block.get("DownloadUrl") or "").strip()
        if not currency:
            raise FundPriceFetchError(f"VanEck states no currency for {isin}")
        if not download:
            raise FundPriceFetchError(f"VanEck offers no price history for {isin}")

        url = _VANECK + download
        rows = _parse_xlsx(self._fetcher.get(url))
        fund_name = (rows[0][0].strip() if rows and rows[0] else isin) or isin
        head = next((i for i, r in enumerate(rows)
                     if len(r) >= 2 and r[0].strip().lower() == "date"
                     and r[1].strip().lower() == "nav"), None)
        if head is None:
            raise FundPriceFetchError(f"{url} has no Date/NAV table")

        series = []
        for row in rows[head + 1:]:
            if len(row) < 2:
                continue
            # Day-first: this provider only. See `_parse_day_first_date`.
            day, price = _parse_day_first_date(row[0]), _parse_price(row[1])
            if day is not None and price is not None:
                series.append((day, price))
        found = _first_price_set_in_year(series, year)
        if found is None:
            raise FundPriceFetchError(f"{url} carries no NAV dated in {year}")
        day, price, skipped = found
        return FetchedPrice(price=price, currency=currency, date_set=day,
                            provider=self.name, url=url, fund_name=fund_name,
                            skipped_carried_forward=skipped)


# --------------------------------------------------------------------------
# The one entry point
# --------------------------------------------------------------------------

def _sources(fetcher: HttpFetcher) -> List:
    # Issuers first: they publish four to six decimals where the aggregator
    # rounds to three, and Rz. 18.4 wants four or more ([GT-INVSTG-017]).
    return [ISharesSource(fetcher), SsgaSource(fetcher), VanEckSource(fetcher),
            SwissFundDataSource(fetcher)]


def fetch_year_start_price(
    asset: Asset,
    year: int,
    fetcher: Optional[HttpFetcher] = None,
) -> Optional[FetchedPrice]:
    """The first NAV published in `year`, or None if it cannot be had.

    **Returns None on every failure and raises on none of them.** A fund this
    cannot price is not an error condition: the prompt asks for the price as it
    did before, and the FAIL_FAST in `fund_prices.py` still stops a run that
    ends without one.

    Nothing is returned unless the provider's own map or search matched the ISIN
    asked for and the document carries a price dated inside `year`.
    """
    isin = (asset.ibkr_isin or "").strip()
    if not isin:
        # Every route is keyed by ISIN, and matching a fund on its description
        # is exactly the kind of near-miss this module refuses.
        return None

    fetcher = fetcher or RequestsHttpFetcher()
    for source in _sources(fetcher):
        try:
            found = source.fetch(isin, asset.ibkr_symbol, year)
        except FundPriceFetchError as e:
            logger.info("No %s year-start price for %s: %s", source.name, isin, e)
            continue
        except Exception as e:                       # a parser meeting a new layout
            logger.warning("The %s lookup for %s failed unexpectedly: %s",
                           source.name, isin, e)
            continue
        logger.info("%s NAV for %s on %s: %s %s%s", source.name, isin, found.date_set,
                    found.price, found.currency,
                    " (skipped a carried-forward row)" if found.skipped_carried_forward else "")
        return found
    return None

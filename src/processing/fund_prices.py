# src/processing/fund_prices.py
"""
The year-start Ruecknahmepreis for a fund the account did not hold on 1 January.

§ 18 Abs. 1 Satz 2 InvStG builds the Basisertrag from *"dem Ruecknahmepreis des
Investmentanteils zu Beginn des Kalenderjahres"* ([GT-INVSTG-010]). That price
is a property of the **fund**: it existed and was set on the year's first
trading day whether or not the taxpayer held a single unit. Abs. 2 then reduces
the figure by a twelfth for each full month before the month of acquisition
([GT-INVSTG-011]), and Rz. 18.4 multiplies by the units held at the close of
31 December ([GT-INVSTG-017]).

**Buying a fund during the year is ordinary, and it is not a data gap.** The
figure is due and it is computable. What is missing is one number, because
`Positions-{Y}-SoY.csv` is a report of what was *held* and no IBKR export
carries a price for an instrument the account did not hold. IBKR cannot supply
it either: its historical endpoints serve market prices, and its NAV ticks reach
one session back.

So the engine asks, and remembers the answer -- the same shape as
`AssetClassifier`, which asks for a classification it cannot derive and caches
it under the asset's classification key. That is the design
`src/processing/data_gaps.py` has described all along, in naming *"an
unresolvable year-start NAV for the Vorabpauschale in a non-interactive run"* as
its fail-fast example: the qualifier presupposes that an interactive run
resolves it by asking.

**What must never happen is the engine inventing the price.** CLAUDE.md draws
the line between deriving a value from inputs that are present and substituting
a stand-in for one that is absent; a mark price, a cost basis or the year-end
price standing in here would each be a plausible number nobody can check, on a
tax return. The three outcomes are: a price the taxpayer supplied, a price
recalled from a previous answer, or a stopped run naming every fund that needs
one.

Provenance travels with the price. A taxpayer-supplied figure is not a broker
figure, so each one is recorded through the data-gap channel at WARNING and
reaches the report -- the treatment `VORABPAUSCHALE_PRICE_WRONG_DAY` already
gets for a substituted price the run then uses.

**The question can arrive with an answer in it.** `fund_price_sources.py` looks
the figure up in the issuer's own published NAV history and offers it as the
prompt's default, alongside what the account actually paid per unit, so the
taxpayer is checking a number rather than hunting for one. Neither of those
changes who decides: the fetched figure is a default on a prompt, the accepted
value is still the taxpayer's, and a fund nothing can price still stops the run.
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from src.domain.assets import Asset, InvestmentFund
from src.domain.exceptions import ProcessingError
from src.processing.data_gaps import DataGapCollector, GapSeverity

logger = logging.getLogger(__name__)

# Recorded per fund whose price the taxpayer supplied, so the report states what
# the Basisertrag rests on. WARNING, not FAIL_FAST: the figure is complete, and
# what the taxpayer has to do before filing is check a number they typed.
USER_SUPPLIED_CODE = "VORABPAUSCHALE_PRICE_USER_SUPPLIED"

# Recorded once, naming every fund, when no price can be obtained. FAIL_FAST:
# deemed income that is due would otherwise be silently absent.
UNKNOWN_CODE = "VORABPAUSCHALE_YEAR_START_PRICE_UNKNOWN"

# Recorded per fund priced from a figure outside the broker export -- the
# provider's published NAV, or an answer the taxpayer gave. WARNING, not
# FAIL_FAST: the figure is complete and is the measure § 18 Abs. 1 Satz 2 asks
# for, but it did not come from the export and the report should say so.
ISSUER_NAV_CODE = "VORABPAUSCHALE_PRICE_ISSUER_NAV"

# Recorded per fund left on the position report's mark because no
# Ruecknahmepreis could be obtained. WARNING: the run is complete, but the
# figure rests on § 18 Abs. 1 Satz 4's substitute where the primary measure
# exists, and a reader should be able to see which funds those are.
MARKET_FALLBACK_CODE = "VORABPAUSCHALE_PRICE_MARKET_FALLBACK"


@dataclass(frozen=True)
class FundPrice:
    """One Ruecknahmepreis, with everything needed to convert and to audit it.

    `date_set` is the day the price was set, which Rz. 18.6 converts at
    ([GT-INVSTG-018]) -- not a day derived from the calendar year, because a
    price supplied by hand may well come from a day the engine cannot guess.
    `source` is where the taxpayer got it, and exists so that a figure on a tax
    return can be traced to something outside this program.
    """
    price: Decimal
    currency: str
    date_set: date
    source: str


class FundPriceStore:
    """Ruecknahmepreise the taxpayer has supplied, keyed by fund and year.

    Mirrors `AssetClassifier`'s cache: a JSON file of answers to questions the
    engine cannot derive. Keyed by the asset's classification key and the
    calendar year, because each year has its own price.

    A file that cannot be read raises rather than starting empty. Starting empty
    would re-ask for every price in an interactive run, and in a non-interactive
    one would abort as though no answer had ever been given -- both of which
    read as "the store is broken" only if someone is watching the log.
    """

    def __init__(self, cache_file_path: Optional[str] = None):
        if cache_file_path is None:
            import src.config as app_config
            cache_file_path = app_config.FUND_PRICE_CACHE_FILE_PATH
        self.cache_file_path = cache_file_path
        self._prices: Dict[str, FundPrice] = {}
        self._load()

    @staticmethod
    def _key(classification_key: str, year: int) -> str:
        return f"{classification_key}|{year}"

    def _load(self) -> None:
        if not os.path.exists(self.cache_file_path):
            return
        try:
            with open(self.cache_file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            raise ProcessingError(
                f"The fund price store at {self.cache_file_path} could not be read: {e}. "
                "It holds Ruecknahmepreise supplied by hand that nothing can recompute; "
                "treating it as empty would discard them silently. Fix or remove the file."
            ) from e

        for key, entry in raw.items():
            try:
                self._prices[key] = FundPrice(
                    # Decimal from the stored *text*: a float round-trip would
                    # alter a figure the taxpayer is asked to check.
                    price=Decimal(str(entry["price"])),
                    currency=entry["currency"],
                    date_set=date.fromisoformat(entry["date_set"]),
                    source=entry.get("source", ""),
                )
            except (KeyError, ValueError, TypeError) as e:
                raise ProcessingError(
                    f"Fund price store entry {key!r} in {self.cache_file_path} is "
                    f"unreadable: {e}. A malformed price cannot be guessed at."
                ) from e

    def get(self, classification_key: str, year: int) -> Optional[FundPrice]:
        return self._prices.get(self._key(classification_key, year))

    def put(self, classification_key: str, year: int, price: FundPrice) -> None:
        self._prices[self._key(classification_key, year)] = price

    def save(self) -> None:
        directory = os.path.dirname(self.cache_file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            key: {
                "price": str(p.price),
                "currency": p.currency,
                "date_set": p.date_set.isoformat(),
                "source": p.source,
            }
            for key, p in sorted(self._prices.items())
        }
        with open(self.cache_file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def __len__(self) -> int:
        return len(self._prices)


def _owes_a_vorabpauschale(asset: Asset) -> bool:
    """Whether this fund's figure turns on a year-start price at all.

    Two conditions, and each keeps a fund off the network and off the
    taxpayer's screen:

    - it is an investment fund, so § 18 reaches it;
    - units were held at the close of 31 December, because Rz. 18.4 multiplies
      by exactly that count and a fund disposed of in full yields nothing
      whatever its price was ([GT-INVSTG-016]).

    **Whether the fund appears in the start-of-year snapshot is not one of
    them.** It was, until 2026-08-08. The snapshot records what the taxpayer
    held; § 18 Abs. 1 Satz 2 asks for a property of the fund.
    """
    if not isinstance(asset, InvestmentFund):
        return False
    return (asset.prior_year_eoy_quantity or Decimal(0)) > Decimal(0)


def _snapshot_price(asset: Asset) -> Optional["FundPrice"]:
    """The start-of-year position report's price, where the fund is in it."""
    if asset.prior_year_soy_mark_price is None:
        return None
    return FundPrice(
        price=asset.prior_year_soy_mark_price,
        currency=asset.prior_year_soy_mark_price_currency or asset.currency or "EUR",
        date_set=asset.prior_year_soy_mark_price_date,
        source="Positionsbericht zum Jahresanfang (Boersen- bzw. Marktpreis)",
    )


def resolve_year_start_prices(
    assets: Iterable[Asset],
    vorabpauschale_year: int,
    store: "FundPriceStore",
    interactive: bool,
    data_gap_collector: Optional[DataGapCollector] = None,
    ask: Optional[Callable] = None,
    fetch: Optional[Callable] = None,
    auto_fetch: bool = True,
) -> int:
    """Give every fund that owes a Vorabpauschale its year-start Ruecknahmepreis.

    Returns the number of funds priced. Raises `DataGapError` -- through the gap
    channel, so the condition is recorded before it raises -- when a fund needs a
    price that nothing and nobody can give.

    **The Ruecknahmepreis is what § 18 Abs. 1 Satz 2 asks for, so it is what is
    sought first, for every fund.** An open-ended fund that redeems units at its
    NAV sets one; the position report's mark is a Boersen- oder Marktpreis, which
    Satz 4 admits only where no Ruecknahmepreis was set ([GT-INVSTG-010]). Until
    2026-08-08 the engine used the report's mark wherever it had one and only
    went looking when it did not, which put the substitute ahead of the primary
    measure for every fund held across 1 January.

    The order is therefore:

    1. **a price already stored** for this fund and year -- a past year's first
       NAV does not change, so a figure once obtained is not fetched again;
    2. **the provider's published NAV**, by ISIN;
    3. **the taxpayer**, offered the position report's price as the default
       where the report has one, because that is the figure the run would
       otherwise have used and it is right to within an ETF's premium to NAV;
    4. **the position report's price**, in a non-interactive run where nobody
       can be asked;
    5. **nothing** -- and then the run stops, naming every fund, rather than
       leaving deemed income silently absent.

    Steps 3 and 4 both record that a market price stood in for the
    Ruecknahmepreis, so a reader can see which funds rest on the substitute.
    """
    from src.tax_law.registry import basiszins_pct

    # A year whose Basiszins is not positive produces no Vorabpauschale for any
    # fund (§ 18 Abs. 1 Satz 2 multiplies by it), so no price can move a figure
    # and no fund is worth a network round trip or a question.
    basiszins = basiszins_pct(vorabpauschale_year)
    if basiszins is None or basiszins <= Decimal(0):
        logger.info(
            "Vorabpauschale %d: Basiszins is %s, so no year-start price is needed.",
            vorabpauschale_year, basiszins)
        return 0

    wanted = [a for a in assets if _owes_a_vorabpauschale(a)]
    if not wanted:
        return 0

    if fetch is None and auto_fetch:
        from src.processing.fund_price_sources import fetch_year_start_price
        fetch = fetch_year_start_price

    priced = 0
    unresolved: List[Tuple[str, str]] = []

    for asset in wanted:
        key = asset.get_classification_key()
        snapshot = _snapshot_price(asset)
        price: Optional[FundPrice] = None
        code = ISSUER_NAV_CODE
        newly_given = False

        # 1 -- already stored. Covers both a NAV fetched on an earlier run and
        # an answer the taxpayer typed; `source` says which.
        price = store.get(key, vorabpauschale_year)

        # 2 -- the provider.
        if price is None and fetch is not None:
            logger.info("Looking up the %d NAV for %s.", vorabpauschale_year, key)
            found = fetch(asset, vorabpauschale_year)
            if found is not None:
                price = FundPrice(price=found.price, currency=found.currency,
                                  date_set=found.date_set,
                                  source=found.as_source(date.today()))
                newly_given = True

        # 3 -- the taxpayer, offered the report's price where there is one.
        # Whether they accepted that default is read off the price's `source`,
        # not off its value: a Ruecknahmepreis someone looked up themselves may
        # happen to equal the report's mark, and it is still not the substitute.
        if price is None and interactive and ask is not None:
            price = ask(asset, vorabpauschale_year, snapshot)
            newly_given = price is not None

        # 4 -- the report's price, where nobody can be asked.
        if price is None and snapshot is not None:
            price = snapshot
            code = MARKET_FALLBACK_CODE

        if price is None:
            unresolved.append((key, asset.description or ""))
            continue

        if price.source.startswith("Positionsbericht"):
            code = MARKET_FALLBACK_CODE

        asset.prior_year_soy_mark_price = price.price
        asset.prior_year_soy_mark_price_currency = price.currency
        asset.prior_year_soy_mark_price_date = price.date_set
        priced += 1

        # Only a figure obtained from outside the export is worth storing. The
        # report's own price is in the export and is re-read every run.
        if newly_given and code != MARKET_FALLBACK_CODE:
            store.put(key, vorabpauschale_year, price)
            store.save()

        if data_gap_collector is not None:
            data_gap_collector.record(
                code=code,
                subject=f"{key} ({asset.description or ''})",
                detail=_price_provenance(code, price, vorabpauschale_year),
                severity=GapSeverity.WARNING,
            )

    if unresolved:
        named = "; ".join(f"{key} ({description})" for key, description in unresolved)
        detail = (
            f"Fuer {len(unresolved)} Fonds fehlt der Ruecknahmepreis zu Beginn des "
            f"Kalenderjahres {vorabpauschale_year}. Die Anteile wurden zum 31.12. "
            "gehalten, also ist nach § 18 Abs. 1 Satz 2 i.V.m. Abs. 2 InvStG eine "
            "-- gegebenenfalls zeitanteilig geminderte -- Vorabpauschale anzusetzen. "
            "Weder der Fondsanbieter noch der Positionsbericht noch eine fruehere "
            "Eingabe liefert einen Preis. Ohne ihn wuerden die Einkuenfte "
            "untererfasst, daher bricht der Lauf ab, statt eine Null auszuweisen."
        )
        if data_gap_collector is not None:
            data_gap_collector.record(
                code=UNKNOWN_CODE, subject=named, detail=detail,
                severity=GapSeverity.FAIL_FAST,
            )  # records, logs CRITICAL and raises
        from src.processing.data_gaps import DataGapError
        raise DataGapError(f"[{UNKNOWN_CODE}] {named}: {detail}")

    return priced


def _price_provenance(code: str, price: "FundPrice", vorabpauschale_year: int) -> str:
    """What the report says about where a fund's Satz 2 base came from."""
    if code == MARKET_FALLBACK_CODE:
        return (
            f"Als Ruecknahmepreis zu Beginn des Kalenderjahres {vorabpauschale_year} "
            f"wurde ersatzweise der Kurs aus dem Positionsbericht verwendet: "
            f"{price.price} {price.currency} zum "
            f"{price.date_set.isoformat() if price.date_set else 'unbekannt'}. "
            "Das ist ein Boersen- bzw. Marktpreis, den § 18 Abs. 1 Satz 4 InvStG "
            "nur vorsieht, wenn kein Ruecknahmepreis festgesetzt wird; ein solcher "
            "war hier nicht abrufbar. Die Abweichung entspricht dem Auf- bzw. "
            "Abgeld zum Nettoinventarwert."
        )
    return (
        f"Der Ruecknahmepreis zu Beginn des Kalenderjahres {vorabpauschale_year} "
        f"stammt nicht aus dem Broker-Export: {price.price} {price.currency} zum "
        f"{price.date_set.isoformat() if price.date_set else 'unbekannt'}. "
        f"Quelle: {price.source}. Bitte vor Abgabe der Erklaerung pruefen."
    )


@dataclass(frozen=True)
class AcquisitionAnchor:
    """What the account paid per unit, shown next to a price to be checked.

    A plausibility check, and nothing more. It cannot tell a right
    Ruecknahmepreis from a slightly wrong one -- a year-start price and a
    mid-year purchase price differ by however the fund moved -- but it is the
    one figure on hand that catches the errors that actually happen: a price off
    by a factor of a hundred, a per-lot amount typed where a per-unit one
    belongs, or a fetch that resolved to the wrong share class.

    Per unit only, deliberately. A total would be the size of the position, and
    a per-unit price is the right comparand for a per-unit Ruecknahmepreis
    anyway.
    """
    price_per_unit: Decimal
    currency: str
    first_date: date
    acquisitions: int

    def describe(self) -> str:
        when = (f"am {self.first_date.isoformat()}" if self.acquisitions == 1
                else f"ab {self.first_date.isoformat()}, {self.acquisitions} Käufe")
        return (f"{self.price_per_unit:.4f} {self.currency} je Anteil "
                f"(gekauft {when})")


def acquisition_anchor(
    asset: Asset, events: Iterable, vorabpauschale_year: int,
) -> Optional[AcquisitionAnchor]:
    """The volume-weighted price per unit the account paid during the year.

    Derived wholly from trades already imported, so this invents nothing: it is
    the arithmetic CLAUDE.md permits on inputs that are all present, not a
    stand-in for one that is absent. Returns None rather than a placeholder when
    the trades do not support it -- a mixed-currency holding has no single
    per-unit price, and showing one currency's figure under another's label
    would mislead exactly the check this exists to support.
    """
    from src.domain.enums import FinancialEventType

    total_units = Decimal(0)
    total_cost = Decimal(0)
    currencies = set()
    dates: List[date] = []

    for event in events:
        if getattr(event, "asset_internal_id", None) != asset.internal_asset_id:
            continue
        if getattr(event, "event_type", None) is not FinancialEventType.TRADE_BUY_LONG:
            continue
        quantity = getattr(event, "quantity", None)
        unit_price = getattr(event, "price_foreign_currency", None)
        if quantity is None or unit_price is None or quantity <= 0:
            continue
        try:
            day = date.fromisoformat(event.event_date)
        except (TypeError, ValueError):
            continue
        if day.year != vorabpauschale_year:
            continue
        total_units += quantity
        total_cost += quantity * unit_price
        currencies.add(getattr(event, "local_currency", None) or asset.currency or "EUR")
        dates.append(day)

    if total_units <= 0 or len(currencies) != 1:
        return None
    return AcquisitionAnchor(
        price_per_unit=total_cost / total_units,
        currency=currencies.pop(),
        first_date=min(dates),
        acquisitions=len(dates),
    )


def prompt_for_fund_price(
    asset: Asset,
    vorabpauschale_year: int,
    snapshot: Optional[FundPrice] = None,
    *,
    anchor: Optional[AcquisitionAnchor] = None,
) -> Optional[FundPrice]:
    """Ask at the console for one fund's year-start Ruecknahmepreis.

    Reached only where no Ruecknahmepreis could be obtained: nothing stored from
    an earlier run, and no provider that publishes this ISIN. Returns None where
    the taxpayer cannot supply one either, which the caller treats as the
    fail-fast case -- never as a zero and never as a skip.

    `snapshot` is the start-of-year position report's price where the report has
    one, offered as the default. Accepting it is a real choice and is recorded as
    one: it is a Boersen- oder Marktpreis, which § 18 Abs. 1 Satz 4 admits only
    where no Ruecknahmepreis was set ([GT-INVSTG-010]), and here one probably was
    -- it just could not be reached. For a liquid ETF the two differ by the
    premium to NAV. `anchor` is what the account paid per unit, shown beside it
    so a figure off by a factor is visible.

    With no snapshot the currency defaults to the fund's own and the day to the
    year's first trading day. Both are confirmable rather than assumed, since a
    price from another day converts at another rate ([GT-INVSTG-018]) -- and for
    a fund launched mid-year the right day is its first, not the year's.
    """
    # No default day where nothing was offered. A calendar date would be wrong
    # for a fund launched during the year, whose first set price is its own
    # first day (Rz. 18.7, [GT-INVSTG-035]) -- and a proposed date is the kind of
    # thing that gets accepted with Enter.
    default_day = snapshot.date_set if snapshot else None
    default_currency = (snapshot.currency if snapshot else asset.currency) or "EUR"
    default_price = snapshot.price if snapshot else None
    default_source = snapshot.source if snapshot else ""

    print(f"\n--- Vorabpauschale {vorabpauschale_year}: Rücknahmepreis zum Jahresanfang ---")
    print(f"  Fonds:   {asset.description or ''} [{asset.get_classification_key()}]")
    print(f"  Gesucht: der erste im Kalenderjahr {vorabpauschale_year} festgesetzte "
          f"Rücknahmepreis JE ANTEIL (§ 18 Abs. 1 Satz 2 InvStG).")

    if anchor is not None:
        print(f"  Gezahlt: {anchor.describe()}  <- nur zum Plausibilisieren")

    print("  Hinweis: beim Fondsanbieter war kein Rücknahmepreis abrufbar.")
    if snapshot is not None:
        print(f"  Ersatz:  {snapshot.price} {snapshot.currency}"
              + (f" zum {snapshot.date_set.isoformat()}" if snapshot.date_set else "")
              + " aus dem Positionsbericht — ein Börsen-/Marktpreis,")
        print("           den § 18 Abs. 1 Satz 4 InvStG nur ersatzweise vorsieht. "
              "Mit Enter übernehmen,")
        print("           oder den Rücknahmepreis des Anbieters eintragen.")
    else:
        print("  Quelle:  die NAV-Historie des Fondsanbieters. Leer lassen, "
              "wenn nicht bekannt.")

    price_default = f" [{default_price}]" if default_price is not None else ""
    raw_price = input(
        f"  Preis je Anteil in {default_currency}{price_default}: "
    ).strip().replace(",", ".")
    if not raw_price and default_price is not None:
        price = default_price
    elif not raw_price:
        logger.warning("No year-start price given for %s.", asset.get_classification_key())
        return None
    else:
        try:
            price = Decimal(raw_price)
        except Exception:
            print(f"  '{raw_price}' ist keine Zahl. Übersprungen.")
            return None
    if price <= Decimal(0):
        print("  Ein Rücknahmepreis muss positiv sein. Übersprungen.")
        return None

    currency = input(f"  Währung [{default_currency}]: ").strip().upper() or default_currency

    hint = f" [{default_day.isoformat()}]" if default_day else ""
    raw_day = input(f"  Festgesetzt am (YYYY-MM-DD){hint}: ").strip()
    if not raw_day and default_day is None:
        print("  Ohne den Tag lässt sich der Kurs nicht umrechnen "
              "(Rz. 18.6). Übersprungen.")
        return None
    try:
        day = date.fromisoformat(raw_day) if raw_day else default_day
    except ValueError:
        print(f"  '{raw_day}' ist kein Datum. Übersprungen.")
        return None
    if day.year != vorabpauschale_year:
        print(f"  {day} liegt nicht im Kalenderjahr {vorabpauschale_year}. Übersprungen.")
        return None

    source_default = f" [{default_source}]" if default_source else ""
    source = input(
        f"  Quelle (z.B. 'iShares NAV-Historie, abgerufen "
        f"{date.today().isoformat()}'){source_default}: "
    ).strip() or default_source
    if not source:
        print("  Ohne Quellenangabe wird der Wert nicht übernommen: eine Zahl in der "
              "Steuererklärung muss nachvollziehbar sein.")
        return None

    return FundPrice(price=price, currency=currency, date_set=day, source=source)


def make_price_prompt(
    events: Optional[Iterable] = None,
) -> Callable[[Asset, int, Optional[FundPrice]], Optional[FundPrice]]:
    """Build the `ask` callable the pipeline passes to the resolver.

    Kept as a factory only so the acquisition anchor can be closed over: the
    resolver takes a plain three-argument `ask` and stays testable without a
    console or a stream of events. The lookup is no longer in here -- the
    resolver does it for every fund, before anyone is asked.
    """
    materialised = list(events) if events is not None else []

    def ask(asset: Asset, vorabpauschale_year: int,
            snapshot: Optional[FundPrice] = None) -> Optional[FundPrice]:
        return prompt_for_fund_price(
            asset, vorabpauschale_year, snapshot,
            anchor=acquisition_anchor(asset, materialised, vorabpauschale_year))

    return ask

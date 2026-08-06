"""
Download Flex Query reports for any year from the IBKR Client Portal.

The Flex Web Service API (src/flex_downloader.py) only serves about the last
two calendar years; everything older has to come from the portal, which the
README documents as a manual procedure. This runs that procedure.

    uv run --extra web python -m src.web_portal.download --years 2021-2023

A browser opens; log in yourself, including two-factor. Your password is never
asked for, stored or recorded. Once the portal answers as a logged-in user, the
downloader runs each configured query for each requested year, waits for the
portal's batch processing, and writes the results into data_import/ under the
naming scheme the engine expects.

Existing files are never overwritten unless --overwrite is given: data_import/
is the engine's source of truth for input, and silently replacing a year of
history is not something a download flag should do by accident.
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

from src import config
from src.web_portal import require_playwright
from src.web_portal.browser import (
    DEFAULT_PORTAL_URL,
    DEFAULT_PROFILE_DIR,
    open_portal,
    portal_session,
    reset_profile,
)
from src.web_portal.flex_portal import (
    BASE_URL,
    NoStatementAvailableError,
    NotAuthenticatedError,
    AmHeaderHarvester,
    FlexQuery,
    PageRequestTransport,
    PortalError,
    PortalFlexClient,
    normalise_query_name,
    strip_name_prefix,
)
from src.web_portal.identity import load_username, save_username

logger = logging.getLogger(__name__)

IMPORT_DIR = Path(config.IMPORT_DIR)

# Query key -> data_import/ filename prefix. Must stay in step with what
# src/data_preparation.py looks for; tests/test_web_portal_targets.py asserts
# that the files written here are the files it finds.
FILENAME_PREFIXES = {
    "trades": "Trades",
    "cash_transactions": "Cash_Transactions",
    "corporate_actions": "Corporate_Actions",
    "cash_balance": "Cash_Balance",
    "options_eae": "Options_EAE",
    "positions": "Positions",
}

# Portal query name (normalised, naming prefix removed) -> query key. The names
# are the ones the README tells you to give the six queries; separators and
# case do not matter, so "MyTax_Cash_Transactions" and "MyTax Cash
# Transactions" both resolve to cash_transactions.
QUERY_KEYS_BY_NAME = {
    "trades": "trades",
    "cash transactions": "cash_transactions",
    "corporate actions": "corporate_actions",
    "positions": "positions",
    "cash balance": "cash_balance",
    "options eae": "options_eae",
    "option exercises assignments expirations": "options_eae",
    "options exercises assignments expirations": "options_eae",
}

# How long to wait for a manual login before giving up.
LOGIN_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class DownloadTarget:
    """One query run over one date range, landing in one file."""
    query_key: str
    query_id: int
    from_date: date
    to_date: date
    filename: str

    @property
    def label(self) -> str:
        if self.from_date == self.to_date:
            return f"{self.query_key} @ {self.from_date}"
        return f"{self.query_key} {self.from_date.year}"


def weekday_on_or_before(day: date) -> date:
    """
    `day` itself if it is a weekday, else the Friday before it.

    The portal's date picker accepts weekdays and refuses weekends — it does
    not know or care about market holidays. 1 January 2025 was a Wednesday and
    was accepted; the recorded run for it returned a report. So the constraint
    to respect is Monday-to-Friday, not "a day the exchange was open".
    """
    while day.weekday() >= 5:      # 5 = Saturday, 6 = Sunday
        day -= timedelta(days=1)
    return day


def last_business_day_of_year(year: int) -> date:
    """31 December, or the Friday before it when it falls on a weekend."""
    return weekday_on_or_before(date(year, 12, 31))


def first_business_day_of_year(year: int) -> date:
    """
    The date to ask for a start-of-year snapshot: 1 January, rolled back.

    This snapshot supplies two different things, and they want two different
    days. Its **quantities and cost bases** are the ledger's opening position,
    on top of which the year's trades are replayed — so they must be the
    holding *before* the year's first trade. Its **mark price** feeds the
    Vorabpauschale as the Ruecknahmepreis *zu Beginn des Kalenderjahres* of
    § 18 Abs. 1 Satz 2 InvStG, which open question Q12 resolved to the first
    price set *in* the year.

    One report cannot carry both. Asked for the first trading day, the snapshot
    is taken at that day's close and omits anything sold that morning: a real
    2024 run then failed with "Insufficient long lots" for a holding sold on
    2 January, because the opening ledger no longer contained it while the
    Trades file still carried the sale.

    The quantities win, because without them nothing computes at all. The
    price therefore comes from the preceding close, which is the reading that
    was *not* chosen — recorded as a deviation against GT-INVSTG-010 in
    docs/legal-implementation-map.md, to be closed by sourcing the Satz 2 price
    from a separate first-trading-day snapshot.
    """
    return weekday_on_or_before(date(year, 1, 1))


def positions_snapshot_dates(year: int) -> tuple[date, date]:
    """
    The dates to request for a year's start-of-year and end-of-year snapshots.

    Returns:
        (start_of_year_date, end_of_year_date)
    """
    return first_business_day_of_year(year), last_business_day_of_year(year)


def parse_years(specs: Iterable[str]) -> list[int]:
    """
    Read year arguments: "2021", "2021-2023", or several of either.

    Raises:
        ValueError: On an unparseable or inverted range. Collected across all
            arguments so one run names every bad value.
    """
    years: list[int] = []
    problems: list[str] = []

    for spec in specs:
        spec = spec.strip()
        try:
            if "-" in spec:
                start_text, _, end_text = spec.partition("-")
                start, end = int(start_text), int(end_text)
                if end < start:
                    problems.append(f"{spec!r}: range ends before it starts")
                    continue
                years.extend(range(start, end + 1))
            else:
                years.append(int(spec))
        except ValueError:
            problems.append(f"{spec!r}: not a year or a YYYY-YYYY range")

    if problems:
        raise ValueError("Bad --years argument(s): " + "; ".join(problems))

    return sorted(set(years))


def build_targets(years: Iterable[int], query_ids: dict[str, Optional[int]],
                  selected: Optional[Iterable[str]] = None) -> list[DownloadTarget]:
    """
    Expand years and configured queries into the files to download.

    Positions becomes two targets per year — the start-of-year and
    end-of-year snapshots the engine reconciles against — from one query ID,
    exactly as the manual procedure and src/flex_downloader.py do it.

    Raises:
        ValueError: If a selected query is unknown or has no configured ID.
            All such problems are collected and reported together.
    """
    keys = list(selected) if selected is not None else [
        key for key in FILENAME_PREFIXES if query_ids.get(key) is not None]

    problems = []
    for key in keys:
        if key not in FILENAME_PREFIXES:
            problems.append(
                f"unknown query {key!r} (known: {', '.join(sorted(FILENAME_PREFIXES))})")
        elif query_ids.get(key) is None:
            problems.append(
                f"query {key!r} has no ID in config.FLEX_QUERY_IDS")
    if problems:
        raise ValueError("Cannot build download list: " + "; ".join(problems))

    targets = []
    for year in sorted(set(years)):
        for key in keys:
            query_id = query_ids[key]
            prefix = FILENAME_PREFIXES[key]

            if key == "positions":
                soy_date, eoy_date = positions_snapshot_dates(year)
                targets.append(DownloadTarget(
                    key, query_id, soy_date, soy_date,
                    f"{prefix}-{year}-SoY.csv"))
                targets.append(DownloadTarget(
                    key, query_id, eoy_date, eoy_date,
                    f"{prefix}-{year}-EoY.csv"))
            else:
                targets.append(DownloadTarget(
                    key, query_id, date(year, 1, 1), date(year, 12, 31),
                    f"{prefix}-{year}.csv"))

    return targets


def resolve_query_ids_by_name(queries: Iterable[FlexQuery],
                              name_prefix: str) -> dict[str, int]:
    """
    Map the portal's own query names onto this engine's query keys.

    Only queries whose name starts with `name_prefix` are considered, so an
    account holding other Flex queries — for a different tool, a different
    year, a colleague's report — cannot be picked up by accident.

    Raises:
        ValueError: If two prefixed queries claim the same key. Guessing which
            "Trades" query was meant is exactly the kind of silent choice that
            produces a plausible wrong number.
    """
    resolved: dict[str, int] = {}
    claims: dict[str, list[str]] = {}

    for query in queries:
        remainder = strip_name_prefix(query.name, name_prefix)
        if normalise_query_name(query.name) == remainder:
            continue  # the prefix was not present; not one of ours
        key = QUERY_KEYS_BY_NAME.get(remainder)
        if key is None:
            logger.info("Ignoring query %r: no known report matches %r.",
                        query.name, remainder)
            continue
        claims.setdefault(key, []).append(query.name)
        resolved[key] = query.query_id

    ambiguous = {key: names for key, names in claims.items() if len(names) > 1}
    if ambiguous:
        raise ValueError(
            "More than one portal query matches the same report: "
            + "; ".join(f"{key} <- {', '.join(names)}"
                        for key, names in sorted(ambiguous.items()))
            + ". Rename one of them in the portal.")

    return resolved


def wait_for_login(client: PortalFlexClient, timeout_seconds: int = LOGIN_TIMEOUT_SECONDS,
                   poll_seconds: float = 3.0, sleep=time.sleep,
                   nudge=None, nudge_every: int = 8) -> None:
    """
    Block until the portal answers as a logged-in user.

    The test is whether the batch-statements API answers, not which page is on
    screen: that is the API this downloader depends on, and it is the only
    thing that has to be true before it starts.

    That API is not satisfied by cookies — it wants the headers the portal's
    own XHRs carry, which are read off a live request. So an already-logged-in
    session still has to make the app talk before this can return, and `nudge`
    is called periodically to reload the page and prompt exactly that.

    Raises:
        PortalError: If the login does not complete within the timeout.
    """
    deadline = time.monotonic() + timeout_seconds
    announced = False
    attempts = 0

    while True:
        if client.is_authenticated():
            print("Portal session is live.")
            return

        attempts += 1
        if not announced:
            print("Waiting for the portal...")
            announced = True

        elapsed = int(time.monotonic() - (deadline - timeout_seconds))
        reason = getattr(client, "last_probe_reason", "")
        print(f"    waiting {elapsed}s — {reason}")

        if time.monotonic() >= deadline:
            raise PortalError(
                f"Not logged in after {timeout_seconds}s. Nothing was "
                "downloaded."
                + ("" if client.has_am_headers else
                   " The portal never issued an AccountManagement request, so "
                   "its session headers could not be read — check that the "
                   "Flex Queries page actually loaded in the browser window."))

        if nudge is not None and attempts % nudge_every == 0:
            logger.info("Reloading the portal page to prompt a session request.")
            nudge()

        sleep(poll_seconds)


def write_report(csv_text: str, filename: str, import_dir: Path,
                 overwrite: bool = False) -> Optional[Path]:
    """
    Write one report into data_import/.

    Returns:
        The path written, or None if the file already existed and was kept.
    """
    import_dir.mkdir(parents=True, exist_ok=True)
    out = import_dir / filename

    if out.exists() and not overwrite:
        print(f"  kept existing {out.name} (use --overwrite to replace)")
        return None

    out.write_text(csv_text, encoding="utf-8-sig")
    print(f"  -> {out} ({len(csv_text)} bytes)")
    return out


def download_targets(client: PortalFlexClient, targets: list[DownloadTarget],
                     import_dir: Path = IMPORT_DIR, overwrite: bool = False,
                     poll_seconds: float = 10.0,
                     timeout_seconds: float = 900.0,
                     sleep=time.sleep) -> tuple[list[Path], list[str]]:
    """
    Run every target, collecting failures rather than stopping at the first.

    One run should tell you everything that is wrong with the request, not the
    first thing.

    Returns:
        (paths written, failure descriptions)
    """
    written: list[Path] = []
    failures: list[str] = []
    empty: list[str] = []

    for index, target in enumerate(targets, start=1):
        out = import_dir / target.filename
        if out.exists() and not overwrite:
            print(f"[{index}/{len(targets)}] {target.label}: "
                  f"{target.filename} already present, skipping")
            continue

        print(f"[{index}/{len(targets)}] {target.label} -> {target.filename}")
        try:
            csv_text = client.run_and_collect(
                target.query_id, target.from_date, target.to_date,
                poll_seconds=poll_seconds, timeout_seconds=timeout_seconds,
                progress=print, sleep=sleep)
        except NoStatementAvailableError as e:
            # An answer, not a fault: there is nothing to report for that date.
            # Written down rather than passed over, because "no data" for a
            # year you traded in would matter.
            print(f"  no data: {e}")
            empty.append(f"{target.label} ({target.filename})")
            continue
        except NotAuthenticatedError as e:
            # Every remaining target would fail the same way against a dead
            # session, and each attempt is another minute of waiting for an
            # answer that cannot come.
            print(f"  FAILED: {e}")
            failures.append(f"{target.label} ({target.filename}): {e}")
            not_attempted = targets[index:]
            if not_attempted:
                print(f"  Stopping: {len(not_attempted)} further report(s) "
                      "not attempted because the session is gone.")
                failures.extend(
                    f"{other.label} ({other.filename}): not attempted — "
                    "session lost earlier in the run"
                    for other in not_attempted)
            break
        except PortalError as e:
            print(f"  FAILED: {e}")
            failures.append(f"{target.label} ({target.filename}): {e}")
            continue

        path = write_report(csv_text, target.filename, import_dir, overwrite)
        if path is not None:
            written.append(path)

    return written, failures, empty


def run(years: list[int], selected: Optional[list[str]], portal_url: str,
        profile_dir: Path, channel: Optional[str], import_dir: Path,
        overwrite: bool, poll_seconds: float, timeout_seconds: float,
        name_prefix: Optional[str] = None, record: bool = False) -> int:
    """Open a session, download everything requested, and report. Returns exit code."""
    require_playwright()

    # Checked before a browser opens: a typo in --queries should not cost a login.
    unknown = [key for key in (selected or []) if key not in FILENAME_PREFIXES]
    if unknown:
        raise ValueError(
            f"Unknown quer{'y' if len(unknown) == 1 else 'ies'} "
            f"{', '.join(repr(key) for key in unknown)}. "
            f"Known: {', '.join(sorted(FILENAME_PREFIXES))}")

    recorder = None
    with portal_session(profile_dir=profile_dir, headless=False,
                        channel=channel) as (_, context):
        # Attached before the first navigation: the Flex Queries page issues
        # the request whose headers we need while it is still loading.
        harvester = AmHeaderHarvester()
        harvester.attach(context)

        if record:
            from datetime import datetime

            from src.web_portal.recorder import PortalRecorder
            out_dir = Path("private/portal_discovery") / (
                datetime.now().strftime("%Y%m%d-%H%M%S") + "-download")
            recorder = PortalRecorder(out_dir)
            recorder.attach(context)
            recorder.marker("run-start")
            print(f"Recording this run to {out_dir}/")

        open_portal(context, portal_url)

        def live_page():
            """Whichever page is currently open; login can replace it."""
            for candidate in reversed(context.pages):
                if not candidate.is_closed():
                    return candidate
            return None

        # Through the page, not the driver: see PageRequestTransport.
        client = PortalFlexClient(PageRequestTransport(live_page),
                                  base_url=BASE_URL,
                                  headers_provider=harvester.get)

        # No nudge. Reloading the page used to be how a session request was
        # prompted, but the page it reloaded was AmAuthentication — an SSO
        # entry point — and re-entering it just after a login appears to end
        # the session that login established. The only flow that has ever
        # worked end to end navigates once and then leaves the browser alone.
        print("\nIn the browser: log in, then open "
              "Performance & Reports > Flex Queries.")

        def pump(seconds: float) -> None:
            """
            Wait, and let Playwright deliver the events queued in the meantime.

            Playwright's sync API dispatches browser events only when the
            program calls into it. While no headers have been captured the
            authentication probe returns early without touching the browser,
            so a plain time.sleep here starves the very listener that would
            capture them: no events, no headers, no request, no events. The
            run sat forever on a fully loaded Flex Queries page, and the
            recording froze at 43 events because it was starved too.
            """
            page = live_page()
            if page is None:
                time.sleep(seconds)
                return
            try:
                page.wait_for_timeout(seconds * 1000)
            except Exception:  # pragma: no cover - page can close mid-wait
                time.sleep(seconds)

        wait_for_login(client, sleep=pump)

        if name_prefix:
            print(f"Resolving queries named {name_prefix!r}* from the portal...")
            query_ids = resolve_query_ids_by_name(client.list_flex_queries(),
                                                  name_prefix)
            for key, query_id in sorted(query_ids.items()):
                print(f"  {key}: query {query_id}")
            if not query_ids:
                raise PortalError(
                    f"No portal query starts with {name_prefix!r}. Nothing to do.")
        else:
            query_ids = config.FLEX_QUERY_IDS

        targets = build_targets(years, query_ids, selected)
        if not targets:
            print("Nothing to download: no query IDs configured. Set "
                  "FLEX_QUERY_IDS in src/config.py, or use --query-name-prefix.")
            return 1

        print(f"\n{len(targets)} report(s) to fetch into {import_dir}/:")
        for target in targets:
            print(f"  {target.filename}")
        print()

        if recorder is not None:
            recorder.marker("logged-in; starting downloads")

        try:
            written, failures, empty = download_targets(
                client, targets, import_dir, overwrite, poll_seconds,
                timeout_seconds, sleep=pump)
        finally:
            if recorder is not None:
                recorder.marker("run-end")

    # Only now that the browser is closed: while it is open it keeps emitting
    # events, and writing them to a closed recording raises inside Playwright's
    # dispatch — a stack trace at the end of a run that otherwise succeeded.
    if recorder is not None:
        recorder.close()
        print(f"Recording written to {recorder.write_summary()}")

    print()
    print(f"Wrote {len(written)} file(s) to {import_dir}/.")
    if empty:
        print(f"{len(empty)} report(s) had no data at the portal — nothing "
              "was written for them:")
        for item in empty:
            print(f"  - {item}")
        print("  For a start-of-year snapshot in your first year of trading "
              "this is expected; the engine allows a missing SoY file.")
    if failures:
        print(f"{len(failures)} report(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download IBKR Flex Query reports through the Client Portal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument("--years", nargs="+", required=True, metavar="YYYY",
                        help="Years to download: 2021, or a range 2021-2023")
    parser.add_argument("--queries", nargs="+", default=None, metavar="NAME",
                        help="Which queries to run (default: every one with an "
                             f"ID in config.FLEX_QUERY_IDS). Known: "
                             f"{', '.join(sorted(FILENAME_PREFIXES))}")
    parser.add_argument("--query-name-prefix", default=None,
                        help="Resolve query IDs from the portal by name instead "
                             "of config.FLEX_QUERY_IDS: only queries whose name "
                             "starts with this are used (default: "
                             "config.FLEX_QUERY_NAME_PREFIX)")
    parser.add_argument("--record", action="store_true",
                        help="Record this run to private/portal_discovery/ "
                             "(redacted), the same way discover.py does, so a "
                             "failure leaves evidence instead of a guess.")
    parser.add_argument("--reset-profile", action="store_true",
                        help="Delete the saved browser profile first and log in "
                             "fresh. Use this if the portal keeps answering "
                             "\"Your Session Has Expired\".")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace files that already exist in data_import/")
    parser.add_argument("--import-dir", type=Path, default=IMPORT_DIR,
                        help=f"Where to write (default: {IMPORT_DIR})")
    parser.add_argument("--portal-url", default=DEFAULT_PORTAL_URL,
                        help=f"Page to open (default: {DEFAULT_PORTAL_URL}). The "
                             "Flex Queries deep link is deliberately not used: "
                             "it is an SSO entry point and navigating to it "
                             "around a login has been seen to end the session.")
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--channel", default="chrome",
                        help="Browser channel, or 'chromium' for the bundled build")
    parser.add_argument("--username", default=None,
                        help="Portal username, remembered in private/portal_username. "
                             "The password is never stored.")
    parser.add_argument("--poll-seconds", type=float, default=10.0,
                        help="How often to check the portal's batch list")
    parser.add_argument("--timeout-seconds", type=float, default=900.0,
                        help="How long to wait for one report before moving on. A report that outlives this keeps generating in the portal; re-running collects it from the batch list without regenerating it.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")

    if args.reset_profile:
        if reset_profile(args.profile_dir):
            print(f"Removed browser profile {args.profile_dir}. "
                  "You will need to log in again.")
        else:
            print(f"No browser profile at {args.profile_dir}.")

    if args.username:
        save_username(args.username)
    if load_username():
        print("Portal username on file. Password: never stored.")

    try:
        years = parse_years(args.years)
    except ValueError as e:
        parser.error(str(e))

    channel = None if args.channel.lower() == "chromium" else args.channel

    name_prefix = args.query_name_prefix or config.FLEX_QUERY_NAME_PREFIX

    try:
        return run(years, args.queries, args.portal_url, args.profile_dir,
                   channel, args.import_dir, args.overwrite,
                   args.poll_seconds, args.timeout_seconds, name_prefix,
                   args.record)
    except KeyboardInterrupt:
        print("\nInterrupted. Files already written are kept; reports still "
              "generating in the portal are collected on the next run.",
              file=sys.stderr)
        return 130
    except (PortalError, ValueError, RuntimeError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

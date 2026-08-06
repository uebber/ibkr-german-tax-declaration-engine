"""
Download Flex Query reports for any year from the IBKR Client Portal.

The Flex Web Service API (src/flex_downloader.py) only serves about the last
two calendar years; everything older has to come from the portal, which the
README documents as a manual procedure. This runs that procedure.

    uv run --extra web python -m src.web_portal.download --years 2021-2023

A browser opens; log in yourself, including two-factor. Your password is never
asked for, stored or recorded. Once the portal answers as a logged-in user, the
downloader asks for every configured query over every requested year, then
collects the reports as the portal finishes them, writing each into
data_import/ under the naming scheme the engine expects as soon as it arrives.

Reports are requested in parallel — several at a time, topped up as each one
lands — rather than one at a time, because the portal queues batch jobs
concurrently and ends a session after about fifteen minutes regardless of what
the downloader is doing.

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
    ACTIVITY_INTERVAL_SECONDS,
    DEFAULT_PORTAL_URL,
    DEFAULT_PROFILE_DIR,
    nudge_activity,
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
    MAX_REPORTS_IN_FLIGHT,
    PortalFlexClient,
    ReportRequest,
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
    # The name this query has in the portal, when it is known. Needed to
    # identify a batch entry the portal lists without a query ID — see
    # flex_portal.batch_entry_matches. None when query IDs came from config
    # and the portal was never asked for its names.
    query_name: Optional[str] = None

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
    The first trading day of a calendar year.

    This is the day the start-of-year snapshot is requested for. That file is
    now only a price source — the Ruecknahmepreis *zu Beginn des Kalenderjahres*
    of § 18 Abs. 1 Satz 2 InvStG, resolved by open question Q12 to the first
    price set *in* the year. Its unit count is not used: the Vorabpauschale
    takes that from the 31 December snapshot (Rz. 18.4), and the ledger takes
    its opening position from the preceding year end.

    That separation is what makes this date safe. While the same file also
    seeded the opening ledger, dating it here broke a run outright — a snapshot
    is taken at the close of the day it names, so a holding sold that morning
    was missing from it while the Trades file still carried the sale.

    1 January is closed on every exchange IBKR serves whatever weekday it falls
    on — 1 January 2021 was a Friday — and when it falls on a Sunday the
    exchanges observe it on Monday 2 January. Corroborated: the 2021 cash report
    carries FromDate 20210104, and this returns 4 January 2021.
    """
    new_year = date(year, 1, 1)
    closed = {new_year}
    if new_year.weekday() == 6:          # Sunday -> observed on the Monday
        closed.add(date(year, 1, 2))

    day = new_year
    while day.weekday() >= 5 or day in closed:
        day += timedelta(days=1)
    return day


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
                  selected: Optional[Iterable[str]] = None,
                  query_names: Optional[dict[str, str]] = None
                  ) -> list[DownloadTarget]:
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

            name = (query_names or {}).get(key)

            if key == "positions":
                soy_date, eoy_date = positions_snapshot_dates(year)
                targets.append(DownloadTarget(
                    key, query_id, soy_date, soy_date,
                    f"{prefix}-{year}-SoY.csv", name))
                targets.append(DownloadTarget(
                    key, query_id, eoy_date, eoy_date,
                    f"{prefix}-{year}-EoY.csv", name))
            else:
                targets.append(DownloadTarget(
                    key, query_id, date(year, 1, 1), date(year, 12, 31),
                    f"{prefix}-{year}.csv", name))

    return targets


def resolve_query_ids_by_name(queries: Iterable[FlexQuery],
                              name_prefix: str) -> dict[str, int]:
    """Query key -> portal query ID. See resolve_queries_by_name."""
    return {key: query.query_id
            for key, query in resolve_queries_by_name(queries, name_prefix).items()}


def resolve_queries_by_name(queries: Iterable[FlexQuery],
                            name_prefix: str) -> dict[str, FlexQuery]:
    """
    Map the portal's own query names onto this engine's query keys.

    Returns the whole FlexQuery, not just the ID, because the name is needed
    again later: the portal lists some reports in the batch list with no query
    ID at all, and the name in the summary is then the only way to tell which
    report it is (see flex_portal.batch_entry_matches).

    Only queries whose name starts with `name_prefix` are considered, so an
    account holding other Flex queries — for a different tool, a different
    year, a colleague's report — cannot be picked up by accident.

    Raises:
        ValueError: If two prefixed queries claim the same key. Guessing which
            "Trades" query was meant is exactly the kind of silent choice that
            produces a plausible wrong number.
    """
    resolved: dict[str, FlexQuery] = {}
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
        resolved[key] = query

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
            # has_am_headers now means "a *complete* set", so a false answer
            # no longer implies the portal stayed silent: it may have issued
            # several requests and carried the account scope on none of them.
            # The probe reason distinguishes the two; the sentence here has to
            # be true of both.
            raise PortalError(
                f"Not logged in after {timeout_seconds}s. Nothing was "
                "downloaded."
                + (f" Last reason: {reason}." if reason else "")
                + ("" if client.has_am_headers else
                   " The portal never issued an AccountManagement request "
                   "carrying a complete set of session headers, so they could "
                   "not be read — check that the Flex Queries page actually "
                   "loaded in the browser window."))

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
                     max_in_flight: int = MAX_REPORTS_IN_FLIGHT,
                     sleep=time.sleep) -> tuple[list[Path], list[str], list[str]]:
    """
    Ask the portal for every target, then write each report as it arrives.

    Several targets are in flight at once, topped up as reports land, rather
    than one at a time. The portal queues batch jobs in parallel and reports
    on all of them in one list, so waiting for each in turn only spends the
    session — and the session is the scarce thing, since the portal ends it
    after about fifteen minutes regardless. See
    PortalFlexClient.run_and_collect_many.

    Each report is written the moment it is collected rather than at the end,
    so a session lost half way through still leaves everything that had
    already been fetched on disk.

    Failures are collected rather than stopping the run: one run should tell
    you everything that is wrong with the request, not the first thing.

    Returns:
        (paths written, failure descriptions, reports the portal had no data
        for)
    """
    written: list[Path] = []
    failures: list[str] = []
    empty: list[str] = []

    wanted: list[DownloadTarget] = []
    for target in targets:
        if (import_dir / target.filename).exists() and not overwrite:
            print(f"{target.label}: {target.filename} already present, skipping")
        else:
            wanted.append(target)

    if not wanted:
        return written, failures, empty

    by_key = {target.filename: target for target in wanted}
    requests = [
        ReportRequest(key=target.filename, query_id=target.query_id,
                      from_date=target.from_date, to_date=target.to_date,
                      query_name=target.query_name, label=target.label)
        for target in wanted]

    print(f"Requesting {len(requests)} report(s) from the portal, "
          f"up to {max_in_flight} at a time...")
    done = 0
    for outcome in client.run_and_collect_many(
            requests, poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds, max_in_flight=max_in_flight,
            progress=print, sleep=sleep):
        target = by_key[outcome.request.key]
        done += 1
        prefix = f"[{done}/{len(requests)}] {target.label}"

        if outcome.ok:
            print(f"{prefix} -> {target.filename}")
            path = write_report(outcome.csv, target.filename, import_dir,
                                overwrite)
            if path is not None:
                written.append(path)
        elif isinstance(outcome.error, NoStatementAvailableError):
            # An answer, not a fault: there is nothing to report for that date.
            # Written down rather than passed over, because "no data" for a
            # year you traded in would matter.
            print(f"{prefix}: no data: {outcome.error}")
            empty.append(f"{target.label} ({target.filename})")
        else:
            print(f"{prefix}: FAILED: {outcome.error}")
            failures.append(f"{target.label} ({target.filename}): "
                            f"{outcome.error}")

    return written, failures, empty


def run(years: list[int], selected: Optional[list[str]], portal_url: str,
        profile_dir: Path, channel: Optional[str], import_dir: Path,
        overwrite: bool, poll_seconds: float, timeout_seconds: float,
        name_prefix: Optional[str] = None, record: bool = False,
        max_in_flight: int = MAX_REPORTS_IN_FLIGHT) -> int:
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

        last_nudge = [time.monotonic()]

        def pump(seconds: float) -> None:
            """
            Wait; deliver queued browser events; keep the session alive.

            Playwright's sync API dispatches browser events only when the
            program calls into it. While no headers have been captured the
            authentication probe returns early without touching the browser,
            so a plain time.sleep here starves the very listener that would
            capture them: no events, no headers, no request, no events. The
            run sat forever on a fully loaded Flex Queries page, and the
            recording froze at 43 events because it was starved too.

            Every wait in a run passes through here, which makes it the one
            place that knows the program is idle — and the portal logs itself
            out after about fifteen minutes with no *user* activity, however
            much traffic the downloader generates. So this is also where the
            pointer gets moved. See browser.nudge_activity for the measurement.
            """
            page = live_page()
            if page is None:
                time.sleep(seconds)
                return

            now = time.monotonic()
            if now - last_nudge[0] >= ACTIVITY_INTERVAL_SECONDS:
                last_nudge[0] = now
                nudge_activity(page)

            try:
                page.wait_for_timeout(seconds * 1000)
            except Exception:  # pragma: no cover - page can close mid-wait
                time.sleep(seconds)

        wait_for_login(client, sleep=pump)

        query_names: dict[str, str] = {}
        if name_prefix:
            print(f"Resolving queries named {name_prefix!r}* from the portal...")
            resolved = resolve_queries_by_name(client.list_flex_queries(),
                                               name_prefix)
            query_ids = {key: query.query_id for key, query in resolved.items()}
            query_names = {key: query.name for key, query in resolved.items()}
            for key, query_id in sorted(query_ids.items()):
                print(f"  {key}: query {query_id}")
            if not query_ids:
                raise PortalError(
                    f"No portal query starts with {name_prefix!r}. Nothing to do.")
        else:
            query_ids = config.FLEX_QUERY_IDS
            # Ask the portal what these queries are called, even though the
            # IDs came from config. Some reports are listed in the batch list
            # with no query ID, and then the name is the only handle on them.
            # Not fatal if it fails: everything identified by ID still works,
            # and an unattributable entry reports itself at the timeout.
            try:
                query_names = {
                    key: query.name
                    for query in client.list_flex_queries()
                    for key, configured in query_ids.items()
                    if configured == query.query_id}
            except PortalError as e:
                logger.warning(
                    "Could not read the portal's query names (%s). A report "
                    "the portal lists without a query ID cannot be matched.", e)

        targets = build_targets(years, query_ids, selected, query_names)
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
                timeout_seconds, max_in_flight, sleep=pump)
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
                        help="How long to wait for any one report, measured from when it was queued. Reports are waited for concurrently, so this is not a budget for the whole run. A report that outlives it keeps generating in the portal; re-running collects it from the batch list without regenerating it.")
    parser.add_argument("--max-in-flight", type=int,
                        default=MAX_REPORTS_IN_FLIGHT,
                        help="How many reports to keep queued at the portal at "
                             f"once (default {MAX_REPORTS_IN_FLIGHT}). Reports "
                             "the portal answers immediately do not count "
                             "against it.")
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
        if args.max_in_flight < 1:
            parser.error("--max-in-flight must be at least 1")

        return run(years, args.queries, args.portal_url, args.profile_dir,
                   channel, args.import_dir, args.overwrite,
                   args.poll_seconds, args.timeout_seconds, name_prefix,
                   args.record, args.max_in_flight)
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

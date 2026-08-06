"""
What the portal downloader decides to fetch, and what it calls the result.

legal_basis: infrastructure. The engine reads whatever is in data_import/ and
believes it. A downloader that writes a start-of-year snapshot under the
end-of-year name, or a 2021 report as Trades-2022.csv, produces figures that
are wrong and look fine — the reconciliation invariant cannot see it, because
the snapshot it reconciles against would be the wrong one too.

The filename agreement with src/data_preparation.py is asserted against that
module's own lookup, not against a copy of the naming scheme: two independent
spellings of the same convention drift.
"""
from datetime import date
from pathlib import Path

import pytest

from src.web_portal.download import (
    FILENAME_PREFIXES,
    QUERY_KEYS_BY_NAME,
    DownloadTarget,
    build_targets,
    download_targets,
    first_business_day_of_year,
    last_business_day_of_year,
    parse_years,
    resolve_query_ids_by_name,
    wait_for_login,
    write_report,
)
from src.web_portal.browser import DEFAULT_PORTAL_URL
from src.web_portal.flex_portal import (
    FLEX_QUERIES_URL,
    FlexQuery,
    NoStatementAvailableError,
    PortalError,
)

ALL_IDS = {
    "trades": 1212943,
    "cash_transactions": 1212969,
    "positions": 1212973,
    "corporate_actions": 1213973,
    "cash_balance": 1372852,
    "options_eae": 1427928,
}

CSV = '"ClientAccountID","Symbol"\n"U1234567","SAP"\n'


class TestParseYears:
    def test_single_years(self):
        assert parse_years(["2021", "2023"]) == [2021, 2023]

    def test_a_range_is_inclusive_of_both_ends(self):
        assert parse_years(["2021-2023"]) == [2021, 2022, 2023]

    def test_ranges_and_years_combine_and_deduplicate(self):
        assert parse_years(["2021-2023", "2023", "2025"]) == [2021, 2022, 2023, 2025]

    def test_every_bad_argument_is_named_at_once(self):
        """One run should say everything that is wrong with the request."""
        with pytest.raises(ValueError) as excinfo:
            parse_years(["2021", "twentytwo", "2025-2023"])

        message = str(excinfo.value)
        assert "twentytwo" in message
        assert "2025-2023" in message
        assert "ends before it starts" in message


class TestBuildTargets:
    def test_a_transaction_query_covers_the_whole_calendar_year(self):
        targets = build_targets([2021], ALL_IDS, ["trades"])

        assert len(targets) == 1
        assert targets[0].from_date == date(2021, 1, 1)
        assert targets[0].to_date == date(2021, 12, 31)
        assert targets[0].filename == "Trades-2021.csv"

    def test_positions_becomes_two_single_day_snapshots(self):
        """
        The engine reconciles against these two, and takes the start-of-year
        quantity straight from the SoY file. A range query would return a
        period report instead of a snapshot.
        """
        targets = build_targets([2021], ALL_IDS, ["positions"])

        assert len(targets) == 2
        soy, eoy = targets

        assert soy.filename == "Positions-2021-SoY.csv"
        assert soy.from_date == soy.to_date

        assert eoy.filename == "Positions-2021-EoY.csv"
        assert eoy.from_date == eoy.to_date

        # Both come from one configured query, as in the manual procedure.
        assert soy.query_id == eoy.query_id == ALL_IDS["positions"]

    def test_every_snapshot_date_is_a_weekday(self):
        """
        The portal's date picker accepts weekdays and refuses weekends. It does
        not mind a market holiday: 1 January 2025 was a Wednesday, was accepted,
        and returned a report.
        """
        for year in range(2018, 2031):
            soy, eoy = build_targets([year], ALL_IDS, ["positions"])
            assert soy.from_date.weekday() < 5, f"{year} SoY: {soy.from_date}"
            assert eoy.from_date.weekday() < 5, f"{year} EoY: {eoy.from_date}"

    @pytest.mark.parametrize("year,expected", [
        (2020, date(2020, 1, 2)),   # 1 Jan Wed, closed -> Thursday
        (2021, date(2021, 1, 4)),   # 1 Jan Fri, closed; weekend -> Monday
        (2022, date(2022, 1, 3)),   # 1 Jan Saturday -> Monday
        (2023, date(2023, 1, 3)),   # 1 Jan Sunday, observed Mon 2nd -> Tuesday
        (2024, date(2024, 1, 2)),   # 1 Jan Mon, closed -> Tuesday
        (2025, date(2025, 1, 2)),   # 1 Jan Wed, closed -> Thursday
    ])
    def test_the_start_of_year_is_the_first_trading_day(self, year, expected):
        """
        § 18 Abs. 1 Satz 2 InvStG's *Ruecknahmepreis zu Beginn des
        Kalenderjahres* is the first price set **in** the year — open question
        Q12, resolved against GT-INVSTG-010. So the snapshot must be requested
        for a day on which a price was actually set.

        1 January will not do, and not only because of weekends: it is closed
        on every exchange whatever weekday it falls on, and a request for it
        returns the preceding 31 December close, which is the reading that was
        not chosen. 2021 is the case that catches a weekday-only rule — 1
        January 2021 was a Friday.
        """
        assert first_business_day_of_year(year) == expected
        soy, _ = build_targets([year], ALL_IDS, ["positions"])
        assert soy.from_date == expected

    def test_a_start_of_year_snapshot_is_never_requested_for_1_january(self):
        """
        The single assertion that separates the two readings: asking for
        1 January is asking for the previous year's close.
        """
        for year in range(2018, 2031):
            soy, _ = build_targets([year], ALL_IDS, ["positions"])
            assert soy.from_date != date(year, 1, 1), year
            assert soy.from_date.year == year, year

    @pytest.mark.parametrize("year,expected", [
        (2021, date(2021, 12, 31)),   # Friday
        (2022, date(2022, 12, 30)),   # 31st is a Saturday
        (2023, date(2023, 12, 29)),   # 31st is a Sunday
        (2024, date(2024, 12, 31)),   # Tuesday
    ])
    def test_year_end_rolls_back_off_the_weekend(self, year, expected):
        assert last_business_day_of_year(year) == expected
        _, eoy = build_targets([year], ALL_IDS, ["positions"])
        assert eoy.to_date == expected

    def test_every_configured_query_is_included_by_default(self):
        targets = build_targets([2021], ALL_IDS)
        filenames = {target.filename for target in targets}

        assert filenames == {
            "Trades-2021.csv", "Cash_Transactions-2021.csv",
            "Corporate_Actions-2021.csv", "Cash_Balance-2021.csv",
            "Options_EAE-2021.csv",
            "Positions-2021-SoY.csv", "Positions-2021-EoY.csv",
        }

    def test_unconfigured_queries_are_skipped_not_guessed(self):
        partial = dict(ALL_IDS, options_eae=None, cash_balance=None)
        filenames = {t.filename for t in build_targets([2021], partial)}

        assert "Options_EAE-2021.csv" not in filenames
        assert "Trades-2021.csv" in filenames

    def test_asking_for_an_unconfigured_query_explicitly_is_an_error(self):
        """Silently skipping a query the user named would leave a gap."""
        partial = dict(ALL_IDS, options_eae=None)

        with pytest.raises(ValueError, match="options_eae"):
            build_targets([2021], partial, ["options_eae"])

    def test_an_unknown_query_name_is_an_error_that_lists_the_known_ones(self):
        with pytest.raises(ValueError) as excinfo:
            build_targets([2021], ALL_IDS, ["trade"])

        assert "trade" in str(excinfo.value)
        assert "corporate_actions" in str(excinfo.value)

    def test_multiple_years_expand_in_order(self):
        targets = build_targets([2023, 2021], ALL_IDS, ["trades"])
        assert [t.filename for t in targets] == ["Trades-2021.csv", "Trades-2023.csv"]


class TestFilenameAgreementWithDataPreparation:
    """
    The consumer's own lookup must find what the downloader writes.

    src/data_preparation.py spells the naming scheme independently. This drives
    that module's real lookup functions over files named by the downloader.
    """

    def test_data_preparation_finds_every_file_the_downloader_writes(self, tmp_path,
                                                                     monkeypatch):
        from src import data_preparation

        monkeypatch.setattr(data_preparation, "IMPORT_DIR", tmp_path)

        for target in build_targets([2021], ALL_IDS):
            (tmp_path / target.filename).write_text(CSV, encoding="utf-8-sig")

        for prefix in ("Trades", "Cash_Transactions", "Corporate_Actions",
                       "Options_EAE", "Cash_Balance"):
            assert data_preparation._find_import_file(prefix, 2021) is not None, prefix
            assert data_preparation._find_years_available(prefix) == [2021], prefix

        assert data_preparation._find_import_file("Positions", 2021, "-SoY.csv")
        assert data_preparation._find_import_file("Positions", 2021, "-EoY.csv")


class TestResolveQueryIdsByName:
    PREFIX = "MyTax"

    def test_resolves_the_six_reports_by_their_portal_names(self):
        queries = [
            FlexQuery(1212943, "MyTax Trades"),
            FlexQuery(1212969, "MyTax Cash Transactions"),
            FlexQuery(1213973, "MyTax Corporate Actions"),
            FlexQuery(1212973, "MyTax Positions"),
            FlexQuery(1372852, "MyTax Cash Balance"),
            FlexQuery(1427928, "MyTax Options EAE"),
        ]

        assert resolve_query_ids_by_name(queries, self.PREFIX) == ALL_IDS

    def test_underscores_and_case_do_not_matter(self):
        """The portal shows "MyTax Trades"; people type "MyTax_Trades"."""
        queries = [FlexQuery(1, "MyTax_Trades"), FlexQuery(2, "MYTAX cash-balance")]

        assert resolve_query_ids_by_name(queries, "mytax") == {
            "trades": 1, "cash_balance": 2}

    def test_queries_without_the_prefix_are_left_alone(self):
        """Another tool's queries live in the same account."""
        queries = [FlexQuery(1, "MyTax Trades"),
                   FlexQuery(2, "Trades"),
                   FlexQuery(3, "Steuer Positions")]

        assert resolve_query_ids_by_name(queries, "MyTax") == {"trades": 1}

    def test_a_prefixed_query_with_no_matching_report_is_ignored(self):
        queries = [FlexQuery(1, "MyTax Trades"),
                   FlexQuery(2, "MyTax Something Experimental")]

        assert resolve_query_ids_by_name(queries, "MyTax") == {"trades": 1}

    def test_two_queries_claiming_the_same_report_is_an_error(self):
        """Picking one would silently decide which figures get computed."""
        queries = [FlexQuery(1, "MyTax Trades"), FlexQuery(2, "MyTax_Trades")]

        with pytest.raises(ValueError) as excinfo:
            resolve_query_ids_by_name(queries, "MyTax")

        assert "trades" in str(excinfo.value)
        assert "Rename" in str(excinfo.value)

    def test_every_known_name_maps_to_a_real_query_key(self):
        assert set(QUERY_KEYS_BY_NAME.values()) <= set(FILENAME_PREFIXES)


class TestWriteReport:
    def test_writes_with_the_byte_order_mark_the_parsers_expect(self, tmp_path):
        path = write_report(CSV, "Trades-2021.csv", tmp_path)

        assert path == tmp_path / "Trades-2021.csv"
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")
        assert path.read_text(encoding="utf-8-sig") == CSV

    def test_an_existing_file_is_kept_not_replaced(self, tmp_path):
        (tmp_path / "Trades-2021.csv").write_text("original", encoding="utf-8-sig")

        assert write_report(CSV, "Trades-2021.csv", tmp_path) is None
        assert (tmp_path / "Trades-2021.csv").read_text(
            encoding="utf-8-sig") == "original"

    def test_overwrite_replaces_it(self, tmp_path):
        (tmp_path / "Trades-2021.csv").write_text("original", encoding="utf-8-sig")

        assert write_report(CSV, "Trades-2021.csv", tmp_path, overwrite=True)
        assert (tmp_path / "Trades-2021.csv").read_text(encoding="utf-8-sig") == CSV


class StubClient:
    """A client that succeeds, or fails, per target."""

    def __init__(self, failures=(), report=CSV):
        self.failures = set(failures)
        self.report = report
        self.calls = []

    def run_and_collect(self, query_id, from_date, to_date, **kwargs):
        self.calls.append((query_id, from_date, to_date))
        if query_id in self.failures:
            raise PortalError(f"query {query_id} failed")
        return self.report


class TestDownloadTargets:
    def test_a_failure_does_not_stop_the_remaining_downloads(self, tmp_path):
        """
        One run should report everything that went wrong, not the first thing.
        Stopping early would also mean a re-run repeats the reports that
        already succeeded — each of which costs a portal batch job.
        """
        targets = build_targets([2021], ALL_IDS, ["trades", "cash_transactions",
                                                  "corporate_actions"])
        client = StubClient(failures={ALL_IDS["cash_transactions"]})

        written, failures, empty = download_targets(client, targets, tmp_path)

        assert empty == []
        assert {p.name for p in written} == {"Trades-2021.csv",
                                             "Corporate_Actions-2021.csv"}
        assert len(failures) == 1
        assert "Cash_Transactions-2021.csv" in failures[0]

    def test_existing_files_are_not_re_downloaded(self, tmp_path):
        (tmp_path / "Trades-2021.csv").write_text("already here", encoding="utf-8-sig")
        targets = build_targets([2021], ALL_IDS, ["trades"])
        client = StubClient()

        written, failures, empty = download_targets(client, targets, tmp_path)

        assert client.calls == []      # no portal batch job was started
        assert written == [] and failures == [] and empty == []


class StubLoginClient:
    """Answers after `succeed_after` probes."""

    def __init__(self, succeed_after=1, has_headers=True):
        self.probes = 0
        self.succeed_after = succeed_after
        self.has_am_headers = has_headers

    def is_authenticated(self):
        self.probes += 1
        return self.probes >= self.succeed_after


def test_the_downloader_does_not_enter_the_sso_deep_link():
    """
    AmAuthentication is an SSO entry point. The downloader used to open it and
    then re-open it periodically while waiting for a login, and the session
    ended moments after logging in — repeatedly, while the flow that opens the
    plain portal page and then leaves the browser alone has never once failed.
    """
    assert "AmAuthentication" in FLEX_QUERIES_URL       # it is the deep link
    assert "AmAuthentication" not in DEFAULT_PORTAL_URL  # and not the default


def test_waiting_for_login_makes_no_request_before_the_headers_are_current():
    """
    Nothing may be sent while the capture is stale, which is the state right
    after a login. The probe has to decline rather than replay the previous
    session's token.
    """
    class StaleHeaderClient:
        has_am_headers = False

        def __init__(self):
            self.probes = 0

        def is_authenticated(self):
            self.probes += 1
            return False

    client = StaleHeaderClient()
    with pytest.raises(PortalError):
        wait_for_login(client, timeout_seconds=0, sleep=lambda _: None)

    # It still asks the client, but the client refuses to send: see
    # PortalFlexClient.is_authenticated and AmHeaderHarvester.get.
    assert client.probes >= 1


class TestNoDataIsNotAFailure:
    def test_a_report_with_no_data_is_reported_separately(self, tmp_path):
        """
        "There is no statement available for the account(s) and date(s)
        selected" is a legitimate answer — on 1 January of a first trading
        year nothing was held. It must not be counted as a failure, must not
        write a file, and must not be passed over in silence either.
        """
        class NoDataClient:
            def run_and_collect(self, query_id, from_date, to_date, **kwargs):
                raise NoStatementAvailableError(
                    "No statement for query 1 over 2021-01-01..2021-01-01")

        targets = build_targets([2021], ALL_IDS, ["positions"])
        written, failures, empty = download_targets(
            NoDataClient(), targets, tmp_path)

        assert written == []
        assert failures == []
        assert len(empty) == 2
        assert "Positions-2021-SoY.csv" in empty[0]
        assert list(tmp_path.iterdir()) == []       # no empty file written


class TestWaitForLogin:
    def test_returns_as_soon_as_the_portal_answers(self):
        client = StubLoginClient(succeed_after=3)
        slept = []

        wait_for_login(client, poll_seconds=2, sleep=slept.append)

        assert client.probes == 3
        assert slept == [2, 2]

    def test_gives_up_rather_than_waiting_forever(self):
        client = StubLoginClient(succeed_after=10**9)

        with pytest.raises(PortalError, match="Nothing was"):
            wait_for_login(client, timeout_seconds=0, sleep=lambda _: None)

    def test_the_page_is_reloaded_periodically_to_prompt_a_session_request(self):
        """
        An already-logged-in session sits there doing nothing, and the headers
        this downloader needs are only readable off a request the portal makes.
        Without a nudge it waits for a login that has already happened — which
        is exactly what it did.
        """
        client = StubLoginClient(succeed_after=7, has_headers=False)
        nudges = []

        wait_for_login(client, poll_seconds=0, sleep=lambda _: None,
                       nudge=lambda: nudges.append(1), nudge_every=3)

        assert len(nudges) == 2       # after the 3rd and 6th failed probe

    def test_timing_out_without_headers_says_so(self):
        """
        'Not logged in' is the wrong diagnosis when the real problem is that
        the portal never issued a request to read the session headers from.
        """
        client = StubLoginClient(succeed_after=10**9, has_headers=False)

        with pytest.raises(PortalError) as excinfo:
            wait_for_login(client, timeout_seconds=0, sleep=lambda _: None)

        assert "never issued an AccountManagement request" in str(excinfo.value)

    def test_timing_out_with_headers_does_not_blame_the_page(self):
        client = StubLoginClient(succeed_after=10**9, has_headers=True)

        with pytest.raises(PortalError) as excinfo:
            wait_for_login(client, timeout_seconds=0, sleep=lambda _: None)

        assert "never issued an AccountManagement request" not in str(excinfo.value)


def test_download_target_labels_distinguish_snapshots_from_year_reports():
    year = DownloadTarget("trades", 1, date(2021, 1, 1), date(2021, 12, 31),
                          "Trades-2021.csv")
    snapshot = DownloadTarget("positions", 1, date(2021, 1, 1), date(2021, 1, 1),
                              "Positions-2021-SoY.csv")

    assert year.label == "trades 2021"
    assert snapshot.label == "positions @ 2021-01-01"

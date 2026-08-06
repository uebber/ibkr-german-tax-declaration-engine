"""
The portal's Flex protocol as observed in a recorded session, pinned down.

legal_basis: infrastructure. No declared figure depends on these assertions
directly — but the engine's figures are only as good as the input files, and
this is the code that decides which bytes become Trades-2021.csv. The failure
this guards is the quiet one: writing a file that is not the report that was
asked for, or is a truncated part of it, and leaving the engine to compute a
plausible wrong number from it.

The behaviour encoded here comes from private/portal_discovery — the run
request, HTTP 601 for a queued batch, the batch list, and the status codes
taken from the portal's own template
(template/page/reporting/common/batch.reports.html).
"""
import base64
import json
from datetime import date

import pytest

from src.web_portal.flex_portal import (
    AM_HEADER_NAMES,
    HTTP_QUEUED_FOR_BATCH,
    _FETCH_IN_PAGE,
    AmHeaderHarvester,
    BatchRequest,
    NoStatementAvailableError,
    NotAuthenticatedError,
    PageRequestTransport,
    PortalError,
    PortalFlexClient,
    batch_entry_matches,
    build_run_options,
    config_id_matches,
    extract_report_csv,
    looks_like_csv,
    parse_batch_requests,
)

# A real Flex CSV header, as the engine's parsers expect it.
CSV = ('"ClientAccountID","CurrencyPrimary","AssetClass","Symbol","TradeDate"\n'
       '"U1234567","EUR","STK","SAP","2021-03-01"\n')

# The configId the portal generated for a real run of query 1212943 over 2025.
REAL_CONFIG_ID = ("U1234567_U1234567_20250101_20251231_AF_1212943_"
                  "0123456789abcdef0123456789abcdef.csv")


def test_run_options_match_the_request_the_portal_sends():
    options = json.loads(build_run_options(1212943, date(2021, 1, 1), date(2021, 12, 31)))

    assert options == {
        "queryId": "1212943",          # a string in the portal's own request
        "queryType": "AF",
        "outputFormat": "CSV",
        "period": "Custom",
        "fromDate": "2021-01-01",
        "toDate": "2021-12-31",
        "noOfDays": 1,
        "filterConfig": {"includeDerivatives": False},
    }


def test_run_options_for_a_single_day_snapshot():
    """Positions SoY/EoY are one-day ranges, not calendar years."""
    options = json.loads(build_run_options(999, date(2021, 1, 1), date(2021, 1, 1)))

    assert options["fromDate"] == options["toDate"] == "2021-01-01"
    assert options["period"] == "Custom"


class TestConfigIdMatching:
    def test_matches_the_run_it_describes(self):
        assert config_id_matches(REAL_CONFIG_ID, 1212943,
                                 date(2025, 1, 1), date(2025, 12, 31))

    def test_rejects_a_different_year(self):
        assert not config_id_matches(REAL_CONFIG_ID, 1212943,
                                     date(2024, 1, 1), date(2024, 12, 31))

    def test_rejects_a_different_query(self):
        assert not config_id_matches(REAL_CONFIG_ID, 1212969,
                                     date(2025, 1, 1), date(2025, 12, 31))

    def test_rejects_a_query_id_that_is_a_prefix_of_ours(self):
        """
        121294 must not match the report of query 1212943. Delimiters are
        part of the needle precisely so a shorter ID cannot ride along.
        """
        assert not config_id_matches(REAL_CONFIG_ID, 121294,
                                     date(2025, 1, 1), date(2025, 12, 31))

    def test_distinguishes_a_soy_snapshot_from_an_eoy_snapshot(self):
        soy = "U1_U1_20250101_20250101_AF_555_abc.csv"
        eoy = "U1_U1_20251231_20251231_AF_555_abc.csv"

        assert config_id_matches(soy, 555, date(2025, 1, 1), date(2025, 1, 1))
        assert not config_id_matches(eoy, 555, date(2025, 1, 1), date(2025, 1, 1))


class TestEntriesThePortalListsWithoutAQueryId:
    """
    Not every report is listed under its query ID.

    Observed live on 2026-08-06: the Options EAE query, run for 2022, was
    queued and appeared in the batch list as

        Gemini Options EAE; <acct>; 20220101-20221231
        <acct>_<acct>_20220101_20221231_AF_NA_<hash>.csv

    — `NA` where every other report carries its numeric query ID. The needle
    `_AF_1427928_` can never match that, so the report sat "not in the batch
    list yet" for 843 seconds while it was sitting there ready, and the run
    died holding it.

    The date range and query type are still in the configId, so what is
    missing is only *which* query. The summary carries the name, and that is
    what closes the gap — matching on the range alone would claim any other
    unattributed report over the same year.
    """

    NA_CONFIG_ID = ("U1234567_U1234567_20220101_20221231_AF_NA_"
                    "fedcba9876543210fedcba9876543210.csv")
    YEAR = (date(2022, 1, 1), date(2022, 12, 31))

    def _entry(self, summary):
        return BatchRequest(self.NA_CONFIG_ID, "S", summary, "", "csv")

    def test_the_query_id_needle_cannot_match_it(self):
        """The defect itself, before anything is done about it."""
        assert not config_id_matches(self.NA_CONFIG_ID, 1427928, *self.YEAR)

    def test_it_is_matched_by_the_query_name_in_the_summary(self):
        entry = self._entry("Gemini Options EAE; U1234567; 20220101-20221231")

        assert batch_entry_matches(entry, 1427928, *self.YEAR,
                                   query_name="Gemini Options EAE")

    def test_separators_and_case_in_the_name_do_not_matter(self):
        entry = self._entry("MyTax_Options_EAE; U1234567; 20220101-20221231")

        assert batch_entry_matches(entry, 1427928, *self.YEAR,
                                   query_name="MyTax Options EAE")

    def test_another_unattributed_report_over_the_same_year_is_not_claimed(self):
        """
        Two `NA` entries for the same range are told apart by name, not taken
        on faith. Guessing here writes one report into another's file.
        """
        entry = self._entry("Gemini Something Else; U1234567; 20220101-20221231")

        assert not batch_entry_matches(entry, 1427928, *self.YEAR,
                                       query_name="Gemini Options EAE")

    def test_without_a_name_it_is_left_alone(self):
        """
        No name, no attribution. The run times out saying what it saw, which
        is better than claiming an entry it cannot identify.
        """
        entry = self._entry("Gemini Options EAE; U1234567; 20220101-20221231")

        assert not batch_entry_matches(entry, 1427928, *self.YEAR)

    def test_a_different_year_is_still_rejected(self):
        entry = self._entry("Gemini Options EAE; U1234567; 20220101-20221231")

        assert not batch_entry_matches(entry, 1427928, date(2023, 1, 1),
                                       date(2023, 12, 31),
                                       query_name="Gemini Options EAE")

    def test_an_ordinary_entry_still_matches_on_its_id_alone(self):
        entry = BatchRequest(REAL_CONFIG_ID, "S", "MyTax Trades", "", "csv")

        assert batch_entry_matches(entry, 1212943, date(2025, 1, 1),
                                   date(2025, 12, 31))


class TestBatchStatuses:
    """Status codes from the portal's batch.reports.html."""

    @pytest.mark.parametrize("code", ["I", "Q"])
    def test_in_progress_and_queued_are_pending(self, code):
        entry = BatchRequest(REAL_CONFIG_ID, code, "summary", "", "csv")
        assert entry.is_pending
        assert not entry.is_ready
        assert entry.failure_description() is None

    def test_success_is_ready(self):
        entry = BatchRequest(REAL_CONFIG_ID, "S", "summary", "", "csv")
        assert entry.is_ready
        assert not entry.is_pending
        assert entry.failure_description() is None

    @pytest.mark.parametrize("code,expected", [
        ("F", "failed to generate"),
        ("M", "on hold"),
        ("L", "delivery fetch error"),
        ("D", "delivered by FTP"),
    ])
    def test_terminal_failures_are_described(self, code, expected):
        entry = BatchRequest(REAL_CONFIG_ID, code, "summary", "", "csv")
        description = entry.failure_description()
        assert description is not None
        assert expected in description

    def test_failure_reason_is_carried_through(self):
        entry = BatchRequest(REAL_CONFIG_ID, "F", "summary",
                             "Too much data requested", "csv")
        assert "Too much data requested" in entry.failure_description()

    def test_an_unknown_status_code_is_a_failure_not_a_silent_wait(self):
        """
        A code this project has never seen must not be treated as pending:
        that would poll until the timeout and report the wrong problem.
        """
        entry = BatchRequest(REAL_CONFIG_ID, "Z", "summary", "", "csv")
        assert not entry.is_pending
        assert "unknown status code" in entry.failure_description()


class TestParseBatchRequests:
    def test_parses_the_recorded_response(self):
        payload = {
            "batchStmtRequests": [{
                "stmtSummary": "MyTax Trades; U1234567; 20250101-20251231",
                "configId": REAL_CONFIG_ID,
                "reason": "",
                "statusCode": "S",
                "format": "csv",
            }],
            "errors": {}, "requestErrors": {}, "expireSeconds": 3300,
        }
        entries = parse_batch_requests(payload)

        assert len(entries) == 1
        assert entries[0].config_id == REAL_CONFIG_ID
        assert entries[0].is_ready

    def test_an_empty_list_is_valid(self):
        """The portal returns [] before anything has been queued."""
        assert parse_batch_requests({"batchStmtRequests": []}) == []

    def test_a_missing_field_raises_rather_than_returning_nothing(self):
        with pytest.raises(PortalError, match="batchStmtRequests"):
            parse_batch_requests({"errors": {}})


class TestExtractReportCsv:
    def test_raw_csv_passes_through(self):
        assert extract_report_csv(CSV) == CSV

    def test_base64_inside_a_json_envelope(self):
        """
        The recorded FETCH_REPORT response was 538210 bytes of JSON for a
        403497-byte CSV — the 4/3 ratio of base64 — but was too large to
        capture in full, so the field name is not known. Finding the CSV by
        what it is, rather than by a field name, survives that.
        """
        payload = json.dumps({
            "fileName": "whatever.csv",
            "data": base64.b64encode(CSV.encode()).decode(),
        })
        assert extract_report_csv(payload) == CSV

    def test_plain_csv_inside_a_json_envelope(self):
        payload = json.dumps({"fileName": "whatever.csv", "content": CSV})
        assert extract_report_csv(payload) == CSV

    def test_unknown_field_name_does_not_matter(self):
        payload = json.dumps({"somethingNewIBKRInvented": CSV})
        assert extract_report_csv(payload) == CSV

    def test_no_csv_anywhere_raises_and_names_the_fields(self):
        payload = json.dumps({"errors": {"flexError": "nope"}, "expireSeconds": 3300})

        with pytest.raises(PortalError) as excinfo:
            extract_report_csv(payload)

        message = str(excinfo.value)
        assert "errors" in message and "expireSeconds" in message
        assert "discover" in message  # tells the reader how to find out what changed

    def test_a_non_json_non_csv_body_raises(self):
        with pytest.raises(PortalError, match="neither CSV nor JSON"):
            extract_report_csv("<html><body>Session expired</body></html>")

    def test_the_real_fetch_report_envelope(self):
        """
        The shape FETCH_REPORT actually returned, observed on a live run:
        the report in fileContent, beside three short descriptive fields.

        Those three used to be classified as CSVs too — the detector appended
        a comma before matching, so "csv" and "text/csv" both qualified — and
        only a largest-wins tie-break kept the right one. A report smaller than
        its own metadata would have written the metadata to data_import/.
        """
        payload = json.dumps({
            "fileContent": CSV,
            "contentType": "text/csv",
            "fileName": "U1234567_U1234567_20210101_20211231_AF_1372852_abc.csv",
            "fileFormat": "csv",
        })

        assert extract_report_csv(payload) == CSV

    @pytest.mark.parametrize("value", [
        "csv", "text/csv", "U1_U1_20210101_20211231_AF_1372852_abc.csv",
        "application/json", "MyTax Cash Balance",
    ])
    def test_envelope_metadata_is_not_mistaken_for_a_report(self, value):
        assert not looks_like_csv(value)

    def test_a_report_smaller_than_its_metadata_is_still_chosen(self):
        """
        The case largest-wins would get wrong: a one-row report next to a long
        filename. Preferring the known content field decides it on identity
        rather than size.
        """
        tiny = '"A","B"\n"1","2"\n'
        payload = json.dumps({
            "fileContent": tiny,
            "fileName": "U1234567_U1234567_20210101_20211231_AF_1372852_"
                        + "x" * 400 + ".csv",
        })

        assert extract_report_csv(payload) == tiny

    def test_the_largest_candidate_wins_when_several_look_like_csv(self):
        longer = CSV + '"U1234567","USD","OPT","SPX","2021-04-01"\n'
        payload = json.dumps({"preview": CSV, "content": longer})

        assert extract_report_csv(payload) == longer

    def test_an_html_error_page_is_not_mistaken_for_a_report(self):
        assert not looks_like_csv("<!DOCTYPE html>\n<html>,</html>")


class FakePortalClient(PortalFlexClient):
    """
    Drives run_and_collect's orchestration without a browser.

    Scripted batch-list responses stand in for the portal's progression from
    queued to ready.
    """

    def __init__(self, batch_states, immediate=None, report=CSV):
        super().__init__(transport=None)
        self.batch_states = list(batch_states)
        self.immediate = immediate
        self.report = report
        self.fetched: list[str] = []
        self.runs: list[tuple] = []

    def list_batch_requests(self):
        return self.batch_states.pop(0) if len(self.batch_states) > 1 \
            else self.batch_states[0]

    def request_report(self, query_id, from_date, to_date, query_type="AF"):
        self.runs.append((query_id, from_date, to_date))
        return self.immediate

    def fetch_report(self, config_id):
        self.fetched.append(config_id)
        return self.report


def _entry(status, config_id=REAL_CONFIG_ID, reason=""):
    return BatchRequest(config_id, status, "MyTax Trades", reason, "csv")


class TestRunAndCollect:
    YEAR = (date(2025, 1, 1), date(2025, 12, 31))

    def test_a_report_returned_immediately_is_used_without_polling(self):
        client = FakePortalClient([[]], immediate=CSV)

        assert client.run_and_collect(1212943, *self.YEAR) == CSV
        assert client.fetched == []

    def test_a_queued_report_is_polled_until_ready(self):
        client = FakePortalClient([
            [],                        # nothing queued before the run
            [_entry("Q")],             # queued
            [_entry("I")],             # generating
            [_entry("S")],             # ready
        ])
        slept = []

        result = client.run_and_collect(1212943, *self.YEAR, poll_seconds=7,
                                        sleep=slept.append)

        assert result == CSV
        assert client.fetched == [REAL_CONFIG_ID]
        assert slept == [7, 7]

    def test_a_failed_report_raises_with_the_portal_s_reason(self):
        client = FakePortalClient([
            [],
            [_entry("F", reason="Query returned too much data")],
        ])

        with pytest.raises(PortalError, match="too much data"):
            client.run_and_collect(1212943, *self.YEAR, timeout_seconds=5,
                               sleep=lambda _: None)

    def test_a_stale_failure_from_an_earlier_run_is_not_reported_as_ours(self):
        """
        The batch list keeps old entries. A previous failed attempt at the
        same query and range must not abort this run: what matters is the
        entry this call created.
        """
        stale = _entry("F", config_id="U1_U1_20250101_20251231_AF_1212943_OLD.csv",
                       reason="an old failure")
        fresh = _entry("S", config_id="U1_U1_20250101_20251231_AF_1212943_NEW.csv")
        client = FakePortalClient([[stale], [stale, fresh]])

        result = client.run_and_collect(1212943, *self.YEAR, timeout_seconds=5,
                               sleep=lambda _: None)

        assert result == CSV
        assert client.fetched == ["U1_U1_20250101_20251231_AF_1212943_NEW.csv"]

    def test_a_previously_ready_report_does_not_pre_empt_the_run_we_started(self):
        """
        The batch list keeps an earlier, still-ready copy of the same query and
        range. Once this call has queued its own run, that run is the one to
        wait for — taking the older copy would return data generated before
        the request, silently.
        """
        old = _entry("S", config_id="U1_U1_20250101_20251231_AF_1212943_OLD.csv")
        new_pending = _entry("Q", config_id="U1_U1_20250101_20251231_AF_1212943_NEW.csv")
        new_ready = _entry("S", config_id="U1_U1_20250101_20251231_AF_1212943_NEW.csv")
        client = FakePortalClient([[old], [old, new_pending], [old, new_ready]])

        client.run_and_collect(1212943, *self.YEAR, timeout_seconds=5,
                               sleep=lambda _: None)

        assert client.fetched == ["U1_U1_20250101_20251231_AF_1212943_NEW.csv"]

    def test_a_pre_existing_report_is_used_when_the_portal_queues_nothing_new(self):
        """
        The other side of the same rule: if the portal answers a repeat request
        by reusing the entry it already has, waiting for a new one would hang
        until the timeout for a report that is sitting there ready.
        """
        existing = _entry("S", config_id="U1_U1_20250101_20251231_AF_1212943_OLD.csv")
        client = FakePortalClient([[existing], [existing]])

        result = client.run_and_collect(1212943, *self.YEAR, timeout_seconds=5,
                               sleep=lambda _: None)

        assert result == CSV
        assert client.fetched == ["U1_U1_20250101_20251231_AF_1212943_OLD.csv"]

    def test_an_unrelated_query_in_the_batch_list_is_ignored(self):
        other = _entry("S", config_id="U1_U1_20250101_20251231_AF_999999_x.csv")
        ours = _entry("S", config_id="U1_U1_20250101_20251231_AF_1212943_y.csv")
        client = FakePortalClient([[], [other, ours]])

        client.run_and_collect(1212943, *self.YEAR, timeout_seconds=5,
                               sleep=lambda _: None)

        assert client.fetched == ["U1_U1_20250101_20251231_AF_1212943_y.csv"]

    def test_a_report_that_never_finishes_times_out_with_advice(self):
        client = FakePortalClient([[], [_entry("I")]])

        with pytest.raises(PortalError) as excinfo:
            client.run_and_collect(1212943, *self.YEAR, timeout_seconds=0,
                                   sleep=lambda _: None)

        assert "did not become ready" in str(excinfo.value)
        # The report keeps generating; the user should know re-running is cheap.
        assert "re-running" in str(excinfo.value)

    def test_a_pre_existing_failure_does_not_abort_the_run_we_just_queued(self):
        """
        The docstring on run_and_collect promises this and the code did not
        honour it. Between the portal answering "queued" and the portal
        listing the new run there is a window in which the only matching entry
        is the previous attempt — and the previous attempt failed. Aborting
        there reports last run's failure as this one's, seconds after the
        portal accepted the request.

        The window is wider than it looks, because the configId is
        deterministic: <acct>_<acct>_<from>_<to>_AF_<queryId>_<hash>, with no
        run instance in it. A re-run can therefore reuse the entry outright,
        and "an entry this call created" never appears at all.
        """
        stale = _entry("F", reason="a failure from an earlier run")
        client = FakePortalClient([[stale], [stale], [stale], [_entry("S")]])

        result = client.run_and_collect(1212943, *self.YEAR, poll_seconds=1,
                                        timeout_seconds=600,
                                        sleep=lambda _: None)

        assert result == CSV

    def test_a_failure_the_portal_never_re_queues_is_named_as_the_old_one(self):
        """
        The other side: if nothing fresh ever appears, the run must still end,
        and must not claim the failure is its own.
        """
        stale = _entry("F", reason="an old failure")
        client = FakePortalClient([[stale], [stale]])

        with pytest.raises(PortalError) as excinfo:
            client.run_and_collect(1212943, *self.YEAR, timeout_seconds=600,
                                   stale_failure_grace_seconds=0,
                                   sleep=lambda _: None)

        message = str(excinfo.value)
        assert "an old failure" in message
        assert "earlier run" in message

    def test_a_fresh_failure_still_ends_the_run_at_once(self):
        """The grace period is for stale entries only; ours is decisive."""
        client = FakePortalClient([[], [_entry("F", reason="too much data")]])

        with pytest.raises(PortalError, match="too much data"):
            client.run_and_collect(1212943, *self.YEAR, timeout_seconds=600,
                                   sleep=lambda _: None)

    def test_a_report_listed_without_a_query_id_is_still_collected(self):
        """
        End to end over the shape that cost a whole run: queued, then listed
        as `_AF_NA_` with only the summary to identify it.
        """
        na = BatchRequest(
            "U1_U1_20250101_20251231_AF_NA_fedcba98.csv", "S",
            "MyTax Trades; U1; 20250101-20251231", "", "csv")
        client = FakePortalClient([[], [na]])

        result = client.run_and_collect(1212943, *self.YEAR, timeout_seconds=5,
                                        query_name="MyTax Trades",
                                        sleep=lambda _: None)

        assert result == CSV
        assert client.fetched == ["U1_U1_20250101_20251231_AF_NA_fedcba98.csv"]

    def test_an_unidentifiable_entry_is_named_in_the_timeout(self):
        """
        When an entry cannot be attributed, the run must say what it saw. The
        843-second wait reported "not in the batch list yet (5 other report(s)
        queued)" while the report it wanted was one of those five.
        """
        na = BatchRequest(
            "U1_U1_20250101_20251231_AF_NA_fedcba98.csv", "S",
            "MyTax Trades; U1; 20250101-20251231", "", "csv")
        client = FakePortalClient([[], [na]])

        with pytest.raises(PortalError) as excinfo:
            client.run_and_collect(1212943, *self.YEAR, timeout_seconds=0,
                                   sleep=lambda _: None)

        assert "MyTax Trades" in str(excinfo.value)

    def test_reusing_the_portal_s_existing_copy_is_said_out_loud(self):
        """
        A ready entry that was already there when this call started is the
        previous run's output. Returning it is right — the portal reuses the
        configId and may not regenerate — but --overwrite then replaces a file
        with a copy that was not freshly generated, and silence about that
        reads as "re-fetched".
        """
        existing = _entry("S")
        client = FakePortalClient([[existing], [existing]])
        said = []

        client.run_and_collect(1212943, *self.YEAR, timeout_seconds=5,
                               progress=said.append, sleep=lambda _: None)

        assert any("already had" in line for line in said), said


class FakeFrame_:
    def __init__(self, url, parent=None):
        self.url = url
        self.parent_frame = parent


class FakeRequest:
    def __init__(self, url, headers):
        self.url = url
        self.headers = headers


# The header set a real portal XHR carried, with the credential shortened.
PORTAL_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "active_context": "AM_DEPENDENCY",
    "accounthash": "1484312398",
    "sessionid": "69XHW0D4kNebXYfyR7Q75dlib6QoX2eN",
    "am_uuid": "3c99c2df-44d1-4a13-8875-d854407bcff3",
    "referer": "https://ndcdyn.interactivebrokers.com/AccountManagement/AmAuthentication",
    "user-agent": "Mozilla/5.0",
    "sec-ch-ua-mobile": "?0",
}


class TestAmHeaderHarvester:
    """
    Cookies alone do not authenticate the AccountManagement API; an Angular
    interceptor adds these headers to every XHR the portal makes. Reading them
    off a live request is what lets this project call the API at all.
    """

    def test_captures_the_headers_from_an_account_management_request(self):
        harvester = AmHeaderHarvester()
        assert not harvester.ready

        harvester._on_request(FakeRequest(
            "https://ndcdyn.interactivebrokers.com/AccountManagement/BatchStatements"
            "?action=FETCH_BATCH_REQUESTS", PORTAL_HEADERS))

        assert harvester.ready
        captured = harvester.get()
        for name in AM_HEADER_NAMES:
            assert name in captured, name
        assert captured["sessionid"] == PORTAL_HEADERS["sessionid"]

    def test_ignores_requests_to_other_parts_of_the_site(self):
        harvester = AmHeaderHarvester()

        harvester._on_request(FakeRequest(
            "https://ndcdyn.interactivebrokers.com/portal.proxy/v1/portal/tickle",
            PORTAL_HEADERS))

        assert not harvester.ready

    def test_ignores_account_management_requests_without_a_session(self):
        """Static assets under the same path carry no session header."""
        harvester = AmHeaderHarvester()

        harvester._on_request(FakeRequest(
            "https://ndcdyn.interactivebrokers.com/AccountManagement/script/amCore.js",
            {"accept": "*/*"}))

        assert not harvester.ready

    def test_later_requests_replace_earlier_ones(self):
        """am_uuid rotates per page load; a long run must not pin a stale set."""
        harvester = AmHeaderHarvester()
        url = "https://ndcdyn.interactivebrokers.com/AccountManagement/User"

        harvester._on_request(FakeRequest(url, PORTAL_HEADERS))
        harvester._on_request(FakeRequest(
            url, dict(PORTAL_HEADERS, am_uuid="5a54d3c2-06e9-4f16-9936-0ec35cd9c2af")))

        assert harvester.get()["am_uuid"] == "5a54d3c2-06e9-4f16-9936-0ec35cd9c2af"

    def test_a_partial_later_capture_does_not_drop_the_account_scope(self):
        """
        The portal's requests do not all carry the same headers: some omit
        accounthash and active_context. Replacing the set wholesale meant
        whichever request fired last decided whether the next call carried an
        account scope — observed flipping between four headers and seven
        within a single run, with the run then failing on an internal error.
        """
        harvester = AmHeaderHarvester()
        url = "https://ndcdyn.interactivebrokers.com/AccountManagement/User"

        harvester._on_request(FakeRequest(url, PORTAL_HEADERS))
        harvester._on_request(FakeRequest(url, {
            "sessionid": PORTAL_HEADERS["sessionid"],
            "accept": "application/json, text/plain, */*",
            "referer": PORTAL_HEADERS["referer"],
            "user-agent": "Mozilla/5.0",
        }))

        captured = harvester.get()
        assert captured["accounthash"] == PORTAL_HEADERS["accounthash"]
        assert captured["active_context"] == "AM_DEPENDENCY"
        assert set(AM_HEADER_NAMES) <= set(captured)

    def test_the_headers_sent_all_come_from_one_request(self):
        """
        Completeness is not worth incoherence. Pairing a sessionid from one
        page load with an am_uuid from another is a plausible way to have the
        session invalidated server-side, which is what "Your Session Has
        Expired" on every subsequent request looks like. A complete set
        captured from a single request is preferred over a union of several.
        """
        harvester = AmHeaderHarvester()
        url = "https://ndcdyn.interactivebrokers.com/AccountManagement/User"

        harvester._on_request(FakeRequest(url, PORTAL_HEADERS))
        harvester._on_request(FakeRequest(url, {
            "sessionid": "A-DIFFERENT-SESSION",
            "am_uuid": "99999999-0000-0000-0000-000000000000",
            "accept": "application/json",
        }))

        captured = harvester.get()
        assert captured["sessionid"] == PORTAL_HEADERS["sessionid"]
        assert captured["am_uuid"] == PORTAL_HEADERS["am_uuid"]
        assert "A-DIFFERENT-SESSION" not in captured.values()

    def test_a_newer_complete_set_supersedes_an_older_one(self):
        """Coherence must not mean going stale: a full set still wins."""
        harvester = AmHeaderHarvester()
        url = "https://ndcdyn.interactivebrokers.com/AccountManagement/User"
        newer = dict(PORTAL_HEADERS, sessionid="NEWER", am_uuid="newer-uuid")

        harvester._on_request(FakeRequest(url, PORTAL_HEADERS))
        harvester._on_request(FakeRequest(url, newer))

        assert harvester.get()["sessionid"] == "NEWER"
        assert harvester.get()["am_uuid"] == "newer-uuid"

    def test_nothing_is_sent_after_a_navigation_until_the_app_speaks_again(self):
        """
        A login is a navigation. Headers captured from the expired-session
        page describe a session that is gone, and presenting that sessionid
        against the newly logged-in session is a replayed token — the server
        ends the new session over it. Observed as "logged in for half a
        second", repeatedly.
        """
        harvester = AmHeaderHarvester()
        url = "https://ndcdyn.interactivebrokers.com/AccountManagement/User"
        harvester._on_request(FakeRequest(url, PORTAL_HEADERS))
        assert harvester.ready

        harvester.mark_navigation()

        assert harvester.get() == {}
        assert not harvester.ready

    def test_headers_become_usable_again_once_the_new_session_makes_a_request(self):
        harvester = AmHeaderHarvester()
        url = "https://ndcdyn.interactivebrokers.com/AccountManagement/User"
        harvester._on_request(FakeRequest(url, PORTAL_HEADERS))
        harvester.mark_navigation()

        after_login = dict(PORTAL_HEADERS, sessionid="ISSUED-AFTER-LOGIN")
        harvester._on_request(FakeRequest(url, after_login))

        assert harvester.get()["sessionid"] == "ISSUED-AFTER-LOGIN"

    def test_a_change_of_document_marks_the_capture_stale(self):
        harvester = AmHeaderHarvester()
        harvester._on_frame_navigated(FakeFrame_(
            "https://x.example/AccountManagement/AmAuthentication?action=FlexQueries"))
        harvester._on_request(FakeRequest(
            "https://x.example/AccountManagement/User", PORTAL_HEADERS))

        harvester._on_frame_navigated(FakeFrame_("https://x.example/sso/Login"))

        assert harvester.get() == {}

    def test_a_fragment_route_change_does_not(self):
        """
        The portal routes on the fragment — ".../FlexQueries#!#<uuid>" — and
        each route change raises the same event as a real navigation. Treating
        those as navigations left the capture permanently stale, because the
        fragment moves after the page's own requests have already gone out,
        and nothing then clears it. The run waited forever on a fully loaded
        Flex Queries page.
        """
        base = "https://x.example/AccountManagement/AmAuthentication?action=FlexQueries"
        harvester = AmHeaderHarvester()
        harvester._on_frame_navigated(FakeFrame_(base))
        harvester._on_request(FakeRequest(
            "https://x.example/AccountManagement/User", PORTAL_HEADERS))

        harvester._on_frame_navigated(FakeFrame_(base + "#!#0d3f-uuid"))
        harvester._on_frame_navigated(FakeFrame_(base + "#!#9a71-uuid"))

        assert harvester.get()["sessionid"] == PORTAL_HEADERS["sessionid"]

    def test_a_subframe_navigation_does_not_either(self):
        """The portal renders in iframes; only the top-level load is a login."""
        harvester = AmHeaderHarvester()
        harvester._on_request(FakeRequest(
            "https://x.example/AccountManagement/User", PORTAL_HEADERS))

        harvester._on_frame_navigated(
            FakeFrame_("https://x.example/other", parent=FakeFrame_("https://x")))

        assert harvester.get()["sessionid"] == PORTAL_HEADERS["sessionid"]

    def test_a_partial_capture_is_never_sent(self):
        """
        The session killer, in one assertion.

        Not every AccountManagement request carries the full set — a login
        redirect and some early XHRs go out with sessionid alone. Sending that
        combination is answered HTTP 604, and the session does not survive it:
        in the recorded run of 2026-08-06 10:07 the first probe carried
        sessionid only, was answered 604, and all 368 requests after it were
        answered 603 no_session. Runs whose first probe happened to carry the
        complete set were answered 200 and went on to download.

        Waiting for the app to make one more request costs seconds. Sending an
        incomplete set costs the login.
        """
        harvester = AmHeaderHarvester()

        harvester._on_request(FakeRequest(
            "https://x.example/AccountManagement/User", {
                "sessionid": PORTAL_HEADERS["sessionid"],
                "accept": "application/json, text/plain, */*",
                "referer": PORTAL_HEADERS["referer"],
                "user-agent": "Mozilla/5.0",
            }))

        assert harvester.get() == {}
        assert not harvester.ready

    def test_the_set_becomes_usable_as_soon_as_it_is_complete(self):
        """The wait is for completeness, not for a particular request."""
        harvester = AmHeaderHarvester()
        url = "https://x.example/AccountManagement/User"

        harvester._on_request(FakeRequest(url, {
            "sessionid": PORTAL_HEADERS["sessionid"],
            "accounthash": PORTAL_HEADERS["accounthash"],
        }))
        assert harvester.get() == {}

        harvester._on_request(FakeRequest(url, {
            "sessionid": PORTAL_HEADERS["sessionid"],
            "am_uuid": PORTAL_HEADERS["am_uuid"],
            "active_context": "AM_DEPENDENCY",
        }))

        assert set(AM_HEADER_NAMES) <= set(harvester.get())

    def test_the_captured_set_is_a_copy(self):
        harvester = AmHeaderHarvester()
        harvester._on_request(FakeRequest(
            "https://ndcdyn.interactivebrokers.com/AccountManagement/User",
            PORTAL_HEADERS))

        harvester.get()["sessionid"] = "tampered"

        assert harvester.get()["sessionid"] == PORTAL_HEADERS["sessionid"]


class RecordingRequestContext:
    """Captures what the client sends, and answers with a batch list."""

    def __init__(self, payload=None, status=200):
        self.calls = []
        self._payload = payload if payload is not None else {"batchStmtRequests": []}
        self._status = status

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        context = self

        class Response:
            status = context._status

            def json(self):
                return context._payload

            def text(self):
                return json.dumps(context._payload)

        return Response()


class FakePage:
    """Stands in for a logged-in portal page."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def evaluate(self, script, arg):
        self.calls.append(arg)
        return self.result


class TestPageRequestTransport:
    """
    The portal's API is called from inside the page, not from Playwright's
    driver. The driver shares cookies but is a different HTTP client, and a
    live sessionid arriving from a different client is what a hijack defence
    ends the session over — which is what happened: every run after the API
    calls were added died with "Your Session Has Expired", while the
    browser-only recording never did.
    """

    def test_parameters_are_encoded_onto_the_url(self):
        page = FakePage({"status": 200, "body": "{}"})
        transport = PageRequestTransport(page)

        transport.get("https://x.example/AccountManagement/BatchStatements",
                      params={"action": "FETCH_REPORT", "configId": "a b.csv"})

        url = page.calls[0]["url"]
        assert url.startswith(
            "https://x.example/AccountManagement/BatchStatements?")
        assert "action=FETCH_REPORT" in url
        assert "configId=a+b.csv" in url or "configId=a%20b.csv" in url

    def test_a_url_without_parameters_is_left_alone(self):
        page = FakePage({"status": 200, "body": "{}"})

        PageRequestTransport(page).get("https://x.example/AccountManagement/User")

        assert page.calls[0]["url"] == "https://x.example/AccountManagement/User"

    def test_the_portal_headers_are_handed_to_the_page(self):
        page = FakePage({"status": 200, "body": "{}"})

        PageRequestTransport(page).get("https://x.example/a",
                                       headers=dict(PORTAL_HEADERS))

        assert page.calls[0]["headers"]["sessionid"] == PORTAL_HEADERS["sessionid"]

    def test_a_non_2xx_status_comes_back_as_data(self):
        """601, 603 and 604 all carry meaning; none may raise inside fetch."""
        page = FakePage({"status": 601, "body": '{"isBatchFlex": true}'})

        response = PageRequestTransport(page).get("https://x.example/a")

        assert response.status == 601
        assert response.json() == {"isBatchFlex": True}

    def test_the_body_is_available_as_text_and_json(self):
        page = FakePage({"status": 200, "body": '{"batchStmtRequests": []}'})

        response = PageRequestTransport(page).get("https://x.example/a")

        assert response.text() == '{"batchStmtRequests": []}'
        assert response.json() == {"batchStmtRequests": []}

    def test_a_failed_fetch_raises_rather_than_looking_like_an_empty_answer(self):
        page = FakePage({"status": 0, "body": "", "error": "TypeError: aborted"})

        with pytest.raises(PortalError, match="aborted"):
            PageRequestTransport(page).get("https://x.example/a")

    def test_the_timeout_is_passed_to_the_page(self):
        page = FakePage({"status": 200, "body": "{}"})

        PageRequestTransport(page).get("https://x.example/a", timeout=45_000)

        assert page.calls[0]["timeoutMs"] == 45_000

    def test_the_response_is_never_served_from_the_browser_cache(self):
        """
        Polling only works if the answer can change.

        The batch list is fetched over and over at a byte-identical URL, and
        the portal's own app never does that — it reads the list once per page
        load, and cache-busts its other endpoints with a per-load
        `cacheControl` UUID. A cached answer would leave the poll watching a
        frozen list while the report it is waiting for is generated and
        finishes, which is the shape of "queued, then never appears".

        Not proven to be the cause: the recordings do not keep response
        headers, so no Cache-Control from the portal is on file. What is
        certain is that the default `fetch` cache mode allows it, and asking
        for no-store costs nothing.
        """
        assert "'no-store'" in _FETCH_IN_PAGE
        # In the options object, not in a comment about it.
        assert "cache:" in _FETCH_IN_PAGE.replace(" ", "")

    def test_the_client_works_over_this_transport(self):
        """End to end through the real client, with the page as the wire."""
        page = FakePage({"status": 200, "body": json.dumps({
            "batchStmtRequests": [{
                "configId": REAL_CONFIG_ID, "statusCode": "S",
                "stmtSummary": "MyTax Trades", "reason": "", "format": "csv",
            }]})})
        client = PortalFlexClient(PageRequestTransport(page),
                                  headers_provider=lambda: dict(PORTAL_HEADERS))

        entries = client.list_batch_requests()

        assert len(entries) == 1 and entries[0].is_ready
        assert page.calls[0]["headers"]["sessionid"] == PORTAL_HEADERS["sessionid"]


class TestWhatSixOhOneMeans:
    """
    601 is not "queued". It is "this flex request was not served", and only the
    body says why. Reading the status alone left a run polling for fifteen
    minutes for a report the portal had already declined to produce.
    """

    QUEUED = {"isBatchFlex": True, "errors": {"flexError":
              "Your request has been queued for batch processing. "
              "Please check Batch Statements for status."}}
    NO_DATA = {"isBatchFlex": False, "errors": {"flexError":
               "There is no statement available for the account(s) and "
               "date(s) selected."}}
    REFUSED = {"isBatchFlex": False, "errors": {"flexError":
               "Query returned too much data."}}

    def _client(self, payload, status=601):
        return PortalFlexClient(RecordingRequestContext(payload, status),
                                headers_provider=lambda: dict(PORTAL_HEADERS))

    def test_is_batch_flex_true_means_queued(self):
        client = self._client(self.QUEUED)

        assert client.request_report(1, date(2021, 1, 1), date(2021, 12, 31)) is None

    def test_no_statement_available_is_its_own_answer(self):
        """
        The portal's reply for a start-of-year snapshot in the first year of
        trading. Not a failure and not a report — nothing was held that day.
        """
        client = self._client(self.NO_DATA)

        with pytest.raises(NoStatementAvailableError, match="no statement"):
            client.request_report(1, date(2021, 1, 1), date(2021, 1, 1))

    def test_any_other_refusal_raises_with_the_portal_s_wording(self):
        client = self._client(self.REFUSED)

        with pytest.raises(PortalError, match="too much data"):
            client.request_report(1, date(2021, 1, 1), date(2021, 12, 31))

    def test_a_refusal_is_not_mistaken_for_a_queued_report(self):
        """The whole defect in one assertion."""
        for payload in (self.NO_DATA, self.REFUSED):
            client = self._client(payload)
            with pytest.raises(PortalError):
                client.request_report(1, date(2021, 1, 1), date(2021, 1, 1))

    def test_a_no_statement_answer_is_not_a_plain_failure(self):
        """
        It has its own type so the caller can report it as "no data" instead
        of "failed", without matching on message text.
        """
        assert issubclass(NoStatementAvailableError, PortalError)


class TestARejectedSession:
    """
    603 arrives when the portal has stopped recognising the session, and "log
    in again and re-run" does not say why it happened or how to avoid it.

    The recorded run of 2026-08-06 09:54 shows what it actually is: fifteen
    and a half minutes after the last user interaction — with the portal's own
    tickle firing every 30 seconds and a batch-list request every 10 — the
    page called `portal/logout`, `ibcust/logout` and `sso/Logout` on itself and
    navigated to the login screen. The downloader was mid-poll and had done
    nothing wrong. Network traffic does not reset that timer.
    """

    def _client(self):
        return PortalFlexClient(
            RecordingRequestContext({"errors": {"rejected": "no_session"}},
                                    status=603),
            headers_provider=lambda: dict(PORTAL_HEADERS))

    def test_the_error_names_the_inactivity_logout(self):
        with pytest.raises(NotAuthenticatedError) as excinfo:
            self._client().list_batch_requests()

        assert "inactivity" in str(excinfo.value).lower()

    def test_it_still_says_nothing_has_to_be_regenerated(self):
        """The reassurance that makes re-running cheap must survive."""
        with pytest.raises(NotAuthenticatedError, match="without being regenerated"):
            self._client().list_batch_requests()


class TestHeadersAreSentWithEveryCall:
    def test_the_portal_headers_reach_the_request(self):
        request_context = RecordingRequestContext()
        client = PortalFlexClient(request_context,
                                  headers_provider=lambda: dict(PORTAL_HEADERS))

        client.list_batch_requests()

        assert request_context.calls[0]["headers"]["sessionid"] == \
            PORTAL_HEADERS["sessionid"]

    def test_the_probe_reports_not_authenticated_before_any_headers_exist(self):
        """
        Asking the API without the headers always answers 'no', so probing
        would report a live session as logged out — which is what it did, and
        the run waited for a login that had already happened.
        """
        request_context = RecordingRequestContext()
        client = PortalFlexClient(request_context, headers_provider=dict)

        assert not client.has_am_headers
        assert not client.is_authenticated()
        assert request_context.calls == []   # not even attempted

    def test_the_probe_says_why_it_failed(self):
        """
        A run that is not progressing has to say what it is waiting for. This
        one sat silent for ten minutes while the browser was in the modern
        Client Portal SPA, which never touches the Account Management app the
        session headers come from.
        """
        client = PortalFlexClient(RecordingRequestContext(), headers_provider=dict)

        assert not client.is_authenticated()
        assert "Flex Queries" in client.last_probe_reason

        rejected = PortalFlexClient(RecordingRequestContext(status=603),
                                    headers_provider=lambda: dict(PORTAL_HEADERS))
        assert not rejected.is_authenticated()
        assert "603" in rejected.last_probe_reason

    def test_the_probe_succeeds_once_the_headers_are_available(self):
        request_context = RecordingRequestContext()
        client = PortalFlexClient(request_context,
                                  headers_provider=lambda: dict(PORTAL_HEADERS))

        assert client.has_am_headers
        assert client.is_authenticated()

    def test_a_partial_set_is_not_probed_with_either(self):
        """
        The harvester holds a partial capture back, and the client must not
        undo that by deciding a sessionid on its own is enough to ask with.
        That decision is what put the malformed request on the wire.
        """
        request_context = RecordingRequestContext()
        client = PortalFlexClient(
            request_context,
            headers_provider=lambda: {"sessionid": PORTAL_HEADERS["sessionid"]})

        assert not client.has_am_headers
        assert not client.is_authenticated()
        assert request_context.calls == []   # not even attempted

    def test_the_probe_names_the_headers_it_is_still_waiting_for(self):
        """
        "The Account Management app has not been opened yet" is wrong once it
        has been opened and is simply mid-handshake, and it sends the reader
        to click something that is already on screen.
        """
        client = PortalFlexClient(
            RecordingRequestContext(),
            headers_provider=lambda: {"sessionid": PORTAL_HEADERS["sessionid"],
                                      "am_uuid": PORTAL_HEADERS["am_uuid"]})

        assert not client.is_authenticated()
        assert "accounthash" in client.last_probe_reason
        assert "active_context" in client.last_probe_reason

    def test_headers_are_re_read_for_each_call_not_frozen_at_construction(self):
        current = {}
        request_context = RecordingRequestContext()
        client = PortalFlexClient(request_context, headers_provider=lambda: dict(current))

        assert not client.has_am_headers
        current.update(PORTAL_HEADERS)

        assert client.has_am_headers


def test_the_queued_status_code_is_the_one_the_portal_returned():
    """601 reads like an error and means 'accepted, being generated'."""
    assert HTTP_QUEUED_FOR_BATCH == 601

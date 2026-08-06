"""
The IBKR Client Portal's own Flex Query protocol.

Observed in a recorded portal session (see src/web_portal/discover.py), not
guessed. Running a query from the portal UI is three HTTP calls, and the
elaborate date picker in the run dialog only assembles the JSON in the first
one:

1. GET /AccountManagement/FlexQueries/Download?runOptions=<json>
   Returns the report directly on 200. Anything large comes back as HTTP 601
   with {"isBatchFlex": true} — queued, despite the "errors" object it arrives
   in. The same 601 with {"isBatchFlex": false} is a refusal, and its
   flexError says whether that is "no statement available" (nothing was held
   on that date) or a real problem.

2. GET /AccountManagement/BatchStatements?action=FETCH_BATCH_REQUESTS
       &batchReportType=FLEX
   Lists the queued reports with a statusCode each. The portal only calls this
   on page load, which is why running a query by hand needs a manual refresh
   before the download link appears. Polled directly, no refresh is involved.

   Reports queue in parallel and this lists all of them together, so step 1 is
   done for a whole batch of reports before step 2 is done for any of them —
   see run_and_collect_many. Waiting for one report before asking for the next
   costs session time, and the session is what runs out.

3. GET /AccountManagement/BatchStatements?action=FETCH_REPORT&configId=<id>
   Returns the report. The browser turns it into a blob download.

The status codes are the complete set from the portal's own template,
template/page/reporting/common/batch.reports.html.

Nothing here interprets a figure: it moves bytes from the portal to
data_import/. The one judgement it makes is refusing to write a file it cannot
prove is the report that was asked for.
"""

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

BASE_URL = "https://ndcdyn.interactivebrokers.com"
RUN_PATH = "/AccountManagement/FlexQueries/Download"
BATCH_PATH = "/AccountManagement/BatchStatements"
ACTIVITY_FLEX_PATH = "/AccountManagement/ActivityFlex/Data"

# The Flex Queries page itself. Landing here rather than on the portal home
# page does two things: a live session goes straight to the right screen, and
# the page issues the AccountManagement request whose headers this module needs
# while it is still loading. A logged-out session is redirected to the login
# and comes back here afterwards.
FLEX_QUERIES_URL = f"{BASE_URL}/AccountManagement/AmAuthentication?action=FlexQueries"

# Activity Flex. Every query this engine consumes is one; the portal also has
# TradeConfirm ("TCF") and Delivered flex types, which it does not.
QUERY_TYPE_ACTIVITY_FLEX = "AF"

# Non-standard statuses the AccountManagement API uses. Observed live.
#
# 601 — the flex request was not served, and only the body says why:
#       {"isBatchFlex": true, ...} is queued for batch processing, while
#       {"isBatchFlex": false, "errors": {"flexError": "There is no statement
#       available ..."}} is a refusal. Reading the status alone and calling it
#       "queued" left a run polling for a report that was never coming.
# 603 — {"errors": {"rejected": "no_session"}}. The session is gone; every
#       later call fails the same way until a fresh login.
# 604 — {"errors": {"internal": "unhandled"}}. The portal could not serve the
#       request at all. Seen once, on a session that was already being
#       destroyed by this project replaying a dead sessionid; it was briefly
#       blamed on the requested date, wrongly — a later recording shows the
#       same date served without complaint.
HTTP_QUEUED_FOR_BATCH = 601
HTTP_SESSION_REJECTED = 603
HTTP_INTERNAL_ERROR = 604

# statusCode values, from batch.reports.html.
STATUS_IN_PROGRESS = "I"
STATUS_QUEUED = "Q"
STATUS_SUCCESS = "S"
STATUS_FAILED = "F"
STATUS_ON_HOLD = "M"
STATUS_DELIVERED_FTP = "D"
STATUS_DELIVERY_ERROR = "L"

_PENDING_STATUSES = frozenset({STATUS_IN_PROGRESS, STATUS_QUEUED})

# How long a failure recorded against an *earlier* run of the same query and
# range is given to be superseded before it is reported as this run's. The
# configId carries no run instance, so between the portal accepting a request
# and listing it there is a window in which last run's failure is the only
# entry that matches — see _resolve_pending.
STALE_FAILURE_GRACE_SECONDS = 60.0

# How many batch reports to keep queued at the portal at once.
#
# The portal takes them in parallel — five were seen in the batch list
# together, three finishing while the others were still queued — and the win
# is entirely in not making report N+1 wait for report N. That win is had at
# ten as fully as at thirty-five, and thirty-five simultaneous batch jobs is a
# burst this project has never asked for and the portal has every right to
# refuse. Reports the portal answers immediately do not occupy a slot: they
# are finished, not in flight.
MAX_REPORTS_IN_FLIGHT = 10

# How many outstanding reports to name in a progress line before eliding the
# rest, with the elision stated rather than silent.
_PROGRESS_MAX_NAMED = 4

_TERMINAL_FAILURES = {
    STATUS_FAILED: "the report failed to generate",
    STATUS_ON_HOLD: "the report is on hold",
    STATUS_DELIVERY_ERROR: "delivery fetch error",
    STATUS_DELIVERED_FTP: "the report was delivered by FTP, not to the portal",
}


# Headers the AccountManagement API authenticates and routes on. Cookies alone
# are not enough: an Angular interceptor adds these to every XHR the portal
# makes, and requests without them are not recognised as a logged-in session.
# `sessionid` is a bearer credential — it is read from the live page, used, and
# never written anywhere.
AM_HEADER_NAMES = ("sessionid", "accounthash", "am_uuid", "active_context")

# Sent alongside them so the request looks like the one the portal makes.
_AM_CONTEXT_HEADERS = ("accept", "referer", "user-agent")

AM_PATH_MARKER = "/AccountManagement/"


class AmHeaderHarvester:
    """
    Takes the AccountManagement headers from the portal's own requests.

    The alternative — digging the session token out of the Angular app's
    internals — depends on where a portal release happens to keep it. Watching
    what the app actually sends does not: any AccountManagement XHR carries the
    full set, and the Flex Queries page issues one as soon as it loads.

    Holds a live credential in memory for the duration of the run. Nothing here
    logs or persists it.
    """

    def __init__(self):
        # Two views of what the portal has been seen sending.
        #
        # `_coherent` is the most recent single request that carried every
        # AccountManagement header — one session, one page load, internally
        # consistent. `_merged` is the union across requests, which can pair a
        # sessionid from one page load with an am_uuid from another. The
        # coherent set is preferred: sending a mismatched combination is a
        # plausible way to have a session invalidated, and completeness is
        # worth nothing if the server rejects the mixture.
        #
        # Neither is complete by construction — the union is only as complete
        # as the requests seen so far, and early in a page load that can be
        # `sessionid` and nothing else. `get` is what refuses to hand out a
        # partial set; both of these may hold one.
        self._coherent: dict[str, str] = {}
        self._merged: dict[str, str] = {}
        # Headers captured before the page last navigated describe a session
        # that may no longer be the current one. Presenting an old sessionid
        # against a freshly logged-in session is a replayed token as far as the
        # server is concerned, and it ends the new session — which is what
        # "logged in for half a second, then Your Session Has Expired" is.
        # Nothing is sent until the portal has been seen making a request under
        # the session now in force.
        self._stale = False
        self._document_url: Optional[str] = None

    def attach(self, context) -> None:
        context.on("request", self._on_request)
        context.on("page", self._watch_page)
        for page in context.pages:
            self._watch_page(page)

    def _watch_page(self, page) -> None:
        page.on("framenavigated", self._on_frame_navigated)

    def _on_frame_navigated(self, frame) -> None:
        try:
            if frame.parent_frame is not None:
                return
            url = frame.url
        except Exception:  # pragma: no cover - frame may be detached
            return

        # Only a change of document counts. The portal routes on the fragment
        # (".../AmAuthentication?action=FlexQueries#!#<uuid>"), and every such
        # route change raises this event without any session changing. Treating
        # those as navigations left the capture permanently stale, because the
        # fragment moves after the page's own requests have gone out.
        document = url.split("#", 1)[0]
        if self._document_url is not None and document != self._document_url:
            self.mark_navigation()
        self._document_url = document

    def mark_navigation(self) -> None:
        """
        Treat what has been captured as belonging to a previous page load.

        A login is a navigation, so this is what stops the credentials of the
        expired session being replayed against the new one.
        """
        if not self._stale:
            logger.debug("Page navigated; holding portal headers until the "
                         "app makes a request under the new session.")
        self._stale = True

    def _on_request(self, request) -> None:
        url = request.url
        if AM_PATH_MARKER not in url:
            return
        try:
            # all_headers() is the complete set; headers is the provisional one
            # and is enough in practice, but only the former is guaranteed to
            # include everything an interceptor added.
            headers = (request.all_headers() if hasattr(request, "all_headers")
                       else request.headers)
        except Exception:  # pragma: no cover - request may be gone
            return
        if "sessionid" not in headers:
            return

        captured = {name: headers[name]
                    for name in AM_HEADER_NAMES + _AM_CONTEXT_HEADERS
                    if headers.get(name)}

        # An observed request is proof the app is working under the session
        # in force right now, so what was captured is current again.
        self._stale = False

        if all(name in captured for name in AM_HEADER_NAMES):
            if captured != self._coherent:
                logger.debug("Complete AccountManagement header set captured.")
            self._coherent = captured

        merged = dict(self._merged)
        merged.update(captured)
        self._merged = merged

    @property
    def ready(self) -> bool:
        return bool(self.get())

    def get(self) -> dict[str, str]:
        """
        The header set to send. Empty until a complete one is available.

        A complete set from one request when one has been seen; otherwise the
        union across requests, and only if that union is itself complete.
        Empty while the capture is stale — after a navigation, until the
        portal makes its next request.

        **Never a partial set.** Not every AccountManagement request carries
        all four: some early XHRs go out with `sessionid` alone, and sending
        that combination is answered HTTP 604 by a session that then stops
        existing. In the recorded run of 2026-08-06 10:07 the first probe
        carried `sessionid` alone, was answered 604, and every one of the 368
        requests after it was answered 603 `no_session` — the login was gone
        before a single report had been asked for. The runs that worked are
        the ones where a complete set happened to be captured before the first
        probe fired; nothing but timing separated them.

        The union is kept for completeness rather than dropped in favour of
        the coherent set alone, because the account scope has been seen
        arriving spread across two requests — but it is held back until it is
        whole, which is the part that was missing.
        """
        if self._stale:
            return {}
        candidate = self._coherent or self._merged
        if not all(name in candidate for name in AM_HEADER_NAMES):
            return {}
        return dict(candidate)


# Runs in the page. Returns the status and body rather than throwing, so a
# non-2xx answer — 601 queued, 603 no_session, 604 internal — comes back to
# Python as data instead of an exception.
#
# cache: 'no-store' because polling only works if the answer can change. The
# batch list is fetched repeatedly at a byte-identical URL, which the portal's
# own app never does — it reads that list once per page load, and cache-busts
# its other endpoints with a per-load `cacheControl` UUID. Under the default
# cache mode a stored response would leave the poll watching a frozen list
# while the report it is waiting for is generated and finishes: queued, then
# never appears. Whether that is what happens here is *not* established — the
# recordings do not keep response headers, so no Cache-Control from the portal
# is on file — but the default mode permits it and no-store costs nothing.
_FETCH_IN_PAGE = """
async ({url, headers, timeoutMs}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: headers,
      credentials: 'include',
      cache: 'no-store',
      signal: controller.signal,
    });
    return {status: response.status, body: await response.text()};
  } catch (error) {
    return {status: 0, body: '', error: String(error)};
  } finally {
    clearTimeout(timer);
  }
}
"""


class PageRequestTransport:
    """
    Issues the portal's API calls from inside the logged-in page.

    Playwright's APIRequestContext shares the browser's cookies but is not the
    browser: it is the driver process, with its own HTTP and TLS stack. A
    request bearing a live `sessionid` from something that does not look like
    the client the session was issued to is what a hijack defence exists to
    stop, and the portal responded by ending the session — every run after the
    API calls were introduced died with "Your Session Has Expired", while the
    recorded browser-only session never did.

    Going through page.evaluate makes the call same-origin from the page that
    is already logged in: same connection, same TLS, same cookies, and the
    portal's own headers on top. It is the app making the request.
    """

    def __init__(self, page_source):
        """
        Args:
            page_source: a Playwright page, or a callable returning the page to
                use. A callable is what a real run passes: logging in can leave
                a different page current than the one open at startup, and a
                transport pinned to a stale page evaluates against a document
                that is no longer there.
        """
        self._page_source = page_source

    def _page(self):
        return (self._page_source() if callable(self._page_source)
                else self._page_source)

    def get(self, url: str, params: Optional[dict] = None,
            headers: Optional[dict] = None, timeout: Optional[float] = None):
        page = self._page()
        if page is None:
            raise PortalError("No open browser page to make the request from.")

        full_url = f"{url}?{urlencode(params)}" if params else url
        result = page.evaluate(_FETCH_IN_PAGE, {
            "url": full_url,
            "headers": headers or {},
            "timeoutMs": int(timeout) if timeout else 120_000,
        })
        if result.get("status") == 0:
            raise PortalError(
                f"The page could not reach {url}: {result.get('error')}")
        return _PageResponse(result["status"], result["body"])


class _PageResponse:
    """The part of Playwright's response interface this module uses."""

    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    def text(self) -> str:
        return self._body

    def json(self):
        return json.loads(self._body)


class PortalError(Exception):
    """Raised when the portal cannot be made to produce the requested report."""


class NotAuthenticatedError(PortalError):
    """Raised when the portal session is absent or has expired."""


class NoStatementAvailableError(PortalError):
    """
    The portal has no report for that query and date — an answer, not a fault.

    Legitimate for a start-of-year snapshot in the first year of trading: on
    1 January there was nothing held, so there is no statement. The engine
    tolerates a missing start-of-year file for exactly that case.
    """


# What the portal says when there is simply nothing to report.
_NO_STATEMENT_MARKER = "no statement available"


@dataclass(frozen=True)
class FlexQuery:
    """One Activity Flex query as the portal has it configured."""
    query_id: int
    name: str


def normalise_query_name(name: str) -> str:
    """
    Reduce a query name to a comparable form.

    Separators are levelled because the portal is not consistent about them:
    a query shown as "MyTax Trades" in the Flex Queries list appears in the
    batch summary the same way, but users name them with underscores. Matching
    on "mytax trades" makes "MyTax_Trades" and "MyTax Trades" the same
    query, which is what the person who named it meant.
    """
    return re.sub(r"[\s_-]+", " ", name.strip().lower()).strip()


def strip_name_prefix(name: str, prefix: str) -> str:
    """Remove a naming prefix like "MyTax" from a query name, if present."""
    normalised = normalise_query_name(name)
    normalised_prefix = normalise_query_name(prefix)
    if normalised_prefix and normalised.startswith(normalised_prefix):
        return normalised[len(normalised_prefix):].strip()
    return normalised


def extract_flex_queries(payload) -> list[FlexQuery]:
    """
    Pull (id, name) pairs out of the Activity Flex configuration response.

    The response is several megabytes of query definitions and its exact shape
    is not something this project can cite, so rather than depending on a path
    through it, this walks the tree for objects that carry both a query name
    and a numeric query ID. A portal release that moves them somewhere else in
    the structure does not break it.
    """
    found: dict[int, str] = {}

    def visit(node):
        if isinstance(node, dict):
            name = next((node[key] for key in ("queryName", "name")
                         if isinstance(node.get(key), str) and node[key].strip()), None)
            raw_id = next((node[key] for key in ("queryId", "id")
                           if key in node), None)
            query_id = _as_query_id(raw_id)
            if name is not None and query_id is not None:
                # First name wins: the outermost object carrying both is the
                # query itself, not a nested reference to it.
                found.setdefault(query_id, name.strip())
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return [FlexQuery(query_id, name) for query_id, name in sorted(found.items())]


def _as_query_id(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


@dataclass(frozen=True)
class ReportRequest:
    """
    One query over one date range, as asked of the portal.

    `key` is the caller's own handle — a filename, say — echoed back on the
    outcome. Nothing here reads it; it exists so the caller does not have to
    match results back by comparing dates.
    """
    key: str
    query_id: int
    from_date: date
    to_date: date
    query_name: Optional[str] = None
    query_type: str = QUERY_TYPE_ACTIVITY_FLEX
    label: str = ""

    def describe(self) -> str:
        return (self.label
                or f"query {self.query_id} for {self.from_date}..{self.to_date}")


@dataclass(frozen=True)
class ReportOutcome:
    """What became of one ReportRequest. Exactly one of csv/error is set."""
    request: ReportRequest
    csv: Optional[str] = None
    error: Optional[PortalError] = None

    @property
    def ok(self) -> bool:
        return self.csv is not None


@dataclass
class _PendingReport:
    """A queued report the collection loop is still waiting on."""
    request: ReportRequest
    pre_existing: set
    queued_at: float

    def age(self) -> float:
        return time.monotonic() - self.queued_at

    def expired(self, timeout_seconds: float) -> bool:
        return self.age() >= timeout_seconds

    def describe(self, listed, is_ours) -> str:
        statuses = sorted(entry.status_code for entry in listed
                          if is_ours(entry, self.request))
        return (f"{self.request.describe()} "
                f"({', '.join(statuses) or 'not listed yet'})")


@dataclass(frozen=True)
class BatchRequest:
    """One row of the portal's batch-statements list."""
    config_id: str
    status_code: str
    summary: str
    reason: str
    format: str

    @property
    def is_pending(self) -> bool:
        return self.status_code in _PENDING_STATUSES

    @property
    def is_ready(self) -> bool:
        return self.status_code == STATUS_SUCCESS

    def failure_description(self) -> Optional[str]:
        """A human-readable failure, or None if this is pending or ready."""
        if self.is_pending or self.is_ready:
            return None
        described = _TERMINAL_FAILURES.get(
            self.status_code, f"unknown status code {self.status_code!r}")
        return f"{described} ({self.reason})" if self.reason else described


def build_run_options(query_id: int, from_date: date, to_date: date,
                      query_type: str = QUERY_TYPE_ACTIVITY_FLEX,
                      output_format: str = "CSV") -> str:
    """
    The runOptions JSON the portal sends when a query is run by hand.

    Reproduced field for field from the recorded request, including
    filterConfig.includeDerivatives — which does not apply to Activity Flex.
    The recorded run carried it as false and the resulting Trades report still
    contained 425 option rows, so it strips nothing here; it is kept only
    because sending what the portal sends is the safer default.
    """
    return json.dumps({
        "queryId": str(query_id),
        "queryType": query_type,
        "outputFormat": output_format,
        "period": "Custom",
        "fromDate": from_date.isoformat(),
        "toDate": to_date.isoformat(),
        "noOfDays": 1,
        "filterConfig": {"includeDerivatives": False},
    }, separators=(",", ":"))


def config_id_matches(config_id: str, query_id, from_date: date,
                      to_date: date,
                      query_type: str = QUERY_TYPE_ACTIVITY_FLEX) -> bool:
    """
    Whether a batch entry is the report we asked for.

    The portal names it
    <acct>_<acct>_<from>_<to>_<queryType>_<queryId>_<hash>.<ext>, which
    identifies the run precisely. Matching on this rather than on the
    human-readable summary means a second query with the same name, or a
    different date range of the same query, cannot be mistaken for ours.

    `query_id` is normally the numeric ID; UNATTRIBUTED_QUERY_ID is passed to
    look for the entries the portal declines to attribute — see
    batch_entry_matches.
    """
    needle = (f"_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}"
              f"_{query_type}_{query_id}_")
    return needle in config_id


# What the portal puts in the query-ID slot for a report it does not attribute
# to a query. Observed live on 2026-08-06: the Options EAE run for 2022 was
# listed as ..._20220101_20221231_AF_NA_<hash>.csv, while every other report in
# the same list carried its numeric ID.
UNATTRIBUTED_QUERY_ID = "NA"


def summary_names_query(summary: str, query_name: str) -> bool:
    """
    Whether a batch entry's summary is for the named query.

    The summary is "<query name>; <account>; <from>-<to>"; only the first
    field is the name. Compared with the same separator- and case-insensitive
    rule used to resolve queries by name, because the portal is no more
    consistent here than it is there.
    """
    head = summary.split(";", 1)[0]
    return bool(query_name) and \
        normalise_query_name(head) == normalise_query_name(query_name)


def batch_entry_matches(entry: "BatchRequest", query_id: int, from_date: date,
                        to_date: date,
                        query_type: str = QUERY_TYPE_ACTIVITY_FLEX,
                        query_name: Optional[str] = None) -> bool:
    """
    Whether a batch-list entry is the report this run asked for.

    Normally the configId settles it. The exception is a report the portal
    lists with UNATTRIBUTED_QUERY_ID in place of the query ID: the account,
    date range and query type are still there, but not which query. That cost
    a whole run — an Options EAE report sat ready in the list for 843 seconds
    while the downloader reported "not in the batch list yet", and the session
    expired underneath it.

    For those, the query *name* out of the summary is required as
    corroboration. Matching on the date range alone would claim any other
    unattributed report over the same range, and writing one query's report
    into another's file is exactly the silent wrong answer this module exists
    to avoid. With no name available, the entry is left alone and the run
    times out saying what it saw.
    """
    if config_id_matches(entry.config_id, query_id, from_date, to_date,
                         query_type):
        return True

    if query_name and config_id_matches(entry.config_id, UNATTRIBUTED_QUERY_ID,
                                        from_date, to_date, query_type):
        return summary_names_query(entry.summary, query_name)

    return False


def parse_batch_requests(payload: dict) -> list[BatchRequest]:
    """Read the batch list response into BatchRequest rows."""
    if "batchStmtRequests" not in payload:
        raise PortalError(
            "Batch-statements response has no 'batchStmtRequests' field. "
            f"Fields present: {sorted(payload)}")

    return [
        BatchRequest(
            config_id=row.get("configId", ""),
            status_code=row.get("statusCode", ""),
            summary=row.get("stmtSummary", ""),
            reason=row.get("reason", ""),
            format=row.get("format", ""),
        )
        for row in payload["batchStmtRequests"]
    ]


# A Flex CSV starts with the quoted header of whichever section is enabled,
# and a header has at least two columns — so the first line contains a comma.
_CSV_START_PATTERN = re.compile(r'^\s*"?[A-Za-z][A-Za-z0-9 /_.-]*"?\s*,')

# Envelope fields known to carry the report, tried before falling back to
# detection. Observed live: FETCH_REPORT answers with
# {"fileContent", "contentType", "fileName", "fileFormat"}.
_REPORT_CONTENT_FIELDS = ("fileContent", "content", "data", "fileData")


def looks_like_csv(text: str) -> bool:
    """
    Whether a payload is the report itself rather than a JSON envelope.

    The comma has to be in the text. An earlier version appended one before
    matching, which made every short string qualify: alongside the report,
    the envelope's own "csv" and "text/csv" fields were each judged to be a
    CSV, and only a largest-wins tie-break kept the right one.
    """
    if not text or text.lstrip()[:1] in ("{", "["):
        return False
    lines = text.splitlines()
    if not lines:
        return False
    return "," in lines[0] and bool(_CSV_START_PATTERN.match(lines[0]))


def extract_report_csv(payload: str) -> str:
    """
    Get the CSV out of whatever FETCH_REPORT returned.

    The endpoint answers with content-type application/json but the field
    holding the report is not documented anywhere this project can cite, and
    the recorded response was too large to capture in full. So rather than
    hard-coding a field name that a portal release can rename, this looks for
    the payload that *is* a CSV: directly, or base64-encoded inside the
    envelope.

    Raises:
        PortalError: If no CSV can be found. It names the fields that were
            present, so the next person can see what the portal now returns
            instead of receiving a truncated or empty file.
    """
    if looks_like_csv(payload):
        return payload

    try:
        envelope = json.loads(payload)
    except ValueError as e:
        raise PortalError(
            f"FETCH_REPORT returned neither CSV nor JSON ({e}). "
            f"First 200 characters: {payload[:200]!r}") from e

    if not isinstance(envelope, dict):
        raise PortalError(
            f"FETCH_REPORT returned a JSON {type(envelope).__name__}, "
            "not an object holding a report.")

    # The field the portal actually uses, when it is there and holds a report.
    for field in _REPORT_CONTENT_FIELDS:
        value = envelope.get(field)
        if not isinstance(value, str) or not value:
            continue
        if looks_like_csv(value):
            return value
        decoded = _try_base64_csv(value)
        if decoded is not None:
            return decoded

    candidates: list[tuple[str, str]] = []
    for key, value in envelope.items():
        if not isinstance(value, str) or not value:
            continue
        if looks_like_csv(value):
            candidates.append((key, value))
            continue
        decoded = _try_base64_csv(value)
        if decoded is not None:
            candidates.append((key, decoded))

    if not candidates:
        raise PortalError(
            "FETCH_REPORT returned JSON with no field holding a CSV report. "
            f"Fields present: {sorted(envelope)}. "
            "The portal's response shape has changed; re-run "
            "`python -m src.web_portal.discover` and inspect FETCH_REPORT.")

    if len(candidates) > 1:
        # Deterministic, and loud: guessing quietly between two payloads is
        # how a truncated report gets written as if it were complete.
        names = ", ".join(name for name, _ in candidates)
        logger.warning(
            "FETCH_REPORT returned more than one CSV-like field (%s). "
            "Using the largest.", names)

    return max(candidates, key=lambda item: len(item[1]))[1]


def _try_base64_csv(value: str) -> Optional[str]:
    """Decode a base64 field if what comes out is a CSV; else None."""
    if len(value) < 16 or len(value) % 4:
        return None
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8-sig")
    except (ValueError, UnicodeDecodeError):
        return None
    return decoded if looks_like_csv(decoded) else None


class PortalFlexClient:
    """
    Issues the three portal calls over an authenticated browser session.

    Takes a transport with a `get(url, params, headers, timeout)` method —
    in a real run a PageRequestTransport, so the calls go out from the page the
    user logged into rather than from Playwright's driver. No credential passes
    through this object; the session headers come from the provider on each
    call and are never stored here.
    """

    def __init__(self, transport, base_url: str = BASE_URL,
                 headers_provider=None):
        self._request = transport
        self._base_url = base_url.rstrip("/")
        # Callable rather than a fixed dict: the portal rotates am_uuid per
        # page load, and a long download run outlives the set captured at the
        # start.
        self._headers_provider = headers_provider or (lambda: {})
        # Why the last authentication probe said no. Printed while waiting, so
        # a run that is not progressing says what it is waiting for instead of
        # sitting silent for ten minutes — which is what it did.
        self.last_probe_reason = "not probed yet"

    def _headers(self) -> dict[str, str]:
        return self._headers_provider()

    @property
    def has_am_headers(self) -> bool:
        """
        Whether a *complete* AccountManagement header set is available.

        Gating on `sessionid` alone is what let a partial set onto the wire
        even when the harvester was holding one back — see
        AmHeaderHarvester.get. One malformed request ends the session.
        """
        return not self._missing_am_headers()

    def _missing_am_headers(self) -> list[str]:
        headers = self._headers()
        return [name for name in AM_HEADER_NAMES if not headers.get(name)]

    # -- individual calls --------------------------------------------------

    def is_authenticated(self) -> bool:
        """
        Whether the portal answers the batch list as a logged-in user.

        Used to wait for a manual login without knowing what the post-login
        URL looks like: the question that matters is not which page is showing
        but whether the API this downloader needs will answer.
        """
        missing = self._missing_am_headers()
        if missing:
            # Cookies alone never satisfy this API, so asking without the
            # headers would report "not logged in" for a session that is —
            # and asking with only some of them ends the session outright.
            if len(missing) == len(AM_HEADER_NAMES):
                self.last_probe_reason = (
                    "the Account Management app has not been opened yet — "
                    "go to Performance & Reports > Flex Queries in the browser")
            else:
                # Naming them matters: the app *is* open, and telling the
                # reader to go and open it sends them to click something
                # already on screen.
                self.last_probe_reason = (
                    "the portal has not yet sent a request carrying its full "
                    "session header set; still waiting for "
                    + ", ".join(missing))
            logger.debug("Incomplete AccountManagement header set: missing %s.",
                         ", ".join(missing))
            return False

        try:
            response = self._request.get(
                f"{self._base_url}{BATCH_PATH}",
                params={"action": "FETCH_BATCH_REQUESTS", "batchReportType": "FLEX"},
                headers=self._headers(), timeout=30_000)
        except Exception as e:  # pragma: no cover - transport error
            self.last_probe_reason = f"the request could not be made: {e}"
            logger.debug("Authentication probe failed: %s", e)
            return False

        if response.status != 200:
            self.last_probe_reason = f"the portal answered HTTP {response.status}"
            logger.debug("Authentication probe: HTTP %d", response.status)
            return False
        try:
            if "batchStmtRequests" in response.json():
                self.last_probe_reason = "ok"
                return True
        except Exception:
            pass
        self.last_probe_reason = (
            "the portal answered something other than the batch list")
        logger.debug("Authentication probe: response was not the batch list.")
        return False

    def list_flex_queries(self) -> list[FlexQuery]:
        """
        Every Activity Flex query configured in the account, with its ID.

        Resolving a query by the name it has in the portal is steadier than
        pinning its numeric ID in config: recreating a query changes the ID and
        keeps the name, and a stale ID downloads someone else's report shape
        without complaining.
        """
        response = self._request.get(f"{self._base_url}{ACTIVITY_FLEX_PATH}",
                                     headers=self._headers(), timeout=120_000)
        if response.status != 200:
            raise self._error_for(response, "listing Flex queries")

        queries = extract_flex_queries(response.json())
        if not queries:
            raise PortalError(
                "The portal returned no Activity Flex queries. Either none are "
                "configured, or the response shape has changed — re-run "
                "`python -m src.web_portal.discover` to see it.")
        return queries

    def list_batch_requests(self) -> list[BatchRequest]:
        """Fetch the current batch-statements list."""
        response = self._request.get(
            f"{self._base_url}{BATCH_PATH}",
            params={"action": "FETCH_BATCH_REQUESTS", "batchReportType": "FLEX"},
            headers=self._headers(), timeout=60_000)

        if response.status != 200:
            raise self._error_for(response, "listing batch statements")
        return parse_batch_requests(response.json())

    def request_report(self, query_id: int, from_date: date, to_date: date,
                       query_type: str = QUERY_TYPE_ACTIVITY_FLEX) -> Optional[str]:
        """
        Ask the portal to run a query over a date range.

        Returns:
            The CSV, when the portal produced it immediately. None when the run
            was queued for batch processing, which is the usual answer for a
            full calendar year.
        """
        response = self._request.get(
            f"{self._base_url}{RUN_PATH}",
            params={"runOptions": build_run_options(query_id, from_date, to_date,
                                                    query_type)},
            headers=self._headers(), timeout=180_000)

        body = response.text()
        payload = None
        if body.lstrip()[:1] == "{":
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None

        # 601 is not "queued". It is "this flex request was not served", and
        # only the body says why: isBatchFlex true means queued for batch
        # processing, false means refused. Treating every 601 as queued left a
        # run polling for fifteen minutes for a report the portal had already
        # declined to produce.
        if payload is not None and payload.get("errors"):
            flex_error = str(payload["errors"].get("flexError", payload["errors"]))

            if payload.get("isBatchFlex"):
                logger.info("Query %d (%s..%s) queued for batch processing.",
                            query_id, from_date, to_date)
                return None

            if _NO_STATEMENT_MARKER in flex_error.lower():
                raise NoStatementAvailableError(
                    f"No statement for query {query_id} over "
                    f"{from_date}..{to_date}: {flex_error}")

            raise PortalError(
                f"Portal refused query {query_id} for "
                f"{from_date}..{to_date}: {flex_error}")

        if response.status == HTTP_QUEUED_FOR_BATCH:
            # Queued, with no body to confirm it. Believe the status code.
            logger.info("Query %d (%s..%s) queued for batch processing.",
                        query_id, from_date, to_date)
            return None

        if response.status != 200:
            raise self._error_for(
                response, f"running query {query_id} for {from_date}..{to_date}")

        return extract_report_csv(body)

    def fetch_report(self, config_id: str) -> str:
        """Download a finished batch report as CSV text."""
        response = self._request.get(
            f"{self._base_url}{BATCH_PATH}",
            params={"action": "FETCH_REPORT", "configId": config_id},
            headers=self._headers(), timeout=300_000)

        if response.status != 200:
            raise self._error_for(response, f"fetching report {config_id}")
        return extract_report_csv(response.text())

    # -- the whole run -----------------------------------------------------

    def run_and_collect(self, query_id: int, from_date: date, to_date: date,
                        query_type: str = QUERY_TYPE_ACTIVITY_FLEX,
                        poll_seconds: float = 10.0,
                        timeout_seconds: float = 900.0,
                        stale_failure_grace_seconds: float = STALE_FAILURE_GRACE_SECONDS,
                        query_name: Optional[str] = None,
                        sleep=time.sleep, progress=None) -> str:
        """
        Run one query over one date range and return the report as CSV.

        One report's worth of run_and_collect_many. Nothing in this package
        calls it — the downloader queues everything at once — but a single
        report is a real thing to want, and this raises rather than handing
        back an outcome to inspect.

        It delegates rather than repeating the rules. The stale-entry handling
        is subtle enough that two copies would drift, and the tests that drive
        this method are the ones covering that handling: they exercise the
        shared engine through the narrow door.

        Raises:
            PortalError: On a failed, held or undeliverable report, or when the
                report does not become ready within timeout_seconds.
        """
        request = ReportRequest("", query_id, from_date, to_date, query_name,
                                query_type)
        outcome = next(iter(self.run_and_collect_many(
            [request], poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
            stale_failure_grace_seconds=stale_failure_grace_seconds,
            sleep=sleep, progress=progress)))
        if outcome.error is not None:
            raise outcome.error
        return outcome.csv

    def run_and_collect_many(self, requests: "Iterable[ReportRequest]",
                             poll_seconds: float = 10.0,
                             timeout_seconds: float = 900.0,
                             stale_failure_grace_seconds: float = STALE_FAILURE_GRACE_SECONDS,
                             max_in_flight: int = MAX_REPORTS_IN_FLIGHT,
                             sleep=time.sleep, progress=None):
        """
        Run every request, then collect the reports as they ripen.

        Yields:
            ReportOutcome per request, in completion order, as each finishes.
            Every request yields exactly once.

        The portal queues batch jobs in parallel and its batch list reports on
        all of them at once, so asking for one report, waiting for it, and only
        then asking for the next is pure waste. Worse than waste: the portal
        ends a session after about fifteen minutes whatever the downloader is
        doing, which makes serial waiting a way to run out of session with most
        of the work never requested. That is not hypothetical — on 2026-08-06 a
        single report that could not be matched held the queue for 843 seconds
        and the session died owing twenty-four reports that had never been
        asked for.

        So: up to `max_in_flight` reports are queued at the portal at once, one
        poll of the batch list serves all of them, and a slot is refilled from
        the backlog as soon as the report holding it lands. Wall-clock becomes
        roughly the slowest report rather than the sum, and outcomes are
        yielded the moment they are settled so the caller can write each report
        to disk before anything else can go wrong.

        Not unbounded, because "as many as possible" was never the point.
        Thirty-five simultaneous batch jobs is a burst the portal has never
        been asked for and may refuse; what matters is only that report N+1
        does not wait behind report N. Reports the portal answers on the spot —
        the small snapshots and cash balances — never occupy a slot at all,
        since they are finished rather than in flight.

        Two subtleties, both about telling our run's entry from an older one.
        The configId carries no run instance — it is
        <acct>_<acct>_<from>_<to>_<queryType>_<queryId>_<hash> — so a repeat of
        the same query over the same range lands on the same string, and "an
        entry this call created" may never appear at all. Therefore a
        pre-existing *failure* is given `stale_failure_grace_seconds` to be
        superseded before it is believed, and a pre-existing *ready* report is
        used but announced, because it was not generated by this call.

        `timeout_seconds` is per report, measured from when that report was
        queued, so one slow report cannot condemn the others.
        """
        requests = list(requests)
        if not requests:
            return

        def is_ours(entry, request) -> bool:
            return batch_entry_matches(entry, request.query_id,
                                       request.from_date, request.to_date,
                                       request.query_type, request.query_name)

        # One snapshot before anything is queued, so every request can tell
        # what was already there from what it puts there.
        try:
            already_listed = self.list_batch_requests()
        except PortalError as e:
            if isinstance(e, NotAuthenticatedError):
                for request in requests:
                    yield ReportOutcome(request, error=e)
                return
            # Not fatal: without the snapshot every entry looks fresh, which
            # is the pre-2026-08 behaviour and only costs the stale-entry
            # protection.
            logger.warning("Could not read the batch list before queueing "
                           "(%s); pre-existing reports cannot be told apart "
                           "from this run's.", e)
            already_listed = []

        # -- ask for as many as may be in flight, then collect --------------
        #
        # Not all of them at once. The portal takes batch jobs in parallel,
        # but a hundred queued reports is a burst it has never been asked for
        # and has every right to refuse; MAX_REPORTS_IN_FLIGHT keeps a working
        # set going and tops it up as reports land. The point was never "all
        # at once" — it is that nothing waits its turn behind a report that
        # has nothing to do with it.
        backlog = list(requests)
        pending: list[_PendingReport] = []
        first_request = True

        def queue_more():
            """
            Fill the in-flight window from the backlog.

            Yields outcomes for anything settled on the spot: a refusal, or a
            report the portal simply hands back. Those do not occupy a slot —
            a small snapshot or cash-balance report comes straight down the
            first call with no batch job behind it, so counting it as in
            flight would throttle the run against work that is already done.
            """
            nonlocal first_request
            while backlog and len(pending) < max_in_flight:
                request = backlog.pop(0)

                # Between requests, not before the first and not after the
                # last: queueing takes minutes at this scale, and nothing else
                # here gives Playwright a chance to deliver events or the
                # session a chance to be kept awake.
                if not first_request:
                    sleep(0)
                first_request = False

                try:
                    immediate = self.request_report(
                        request.query_id, request.from_date, request.to_date,
                        request.query_type)
                except NotAuthenticatedError as e:
                    # Every remaining request would fail the same way, and
                    # each attempt is another wait for an answer that cannot
                    # come. Account for all of them, including whatever is
                    # still in flight, and stop.
                    yield ReportOutcome(request, error=e)
                    for item in pending:
                        yield ReportOutcome(item.request, error=e)
                    for other in backlog:
                        yield ReportOutcome(other, error=NotAuthenticatedError(
                            "not requested — the portal session was lost "
                            "earlier in the run"))
                    pending.clear()
                    backlog.clear()
                    return
                except PortalError as e:
                    # Includes NoStatementAvailableError, which is an answer
                    # rather than a fault; the caller tells them apart by type.
                    yield ReportOutcome(request, error=e)
                    continue

                if immediate is not None:
                    yield ReportOutcome(request, csv=immediate)
                    continue

                pending.append(_PendingReport(
                    request=request,
                    pre_existing={entry.config_id for entry in already_listed
                                  if is_ours(entry, request)},
                    queued_at=time.monotonic()))

                if progress is not None:
                    progress(f"    queued {request.describe()}")

        # -- one poll serves all of them -------------------------------------
        listed: list[BatchRequest] = []
        polls = 0
        collecting_since = time.monotonic()

        while True:
            # Top up first, so a slot freed by a finished report is refilled
            # before the next poll rather than after it. Each call drains at
            # least one item from the backlog whenever the window has room,
            # which is what makes the `continue` below terminate.
            yield from queue_more()
            if not pending:
                if backlog:
                    continue
                return

            try:
                listed = self.list_batch_requests()
            except NotAuthenticatedError as e:
                for item in pending:
                    yield ReportOutcome(item.request, error=e)
                return
            except PortalError as e:
                # The batch list answers HTTP 604 intermittently — seen twice,
                # each time succeeding on the next call. One bad answer is not
                # a reason to abandon reports that are being generated.
                logger.warning("Batch list unavailable (%s); retrying.", e)
                if all(item.expired(timeout_seconds) for item in pending):
                    for item in pending:
                        yield ReportOutcome(item.request, error=e)
                    return
                sleep(poll_seconds)
                continue

            polls += 1
            still_pending: list[_PendingReport] = []

            for item in pending:
                outcome = self._resolve_pending(
                    item, listed, is_ours, timeout_seconds,
                    stale_failure_grace_seconds, progress)
                if outcome is None:
                    still_pending.append(item)
                else:
                    yield outcome

            pending[:] = still_pending
            if not pending and not backlog:
                return

            if pending and progress is not None:
                # Truncated, and honest about it. Thirty-five pending reports
                # would print a paragraph every ten seconds, and a wall of
                # text is read as noise — but silently showing only some of
                # them would misreport how much is outstanding, so the count
                # leads and the elision is stated.
                elapsed = int(time.monotonic() - collecting_since)
                shown = [item.describe(listed, is_ours)
                         for item in pending[:_PROGRESS_MAX_NAMED]]
                if len(pending) > _PROGRESS_MAX_NAMED:
                    shown.append(f"and {len(pending) - _PROGRESS_MAX_NAMED} more")
                waiting_to_queue = (f", {len(backlog)} not yet requested"
                                    if backlog else "")
                progress(f"    waiting {elapsed}s — {len(pending)} report(s) "
                         f"generating{waiting_to_queue}: " + ", ".join(shown))

            # If nothing of ours is listed at all, show what the portal did
            # queue: the likeliest reason is that it named them differently.
            if polls % 6 == 0 and listed and not any(
                    any(is_ours(entry, item.request) for entry in listed)
                    for item in pending):
                logger.info("Batch list currently holds: %s",
                            "; ".join(entry.summary or entry.config_id
                                      for entry in listed))

            sleep(poll_seconds)

    def _resolve_pending(self, item, listed, is_ours, timeout_seconds,
                         stale_failure_grace_seconds, progress):
        """
        Decide what one pending report's entry in the batch list means.

        Returns:
            A ReportOutcome when the report is settled, or None to keep
            waiting for it.
        """
        request = item.request
        matches = [entry for entry in listed if is_ours(entry, request)]
        fresh = [entry for entry in matches
                 if entry.config_id not in item.pre_existing]
        # Prefer an entry this call created; fall back to a pre-existing one
        # only when the portal reused it rather than queueing again.
        considered = fresh or matches
        reused = not fresh and bool(matches)

        for entry in considered:
            if entry.is_ready:
                logger.info("Report ready: %s", entry.summary)
                if reused and progress is not None:
                    progress("    using the copy the portal already had; "
                             "it was not generated by this request")
                try:
                    return ReportOutcome(request, csv=self.fetch_report(
                        entry.config_id))
                except PortalError as e:
                    return ReportOutcome(request, error=e)

        failures = [entry.failure_description() for entry in considered
                    if entry.failure_description()]
        if failures and not any(entry.is_pending for entry in considered):
            # A failure under an entry this call created is decisive. One
            # under an entry that was already there is last run's, and the
            # portal has just accepted a new request against the same
            # configId — believing it straight away reports an old failure as
            # this one's, seconds after the run was queued. Give the list time
            # to catch up first.
            if not reused:
                return ReportOutcome(request, error=PortalError(
                    f"{request.describe()}: " + "; ".join(failures)))

            if item.age() >= stale_failure_grace_seconds:
                return ReportOutcome(request, error=PortalError(
                    f"{request.describe()}: " + "; ".join(failures)
                    + " — recorded against an earlier run, and unchanged "
                    f"{stale_failure_grace_seconds:.0f}s after this one was "
                    "queued, so the portal is not regenerating it. Delete the "
                    "entry in Performance & Reports > Batch Statements and run "
                    "again."))

        if item.expired(timeout_seconds):
            status_now = sorted(entry.status_code for entry in considered)
            # An entry over this exact range that the portal did not attribute
            # to a query is the likeliest reason ours "never appeared", and
            # without a name there is nothing to match it on. Say so rather
            # than leaving the reader to compare configIds by eye.
            unattributed = [
                entry for entry in listed
                if config_id_matches(entry.config_id, UNATTRIBUTED_QUERY_ID,
                                     request.from_date, request.to_date,
                                     request.query_type)]
            return ReportOutcome(request, error=PortalError(
                f"{request.describe()} did not become ready within "
                f"{timeout_seconds:.0f}s "
                f"(last status: {', '.join(status_now) or 'never listed'}). "
                + (f"The batch list holds: "
                   f"{'; '.join(entry.summary or entry.config_id for entry in listed)}. "
                   if listed and not considered else "")
                + (f"{len(unattributed)} report(s) over this exact range carry "
                   f"no query ID ({UNATTRIBUTED_QUERY_ID}) and could not be "
                   "attributed; set FLEX_QUERY_NAME_PREFIX or pass "
                   "--query-name-prefix so they can be matched by name. "
                   if unattributed and not considered and not request.query_name
                   else "")
                + "The portal keeps generating it; re-running will pick it up "
                "from the batch list."))

        return None

    # -- errors ------------------------------------------------------------

    def _error_for(self, response, context: str) -> PortalError:
        body = ""
        try:
            body = response.text()[:300]
        except Exception:  # pragma: no cover - body may be unavailable
            pass

        if response.status in (401, 403, HTTP_SESSION_REJECTED) \
                or "no_session" in body:
            # Usually not the request's fault. The portal logs itself out
            # after roughly fifteen minutes without *user* interaction, and
            # neither its own keep-alive nor a request every ten seconds
            # resets that timer — measured in the recorded run of 2026-08-06
            # 09:54, where the page called logout on itself at 10:11:00 and
            # navigated to the login screen mid-poll.
            return NotAuthenticatedError(
                f"Portal session rejected while {context} (HTTP "
                f"{response.status}). The portal ends a session after about "
                "fifteen minutes of inactivity — moving the mouse over the "
                "browser window while a long report generates keeps it alive. "
                "Log in again and re-run; reports already generated are "
                "collected from the batch list without being regenerated.")

        if response.status == HTTP_INTERNAL_ERROR:
            return PortalError(
                f"The portal failed internally while {context} (HTTP "
                f"{response.status}). This is what it answers for a request it "
                "cannot serve at all. The one time it was seen, the session "
                "was already being torn down by other requests rather than "
                "anything being wrong with this one. Response: "
                f"{body!r}")

        return PortalError(f"Portal returned HTTP {response.status} while "
                           f"{context}. Response: {body!r}")

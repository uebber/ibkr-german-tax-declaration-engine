"""
The portal recorder writes a log of a live IBKR session to disk, and that log
is the artefact a human or an agent reads while building the downloader. It
must not carry account identifiers, cookies or session tokens out of the
browser.

legal_basis: infrastructure. No declared figure depends on these assertions.
What depends on them is the standing rule that this repository is public and
account data must never reach a commit — the rule with the worst violation
record here (three cleanups after the fact). The recording directory is
gitignored; redaction is the second line of defence, and a second line nobody
tests is decoration.

These tests import only src.web_portal.recorder, which is pure text handling
with no playwright dependency, so they run in a clean clone without the
optional `web` extra.
"""
import pytest

from src.web_portal import recorder as recorder_module
from src.web_portal.recorder import (
    PortalRecorder,
    is_auth_url,
    redact,
    redact_body,
    redact_headers,
    redact_url,
    register_literal_secret,
    sanitize_html_snapshot,
)

ACCOUNT_IDS = ["U1234567", "U123456789", "DU9876543", "F1234567", "I1234567"]


@pytest.fixture(autouse=True)
def _isolate_registered_literals():
    """Literal secrets are process-global; no test may leak one into another."""
    saved = list(recorder_module._LITERAL_SECRETS)
    recorder_module._LITERAL_SECRETS.clear()
    yield
    recorder_module._LITERAL_SECRETS[:] = saved


def test_account_identifiers_are_replaced_wherever_they_appear():
    for account_id in ACCOUNT_IDS:
        text = f"Flex Queries for {account_id} (primary)"
        assert account_id not in redact(text), account_id
        assert "<ACCOUNT_ID>" in redact(text)


def test_account_id_is_redacted_when_an_underscore_follows_it():
    """
    IBKR names a generated statement <ACCT>_<ACCT>_20250101_20251231_AF_<query>
    and puts the same form in the batch-statement configId. An underscore is a
    word character, so a \\b-anchored pattern does not see the end of the
    identifier and leaves it whole. Found in a real recording, in eleven
    places, after the pattern had been called tested.
    """
    text = "configId=U1234567_U1234567_20250101_20251231_AF_1212943_a4363c1b"
    result = redact(text)

    assert "U1234567" not in result
    assert result.count("<ACCOUNT_ID>") == 2
    # The shape of the identifier is what a downloader needs to reconstruct.
    assert "20250101_20251231_AF_1212943" in result


def test_account_id_is_redacted_as_a_json_object_key():
    """The portal keys account maps by account number: {"U1234567": {...}}."""
    body = '{"aliases": {"U1234567": "my account"}, "acctProps": {"U1234567": {}}}'
    result = redact_body(body)

    assert "U1234567" not in result


def test_redaction_does_not_swallow_ordinary_identifiers():
    """Query IDs and dates are the payload of a recording; they must survive."""
    text = "queryId=1212943 fromDate=20210101 toDate=20211231 section=TRADES"
    assert redact(text) == text


def test_redact_url_withholds_secret_values_and_keeps_parameter_names():
    url = ("https://www.interactivebrokers.com/AccountManagement/run"
           "?queryId=1212943&token=abcdef0123456789&fromDate=20210101")
    result = redact_url(url)

    assert "abcdef0123456789" not in result
    assert "token=<redacted:16>" in result
    # The names and the non-secret values are what make the log usable.
    assert "queryId=1212943" in result
    assert "fromDate=20210101" in result


def test_redact_headers_withholds_credentials_but_records_their_presence():
    headers = {
        "Cookie": "JSESSIONID=deadbeefcafe; XYZAB=1234",
        "Authorization": "Bearer sometokenvalue",
        "X-CSRF-Token": "csrf-value-here",
        "Content-Type": "application/json",
        "Referer": "https://www.interactivebrokers.com/portal/U1234567",
    }
    result = redact_headers(headers)

    assert "deadbeefcafe" not in str(result)
    assert "sometokenvalue" not in str(result)
    assert "csrf-value-here" not in str(result)
    # Presence is still visible: it tells us the call was authenticated.
    assert result["Cookie"].startswith("<withheld:")
    assert result["Content-Type"] == "application/json"
    assert "U1234567" not in result["Referer"]


def test_redact_headers_withholds_credentials_it_was_never_told_about():
    """
    The portal authenticates its AccountManagement API with a `sessionid`
    header — a bearer credential in a header name no list here anticipated,
    and it went into a recording in the clear. Header names are matched by
    pattern for that reason.
    """
    headers = {
        "sessionid": "69XHW0D4kNebXYfyR7Q75dlib6QoX2eN26GSEW7iPKlokP9SK7B7HRto",
        "am_uuid": "3c99c2df-44d1-4a13-8875-d854407bcff3",
        "accounthash": "1484312398",
        "active_context": "AM_DEPENDENCY",
    }
    result = redact_headers(headers)

    assert "69XHW0D4kNebXYfyR7Q75dlib6QoX2eN26GSEW7iPKlokP9SK7B7HRto" not in str(result)
    assert result["sessionid"].startswith("<withheld:")
    # Non-secret routing headers stay readable: they are what makes the
    # recording usable for writing the downloader.
    assert result["active_context"] == "AM_DEPENDENCY"
    assert result["am_uuid"] == "3c99c2df-44d1-4a13-8875-d854407bcff3"


def test_redact_body_keeps_json_structure_while_withholding_secrets():
    body = ('{"acctId": "U1234567", "csrfToken": "CSRF-SECRET-9876", '
            '"queryId": 1212943, "fromDate": "20210101", "toDate": "20211231"}')
    result = redact_body(body)

    assert "U1234567" not in result
    assert "CSRF-SECRET-9876" not in result
    # The request shape is the whole reason to record the body.
    assert '"queryId": 1212943' in result
    assert '"fromDate": "20210101"' in result


def test_redact_body_withholds_form_encoded_credentials():
    """
    The shape an HTML login form posts. This is the case that made the
    difference: before form bodies were handled field by field, a password in
    a urlencoded body passed straight through the JSON-only filter and into
    the log.
    """
    body = "user_name=someone&password=hunter2&csrfToken=abc123&acctId=U1234567"
    result = redact_body(body)

    assert "hunter2" not in result
    assert "abc123" not in result
    assert "U1234567" not in result
    assert "password=<redacted:7>" in result


def test_redact_body_handles_non_json_payloads():
    body = "acctId=U1234567&queryId=1212943"
    result = redact_body(body)

    assert "U1234567" not in result
    assert "queryId=1212943" in result


@pytest.mark.parametrize("url", [
    "https://www.interactivebrokers.com/sso/Login",
    "https://www.interactivebrokers.com/portal/auth/challenge",
    "https://www.interactivebrokers.com/AccountManagement/api/session",
    "https://www.interactivebrokers.com/portal.proxy/v1/2fa/verify",
    "https://www.interactivebrokers.com/signin?next=/portal",
])
def test_authentication_urls_are_recognised(url):
    """
    Bodies of these are dropped whole rather than filtered: a login form can
    name its password field anything, so a name-based filter is not a defence.
    """
    assert is_auth_url(url)


@pytest.mark.parametrize("url", [
    "https://www.interactivebrokers.com/AccountManagement/FlexQuery/run",
    "https://www.interactivebrokers.com/AccountManagement/statements/download",
])
def test_report_urls_are_not_treated_as_authentication(url):
    """Over-matching here would blank the request shapes we need to learn."""
    assert not is_auth_url(url)


def test_registered_username_is_redacted_everywhere():
    register_literal_secret("chris.example", "<PORTAL_USERNAME>")

    assert "chris.example" not in redact("welcome back chris.example")
    assert "chris.example" not in redact_url(
        "https://x.example/portal?user=chris.example")
    assert "chris.example" not in redact_body('{"user": "chris.example"}')
    assert "<PORTAL_USERNAME>" in redact("hello chris.example")


def test_short_literals_are_refused_as_secrets():
    """A two-character literal would match half the log and destroy it."""
    register_literal_secret("ab", "<NOPE>")
    register_literal_secret("", "<NOPE>")

    assert redact("abacus and a blank") == "abacus and a blank"


def test_redact_body_truncates_long_payloads_but_keeps_the_head():
    """
    Truncated, not dropped, and the total size is stated. A large JSON response
    carries its field names at the front, and those are what the downloader is
    written from — the FETCH_REPORT envelope went unrecorded once because a
    body over the cap was discarded whole instead of clipped.
    """
    body = '{"fileName": "report.csv", "data": "' + "x" * 500_000 + '"}'
    result = redact_body(body)

    assert len(result) < 30_000
    assert "truncated" in result
    assert "500" in result            # the real size is stated
    assert "fileName" in result       # the head survived


def test_redaction_is_idempotent():
    once = redact("account U1234567")
    assert redact(once) == once


def test_snapshot_blanks_credential_fields_but_keeps_the_date_range():
    """
    A DOM snapshot taken with a login form filled in would otherwise put the
    password on disk. The custom date range in the same page is exactly what
    the snapshot exists to capture, and must survive.
    """
    html = (
        '<form>'
        '<input type="text" name="user_name" value="someone">'
        '<input type="password" name="password" value="hunter2">'
        '<input type="text" name="otpCode" value="483927">'
        "<input type='text' id='fromDate' value='2021-01-01'>"
        '<input type="text" id="toDate" value="2021-12-31">'
        '</form>')
    result = sanitize_html_snapshot(html)

    assert "hunter2" not in result
    assert "483927" not in result
    assert result.count("<withheld>") == 2
    assert 'value="2021-12-31"' in result
    assert "value='2021-01-01'" in result


def test_snapshot_sanitising_leaves_ordinary_markup_untouched():
    html = '<table><tr><td>Trades</td><td>1212943</td></tr></table>'
    assert sanitize_html_snapshot(html) == html


def test_summary_and_log_carry_no_account_identifier(tmp_path):
    """
    End-to-end over the two files that leave the recording directory by hand:
    whatever a marker is given, neither network.jsonl nor summary.md may show
    an account number.
    """
    recorder = PortalRecorder(tmp_path)
    recorder.marker("running Trades for U1234567 2021")
    recorder.close()
    summary = recorder.write_summary()

    log_text = (tmp_path / "network.jsonl").read_text()
    summary_text = summary.read_text()

    assert "U1234567" not in log_text
    assert "U1234567" not in summary_text
    assert "<ACCOUNT_ID>" in log_text
    assert "<ACCOUNT_ID>" in summary_text


def test_events_after_close_are_dropped_not_raised(tmp_path):
    """
    The browser keeps emitting events after the recording is closed off, and
    those handlers run inside Playwright's event dispatch — a write to a closed
    file there surfaces as a stack trace at the end of a run that otherwise
    succeeded.
    """
    recorder = PortalRecorder(tmp_path)
    recorder.marker("before")
    recorder.close()

    recorder.marker("after")      # must not raise
    recorder.close()              # idempotent

    log = (tmp_path / "network.jsonl").read_text()
    assert "before" in log
    assert "after" not in log

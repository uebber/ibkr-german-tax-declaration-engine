"""
Records what the IBKR portal actually does, so the downloader can be written
against observed facts rather than a guess at the portal's structure.

Everything written here is redacted on the way out: no cookies, no bearer
tokens, no account identifiers, and nothing at all from a request that carries
a login. The recording still lands in a gitignored directory, because redaction
is a second line of defence and not a licence to publish. Downloaded statements
are account data in full and are kept apart from the log.

**The password is never written, in any form.** It is typed by the user
straight into the browser, this project never asks for it, and the bodies of
authentication requests are dropped whole rather than filtered — a filter has
to recognise the field name to withhold it, and a login form this code has
never seen can name that field anything.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Header names never written to disk. Recorded as present-but-withheld so the
# log still shows which requests were authenticated.
_SECRET_HEADERS = {
    "cookie", "set-cookie", "authorization", "proxy-authorization",
    "x-csrf-token", "x-xsrf-token", "x-auth-token", "x-session-id",
}

# Query-parameter, form-field and JSON-key names whose values are withheld.
_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(token|passw|pwd|secret|csrf|xsrf|sessionid|session_id|jsessionid|"
    r"cookie|apikey|api_key|credential|otp|challenge|signature|pin\b|"
    r"security_?(answer|question)|two_?factor|second_?factor)")

# URLs whose request bodies are dropped in full rather than filtered. A login
# form can name its password field anything, so recognising field names is not
# a defence here; not recording the body at all is.
_AUTH_URL_PATTERN = re.compile(
    r"(?i)(login|logon|signin|sign-in|auth|sso|session|challenge|"
    r"twofactor|two-factor|2fa|mfa|otp|verify|credential|password)")

# IBKR account identifiers: U1234567 (live), DU1234567 (paper), F/I prefixed
# institutional forms. Replaced wherever they appear, including inside bodies.
#
# Not \b-anchored. IBKR names a generated statement
# <ACCT>_<ACCT>_20250101_20251231_AF_<queryId>_<hash>.csv and repeats that form
# in the batch-statement configId; an underscore is a word character, so \b
# does not see the end of the identifier and a \b-anchored pattern walks past
# the whole thing. A trailing digit is the only continuation that means this is
# not an account number.
_ACCOUNT_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])((?:DU|DF|U|F|I)\d{6,10})(?!\d)")

# Resource types with no bearing on how a report is requested.
_IGNORED_RESOURCE_TYPES = {"image", "font", "stylesheet", "media", "manifest"}

# Third-party telemetry that would otherwise dominate the log.
_IGNORED_HOST_PATTERN = re.compile(
    r"(?i)(google-analytics|googletagmanager|doubleclick|adservice|"
    r"facebook\.|hotjar|newrelic|nr-data\.net|optimizely|qualtrics|"
    r"sentry\.io|cloudflareinsights)")

# Response bodies are captured when structured. A large body is truncated to a
# prefix rather than dropped: dropping it is a silent cap, and this one cost a
# session. The FETCH_REPORT response that carries a finished statement was
# 538 KB and went unrecorded, so the shape of the envelope holding the CSV —
# the one thing a downloader has to know — had to be inferred from its size.
_BODY_CONTENT_TYPES = ("json", "xml", "javascript", "text/plain", "text/html")
_MAX_BODY_BYTES = 8_000_000
_BODY_PREVIEW_CHARS = 20_000


# Literal strings known to this session that must never be written — the
# portal username, if one is configured. Registered at runtime, because the
# value is personal data this repository does not contain.
_LITERAL_SECRETS: list[tuple[str, str]] = []


def register_literal_secret(value: Optional[str], placeholder: str) -> None:
    """
    Have every recorded string with `value` in it rewritten to `placeholder`.

    Short values are refused: a two-character literal would match half the log
    and destroy the recording it is meant to protect.
    """
    if not value or len(value.strip()) < 3:
        return
    entry = (value.strip(), placeholder)
    if entry not in _LITERAL_SECRETS:
        _LITERAL_SECRETS.append(entry)


def redact(text: Optional[str]) -> Optional[str]:
    """Remove registered literals and account identifiers. Idempotent."""
    if text is None:
        return None
    for value, placeholder in _LITERAL_SECRETS:
        text = text.replace(value, placeholder)
    return _ACCOUNT_ID_PATTERN.sub("<ACCOUNT_ID>", text)


def redact_url(url: str) -> str:
    """
    Redact secret-looking query-parameter values, keeping parameter names.

    The names are the interesting part: they tell us what the endpoint expects.
    """
    if "?" not in url:
        return redact(url)

    base, _, query = url.partition("?")
    parts = []
    for pair in query.split("&"):
        name, sep, value = pair.partition("=")
        if sep and value and _SECRET_KEY_PATTERN.search(name):
            parts.append(f"{name}=<redacted:{len(value)}>")
        else:
            parts.append(pair)
    return redact(f"{base}?{'&'.join(parts)}")


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Withhold secret headers, keeping their names and value lengths.

    Matched by pattern as well as by name. The exact-name list alone let the
    portal's `sessionid` header — a bearer credential for the whole
    AccountManagement API, in a header this project had never heard of —
    through into the log verbatim. A list of names only protects against the
    names someone thought of.
    """
    out = {}
    for name, value in headers.items():
        if name.lower() in _SECRET_HEADERS or _SECRET_KEY_PATTERN.search(name):
            out[name] = f"<withheld:{len(value)}>"
        else:
            out[name] = redact(value)
    return out


def redact_body(body: Optional[str]) -> Optional[str]:
    """
    Redact a request or response body, then truncate it.

    JSON bodies are walked key by key and form-encoded bodies field by field,
    so secret-looking values are withheld without destroying the structure that
    makes the recording useful; anything else is redacted as text.
    """
    if body is None:
        return None

    stripped = body.lstrip()
    if stripped[:1] in ("{", "["):
        try:
            return _truncate(json.dumps(_redact_json(json.loads(body)), indent=None))
        except (ValueError, TypeError):
            pass

    if _looks_form_encoded(body):
        return _truncate(_redact_form_pairs(body))

    return _truncate(redact(body))


def _looks_form_encoded(body: str) -> bool:
    """A single-line `a=1&b=2` payload — the shape an HTML form posts."""
    return "=" in body and "\n" not in body.strip() and len(body) < _MAX_BODY_BYTES


def _redact_form_pairs(body: str) -> str:
    """
    Withhold the values of secret-looking fields in a form-encoded body.

    This is a filter, and a filter only catches field names it recognises —
    which is why bodies of authentication requests are dropped entirely
    upstream of it rather than relying on this.
    """
    parts = []
    for pair in body.split("&"):
        name, sep, value = pair.partition("=")
        if sep and value and _SECRET_KEY_PATTERN.search(name):
            parts.append(f"{name}=<redacted:{len(value)}>")
        else:
            parts.append(redact(pair))
    return "&".join(parts)


def _redact_json(node: Any) -> Any:
    if isinstance(node, dict):
        # Keys are redacted too: the portal keys its account maps by account
        # number, so {"U1234567": {...}} carries the identifier in the key.
        return {
            redact(str(key)): (f"<redacted:{len(str(value))}>"
                               if _SECRET_KEY_PATTERN.search(str(key))
                               else _redact_json(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_redact_json(item) for item in node]
    if isinstance(node, str):
        return redact(node)
    return node


def _truncate(text: str) -> str:
    if len(text) <= _BODY_PREVIEW_CHARS:
        return text
    return text[:_BODY_PREVIEW_CHARS] + f"\n<truncated: {len(text)} chars total>"


# Input fields whose value is blanked out of a saved DOM snapshot.
_CREDENTIAL_INPUT_HINT = re.compile(
    r"""(?ix)
    type \s* = \s* ["']? password
  | autocomplete \s* = \s* ["']? (current|new) - password
  | (name|id|placeholder) \s* = \s* ["'][^"']* (passw|pwd|otp|pin|secret|token)
    """)
_INPUT_TAG_PATTERN = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
_VALUE_ATTR_PATTERN = re.compile(
    r"""\bvalue\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.IGNORECASE | re.DOTALL)


def sanitize_html_snapshot(html: str) -> str:
    """
    Blank the value of any credential-looking input before a DOM is saved.

    Serialising a live page can carry a filled-in login form to disk. Values of
    ordinary fields — the custom date range, above all — are kept, because they
    are the point of taking the snapshot.

    This is defence in depth over a page's *form state*. A page that writes a
    credential into its own markup is outside what any scrub can reach, which
    is why the instruction to snapshot comes after login, never during it.
    """
    def scrub(match: "re.Match[str]") -> str:
        tag = match.group(0)
        if not _CREDENTIAL_INPUT_HINT.search(tag):
            return tag
        return _VALUE_ATTR_PATTERN.sub(
            lambda v: f'value={v.group("quote")}<withheld>{v.group("quote")}', tag)

    return _INPUT_TAG_PATTERN.sub(scrub, html)


def is_auth_url(url: str) -> bool:
    """Whether a URL may be carrying credentials, judged conservatively."""
    return bool(_AUTH_URL_PATTERN.search(url))


def _is_interesting(url: str, resource_type: str) -> bool:
    if resource_type in _IGNORED_RESOURCE_TYPES:
        return False
    return not _IGNORED_HOST_PATTERN.search(url)


class PortalRecorder:
    """
    Streams a redacted log of portal traffic, downloads and DOM snapshots.

    Entries are appended to network.jsonl as they happen, so a crashed or
    force-quit session still leaves everything recorded up to that point.
    """

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.downloads_dir = out_dir / "downloads"
        self.snapshots_dir = out_dir / "snapshots"
        for directory in (self.out_dir, self.downloads_dir, self.snapshots_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self._log_path = out_dir / "network.jsonl"
        self._log = self._log_path.open("a", encoding="utf-8")
        self._seq = 0
        self.entries: list[dict] = []
        self._pending_bodies: dict[str, str] = {}

    # -- recording ---------------------------------------------------------

    def _emit(self, kind: str, **fields) -> dict:
        if self._log.closed:
            # Events keep arriving from a browser that is still open after the
            # recording has been closed off. Dropping them is right; letting
            # the write fail raises inside Playwright's event dispatch, which
            # surfaces as a stack trace after an otherwise successful run.
            return {}

        self._seq += 1
        entry = {
            "seq": self._seq,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            **fields,
        }
        self.entries.append(entry)
        self._log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._log.flush()
        return entry

    def marker(self, label: str) -> None:
        """Record a labelled point in time, to correlate clicks with traffic."""
        self._emit("marker", label=redact(label))
        logger.info("Marker: %s", label)

    def attach(self, context) -> None:
        """Subscribe to a browser context's traffic, pages and downloads."""
        context.on("request", self._on_request)
        context.on("response", self._on_response)
        context.on("requestfailed", self._on_request_failed)
        context.on("page", self._on_page)
        for page in context.pages:
            self._on_page(page)

    def _on_page(self, page) -> None:
        self._emit("page_opened", url=redact_url(page.url))
        page.on("download", self._on_download)
        page.on("framenavigated", lambda frame: (
            self._emit("navigation", url=redact_url(frame.url),
                       main_frame=frame.parent_frame is None)
            if _is_interesting(frame.url, "document") else None))
        page.on("popup", lambda popup: self._emit("popup", url=redact_url(popup.url)))

    def _on_request(self, request) -> None:
        if not _is_interesting(request.url, request.resource_type):
            return
        if is_auth_url(request.url):
            # Credentials may be in here. Nothing about how a *report* is
            # requested is, so there is nothing to trade off.
            post_data = "<withheld: authentication request>"
        else:
            try:
                post_data = redact_body(request.post_data)
            except Exception:  # pragma: no cover - body not always retrievable
                post_data = None

        self._emit(
            "request",
            method=request.method,
            url=redact_url(request.url),
            resource_type=request.resource_type,
            headers=redact_headers(request.headers),
            post_data=post_data,
        )

    def _on_response(self, response) -> None:
        request = response.request
        if not _is_interesting(response.url, request.resource_type):
            return

        headers = response.all_headers()
        entry_fields = {
            "status": response.status,
            "method": request.method,
            "url": redact_url(response.url),
            "resource_type": request.resource_type,
            "content_type": headers.get("content-type"),
            "content_disposition": headers.get("content-disposition"),
        }

        body = self._maybe_body(response, headers, request.resource_type)
        if body is not None:
            entry_fields["body"] = body

        self._emit("response", **entry_fields)

    def _maybe_body(self, response, headers: dict[str, str],
                    resource_type: str) -> Optional[str]:
        """
        Capture small, structured response bodies only.

        Attachments are skipped: reading them here would compete with the
        browser's own download of the statement, and the file itself is saved
        separately.
        """
        if resource_type not in ("xhr", "fetch", "document", "script", "other"):
            return None
        if "attachment" in (headers.get("content-disposition") or "").lower():
            return None
        if is_auth_url(response.url):
            # A login response can echo the form it was sent. Same rule as the
            # request side: drop it, do not filter it.
            return "<withheld: authentication response>"

        content_type = (headers.get("content-type") or "").lower()
        if not any(marker in content_type for marker in _BODY_CONTENT_TYPES):
            return None

        length = headers.get("content-length")
        if length and length.isdigit() and int(length) > _MAX_BODY_BYTES:
            return f"<body not read: {length} bytes>"

        try:
            raw = response.body()
        except Exception as e:  # pragma: no cover - body may already be gone
            return f"<body unavailable: {e}>"

        # Truncated, never dropped: the head of a large JSON response is where
        # its field names are, and those are what a downloader is written from.
        return redact_body(raw.decode("utf-8", errors="replace"))

    def _on_request_failed(self, request) -> None:
        if not _is_interesting(request.url, request.resource_type):
            return
        self._emit("request_failed", method=request.method,
                   url=redact_url(request.url),
                   failure=redact(request.failure))

    def _on_download(self, download) -> None:
        suggested = download.suggested_filename
        target = self.downloads_dir / suggested
        counter = 1
        while target.exists():
            target = self.downloads_dir / f"{target.stem}__{counter}{target.suffix}"
            counter += 1
        try:
            download.save_as(target)
            size = target.stat().st_size
        except Exception as e:  # pragma: no cover - download may be cancelled
            self._emit("download_failed", url=redact_url(download.url),
                       suggested_filename=suggested, error=str(e))
            return

        # The file keeps its real name on disk — it is the artefact, and the
        # name is how the portal identifies it. The log gets the redacted form,
        # which still shows the pattern: <ACCOUNT_ID>_<ACCOUNT_ID>_<from>_<to>_
        # AF_<queryId>_<hash>.csv.
        self._emit("download", url=redact_url(download.url),
                   suggested_filename=redact(suggested),
                   saved_as=redact(str(target.relative_to(self.out_dir))),
                   bytes=size)
        logger.info("Saved download %s (%d bytes)", target, size)

    # -- snapshots ---------------------------------------------------------

    def snapshot(self, page, label: str) -> None:
        """
        Save the current DOM and a screenshot of a page.

        Credential fields are blanked out of the DOM. The screenshot is a
        picture of whatever is on screen: take snapshots after logging in, not
        during, and never with a password revealed.
        """
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label) or "snapshot"
        stem = f"{self._seq + 1:04d}_{safe}"

        html_path = self.snapshots_dir / f"{stem}.html"
        html_path.write_text(
            sanitize_html_snapshot(redact(page.content())), encoding="utf-8")

        png_path = self.snapshots_dir / f"{stem}.png"
        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception as e:  # pragma: no cover - screenshots can time out
            logger.warning("Screenshot failed: %s", e)
            png_path = None

        self._emit("snapshot", label=label, url=redact_url(page.url),
                   html=str(html_path.relative_to(self.out_dir)),
                   screenshot=str(png_path.relative_to(self.out_dir)) if png_path else None)
        logger.info("Snapshot saved: %s", html_path)

    # -- output ------------------------------------------------------------

    def close(self) -> None:
        """Stop recording. Idempotent; later events are dropped."""
        if not self._log.closed:
            self._log.close()

    def write_summary(self) -> Path:
        """
        Write summary.md: the log reduced to what a downloader has to know.

        Static assets and repeated polling noise are dropped; markers,
        navigations, downloads and API-shaped calls are kept in order.
        """
        lines = [
            "# IBKR portal discovery session",
            "",
            f"Recorded {len(self.entries)} events. "
            f"Full redacted log: `{self._log_path.name}`.",
            "",
            "Account identifiers are replaced with `<ACCOUNT_ID>`; cookies and "
            "tokens are withheld. Downloaded statements under `downloads/` are "
            "NOT redacted — they are account data.",
            "",
            "## Timeline",
            "",
        ]

        for entry in self.entries:
            kind = entry["kind"]
            if kind == "marker":
                lines.append("")
                lines.append(f"### MARK: {entry['label']}")
                lines.append("")
            elif kind == "navigation" and entry.get("main_frame"):
                lines.append(f"- NAV  {entry['url']}")
            elif kind == "download":
                lines.append(f"- **DOWNLOAD** `{entry['suggested_filename']}` "
                             f"({entry['bytes']} bytes) from {entry['url']}")
            elif kind == "download_failed":
                lines.append(f"- **DOWNLOAD FAILED** {entry['url']}: {entry['error']}")
            elif kind == "snapshot":
                lines.append(f"- SNAP `{entry['html']}` at {entry['url']}")
            elif kind == "response" and entry.get("resource_type") in ("xhr", "fetch"):
                lines.append(f"- {entry['method']} {entry['status']} {entry['url']}")
                if entry.get("content_disposition"):
                    lines.append(f"    - content-disposition: {entry['content_disposition']}")
            elif kind == "request_failed":
                lines.append(f"- FAILED {entry['method']} {entry['url']}: {entry['failure']}")

        lines.append("")
        lines.append("## Request bodies of XHR calls")
        lines.append("")
        for entry in self.entries:
            if entry["kind"] == "request" and entry.get("post_data") \
                    and entry.get("resource_type") in ("xhr", "fetch"):
                lines.append(f"### {entry['method']} {entry['url']}")
                lines.append("")
                lines.append("```")
                lines.append(entry["post_data"])
                lines.append("```")
                lines.append("")

        summary_path = self.out_dir / "summary.md"
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return summary_path

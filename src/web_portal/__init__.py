"""
Browser automation against the IBKR Client Portal.

The Flex Web Service API (src/flex_downloader.py) only serves roughly the last
two calendar years. Everything older has to come out of the portal by hand
today — README, "Manual Download (Required for Older Years)". This package
drives that same procedure in a real browser.

Nothing here is legally relevant: it moves bytes from the portal into
data_import/ under the naming scheme, and never interprets them.

Requires the optional dependency group:

    uv sync --extra web
"""

PLAYWRIGHT_MISSING_MESSAGE = (
    "Playwright is not installed. The IBKR portal downloader needs it:\n"
    "    uv sync --extra web\n"
    "If Google Chrome is not installed on this machine, also run:\n"
    "    uv run playwright install chromium"
)


def require_playwright():
    """
    Import playwright's sync API, or fail with an actionable message.

    Returns:
        The playwright.sync_api module.

    Raises:
        RuntimeError: If playwright is not installed.
    """
    try:
        from playwright import sync_api
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(PLAYWRIGHT_MISSING_MESSAGE) from e
    return sync_api

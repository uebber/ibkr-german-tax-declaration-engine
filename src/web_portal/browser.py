"""
Persistent, headed browser sessions for the IBKR Client Portal.

Login is deliberately manual: IBKR requires two-factor authentication, and this
project stores no password. The browser profile lives in a gitignored directory
so that a session survives between runs for as long as IBKR keeps it alive, and
so that no cookie can reach a commit.

The profile is launched with Chrome's password manager and autofill switched
off. Without that, Chrome offers to save the password after a manual login and
writes it into the profile directory — putting on disk precisely the one thing
that must never land there.
"""

import json
import logging
import shutil
from contextlib import contextmanager
from itertools import cycle
from pathlib import Path
from typing import Iterator, Optional

from src.web_portal import require_playwright

logger = logging.getLogger(__name__)

# The portal entry point documented in the README. IBKR serves several regional
# hostnames; --portal-url overrides this.
DEFAULT_PORTAL_URL = "https://www.interactivebrokers.com/portal"

# Gitignored (private/ is in .gitignore). Holds cookies and a logged-in session:
# it must never be committed and never be shared.
DEFAULT_PROFILE_DIR = Path("private/portal_profile")

# Chrome preferences that keep the password off the disk. Seeded into the
# profile before the browser starts; Chrome preserves unknown-to-us settings
# around them because the existing file is merged, not replaced.
_NO_PASSWORD_STORAGE_PREFS = {
    "credentials_enable_service": False,
    "credentials_enable_autosignin": False,
    "profile": {
        "password_manager_enabled": False,
        "password_manager_leak_detection": False,
    },
    "autofill": {
        "profile_enabled": False,
        "credit_card_enabled": False,
    },
}

_NO_PASSWORD_STORAGE_ARGS = [
    # Never hand a credential to the macOS Keychain or a Linux secret service.
    "--password-store=basic",
    "--disable-features=PasswordManagerEnableAccountStore,PasswordLeakDetection,"
    "AutofillServerCommunication",
    "--disable-save-password-bubble",
]


def _merge(base: dict, overrides: dict) -> dict:
    """Recursively apply `overrides` onto `base`, returning `base`."""
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def disable_password_storage(profile_dir: Path) -> None:
    """
    Turn off Chrome's password manager and autofill in a profile directory.

    Safe to call on a profile that does not exist yet, and on one that already
    does: existing preferences are read and merged rather than overwritten.
    """
    prefs_path = profile_dir / "Default" / "Preferences"
    prefs_path.parent.mkdir(parents=True, exist_ok=True)

    prefs = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            # A corrupt preferences file must not silently leave the password
            # manager enabled; start from a known-good minimal file instead.
            logger.warning("Could not read %s (%s). Rewriting it.", prefs_path, e)
            prefs = {}

    prefs_path.write_text(
        json.dumps(_merge(prefs, _NO_PASSWORD_STORAGE_PREFS)), encoding="utf-8")


def reset_profile(profile_dir: Path = DEFAULT_PROFILE_DIR) -> bool:
    """
    Delete a saved browser profile, so the next run starts from a clean login.

    The portal can get stuck answering "Your Session Has Expired" for every
    request when the profile holds cookies it no longer accepts — a state a
    fresh login does not clear, because the stale cookies are sent again.

    Only ever removes the profile directory, which holds nothing but browser
    session state and is gitignored. Refuses anything that does not look like
    one, rather than deleting whatever path it is handed.

    Returns:
        True if a profile was removed, False if there was nothing to remove.
    """
    if not profile_dir.exists():
        logger.info("No browser profile at %s; nothing to reset.", profile_dir)
        return False

    if not (profile_dir / "Default").exists():
        raise RuntimeError(
            f"{profile_dir} does not look like a browser profile (no Default/ "
            "directory). Refusing to delete it.")

    shutil.rmtree(profile_dir)
    logger.info("Removed browser profile %s. The next run needs a fresh login.",
                profile_dir)
    return True


@contextmanager
def portal_session(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    headless: bool = False,
    slow_mo_ms: int = 0,
    channel: Optional[str] = "chrome",
) -> Iterator[tuple[object, object]]:
    """
    Open a persistent browser context against the IBKR portal.

    Args:
        profile_dir: Directory holding the browser profile (cookies, session).
        headless: Run without a visible window. Login needs a visible window.
        slow_mo_ms: Delay between browser operations, for watching a run.
        channel: Browser channel to prefer ("chrome"). Falls back to
            Playwright's bundled Chromium when the channel is unavailable.

    Yields:
        (playwright, context) — the context is a persistent BrowserContext.
    """
    sync_api = require_playwright()

    profile_dir.mkdir(parents=True, exist_ok=True)
    disable_password_storage(profile_dir)
    logger.info("Using browser profile %s (password storage disabled)", profile_dir)

    launch_kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "accept_downloads": True,
        # A real window rather than Playwright's default 1280x720 viewport:
        # the portal's Flex Query table collapses at small widths.
        "no_viewport": True,
        "args": ["--start-maximized", *_NO_PASSWORD_STORAGE_ARGS],
        "slow_mo": slow_mo_ms,
    }

    with sync_api.sync_playwright() as playwright:
        context = None
        channel_error = None
        if channel:
            try:
                context = playwright.chromium.launch_persistent_context(
                    channel=channel, **launch_kwargs
                )
                logger.info("Launched browser channel '%s'.", channel)
            except sync_api.Error as e:
                channel_error = e
                logger.warning(
                    "Browser channel '%s' unavailable (%s). "
                    "Falling back to Playwright's bundled Chromium.", channel, e)

        if context is None:
            try:
                context = playwright.chromium.launch_persistent_context(**launch_kwargs)
                logger.info("Launched bundled Chromium.")
            except sync_api.Error as e:
                # Playwright's own message here is a wall of stack trace ending
                # in an executable path. Say what to do instead.
                raise RuntimeError(
                    "No browser could be started.\n"
                    + (f"Channel '{channel}' failed: {channel_error}\n"
                       if channel_error else "")
                    + f"Bundled Chromium failed: {e}\n"
                    "Fix either one:\n"
                    "  - install Google Chrome, or\n"
                    "  - run: uv run --extra web playwright install chromium"
                ) from e

        try:
            yield playwright, context
        finally:
            context.close()


# How often to generate activity while waiting. The portal was seen logging
# itself out fifteen and a half minutes after the last interaction, so this has
# a wide margin; the cost of a nudge is one synthetic mouse move.
ACTIVITY_INTERVAL_SECONDS = 45.0

# Two positions near the top-left, alternated. Movement is what registers; the
# pointer must not settle anywhere that matters, and it never clicks.
_NUDGE_POSITIONS = cycle(((6, 6), (7, 7)))


def nudge_activity(page) -> None:
    """
    Reset the portal's inactivity timer with a synthetic mouse move.

    The Client Portal ends a session after about fifteen minutes without user
    input, and *nothing this downloader does over the network counts*. In the
    recorded run of 2026-08-06 09:54 the portal's own keep-alive
    (`portal.proxy/v1/portal/tickle`) fired 32 times at 30-second intervals and
    a batch-list request went out every 10 seconds; at 10:11:00, fifteen and a
    half minutes after the last interaction, the page called `portal/logout`,
    `ibcust/logout` and `sso/Logout` on itself, navigated to the login screen,
    and the next request was answered 603. Twenty-four reports were lost.

    A mouse *move* rather than a click: the pointer is over the portal's own
    UI, and a click lands on whatever is beneath it — a Run button, a delete
    icon. Movement is enough to count as activity and can actuate nothing.

    Best effort. A page that has gone away is not worth an exception: the cost
    of a missed nudge is a session that eventually expires, and the run
    reports that clearly when it happens. The cost of raising here is losing
    the reports already collected.
    """
    try:
        if page is None or page.is_closed():
            return
        page.mouse.move(*next(_NUDGE_POSITIONS))
    except Exception as e:      # pragma: no cover - page can die mid-nudge
        logger.debug("Could not nudge the page to keep the session alive: %s", e)


def open_portal(context, portal_url: str = DEFAULT_PORTAL_URL):
    """
    Bring up the portal in the context's first page and return that page.

    Does not wait for login: the caller decides how login is confirmed.
    """
    page = context.pages[0] if context.pages else context.new_page()
    logger.info("Navigating to %s", portal_url)
    page.goto(portal_url, wait_until="domcontentloaded")
    return page

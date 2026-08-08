"""
Discovery session against the IBKR Client Portal.

Opens the portal in a real browser and records everything it does while YOU
drive it by hand: which URLs the Flex Query page calls, what it posts, how the
custom date range is submitted, and how the finished CSV arrives. The result is
the specification the automated downloader is then written against.

    uv run python -m src.web_portal.discover

You log in (including two-factor) yourself. Your password is never asked for,
never stored and never recorded: bodies of authentication requests are dropped
whole, and Chrome's own password manager is switched off in the profile. A
username given with --username is remembered in private/portal_username and is
redacted out of the recording.

Type commands in this terminal while the browser stays open:

    mark <label>   record a labelled point in time, before you click something
    snap [label]   save the current page's DOM and a screenshot
    pages          list the open browser tabs
    done           finish, write the summary and close the browser

Output goes to private/portal_discovery/<timestamp>/, which is gitignored.
"""

import argparse
import logging
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from src.web_portal import require_playwright
from src.web_portal.browser import (
    DEFAULT_PORTAL_URL,
    DEFAULT_PROFILE_DIR,
    open_portal,
    portal_session,
)
from src.web_portal.identity import load_username, save_username
from src.web_portal.recorder import PortalRecorder, register_literal_secret

logger = logging.getLogger(__name__)

DEFAULT_DISCOVERY_ROOT = Path("private/portal_discovery")

_INSTRUCTIONS = """
================================================================================
IBKR portal discovery session
================================================================================
The browser window is open. Do this in it, by hand:

  1. Log in, including two-factor authentication. Your password is typed into
     the browser only: it is not recorded, and Chrome will not offer to save it.
  2. Type:  mark logged-in
  3. Navigate to Performance & Reports > Flex Queries.
  4. Type:  snap flex-queries-list
  5. Type:  mark before-run
  6. Run ONE query (e.g. Trades) with Period = Custom Date Range over a full
     calendar year you actually need, and download the CSV.
  7. Type:  mark after-download
  8. If a dialog appeared on the way, run 'snap <name>' while it is on screen.
  9. Type:  done

Commands:  mark <label> | snap [label] | pages | help | done
================================================================================
"""


def _stdin_reader(commands: "queue.Queue[str]") -> None:
    """Read terminal lines on a background thread so the browser stays live."""
    for line in sys.stdin:
        commands.put(line.strip())
    commands.put("done")


def _active_page(context):
    """The most recently opened, still-open page."""
    for page in reversed(context.pages):
        if not page.is_closed():
            return page
    return None


def _handle_command(command: str, context, recorder: PortalRecorder) -> bool:
    """Execute one terminal command. Returns False when the session should end."""
    verb, _, argument = command.partition(" ")
    verb = verb.strip().lower()
    argument = argument.strip()

    if verb in ("done", "quit", "exit"):
        return False

    if verb == "mark":
        if not argument:
            print("Usage: mark <label>")
            return True
        recorder.marker(argument)
        print(f"  marked: {argument}")
        return True

    if verb == "snap":
        page = _active_page(context)
        if page is None:
            print("  no open page to snapshot")
            return True
        recorder.snapshot(page, argument or "snapshot")
        print(f"  snapshot saved for {page.url}")
        return True

    if verb == "pages":
        for index, page in enumerate(context.pages):
            state = "closed" if page.is_closed() else "open"
            print(f"  [{index}] {state}: {page.url}")
        return True

    if verb in ("help", "?", ""):
        print("Commands: mark <label> | snap [label] | pages | help | done")
        return True

    print(f"  unknown command: {command!r} (try 'help')")
    return True


def run_discovery(portal_url: str, profile_dir: Path, out_dir: Path,
                  channel: str | None) -> Path:
    """
    Run one interactive discovery session.

    Returns:
        Path to the written summary.
    """
    # Checked before anything is created on disk: a run that cannot start
    # should leave no empty recording directory behind.
    require_playwright()

    recorder = PortalRecorder(out_dir)
    commands: "queue.Queue[str]" = queue.Queue()

    print(f"Recording to {out_dir}/")

    with portal_session(profile_dir=profile_dir, headless=False, channel=channel) as (_, context):
        recorder.attach(context)

        closed = threading.Event()
        context.on("close", lambda _: closed.set())

        page = open_portal(context, portal_url)
        recorder.marker("session-start")

        print(_INSTRUCTIONS)

        reader = threading.Thread(target=_stdin_reader, args=(commands,), daemon=True)
        reader.start()

        running = True
        while running:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                command = None

            if command is not None:
                try:
                    running = _handle_command(command, context, recorder)
                except Exception as e:
                    # A failed command must not lose the recording so far.
                    logger.warning("Command %r failed: %s", command, e)
                    print(f"  command failed: {e}")
                continue

            if closed.is_set() or _active_page(context) is None:
                print("\nBrowser closed. Finishing the recording.")
                break

            # Pumping a Playwright call delivers queued browser events.
            live = _active_page(context)
            try:
                live.wait_for_timeout(250)
            except Exception:
                time.sleep(0.25)

        recorder.marker("session-end")

    recorder.close()
    summary = recorder.write_summary()
    print(f"\nSummary written to {summary}")
    print(f"Downloads (account data, gitignored): {recorder.downloads_dir}/")
    return summary


def _mask(value: str) -> str:
    """Show enough of a username to confirm which one, and no more."""
    if len(value) <= 2:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record an interactive session against the IBKR Client Portal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--portal-url", default=DEFAULT_PORTAL_URL,
                        help=f"Portal entry point (default: {DEFAULT_PORTAL_URL})")
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR,
                        help=f"Browser profile directory (default: {DEFAULT_PROFILE_DIR})")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Recording directory (default: private/portal_discovery/<timestamp>)")
    parser.add_argument("--channel", default="chrome",
                        help="Browser channel to prefer, or 'chromium' for the bundled build")
    parser.add_argument("--username", default=None,
                        help="IBKR portal username. Stored in private/portal_username "
                             "for later runs and redacted out of the recording. "
                             "The password is never stored or recorded.")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.username:
        save_username(args.username)
    username = args.username or load_username()
    if username:
        # Registered before the browser opens, so it cannot appear in any
        # entry: the recording is streamed to disk as events arrive.
        register_literal_secret(username, "<PORTAL_USERNAME>")
        print(f"Portal username on file: {_mask(username)} "
              f"(redacted from the recording). Password: never stored.")
    else:
        print("No portal username on file. Pass --username <name> to remember one. "
              "The password is never stored.")

    out_dir = args.out_dir or (
        DEFAULT_DISCOVERY_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S"))
    channel = None if args.channel.lower() == "chromium" else args.channel

    run_discovery(args.portal_url, args.profile_dir, out_dir, channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

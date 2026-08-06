"""
The portal username, and nothing else.

The username is a convenience: it is stored so a run can pre-fill the login
form and so the recorder can redact it out of everything it writes. It lives in
a gitignored file under private/, never in a tracked file.

**The password is not handled by this project at all.** It is not read, not
prompted for, not passed, not cached and not stored. The user types it into the
browser window directly. There is deliberately no function here to change that:
the browser's own password manager is disabled when the session launches (see
browser.py), so not even Chrome writes it to the profile on disk.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# private/ is gitignored.
USERNAME_FILE = Path("private/portal_username")


def load_username(path: Path = USERNAME_FILE) -> Optional[str]:
    """Read the stored portal username, or None if none is stored."""
    if not path.exists():
        return None
    username = path.read_text(encoding="utf-8").strip().splitlines()
    if not username or not username[0].strip():
        return None
    return username[0].strip()


def save_username(username: str, path: Path = USERNAME_FILE) -> Path:
    """
    Store the portal username for future runs.

    Raises:
        ValueError: If the value is empty.
    """
    username = username.strip()
    if not username:
        raise ValueError("Refusing to store an empty portal username.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(username + "\n", encoding="utf-8")
    logger.info("Stored portal username in %s", path)
    return path

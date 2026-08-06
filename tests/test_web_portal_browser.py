"""
The browser profile: what is written into it, and what may delete it.

legal_basis: infrastructure. Two things are guarded here. The password must
never reach the disk, which is why the profile is seeded with Chrome's password
manager switched off before the browser is ever started. And the reset that
clears a stuck session is a recursive delete — it must refuse any path that is
not a browser profile, because the flag that triggers it takes a directory
name.

These tests import only src.web_portal.browser's pure file handling; no browser
is launched and playwright is not needed.
"""
import json

import pytest

from src.web_portal.browser import disable_password_storage, reset_profile


class TestDisablePasswordStorage:
    def test_seeds_a_fresh_profile_with_the_password_manager_off(self, tmp_path):
        disable_password_storage(tmp_path)

        prefs = json.loads((tmp_path / "Default" / "Preferences").read_text())
        assert prefs["credentials_enable_service"] is False
        assert prefs["profile"]["password_manager_enabled"] is False

    def test_keeps_existing_preferences_it_does_not_own(self, tmp_path):
        """Chrome stores much more in here; only these keys are ours to set."""
        prefs_path = tmp_path / "Default" / "Preferences"
        prefs_path.parent.mkdir(parents=True)
        prefs_path.write_text(json.dumps({
            "profile": {"exit_type": "Normal", "name": "Person 1"},
            "intl": {"accept_languages": "en-GB"},
        }))

        disable_password_storage(tmp_path)

        prefs = json.loads(prefs_path.read_text())
        assert prefs["intl"]["accept_languages"] == "en-GB"
        assert prefs["profile"]["exit_type"] == "Normal"
        assert prefs["profile"]["password_manager_enabled"] is False

    def test_a_corrupt_preferences_file_does_not_leave_the_manager_enabled(
            self, tmp_path):
        prefs_path = tmp_path / "Default" / "Preferences"
        prefs_path.parent.mkdir(parents=True)
        prefs_path.write_text("{not json at all")

        disable_password_storage(tmp_path)

        prefs = json.loads(prefs_path.read_text())
        assert prefs["credentials_enable_service"] is False


class TestResetProfile:
    def test_removes_a_profile(self, tmp_path):
        profile = tmp_path / "portal_profile"
        (profile / "Default").mkdir(parents=True)
        (profile / "Default" / "Cookies").write_bytes(b"stale session")

        assert reset_profile(profile) is True
        assert not profile.exists()

    def test_missing_profile_is_not_an_error(self, tmp_path):
        assert reset_profile(tmp_path / "nothing_here") is False

    def test_refuses_a_directory_that_is_not_a_browser_profile(self, tmp_path):
        """
        --reset-profile takes a path. Pointed at the wrong one — a home
        directory, a data directory — an unguarded rmtree would take it.
        """
        not_a_profile = tmp_path / "data_import"
        not_a_profile.mkdir()
        (not_a_profile / "Trades-2021.csv").write_text("real data")

        with pytest.raises(RuntimeError, match="does not look like a browser profile"):
            reset_profile(not_a_profile)

        assert (not_a_profile / "Trades-2021.csv").exists()

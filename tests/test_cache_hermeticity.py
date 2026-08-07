# tests/test_cache_hermeticity.py
#
# The clean-clone protocol used to prescribe `rm -rf cache` because tests once read the
# developer's real classifications and passed on data absent from the repository. The
# step was destructive — cache/user_classifications.json is hand-made and nothing
# rebuilds it — so it was replaced by the two autouse guards in conftest.py. This file
# is what makes dropping the rm defensible: it asserts the suite can no longer reach the
# real cache, and it proves the guards can fail.
#
# GREEN means the guards hold and the protocol does not need to delete anything.
# RED means hermeticity has broken and a test is reading developer state again.
#
# This module deliberately does NOT request mock_config_paths. Everything below relies
# only on the autouse fixtures, which is the property being asserted: a test that asks
# for no fixture at all is still hermetic.

import os

import pytest

from src import config as app_config
from src.classification.asset_classifier import AssetClassifier
from src.utils.exchange_rate_provider import ECBExchangeRateProvider

from tests.conftest import (
    RepositoryCacheAccessError,
    _REPO_CACHE_DIR,
    _config_cache_attributes,
)


# --- The invariant ---------------------------------------------------------------


def test_no_config_cache_path_resolves_inside_the_repository():
    """Every cache path src.config offers points outside the repository during a test."""
    offenders = {
        name: value
        for name, value in _config_cache_attributes(app_config)
        if os.path.abspath(value).startswith(os.path.abspath(_REPO_CACHE_DIR) + os.sep)
    }
    assert not offenders, (
        f"config cache paths still resolve inside the repository: {offenders}. "
        f"_hermetic_cache_paths in tests/conftest.py should have redirected them."
    )


def test_the_cache_attributes_actually_under_guard_are_the_expected_ones():
    """The selection rule sees the caches it is supposed to see.

    Named explicitly so that deleting the rule, or narrowing it until it matches
    nothing, is a red test rather than a silently empty loop.
    """
    guarded = {name for name, _ in _config_cache_attributes(app_config)}
    assert {
        "CLASSIFICATION_CACHE_FILE_PATH",
        "ECB_RATES_CACHE_FILE_PATH",
        "FLEX_CACHE_DIR",
    } <= guarded


def test_default_constructed_classifier_writes_outside_the_repository(tmp_path):
    """AssetClassifier() with no path — the config default — stays in the temp dir."""
    classifier = AssetClassifier()
    assert not os.path.abspath(classifier.cache_file_path).startswith(
        os.path.abspath(_REPO_CACHE_DIR) + os.sep
    )
    classifier.classifications_cache["probe"] = ("STOCK", "NONE", "test")
    classifier.save_classifications()
    assert os.path.exists(classifier.cache_file_path)


def test_each_test_gets_its_own_cache_directory(hermetic_cache_dir):
    """The redirection is per-test, so one test cannot see another's classifications."""
    assert app_config.CLASSIFICATION_CACHE_FILE_PATH.startswith(hermetic_cache_dir)


# --- Calibration -----------------------------------------------------------------
#
# A guard nobody broke on purpose reports green whether or not it can see anything.
# Each of the three below is one of the ways hermeticity can break, exercised here so
# the guard's sensitivity is asserted by the suite rather than argued in a commit
# message. All three read only; none creates, modifies or removes anything in cache/.


def test_guard_fires_on_a_hardcoded_cache_literal():
    """The break config redirection cannot reach: a path literal in the source."""
    with pytest.raises(RepositoryCacheAccessError):
        open(os.path.join("cache", "user_classifications.json"), "r")


def test_guard_fires_on_a_classifier_built_with_a_real_path():
    """The original incident, verbatim: a classifier pointed at the developer's cache."""
    with pytest.raises(RepositoryCacheAccessError):
        AssetClassifier(cache_file_path="cache/user_classifications.json")


def test_guard_survives_a_readers_bare_except(tmp_path):
    """The guard must not be swallowable by the `except Exception` around a cache write.

    This is the case that makes RepositoryCacheAccessError a BaseException rather than
    an Exception. On the LOAD path the guarded os.path.exists sits outside the try, so
    either base class works; ECBExchangeRateProvider._save_cache calls open() inside a
    bare `except Exception` that logs and returns, and there an Exception would vanish
    and leave the write to the real cache unreported.
    """
    provider = ECBExchangeRateProvider(cache_file_path=str(tmp_path / "rates.json"))
    provider.cache_file_path = os.path.join("cache", "ecb_exchange_rates.json")
    with pytest.raises(RepositoryCacheAccessError):
        provider._save_cache()


def test_guard_fires_on_the_exchange_rate_providers_hardcoded_default():
    """ECBExchangeRateProvider's cache_file_path default is a repository-relative literal.

    src/utils/exchange_rate_provider.py defaults it to "cache/ecb_exchange_rates.json"
    without consulting config, so _hermetic_cache_paths cannot redirect it. Constructing
    the provider with no path must therefore trip the tripwire instead.
    """
    with pytest.raises(RepositoryCacheAccessError):
        ECBExchangeRateProvider()


def test_guard_fires_on_an_absolute_path_into_the_cache():
    """Reaching the same directory by absolute path is the same violation."""
    with pytest.raises(RepositoryCacheAccessError):
        os.path.exists(os.path.join(_REPO_CACHE_DIR, "anything.json"))


def test_guard_fires_on_creating_the_cache_directory():
    """Creating cache/ counts too: it is how a clean clone silently grows one."""
    with pytest.raises(RepositoryCacheAccessError):
        os.makedirs(_REPO_CACHE_DIR, exist_ok=True)


def test_guard_leaves_paths_outside_the_cache_alone(tmp_path):
    """The tripwire is targeted, not a blanket ban on file access."""
    probe = tmp_path / "elsewhere.json"
    probe.write_text("{}", encoding="utf-8")
    assert os.path.exists(str(probe))
    with open(str(probe), "r", encoding="utf-8") as handle:
        assert handle.read() == "{}"

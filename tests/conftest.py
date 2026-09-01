# tests/conftest.py
import builtins
import pytest
import tempfile
import os
from decimal import Decimal, getcontext, ROUND_HALF_UP # Default rounding for tests if config fails

# Attempt to import app_config from the refactored structure
try:
    from src import config as app_config
except ImportError:
    # Fallback if src.config is not found (e.g., PYTHONPATH issues during test discovery)
    class MockAppConfig:
        INTERNAL_CALCULATION_PRECISION = 28 # Updated name
        DECIMAL_ROUNDING_MODE = "ROUND_HALF_UP"
        TRADES_FILE_PATH = "trades.csv"
        CASH_TRANSACTIONS_FILE_PATH = "cash.csv"
        POSITIONS_START_FILE_PATH = "pos_start.csv"
        POSITIONS_END_FILE_PATH = "pos_end.csv"
        CORPORATE_ACTIONS_FILE_PATH = "corp_actions.csv"
        CLASSIFICATION_CACHE_FILE_PATH = "user_classifications.json" # Updated name
        ECB_RATES_CACHE_FILE_PATH = "ecb_rates.json" # Updated name
        TAX_YEAR = 2023
        IS_INTERACTIVE_CLASSIFICATION = False # Updated name
        MAX_FALLBACK_DAYS_EXCHANGE_RATES = 7
        CURRENCY_CODE_MAPPING_ECB = {"CNH": "CNY"}
        OUTPUT_PRECISION_AMOUNTS = Decimal("0.01") # Added for test_result_defs.py
        APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING = True

    app_config = MockAppConfig()
    print("Warning: Using MockAppConfig in tests/conftest.py. Ensure src is in PYTHONPATH.")


# --- Cache hermeticity ---------------------------------------------------------------
#
# No test may read or write the repository's real cache/ directory. That directory holds
# the maintainer's hand-made asset classifications, which nothing can rebuild
# automatically, and it is absent from a clean clone — so a test that reads it passes on
# data the repository does not contain.
#
# Two guards, because they fail differently and neither covers the other:
#
#   _hermetic_cache_paths   redirects every cache path in src.config into a per-test
#                           temp dir. AUTOUSE: unlike mock_config_paths it cannot be
#                           opted out of, so a new test that drives the pipeline without
#                           asking for any fixture is still hermetic.
#   _repo_cache_tripwire    raises on any access that resolves inside the real cache/
#                           directory. This is the half config redirection cannot reach:
#                           a hardcoded literal (ECBExchangeRateProvider's cache_file_path
#                           default is "cache/ecb_exchange_rates.json") or a classifier
#                           constructed with a real path never consults config at all.

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_CACHE_DIR = os.path.join(_REPO_ROOT, "cache")


class RepositoryCacheAccessError(BaseException):
    """A test reached the repository's real cache/ directory.

    Deliberately a BaseException and not an Exception. Both cache classes wrap their
    file access in a bare `except Exception` that logs and continues
    (AssetClassifier.load_classifications / save_classifications,
    ECBExchangeRateProvider._load_cache / _save_cache), so an Exception raised here
    would be swallowed at the very site being guarded and the test would stay green.

    Measured, not assumed: on the load path the guarded os.path.exists sits OUTSIDE
    those try blocks, so demoting this to Exception changes nothing there. The save
    path is what makes the choice load-bearing — ECBExchangeRateProvider._save_cache
    calls open() inside the try. test_guard_survives_a_readers_bare_except pins that
    case, and goes red when this class is demoted.
    """


def _resolves_inside_repo_cache(path) -> bool:
    """True if `path` names the repository's cache/ directory or something inside it.

    Resolution is textual (os.path.abspath), so a relative path is judged against the
    current working directory and a symlink pointing into cache/ is not followed. Both
    are acceptable: a test that chdir'd away cannot reach the real cache with a relative
    path, and nothing in this repository symlinks into cache/.
    """
    if isinstance(path, int):  # an already-open file descriptor names no path
        return False
    try:
        candidate = os.path.abspath(os.fspath(path))
    except TypeError:
        return False
    return candidate == _REPO_CACHE_DIR or candidate.startswith(_REPO_CACHE_DIR + os.sep)


def _config_cache_attributes(module):
    """Yield (name, value) for every config attribute naming a cache location.

    Selected two ways so the rule has no gap to fall through: by NAME, which catches a
    cache attribute pointing somewhere harmless today, and by VALUE, which catches an
    attribute pointing into the real cache/ under a name this rule would not recognise.
    """
    for name in sorted(dir(module)):
        if not name.isupper():
            continue
        value = getattr(module, name)
        if not isinstance(value, str):
            continue
        if "CACHE" in name or _resolves_inside_repo_cache(value):
            yield name, value


@pytest.fixture(autouse=True)
def hermetic_cache_dir():
    """Per-test temp directory standing in for the repository's cache/."""
    with tempfile.TemporaryDirectory(prefix="hermetic-cache-") as tmpdir:
        yield tmpdir


@pytest.fixture(autouse=True)
def _hermetic_cache_paths(hermetic_cache_dir):
    """Point every src.config cache path into a per-test temp directory.

    Restores by hand rather than through the `monkeypatch` fixture, and that is
    load-bearing. `monkeypatch` is one function-scoped instance shared by every fixture
    that asks for it, undone at ITS teardown. An autouse fixture requesting it would
    make it set up first and therefore tear down last — after
    _global_config_leak_tripwire's teardown, which would then read mock_config_paths'
    still-applied patches as a leak and fail every test that uses it.
    """
    from src import config as config_module

    originals = {}
    for name, value in _config_cache_attributes(config_module):
        originals[name] = value
        # One subdirectory per attribute, so two caches whose basenames collide do not
        # end up sharing a file.
        redirected_dir = os.path.join(hermetic_cache_dir, name)
        os.makedirs(redirected_dir, exist_ok=True)
        setattr(config_module, name,
                os.path.join(redirected_dir, os.path.basename(os.path.normpath(value))))
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(config_module, name, value)


@pytest.fixture(autouse=True)
def _repo_cache_tripwire():
    """Raise on any access resolving inside the repository's real cache/ directory.

    Guards the three calls both cache readers make — os.path.exists, open and
    os.makedirs — rather than open alone, so the tripwire fires on the attempt and not
    on whether the developer happens to have the file. A guard whose sensitivity depends
    on developer state reports green in a clean clone for the wrong reason.
    """
    patched = {
        (builtins, "open"): builtins.open,
        (os.path, "exists"): os.path.exists,
        (os, "makedirs"): os.makedirs,
    }

    def guard(original, verb):
        def wrapper(path, *args, **kwargs):
            if _resolves_inside_repo_cache(path):
                raise RepositoryCacheAccessError(
                    f"test {verb} the repository's real cache: {path!r}. "
                    f"Tests must not touch {_REPO_CACHE_DIR} — it holds hand-made "
                    f"classifications that are absent from a clean clone. Use the "
                    f"hermetic_cache_dir fixture, or pass an explicit tmp_path."
                )
            return original(path, *args, **kwargs)
        return wrapper

    for (owner, attr), original in patched.items():
        setattr(owner, attr, guard(original, {"open": "opened", "exists": "probed",
                                              "makedirs": "created"}[attr]))
    try:
        yield
    finally:
        for (owner, attr), original in patched.items():
            setattr(owner, attr, original)


@pytest.fixture(scope="session", autouse=True)
def set_decimal_precision_session_wide():
    """
    Set global decimal precision and rounding for all tests in the session.
    This mirrors the setup in your main_application or setup_decimal_context.
    """
    prec = app_config.INTERNAL_CALCULATION_PRECISION # Updated name
    rounding_mode_str = app_config.DECIMAL_ROUNDING_MODE
    
    getcontext().prec = prec
    
    valid_rounding_modes = ["ROUND_CEILING", "ROUND_DOWN", "ROUND_FLOOR", "ROUND_HALF_DOWN",
                            "ROUND_HALF_EVEN", "ROUND_HALF_UP", "ROUND_UP", "ROUND_05UP"]
    if rounding_mode_str in valid_rounding_modes:
        getcontext().rounding = rounding_mode_str # type: ignore
    else:
        print(f"Warning: Invalid DECIMAL_ROUNDING_MODE '{rounding_mode_str}'. Using ROUND_HALF_UP for tests.")
        getcontext().rounding = ROUND_HALF_UP # type: ignore
    # print(f"\nDecimal context set for test session: Precision={getcontext().prec}, Rounding={getcontext().rounding}")


@pytest.fixture
def temp_data_dir():
    """
    Creates a temporary directory for test input/output files.
    Yields the path to this directory.
    Cleans up the directory after the test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_subdir = os.path.join(tmpdir, "cache")
        os.makedirs(cache_subdir, exist_ok=True)
        # data_subdir = os.path.join(tmpdir, "data") # Not strictly needed if files go to tmpdir root
        # os.makedirs(data_subdir, exist_ok=True)
        yield tmpdir

@pytest.fixture
def mock_config_paths(temp_data_dir, monkeypatch):
    """
    Mocks file paths in app_config to use the temp_data_dir.
    This is useful if the application directly uses config.TRADES_FILE_PATH etc.
    Returns a dictionary of these temporary paths for explicit use in tests.
    """
    data_path = lambda filename: os.path.join(temp_data_dir, filename)
    cache_path = lambda filename: os.path.join(temp_data_dir, "cache", filename)

    # Define paths for explicit use first
    paths_dict = {
        "trades": data_path("trades.csv"),
        "cash": data_path("cash_transactions.csv"),
        "pos_start": data_path("positions_start_of_year.csv"),
        "pos_end": data_path("positions_end_of_year.csv"),
        # Preceding calendar year's snapshots. The Vorabpauschale declared in VZ Y is the
        # one computed for calendar Y-1 (18 Abs. 3 InvStG), so it reads these rather than
        # the tax year's own. See reference/investment-tax-law/invstg-18-vorabpauschale.md.
        "pos_prior_start": data_path("positions_prior_year_start.csv"),
        "pos_prior_end": data_path("positions_prior_year_end.csv"),
        "corp_actions": data_path("corporate_actions.csv"),
        "cash_balance": data_path("cash_balance.csv"),
        "transfers": data_path("transfers.csv"),
        "classification_cache": cache_path("user_classifications.json"),
        "ecb_cache": cache_path("ecb_exchange_rates.json"),
        "temp_dir_root": temp_data_dir
    }

    # Attempt to monkeypatch the actual src.config module if it's loaded
    try:
        # This assumes 'src.config' is the canonical path to the config module
        # as it would be imported by other application modules.
        target_config_module = "src.config" 
        
        # Check if module is loaded and patchable, common for when tests import app code that imports config
        import sys
        if target_config_module in sys.modules:
            config_module_obj = sys.modules[target_config_module]
            # Cache hermeticity is NOT this fixture's job any more, and must not become
            # it again: this fixture is opt-in, and the caches were reachable from the
            # tests that do not request it. The autouse _hermetic_cache_paths above
            # redirects them for every test unconditionally, and _repo_cache_tripwire
            # raises on anything that reaches the real cache/ regardless of config. The
            # two cache lines below now only keep this fixture's temp tree self-
            # consistent, so a test can point at paths_dict and find its own files.
            # raising=False: attribute sets must not abort the remaining patches (the
            # legacy *_FILE_PATH attributes no longer exist in config).
            monkeypatch.setattr(config_module_obj, "TRADES_FILE_PATH", paths_dict["trades"], raising=False)
            monkeypatch.setattr(config_module_obj, "CASH_TRANSACTIONS_FILE_PATH", paths_dict["cash"], raising=False)
            monkeypatch.setattr(config_module_obj, "POSITIONS_START_FILE_PATH", paths_dict["pos_start"], raising=False)
            monkeypatch.setattr(config_module_obj, "POSITIONS_END_FILE_PATH", paths_dict["pos_end"], raising=False)
            monkeypatch.setattr(config_module_obj, "CORPORATE_ACTIONS_FILE_PATH", paths_dict["corp_actions"], raising=False)
            monkeypatch.setattr(config_module_obj, "CLASSIFICATION_CACHE_FILE_PATH", paths_dict["classification_cache"])
            monkeypatch.setattr(config_module_obj, "ECB_RATES_CACHE_FILE_PATH", paths_dict["ecb_cache"])
            # raising=False: these two are introduced later in the train (VP work);
            # they must not abort the remaining patches when absent.
            monkeypatch.setattr(config_module_obj, "FUND_SOY_NAV_CACHE_FILE_PATH",
                                os.path.join(os.path.dirname(paths_dict["classification_cache"]), "fund_soy_nav.json"),
                                raising=False)
            monkeypatch.setattr(config_module_obj, "DECLARED_VP_CACHE_FILE_PATH",
                                os.path.join(os.path.dirname(paths_dict["classification_cache"]), "declared_vp.json"),
                                raising=False)
            monkeypatch.setattr(config_module_obj, "IS_INTERACTIVE_CLASSIFICATION", False)
        else:
            # This might occur if tests are structured such that src.config isn't loaded when conftest runs,
            # or if the way config is imported varies. Passing paths explicitly to pipeline_runner is robust.
            print(f"Warning: {target_config_module} not in sys.modules during conftest. Direct config patching might be incomplete.")
            print("Tests should rely on explicit file paths passed to the processing pipeline.")

    except Exception as e: # Catch broad exceptions during patching
        print(f"Notice: Skipping monkeypatch of config paths due to an issue: {e}. Ensure config is structured as expected or pass paths explicitly.")

    return paths_dict


@pytest.fixture
def default_tax_year():
    """Returns the default tax year for tests."""
    return 2023


@pytest.fixture(autouse=True)
def _global_config_leak_tripwire(_hermetic_cache_paths):
    """No test may leak a mutated global config value past its own teardown.

    Depends on _hermetic_cache_paths so the cache redirection is already applied when
    the `before` snapshot is taken; otherwise the snapshot records the repository paths
    and the redirection itself reads as a leak.

    The incident this guards: a leaked src.config.TAX_YEAR made group-6 results
    depend on which modules ran before it. Patches via pytest's monkeypatch are
    auto-reverted; anything else trips this wire.

    Deliberately PER-TEST and over EVERY uppercase config attribute, because a
    session-scoped probe on TAX_YEAR alone has three blind spots, all verified
    against deliberately broken trees:
      * leak-then-restore — one test corrupts TAX_YEAR, a later one happens to
        set it back, session-level before/after match and the run is green even
        though every test in between ran corrupted. That is exactly the shape of
        the original incident.
      * every other config global is unwatched, including the legally-relevant
        APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING.
      * the failure is attributed to whichever test happened to run last, not to
        the one that leaked.
    """
    from src import config as app_config
    watched = [name for name in dir(app_config) if name.isupper()]
    sentinel = object()
    before = {name: getattr(app_config, name) for name in watched}
    yield
    changed = {
        name: (before[name], getattr(app_config, name, sentinel))
        for name in watched
        if getattr(app_config, name, sentinel) != before[name]
    }
    assert not changed, (
        f"GLOBAL CONFIG LEAK: this test mutated src.config without restoring it: "
        f"{ {k: f'{v[0]!r} -> {v[1]!r}' for k, v in changed.items()} }. "
        f"Use the monkeypatch fixture so the change is auto-reverted."
    )


@pytest.fixture(autouse=True)
def _no_issuer_lookups():
    """No test reaches a fund provider's website.

    Since 2026-08-08 the year-start Ruecknahmepreis is fetched for **every** fund
    that owes a Vorabpauschale, not only for one the position report cannot
    price, so an ordinary pipeline test would otherwise open five providers'
    sites. Two guards, because either alone is weak:

    - `FUND_PRICE_AUTO_FETCH` off, which is the switch a user has;
    - a tripwire on the fetch itself, so a test that wires the lookup up by hand
      fails loudly instead of going to the network. A suite whose speed and
      result depend on a provider being up is not a suite.

    A test that wants a lookup injects its own `fetch`, which the resolver takes
    as a parameter and which never reaches this function.
    """
    from src import config as config_module
    from src.processing import fund_price_sources

    had = hasattr(config_module, "FUND_PRICE_AUTO_FETCH")
    previous = getattr(config_module, "FUND_PRICE_AUTO_FETCH", None)
    config_module.FUND_PRICE_AUTO_FETCH = False

    real = fund_price_sources.fetch_year_start_price

    def _tripwire(*args, **kwargs):
        raise AssertionError(
            "fetch_year_start_price reached the network during a test. Inject a "
            "`fetch` callable instead; see tests/conftest.py::_no_issuer_lookups."
        )

    fund_price_sources.fetch_year_start_price = _tripwire
    try:
        yield
    finally:
        fund_price_sources.fetch_year_start_price = real
        if had:
            config_module.FUND_PRICE_AUTO_FETCH = previous
        else:
            delattr(config_module, "FUND_PRICE_AUTO_FETCH")

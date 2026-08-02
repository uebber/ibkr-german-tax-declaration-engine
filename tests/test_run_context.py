"""
Explicit RunContext: no ambient mutable configuration.

Infrastructure, not a legal rule — this eliminates the bug class where a leaked
global src.config.TAX_YEAR made results depend on which modules ran first (the
order-dependent suite fixed earlier in this train).
"""
import inspect
from dataclasses import FrozenInstanceError

import pytest

from src.run_context import RunContext
from src.cli import parse_arguments
from src.pipeline_runner import run_core_processing_pipeline


def test_pipeline_requires_explicit_tax_year():
    """The pipeline must not silently inherit a module-global tax year: the
    parameter has NO default."""
    sig = inspect.signature(run_core_processing_pipeline)
    param = sig.parameters["tax_year_to_process"]
    assert param.default is inspect.Parameter.empty, (
        "tax_year_to_process must be required — a global default reintroduces "
        "ambient-state behavior")


def test_from_config_reads_boundary_defaults(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "TAX_YEAR", 2031)
    monkeypatch.setattr(config, "IS_INTERACTIVE_CLASSIFICATION", False)
    ctx = RunContext.from_config()
    assert ctx.tax_year == 2031 and ctx.interactive is False


def test_explicit_values_override_config(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "TAX_YEAR", 2031)
    monkeypatch.setattr(config, "IS_INTERACTIVE_CLASSIFICATION", True)
    ctx = RunContext.from_config(tax_year=2025, interactive=False)
    assert ctx.tax_year == 2025 and ctx.interactive is False


def test_run_context_is_immutable():
    ctx = RunContext.from_config(tax_year=2025, interactive=False)
    with pytest.raises(FrozenInstanceError):
        ctx.tax_year = 2026  # frozen dataclass


def test_run_context_carries_no_decimal_context():
    """Precision lives in one place only (main.setup_decimal_context). A second
    copy on the run context would be an inert duplicate source of truth."""
    ctx = RunContext.from_config(tax_year=2025, interactive=False)
    assert not hasattr(ctx, "decimal_context")


# --- the boundary must be the ONLY config read, not merely the last one ------
# Regression guard: --tax-year previously carried `default=config.TAX_YEAR` and
# the parser resolved IS_INTERACTIVE_CLASSIFICATION itself, so from_config() was
# always handed non-None values and its resolution branches were dead code —
# covered by tests, unreachable in production.

def test_cli_module_does_not_read_user_config():
    """src/cli.py must stay purely syntactic — no config read at all.

    Checked over the parsed AST, not the source text: the module explains in a
    comment why it does not import the config, and a substring check matches
    that comment.
    """
    import ast
    import src.cli as cli
    tree = ast.parse(inspect.getsource(cli))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    offenders = {name for name in imported if name.split(".")[-1] == "config"
                 or name.startswith("src.config")}
    assert not offenders, (
        f"src/cli.py must not read the user config (found {offenders}): that "
        f"would place a second config read upstream of the RunContext boundary")


@pytest.mark.parametrize("argv,expected", [
    ([], (None, None)),
    (["--tax-year", "2022"], (2022, None)),
    (["--interactive"], (None, True)),
    (["--no-interactive"], (None, False)),
])
def test_parser_leaves_unspecified_run_values_as_none(monkeypatch, argv, expected):
    """Unspecified run-defining options must reach the boundary as None, so the
    boundary can actually resolve them."""
    monkeypatch.setattr("sys.argv", ["prog"] + argv)
    args = parse_arguments()
    assert (args.tax_year, args.interactive) == expected


def test_boundary_resolves_what_the_parser_left_unset(monkeypatch):
    """End to end: bare argv + config defaults -> the config values are used."""
    import src.config as config
    monkeypatch.setattr("sys.argv", ["prog"])
    monkeypatch.setattr(config, "TAX_YEAR", 2031)
    monkeypatch.setattr(config, "IS_INTERACTIVE_CLASSIFICATION", True)
    args = parse_arguments()
    ctx = RunContext.from_config(tax_year=args.tax_year, interactive=args.interactive)
    assert ctx.tax_year == 2031 and ctx.interactive is True

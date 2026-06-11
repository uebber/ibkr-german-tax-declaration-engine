"""
AR1 (rework2-plan): explicit RunContext, no ambient mutable configuration.

legal_basis: infrastructure — eliminates the F1 bug class (order-dependent
results via leaked global TAX_YEAR; see legal-review-todo.md F1).
"""
import inspect
from decimal import Context

import pytest

from src.run_context import RunContext
from src.pipeline_runner import run_core_processing_pipeline


def test_pipeline_requires_explicit_tax_year():
    """The pipeline must not silently inherit a module-global tax year: the
    parameter has NO default."""
    sig = inspect.signature(run_core_processing_pipeline)
    param = sig.parameters["tax_year_to_process"]
    assert param.default is inspect.Parameter.empty, (
        "tax_year_to_process must be required — a global default reintroduces "
        "ambient-state behavior (finding F1)")


def test_from_config_reads_boundary_defaults(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "TAX_YEAR", 2031)
    monkeypatch.setattr(config, "IS_INTERACTIVE_CLASSIFICATION", False)
    ctx = RunContext.from_config()
    assert ctx.tax_year == 2031 and ctx.interactive is False
    assert isinstance(ctx.decimal_context, Context)


def test_explicit_values_override_config(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "TAX_YEAR", 2031)
    ctx = RunContext.from_config(tax_year=2025, interactive=True)
    assert ctx.tax_year == 2025 and ctx.interactive is True


def test_run_context_is_immutable():
    ctx = RunContext.from_config(tax_year=2025, interactive=False)
    with pytest.raises(Exception):
        ctx.tax_year = 2026  # frozen dataclass

# src/run_context.py
"""
RunContext — explicit, immutable per-run configuration (rework2-plan AR1).

Why: mutable module-global configuration (src.config.TAX_YEAR & friends) made
behavior depend on ambient state — the root cause of the order-dependent test
suite (legal-review finding F1) and of tests whose results depended on the
UNTRACKED local src/config.py. The run-defining values are now carried by an
explicit, frozen object constructed ONCE at the process boundary
(src/main.py / src/cli.py); everything below the boundary receives them as
parameters.

src.config remains the home of true constants (precisions, file paths) and of
user-editable defaults; it is READ at the boundary, never relied upon as
ambient state inside the engine.
"""
from dataclasses import dataclass
from decimal import Context


@dataclass(frozen=True)
class RunContext:
    """The values that define a single pipeline run."""
    tax_year: int
    interactive: bool
    decimal_context: Context

    @staticmethod
    def from_config(tax_year=None, interactive=None) -> "RunContext":
        """Boundary constructor: read user config ONCE, apply explicit overrides.

        Only src/main.py (and tests that deliberately want config defaults)
        should call this; library code receives a ready RunContext or explicit
        parameters.
        """
        import src.config as config
        return RunContext(
            tax_year=int(tax_year if tax_year is not None else config.TAX_YEAR),
            interactive=bool(interactive if interactive is not None
                             else config.IS_INTERACTIVE_CLASSIFICATION),
            decimal_context=Context(
                prec=config.INTERNAL_CALCULATION_PRECISION,
                rounding=config.DECIMAL_ROUNDING_MODE,
            ),
        )

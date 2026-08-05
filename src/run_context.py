# src/run_context.py
"""
RunContext — explicit, immutable per-run configuration.

Why: mutable module-global configuration (src.config.TAX_YEAR & friends) made
behavior depend on ambient state — the root cause of the order-dependent test
suite and of tests whose results depended on the UNTRACKED local src/config.py.
The run-defining values are now carried by an explicit, frozen object
constructed ONCE at the process boundary (src/main.py); everything below the
boundary receives them as parameters.

src/cli.py deliberately does not read src.config: it leaves an unspecified
--tax-year / --interactive as None, so from_config() below is the single place
the user config is consulted for a run-defining value.

Scope: this object carries only the values that vary per run. src.config
remains the home of true constants (precisions, file paths) and of
user-editable defaults; it is READ at the boundary, never relied upon as
ambient state inside the engine. Decimal precision is deliberately NOT carried
here — src/main.py::setup_decimal_context() installs it into the process-wide
decimal context, and a second, inert copy on this object would be a duplicate
source of truth for the precision rules CLAUDE.md requires.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    """The values that define a single pipeline run."""
    tax_year: int
    interactive: bool

    @staticmethod
    def from_config(tax_year=None, interactive=None) -> "RunContext":
        """Boundary constructor: read user config ONCE, apply explicit overrides.

        A None argument means "the user did not specify this" and is resolved
        from src.config. Only src/main.py should call this; library code
        receives a ready RunContext or explicit parameters.
        """
        import src.config as config
        return RunContext(
            tax_year=int(tax_year if tax_year is not None else config.TAX_YEAR),
            interactive=bool(interactive if interactive is not None
                             else config.IS_INTERACTIVE_CLASSIFICATION),
        )

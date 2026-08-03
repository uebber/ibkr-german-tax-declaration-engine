# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

This file states **how the project is built, run, verified and validated**, and the discipline
that governs anything with a legal consequence. It deliberately contains **no tax content** —
no form line numbers, rates, thresholds or year rules. Those live in `reference/`, which is the
only place they may live. If you find a legal fact stated here, it is a defect: remove it and
cite the reference instead.

## Project Overview

Generates the figures for a German tax declaration (Anlage KAP, KAP-INV, SO) from Interactive
Brokers Flex Query CSV exports. It handles FIFO lot tracking, currency conversion at ECB rates,
corporate actions, options and futures, and investment-fund taxation.

The output is a number a person puts on a tax return. That single fact sets the standard for
everything below: **a wrong number that looks plausible is worse than a crash.**

## Setup

Uses `uv`. Install it first: https://docs.astral.sh/uv/getting-started/installation/

```bash
uv sync                                    # creates .venv and installs dependencies
cp src/config_example.py src/config.py     # config.py is gitignored; it holds personal data
```

`src/config.py` carries the default tax year, taxpayer identity for reports, the interactive
classification switch, and Flex Query IDs. `config_example.py` is the tracked template and must
define every attribute `src/` reads — a test enforces this.

## Running

```bash
uv run python -m src.main --tax-year YYYY --report-tax-declaration
uv run python -m src.main --help           # all options
```

Common flags: `--interactive` / `--no-interactive` (asset classification), `--pdf-output-file`,
`--download` / `--download-only` (fetch from the IBKR Flex Web Service first), `--group-by-type`
and `--debug-asset-summary` (diagnostics).

## Verification

```bash
uv run pytest                              # full suite
uv run pytest tests/test_<area>.py -v      # one area
```

**Clean-clone protocol — the only run that proves anything.** The suite must pass on a checkout
with no developer state. Tests once read the developer's real `cache/` and passed on
classifications absent from the repo:

```bash
rm -rf cache && cp src/config_example.py src/config.py && uv run pytest -q
```

**A green suite is weaker evidence than it looks.** Coverage is uneven and the gaps are not
where the diff is. Before trusting a passing run on a change:

- **Probe by mutation.** Break the behaviour deliberately, in each way it can break, and confirm
  a test fails. Sites the suite reaches fail loudly; sites it does not are silent.
- **Calibrate every new guard.** A check that cannot observe what it claims to check is worth
  nothing, and it will be green. Write the tree that should trip it and confirm it does.
- **Verify red-first.** Revert the change, confirm the new tests fail, and report the count.

Test fixtures are YAML specs in `tests/fixtures/` with helpers in `tests/support/`;
`tests/docs/` holds the behavioural specs they encode.

## Validation against real data

- `validate_ledgers.py` — reconciles start-of-year and end-of-year positions per tax year.
- `scripts/parity_check.sh` — captures a full run (console, log, PDF) and compares two captures,
  for proving a refactor is output-neutral. It is cache-hermetic and order-sensitive; read its
  header before relying on it. Parity results are **year-specific** — always name the assessment
  year you measured, and take a same-tree control capture first so ambient nondeterminism is not
  read as a change.

See also the reconciliation invariant under Engineering rules — the engine enforces it on every
run, not only when validating against real data.

## Architecture

Processing flow:

1. **Data preparation** (`src/data_preparation.py`) — resolves and concatenates input files by tax year
2. **Parsing** (`src/parsers/`) — CSV to raw records; `src/identification/asset_resolver.py` maintains one `Asset` per instrument across all files
3. **Enrichment** (`src/processing/`) — EUR conversion at ECB rates; links withholding tax and option exercises to their counterparts
4. **Classification** (`src/classification/`) — assigns each asset its category, interactively or from cache
5. **Calculation** (`src/engine/`) — FIFO ledgers, corporate actions, realised gains
6. **Aggregation** (`src/engine/loss_offsetting.py`) — figures per reporting category
7. **Reporting** (`src/reporting/`) — console and PDF

Seams worth knowing before changing the engine:

- `src/engine/fifo_manager.py` — lot tracking for long and short positions; start-of-year reconciliation
- `src/engine/replay.py` — one ordered stream rebuilding all pre-tax-year ledger state; its ordering contract is load-bearing and has its own tests
- `src/engine/ledger_views.py`, `src/utils/account_utils.py` — ledgers keyed by (account, asset), with aggregate views
- `src/engine/event_processors/` — one processor per event kind
- `src/tax_law/` — year-parameterised legal values (`registry.py`) and domain rules (`holding_period.py`), each citing `reference/`
- `src/processing/data_gaps.py` — the one channel for "the input cannot support this computation"
- `src/reporting/form_rules.py` — year-specific form structure
- `src/domain/` — assets, events, results, enums, exceptions

## Ground truth: the `reference/` library

`reference/` is the **single source of truth for every legal requirement this engine
implements**. `reference/INDEX.md` is its directory; `reference/research/coverage-matrix.md`
maps every supported event and asset to its legal source.

### The Ground Truth Rule (non-negotiable)

**Never implement, change, or justify legally relevant behaviour from a source outside
`reference/`.** Not from web search, not from a linked PDF, not from your own knowledge of German
tax law, not from what the existing code appears to assume.

**Legally relevant** means anything that can change a declared figure or where it lands —
including the expected values of any test asserting one.

The order of operations is always:

1. **Look it up in `reference/`.** Read the file; do not assume it says what you expect.
2. **If covered:** the reference is authoritative — over general knowledge, and over the code.
3. **If not covered, or stale, ambiguous or contradicted: stop.** Do not proceed on recall or an
   ad-hoc lookup. **Extend the store first, and only as `reference/research/research-strategy.md`
   prescribes** — that document defines the source tiers, the validation protocol, and the
   required procedure for adding a file. It is the only sanctioned way the library may grow.
4. **Then implement**, citing the reference in the code comment, test docstring or commit message,
   so the figure stays traceable to its source.

Research done in conversation and not written into `reference/` is not ground truth. If a question
cannot be resolved to the standard `research-strategy.md` sets, record the gap and raise it —
do not close it with a guess.

If code and a reference file conflict, **surface it**; do not silently follow the code.

## Engineering rules

### SoY → EoY must reconcile (non-negotiable)

**After the ledger has run, the calculated end-of-year position must equal the position the
broker reports. There is no tolerance for disagreement and no override.**

The start-of-year quantity is *taken from* the positions snapshot, not reconstructed — the
historical replay supplies cost basis and acquisition dates, never the running quantity. So the
end-of-year quantity follows from that snapshot plus the tax year's own events, and it has
exactly one correct answer. When the engine's answer differs from the broker's, an event is
missing or was processed incorrectly: an absent trade or corporate action, an unlinked option
exercise, one instrument resolved under two identifiers. At least one disposal is then matched
against the wrong lots, which makes the reported gain wrong and not merely the quantity.

The engine checks every asset, then aborts naming all of them. It does not emit figures, form
lines or a PDF from a ledger that does not reconcile.

Two things to hold on to, because both have already misled people here:

- **An incomplete prior-year trade history cannot cause this.** Missing earlier years change the
  cost basis and acquisition dates of carried-in positions; they cannot move the quantity, which
  the snapshot pins. A mismatch always points at the tax year's own input, or at the engine's
  handling of it. Do not go looking for old data, and do not relax the check on that theory.
- **It does not prove the lots are right.** The comparison is of net quantity. A defect that
  misassigns lots without changing the net — the wrong lot consumed, a wrong acquisition date,
  a wrong basis — reconciles clean. A green reconciliation is a floor, not a guarantee.

Cash-balance (currency) reconciliation is deliberately *not* fatal: its causes are input
completeness rather than a ledger disagreeing about a holding. It is recorded as a data gap so it
reaches the report instead of only the log.

### Everything else

**Fail fast; never substitute a value.** Do not swallow errors, default a missing value, or skip a
row to keep a run alive when the value is required for a correct figure. Raise `DataIntegrityError`
in parsing and event creation, `ProcessingError` in the engine. Route "the input cannot support
this computation" conditions through `src/processing/data_gaps.py`, and choose the severity
honestly — recording a condition as a warning asserts the declared figures are still safe. When you
do raise, check every case first and report them together, so one run identifies the whole problem.

**Verify your rationale, not just your citations.** A reason given in a comment, a commit message or
a document is a claim, and a plausible one is the hardest kind to catch. Check it, or mark it
unverified. The most damaging error in this repository's history was an engineering rationale that
was not merely unproven but incapable of being true, and it propagated into four documents and a
user-facing message before anyone tested it.

**Use `Decimal`, constructed from strings.** All money and quantity arithmetic runs at
`INTERNAL_CALCULATION_PRECISION`. `Decimal("123.45")`, never `Decimal(123.45)`.

**`data_import/` is read-only.** It is the source of truth for input; the application must never
write to it. Working copies go in `data/`. See `input_data_spec.md` for the naming scheme and
column specifications.

**This repository is public.** Account data must never reach a commit — no holdings, identifiers or
amounts. Public documents state the mechanism; instance data stays in gitignored notes.

## Ground rules

After modifying or extending application code: never change pre-existing tests without asking the
user and explaining why it is, without doubt, necessary.

After modifying or extending test code: never change pre-existing application code without asking
the user and explaining why it is, without doubt, necessary.

Never fit tests to the application. Fit them to the requirement, and ask when the requirement is
ambiguous — do not make tests pass for their own sake.

Never change legally relevant behaviour in application code or tests on the strength of a legal
requirement not already written into `reference/`. Extend the store first, via
`reference/research/research-strategy.md`.

## Repository documentation

- `PRD.md` — product requirements; the functional spec the engine is built against
- `README.md` — user-facing setup, Flex Query configuration, manual data export
- `input_data_spec.md` — IBKR CSV column specifications and the `data_import/` naming scheme
- `reference/INDEX.md` — the tax law library directory
- `reference/research/research-strategy.md` — how that library may be extended
- `docs/contribution-standards.md` — what a change must satisfy before it lands
- `tests/docs/` — behavioural specs and coverage analysis
- `VALIDATION_REPORT.md` — real-data validation results

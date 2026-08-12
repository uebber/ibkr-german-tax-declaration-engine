# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

This file states **how the project is built, run, verified and validated**, the categories a
change may be, and the discipline that governs anything with a legal consequence. It deliberately
contains **no tax content** — no form line numbers, rates, thresholds or year rules. Those live in
`reference/`, which is the only place they may live. If you find a legal fact stated here, it is a
defect: remove it and cite the reference instead.

## Project Overview

Generates the figures for a German tax declaration (Anlage KAP, KAP-INV, SO) from Interactive
Brokers Flex Query CSV exports. It handles FIFO lot tracking, currency conversion at ECB rates,
corporate actions, options and futures, and investment-fund taxation.

The output is a number a person puts on a tax return. That single fact sets the standard for
everything below: **a wrong number that looks plausible is worse than a crash.**

## Before you start

**Name the category. Exactly one. State it before the first edit.**

If the work needs two, it is two changes — do them in order, store before code, and say so. If you
cannot name one, stop and ask; do not pick the nearest fit. Commit subjects carry it:
`fix-func(engine): …`, `ks-maint(reference): …`, `feat-ux(docs): …`.

| Band | Category | Scope |
|---|---|---|
| **A** | `feat-func` | Expands the tax events or asset types the engine can process. |
| **A** | `fix-func` | Moves a declared figure, or where it lands, from wrong to compliant. |
| **A** | `ks-maint` | Brings `reference/` up to current law after an audit trigger. Changes no behaviour. |
| **B** | `feat-ux` | Reduces the effort of getting from broker export to a checked declaration. |
| **B** | `fix-ux` | Corrects presentation that misleads, without moving a figure. |
| **B** | `fix-nonfunc` | Removes a way the engine can fail, a way a failure can go unnoticed, or a way this repository can disclose what it must not. |
| **B** | `refactor` | Restructures code for a specific imminent change. Output-identical. |

**Band A changes what a correct figure is, or produces one. Band B must provably not move one.**
The axis is ground truth, not figure movement — `ks-maint` touches no figure and no code, but it
moves the standard every figure is measured against, which is the one consequence a parity run
cannot see.

Three boundaries that decide categories people get wrong:

- **Documentation is not a category.** A knowledge-store update rides with the `feat-func` or
  `fix-func` that needs it, store commit first. A genuine documentation improvement is `feat-ux`
  or `fix-ux` — for this file the user is the next agent, and the target is fewer wrong turns and
  fewer files to open.
- **If a change alters which figure appears against which form line, it is `fix-func`, not
  `fix-ux`.** Presentation-only means the figures are identical and were compared.
- **A leftover is not its own change.** An unused import, a stale comment, a dead reference: it
  goes with whatever change next touches that file, under that change's category. Do not stop and
  ask over a one-line deletion. If a leftover must stand alone, sort it by what it *does*:
  - a comment or docstring asserting something false — a guard that exists, a contract the code
    does not honour — is `fix-nonfunc`, because the next reader trusts it and does not add the
    check. It takes the calibration gate: state what a reader would have concluded.
  - a dead reference to something this repo does not contain is `fix-ux`. It misleads a reader,
    hides no failure, moves no figure.
  - an inert leftover is `refactor`, and on its own it will not clear the bar below. **That is
    the answer, not a gap.** A category that waves these through lets residue accumulate
    unexamined, and residue is how a half-converted tree stays invisible.

`refactor` is **restricted**: permitted only when it is highly beneficial for a specific, imminent
`feat-*` or `fix-*`, and demonstrably reduces complexity. Speculative restructuring is not a
change this repository accepts.

### Gates

Each gate carries the failure it prevents. Read the second line before deciding a gate is
overhead.

**Every change:**

- **Clean-clone suite green** (see Verification).
  Developer state passes tests the repository cannot.
- **No silent default.** Anything unresolvable raises, after collecting every case.
  A substituted value understates income invisibly; a crash does not.
- **No account data, and no reference to a document this repo does not contain.**
  This repository is public, and a pointer to something absent is a false statement.
- **No half-converted tree left behind.** Enumerate the sites, and show the enumeration is
  exhausted — **including the docs, comments and docstrings that assert something about what you
  changed.** Grep for the old form and give the count.
  A conversion can be fully understood and still incomplete: the worst instance here converted
  three selectors and left a fourth in the same file, one screen from a comment explaining the
  rule it broke. The prose half is missed more often than the code half — a protocol survived the
  change that made it unnecessary, and a docstring went on describing a defect that had been
  fixed.
- **Look at what you are about to destroy or overwrite, even when a documented step tells you
  to.** A command in this file is a claim that running it is safe and still necessary, and claims
  decay like any other. One `ls` is cheaper than the recovery.
- **The standing constraints below honoured**, any departure explicitly asked for and answered.
- **Every factual claim in the description says how it was measured.**
  An unmeasured claim reads exactly like a measured one.
- **What the exports contain is settled in `data_import/`, never assumed.** It is ground truth for
  input behaviour as `reference/` is for the law, and the same rule applies: look before you
  claim. Any claim that a column can be absent, blank or malformed is counted there before it
  becomes work — the condition that would produce the wrong figure, not a precursor of it, as N of
  M rows across the window. Zero means stop: write the assumption where the code relies on it, and
  open nothing — **the assumption, not the count**, which belongs in the description (see "A
  comment may rest only on what a reader of this repository can check" under Engineering rules).
  Does not reach a `reference/` deviation, a defect at zero incidence because there
  the law is ground truth and the data is not.
  Every other gate here points at the harm of a silent substitution and none asked whether the
  input ever goes missing. On 2026-08-09 that produced two issues (#72, #73) for failures with
  zero occurrences in five years, in a session whose one costly error sat unread in the report.

**Band A adds:**

- The requirement was written in `reference/` *before* the code, cited to the sentence, and
  verified against all nine items of the Validation Protocol in `docs/knowledge-store.md`.
- A `GT-<AREA>-<NNN>` claim ID cited in code, test or commit.
- The `docs/legal-implementation-map.md` row present and honest; `reference/INDEX.md` and
  `coverage-matrix.md` in step where the store changed.
- `feat-func` / `fix-func`: red-first verified with the actual count; parity measured with the
  assessment year named.
  A test that was never red proves nothing about the fix. Parity without a year is
  unfalsifiable — a change keyed to a form-year rule is identical for one assessment year and
  different for another.
- **Every input the figure depends on named, with what the code does when it is absent, and how
  often it is absent in fact.** Once, in writing, per figure. Inputs always present need no entry
  — and "always present" is the count above, not an impression. The ones that matter are where
  something is substituted and the run continues, and each is either removed or argued.
- `ks-maint`: no red-first and no parity — it changes nothing. Instead, **every claim the audit
  touched has its map row re-decided**, and each new `deviates` names the `fix-func` that will
  close it. A row left at `implements` because no code was touched, when the audit just moved the
  law underneath it, is the failure this category exists to catch.

**Band B adds:**

- Figures provably unmoved: parity measured with the assessment year named, or — where the diff
  does not touch `src/` — the statement that it does not.
- Zero map rows changed, zero claim IDs changed.
- `refactor`: probed site by site, not merely run.
  A green suite proves the covered sites were converted and says nothing about the rest.
  Probing one ledger-lookup site at a time once found five of fourteen the suite cannot observe
  at all.
- `fix-nonfunc`: **calibrated against a deliberately broken tree, stated in the description** —
  the red-first count for a code fix, the mutation the new test now catches for a blind-spot
  closure, what was grepped across the whole tree for a disclosure fix.
  An instrument nobody broke on purpose reports green whether or not it can see anything. This
  is the most expensive gate here and the one with the worst compliance record.

## Setup

Uses `uv`. Install it first: https://docs.astral.sh/uv/getting-started/installation/

```bash
uv sync                                    # creates .venv and installs dependencies
cp src/config_example.py src/config.py     # config.py is gitignored; it holds personal data
```

`src/config.py` carries the default tax year, taxpayer identity for reports, the interactive
classification switch, and Flex Query IDs. `config_example.py` is the tracked template and must
define every attribute `src/` reads — `tests/test_config_example_completeness.py` enforces this.

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
with no developer state:

```bash
cp src/config_example.py src/config.py && uv run pytest -q
```

The `cp` still overwrites `src/config.py`, which is gitignored and holds the Flex Query IDs and
taxpayer identity. Back it up first, or run the protocol in a throwaway worktree
(`git worktree add /tmp/cc HEAD --detach`), which is a truer clean clone anyway.

**Do not put `rm -rf cache` back into this line.** It stood there until issue #51, by which time
its only remaining effect was destroying the hand-made asset classifications — which nothing
rebuilds automatically. It did exactly that once, and the resulting unclassified instrument
blocked a real-data parity gate. Hermeticity is enforced by construction instead, in two autouse
fixtures in `tests/conftest.py`: every `src.config` cache path is redirected into a per-test temp
directory, and any access reaching the real `cache/` raises. A caller that genuinely must clear
the directory snapshots and restores it on a `trap ... EXIT`; `scripts/parity_check.sh` is the
model.

**A green suite is weaker evidence than it looks.** Coverage is uneven and the gaps are not where
the diff is. This is why the gates ask for mutation probes and calibration rather than a passing
run.

**Where the suite is blind.** Probe these by mutation; running the suite will not tell you.

- **The historical FX/currency replay.** Reversing the chronological order of every historical
  currency event leaves the suite green. The same mutation on securities fails a test.
- **The ends of a new channel.** When the data-gap channel was added, its second recording site
  and its entire report-rendering block could each be deleted with the suite green. Probe the
  ends, not the middle.
- **Anything a start-of-year snapshot can rebuild.** The reconcile phase compares against the
  Positions file, so a defect that loses lots stays invisible in quantity, cost basis, proceeds
  *and* gain — only the acquisition date is wrong. A test asserting those four figures on a
  scenario with an SoY snapshot is weaker than it looks.
- **A dispatch that falls through without an `else`.** The historical replay ignored four event
  kinds this way, and each affected instrument reconciled against a reported zero — which clears
  the ledger and hides the disagreement. Probe by reconciling at every yearly snapshot, not only
  the tax year's. Written up in `docs/research_historical_replay_defects.md`.
- **A ledger that the opening snapshot reconciles away again.** The checkpoint marks are one of
  four sources of the accounts a FIFO ledger is built for, and deleting that source leaves the
  suite fully green: an account appearing only in a mid-window mark is reconciled back to the
  opening snapshot, which does not list it. Anything whose only effect is confined to an interval
  the final reconciliation overwrites is invisible the same way.

Add to this list whenever a probe finds a site the suite cannot observe.

Test fixtures are YAML specs in `tests/fixtures/` with helpers in `tests/support/`;
`tests/docs/` holds the behavioural specs they encode.

## Validation against real data

**Assessment years before 2023 are never processed. Every end-to-end run, regression baseline
and parity capture against real data starts at VZ 2023.** Earlier data is still *imported* — the
transaction files from 2021 on are concatenated to build the historical FIFO ledger, so a lot
acquired in 2021 keeps its real acquisition date and cost basis. What is forbidden is treating a
figure from VZ 2021 or VZ 2022 as a result, a baseline or a parity capture.

VZ 2021 has no opening position at all: `Positions-2020-EoY.csv` does not exist
(`src/data_preparation.py:211`). VZ 2022 realises gains against a cost basis nobody observed —
lots carried in from before the data window have no acquisition date, so reconciliation discards
the reconstruction and synthesises a single lot dated `f"{tax_year-1}-12-31"`
(`src/engine/fifo_manager.py:400`). The opening quantities at 2021-01-01 are derivable, but a
derivable quantity does not make an unobserved date safe to invent; see the fallback rule under
Engineering rules. The measurement establishing VZ 2023 as the first year whose opening lots are
all traceable is in `VALIDATION_REPORT.md` § 2026-08-06.

**The failure this prevents is an invented figure, not a visibly wrong one.** A contaminated year
still produces plausible output, because a synthesised lot carries a well-formed date no
downstream consumer can distinguish from a measured one.

- `validate_ledgers.py` — reconciles start-of-year and end-of-year positions per tax year. Its
  `find_complete_years()` selects on `Positions-{Y}-SoY.csv`, which is not what the pipeline
  opens from; pass `--year` explicitly rather than trusting the sweep to exclude an early year.
- `scripts/parity_check.sh` — captures a full run (console, log, PDF) and compares two captures,
  for proving a change is output-neutral. It is cache-hermetic and order-sensitive; read its
  header before relying on it, and take a same-tree control capture first so ambient
  nondeterminism is not read as a change. What a parity result must state to count is a gate,
  above.

See also the reconciliation invariant below — the engine enforces it on every run, not only when
validating against real data.

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

`reference/` is the single source of truth for every legal requirement this engine implements.
**`docs/knowledge-store.md` governs it** — what counts as a source, the Validation Protocol, claim
IDs, the binding to `docs/legal-implementation-map.md`, and the only sanctioned procedure for
extending the library. Read it before any Band A change.

### The Ground Truth Rule (non-negotiable)

**Never implement, change, or justify legally relevant behaviour from a source outside
`reference/`.** Not from web search, not from a linked PDF, not from your own knowledge of German
tax law, not from what the existing code appears to assume.

**Legally relevant** means anything that can change a declared figure or where it lands —
including the expected values of any test asserting one.

Look it up in `reference/` first, and read the file rather than assuming what it says. If it is
covered, the reference wins — over general knowledge, and over the code. If it is not covered, or
is stale, ambiguous or contradicted, **stop**: extend the store first, by the procedure in
`docs/knowledge-store.md`, then implement citing it. Research done in conversation and not written
into `reference/` is not ground truth.

If code and a reference file conflict, **surface it**; do not silently follow the code.

Nothing enforces this rule — a test can check that a cited claim ID resolves, never that a change
needing a citation carried one. Its mirror image *is* enforced: `reference/` states law and
contains no implementation state, which is the Purity Rule in `docs/knowledge-store.md`, checked
by `tests/test_reference_purity.py`.

### When the sources tie: lean to the taxpayer

**A legal grey area is not a data gap, and the fallback rule under Engineering rules does not
reach it.** That rule governs a missing *input*, where any direction you pick is invented. A grey
area is the opposite: the data are complete and the figure is well founded under either reading;
what is unsettled is the law. Choosing between them is a position, not a fabrication.

**In a genuine grey area, lean to the taxpayer.** This produces a *declaration*, not a submission
to a moot court — the favourable reading is a position the Finanzamt can assess differently, and
being assessed differently is the normal working of the process.

**The permission is narrow.** Every one of these must hold; they are conditions, not factors to
weigh against each other:

- **Never against Tier 1 or Tier 2**, whichever way it falls, and administrative guidance binding
  the Finanzamt rather than the taxpayer changes nothing. A reading that needs the statute or the
  guidance to be wrong is a dispute, and a dispute is not something to bake into a figure.
- **BMF must not have stated otherwise**, including by clear implication. What is required is that
  the administration has *not spoken* — a shallow search does not meet this.
- **The ambiguity must be documented as disputed, not constructed.** With enough ingenuity
  anything has two readings, and that ingenuity is what this condition exists to disallow.
- **It never licenses an invented input.** If the figure is uncertain because the data are
  missing, you are in the fallback rule, not this one.
- **Ask, and get permission, before implementing** — both readings, the authority behind each,
  what the choice moves. The taxpayer signs the return; a grey area is never resolved in a commit.

The choice and the evidence that each condition was met go in
`docs/legal-implementation-map.md` against the claim ID.

## Engineering rules

### SoY → EoY must reconcile (non-negotiable)

**After the ledger has run, the calculated end-of-year position must equal the position the broker
reports.** No tolerance, no override. The engine checks every asset, then aborts naming all of
them; it emits no figures, form lines or PDF from a ledger that does not reconcile.

Cash-balance (currency) reconciliation is deliberately *not* fatal: its causes are input
completeness rather than a ledger disagreeing about a holding. It is recorded as a data gap so it
reaches the report instead of only the log.

The rule enforces itself at runtime. These two corrections do not, and both have already misled
people here:

- **An incomplete prior-year trade history cannot cause a mismatch.** The start-of-year quantity
  is *taken from* the positions snapshot, not reconstructed — the historical replay supplies cost
  basis and acquisition dates, never the running quantity. Missing earlier years cannot move it.
  A mismatch always points at the tax year's own input, or at the engine's handling of it: an
  absent trade or corporate action, an unlinked option exercise, one instrument resolved under two
  identifiers. Do not go looking for old data, and do not relax the check on that theory.
- **A green reconciliation does not prove the lots are right.** The comparison is of net quantity.
  A defect that misassigns lots without changing the net — the wrong lot consumed, a wrong
  acquisition date, a wrong basis — reconciles clean. It is a floor, not a guarantee.

### Everything else

**Fail fast; never substitute a value.** Do not swallow errors, default a missing value, or skip a
row to keep a run alive when the value is required for a correct figure. Raise `DataIntegrityError`
in parsing and event creation, `ProcessingError` in the engine. Route "the input cannot support
this computation" conditions through `src/processing/data_gaps.py`, and choose the severity
honestly — recording a condition as a warning asserts the declared figures are still safe. When you
do raise, check every case first and report them together, so one run identifies the whole problem.

**Derive freely; never invent a stand-in for a missing import.** Computing a value from inputs that
are all present is fine, and often better than importing it — a per-unit price from a value and a
count. What is forbidden is a value standing in for an input this run does not have: a fallback
lot's `acquisition_date` set to `f"{tax_year-1}-12-31"` is the missing import wearing its clothes,
and downstream it is a well-formed date no consumer can tell from a measured one. Standing in for
a missing input is a decision about someone's tax return, not an implementation detail — route it
through `src/processing/data_gaps.py` and let the run stop, or ask, but never both invent it and
continue. **Never add such a fallback without asking first:** a value missing often enough that you
are reaching for a default is a finding to report, not a hole to fill — and "often enough" is the
count under Gates, not an impression.

**There is no safe direction to be wrong.** "This can only overstate, which is the safer side" is
an argument for putting a number nobody can check on a tax return. Understatement versus
overstatement only ranks a gap that has *already been recorded*; it is never a reason to prefer one
wrong figure over another, nor a licence to compute through a gap instead of recording it. The
choice is between a figure and no figure, not between two figures.

**Verify your rationale, not just your citations.** A reason given in a comment, a commit message or
a document is a claim, and a plausible one is the hardest kind to catch. Check it, or mark it
unverified.

**A comment may rest only on what a reader of this repository can check** — the law in
`reference/`, the code, the test suite, `input_data_spec.md`. Not on one person's export: no row
counts from `data_import/`, no figures or outcomes from a particular run. Name the test that pins
the rule, or invent an example. A count that justified a decision goes in the commit description;
what belongs in the code is the reason — "a substituted value is an invented figure" — which
cannot go stale.

**Use `Decimal`, constructed from strings.** All money and quantity arithmetic runs at
`INTERNAL_CALCULATION_PRECISION`. `Decimal("123.45")`, never `Decimal(123.45)`. Nothing catches a
float construction — `tests/test_precision.py` tests the arithmetic, not how the value was built.

**`data_import/` is read-only.** It is the source of truth for input; the application must never
write to it. Working copies go in `data/`. See `input_data_spec.md` for the naming scheme and
column specifications. Nothing enforces this either.

**This repository is public.** What must never reach a commit is **anything from which the size of
the account can be inferred**: monetary amounts at portfolio scale, cash balances, position values,
settlement proceeds, realised gains, and the account number. Not in code, not in tests, not in
docs, not in a commit message. Illustrative figures are invented, never copied from a real export —
copying is how every violation here happened, because real data makes an example feel concrete.

**Deliberately not in scope**, so that a cleanup does not turn into an unbounded rewrite: ticker
symbols, instrument descriptions, ISINs, IBKR contract identifiers (a Conid names a contract, not a
person), transaction and action IDs, and small non-round figures used to make an example real.
Those identify *instruments*, not wealth, and scrubbing them churns test fixtures that key off
symbols and descriptions for nothing the owner cares about.

**Check before committing, since nothing else will.** Public documents state the mechanism;
instance data stays in gitignored notes. Cross-check the staged diff against `data_import/`:
extract the monetary columns, and grep the diff for those values. A leak is a figure that appears
in both. There is no tripwire, and this is the rule with the worst record here — **four** cleanups
after publication, the most recent in August 2026.

## Standing constraints

Nothing enforces these. They hold for every category.

- After modifying or extending application code: **never change a pre-existing test** without
  asking the user and explaining why it is, without doubt, necessary.
- After modifying or extending test code: **never change pre-existing application code** without
  the same ask.
- **Never fit tests to the application.** Fit them to the requirement, and ask when the requirement
  is ambiguous — do not make tests pass for their own sake.

## Repository documentation

- `PRD.md` — product requirements; the functional spec the engine is built against
- `README.md` — user-facing setup, Flex Query configuration, manual data export
- `input_data_spec.md` — IBKR CSV column specifications and the `data_import/` naming scheme
- `docs/knowledge-store.md` — how `reference/` is managed, extended, and linked to the code
- `reference/INDEX.md` — the tax law library directory
- `reference/research/open-legal-questions.md` — points no Tier 1/2 source settles, both readings
- `docs/legal-implementation-map.md` — each legal requirement → the engine's position → the tests
- `tests/docs/` — behavioural specs and coverage analysis
- `VALIDATION_REPORT.md` — the test suite audited against `reference/`, plus the real-data validation log

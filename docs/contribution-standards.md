# Contribution standards

What a change to this engine has to satisfy before it lands. Written for the PR train in
issue #15, but it applies to any contribution.

This is not a style guide. Every item below exists because a change that looked correct,
tested green, and read plausibly turned out not to be — usually in a way that would have
moved a declared tax figure, or hidden that one was wrong. `docs/pr-train-review.md` is the
evidence; this file is the distillation.

Read it as a checklist you apply to your own diff before asking anyone else to.

---

## 1. Root every legally relevant behaviour in `reference/`

The rule is in CLAUDE.md and it is the one that gets PRs sent back. "Legally relevant" means
anything that can change a declared figure or where it lands: form-line mappings,
Teilfreistellung rates, loss-offsetting and ring-fencing, holding periods, thresholds, caps,
Basiszins values, withholding-tax treatment, event classification with tax consequences, and
the expected values in any test asserting those.

**Order of operations:** look it up in `reference/` → if covered, the file wins over your own
knowledge *and* over what the code currently does → if not covered, stop and extend the store
first, to Tier 1/2, following `reference/research/research-strategy.md`. Research done in a
conversation and not written into `reference/` does not count.

Three failure modes seen repeatedly, in increasing subtlety:

**a) Citing a provision the store does not contain.** Three PRs cited a rule that was simply
absent from `reference/` — the coverage-matrix row pointed at a file that did not carry the
controlling sentence. Grep before you cite; note that grepping for "Satz 7" can hit the wrong
Absatz.

**b) Citing by section instead of by sentence.** `§108 AO` is true of the anniversary rule and
*also* drags in §108 Abs. 3 AO, which this engine does not implement and which is an open
question capable of moving a figure. `§20 Abs. 6 Satz 5` means opposite things before and
after 02.12.2024. **The unstated Absatz is where the unimplemented rule hides.** Cite to the
sentence. Validation Protocol item 3 is not pedantry.

**c) Citing something the store already contradicts.** One PR's docstrings asserted that
per-Depot FIFO is statutory under §20 Abs. 4 S. 7 EStG when the reference file already
recorded that the statute says no such thing (it is Tier 2 — BMF, by Randziffer). If code and
`reference/` disagree, surface it; do not follow the code.

And a fourth that is not about citations at all:

**d) Check your *rationale*, not just your citations.** The worst factual error in this
review was made by the reviewer, not a contributor: a plausible-sounding cause for a
reconciliation failure ("the trade history does not reach back far enough") that was not
merely unverified but *incapable* of being true, because the start-of-year quantity is taken
from a snapshot and no prior-year gap can reach it. It had propagated into the README, the
PRD, a test spec and a user-facing error message before anyone questioned it. A rationale in
a comment or a commit message is a claim. Verify it like one.

---

## 2. For every new guard, write the tree that should trip it

Four of the first five PRs that added a checking mechanism shipped one that **could not see
what it claimed to check**, and all four were green:

- a test suite silently reading the developer's real `cache/`, so classification-dependent
  tests passed on data not in the repo;
- a real-data parity gate blind to classification changes, because the pipeline both reads
  and writes the classification cache and the baseline capture warmed it — it certified
  "output-neutral" while a holding moved between tax categories;
- a config-leak tripwire that passed green on the exact leak shape it was written for
  (leak early, restore late), and ignored every global except the one in its name;
- a registry↔reference consistency test that compared two hand-kept copies of the same
  numbers — both containing the wrong-statute rows it existed to catch.

So: **calibrate the instrument.** Deliberately break the thing your guard watches, in each
distinct way it can break, and confirm the guard fails. Say so in the PR. A green result from
an uncalibrated instrument is worth nothing.

The same applies to a documented contract with **no** instrument: one PR shipped an explicit
"ordering contract" and zero tests, and the existing suite could not observe it — reversing
every historical currency event left all 466 tests green. If you document a contract, write
the tree that violates it.

---

## 3. Know where the suite is blind, and probe there

A green suite on a mechanical refactor proves the *covered* sites were converted. Probing one
ledger-lookup site at a time — revert it, run everything — found **five of fourteen** the
suite cannot observe at all. Covered sites fail loudly (2–105 failures); the uncovered ones
are silent.

Known blind spots, as of this writing:

- **The historical FX/currency replay.** Reversing the chronological order of every historical
  currency event leaves the suite green; the same mutation on securities fails one test. Probe
  currency changes *by mutation*, not by running the suite.
- **The ends of a new channel.** For the data-gap channel, both the second recording site and
  the entire report-rendering block could be deleted with the suite green. Probe the ends, not
  just the middle.
- **Anything an SoY snapshot can rebuild.** Pass 3 reconciles against the Positions file, so a
  bug that loses lots is invisible in quantity, cost basis, proceeds *and* gain — only the
  acquisition date is wrong. A test asserting only those four figures on a scenario with an
  SoY snapshot is weaker than it looks.

---

## 4. No silent defaults, ever, in the direction of less income

The engine is fail-fast by policy (CLAUDE.md). The recurring anti-pattern is a local
convenience decision that substitutes a value when the input cannot support the computation:

- a redemption with a blank proceeds column producing a loss equal to the full basis;
- an unreadable date pair falling through to "exempt", which drops a disposal out of Anlage SO;
- an unsortable event getting a sort key that places it *before every other event*;
- an End-of-Year reconciliation failure logged and then ignored.

Each looked harmless locally. Each understates income, invisibly, in the output. If a value is
required for a correct figure and you cannot derive it, raise — `DataIntegrityError` in
parsing, `ProcessingError` (or a subclass) in the engine. Route "the input cannot support
this" conditions through `src/processing/data_gaps.py`, and choose the severity honestly: a
WARNING is a claim that the declared figures are still safe.

When you do raise, **check every case first and then report them all at once.** One run should
identify the whole problem, not one item per attempt.

---

## 5. Make the PR description survive checking

Across nine reviewed PRs the code and tests were consistently sound and the prose was not.
Twelve citation or claim errors; two descriptions had nothing wrong in them. Specific things
that turned out false:

- **"Real-data parent-parity: IDENTICAL"** — parity results are year-specific. A change keyed
  to a form-year rule is identical for one assessment year and different for another. Say
  which year you measured.
- **Red-first counts.** If you say seven tests fail without the fix, ten failing is a signal
  you have not run it.
- **"Contains: code, tests"** when the diff has no tests.
- **Conditions "fixed"** that do not occur in this repo's data — check before asserting them
  as fact.
- **Justifications that cannot fire**: one comment defended downgrading a warning because "the
  rate reconciliation below confirms consistency", where the reconciliation was arithmetically
  incapable of failing.

Practical form: for each factual claim in your description, name how it was measured.

---

## 6. Housekeeping that keeps costing review time

- **No references to documents this repo does not contain.** Working-plan identifiers
  (`rework2-plan AR6`, `legal-review finding F4`) appear in production source, test docstrings
  and commit messages. Those files are not here. Five separate cleanup commits so far.
- **Do not fit tests to the application.** Fit them to the requirement, and if the requirement
  is ambiguous, ask. One spec group had been written around the engine's behaviour and
  contradicted the PRD it cited for coverage.
- **Account data never reaches a commit.** This repository is public. Public documents state
  the mechanism; instance data stays in the maintainer's gitignored notes. Instruments in this
  documentation appear as `XYZ1`, `XYZ2`, …

---

## 7. Before you open the PR

- [ ] Every legally relevant change traces to a `reference/` file that actually says it, cited
      to the sentence, with the coverage matrix updated.
- [ ] Every new guard calibrated against a deliberately broken tree — and the calibration
      stated in the description.
- [ ] Mechanical refactors probed site-by-site, not just run.
- [ ] No new silent default; anything unresolvable raises, after collecting all cases.
- [ ] Red-first verified, with the actual count.
- [ ] Real-data parity measured, with the assessment year named.
- [ ] Clean-clone check: `rm -rf cache && cp src/config_example.py src/config.py && uv run pytest -q`.
- [ ] No account data, and no references to documents outside this repo.

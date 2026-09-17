# PR review and merge train

Last updated: **2026-09-17**. Repository:
[`uebber/ibkr-german-tax-declaration-engine`](https://github.com/uebber/ibkr-german-tax-declaration-engine).

This document tracks work needed to review and merge the train. Accepted follow-up
work belongs in [post-merge-todos.md](post-merge-todos.md); merging does not close it.
Apply [review-criteria.md](review-criteria.md) to every PR.

## Resume here

**Active #88 correction:** the maintainer authorized #88 together with PM-005.
Live main is `89e7c24`, original head `4da165a`, isolated integration `0b1910e`.
The initial candidate fails every supported real-data year despite 1,293 passing
tests. Option-order correction restores parity in diagnostic captures. See
[PR #88 review](pr-88-review.md) for findings and the ongoing correction plan.
No candidate is accepted or published. PM-005 is active in this run; other accepted
follow-up remains open. Any further figure change needs explicit approval.

**TR-008 update, 2026-09-17:** the maintainer confirmed that the commission credit
is a refund of an earlier overcharge and approved the measured VZ 2024 difference.
The restoration on `fix/pr87-commission-refund` is verified and authorized for merge.
`FeeEvent.is_refund` preserves the cash direction in current and historical replay;
the blanket import refusal is removed. All VZ 2023–2025 runs complete with PDFs.
2023/2025 match pre-#87 main; all parsed 2024 form lines match the working #87
candidate before the refusal, with the approved currency correction against
pre-#87 main. Suite: 1,231 passed, 1 skipped. Source: `VALIDATION_REPORT.md`, TR-008.
The earlier refusal/acceptance statements below describe the #87 merge, not the
subsequent decision to restore processing. PM-005 remains open; #88 follows TR-008.

1. Check the working branch, uncommitted files, remote `main`, and live PR heads.
   Recorded hashes below are observations, not permission to overwrite newer work.
2. Complete **#87's verified correction and merge**, documented in
   [pr-87-review.md](pr-87-review.md). F1 now refuses disposals from undated
   reconstructed lots; F2 explicitly dispatches currencies and refuses unattributed
   commission credits. The inherited option-linking gap is accepted as PM-005.
3. Update the relevant PR branch onto corrected history before accepting it.
   All remaining branches were reported `CONFLICTING` against `main` at the last check.
4. Review its incremental changes, verify against the knowledge store, and run both
   the full suite and comparisons against the maintainer's actual data.
5. Record the reviewed SHA and evidence. Resolve blockers before merge; link any
   accepted bounded architectural follow-up to its `PM-*` entry.

## Scope and authorization

- #81-#84 were closed without merging at the maintainer's request; they are the
  older series and are not candidates to revive.
- The maintainer authorized the three corrections and merge of **#86**. That work
  is complete. The subsequent request authorized review/merge of **#87**, subject
  to the review gates. The maintainer then authorized fixing the blockers and merge,
  and explicitly deferred option linking as PM-005. F1/F2 are implemented locally;
  complete verification and record the published/merged revision below.
  #88-#92 have not been accepted or authorized for blanket merge.
- A stacked rebase was recommended, but **has not been performed**. Update remote
  branches only within the authorization of the active task.
- The maintainer explicitly said local-branch integration is unnecessary. Review
  against the GitHub PR base and accepted predecessors. Do not bring local issue
  #76 work into the contributor's branches or make it a merge gate.
- At handoff, the main workspace was on local `fix-func-76-lending-fee-anlage-so`
  at `3183f18`. Its source predates merged #86. Preserve that work; use an isolated
  checkout for train changes. Untracked `docs/knowledge-store-audit-instructions.md`
  is unrelated user work.

## PR state

All open PRs target `main`, but their commits form a dependency chain. Their GitHub
diffs can include earlier unmerged PRs. Review against the preceding head to isolate
each change, then test the complete candidate tree.

| PR | Scope | Last observed head | Own commits in original stack | Review/merge state |
|---|---|---|---:|---|
| [#86](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/86) | Per-account snapshots | `5d25270` | 4 original + 1 corrective | Merged as `8b7e49f`; [review](pr-86-review.md) complete |
| [#87](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/87) | Per-account securities FIFO | `2c8c45b` | 1 | Reviewed: rework before merge; local updated candidate `0d5c958`, unpublished; [findings](pr-87-review.md) |
| [#88](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/88) | Internal transfers | `4da165a` | 1 | Pending review and branch update |
| [#89](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/89) | Per-account currency | `513ab0f` | 2 | Pending review and branch update |
| [#90](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/90) | Stock grants | `6d89379` | 6 | Pending review and branch update |
| [#91](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/91) | Purchase transaction taxes | `39db47a` | 4 | Pending review and branch update |
| [#92](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/92) | Capital-income reporting breakdown | `940870e` | 2 | Pending review and branch update; targeted checks only |

Verified `main` at handoff: `8b7e49febcf1035d07391f9d52cfd40f0b0f9411`.
Corrective commit: `5d25270eb36a43846e666d2150b8ecb48113fc1a`.
Original #86 head: `ea45c429acfa5b54e6d5830c22b0a1effdd9b6c5`.
Original base: `5a64079c277451da1b082a1d7f753821cc68466f`.

## Active train tasks

| ID | Task | Status | Completion evidence |
|---|---|---|---|
| TR-001 | Update #87-#92 onto corrected accepted history | In progress locally for #87; no remote update or rebase | #87 local merge candidate `0d5c958` preserves corrected `main`; conflicts resolved and shipped suite green. Findings prevent acceptance. #88-#92 unchanged |
| TR-002 | Review #87 | Accepted with required follow-up; verified correction `46aa37b`, publication/merge pending | [Review](pr-87-review.md): 1,224 passed/1 skipped clean; 1,225 passed with exports; 13 correction regressions pass. Option linking deferred as PM-005. VZ 2023 parity; VZ 2024/2025 safely refuse an unclassified refund |
| TR-003 | Review #88 | Pending | Same evidence; assess delivery/receipt boundaries, ordering, lot preservation and partial-failure handling |
| TR-004 | Review #89 | Pending | Same evidence; assess currency authority, account independence and shared ledger abstractions |
| TR-005 | Review #90 | Pending | Same evidence; assess grant lifecycle, acquisition basis and income-reporting completeness |
| TR-006 | Review #91 | Pending | Same evidence; assess trade-cost consistency and compatibility with the maintainer's exports |
| TR-007 | Review #92 | Pending | Same evidence; assess report reconciliation, calculations versus presentation and output parity |

Each review includes its merge decision. Record the merge commit only after GitHub
confirms it. Keep unresolved correctness findings in this workstream with IDs such
as `PR87-F1`; do not move them to post-merge TODOs to make a PR appear ready.

### Branch-update procedure

The proposed order is #87 onto updated `main`, then #88 onto updated #87, continuing
through #92. Record the original dependency heads before rewriting so each step
replays only that PR's own commits. Preserve original refs for recovery and use
explicit expected remote heads with `--force-with-lease` if publishing a rebase.
A merge of updated history is an alternative; decide within the active task.

The first preview for #87 found conflicts in `src/parsers/parsing_orchestrator.py`,
`docs/legal-implementation-map.md` and `VALIDATION_REPORT.md`. Preserve the corrected
behavior and both relevant validation histories. Do not resolve by blindly choosing
one side. Refresh `main` again before each subsequent review/merge.

The #87 review resolved those conflicts in a **local merge**, not a rebase:
`0d5c958a4d7d6048bb3365937a40107db73b4cf7` on `review/pr87-account-fifo`, parents
`2c8c45b710f121c2d841872e58a73d53982cae50` and
`8b7e49febcf1035d07391f9d52cfd40f0b0f9411`. The candidate is unpublished and not
accepted. The remote head remains the original PR commit. Do not discard the
candidate merely because the source worktree still contains separate failing
review probes; they are preserved durably as `pr-87-probes.py.txt`.

### #87 initial review evidence and correction

Corrective code: `46aa37b65e6cc9a6a1d922d78abd7f8cb16ca337`. Final clean checkout:
**1,224 passed, 1 skipped**; copied exports: **1,225 passed**. The 13 new tests
give **12 failed, 1 passed** on pre-fix `0d5c958` and **13 passed** after correction.
F1 is closed by refusal of securities disposals requiring unresolved lot history,
including long/short histories preserved through mergers. F2 is closed by explicit
currency dispatch and refusal of unclassified positive commission adjustments.
This is not an implementation of refund taxation: VZ 2024 and 2025 cannot complete
until the unidentified refund's original transaction/service and treatment are
established. Both now exit 1 without a PDF; VZ 2023 remains identical to accepted
base. No input override was used. PM-005 records the explicitly deferred option
linking defect. The following bullets retain the **pre-correction** findings.

- PR87-F1: historical account moves without transfer records can produce an
  invented acquisition date and still complete. Reproduced on #87 and through #92.
  #88 `4da165a` supplies a partial resolution for **provided** transfers; five
  provenance controls pass, but the absent-export path remains unsafe.
- PR87-F2: naming the sole account changes the commission-refund/currency dispatch.
  Reproduced synthetically and on the maintainer's VZ 2024 exports. The label-equivalence
  probe first passes at #89 `513ab0f`, but that restores the older refund path and
  does not establish correct refund taxation. Requires explicit treatment and checks.
- PR87-P1: simultaneous option exercises in two accounts collide in a shared
  linker. Each account alone passes. Also fails on accepted base and #92; this is
  an inherited boundary defect, not an introduced regression or accepted TODO.
- Candidate shipped suite: **1,211 passed, 1 skipped** without exports;
  **1,212 passed** with copied exports. Accepted base with the same exports:
  **1,194 passed**. The PR's 18 account tests give **11 failed, 7 passed** on base.
- VZ 2023 and 2025 console/PDF/gap codes match accepted base. VZ 2024 changes
  currency figures and removes a currency warning. All same-base controls match.
  Original input/cache/configuration hashes remain unchanged. Full evidence and
  reproduction commands are in [pr-87-review.md](pr-87-review.md).

## Correctness already fixed — preserve during updates

1. Incomplete acquisition cost must remain incomplete across rows/accounts and at
   checkpoint reconciliation. An explicit zero cost is a known value.
2. A price conflict must survive aggregation. Missing and conflicting observations
   are different states; independent price resolution can clear the conflict.
3. A prior position count does not prove the acquisition timing of surviving lots.
   When that timing is required for a positive Vorabpauschale, undated lots cause an
   error. Zero already established from the cap, distributions or rate needs no factor.

These fixes are in `5d25270` and its 36 regression cases in
`tests/test_snapshot_integrity.py`. They are **completed work**, not post-merge debt.
Checks on the original later heads showed #87 only partly addressed the first
finding; the other cases still failed through #92. Those branches need the merged
corrections before new results can be trusted. Their targeted checks were not full reviews.

## Verification baseline and reproducibility

- Corrected #86: **1,193 passed, 1 skipped** without private exports; **1,194 passed**
  with a copy of the maintainer's exports. Python 3.12.12; frozen `uv.lock` dependencies.
- Maintainer inputs: 34 CSVs, history from 2021-2025, one account and 87 position rows.
  No blank account, quantity, basis or price in those position rows. This cannot
  exercise multi-account behavior or all missing-input cases; synthetic tests remain necessary.
- VZ 2023, 2024 and 2025 completed with identical console reports and PDFs against
  `5a64079`, after stripping volatile PDF metadata. Data-gap codes were unchanged.
  Base control captures matched; checkpoint log wording changed as expected.
- Captures used fresh copies of saved classifications, FX rates and fund prices,
  the tracked configuration template, non-interactive execution and automatic NAV
  fetching disabled equally on both sides. No input gap was overridden.
- Run the normal application entry point for real-data validation. Keep earlier
  transaction history but never process actual assessment years before 2023.
  Use `scripts/parity_check.sh` only after reading its cache and output handling;
  all runs must use disposable copies of private state.
- Preserve original `data_import/`, configuration, caches and declaration history.
  Private captures stay gitignored/outside the repository. A matching output proves
  regression parity on that input, not correctness of every pre-existing figure.

## Update after each meaningful step

Record base/head hashes, the incremental review range, new findings, fixes, test
commands/results, actual-data assessment years and comparison limits. Before merge,
check for fixes in later commits and credit them explicitly. After merge, record
the merge hash, next PR and linked `PM-*` entries. Update the post-merge list only
if the status of that separate work actually changed. No temporary path or prior
conversation should be needed to decide what remains to do.

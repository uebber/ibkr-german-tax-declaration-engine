# PR review and merge train

Last updated: **2026-09-17**. Repository:
[`uebber/ibkr-german-tax-declaration-engine`](https://github.com/uebber/ibkr-german-tax-declaration-engine).

This document tracks work needed to review and merge the train. Accepted follow-up
work belongs in [post-merge-todos.md](post-merge-todos.md); merging does not close it.
Apply [review-criteria.md](review-criteria.md) to every PR.

## Resume here

**#88 verified candidate, 2026-09-18:** the maintainer authorized correction and
merge of #88 together with PM-005. The isolated branch is `review/pr88-transfers`:
integration `0b1910e`, option chronology `31824f8`, remaining corrections `b8b5b11`.
Clean suite: **1,327 passed, 1 skipped**; copied-export schema checks: **9 passed**.
VZ 2023–2025 console and metadata-stripped PDFs match accepted main `89e7c24`,
with matching same-main controls. No new difference is approved or required.
PM-005 is complete; PM-001–PM-004 and the separate pre-existing PM-006 remain open.
See [PR #88 review](pr-88-review.md). Publication/merge confirmation is pending.
No issue #76 application source was integrated.

1. Check the working branch, uncommitted files, remote `main`, and live PR heads.
   Recorded hashes below are observations, not permission to overwrite newer work.
2. **Continue with #88 under the committed review criteria.** TR-008 is resolved by
   #93 (`89e7c24`); the review rules are now in `review-criteria.md`. CLAUDE.md's
   existing safeguards remain, with the three clarifications in local commit `6a1c8f9`.
3. Update #88 locally with accepted `main` before acceptance; use the concrete plan
   below. Fsaupe does not need to rebase first. Do not bring local issue #76 into it.
4. Assess overall quality, check actual data early, inspect relevant legal/architectural
   boundaries and major tests, then verify the final candidate. Defer important work
   only when economical and permitted by the criteria; never waive the real-data gate.
5. Record the reviewed SHA, disposition and evidence. Stop expanding the review once
   acceptance is established; merge only within the active task's authorization.

## Scope and authorization

- #81-#84 were closed without merging at the maintainer's request; they are the
  older series and are not candidates to revive.
- The maintainer authorized the three corrections and merge of **#86**. That work
  is complete. The subsequent request authorized review/merge of **#87**, subject
  to the review gates. The maintainer then authorized fixing the blockers and merge,
  and explicitly deferred option linking as PM-005. That work is complete:
  verified head `2821d50` was published and merged as `0f0db9f`.
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
| [#87](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/87) | Per-account securities FIFO | `2821d50` | 1 original + history merge + correction + verification record | Merged as `0f0db9f`; [review](pr-87-review.md) complete; PM-005 deferred |
| [#88](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/88) | Internal transfers | `4da165a` (remote); `b8b5b11` (verified local code) | 1 original + history merge + corrections | Verified; publishing/merge pending |
| [#89](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/89) | Per-account currency | `513ab0f` | 2 | Pending review and branch update |
| [#90](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/90) | Stock grants | `6d89379` | 6 | Pending review and branch update |
| [#91](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/91) | Purchase transaction taxes | `39db47a` | 4 | Pending review and branch update |
| [#92](https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/92) | Capital-income reporting breakdown | `940870e` | 2 | Pending review and branch update; targeted checks only |

Verified merged `main` at handoff: `89e7c2431d19027f0e092ac50c23428833367897`.
Refund restoration #93: `e0b46444e9c72307d635935440a3063ee6a87e0b`, merged as above.
#87 corrective commit: `46aa37b65e6cc9a6a1d922d78abd7f8cb16ca337`;
published/merged head: `2821d50135252ab943278452eec4177f26f78f7b`.
#86 corrective commit: `5d25270eb36a43846e666d2150b8ecb48113fc1a`.
Original #86 head: `ea45c429acfa5b54e6d5830c22b0a1effdd9b6c5`.
Original base: `5a64079c277451da1b082a1d7f753821cc68466f`.

## Active train tasks

| ID | Task | Status | Completion evidence |
|---|---|---|---|
| TR-001 | Update #87-#92 onto corrected accepted history | #87 complete via history merge; #88-#92 remain open | #87 published as `2821d50`, merged as `0f0db9f`; no rebase. #88-#92 unchanged |
| TR-002 | Review #87 | Done: merged with follow-up; its refund regression was subsequently corrected by #93 | Historical #87 verification is in [review](pr-87-review.md); use TR-008 for the final restored behavior. Option linking remains PM-005 |
| TR-003 | Review #88 and correct PM-005 | Verified locally; publishing/merge pending | `b8b5b11`; 1,327 passed/1 skipped; VZ 2023–2025 exact parity. [Review](pr-88-review.md) |
| TR-004 | Review #89 | Pending | Same evidence; assess currency authority, account independence and shared ledger abstractions |
| TR-005 | Review #90 | Pending | Same evidence; assess grant lifecycle, acquisition basis and income-reporting completeness |
| TR-006 | Review #91 | Pending | Same evidence; assess trade-cost consistency and compatibility with the maintainer's exports |
| TR-007 | Review #92 | Pending | Same evidence; assess report reconciliation, calculations versus presentation and output parity |
| TR-008 | Correct the new VZ 2024/2025 refusal introduced with #87 | Done; #93 merged as `89e7c24` | Maintainer confirmed commission-overcharge refund and approved the measured difference. `FeeEvent.is_refund` credits cash once in current and historical processing. Suite: 1,231 passed/1 skipped. All three years complete; 2023/2025 byte parity, all 24 parsed 2024 form lines match working pre-refusal #87. Two changed 2024 lines against pre-#87 main are explicitly approved |
| TR-009 | Apply the agreed review/merge process | Done in this documentation change | `review-criteria.md`: hard real-data gate, initial quality assessment, economical deferral of important findings, staged-train review and stopping rule. CLAUDE.md's original category-specific gates retained; three clarifications committed as `6a1c8f9`. The earlier broad rewrite and documentation-only suite exemption were not adopted |

Each review includes its merge decision. Record the merge commit only after GitHub
confirms it. Keep unresolved correctness findings in this workstream with IDs such
as `PR87-F1`; do not move them to post-merge TODOs to make a PR appear ready.

### Branch-update procedure

**Concrete #88 resume plan (live refs checked 2026-09-17):**

- PR head: `4da165acd3d799e4afc3f8b9c0a0f615ab45627c` on
  `Fsaupe:rw/per-account-transfers`; GitHub reports `maintainerCanModify=true`.
- Accepted main: `89e7c2431d19027f0e092ac50c23428833367897`.
- Original incremental review range: `2c8c45b..4da165a`. Retain this range for
  understanding #88's own change; test the candidate including all accepted fixes.
- Fetch current refs again. Create an isolated branch/worktree from #88's head,
  then merge current `main` into it. Prefer this history-preserving update over a
  stacked rebase/force-push. No contributor action is required before starting.
- The non-branch-mutating `git merge-tree --write-tree --name-only` preview against
  the refs above found conflicts in `VALIDATION_REPORT.md`,
  `docs/legal-implementation-map.md`, `src/engine/calculation_engine.py` and
  `src/engine/fifo_manager.py`. Resolve semantically, retaining accepted fixes and
  both relevant validation histories. Automatic textual merges also need review.
- Preserve snapshot completeness/price-conflict guards, unknown lot provenance
  through transfers/mergers, and the commission-refund cash direction from #93.
  Review complete outgoing/incoming lot information, chronology and partial failures.
- Use the approved working results represented by main `89e7c24` as the immediate
  regression baseline. They preserve the pre-train results except the specifically
  approved refund correction. All VZ 2023–2025 must complete identically; any further
  difference needs its own explicit approval. Neither an abort nor an unapproved
  merged result may become the new baseline.
- When review and final verification pass, a normal fast-forward push can update
  the contributor's PR branch because its existing head is retained as an ancestor.
  Refresh the remote head first; if it advanced, integrate/review that work instead
  of overwriting it. Publish/merge only when authorized by the resumed task.

The main workspace remains on the local issue #76 branch; its application source
is not the review target. Read the committed local AGENTS.md, CLAUDE.md and review
records while working on the isolated GitHub candidate. Do not merge the whole
local branch merely to carry these documentation changes into a PR. Temporary
checkouts and captures from prior turns are optional, not prerequisites to resume.

The remaining order is #88 onto updated `main` (including merged #87), then #89
onto updated #88, continuing through #92. Record the original dependency heads before rewriting so each step
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
`8b7e49febcf1035d07391f9d52cfd40f0b0f9411`. That pre-fix candidate was followed
by corrective commit `46aa37b` and documentation commit `2821d50`, then published
and merged as `0f0db9f`. Diagnostic probes from the initial review remain preserved
as `pr-87-probes.py.txt`; the passing correction regressions are application tests.

### #87 initial review evidence and correction

**Subsequent maintainer decision:** the commission-refund refusal below was rejected
as a regression and corrected by merged #93 (TR-008). The compatibility gate is now
explicit in CLAUDE.md and the review criteria. The acceptance/refusal evidence below
describes the original #87 correction, not the current restored behavior.

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

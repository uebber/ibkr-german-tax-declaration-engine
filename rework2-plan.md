# Rework2 Plan — architecture-first rebuild of per-depot-fifo from main

Successor of `rework-plan.md`. That plan kept the rearchitecture partially optional
("applied opportunistically") and sequenced the two engine seams (old B7a/B8a) AFTER the
features — which twice let execution degenerate into replaying the old branch's commits.
This plan makes the architecture **mandatory, early, and integral**: seams first, features
built on the seams, per-Depot flip last as a small delta.

Relationship to other artifacts:
- `legal-review-todo.md` — findings F1–F6, action list, coverage gaps (unchanged input).
- `rework` branch — the completed feature-first port (17 commits, parity-proven vs the
  oracle). It stays untouched as the **standalone-PR packaging**; `rework2` is the
  **architecture-first packaging**. After the parity gate the user decides which branch
  carries Phase C and the upstream PRs.
- `oracle/per-depot-fifo` tag — immutable output oracle.

---

## Ground rules (binding)

**0. Existing work stays untouched.**
- All work happens on branch `rework2`, recreated from `main`. No existing branch
  (`per-depot-fifo`, `main`, `rework`, …) is rebased, force-pushed, amended, or deleted.
- `oracle/per-depot-fifo` is the immutable parity target.

**1. Reuse policy (pinned — this ambiguity caused the earlier blowups).**
- MAY be ported and re-expressed on the new architecture: architecture-independent content
  authored during the rework effort — the Phase-A legal-fix tests, parser fixes,
  VP modules (`processing/vp_*`, `identification/*provider*`), bond-maturity mapping,
  PDF improvements, and all test files (tests are the spec).
- MUST be written fresh against the seams: the ENGINE core — ledger keying, replay,
  per-Depot logic, transfer handling. The oracle's tests serve as the black-box spec.
- NO wholesale commit replay from `rework` or `per-depot-fifo`.

**2. One commit = one issue, fully e2e.**
- Each commit contains requirement/reference updates, tests, and code together.
- Commit message: one-line issue, body with legal basis (statute + `reference/` file).
- Bugfix tests are demonstrated red-first on the pre-fix tree.

**3. Every commit is green.**
- `uv run pytest -q` passes at every commit — real exit code, never piped through `tail`.
- Final whole-history sweep: check out each commit (pin `src/config.py` to that commit's
  `config_example.py`) and run the suite.

**4. Architecture is mandatory and comes first.**
- The Phase AR items below are binding train items, not guidance. Nothing is
  "opportunistic".
- Every AR refactor is no-behavior-change, verified by (a) the full suite and (b) a
  real-data parity run against its PARENT commit: run
  `uv run python -m src.main --report-tax-declaration --pdf-output-file …` on
  `data_import/`, normalize run-random event UUIDs, timestamps and output paths, sort log
  lines; the diff must be 0 and the non-log report section byte-identical. (Technique
  proven during the rework parity gate; PDF differs only in CreationDate//ID.)

**5. End state: FULL output parity with the oracle.**
- After the last Phase-B commit: full parity gate vs `oracle/per-depot-fifo` (console +
  PDF, same normalization), for the configured tax year and at least one earlier year if
  data permits.
- Every diff hunk gets a deep-dive in `parity-log.md`: symptom → root cause →
  classification. **(a) accepted** only if it is a documented bug in per-depot-fifo
  (citing a finding in `legal-review-todo.md` or a newly written-up oracle defect);
  **(b) anything else is a regression** — fix before proceeding, no exceptions.
- Known candidate (a)-diffs from Phase A: repealed €20k cap lines (F2), §23 leap-year
  anniversary classification (F3), VP for previously missing Basiszins years (F6) — each
  individually verified and logged, never waved through. (On the current real data set
  none of these constellations occur; the rework gate showed zero diffs.)

---

## The commit train (order = build order)

### Phase 0 — trustworthy greens

| # | Issue | Content |
|---|-------|---------|
| A1 | Test suite is order-dependent; group 6 not pinned to its law year (F1) | Harness fix (`tests/support/base.py` via pytest monkeypatch), pin group 6 to `tax_year=2024`, ADD the 2025-law scenario set. Port from the rework work (authored fresh there, fits the reuse policy). **First commit.** |

### Phase AR — mandatory architecture (before all features)

Each item: one commit, single-purpose, suite green, parent-parity-checked (rule 4).

| # | Item | Content |
|---|------|---------|
| AR0 | Parity tooling + multi-account harness (improvements #10, #9-harness) | `scripts/parity_check.sh`: pipeline run capture, UUID/timestamp normalization, diff; used per-commit from here on. Extend the test harness with multi-account CSV builders (the YAML harness is single-account today; per-depot tests had to hand-roll writers). |
| AR1 | RunContext — no global mutable config (#1) | `src/utils/run_context.py`: pipeline entry constructs an explicit context (tax_year, precision, rounding mode, registry handles) threaded through engine/processors; `src.config` is read once at the boundary (`main.py`/`pipeline_runner.py`). Tests construct their own context — the F1 bug class and the untracked-config test fragility become impossible. |
| AR2 | Law-as-data registry + core-vs-form layering (#2, #6) | `src/tax_law/registry.py`: Basiszins table, Teilfreistellung rates, FormYearRules — each entry with statutory citation and effective range; out-of-range lookups fail LOUD. The engine emits year-agnostic `TaxReportingCategory` totals; the registry-driven projection is the only Zeilen-aware layer. Registry↔`reference/` consistency test (generalizes the A5 table test). Absorbs legal fixes **A3** (cap repealed for all years, JStG 2024 retroactive) and **A5** (complete Basiszins 2016–2026 + loud gap) as registry content with red-first tests. |
| AR3 | HoldingPeriod domain type (#3) | `src/utils/holding_period.py`: §§108 AO, 187 Abs. 1, 188 Abs. 2/3 BGB anniversary arithmetic as a type, property-tested incl. leap years and 29-Feb acquisitions. Absorbs legal fix **A2**: replacing the `<= 365` day-count IS the introduction of this type (red-first leap-year spec). |
| AR4 | LedgerKey seam + aggregate views (#5) | Ledger registries keyed by `(account_key, asset_id)` with everything on `DEFAULT_ACCOUNT`; explicit `aggregate_view(asset_id)` for per-person consumers (VP, EOY validation, return totals). No behavior change. Keying shape matches the oracle's `(account_key, asset_id)` tuples so the later flip stays oracle-faithful. |
| AR5 | Unified chronological replayer (#4) | One sorted event stream with registered per-event-type handlers; the SAME loop serves historical reconstruction and current-year processing; securities and currencies share the stream. Intra-day ordering contract documented here (merger before transfer of its output; transfer before merger at destination). No behavior change. Written fresh on main's engine — the biggest new build of the plan; the 7/n bug class (parallel currency replay path) becomes structurally impossible. |
| AR6 | Data-gap channel (#7) | `src/processing/data_gaps.py`: one collector with a severity policy — fail-fast where income could be understated, warn for evidentiary mismatches; gaps surfaced in the report. Resolves **F4** to fail-fast by construction (B4 plugs into it). |
| AR7 | Legal-position register (#8, scoped light) | `src/tax_law/legal_positions.py`: entries (position taken, alternative, source) for per-Depot FX, short-FX analogy, Einlagenrückgewähr excess; rendered as report caveats. |

### Phase A remainder — legal fixes not absorbed by AR

| # | Issue | Content |
|---|-------|---------|
| A4 | False-confidence tests (F6) | Replace: misnamed negative-gross test (factory contract), CFX_ERR_002 (row must reach the engine; fail-fast `DataIntegrityError` pinned), group-11 soft assert (pin exactly one zero-gain RGL), WHT double-link (two dividends, correct pairing). Port from the rework work. |

(A2 → AR3, A3/A5 → AR2.)

### Phase B — features built ON the architecture

Content ported per reuse policy (rule 1), re-expressed against RunContext / registry /
replayer / gap channel where they touch those seams.

| # | Issue | Content / seam usage |
|---|-------|----------------------|
| B1 | Parser fails on current IBKR export format | Port fix + the regression tests added during rework (repeated headers, extra columns, BASE_SUMMARY). |
| B2 | Multi-account rows overwrite instead of summing | Port aggregation fix + tests. Per-account recording is NOT here (belongs to B7b). |
| B3 | Bond maturity (BM) unsupported | Port factory mapping + tests + docs. The synthetic sell flows through the AR5 stream like any trade. |
| B4 | Vorabpauschale §18 missing (partial-year, deemed inflow Y+1) | Port VP modules/tests; Basiszins via AR2 registry; NAV gaps via AR6 channel (**fail-fast in non-interactive runs — F4 resolved**; adjust the warn-only test accordingly); fixture-label and docstring fixes from the legal review. |
| B5 | §19 VP deduction missing at disposal | Port per-lot FIFO deduction, only-if-declared cap, provider (prompted-only slice), Z13+Z26 invariant test. |
| B5g | Glue: auto-compute the V−1 declared VP | Port the auto-compute path + tests (depends on B4+B5). |
| B6 | PDF Sonstige Kapitalerträge breakdown | Port; reporting only. |
| B7b | FIFO across depots violates §20 Abs. 4 S. 7 | **Small delta now**: flip LedgerKey from DEFAULT to the events' real `account_id` (plumbing: account on events + per-account recording included here), per-account SoY init/reconciliation; aggregate views keep feeding VP/EOY/totals. Engine logic written fresh on AR4/AR5; oracle's cross-account/propagation tests ported as the spec. |
| B8b | Depotübertragung not modeled (incl. historical non-EUR cash) | Transfers parser (port) + ONE tax-neutral `InternalTransferEvent` handler (drain/receive, basis+date carry, §43 Abs. 1 S. 5) registered in the AR5 replayer — securities and non-EUR cash share the path by construction. Oracle's transfer/merger/cash-basis/SoY-reconciliation tests ported as the spec; add the bond-maturity-after-transfer composition scenario. |

### → PARITY GATE (rule 5) vs `oracle/per-depot-fifo`.

### Phase C — coverage gaps (unchanged from rework-plan; each one issue)

**COMPLETED 2026-06-12** (C1 6179dc3 + strict-split def42f9, C2 bc31379,
C3 63b7c94, C4 aed9607, C5 ea7b0fc, C6 b3df825, C7 0fa4f73, C8 7b81edc).
C2-C7 passed against the existing engine (pure coverage); C8 and the C1
Stillhalter netting exposed real issues — see parity-log.md and the commit
messages.

| # | Gap | Legal basis |
|---|-----|-------------|
| C1 | Cash-settled index options (Barausgleich) | §20 Abs. 2 Nr. 3a; BFH VIII R 55/13 |
| C2 | Cash merger / Barzuzahlung / spin-off | §20 Abs. 4a S. 1–2, 7 |
| C3 | Forward split (imported, never tested) | §20 Abs. 4a |
| C4 | CFD lifecycle | §20 Abs. 2 Nr. 3 |
| C5 | Fee cashflows consuming currency lots | BMF FX 2022 Rz. 131 |
| C6 | WHT → Zeile 41, treaty-capped | §32d Abs. 5, §34c EStG |
| C7 | Stückzinsen | §20 Abs. 1 Nr. 7; BMF Einzelfragen |
| C8 | Einlagenrückgewähr excess (F5) — **decision PR**, confirm treatment first | §20 Abs. 1 Nr. 1 S. 3; BMF Rz. 92 |

Phase C lands on whichever branch the user picks after the gate (`rework` or `rework2`).
**DECIDED 2026-06-12: `rework2` carries Phase C and the upstream PRs** (gate passed —
PDF byte-identical to the oracle, zero figure mismatches; see parity-log.md).
New-test rule from here on (#9): every NEW behavior test carries a `legal_basis` reference
(YAML specs where the spec-runner pattern fits).

---

## Packaging impact (honest trade-off)

Architecture-first breaks the "14 standalone PRs off plain main" property of
`rework-plan.md`: Phase-B features now depend on AR commits. The two packagings coexist:

- `rework` — standalone-first PRs, feature code identical to the oracle, parity-proven.
- `rework2` — architecture-first train: better structure, cheaper Phase C, but PRs form a
  deeper stack (AR seams precede features).

The maintainer-communication mechanics from `rework-plan.md` (tracking issue, per-PR
template, stack handling) apply to whichever branch is chosen.

---

## Verification

- Per commit: full suite green (real exit code); red-first for every bugfix.
- Per AR/engine commit: parent-parity run (rule 4) — normalized diff 0 on real data.
- Final: parity gate vs oracle (rule 5) + whole-history green sweep + `parity-log.md`
  entries for every hunk (only proven oracle bugs acceptable).

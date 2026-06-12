# rework2 → uebber/main: PR package (tracking-issue content)

Paste the section "Tracking issue" below into a new issue on uebber's repo
BEFORE opening the first PR; every PR body links back with `Part of uebber#<N>`.
Branches `pr/01` … `pr/25` are pushed to the fork (`Fsaupe/...`); open each PR
from its branch against `uebber:main`.

## Motivation (one paragraph, for the tracking issue)

This package rebuilds the per-Depot-FIFO work from `main` as an ordered train
of single-issue, individually-green PRs (req-fix + tests + code per PR), with
seven structural improvements landed FIRST so every feature sits on explicit
seams (run context, law-as-data registry, ledger keying, unified replayer,
data-gap channel). The full set reproduces the `per-depot-fifo` branch's
real-data output byte-identically (PDF, metadata-stripped) EXCEPT two
documented engine bugs found red-first after the gate — historical
Einlagenrückgewähr basis reductions and historical option-premium adjustments
were lost in SoY reconstruction (cost-only mutations, invisible to quantity
reconciliation); both understate income, both are fixed and pinned (see
`parity-log.md` in the fork). Every commit in every PR passes its own suite
with that commit's `config_example.py` (whole-history sweep, 373→560 tests).

## Stack mechanics

History is one linear train: PR N's branch contains PRs 1..N. GitHub will
show cumulative diffs until predecessors merge. Preferred handling (stacks
are short at each step): merge in order, top of the table first — each PR's
diff collapses to its own commits as its predecessor merges. PRs marked ⊥
have no semantic dependency and can be reviewed in any order even while
queued. Don't open all 25 at once; batch 3–5, tracking issue carries the
full inventory.

## PR inventory (merge order = table order)

| # | Branch | Title | Commits | Standalone | Notes |
|---|--------|-------|---------|-----------|-------|
| 01 | pr/01-deterministic-suite | tests: fix order-dependent suite (F1) | 2 | ⊥ | hardens CI trust first; includes the plan doc |
| 02 | pr/02-ibkr-export-format | fix: parse current IBKR Flex export format | 1 | ⊥ | clears shared parser files early |
| 03 | pr/03-bond-maturity | feat: bond maturity (Type="BM") | 1 | ⊥ | |
| 04 | pr/04-parity-tooling | feat: parity-check script + multi-account test harness | 1 | ⊥ | tooling only |
| 05 | pr/05-run-context | refactor: explicit RunContext (no ambient config) | 1 | ⊥ | F1 bug class |
| 06 | pr/06-tax-law-registry | feat: law-as-data registry (Basiszins, TF, form rules) | 1 | ⊥ | includes JStG-2024 cap repeal (F2) |
| 07 | pr/07-section23-holding-period | feat: §23 anniversary arithmetic (F3 legal fix) | 1 | ⊥ | red-first leap-year fix |
| 08 | pr/08-ledgerkey-seam | refactor: ledgers keyed by (account, asset) | 1 | — | no behavior change, parity-checked |
| 09 | pr/09-unified-replayer | refactor: one chronological replay stream | 1 | dep 08 | no behavior change, parity-checked |
| 10 | pr/10-data-gap-channel | feat: DataGap collector + severity policy | 1 | dep 09 | F4 groundwork |
| 11 | pr/11-legal-position-register | feat: contested readings as data + report section | 1 | ⊥ | |
| 12 | pr/12-false-confidence-tests | tests: replace four no-op/blessing tests | 1 | ⊥ | |
| 13 | pr/13-multi-account-aggregation | fix: sum multi-account cash/positions | 1 | dep 04 | |
| 14 | pr/14-vorabpauschale | feat: §18 VP + §19 disposal deduction (B4/B5/B5g) | 3 | dep 06,08,10 | F4 resolved fail-fast |
| 15 | pr/15-pdf-itemization | feat: itemize Sonstige Kapitalerträge in the PDF | 1 | dep 14 | reporting only |
| 16 | pr/16-per-depot-fifo | feat: per-Depot FIFO (§20 Abs. 4 S. 7) | 3 | dep 08,09,13 | oracle tests as spec |
| 17 | pr/17-internal-transfers | feat: tax-neutral Depotübertragungen + parity gate doc | 3 | dep 16 | one handler, securities + cash |
| 18 | pr/18-hermetic-tests | tests: hermetic caches + config-example guard | 2 | ⊥ | clean-clone correctness |
| 19 | pr/19-e2e-declaration | tests: e2e declaration correctness (3 surfaces) | 2 | dep 16 | multi-Depot scenario included |
| 20 | pr/20-einlagenrueckgewaehr | feat: ERG position pinned + cross-year carry FIX | 1 | dep 09,19 | corrects a real cross-year understatement |
| 21 | pr/21-cost-divergence-tripwire | feat: SoY cost-divergence warning | 1 | dep 20 | guards the bug class |
| 22 | pr/22-option-replay-fix | fix: historical option premium adjustments FIX | 1 | dep 09 | corrects a real cross-year understatement |
| 23 | pr/23-coverage-c1-c3 | tests: cash-settled options, cash merger, split | 3 | dep 19 | pure coverage |
| 24 | pr/24-stillhalter-split | fix: strict Nr. 11 / Nr. 3a split (BFH VIII R 55/13) | 1 | dep 23 | presentation-correct Z22 |
| 25 | pr/25-coverage-c4-c7 | tests: CFD, fee-FX, WHT Z41, Stückzinsen | 5 | dep 19 | pure coverage + docs |

## Per-PR description template (fill per PR)

```
Part of uebber#<tracking>          Standalone: yes / depends on #X
Issue: <one sentence>
Legal basis: <statute + reference/ file>
Contains: requirements (<files>), tests (<files>, red-first for bugfixes), code (<files>)
Merge notes: stacked on pr/<N-1>; diff collapses to own commits once it merges.
```

## Parity guarantee (for the tracking issue)

After PR 17 the output is byte-identical (PDF, metadata-stripped; all console
figures) to the `per-depot-fifo` branch on identical real inputs. PRs 20 and
22 then INTENTIONALLY diverge: they fix two cross-year basis bugs present in
`main` and `per-depot-fifo` alike (proof: red-first tests with hand-computed
statutory figures; full analysis in the fork's `parity-log.md`). All other
PRs are output-neutral or pure coverage.

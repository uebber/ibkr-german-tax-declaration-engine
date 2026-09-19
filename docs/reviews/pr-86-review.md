# PR #86 review

**Final disposition: fixed and merged with required architectural rework.**
The initial review required correction of the three findings below. The maintainer
authorized those fixes and merge; fix commit `5d25270eb36a43846e666d2150b8ecb48113fc1a`
was pushed to #86 and merged into GitHub `main` on 2026-09-17 as
`8b7e49febcf1035d07391f9d52cfd40f0b0f9411`. The findings below describe the original
reviewed head and remain as the evidence for the corrections.

The fixed tree passes 1,193 tests with 1 skip without private data, and 1,194 tests
with the maintainer's exports. All 36 snapshot-integrity regression cases pass.
The maintainer's VZ 2023-2025 console reports, metadata-normalized PDFs and data-gap
codes remain unchanged against base `5a64079`. Required follow-up is committed as
`docs/reviews/pr-86-required-rework.md`. No local branch was included in the GitHub merge.

**Later-commit check:** PR #87 fixes the cross-account manifestation of F1, but
F1 still occurs when one account contributes multiple rows. F2 and F3 remain
reproducible at the current end of the series, PR #92 (`940870e`). Details below.

- Review date: 2026-09-17.
- PR: https://github.com/uebber/ibkr-german-tax-declaration-engine/pull/86
- Reviewed head: `ea45c429acfa5b54e6d5830c22b0a1effdd9b6c5`.
- Base: `5a64079c277451da1b082a1d7f753821cc68466f`.
- Scope: all four commits; 37 changed files, including 11 application files.
- Criteria: [review-criteria.md](review-criteria.md).
- The initial review was read-only; implementation and merge were separately authorized.

All monetary examples below are synthetic.

## Findings requiring correction before merge

### F1 — Partial cost basis becomes an apparently complete basis (P1)

Locations at the reviewed head:

- `src/domain/assets.py:337` (`person_snapshot.total`), and `:407` (`person_mark`).
- `src/parsers/parsing_orchestrator.py:129` (`_sum_snapshot_column`) and `:1084`
  (`_ensure_soy_quantities_are_set`).

The new aggregation sums every quantity but skips `None` cost-basis values. Its
result is no longer missing, so the downstream missing-basis guard accepts it.
This occurs both within one account and across accounts. The new helper's own
docstring explicitly acknowledges the undetectable partial total.

**Reproduced through the pipeline:** two opening rows of 100 shares each, one with
EUR 1,000 cost basis and one with no cost basis; sell all 200 for EUR 3,000. The
PR completes, using EUR 1,000 as the basis of all 200 shares and reporting EUR 2,000
gain. The same CSV inputs on the base stop with an error. The missing acquisition
cost has not been established, so no correct gain can be computed from these inputs.

**Requirement:** [GT-ESTG20-011](../../reference/tax-law/estg-20-kapitalvermoegen.md)
quotes § 20 Abs. 4 Satz 1 erster Halbsatz (Tier 1): gain subtracts acquisition costs.
The maintainer explicitly requires missing lot valuation data to stop. A generic
unconfirmed-history warning does not make a partially known cost basis complete.

**Required correction:** preserve completeness through both aggregation stages and
checkpoint marks, or reject an incomplete required basis before aggregation. Do
not default missing contributions to zero. Report affected rows/accounts together.
Tests must include mixed known/missing basis, row-order reversal, same-account rows,
different-account rows and checkpoint reconstruction. Wholly missing and valid-zero
bases must remain distinguishable.

**Later status:** `2c8c45b` in #87 passes each account's own snapshot to its ledger,
so another account's known basis no longer conceals a missing basis during that
reconciliation. Verified on #87 and #92 using sales from each account's own
holdings and requiring a basis-specific error. Within-account accumulation still
skips missing basis in both revisions and still produces the unsupported gain.

### F2 — A price conflict disappears when another account has a price (P1)

Locations: `src/parsers/parsing_orchestrator.py:175` (`_one_snapshot_price`),
`src/domain/assets.py:344` (`person_snapshot.agreed`), with a downstream consequence
in `src/engine/calculation_engine.py:1993` (Vorabpauschale end-price/cap).

Within an account, disagreeing prices are reduced to `None`. Across accounts,
`person_snapshot` treats that `None` as an absent observation and discards it.
Another account's price then looks unanimous. The representation loses the
distinction between no observation and conflicting observations.

**Reproduced:** A has two listings of the same fund priced at EUR 101 and EUR 110;
B has the first listing priced at EUR 101. All input prices are populated. A's
price becomes `None`, and the person-level price becomes EUR 101. With 300 units,
a year-start price of EUR 100 and no distributions, the 2024 Vorabpauschale
calculation completes at EUR 300 with no price gap. Putting the same three price
observations in A correctly raises `VORABPAUSCHALE_PRICE_UNUSABLE`. Account grouping
therefore decides whether a conflict is considered resolved.

**Requirement:** [GT-INVSTG-010](../../reference/investment-tax-law/invstg-18-vorabpauschale.md)
quotes § 18 Abs. 1 Sätze 2-4 (Tier 1), including the redemption-price measure and
its conditions for market-price substitution. Neither those rules nor the PR's
declared consensus policy authorizes suppressing an observed price conflict.

**Required correction:** retain conflict/provenance state, or resolve the price once
from the original observations before grouping holdings. An authoritative independently
resolved price may settle the conflict; another grouped snapshot must not erase it.
Verify both start/end prices and permutations of the same observations across accounts.

### F3 — Old position size does not prove that undated replacement lots are old (P1)

Locations: `src/engine/calculation_engine.py:1941` (quantity-only evidence check)
and `:2057` (new unconditional twelve-twelfths treatment of accepted undated tranches).
Introduced behavior is in commit `18d7285`; the insufficient quantity check existed
before, but the old branch raised instead of producing this figure.

**Reproduced through the pipeline:** buy 100 fund units in 2022, sell all 100 in June
2024, then supply a 2024 closing snapshot of 100 units with a known basis but no
replacement-acquisition record. The snapshot before 2024 also contained 100 units.
Reconciliation creates an undated closing lot. The PR compares 100 undated units
with the old opening count of 100 and grants twelve twelfths, producing EUR 160.30
for calendar 2024/VZ 2025. The base raises `ProcessingError`. The recorded sale
already consumed the old units; the earlier count cannot date their replacements.

**Requirement:** [GT-INVSTG-011](../../reference/investment-tax-law/invstg-18-vorabpauschale.md)
quotes § 18 Abs. 2 (Tier 1), supported by BMF Rz. 18.11 (Tier 2): the reduction
attaches to the acquisition of the surviving units. Its statement that units
already held at the year's opening keep twelve twelfths requires evidence that
these are those units. GT-INVSTG-055/Rz. 18.9 expressly confines the automatic
full-year treatment for missing transfer acquisition data to the withholding
procedure; it does not justify this inference in the declaration engine.

**Required correction:** establish surviving-lot provenance through disposals,
transfers and corporate actions, or stop when it cannot be established. Do not
infer continuity from matching counts. Correct the implementation-map assertion
that the earlier snapshot alone proves acquisition timing. A bounded alternative
is to defer this separate fix commit until its proof condition is implemented.

## Architecture assessment and required rework

The independent `PositionSnapshot` object and removal of account holdings from
`Asset` improve responsibility boundaries. `FifoLedger.reconcile_with_soy_position`
now receives a snapshot rather than discovering holdings through an instrument.
Reclassification retains the instrument ID, so snapshot fields cannot disappear
because a manual field-copy list omitted them. These are worth keeping.

This PR is nevertheless a storage transition, not independent account execution.
Ledgers remain pooled and `person_snapshot`/`person_mark` feed their calculations.
GT-ESTG20-013 remains marked `deviates`; the next PR changes FIFO ownership. Do not
describe this PR alone as completed multi-account support or use taxpayer-level
assessment as proof that lots may be pooled.

The following cleanup is bounded enough for an acceptance-with-required-rework
disposition **after F1-F3 are fixed and verified**. It is not a requirement for a
complete architectural rewrite before this PR can land.

| Item | Deviation and affected components | Intended boundary and completion evidence |
|---|---|---|
| R1 | Mutable tuple-keyed registries pass through parser, pipeline, calculator and diagnostic reporter; five new optional snapshot arguments default to empty dictionaries. | Introduce a cohesive typed snapshot input with account-scoped access. Calculators receive their account's records; the coordinator owns routing. Distinguish an unavailable snapshot from a supplied empty one. Tests prove another account cannot affect a ledger's opening/closing input. |
| R2 | `fund_prices._record_year_start_price` and the parser's price fallback write instrument prices into every account's holdings, sometimes creating quantity-less holding records solely to store a price. | Keep immutable imported holdings separate from resolved instrument prices carrying currency, date, source and resolution/conflict state. Price resolution should not enumerate or mutate account holdings. Test an instrument first acquired midyear and an account introduced after the start snapshot. |
| R3 | Aggregation assumes one quote currency per instrument across all accounts and rejects mixed currencies globally. The domain helpers depend on prior parser validation. | Keep native observations with their currency; enforce valid valuation at the appropriate boundary before summing money. Account independence must permit a later external broker to describe the same instrument differently. Until supported, reject explicitly and document the limitation. A valid account-local calculation should not depend on another account's quote currency. |
| R4 | Several wiring tests inspect source strings; fund-price tests add module-global mutable registries; unchanged `ExpectedAssetEoyState` semantics inspect the imported closing snapshot rather than calculated ledger state. | Use behavioral boundary tests, fixture-owned state and separate assertions for imported snapshots and calculated positions. A broken argument forwarding or incorrect ledger balance must cause a meaningful failure. Existing source checks can remain until replacements prove the same coverage. |

No inter-account transfer implementation is introduced in #86. Atomic delivery/
receipt, chronological reciprocal transfers, and future external-account endpoints
remain mandatory review topics for #88. They are not certified by this review.

## Knowledge-store review

The review read `docs/knowledge-store.md`, the relevant reference passages and
implementation-map changes. Tier 1/2 rules were used for calculations; no Tier 4/5
opinion was used to establish a new treatment. No legal rule was changed.

| Claim or requirement | Assessment |
|---|---|
| New GT-ESTG20-061, taxpayer/assessment period | The quoted § 2 Abs. 1 Satz 1 and § 25 Abs. 1/Abs. 3 Satz 1 match the official texts checked during review. This supports aggregation of results for assessment, not pooling before account-specific calculations. |
| GT-ESTG20-012/013, FIFO and depot boundary | Statutory FIFO and the Tier 2 depot boundary are distinguished in the store. Q2 remains recorded; #86 does not settle it. Pooled FIFO is an acknowledged remaining deviation, not a result of the new taxpayer claim. |
| GT-ESTG20-011, acquisition costs | F1 violates the required basis calculation when a contributing row is incomplete. |
| GT-INVSTG-010/011, prices and acquisition-year reduction | F2 and F3 violate the evidence conditions for these calculations. Existing green tests do not close those gaps. |
| GT-INVSTG-012/014/017/018, declaration year, input year, units, rounding and FX date | The refactor preserves the relevant consumers and migrated tests; the full suite and real-data outputs show no regression. The documented date-from-filename limitation is inherited, not newly resolved. |
| GT-FX-008, currency FIFO | Separate currency authority is correctly recognized. The map's cross-account pooling inference does not establish a general legal rule; reassess at #89. |

Against the nine-item protocol: source tier and sentence-level wording were checked;
the new claim states VZ 2023-2025; no new annual rate, threshold or form-line mapping
was introduced; the affected map/index/coverage links and purity checks pass; Q2
remains explicit. The historical amendment chronology and previously recorded
website disagreement in GT-ESTG20-061 were **not independently re-established**.
The official-text checks verified the newly introduced premise, not every historical
statement in the library. The remaining map correctness issue is F3.

## Independent verification

Python 3.12.12; the PR's frozen `uv.lock` dependencies, identical to the base.
All runs used isolated checkouts. Existing application/test files were not edited.

| Check | Result |
|---|---|
| PR full suite without private exports/cache | 1,157 passed, 1 skipped |
| PR full suite with a copy of the maintainer's exports | 1,158 passed |
| Base full suite with the same exports | 1,112 passed |
| Independent synthetic requirement probes on PR | 4 failed, 1 passed: F1 twice, F2 once, F3 once; same-account price-conflict control passes |
| Matching portable F1/F3 probes on base | 3 passed: both incomplete-basis cases and the undated-replacement case are refused |
| Whitespace/error-marker check of PR diff | `git diff --check` passes |

The added review probes are intentionally failing requirement tests, separate from
the shipped suite. See [pr-86-probes.py.txt](pr-86-probes.py.txt). Copy to
`tests/test_pr86_review_probes.py` in a checkout of the reviewed PR and run
`python -m pytest -q -s tests/test_pr86_review_probes.py --tb=short`.
The `.txt` suffix prevents these review artifacts being collected as application tests.

### Check for fixes in later commits

Fetched the live series through PR #92 on 2026-09-17 and inspected its 16 commits
after #86. The head remains `940870e8424f75067aad95e059a91ac3f8efd7f3`.
The domain aggregation and fund-price files are unchanged after #86. The
Vorabpauschale quantity-only test and full-year acceptance remain in place.
The per-account reconciliation change first appears in #87's `2c8c45b`.

Ran the same five independent requirement probes, without application edits,
against #86, #87 and #92:

| Probe | #86 `ea45c42` | #87 `2c8c45b` | #92 `940870e` |
|---|---|---|---|
| F1: incomplete basis, multiple rows in one account | Fails | Fails | Fails |
| F1: incomplete basis across two accounts | Fails | Passes: basis-specific refusal | Passes: basis-specific refusal |
| F2: conflicting prices across account groups | Fails | Fails | Fails |
| F2 control: all conflicting observations in one account | Passes | Passes | Passes |
| F3: sold old units followed by undated replacements | Fails | Fails | Fails |

Thus #87 contains a **partial fix**, not a complete resolution of F1. Its new
docstring says the incomplete sum no longer reaches ledger basis, but that claim
overlooks multiple rows within one account. The other two findings are not fixed
by the later PRs. These targeted checks do not constitute full reviews or
real-data validations of #87-#92.

**Maintainer's actual data:** 34 CSV files covering 2021-2025, one distinct account,
87 position rows. No position row has a blank account, quantity, cost basis or mark
price. This data cannot exercise the central cross-account behavior or F1's missing
field case. This is different from the contributor's reported two-account dataset.

For each VZ, ran base twice (control) and PR once, with fresh identical input/cache
copies. Used the supplied saved classifications, ECB rates and fund prices; disabled
automatic NAV fetching equally on all runs to avoid changing inputs during comparison.
No new price was supplied and no existing data gap was overridden.

| VZ | Base and PR complete with PDF | Console comparison | PDF comparison excluding volatile metadata | Log difference |
|---|---|---|---|---|
| 2023 | Yes | Identical | Identical | One checkpoint message reworded |
| 2024 | Yes | Identical | Identical | Two checkpoint messages reworded |
| 2025 | Yes | Identical | Identical | Three checkpoint messages reworded |

Same-tree controls match in console, normalized logs and metadata-normalized PDF
bytes for all three years. Pre-existing data gaps are unchanged, including the
2024 currency reconciliation warning. This establishes regression parity on these
inputs, not certification that every pre-existing declared figure is correct.
Original export/cache hashes were unchanged after all captures; personal configuration
was not copied or altered. Captures used the tracked configuration template with
the saved calculation inputs above.

## Interaction with local issue #76 work

Read-only merge preview compared PR #86 with local `3183f18` over common base
`5a64079`. It reports a text conflict in `VALIDATION_REPORT.md`; application changes
merge textually. The document conflict must preserve both validation histories.
No combined checkout was executed. The maintainer subsequently instructed that no
local-branch integration was necessary: the corrected PR was merged against its
GitHub base. The local branch and its application changes remain untouched.

## Remaining work

F1-F3 were corrected and verified before merge. R1-R4 remain documented architectural
follow-up. PRs #87-#92 remain open and require their own reviews; this merge does not
accept their implementation. Their later branches must be assessed with the merged
correctness fixes present.

# PR #87 review

**Initial disposition: rework before merge; corrections now authorized and implemented.**
Reviewed 2026-09-17. The initial findings below describe `0d5c958`; the correction
record at the end states the resulting behavior and verification. The maintainer
authorized fixing/merging F1/F2 and explicitly deferred option linking as PM-005.

## Revisions and scope

- GitHub head: `2c8c45b710f121c2d841872e58a73d53982cae50`;
  contributor branch `Fsaupe:rw/per-account-fifo`, targeting `main`.
- Accepted base: `8b7e49febcf1035d07391f9d52cfd40f0b0f9411`.
- Incremental review: `ea45c429..2c8c45b`, one commit, 16 files.
- Local candidate: `0d5c958a4d7d6048bb3365937a40107db73b4cf7` on
  `review/pr87-account-fifo`. It merges accepted `main` into the original PR head,
  preserving history. It is **not published or accepted**.
- Three conflicts resolved: the snapshot-sum docstring retains #86's corrected
  completeness semantics; the implementation map combines account-local FIFO
  with the corrected completeness/conflict record; both validation histories remain.
  All #86 correctness fixes and regression cases remain present.

The main workspace's issue #76 branch, personal configuration, exports and caches
were preserved. Existing architectural criteria already settle the account/FIFO
boundary; no additional design choice was needed to conduct this review.

## PR87-F1 — Unobserved historical transfers still produce invented lot dates (P1)

Locations in the candidate: `src/engine/calculation_engine.py` account-local
opening reconciliation and `_report_multi_account_limitations`;
`src/engine/fifo_manager.py::_create_fallback_long_lot` and disposal consumers.

Synthetic pipeline reproduction: A buys 100 shares on 2023-05-01; the opening
snapshot for VZ 2025 reports those shares in B; B sells them in June 2025. No
transfer record is supplied. Accepted base preserves the observed acquisition
date through its pooled reconstruction. #87 discards A's reconstruction, builds
B's holding from the snapshot, and returns a sale dated **2024-12-31** for
acquisition. It completes with warnings and reconciles at year end.

The fallback mechanism predates this PR, but per-account reconciliation newly
routes this previously traceable case through it. A generic multi-account warning
does not satisfy the maintainer's requirement that untraceable acquisition dates
stop computation. The date can determine FIFO order, holding period and acquisition
FX conversion; the probe establishes date invention, not a measured monetary
error for this EUR-denominated example.

Ground truth: GT-ESTG20-013 (BMF Rz. 97 Satz 2, per-depot FIFO),
GT-ESTG20-014 (own-depot transfer preserves date and cost), and GT-ESTG20-022
(acquisition-side FX at acquisition). See
`reference/tax-law/estg-20-kapitalvermoegen.md`. Missing-input refusal also follows
the explicit review criteria and CLAUDE.md.

**Required result:** preserve documented provenance through a supported transfer,
or refuse a computation requiring unavailable lot dates/basis. Do not infer a
transfer from equal quantities, and do not replace an error with a banner.
Verify opening and checkpoint reconstruction, partial sales and the real-date
consumers; valid single-account history must continue to work.

**Later commits:** #88 `4da165a` first supports supplied transfers. Its five
`TestTheMovedSharesKeepTheirDateAndCost` tests pass, including date, basis and
absence of a reconstructed lot. This is a **partial resolution**: the no-transfer
probe still returns the invented date on #88, #89 and #92. A supplied export's
missing-year guard does not close the entirely-absent-export path.

## PR87-F2 — Account labels select different currency/refund algorithms (P1)

Locations: `src/engine/calculation_engine.py` tax-year ledger lookup (line 1016
in the candidate), `CAPITAL_REPAYMENT` dispatch and generic cash-flow dispatch;
`src/parsers/domain_event_factory.py` commission adjustments in
`Deposits/Withdrawals` (around line 640).

The tax-year lookup now uses the real account for **all** assets, while currency
ledgers deliberately remain under `DEFAULT_ACCOUNT`. A commission refund is
classified as `CAPITAL_REPAYMENT` on a CashBalance asset. With a named account,
the lookup misses, bypassing capital-repayment handling and taking generic cash
inflow handling. With the supported absent-account representation it finds the
currency ledger and takes the old path, including creation of an excess dividend.

**Measured on the maintainer's actual exports:** VZ 2024 console and PDF change,
including the foreign-capital-income total and general capital-loss figure; the
existing `CURRENCY_EOY_MISMATCH` warning disappears. The two same-base controls
match. VZ 2023 and 2025 match the base. The affected real event is a commission
refund; no private amounts are recorded here.

**Synthetic reproduction:** a sole USD account with opening balance -100, closing
balance -90, a USD 10 commission refund and constant USD/EUR rate 2 returns
different FX results solely when its account ID is changed from blank to named:
EUR 20 and a currency mismatch versus EUR 0 and no mismatch. All values are invented.
Accepted base treats both labels identically. The named-account result avoids
the old refund path's error; this review does **not** label every changed figure
as a new tax error merely because it differs from the base. The introduced defect
is accidental, account-label-dependent dispatch and the false single-account
parity claim; the underlying refund treatment is pre-existing.

**Required result:** dispatch currency and securities by explicit boundaries,
not the incidental presence of a ledger key. Resolve the commission-refund
treatment deliberately, with a scoped legal requirement and map entry before
changing tax behavior, or keep that separate correction explicitly pending.
Test equivalent named/unnamed single-account inputs, native/EUR amounts, positive
and negative cash positions, refund classification and cash conservation.
Measure and explain every resulting VZ 2024 difference. Restoring an old erroneous
figure is not evidence of a correct fix.

**Later commits:** the equivalence probe fails on #88, then passes first at #89
`513ab0f` when currency ledgers also receive account keys; it remains green on
#92. This restores equal routing but does **not** establish correct refund
taxation: both representations again reach the older capital-repayment branch.
Do not count this as complete legal resolution or import all of #89 into #87
merely to hide the discrepancy.

## PR87-P1 — Existing option-linking boundary defect (separate from introduced findings)

`src/processing/option_trade_linker.py` indexes by date, underlying contract and
quantity, without account. Duplicate keys overwrite. The shared pending-premium
map then allows both stock deliveries to reference one option event, whose
adjustment is consumed only once.

Two synthetic accounts each buy and exercise one identical call on the same day
and sell the delivered shares later. Each account alone completes. Combined,
the pipeline raises `Missing pending adjustment data for option event`.
Transaction IDs deliberately order exercise events before stock deliveries, so
this is not an ordering error in the fixture.

The same defect reproduces on accepted base, #87, #88, #89 and #92. No later
commit changes the linker. It is an **unchanged pre-existing gap**, not a newly
introduced regression and not silently added to the accepted post-merge TODO list.
It contradicts the PR description's claim that every account now processes
independently. The maintainer subsequently accepted this as **PM-005** in
[post-merge-todos.md](post-merge-todos.md); no option-linking implementation is
included in this correction. The maintainer's one-account exports have
zero cross-account simultaneous-exercise groups and cannot exercise this case.

## Architecture and legal assessment

The main change is sound in direction: one securities ledger per account/asset,
filtered historical events, account-local marks and opening reconciliation, and
an EOY union over ledger keys and closing rows. Historical and current mergers
select both instruments in the event's account. Chronological replay remains
coordinated; it does not finish one account's whole history before another's.

Account independence is incomplete. Processors still receive the global ledger
registry; the merger processor reaches into it, although its chosen target is
account-local. Option links and pending adjustments are shared. Fund tranche
snapshots/attribution and reported holdings still aggregate before the reporting
boundary. Shared market prices are appropriate, but their storage in holdings is
the existing PM-002 concern. PM-001 through PM-004 remain open; this PR does not
close them, and no new deferred work was accepted during this review.

The changed implementation-map rows and the relevant reference passages were
read against the nine-item knowledge-store protocol. GT-ESTG20-012 is the Tier 1
FIFO fiction; GT-ESTG20-013 is the Tier 2 depot boundary, with Q2's foreign-account
interpretation kept explicit. The existing maintainer criteria require separate
account holdings; no new filing election was made. GT-ESTG20-061 supports
assessment-level aggregation, not pooled lot ownership. GT-FX-001/008 do not
establish a commission-refund classification or cure the dispatch discrepancy.

No reference claim, rate, form mapping or legal premise was added by #87; no
unrelated legal audit was undertaken. Existing source wording, sentence scope,
applicable-year discussion, open questions and map changes were inspected;
reference purity/map tests pass. This is not a new independent verification of
every historical BMF amendment or every inherited currency filing position.

## Verification and reproducibility

Python 3.12.12; frozen `uv.lock`; tracked `config_example.py` as configuration.
The candidate source is the local merge commit above; diagnostic probes are
separate from the shipped suite and never weaken its expectations.

| Check | Result |
|---|---|
| Candidate full suite without private exports/cache | 1,211 passed, 1 skipped |
| Candidate full suite with copied exports | 1,212 passed |
| Accepted-base full suite with copied exports | 1,194 passed |
| #87's 18 account tests on accepted base | 11 failed, 7 passed |
| Five independent probes on accepted base | 1 failed, 4 passed: existing option defect only |
| Same probes on original #87 and corrected candidate | 3 failed, 2 passed |
| Same probes on #88 | 3 failed, 2 passed |
| Same probes on #89 and #92 | 2 failed, 3 passed: date and option cases remain |
| #88 supplied-transfer provenance controls | 5 passed |
| Conflict markers and whitespace | Resolved; `git diff --check` clean |

Both existing test behavior changes were inspected: the former pooled checkpoint
scenario becomes a single-account mark/basis scenario, and parser account
assertions are strengthened. The new scenario no longer tests multi-account
checkpoint routing; the account-specific replay cases and future behavioral
boundary work matter for that coverage. Other changed test text concerns price
propagation and pooled-state descriptions. #86's regression suite remains green.

Probes: [pr-87-probes.py.txt](pr-87-probes.py.txt). Copy to
`tests/test_pr87_review_probes.py` in the checkout being assessed, then run:

```sh
python -m pytest -q tests/test_pr87_review_probes.py --tb=short --show-capture=no
```

The file deliberately contains failing requirement probes, not committed passing
application tests. The transfer assertion records the date returned by an
unsafe successful run; a future refusal must be assessed and converted into an
explicit expected-error regression, not described as preserved provenance.
For the full suite exclude the diagnostic file with
`--ignore=tests/test_pr87_review_probes.py`. On a base checkout temporarily carrying
the PR's new account tests, exclude that added file too for the base-suite count.

Actual-data inventory: 34 CSVs, 2021–2025 history, one account. Non-header rows:
6,976 trades, 920 cash transactions, 13 corporate actions, 170 Options_EAE,
87 positions and 55 cash-balance rows; zero blank account IDs in each group.
Contributor-reported two-account runs are separate evidence.

For each VZ 2023, 2024 and 2025, ran accepted base twice and candidate once through
the normal application entry point, with fresh identical copies of classifications,
FX rates, fund prices and declaration history. Non-interactive; automatic NAV
fetching disabled equally. All nine runs produced PDFs. Console bytes and PDF
bytes excluding volatile date/ID metadata match for all controls and for candidate
2023/2025; candidate 2024 differs as described in F2. Data-gap codes have the same
comparison pattern. No missing input was overridden. Original exports, caches
and personal configuration hashes are unchanged. Private captures remain outside
the repository and are not required to understand the findings.

## Authorized correction — 2026-09-17

Category: `fix-func`. The maintainer authorized the implementation and merge,
including the application/test changes required to replace unsafe expectations.
Option linking is excluded at the maintainer's subsequent direction (PM-005).

**F1:** the coordinator asks each ledger whether its acquisition history is
resolved before current-year securities disposals. Every affected account/asset
is collected in `SECURITIES_ACQUISITION_HISTORY_UNKNOWN`; no report is emitted.
Short reconstructed lots now carry the same provenance flag as long lots, and
stock mergers preserve it on both sides. Snapshots may retain unresolved
quantities for reconciliation/diagnostics, but cannot authorize a disposal.
This also protects §23 and securities acquisition-FX consumers from accepting
the placeholder date. It does not import transfers or infer them from quantities.

The maintainer's proposed complete outgoing/incoming lot events are the intended
transfer boundary for #88. Those events must preserve lot identity, dates, cost
and other tax attributes. The guard closes the alternative path where an absent
incoming event was silently replaced by a reconstructed snapshot lot. Properly
documented transfers should pass without using this fallback.

**F2:** currency lookup is explicitly pooled while securities lookup remains
account-local. Positive commission adjustments are refused before event creation
with `COMMISSION_REFUND_UNCLASSIFIED`, for both named/unnamed accounts and both
commission adjustment labels. All affected rows are collected. The old conversion
of a generic commission credit into `CAPITAL_REPAYMENT` has been removed.

This is a refusal, **not a completed commission-refund tax calculation**. The
actual row says only `ADJUSTMENT: COMMISSION` and has no instrument or transaction
link. Existing GT-ESTG20-010/048 and GT-ESTG20-011 require distinctions the row
cannot support. No tax-free assumption, arbitrary lot adjustment or new legal
election was made; no reference claim changed. The original transaction/service
and its treatment must be established before this input can be supported.

**Calibration:** the initial 11 regression cases produced 10 failures and one
valid-history control before the fix. The final 13 cases (including long/short
merger provenance) produce 12 failures and one pass on `0d5c958`, and 13 passes
on the corrected code. Tests are committed as `tests/test_account_boundary_integrity.py`.

Older snapshot-only disposal scenarios now assert refusal; scenarios testing EOY,
splits, option lifecycle or currency behavior receive explicit synthetic dated
acquisitions instead. Their numerical assertions remain unchanged. The zero-basis
regression retains its distinction between zero and unknown cost, with observed
acquisition history added. The source, PRD, map and behavioral specification were
updated together. The option-linking code was not changed.

**Real data:** fresh fixed-tree captures with identical saved inputs leave VZ 2023
console/PDF unchanged against accepted base. VZ 2024 **and VZ 2025** now exit 1
with `COMMISSION_REFUND_UNCLASSIFIED` and emit no PDF; 2025 imports the 2024 event
as history. This is the intended safe refusal of an unresolved input, not parity
and not successful completion of those tax declarations. Original exports/cache
hashes remain unchanged. No row was deleted or overridden to make verification pass.

The final clean-checkout suite and merge revision are recorded in `pr-train.md`.
PM-001 through PM-005 remain open. #88-#92 still require individual updates/reviews.

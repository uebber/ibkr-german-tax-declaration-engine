# PR Train Review — state, rationale, and how to resume

**Branch:** `hermetic-tests-first` (local only, never pushed)
**Base:** `main` @ `ebad4e7`
**Status as of 2026-08-02:** 5 of 25 PRs reviewed and accepted; 20 not yet reviewed.
**Not done deliberately:** nothing pushed, no tags, no PRs closed, no comment posted on
issue #15, no CI added. All of that is still open for decision.

---

## 1. What this branch is

Upstream contributor **Fsaupe** opened a 25-PR train (#16–#40, tracking issue #15) on
2026-06-12: a rebuild of per-Depot FIFO work, structured as one linear stack where PR N's
branch contains PRs 1..N. **Branch names encode train position, not PR number**
(`pr/01-…` = PR #16, `pr/18-hermetic-tests` = PR #33). So *train position = PR number − 15*.

This branch carries the PRs reviewed and accepted so far, cherry-picked onto `main` with
Fsaupe's authorship preserved, plus our own fix commits.

```
5050bba fix: drop the stray data_import symlink, harden .gitignore            [ours]
57d7f5f docs(tests): cite the reference library, not the Fifo rule inline       [ours]
96d4312 fix(scripts): parity_check.sh cache-hermetic/ordered/portable           [ours]
a40adce docs(reference): add EStG 20 Abs. 4 Satz 7 (Fifo), correct per-Depot    [ours]
312bc3a feat: parity tooling + multi-account harness                     (PR #19, Fsaupe)
8ee553e docs(reference): add EStG 36/45a — Anrechnung inlaendischer KESt      [ours]
320e20a fix(parsers): reject BM records with missing/non-positive Proceeds     [ours]
76cb8df docs(reference): validate the Satz 2 entry against Validation Protocol [ours]
547df96 docs(reference): add EStG 20 Abs. 2 Satz 2, correct citation           [ours]
4fbf570 feat: bond maturity (Type="BM") support                          (PR #18, Fsaupe)
f5e8c0c docs: correct three inaccurate justifications                          [ours]
55c7b95 fix: parse the current IBKR Flex export format                   (PR #17, Fsaupe)
86c34c4 tests: fix order-dependent suite                                 (PR #16, Fsaupe)
2383b8a tests: don't abort cache patching on later config attrs                [ours]
be66807 tests: config_example completeness guard                         (PR #33, Fsaupe)
449767f tests: hermetic caches                                           (PR #33, Fsaupe)
```

**Verification at HEAD:** 397 tests pass on a simulated clean clone
(`config_example.py`, no `cache/`). Real-data output is **byte-identical to `ebad4e7`**
across tax years 2022–2025 — console report, `validate_ledgers.py`, and PDF text SHA-256.

> That real-data run was performed at `8ee553e` (through #18). It was **not** re-run for
> #19, because `data_import/` no longer exists on this machine — see section 8. It still
> holds by construction: #19 and the four commits on top of it change `scripts/`, `tests/`,
> `reference/`, `docs/` and `.gitignore` only, and touch no file under `src/`.

One commit from PR #16 was **deliberately dropped**: `af95b72` added `rework2-plan.md`,
Fsaupe's internal working plan referencing branches/tags/files that do not exist in this
repo (`rework`, `rework2`, `per-depot-fifo`, `oracle/…`, `legal-review-todo.md`,
`parity-log.md`).

---

## 2. Review criteria

Set by the repo owner, stricter than the PR descriptions assume:

> All behavioural changes must be rooted in the current knowledge store (`reference/`), or
> accompanied by knowledge-store updates validated at the highest verification levels.

"Highest verification levels" = the Validation Protocol in
`reference/research/research-strategy.md`: every claim traces to Tier 1 (statute) or
Tier 2 (BMF); year-specific rules cite the exact amendment law; rates/thresholds cite
paragraph *and* sentence; **form line mappings verified against the official form for the
specific tax year**; Tier 4/5 cross-checked against Tier 1.

---

## 3. Per-PR verdicts

### PR #33 (train 18) — hermetic caches + config_example guard — **ACCEPTED, moved to front**

Moved from position 18 to position 1 because nothing before it was verifiable on a clean
clone. Root cause it fixes: legacy `*_FILE_PATH` attributes no longer exist in config, so
`monkeypatch.setattr(..., raising=True)` threw, the surrounding broad
`except Exception: print(...)` swallowed it, and the cache-path patches never ran — tests
silently read and wrote the developer's real `cache/`.

Independently confirmed: `main` fails 2 tests in a clean worktree
(`test_d05_stock_dividend_…`, `test_chained_mergers_historical`); they pass in the owner's
checkout only because a 49 KB untracked `cache/user_classifications.json` supplies the
classifications. `cache/` is gitignored and survives `git checkout`, which is why Fsaupe's
"every commit green" sweep was green.

**Defect found and fixed (`2383b8a`):** #33 patches `FUND_SOY_NAV_CACHE_FILE_PATH` and
`DECLARED_VP_CACHE_FILE_PATH` with `raising=True`, but those attributes are introduced by
the Vorabpauschale work at train position 14 (PR #29). At the front of the train they don't
exist, so the block threw on *every test* — same failure mode #33 exists to fix,
reintroduced two lines lower, leaving `IS_INTERACTIVE_CLASSIFICATION` unpatched.
`raising=False` fixes it and is forward-compatible.

Verified by property, not just by green: with a deliberately poisoned real cache
(`BOND`/`OPTION` instead of `STOCK`) the suite still passes and the file is not mutated.

### PR #16 (train 1) — order-dependent suite — **ACCEPTED**

Claim verified empirically: `src.config.TAX_YEAR` leaked across modules (probe after
group7 saw 2023, not 2024). Masked because `get_form_rules(2023)` falls back to the 2024
entry and returns identical rules — so a green run genuinely did not prove the law year.

Six new VZ≥2025 fixtures hand-checked against the knowledge store's VZ≥2025 table (not
against the engine). All correct.

Findings: description claims a "leak tripwire in conftest" that **does not exist** in the
diff; de-globalisation is incomplete (`test_group6_loss_offsetting.py` still reads
`APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING`, two import-time-bound `TAX_YEAR` date defaults,
and `OUTPUT_PRECISION_AMOUNTS` from the untracked `config.py`). Neither fixed — the
tripwire would be the more valuable of the two.

### PR #17 (train 2) — current IBKR Flex export format — **ACCEPTED**

Red-first verified (5/6 new tests fail without the fix; the 6th is a backward-compat guard,
correctly green both ways). Real-data parity byte-identical — important because
`_copy_file` changed from `write_bytes` to a full CSV parse-and-rewrite with `QUOTE_ALL`,
touching every Positions and Cash_Balance snapshot.

Checked and cleared: `io`/`csv` already imported; `allow_extra=True` is safe because
`RawCashBalanceRecord` has `Config.extra = 'ignore'`.

Findings, both corrected in `f5e8c0c`: the comment justifying the warning→debug downgrade
claimed "the rate reconciliation below confirms consistency" — it **cannot**, because the
second leg was just derived as `|Quantity| × rate`, making `calculated_rate == rate`
identically in both directions. And **none of the three conditions #17 fixes occur in this
repo's data** (all 35 files, 2021–2025: no BASE_SUMMARY, no repeated headers, no extra
Cash_Balance columns) — the docstring asserted them as fact.

Note: the downgrade silences 1,194 warnings per full-history run. Almost certainly right,
but it was justified by a check that cannot fire.

### PR #18 (train 3) — bond maturity (`Type="BM"`) — **ACCEPTED after knowledge-store repair**

First PR where the rooting criterion bit, and it **failed** — on traceability, not on tax
treatment.

#18 cites §20 Abs. 2 **Satz 2** (Einlösung = Veräußerung) as its legal basis, but that
provision was **absent from `reference/`**: `estg-20-kapitalvermoegen.md` documented Abs. 2
Satz 1 Nr. 1/2/3/7 then jumped to Abs. 3. The coverage-matrix row #18 added pointed at a
file that did not contain the controlling rule. Four artifacts cited "Satz 1 Nr. 7" alone
(PRD, coverage matrix, code comment, test docstring) — that gives the gain *category*, not
the disposal fiction.

Fixed in `547df96` + `76cb8df`: Satz 2 added with verbatim text cross-verified against two
Tier 1 sources (gesetze-im-internet, dejure), version status recorded (JStG 2024, BGBl. I
2024 Nr. 387), dejure's caveat noted that Abs. 2 continues past Satz 2. Form placement
verified against the official Anleitung for **both** 2024 and 2025 — and corrected: the
Zeile 19 mapping is **conditional on the broker being foreign**, not a property of bond
maturities. A bond redeemed through a German Zahlstelle belongs in Zeile 18.

*(#28 retroactively closes the Satz 2 gap 10 PRs later with a one-line clause — but #18 is
labelled "Standalone: yes", so merged alone the gap persists. Our version is more complete
and will conflict with #28's clause; keep ours.)*

**Code defect found and fixed (`320e20a`):** the BM guard tested `maturity_proceeds is None`,
which is unreachable — `gross_amount_ca` comes from `safe_decimal(..., default=Decimal('0.0'))`
and never returns None. Demonstrated red-first: a BM record with a blank `Proceeds` column
and a €1,020 basis produced `G/L = −1020.00` silently, with no error. Under §20 Abs. 4 an
unknown Veräußerungserlös makes the gain incomputable; inferring zero understates income by
the full basis. Now rejects `proceeds <= 0`. Three red-first tests added.
Documented as unsupported in PRD: bonds held **short** to maturity, and genuine zero
redemptions (issuer default — IBKR reports those as a write-off, not `Type="BM"`).

---

### PR #19 (train 4) — parity tooling + multi-account harness — **ACCEPTED, tool repaired**

No production code touched (verified: `.gitignore`, `scripts/`, `tests/` only). Rebased
clean. 397 tests pass on a simulated clean clone (394 → 397).

The harness is sound. All four row builders match the canonical `column_validator.py`
tuples in order and arity (trades 23, positions 15, cash balance 6, cash transactions 14);
importing the tuples instead of copying them is the right call. The deferred assertion in
`test_position_rows_per_account` is honest: `RawPositionRecord` really does carry
`alias="AccountId"` while the column is `ClientAccountID`, so positions really do lose the
account. **This PR's description is the first in the train that I could not fault.**

**Defect found and fixed (`96d4312`), severe.** `scripts/parity_check.sh` is the evidence
base every remaining PR cites for its parent-parity claim, and it could not see a
classification change. The pipeline reads *and writes* `cache/user_classifications.json`;
the baseline capture warmed the cache and the second capture read it back. A/B on the
identical sequence (no cache → capture A → reclassify a holding STOCK→AKTIENFONDS →
capture B):

| | verdict |
|---|---|
| original script | cache leaks between legs, both legs `Aktien 2250.00`, **`IDENTICAL`, exit 0** |
| repaired script | no leakage, `2250.00` vs `250.00`, console DIFF 24 lines, PDF DIFF, exit 1 |

Classification drives Teilfreistellung and the KAP/KAP-INV split, so this was the blind
spot with the largest tax consequence — and it is the same bug class **#33** was moved to
the front of the train to fix for the test suite. Fixed by snapshot/restore of `cache/`
around each capture (not by deleting it — 49 KB of hand-made classifications). Verified the
curated file is byte-identical afterwards.

Two further defects in the same script: the global `sort` in `normalize()` reduced the
console leg to a multiset of lines, justified by a cause that isn't real (dicts are
insertion-ordered); the actual cause was the script's own `2>&1` merging unbuffered stderr
with block-buffered stdout — proven by moving 16 lines under `PYTHONUNBUFFERED=1` with
identical code. Fixed at source by splitting the streams, after confirming two same-tree
runs then compare identical on all three legs *without* sorting. And `stat -c%s` is GNU-only
and fails on macOS, in the branch that only runs when there is a difference to report.

**Knowledge-store repair (`a40adce`).** Same pattern as #18: the PR cites
`§20 Abs. 4 S. 7 EStG (FIFO je Depot)` and the provision was **absent** from `reference/` —
"Abs. 4 — Gain Calculation" was three lines before jumping to Abs. 4a. Grepping the file for
"Satz 7" gives a false positive (that hit is Abs. 4a, Abspaltungen). Added with the full
verbatim sentence from gesetze-im-internet.de cross-checked against dejure.org, sentence
position confirmed as Satz 7 of 9.

The citation turned out to be **substantively right but mis-attributed**: Satz 7 mandates
FIFO for Sammelverwahrung per §5 DepotG and never says "per Depot" (its only "Depot" is
inside "Depotgesetzes"). "Je Depot" is Tier 2 — BMF 14.05.2025, GZ IV C 1 - S
2252/00075/016/070, Rz. 97 S. 2, *"auf das einzelne Depot bezogen anzuwenden"*, with Rz. 98
counting a sub-depot as a Depot and Rz. 99 extending FIFO to Streifbandverwahrung. Identical
wording in the 18.01.2016 version, so stable practice. Both PDFs were retrieved and text-
extracted; the Rz. numbers are read off the documents.

This **closes the open question §7 parked for #32** — the per-Depot reading does have solid
Tier 2 backing, now located with Randziffer.

**It also found an outright wrong claim already in the store**, unsourced since before the
train: *"FIFO method applies per asset per depot unless specific identification is
possible."* Rz. 97 S. 3 says customer instructions on which security to sell are
*einkommensteuerrechtlich unbeachtlich*, and Rz. 99 closes the Streifbandverwahrung escape.
There is no specific-identification alternative. This was a live hazard, not a nit: IBKR
supports lot-matching methods (LIFO, specific lot, MaxLoss), and CLAUDE.md tells engineers
`reference/` outranks general knowledge — the library would have blessed adopting IBKR's lot
matching.

**Legal impact assessed as currently nil, and worth recording why:** the maintainer's data
contains exactly one `ClientAccountID` across the whole history (figures in
`private/real-data-observations.md`). Per-Depot and pooled FIFO coincide at one depot. The engine reads no account
identifier anywhere in `src/engine/`, `src/domain/` or `src/processing/`. So the whole
per-Depot thread — #19's harness, #28's aggregation, #31/#32 — changes no figure in the
maintainer's own declaration while refactoring the FIFO core that determines every figure
that *is* declared. That is a sequencing argument for landing the parity repair before the
engine work, not against the work.

Recorded as **open, not settled**: Satz 7 hooks on §5 DepotG and Rz. 97–99 are written for a
German depotführende Stelle; whether the "einzelnes Depot" boundary transposes to a foreign
broker's sub-account structure is not answered by any Tier 1/2 source located.

Not fixed here, deliberately: the `RawPositionRecord` alias (that is #28's `febf459`, and
duplicating it would collide).

## 4. Cross-cutting pattern

Across five PRs: **the code and tests are consistently sound; the legal and factual prose is
unreliable.** Every substantive mechanism held up under testing. 8 citation/claim errors,
all corrected here. #19 is the first description with nothing wrong in it, so this is a
tendency rather than a law — but it has held four times out of five.

Practical consequence: **review the diff, not the description.** Verify claims empirically
rather than reading them.

**Second pattern, visible from #19 onward: verification tooling that cannot see what it
claims to check.** #33 found the test suite silently reading the developer's real `cache/`;
#19 shipped a real-data parity gate with the same hole, which would have certified every
later PR's "output-neutral" claim without being able to observe a classification change.
Both were green. When a PR adds a checking mechanism, test the *mechanism* against a
deliberately broken tree — a green result from an instrument nobody calibrated is worth
nothing.

---

## 5. Verified migration path for the remaining 20 PRs

The first five commits of every branch in the train are exactly the ones absorbed here
(`af95b72`, `7f6fca0`, `35d5873`, `1d7728b`, `361b11a`), so one command migrates any of them:

```
git rebase --onto <new-main> 361b11a <branch>   # 1d7728b before #19 was absorbed
```

Simulated against this branch's HEAD:

| PR | Result |
|----|--------|
| #20 | **clean** |
| **#21** | 4 conflict hunks, one file (`tests/fixtures/loss_offsetting_data.py`) |
| #22–#40 | inherit #21's conflict (cumulative train) |

Only two commits in the whole train touch that file: `7f6fca0` (#16, absorbed) and
`4eeeffb` (#21, the JStG-2024 cap repeal). The conflict is our `KNOWN-WRONG` markers meeting
the fix they point at:

```
<<<<<<< HEAD
    # KNOWN-WRONG (VALIDATION_REPORT.md finding #1, HIGH): … Correct value: -30000.00.
    conceptual_net_derivatives_capped=D("-20000.00"),  # Capped!
=======
    conceptual_net_derivatives_capped=D("-30000.00"),  # cap repealed (JStG 2024)
>>>>>>> 4eeeffb
```

**#21's value equals the value our marker predicted** — two independent derivations
agreeing. Resolution is "take theirs, drop the marker", ×4. The conflict is desirable: it
forces whoever lands #21 to retire the markers consciously.

---

## 6. Merge constraints discovered (binding, independent of anything else)

- **#31 and #32 cannot be separated.** #31 implements per-Depot FIFO but touches no
  reference file; until #32 lands, `estg-20-kapitalvermoegen.md` still says the engine is
  account-agnostic and "full per-Depot FIFO is a deferred larger change" — the library would
  actively contradict the code.
- **#18's reference fix must stay in #18**, not #28.
- **#28 (`febf459`) will conflict with our Satz 7 section, and should.** #28 inserts a
  "Known limitation — account-agnostic (merged) FIFO" block at exactly the line our
  `a40adce` rewrote, and it re-adds the false *"unless specific identification is
  possible"* clause because it was written against the old text. Resolution when #28 is
  reached: **keep ours**, graft #28's block in (it is good, more specific content —
  it characterises precisely when merged FIFO bites and documents the co-holding warning),
  but re-cite it from bare "§20 Abs. 4 EStG" to **Rz. 97 S. 2**, and do not restore the
  deleted clause. #28's harness edit (strengthening `test_position_rows_per_account` once
  it fixes the `AccountId` alias) is in a different hunk from our docstring change and will
  merge cleanly.
- **Nothing in #20–#40 ever touches `scripts/parity_check.sh` again**, so the repairs in
  `96d4312` are not duplicated by any later PR and conflict with nothing. Verified by
  scanning every `pr/*` ref.
- **`89fdd80` (train: tax-neutral internal transfers, Depotübertragung)** also edits
  `estg-20-kapitalvermoegen.md`. Our Satz 7 section already records that a transfer between
  the taxpayer's own depots is not a Veräußerung under Abs. 2 and that the §43/§43a
  Depotübertrag rules are Kapitalertragsteuer provisions that cannot carry the disposal
  question — check that commit against it rather than the other way round.
- **#16 must not land without #21**, or the legally-repealed €20k cap stays pinned and
  blessed by a comment. (Mitigated here by the `KNOWN-WRONG` markers.)

## 7. Knowledge-store scan of the unreviewed PRs

8 of 25 touch `reference/`: #18, #21, #22, #28, #29, #32, #35, #40. Quality improves sharply
after #18 — #22 (§108 AO i.V.m. §§187/188 BGB anniversary arithmetic incl. leap year), #29
(§18 Abs. 2 S. 2 partial-year + §18 Abs. 3 verbatim deemed-inflow) and #35 (Einlagenrückgewähr,
explicitly separating settled law from open questions) are the strongest legal work in the train.

Two things to scrutinise when reached:
- **§20 Abs. 4 Satz 7** is cited by #32 as "(FIFO per Depot)" but never quoted. Verified Tier 1:
  Satz 7 *is* the FIFO fiction, but it is conditioned on *Sammelverwahrung* per §5 DepotG and
  does not literally say "per Depot". That is the standard interpretation presented as statute;
  it needs Tier 2 backing.
- **#32** claims non-EUR cash transfers are tax-neutral citing "§43 Abs. 1 S. 5 /
  Fußstapfentheorie". §43 is Kapitalertragsteuer (withholding), not the disposal question.
  Conclusion likely right, citation likely doing work it can't do.

---

## 8. Open items NOT in the train

- **German KESt misdeclared as foreign tax.** `loss_offsetting.py:167-171` sums every
  `WithholdingTaxEvent` into Zeile 41 (*ausländische* Steuern) with no country filter, and the
  engine has no Zeile 7/37/38/39 at all. Confirmed in real data: several German issuers'
  dividends withhold **exactly 26.375%** of gross (25% KESt + 5.5% SolZ) — the signature of
  German KESt. Instances in `private/real-data-observations.md` (not published).
  Fully researched — see `reference/tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md`,
  section 6 for the required fix. **Not implemented.**
- **`data_import/` was lost and has been rebuilt** from the derived `data/` copy with
  `scripts/rebuild_data_import.py --verify` (round trip lossless). Snapshot files survive
  for **one tax year only**, so parity runs are limited to that year until the earlier
  years' Positions/Cash_Balance files are re-downloaded from IBKR. Real-data parity on that
  year is confirmed working: two same-tree captures compare identical on console and PDF.
- **Same-date event processing order is nondeterministic (found 2026-08-02, not fixed).**
  Two runs of identical code over the real 2025 data permute 12 log lines: several
  `OPTION_CASH_SETTLEMENT` events falling on the same date are processed in a different
  order each run. Tax figures were unaffected — console report and PDF compared identical —
  so this is not a live defect, but the ordering is unstable, which suggests a sort keyed on
  date without a stable tiebreaker. It matters for the per-Depot work: once lots are
  partitioned per account, the order in which same-day disposals consume lots can change
  which lot each one takes. Worth pinning a deterministic secondary sort key before #31/#32
  land. This is also why the parity gate treats a log-only difference as non-fatal
  (`PARITY_STRICT_LOG=1` to enforce) — with the streams split, console and PDF are compared
  strictly and only the log tolerates it.
- **No CI.** No `.github/workflows`. Every "green" claim in the train is unverified by
  anything observable; each review currently costs a manual baseline-control run.
- `VALIDATION_REPORT.md` findings 2–6 remain open (finding 1 is handled by #21).
- 2022 ledger validation still FAILs — one security's EOY quantity is non-zero when the
  broker reports zero; pre-existing, caused by trade history predating the 2021 data floor.
  Unchanged by this branch. Instance in `private/real-data-observations.md`.

---

## 9. Attribution — preserving Fsaupe's GitHub credit

**Verified 2026-08-02:** `florian.saupe@gmx.de` is registered to the GitHub account
`Fsaupe` (checked against an already-merged commit via the API — `.author.login` resolves,
it is not an unlinked email). Therefore **preserving the git Author field is sufficient for
full GitHub attribution**: profile link, avatar, and contribution-graph credit, as soon as
these commits land on the default branch.

Structural rule that makes this work, and that must be maintained:

> **Fsaupe's commits are cherry-picked unmodified. Every correction of ours is a separate
> commit on top.** Never amend, squash, or fold a fix into one of their commits.

Current state on this branch: 5 commits authored by `Fsaupe <florian.saupe@gmx.de>`,
6 authored by the repo owner. Committer is the repo owner throughout (normal for
cherry-pick; GitHub attributes by Author).

### Original → landed SHA map

| PR | Original (on `pr/*` ref) | Landed here | Author |
|----|--------------------------|-------------|--------|
| #33 | `f90c319` | `449767f` | Fsaupe |
| #33 | `5197bd5` | `be66807` | Fsaupe |
| #16 | `7f6fca0` | `86c34c4` | Fsaupe |
| #16 | `af95b72` | **dropped** (`rework2-plan.md`, internal working doc) | Fsaupe |
| #17 | `35d5873` | `55c7b95` | Fsaupe |
| #18 | `1d7728b` | `4fbf570` | Fsaupe |
| #19 | `361b11a` | `312bc3a` | Fsaupe |

All original SHAs remain resolvable in the local object store via the fetched `pr/*` refs
(`git fetch origin 'refs/pull/*/head:refs/remotes/pr/*'`).

### When landing on GitHub later

1. **Do not squash-merge.** Squashing collapses all 11 commits to a single author and
   destroys Fsaupe's credit. Use a merge commit, or fast-forward.
2. #16/#17/#18/#33 will **not** auto-close, because these are cherry-picks, not the branch
   heads. Close each manually with a comment naming the landed SHA and the deltas applied
   (`2383b8a` for #33; `f5e8c0c` for #16/#17; `547df96`+`76cb8df`+`320e20a` for #18) so the
   trail from PR to commit is explicit.
3. Reference the PR numbers in the merge commit body so GitHub cross-links them.
4. Fsaupe's contribution graph credits the Author email regardless of who merges, so no
   `Co-authored-by:` trailer is needed — and adding one to *our* fix commits would muddy who
   is responsible for which change.

An alternative that yields "merged" status on the PRs themselves: ask Fsaupe to pull our fix
commits into their branches and re-push, then merge their PRs normally. Higher fidelity for
them, more coordination for us. Either way the structural rule above keeps both options open.

---

## 10. How to resume

```bash
# the branch lives in the main repo's object store; /tmp worktrees were disposable
git worktree add /tmp/review hermetic-tests-first
cp src/config.py /tmp/review/src/config.py          # config.py is gitignored
ln -s "$PWD/data_import" /tmp/review/data_import    # data_import is gitignored

# clean-clone protocol (what CI should do)
cd /tmp/review && rm -rf cache && cp src/config_example.py src/config.py && uv run pytest -q

# PR refs (re-fetch if absent)
git fetch origin 'refs/pull/*/head:refs/remotes/pr/*'
```

**Review method that worked** — worth repeating rather than reinventing:
1. Never trust the PR description; diff the code and verify claims empirically.
2. Always run a **baseline control** — the same check on unmodified `main` in an equally
   clean worktree — before attributing a failure to a PR. This is what distinguished #33's
   real defect from the two pre-existing clean-clone failures.
3. Verify **red-first** by reverting `src/` and re-running the PR's new tests.
4. Run **real-data parity** (`validate_ledgers.py` + `src.main --report-tax-declaration` for
   each year, plus PDF text SHA) against the baseline; normalise timestamps and log lines.
5. For any behavioural change, check the cited provision **actually exists** in `reference/`
   and says what the PR claims.

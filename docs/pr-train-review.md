# PR Train Review — state, rationale, and how to resume

**Branch:** `hermetic-tests-first` (local only, never pushed)
**Base:** `main` @ `ebad4e7`
**Status as of 2026-08-02:** 4 of 25 PRs reviewed and accepted; 21 not yet reviewed.
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

**Verification at HEAD:** 394 tests pass on a simulated clean clone
(`config_example.py`, no `cache/`). Real-data output is **byte-identical to `ebad4e7`**
across tax years 2022–2025 — console report, `validate_ledgers.py`, and PDF text SHA-256.

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

## 4. Cross-cutting pattern

Across four PRs: **the code and tests are consistently sound; the legal and factual prose is
consistently unreliable.** Every substantive mechanism held up under testing. Not one
description was fully accurate — 7 citation/claim errors, all corrected here.

Practical consequence: **review the diff, not the description.** Verify claims empirically
rather than reading them.

---

## 5. Verified migration path for the remaining 21 PRs

The first four commits of every branch in the train are exactly the ones absorbed here
(`af95b72`, `7f6fca0`, `35d5873`, `1d7728b`), so one command migrates any of them:

```
git rebase --onto <new-main> 1d7728b <branch>
```

Simulated against this branch's HEAD:

| PR | Result |
|----|--------|
| #19, #20 | **clean** |
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
  engine has no Zeile 7/37/38/39 at all. Real data: BMW 2024 = €317.56 on €1,204.00 gross =
  exactly 26.375% (25% KESt + 5.5% SolZ). Also Aurubis 2021/22/23 and BASF 2022.
  Fully researched — see `reference/tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md`,
  section 6 for the required fix. **Not implemented.**
- **No CI.** No `.github/workflows`. Every "green" claim in the train is unverified by
  anything observable; each review currently costs a manual baseline-control run.
- `VALIDATION_REPORT.md` findings 2–6 remain open (finding 1 is handled by #21).
- 2022 ledger validation still FAILs (AMAZON.COM INC EOY 320 vs 0) — pre-existing, caused by
  trade history predating the 2021 data floor. Unchanged by this branch.

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

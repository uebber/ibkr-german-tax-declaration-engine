# PR Train Review — state, rationale, and how to resume

**Branch:** `hermetic-tests-first` (local only, never pushed)
**Base:** `main` @ `ebad4e7`
**Status as of 2026-08-02:** 11 of 25 PRs reviewed and accepted; 14 not yet reviewed.
**Next up:** #26 (train 11). Rebase remaining branches from `345bd49`; see section 5.
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
1c4c981 fix(engine): EoY reconciliation failure is fatal (owner's ruling)      [ours]
47f2581 chore: drop the unused typing import the channel arrived with         [ours]
a2f3974 fix(reporting): PDF stops certifying an EoY reconciliation             [ours]
0893139 tests: pin the two ends of the data-gap channel the suite can't see    [ours]
7e3eada fix: say what the data-gap channel covers; root its error type         [ours]
68fd82d feat: data-gap channel                                        (PR #25, Fsaupe)
1c01fbd docs: correct the replay determinism claim and the merger citation    [ours]
273f6ef fix(engine): refuse an unsortable historical currency event            [ours]
a35a881 tests: pin the replay stream's ordering contract                       [ours]
a1bd93c refactor: unified chronological replayer                      (PR #24, Fsaupe)
edda318 chore(engine): finish the LedgerKey conversion in the annotations      [ours]
0ad410d tests: close the blind spot at the Pass 2 merger source lookup         [ours]
3d3873b fix: drop the merger lookup's test-only fallback, re-key fixtures      [ours]
d6537aa fix(engine): aggregate view's lot order matches the ledgers            [ours]
05b839b fix(tax-law): cite the Depot rule where it actually comes from         [ours]
3b8012c refactor: LedgerKey seam — (account, asset) + views          (PR #23, Fsaupe)
f5248a3 fix(engine): refuse an undecidable §23 case; truthful flag             [ours]
f2e5cc3 fix(tax-law): cite the reference, refuse an undefined §23 period       [ours]
24b3c1f docs(reference): root the §23 Jahresfrist at Tier 1; §108 Abs. 3 open  [ours]
e0026da feat: HoldingPeriod domain rule — §23 Jahresfrist            (PR #22, Fsaupe)
eeb129c fix(tax-law): verify the KAP Zeilen per year; refuse pre-2021          [ours]
50d282b docs(reference): close the Basiszins sourcing gap (BMF-Schreiben)      [ours]
47b00a4 docs: record the #21 verdict, BewG provenance, VP year gap            [ours]
a96a5fd docs: drop the dangling working-document refs AR2 reintroduced         [ours]
a41dbb9 fix(reporting): correct repeal note, keep the Zeile 24 cross-check     [ours]
a6ff53d fix(tax-law): Basiszins regime floor; pin registry to the reference    [ours]
7bfc8fa docs(reference): correct the Basiszins table, cite it per year         [ours]
df8dd6b docs(reference): root the JStG-2024 cap repeal at Tier 1               [ours]
88a91e9 feat: law-as-data registry                                       (PR #21, Fsaupe)
e467cad docs: drop refs to working documents this repo does not contain        [ours]
fa05198 fix(tests): close three blind spots in the leak tripwire               [ours]
a7f7032 fix: make the RunContext boundary real, drop dead decimal_context      [ours]
16cd0c8 refactor: explicit RunContext                                    (PR #20, Fsaupe)
266d814 docs: trace event-ordering nondeterminism to PRD 5.8                   [ours]
555a57b docs: record same-date event-ordering nondeterminism                   [ours]
e9d39ec chore: separate published content from private account data            [ours]
9e90f7b docs: record #19 verdict, parity-tool defect, #28 conflict             [ours]
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

**Verification at HEAD:** 489 tests pass on a simulated clean clone
(`config_example.py`, no `cache/`) and with the real config. Real-data output is
**byte-identical to `ebad4e7`** across tax years 2022–2025 — console report,
`validate_ledgers.py`, and PDF text SHA-256.

> That real-data run was performed at `8ee553e` (through #18). It was **not** re-run for
> #19, because `data_import/` no longer exists on this machine — see section 8. It still
> holds by construction: #19 and the four commits on top of it change `scripts/`, `tests/`,
> `reference/`, `docs/` and `.gitignore` only, and touch no file under `src/`.
>
> From #20 on, parity is run for **tax year 2025 only** — the one year whose Positions and
> Cash_Balance snapshots survived the `data_import/` rebuild. At `eeb129c` (#21 + our seven
> fixes) versus `f004746`: **PDF IDENTICAL**, console 3 lines (our reworded repeal note),
> log difference entirely the known `OPTION_CASH_SETTLEMENT` permutation, checked against a
> same-tree control taken the same session. At `47f2581` (#25 + our four fixes) versus
> `78868e4`: **console IDENTICAL, PDF IDENTICAL**, 14 log lines against a 10-line same-tree
> control, all of them the same permutation.

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

### PR #20 (train 5) — explicit RunContext — **ACCEPTED, boundary made real**

Rebased clean, as predicted. 397 → 401 tests. Red-first confirmed on
`test_pipeline_requires_explicit_tax_year` (the other three test a brand-new module, so
red-first is vacuous for them).

**First PR in the train with genuinely zero legal surface — verified, not assumed.** The
only hunk touching tax logic is the `loss_offsetting.py` capping default, moved from
import-time to call-time binding. Three independent checks agree it is inert:

1. Nothing in `src/` or `tests/` mutates `APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING`, so
   the two binding times coincide.
2. A/B with a deliberately leaked flag produces the *identical* four failures before and
   after the change.
3. Blast radius is nil regardless: `conceptual_net_derivatives_capped` is consumed only by
   `console_reporter.py:214`, a diagnostic line labelled *konzeptionell*. It reaches no
   form-line mapping. (README already says form reporting is always un-capped; confirmed
   in code.)

So no `reference/` work was required, and none was done.

Real-data parity, tax year 2025 (the only year with surviving snapshots): console
IDENTICAL, PDF IDENTICAL. The 12-line log difference is entirely the known same-date
`OPTION_CASH_SETTLEMENT` permutation — established by a **same-tree control capture that
produced a larger 14-line difference**, so the noise is ambient, not attributable to #20.

**Defect 1, moderate — the boundary was a pass-through; its config fallbacks were dead
code (`a7f7032`).** `src/cli.py` already resolved both run-defining values before `main.py`
saw them: `--tax-year` carried `default=config.TAX_YEAR`, and the parser did the
`IS_INTERACTIVE_CLASSIFICATION` fallback itself. `RunContext.from_config()` was therefore
always handed non-None arguments and never executed its resolution branches. Proven with a
runtime probe that printed on fallback: **0 hits** on a default invocation and on
`--no-interactive`. Consequences: the commit's central claim — main.py is "the only place
user config is read for run-defining values" — is false, and
`test_from_config_reads_boundary_defaults` covers a path production never takes.

Fixed by making the claim true rather than softening it: `cli.py` no longer imports
`src.config` at all, unspecified options stay `None`, the boundary resolves them, and the
default PDF filename (which embeds the tax year) moves to `main.py`. Resolution verified
unchanged for every argv shape. Only `--help` differs — it prints "TAX_YEAR from config.py"
instead of interpolating the value.

**Defect 2, low — `RunContext.decimal_context` was dead and duplicated precision config
(`a7f7032`).** Never read anywhere; `main.py` still calls `setup_decimal_context()`, which
installs precision into the process-wide context. Two sources of truth for precision, one
inert, in a repo whose CLAUDE.md makes precision discipline explicit. Field removed.

**Defect 3, low-moderate — the new leak tripwire had three blind spots (`fa05198`).**
Calibrated against deliberately broken trees rather than trusted:

| broken tree | session-scoped (as shipped) | per-test (repaired) |
|---|---|---|
| persistent `TAX_YEAR` leak | exit 1 ✓ | exit 1 ✓ |
| leak early, restore late | **exit 0, green** | exit 1 ✓ |
| leak any other config global | **silent** | exit 1 ✓ |
| culprit named | last test to run (innocent) | the actual leaker |

The leak-then-restore hole matters most: it is the exact shape of the incident the wire
exists to catch. The second hole contradicted its own docstring ("a mutated global config
value"), and left the legally-relevant capping flag unwatched. Made per-test and widened to
every uppercase config attribute; no latent leaks surfaced in the existing suite, runtime
unchanged.

**Defect 4, low — dangling references in production source (`e467cad`).**
`src/run_context.py`, `tests/test_run_context.py`, `src/pipeline_runner.py` and
`src/engine/loss_offsetting.py` cite "rework2-plan AR1" and "legal-review-todo.md F1".
Neither file exists here — `rework2-plan.md` is `af95b72`, dropped when #16 was absorbed,
and "AR1"/"F1" are identifiers from that same dropped document. Also cleared the two
instances that arrived with #19 and were missed then.

**Defect 5, nit — `pytest.raises(Exception)`** in the immutability test passes on any
error at all; narrowed to `FrozenInstanceError`.

**Right-sizing what this PR is worth.** At the *end* of the train (`pr/40`), `RunContext`
is still referenced only in `src/main.py`, at the same single call site it is introduced
at — no commit in #21–#40 touches `src/run_context.py` or consumes the object, and the
remaining 20 PRs keep passing `tax_year` as a plain `int`. So the durable value of #20 is
**the required `tax_year_to_process` parameter and the leak tripwire**, not the context
object, which stays a two-field wrapper around one call site for the whole train. That is
not a reason to reject — the required parameter genuinely removes the ambient default, and
the repaired tripwire is a real regression guard — but the PR title's "explicit RunContext"
oversells an abstraction nothing downstream adopts. Worth remembering if a later PR is
justified by "consistency with the RunContext pattern": there is no such pattern in the
train yet.

### PR #21 (train 6) — law-as-data registry — **ACCEPTED after knowledge-store repair**

Rebased with the 4 predicted conflicts in `tests/fixtures/loss_offsetting_data.py`;
resolution was "take theirs, drop the `KNOWN-WRONG` marker" ×4, exactly as section 5
foresaw. 401 → 420 tests, then 440 with ours. Red-first verified: with `src/` reverted,
10 tests fail (6 cap-repeal, 4 Basiszins) — the commit says 7, which is imprecise but not
wrong in kind. Real-data parity for tax year 2025 below.

**The central legal claim is right, and it is the first time in the train that a
behavioural change rests on a provision the store already contained.** #21 sets
`derivative_loss_cap_applies=False` for VZ 2024 on the strength of "abolished
retroactively for all open cases (§52 Abs. 28 EStG n.F.)", which
`estg-20-abs6-verlustverrechnung.md` already asserted. Verified at Tier 1 rather than
taken on trust — and it holds:

- **§52 Abs. 28 Satz 25 EStG n.F.** — §20 Abs. 6 Satz 5 a.F. *"ist auf alle offenen Faelle
  nicht mehr anzuwenden"*; **Satz 26** the same for Satz 6. Read off dejure.org; the
  buzer.de synopsis of the JStG-2024 amendment shows what each clause replaced
  (*"ist auf Verluste anzuwenden, die nach dem 31. Dezember 2020 entstehen"*).
- gesetze-im-internet.de confirms §20 Abs. 6 now has **five** Saetze and neither €20,000
  restriction. Note the renumbering trap: the *current* Satz 5 is the §43a Abs. 3 S. 4
  Bescheinigung rule, formerly Satz 7.

**What the store was missing was the sentence numbers and a Tier 1 quote** — its only
source was a Bayerisches-LfSt summary page, and Validation Protocol item 3 asks for
paragraph *and* sentence. Repaired in `df8dd6b`, together with the distinction #21 depends
on but does not state: the repeal removes the *offsetting restriction*, not the published
*forms*. Z21/Z24 stay for VZ ≤ 2024, which is why `separate_derivative_lines` must remain
year-specific while `derivative_loss_cap_applies` goes to False everywhere.

**Blast radius of the cap flag, re-confirmed at this tree:** `loss_offsetting.py:266` and
`console_reporter.py:213` only. No form line. The −20000 → −25000 fixture corrections are
the diagnostic *konzeptionell* figure, i.e. VALIDATION_REPORT finding #1, now marked
resolved there.

**Defect 1, moderate — the Basiszins table promoted two rows of the wrong statute
(`7bfc8fa`, `a6ff53d`, `50d282b`).** #21 widens the table from {2024, 2025} to 2016-2026 and makes the
engine compute a Vorabpauschale for every listed year. That raises the evidentiary bar on
rows that had been inert, and the two oldest do not survive it: **1.10% (2016) and 0.59%
(2017) are the Basiszins for the vereinfachtes Ertragswertverfahren nach §203 Abs. 2 BewG**
(BMF 04.01.2016, IV C 7 - S 3102/07/10001; the 2017 value from OFD-Verfuegungen) — a
different statute. The rows even carried the BewG reference dates, 04.01.2016 and
02.01.2017, which is how it surfaced. The Vorabpauschale did not exist then: InvStG 2018
provisions *"sind ab dem 1. Januar 2018 anzuwenden"* (**§56 Abs. 1 S. 1 InvStG**), the first
Basiszins notice is BMF 04.01.2018, the first Vorabpauschale is the one for calendar 2018.
Left in, a run for VZ 2016/2017 invents deemed income. Both rows removed.

The sourcing was then closed rather than left as a caveat (`50d282b`). The BMF site hosts
only the two newest Schreiben, so the 2018-2024 originals were retrieved as archived copies
of the BMF PDFs (2019 from the BVL mirror) and read in full: every row now carries the
Schreiben date, the GZ and the BStBl page, taken from the document. The chain
self-authenticates — each letter's BEZUG line names its predecessor *with that
predecessor's BStBl page*, so all but the newest citation is confirmed by a second BMF
document. Two things the letters settle that the summaries only paraphrased: the year
mapping, verbatim (*"Die Vorabpauschale fuer 2024 ... gilt ... am 2. Januar 2025 ...
zugeflossen"*), and the negative years (*"Aufgrund des negativen Basiszins wird keine
Vorabpauschale erhoben"*). Also corrected: 2021 and 2022 were computed on 04.01. and 03.01.,
2 January not being a Boersentag in those years.

**Defect 2, moderate — the registry↔reference "consistency" check could not see the
reference (`a6ff53d`). Fourth instance of the pattern.** The shipped test kept its own
hardcoded copy of all eleven rates while the reference document claimed the tests "assert
the registry matches this document". Two hand-kept copies cannot detect drift from a third
— and both copies carried the BewG rows, so the check was green on the exact defect it
existed to prevent. Replaced by a parse of the markdown table, calibrated against five
deliberately broken trees (value edited on either side, row added to the doc only, hole
punched in the registry, BewG row restored): all five trip it, green again when restored.

**Defect 3, moderate — the console tells VZ ≤ 2024 users a false rule and drops a live
form line (`a41dbb9`).** Flipping the flag for 2024 moves the summary onto a branch written
for the 2025 boundary. It prints *"(Verlustverrechnungsbeschraenkung fuer Termingeschaefte
ab {tax_year} aufgehoben)"* — "ab 2024" on a 2024 run, "ab 2021" on a 2021 run. The repeal
has no first year of application; that is the whole point of "alle offenen Faelle". And the
line reporting the gross losses declared on **Zeile 24** was nested inside the cap branch,
so a form line that still exists for VZ ≤ 2024 and is still populated stopped being shown.
Keyed to `separate_derivative_lines` now. New `tests/test_console_reporter_derivatives.py`,
red-first 7/13.

This also falsifies the commit's "Real-data parent-parity: IDENTICAL" for any VZ ≤ 2024
run: that block prints unconditionally, so the console *always* changes. It is true for
2025, which is the only year with surviving snapshots here.

**Real-data parity, tax year 2025** (baseline `f004746` vs. #21 + our five fixes):
**PDF IDENTICAL**, console 3 lines — solely our reworded repeal note — log 8 lines, the
same count and the same `OPTION_CASH_SETTLEMENT` permutation shape as the same-tree control
capture taken immediately before. No declared figure moves.

**Open, and it is not #21's bug — but #21 enlarges it. The engine books the
Vorabpauschale one year too early.** §18 Abs. 3 InvStG (already in the store, in
`invstg-18-vorabpauschale.md`) deems the VP for calendar X to flow on the first working day
of X+1, so it is income of **X+1**. `_calculate_vorabpauschale` computes it from
`basiszins[tax_year]` and the tax year's own SoY position and reports it **in tax_year**.
Before #21 that misfired only for 2024 and 2025, the only years in the config; now it
misfires for every year 2018-2026. The sharpest case is **VZ 2023**, which flips from right
to wrong: the amount taxable in 2023 is the 2022 VP, and 2022's Basiszins is −0.05% → zero,
which is what the engine produced when it skipped; it now computes 2.55% on the 2023 SoY
value instead.

Not fixed here, deliberately — **PR #29 fixes it** (`_vp_for_calendar_year`,
`deemed_inflow_year = target_year + 1`, prior-year lines feeding this year's return), and
#29 needs exactly the widened table #21 supplies, since it looks up `basiszins(tax_year−1)`.
#29 also rewrites `invstg-18-vorabpauschale.md` with the verbatim Abs. 3 text and the
Zuflussprinzip reasoning, so that file is left untouched here to avoid a pointless conflict.
Practically the exposure is nil today: VP needs an SoY positions snapshot, and only 2025 has
one. See the new merge constraint in section 6.

**Defect 4, moderate — the pre-2024 form-line fallback was never verified, and below 2021
it was wrong (`eeb129c`).** `get_form_rules` serves the 2024 entry to every earlier year,
and the store only had the Anleitung for 2024/2025, so Validation Protocol item 4 (form
lines verified against the official form *for that year*) was unmet for everything before
2024. Checked against the official forms:

| VZ | Z20 | Z21 | Z22 | Z23 | Z24 | source |
|----|----|----|----|----|----|----|
| 2020 | 232/432 | **frei** | 235/435 | 236/436 | **frei** | 2020AnlKAP051 |
| 2021 | 232/432 | 631/831 | 235/435 | 236/436 | 635/835 | 2021AnlKAP051 |
| 2022 | 232/432 | 631/831 | 235/435 | 236/436 | 635/835 | form + Anleitung 2022 |
| 2023 | 232/432 | 631/831 | 235/435 | 236/436 | 635/835 | form 2023 |

2021-2023 are identical to 2024 down to the Kennzahlen, so the fallback was right and is now
a verified mapping. **VZ 2020 is a different form**: Zeilen 21 and 24 are printed *"frei"*
and "Termingeschaefte" does not appear anywhere in it — the separate lines arrived with the
VZ 2021 form alongside the restriction that made them necessary. The engine would have
emitted figures onto non-existent lines, silently. `get_form_rules` now raises
`ProcessingError` below the earliest verified year. Forward carry-over is untouched: a form
structure holds until a later year changes it, and next year's form is not published yet.

**Nit, fixed with the owner's go-ahead:** `tests/test_config_example_completeness.py` cited
"B4/B5g", identifiers from the dropped `rework2-plan.md` — same dangling-reference class as
`e467cad`.

**Everything found in #21 is now fixed in commits**, except the Vorabpauschale year mapping
below, which belongs to #29.

### PR #22 (train 7) — §23 Jahresfrist as anniversary arithmetic — **ACCEPTED after knowledge-store repair**

Rebased clean from `4eeeffb` (#21's fixture conflict is gone, as section 5 predicted).
455 tests, green on the clean-clone protocol. **The tax reasoning is correct and it is the
first behavioural change in the train I could not fault on the law itself** — only on where
the law came from.

**The fix is real.** `days <= 365` and the statutory Jahresfrist coincide except when the
holding spans a 29 February, where the anniversary lies 366 days out and the shortcut wrongly
exempts an anniversary-day disposal. Derived independently from Tier 1: §187 Abs. 1 BGB drops
the acquisition day, §188 Abs. 2 BGB ends the period with the expiry of the day whose number
matches, so a disposal *on* the anniversary is still inside the year. The 29-February clamp is
§188 Abs. 3 BGB, which reads *"nach Monaten bestimmten Frist"* but covers a Jahresfrist because
Abs. 2 treats both as ending on a day *"des letzten Monats"*. `relativedelta(years=1)` clamps
exactly that way. All nine parametrised cases hand-checked against the statute, not the engine.

Red-first verified on this tree: reverting `src/` fails **exactly one** test, the leap-span
ledger case — matching the commit's claim that only the leap case was wrong. Real-data parity
for 2025: console IDENTICAL, PDF IDENTICAL, log 10 lines, all the known
`OPTION_CASH_SETTLEMENT` permutation against a 12-line same-tree control. The commit's "no
leap-year anniversary sale in the dataset" is verified rather than taken: replaying FIFO over
the four real `PRIVATE_SALE_ASSET` ISINs (156 trades, 2021–2025), **no lot/disposal pair
changes verdict** — the closest approaches to the boundary are 340 and 408 days.
The YAML fixture edit is comments and `description`/`notes` only; no `expected` block moves.

**Defect 1, moderate — the citation is broader than the implementation, and the gap is a live
legal question (`24b3c1f`).** #22 cites "§108 AO i.V.m. §§187 Abs. 1, 188 Abs. 2/3 BGB". But
§108 AO is not only Abs. 1. **§108 Abs. 3 AO** extends any Frist whose end falls on a Sunday,
public holiday or Saturday to the next working day — and the engine does not implement it. It
is not a nit: an anniversary on a Saturday or Sunday would run to the Monday, and the Monday is
the first day a taxpayer waiting out the year can actually trade. The two readings disagree on
precisely the disposals most likely to happen.

Neither reading is settled at Tier 1 or Tier 2. Tier 1 is unqualified (*"das Ende einer
Frist"*), and §108 Abs. 1 makes Abs. 3 lex specialis to §193 BGB, which *is* limited to
Handlungsfristen. AEAO zu §108 Nr. 2 lists where the administration applies Abs. 3 —
Bekanntgabefiktionen, §149 Erklärungsfrist, Festsetzungsfrist — and §23 is absent, but as a
list of confirmed applications, not an exclusion. Tier 4 points both ways: **BFH 14.10.2003
IX R 68/98, BStBl II 2003, 898** abandoned the eigentlich/uneigentlich distinction for Abs. 3
altogether (extended to the Festsetzungsfrist by **BFH 20.01.2016 VI R 14/15**), while
**FG Köln 02.06.1997, EFG 1997, 1187 (rkr.)** denied the extension for §23 specifically — and
pre-dates IX R 68/98. Littmann/Bitz/Pust §23 Rn. 106 (Tier 5) follows the FG.

Recorded in `reference/` as an **open question** with both readings, the engine's choice (no
extension) and why, plus a new *Open Legal Questions* section in the coverage matrix carrying
it and #19's foreign-broker Depot question. Not implemented either way: §108 Abs. 3 AO's
*"gesetzlicher Feiertag"* is Land-specific, which would be a second unresolved input.

**Defect 2, moderate — the store did not carry what the PR cites (`24b3c1f`).** Same pattern
as #18 and #19, third instance. `estg-23-private-veraeusserung.md` had three lines on period
calculation, no statutory text, no source for any of it, and one line that just restated the
code ("365-day threshold in `FifoManager`"). #22 replaced that line with a correct prose
summary but added no text, no Absatz precision and no retrieval. Rewritten to the Validation
Protocol: §23 Abs. 1 S. 1 Nr. 2 S. 1 EStG, §108 Abs. 1 AO, §§187 Abs. 1, 188 Abs. 2/3 BGB
verbatim from gesetze-im-internet.de, the derivation, and a table of all seven boundary cases.
Two further findings while doing it:

- The file ran together two separate questions. **Which dates count** is
  H 23 EStH *"Veräußerungsfrist"* — the obligatorisches Geschäft (BFH 15.12.1993 BStBl 1994 II
  687; 8.4.2014 IX R 18/13 BStBl II 826; 10.2.2015 IX R 23/13 BStBl II 487). The store asserted
  it as "Per BFH case law" with no cite. It matters: it is what makes IBKR's `TradeDate` the
  right column and `SettleDate` the wrong one, for every §23 figure the engine emits.
- Two Nr. 2/Nr. 3 rules are unimplemented and were undocumented. **Nr. 2 Satz 4** extends the
  period to ten years for an asset that produced income in any calendar year. **Nr. 3** makes a
  short sale of "andere Wirtschaftsgüter" a private Veräußerungsgeschäft with **no holding
  period at all** — while the engine applies the Nr. 2 Jahresfrist in
  `consume_short_lots_for_cover`, so a short held over a year would be reported exempt where
  Nr. 3 taxes it. Unexercised in the real data (checked: no sell-to-open on any
  `PRIVATE_SALE_ASSET`; the negative running positions on two ISINs are the known pre-2021
  data-floor artefact, first row is a `C` sell with no prior `O`). Documented, not implemented.

**Defect 3, moderate — an unreadable date pair silently produced EXEMPT (`f5248a3`).**
`within_speculation_period` is `None` when either date fails to parse or the disposal predates
the lot, and `if within_speculation_period:` then books
`SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET`. #22 carried this over deliberately — "None
(unparseable dates) falls through to exempt as before". But exempt is a positive finding, not a
null: it drops the disposal out of Anlage SO. Silent, and it always errs towards
under-declaring. Same shape as #18's `320e20a`. Raises `ProcessingError` now, naming both raw
date strings; scoped to the §23 branch, so a STOCK disposal with the same unusable dates still
just leaves `holding_period_days` unknown.

**Defect 4, moderate — the store described an engine that does not exist (`f5248a3`).**
`RealizedGainLoss.__post_init__` set `is_within_speculation_period = True` for *every*
`PRIVATE_SALE_ASSET`, holding period irrelevant — so it read "within the speculation period" on
exactly the disposals just classified as exempt. Nothing reads the field, so no figure was ever
wrong, but the reference file's "Engine mapping" section documented that field as what selects
the §23 category. #22 compounded it by introducing a local `within_speculation_period` with
almost the same name and not connecting the two. The ledger now passes the rule's answer in,
`__post_init__` no longer overwrites it, PRD updated.

**Defect 5, low — dangling references in production source (`f2e5cc3`).**
`src/tax_law/holding_period.py` cites "rework2-plan AR3" and "legal-review finding F3".
Same class as #20's `e467cad`; both documents were dropped with `af95b72`. Also hardened the
domain rule itself, which returned `True` for a disposal dated before the acquisition.

**Calibrated, not just green** (standing checklist item): all four new assertions in
`tests/test_section23_holding_period_guards.py` fail against the pre-fix tree and pass after.
455 → 462 tests. Parity re-run after our fixes: console IDENTICAL, PDF IDENTICAL, log 6 lines,
all known noise — the fail-fast branch never fires on the real data.

**Everything found in #22 is fixed in commits.** Nothing in #23–#40 touches
`src/tax_law/holding_period.py` or `estg-23-private-veraeusserung.md`, and no later commit
touches the §23 branches in `fifo_manager.py`, so all five defects would have survived to the
end of the train.

### PR #23 (train 8) — LedgerKey seam, `(account, asset)`-keyed ledgers — **ACCEPTED after knowledge-store repair**

Rebased clean from `1382bb9`. 462 → 463 tests, green on the clean-clone protocol and with
the real config. Real-data parity for 2025: **console IDENTICAL, PDF IDENTICAL**, log 14
lines against a same-tree control of 10, every one of them the known
`OPTION_CASH_SETTLEMENT` permutation and nothing else. The "no behaviour change" claim
holds.

**This is the first PR in the train whose new guard passed calibration unmodified** — four
deliberately broken `ledger_views` (drop the asset filter, drop the sort, take only the
first ledger, match on account instead of asset) all trip `test_ledger_views.py`. After four
consecutive PRs shipping instruments that could not see what they claimed to check, that is
worth recording as a break in the pattern rather than a non-event.

**And unlike #20's `RunContext`, this seam is really consumed.** Scanning every `pr/*` ref:
`ledger_views.py` and `account_utils.py` are created here, never modified again, and by
`pr/40` `ledgers_for_asset` / `aggregate_lots` feed the EoY validation and the Vorabpauschale
(`calculation_engine.py:1029/1097/1185`) while `account_key()` replaces `DEFAULT_ACCOUNT` at
all fourteen lookup sites. The right-sizing caveat recorded against #20 does **not** apply
here — this is load-bearing infrastructure for #31/#32, introduced one commit ahead of use.

**Defect 1, moderate — the seam is justified by a rule the statute does not contain, and the
store already said so (`05b839b`). Fifth instance of the citation pattern, and the first to
contradict `reference/` rather than outrun it.** Three docstrings and the commit message
assert *"Per-Depot is the statutory FIFO unit (§ 20 Abs. 4 S. 7 EStG)"*; `account_utils.py`
goes further with a bare *"German FIFO (§ 20 Abs. 4) is applied per custody account"*. Our
`a40acce` had already established in `estg-20-kapitalvermoegen.md` that Satz 7 mandates the
FIFO fiction for Sammelverwahrung per § 5 DepotG and that its only "Depot" is inside
*"Depotgesetzes"* — "je Depot" is Tier 2, BMF 14.05.2025 Rz. 97 S. 2. So this is not a gap in
the store, it is the code contradicting it, which CLAUDE.md says to surface rather than
follow. The bare "§ 20 Abs. 4" is the citation-by-section form #22 sharpened.

Both docstrings now also carry the question the seam silently answers: § 5 DepotG is German
and Rz. 97–99 are written for a German depotführende Stelle, so whether the *"einzelnes
Depot"* boundary transposes to a **foreign** broker's sub-accounts is reasoned, not sourced —
recorded as open since #19 and never cited by the PR that builds on it.

**Note for #31:** `7085652` repeats the same sentence verbatim in its commit message. The
correction belongs there too.

Also corrected: the reference's own *"Engine mapping and known deviation"* note, which #23
made stale — the registries are no longer keyed by asset only. The substantive deviation is
unchanged (every write is `DEFAULT_ACCOUNT`, so FIFO is still pooled).

**Defect 2, moderate, latent — `aggregate_lots` sorts by a raw date string with no tie-break
(`d6537aa`).** Every other lot sort in the engine uses `(parse_ibkr_date(...) or
datetime.min.date(), source_transaction_id)`; this one used `lambda l: l.acquisition_date`.
Two problems, neither reachable at this commit because nothing calls the view yet, both
reachable at `pr/40` where it feeds the Vorabpauschale:

1. `acquisition_date` is IBKR-sourced and only *documented* as ISO. `parse_ibkr_date` also
   accepts `YYYYMMDD`, `MM/DD/YYYY`, `DD.MM.YYYY`, and those do not sort lexicographically
   against ISO — `"2024-12-31" < "20240501"` as strings, because `-` is `0x2D`. Production
   does normalise to ISO (`_get_prioritized_date` returns `.isoformat()`), so the shipped
   sort is *coincidentally* right; the rest of the codebase parses first **and** logs
   unparseable dates, which is a fair sign its authors did not treat the format as given.
2. No tie-break, so same-date lots in different Depots fall back to `sorted`'s stability —
   i.e. to registry iteration order, i.e. to the order the ledgers were constructed in. That
   is the same conflation of "unique" with "deterministic" already recorded against PRD 5.8,
   and after the flip it decides which Depot's tranche is which.

Two red-first tests added (mixed formats ordered chronologically; a registry built in both
orders yielding the same sequence).

**Defect 3, low-moderate — production carries a branch only tests reach (`3d3873b`).**
`MergerStockProcessor` gained a second lookup accepting a bare `asset_id` when the tuple
misses, commented *"used by some unit tests passing hand-built ledger dicts"*. Nothing in
`src/` writes a bare key, so it is unreachable in production — the mirror image of #20's
Defect 1, and permanent: it survives unmodified to `pr/40` with per-Depot FIFO live. Removed;
the seven hand-built registries in `tests/test_stock_merger_fifo.py` are re-keyed to
`(DEFAULT_ACCOUNT, asset_id)` instead, so those tests now exercise the lookup production
performs. Pre-existing tests, so cleared with the owner first. Calibrated: reverting one
registry to the bare shape now fails.

**Defect 4, moderate — five of the fourteen converted lookup sites are invisible to the
entire suite.** Probed one at a time by reverting the site to a bare key and running all 463
tests:

| site | suite |
|---|---|
| `calculation_engine.py:277` historical merger **source** | **blind** |
| `calculation_engine.py:645` currency EoY validation | **blind** |
| `corporate_action_processor.py:106` MergerCash currency ledger | **blind** |
| `trade_processor.py:450` currency ledger (2nd site) | **blind** |
| `option_processor.py:460` OptionCashSettlement currency ledger | **blind** |
| the other nine | caught (2–105 failures each) |

So "verified by full suite" covers nine of fourteen; the rest rest on the 2025-only parity
run. That run does exercise site 277 — the real data replays one historical merger, 2 lots,
successfully — which is why the acceptance still stands.

Site 277 is the sharp one, and probing it surfaced a **pre-existing** defect worth its own
entry. The two lookups opening the replay are asymmetric: a missing **target** raises, a
missing **source** only warns and `continue`s. A skipped merger is then absorbed by Pass 3,
which reconciles against the SoY snapshot and synthesises a fallback lot — and because a
merged holding's SoY cost basis *is* the carried-over basis, that fallback reproduces
quantity, cost basis, proceeds and gain exactly. Proven with a probe that raises instead of
warning: under the mutation the source lookup **does** miss on both historical-merger tests,
and both still pass.

What the fallback does not reproduce is the acquisition date — it dates the lot
`f"{tax_year-1}-12-31"`. `test_chained_mergers_historical`'s own docstring says the sale
"uses AAA's original acquisition date" and then never asserts it. New guard `0ad410d` pins
exactly that; on the broken tree it is the **only** failure out of 466. For a STOCK the date
moves no declared figure, but for a `PRIVATE_SALE_ASSET` it decides the § 23 Jahresfrist #22
has just been hardened around. Per the owner's decision the warn-vs-raise asymmetry itself is
left alone and recorded in section 8.

**Defect 5, nits (`edda318`).** Five signatures still declared the registries as
`Dict[uuid.UUID, FifoLedger]` after the keys became tuples, and stay wrong through `pr/40`;
corrected. Double trailing comment un-nested. Two things left alone **deliberately**, both
checked against `pr/40`: the now-unused `account_key` imports (the flip calls
`account_key(event.account_id)` at those exact sites) and `for (ledger_account, asset_id)`
in Pass 3, whose loop variable looks unused here but becomes load-bearing at `pr/40`.
Also dropped the "rework2 AR4" markers — `rework2-plan.md` is the deliberately dropped
`af95b72`, same dangling-reference class as `e467cad` and `f2e5cc3`, fourth instance.

**Everything found in #23 is fixed in commits**, except the merger warn-vs-raise asymmetry,
which is pre-existing and now an open item.

### PR #24 (train 9) — unified chronological replayer — **ACCEPTED, contract now tested**

Rebased clean from `ac1e9a1`. 466 → 471 tests with ours (the PR itself adds none), green on
the clean-clone protocol and with the real config. Real-data parity for 2025 is the
strongest in the train so far: **console IDENTICAL, PDF IDENTICAL**, and the log compared as
a *multiset* differs from the parent by exactly the three intentional wording lines
(`Pass 1: Creating…` removed, `Building unified historical replay stream…` added,
`(three-pass)` → `(unified replay)`) plus one ECB read-timeout that the same-tree control
reproduces. The 98-line ordered log diff is pure reordering, which is what the refactor is.

**The "no behaviour change" claim holds, and the commutation argument behind it checks
out** — read rather than assumed. Every Phase.LEDGER_EVENTS handler touches exactly one
ledger: `apply_historical_event` only `self`; `_apply_historical_currency_event` only the
`ledger` it is passed; `reconcile_with_soy_position` and `_reconcile_currency_soy` only their
own. `_replay_historical_merger` spans two securities ledgers but runs in a later phase, as
before. So interleaving securities and currency events, and moving MERGERS and the securities
RECONCILE to after the currency events, cannot change a figure. Two orderings that did NOT
change are worth recording because they look like they should have: `securities_ledger_count`
is captured before `_ensure_currency_ledger_exists` starts adding currency ledgers to
`fifo_ledgers`, so the count logged at the end is still the securities-only count; and the
Pass 3 loop still iterates `fifo_ledgers` before that same mutation, so currency ledgers still
get no securities reconcile.

**And the seam is really consumed** — the #20 `RunContext` caveat does not apply. `replay.py`
is created here and never modified again, but by `pr/40` the internal-transfer handler
registers at `Phase.LEDGER_EVENTS` *because* it needs the chronological interleave with
trades ("reconstructs a bought-transferred-sold history lot-exactly"), and the historical
option-replay fix relies on the same ordering to run an exercise before its stock leg. The
contract becomes figure-load-bearing later in the train even though it moves nothing here.

**Defect 1, moderate — the contract is the whole PR and it shipped with no test, in a suite
that cannot see it (`a35a881`).** Mutating `ReplayStream.run()` and running all 466:

| mutation | failures |
|---|---|
| drop the sort entirely (insertion order) | **0** |
| drop chronology, keep phase + insertion order | **0** |
| drop the `seq` tie-breaker | **0** |
| reverse every historical **currency** event | **0** |
| reverse every historical **security** event | 1 |
| run MERGERS before LEDGER_EVENTS | 1 |
| run RECONCILE before MERGERS | 1 |

The first three are weak mutations and it is worth knowing why: **insertion order almost
exactly reproduces the old three-pass order**, so "no sorting at all" is nearly a no-op here.
The fourth is not weak. The entire historical currency replay — which fixes the EUR cost basis
of every foreign-currency lot and so every FX gain declared under §20 Abs. 2 Nr. 3 / Abs. 4 —
can be replayed backwards with the whole suite green. And the single failure the two phase
mutations produce is **our own `0ad410d`** from the #23 review; without that guard the phase
contract would have been unobservable too. `tests/test_replay_stream.py` now pins the three
run() properties plus a figure-level currency scenario (−25.00 EUR chronologically, −75.00 EUR
if the order is disturbed), calibrated against every mutation above.

Two things that probe surfaced, both recorded in the test module because they bound what it
proves. **`ParsingOrchestrator.get_all_financial_events` already sorts the entire event list
by `get_event_sort_key` before the engine runs**, so CSV row order is normalised away upstream
and the stream's sort is a second, independent guarantee rather than the one that establishes
chronology — which is the other reason the insertion-order mutations are green. And **`seq` is
redundant today**: `sorted()` is stable and `_items` is already in insertion order, so dropping
`seq` from the key changes nothing. The test pins the property, not the mechanism.

**Defect 2, moderate — a new silent default on the currency sort, with a comment that
describes the opposite of what it does (`273f6ef`).** Three sites build a sort key for the
replay; the securities and merger ones log CRITICAL and re-raise, the new currency one did

```python
hist_key = (date.min, ())  # keep insertion order via seq
```

`(date.min, ())` sorts **ahead of every other item in the phase**, so an event whose place in
the chronology could not be determined would be applied first — before every trade, dividend
and fee of every asset and currency. In a currency ledger the first lot is the first consumed,
so that decides which EUR cost basis carries into the tax year. Same shape as #18's `320e20a`
and #22's `f5248a3`. Made fatal, consistent with its two siblings and with `pr/40`'s own
transfer handler.

The branch is **unreachable** as things stand — and so are the securities and merger ones —
because the event separation loop at the top of `run_main_calculations` already builds a sort
key for every event and drops the failures. That is an argument for consistency, not for
leaving a wrong fallback: #31 rewrites this whole block. **The reachable version of the same
defect is that separation loop**, and it is now an open item in section 8.

**Defect 3, low — `get_event_sort_key` computed twice per historical security event
(`273f6ef`).** Once inside `sorted()`, once again at `stream.add()`. Any warning the function
emits — a historical trade with no `ibkr_transaction_id` — would print twice. It does not on
this dataset (42 such warnings before and after, which is how the double call was ruled out as
an output change), but it is ~4,264 redundant calls on the 2025 history. Each event is keyed
once now and the key is carried into the stream; `7085652` arrives at the same shape.

**Defect 4, moderate — the determinism claim is false, and it is the third instance of the
same conflation (`1c01fbd`).** The docstring calls `seq` the tie-breaker "making replay fully
deterministic". `sort_key` is `get_event_sort_key`, whose tail is `event.event_id` =
`uuid.uuid4()`; `seq` stabilises only items whose keys are already *identical*. Measured on
the real 2025 history: 7,614 of 8,949 items collide (every trade is streamed twice under the
same key, once per ledger; all 420 RECONCILE items share `(0,)`), so `seq` is doing real work —
just not the work claimed. Order between *distinct* same-day events sharing a transaction id is
still redrawn every run. PRD 5.8 says the same thing and `89fdd80` repeats it; nothing in the
train fixes it. Docstring corrected and pointed at where the repair belongs.

**Defect 5, low — citation by section, and one the store already contradicts (`1c01fbd`).**
Sixth instance of the pattern. The MERGERS phase cited "§20 Abs. 4a EStG" by Absatz; the
controlling rule is **Abs. 4a Satz 1-2** (the new shares step into the tax position of the old
ones), which is precisely what licenses transferring lots with their acquisition date and cost
basis rather than closing and reopening them. `reference/tax-law/estg-20-kapitalvermoegen.md`
already carries it verbatim, so this is rooted — it just was not cited to the sentence. Worse,
the same docstring lists *"internal transfers, §43 Abs. 1 S. 5"* as a future stream member,
and that file says in terms that the §43/§43a Depotübertrag rules "are Kapitalertragsteuer
provisions addressed to German institutions and do not apply to a foreign broker; they cannot
be cited for the disposal question". Section 7 predicted that mis-citation for **#32**; it
actually lands here, as a forward-looking aside, one PR before the code that leans on it.
Dropped; the architectural point survives without it.

**Nits (`1c01fbd`, `273f6ef`):** `_replay_historical_merger` took an `asset_resolver` it never
used and still never uses at `pr/40` — dropped. `replay.py` imported `dataclasses.field` and
`typing.Any`, neither used. CLAUDE.md still described the engine as "three-pass historical
replay" and did not list `src/engine/replay.py` — refreshed; it stays stale through `pr/40`
otherwise. Left alone deliberately: the `Pass 2:` / `Pass 3:` log prefixes (kept verbatim so the
parity capture stays comparable), the function-level `from src.engine.replay import …` (#31
rewrites that block, so moving it buys a conflict for nothing), and
`tests/test_stock_merger_fifo.py`'s "three-pass SOY initialization" docstring — a pre-existing
test file, so a one-line follow-up for the owner rather than a unilateral edit.

**Description accuracy.** The PR body says *"Contains: code (src/engine/replay.py: …), tests"*.
The diff contains **no tests**. Every other factual claim in it checks out: the parity result
is right (and understated — it was measured with the pre-repair script that sorted lines, so
the reordering it produces was invisible then), the three log-wording lines are exactly three,
and the "one stream replaces three machines" description is accurate.

**Everything found in #24 is fixed in commits**, except the separation loop's silent drop,
which is pre-existing and now an open item.

### PR #25 (train 10) — data-gap channel — **ACCEPTED, both ends now tested**

Rebased clean from `a717f47`. 471 → 474 with the PR, 485 with ours; green on the clean-clone
protocol (`config_example.py`, no `cache/`) and with the real config. Real-data parity for
2025: **console IDENTICAL, PDF IDENTICAL**, log 14 lines against a same-tree control of 10,
every one of them the known `OPTION_CASH_SETTLEMENT` permutation and nothing else. The
commit's *"the dataset has no gaps, so no new output"* is **verified rather than taken**: the
2025 run produces zero `EOY MISMATCH` log lines, so the new report section never prints.

**The smallest PR since #17 and the only one whose description I could not fault.** *(#19 was
the other; #22 came close.)* `Legal basis: n/a (infrastructure)` is accurate — no
`reference/` file is touched and none needs to be, because nothing here can move a figure:
the only wired condition records an already-logged, already-counted EoY mismatch, and the
FAIL_FAST path has no call site at this commit. `Contains: code (…), tests` is accurate,
which #24's was not. The forward claim *"PR 14 plugs missing-NAV gaps into this channel with
FAIL_FAST"* checks out at `dc05960`.

**And the seam is genuinely consumed** — the #20 `RunContext` caveat does not apply, for the
third time running. `data_gaps.py` is created here and **never modified again** through
`pr/40`, but by then `_record_vp_nav_gaps` makes an unresolvable §18 InvStG year-start NAV
FAIL_FAST in a non-interactive run — i.e. the channel is what stops the engine declaring a
fund's deemed income as zero — while a missing *declared* VP is deliberately WARNING because
it only overstates the gain. That is a real severity policy doing real work, introduced four
PRs ahead of its first user.

**Defect 1, moderate → escalated by the owner into a behavioural fix (`7e3eada`, `1c4c981`).**
The module placed EoY quantity mismatches under WARNING, defined there as *"evidentiary
divergences that do not silently change the declared figures"*. An EoY quantity mismatch is
the signature of a disposal the engine did not process: calculated > reported means a sale is
missing and with it its realised gain, so income is understated by an amount that appears
nowhere in the output. That is the file's own FAIL_FAST criterion, verbatim.

Raised as an open question; the owner's ruling was that **SoY → EoY must always compute
cleanly given full-year data**, so the mismatch is now **fatal**. That surfaced a genuine
document conflict worth recording: **PRD.md 2.4 already required it** (*"must be identical"*,
*"must be flagged as a critical error"*, no licence to continue), while the engine logged
*"Processing will continue, but results may be inaccurate"* and
`tests/docs/spec_fifo.md` Group 3 had been written around the engine — five cases
(`EOY_M_001`–`004`, `EOY_SM_001`) specifying a surviving mismatch **with a defined
post-mismatch EOY state**. So the spec had been fitted to the implementation, and the PRD was
the thing being contradicted. The spec, the fixtures, `test_data_gaps.py` and the harness's
blanket `pytest.fail` were changed with the owner's approval; the five fixtures now expect the
abort and their EOY-state fields are documentation only.

Design points worth keeping: the check runs to completion over every asset and *then* raises
one `EOY_RECONCILIATION_FAILED` naming all of them (one run identifies the whole problem), and
the raise does **not** depend on the optional collector being supplied — an optional argument
must not decide whether the engine aborts. Calibrated: removing the raise fails 8 tests.

**The accepted cost:** 2022 now aborts. The owner chose no override flag. Note that the
justification first recorded here — "its history is incomplete, so its gain was wrong anyway"
— is **false**, and the owner is the one who caught it: the SoY quantity is authoritative, so
a prior-year gap cannot produce a current-year quantity mismatch at all. 2022's input is
complete and its correct EoY is zero, which makes the residual an engine defect and the abort
the right outcome for a different and better reason. See section 8.

**The currency (cash balance) check stays non-fatal, also the owner's call.** Its documented
causes are input-completeness problems — the cash-balance export's date range, or transaction
types missing from the Cash Transactions query — not a ledger disagreeing about a holding. It
is now recorded as a `CURRENCY_EOY_MISMATCH` WARNING gap so it reaches the console and the PDF
instead of only the log. Real 2024 has one (−0.51 USD); 2025 has none, which is why parity
holds.

**Defect 2, moderate — the report half of the feature is invisible to the suite, and so is
one of the two recording sites (`0893139`).** Mutation-probed with all 474 running:

| mutation | failures |
|---|---|
| drop the record at the "quantity differs" EoY branch | 1 |
| drop the record at the "asset absent from EoY report" branch | **0** |
| delete the report section that renders the gaps | **0** |

The blind recording branch is the sharper of the two — the engine holds a position the
broker's EoY export does not list at all — and the rendering block is the entire point of
the channel: a gap that reaches only the log is precisely the condition the module was
written to end. Deleting it outright leaves a green suite. This is the same shape as #24's
untested ordering contract, one layer up: the mechanism is fine, the instrument is missing.
Six assertions added in `tests/test_data_gap_channel_guards.py`, each calibrated against the
tree that should break it (all five mutations trip exactly the intended test and only it).
Two of them pin a promise nothing exercises yet — that `DataGapError` is catchable as
`ProcessingError`, and that `run_core_processing_pipeline`'s `except Exception` re-raises
rather than degrading a fail-fast gap into a warning with no report entry — because #29 is
what starts depending on both.

**Defect 3, moderate, pre-existing but fixed here because #25 is what makes it fixable
(`a2f3974`) — the PDF certifies an EoY reconciliation that never happened.** `main.py` hands
`PdfReportGenerator` a **hardcoded empty** `eoy_mismatch_details`, and
`_add_eoy_reconciliation` prints *"Alle berechneten Endbestände stimmen mit den gemeldeten
Endbeständen überein."* whenever that list is empty. Since it is always empty, **every PDF
ever produced by this engine carries the all-clear** — including runs where the engine has
just logged `CRITICAL EOY MISMATCH` and the console has just printed `ACHTUNG`. The dead
`and not eoy_mismatch_details_for_pdf` guard beside it logged the missing detail into the log,
the one place the user is not looking. This is the sharpest instance of the exact failure #25
exists to prevent — a plausible-looking incomplete declaration — in the artifact that leaves
the machine. The all-clear is now conditioned on the mismatch count, the recorded
`EOY_QTY_MISMATCH` gaps supply the per-asset detail, and where no detail is available the
report says so. Red-first: 3 of 5 new assertions fail on the pre-fix tree; the other two pin
behaviour that must not change (the all-clear on a genuinely clean run, and the untouched
structured-table path). 2025 parity is unaffected because that year takes the all-clear
branch. **`PdfReportGenerator` had no test of any kind before this**; it is instantiated only
from `main.py`.

**Defect 4, low — `DataGapError(RuntimeError)` sits outside the project's exception taxonomy
(`7e3eada`).** CLAUDE.md and `src/domain/exceptions.py` define `DataIntegrityError` for
parsing and `ProcessingError` for the engine; a third RuntimeError subclass means an
`except ProcessingError` handler cannot see the one exception the fail-fast policy exists to
raise. Now a `ProcessingError`, which is itself a `RuntimeError`, so nothing that caught the
original type stops catching it.

**Defect 5, low — the module claims a scope it does not have (`7e3eada`).** *"Every such
condition now flows through a collector"*: exactly one does. The three silent-fallback sites
already recorded as open items — the separation loop's dropped event, the historical currency
replay's DEBUG swallow, Pass 2's missing merger source — are untouched by it, and one of them
(the currency swallow) is precisely the "silent zero" class the module names in its own
rationale. Named them, so the file documents its actual reach.

**Nits (`7e3eada`, `47f2581`).** Dangling references: *"rework2-plan AR6"* and *"finding
F4/F6"* name documents this repo does not contain — `af95b72` was dropped when #16 was
absorbed. **Fifth instance** of the class after `e467cad`, `f2e5cc3`, `edda318`, and it
propagates: `dc05960` repeats *"resolves legal-review finding F4"* in `_record_vp_nav_gaps`,
so apply the same correction at #29. `GapSeverity` is imported into `calculation_engine.py`
and never used (and stays unused through `pr/40`); `Optional` is imported into
`data_gaps.py` and never used. The console's pre-existing EoY warning still said *"Siehe Log
für Details"* after the details had been moved into the report; it now points at the section
carrying them and falls back to the log line when no gaps were collected.

**Two observations recorded rather than changed.** Each EoY mismatch is now logged twice, by
the engine at ERROR and by the collector at WARNING — defensible (engine validation vs.
channel record) but it doubles the line count for anyone grepping. And
`tests/test_data_gaps.py`'s *"recorded before raising (visible post-mortem)"* is not true in
production: the collector is a local of `run_core_processing_pipeline` and its gaps reach
`ProcessingOutput` only on the success path, so a FAIL_FAST gap is visible in the CRITICAL
log and nowhere else. Fsaupe's own new test file left untouched.

**Everything found in #25 is fixed in commits**, except the EoY-mismatch severity question,
which is the owner's call and is now an open item.

## 4. Cross-cutting pattern

Across eight PRs: **the code and tests are consistently sound; the legal and factual prose is
unreliable.** Every substantive mechanism held up under testing. 12 citation/claim errors,
all corrected here. #19 remains the only description with nothing wrong in it — #20's
central claim ("the only place user config is read") was false, and #21's
"parent-parity: IDENTICAL" cannot hold for any VZ ≤ 2024 run — so this is a tendency
rather than a law, but it has now held seven times out of eight. #22 is the near-miss: every
factual claim in its description checks out empirically (red-first count, parity, "no
leap-year anniversary sale in the dataset"), and only the *citation* overreaches.

A refinement #21 adds: the failure is **not** in the legal reasoning, which was right and
rooted. It is in *provenance* — where a number came from and whether the cited document
actually says it. #21's two worst defects are a value silently inherited from the wrong
statute (§203 BewG) and a claim about what the tests check.

**#22 sharpens it into a third form: citation by section instead of by sentence.** "§108 AO"
is true of the anniversary rule and also drags in §108 Abs. 3 AO, which the engine does not
implement and which is a genuinely open question capable of moving a figure. The Validation
Protocol's item 3 — cite paragraph *and* sentence — is not pedantry: **the unstated Absatz is
where the unimplemented rule hides.** Worth applying to every remaining citation in the train,
and it is exactly the same failure as #21's bare "§20 Abs. 6 Satz 5", which means opposite
things before and after 02.12.2024.

**#25 is the first clean break in that pattern since #19, and it is worth being precise about
why.** Every factual claim in its description holds under test, and — unlike #22 — there is
no citation to overreach, because there is nothing to cite: the PR is pure infrastructure,
`Legal basis: n/a` is the truthful answer, and it gives it. The prose that *is* wrong in #25
is not a citation but a **rationale**: WARNING justified by "does not silently change the
declared figures" for the one condition where it does. So the pattern refines once more —
where a PR has no legal claim to get wrong, the same unreliability reappears one level down,
in the reason given for a policy rather than the source given for a rule. Two for nine on
descriptions; the code and tests remain sound in all nine.

Practical consequence: **review the diff, not the description.** Verify claims empirically
rather than reading them.

**Second pattern, now four for four: verification tooling that cannot see what it claims
to check.** #33 found the test suite silently reading the developer's real `cache/`; #19
shipped a real-data parity gate with the same hole, which would have certified every later
PR's "output-neutral" claim without being able to observe a classification change; #20's
leak tripwire passes green on the very leak shape it was written for, and its
`from_config` tests cover a code path production never executes; #21's registry↔reference
consistency test compared two hand-kept copies of the same numbers, both of which contained
the wrong-statute rows it should have caught. All were green. When a PR adds a checking
mechanism, test the *mechanism* against a deliberately broken tree — a green result from an
instrument nobody calibrated is worth nothing.

This pattern is now reliable enough to be a checklist item rather than an observation:
**for every new guard, write the tree that should trip it and confirm it does.**

**#23 is the first PR to break that streak** — all four mutations of `ledger_views` trip its
new test, unmodified. Keep running the calibration, but the pattern is now four for five,
not four for four.

**#24 is the limiting case of the same pattern: a documented contract with no instrument at
all.** It ships an explicit "ordering contract (the law of the stream)" and zero tests, and
the existing suite can observe almost none of it — reversing every historical currency event
leaves all 466 green. So the checklist item needs a second half: *when a PR documents a
contract, also write the tree that violates it.* An untested contract is not weaker evidence
than an uncalibrated guard; it is the same failure with the instrument omitted rather than
miscalibrated.

**Third pattern, new with #23: the suite's blind spots are not where the diff is.** Probing
each converted lookup site individually found five of fourteen that the whole 463-test suite
cannot observe. Two of those five are the FX/currency paths and one is the option cash
settlement — the same corner as the known same-date nondeterminism. A green suite on a
mechanical, repetitive refactor says much less than it appears to: the sites the tests do
reach fail loudly (2–105 failures), so a passing run mostly proves the *covered* sites were
converted, not the uncovered ones. Worth doing on every remaining mechanical refactor in the
train, since #31/#32 convert these exact call sites again for real.

**#25 is the third consecutive PR where the probe pays, and it moves the target.** #23 and #24
were probed at *lookup sites* and *ordering*; #25's blind spots are a **recording site** and
the **rendering block** — the feature's own two ends. Deleting either leaves 474 green. The
generalisation: probe the ends of a new channel, not just its middle. A collector that
records and a report that prints are each a place where the whole feature can vanish without
a single test noticing.

**#24 confirms it and locates the blind spot precisely: the historical FX replay.** Reversing
the chronological order of every historical currency event leaves all 466 tests green, while
the equivalent mutation on securities fails one. Three of #23's five blind lookup sites were
FX paths; this is the same hole seen from the other side. Anything touching the currency
replay should be probed by reversal, not by running the suite.

And the masking mechanism found underneath it generalises: **Pass 3's SoY reconciliation can
paper over an engine failure with a plausible number.** It rebuilds whatever the replay did
not, from the Positions snapshot, so any bug that loses lots is invisible in every figure
except the acquisition date. Any future test asserting only quantity/basis/proceeds/gain on
a scenario with an SoY snapshot is weaker than it looks.

---

## 5. Verified migration path for the remaining 16 PRs

The first eleven commits of every branch in the train are exactly the ones absorbed here
(`af95b72`, `7f6fca0`, `35d5873`, `1d7728b`, `361b11a`, `960d1ab`, `4eeeffb`, `1382bb9`,
`ac1e9a1`, `a717f47`, `345bd49`), so one command migrates any of them:

```
git rebase --onto <new-main> 345bd49 <branch>   # a717f47 before #25 was absorbed
```

Remaining PR heads, for orientation (train position = PR − 15; several PRs are docs/tests
only and share code commits with their neighbours):

| #25 `345bd49` data-gap channel | #26 `169ccc5` legal-position register | #27 `91c9297` replace false-confidence tests | #28 `febf459` sum multi-account balances |
|---|---|---|---|
| #29 `2dbb5dc` V-1 declared Vorabpauschale | #30 `3220bd3` itemize Sonstige Kapitalerträge | #31 `7085652` per-Depot FIFO | #32 `b788c5c` final parity gate |
| ~~#33~~ absorbed | #34 `0b27054` branch decision | #35 `391782b` Einlagenrückgewähr | #36 `dca13f3` SoY cost-divergence tripwire |
| #37 `0163bcd` historical option replay | #38 `8cfd6b3` forward-split tests | #39 `f16aa40` Nr. 11 / Nr. 3a split | #40 `8988198` PRD + coverage sync |

Simulated against this branch's HEAD:

| PR | Result |
|----|--------|
| ~~#20~~ | absorbed (`16cd0c8`) |
| ~~#21~~ | absorbed (`88a91e9`); its 4 conflict hunks resolved, `KNOWN-WRONG` markers retired |
| ~~#22~~ | absorbed (`e0026da`); rebased clean, no conflicts |
| ~~#23~~ | absorbed (`3b8012c`); rebased clean, no conflicts |
| ~~#24~~ | absorbed (`a1bd93c`); rebased clean, no conflicts |
| ~~#25~~ | absorbed (`68fd82d`); rebased clean, no conflicts |
| #26–#40 | rebase from `345bd49` |

Note for whoever lands #21 onward: our `a7f7032` removed `src.config` from `src/cli.py` and
moved the default-PDF-filename derivation into `src/main.py`. No commit in #21–#40 touches
`src/cli.py` — verified by scanning every `pr/*` ref — so this conflicts with nothing, but a
later PR that reintroduces a config read there will now fail
`test_cli_module_does_not_read_user_config`, which is the intended behaviour.

Only two commits in the whole train touched `tests/fixtures/loss_offsetting_data.py`:
`7f6fca0` (#16) and `4eeeffb` (#21), both absorbed. The conflict was our `KNOWN-WRONG`
markers meeting the fix they pointed at:

```
<<<<<<< HEAD
    # KNOWN-WRONG (VALIDATION_REPORT.md finding #1, HIGH): … Correct value: -30000.00.
    conceptual_net_derivatives_capped=D("-20000.00"),  # Capped!
=======
    conceptual_net_derivatives_capped=D("-30000.00"),  # cap repealed (JStG 2024)
>>>>>>> 4eeeffb
```

**#21's value equalled the value our marker predicted** — two independent derivations
agreeing. Resolved as "take theirs, drop the marker", ×4; all four markers are retired and
VALIDATION_REPORT finding #1 is marked resolved there.

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
- ~~**#16 must not land without #21**~~ — satisfied; #21 is absorbed and the cap is False
  for every year.
- **#21 must not be followed by a pre-2024 filing until #29 lands.** #21 widens the
  Basiszins table so the engine computes a Vorabpauschale for 2018-2026, but the engine
  still books the VP for calendar X in VZ X, where §18 Abs. 3 InvStG puts it in X+1. #29
  fixes the year mapping and *requires* the widened table (it looks up
  `basiszins(tax_year−1)`), so the ordering is right — but between the two, a VZ 2018-2023
  run produces a wrong-year VP where it previously produced none. VZ 2023 flips from
  right to wrong. No exposure with the current data (VP needs an SoY snapshot; only 2025
  has one).
- **Our #22 fixes conflict with nothing.** Verified by scanning every `pr/*` ref: no commit in
  #23–#40 touches `src/tax_law/holding_period.py` or
  `reference/tax-law/estg-23-private-veraeusserung.md`, and none of the seven later commits
  that edit `src/engine/fifo_manager.py` touches a `within_speculation_period` /
  `PRIVATE_SALE_ASSET` / `SECTION_23` line. `dc05960` (#29) does edit `src/domain/results.py`,
  but its hunk is the `RealizedGainLoss` field block, ending at the `def __post_init__` line;
  our change is inside that method's §23 block, several lines below its context.
- **Our #23 fixes conflict with nothing.** Verified by scanning every `pr/*` ref: no commit
  in #24–#40 touches `src/engine/ledger_views.py`, `src/utils/account_utils.py` or
  `tests/test_ledger_views.py`, and the only commit touching
  `tests/test_stock_merger_fifo.py` is `f90c319` (#33, already absorbed). `7085652` (#31)
  edits `currency_conversion_processor.py` only at lines 85 and 100, not the signature our
  `edda318` re-annotated.
- **#31 (`7085652`) repeats #23's mis-citation verbatim** — *"§20 Abs. 4 S. 7 EStG applies
  FIFO je Depot"* in its commit message. Apply the same correction (Rz. 97 S. 2) when it is
  reached, and check the reference's "known deviation" note again: #31 is the commit that
  actually ends the deviation, so that paragraph must be rewritten, not merely updated.
  Two things in its description to verify rather than accept: *"no per-account row -> SoY 0,
  **silently**"* is exactly the shape of the silent-default defects fixed in #18 and #22, and
  it claims to remove the orchestrator's merged-FX limitation warning.
- **Our #24 fixes: one expected conflict, and it is a good one.** `7085652` (#31) rewrites the
  securities replay loop wholesale — it drops `sort_key_func`, keys each event once inside the
  loop and carries the key into `stream.add`, i.e. it independently arrives at our `273f6ef`.
  Resolution when #31 is reached: **take theirs**, then re-check that the currency branch three
  hundred lines below still raises rather than falling back — #31 does *not* touch it, and the
  `(date.min, ())` fallback otherwise survives to `pr/40` unchanged. Everything else of ours is
  conflict-free: no commit in #25–#40 touches `src/engine/replay.py` (created at #24, never
  modified again) or adds any test file matching `replay`/`stream`, and
  `_replay_historical_merger` is untouched after #24, so dropping its unused `asset_resolver`
  collides with nothing.
- **Our #25 fixes: one expected conflict, trivial.** `169ccc5` (#26) inserts its
  legal-position render block immediately above the data-gap section in
  `console_reporter.py`, and its hunk carries the *"AR6 data-gap channel"* comment our
  `7e3eada` reworded as context. Resolution: keep ours, take their block — and drop the
  *"AR7"* marker from it, same dangling-reference class. Everything else of ours is
  conflict-free, verified by scanning every `pr/*` ref: `src/processing/data_gaps.py` is
  created at #25 and never modified again; no later commit touches
  `PdfReportGenerator.__init__` or `_add_eoy_reconciliation` (`dc05960` hits line 319,
  `3220bd3` lines 994/1133/1158, `89fdd80` none); the two later `src/main.py` hunks are both
  at lines 96–98, not the PDF block; and no later commit modifies
  `calculation_engine.py`'s import of `GapSeverity`.
- **`dc05960` (#29) repeats #25's dangling reference** — *"resolves legal-review finding F4"*
  in `_record_vp_nav_gaps`, naming a document dropped with `af95b72`. Apply the same
  correction when #29 is reached. Also verify there that the VP severity split is what it
  claims: FAIL_FAST non-interactive, WARNING interactive for a missing year-start NAV, and
  WARNING always for a missing *declared* VP (which only overstates the gain).
- **`0163bcd` (#37) and `89fdd80` both depend on #24's chronological interleave for a tax
  figure** — the option-replay fix needs a historical exercise to run before its stock leg, and
  the transfer handler needs bought-transferred-sold reconstruction. Verify both against
  `tests/test_replay_stream.py` rather than against the suite at large, which cannot see
  ordering.
- **Leave `reference/investment-tax-law/invstg-18-vorabpauschale.md` to #29.** It rewrites
  that file with verbatim §18 Abs. 3 and the Zuflussprinzip mapping, and also flags that the
  store's current "Z55" mapping for the §19 disposal deduction is wrong (Z55 =
  bestandsgeschützte Alt-Anteile). Our Basiszins work deliberately touched only
  `reference/bmf-guidance/basiszins-vorabpauschale.md`, which no later PR edits.

## 7. Knowledge-store scan of the unreviewed PRs

8 of 25 touch `reference/`: #18, ~~#21~~, ~~#22~~, #28, #29, #32, #35, #40. (#23 touches none
but is justified by one — see its verdict; #24 and #25 touch none and need none, #25 because
it genuinely has no legal surface.) Quality improves sharply
after #18 — #22 (§108 AO i.V.m. §§187/188 BGB anniversary arithmetic incl. leap year), #29
(§18 Abs. 2 S. 2 partial-year + §18 Abs. 3 verbatim deemed-inflow) and #35 (Einlagenrückgewähr,
explicitly separating settled law from open questions) are the strongest legal work in the train.

Two things to scrutinise when reached:
- **The Basiszins provenance lesson generalises.** #21's table was legally reasoned but two
  rows came from the wrong statute, undetected because three copies of the numbers agreed
  with each other. For any later PR that ships a rate table, check where each row came from,
  not just that the copies match.
- **§20 Abs. 4 Satz 7** is cited by #32 as "(FIFO per Depot)" but never quoted. Verified Tier 1:
  Satz 7 *is* the FIFO fiction, but it is conditioned on *Sammelverwahrung* per §5 DepotG and
  does not literally say "per Depot". That is the standard interpretation presented as statute;
  it needs Tier 2 backing.
- **#32** claims non-EUR cash transfers are tax-neutral citing "§43 Abs. 1 S. 5 /
  Fußstapfentheorie". §43 is Kapitalertragsteuer (withholding), not the disposal question.
  Conclusion likely right, citation likely doing work it can't do.

---

## 8. Open items NOT in the train

- **§108 Abs. 3 AO and the §23 Jahresfrist — an open legal question the engine has to answer
  either way (found in #22).** If the weekend/holiday extension applies, an anniversary falling
  on a Saturday or Sunday runs to the following Monday and a Monday disposal is still taxable;
  if it does not, that disposal is exempt. No Tier 1/2 source resolves it; the §23-specific
  authority (FG Köln 1997) and the general one (BFH IX R 68/98, 2003) point opposite ways.
  The engine implements no extension. Documented in
  `reference/tax-law/estg-23-private-veraeusserung.md` and in the coverage matrix's new
  *Open Legal Questions* section. No exposure in the current data — no disposal falls in such a
  window — but the maintainer holds and actively trades four `PRIVATE_SALE_ASSET` instruments,
  so it can arise in any future year. Implementing it would additionally require deciding which
  Land's `gesetzlicher Feiertag` calendar governs.
- **§23 Abs. 1 S. 1 Nr. 3 (short sales) is mis-handled, and Nr. 2 S. 4 is not handled.**
  A short position in "andere Wirtschaftsgüter" is a private Veräußerungsgeschäft with no
  holding period; `consume_short_lots_for_cover` applies the Nr. 2 Jahresfrist to it, so a
  short held over a year is reported exempt where Nr. 3 taxes it. Nr. 2 S. 4 extends the period
  to ten years for an asset that produced income. Both documented as unimplemented in
  `estg-23-private-veraeusserung.md`; neither is reachable in the current data.

- **A missing merger SOURCE ledger is skipped silently, and Pass 3 hides it (found in #23).**
  In `run_main_calculations` Pass 2, a missing **target** ledger raises but a missing
  **source** ledger only logs a warning and `continue`s. The un-transferred lots are then
  rebuilt by Pass 3's SoY reconciliation as a fallback lot dated `f"{tax_year-1}-12-31"` with
  the cost basis read from the Positions file — which for a merged holding is the correct
  basis, so quantity, cost basis, proceeds and gain all come out right and only the
  acquisition date is wrong. Same silent-default shape as #18's `320e20a` and #22's
  `f5248a3`, but pre-existing and outside #23's diff, so by the owner's decision only test
  coverage was added (`0ad410d`), not a fail-fast. Does not fire on the real 2025 data (the
  one historical merger there replays successfully). Harmless for STOCK; for a
  `PRIVATE_SALE_ASSET` it would flip the § 23 Jahresfrist. A fix should make source-None
  raise `ProcessingError`, consistent with the target branch two lines below it.
- **An event the engine cannot sort is dropped from the entire calculation, silently (found in
  #24).** `run_main_calculations`'s event separation loop calls `get_event_sort_key` on every
  event and, on `ValueError` — unparseable date, or an `asset_internal_id` the resolver does not
  know — logs `logger.error` and `continue`s. The event never reaches `historical_events_by_asset`,
  `historical_currency_events`, `historical_merger_events` or `current_year_events`. A dropped
  trade is a missing FIFO lot or a missing disposal; a dropped cash flow is missing income. It is
  the reachable version of the defect fixed inside #24's diff, the same shape as #18's `320e20a`
  and #22's `f5248a3`, and it is why the three `except ValueError` branches in the replay build
  are all dead code. Pre-existing and outside #24's diff, so not fixed — the fix is to raise
  `ProcessingError`. Note it also makes those three branches genuinely unreachable, so any future
  test of them has to bypass the public path.
- ~~**Should an EoY quantity mismatch be FAIL_FAST?**~~ **Resolved by the owner during the #25
  review: yes, fatal, no override** (`1c4c981`). Consequence: tax year **2022 aborts** — and
  see the next item, because the reason is not what this document previously said. The
  reporting paths for a non-zero mismatch count (console `ACHTUNG` line, PDF section) are now
  backstops that production can no longer reach. They are kept and tested deliberately — the
  sentence the PDF branch replaces was wrong for the whole history of that file, and nothing
  should be able to restore it through another path.
- **`validate_ledgers.py` still reports rather than refuses.** It is a separate script with its
  own SoY/EoY comparison and was not touched; it remains the right tool for surveying which
  years reconcile, now that `src.main` refuses the ones that do not. Worth confirming its
  verdicts still agree with the engine's once earlier years' snapshots are re-downloaded.
- **The PDF's structured EoY mismatch table is still unfed.** `a2f3974` stops the report
  claiming a reconciliation it never performed and renders the recorded gaps as text, but the
  five-column table (calculated / reported / difference) remains unreachable from production,
  because `run_main_calculations` returns a count and not rows. Feeding it means giving
  `DataGap` a structured payload alongside its human-readable `detail`. Worth doing if any
  later PR needs machine-readable gaps; not needed to remove the false statement.
- **Non-EoY gaps never reach the PDF.** The console renders every collected gap; the PDF now
  renders only `EOY_QTY_MISMATCH`. From #29 an *interactive* run can finish with a
  `VP_NAV_MISSING` WARNING that appears in the console and not in the PDF. Decide at #29
  whether the PDF needs a general gap section.
- **The historical currency replay swallows every exception at DEBUG level.**
  `_apply_historical_currency_event` wraps its whole body in
  `except Exception as e: logger.debug(f"…skipped event {event.event_id}: {e}")`. A rate lookup
  failure, a bad Decimal, a missing field — all silently skip the event's currency impact at a
  log level the default configuration does not print, leaving the lot state short and the FX cost
  basis wrong. Pre-existing (#24 only extracted it verbatim as the per-event unit); recorded here
  because #24 is what made it a named function worth fixing on its own.
- **Four ledger-lookup sites remain unobservable to the test suite (found in #23).**
  `calculation_engine.py:645` (currency EoY validation), `corporate_action_processor.py:106`
  (MergerCash currency ledger), `trade_processor.py:450` and `option_processor.py:460`. Each
  can be broken outright with all 466 tests still green; site 277 is now covered by
  `0ad410d`. Three of the four are FX/currency paths. #31 rewrites all of them for real
  per-Depot keys, so coverage here is worth adding before that lands rather than after.
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
- **Same-date event ordering is nondeterministic — spec-level, not fixed anywhere in the
  train (found 2026-08-02).** Two runs of identical code over the real 2025 data permute 12
  log lines: same-date `OPTION_CASH_SETTLEMENT` events are processed in a different order
  each run. Tax figures were unaffected — console and PDF compared identical — but the
  ordering is unstable.

  Root cause, traced end to end:
  1. `src/utils/sorting_utils.py::get_event_sort_key` ends every secondary key tuple with
     `event.event_id`, which is `uuid.uuid4()` — regenerated on every run.
  2. The element before it is `event.ibkr_transaction_id or ""`, so the random UUID decides
     the order whenever same-date events share an empty transaction ID.
  3. `OptionCashSettlementEvent` is constructed without `ibkr_transaction_id` at all, and
     cannot have one: `OPTIONS_EAE_COLUMNS` has a `Transaction Type` column but **no
     `TransactionID` column**, and `RawOptionsEAERecord` accordingly has no such field.
     So the precondition fails for every cash-settlement event, by construction.

  **The PRD mandates the defect**, which is why the code looks correct and reviews clean.
  PRD.md lines 598–619 state that `event_id` is "always the last element in this tuple to
  guarantee uniqueness and deterministic order" and that its inclusion "guarantees that the
  overall sorting order is strictly deterministic, as each `FinancialEvent` object has a
  unique `event_id`". That conflates **uniqueness** with **determinism**: a random UUID makes
  the key unique *within* a run — so the sort is total and never fails — while making the
  order differ *between* runs. The function's own docstring inherits the false claim
  ("Generates a deterministic sort key tuple ... as per PRD 5.8").

  Train scan: **nothing in #20–#40 fixes it.** The only train commit touching
  `sorting_utils.py` is `89fdd80` (tax-neutral internal transfers), and it *propagates the
  pattern* — it adds an `InternalTransferEvent` branch commented "the `event_id` tail keeps
  the key unique", the same conflation. That commit's own events do pass
  `ibkr_transaction_id=rt.transaction_id`, so it is not itself broken as long as IBKR
  populates that field; but the spec it is following is.

  Why it matters for what is coming: once #31/#32 partition lots per account, the order in
  which same-day disposals consume lots decides *which lot* each one takes. Today the
  instability is confined to an event type that does not consume FIFO lots competitively.
  It should be fixed before per-Depot FIFO lands, and the fix belongs in the PRD first.

  **#24 restates the false claim a third time** (`replay.py`: `seq` as the tie-breaker "making
  replay fully deterministic"), corrected in `1c01fbd`. It also quantifies the collision rate
  that makes `seq` worth having at all: 7,614 of 8,949 stream items on the real 2025 history
  share a `(phase, sort_key)`.

  Cheapest correct fix: make `event_id` itself deterministic — `uuid.uuid5(NAMESPACE, key)`
  over the event's identifying content — which repairs every sort key at once without
  touching `get_event_sort_key` or any of the per-type tuples. The alternative is to replace
  the tail with a stable input-derived key (source file + row index) and keep `event_id` out
  of ordering entirely.

  Instance details (conids, dates) in `private/real-data-observations.md`.
- **No CI.** No `.github/workflows`. Every "green" claim in the train is unverified by
  anything observable; each review currently costs a manual baseline-control run.
- `VALIDATION_REPORT.md` findings 2–6 remain open. Finding 1 is **resolved** by #21 plus
  `a41dbb9`, and marked so in that file.
- **Vorabpauschale is booked one assessment year too early** (§18 Abs. 3 InvStG). Pre-existing;
  #21 widens its reach; **#29 fixes it**. Detail in the #21 verdict and section 6.
- **2022's EoY failure is an engine defect, not a data limitation — the "pre-2021 data floor"
  explanation carried in this document was wrong, and was checked out of the data on
  2026-08-03.** The owner's challenge is what exposed it: 2022 has a SoY snapshot, and
  `reconcile_with_soy_position` pins the ledger to the reported SoY quantity in *every* branch
  (reconstruction, fallback, reported-zero), using the historical replay only for cost basis
  and acquisition dates. So no prior-year history can move a current-year EoY **quantity**,
  and the data-floor story was never capable of being true. Arithmetic on the real files
  confirms the input is complete: prior-year net gives the SoY, the year's pre-split trades and
  the 20-for-1 `FS` action give the post-split position (the CA row's own `Quantity` field
  independently confirms it), and the year's final sell closes it to exactly the zero the
  broker reports. Figures in `private/real-data-observations.md`.
  `tests/test_forward_split_soy_reconciliation.py` reduces the case to its shape and **passes**,
  so it is not the plain split-across-SoY pattern; the residual implies a pre-split ledger
  larger than it should be, pointing at a sell that under-consumed or a buy counted twice.
  Pinning it needs the 2022 Positions snapshots, lost in the `data_import/` rebuild. It is also
  unconfirmed whether the recorded figure came from the engine or from `validate_ledgers.py`,
  which reconciles independently. **As of `1c4c981` this aborts the 2022 run**, which is the
  correct outcome for a defect of this kind.
- **Lesson, and it is the same one this review keeps recording against the train.** The
  data-floor claim was a plausible rationale stated without checking — the exact provenance
  failure catalogued in section 4, committed here by the reviewer rather than by Fsaupe, and
  it had already reached `README.md`, `PRD.md`, `spec_fifo.md` and the user-facing German
  error message before the owner questioned it. Corrected in all five places. Instance in `private/real-data-observations.md`.

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

Current state on this branch: 58 commits — 12 authored by `Fsaupe <florian.saupe@gmx.de>`,
46 by the repo owner. (Recount with
`git log --format='%an' ebad4e7..HEAD | sort | uniq -c`.) Committer is the repo owner throughout (normal for
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
| #20 | `960d1ab` | `16cd0c8` | Fsaupe |
| #21 | `4eeeffb` | `88a91e9` | Fsaupe |
| #22 | `1382bb9` | `e0026da` | Fsaupe |
| #23 | `ac1e9a1` | `3b8012c` | Fsaupe |
| #24 | `a717f47` | `a1bd93c` | Fsaupe |
| #25 | `345bd49` | `68fd82d` | Fsaupe |

All original SHAs remain resolvable in the local object store via the fetched `pr/*` refs
(`git fetch origin 'refs/pull/*/head:refs/remotes/pr/*'`).

### When landing on GitHub later

1. **Do not squash-merge.** Squashing collapses all 25 commits to a single author and
   destroys Fsaupe's credit. Use a merge commit, or fast-forward.
2. #16/#17/#18/#33 will **not** auto-close, because these are cherry-picks, not the branch
   heads. Close each manually with a comment naming the landed SHA and the deltas applied
   (`2383b8a` for #33; `f5e8c0c` for #16/#17; `547df96`+`76cb8df`+`320e20a` for #18;
   `96d4312`+`a40adce` for #19; `a7f7032`+`fa05198`+`e467cad` for #20;
   `df8dd6b`+`7bfc8fa`+`a6ff53d`+`a41dbb9`+`a96a5fd` for #21;
   `24b3c1f`+`f2e5cc3`+`f5248a3` for #22;
   `05b839b`+`d6537aa`+`3d3873b`+`0ad410d`+`edda318` for #23;
   `a35a881`+`273f6ef`+`1c01fbd` for #24;
   `7e3eada`+`0893139`+`a2f3974`+`47f2581`+`1c4c981` for #25) so the
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

# PR Train Review — state, rationale, and how to resume

**Branch:** `hermetic-tests-first` (local only, never pushed)
**Base:** `main` @ `ebad4e7`
**Status as of 2026-08-02:** 7 of 25 PRs reviewed and accepted; 18 not yet reviewed.
**Next up:** #22 (train 7). It inherited #21's conflict in
`tests/fixtures/loss_offsetting_data.py`, which is now resolved here, so rebase from
`4eeeffb` onward; see section 5.
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

**Verification at HEAD:** 440 tests pass on a simulated clean clone
(`config_example.py`, no `cache/`) and with the real config. Real-data output is
**byte-identical to `ebad4e7`** across tax years 2022–2025 — console report,
`validate_ledgers.py`, and PDF text SHA-256.

> That real-data run was performed at `8ee553e` (through #18). It was **not** re-run for
> #19, because `data_import/` no longer exists on this machine — see section 8. It still
> holds by construction: #19 and the four commits on top of it change `scripts/`, `tests/`,
> `reference/`, `docs/` and `.gitignore` only, and touch no file under `src/`.
>
> From #20 on, parity is run for **tax year 2025 only** — the one year whose Positions and
> Cash_Balance snapshots survived the `data_import/` rebuild. At `a96a5fd` (#21 + our five
> fixes) versus `f004746`: **PDF IDENTICAL**, console 3 lines (our reworded repeal note),
> log 8 lines matching the same-tree control in count and shape.

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
(`7bfc8fa`, `a6ff53d`).** #21 widens the table from {2024, 2025} to 2016-2026 and makes the
engine compute a Vorabpauschale for every listed year. That raises the evidentiary bar on
rows that had been inert, and the two oldest do not survive it: **1.10% (2016) and 0.59%
(2017) are the Basiszins for the vereinfachtes Ertragswertverfahren nach §203 Abs. 2 BewG**
(BMF 04.01.2016, IV C 7 - S 3102/07/10001; the 2017 value from OFD-Verfuegungen) — a
different statute. The rows even carried the BewG reference dates, 04.01.2016 and
02.01.2017, which is how it surfaced. The Vorabpauschale did not exist then: InvStG 2018
provisions *"sind ab dem 1. Januar 2018 anzuwenden"* (**§56 Abs. 1 S. 1 InvStG**), the first
Basiszins notice is BMF 04.01.2018, the first Vorabpauschale is the one for calendar 2018.
Left in, a run for VZ 2016/2017 invents deemed income. Both rows removed; each surviving
row now names its BMF-Schreiben, and the 2018-2023 sourcing gap (the BMF site hosts only
the last two PDFs) is recorded in the file rather than papered over.

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

**Nit, not fixed:** `tests/test_config_example_completeness.py` cites "B4/B5g", identifiers
from the dropped `rework2-plan.md` — the same dangling-reference class as `e467cad`, in a
test file, so left for the owner to wave through.

## 4. Cross-cutting pattern

Across seven PRs: **the code and tests are consistently sound; the legal and factual prose is
unreliable.** Every substantive mechanism held up under testing. 12 citation/claim errors,
all corrected here. #19 remains the only description with nothing wrong in it — #20's
central claim ("the only place user config is read") was false, and #21's
"parent-parity: IDENTICAL" cannot hold for any VZ ≤ 2024 run — so this is a tendency
rather than a law, but it has now held six times out of seven.

A refinement #21 adds: the failure is **not** in the legal reasoning, which was right and
rooted. It is in *provenance* — where a number came from and whether the cited document
actually says it. #21's two worst defects are a value silently inherited from the wrong
statute (§203 BewG) and a claim about what the tests check.

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

---

## 5. Verified migration path for the remaining 19 PRs

The first seven commits of every branch in the train are exactly the ones absorbed here
(`af95b72`, `7f6fca0`, `35d5873`, `1d7728b`, `361b11a`, `960d1ab`, `4eeeffb`), so one
command migrates any of them:

```
git rebase --onto <new-main> 4eeeffb <branch>   # 960d1ab before #21 was absorbed
```

Simulated against this branch's HEAD:

| PR | Result |
|----|--------|
| ~~#20~~ | absorbed (`16cd0c8`) |
| ~~#21~~ | absorbed (`88a91e9`); its 4 conflict hunks resolved, `KNOWN-WRONG` markers retired |
| #22–#40 | rebase from `4eeeffb`; #21's conflict no longer applies |

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
- **Leave `reference/investment-tax-law/invstg-18-vorabpauschale.md` to #29.** It rewrites
  that file with verbatim §18 Abs. 3 and the Zuflussprinzip mapping, and also flags that the
  store's current "Z55" mapping for the §19 disposal deduction is wrong (Z55 =
  bestandsgeschützte Alt-Anteile). Our Basiszins work deliberately touched only
  `reference/bmf-guidance/basiszins-vorabpauschale.md`, which no later PR edits.

## 7. Knowledge-store scan of the unreviewed PRs

8 of 25 touch `reference/`: #18, ~~#21~~, #22, #28, #29, #32, #35, #40. Quality improves sharply
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

Current state on this branch: 8 commits authored by `Fsaupe <florian.saupe@gmx.de>`,
23 authored by the repo owner. Committer is the repo owner throughout (normal for
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

All original SHAs remain resolvable in the local object store via the fetched `pr/*` refs
(`git fetch origin 'refs/pull/*/head:refs/remotes/pr/*'`).

### When landing on GitHub later

1. **Do not squash-merge.** Squashing collapses all 25 commits to a single author and
   destroys Fsaupe's credit. Use a merge commit, or fast-forward.
2. #16/#17/#18/#33 will **not** auto-close, because these are cherry-picks, not the branch
   heads. Close each manually with a comment naming the landed SHA and the deltas applied
   (`2383b8a` for #33; `f5e8c0c` for #16/#17; `547df96`+`76cb8df`+`320e20a` for #18;
   `96d4312`+`a40adce` for #19; `a7f7032`+`fa05198`+`e467cad` for #20;
   `df8dd6b`+`7bfc8fa`+`a6ff53d`+`a41dbb9`+`a96a5fd` for #21) so the
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

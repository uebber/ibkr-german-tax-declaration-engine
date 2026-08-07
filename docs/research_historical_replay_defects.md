# Historical replay: defects, target design, fix plan

Investigation prompted by issue #56 (historical mergers replay after every trade in the window).
The merger phase turned out to be one of four defects in the pre-tax-year reconstruction, and not
the one with the widest reach.

**Status:** **all four changes are implemented.** Measured outcomes are recorded in each
change's section below.

Change 4 was pulled forward into change 2 rather than scheduled: checkpointing turned defect D
from "structural, unmeasured" into nine blocked ledgers on the first real run, and the fix had to
land with it.

## How everything here was measured

Unless a claim says otherwise, it comes from one of three things:

1. **Full engine runs** for VZ 2023, 2024 and 2025 —
   `uv run python -m src.main --tax-year Y --no-interactive --count-objects`, logs captured.
   2023 and 2025 exit 0; 2024 exits 1 on a fail-fast Vorabpauschale gap. VZ 2022 and earlier were
   not run: the validation floor in `CLAUDE.md` forbids treating them as results.
2. **Direct reads of `data_import/`** — every trade, corporate action and position row touching an
   affected ISIN, replayed by hand.
3. **Reads of the code**, cited to `file:line`.

Claims derived only from reading code, with no measured instance behind them, are marked
**(structural, unmeasured)**.

Share quantities and ISINs appear below. Per the public-repository rule in `CLAUDE.md` those
identify instruments, not wealth, and are deliberately out of scrubbing scope. No monetary amount
appears anywhere in this document.

## The population

Seven distinct assets trip `_historical_simulation_inconsistent` (`fifo_manager.py:290-292`) in
each of VZ 2023, 2024 and 2025 — the same seven every year. Measured by counting distinct asset
IDs in the run logs.

Of the resulting reconciliations, five produce a synthesised start-of-year lot:

| VZ | Asset | Reconstructed | Reported SoY | Defect |
|---|---|---|---|---|
| 2023 | `DE0006766504` (NDAd) | 200 | 200 | A |
| 2023 | `SG1L01001701` (D05) | 0 | 16 | A |
| 2024 | `JE00B588CD74` (SGBS) | 230 | 100 | **B** |
| 2024 | `SG1L01001701` (D05) | 1000 | 1016 | A |
| 2025 | `SG1L01001701` (D05) | 51 | 67 | A |

The other two flagged assets (`IE00BKLF1R75`, `US0970231058`) and `DE000A1DCTL3` reconcile against
a reported 0, so `_create_fallback_long_lot` returns early and no lot is created.

**Zero of the five fire for the "history does not reach back far enough" reason on its own.** All
five carry `Inconsistent: True`. This matters because it kills the obvious discriminator — see
"What does not work", below.

## Defect A — a pre-window holding corrupts the replay long after its units are gone

**Five of seven assets. The only defect touching VZ 2023 and VZ 2025.**

The historical replay starts from an empty ledger. The first disposal that reaches into a
pre-window tranche oversells; `consume_long_lots_for_sale(..., is_historical_simulation=True)`
consumes what exists and **drops the remainder** rather than carrying a deficit. From that point
the ledger is permanently offset — including after every pre-window unit has, in reality, been
consumed.

D05 (`SG1L01001701`), reconstructed by hand from the input:

| | reality | engine |
|---|---|---|
| 2021-01-01 | 807 (pre-window) | 0 |
| two stock dividends | 816 | 9 |
| 2021-11-19 sell 800 | 16 | oversell, 791 dropped → 0 |
| 2021-11-19 buy 800 | 816 | 800 |
| 2022-04-07 sells 800 | 16 | 0 |

Reported SoY 2023 is 16; the engine reconstructs 0 and synthesises a lot. The same offset persists
into 2024 (1000 vs 1016) and 2025 (51 vs 67).

The pre-window quantity is **derivable** from data that is entirely present —
`Positions-2021-EoY` minus every observed 2021 event. Checked for all seven assets; each
derivation replays through 2021 and lands exactly on the reported EoY:

| ISIN | EoY-2021 | 2021 events | derived opening |
|---|---|---|---|
| `SG1L01001701` | 816 | 9 | 807 |
| `DE0006766504` | 200 | 125 | 75 |
| `IE00BKLF1R75` | 0 | −500 | 500 |
| `US0970231058` | 0 | 300 | −300 (short) |
| `DE000A1DCTL3` | 0 | −250 | 250 |
| `JE00B588CD74` | 0 | 0 | 0 |
| `IE00BJ38QD84` | 0 | 0 | 0 (but see Defect C) |

The acquisition dates and cost bases behind those quantities are **not** derivable. That is the
same boundary `CLAUDE.md` already draws, and it is why the VZ 2023 floor exists.

`DE0006766504` is the sharpest instance and does not involve missing history at the mark at all:
its reconstruction at SoY 2023 is **exactly right** — 200 units, both lots from the 2022-12-29
buys — and is discarded anyway, because `fifo_manager.py:331` sets `use_fallback` from the
inconsistency flag before any quantity comparison happens.

## Defect B — the merger phase (issue #56 as filed)

`JE00B588CD74` only. Confirmed exactly as the issue describes: `Phase` is the primary sort key in
`replay.py:86-88`, so `Phase.MERGERS` (1) is applied after every `Phase.LEDGER_EVENTS` (0) item in
the whole window regardless of date.

`DE000A1DCTL3` carries both a pre-window tranche of 250 **and** the merger, which is why it appears
under A as well.

### Correction to an earlier reading

An earlier draft of this analysis claimed `CorpActionMergerStock` carries an IBKR transaction id,
so collapsing the phase would leave merger-vs-same-day-trade order arbitrary, and that
`get_event_sort_key` had to be repaired first. **That is wrong.**

`Corporate_Actions-*.csv` has no `TransactionID` column (header inspected).
`RawCorporateActionRecord.transaction_id` aliases it (`raw_models.py:209`) and resolves to `None`;
`domain_event_factory.py:711` puts it in the kwargs and the surrounding comprehension strips
`None`; `FinancialEvent.ibkr_transaction_id` defaults to `None` (`events.py:31`). So
`transaction_id_for_sort` is `""` (`sorting_utils.py:102`) and the merger sorts ahead of every
same-day trade id.

Consequence: **the phase collapse alone is sufficient**, and no change to `get_event_sort_key` or
to PRD 5.8 is needed. The wide-blast-radius sort change described earlier is off the table.

The caveat survives in weaker form: the order is correct *because a CSV column is absent*. It must
be pinned by a test rather than left to inference.

## Defect C — cancelled/rebooked trades are re-inferred from the quantity sign

`IE00BJ38QD84` (R2US). Two `(Ca.)` rows, both dated 2021-02-01; grepped, they are the only two in
the entire import.

`_determine_trade_event_type` compares `buy_sell == "BUY"` and `== "SELL"` exactly
(`domain_event_factory.py:81,97`). `"BUY (Ca.)"` matches neither, so control reaches
`domain_event_factory.py:114`, which logs *"Buy/Sell indicator missing"* — false; the indicator is
present and unrecognised — and infers direction from the quantity sign with an empty Open/Close
indicator. `BUY (Ca.)` with quantity −200 becomes `TRADE_SELL_LONG`; `SELL (Ca.)` with +70 becomes
`TRADE_BUY_LONG`.

Result: a phantom 200-unit long position, and a running total that dips to −470 during 2021 in an
account with no short position in that instrument.

**No effect on any declared figure in VZ 2023-2025**: the ISIN appears in no `Positions-*.csv`, so
the reported quantity is 0 at every mark and the phantom is cleared without a fallback lot being
created. The defect is that an *unrecognised* value is silently handled as a *missing* one, which
would misprice a realised gain if such a pair ever landed in a declared year.

## Defect D — the historical dispatch is a strict subset of the current-year dispatch

**Was marked (structural, unmeasured). It is neither — see "Measured once checkpointing landed".**

`OptionLifecycleEvent` subclasses `FinancialEvent` directly, not `TradeEvent` (`events.py:276`).
The historical separation at `calculation_engine.py:245` buckets only
`TradeEvent`, `CorpActionSplitForward` and `CorpActionStockDividend`, and
`apply_historical_event` (`fifo_manager.py:255-292`) has no branch for anything else and no `else`.
So historical option exercises, assignments, expirations and cash settlements never touch a
ledger, and neither do `CorpActionMergerCash` or `CorpActionExpireDividendRights`. The current-year
dispatch table has twelve entries.

Volume in the window: 16 expirations in 2021; one assignment, two exercises and six expirations in
2022.

### Measured once checkpointing landed

The original assessment — "no measured impact on VZ 2023-2025" — was correct only because the
single-mark reconciliation could not see it. Reconciling at every yearly snapshot exposed it on
the first real run: **nine option ledgers** carried a phantom holding into the 2022-12-31 mark
(6 expirations, 2 exercises, 1 assignment), and **200 ATVI shares** cash-merged away in October
2023 (`US00507V1098`) sat in the ledger from then on. All ten reported a broker quantity of zero,
which is exactly why the suite and the old reconciliation were blind to them: a reported zero
clears the ledger and hides the disagreement.

Fixed with change 2. `OptionLifecycleEvent`, `CorpActionMergerCash` and
`CorpActionExpireDividendRights` now enter the historical bucket, and
`FifoLedger._close_position_lots_historically` applies the lot effect without producing a realised
gain (the historical replay declares nothing). The share leg of an exercise or assignment is
deliberately not handled there — IBKR books it as an ordinary stock trade that already replays
against the underlying's own ledger, and touching it here would double it.

**The dispatch no longer falls through silently.** A `CorporateActionEvent` routed into the
historical bucket with no handler raises `ProcessingError`. Silence is what let a cash merger
leave 200 shares in the ledger for every year after 2023.

## Two latent defects found on the way

Neither is reachable today. Both become reachable under the target design, so they are listed here
rather than filed separately.

1. **`fifo_manager.py:335` keeps the oldest lots when the reconstruction exceeds the report.**
   **Correction:** an earlier draft of this document said nothing in the suite exercised this
   branch. That was wrong — `SOY_H_001` and `SOY_H_002` in
   `tests/fixtures/group2_soy_handling.yaml` exercise it deliberately, asserting that the real
   historical acquisition date survives. They pin *keep real lots*, not *keep the oldest*: each
   holds a single lot, so either end of the list returns the same one. Verified by mutation —
   restoring oldest-first leaves both green and fails only the two-lot case in
   `test_replay_checkpoint_marks.py`. The
   condition is `reconstructed_total_long_qty >= reported_soy_qty`, and the loop then fills from
   `reconstructed_long_lots_snapshot` in order until the reported quantity is satisfied. Lots are
   held oldest-first (`fifo_manager.py:392`). Under FIFO the units surviving to a mark are the
   *newest* — the oldest were sold — so this keeps the wrong ones. Unreachable today because
   `:331` short-circuits it for every affected asset. If the flag stops deciding without this
   being addressed, SGBS at the 2024 mark (230 vs 100) would keep the phantom merger lots dated
   2022-04-20 and 2022-06-13 instead of the real 2023-05-12 buy — turning a loud abort into a
   silently wrong acquisition date.
2. **`domain_event_factory.py:943` synthesises `f"BM-{action_id}"`** as the transaction id of a
   bond-maturity `TradeEvent`. `"B"` sorts after every digit, so a bond maturity sorts *last*
   among that instrument's same-day events. No bond maturity appears in the flagged set.

## What does not work

An earlier proposal was to treat the inconsistency flag as the discriminator: flag set means an
engine or input defect and should stop the run; flag clear means insufficient history and keeps the
argued fallback.

**D05 disproves it.** A pre-window holding sets the flag whenever it is disposed of inside the
window, which is the ordinary case, not a defect. The flag does not separate the two conditions.
After A and B are fixed the flag should stop firing for these seven assets, and only then does it
become a usable tripwire.

A second proposal was to seed the replay at the window start with the derived opening quantity.
Rejected: a partial ledger is the normal starting condition for any user, and the position
snapshots are already the mechanism for recovering from it. Seeding hides at the window start what
should be handled, visibly, at every mark.

## Target design — reconcile at every mark

The position reports are ground truth snapshots. At each one, the reconstruction is either accurate
or it is not; where it is not, the snapshot replaces it and FIFO carries on from there.

**Marks** are every position snapshot in the window. Present at 2021-EoY, 2022-EoY, 2023-EoY and
2024-EoY. `SoY(Y)` was compared against `EoY(Y-1)` at all four boundaries — 4/4, 7/7, 11/11 and 6/6
rows — with **zero disagreements**, so the marks are self-consistent.

Per asset, at each mark:

- replayed quantity **equals** the snapshot → keep the reconstructed lots, with their real
  acquisition dates and cost bases;
- **differs** → discard them, take the snapshot as one lot (quantity and reported cost basis,
  `acquisition_date_is_known=False`), and record a data gap naming the mark, the asset and the
  discrepancy.

Then continue the replay into the next interval.

### This reuses the existing machinery

`reconcile_with_soy_position` (`fifo_manager.py:305`) with `_create_fallback_long_lot` /
`_create_fallback_short_lot` already implements compare-then-anchor. It is called once today. The
change is to call it at each mark, parameterising the three inputs it currently hard-codes:

| currently | becomes |
|---|---|
| `asset.soy_quantity` (`:318`) | the mark's reported quantity |
| `asset.soy_cost_basis_amount` / `_currency` (`:403-408`) | the mark's reported basis |
| `tax_year`, used for `f"{tax_year-1}-12-31"` (`:425`) and `date_obj(tax_year,1,1)` (`:412`) | the mark date |

Reused unchanged: the comparison, the fallback lot construction, `acquisition_date_is_known=False`
(`:430`), the final re-sort and the unparseable-date guard (`:391-398`). The
"reported quantity is 0 → no lots" branch (`:327-329`) is already what clears a phantom position at
a mark.

### Simulated against the real input

Quantity-and-dates simulation of the design, driven by `data_import/`:

```
ISIN              mark      replayed  snapshot           lots carried forward
SG1L01001701   2021-EoY          800       816   ANCHOR  816@UNDATED
SG1L01001701   2022-EoY           16        16   keep    16@2022-12-20
SG1L01001701   2023-EoY         1016      1016   keep    real dated lots
SG1L01001701   2024-EoY           67        67   keep    67@2024-08-05

DE0006766504   2021-EoY          200       200   keep    200@2021-12-14
DE0006766504   2022-EoY          200       200   keep    40@2022-12-29, 160@2022-12-29

JE00B588CD74   2022-EoY          130         0   ANCHOR  (empty)
JE00B588CD74   2023-EoY          100       100   keep    100@2023-05-12
```

D05 needs one anchor, at 2021-EoY, and is back on real dated lots from 2022-EoY onward — all three
declared years gain real lots where they have synthesised ones today. `DE0006766504` needs no
anchor at all.

The SGBS rows matter for sequencing: the 2022 mark clears the phantom 130 **regardless of merger
ordering**, so SoY 2024 comes out as `100 @ 2023-05-12` whether or not Defect B is fixed.

Simulation limits, stated because they bound the conclusions: shorts are modelled as longs (so the
`US0970231058` row is an artifact), the merger's source side is not modelled (so `DE000A1DCTL3`
would show a false anchor), and cost basis is not modelled at all. None of these affect the rows
above.

### Why a historical mark is recoverable but the tax-year EoY check stays fatal

A historical interval declares no figure; only its end state is consumed, and the snapshot supplies
that authoritatively. The tax year's own figures are computed *from* its interval, so a mismatch
there means the declared numbers are wrong. The two reconciliations must not be unified, and the
reason needs to be written down where someone would look before unifying them.

## Fix plan

Four changes, in order. Each is separately committable and separately verifiable.

### 1. Merger phase — `fix-func(engine)`

Closes issue #56.

- Red-first test in `tests/test_stock_merger_fifo.py`: a merger inside the historical window,
  received shares disposed of the same day, more bought later in the window, a holding at SoY.
  Assert the acquisition date and `acquisition_date_is_known`, **not** quantity, cost basis,
  proceeds or gain — `CLAUDE.md` records that a start-of-year snapshot rebuilds those four, so a
  test asserting them would pass against the broken tree.
- Delete `Phase.MERGERS`; stream the merger into `Phase.LEDGER_EVENTS` at its own
  `get_event_sort_key`. `Phase` collapses to `LEDGER_EVENTS → RECONCILE`.
- Add a test pinning merger-before-same-day-trade, so the ordering stops depending on the absence
  of a CSV column.
- A merger source ledger holding lots after the replay is a contradiction; assert it.
- `tests/test_historical_merger_replay_guard.py` encodes the Pass-2 semantics being removed. It is
  a pre-existing test, so it needs sign-off before any change — see Open questions.
- Parity: VZ 2023 and VZ 2025 expected unmoved, measured. VZ 2024 moves from no output to output,
  so parity does not apply and the description must say so.

**Measured outcome.** Red-first: the new test failed 1/1 on `acquisition_date` alone
(`2023-12-31` against an expected `2023-04-10`) with quantity, cost basis, proceeds and gain all
matching — the discriminator behaved as designed. After the change the full suite is 771 passed,
and 771 again under the clean-clone protocol.

Parity, same-tree control first: VZ 2023 control (two captures, one tree) was IDENTICAL on
console, log and PDF. Baseline against fix, **VZ 2023 and VZ 2025: console IDENTICAL, PDF
IDENTICAL** — no declared figure moved in either year. The VZ 2023 log differs by 8 lines: two
renamed INFO messages, the two SGBS oversell warnings gone, and
`Reconstructed SOY Qty 130 → 0, Inconsistent True → False`. VZ 2025 shows the same, plus the
merger's transfer line moving to its chronological position, plus reordered
`OPTION_CASH_SETTLEMENT` lines — the last of which a same-tree VZ 2025 control reproduced exactly
(6 changed lines, all option settlements, no merger or reconcile lines), so it is the `event_id`
uuid4 nondeterminism `replay.py` already documents and not this change.

VZ 2024, previously aborting: now exits 0. SGBS reconstructs 100 against a reported 100 with
`Inconsistent: False`, `VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN` goes from 5 log mentions to 0,
one Vorabpauschale record is produced where the run previously emitted nothing, and synthesised
SoY lots for the year drop from 2 to 1. The one remaining is `SG1L01001701` — defect A, which is
change 2's job.

### 2. Checkpoint reconciliation — `fix-func(engine)`

**Measured outcome.** Red-first: 2/2 in `test_replay_checkpoint_marks.py` fail when the engine is
mutated to ignore the marks, and the failure is the described mechanism — a 2021 shortfall
surviving to the 2023 opening snapshot and being replaced by a synthesised lot. Two further rules
were pinned and each calibrated against its own mutation: restoring "the oversell flag forces the
fallback" fails exactly one test, restoring "fill from the oldest end" fails exactly one other
(and leaves `SOY_H_001`/`SOY_H_002` green, which is how those two were shown not to discriminate).
Suite 775 passed, and 775 again under the clean-clone protocol.

Real data, all three years exit 0. Across VZ 2023, 2024 and 2025 the run now produces **two**
mark warnings and **one** synthesised lot, all at the 2021-12-31 mark: `SG1L01001701` (the genuine
pre-2021 holding) and `IE00BJ38QD84` (defect C's `(Ca.)` phantom). Every declared year's opening
lots are real and dated — `SG1L01001701` reconciles 16/16, 1016/1016 and 67/67 at the final mark
of 2023, 2024 and 2025 respectively, and `DE0006766504` 200/200 then 0/0.

Parity against a change-1-only baseline, years named. **VZ 2025: no figure moved** — PDF
identical, the only console change being the two new data-gap lines. **VZ 2023: one asset moved**
— DBS Group Holdings (`SG1L01001701`). Four figure lines change and all trace to it; no other
instrument appears in the per-asset diff. The cause: its 2023 disposals were measured against a
synthesised lot dated 2022-12-31 carrying the broker's snapshot basis converted at 2023-01-01, and
are now measured against the real 2022-12-20 purchase converted at the trade date. Both the basis
and the conversion date differ, so the gain moves. That is the correction, not a side effect.

`DE0006766504` moved no figure while its lots changed from synthesised to real — it is
EUR-denominated and its snapshot basis equals the real purchase cost, so only the acquisition date
differs. That is the blind spot `CLAUDE.md` describes, and the reason the new tests assert dates.

#### Original plan



Subsumes Defect A. Also removes the need for any separate repair of the discarded exact match on
`DE0006766504`: with checkpointing the flag never decides, so the reconstruction is kept.

- `data_preparation.py` loads every position snapshot in the window, not only the tax year's.
- Generalise `reconcile_with_soy_position` to a mark (quantity, basis, date), as tabulated above.
- Run the replay interval by interval, reconciling at each mark.
- **Stop the inconsistency flag deciding** (`fifo_manager.py:331`). The snapshot comparison becomes
  the sole arbiter; the flag becomes a recorded warning.
- **Tighten `:333-378` to equality.** Delete the `>=` truncation rather than repair it: equal →
  keep the reconstruction, anything else → anchor and record. Nothing in the suite exercises that
  branch (grepped), to be confirmed against a run.
- Record a data gap per mark per asset on mismatch, never aggregated.
- Parity: this **moves** figures in VZ 2023 and VZ 2025, which is the intent. Each movement must be
  explained asset by asset, not merely observed.

### 3. Unrecognised `Buy/Sell` — `fix-nonfunc(parsers)`

**Semantics chosen.** A `(Ca.)` row and the booking it cancels are together a no-op, so both are
removed before event creation (`_drop_cancelled_trade_pairs`). IBKR emits the cancellation with
the *original's* direction word, the negated quantity, and a later transaction id, so the match is
deterministic rather than guessed — verified against the input: both cancellation rows have
exactly one candidate. Interpreting the cancellation row instead was rejected because it carries
no `Open/CloseIndicator`, and the rebooked row is not a guide: on the one real instance the
original was `oc=C` and the rebook `oc=O`. An unmatched cancellation raises.

Anything else unrecognised in `Buy/Sell` now raises `DataIntegrityError` rather than falling
through to sign inference. Note this could not be shipped on its own: transaction files are
concatenated for every year ≤ the tax year, so `Trades-2021.csv` is parsed in every run and a bare
raise would have blocked all three years on those two rows.

**Calibration (the gate for this category).** With the pre-change parser restored, the scenario
"BUY 100, cancel it, rebook it" produces a `LONG_POSITION_SALE` of **100 units** — a disposal that
never happened, measured against whichever lots FIFO consumed first, with the end-of-year quantity
still reconciling because the rebooked row restores the count. Two of the five new tests fail
under that mutation; the other three call the rules directly and are unaffected by removing only
the wiring.

**Parity, years named.** VZ 2023, 2024 and 2025: **PDF identical in all three**. One console line
changes in each — R2US's mark warning, from `reconstructed 200` blamed on missing history to
`reconstructed 0` with the actual cause. No declared figure moved, which is what Band B requires.

**What it did not do.** R2US still warrants a warning at the 2021 mark. After pairing, the
surviving rows are three short opens and a rebooked `BUY +200` carrying `oc=O` — "open a long" —
while the account is short 200; the original it replaced was `oc=C`. The reconstruction therefore
holds long 200 *and* short 200, net zero, with no oversell. That is contradictory broker input,
not an engine guess, and the warning now says so instead of attributing it to a short history.

#### Original plan


- An unrecognised non-empty `Buy/Sell` must raise `DataIntegrityError`, not fall into sign
  inference. The current path also emits a false diagnostic ("indicator missing").
- Decide and record the correct semantics for `(Ca.)` cancellation rows before handling them; do
  not infer them from the sign.
- Calibration against a deliberately broken tree is the gate for this category, and the two 2021
  rows are the calibration case.

### 4. Unify the historical and current-year dispatch — `refactor` or `feat-func`, not yet scoped

Defect D. No measured impact on any declared year, so it is scheduled rather than rushed. The end
state is one dispatch serving both windows, with processors run in a rebuild-lots-discard-RGL mode;
`is_historical_simulation` already exists at the ledger layer. Category depends on whether it
changes any figure, which is not yet known.

### After all four

The inconsistency flag should stop firing for the seven assets. Only then does turning it into a
fail-fast condition become meaningful, and at that point it is a genuine tripwire rather than a
year-blocker.

## Open questions

1. ~~**Severity of a mark mismatch.**~~ **Decided.** The discriminator is not which mark it is,
   but what the interval *started* from. An interval that began at a confirmed snapshot and ends
   at a confirmed snapshot must reconcile: a mismatch there is an **error**, because both ends are
   ground truth and the replay between them is the engine's own work. An interval whose ledger did
   not start from a confirmed SoY or EoY — in practice the first one, before any snapshot exists —
   may mismatch, and that is a **warning**.

   This is stricter than the "historical marks warn" reading it replaces, and it matters for
   sequencing: under it, SGBS's 2022 interval starts from a confirmed 2021-EoY anchor, so the
   phantom 130 the merger phase produced is an error rather than something the next mark quietly
   absorbs. Checkpointing surfaces defect B instead of masking it.
2. **Does the VZ 2023 floor move?** It should not. VZ 2022's disposals still consume the 2021-EoY
   anchored lot, so its gains rest on a basis and a date nobody observed. Worth restating
   explicitly once checkpointing lands, since the reasoning in `CLAUDE.md` is phrased around a
   single reconstruction pass.
3. **`test_historical_merger_replay_guard.py`.** It encodes the ordering being removed. Standing
   constraint: a pre-existing test may not be changed without explicit sign-off. Each of its cases
   needs re-deciding against the new contract before change 1 can land.
4. **Correct semantics for `(Ca.)` rows.** Whether a cancellation should reverse the specific prior
   booking or be netted, and whether IBKR guarantees the rebooked row accompanies it. Not settled
   by anything read so far.
5. **Should the newly found defects be filed as issues?** A, C and D are not covered by issue #56.
   Not filed — filing is an outward-facing action and has not been authorised.
6. ~~**`US0970231058` short-side behaviour under checkpointing**~~ **Exercised.** The short path
   runs on the real data and all three years reconcile with no short-side mark disagreement.
7. ~~**`ShortFifoLot` does not flag an invented opening date.**~~ **Withdrawn — do not file this.**
   It is true that `FifoLot` carries `acquisition_date_is_known` and `ShortFifoLot` has no
   counterpart, but adding one would create a field nothing reads. `acquisition_date_is_known`
   has exactly one consumer in `src/`: the Vorabpauschale, via `_snapshot_fund_lots` →
   `FundUnitTranche.abs2_retained_twelfths`. That function iterates `ledger.lots` only and never
   `ledger.short_lots`, deliberately — a short fund position is not a holding of
   Investmentanteile, and Rz. 18.4 counts units *verwahrt oder verwaltet*. So the Vorabpauschale
   can never see a short lot, and no other consumer exists.

8. **§ 23 decides a Jahresfrist from a date that may be invented, and consults no guard.**
   The real finding behind item 7. `is_within_section23_speculation_period` is computed from
   `acquisition_date` (`fifo_manager.py:838`, `:975`) with no reference to
   `acquisition_date_is_known`, and the result is not informational — `loss_offsetting.py:253`
   and `pdf_generator.py:1275` both branch on `is_taxable_under_section_23`. So the Vorabpauschale
   is currently the *only* consumer in the engine that refuses to compute from a date nobody
   observed.

   **Not live.** Measured on the maintainer's data after checkpointing: the only synthesised lot
   in any of VZ 2023-2025 belongs to `SG1L01001701`, a stock, whose Jahresfrist decides nothing.
   The two `PRIVATE_SALE_ASSET` holdings (`DE000A27Z304`, `DE000A4AER62` — the § 23 category is
   "Gold-ETC, Krypto-ETP") reconcile exactly at every mark, with zero disagreements and zero
   fallback lots, so both carry real acquisition dates.

   Checkpointing also narrowed the exposure: a fallback lot can now only arise in the first
   interval, and only for a holding that genuinely predates the input window. Recorded as a
   latent coupling, not scheduled.

# Test Suite Validation Report

**Date:** 2026-04-04
**Scope:** Complete test suite cross-checked against curated reference library (`reference/`)
**Method:** Every test file's assertions compared against authoritative German tax law sources (EStG, InvStG, BMF-Schreiben, official form instructions)

---

## Confirmed Errors

### 1. Derivative Loss Cap Still Applied for Tax Year 2024 -- RESOLVED

**Status:** fixed. `derivative_loss_cap_applies` is now False for every year in
`src/tax_law/registry.py`, and the four fixture expectations below carry the
values this finding predicted. The application rule is quoted verbatim in
`reference/tax-law/estg-20-abs6-verlustverrechnung.md`: 52 Abs. 28 Satz 25 EStG
n.F., *"ist auf alle offenen Faelle nicht mehr anzuwenden"*. The description
below is kept as the original finding.

**Severity:** HIGH
**Legal basis:** EStG 20 Abs. 6 Satz 5 a.F., abolished by JStG 2024 (BGBl. I 2024 Nr. 387, Art. 1 Nr. 10)
**Reference file:** `reference/tax-law/estg-20-abs6-verlustverrechnung.md`

The EUR 20,000 annual cap on derivative losses (Verlustverrechnungsbeschraenkung fuer Termingeschaefte) was abolished with **retroactive effect to all open cases** (52 Abs. 28 EStG n.F., effective 02.12.2024). Tax year 2024 is an open case at that date, so the cap must not apply.

**Affected code:**
- `src/reporting/form_rules.py:41` -- `derivative_loss_cap_applies=True` for 2024 (should be `False`)
- `src/config.py:76` -- `APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING: bool = True` (default compounds the issue)

**Affected test expectations** (all in `tests/fixtures/loss_offsetting_data.py`):

| Test ID | Field | Current Value | Correct Value | Line |
|---------|-------|---------------|---------------|------|
| LO_TERM_004 | `conceptual_net_derivatives_capped` | `-20000.00` | `-30000.00` | 254 |
| LO_TERM_007 | `conceptual_net_derivatives_capped` | `-20000.00` | `-25000.00` | 318 |
| LO_MIX_002 | `conceptual_net_derivatives_capped` | `-20000.00` | `-29000.00` | 594 |
| LO_MIX_004 | `conceptual_net_derivatives_capped` | `-20000.00` | `-25000.00` | 646 |

The form line values (Z24) are unaffected -- they always report gross uncapped amounts. Only the conceptual summary field is wrong.

---

### 2. `is_taxable_under_section_23` Incorrectly Defaults to True

**Severity:** LOW (no current calculation impact)
**Legal basis:** Options/stocks/bonds/funds are taxed under EStG 20, not EStG 23
**Reference file:** `reference/tax-law/estg-20-kapitalvermoegen.md`

In `src/engine/fifo_manager.py`, the `is_taxable_under_section_23_flag` defaults to `True` in each of the three realization paths (long sale, short cover, cash merger) and is only corrected for `AssetCategory.PRIVATE_SALE_ASSET`. For all other categories (STOCK, BOND, SONSTIGE_KAPITALFORDERUNG, OPTION, CFD, FUTURE, INVESTMENT_FUND), the flag remains `True` -- semantically wrong. (The line numbers this entry used to give had drifted; the paths are named instead, since they move with every edit to the file.)

Additionally, `src/engine/event_processors/option_processor.py:223` explicitly sets `is_taxable_under_section_23=True` for option expiration RGLs, with a comment acknowledging the contradiction: "Options are Termingeschaefte, not 23".

**Why low impact:** The loss offsetting engine only checks this flag when `asset_category_at_realization == AssetCategory.PRIVATE_SALE_ASSET`, so the incorrect default does not affect tax calculations. However, it would cause incorrect behavior if the guard logic changes in the future.

---

### 3. Stock Dividend Tax Treatment May Be Incorrect

**Severity:** MEDIUM
**Legal basis:** EStG 20 Abs. 4a Satz 5
**Reference file:** `reference/tax-law/estg-20-kapitalvermoegen.md`

`tests/test_dividend_handling.py:367-460` (test_d05) treats a stock dividend ("SD" corporate action type) as:
- Taxable income of EUR 349 (FMV of received shares)
- New FIFO lot with cost basis = FMV (EUR 34.90 per share)

EStG 20 Abs. 4a Satz 5 states: shares allocated by a foreign corporation **without consideration** (ohne Gegenleistung) have **income = EUR 0** and **acquisition cost = EUR 0**. The original shares' cost basis remains unchanged.

The correct treatment depends on the nature of the corporate action:

| Type | German Term | Income | Cost Basis | Statutory Ref |
|------|-------------|--------|------------|---------------|
| Bonus shares from capital increase | Gratisaktien | EUR 0 | EUR 0 | 20 Abs. 4a Satz 5 |
| Scrip dividend (distribution in shares) | Sachdividende | FMV | FMV | 20 Abs. 1 Nr. 1 |

The test does not clearly distinguish which scenario it models. If IBKR's "SD" corporate action represents a Gratisaktie (which is the more common interpretation for "STOCK DIVIDEND" in IBKR's terminology), the test expectations and the `StockDividendProcessor` cost basis assignment are both wrong.

**Recommendation:** Clarify with IBKR documentation or real examples whether "SD" type stock dividends represent bonus shares (Gratisaktien) or scrip dividends (Sachdividenden). Adjust treatment accordingly, potentially requiring two separate code paths.

---

## Potential Errors

### 4. Negative Dividends and Interest Silently Ignored

**Severity:** MEDIUM
**Location:** `src/engine/loss_offsetting.py:121-126`
**Reference:** Dividend corrections, reversals, and payment-in-lieu adjustments can produce negative amounts.

The loss offsetting engine only accumulates **positive** dividend and interest amounts:

```python
if event.event_type == FinancialEventType.DIVIDEND_CASH and ...:
    if event_gross_eur > Decimal('0'):          # <-- negative amounts skipped
        kap_other_income_positive = ...
elif event.event_type == FinancialEventType.INTEREST_RECEIVED:
    if event_gross_eur > Decimal('0'):          # <-- negative amounts skipped
        kap_other_income_positive = ...
```

Negative dividends (e.g., dividend corrections, reversals) are silently discarded, which would **overstate Z19** (Auslaendische Kapitalertraege). No test covers this scenario.

---

### 5. Vorabpauschale: Partial Year Reduction Not Implemented

**Severity:** MEDIUM
**Location:** `src/engine/calculation_engine.py:703-830`
**Legal basis:** InvStG 18 Abs. 3
**Reference file:** `reference/investment-tax-law/invstg-18-vorabpauschale.md`

InvStG 18 Abs. 3 requires the Vorabpauschale to be reduced by 1/12 for each **full calendar month** before the month of acquisition within the tax year. For example, a fund acquired in April would have VP reduced by 3/12 (January, February, March).

The implementation contains:
- No acquisition date tracking for fund positions
- No monthly proration logic
- No test coverage for this scenario

This means funds acquired mid-year will have an **overstated Vorabpauschale**.

---

### 6. Cross-Year Option Premium Timing (Zuflussprinzip)

**Severity:** LOW (test coverage gap, not an assertion error)
**Location:** `src/engine/event_processors/option_processor.py:132-230`
**Legal basis:** EStG 20 Abs. 1 Nr. 11, EStG 11 (Zuflussprinzip)
**Reference file:** `reference/tax-law/estg-20-kapitalvermoegen.md`

EStG 20 Abs. 1 Nr. 11 provides that Stillhalterpraemien (option premiums received by the writer) are taxable **upon receipt**. The engine uses a lot-based approach that defers premium recognition until position close (expiration, assignment, or buy-to-close).

For options opened and closed in the same tax year, the net result is identical. For options **spanning tax years** (sold in year N, closed in year N+1), the premium income is attributed to the wrong year.

All Group 8 test specs (`tests/fixtures/group8_options.yaml`) use dates within 2023 only -- no cross-year scenario exists. This is a coverage gap rather than an incorrect assertion.

---

## Verified Correct

The following areas were validated against the reference library and found to be correct:

### Teilfreistellung Rates (InvStG 20)
All five rates in `src/utils/tax_utils.py` match the statutory provisions exactly:

| Fund Type | Code Rate | Reference Rate | Statutory Ref |
|-----------|-----------|---------------|---------------|
| Aktienfonds | 30% | 30% | InvStG 20 Abs. 1 S. 1 |
| Mischfonds | 15% | 15% | InvStG 20 Abs. 2 |
| Immobilienfonds | 60% | 60% | InvStG 20 Abs. 3 S. 1 Nr. 1 |
| Auslands-Immobilienfonds | 80% | 80% | InvStG 20 Abs. 3 S. 1 Nr. 2 |
| Sonstige Fonds | 0% | 0% | (no provision) |

Symmetric application for negative amounts (loss reversal) is tested and correct.

### Vorabpauschale Formula (InvStG 18)
- Basisertrag = SoY x Basiszins x 0.70 -- correct (calculation_engine.py:778)
- Basisertrag capped at value gain (EoY - SoY) -- correct (calculation_engine.py:792-795)
- VP = max(0, Basisertrag - distributions) -- correct (calculation_engine.py:786-790)
- Negative distributions excluded from reduction -- correct
- Basiszins 2024 = 2.29% -- correct per BMF 02.01.2024
- **Incomplete, noted 2026-08-09.** The three lines above check Saetze 1 to 3 against each other
  and never ask where 18 Abs. 2 enters. It enters between them: Rz. 18.3 subtracts the
  distributions and Rz. 18.11 takes the twelfths of what remains, so a fund acquired mid-year and
  distributing in the same year is not covered by *"VP = max(0, Basisertrag - distributions)"*
  alone. Recorded as [GT-INVSTG-056]; the engine's position is in
  `docs/legal-implementation-map.md`. Pro-rata was not implemented at all when this audit ran, so
  the omission was invisible to it -- which is the point: an audit of a formula cannot see a term
  the formula does not have.

### Anlage KAP Form Lines Z19-Z24
**2024 formula** (separate_derivative_lines = True):
- Z19 = stock_g - stock_v + other_g - other_v + deriv_g (derivative losses NOT subtracted) -- correct
- Z20 = gross stock gains -- correct
- Z21 = gross derivative gains -- correct
- Z22 = other losses (non-stock, non-derivative only) -- correct
- Z23 = stock losses (absolute) -- correct
- Z24 = derivative losses (absolute, uncapped for form) -- correct

**2025 formula** (separate_derivative_lines = False):
- Z19 now subtracts derivative losses -- correct
- Z21 = 0.00, Z24 = 0.00 (lines removed) -- correct
- Z22 includes derivative losses -- correct

All 28 loss offsetting test cases (LO_ALL_001 through LO_FUND_MISCH_002) were spot-checked against the reference Z19 formula. All Z19, Z20-Z24, and Z54 assertions are arithmetically correct (apart from the derivative cap issue in finding 1).

### Other Verified Areas

| Area | Reference | Verdict |
|------|-----------|---------|
| Z55 = sum of gross VP (before TF) | InvStG 19 Abs. 1 S. 3-4 | Correct |
| KAP-INV amounts reported as gross | anlage-kap-inv-zeilen.md | Correct |
| Fund income isolated from Z19 | InvStG 16 | Correct |
| WHT sign convention (positive for Z41) | EStG 32d Abs. 5 | Correct (parser uses copy_abs) |
| FX gains/losses mapped to 20 EStG | BMF fremdwaehrung-konten.md | Correct |
| Stock loss ring-fencing (Z23 separate) | EStG 20 Abs. 6 S. 4 | Correct |
| Stock-for-stock merger tax-neutral | EStG 20 Abs. 4a S. 1-2 | Correct |
| Cash merger = taxable disposal | EStG 20 Abs. 2 Nr. 1 | Correct |
| FIFO method per asset per depot | EStG 20 Abs. 4 | Correct |
| 23 EStG losses isolated from 20 EStG | EStG 23 Abs. 3 S. 7-8 | Correct |
| 2025 form rules (derivative lines removed) | anlage-kap-zeilen.md | Correct |

---

## Summary

| # | Finding | Severity | Type |
|---|---------|----------|------|
| 1 | Derivative loss cap applied for 2024 (abolished retroactively) | HIGH | Test + code error -- RESOLVED |
| 2 | `is_taxable_under_section_23` defaults True for non-23 assets | LOW | Code error (dormant) |
| 3 | Stock dividend treated as taxable income (may conflict with Satz 5) | MEDIUM | Ambiguous test |
| 4 | Negative dividends/interest ignored in loss offsetting | MEDIUM | Missing handling |
| 5 | Vorabpauschale partial year reduction not implemented | MEDIUM | Missing feature |
| 6 | Cross-year option premium timing not tested | LOW | Coverage gap |

---

# Real-data validation log

Ledger reconciliation and output parity against the maintainer's own IBKR export. Instance data —
holdings, identifiers, amounts — stays in gitignored working copies; only outcomes are recorded here.

## 2026-08-12 — per-Depot FIFO: what it corrects, and what it re-dates

Captures with `scripts/parity_check.sh`, VZ 2025, on the branch that keys FIFO ledgers by the real
account.

| Capture | Result |
|---|---|
| Control, unmodified tree twice (`base25a` vs `base25b`) | console, log and PDF IDENTICAL |
| Per-account tree, VZ 2025 | **the run aborts** — see below; it is not a designed refusal |
| Per-account tree, VZ 2024 / VZ 2023 | aborts, as it does on the unmodified tree; neither year produces figures there either |
| **Cash- and position-snapshot summation alone, applied to the unmodified tree, VZ 2025** | **three declared figures move, and a standing data gap closes** |
| **Per-account tree with the § 18 Abs. 2 refusal patched, VZ 2025** | **eight declared figures move** |

### The half that is a correction

Isolating the snapshot summation — the record on `Asset` summed across accounts instead of taking
the last row read — and applying it alone to an `origin/main` worktree, VZ 2025 completes and
differs from the unmodified capture in exactly four places:

- **Anlage KAP Zeile 19** (Ausländische Kapitalerträge nach Saldierung, ohne Fonds),
- **Anlage KAP Zeile 22** (Verluste Kapitalerträge ohne Aktien, inkl. Termingeschäfte),
- the **Saldo Sonstige Kapitalerträge (nicht Fonds)** line, and
- the standing **`[CURRENCY_EOY_MISMATCH]` USD** data gap, which **disappears**.

The gap closing is the confirmation that the new figure is the right one: the USD ledger was
seeded from one account's opening balance and therefore disagreed with the broker's reported
closing balance all along. Seeded from the person's total it reconciles.

### The half that is blocked, and what is behind the block

The full branch produces no VZ 2025 output. The abort is **not** the per-account code refusing:
it is `FundUnitTranche.abs2_retained_twelfths` raising because
`_calculate_vorabpauschale` re-dates an undated tranche with `dataclasses.replace(...)` and does
not clear `acquisition_date_is_known` — a dormant defect from `e70099b`, present on `origin/main`,
which this change is the first input shape to reach.

Patching that one line (`acquisition_date_is_known=True`, which is what the surrounding comment
intends) and re-running VZ 2025 on the branch: the run completes, and **eight** declaration lines
differ from `origin/main` — the three above plus **Saldo Aktien**, **Zeile 20** (Gewinne aus
Aktienveräußerungen), **Zeile 26** (Sonstige Investmentfonds G/V), **Zeile 53** and **Saldo
Investmentfonds**.

Those five extra movements are not the per-Depot rule working. They come from lots the checkpoint
reconciliation discarded and rebuilt from the broker's snapshot: `REPLAY_MARK_UNCONFIRMED_START`
goes from **1 gap on `origin/main` to 19 on the branch**. The quantities are the broker's, so the
end-of-year reconciliation passes; the acquisition dates are invented, and only § 18 Abs. 2
refuses to read one — § 23 and the FIFO order do not.

The cause is input the engine does not read: the export records transfers between the two
accounts, all in one earlier year. Per-account ledgers turn each into a hole — the sending account
still holds units, the receiving one holds none — and the reconciliation papers over it with dated
lots nobody measured.

**Three conclusions, recorded because each was wrong in an earlier draft of this entry:**

1. The per-Depot half is **not latent on this data**. It is blocked, and it moves five further
   declared figures the moment the block is removed.
2. The engine's "refusal" here is a property of the fund path, not of this change. A portfolio
   with no Investmentfonds would declare those figures without stopping.
3. The effect is not confined to the year of a transfer. The historical replay spans the whole
   window, so an early move re-dates lots that later years still hold.

Until the Transfers export is read, this branch is sound only for input in which nothing was ever
moved between accounts.

## 2026-08-12 (later the same day) — reading the Transfers export closes the block above

Same tooling, same year. This entry supersedes the last sentence of the one above.

### What the export contains — measured before any code was written

`data_import/Transfers-*.csv`, all three files, 2026-08-12:

| Measurement | Result |
|---|---|
| Files with rows | one only (2023): **52 data rows**. 2022 is header-only; 2024 carries a repeated header and no data. |
| Rows by class | 48 `STK`, 4 `CASH` |
| `Type` | `INTERNAL` on all 52 |
| `Code` = `ST` ⟺ blank `TransactionID` | exactly, both ways: **28 rows** of each, the same 28 |
| The complement | **24 summary rows**, each carrying `TransactionID` *and* `PositionAmount`: 20 `STK` (10 OUT, 10 IN) and 4 `CASH` (2 OUT, 2 IN) |
| Pairing the STK summary rows on (ISIN, Date, reversed accounts, \|Quantity\|) | **10 OUT, 10 IN, 0 unmatched either way** |
| Signs across a pair | opposite in all 10; **8 pairs are OUT-negative, 2 are OUT-positive** — so the sign carries neither the direction nor long-versus-short |
| `TransferPrice` | `0` on all 52 rows |
| `Multiplier` on the STK rows | `1` on all 20 |
| Distinct move dates | 2 |

That settles the collapse rule the engine implements: drop the rows with no `TransactionID`, read
the direction from `Direction`, take `abs(Quantity)`, and deduplicate the two sides of each move.

### VZ 2025 with the export read

| Capture | Result |
|---|---|
| Control, this tree twice (`pr2_a` vs `pr2_a2`) | console, log and PDF IDENTICAL |
| **This tree, VZ 2025** | **the run completes.** On the branch without this change it aborts (entry above) |
| This tree vs `origin/main`, VZ 2025 | **three declared figures move** — Zeile 19, Zeile 22, Saldo Sonstige — plus the new multi-account banner and gap text, and `[CURRENCY_EOY_MISMATCH]` closing. **Nothing else differs.** |
| `REPLAY_MARK_UNCONFIRMED_START` | **1**, the same single instrument and the same interval as on `origin/main`. It was 19 on the branch without this change. |
| VZ 2024 | aborts on `VORABPAUSCHALE_YEAR_START_PRICE_UNKNOWN` in a `--no-interactive` run — identical on `origin/main`, unrelated to this change |
| VZ 2023 | cannot be prepared at all: `Positions-2022-EoY.csv` is absent. Unchanged, and unrelated |

**The eight moved lines reduce to three, and the three are exactly the ones the snapshot summation
accounts for.** The five that came off re-dated lots are gone, which is what the plan required:
anything still moving would have been a defect rather than a consequence of lot selection.

### What the engine did with the rows

10 moves built from 52 rows, 28 of them lot-detail rows collapsed into their summary rows. All 10
are whole-position moves, so the partial-move refusal does not fire on this data. **Eight moved a
long position and two moved a short one** — six short lots each — which is the reading taken from
the sending ledger rather than from the export's sign, and the case that sign could never have
identified.

## 2026-08-12 (third entry) — incidence behind per-account currency, measured before the code

The counting gate for [GT-FX-009] and [GT-FX-010]. `data_import/Cash_Balance-*.csv` and
`data_import/Transfers-*.csv`, all years, 2026-08-12, repeated mid-file headers stripped the way
the engine strips them.

| Measurement | Result |
|---|---|
| Export years carrying a cash-balance report | 4 |
| Years whose report names more than one account | 3 of 4 |
| Non-EUR currencies held in **more than one account** in the same year | 3, 3 and 4 in the three multi-account years; 0 in the single-account year |
| `ClientAccountID` present on every cash-balance row | yes, all years |
| `ClientAccountID` present on every cash-transaction row | yes, all years |
| Non-EUR `AssetClass=CASH` transfer rows between the taxpayer's own accounts | **1 move**, in one year, appearing as one OUT and one IN summary row |
| EUR `AssetClass=CASH` transfer rows | 1 move, same year — out of scope, the engine's base currency is not a Fremdwährungsguthaben |
| `Quantity`, `PositionAmount`, `TransferPrice` on the cash rows | `0` on every one; the amount is in `CashTransfer` |
| Sign of `CashTransfer` | negative on the OUT side, positive on the IN side, in the one move observed. **Not relied on** — the direction is read from `Direction`, as for securities |
| `CASH` rows in any `Positions-*.csv` | none, any year. So no export supplies a cost basis for a currency balance, and none is read |

**Zero would have meant stop.** It is not zero on either half: currencies collide across accounts
in most years, so the pooled ledger measures disposals against the wrong lots today; and a move of
a foreign-currency balance between the two accounts has occurred, so the disposal [GT-FX-009]
creates is a real one rather than a hypothetical.

**Reproduce with:** read each file with the header row taken from the first line and any later row
equal to it discarded, then group the non-EUR, non-`BASE_SUMMARY` rows by `CurrencyPrimary` and
count distinct `ClientAccountID`.

## 2026-08-12 (fourth entry) — per-account currency on VZ 2025

### The input this had to be captured against, and why it is not `data_import/` untouched

`Positions-2022-EoY.csv` and `Positions-2022-SoY.csv` were added after the third entry above,
which recorded that VZ 2023 could not be prepared without them. They turn the 2023 interval into a
*confirmed* one — an interval that begins at a reported snapshot and ends at one — and it fails.
**With them present no assessment year produces figures on any tree**, including `origin/main`
(`5a64079`), checked in a clean worktree:

| Year | Outcome, on `origin/main` and on this branch alike |
|---|---|
| VZ 2023 | aborts, `EOY_RECONCILIATION_FAILED`, one instrument |
| VZ 2024 | aborts, `VORABPAUSCHALE_YEAR_START_PRICE_UNKNOWN`, in a `--no-interactive` run |
| VZ 2025 | aborts, `REPLAY_MARK_MISMATCH` at the 2023-12-31 mark, one instrument |

That is a pre-existing finding about the input and the replay, not about this change, and it wants
its own investigation: both ends of the 2023 interval are ground truth, so the disagreement is in
the engine's handling of the events between them or in the events themselves.

**Parity was therefore captured against a copy of `data_import/` with `Positions-2022-*.csv`
withheld** — the exact input state the previous two entries were measured under. Reproducing it
needs nothing but a directory of symlinks with those two files left out.

### Same-tree control

Base branch captured twice against that input: console identical. So no ambient nondeterminism is
being read as a change. The ECB cache was warm before either capture.

### VZ 2025, base branch versus this one

| | Result |
|---|---|
| **Declared figures that move** | **three** — Anlage KAP Zeile 19, Zeile 22, and the Saldo Sonstige Kapitalerträge |
| Declared figures that do not | every other one: Saldo Aktien, Saldo Termingeschäfte, Saldo Investmentfonds, Saldo § 23, Zeilen 20/23/26/41/53, and the itemised interest, dividend and bond components |
| Direction | gross positives and gross losses both rise; the net moves by about a euro |
| PDF | the same three figures and their two restatements, and nothing else |
| Currency FIFO ledgers initialised | 9 → 13, as four currencies split across the two accounts |
| Internal cash transfer events | 1 built; the EUR move produces none |
| Realised gain/loss records | 197 → 216. **Not the cash move**: the one non-EUR move in the export is dated in an earlier year, so it is replayed historically and by design emits none. The rise is the pooled ledger splitting into per-account queues, which is the same cause as the moved figures |
| `InternalCashTransferProcessor` invocations | **zero** — the tax-year path that emits the disposal and the acquisition is not reached on this data, and has unit-test evidence only. What the move does here is relocate the balance during the replay, which changes the basis of every later disposal from it |
| `REPLAY_MARK_UNCONFIRMED_START` | 1, the same instrument and interval as before |
| `CURRENCY_EOY_MISMATCH` | absent on both, so per-account reconciliation did not reopen what the previous change closed |
| `MULTI_ACCOUNT_LIMITATIONS` and its console banner | gone |

**Every movement is a currency figure, and no securities or fund figure moves at all.** That is
what per-account lot selection on currency alone should do; anything else would have been a defect.
Gross gains and gross losses both rising is the signature of a pooled position being split: a
disposal that netted against another account's cheaper balance now has its own basis on each side.

### A hole this change makes per-account, found by review

The sub-0.01 threshold in `_process_cash_balance_positions` drops a cash-report row whose opening
and closing balances are both dust. A dropped row is not merely unreported: the ledger it would
have belonged to is then reconciled against nothing at the start of the year and checked against
nothing at the end.

| Export year | non-EUR (account, currency) rows | dropped by the threshold |
|---|---|---|
| 2022 | 5 | 1 |
| 2023 | 9 | 2 |
| 2024 | 11 | 6 |
| 2025 | 13 | 7 |

Instrumented on the VZ 2025 run, head tree: **7 of the 13 currency ledgers have no reported
balance to compare against**, and on the base tree 4 of 9. Six of the seven hold dust. **One does
not**: a ledger in the second account ends the year holding about 36 units of a currency whose
reported balance is effectively zero, and nothing says so on either tree.

**The threshold predates this change and so does the hole.** What this change does is make it
per (account, currency) rather than per currency, which is why the count rises. It is not closed
here — neither lowering the threshold nor adding a person-level backstop is currency-per-account
work, and both move figures of their own. The map row for [GT-FX-009] says the condition exists
rather than claiming it does not; an earlier draft of that row said "incidence measured: zero",
which was true of a different question (every row states both ends) and false of this one.

### Suite

Full suite 1201 passed, 1 failed — `test_the_column_tuples_match_the_real_exports`, which fails
identically on `origin/main`. Clean clone by the exact command in `CLAUDE.md`: **1207 passed,
1 skipped**.

## 2026-08-07

**Supersedes the 2026-08-06 row reading "2024 | aborts on
`VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN`".** Issue #56 — the root cause recorded below — is
fixed on this branch by `efb0d97` (a historical merger applies at its own date) and `13f6b6d`
(reconcile at every yearly snapshot). **VZ 2024 no longer aborts there.**

| VZ | Result |
|---|---|
| 2023 | **runs clean**, and declares **no Vorabpauschale**: it carries calendar 2022, whose Basiszins was −0.05 % — negative, so none arises. Zeilen 9–13 all zero. |
| 2024 | aborts **earlier than before**, during classification |
| 2025 | aborts during classification |

**Both remaining runs stop on the same instrument** — `CONID:69067924` / `XAUUSD` / `CMDTY` has
category `UNKNOWN` and cannot be auto-classified, so `DataIntegrityError` fires before any figure
is produced. The classification it needs is Q11 Reading C, a sonstige Kapitalforderung under
§ 20 Abs. 2 Satz 1 Nr. 7, and no such category exists: **issue #53.** VZ 2024 and VZ 2025 are also
the first two years in which a Vorabpauschale can be non-zero at all.

**But #53 is not the only thing between here and those two declarations, and an earlier version of
this entry said it was.** The classification cache was rebuilt on 2026-08-07 against a VZ 2023 run,
so it covers that year's instruments and no others. Measured by comparing cache keys against the
instruments each year's window contains:

| VZ | instrument keys in window | not in cache | composition of the uncached |
|---|---|---|---|
| 2023 | 169 | **0** | — |
| 2024 | 265 | **96** | 68 `OPT`, 24 `STK`, 1 `CMDTY`, 1 `CASH`, 2 blank |
| 2025 | 408 | **239** | 175 `OPT`, 58 `STK`, 1 `CMDTY`, 3 `CASH`, 2 blank |

Only about three per year refuse outright and stop the run. **The quieter risk is the `STK`
rows:** they auto-classify to `STOCK` without prompting, and this account's fund descriptions
contain no "ETF" marker, so a fund among them is silently declared as a share — wrong form lines
and no Teilfreistellung, with nothing failing. Both years therefore need an interactive
classification pass, not just #53.

**Not re-verified, and not claimed:** whether the Swiss Gold Vorabpauschale chain is now clean.
The run stops before reaching it.

**The input carries no duplicate trade rows.** Measured across `Trades-2021.csv` …
`Trades-2025.csv`: 6 976 rows, 6 976 distinct `TransactionID`s, none repeated within a file or
across files. A working note had described the VZ 2024 failure as caused by "duplicated 2022 trade
rows"; that is wrong, and the 2026-08-06 entry below already states the correct mechanism —
phantom units from replay *ordering*, not from the input.

**Classification cache.** Destroyed on this date by the clean-clone protocol
(`rm -rf cache`, see issue #51) and rebuilt by the maintainer. `XAUUSD` was not reclassified,
which is why the two aborts above are reachable. No other run state was lost.

## 2026-08-06

**Supersedes the 2026-08-05 statement that "VZ 2023 cannot be computed and VZ 2022 cannot be run
at all."** The snapshots called absent that day are present in `data_import/` now, and the
picture has moved. Measured by running the full pipeline for each year and reading the logs; the
working tree carried unrelated in-flight Vorabpauschale changes at the time.

| VZ | Result |
|---|---|
| 2021 | cannot be run — `Positions-2020-EoY.csv` absent, and it is the opening position |
| 2022 | aborts on `VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING` (needs `Positions-2021-SoY.csv`) |
| 2023 | **runs clean** |
| 2024 | aborts on `VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN` |
| 2025 | **runs clean** |

**How far back the ledger depends on data we do not have.** The 2021-01-01 opening quantities
were derived (EoY-2021 snapshot minus every 2021 trade, corporate action and option
exercise/expiry) and real FIFO replayed over every observed event. Five securities carried a
pre-2021 tranche; four clear during 2021, the last on **2022-04-07**. Sixteen option contracts
open at 2021-01-01 all expired by 2021-07-23. From 2022-04-07 every lot in every securities
ledger traces to a recorded trade, so **VZ 2023 is the first assessment year whose opening lots
are all observed** — which is the measurement behind the VZ 2023 floor now stated in `CLAUDE.md`.

Currency ledgers are a separate matter: they take a `SOY_RECONCILIATION_*` plug lot dated
`{tax_year-1}-12-31` whenever cash FIFO disagrees with the reported balance, by design and every
year. Two currencies still carry a constant residual in VZ 2025.

**The VZ 2024 abort is a defect, not a data gap.** A stock-for-stock merger delivers its lots
after every trade in the historical window, so shares sold on the merger date oversell against a
ledger that does not hold them yet; the reconstruction ends up over the reported SoY by exactly
the transferred quantity, reconciliation discards it, and the synthesised lot has no real
acquisition date for § 18 Abs. 2 InvStG. Filed as issue #56. This one is independent of the
pre-2021 gap and would fire on any merger whose shares are disposed of inside the replay window.

## 2026-08-05

**Ledger reconciliation** (`validate_ledgers.py`), 3 assessment years tested:

| VZ | Result | Assets | RGL records |
|---|---|---|---|
| 2023 | **FAIL** — expected | — | — |
| 2024 | **PASS** | 276 | 6 346 |
| 2025 | **PASS** | 421 | 4 128 |

**Asset EOY mismatches: 0.** The SoY → EoY invariant holds on real input for every year that can
be computed.

**Currency EOY mismatches: 0 — and that verdict is vacuous for VZ 2024.** A cash-balance export
exists for 2025 only, so for 2024 the currency check has nothing to compare the ledger against and
reports zero because it compared nothing. Read the currency result as meaningful for VZ 2025 and
as *unmeasured* for VZ 2024. Supplying `Cash_Balance-2024.csv` would make it real.

### Provenance of the position snapshots

`Positions-2023-*` and `Positions-2024-*` were recovered from older working trees on 2026-08-03
and identified **by content, not by filename** — filenames in those trees are unreliable, one
labelled as end-of-2024 being in fact end-of-2025. The verification anchor was that the recovered
EoY-2024 matches the authoritative `Positions-2025-SoY.csv` symbol for symbol.

**No snapshot exists anywhere for end-2021 / start-2022.** That is why VZ 2023 cannot be computed
and why VZ 2022 cannot be run at all, and it is a property of the available input rather than
something a code change can fix.

VZ 2023 fails on `VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING` and the failure is correct: the
Vorabpauschale declared in VZ 2023 is the one computed for calendar 2022 (§ 18 Abs. 3 InvStG), and
the 2022 position snapshots are genuinely absent from the input. This is a data gap, not a defect.
Supplying `Positions-2022-SoY.csv` and `Positions-2022-EoY.csv` would close it.

Until this run the validator had been unable to validate any year since 2026-08-03; it called the
pipeline without the prior-year snapshot paths and reported the cause as missing files.

**Output parity**, German-KESt fix on Anlage KAP Zeile 41:

| Capture | Result |
|---|---|
| Control, same tree twice, VZ 2024 | console, log and PDF IDENTICAL |
| Pre- vs post-fix, **VZ 2024** | 3 console lines changed — intended |
| Pre- vs post-fix, **VZ 2025** | console and PDF IDENTICAL |

VZ 2024 moves exactly as designed: Zeile 41 falls by the amount of one withholding row identified
as German Kapitalertragsteuer, and a data-gap line appears naming that amount and the
Steuerbescheinigung requirement. The reduction equals the excluded row to the cent. VZ 2025 does
not move, because every withholding row that year carries a non-German issuer country and is
correctly retained as foreign tax.

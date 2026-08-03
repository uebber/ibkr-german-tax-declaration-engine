# Legal implementation map

What this engine does about each legal requirement in `reference/`, which module does it, and
which tests would notice if it stopped.

## How to read this

`reference/` states law and nothing else — that is the Purity Rule in CLAUDE.md, and
`tests/test_reference_purity.py` enforces it. **This file is the other side of that split.** Every
normative requirement in the store carries a claim ID tagged on its heading (`GT-<AREA>-<NNN>`),
and every one of those IDs has exactly one row here. The test asserts both directions: a claim
with no row fails, and a row citing a claim that does not exist fails.

The **Position** column takes one of four values, and the distinction matters more than it looks:

| Position | Meaning |
|----------|---------|
| **implements** | The engine acts on the requirement and the result is intended to be correct. |
| **deviates** | The engine does something the requirement does not sanction. A known defect, stated as one. |
| **not reached** | The requirement is real but nothing in the input can trigger it. Not a defect; a scope boundary. |
| **out of scope** | The requirement addresses a taxpayer or asset this engine is not built for. |

**"not reached" is a claim about the input, and it can go stale.** It means no supported input
produces the event today — not that the event is impossible. When a new input type or asset class
is added, the "not reached" rows are the ones to re-check first.

Where a claim is an **open question**, this file records the reading that was chosen and why.
Both readings and their authorities stay in `reference/research/open-legal-questions.md`. Choosing
is an implementation act; it does not belong in the store.

---

## Anlage KAP — § 20 EStG

### Abs. 1 — current income

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG20-001 | implements | `src/parsers/domain_event_factory.py` → `DIVIDEND_CASH` → `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE` | `test_dividend_handling.py` | Component of Zeile 19. |
| GT-ESTG20-002 | implements | `src/domain/enums.py` `ANLAGE_KAP_INV_*`; `src/engine/loss_offsetting.py` keeps the KAP-INV pool separate | `test_group6_loss_offsetting.py::TestLossOffsettingFundIsolation` | The hook that sends fund income to Anlage KAP-INV rather than KAP. |
| GT-ESTG20-003 | implements | `INTEREST_RECEIVED` → `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE` | `test_group11_cashflow_currency.py` | |
| GT-ESTG20-004 | implements | `src/engine/event_processors/`, short option paths | `test_options_lifecycle.py` | Premium taxed on receipt; Glattstellung booked at payment date. **Open question Q4** — see below. |
| GT-ESTG20-010 | not reached | — | — | Besondere Entgelte und Vorteile. No broker input maps to one. |
| GT-ESTG20-021 | out of scope | — | — | Subsidiarity. Everything here assumes Privatvermögen; the engine has no Betriebsvermögen concept. |

**GT-ESTG20-004, open question Q4 — reading chosen: payment date, in every year.** The paid
Glattstellungsprämie is booked as negative income when paid. Reason: it matches the JStG-2024
statutory wording and the administration's practice before it (BMF 18.01.2016 Rz. 25 ff.). It is
contrary to BFH VIII R 27/21 for any VZ before the amendment took effect, and no § 52 EStG
application rule for Nr. 11 has been located. **A Stillhalter/Glattstellung pair straddling a year
end in VZ 2024 or earlier should be reviewed by hand.**

### Abs. 2 — disposals

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG20-005 | implements | `LONG_POSITION_SALE` / `SHORT_POSITION_COVER` on `STOCK` → `ANLAGE_KAP_AKTIEN_GEWINN` / `_VERLUST` | `test_fifo_groups.py`, `test_group6_loss_offsetting.py` | Zeilen 20 and 23. |
| GT-ESTG20-006 | not reached | — | — | Sale of a Dividenden-/Zinsschein detached from the Stammrecht. No event kind, and no broker input produces one. |
| GT-ESTG20-007 | implements | option and CFD close/expiry/settlement paths | `test_options_lifecycle.py`, `test_futures.py`, `test_console_reporter_derivatives.py` | Routed by `get_form_rules(tax_year)` — Zeile 21/24 up to VZ 2024, merged into 19/22 from VZ 2025. |
| GT-ESTG20-008 | implements | bond disposals; currency disposals via `FX_*` realization types | `test_bond_maturity.py`, `test_group7_currency_fifo.py` | |
| GT-ESTG20-009 | implements | IBKR corporate action `BM` → synthetic sell → `LONG_POSITION_SALE` | `test_bond_maturity.py::TestBondMaturity` | The Einlösung fiction is what makes a redemption at maturity a disposal at all. |

### Abs. 4 — gain calculation and lot identification

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG20-011 | implements | `src/engine/fifo_manager.py` | `test_precision.py`, `test_fifo_groups.py` | Proceeds − costs − basis, all `Decimal` at `INTERNAL_CALCULATION_PRECISION`. |
| GT-ESTG20-012 | implements | `src/engine/fifo_manager.py` — FIFO lot consumption | `test_fifo_groups.py`, `tests/docs/spec_fifo.md` | Mandatory fiction; no specific-identification alternative is offered. |
| GT-ESTG20-013 | **deviates** | `src/engine/ledger_views.py`, `src/utils/account_utils.py` | `test_ledger_views.py`, `test_multi_account_harness.py` | See below. |
| GT-ESTG20-014 | not reached | — | — | Own-depot transfer is not a disposal. No input represents one; a per-depot implementation would have to relocate lots rather than close and reopen them. |

**GT-ESTG20-013 — known deviation.** The ledger registries are keyed by `(account_key, asset_id)`,
but every write uses a single `DEFAULT_ACCOUNT` constant and no account identifier is read
anywhere in `src/engine/`, `src/domain/` or `src/processing/`. The key is a seam; FIFO is pooled
across accounts. **This deviates from BMF Rz. 97 Satz 2.** It has no effect where the input covers
a single depot, because per-depot and pooled FIFO coincide then. For a taxpayer holding one ISIN
in two accounts the pooled result is wrong.

**Open question Q2 — reading chosen: not reached.** Whether the *"einzelnes Depot"* boundary
transposes to a foreign broker's sub-accounts is unresolved, and the engine is account-agnostic,
so it does not take a position either way. The deviation above is separate from, and prior to,
that question: pooling is wrong under both readings.

### Abs. 4a — corporate actions

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG20-015 | implements | `CORP_MERGER_STOCK` → tax-neutral basis transfer (FIFO drain/receive) | `test_stock_merger_fifo.py`, `test_historical_merger_replay_guard.py` | Cash consideration is handled separately as `CORP_MERGER_CASH` → `CASH_MERGER_PROCEEDS`. |
| GT-ESTG20-016 | **deviates** | `CORP_STOCK_DIVIDEND` → new shares at EUR 0 basis | `test_stock_merger_fifo.py` (adjacent coverage only) | Satz 5 is the *residual* case, conditional on Sätze 3, 4 and 7 not applying. The engine applies the EUR 0 treatment without testing those three conditions. |
| GT-ESTG20-017 | not reached | — | — | Abspaltung. No corporate-action type maps to it. |
| GT-ESTG20-018 | not reached | — | — | Timing by Einbuchung date. The engine uses the corporate action's reported date; no input distinguishes the two. Note Satz 6 governs Sätze 1–5 only, not the Satz 7 Abspaltung. |
| GT-ESTG20-019 | not reached | — | — | Wandel-/Umtauschanleihen. |
| GT-ESTG20-020 | not reached | — | — | Bezugsrechte. |

### Abs. 6 — loss offsetting

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG20-030 | implements | `src/engine/loss_offsetting.py` — capital income pooled apart from § 23 | `test_group6_loss_offsetting.py` | |
| GT-ESTG20-031 | out of scope | — | — | Carryforward to later VZ is the Finanzamt's step; the engine reports one year. |
| GT-ESTG20-032 | out of scope | — | — | Spousal pooling happens at Veranlagung across both spouses' returns. |
| GT-ESTG20-033 | implements | `src/engine/loss_offsetting.py` — Aktienverlusttopf kept separate | `test_group6_loss_offsetting.py::TestLossOffsettingFromSpec` | Zeile 23 apart from Zeile 22. |
| GT-ESTG20-034 | not reached | — | — | Bescheinigung under § 43a Abs. 3 Satz 4 applies to losses that bore Kapitalertragsteuer. Foreign-broker income bears none. |
| GT-ESTG20-035 | implements (as repealed) | `src/tax_law/registry.py` — `derivative_loss_cap_applies` is `False` in **every** year entry | `test_tax_law_registry.py::TestFormYearRules::test_cap_repealed_for_every_configured_year`, `test_group6_loss_offsetting.py::TestLossOffsettingDerivativeCapRepealed` | |
| GT-ESTG20-036 | implements (as repealed) | same | same | |
| GT-ESTG20-037 | implements | the two rows above | same | *"Alle offenen Fälle"* means no assessment year applies the cap — not that it applies before 2025. |
| GT-ESTG20-060 | — | — | — | Version history of the BMF circular. Bibliographic, no engine position. |

---

## Anlage KAP — form structure

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-FORM-001 | implements | everything routes to Zeile 19 | `test_group6_loss_offsetting.py` | Correct **because the broker is foreign**. A German Zahlstelle would need Zeile 18; nothing implements that. |
| GT-FORM-002 | implements | `src/engine/loss_offsetting.py:249-275` | `test_group6_loss_offsetting.py` | Zeile 19 is a net figure; Zeilen 20/22/23 restate parts of it. |
| GT-FORM-003 | **deviates** | — | — | **Zeile 25 has no representation.** Forderungsausfall and wertlose Ausbuchung losses fall into `ANLAGE_KAP_SONSTIGE_VERLUSTE` (Zeile 22), which the 2024 Anleitung expressly forbids — *"ausschließlich in Zeile 25"*. No input in the maintainer's data produces such a loss today, so the path is unexercised, but nothing detects one if it appears. |
| GT-FORM-004 | **deviates** | — | — | Same shape: a worthless-share write-off should go to Zeile 23 in VZ 2025, and there is no event kind for it. |
| GT-FORM-005 | not reached | — | — | Nothing is written to Zeilen 21/24 for VZ 2025 under either reading, so no figure turns on the open question. See Q3. |
| GT-FORM-006 | implements | `ANLAGE_KAP_FOREIGN_TAX_PAID` — sum of withholding events | `test_withholding_tax_linker.py` | Neither ceiling is applied; the Finanzamt applies § 32d Abs. 5 Sätze 1 and 3. See GT-CREDIT-005/006. |
| GT-FORM-007 | **deviates** | — | — | See GT-CREDIT-025. Zeilen 7/37/38/39 have no representation. |
| GT-FORM-008 | out of scope | — | — | Zeile 4 (Günstigerprüfung) and Zeile 5 (Überprüfung des Steuereinbehalts) are taxpayer elections, not computed figures. |
| GT-FORM-009 | implements | classification decides the Anlage | `test_futures.py::TestFuturesClassification`, `test_section23_holding_period.py` | Fund → KAP-INV, private sale asset → SO, Einlagenrückgewähr (`CAPITAL_REPAYMENT`) → not taxable. |
| GT-FORM-010 | implements | `src/tax_law/registry.py` `FormYearRules(separate_derivative_lines=True)` for 2021 and 2024 | `test_tax_law_registry.py::TestFormYearRules` | |
| GT-FORM-011 | implements | `FormYearRules(separate_derivative_lines=False)` for 2025 | `test_tax_law_registry.py::TestFormYearRules::test_2024_vs_2025_form_structure` | |
| GT-FORM-012 | implements | `src/tax_law/registry.py:139-145` — 2021 is the earliest entry; earlier years **raise** | `test_tax_law_registry.py::test_years_before_the_earliest_verified_form_raise`, `test_every_configured_year_2021_to_2023_matches_2024` | Backward projection refused because Zeilen 21/24 were *frei* on the VZ 2020 form. Forward carry-over is a deliberate silent default. |

**`FormYearRules`** (`src/tax_law/registry.py`, re-exported by `src/reporting/form_rules.py`) is
the single place year-specific form structure lives. Entries for **2021** (covering 2021–2023 by
forward carry-over), **2024** and **2025**. Only `separate_derivative_lines`,
`z19_subtracts_derivative_losses` and `z22_includes_derivative_losses` vary by year;
`derivative_loss_cap_applies` is `False` throughout.

---

## Anlage KAP-INV — InvStG

### § 16 — what fund income is

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-INVSTG-001 | implements | `DISTRIBUTION_FUND`, Vorabpauschale computation, fund disposals | `test_vorabpauschale.py`, `test_group6_loss_offsetting.py::TestLossOffsettingFundIsolation` | All three limbs of Abs. 1. |
| GT-INVSTG-002 | implements | `src/domain/enums.py` `ANLAGE_KAP_INV_*` categories | `test_vorabpauschale.py::TestGetVpReportingCategory` | |
| GT-INVSTG-003 | not reached | — | — | Disapplication of § 3 Nr. 40 EStG / § 8b KStG. Neither is in the computation to begin with. |
| GT-INVSTG-004 | out of scope | — | — | Altersvorsorge contracts and DBA-Freistellung of a foreign fund's distribution. |
| GT-INVSTG-005 | implements | gross figures per fund type; no Teilfreistellung applied to the declared amount | `test_vorabpauschale.py`, `test_group6_loss_offsetting.py` | |

### § 18 — Vorabpauschale

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-INVSTG-010 | implements | `_calculate_vorabpauschale()` in `src/engine/calculation_engine.py` | `test_vorabpauschale.py::TestVorabpauschaleCalculation` | Sätze 1–3: Basisertrag, the value-gain cap, and the distribution subtraction. |
| GT-INVSTG-011 | **deviates** | — | — | **Abs. 2 pro-rata is not implemented.** The engine computes only for units held at the start of the calendar year, so units acquired during the year produce *nothing* where Abs. 2 gives up to eleven twelfths. Understates deemed income in an acquisition year. |
| GT-INVSTG-012 | implements | `VorabpauschaleData.vorabpauschale_year` and `.declaration_year` | `test_vorabpauschale.py::TestVorabpauschaleDeclarationYear` | The VZ `Y` return carries the Vorabpauschale for calendar `Y-1`. |
| GT-INVSTG-013 | implements | `src/tax_law/registry.py` `BASISZINS_PCT` | `test_tax_law_registry.py::TestBasiszinsLookup` | |
| GT-INVSTG-014 | implements | `Asset.prior_year_*` fields, populated by `src/data_preparation.py` | `test_vorabpauschale.py::TestVorabpauschaleDeclarationYear` | Where the prior year's snapshots are absent and funds are held, the run stops with a `FAIL_FAST` data gap rather than substituting the tax year's own snapshot. |
| GT-INVSTG-015 | implements | gross on Zeilen 9–13 | `test_vorabpauschale.py::TestTeilfreistellungNegativeDistribution` | |
| GT-INVSTG-016 | **choice under uncertainty** | funds with no end-of-year position are skipped | `test_vorabpauschale.py` | See below. |

**GT-INVSTG-010, Satz 4 — partial.** The Rücknahmepreis is the primary measure and a market price
substitutes only where none was set. The engine uses the broker's position mark price
unconditionally, without establishing that no Rücknahmepreis exists for the instrument. Correct
wherever the fund publishes no Rücknahmepreis; **not verified per instrument.**

**GT-INVSTG-016, open question Q5 — reading chosen: no Vorabpauschale in the year of disposal.**
Reason: § 18 Abs. 3 deems the inflow to fall on the first working day of the following year, by
which time the units are gone. This is inferred from the Zuflussfiktion, not stated by any located
Tier 1 or Tier 2 source, and the opposite reading is defensible.

### § 19 — disposal gains

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-INVSTG-030 | implements (partly) | fund disposals → `ANLAGE_KAP_INV_*_GEWINN_GROSS` | `test_group6_loss_offsetting.py::TestLossOffsettingFundIsolation` | Sätze 1–2 implemented. Sätze 3–4 — the Vorabpauschale deduction — are not; see GT-FORM-033. |
| GT-INVSTG-031 | not reached | — | — | A fund leaving the InvStG's scope is not reported in any broker statement. |
| GT-INVSTG-032 | out of scope | — | — | Wegzug and related, gated by a 1 % / EUR 500 000 threshold. |
| GT-INVSTG-033 | implements | `ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z53` in `src/domain/enums.py` | `test_vorabpauschale.py::TestZeile53VorabpauschaleDeduction` | The category names the right line. The figure is not computed — next row. |
| GT-INVSTG-034 | **deviates — reports the gap** | `src/engine/calculation_engine.py` records a data gap on fund disposal | `test_vorabpauschale.py::TestZeile53VorabpauschaleDeduction` | See below. |

**GT-INVSTG-034 / GT-FORM-033 — the Zeile 53 deduction is not computed, deliberately.** There is
no per-lot Vorabpauschale accumulation: `RealizedGainLoss` carries no Vorabpauschale field. The
value formerly emitted was the sum of the *current* year's gross Vorabpauschalen — neither
"während der Besitzzeit" nor restricted to the units disposed of — and it was written to Zeile 55.
Computing it correctly needs each lot's assessed Vorabpauschalen carried across years **together
with evidence they were declared**, which is a multi-year record the engine does not hold. It now
emits no figure and records a data gap when fund units are disposed of, rather than a plausible
wrong number. The deduction must be completed by hand.

### § 20 — Teilfreistellung

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-INVSTG-020 | implements | `registry.teilfreistellung_rate` → 30 % | `test_tax_law_registry.py::TestTeilfreistellung` | Applied to derive net figures for offsetting; the declared figure stays gross. |
| GT-INVSTG-021 | implements | → 15 % | same | |
| GT-INVSTG-022 | implements | → 60 % | same | |
| GT-INVSTG-023 | implements | → 80 % | same | |
| GT-INVSTG-024 | implements | → 0 % | same | |
| GT-INVSTG-025 | out of scope | — | — | Betriebsvermögen rates. |
| GT-INVSTG-026 | **not implemented — human input** | `src/classification/asset_classifier.py:25-29` | — | See below. |
| GT-INVSTG-027 | **not implemented — human input** | same | — | Mischfonds is *mindestens 25 %*, inclusive, where Aktienfonds is *mehr als 50 %*, exclusive. |
| GT-INVSTG-028 | not reached | — | — | The 51 % look-through for fund-of-funds. Nothing computes a quota. |
| GT-INVSTG-029 | **not implemented — human input** | same | — | |
| GT-INVSTG-019 | out of scope | — | — | Teilfreistellung on proof of the actual quota is an application in the assessment. |

**GT-INVSTG-026/027/029 — the engine does not classify funds; a person does.** Fund type comes
from interactive classification or the classification cache
(`src/classification/asset_classifier.py`), and **no quota is computed anywhere.** The thresholds
therefore constrain the human making the choice, not any code path. This is why the *">= 51 %"*
error corrected on 2026-08-03 was figure-changing even though no code changed: it would have led
someone to classify a fund at 50.5 % as Sonstiger Fonds (0 %) when it is an Aktienfonds (30 %).

### § 22 — change of the applicable rate

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-INVSTG-040 | not reached | — | — | A change of Teilfreistellungssatz triggers a deemed disposal and reacquisition. No input signals a fund's type changing; the classification cache would simply be edited, silently. |
| GT-INVSTG-041 | out of scope | — | — | Lapse of a § 20 Abs. 4 proof. |
| GT-INVSTG-042 | not reached | — | — | The Rücknahmepreis to use for the fiction. |

**GT-INVSTG-040 is the sharpest of the "not reached" rows.** Editing a fund's cached
classification changes the Teilfreistellung applied from that run onward, with no deemed disposal
and no reacquisition — which is what § 22 Abs. 1 Satz 1 requires if the *applicable rate* actually
changed. Reclassifying to correct a past mistake is a different thing from a rate that changed,
and nothing distinguishes them.

### Basiszins (BMF, under § 18 Abs. 4)

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-INVSTG-050 | implements | `src/tax_law/registry.py` `BASISZINS_PCT` — law as data, not configuration | `test_tax_law_registry.py::TestBasiszinsReferenceConsistency` | **The consistency test parses the table out of `reference/bmf-guidance/basiszins-vorabpauschale.md` and asserts the registry equals it row for row.** The doc is authoritative; the code follows. |
| GT-INVSTG-051 | implements | `vorabpauschale_year = tax_year - 1` | `test_vorabpauschale.py::TestVorabpauschaleDeclarationYear` | |
| GT-INVSTG-052 | out of scope | — | — | How the Bundesbank derives the rate. |
| GT-INVSTG-053 | implements | `registry.basiszins_pct()` distinguishes the two cases | `test_tax_law_registry.py::TestBasiszinsLookup` (all four tests), `test_vorabpauschale.py::TestBasiszinsTableCoverage` | Pre-2018 → INFO, nothing missed. 2018 or later and absent → **WARNING**, because skipping would understate deemed income. 2021/2022 are negative *values*, not gaps. |

---

## Anlage SO — § 23 EStG

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG23-001 | implements | assets classified `PRIVATE_SALE_ASSET` | `test_section23_holding_period.py::TestSection23LedgerClassification` | |
| GT-ESTG23-002 | implements | the broker's trade date is used, never the settlement date | `test_section23_holding_period.py` | Trade date is when the contract became binding — the obligatorisches Geschäft the rule points at. |
| GT-ESTG23-003 | implements | `is_within_section23_speculation_period()` in `src/tax_law/holding_period.py` | `test_section23_holding_period.py::TestSpeculationPeriodRule`, `test_section23_holding_period_guards.py` | Anniversary arithmetic per §§ 187/188 BGB, implemented once and called from the three `FifoLedger` disposal paths. A `days <= 365` shortcut is wrong across a 29 February and is not used. |
| GT-ESTG23-004 | **choice under uncertainty** | `src/tax_law/holding_period.py` | `test_section23_holding_period.py::TestSpeculationPeriodRule` | See below. |
| GT-ESTG23-005 | **deviates** | — | — | **The ten-year period is not implemented**; one year is applied unconditionally. Idle for the instruments currently classified `PRIVATE_SALE_ASSET`, which produce no income from the asset itself — but that is a property of those instruments, not a safeguard. Adding an income-producing "anderes Wirtschaftsgut" makes this wrong. |
| GT-ESTG23-006 | **deviates** | `consume_short_lots_for_cover` in `src/engine/fifo_manager.py` | — | Nr. 3 has **no holding period**. The engine applies the Nr. 2 Jahresfrist to a short cover, so a short held longer than a year would be reported exempt where Nr. 3 makes it taxable. Unexercised — no sell-to-open on any `PRIVATE_SALE_ASSET` in the maintainer's data (checked 2026-08-02) — and wrong if reached. |
| GT-ESTG23-007 | not reached | — | — | Inherited or gifted assets carry the predecessor's acquisition date. No input represents an unentgeltlicher Erwerb. |
| GT-ESTG23-008 | implements | `src/engine/fifo_manager.py` | `test_section23_holding_period.py` | |
| GT-ESTG23-009 | out of scope (deliberate) | — | — | The Freigrenze applies to the taxpayer's *total* private-sale gain for the year, which one portfolio cannot establish. The engine reports the gross figure and leaves the threshold to the taxpayer and the Finanzamt. |
| GT-ESTG23-010 | implements | `src/engine/loss_offsetting.py` — § 23 pool separate from § 20 | `test_group6_loss_offsetting.py` | Carryback and carryforward are the Finanzamt's step. |
| GT-ESTG23-011 | **not implemented — human input** | `src/classification/asset_classifier.py:30` | — | Whether an instrument is a § 23 asset comes from classification, not from any property the engine reads. A cash-settled ETC may well be a Kapitalforderung under § 20 instead. |
| GT-ESTG23-012 | implements | `SECTION_23_ESTG_TAXABLE_GAIN` / `_TAXABLE_LOSS` / `_EXEMPT_HOLDING_PERIOD_MET` | `test_section23_holding_period_guards.py::TestSpeculationPeriodFlagIsTruthful` | Dates that cannot decide the question raise `ProcessingError` rather than defaulting to exempt — an undecidable § 23 case is unreported income, not tax-free income. |

**GT-ESTG23-004, open question Q1 — reading chosen: no extension.** The period ends on the
anniversary day whatever weekday it falls on. Reasons: it follows FG Köln 02.06.1997, the only
§ 23-specific authority located, and what the commentary describes as practice; and the extension
reading would make the Jahresfrist depend on a Land-specific Feiertagskalender, itself an
unresolved input. **This is a choice between two defensible readings** — BFH IX R 68/98 points the
other way — and it changes a declared figure. A disposal falling between a weekend or holiday
anniversary and the next working day should be reviewed by hand.

### Anlage SO form structure

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-FORM-020 | implements | § 23 gains and losses → Zeile 54 | `test_section23_holding_period.py` | |
| GT-FORM-021 | out of scope | — | — | Same as GT-ESTG23-009. |
| GT-FORM-022 | implements | separate § 23 pool | `test_group6_loss_offsetting.py` | |
| GT-FORM-023 | **choice under uncertainty** | `src/engine/fifo_manager.py` applies FIFO to § 23 assets | `test_section23_holding_period.py` | See below. |

**GT-FORM-023, open question Q6 — reading chosen: FIFO.** § 23 contains no lot-identification
rule, and § 20 Abs. 4 Satz 7 is confined by its wording to *vertretbare Wertpapiere* in
Sammelverwahrung, so it does not reach an "anderes Wirtschaftsgut". FIFO is applied for
consistency with the § 20 treatment and because it is the conservative ordering in a rising
market. **No source supports it.** Until 2026-08-03 the store asserted this was "the general
principle applied by the Finanzverwaltung", which was unsourced. The ordering decides which
acquisition date is compared with the disposal date, so it can decide taxability outright.

---

## Anlage KAP-INV form structure

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-FORM-030 | implements | `ANLAGE_KAP_INV_*_AUSSCHUETTUNG_GROSS`, one per fund type | `test_vorabpauschale.py::TestGetVpReportingCategory` | Zeilen 4–8. |
| GT-FORM-031 | implements | `ANLAGE_KAP_INV_*_VORABPAUSCHALE_BRUTTO` | `test_vorabpauschale.py` | Zeilen 9–13, carrying the **prior** calendar year's Vorabpauschale. |
| GT-FORM-032 | implements | `ANLAGE_KAP_INV_*_GEWINN_GROSS` | `test_group6_loss_offsetting.py::TestLossOffsettingFundIsolation` | Zeilen 14/17/20/23/26. |
| GT-FORM-033 | **deviates** | — | `test_vorabpauschale.py::TestZeile53VorabpauschaleDeduction` | See GT-INVSTG-034. |
| GT-FORM-034 | implements | gross figures throughout | `test_vorabpauschale.py`, `test_group6_loss_offsetting.py` | Teilfreistellung is used internally for offsetting, never applied to a declared amount. |

**Not produced at all:** Zeilen 15/18/21/24/27 (bestandsgeschützte Alt-Anteile, § 56 Abs. 6 Satz 1
Nr. 2 InvStG) and Zeilen 16/19/22/25/28 (fiktive Veräußerung of non-bestandsgeschützte Alt-Anteile
at 31.12.2017). Both need pre-2018 data the engine has no source for — an acquisition date before
01.01.2009, and a 31.12.2017 valuation. A taxpayer holding such units must complete these by hand.

---

## Foreign tax credit and withholding — §§ 32d, 34c, 34d, 36, 45a

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-CREDIT-001 | out of scope | — | — | The 25 % rate is applied by the Finanzamt. The engine produces pre-tax figures. |
| GT-CREDIT-002 | implements (as premise) | the whole pipeline | — | Every figure the engine produces exists *because* of Abs. 3: foreign broker, no inländische Zahlstelle, no Steuerabzug, so the income must be declared. |
| GT-CREDIT-003 | not reached | — | — | There is no Steuereinbehalt on foreign-broker income to review. |
| GT-CREDIT-004 | implements | withholding events summed into `ANLAGE_KAP_FOREIGN_TAX_PAID` | `test_withholding_tax_linker.py` | |
| GT-CREDIT-005 | out of scope | — | — | The per-Kapitalertrag 25 % ceiling is applied by the Finanzamt. |
| GT-CREDIT-006 | out of scope | — | — | The per-VZ ceiling likewise. |
| GT-CREDIT-007 | out of scope | — | — | Günstigerprüfung is a taxpayer election (Zeile 4). |
| GT-CREDIT-010 | out of scope | — | — | Definitional scope of § 34d. |
| GT-CREDIT-011 | not reached | — | — | The Schuldner-domicile test has no expression on the declaration for a foreign-broker portfolio under Abgeltungsteuer. |
| GT-CREDIT-012 | not reached | — | — | The § 34c carve-out is why no per-country computation is needed. Nothing to implement. |
| GT-CREDIT-013 | not reached | — | — | Günstigerprüfung stays inside the carve-out, so it does not restore a per-country mechanism either. |
| GT-CREDIT-014 | **deviates (silently)** | — | — | Withholding is treated as foreign without testing the debtor's domicile by any proxy. This is the same defect as GT-CREDIT-025, seen from the § 34d side. |
| GT-CREDIT-020 | not reached | — | — | German KESt is withheld upstream, not by the broker. |
| GT-CREDIT-021 | **deviates** | — | — | Zeilen 7/37/38/39 have no representation. |
| GT-CREDIT-022 | **deviates** | — | — | The Steuerbescheinigung requirement is not surfaced. Without a certificate the credit is barred by § 36 Abs. 2 Satz 2, and the report says nothing about it. |
| GT-CREDIT-023 | not reached | — | — | That the certificate is obtainable on request is a fact about the broker, not a computation. |
| GT-CREDIT-024 | not reached | — | — | § 36a Cum/Cum, with a EUR 20 000 Bagatellgrenze. |
| GT-CREDIT-025 | **deviates — KNOWN DEFECT** | `src/engine/loss_offsetting.py` | — | See below. |

**GT-CREDIT-025 / GT-CREDIT-021 / GT-CREDIT-022 / GT-CREDIT-014 — one defect, four claims.**

`src/engine/loss_offsetting.py` sums **every** withholding event into
`ANLAGE_KAP_FOREIGN_TAX_PAID` (Zeile 41) with **no country filter**, and the engine has no
representation of Zeilen 7, 37, 38 or 39 at all. German Kapitalertragsteuer withheld upstream on a
German issuer's dividend is therefore declared as anrechenbare *ausländische* Steuer, on the wrong
line and through the wrong credit mechanism.

Confirmed against real data: German-issuer dividends held at a foreign broker carry withholding
rows whose amount is **exactly 26.375 % of the gross** — 25 % KESt plus 5.5 % SolZ on the tax.
That arithmetic is the signature to key a fix on; no DBA rate produces it. Several issuers across
several assessment years match. Issuer names and amounts are account data and stay in the
maintainer's gitignored notes.

To fix, three things are needed together:
1. classify withholding by issuer country or by the 26.375 % signature rather than treating all of
   it as foreign;
2. add Zeile 7 (certified gross income), 37 (KESt), 38 (SolZ), 39 (KiSt);
3. tell the user to obtain a Steuerbescheinigung — without it § 36 Abs. 2 Satz 2 bars the credit
   outright, so the figure is worthless without the document.

---

## Foreign currency

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-FX-001 | implements | `FX_CONVERSION_SALE`, `FX_CONVERSION_SHORT_COVER`, `FX_IMPLICIT_SECURITY_PURCHASE`, `FX_IMPLICIT_SECURITY_SALE`, `FX_IMPLICIT_CASHFLOW_EXPENSE`, `FX_IMPLICIT_CASHFLOW_INCOME` → `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE` / `_VERLUSTE` | `test_group7_currency_fifo.py`, `test_group9_variable_fx.py`, `test_group11_cashflow_currency.py`, `test_fx_rgl_hardening.py` | All currency balances are treated as § 20; see Q7. |
| GT-FX-002 | not reached | — | — | Non-interest-bearing accounts. A margin brokerage account pays or charges interest on balances, so the § 23 branch is not exercised — **but nothing tests the account's actual character.** |
| GT-FX-003 | not reached | — | — | Pure payment accounts. |
| GT-FX-004 | not reached | — | — | Retroactivity to VZ 2009 and the 2025 bank withholding duty both concern German Zahlstellen. |
| GT-FX-005 | **choice under uncertainty** | as GT-FX-001 | same | § 20 throughout. Reason: the administrative position, and a margin account's balances bear interest. The § 23 reading would make gains after a year tax-free, so the choice is not conservative in the taxpayer's favour — it is the one that follows the administration. |
| GT-FX-006 | **choice under uncertainty** | short currency positions tracked and taxed symmetrically with long ones | `test_group7_currency_fifo.py` | No guidance addresses a negative balance in Privatvermögen. Symmetry is an assumption. |
| GT-FX-007 | **choice under uncertainty** | currency legs of securities trades measured separately (`FX_IMPLICIT_*`) | `test_group9_variable_fx.py`, `test_group10_options_variable_fx.py` | The conservative reading, and what BMF Rz. 131 is cited for — subject to the sourcing gap recorded in `reference/bmf-guidance/fremdwaehrung-konten.md`. |

**The currency area is the weakest-sourced part of the store and the most heavily implemented part
of the engine.** Four of seven claims are choices under uncertainty, resting on a BMF circular
cited by Randziffer that has never been retrieved. That combination — high implementation
confidence, low source confidence — is worth remembering before treating any FX figure as settled.

**Known blind spot:** per `docs/contribution-standards.md` §3, reversing the chronological order
of every historical currency event leaves the whole suite green. Currency changes must be probed
by mutation, not by running the suite.

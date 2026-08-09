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
statutory wording *and* the administration's practice before it (BMF 18.01.2016 Rz. 25 ff., carried
into 19.05.2022 and 14.05.2025), so the amendment's first year of application cannot change the
result and does not need to be established.

It remains contrary to **BFH VIII R 27/21**, which puts the cost in the year the Stillhalterprämie
was received, as a rückwirkendes Ereignis. That route can be the better outcome or the worse one
depending on which year has losses to absorb, so it is a per-case election rather than a rule the
engine should take. **A Stillhalter/Glattstellung pair straddling a year end should be reviewed by
hand**, and the BFH route considered where the earlier year would use the loss.

*Rescoped 2026-08-07 with Q4 itself: this row previously rested part of its reasoning on "no § 52
EStG application rule for Nr. 11 has been located", which was true and beside the point.*

### Abs. 2 — disposals

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG20-005 | implements | `LONG_POSITION_SALE` / `SHORT_POSITION_COVER` on `STOCK` → `ANLAGE_KAP_AKTIEN_GEWINN` / `_VERLUST` | `test_fifo_groups.py`, `test_group6_loss_offsetting.py` | Zeilen 20 and 23. |
| GT-ESTG20-006 | not reached | — | — | Sale of a Dividenden-/Zinsschein detached from the Stammrecht. No event kind, and no broker input produces one. |
| GT-ESTG20-038 | **not yet reached** (the positive definition) / **implements** (the exclusion) | `AssetCategory.SONSTIGE_KAPITALFORDERUNG`; `src/engine/loss_offsetting.py`, `src/engine/fifo_manager.py` route it to Zeile 19/22 | `test_sonstige_kapitalforderung.py::test_gain_feeds_zeile_19`, `::test_loss_feeds_zeile_22` | **Re-decided 2026-08-07 with issue #53.** Rz. 9's *definition* is still unconsumed: `FXCFD` and `CMDTY` fall through to UNKNOWN and no asset class is mapped to a Termingeschaeft by it. Its *exclusion* — *"Zertifikate und Optionsscheine gehören nicht zu den Termingeschäften"* — has moved from **relied on** to **implements**: a Zertifikat or an unallocated spot metal position can now be classified into a category that lands on Zeile 19/22 and is asserted *not* to reach the Termingeschaeft lines. Two limits stand, and neither is closed by #53: the exclusions still have no IBKR asset class of their own, so **a Zertifikat arriving as `STK` is auto-classified `STOCK` and taxed as a share unless the taxpayer classifies it by hand** — see the note on the interactive pass under Q11 — and the positive definition remains unimplemented. **Re-decided 2026-08-08 by the issue #66 audit; position unchanged.** Rn. 8 f., the cross-reference this Randziffer makes for both exclusions, is now recorded: an Optionsschein is a Kapitalforderung under Satz 1 Nr. 7, the same destination as a Zertifikat. **No warrant has ever been traded on this account**, so nothing is implemented for one and nothing needs to be: a warrant arriving as `OPT` would be declared a Termingeschaeft and would not be put to the taxpayer, which is a defect to fix if one is ever bought, not before. |
| GT-ESTG20-007 | implements | option and CFD close/expiry/settlement paths | `test_options_lifecycle.py`, `test_futures.py`, `test_console_reporter_derivatives.py` | Routed by `get_form_rules(tax_year)` — Zeile 21/24 up to VZ 2024, merged into 19/22 from VZ 2025. |
| GT-ESTG20-008 | implements | bond disposals; currency disposals via `FX_*` realization types | `test_bond_maturity.py`, `test_group7_currency_fifo.py` | **Re-decided unchanged 2026-08-08 by the issue #66 audit**, which reached this row only because Rn. 9's Zertifikat exclusion points here and its Optionsschein exclusion now points here too. Nothing about the claim moved. |
| GT-ESTG20-009 | implements | IBKR corporate action `BM` → synthetic sell → `LONG_POSITION_SALE` | `test_bond_maturity.py::TestBondMaturity` | The Einlösung fiction is what makes a redemption at maturity a disposal at all. |


**Q11 — reading chosen: sonstige Kapitalforderung (Reading C), § 20 Abs. 2 Satz 1 Nr. 7 →
Zeile 19/22.** An unallocated spot precious-metal position held at the broker (no expiry, no
underlying, monthly carrying fee) is **not** a Termingeschaeft. It is treated like a Zertifikat.
Chosen by the taxpayer, 2026-08-07; `reference/research/open-legal-questions.md` Q11 records three
readings and no Tier 1/2 source chooses between them.

What supports it, all already in the store:

- **Rz. 9 excludes it from the Termingeschaeft route expressly** — *"Zertifikate und Optionsscheine
  gehören nicht zu den Termingeschäften, vgl. Rn. 8 f."* ([GT-ESTG20-038]). The same Randziffer
  opens by requiring an Options- or Festgeschaeft *"die zeitlich verzögert zu erfüllen sind"*,
  which a rolling position with no maturity does not obviously satisfy.
- **§ 23 is unavailable**: Rz. 57 requires physical backing with an exclusive delivery or proceeds
  claim ([GT-ESTG23-011]) and the broker evidences neither.
- **Nothing located argues against Reading C.** Q11 records that the BFH line cutting against it
  presupposes a delivery claim, which is absent here, so it neither supports nor excludes it.

It is also the taxpayer-favourable reading against Reading A — no derivative ring-fencing, so
losses offset against all capital income rather than sitting in the Termingeschaeft pot with the
pre-2025 cap. **Checked against every condition of the grey-area rule in CLAUDE.md**, since the
rule is unavailable if any one fails: no Tier 1 or Tier 2 source contradicts Reading C, and Rz. 9
positively excludes the alternative; the BMF has not addressed unallocated spot metal at a broker
in any located passage, directly or by implication; the ambiguity is documented rather than
constructed, as three readings each constrained by Tier 4 and none chosen by Tier 1 or Tier 2; and
the taxpayer was asked and decided, on 2026-08-07.

**Superseded, and why it is recorded rather than deleted.** This row previously read *"reading
chosen: Termingeschaeft (Reading A)"*, reasoned as "§ 23 is out, and between the two remaining
readings the Termingeschaeft one was taken" — which treated Reading C as unavailable because the
engine could not express it. That is an implementation constraint standing in for a legal
conclusion, and Rz. 9 points the other way.

**The engine can now express the chosen reading. Issue #53 landed on 2026-08-07**, adding
`AssetCategory.SONSTIGE_KAPITALFORDERUNG` and the dialog option that reaches it, so an
unallocated spot metal position is classifiable as a sonstige Kapitalforderung and its disposals
go to Zeile 19/22 under its own name. `BOND` would have landed the same figures on the same lines
and was **declined as a workaround**: it makes one category mean two unrelated things, and it does
not merely mislabel — a bond's trade price is a percentage of nominal and its gross is divided by
100, which on a metal position understates cost and proceeds by two orders of magnitude. Measured
2026-08-07 on the test scenario in `tests/test_sonstige_kapitalforderung.py`: the same trades give
cost 2000.00 / proceeds 2300.00 / gain 300.00 under the new category and 20.00 / 23.00 / 3.00
under `BOND`.

**What #53 did not do is reclassify anything.** No holding was moved into the new category, and
`preliminary_classify` never returns it — Rz. 57's test is not readable off an IBKR asset class,
so it is asked, never inferred. Recording the answer is the follow-up work, and the sequence is
deliberate: the option had to exist before the interactive pass, or the pass would have forced a
choice among options that were all wrong and written it into the gitignored cache, where a wrong
entry cannot be seen afterwards.

**Which instruments are routed here, and why.** One so far, and it is not yet recorded in any
cache:

| Instrument | Why | Authority |
|---|---|---|
| `CONID:69067924` — `XAUUSD`, IBKR AssetClass `CMDTY`, unallocated spot gold at the broker | Not a Termingeschaeft, not a § 23 asset: no expiry and no delayed settlement, no physical backing and no delivery or proceeds claim | Rz. 9 [GT-ESTG20-038]; Rz. 57 [GT-ESTG23-011]; Q11 Reading C, chosen by the taxpayer 2026-08-07 |

Nothing else in the maintainer's data has been assessed against Rz. 57. **The population that
needs assessing is larger than this row**, and it is not the `CMDTY` rows: a Zertifikat and an
unbacked ETC both arrive as `STK` and auto-classify to `STOCK` with no prompt. VZ 2024 and VZ 2025
have 96 and 239 instruments not in the cache respectively (measured 2026-08-07, issue #53), and
the interactive pass over them is where any further entry to this table will come from.

**Blocker status, measured 2026-08-07.** VZ 2024 no longer stops on `XAUUSD`: with that
classification supplied, the run reaches the next uncached instrument (`ISIN:SG1L1701REC0`) and
stops there. So #53 removed this instrument as a blocker and did not, on its own, unblock the
year — the interactive pass is the remaining step.

**A previous version of this note said the choice lived only in a gitignored cache and that this
row was its sole public record.** That was true, and it was tested the hard way on 2026-08-07 when
the cache was destroyed by the clean-clone protocol: the classification was lost and this row was
what survived. Keep it current for that reason.

### Abs. 4 — gain calculation and lot identification

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-ESTG20-011 | implements | `src/engine/fifo_manager.py` | `test_precision.py`, `test_fifo_groups.py` | Proceeds − costs − basis, all `Decimal` at `INTERNAL_CALCULATION_PRECISION`. |
| GT-ESTG20-022 | implements | `src/processing/` EUR conversion at ECB rates; `src/engine/fifo_manager.py` stores per-lot EUR basis | `test_group7_currency_fifo.py`, `test_group9_variable_fx.py`, `test_precision.py` | Abs. 4 Satz 1 Hs. 2 — each leg at its own date. **The statute names no rate source**; the engine uses ECB reference rates, which is a choice no located Tier 1/2 source prescribes for the Veranlagung. BMF 14.05.2025 Rz. 247 prescribes the Devisenbriefkurs only for the Steuerabzug by an inländische Zahlstelle, which does not apply here. |
| GT-ESTG20-023 | implements | derivative close/expiry/settlement paths in `src/engine/event_processors/` | `test_options_lifecycle.py`, `test_futures.py` | Abs. 4 Satz 5 — Differenzausgleich less directly related costs, and the same Satz governs a worthless expiry (BMF Rz. 27). Newly stated in the store; the engine already computed derivative results this way, but the store had only the Abs. 4 Satz 1 formula. |
| GT-ESTG20-024 | out of scope | — | — | Sparer-Pauschbetrag (Abs. 9). Applied by the Finanzamt; the engine reports gross figures and has no representation of Zeilen 16/17. The Satz 1 exclusion of actual Werbungskosten is nonetheless why only directly-related disposal costs reduce a gain — that part *is* how the engine computes. |
| GT-ESTG20-012 | implements | `src/engine/fifo_manager.py` — FIFO lot consumption; `reconcile_with_mark` decides which lots survive each checkpoint | `test_fifo_groups.py`, `test_replay_checkpoint_marks.py`, `tests/docs/spec_fifo.md` | Mandatory fiction; no specific-identification alternative is offered. Which lots a reconciliation keeps is part of it: where the reconstruction exceeds the reported holding the survivors are the **newest**, because FIFO consumed the oldest. Filling from the oldest end (the behaviour before August 2026) returned the wrong lot whenever a ledger held more than one, and the oversell flag previously discarded even an exactly-matching reconstruction. |
| GT-ESTG20-013 | **deviates** | `src/engine/ledger_views.py`, `src/utils/account_utils.py` | `test_ledger_views.py`, `test_multi_account_harness.py` | See below. |
| GT-ESTG20-014 | not reached | — | — | Own-depot transfer is not a disposal. No input represents one; a per-depot implementation would have to relocate lots rather than close and reopen them. |
| GT-ESTG20-039 | implements | `DomainEventFactory._trade_contract_date()` in `src/parsers/domain_event_factory.py`, feeding `FinancialEvent.event_date` | `test_trade_event_date.py` — the rule, the signature, the absent-date case, and the wiring through `create_events_from_trades` | Rn. 85: the obligatorisches Rechtsgeschäft fixes the FX rate and the gain computation, so the trade date governs and settlement does not. **By rule since 2026-08-07**, not by fallback: the trade path has its own helper, which takes no settlement or report parameter, and `RawTradeRecord` no longer declares a settlement field. Previously the trades path used the general helper, which orders settlement first, and was right only because IBKR's Trades export omits `SettleDateTarget` — measured that day, 0 of 6,976 rows across `Trades-2021.csv`…`Trades-2025.csv`. |
| GT-ESTG20-040 | implements | as above | as above. The § 23 tests (`test_section23_holding_period.py`, `test_section23_holding_period_guards.py`) build lots directly and do not reach the parser's choice of date, which is why `test_trade_event_date.py` exists | Rn. 317 defines *Erwerb* as the rechtswirksam abgeschlossener obligatorischer Vertrag; BFH IX R 18/13 (BStBl II 2014, 826, Rz 29) is to the same effect for § 23 and does not stand alone. Acquisition dates are therefore trade dates, which is what the ledger holds. The claim reaches past the Vorabpauschale: it also fixes the § 23 Jahresfrist and the month for § 18 Abs. 2. |
| GT-ESTG20-041 | implements | `FifoLedger.receive_all_lots_from_merger()` in `src/engine/fifo_manager.py` carries `acquisition_date` across to the replacement lots | `test_stock_merger_fifo.py` asserts the carry-over (four separate assertions on the surviving lot's `acquisition_date`) | Rn. 184a: a steuerneutrale Fondsverschmelzung restates the count *"unter Berücksichtigung des Umtauschverhältnisses"* and does not create a new Anschaffungszeitpunkt. **What the guarding test does not cover:** every case it exercises is a stock merger. The path is shared, but no test merges an `InvestmentFund`, so the § 18 Abs. 2 consequence — a merged fund keeping its acquisition month — is unguarded. The per-acquisition half of Rn. 184a is what grounds GT-INVSTG-011. |

**GT-ESTG20-039 and GT-ESTG20-040 — done, 2026-08-07.** The follow-up recorded here was to make
the trade date the stated rule rather than the third fallback behind settlement. It landed in two
steps: the trade path got its own helper, and then the concept was made unambiguous end to end —
`event_date` now documents which date each event kind carries and why, the general helper is named
`_zufluss_date` and says never to call it for a trade, `RawTradeRecord` no longer declares a
settlement field, and `input_data_spec.md` says not to add the column.

**What the pre-fix state actually risked, corrected twice on the day.** It was first written here
as one Flex Query checkbox away from silently misdating every lot. It is not: the trades parser
validates with `allow_extra=False`, so that column alone aborts the run. The silent path needed
two edits — the column added to the query *and* to `TRADES_COLUMNS` — or no CSV at all, since the
raw model declared the field and a record built in code never meets the validator. Removing the
field closes the second route; the validator closes the first.

> **Two corrections to this block, both on 2026-08-07, kept because the pattern matters.** It
> first claimed the hazard was one Flex Query checkbox — asserted from the shape of the helper
> without reading `validate_csv_columns`. Restated as a two-step hazard, it then stood as an open
> follow-up for an hour after the first half had already been fixed, because the commit that fixed
> it did not update the row. Both are the same failure: writing about code from what it looks like
> it does rather than from what it does.

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
| GT-ESTG20-015 | implements | `CORP_MERGER_STOCK` → tax-neutral basis transfer (FIFO drain/receive) | `test_stock_merger_fifo.py` (incl. `test_merged_in_shares_sold_inside_the_historical_window`), `test_historical_merger_replay_guard.py` | Cash consideration is handled separately as `CORP_MERGER_CASH` → `CASH_MERGER_PROCEEDS`. Until issue #56 the transfer did not survive a disposal of the merged-in shares *inside* the historical window: the replay applied mergers after every ledger event, so the reconstruction overshot, reconcile discarded it and substituted a lot with a fabricated acquisition date. Basis and date now transfer in that case too. |
| GT-ESTG20-016 | **deviates** | `CORP_STOCK_DIVIDEND` → new shares at EUR 0 basis | `test_stock_merger_fifo.py` (adjacent coverage only) | Satz 5 is the *residual* case, conditional on Sätze 3, 4 and 7 not applying. The engine applies the EUR 0 treatment without testing those three conditions. |
| GT-ESTG20-017 | not reached | — | — | Abspaltung. No corporate-action type maps to it. |
| GT-ESTG20-018 | implements | Merger streamed chronologically at its own date (`engine/replay.py` `Phase.LEDGER_EVENTS`, `calculation_engine._replay_historical_merger`) | `test_stock_merger_fifo.py::TestMergerIntraDayOrdering`, `test_merged_in_shares_sold_inside_the_historical_window` | Satz 6 has two consequences and the engine reaches one. **Reached:** the measure takes effect at that moment, so the same day's disposals can consume the delivered lots — this is what fixed issue #56, and the intra-day rule is merger-before-trades. **Not reached:** *which* date is the Einbuchung. The engine uses the corporate action's reported date as a proxy; no input distinguishes the two. Note Satz 6 governs Sätze 1–5 only, not the Satz 7 Abspaltung. |
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
| GT-FORM-002 | implements | `src/engine/loss_offsetting.py:249-275` | `test_group6_loss_offsetting.py` | Zeile 19 is a net figure; Zeilen 20/21/22/23 restate parts of it, Zeilen 24/25 do not (*ausschließlich*). The engine gets the Zeile 24 half right and the Zeile 25 half wrong — next row. |
| GT-FORM-003 | **deviates** | — | — | **Zeile 25 has no representation.** Forderungsausfall and wertlose Ausbuchung losses fall into `ANLAGE_KAP_SONSTIGE_VERLUSTE` (Zeile 22), which the 2024 Anleitung expressly forbids — *"ausschließlich in Zeile 25"*. Because *ausschließlich* also excludes them from Zeilen 18/19, the same defect **understates nothing but misplaces twice**: the loss appears in Zeile 22 where it may not, and inside the Zeile 19 net figure where it may not. No input in the maintainer's data produces such a loss today, so the path is unexercised, but nothing detects one if it appears. |
| GT-FORM-004 | **deviates** | — | — | Same shape: a worthless-share write-off should go to Zeile 23 in VZ 2025, and there is no event kind for it. |
| GT-FORM-005 | implements | `src/reporting/form_rules.py` — the 2025 rules write nothing to Zeilen 21/24/25 | `test_group6_loss_offsetting.py` | Nothing is entered on the separate derivative lines for VZ 2025, which is what the claim asserts and what the engine does. Whether the form still prints those numbers is a layout point that decides no figure; it was carried as open question Q3 until 2026-08-07 and is now a note in `reference/tax-forms/anlage-kap-zeilen.md`. |
| GT-FORM-006 | implements | `ANLAGE_KAP_FOREIGN_TAX_PAID` — sum of withholding events | `test_withholding_tax_linker.py` | Neither ceiling is applied; the Finanzamt applies § 32d Abs. 5 Sätze 1 and 3. See GT-CREDIT-005/006. |
| GT-FORM-007 | **partially implements** | `src/engine/loss_offsetting.py` | `test_german_kest_detection.py`, `test_withholding_tax_linker.py` | The negative half is implemented: German KESt is off Zeile 41. The positive half (Zeilen 7/37/38/39) is not computable — see GT-CREDIT-021. |
| GT-FORM-008 | out of scope | — | — | Zeile 4 (Günstigerprüfung) and Zeile 5 (Überprüfung des Steuereinbehalts) are taxpayer elections, not computed figures. |
| GT-FORM-009 | implements | classification decides the Anlage | `test_futures.py::TestFuturesClassification`, `test_section23_holding_period.py` | Fund → KAP-INV, private sale asset → SO, Einlagenrückgewähr (`CAPITAL_REPAYMENT`) → not taxable. |
| GT-FORM-010 | implements | `src/tax_law/registry.py` `FormYearRules(separate_derivative_lines=True)` for 2021 and 2024 | `test_tax_law_registry.py::TestFormYearRules` | |
| GT-FORM-011 | implements | `FormYearRules(separate_derivative_lines=False)` for 2025 | `test_tax_law_registry.py::TestFormYearRules::test_2024_vs_2025_form_structure` | |
| GT-FORM-012 | implements | `src/tax_law/registry.py:139-145` — 2021 is the earliest entry; `get_form_rules` **raises** for any earlier year rather than falling back | `test_tax_law_registry.py::test_years_before_the_earliest_verified_form_raise`, `test_every_configured_year_2021_to_2023_matches_2024` | Backward projection refused because Zeilen 21/24 were *frei* on the VZ 2020 form. Forward carry-over is a deliberate silent default. The raising behaviour used to be stated in the reference file itself, naming the function; moved here 2026-08-03 under the Purity Rule. |

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
| GT-INVSTG-010 | implements (Satz 2 price), see GT-INVSTG-017 for the unit count | `_calculate_vorabpauschale()` in `src/engine/calculation_engine.py`; the Satz 2 price for a fund bought mid-year comes from `src/processing/fund_prices.py` | `test_vorabpauschale.py::TestVorabpauschaleCalculation`, `test_vorabpauschale.py::TestAFundTheEngineCannotPrice`, `test_vorabpauschale_reclassification.py`, `test_fund_price_store.py` | Sätze 1–3: Basisertrag, the value-gain cap, and the distribution subtraction. Reached only for some funds until 2026-08-04, and a fund it could not price dropped out silently until 2026-08-09 — see below. |
| GT-INVSTG-011 | implements | `abs2_retained_twelfths()` in `src/engine/vorabpauschale_attribution.py`, used by `_calculate_vorabpauschale()` and by the Zeile 53 distribution key | `test_vorabpauschale_abs2.py`, `test_vorabpauschale_zeile53.py::TestAbs2Twelfths` | Abs. 2 reduces each acquisition by one twelfth per full month before its month of acquisition; units held before the year keep twelve. **No longer a choice under uncertainty** — the 2026-08-07 audit closed Q13 in favour of exactly this reading, on Rz. 18.11's worked example applying the reduction to the *per-Anteil* amount, with Rz. 18.9 and Rn. 184a alongside. The one residual is recorded in the store, not here: no source works a mixed holding, so summing per acquisition joins two quoted rules. Superseded text: *"implements (Q13 Reading A: per acquisition) … a choice under uncertainty"*; and before that, **Abs. 2 pro-rata was not implemented** at all. |
| GT-INVSTG-012 | implements | `VorabpauschaleData.vorabpauschale_year` and `.declaration_year` | `test_vorabpauschale.py::TestVorabpauschaleDeclarationYear`, `test_pdf_vorabpauschale.py` | The VZ `Y` return carries the Vorabpauschale for calendar `Y-1`. All three output surfaces select on `declaration_year`; the PDF read the pre-rename field until 2026-08-04. Re-decided 2026-08-07 on Rz. 18.12, now recorded: the Zuflussfiktion is stated there as a Steuerabzug convenience so that a full Sparer-Pauschbetrag is available, **not** as a holding test — which is why it could not carry GT-INVSTG-016 and no longer has to. |
| GT-INVSTG-013 | implements | `src/tax_law/registry.py` `BASISZINS_PCT` | `test_tax_law_registry.py::TestBasiszinsLookup` | Re-decided 2026-08-07 on Rz. 18.13 and 18.14, now recorded. Rz. 18.14 fixes the rate as the value determined for the **erster Börsentag** of the calendar year, which is 2 January only in years whose first exchange day falls on it. This does not reach the engine: it looks up the value the BMF published for the year, and choosing the day is the BMF's step, not the engine's. It bore on GT-INVSTG-018, where a 2 January date *was* used as a Stichtag; that was closed on 2026-08-08 and the two now read the same way. |
| GT-INVSTG-014 | implements | `Asset.prior_year_*` fields, resolved by `src/data_preparation.py` and populated by `ParsingOrchestrator.process_positions()` | `test_vorabpauschale.py::TestVorabpauschaleDeclarationYear`, `test_vorabpauschale_reclassification.py` | Records which *year* each input is drawn from; the day within it is GT-INVSTG-010. Where the prior year's snapshots are absent and funds are held, the run stops with a `FAIL_FAST` data gap rather than substituting the tax year's own snapshot. Where they are present but do not survive classification, the run stops with a `DataIntegrityError` — see below. |
| GT-INVSTG-015 | implements | gross on Zeilen 9–13 | `test_vorabpauschale.py::TestTeilfreistellungNegativeDistribution` | |
| GT-INVSTG-016 | implements | the unit count at the close of 31 December, from the ledger's own lots — see GT-INVSTG-017 | `test_vorabpauschale.py`, `test_vorabpauschale_price_and_units.py` | **No longer a choice under uncertainty.** The 2026-08-07 audit closed Q5 on Rz. 18.4: the multiplier is the holding at the close of 31 December, so a fund disposed of in full produces nothing without any rule about disposal being needed. The engine already computed it that way. Superseded position: **choice under uncertainty**, reasoned from the Abs. 3 Zuflussfiktion — see below. |
| GT-INVSTG-017 | implements | the unit count is taken from the ledger's own lots at the close of 31 December, snapshotted immediately after the historical replay reconciles | `test_vorabpauschale_price_and_units.py` | Rz. 18.4 multiplies by the units held at the **close of 31 December** of the calendar year, and the engine does exactly that. Rounding is compliant: full precision throughout, quantised to two places once, after every multiplication. See below for what it replaced and why the moment of the snapshot matters. |
| GT-INVSTG-018 | implements | ECB conversion at the day each price was set, carried on `Asset.prior_year_*_mark_price_date` and applied in `_calculate_vorabpauschale()`; the days themselves come from `src/utils/snapshot_dates.py` | `test_vorabpauschale_stichtag.py`, `test_vorabpauschale.py::TestVorabpauschaleCalculation` | Rz. 18.6 converts each input at the ECB rate of its own Stichtag, and a Stichtag is a day a price was set, never a fixed calendar date — the reading Rz. 18.14 confirms by anchoring the year on its **erster Börsentag**. **Re-decided 2026-08-08, and the imprecision is closed.** Superseded position: *"implements, with a known imprecision"* — the Jahresanfang Stichtag was hardcoded to 2 January and the Jahresende to 31 December. Measured over 2021–2025, 2 January is the first trading day in only 2024 and 2025, and in 2021 and 2022 it is a Saturday and a Sunday, so the ECB had no rate and `MAX_FALLBACK_DAYS_EXCHANGE_RATES` silently supplied one from another day. The 31 December instance was in neither this row nor issue #60 and was found by measurement: it is a weekend in 2022 and 2023. **What remains, and is not this claim's:** the day is derived from the snapshot naming convention, not read from the export, because the Positions report carries no date — issue #59. |
| GT-INVSTG-035 | **implements** where a price can be fetched, re-decided 2026-08-08 | `_first_price_set_in_year()` in `src/processing/fund_price_sources.py`; `src/processing/fund_prices.py` otherwise | `test_fund_price_sources.py::TestFirstPriceSetInYear`, `test_fund_price_store.py` | Rz. 18.7: a fund launched during the year takes its first set price, with Abs. 2 pro-rata on top. **No launch date is needed** — a provider's published series begins at launch, so the first new publication in the calendar year is Rz. 18.7's base for a launch year and the ordinary Satz 2 base otherwise, by one rule. Measured 2026-08-08 on a fund with an 18 April 2018 inception: calendar 2018 resolves to 19 April 2018, calendar 2019 to 2 January. Superseded positions: **deviates** — first *"skips any fund without a start-of-year position outright"*, then *"the launch date is still unknown"*. The second was written the same day and was wrong. |
| GT-INVSTG-036 | **not reached**, re-decided 2026-08-08 | — | — | Rz. 18.8: where a fund does not set a Rücknahmepreis at least monthly, the market price takes its place. **Both branches land on a price the engine already uses** — the Rücknahmepreis where one is set, the broker's market price where none is — so the determination cannot change a figure here and no behaviour follows from it. Superseded position: **deviates**, on the ground that the engine *"has no notion of whether a Rücknahmepreis exists and always uses the broker's mark price"*. Both halves were wrong: the second stopped being true on 2026-08-08, and the first described a distinction with no consequence. Which price is used, and why, is GT-INVSTG-010 Satz 4 below. |
| GT-INVSTG-055 | **not reached** (Satz 1) / **out of scope** (Satz 2) | — | — | Rz. 18.9. Satz 1 is confined to the Steuerabzugsverfahren, which a foreign custodian does not perform. Satz 2 is a refund route in the assessment for tax over-withheld by a domestic agent — there is none here. Recorded because it is the administrative statement that the Abs. 2 reduction turns on *Anschaffungsdaten* attaching to units, which is part of what closed Q13 (GT-INVSTG-011). No behaviour follows from it. |
| GT-INVSTG-056 | **deviates** | `_calculate_vorabpauschale()` in `src/engine/calculation_engine.py` — the tranche loop applies the Abs. 2 twelfths to each tranche's Basisertrag, and the distributions are subtracted from the sum afterwards | none: no test combines a distribution with `k < 12` | Rz. 18.3 computes Satz 3's cap, then Satz 1's subtraction, and Rz. 18.11 takes 6/12 of what remains — so the twelfths multiply `Basisertrag − Ausschüttungen`. The engine has the two steps the other way round and is therefore lower by `Ausschüttungen × (12 − k)/12`; where that drives the result to zero or below the fund is dropped and nothing is declared at all. Measured 2026-08-09 on the module's own harness: a July acquisition with distributions at 37% of the Basisertrag yields 20.15 against the statute's 50.15, and at 75% the engine declares nothing against the statute's 20.15. Closed by the `fix-func(engine)` for issue #58. |

**GT-INVSTG-010 and GT-INVSTG-014 — reached only for some funds until 2026-08-04.** A positions
row is resolved without its `SubCategory`, so the description is the only fund signal that
survives: an instrument described as an ETF is created as an `InvestmentFund` outright, and any
other fund is created as a `Stock` and retyped when the user's classification is applied — which
is after the prior-year snapshot has been read onto it. Retyping copies a hand-listed set of
fields and the `prior_year_*` fields were not on it, so a retyped fund reached § 18's
computation with no year-start Rücknahmepreis and was skipped, with nothing recorded. A fund
created as a fund was unaffected. **On this repository's own data the distinction is not a
mitigation:** no fund description contains "ETF", so every one was retyped and Zeilen 9–13 were
empty on every run, whether or not deemed income was due.

Two guards now stand where that failed. The values read are checked against the values the
engine will see (`ParsingOrchestrator._verify_prior_year_snapshot_survived_classification`,
`DataIntegrityError`, naming every affected fund); it follows an alias rather than an id, so an
instrument merged into another after its snapshot was read is followed to the survivor, and it
reports investment funds only, since nothing else can lose a declared figure this way. And the
itemisation is exercised with a record present (`test_pdf_vorabpauschale.py`) — the PDF read the
pre-rename `tax_year` field and would have raised `AttributeError` on the first run that
produced one.

**GT-INVSTG-010, Satz 4 — closed for any fund a provider publishes, 2026-08-08.** The
Ruecknahmepreis is the primary measure and a market price substitutes only where none was set. An
open-ended fund that redeems units at its NAV sets one — *Rücknahme* plus *Preis*, the price it
takes the share back at.

The engine therefore looks that price up, by ISIN, **for every fund held across the year end** —
not only for one the start-of-year position report cannot price. Until 2026-08-08 it used the
report's mark wherever it had one and only went looking when it did not, which put Satz 4's
substitute ahead of the primary measure for every fund held on 1 January. Superseded positions:
first *"uses the broker's position mark price unconditionally"*; then, for one day, a
`--vorabpauschale-strict-nav` switch that made the NAV opt-in. The switch is gone — an opt-in
default is still the substitute for everyone who does not know to ask for it.

**What remains is the fallback, and it is recorded.** Where no Ruecknahmepreis can be obtained the
taxpayer is asked and offered the report's price, and in a non-interactive run that price is used
outright; both record `VORABPAUSCHALE_PRICE_MARKET_FALLBACK` against the fund, so a reader can see
which figures rest on the substitute. A fund that nothing can price stops the run.

**GT-INVSTG-010 — the Satz 2 price.** *Ruecknahmepreis zu Beginn des Kalenderjahres* is the
first Rücknahmepreis set in the calendar year. Rz. 18.3 of the BMF-Schreiben demonstrates it: one
figure serves as both the Satz 2 base and the Satz 3 cap's lower bound, which Satz 3 defines as
the first price set in the year. Rz. 18.7 anchors a mid-year fund on the first price actually set.

The engine takes it from the calendar year's own start-of-year position report; where a fund was
sold on that day and so has no price there, the last price set before the year began is used and a
`VORABPAUSCHALE_PRICE_WRONG_DAY` data gap is recorded. How the stored reports are read into a
position history is described in `src/data_preparation.py` and
`src/parsers/parsing_orchestrator.py`.

**A third source, for the fund the export cannot price at all.** A fund bought during the year has
no row in that year's start-of-year report, because the report lists what was held. The price
nevertheless exists — it is a property of the fund, not of the holding — so the figure is due and
buying mid-year is an ordinary event, not a data gap. `src/processing/fund_prices.py` asks the
taxpayer for the price and caches it under the asset's classification key and the calendar year,
the same shape as the classification cache; each supplied price is recorded as a
`VORABPAUSCHALE_PRICE_USER_SUPPLIED` gap at WARNING so the report states what the Basisertrag rests
on and where it came from. **Nothing is invented:** a run that cannot obtain a price stops on a
`VORABPAUSCHALE_YEAR_START_PRICE_UNKNOWN` FAIL_FAST naming every affected fund. Neither IBKR nor
any broker export can supply this price — measured 2026-08-08: IBKR's historical endpoints serve
market prices only, and its ETF NAV ticks (92–99) reach one session back.

The conversion of this price is no longer pinned to 2 January; the follow-up that stood here is
closed under GT-INVSTG-018 below.

**A price the engine cannot use no longer removes the figure quietly, 2026-08-09.** Four paths in
`_calculate_vorabpauschale()` dropped a single fund and let the run finish: no Satz 2 price, that
price not convertible to EUR, no Satz 3 price though units were held at the close, that price not
convertible. Each was a log line and a `continue`, so an instrument the engine had itself
classified as an investment fund contributed no deemed income and the report said nothing —
measured on 2026-08-07, four funds across VZ 2024 and VZ 2025 with Anlage KAP-INV Zeilen 9–13 at
0.00 and an empty gap section. All four now collect and record one `VORABPAUSCHALE_PRICE_UNUSABLE`
FAIL_FAST naming every affected fund with its reason. The figure in these cases is not zero, it is
un-computable, and a zero on Zeile 9 is indistinguishable from a lawful one (issue #55).

Two boundaries on that gap. It is **not** recorded for a calendar year whose Basiszins is not
positive — Satz 2 multiplies by it, so no fund owes anything whatever its price was, and calendar
2021 and 2022 are such years; without the guard VZ 2023's lawful zero would start aborting. And it
is recorded **after** `VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN`, so a tree missing both keeps
aborting on the acquisition dates as it did before: a FAIL_FAST raises where it is recorded, so
only the first of two ever reaches the report.

**GT-INVSTG-017 — the unit count. Closed.** Rz. 18.4 multiplies the per-unit Basisertrag by the
units held at the close of 31 December of the calendar year, and the engine now does exactly that,
taking them from the ledger's own lots at that moment. It previously multiplied by the units held
when the year opened. The two coincide for an unchanged holding; on VZ 2024 real data they give Anlage
KAP-INV Zeile 13 393.27 against 491.59.

Bearing on the choice: § 18 Abs. 2 reduces the Vorabpauschale pro rata for units *acquired during
the year*, which presupposes those units are counted; and GT-INVSTG-016 — no longer a reading but
a consequence of this very Randziffer — gives no Vorabpauschale for a fund fully disposed of
during the year.

**Re-decided 2026-08-07 and strengthened.** Rz. 18.4 is not a Steuerabzug convention: it sits in
Textziffer 18.1 *"Ermittlung der Vorabpauschale"* and is unqualified, where the Randziffern of
this section that *are* confined to withholding say so (Rz. 18.9, Rz. 18.10, both *"im
Steuerabzugsverfahren"*). It therefore governs the amount itself, which is what lets it carry
GT-INVSTG-016 as well as the count.

Done. The lots are snapshotted immediately after the historical replay reconciles, which is the
one moment they describe the close of the preceding calendar year and still carry their
acquisition dates.

**GT-INVSTG-035 — partly closed, and re-decided 2026-08-08.** The Abs. 2 pro-rata applies to units
acquired during the year (`e70099b`), and the price is no longer unobtainable: a fund with no
start-of-year row is asked about rather than skipped, so a taxpayer who has the first price the
fund actually set can enter it and Rz. 18.7's base is used.

**It does not need to tell the two apart.** The engine cannot distinguish a fund *newly launched*
mid-year from one merely *bought* mid-year, and that turns out not to matter: it asks the provider
for the first value published in the calendar year, and a series that starts at launch answers
Rz. 18.7 without anyone establishing a launch date. The earlier note here said closing this
*"needs the launch date, which no input this pipeline holds supplies"*; that was wrong.

**The manual path proposes no day it was not given.** Where no provider can be reached the
taxpayer is asked, and where the fund has no start-of-year row the prompt offers no default date:
the year's first trading day is wrong for a fund launched in April, and a proposed date is the
kind of thing that gets accepted with Enter. An empty answer is a refusal, not a guess
(`test_fund_price_store.py::TestThePromptDefaults::test_with_no_report_row_no_day_is_proposed`).
Superseded position, written 2026-08-08 in the same commit that fixed it: *"What is still open is
the manual path … the prompt offers the year's first trading day as the default date."* It
described the behaviour the code half of `366f832` had already removed.

**GT-INVSTG-036 — follow-up withdrawn 2026-08-08.** It named a `fix-func(engine)` to distinguish a
fund that sets a Rücknahmepreis at least monthly from one that does not. There is nothing for it to
close: both branches of Rz. 18.8 land on a price the engine already uses, so the distinction cannot
move a figure. The Satz 4 choice it also claimed to close is a separate matter and is decided under
GT-INVSTG-010 above.

**GT-INVSTG-016 — settled 2026-08-07, formerly open question Q5.** The engine's behaviour is
unchanged; its justification is not. The reading was previously *chosen* from the Abs. 3
Zuflussfiktion — the units are gone by the first working day of the following year — and recorded
as a defensible guess. It now rests on Rz. 18.4, which states the multiplier as the units held
*"mit Ablauf des 31. Dezember des Kalenderjahres"*. A fund disposed of in full is multiplied by
nothing; no rule about disposal is needed, and none exists. Rz. 20.4 confirms the direction: a
merely deemed disposal under § 22 Abs. 1 leaves the units in the count and the full year stands
(GT-INVSTG-054).

This is the same Randziffer the engine already implements for the unit count (GT-INVSTG-017), so
Q5 was never a separate decision — it was a consequence of one already taken. Recording it as an
open question, and reasoning it from the wrong Absatz, is the defect the audit corrected.

**Follow-up from closing Q5 and Q13:** `fix-nonfunc(engine)` — three comments now assert something
false and a reader would trust them. `src/engine/calculation_engine.py:1299` says *"Both readings
are in reference/research/open-legal-questions.md Q13"*; there are no longer two readings there,
only a retirement note. Line 1331 attributes the disposal-year result to *"Q5 Reading A: the
Abs. 3 Zufluss falls after the disposal"*, which is the reasoning this audit replaced — the ground
is Rz. 18.4. And `tests/test_vorabpauschale_abs2.py:12` describes Q13 as an open question. None
changes behaviour, which is why they are not in this `ks-maint`; a comment that misstates why a
figure is correct is how the next reader reopens a settled point or, worse, "fixes" it.

### § 19 — disposal gains

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-INVSTG-030 | implements | fund disposals → `ANLAGE_KAP_INV_*_GEWINN_GROSS`, net of the Satz 3 deduction; Satz 4's gross ordering in `RealizedGainLoss.__post_init__` (`src/domain/results.py`) | `test_group6_loss_offsetting.py::TestLossOffsettingFundIsolation`, `test_vorabpauschale_zeile53.py::TestSatz4GrossDeductionThenTeilfreistellung` | All four Sätze. Satz 3's deduction reaches the lot through `FifoLot.vorabpauschale_gross_eur`; Satz 4 fixes the order — the full, pre-Teilfreistellung amount comes off the gain first, and the Teilfreistellung is applied to what is left. Was "implements (partly)" until issue #63. |
| GT-INVSTG-031 | not reached | — | — | A fund leaving the InvStG's scope is not reported in any broker statement. |
| GT-INVSTG-032 | out of scope | — | — | Wegzug and related, gated by a 1 % / EUR 500 000 threshold. |
| GT-INVSTG-033 | implements | `ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z53`, summed in `src/engine/loss_offsetting.py` | `test_vorabpauschale.py::TestZeile53VorabpauschaleDeduction`, `test_vorabpauschale_zeile53_engine.py::TestTheDeductionReachesTheFormLine` | The figure is on the right line, and the gain lines are net of it because the form reaches them through Zeile 54. |
| GT-INVSTG-034 | implements | `src/processing/vorabpauschale_declarations.py` (what was declared) with `src/engine/vorabpauschale_attribution.py` (distributing it to the lots); `src/engine/calculation_engine.py` reports every holding-period year that reached no lot | `test_vorabpauschale_zeile53.py`, `test_vorabpauschale_zeile53_engine.py::TestAYearWithNoDeclarationRecord` and `::TestDivergenceFromWhatWasDeclared` | See below. Was **deviates — reports the gap** until issue #63. |

**GT-INVSTG-034 / GT-FORM-033 — the Zeile 53 deduction, and what it may rest on.** The deduction
is the mirror of a declaration, not a second quantity the engine may derive: for units that never
bore inländischer Steuerabzug the Anleitung admits it *"nur, soweit Sie diese Vorabpauschalen der
Besteuerung unterworfen haben (Zeile 9 bis 13)"*, and requires the taxpayer to demonstrate it. So
three things had to hold together, and each is a place a plausible wrong number was available:

- **It follows the lot.** `FifoLot.vorabpauschale_gross_eur` accumulates as the replay passes each
  year end — the moment the ledger describes the Rz. 18.4 holding — and every consumption path
  hands the disposed units their pro-rata share. A partial sale therefore deducts the tranches
  FIFO consumed and nothing else.
- **What is spread is what was declared.** The annual figure per fund is the taxpayer's input,
  recorded write-once at filing (`--commit-vorabpauschale-declaration`); the engine's own § 18
  Abs. 2 split is only the key that distributes it, and the prices cancel out of that key, so a
  year whose prices this run never loaded can still be distributed. For calendar `tax_year-1` the
  declaration is *this return's own Zeilen 9-13*, which is why that year needs no stored record.
  Where a stored figure and this run's computation disagree, the stored one governs and the
  divergence is reported while the return is amendable.
- **A year with no record deducts nothing, and is named.** Never the engine's recomputation
  standing in for a declaration — that is the invented input CLAUDE.md refuses. A year whose
  Basiszins was not positive is excluded from the demand instead of reported, because § 18
  Abs. 1 Satz 2 yields no Vorabpauschale for any fund in such a year (2021 and 2022).

Superseded text: *"the Zeile 53 deduction is not computed, deliberately … It now emits no figure
and records a data gap when fund units are disposed of"* — true from 2026-08-03 until issue #63,
and before that the line carried the current year's gross Vorabpauschalen on Zeile 55.

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
| GT-INVSTG-043 | not reached | — | — | Abs. 3 Satz 1 — the fiktive-Veräußerung gain is deemed to flow only on the **actual** disposal. Nothing reaches it because GT-INVSTG-040 is not reached either, but it changes what a fix would have to do: see below. |
| GT-INVSTG-054 | **not reached** | — | — | Rz. 20.4, as amended 29.04.2021: in a year the § 22 Abs. 1 fiction bites, the Vorabpauschale is set for the **whole** calendar year — a deemed acquisition triggers no Abs. 2 reduction — and the Teilfreistellung follows the rate at the Abs. 3 Zuflusszeitpunkt. Not reached for the same reason as GT-INVSTG-040: nothing detects a rate change. **It constrains the eventual § 22 fix**, which must not pro-rate the Vorabpauschale of the fiction year. Its Sätze 3–5 are a 2018/2019 Steuerabzug Nichtbeanstandung and are out of scope by their own wording. Recorded now because the audit found the 29.04.2021 amendment, which no file in this repository had. |

**GT-INVSTG-043 changes the shape of the GT-INVSTG-040 gap.** Implementing § 22 is not "emit a
disposal in the year the rate changes". Abs. 3 Satz 1 defers the Zufluss to the actual disposal, so
a correct implementation must **carry** a per-lot deferred gain across years and release it when
the units are sold — the same multi-year per-lot record the Zeile 53 deduction needs
(GT-INVSTG-034), and the engine holds neither. Emitting the gain in the year of the fiction would
declare income a year or more early and then omit it at the real disposal.

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
| GT-ESTG23-005 | **deviates** | — | — | **The ten-year period is not implemented**; one year is applied unconditionally. Idle for the instruments currently classified `PRIVATE_SALE_ASSET`, which produce no income from the asset itself — but that is a property of those instruments, not a safeguard. Adding an income-producing "anderes Wirtschaftsgut" makes this wrong. **Re-decided unchanged by the issue #66 audit, 2026-08-08:** the claim's text lost its reference to Crypto ETPs, but the instruments the taxpayer has classified `PRIVATE_SALE_ASSET` are the same set and none of them produces income from the asset itself, so the deviation's scope and its idleness are both where they were. |
| GT-ESTG23-006 | **deviates** | `consume_short_lots_for_cover` in `src/engine/fifo_manager.py` | — | Nr. 3 has **no holding period**. The engine applies the Nr. 2 Jahresfrist to a short cover, so a short held longer than a year would be reported exempt where Nr. 3 makes it taxable. Unexercised — no sell-to-open on any `PRIVATE_SALE_ASSET` in the maintainer's data (checked 2026-08-02) — and wrong if reached. |
| GT-ESTG23-007 | not reached | — | — | Inherited or gifted assets carry the predecessor's acquisition date. No input represents an unentgeltlicher Erwerb. |
| GT-ESTG23-008 | implements | `src/engine/fifo_manager.py` | `test_section23_holding_period.py` | |
| GT-ESTG23-009 | out of scope (deliberate) | — | — | The Freigrenze applies to the taxpayer's *total* private-sale gain for the year, which one portfolio cannot establish. The engine reports the gross figure and leaves the threshold to the taxpayer and the Finanzamt. |
| GT-ESTG23-010 | implements | `src/engine/loss_offsetting.py` — § 23 pool separate from § 20 | `test_group6_loss_offsetting.py` | Carryback and carryforward are the Finanzamt's step. |
| GT-ESTG23-011 | **deviates** (crypto ETPs) / **implements — as a question, not an inference** (Rohstoff ETCs) | `src/classification/asset_classifier.py` — the two dialog options that are Rz. 57's two outcomes; `AssetCategory.SONSTIGE_KAPITALFORDERUNG` | `test_sonstige_kapitalforderung.py::TestSonstigeKapitalforderungIsClassifiable` | **Re-decided 2026-08-08 by the issue #66 audit; the Rohstoff half is unchanged from the 2026-08-07 re-decision under issue #53.** Rz. 57's test — physical backing plus an exclusive delivery-or-proceeds claim — turns on the Emissionsbedingungen, which no input carries, so the engine asks. Both of Rz. 57's outcomes have had a dialog option since #53; before it, an unbacked ETC had nowhere to go but `BOND` or a wrong category. `test_it_is_never_a_preliminary_classification` holds the store's own conclusion in place: no heuristic may infer this from an asset class label. **What the #66 audit changed:** the claim no longer lists Crypto ETPs, because Rz. 57 reaches Gold und andere Rohstoffe only and the crypto row never had an authority. The `deviates` this opened — the engine answering the crypto question in three places, the `preliminary_classify` branch, the dialog default it produced, and the § 23 option label naming *Krypto-ETP* — **is closed**: `preliminary_classify` returns `UNKNOWN` for a crypto product, which is the one category that suppresses the dialog default and raises in a non-interactive run, and the label names no instrument the Randziffer does not reach. Guarded by `test_crypto_etp_is_not_pre_answered.py`, 19 tests. The category a crypto ETP belongs in is now the taxpayer's determination alone, recorded in the classification cache; the engine holds no position and states none. |
| GT-ESTG23-012 | implements | `SECTION_23_ESTG_TAXABLE_GAIN` / `_TAXABLE_LOSS` / `_EXEMPT_HOLDING_PERIOD_MET` | `test_section23_holding_period_guards.py::TestSpeculationPeriodFlagIsTruthful` | Dates that cannot decide the question raise `ProcessingError` rather than defaulting to exempt — an undecidable § 23 case is unreported income, not tax-free income. |
| GT-ESTG23-013 | implements | `src/engine/fifo_manager.py` — currency ledgers consume lots first-in-first-out | `test_group7_currency_fifo.py` | Nr. 2 Satz 3, the statutory FIFO fiction for *gleichartige Fremdwährungsbeträge*. **This is the Tier 1 grounding the currency FIFO always needed and never had.** Until this audit the store cited § 20 Abs. 4 Satz 7, which is confined to vertretbare Wertpapiere in Sammelverwahrung and cannot reach a currency balance. The engine's behaviour is unchanged and was already right; what changes is that it is now sourced. Applies from 31.07.2014 (Art. 2 G. v. 25.07.2014, BGBl. I S. 1266) — earlier assessment years have no statutory ordering for currency. |

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
| GT-FORM-023 | **choice under uncertainty** | `src/engine/fifo_manager.py` applies FIFO to § 23 assets | `test_section23_holding_period.py` | See below. **Re-decided unchanged by the issue #66 audit, 2026-08-08:** the claim's text no longer offers Crypto ETPs as an example of the *anderes Wirtschaftsgut* the gap bites on. The gap itself is unmoved — it is defined by § 23 Abs. 1 Satz 1 Nr. 2 Satz 3 covering currency and nothing else, not by which instruments are listed beside it. |

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
| GT-FORM-033 | implements | `src/engine/loss_offsetting.py` (Zeile 53 total; gain lines net of it) | `test_vorabpauschale.py::TestZeile53VorabpauschaleDeduction`, `test_vorabpauschale_zeile53_engine.py` | See GT-INVSTG-034. Was **deviates** until issue #63. |
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
| GT-CREDIT-014 | **deviates (no longer silently)** | `src/engine/loss_offsetting.py` `_is_german_kest` | `test_german_kest_detection.py` | Domicile is now tested by two proxies — issuer country where the broker supplies one, the 26.375% composite otherwise. Rows matching neither are still treated as foreign, but that is now a stated fallback rather than an untested assumption. |
| GT-CREDIT-020 | not reached | — | — | German KESt is withheld upstream, not by the broker. |
| GT-CREDIT-021 | **deviates — by design** | — | `test_german_kest_detection.py::TestTheExcludedAmountReachesTheUser` | Zeilen 7/37/38/39 have no representation, and will not: they transcribe a Steuerbescheinigung the engine does not hold. The amount reaches the user as a data gap instead. |
| GT-CREDIT-022 | implements | `src/engine/loss_offsetting.py` `_record_german_kest_gap` | `test_german_kest_detection.py::TestTheExcludedAmountReachesTheUser` | The report now names the amount, the Zeilen 7/37/38 route, and that § 36 Abs. 2 Satz 2 bars the credit without a certificate obtained from the German custodian. |
| GT-CREDIT-023 | not reached | — | — | That the certificate is obtainable on request is a fact about the broker, not a computation. |
| GT-CREDIT-024 | not reached | — | — | § 36a Cum/Cum, with a EUR 20 000 Bagatellgrenze. |
| GT-CREDIT-025 | **implements (detection); deviates (credit route)** | `src/engine/loss_offsetting.py` `_is_german_kest` | `test_german_kest_detection.py`, `test_withholding_tax_linker.py::test_german_kest_is_excluded_from_zeile_41` | German KESt is identified and kept off Zeile 41. It is not re-declared — see below. |

**GT-CREDIT-025 / GT-CREDIT-021 / GT-CREDIT-022 / GT-CREDIT-014 — one defect, four claims.**

`src/engine/loss_offsetting.py` sums **every** withholding event into
`ANLAGE_KAP_FOREIGN_TAX_PAID` (Zeile 41) with **no country filter**, and the engine has no
representation of Zeilen 7, 37, 38 or 39 at all. German Kapitalertragsteuer withheld upstream on a
German issuer's dividend is therefore declared as anrechenbare *ausländische* Steuer, on the wrong
line and through the wrong credit mechanism.

### Recognising German KESt in IBKR data

This is an input-data question, not a legal one, which is why it is recorded here and not in the
store. Two signals, and neither is sufficient alone.

**1. `IssuerCountryCode`, where IBKR populates it.** The column exists in the Cash Transactions
export, is parsed onto the withholding event, and is authoritative when non-empty. **Its
availability is a function of export vintage:** essentially absent from older exports, partial in
2024, fully populated in 2025. `XX` occurs as a value and is not a country. A country filter alone
therefore fixes recent assessment years and leaves older ones untouched.

**2. The 26.375 % composite** ([GT-CREDIT-025]), for the years where no country code exists.
Measured against real data, the observed rates cluster at 26.369–26.375 % — the withheld amount is
*not* reproducible from the paired gross by any simple rounding rule. Three hypotheses were tested
against the German-signature rows and each matched exactly half of them: one-step
`round(gross × 0.26375, 2)`, two-step KESt-then-SolZ with half-up rounding, and the same with
round-down. **So any tolerance used here is empirical, not derived, and must be recorded as such.**
Observed deviation from the one-step figure reaches two cents.

**Why the credit cannot simply be moved to Zeilen 7/37/38/39.** [GT-FORM-007] routes it there, but
Zeilen 7–15 are defined as the figures *taken from* the Steuerbescheinigung of the inländische
auszahlende Stelle, and § 36 Abs. 2 Satz 2 bars the credit outright when no certificate is
presented ([GT-CREDIT-022]). Zeile 7 is a transcription of a document the taxpayer holds, not a
figure this engine can compute. Populating it from calculated values would fabricate the one thing
the form defines as copied.

What a fix can therefore do: stop declaring German KESt as ausländische Steuer on Zeile 41, and
tell the user the amount, the correct route, and that the certificate must be obtained from the
German custodian through the broker.

---

## Foreign currency

| Claim | Position | Module | Guarding tests | Notes |
|---|---|---|---|---|
| GT-FX-001 | implements | `FX_CONVERSION_SALE`, `FX_CONVERSION_SHORT_COVER`, `FX_IMPLICIT_SECURITY_PURCHASE`, `FX_IMPLICIT_SECURITY_SALE`, `FX_IMPLICIT_CASHFLOW_EXPENSE`, `FX_IMPLICIT_CASHFLOW_INCOME` → `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE` / `_VERLUSTE` | `test_group7_currency_fifo.py`, `test_group9_variable_fx.py`, `test_group11_cashflow_currency.py`, `test_fx_rgl_hardening.py` | All currency balances are treated as § 20; see Q7. **The cash-flow debit case (`FX_IMPLICIT_CASHFLOW_EXPENSE`/`_INCOME`) is an extension of this claim, not one of the disposing events Rz. 131 enumerates — see Q9, instance (b).** |
| GT-FX-002 | not reached | — | — | Non-interest-bearing accounts. A margin brokerage account pays or charges interest on balances, so the § 23 branch is not exercised — **but nothing tests the account's actual character.** |
| GT-FX-003 | not reached | — | — | Pure payment accounts. |
| GT-FX-004 | not reached | — | — | Retroactivity to VZ 2009 and the 2025 bank withholding duty both concern German Zahlstellen. |
| GT-FX-005 | implements | as GT-FX-001 | same | § 20 throughout. Reason: the administrative position, and a margin account's balances bear interest. The § 23 reading would make gains after a year tax-free, so this is **not** the taxpayer-favourable choice — and under the grey-area rule in CLAUDE.md it is not a choice at all. BMF 14.05.2025 Rz. 131 states the § 20 treatment at Tier 2, verbatim and verified, drawn on the verzinslich/unverzinslich line; the rule's first condition bars implementing against it, whichever way it falls. **Do not reopen this on the ground that the favourable reading exists.** What remains genuinely open is whether the administration's position is correct, which is Q7 and is not something a generated figure should take a side on. Position changed from *"choice under uncertainty"* on 2026-08-07: Rz. 131 having been verified, following it is compliance, not a selection. |
| GT-FX-006 | **choice under uncertainty** | short currency positions tracked and taxed symmetrically with long ones | `test_group7_currency_fifo.py` | No guidance addresses a negative balance in Privatvermögen. Symmetry is an assumption. |
| GT-FX-007 | **choice under uncertainty — now unsourced outright** | currency legs of securities trades measured separately (`FX_IMPLICIT_*`) | `test_group9_variable_fx.py`, `test_group10_options_variable_fx.py` | See below. |
| GT-FX-008 | implements | `src/engine/fifo_manager.py` — currency lots consumed FIFO | `test_group7_currency_fifo.py` | FIFO for currency, now sourced on both branches: BMF 14.05.2025 Rz. 131 for § 20, § 23 Abs. 1 S. 1 Nr. 2 S. 3 for § 23 ([GT-ESTG23-013]). Same ordering either way, so the unresolved classification in GT-FX-005 does not put the lot order in doubt. |

**GT-FX-007 — the citation that supported this was checked and does not say it.** BMF 14.05.2025
was retrieved on 2026-08-03 and Rz. 131 read in full. It addresses Fremdwährungs*beträge* —
accounts, deposits, payment balances — and says nothing about the currency leg of a securities
transaction. The store had cited it for separate measurement; it does not carry that. The engine's
`FX_IMPLICIT_*` treatment is unchanged and remains the conservative reading (it cannot understate
income), but it is now recorded as **reasoned, not sourced**, and it is the most heavily exercised
FX path in the engine. Combined with the blind spot noted at the end of this section — reversing
the order of every historical currency event leaves the suite green — this is the area to treat
with the most caution.

**The currency area, restated after the 2026-08-03 audit.** The BMF circular that carried this
area had never been retrieved; it now has been, and the picture is better in most places and worse
in one:

- **Better:** GT-FX-001, -002, -003 and -004 are verified Tier 2 verbatim (Rz. 131, Rz. 324), and
  currency FIFO has a Tier 1 anchor it never had (GT-FX-008 / GT-ESTG23-013). Rz. 131 also supplies
  detail the engine should be checked against and the store never carried: **prolongation of a
  daily-callable deposit and a change of interest rate are not disposals**, but a balance becoming
  interest-bearing for the first time, or ceasing to be, *is* an event.
- **Worse:** GT-FX-007's only citation turned out not to say what it was cited for.

So the earlier summary — "four of seven claims resting on a circular never retrieved" — no longer
holds. Three choices under uncertainty remain (GT-FX-005, -006, -007) and they are genuine ones.

**Known blind spot:** per CLAUDE.md's *Where the suite is blind*, reversing the chronological order
of every historical currency event leaves the whole suite green. Currency changes must be probed
by mutation, not by running the suite.

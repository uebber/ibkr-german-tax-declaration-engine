# PR #88 review and correction

Base: accepted main `89e7c24`. Original incremental range: `2c8c45b..4da165a`.
Isolated integration: `0b1910e` (history merge, no issue #76 source).
The maintainer authorized correcting #88 and PM-005 together, then merging only
after verification. No further real-data figure changes are approved.

## Initial evidence

- Clean candidate suite: 1,293 passed, 1 data-dependent skip. Focused transfer,
  snapshot and account-boundary suite: 111 passed.
- Fresh main/control runs complete identically for VZ 2023, 2024 and 2025.
  Initial #88 candidate aborts all three on `REPLAY_MARK_MISMATCH`, without PDFs.
  Moving option lifecycle events before their same-day opening trades causes it.
  A diagnostic restoring only option transaction order restores identical console
  reports and metadata-stripped PDFs for all three years. Original input, cache and
  configuration hashes are unchanged; the maintainer's exports have no Transfers files.
- Seven initial independent probes: six fail, one passes. They demonstrate
  incoming undated long/short lots bypassing the opening-time disposal-history
  guard, a same-day transfer relay ordered by account name, equal-sized distinct
  transfers collapsed, and conflicting side details silently selected by row order.
- #88 did not alter option fixture suites. Their 19 scenarios include 11 lifecycle
  scenarios and none opening and consuming an option on the same day. Three new
  chronology regressions fail before correction. The focused corrected set has
  55 passing tests, including existing option and merger tests.
- Later heads refreshed through #92 `940870e`: the securities transfer deduplication
  and blanket option precedence remain. Later currency work does not fix them.

## Required correction

1. Preserve option transaction chronology and explicit account-local delivery links;
   partial deliveries must consume their allocated premium exactly once (PM-005).
2. Preserve distinct transfers and reconcile reciprocal detail. Coordinate delivery
   and receipt through account-local lot operations, validating before mutation.
3. Preserve provenance at each disposal, including lots received during the year.
4. Verify final clean suite and VZ 2023–2025 against the accepted baseline. A new
   refusal or figure difference is not parity and requires a maintainer decision.

## Separate pre-existing legal finding

`TradeProcessor` folds assignment premiums into stock basis/proceeds; historical
replay does not apply the current-year premium adjustment. The assignment treatment
conflicts with GT-ESTG20-004 (BMF Rz. 26); the implementation-map claim is too broad.
This is distinct from matching the right exercise and keeping premium ownership
account-local. No tax-treatment correction or new filing position is approved by
this review record. Do not silently change it to make an ownership test pass.

## Corrected behavior and verification

- Option-order fix: `31824f8`. The shared day scheduler preserves the ordinary
  currency-affecting sequence and each option ledger's chronology, then enforces
  validated option-delivery and transfer-side dependencies. Transfer cycles with
  contradictory source observations are refused before replay.
- PM-005: links include account, action, direction, strike and currency. Repeated
  same-contract executions support partial and aggregated stock deliveries.
  Account-owned premium allocations conserve the exact remainder and cannot be
  consumed twice, including a repeated partial delivery. Position flips preserve
  account and allocated quantities. Combined-account results match separate runs.
- Transfers retain distinct equal-size movements and both side identifiers.
  Reciprocal quantity/date detail must agree. Delivery and receipt are prepared
  by their owning ledgers; validation/sorting precede both state commits.
  Lot objects retain basis, dates, provenance and accrued Vorabpauschale.
- The original PM-005 reproduction passes all three standalone/combined cases.
  Thirty regression cases replayed on integration `0b1910e`: **28 failed, 2 passed**.
  Some failures concern newly required interfaces. The corrected set then passed
  all 30; three additional scheduler tests pass, and a repeated-partial-consumption
  test was independently red before its correction. Final focused total: **34**.
- Export inventory: 44 option exercise/assignment rows and 30 broker-STK delivery
  rows across 2021–2025. Zero missing account/date/transaction id, required option
  identity/strike/multiplier/quantity/currency, or stock id/price/quantity/currency
  in the respective rows. Some broker-STK instruments classify as funds and remain
  outside the existing stock-premium channel. No Transfers files are supplied.
- Current candidate runs complete VZ 2023–2025 with identical console and
  metadata-stripped PDF bytes. After midnight, accepted-main and control were
  recaptured: the previous PDF-only difference was the printed generation date,
  with identical page counts and all other extracted content.

Compatibility boundaries remain explicit: stock-only earlier acquisitions without
a supplied option event retain their existing warning/treatment (five existing
dividend-rights tests remain unchanged); fund-underlying and historical premium
treatment are not silently expanded. Sub-day transfer selection remains unsupported.
These are separate from the corrected matching/ownership defects, not new refusals.

Legal review used the existing GT-ESTG20-011/013/014/022 passages and GT-ESTG20-004
under the knowledge-store protocol: statutory gain/FX rules and BMF depot FIFO
remain distinct from the foreign-custody interpretation already recorded in Q2.
No rates, form mappings, assessment-year rules, reference claims or filing positions
were changed. The map now states the pre-existing assignment deviation honestly.

Disposition: final clean-checkout verification pending; not published or merged.

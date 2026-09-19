# Post-merge TODOs

Last updated: **2026-09-17**. This is the authoritative status list for accepted
follow-up work. Review, rebasing, correctness fixes and merge readiness belong in
[pr-train.md](pr-train.md). The originating PR's merge does not complete these items.

The four initial items were accepted with #86 and recorded in its
[merged rework document](https://github.com/uebber/ibkr-german-tax-declaration-engine/blob/8b7e49febcf1035d07391f9d52cfd40f0b0f9411/docs/reviews/pr-86-required-rework.md).
Use the IDs below for ongoing tracking; the old R1-R4 labels are aliases for the
same obligations, not additional TODOs.

| ID | Accepted from | Work | Status | Owner / intended follow-up | Closing evidence |
|---|---|---|---|---|---|
| PM-001 | #86 R1 | Account-scoped snapshot input | Open | Unassigned / not yet scheduled | None |
| PM-002 | #86 R2 | Separate instrument prices from holdings | Open | Unassigned / not yet scheduled | None |
| PM-003 | #86 R3 | Explicit currency boundaries | Open | Unassigned / not yet scheduled | None |
| PM-004 | #86 R4 | Behavioral boundary tests | Open | Unassigned / not yet scheduled | None |
| PM-005 | #87 PR87-P1; brought into #88 by the maintainer | Account-scoped option linking and premium adjustments | Done | #88, implementation `b8b5b11` | Original reproduction: 3 passed; account-pooling mutations: 8 linker failures / 1 premium-book failure; VZ 2023–2025 parity |
| PM-006 | #88 review; pre-existing behavior | Option premium tax treatment across assignment, historical replay and fund underlyings | Open | Separate figure-changing correction | Reference conflict recorded; correction and measured impact pending |

## PM-001 — Account-scoped snapshot input

**Affected components:** parsing output, pipeline, calculation entry points and
position diagnostics. Current snapshot dictionaries and optional arguments expose
storage details across these layers.

**Required result:** a cohesive typed input with account-local access, explicit
unavailable-versus-empty snapshot state, and routing owned by chronological
orchestration. Each ledger receives its own state. Aggregation for a declaration
does not require a Person domain entity or pooled lot calculations.

**Done when:** an account's opening/closing reconciliation cannot be changed by
another account's records; absent required input cannot masquerade as an empty
portfolio; callers and behavioral tests use the new boundary consistently.

## PM-002 — Separate instrument prices from holdings

**Affected components:** `PositionSnapshot`, parser price fallback, `fund_prices`
and Vorabpauschale inputs. Price resolution currently writes into each account's
snapshot and may create quantity-less rows solely to hold a price.

**Required result:** immutable reported holdings plus instrument-level price
results carrying currency, date, provenance and conflict/resolution state. Price
resolution does not enumerate or mutate account holdings.

**Done when:** midyear acquisition and an account first appearing after the opening
snapshot receive the correct price without a fabricated holding record. Existing
conflict-preservation and independent-resolution regressions continue to pass.

## PM-003 — Explicit currency boundaries

**Affected components:** snapshot ingestion, aggregate views and valuation.
Current aggregation assumes one quote currency for an instrument across accounts
and depends on earlier parser checks.

**Required result:** keep native observations with currency and perform explicit
valuation before summing monetary amounts. One account's calculation must not
depend on another account's quote currency. The interface accommodates future
non-IBKR counterpart accounts; implementing every external import now is not required.

**Done when:** valid account-local valuations remain independent, monetary sums
have a defined common currency, and unsupported mixed-currency inputs fail clearly.
Legal treatment and exchange-rate dates are verified against the knowledge store.

## PM-004 — Behavioral boundary tests

**Affected components:** snapshot/price test fixtures, pipeline wiring checks and
EOY assertions. Some checks inspect source strings; some fixtures keep mutable
module-global registries; some EOY assertions check reported rather than calculated state.

**Required result:** fixture-owned state, behavioral tests for data forwarding and
separate assertions for imported snapshots, calculated ledger positions and report inputs.

**Done when:** deliberately broken forwarding or ledger behavior causes a meaningful
test failure. Replace existing source checks only after demonstrating equivalent
coverage. The full suite passes without developer caches and with the maintainer's
data-dependent checks.

## PM-005 — Account-scoped option linking and premium adjustments

**Completed in #88's verified correction.** The original reproduction now passes
all three cases. New tests cover reversed/crossed stock-leg order, partial and
aggregated deliveries, all exercise/assignment directions, ambiguous contracts,
interleaved same-day exercises and exact single consumption of premiums. Combined
account results match separate runs; account-pooling mutations fail. The full
clean suite and VZ 2023–2025 parity pass. This closes stock-delivery ownership;
the separate pre-existing tax-treatment issues are PM-006.

**Origin and deferral:** [PR87-P1](pr-87-review.md), explicitly accepted as a TODO
by the maintainer on 2026-09-17. This defect predates #87 and reproduces on accepted
base and through #92. The observed combined-account case aborts; each account's
standalone run succeeds. It is not part of #87's corrective implementation.

**Affected components:** `src/processing/option_trade_linker.py`, the pending
option-premium adjustments shared by calculation/option/trade processors, and
their pipeline tests. The link key includes date, underlying contract and quantity
but omits account; duplicate keys overwrite one another.

**Required result:** account-local, unambiguous option-to-stock links and ownership
of premium adjustments. A stock delivery must not consume another account's
premium. Reject unresolved ambiguity instead of overwriting a candidate. Preserve
chronological execution, correct quantities, basis/proceeds and single consumption
of each adjustment.

**Done when:** simultaneous exercises/assignments with the same date, underlying
and delivery quantity work independently in two accounts; combined results agree
with the separate runs; different premiums and reversed row order cannot swap
attribution. Include ambiguous same-account inputs and exercise/assignment
directions. The reproduction in `pr-87-probes.py.txt` must pass for the right
reason, and mutations removing account isolation must fail meaningful assertions.
Verify tax consequences against the knowledge store and run the full suite plus
VZ 2023–2025 comparisons. The maintainer's current one-account exports cannot
exercise the cross-account collision.

## PM-006 — Pre-existing option premium tax treatment

**Origin:** discovered while verifying PM-005; [PR #88 review](pr-88-review.md).
Status: **Open**. This is separate from the completed stock-link ownership repair.

**Exposure and consequence:** assignment premiums are folded into stock basis or
proceeds; historical replay and fund-underlying premium handling differ from the
current stock channel. The assignment treatment conflicts with GT-ESTG20-004.
The maintainer's exports contain option assignments; matching current results
does not certify the existing tax treatment.

**Why separate:** correcting recognition dates and the separation of premiums
from stock gains requires one coherent tax-treatment change across opening,
closing, assignment, historical and fund paths, with measured effects on accepted
returns. #88 corrects ownership and ordering while leaving that treatment unchanged.
Its allocation boundary makes the follow-up easier and does not require retaining
the legacy formula. This deferral is not approval of the existing tax treatment.

**Milestone:** resolve before relying on affected option figures for a new filing.
**Done when:** requirements are grounded in the relevant reference passages;
receipt/closing/assignment and historical/current-year cases agree with them;
the map is honest; full verification and all supported real-data years are measured;
any changed figures receive the maintainer's explicit approval.

## Adding and closing work

- Add only bounded follow-up accepted under `review-criteria.md` or explicitly by
  the maintainer. Important findings may be deferred when the criteria establish
  that doing so is safe and economical; importance alone does not require another
  approval round. An unresolved substantive tradeoff still goes to the maintainer.
  Include originating PR/finding,
  rationale for deferral, affected components, intended result and completion evidence.
- Reuse an existing ID if a later review extends the same obligation. Link both reviews;
  do not create independent copies of one task.
- Statuses: **Open**, **In progress**, **Blocked**, **Done**. Blocked entries state the
  specific dependency. Done entries link the implementing PR/commit and verification.
- A later PR can satisfy an item, but record the actual evidence before marking it done.
  A title, claimed fix or merged originating PR is insufficient.
- Resolve legal consequences against `reference/` and its documented hierarchy. Run
  the applicable suite and real-data comparisons; record limitations and preserve private state.
- Keep correctness defects that prevent a safe merge in the PR train. Do not defer
  them here merely to permit merging.

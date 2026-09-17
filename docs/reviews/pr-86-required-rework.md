# Required architectural rework after PR #86

Agreed with the maintainer on 2026-09-17. PR #86 may be accepted once its
correctness fixes pass verification. These remaining changes are required follow-up
work; acceptance does not certify the original architecture as complete.

## Governing boundary

Accounts own independent ledger state. A coordinator processes events chronologically
and exchanges explicit lot deliveries/receipts, including reciprocal transfers within
one year. A transaction processor must not read or mutate another account's ledger.
The interfaces must accommodate eventual non-IBKR counterpart accounts without
requiring those account ledgers to exist in the engine.

There is no requirement for a `Person` entity. `person_snapshot()` and `person_mark()`
are legacy aggregate views used during the transition from pooled calculations.
Taxpayer-level assessment requires combining results at the declaration boundary;
it does not require pooling holdings or lots before account-specific calculations.
Shared instrument metadata and price data are separate from account holdings.

## Required items

| Item | Current coupling | Required result and acceptance evidence |
|---|---|---|
| R1: Account-scoped snapshot input | Parser-owned dictionaries and several optional snapshot parameters cross pipeline, calculation and diagnostic boundaries. | A cohesive typed input exposes account-local snapshots, distinguishes an unavailable snapshot from an empty one, and confines account routing to the coordinator. A test proves another account cannot affect this ledger's opening/closing reconciliation. |
| R2: Instrument prices separate from holdings | The parser fallback and `fund_prices` write a resolved price into every account's snapshot and may create quantity-less rows solely for prices. | Immutable reported holdings and a separate price result carrying currency, date, provenance and conflict/resolution status. Price resolution does not enumerate or modify holdings. Cover midyear acquisition and an account first appearing after the opening snapshot. |
| R3: Currency boundaries | Aggregation assumes one quote currency across every account holding an instrument; domain helpers rely on earlier parser validation. | Keep observations in their original currencies and value them explicitly before summing money. One account's valid valuation must not depend on another account's quote currency. Until external/mixed-currency input is supported, refuse it clearly. |
| R4: Behavioral boundary tests | Wiring assertions search source strings, and some fixtures use module-global snapshot registries. EOY fixture assertions read reported snapshots rather than calculated state. | Fixture-owned state and behavioral checks of forwarding, ledger results and report inputs. Assert reported and calculated positions separately; demonstrate a broken boundary causes failure before replacing its existing guard. |

FIFO isolation in #87 and transfer handling in #88 require their own reviews.
Independent state permits coordinated execution; it does not mean running each
account's entire year in isolation. An ordinary transfer interface does not imply
taxable sale treatment. Missing required acquisition data remains an error, with
only an explicit, recorded user override permitted if such a feature is later added.

## Completion gate

For each item, record the implementing PR, affected components and behavioral
evidence. Apply the knowledge store and its source hierarchy to all tax consequences.
Run the full suite and compare the maintainer's actual VZ 2023-2025 outputs using
isolated input/cache copies. Keep unresolved correctness findings out of this
post-merge list: they must be fixed before their PR is accepted.

# TODO: Implement Stock Merger FIFO Lot Transfer

## Problem

`MergerStockProcessor` in `src/engine/event_processors/corporate_action_processor.py` is a no-op.
It logs a warning but performs no ledger modifications, causing downstream sells of the
merged-into asset to fail with "Insufficient long lots".

## Affected Data (2022)

GZUR (DE000A1DCTL3) merged into SGBS (JE00B588CD74) on 2022-08-22, ratio 1:1.

Corporate_Actions-2022.csv has two rows (same ActionID 110634406):
- GZURd qty=-130 (dispose old shares)
- SGBS  qty=+130 (receive new shares)

The engine correctly parses this into a `CorpActionMergerStock` event but the processor
does nothing, so the subsequent sell of 130 SGBS fails (no FIFO lots).

## Required Implementation

The processor must:
1. Remove all FIFO lots from the source asset ledger (GZURd)
2. Create corresponding lots in the target asset ledger (SGBS) applying the merger ratio
3. Preserve original cost basis and acquisition dates (tax-neutral rollover)

The target ledger must be obtained from the calculation engine context since the processor
currently only receives the source asset's ledger.

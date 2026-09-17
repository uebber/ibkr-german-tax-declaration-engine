# PR review criteria

Agreed with the maintainer on 2026-09-17. These criteria apply to every PR in
the #86-#92 series, including work outside the multi-account feature.

Live review/merge work is in [pr-train.md](pr-train.md). Accepted follow-up work is
tracked separately in [post-merge-todos.md](post-merge-todos.md).

## Architecture

- Account state and ledgers are independent. An account's transaction processor
  must not inspect or mutate another account's internal state.
- IBKR's combined CSV format is an import concern. Translate it into explicit
  account inputs instead of spreading broker-specific account handling through
  every layer.
- Reciprocal transfers require coordinated chronological execution. Independence
  does not mean finishing each account's whole year separately.
- Transfers have a delivering side and a receiving side using ordinary transaction
  processing boundaries. Preserve lot identity, acquisition information, cost and
  provenance. An ordinary transaction interface does not imply sale tax treatment.
- The boundaries must accommodate eventual transfers to and from non-IBKR accounts;
  implementing those imports now is not required.
- Aggregate account results at the reporting/assessment boundary. Shared instrument
  metadata and market prices should not require access to account ledger internals.
- No separate Person entity is required. Taxpayer-level assessment does not justify
  pooling holdings or lots before account-specific calculations.
- Prefer clear responsibilities, coherent models, consistent invariants and bounded
  dependencies that remain understandable over time.

## Correctness and evidence

- Review each PR's incremental code, tests and documentation, plus its interactions
  with accepted predecessors against the GitHub base. The maintainer explicitly
  excluded local-branch integration as a gate; do not merge issue #76 work into the train.
- Before treating a finding as unresolved in the series, check later commits for
  a fix. Record the first fixing commit and rerun the reproduction; distinguish
  full resolution, partial resolution and a new guard that merely hides the case.
- Run the full suite. Inspect changed test expectations and add isolated diagnostic
  probes where the suite does not establish the required behavior.
- Check tax behavior against `reference/` and the hierarchy and nine-item validation
  protocol in `docs/knowledge-store.md`. A passing test, claim ID, implementation-map
  row or PR description is not sufficient proof of legal correctness.
- Distinguish primary law, administrative guidance, forms, case law and commentary;
  preserve applicable conditions and assessment years. Do not silently choose a
  disputed filing position. Verify newly added legal premises against their cited
  authorities when necessary; do not turn a PR review into an unrelated law audit.
- Missing data needed to value or date imported lots is an error. A user override
  may be designed explicitly, but must be recorded and must not silently invent data.
  This requirement applies even when the current exports do not trigger the gap.
- Validate against the maintainer's actual exports as well as synthetic cases.
  Contributor-reported runs are separate evidence. Use isolated copies and compare
  against the PR base with identical configuration/cache state, including a control
  run. Process real-data assessment years from 2023 onward; import earlier history
  where needed.
- Report unchanged pre-existing gaps separately from introduced defects. State what
  actual data cannot exercise. Never infer correctness solely from reconciliation.
- Keep account identifiers, actual monetary figures and private reports out of public
  review documents. Preserve original inputs, personal configuration and caches.

## Dispositions

1. **Accept:** no material correctness or architectural findings remain.
2. **Accept with required rework:** architecture is mostly sound and residual work is
   bounded and easily correctable. A required rework document must identify each
   deviation, intended design, affected components and verifiable completion criteria.
3. **Rework before merge:** correctness risks, silent acceptance of incomplete inputs,
   or coupling requiring substantial redesign must be addressed first.

Conduct a short architectural interview before each review where its particular
tradeoffs need clarification. The criteria already agreed above remain in force;
do not ask the maintainer to repeat them. Reviewing does not authorize merging,
posting GitHub reviews/comments, or changing the implementation.

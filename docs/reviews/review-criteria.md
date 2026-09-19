# PR review criteria

Agreed with the maintainer on 2026-09-17. These criteria apply to every PR in
the #86-#92 series and its corrective follow-ups. Apply the engineering gates in
`CLAUDE.md` to the relevant change category; this document does not weaken them.

Live review/merge work is in [pr-train.md](pr-train.md). Accepted follow-up work is
tracked separately in [post-merge-todos.md](post-merge-todos.md).

Merge a sound increment when its behavior is sufficiently verified and remaining
deficiencies are safe and economical to resolve later. Do not require each PR to
complete the entire target architecture. Do not use TODOs to rescue a fundamentally
unsound implementation. Judge code and evidence, not the contributor's background.

## Hard gate: the maintainer's real-data results

Every supported assessment year must complete and produce identical declared
figures to the accepted working baseline. Missing output, a new failure, or an
unexplained difference blocks merge. Compare report content as well; exclude only
volatile metadata or specifically approved presentation changes. Preserve ordering.

The only exception is a specific correction whose measured difference the maintainer
explicitly approves. Low probability, small amounts and cheaper later fixes cannot
waive this gate. General fix/merge permission and progress announcements are not
approval of a difference. Do not adopt changed results as the baseline merely because
they were merged. Never preserve a demonstrated legal error just to obtain parity;
present the required correction and its measured impact for decision.

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

## Initial quality assessment

- **Mostly sound:** coherent model, understandable data flow, credible tests and
  legal reasoning consistent with the store. Proceed toward merge; correct isolated
  blockers and defer suitable follow-up.
- **Sound direction with bounded deficiencies:** the core behavior works and the
  remaining boundary/test work is identifiable. Accept with required follow-up when
  the deferral conditions below hold.
- **Substantial rework needed:** the fundamental model is wrong, responsibilities
  are entangled, or repeated defects undermine confidence in the results. Hold the
  PR and produce one concise rework brief instead of patching symptoms indefinitely.

A missing account key may be an isolated correction. Account processors that depend
throughout on pooled ownership require a structural assessment. A pattern of related
failures may be one design defect, not a collection of economical small TODOs.

## Review sequence and evidence

- Review each PR's incremental code, tests and documentation, plus its interactions
  with accepted predecessors against the GitHub base. The maintainer explicitly
  excluded local-branch integration as a gate; do not merge issue #76 work into the train.
- Check the maintainer's data early, before optional edge-case investigation. Review
  the affected legal requirements, architectural boundaries and major test paths.
- For a concrete finding that may already be fixed later in the stack, inspect the
  relevant commits and rerun the reproduction. Distinguish complete resolution,
  partial resolution and a guard that only hides the case. Do not routinely execute
  every later branch's full suite.
- Inspect changed test expectations. Cover the normal path, important boundaries
  and material failures of new behavior, including scenarios absent from the actual
  exports. Passing one-account data does not establish a new multi-account feature.
- Use focused tests during correction and the full clean-clone suite on the final
  code candidate. Apply CLAUDE.md's category-specific probing and calibration gates;
  do not impose every category's gates on every PR or repeat adequate evidence.
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
  Contributor-reported runs are separate evidence. Use isolated copies and identical
  configuration/cache state. Process real-data assessment years from 2023 onward;
  import earlier history where needed. A same-tree control must establish that the
  comparison is reliable; reuse it and baseline captures while their source, inputs,
  configuration, dependencies and comparison environment remain applicable.
- Report unchanged pre-existing gaps separately from introduced defects. State what
  actual data cannot exercise. Never infer correctness solely from reconciliation.
- Apply CLAUDE.md's compatibility-regression gate: a supported real-data year that
  previously completed and now aborts is not a successful validation result. Establish
  the precise requirement and obtain explicit approval for the lost behavior before
  merge. General fix/merge authorization and progress announcements do not suffice;
  unrelated pre-existing gaps remain separate findings.
- Keep account identifiers, actual monetary figures and private reports out of public
  review documents. Preserve original inputs, personal configuration and caches.

Review the train as staged work. A transitional interface is not automatically a
defect: check whether the intermediate behavior is acceptable, whether later work
completes it, and whether the next PR would build on a defective foundation. Place
shared corrections where they can be made once without leaving unsafe intermediate
behavior. Previously agreed architectural decisions need no routine interview;
ask only about a material unresolved choice specific to the PR.

## Findings and economical deferral

Importance determines priority, not automatically whether a fix must precede this
merge. Important findings may be deferred when the current increment is acceptable
and postponement materially reduces implementation or verification cost. Record:

1. The affected scenario and consequence until correction, including actual exposure.
2. Why later is cheaper or better (for example, a later PR changes the same interface).
3. Why merging does not make correction harder or encourage dependent code to rely
   on the defective boundary.
4. The milestone/dependency before which it must be fixed, and a verifiable completion
   criterion. Reuse an existing PM entry where appropriate.

No occurrence in the actual exports supports this assessment but is not sufficient
alone. A TODO does not make unsafe behavior acceptable. Record unrelated pre-existing
defects separately; do not silently expand the current PR to fix them.

**Do not defer** a failed real-data gate, a newly introduced/worsened legal violation
in affected behavior, silent unsupported figures on a path accepted as supported,
a major architectural violation requiring substantial redesign, insufficient evidence
for the core behavior, or a foundation that makes later correction substantially
more expensive. Rarity does not override these conditions.

## Disposition, stopping point and record

1. **Accept:** no material correctness or architectural findings remain.
2. **Accept with required follow-up:** the increment is sound and remaining findings
   satisfy the deferral conditions, including important findings where economical.
3. **Rework before merge:** a non-deferrable finding remains or overall quality is
   insufficient. State the required result and its verification, not an endless
   list of symptoms.

Once evidence supports acceptance and no non-deferrable finding remains, conclude
the review. Extend investigation only for a named concern that could change that
disposition; do not keep searching for increasingly remote issues merely because
further investigation is possible.

Normally one short record states the base/head, overall quality assessment, tests,
real-data years/results, legal/architectural conclusion, approved differences,
remaining TODOs and disposition. Add detailed reproductions only where needed.
Record the merge commit after GitHub confirms it. Accepted follow-up stays open
until its completion evidence exists; merging the originating PR does not close it.

Proceed within existing authorization without another permission round. Return to
the maintainer for a substantive unresolved tradeoff, unacceptable quality, or work
outside that authorization. Review alone does not authorize implementation changes,
GitHub reviews/comments or merge; recorded plans do not grant that authority.

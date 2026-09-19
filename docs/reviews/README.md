# Review and maintenance handoff

Start here after context clearing. Last updated: 2026-09-17.

| Document | Purpose |
|---|---|
| [Review criteria](review-criteria.md) | Standing architectural, legal and verification requirements for every PR |
| [PR train](pr-train.md) | Active review, branch-update, correction and merge work for #86-#92 |
| [Post-merge TODOs](post-merge-todos.md) | Accepted architectural follow-up, tracked independently of PR merges |
| [PR #86 review](pr-86-review.md) | Findings, reproductions, later-commit checks and final resolution |
| [PR #88 review](pr-88-review.md) | Ordering, option delivery ownership, transfer corrections and final evidence |
| [PR #87 review](pr-87-review.md) | Rework-before-merge findings, later-commit checks and verified local candidate |

Current handoff: **#88 and PM-005 are corrected and verified locally** on
`review/pr88-transfers`, implementation `b8b5b11`, based on accepted main
`89e7c24`. The clean suite passes 1,327 tests with one export-dependent skip;
the export schema tests also pass with copied private data. VZ 2023–2025 complete
with identical console/PDF output. See [PR #88 review](pr-88-review.md).
Publishing and merge remain pending confirmation. PM-001–PM-004 remain open.
PM-005 is complete for the existing stock-delivery channel. Separate pre-existing
premium-tax-treatment gaps are recorded as PM-006. The local issue #76 source
has not been integrated.

The PR train is authoritative for review/merge status. The post-merge list is
authoritative for deferred-work status. Individual review documents contain the
supporting evidence; they do not maintain competing live TODO lists. The rework
document merged with #86 remains the historical acceptance record.

Temporary checkouts, virtual environments and private captures can be recreated;
they are not required to understand or resume the work. Do not put account data
or private report amounts into these documents. Application regression tests
from #86 are committed on `main` as `tests/test_snapshot_integrity.py`.

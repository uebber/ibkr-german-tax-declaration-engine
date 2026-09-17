# Review and maintenance handoff

Start here after context clearing. Last updated: 2026-09-17.

| Document | Purpose |
|---|---|
| [Review criteria](review-criteria.md) | Standing architectural, legal and verification requirements for every PR |
| [PR train](pr-train.md) | Active review, branch-update, correction and merge work for #86-#92 |
| [Post-merge TODOs](post-merge-todos.md) | Accepted architectural follow-up, tracked independently of PR merges |
| [PR #86 review](pr-86-review.md) | Findings, reproductions, later-commit checks and final resolution |
| [PR #87 review](pr-87-review.md) | Rework-before-merge findings, later-commit checks and verified local candidate |

Current handoff: **#86 is fixed and merged; #87's authorized corrections are
verified as `46aa37b` and awaiting publication/merge.** The pre-fix corrected-history
candidate is `0d5c958`. No rebase has been executed. PM-001 through PM-004 from
#86 remain open; option linking is explicitly deferred as PM-005.

The PR train is authoritative for review/merge status. The post-merge list is
authoritative for deferred-work status. Individual review documents contain the
supporting evidence; they do not maintain competing live TODO lists. The rework
document merged with #86 remains the historical acceptance record.

Temporary checkouts, virtual environments and private captures can be recreated;
they are not required to understand or resume the work. Do not put account data
or private report amounts into these documents. Application regression tests
from #86 are committed on `main` as `tests/test_snapshot_integrity.py`.

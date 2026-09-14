# Comparison scope

The source review was limited to the fixed writer-exclusion03 source set and the
qualified70 test source. No unrelated repository-wide dependency scan or package
execution was performed.

| Use | Current repair |
| --- | --- |
| FileIdentity dataclass | All six fields and ordinary equality stay unchanged. |
| OwnedWin32Primitives.identity | Same three metadata queries and final-path query; reparse/tag, pending-delete and negative-size refusals unchanged. |
| OwnedWin32Primitives.pin_exact_members | Only expected directories use same_directory_identity. Regular files retain full equality and single-link check. |
| Retained registry/snapshot ancestors | Directory-only comparison plus the original ownership, count and expected-path checks. `_check_scope` returns the retained expected identity; the later registry-root check is therefore not another comparison to mutable observed size. |
| Journal creation and transfer | Exact empty-file identity remains required; no size drift is accepted at creation. |
| Open journal stream | Existing bounded mutable journal size, stable file ID/path, single-link, append/readback/flush and poison rules remain. This is distinct from immutable asset checks. |
| Inherited read sets | Parent and child exact regular-file identities, expected lengths and fixed five-member descriptors unchanged. |
| PinnedBufferNamespace | Exact asset size before reading, bounded byte count/hash and complete before/after FileIdentity equality unchanged. |
| Generated fixture discovery and contender guard | Exact regular-file identity and sizes remain. Directory scopes use the repaired port. |
| Trusted ASR resolver | Separate stat/fstat identity and content-admission code remains unchanged. It does not use FileIdentity or this new helper. |

The new helper is not permission to accept an arbitrary path or replace a handle.
It compares only identities obtained under existing retained ownership. A malformed
size is still refused; a different valid size is allowed only when both identities
are exact FileIdentity directory records and their other five fields match.
Links and exact path spelling remain strict. No new native API is introduced.

All original70 assertions remain. The new cases add regular-file drift checks at
the actual primitive pin method and directory replacement checks at both affected
callers. The unchanged asset/descriptor source bindings substantiate that their
size checks were not generalized to the directory policy. Numerical/native/model
compatibility and restarted ownership are outside this source proposal.

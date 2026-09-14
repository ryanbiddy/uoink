# D2 draft reporting defect: stop before qualification

2026-09-13. Source review of the newly written D2 child found an inherited D1 field whose meaning is wrong for D2. This preparation has stopped before qualification, source activation or any artifact access. No frozen converter defect was found.

At d2_child.py:266, conversion_profile_activated is computed after the final cleanup from whether converter.REAL_PROFILE is still non-None. A successful D2 conversion temporarily activates that profile and clears it afterward, so the field would report false even though activation occurred. launch_d2.py also requires that false value. The underlying cleanup check is appropriate; the field label could misrepresent the recorded operation.

The narrow proposed correction is to rename it conversion_profile_active_at_exit in child and parent. Keep the actual invocation counter and conversion_result separate; report temporary conversion-profile use explicitly from the adapter operation, without treating an attempted invocation as a successful conversion. Keep all owner pins None. Do not change the frozen converter, fixed profile, D1 evidence or existing assertions to resolve this reporting defect.

The inherited forbidden_calls list is also unused in the new child after removal of D1's conversion traps. Its empty value should not be presented as proof that independent call traps ran. Remove that unused list/predicate/field from the new child and parent, while retaining the actual audit-event, heavy-import, metadata and registry checks. This is an instrumentation-claim correction, not permission to weaken an active guard.

These are new, unexecuted proposal defects. There is no failed test or native observation, and no outcome to relabel. The 23 new test methods are source only; their adapter fake-port scope does not qualify child/parent receipt semantics. Root should review this correction before preparation continues. Current new sources remain unchanged so their exact before bytes can be preserved for the later diff.

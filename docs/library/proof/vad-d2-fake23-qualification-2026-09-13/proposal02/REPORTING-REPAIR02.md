# D2 reporting correction before execution

2026-09-13. Root authorized this narrow source correction after reading the original defect note. Proposal01 remains unchanged. DRAFT01-ORIGINS.json binds its15 copied preparation files; before-reporting-repair retains both source files that change. No existing converter or test assertion changes.

Rename conversion_profile_activated to conversion_profile_active_at_exit. Add a child-owned wrapper around the frozen converter's real-file function to count actual calls and normal returns separately. A call count is an attempted file-conversion operation, not a successful result. conversion_result remains present only after the adapter validates the returned report. Require the counting wrapper's identity to remain intact; keep the actual converter bytes unchanged. The profile still resets in cleanup.

Remove the unused inherited forbidden_calls list and its always-empty claim. Preserve the existing content/audit, heavy-import, metadata and registry guards. Parent checks the same real guards plus the new call-wrapper integrity and exact successful-operation counts. Both parent and child retain owner pins None, as does the adapter. No actual owner decision or root admission is created.

The23 adapter fake-port cases remain byte-identical. They do not exercise the real parent/child or conversion wrapper and must not be credited as that qualification. The new fake-port runner will load only adapter/test definitions and four fixed text records, run those23 cases in memory, and keep actual converter, launch and model files inaccessible. It is an unexecuted source proposal awaiting root review.

The first patch tool call refused its patch terminator before applying changes. The next call supplies the required final newline; no source or test ran for that tooling correction.

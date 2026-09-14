# Generated journal normal-drain source review

2026-09-13. No blocking defect found in the added journal/create/flush scope at the hashes below. This is an independent source review before native admission. I read all 609 bootstrap lines, the complete setup helper, changed Windows port and launcher, the source map, protocol, bounds document and three source diffs. I also checked the connected creation, inheritance and retirement methods. No candidate, native operation, model or support binary was executed or opened.

The setup creates one journal with exclusive, non-inheritable `CREATE_NEW` access and retains its handle. The separate creation callback checks that exact empty owner; `stage_created_handle` transfers ownership without issuing evidence. `acquire` moves it into its retained attempt before further identity checks (port lines 241–317). The worker's explicit inheritance list comes from its five generated-member owners and one pipe owner; the journal and ancestor scopes are absent. The setup's two retained ancestor chains remain open until successful journal close (setup lines 37–79, 186–199).

The before-call milestones require confirmed RESERVED bytes and two flushes before process creation, WORKER_BOUND and the exact worker before resume, and CLEARED plus the actual retired-lifetime witness before journal close (setup lines 135–169). The latter witness requires the observed worker to be quiescent, its process/thread/job closed, its read set released and its pipe retired without pending operations. The outer checks the milestone indexes and four successful flushes, then compares the entire bounded closed journal with the confirmed bytes, hash and head (launcher lines 113–156).

API accounting is consistent: 33 dispatched functions, with `GetLastError` separate from that set. The outer expects 34 setup dispatches (33 binding casts and one module query), plus recorded API calls and the controller's single attribute-buffer cast. The child receives no flush or journal-creation permission. Two directory chains and the journal cost 72 identity queries per check; a guarded stream operation costs 145 calls. Empty/nonempty one-chunk reads cost 434/579 calls; the four full-transfer appends total 7,091. The 16,384-call ceiling and 1-MiB receipt cap are explicit prospective bounds, with no measured count claimed here.

Uncertain stream operations poison the journal and retain its owner. The existing 64-call/10-second cleanup reserve excludes journal work and directory closure. Both endpoints retain the outer pending-I/O finalizer; reporting failure cannot skip its current-process abort. Synchronous flush remains potentially blocking, and the receipt cap applies after serialization. These limitations are documented. The exclusive post-exit read demonstrates only the generated file's observed contents; power-loss durability, restart, writer-exclusion and failure scenarios remain separate observations.

Read-only check `b80ab2` (exit 0) verified all 17 source bindings and the false admission template. Nine support identities were compared as JSON records against the preserved origin; no support file was read. The original guard, source/control checks and durable global native-exit capture remain present. The already reported fake 70-case results provide no native acceptance through this review.

Exact SHA-256 bindings:

- `dummy_bootstrap.py`: `e0f424cfcdebfe93709a06eb135ed4d8a598ba704298b7a37d269a8f1f9c0b96`
- `generated_journal_setup.py`: `df7ed56cdcbd23352b3e69a6f6790a012182b294491f38f8ed19610f000b485d`
- `windows_reservation_port.py`: `dd33becb60e4302152179c4a41e4a2bf04d7d1a82bc3371461283688f3105a2e`
- `run_normal_drain01.ps1`: `b9c532a561e31afea34c47d4f060242d23f28fb5ece0eae102ae094a3eb4cb8e`
- `SOURCE-INPUTS.json`: `e4c15e6b414c36e9fe69346cc214bc7d5c7b4f5bf3808e3b165696066de11dcc`
